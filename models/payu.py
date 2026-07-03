from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class PayUTransaction(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    invoice_id: str
    txnid: str
    amount: float
    status: str = "pending"  # pending, success, failed
    hash_sent: str
    hash_received: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class PayUCreateRequest(BaseModel):
    invoice_id: str
    amount: Optional[float] = None

class PayUCreateResponse(BaseModel):
    key: str
    txnid: str
    amount: str
    productinfo: str
    firstname: str
    email: str
    phone: str
    surl: str
    furl: str
    hash: str
    action_url: str
