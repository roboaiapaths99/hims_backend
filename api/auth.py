from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File
from jose import jwt, JWTError
from datetime import datetime, timedelta
import httpx
import os
import shutil
import uuid
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
        device_id=doc.get("device_id"),
        created_at=doc.get("created_at", datetime.utcnow())
    )

@router.post("/login")
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

    # Tenant scoping validation for staff/admins
    if user.get("role") != "super_admin" and credentials.tenant_id:
        if str(user.get("tenant_id")) != credentials.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email, password or selected organization."
            )

    # Device binding validation
    if user.get("role") != "super_admin" and credentials.device_id:
        current_device = user.get("device_id")
        if not current_device:
            # Bind the device
            await users_col.update_one(
                {"_id": user["_id"]},
                {"$set": {"device_id": credentials.device_id}}
            )
            user["device_id"] = credentials.device_id
        elif current_device != credentials.device_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This account is bound to another device. Please contact your hospital administrator to release the device binding."
            )
        
    user_id_str = str(user["_id"])
    
    # 2FA Enforcement Check
    if user.get("two_factor_enabled", False):
        otp = str(random.randint(100000, 999999))
        # Store in redis
        if redis_wrapper:
            redis_wrapper.set(f"2fa_otp:{user_id_str}", otp, ex=300)
            
        # Send SMS via MetaReach SMS Gateway
        phone = user.get("phone", "")
        if phone:
            from services.notification_service import NotificationService
            try:
                await NotificationService.send_sms_via_metareach(
                    phone_number=phone,
                    text=f"Welcome to AGPK Academy login. Your verification code is {otp}. This OTP will expire in 5 minutes",
                    tenant_id=user.get("tenant_id"),
                    branch_id=user.get("branch_id")
                )
            except Exception as e:
                print(f"Error dispatching 2FA SMS: {e}")
                
        masked_phone = f"******{phone[-4:]}" if len(phone) >= 4 else "registered number"
        return {
            "status": "mfa_required",
            "mfa_token": user_id_str,
            "message": f"Two-factor authentication code sent to {masked_phone}"
        }
    
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
    
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": serialize_user(user).dict()
    }

class Verify2FARequest(BaseModel):
    mfa_token: str
    code: str

class Toggle2FARequest(BaseModel):
    enabled: bool

@router.post("/verify-2fa")
async def verify_2fa(payload: Verify2FARequest, request: Request):
    """Verify the 2FA SMS code, issue final access & refresh tokens on success."""
    users_col = get_users_collection()
    
    try:
        user_oid = ObjectId(payload.mfa_token)
    except:
        raise HTTPException(status_code=400, detail="Invalid MFA token format")
        
    user = await users_col.find_one({"_id": user_oid})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Check stored code in Redis
    redis_key = f"2fa_otp:{payload.mfa_token}"
    stored_code = redis_wrapper.get(redis_key) if redis_wrapper else None
    
    is_bypass = settings.DEV_OTP_BYPASS and payload.code.strip() == "123456"
    if not is_bypass and (not stored_code or stored_code != payload.code.strip()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect or expired 2FA code. Please request a new one."
        )
        
    # Delete OTP from Redis
    if redis_wrapper:
        redis_wrapper.delete(redis_key)
        
    # Successful MFA - Issue tokens
    token_payload = {
        "sub": payload.mfa_token,
        "role": user["role"],
        "tenant_id": str(user["tenant_id"]) if user.get("tenant_id") else None,
        "branch_id": str(user["branch_id"]) if user.get("branch_id") else None
    }
    
    access = create_access_token(token_payload)
    refresh = create_refresh_token(token_payload)
    
    # Update login metrics
    await users_col.update_one(
        {"_id": user_oid},
        {"$set": {"last_login": datetime.utcnow(), "last_active": datetime.utcnow()}, "$inc": {"login_count": 1}}
    )
    
    # Log Audit
    await create_audit_log(
        user_id=payload.mfa_token,
        user_name=user["name"],
        action="USER_LOGIN_2FA_VERIFIED",
        entity="users",
        entity_id=payload.mfa_token,
        ip_address=request.client.host if request.client else None,
        tenant_id=user.get("tenant_id"),
        branch_id=user.get("branch_id")
    )
    
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": serialize_user(user).dict()
    }

