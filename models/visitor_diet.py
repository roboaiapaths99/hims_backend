from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ─── Visitor Pass Models ────────────────────────────────────────────

class VisitorPassCreate(BaseModel):
    admission_id: str
    visitor_name: str
    phone: Optional[str] = None
    pass_type: str = Field(..., description="day_pass or night_attendant")
    valid_till: Optional[datetime] = None
    id_proof_type: Optional[str] = None
    id_proof_number: Optional[str] = None
    relationship: Optional[str] = None


class VisitorPassResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    admission_id: str
    patient_name: Optional[str] = None
    visitor_name: str
    phone: Optional[str] = None
    pass_type: str
    valid_till: Optional[datetime] = None
    id_proof_type: Optional[str] = None
    id_proof_number: Optional[str] = None
    relationship: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str

    class Config:
        from_attributes = True


# ─── Patient Diet Prescription Models ──────────────────────────────

class DietOrderCreate(BaseModel):
    admission_id: str
    meal_type: str = Field(..., description="breakfast, lunch, dinner, snack")
    diet_type: str = Field(..., description="regular, diabetic, liquid, low_sodium, soft, npo")
    special_instructions: Optional[str] = None
    delivery_time: Optional[str] = None
    price: Optional[float] = 0.0


class DietOrderUpdate(BaseModel):
    status: Optional[str] = None  # ordered, preparing, prepared, delivered
    special_instructions: Optional[str] = None
    price: Optional[float] = None


class DietOrderResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    admission_id: str
    patient_name: Optional[str] = None
    room_number: Optional[str] = None
    meal_type: str
    diet_type: str
    special_instructions: Optional[str] = None
    delivery_time: Optional[str] = None
    price: float = 0.0
    created_by_role: Optional[str] = "staff"
    status: str
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str

    class Config:
        from_attributes = True
