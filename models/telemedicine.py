from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class TelemedicineCreate(BaseModel):
    appointment_id: str

class TelemedicineResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    appointment_id: str
    room_name: str
    status: str  # active, closed
    jitsi_domain: str
    created_at: datetime
    created_by: str

    class Config:
        from_attributes = True
