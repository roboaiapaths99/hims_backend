from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime
from bson import ObjectId
from models.base import PyObjectId, TenantScopedModel

# Tenant Models
class TenantBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    subdomain: str = Field(..., min_length=2, max_length=50)
    contact_email: EmailStr
    status: str = Field(default="active")  # active, suspended, unpaid

    # SaaS Subscription Settings
    plan_id: str = Field(default="free_trial")
    subscription_status: str = Field(default="trialing")  # trialing, active, suspended, canceled
    subscription_start: Optional[datetime] = None
    subscription_end: Optional[datetime] = None
    billing_interval: Optional[str] = "month"  # month, year

    # Resource Quotas
    max_branches: int = Field(default=1)
    max_staff: int = Field(default=5)
    max_patients: int = Field(default=100)
    
    # Gateways Specific Subscription Ids
    stripe_subscription_id: Optional[str] = None
    razorpay_subscription_id: Optional[str] = None

class TenantCreate(TenantBase):
    pass

class TenantUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    plan_id: Optional[str] = None
    subscription_status: Optional[str] = None
    subscription_start: Optional[datetime] = None
    subscription_end: Optional[datetime] = None
    billing_interval: Optional[str] = None
    max_branches: Optional[int] = None
    max_staff: Optional[int] = None
    max_patients: Optional[int] = None
    stripe_subscription_id: Optional[str] = None
    razorpay_subscription_id: Optional[str] = None

class TenantResponse(TenantBase):
    id: str

    class Config:
        from_attributes = True

# Branch Models
class BranchBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    code: str = Field(..., min_length=2, max_length=10) # e.g. DEL, NOI
    address: str
    contact_number: str

class BranchCreate(BranchBase):
    tenant_id: str

class BranchResponse(BranchBase):
    id: str
    tenant_id: str
    logo_url: Optional[str] = None

    class Config:
        from_attributes = True

class BranchProfile(BaseModel):
    name: str
    code: str
    address: str
    contact_number: str
    gst_number: Optional[str] = None
    logo_url: Optional[str] = None
    letterhead_text: Optional[str] = None

# Role Models
class RoleBase(BaseModel):
    name: str
    permissions: List[str] = Field(default_factory=list)

class RoleCreate(RoleBase):
    tenant_id: str

class RoleResponse(RoleBase):
    id: str
    tenant_id: str

    class Config:
        from_attributes = True

# User / Staff Models
class UserBase(BaseModel):
    name: str
    email: EmailStr
    role: str # super_admin, hospital_admin, branch_admin, doctor, nurse, lab_technician, pharmacist, billing_staff, ot_coordinator, surgeon, anesthetist, patient
    is_active: bool = True

class UserCreate(UserBase):
    password: str = Field(..., min_length=6)
    tenant_id: Optional[str] = None
    hospital_id: Optional[str] = None
    branch_id: Optional[str] = None
    device_id: Optional[str] = None

class UserUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    role: Optional[str] = None
    branch_id: Optional[str] = None

class UserResponse(UserBase):
    id: str
    tenant_id: Optional[str] = None
    hospital_id: Optional[str] = None
    branch_id: Optional[str] = None
    device_id: Optional[str] = None
    created_at: datetime
    last_login: Optional[datetime] = None
    login_count: Optional[int] = 0
    last_active: Optional[datetime] = None

    class Config:
        from_attributes = True

class UserLogin(BaseModel):
    email: EmailStr
    password: str
    tenant_id: Optional[str] = None
    device_id: Optional[str] = None

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse

class CustomPaymentMethod(BaseModel):
    id: str
    name: str
    payment_type: str  # offline, online_gateway, qr_code
    is_active: bool = True
    instructions: Optional[str] = None
    config_keys: Optional[dict] = None

class BranchPaymentSettings(BaseModel):
    payu_enabled: bool = True
    payu_merchant_key: Optional[str] = None
    payu_merchant_salt: Optional[str] = None
    payu_env: str = Field(default="test", pattern="^(test|production)$")
    
    razorpay_enabled: bool = False
    razorpay_key_id: Optional[str] = None
    razorpay_key_secret: Optional[str] = None
    
    stripe_enabled: bool = False
    stripe_publishable_key: Optional[str] = None
    stripe_secret_key: Optional[str] = None
    
    upi_enabled: bool = False
    upi_vpa: Optional[str] = None
    upi_merchant_name: Optional[str] = None
    
    cash_enabled: bool = True
    card_enabled: bool = True
    custom_methods: List[CustomPaymentMethod] = Field(default_factory=list)

