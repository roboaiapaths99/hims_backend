from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ─── Emergency Admission Models ────────────────────────────────────

class EmergencyAdmissionCreate(BaseModel):
    patient_id: Optional[str] = None  # Can be quick-registered or existing
    patient_name: Optional[str] = None  # For quick registration without full patient record
    patient_age: Optional[int] = None
    patient_gender: Optional[str] = None
    patient_phone: Optional[str] = None
    triage_score: int = Field(..., ge=1, le=5, description="Triage score 1 (critical) to 5 (non-urgent)")
    triage_category: str = Field(..., description="red, yellow, or green")
    chief_complaint: Optional[str] = None
    attending_doctor_id: Optional[str] = None
    assigned_bed_number: Optional[str] = None
    notes: Optional[str] = None


class EmergencyAdmissionUpdate(BaseModel):
    triage_score: Optional[int] = Field(None, ge=1, le=5)
    triage_category: Optional[str] = None
    attending_doctor_id: Optional[str] = None
    assigned_bed_number: Optional[str] = None
    status: Optional[str] = None  # admitted, ipd_transferred, discharged
    notes: Optional[str] = None


class EmergencyAdmissionResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    patient_id: Optional[str] = None
    patient_name: Optional[str] = None
    patient_age: Optional[int] = None
    patient_gender: Optional[str] = None
    patient_phone: Optional[str] = None
    triage_score: int
    triage_category: str
    chief_complaint: Optional[str] = None
    attending_doctor_id: Optional[str] = None
    attending_doctor_name: Optional[str] = None
    assigned_bed_number: Optional[str] = None
    status: str  # admitted, ipd_transferred, discharged
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str

    class Config:
        from_attributes = True


# ─── Ambulance Booking Models ──────────────────────────────────────

class AmbulanceBookingCreate(BaseModel):
    driver_name: Optional[str] = None
    vehicle_number: Optional[str] = None
    pickup_address: str
    patient_name: Optional[str] = None
    patient_phone: Optional[str] = None
    emergency_admission_id: Optional[str] = None
    notes: Optional[str] = None


class AmbulanceBookingUpdate(BaseModel):
    driver_name: Optional[str] = None
    vehicle_number: Optional[str] = None
    status: Optional[str] = None  # dispatched, arrived, en_route_hospital, completed, cancelled
    notes: Optional[str] = None


class AmbulanceBookingResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    driver_name: Optional[str] = None
    vehicle_number: Optional[str] = None
    pickup_address: str
    patient_name: Optional[str] = None
    patient_phone: Optional[str] = None
    emergency_admission_id: Optional[str] = None
    status: str
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str

    class Config:
        from_attributes = True
