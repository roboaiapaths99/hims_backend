from fastapi import APIRouter, Depends, HTTPException, status, Request
from jose import jwt, JWTError
from datetime import datetime, timedelta
from bson import ObjectId
import random
from pydantic import BaseModel

from config import settings
from database import get_users_collection, get_roles_collection, get_tenants_collection, get_branches_collection
from middleware.auth import (
    verify_password, get_password_hash, create_access_token, 
    create_refresh_token, get_current_user
)
from middleware.audit import create_audit_log
from middleware.rate_limit import limiter
from services.redis_client import redis_wrapper
from tasks import send_otp_notification
from models.org import UserLogin, TokenResponse, UserResponse, UserCreate

router = APIRouter()

def serialize_user(doc) -> UserResponse:
    return UserResponse(
        id=str(doc["_id"]),
        name=doc["name"],
        email=doc["email"],
        role=doc["role"],
        is_active=doc.get("is_active", True),
        tenant_id=str(doc["tenant_id"]) if doc.get("tenant_id") else None,
        hospital_id=str(doc["hospital_id"]) if doc.get("hospital_id") else None,
        branch_id=str(doc["branch_id"]) if doc.get("branch_id") else None,
        created_at=doc.get("created_at", datetime.utcnow())
    )

@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login_user(credentials: UserLogin, request: Request):
    users_col = get_users_collection()
    user = await users_col.find_one({"email": credentials.email})
    
    if not user or not verify_password(credentials.password, user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
        
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your account is currently inactive. Please contact the hospital administration."
        )
        
    user_id_str = str(user["_id"])
    
    # Generate tokens
    token_payload = {
        "sub": user_id_str,
        "role": user["role"],
        "tenant_id": str(user["tenant_id"]) if user.get("tenant_id") else None,
        "branch_id": str(user["branch_id"]) if user.get("branch_id") else None
    }
    
    access = create_access_token(token_payload)
    refresh = create_refresh_token(token_payload)
    
    # Update last login, login count and active states
    await users_col.update_one(
        {"_id": user["_id"]},
        {"$set": {"last_login": datetime.utcnow(), "last_active": datetime.utcnow()}, "$inc": {"login_count": 1}}
    )
    
    # Log Audit
    await create_audit_log(
        user_id=user_id_str,
        user_name=user["name"],
        action="USER_LOGIN",
        entity="users",
        entity_id=user_id_str,
        ip_address=request.client.host if request.client else None,
        tenant_id=user.get("tenant_id"),
        branch_id=user.get("branch_id")
    )
    
    return TokenResponse(
        access_token=access,
        refresh_token=refresh,
        user=serialize_user(user)
    )

@router.post("/patient/send-otp")
@limiter.limit("5/minute")
async def send_patient_otp(payload: dict, request: Request):
    phone = payload.get("phone")
    if not phone:
        raise HTTPException(status_code=400, detail="Mobile phone number is required.")
    
    # Verify patient exists
    from database import get_patients_collection
    patients_col = get_patients_collection()
    patient = await patients_col.find_one({"phone": phone, "is_deleted": {"$ne": True}})
    if not patient:
        raise HTTPException(status_code=404, detail="No registered profile was found matching this mobile number. Please register first.")
        
    # Generate random 6-digit OTP
    otp = str(random.randint(100000, 999999))
    
    # Save to Redis with 5-minute expiry
    redis_wrapper.set(f"otp:{phone}", otp, ex=300)
    
    # Queue background notification task
    try:
        send_otp_notification.delay(phone, otp)
    except Exception as e:
        print(f"Error queueing OTP: {e}. Executing inline.")
        from tasks import process_otp_notification
        import asyncio
        asyncio.create_task(process_otp_notification(phone, otp))
        
    return {"message": "Verification code dispatched successfully", "phone": phone}

@router.post("/patient/login-phone")
@limiter.limit("5/minute")
async def login_patient_phone(payload: dict, request: Request):
    phone = payload.get("phone")
    otp = payload.get("otp")
    
    if not phone or not otp:
        raise HTTPException(status_code=400, detail="Mobile number and verification OTP code are required.")
        
    # Dev mode fallback
    is_dev_bypass = settings.ENVIRONMENT == "development" and otp == "1234"
    
    if not is_dev_bypass:
        stored_otp = redis_wrapper.get(f"otp:{phone}")
        if not stored_otp or stored_otp != otp:
            raise HTTPException(status_code=401, detail="The verification code entered is invalid or has expired. Please request a new one.")
        # Consume the OTP
        redis_wrapper.delete(f"otp:{phone}")
        
    from database import get_patients_collection
    patients_col = get_patients_collection()
    patient = await patients_col.find_one({"phone": phone, "is_deleted": {"$ne": True}})
    if not patient:
        raise HTTPException(status_code=404, detail="No registered profile was found matching this mobile number.")
        
    patient_id_str = str(patient["_id"])
    
    # Generate token
    token_payload = {
        "sub": patient_id_str,
        "role": "patient",
        "tenant_id": str(patient["tenant_id"]),
        "branch_id": str(patient["branch_id"])
    }
    access = create_access_token(token_payload)
    
    return {
        "access_token": access,
        "patient": {
            "id": patient_id_str,
            "first_name": patient["first_name"],
            "last_name": patient["last_name"],
            "mrn": patient["mrn"],
            "phone": patient["phone"],
            "tenant_id": str(patient["tenant_id"]),
            "branch_id": str(patient["branch_id"])
        }
    }

