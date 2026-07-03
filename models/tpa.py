from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class TPAProviderCreate(BaseModel):
    name: str
    code: str
    is_active: bool = True

class TPAProviderResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    code: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str

    class Config:
        from_attributes = True

class PatientPolicyCreate(BaseModel):
    patient_id: str
    insurance_company: str
    policy_number: str
    card_number: str
    valid_till: datetime
    sum_insured: float = Field(..., gt=0)

class PatientPolicyResponse(BaseModel):
    id: str
    tenant_id: str
    patient_id: str
    insurance_company: str
    policy_number: str
    card_number: str
    valid_till: datetime
    sum_insured: float
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str

    class Config:
        from_attributes = True

class InsuranceClaimCreate(BaseModel):
    invoice_id: str
    policy_id: str
    tpa_id: str
    pre_auth_amount: float = Field(..., gt=0)

class InsuranceClaimResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    invoice_id: str
    policy_id: str
    tpa_id: str
    tpa_name: Optional[str] = None
    pre_auth_amount: float
    approved_amount: float
    co_pay_amount: float
    status: str  # draft, pre_auth_pending, approved, settled, rejected
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str

    class Config:
        from_attributes = True
