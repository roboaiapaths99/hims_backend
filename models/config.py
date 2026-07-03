from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime
from models.base import PyObjectId

# Department Models
class DepartmentBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    code: str = Field(..., min_length=2, max_length=10)
    is_active: bool = Field(default=True)

class DepartmentCreate(DepartmentBase):
    pass

class DepartmentResponse(DepartmentBase):
    id: str
    tenant_id: str
    branch_id: Optional[str] = None

    class Config:
        from_attributes = True

# Pricing Item Models
class PricingItemBase(BaseModel):
    name: str
    code: str
    item_type: str = Field(..., pattern="^(consultation|follow_up|lab_test|procedure|ot_charge|room_charge)$")
    price: float = Field(..., gt=0)
    doctor_id: Optional[str] = None
    is_active: bool = Field(default=True)

class PricingItemCreate(PricingItemBase):
    pass

class PricingItemResponse(PricingItemBase):
    id: str
    tenant_id: str
    branch_id: Optional[str] = None

    class Config:
        from_attributes = True

# Lab Test Master Models
class LabTestMasterBase(BaseModel):
    test_name: str
    test_code: str
    price: float = Field(..., ge=0)
    normal_range: str
    unit: str
    is_active: bool = Field(default=True)

class LabTestMasterCreate(LabTestMasterBase):
    pass

class LabTestMasterResponse(LabTestMasterBase):
    id: str
    tenant_id: str
    branch_id: Optional[str] = None

    class Config:
        from_attributes = True

# Room and OT Room Models
class RoomBase(BaseModel):
    room_number: str
    room_type: str
    hourly_rate: float = Field(..., ge=0)
    status: str = Field(default="available") # available, occupied, maintenance

class RoomCreate(RoomBase):
    pass

class RoomResponse(RoomBase):
    id: str
    tenant_id: str
    branch_id: str

    class Config:
        from_attributes = True

# Document Templates Models
class TemplateBase(BaseModel):
    name: str
    template_type: str = Field(..., pattern="^(prescription|invoice|consent|pre_op_checklist|notification)$")
    content: str
    is_active: bool = Field(default=True)

class TemplateCreate(TemplateBase):
    pass

class TemplateResponse(TemplateBase):
    id: str
    tenant_id: str
    branch_id: Optional[str] = None

    class Config:
        from_attributes = True