@router.post("/toggle-2fa")
async def toggle_2fa(payload: Toggle2FARequest, request: Request, current_user: dict = Depends(get_current_user)):
    """Enable or disable Multi-Factor Authentication for the currently authenticated user."""
    users_col = get_users_collection()
    
    await users_col.update_one(
        {"_id": ObjectId(current_user["_id"])},
        {"$set": {"two_factor_enabled": payload.enabled, "updated_at": datetime.utcnow()}}
    )
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="USER_2FA_CONFIGURED",
        entity="users",
        entity_id=str(current_user["_id"]),
        details={"two_factor_enabled": payload.enabled},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user.get("tenant_id"),
        branch_id=current_user.get("branch_id")
    )
    
    return {"status": "success", "two_factor_enabled": payload.enabled}


@router.post("/patient/send-otp")
@limiter.limit("5/minute")
async def send_patient_otp(payload: dict, request: Request):
    phone = payload.get("phone")
    if not phone:
        raise HTTPException(status_code=400, detail="Mobile phone number is required.")
        
    # 1. Check temporary lockout (5 failures = 15 minute lock)
    failed_attempts = redis_wrapper.get(f"failed_attempts:{phone}")
    if failed_attempts and int(failed_attempts) >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed verification attempts. This mobile number is temporarily locked for 15 minutes."
        )

    # 2. Check resend cooldown (60 seconds)
    if redis_wrapper.get(f"cooldown:{phone}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Please wait 60 seconds before requesting a new verification code."
        )
    
    # Verify patient exists
    from database import get_patients_collection
    patients_col = get_patients_collection()
    patient = await patients_col.find_one({"phone": phone, "is_deleted": {"$ne": True}})
    if not patient:
        raise HTTPException(status_code=404, detail="No registered profile was found matching this mobile number. Please register first.")
        
    # Generate random 6-digit OTP
    otp = str(random.randint(100000, 999999))
    
    # Save to Redis with 5-minute expiry (300 seconds)
    redis_wrapper.set(f"otp:{phone}", otp, ex=300)
    # Set resend cooldown (60 seconds)
    redis_wrapper.set(f"cooldown:{phone}", "1", ex=60)
    
    sms_message = f"Welcome to AGPK Academy login. Your verification code is {otp}. This OTP will expire in 5 minutes"
    
    # Send SMS via MetaReach
    from services.notification_service import NotificationService
    sms_sent = await NotificationService.send_sms_via_metareach(
        phone_number=phone,
        text=sms_message,
        template_id=settings.METAREACH_TEMPLATE_ID,
        tenant_id=patient.get("tenant_id"),
        branch_id=patient.get("branch_id")
    )
    
    if not sms_sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to dispatch SMS verification code. Please check your SMS gateway credentials configuration."
        )
        
    return {"message": "Verification code dispatched successfully", "phone": phone}

@router.post("/patient/login-phone")
@limiter.limit("5/minute")
async def login_patient_phone(payload: dict, request: Request):
    phone = payload.get("phone")
    otp = payload.get("otp")
    
    if not phone or not otp:
        raise HTTPException(status_code=400, detail="Mobile number and verification OTP code are required.")
        
    # Check temporary lockout
    failed_attempts = redis_wrapper.get(f"failed_attempts:{phone}")
    if failed_attempts and int(failed_attempts) >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed verification attempts. This mobile number is temporarily locked for 15 minutes."
        )

    stored_otp = redis_wrapper.get(f"otp:{phone}")
    is_bypass = settings.DEV_OTP_BYPASS and otp == "123456"
    if not is_bypass and (not stored_otp or stored_otp != otp):
        # Increment failed attempts
        current_failed = redis_wrapper.get(f"failed_attempts:{phone}")
        new_failed = int(current_failed or 0) + 1
        redis_wrapper.set(f"failed_attempts:{phone}", str(new_failed), ex=900) # 15 minutes TTL
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"The verification code entered is invalid or has expired. Attempt {new_failed}/5"
        )
        
    # Consume the OTP and reset failures on successful verification
    redis_wrapper.delete(f"otp:{phone}")
    redis_wrapper.delete(f"failed_attempts:{phone}")
        
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
    gstin: str
    license_document_url: str
    office_address: str