@router.post("/refresh")
async def refresh_access_token(payload: dict):
    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="Session refresh token is missing.")
        
    try:
        token_data = jwt.decode(refresh_token, settings.JWT_REFRESH_SECRET, algorithms=["HS256"])
        if token_data.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid session token type.")
        user_id = token_data.get("sub")
        jti = token_data.get("jti")
    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Your session has expired. Please log in again."
        )
        
    from services.redis_client import redis_wrapper
    
    # 1. Replay attack detection
    if jti:
        if redis_wrapper.get(f"used_refresh:{jti}"):
            # Replay attack: Revoke all active refresh tokens for this user
            active_keys = redis_wrapper.keys("active_refresh:*")
            for key in active_keys:
                stored_uid = redis_wrapper.get(key)
                if stored_uid == user_id:
                    redis_wrapper.delete(key)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Refresh token reuse detected! All active sessions for this user have been terminated."
            )
            
        # 2. Check if active
        if not redis_wrapper.get(f"active_refresh:{jti}"):
            raise HTTPException(status_code=401, detail="The session refresh token is invalid or has been revoked.")
            
        # Revoke the used token and mark as used
        redis_wrapper.delete(f"active_refresh:{jti}")
        redis_wrapper.set(f"used_refresh:{jti}", user_id, ex=int(settings.JWT_REFRESH_EXPIRY_DAYS * 86400))
        
    users_col = get_users_collection()
    user = await users_col.find_one({"_id": ObjectId(user_id)})
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=401, detail="Your staff account is inactive. Please contact the system support desk.")
        
    # Generate new tokens
    token_payload = {
        "sub": str(user["_id"]),
        "role": user["role"],
        "tenant_id": str(user["tenant_id"]) if user.get("tenant_id") else None,
        "branch_id": str(user["branch_id"]) if user.get("branch_id") else None
    }
    
    access = create_access_token(token_payload)
    new_refresh = create_refresh_token(token_payload)
    
    return {
        "access_token": access,
        "refresh_token": new_refresh,
        "token_type": "bearer"
    }

@router.post("/logout")
async def logout_user(
    request: Request,
    payload: dict,
    current_user: dict = Depends(get_current_user)
):
    auth_header = request.headers.get("Authorization")
    access_token = None
    if auth_header and auth_header.startswith("Bearer "):
        access_token = auth_header.split(" ")[1]
        
    refresh_token = payload.get("refresh_token")
    from services.redis_client import redis_wrapper
    
    # 1. Blocklist the access token
    if access_token:
        redis_wrapper.set(f"blocklist:{access_token}", "logged_out", ex=int(settings.JWT_EXPIRY_HOURS * 3600))
        
    # 2. Revoke the refresh token
    if refresh_token:
        try:
            token_data = jwt.decode(refresh_token, settings.JWT_REFRESH_SECRET, algorithms=["HS256"])
            jti = token_data.get("jti")
            if jti:
                redis_wrapper.delete(f"active_refresh:{jti}")
        except:
            pass
            
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="USER_LOGOUT",
        entity="users",
        entity_id=str(current_user["_id"]),
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user.get("tenant_id"),
        branch_id=current_user.get("branch_id")
    )
    
    return {"message": "Successfully logged out and session invalidated"}

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return serialize_user(current_user)

