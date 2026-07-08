from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import Depends, HTTPException, status, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
import bcrypt
from bson import ObjectId

from config import settings
from database import get_users_collection, get_roles_collection
from models.org import UserResponse

class CustomBcryptContext:
    def verify(self, plain_password: str, hashed_password: str) -> bool:
        try:
            return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
        except Exception:
            return False

    def hash(self, password: str) -> str:
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

pwd_context = CustomBcryptContext()
from typing import Optional

security = HTTPBearer(auto_error=False)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRY_HOURS)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm="HS256")

def create_refresh_token(data: dict, jti: Optional[str] = None) -> str:
    import uuid
    from services.redis_client import redis_wrapper
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.JWT_REFRESH_EXPIRY_DAYS)
    token_jti = jti or str(uuid.uuid4())
    to_encode.update({"exp": expire, "type": "refresh", "jti": token_jti})
    
    user_id = data.get("sub")
    if user_id:
        redis_wrapper.set(
            f"active_refresh:{token_jti}", 
            str(user_id), 
            ex=int(settings.JWT_REFRESH_EXPIRY_DAYS * 86400)
        )
        
    return jwt.encode(to_encode, settings.JWT_REFRESH_SECRET, algorithm="HS256")

async def get_current_user(
    request: Request = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> dict:
    token = None
    if credentials:
        token = credentials.credentials
    elif request:
        token = request.query_params.get("token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization token is missing."
        )

    from services.redis_client import redis_wrapper
    if redis_wrapper.get(f"blocklist:{token}"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has been logged out. Please log in again."
        )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials or token expired"
        )

    users_col = get_users_collection()
    user = await users_col.find_one({"_id": ObjectId(user_id)})
    if not user:
        from database import get_patients_collection
        patients_col = get_patients_collection()
        patient = await patients_col.find_one({"_id": ObjectId(user_id), "is_deleted": {"$ne": True}})
        if patient:
            user = {
                "_id": patient["_id"],
                "name": f"{patient['first_name']} {patient['last_name']}",
                "email": patient.get("email", ""),
                "role": "patient",
                "tenant_id": patient["tenant_id"],
                "branch_id": patient["branch_id"],
                "is_active": True
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or suspended"
            )
    elif not user.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or suspended"
        )

    # Update last_active timestamp periodically (every 5 mins max write rate)
    if user.get("role") != "patient":
        last_act = user.get("last_active")
        if not last_act or (datetime.utcnow() - last_act).total_seconds() > 300:
            await users_col.update_one(
                {"_id": user["_id"]},
                {"$set": {"last_active": datetime.utcnow()}}
            )

    # Scoped SaaS subscription validation
    if user.get("tenant_id") and user.get("role") != "super_admin":
        from database import get_tenants_collection
        tenants_col = get_tenants_collection()
        tenant = await tenants_col.find_one({"_id": ObjectId(user["tenant_id"])})
        if tenant:
            status_val = tenant.get("status", "active")
            sub_end = tenant.get("subscription_end")
            
            is_expired = False
            if sub_end:
                if isinstance(sub_end, str):
                    try:
                        sub_end = datetime.fromisoformat(sub_end)
                    except:
                        pass
                if isinstance(sub_end, datetime) and sub_end < datetime.utcnow():
                    is_expired = True

            if status_val == "suspended" or is_expired:
                # Bypass billing check for saas/auth/payment paths to enable upgrade/login
                path = request.url.path if request else ""
                is_bypass = (
                    "/api/saas" in path or
                    "/api/org/plans" in path or
                    "/api/auth" in path or
                    "/api/payments/verify" in path
                )
                if not is_bypass:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Subscription suspended or expired. Please contact support or renew."
                    )

    return user