@router.post("/register-hospital")
@limiter.limit("5/minute")
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
        "gstin": payload.gstin.strip().upper(),
        "license_document_url": payload.license_document_url.strip(),
        "office_address": payload.office_address.strip(),
        "is_verified_tenant": True,
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
        "address": payload.office_address.strip() or "Primary Location Address",
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
    abha_number: Optional[str] = None
    abha_address: Optional[str] = None
    consent_signed: Optional[bool] = False
    govt_id_type: Optional[str] = None
    govt_id_number: Optional[str] = None
    govt_id_document_url: Optional[str] = None


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
        "abha_number": payload.abha_number.strip() if payload.abha_number else None,
        "abha_address": payload.abha_address.strip() if payload.abha_address else None,
        "consent_signed": payload.consent_signed or False,
        "govt_id_type": payload.govt_id_type.strip() if payload.govt_id_type else None,
        "govt_id_number": payload.govt_id_number.strip() if payload.govt_id_number else None,
        "govt_id_document_url": payload.govt_id_document_url.strip() if payload.govt_id_document_url else None,
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


class PublicVerifyAbhaRequest(BaseModel):
    abha_number: str

class PublicConfirmAbhaRequest(BaseModel):
    abha_number: str
    otp: str
    transaction_id: str

@router.post("/public/abdm/verify")
async def public_verify_abha(payload: PublicVerifyAbhaRequest):
    # Clean input
    abha_clean = payload.abha_number.replace("-", "").strip()
    
    if settings.DEV_OTP_BYPASS:
        abha_sessions[abha_clean] = {
            "txn_id": "mock-txn-123456",
            "abha_number": payload.abha_number,
            "timestamp": datetime.utcnow()
        }
        return {
            "status": "success",
            "message": "OTP has been sent to your registered mobile number (MOCK MODE)",
            "transaction_id": "mock-txn-123456",
            "is_mock": True
        }

    token = await get_abdm_token()
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ABDM Identity Verification Gateway API credentials are not configured in system settings."
        )
        
    # Real ABDM Integration
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-CM-ID": "sbx"
    }
    
    init_url = f"{settings.ABDM_GATEWAY_URL}/v1/auth/init"
    init_payload = {
        "authMethod": "MOBILE_OTP",
        "healthid": payload.abha_number
    }
    
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(init_url, json=init_payload, headers=headers, timeout=10.0)
            if res.status_code != 200:
                raise HTTPException(status_code=res.status_code, detail=f"ABDM Gateway: {res.text}")
            data = res.json()
            txn_id = data.get("transactionId")
            
            abha_sessions[abha_clean] = {
                "txn_id": txn_id,
                "abha_number": payload.abha_number,
                "timestamp": datetime.utcnow()
            }
            return {
                "status": "success",
                "message": "OTP has been sent to your registered mobile number",
                "transaction_id": txn_id,
                "is_mock": False
            }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ABDM Gateway unreachable: {e}")

