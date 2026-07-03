from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from models.base import PyObjectId

class VisitBase(BaseModel):
    patient_id: str
    doctor_id: str
    appointment_id: str
    symptoms: Optional[str] = None
    clinical_notes: Optional[str] = None
    diagnosis: List[str] = Field(default_factory=list) # List of ICD-10 codes/names
    treatment_plan: Optional[str] = None
    status: str = Field(default="active", pattern="^(active|completed)$")
    is_finalized: bool = False

class VisitCreate(VisitBase):
    pass

class VisitUpdate(BaseModel):
    symptoms: Optional[str] = None
    clinical_notes: Optional[str] = None
    diagnosis: Optional[List[str]] = None
    treatment_plan: Optional[str] = None
    status: Optional[str] = None
    is_finalized: Optional[bool] = None

class VisitResponse(VisitBase):
    id: str
    tenant_id: str
    branch_id: str
    visit_date: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
