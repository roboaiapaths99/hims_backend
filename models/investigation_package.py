from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class PackageTestItem(BaseModel):
    test_type: str = Field(..., description="lab or radiology")
    test_master_id: str = Field(..., description="Master ID of the lab test or radiology exam")
    test_name: str = Field(..., description="Name of the test")

class InvestigationPackageCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)
    description: Optional[str] = None
    price: float = Field(..., gt=0)
    items: List[PackageTestItem]

class InvestigationPackageResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    name: str
    description: Optional[str] = None
    price: float
    items: List[PackageTestItem]
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class BookPackageRequest(BaseModel):
    patient_id: str
    package_id: str
    doctor_id: Optional[str] = None  # Referring doctor if any
    payment_method: str = "cash"    # cash, card, upi, online