async def get_user_permissions(user: dict) -> List[str]:
    """Helper to fetch all active permissions for a user based on their role"""
    role_name = user.get("role")
    if role_name == "super_admin":
        return ["*"] # Wildcard permission
        
    roles_col = get_roles_collection()
    
    # Query matching role for this tenant
    role_doc = await roles_col.find_one({
        "name": role_name,
        "tenant_id": user.get("tenant_id")
    })
    
    if not role_doc:
        # Default global roles fallback mappings
        default_role_mappings = {
            "hospital_admin": ["manage_branches", "manage_staff", "manage_config", "view_queue", "manage_billing"],
            "branch_admin": ["manage_staff", "manage_config", "view_queue", "manage_billing"],
            "receptionist": ["register_patient", "book_appointment", "view_queue", "manage_billing"],
            "doctor": ["view_queue", "write_consultation", "view_patient_emr"],
            "nurse": ["view_queue", "record_vitals", "view_patient_emr"],
            "lab_technician": ["view_queue", "manage_labs"],
            "pharmacist": ["view_queue", "dispense_pharmacy"],
            "billing_staff": ["manage_billing", "view_queue"],
            "ot_coordinator": ["view_queue", "manage_ot"],
            "surgeon": ["view_queue", "write_consultation", "manage_ot"],
            "anesthetist": ["view_queue", "write_consultation", "manage_ot"],
            "patient": ["book_appointment", "view_queue"],
            "driver": ["view_queue"]
        }
        return default_role_mappings.get(role_name, [])
        
    return role_doc.get("permissions", [])

def require_permission(required_permission: str):
    """Enforces specific permission check against the user role profile"""
    async def dependency(current_user: dict = Depends(get_current_user)):
        permissions = await get_user_permissions(current_user)
        if "*" in permissions or required_permission in permissions:
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: missing permission '{required_permission}'"
        )
    return dependency

def require_role(allowed_roles: List[str]):
    """Enforces role profiles membership check"""
    async def dependency(current_user: dict = Depends(get_current_user)):
        if current_user.get("role") in allowed_roles or current_user.get("role") == "super_admin":
            return current_user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: unauthorized role profile"
        )
    return dependency

# ------------------------------------------------------------------
# SAAS TENANT AND BRANCH ISOLATION SCOPERS
# ------------------------------------------------------------------
def get_tenant_filter(current_user: dict, query: Optional[dict] = None) -> dict:
    """Modifies a query dictionary to automatically restrict access by the user's tenant_id, unless they are a super_admin."""
    if query is None:
        query = {}
    
    # Enforce logical deletion filter globally
    query["is_deleted"] = {"$ne": True}
    
    if current_user.get("role") == "super_admin":
        return query
        
    query["tenant_id"] = current_user.get("tenant_id")
    return query

def get_branch_filter(current_user: dict, query: Optional[dict] = None) -> dict:
    """Modifies a query dictionary to automatically restrict access by the user's tenant_id and branch_id, unless they are a super_admin or hospital_admin."""
    if query is None:
        query = {}
        
    # Enforce logical deletion filter globally
    query["is_deleted"] = {"$ne": True}
    
    if current_user.get("role") == "super_admin":
        return query
        
    query["tenant_id"] = current_user.get("tenant_id")
    
    # Restrict to branch if user is not hospital_admin
    if current_user.get("role") != "hospital_admin" and current_user.get("branch_id"):
        query["branch_id"] = current_user.get("branch_id")
        
    return query

def inject_audit_fields(current_user: dict, data: dict, is_create: bool = True) -> dict:
    """Injects tenant_id, branch_id, and audit stamps into data payloads before DB insertion/update."""
    now = datetime.utcnow()
    data["updated_at"] = now
    data["updated_by"] = str(current_user["_id"])
    
    if is_create:
        data["created_at"] = now
        data["created_by"] = str(current_user["_id"])
        data["is_deleted"] = False
        
        # Inject structural tenant scopes unless they're already set or user is super_admin
        if current_user.get("role") != "super_admin":
            data["tenant_id"] = current_user.get("tenant_id")
            if current_user.get("branch_id") and "branch_id" not in data:
                data["branch_id"] = current_user.get("branch_id")
                
    # Normalize PyObjectId instances back to ObjectId for Mongo compatibility
    for key in ["tenant_id", "hospital_id", "branch_id"]:
        if key in data and data[key] and not isinstance(data[key], ObjectId):
            try:
                data[key] = ObjectId(str(data[key]))
            except:
                pass
                
    return data
