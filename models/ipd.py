from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime

class IPDAdmissionCreate(BaseModel):
    patient_id: str
    doctor_id: str
    room_id: str
    admission_date: datetime = Field(default_factory=datetime.utcnow)
    initial_deposit: float = 0.0

class IPDAdmissionResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    patient_id: str
    patient_name: Optional[str] = None
    patient_mrn: Optional[str] = None
    doctor_id: str
    doctor_name: Optional[str] = None
    room_id: str
    room_number: Optional[str] = None
    room_type: Optional[str] = None
    admission_date: datetime
    discharge_date: Optional[datetime] = None
    discharge_summary: Optional[str] = None
    initial_deposit: float
    status: str  # admitted, discharged
    progress_notes: Optional[List[Dict]] = None
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str

    class Config:
        from_attributes = True

class BedTransferRequest(BaseModel):
    to_room_id: str
    reason: str

class IPDChargeCreate(BaseModel):
    charge_type: str  # bed_charge, nursing_fee, doctor_visit, procedure, other
    description: str
    amount: float = Field(..., gt=0)
    gst_rate: float = 0.0

class IPDChargeResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    admission_id: str
    charge_type: str
    description: str
    amount: float
    gst_rate: float
    date: datetime
    created_at: datetime
    created_by: str

    class Config:
        from_attributes = True