@router.post("/bootstrap")
@limiter.limit("1/hour")
async def bootstrap_superadmin(request: Request):
    """Bootstrap a default platform super admin if no users exist in the database."""
    if settings.ENVIRONMENT == "production":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bootstrap is disabled in production environments"
        )
        
    users_col = get_users_collection()
    existing_users_count = await users_col.count_documents({})
    
    if existing_users_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="System is already bootstrapped. Bootstrap is disabled."
        )
        
    superadmin_doc = {
        "name": "Platform Super Admin",
        "email": "superadmin@hmis.com",
        "password_hash": get_password_hash("superadmin123"),
        "role": "super_admin",
        "is_active": True,
        "tenant_id": None,
        "hospital_id": None,
        "branch_id": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    res = await users_col.insert_one(superadmin_doc)
    return {
        "message": "Super Admin bootstrapped successfully",
        "email": "superadmin@hmis.com",
        "user_id": str(res.inserted_id)
    }

class RegisterPushTokenRequest(BaseModel):
    token: str

@router.post("/register-push-token")
async def register_push_token(
    payload: RegisterPushTokenRequest,
    current_user: dict = Depends(get_current_user)
):
    from database import get_db
    db = get_db()
    
    user_id = current_user["_id"]
    role = current_user.get("role")
    
    if role == "patient":
        col = db.patients
    else:
        col = db.users
        
    await col.update_one(
        {"_id": user_id},
        {"$set": {"expo_push_token": payload.token, "updated_at": datetime.utcnow()}}
    )
    
    return {"status": "success", "message": "Expo push token registered successfully"}


class HospitalRegistrationRequest(BaseModel):
    hospital_name: str
    subdomain: str
    admin_name: str
    admin_email: str
    admin_password: str
    admin_phone: str
    plan_id: str = "free_trial"


@router.post("/register-hospital")
async def register_hospital(payload: HospitalRegistrationRequest, request: Request):
    """Registers a new hospital tenant, establishes a MAIN branch, and provisions a hospital admin account."""
    tenants_col = get_tenants_collection()
    branches_col = get_branches_collection()
    users_col = get_users_collection()

    # 1. Check if subdomain already exists
    normalized_subdomain = payload.subdomain.strip().lower()
    existing_tenant = await tenants_col.find_one({"subdomain": normalized_subdomain})
    if existing_tenant:
        raise HTTPException(
            status_code=400,
            detail="This hospital subdomain name is already registered."
        )

    # 2. Check if admin email already exists
    existing_user = await users_col.find_one({"email": payload.admin_email.strip().lower()})
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="This email address is already registered as a hospital administrator."
        )

    # 3. Create tenant
    tenant_oid = ObjectId()
    tenant_doc = {
        "_id": tenant_oid,
        "name": payload.hospital_name.strip(),
        "subdomain": normalized_subdomain,
        "plan_id": payload.plan_id,
        "subscription_status": "trialing",
        "subscription_start": datetime.utcnow(),
        "subscription_end": datetime.utcnow() + timedelta(days=14),  # 14-day free trial
        "max_branches": 1,
        "max_staff": 5,
        "max_patients": 100,
        "status": "active",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    await tenants_col.insert_one(tenant_doc)

    # 4. Create default Main Branch
    branch_oid = ObjectId()
    branch_doc = {
        "_id": branch_oid,
        "name": f"{payload.hospital_name.strip()} Main Branch",
        "code": "MAIN",
        "address": "Primary Location Address",
        "contact_number": payload.admin_phone.strip(),
        "tenant_id": tenant_oid,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    await branches_col.insert_one(branch_doc)

    # 5. Create Hospital Admin user
    admin_oid = ObjectId()
    admin_doc = {
        "_id": admin_oid,
        "name": payload.admin_name.strip(),
        "email": payload.admin_email.strip().lower(),
        "password_hash": get_password_hash(payload.admin_password),
        "role": "hospital_admin",
        "is_active": True,
        "tenant_id": tenant_oid,
        "branch_id": branch_oid,
        "phone": payload.admin_phone.strip(),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    await users_col.insert_one(admin_doc)

    # 6. Generate access token to auto-login
    token_payload = {
        "sub": str(admin_oid),
        "role": "hospital_admin",
        "tenant_id": str(tenant_oid),
        "branch_id": str(branch_oid)
    }
    access = create_access_token(token_payload)
    refresh = create_refresh_token(token_payload)

    await create_audit_log(
        user_id=str(admin_oid),
        user_name=payload.admin_name,
        action="TENANT_REGISTERED",
        entity="tenants",
        entity_id=str(tenant_oid),
        ip_address=request.client.host if request.client else None,
        tenant_id=tenant_oid,
        branch_id=branch_oid
    )

    return {
        "status": "success",
        "message": "Hospital registered successfully.",
        "access_token": access,
        "refresh_token": refresh,
        "user": {
            "id": str(admin_oid),
            "name": payload.admin_name,
            "email": payload.admin_email,
            "role": "hospital_admin",
            "tenant_id": str(tenant_oid),
            "branch_id": str(branch_oid)
        }
    }


from typing import List, Optional

class PublicBranchResponse(BaseModel):
    id: str
    name: str
    code: str

class PublicHospitalResponse(BaseModel):
    id: str
    name: str
    subdomain: str
    branches: List[PublicBranchResponse]

class PatientRegisterRequest(BaseModel):
    first_name: str
    last_name: str
    phone: str
    email: Optional[str] = None
    dob: str  # YYYY-MM-DD
    gender: str
    address: str
    emergency_contact_name: str
    emergency_contact_phone: str
    tenant_id: str
    branch_id: str


@router.get("/public/hospitals", response_model=List[PublicHospitalResponse])
async def list_public_hospitals():
    tenants_col = get_tenants_collection()
    branches_col = get_branches_collection()
    
    # Get active tenants
    tenants = await tenants_col.find({"status": "active"}).to_list(None)
    
    result = []
    for tenant in tenants:
        tenant_id = tenant["_id"]
        # Get branches for this tenant
        branches = await branches_col.find({"tenant_id": tenant_id}).to_list(None)
        
        branch_responses = [
            PublicBranchResponse(
                id=str(b["_id"]),
                name=b["name"],
                code=b.get("code", "MAIN")
            )
            for b in branches
        ]
        
        result.append(
            PublicHospitalResponse(
                id=str(tenant_id),
                name=tenant["name"],
                subdomain=tenant["subdomain"],
                branches=branch_responses
            )
        )
    return result


@router.post("/patient/register")
async def register_patient(payload: PatientRegisterRequest, request: Request):
    from database import get_patients_collection
    from api.patient import generate_patient_mrn
    
    patients_col = get_patients_collection()
    tenants_col = get_tenants_collection()
    branches_col = get_branches_collection()
    
    # 1. Validate tenant and branch format
    try:
        tenant_oid = ObjectId(payload.tenant_id)
        branch_oid = ObjectId(payload.branch_id)
    except Exception:
        raise HTTPException(status_code=400, detail="The selected hospital or branch identifier is invalid.")
        
    # 2. Check if tenant exists and is active
    tenant = await tenants_col.find_one({"_id": tenant_oid, "status": "active"})
    if not tenant:
        raise HTTPException(status_code=404, detail="The selected hospital is currently inactive or unavailable.")
        
    # 3. Check if branch exists
    branch = await branches_col.find_one({"_id": branch_oid, "tenant_id": tenant_oid})
    if not branch:
        raise HTTPException(status_code=404, detail="The selected hospital branch could not be found.")
        
    # 4. Check duplicate patient phone number under the same tenant
    existing = await patients_col.find_one({
        "phone": payload.phone,
        "tenant_id": tenant_oid,
        "is_deleted": {"$ne": True}
    })
    if existing:
        raise HTTPException(
            status_code=400,
            detail="This mobile number is already registered with this hospital. Please sign in to your existing account."
        )
        
    # 5. Parse date of birth
    try:
        dob_dt = datetime.strptime(payload.dob, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Date of birth must be a valid date in YYYY-MM-DD format.")
        
    # 6. Generate MRN
    mrn = await generate_patient_mrn(tenant_oid, branch_oid)
    
    # 7. Create patient document
    patient_doc = {
        "first_name": payload.first_name.strip(),
        "last_name": payload.last_name.strip(),
        "phone": payload.phone.strip(),
        "email": payload.email.strip().lower() if payload.email else None,
        "dob": dob_dt,
        "gender": payload.gender,
        "blood_group": None,
        "address": payload.address.strip(),
        "emergency_contact_name": payload.emergency_contact_name.strip(),
        "emergency_contact_phone": payload.emergency_contact_phone.strip(),
        "photo_url": None,
        "abha_number": None,
        "abha_address": None,
        "consent_signed": False,
        "mrn": mrn,
        "tenant_id": tenant_oid,
        "branch_id": branch_oid,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "is_deleted": False
    }
    
    res = await patients_col.insert_one(patient_doc)
    patient_id_str = str(res.inserted_id)
    
    # 8. Generate JWT Access Token to log them in automatically
    token_payload = {
        "sub": patient_id_str,
        "role": "patient",
        "tenant_id": str(tenant_oid),
        "branch_id": str(branch_oid)
    }
    access = create_access_token(token_payload)
    
    # Log Audit
    await create_audit_log(
        user_id=patient_id_str,
        user_name=f"{payload.first_name} {payload.last_name}",
        action="PATIENT_SELF_REGISTERED",
        entity="patients",
        entity_id=patient_id_str,
        ip_address=request.client.host if request.client else None,
        tenant_id=tenant_oid,
        branch_id=branch_oid
    )
    
    return {
        "access_token": access,
        "patient": {
            "id": patient_id_str,
            "first_name": payload.first_name,
            "last_name": payload.last_name,
            "mrn": mrn,
            "phone": payload.phone,
            "tenant_id": str(tenant_oid),
            "branch_id": str(branch_oid)
        }
    }



