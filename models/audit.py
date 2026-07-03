from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Any
from models.base import PyObjectId

class AuditLogCreate(BaseModel):
    user_id: str
    user_name: str
    action: str
    entity: str
    entity_id: str
    details: Optional[Any] = None
    ip_address: Optional[str] = None
    tenant_id: Optional[PyObjectId] = None
    branch_id: Optional[PyObjectId] = None

class AuditLogResponse(BaseModel):
    id: str
    user_id: str
    user_name: str
    action: str
    entity: str
    entity_id: str
    details: Optional[Any] = None
    ip_address: Optional[str] = None
    timestamp: datetime
    tenant_id: Optional[str] = None
    branch_id: Optional[str] = None

    class Config:
        from_attributes = True
        populate_by_name = True
