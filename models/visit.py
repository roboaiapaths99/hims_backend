from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from models.base import PyObjectId


# --- Amendment Models ---

class VisitAmendmentCreate(BaseModel):
    """Payload for creating a clinical amendment on a finalized visit."""
    reason: str = Field(..., min_length=5, max_length=1000, description="Clinical reason for the amendment")
    amended_symptoms: Optional[str] = None
    amended_clinical_notes: Optional[str] = None
    amended_diagnosis: Optional[List[str]] = None
    amended_treatment_plan: Optional[str] = None

class VisitAmendment(BaseModel):
    """A single amendment record appended to a finalized consultation."""
    id: str
    reason: str
    amended_symptoms: Optional[str] = None
    amended_clinical_notes: Optional[str] = None
    amended_diagnosis: Optional[List[str]] = None
    amended_treatment_plan: Optional[str] = None
    amended_by: str
    amended_by_name: str
    amended_at: datetime

    class Config:
        from_attributes = True


# --- Visit Models ---

class VisitBase(BaseModel):
    patient_id: str
    doctor_id: str
    appointment_id: str
    symptoms: Optional[str] = None
    clinical_notes: Optional[str] = None
    diagnosis: List[str] = Field(default_factory=list) # List of ICD-10 codes/names
    treatment_plan: Optional[str] = None
    status: str = Field(default="draft")
    is_finalized: bool = False
    locked: bool = False
    finalized_at: Optional[datetime] = None
    finalized_by: Optional[str] = None
    amendments: List[Dict[str, Any]] = Field(default_factory=list)

class VisitCreate(VisitBase):
    pass

class VisitUpdate(BaseModel):
    """Client-facing update schema. Finalization fields are excluded
    to prevent bypass of the dedicated /finalize endpoint."""
    symptoms: Optional[str] = None
    clinical_notes: Optional[str] = None
    diagnosis: Optional[List[str]] = None
    treatment_plan: Optional[str] = None
    status: Optional[str] = None

class VisitResponse(VisitBase):
    id: str
    tenant_id: str
    branch_id: str
    visit_date: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
