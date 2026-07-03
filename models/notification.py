from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime

class NotificationLogResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    recipient_id: Optional[str] = None
    recipient_phone: Optional[str] = None
    recipient_email: Optional[str] = None
    channel: str  # sms, whatsapp, push
    template_name: str  # appointment_confirmed, bill_paid
    status: str  # pending, sent, failed
    details: Dict[str, Any]
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class NotificationResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    user_id: str
    title: str
    message: str
    type: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True