@router.post("/public/abdm/confirm")
async def public_confirm_abha(payload: PublicConfirmAbhaRequest):
    abha_clean = payload.abha_number.replace("-", "").strip()
    if settings.DEV_OTP_BYPASS:
        return {
            "status": "success",
            "message": "Aadhaar Identity verified successfully (MOCK MODE).",
            "patient_details": {
                "first_name": "Mock",
                "last_name": "Patient",
                "phone": abha_clean[-10:] if len(abha_clean) >= 10 else "9876543210",
                "dob": "1995-05-15",
                "gender": "Male",
                "address": "123 Mock Street, Delhi",
                "abha_address": f"{abha_clean}@sbx"
            }
        }

    token = await get_abdm_token()
    from api.abdm import abha_sessions
    session = abha_sessions.get(abha_clean)
    
    # OTP Length validation
    if len(payload.otp) != 6:
        raise HTTPException(status_code=400, detail="Invalid OTP length. Enter a 6-digit numeric OTP.")
        
    if not token or (session and "mock-txn" in session["txn_id"]):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ABDM Identity Verification Gateway API credentials are not configured in system settings."
        )
        
    # Real ABDM confirmation
    if not session:
        raise HTTPException(status_code=400, detail="No active verification request found for this ABHA number")
        
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-CM-ID": "sbx"
    }
    
    confirm_url = f"{settings.ABDM_GATEWAY_URL}/v1/auth/confirmWithMobileOTP"
    confirm_payload = {
        "otp": payload.otp,
        "transactionId": session["txn_id"]
    }
    
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(confirm_url, json=confirm_payload, headers=headers, timeout=10.0)
            if res.status_code != 200:
                raise HTTPException(status_code=res.status_code, detail=f"ABDM Verification Failed: {res.text}")
                
            confirm_data = res.json()
            user_profile = confirm_data.get("profile", {})
            
            raw_name = user_profile.get("name", "Verified Patient")
            name_parts = raw_name.split(" ", 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""
            
            raw_gender = user_profile.get("gender", "M")
            gender = "Male" if raw_gender.startswith("M") else "Female" if raw_gender.startswith("F") else "Other"
            
            # Format DOB (from DD-MM-YYYY to YYYY-MM-DD)
            dob_str = user_profile.get("dob", "2000-01-01")
            formatted_dob = dob_str
            try:
                dt = datetime.strptime(dob_str, "%d-%m-%Y")
                formatted_dob = dt.strftime("%Y-%m-%d")
            except:
                pass
                
            if abha_clean in abha_sessions:
                del abha_sessions[abha_clean]
                
            return {
                "status": "success",
                "message": "Identity verified successfully via Aadhaar KYC",
                "patient_details": {
                    "first_name": first_name,
                    "last_name": last_name,
                    "phone": user_profile.get("mobile", "7906681573"),
                    "dob": formatted_dob,
                    "gender": gender,
                    "address": user_profile.get("address", "ABDM Verified Address, India"),
                    "abha_number": user_profile.get("healthIdNumber", payload.abha_number),
                    "abha_address": user_profile.get("healthId", f"{abha_clean}@abdm")
                }
            }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"ABDM gateway error: {e}")


class PublicVerifyGstinRequest(BaseModel):
    gstin: str

@router.post("/public/gstin/verify")
async def public_verify_gstin(payload: PublicVerifyGstinRequest):
    # Regex validate GSTIN
    import re
    gstin_regex = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")
    gstin_upper = payload.gstin.strip().upper()
    if not gstin_regex.match(gstin_upper):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid GSTIN format. Must be 15 alphanumeric characters matching Indian GST registry specifications."
        )
        
    # Check if sandbox keys are set
    if not settings.SANDBOX_CO_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Hospital GSTIN Registry Verification API key is not configured in settings."
        )
        
    # Real Sandbox API Call
    url = f"https://api.sandbox.co.in/gsp/public/gstin/{gstin_upper}"
    headers = {
        "Authorization": settings.SANDBOX_CO_API_KEY,
        "x-api-key": settings.SANDBOX_CO_API_KEY,
        "Accept": "application/json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(url, headers=headers, timeout=10.0)
            if res.status_code != 200:
                raise HTTPException(
                    status_code=res.status_code,
                    detail=f"GSTIN Registry Gateway error: {res.text}"
                )
            
            data = res.json()
            # Parse standard Sandbox India response
            gstin_data = data.get("data", {})
            if not gstin_data:
                raise HTTPException(status_code=404, detail="GSTIN record not found in the national registry.")
                
            legal_name = gstin_data.get("lgnm", "Verified Medical Entity")
            trade_name = gstin_data.get("tradeNam", legal_name)
            gst_status = gstin_data.get("sts", "Active")
            
            pradr = gstin_data.get("pradr", {})
            addr_obj = pradr.get("addr", {})
            # Construct complete address
            addr_parts = [
                addr_obj.get("bno"), addr_obj.get("flno"), addr_obj.get("bnm"),
                addr_obj.get("st"), addr_obj.get("loc"), addr_obj.get("dst"),
                addr_obj.get("stcd"), addr_obj.get("pncd")
            ]
            address_str = ", ".join([p for p in addr_parts if p]) or "Registered GSTIN Address"
            
            return {
                "status": "success",
                "message": "GSTIN verified successfully",
                "data": {
                    "gstin": gstin_upper,
                    "legal_name": legal_name,
                    "trade_name": trade_name,
                    "status": gst_status,
                    "address": address_str
                }
            }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Indian GSTIN Registry communication failed: {str(e)}"
        )


class PublicTenantOtpRequest(BaseModel):
    phone: str

class PublicTenantVerifyOtpRequest(BaseModel):
    phone: str
    otp: str

