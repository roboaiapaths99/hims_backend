from pydantic import BaseModel
from typing import List

class RevenueBranchSummary(BaseModel):
    branch_id: str
    branch_name: str
    amount: float

class RevenueDoctorSummary(BaseModel):
    doctor_name: str
    amount: float

class RevenueCategorySummary(BaseModel):
    category: str
    amount: float

class DailyRevenueSummary(BaseModel):
    date: str
    amount: float

class RevenueReportResponse(BaseModel):
    revenue_by_branch: List[RevenueBranchSummary]
    revenue_by_doctor: List[RevenueDoctorSummary]
    revenue_by_category: List[RevenueCategorySummary]
    daily_revenue: List[DailyRevenueSummary]
    total_revenue: float

class DailyVisitSummary(BaseModel):
    date: str
    count: int

class OperationalReportResponse(BaseModel):
    total_visits_count: int
    unique_patients_count: int
    average_visits_per_patient: float
    daily_visits: List[DailyVisitSummary]
    average_consultation_time_mins: float
    average_lab_turnaround_time_mins: float
