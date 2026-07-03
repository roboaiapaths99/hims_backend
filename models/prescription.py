from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class PrescriptionItem(BaseModel):
    medicine_id: str
    medicine_name: str
    dosage: str  # e.g., "1-0-1", "1 TDS"
    frequency: str  # e.g., "Daily", "TDS", "OD"
    duration: str  # e.g., "5 days"
    instructions: str = ""  # e.g., "After food"
    quantity_prescribed: int = Field(..., gt=0)

class PrescriptionCreate(BaseModel):
    patient_id: str
    visit_id: str
    items: List[PrescriptionItem]

class PrescriptionResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    patient_id: str
    visit_id: str
    items: List[PrescriptionItem]
    status: str = "pending"  # pending, dispensed, cancelled
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str
    patient_name: Optional[str] = None
    doctor_name: Optional[str] = None

    class Config:
        from_attributes = True
