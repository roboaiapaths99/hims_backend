from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from models.base import PyObjectId

class AppointmentBase(BaseModel):
    patient_id: str
    doctor_id: str
    department_id: str
    appointment_date: datetime # Date of appointment (time parts ignored or set to midnight)
    start_time: str = Field(..., pattern="^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$") # Format "HH:MM"
    end_time: str = Field(..., pattern="^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$") # Format "HH:MM"
    status: str = Field(default="scheduled", pattern="^(scheduled|checked_in|waiting|in_vitals|ready_for_doctor|in_consultation|completed|cancelled)$")
    reason: Optional[str] = None
    referred_by_doctor_id: Optional[str] = None
    tenant_id: Optional[str] = None
    branch_id: Optional[str] = None

class AppointmentCreate(AppointmentBase):
    pass

class AppointmentUpdate(BaseModel):
    doctor_id: Optional[str] = None
    appointment_date: Optional[datetime] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    status: Optional[str] = None
    reason: Optional[str] = None
    referred_by_doctor_id: Optional[str] = None

class AppointmentResponse(AppointmentBase):
    id: str
    mrn: str
    patient_name: str
    doctor_name: str
    department_name: str
    tenant_id: str
    branch_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class QueueTokenBase(BaseModel):
    appointment_id: str
    token_number: str # e.g. OPD-001
    status: str = Field(default="waiting", pattern="^(waiting|in_vitals|ready_for_doctor|in_consultation|completed|skipped)$")

class QueueTokenCreate(QueueTokenBase):
    pass

class QueueTokenResponse(QueueTokenBase):
    id: str
    patient_name: str
    doctor_name: str
    department_name: str
    assigned_at: datetime
    tenant_id: str
    branch_id: str

    class Config:
        from_attributes = True
