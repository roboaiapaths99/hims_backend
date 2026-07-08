from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class RadiologyOrderCreate(BaseModel):
    patient_id: str
    visit_id: Optional[str] = None
    modality: str  # XRAY, MRI, CT, US
    test_name: str
    price: float = 0.0

class RadiologyOrderResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    patient_id: str
    patient_name: Optional[str] = None
    patient_mrn: Optional[str] = None
    visit_id: Optional[str] = None
    modality: str
    test_name: str
    status: str  # ordered, scheduled, performed, reported
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str

    class Config:
        from_attributes = True

class RadiologyResultCreate(BaseModel):
    findings: str
    impression: str
    image_links: List[str] = []

class RadiologyResultResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    order_id: str
    findings: str
    impression: str
    image_links: List[str]
    reported_by: str
    reported_by_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str

    class Config:
        from_attributes = True
