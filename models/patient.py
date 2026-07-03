from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime
from models.base import PyObjectId

# Patient Core Models
class PatientBase(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., pattern="^[0-9]{10}$")
    email: Optional[EmailStr] = None
    dob: datetime
    gender: str = Field(..., pattern="^(Male|Female|Other)$")
    blood_group: Optional[str] = Field(None, pattern="^(A\\+|A-|B\\+|B-|AB\\+|AB-|O\\+|O-)$")
    address: str
    emergency_contact_name: str
    emergency_contact_phone: str = Field(..., pattern="^[0-9]{10}$")
    photo_url: Optional[str] = None
    
    # ABHA details
    abha_number: Optional[str] = None
    abha_address: Optional[str] = None
    consent_signed: bool = Field(default=False)
    referred_by_doctor_id: Optional[str] = None

class PatientCreate(PatientBase):
    pass

class PatientUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    dob: Optional[datetime] = None
    gender: Optional[str] = None
    blood_group: Optional[str] = None
    address: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    photo_url: Optional[str] = None
    abha_number: Optional[str] = None
    abha_address: Optional[str] = None
    consent_signed: Optional[bool] = None
    referred_by_doctor_id: Optional[str] = None

class PatientResponse(PatientBase):
    id: str
    mrn: str
    tenant_id: str
    branch_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Medical History Models
class MedicalHistoryBase(BaseModel):
    allergies: List[str] = Field(default_factory=list)
    chronic_conditions: List[str] = Field(default_factory=list)
    past_surgeries: Optional[str] = None
    family_history: Optional[str] = None

class MedicalHistoryCreate(MedicalHistoryBase):
    pass

class MedicalHistoryResponse(MedicalHistoryBase):
    id: str
    patient_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# Patient Family Member Linking Models
class FamilyMemberBase(BaseModel):
    relationship: str
    linked_patient_id: str

class FamilyMemberCreate(FamilyMemberBase):
    pass

class FamilyMemberResponse(FamilyMemberBase):
    id: str
    patient_id: str

    class Config:
        from_attributes = True

# Patient Document Models
class PatientDocumentBase(BaseModel):
    document_name: str
    document_type: str # e.g. Lab Report, Old Prescription, ID Proof
    file_url: str

class PatientDocumentCreate(PatientDocumentBase):
    pass

class PatientDocumentResponse(PatientDocumentBase):
    id: str
    patient_id: str
    uploaded_at: datetime

    class Config:
        from_attributes = True
