from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime


# ─── Referring Doctor Models ────────────────────────────────────────

class CommissionRule(BaseModel):
    """A single commission rule: percentage per department or service type."""
    department_or_service: str
    percentage: float = Field(..., ge=0, le=100, description="Commission percentage (0-100)")


class ReferringDoctorCreate(BaseModel):
    name: str
    hospital_name: Optional[str] = None
    phone: Optional[str] = None
    specialty: Optional[str] = None
    commission_rules: List[CommissionRule] = []


class ReferringDoctorUpdate(BaseModel):
    name: Optional[str] = None
    hospital_name: Optional[str] = None
    phone: Optional[str] = None
    specialty: Optional[str] = None
    commission_rules: Optional[List[CommissionRule]] = None
    is_active: Optional[bool] = None


class ReferringDoctorResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    name: str
    hospital_name: Optional[str] = None
    phone: Optional[str] = None
    specialty: Optional[str] = None
    commission_rules: List[dict] = []
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str

    class Config:
        from_attributes = True


# ─── Referral Transaction Models ────────────────────────────────────

class ReferralTransactionCreate(BaseModel):
    invoice_id: str
    referring_doctor_id: str
    visit_id: Optional[str] = None
    commission_amount: float = Field(..., gt=0)


class ReferralTransactionResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    invoice_id: str
    referring_doctor_id: str
    referring_doctor_name: Optional[str] = None
    visit_id: Optional[str] = None
    commission_amount: float
    payout_status: str  # pending, paid
    paid_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str

    class Config:
        from_attributes = True


# ─── Payout Models ──────────────────────────────────────────────────

class PayoutRequest(BaseModel):
    """Settle pending commissions for a referring doctor."""
    referring_doctor_id: str
    transaction_ids: List[str]
    payment_reference: Optional[str] = None


class PayoutResponse(BaseModel):
    settled_count: int
    total_amount: float
    referring_doctor_id: str
    payment_reference: Optional[str] = None
