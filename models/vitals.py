from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from models.base import PyObjectId

class VitalsBase(BaseModel):
    patient_id: str
    appointment_id: str # Link back to the checked-in appointment
    bp_sys: int = Field(..., ge=40, le=250) # Systolic blood pressure (mmHg)
    bp_dia: int = Field(..., ge=30, le=150) # Diastolic blood pressure (mmHg)
    pulse: int = Field(..., ge=30, le=220) # Heart rate (bpm)
    temperature: float = Field(..., ge=90.0, le=110.0) # Temperature (Fahrenheit)
    spo2: int = Field(..., ge=50, le=100) # Oxygen saturation (%)
    height: float = Field(..., ge=30.0, le=250.0) # Height (cm)
    weight: float = Field(..., ge=1.0, le=300.0) # Weight (kg)
    pain_score: int = Field(default=0, ge=0, le=10) # Pain scale 0-10
    triage_level: str = Field(default="green", pattern="^(red|yellow|green)$")

class VitalsCreate(VitalsBase):
    pass

class VitalsResponse(VitalsBase):
    id: str
    bmi: float # Body Mass Index (kg/m^2)
    tenant_id: str
    branch_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