@router.post("/public/tenant/send-otp")
@limiter.limit("5/minute")
async def send_tenant_otp(payload: PublicTenantOtpRequest, request: Request):
    phone = payload.phone.strip()
    if not phone or len(phone) != 10:
        raise HTTPException(status_code=400, detail="A valid 10-digit mobile phone number is required.")
        
    # Generate 6-digit random code
    otp = str(random.randint(100000, 999999))
    
    # Store in Redis (TTL: 300 seconds)
    redis_wrapper.set(f"tenant_otp:{phone}", otp, ex=300)
    
    sms_message = f"Welcome to AGPK Academy login. Your verification code is {otp}. This OTP will expire in 5 minutes"
    
    # Send SMS via MetaReach Gateway
    from services.notification_service import NotificationService
    sms_sent = await NotificationService.send_sms_via_metareach(
        phone_number=phone,
        text=sms_message,
        template_id=settings.METAREACH_TEMPLATE_ID
    )
    
    if not sms_sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to dispatch SMS verification code. Please check your SMS gateway credentials configuration."
        )
            
    return {"status": "success", "message": "Verification code sent successfully to admin mobile."}

@router.post("/public/tenant/verify-otp")
async def verify_tenant_otp(payload: PublicTenantVerifyOtpRequest):
    phone = payload.phone.strip()
    otp = payload.otp.strip()
    
    stored_otp = redis_wrapper.get(f"tenant_otp:{phone}")
    if not stored_otp:
        raise HTTPException(
            status_code=400,
            detail="Verification code expired or not requested. Please try sending a new one."
        )
        
    if stored_otp != otp:
        raise HTTPException(status_code=400, detail="Invalid verification code entered.")
        
    # Clean up Redis
    redis_wrapper.delete(f"tenant_otp:{phone}")
    return {"status": "success", "message": "Admin mobile number verified successfully."}


@router.post("/public/upload-license")
async def public_upload_license(file: UploadFile = File(...)):
    filename = file.filename or "unnamed_document"
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    
    # Allowed Document Extensions
    ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Only PDF, PNG, JPG, and JPEG document uploads are permitted."
        )
        
    # Max size check: 5MB
    try:
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
    except Exception:
        size = 0
        
    if size > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document size exceeds 5MB upload limit."
        )
        
    # Generate high-entropy filename
    unique_filename = f"license_{uuid.uuid4()}_{filename}"
    
    # Ensure folder exists
    os.makedirs("uploads", exist_ok=True)
    file_path = os.path.join("uploads", unique_filename)
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to write file locally: {str(e)}"
        )
        
    # S3 Upload
    from api.storage import get_s3_client
    s3_client = get_s3_client()
    file_url = f"/uploads/{unique_filename}"  # Fallback local access path
    
    if s3_client:
        try:
            s3_client.upload_file(file_path, settings.S3_BUCKET_NAME, unique_filename)
            os.remove(file_path)
            # Create a public or signed S3 url
            file_url = f"{settings.S3_ENDPOINT_URL}/{settings.S3_BUCKET_NAME}/{unique_filename}"
        except Exception as e:
            if os.path.exists(file_path):
                os.remove(file_path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed S3 secure upload: {str(e)}"
            )
            
    return {
        "status": "success",
        "message": "Clinical Establishment License uploaded successfully.",
        "url": file_url
    }


class AadhaarSendOtpRequest(BaseModel):
    aadhaar_number: str

class AadhaarVerifyOtpRequest(BaseModel):
    otp: str
    ref_id: str

