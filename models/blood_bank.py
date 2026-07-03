from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Dict
from datetime import datetime

class DonorScreeningBase(BaseModel):
    hemoglobin: float = Field(..., description="Hemoglobin level in g/dL", ge=5.0, le=25.0)
    weight: float = Field(..., description="Weight in kg", ge=30.0, le=250.0)
    bp_sys: int = Field(..., description="Systolic Blood Pressure", ge=60, le=250)
    bp_dia: int = Field(..., description="Diastolic Blood Pressure", ge=40, le=150)
    pulse: int = Field(..., description="Pulse rate per minute", ge=40, le=180)
    temperature: float = Field(..., description="Temperature in Fahrenheit", ge=94.0, le=108.0)
    eligible: bool = Field(True, description="Whether the donor passed the screening questions")
    notes: Optional[str] = None

class BloodDonorBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    gender: str = Field(..., pattern="^(Male|Female|Other)$")
    dob: str = Field(..., description="Date of birth in YYYY-MM-DD")
    phone: str = Field(..., min_length=10, max_length=15)
    email: Optional[EmailStr] = None
    blood_group: str = Field(..., pattern="^(A\\+|A-|B\\+|B-|AB\\+|AB-|O\\+|O-)$")

class BloodDonorCreate(BloodDonorBase):
    pass

class BloodDonorResponse(BloodDonorBase):
    id: str
    donor_number: str
    tenant_id: str
    branch_id: str
    screening_vitals: Optional[DonorScreeningBase] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat()}

class BloodDonationCreate(BaseModel):
    volume_ml: int = Field(..., ge=100, le=1000, description="Volume of collected blood in ml")
    collection_date: Optional[datetime] = None
    technician: str = Field(..., min_length=2, max_length=100)

class BloodDonationResponse(BaseModel):
    id: str
    donor_id: str
    bag_number: str
    volume_ml: int
    collection_date: datetime
    technician: str
    testing_status: str  # pending, approved, reactive
    testing_results: Optional[Dict[str, str]] = None
    tenant_id: str
    branch_id: str

    class Config:
        populate_by_name = True

class LabTestingUpdate(BaseModel):
    hiv_status: str = Field(..., pattern="^(Non-Reactive|Reactive)$")
    hepb_status: str = Field(..., pattern="^(Non-Reactive|Reactive)$")
    hepc_status: str = Field(..., pattern="^(Non-Reactive|Reactive)$")
    syphilis_status: str = Field(..., pattern="^(Non-Reactive|Reactive)$")
    malaria_status: str = Field(..., pattern="^(Non-Reactive|Reactive)$")
    notes: Optional[str] = None

class BloodRequisitionCreate(BaseModel):
    patient_id: str
    blood_group: str = Field(..., pattern="^(A\\+|A-|B\\+|B-|AB\\+|AB-|O\\+|O-)$")
    component_type: str = Field(..., pattern="^(Whole Blood|PRBC|FFP|Platelets|Cryoprecipitate)$")
    units_requested: int = Field(..., ge=1, le=10)
    urgency: str = Field(..., pattern="^(routine|urgent|stat)$")

class BloodRequisitionResponse(BaseModel):
    id: str
    request_number: str
    patient_id: str
    patient_name: str
    blood_group: str
    component_type: str
    units_requested: int
    urgency: str
    status: str  # pending, allocated, crossmatched, transfused, cancelled
    allocated_bags: List[str] = []
    tenant_id: str
    branch_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        populate_by_name = True

class BloodCrossmatchCreate(BaseModel):
    bag_number: str

class BloodTransfusionCreate(BaseModel):
    bag_number: str
    started_at: datetime
    ended_at: datetime
    transfused_by: str
    bp_before: str
    pulse_before: int
    temp_before: float
    bp_after: str
    pulse_after: int
    temp_after: float
    reaction_logged: bool
    reaction_details: Optional[str] = None
