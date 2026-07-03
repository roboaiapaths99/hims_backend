from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime

class OTBookingCreate(BaseModel):
    patient_id: str
    surgery_name: str
    surgeon_id: str
    anesthetist_id: str
    room_id: str
    schedule_date: datetime
    pre_op_diagnosis: Optional[str] = None
    post_op_diagnosis: Optional[str] = None
    anesthesia_details: Optional[str] = None
    surgery_findings: Optional[str] = None
    blood_loss: Optional[float] = None
    post_op_plan: Optional[str] = None

class OTBookingUpdate(BaseModel):
    surgery_name: Optional[str] = None
    surgeon_id: Optional[str] = None
    anesthetist_id: Optional[str] = None
    room_id: Optional[str] = None
    schedule_date: Optional[datetime] = None
    status: Optional[str] = None
    pre_op_diagnosis: Optional[str] = None
    post_op_diagnosis: Optional[str] = None
    anesthesia_details: Optional[str] = None
    surgery_findings: Optional[str] = None
    blood_loss: Optional[float] = None
    post_op_plan: Optional[str] = None

class OTBookingResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    patient_id: str
    patient_name: Optional[str] = None
    patient_mrn: Optional[str] = None
    surgery_name: str
    surgeon_id: str
    surgeon_name: Optional[str] = None
    anesthetist_id: str
    anesthetist_name: Optional[str] = None
    room_id: str
    room_number: Optional[str] = None
    schedule_date: datetime
    status: str  # planned, pre_op_pending, in_surgery, completed, cancelled
    pre_op_diagnosis: Optional[str] = None
    post_op_diagnosis: Optional[str] = None
    anesthesia_details: Optional[str] = None
    surgery_findings: Optional[str] = None
    blood_loss: Optional[float] = None
    post_op_plan: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str

    class Config:
        from_attributes = True

class OTChecklistSave(BaseModel):
    items_checked: Dict[str, bool] = Field(default_factory=dict)
    signed_off_by: Optional[str] = None

class OTChecklistResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    booking_id: str
    items_checked: Dict[str, bool]
    signed_off_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str

    class Config:
        from_attributes = True

class ConsumableItem(BaseModel):
    medicine_id: str
    quantity: int = Field(..., gt=0)
    warehouse_id: str
    batch_id: Optional[str] = None

class OTConsumablesDeduct(BaseModel):
    items: List[ConsumableItem]
