from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ─── Feedback Survey Models ─────────────────────────────────────────

class FeedbackCreate(BaseModel):
    patient_id: Optional[str] = None
    visit_id: Optional[str] = None
    rating: int = Field(..., ge=1, le=5, description="Rating from 1 (poor) to 5 (excellent)")
    comments: Optional[str] = None
    category: Optional[str] = None  # overall, doctor, staff, facility, food


class FeedbackResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    patient_id: Optional[str] = None
    patient_name: Optional[str] = None
    visit_id: Optional[str] = None
    rating: int
    comments: Optional[str] = None
    category: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
