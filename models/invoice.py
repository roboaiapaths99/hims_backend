from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class InvoiceItem(BaseModel):
    description: str
    quantity: int = Field(..., gt=0)
    base_price: float = Field(..., ge=0)
    gst_rate: float = Field(default=0.0, ge=0.0)  # GST Percentage, e.g. 18.0 or 12.0
    discount_percentage: float = Field(default=0.0, ge=0.0, le=100.0)
    tax_amount: float = 0.0  # (base_price * quantity * gst_rate / 100) after discount
    line_total: float = 0.0  # Net amount including tax

class InvoiceCreate(BaseModel):
    patient_id: str
    visit_id: Optional[str] = None
    items: List[InvoiceItem]
    discount_amount: float = Field(default=0.0, ge=0.0)  # flat discount on grand total
    discount_approval_code: Optional[str] = None

class InvoiceResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    invoice_number: str
    patient_id: str
    visit_id: Optional[str] = None
    items: List[InvoiceItem]
    subtotal: float
    gst_total: float
    discount_amount: float
    grand_total: float
    payment_status: str = "unpaid"  # unpaid, paid, due
    created_at: datetime
    updated_at: datetime
    created_by: str
    updated_by: str
    patient_name: Optional[str] = None
    doctor_name: Optional[str] = None

    class Config:
        from_attributes = True

class PaymentCreate(BaseModel):
    invoice_id: str
    payment_method: str = Field(..., min_length=2, max_length=100)
    amount_paid: float = Field(..., gt=0)
    transaction_reference: Optional[str] = None

class PaymentResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    invoice_id: str
    payment_method: str
    amount_paid: float
    transaction_reference: Optional[str] = None
    created_at: datetime
    created_by: str

    class Config:
        from_attributes = True
