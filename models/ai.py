from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class VisitSummarizeRequest(BaseModel):
    patient_id: str
    clinical_notes: str
    symptoms: str
    diagnosis: List[str]

class SimplifyInstructionsRequest(BaseModel):
    patient_id: str
    instructions: str
    target_language: str

class AISummaryResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    patient_id: str
    source_type: str  # notes, history
    generated_text: str
    approved_by_doctor: bool
    created_at: datetime
    created_by: str

    class Config:
        from_attributes = True