def fuzzy_match_ratio(s1: str, s2: str) -> float:
    # Normalize strings: lowercase and remove extra whitespace
    str1 = " ".join(s1.lower().strip().split())
    str2 = " ".join(s2.lower().strip().split())
    
    if not str1 or not str2:
        return 0.0
    if str1 == str2:
        return 1.0
        
    # Levenshtein distance matrix calculation
    m, n = len(str1), len(str2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
        
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if str1[i - 1] == str2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
                
    distance = dp[m][n]
    max_len = max(m, n)
    similarity = (max_len - distance) / max_len
    return similarity


class GovtIdVerifyRequest(BaseModel):
    id_type: str  # PAN, VOTER_ID, DRIVING_LICENSE
    id_number: str
    legal_name: str

@router.post("/public/aadhaar/send-otp")
async def public_aadhaar_send_otp(payload: AadhaarSendOtpRequest):
    aadhaar_clean = "".join(filter(str.isdigit, payload.aadhaar_number))
    if len(aadhaar_clean) != 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Aadhaar number must be exactly 12 numeric digits."
        )
        
    if settings.DEV_OTP_BYPASS:
        return {
            "status": "success",
            "message": "OTP has been sent to Aadhaar-registered mobile number (MOCK MODE).",
            "ref_id": "mock-ref-123456"
        }
        
    if not settings.SANDBOX_CO_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Government Identity Verification Service API keys are not configured in system settings."
        )
        
    url = "https://api.sandbox.co.in/kyc/aadhaar/okyc/otp/request"
    headers = {
        "Authorization": settings.SANDBOX_CO_API_KEY,
        "x-api-key": settings.SANDBOX_CO_API_KEY,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    body = {"aadhaar_number": aadhaar_clean}
    
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(url, json=body, headers=headers, timeout=10.0)
            if res.status_code != 200:
                raise HTTPException(
                    status_code=res.status_code,
                    detail=f"Aadhaar Registry Gateway error: {res.text}"
                )
            
            data = res.json()
            ref_id = data.get("data", {}).get("ref_id")
            if not ref_id:
                raise HTTPException(status_code=400, detail="Failed to initialize Aadhaar OTP transaction.")
                
            return {
                "status": "success",
                "message": "OTP has been sent to Aadhaar-registered mobile number.",
                "ref_id": ref_id
            }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Aadhaar Registry Gateway unreachable: {str(e)}"
        )

