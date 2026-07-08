from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class DrugItem(BaseModel):
    name: str = Field(..., description="Trade name or brand name")
    generic_name: str = Field(..., description="Active chemical ingredient")
    strength: str = Field(..., description="e.g., 500mg, 10ml")
    form: str = Field(..., description="Tablet, Capsule, Syrup, Injection, etc.")
    manufacturer: Optional[str] = None

class TemplateMedication(BaseModel):
    drug_id: str
    drug_name: str
    dosage: str = Field(..., description="e.g., 1-0-1")
    frequency: str = Field("Daily", description="Daily, TDS, BD, OD")
    duration: str = Field("5 days")
    instructions: str = ""

class PrescriptionTemplateCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = None
    medications: List[TemplateMedication]

class PrescriptionTemplateResponse(BaseModel):
    id: str
    tenant_id: str
    doctor_id: str
    name: str
    description: Optional[str] = None
    medications: List[TemplateMedication]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
