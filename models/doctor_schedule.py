from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, time

class ShiftWindow(BaseModel):
    start_time: str = Field(..., description="HH:MM format, e.g., '09:00'")
    end_time: str = Field(..., description="HH:MM format, e.g., '13:00'")

class DaySchedule(BaseModel):
    day_of_week: int = Field(..., description="0=Monday, 6=Sunday")
    is_available: bool = True
    shifts: List[ShiftWindow] = Field(default_factory=list)

class DoctorScheduleSaveRequest(BaseModel):
    doctor_id: str
    weekly_schedules: List[DaySchedule]
    slot_duration_minutes: int = Field(15, ge=5, le=120)

class DoctorScheduleResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    doctor_id: str
    weekly_schedules: List[DaySchedule]
    slot_duration_minutes: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class LeaveScheduleRequest(BaseModel):
    doctor_id: str
    start_date: datetime
    end_date: datetime
    reason: Optional[str] = None

class DoctorLeaveResponse(BaseModel):
    id: str
    tenant_id: str
    branch_id: str
    doctor_id: str
    start_date: datetime
    end_date: datetime
    reason: Optional[str] = None
    status: str = "approved"  # approved, cancelled
    created_at: datetime