@router.post("/public/aadhaar/verify-otp")
async def public_aadhaar_verify_otp(payload: AadhaarVerifyOtpRequest):
    if len(payload.otp) != 6:
        raise HTTPException(status_code=400, detail="Invalid OTP length. Enter a 6-digit numeric OTP.")
        
    if not settings.SANDBOX_CO_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Government Identity Verification Service API keys are not configured in system settings."
        )
        
    url = "https://api.sandbox.co.in/kyc/aadhaar/okyc/otp/verify"
    headers = {
        "Authorization": settings.SANDBOX_CO_API_KEY,
        "x-api-key": settings.SANDBOX_CO_API_KEY,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    body = {
        "otp": payload.otp,
        "ref_id": payload.ref_id
    }
    
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(url, json=body, headers=headers, timeout=15.0)
            if res.status_code != 200:
                raise HTTPException(
                    status_code=res.status_code,
                    detail=f"Aadhaar OTP verification failed: {res.text}"
                )
                
            data = res.json()
            profile = data.get("data", {})
            if not profile:
                raise HTTPException(status_code=400, detail="Aadhaar registry returned empty profile data.")
                
            raw_name = profile.get("name", "Verified Aadhaar User")
            name_parts = raw_name.split(" ", 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""
            
            raw_gender = profile.get("gender", "M")
            gender = "Male" if raw_gender.startswith("M") else "Female" if raw_gender.startswith("F") else "Other"
            
            # Format DOB (from DD-MM-YYYY or YYYY-MM-DD)
            dob_str = profile.get("dob", "2000-01-01")
            formatted_dob = dob_str
            try:
                dt = datetime.strptime(dob_str, "%d-%m-%Y")
                formatted_dob = dt.strftime("%Y-%m-%d")
            except:
                pass
                
            # Construct address
            addr = profile.get("split_address", {})
            addr_parts = [
                addr.get("house"), addr.get("street"), addr.get("landmark"),
                addr.get("loc"), addr.get("vtc"), addr.get("dist"),
                addr.get("state"), addr.get("pincode")
            ]
            address_str = ", ".join([p for p in addr_parts if p]) or profile.get("address", "Aadhaar Verified Address")
            
            return {
                "status": "success",
                "message": "Aadhaar Identity verified successfully.",
                "patient_details": {
                    "first_name": first_name,
                    "last_name": last_name,
                    "phone": profile.get("mobile_hash", ""),
                    "dob": formatted_dob,
                    "gender": gender,
                    "address": address_str
                }
            }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Aadhaar verification request failed: {str(e)}"
        )

@router.post("/public/govt-id/verify")
async def public_govt_id_verify(payload: GovtIdVerifyRequest):
    id_upper = payload.id_number.strip().upper()
    id_type = payload.id_type.upper()
    
    if not settings.SANDBOX_CO_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Government Identity Verification Service API keys are not configured in system settings."
        )
        
    headers = {
        "Authorization": settings.SANDBOX_CO_API_KEY,
        "x-api-key": settings.SANDBOX_CO_API_KEY,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            if id_type == "PAN":
                url = "https://api.sandbox.co.in/kyc/pan/verify"
                body = {"pan": id_upper}
                res = await client.post(url, json=body, headers=headers, timeout=10.0)
                if res.status_code != 200:
                    raise HTTPException(status_code=res.status_code, detail=f"PAN Gateway error: {res.text}")
                
                data = res.json()
                pan_data = data.get("data", {})
                if not pan_data:
                    raise HTTPException(status_code=404, detail="PAN record not found.")
                    
                full_name = pan_data.get("full_name", "Verified PAN User")
                if fuzzy_match_ratio(payload.legal_name, full_name) < 0.8:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Registry Name mismatch. The registry returns '{full_name}' which does not match your entered name '{payload.legal_name}'."
                    )
                    
                name_parts = full_name.split(" ", 1)
                first_name = name_parts[0]
                last_name = name_parts[1] if len(name_parts) > 1 else ""
                
                return {
                    "status": "success",
                    "message": "PAN Identity verified successfully.",
                    "patient_details": {
                        "first_name": first_name,
                        "last_name": last_name,
                        "dob": pan_data.get("dob") or "2000-01-01",
                        "gender": "Male"
                    }
                }
                
            elif id_type == "VOTER_ID":
                url = "https://api.sandbox.co.in/kyc/voterid/verify"
                body = {"epic_number": id_upper}
                res = await client.post(url, json=body, headers=headers, timeout=10.0)
                if res.status_code != 200:
                    raise HTTPException(status_code=res.status_code, detail=f"Voter ID Gateway error: {res.text}")
                    
                data = res.json()
                voter_data = data.get("data", {})
                if not voter_data:
                    raise HTTPException(status_code=404, detail="Voter ID record not found.")
                    
                full_name = voter_data.get("name", "Verified Voter")
                if fuzzy_match_ratio(payload.legal_name, full_name) < 0.8:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Registry Name mismatch. The registry returns '{full_name}' which does not match your entered name '{payload.legal_name}'."
                    )
                    
                name_parts = full_name.split(" ", 1)
                first_name = name_parts[0]
                last_name = name_parts[1] if len(name_parts) > 1 else ""
                
                raw_gender = voter_data.get("gender", "M")
                gender = "Male" if raw_gender.startswith("M") else "Female" if raw_gender.startswith("F") else "Other"
                
                return {
                    "status": "success",
                    "message": "Voter ID verified successfully.",
                    "patient_details": {
                        "first_name": first_name,
                        "last_name": last_name,
                        "gender": gender,
                        "address": voter_data.get("address", "Voter Registry Address")
                    }
                }
                
            elif id_type == "DRIVING_LICENSE":
                url = "https://api.sandbox.co.in/kyc/dl/verify"
                body = {"dl_number": id_upper}
                res = await client.post(url, json=body, headers=headers, timeout=10.0)
                if res.status_code != 200:
                    raise HTTPException(status_code=res.status_code, detail=f"DL Gateway error: {res.text}")
                    
                data = res.json()
                dl_data = data.get("data", {})
                if not dl_data:
                    raise HTTPException(status_code=404, detail="Driving License record not found.")
                    
                full_name = dl_data.get("name", "Verified DL User")
                if fuzzy_match_ratio(payload.legal_name, full_name) < 0.8:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Registry Name mismatch. The registry returns '{full_name}' which does not match your entered name '{payload.legal_name}'."
                    )
                    
                name_parts = full_name.split(" ", 1)
                first_name = name_parts[0]
                last_name = name_parts[1] if len(name_parts) > 1 else ""
                
                return {
                    "status": "success",
                    "message": "Driving License verified successfully.",
                    "patient_details": {
                        "first_name": first_name,
                        "last_name": last_name,
                        "dob": dl_data.get("dob") or "2000-01-01",
                        "address": dl_data.get("address", "DL Registry Address")
                    }
                }
                
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported fallback ID Type: {id_type}")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Identity verification lookup failed: {str(e)}"
        )




