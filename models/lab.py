from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class LabOrderItem(BaseModel):
    test_id: str
    test_name: str
    test_code: str
    price: float = 0

class LabOrderBase(BaseModel):
    patient_id: str
    visit_id: str
    items: List[LabOrderItem]
    status: str = Field(default="ordered", pattern="^(ordered|sample_collected|result_entered|verified)$")

class LabOrderCreate(LabOrderBase):
    pass

class LabOrderResponse(LabOrderBase):
    id: str
    tenant_id: str
    branch_id: str
    patient_name: str
    doctor_name: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class LabResultEntry(BaseModel):
    test_id: str
    test_name: str
    result_value: str
    normal_range: str = ""
    unit: str = ""
    abnormal_flag: bool = False

class LabResultCreate(BaseModel):
    results: List[LabResultEntry]
    pdf_url: Optional[str] = None

class LabResultResponse(BaseModel):
    id: str
    lab_order_id: str
    results: List[LabResultEntry]
    pdf_url: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
