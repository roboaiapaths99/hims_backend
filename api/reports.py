from fastapi import APIRouter, Depends, Query, HTTPException, status
from bson import ObjectId
from datetime import datetime, timedelta
from typing import List, Optional, Dict

from database import (
    get_db,
    get_payments_collection,
    get_invoices_collection,
    get_visits_collection,
    get_lab_orders_collection,
    get_branches_collection,
    get_users_collection,
    get_patients_collection,
    get_appointments_collection,
    get_queue_tokens_collection,
    get_ot_bookings_collection,
    get_prescriptions_collection,
    get_radiology_orders_collection,
    get_audit_logs_collection
)
from middleware.auth import get_current_user, get_branch_filter
from models.report import (
    RevenueReportResponse,
    OperationalReportResponse,
    RevenueBranchSummary,
    RevenueDoctorSummary,
    RevenueCategorySummary,
    DailyRevenueSummary,
    DailyVisitSummary
)

router = APIRouter()

def classify_item_category(description: str) -> str:
    desc = description.lower()
    if "consultation" in desc:
        return "consultation"
    elif "lab" in desc or "test" in desc:
        return "lab"
    elif "pharmacy" in desc or "medicine" in desc or "drug" in desc:
        return "pharmacy"
    elif "ot" in desc or "surgery" in desc or "operation" in desc:
        return "ot"
    else:
        return "other"

@router.get("/revenue", response_model=RevenueReportResponse)
@router.get("/revenue/", response_model=RevenueReportResponse)
async def get_revenue_report(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    payments_col = get_payments_collection()
    invoices_col = get_invoices_collection()
    visits_col = get_visits_collection()
    branches_col = get_branches_collection()
    users_col = get_users_collection()
    
    # Establish base tenant/branch query filter
    query = get_branch_filter(current_user)
    
    # Date filtering
    date_query = {}
    if start_date:
        try:
            date_query["$gte"] = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format, use YYYY-MM-DD")
    if end_date:
        try:
            # Set time to end of day
            date_query["$lte"] = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1) - timedelta(microseconds=1)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format, use YYYY-MM-DD")
            
    if date_query:
        query["created_at"] = date_query
        
    # Fetch payments
    payments = await payments_col.find(query).to_list(None)
    
    # Cache maps to reduce db hits
    invoices_cache: Dict[str, dict] = {}
    visits_cache: Dict[str, dict] = {}
    doctors_cache: Dict[str, str] = {}
    branches_cache: Dict[str, str] = {}
    
    branch_revenue: Dict[str, float] = {}
    doctor_revenue: Dict[str, float] = {}
    category_revenue: Dict[str, float] = {
        "consultation": 0.0,
        "lab": 0.0,
        "pharmacy": 0.0,
        "ot": 0.0,
        "other": 0.0
    }
    daily_revenue: Dict[str, float] = {}
    total_rev = 0.0
    
    for payment in payments:
        amount = payment.get("amount_paid", 0.0)
        total_rev += amount
        
        # Group by branch
        branch_id_str = str(payment["branch_id"])
        if branch_id_str not in branches_cache:
            branch_doc = await branches_col.find_one({"_id": payment["branch_id"]})
            branches_cache[branch_id_str] = branch_doc.get("name", "Unknown Branch") if branch_doc else "Unknown Branch"
        branch_name = branches_cache[branch_id_str]
        branch_revenue[branch_id_str] = branch_revenue.get(branch_id_str, 0.0) + amount
        
        # Group by daily trend
        day_str = payment["created_at"].strftime("%Y-%m-%d")
        daily_revenue[day_str] = daily_revenue.get(day_str, 0.0) + amount
        
        # Group by Category and Doctor (requires Invoice lookup)
        invoice_id_str = str(payment["invoice_id"])
        if invoice_id_str not in invoices_cache:
            invoice_doc = await invoices_col.find_one({"_id": payment["invoice_id"]})
            invoices_cache[invoice_id_str] = invoice_doc
            
        invoice = invoices_cache[invoice_id_str]
        
        # Resolve doctor
        doctor_name = "General"
        if invoice:
            visit_id = invoice.get("visit_id")
            if visit_id:
                visit_id_str = str(visit_id)
                if visit_id_str not in visits_cache:
                    visit_doc = await visits_col.find_one({"_id": visit_id})
                    visits_cache[visit_id_str] = visit_doc
                visit = visits_cache[visit_id_str]
                if visit and visit.get("doctor_id"):
                    doc_id_str = str(visit["doctor_id"])
                    if doc_id_str not in doctors_cache:
                        doc_user = await users_col.find_one({"_id": ObjectId(doc_id_str)})
                        doctors_cache[doc_id_str] = doc_user.get("name", "Doctor") if doc_user else "Doctor"
                    doctor_name = doctors_cache[doc_id_str]
            
            # Proportional split calculation for category revenue
            items = invoice.get("items", [])
            invoice_total = sum(item.get("line_total", 0.0) for item in items)
            if invoice_total > 0:
                for item in items:
                    cat = classify_item_category(item.get("description", ""))
                    prop = item.get("line_total", 0.0) / invoice_total
                    category_revenue[cat] += amount * prop
            else:
                category_revenue["other"] += amount
        else:
            category_revenue["other"] += amount
            
        doctor_revenue[doctor_name] = doctor_revenue.get(doctor_name, 0.0) + amount
        
    # Format response lists
    rev_by_branch = [
        RevenueBranchSummary(branch_id=bid, branch_name=branches_cache.get(bid, "Unknown Branch"), amount=round(val, 2))
        for bid, val in branch_revenue.items()
    ]
    
    rev_by_doctor = [
        RevenueDoctorSummary(doctor_name=name, amount=round(val, 2))
        for name, val in doctor_revenue.items()
    ]
    
    rev_by_category = [
        RevenueCategorySummary(category=cat, amount=round(val, 2))
        for cat, val in category_revenue.items()
    ]
    
    # Sort daily trend
    sorted_daily = sorted(daily_revenue.items())
    daily_trend = [
        DailyRevenueSummary(date=day, amount=round(val, 2))
        for day, val in sorted_daily
    ]
    
    return RevenueReportResponse(
        revenue_by_branch=rev_by_branch,
        revenue_by_doctor=rev_by_doctor,
        revenue_by_category=rev_by_category,
        daily_revenue=daily_trend,
        total_revenue=round(total_rev, 2)
    )

@router.get("/operational", response_model=OperationalReportResponse)
@router.get("/operational/", response_model=OperationalReportResponse)
async def get_operational_report(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    visits_col = get_visits_collection()
    labs_col = get_lab_orders_collection()
    
    # Base tenant/branch scope filter
    query = get_branch_filter(current_user)
    
    # Date filtering
    date_query = {}
    if start_date:
        try:
            date_query["$gte"] = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format, use YYYY-MM-DD")
    if end_date:
        try:
            date_query["$lte"] = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1) - timedelta(microseconds=1)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format, use YYYY-MM-DD")
            
    # Copy query for labs as it matches same scopes and dates
    labs_query = query.copy()
    
    if date_query:
        query["visit_date"] = date_query
        labs_query["created_at"] = date_query
        
    # Fetch visits
    visits = await visits_col.find(query).to_list(None)
    
    # Group visits by day for trends
    daily_visits_map: Dict[str, int] = {}
    completed_visits_count = 0
    total_consult_time_seconds = 0.0
    patient_ids = set()
    
    for visit in visits:
        day_str = visit["visit_date"].strftime("%Y-%m-%d")
        daily_visits_map[day_str] = daily_visits_map.get(day_str, 0) + 1
        
        patient_ids.add(str(visit["patient_id"]))
        
        if visit.get("status") == "completed":
            completed_visits_count += 1
            created = visit.get("created_at")
            updated = visit.get("updated_at")
            if created and updated:
                total_consult_time_seconds += (updated - created).total_seconds()
            else:
                total_consult_time_seconds += 900
                
    # Sort daily visits
    sorted_daily_visits = sorted(daily_visits_map.items())
    daily_visits = [
        DailyVisitSummary(date=day, count=cnt)
        for day, cnt in sorted_daily_visits
    ]
    
    # Average consult time in minutes
    avg_consult_time = 0.0
    if completed_visits_count > 0:
        avg_consult_time = round((total_consult_time_seconds / completed_visits_count) / 60.0, 2)
        
    # Lab turnaround computation
    verified_labs_count = 0
    total_lab_time_seconds = 0.0
    
    # Find lab orders
    lab_orders = await labs_col.find(labs_query).to_list(None)
    for order in lab_orders:
        if order.get("status") == "verified":
            verified_labs_count += 1
            created = order.get("created_at")
            updated = order.get("updated_at")
            if created and updated:
                total_lab_time_seconds += (updated - created).total_seconds()
            else:
                total_lab_time_seconds += 1800
                
    avg_lab_time = 0.0
    if verified_labs_count > 0:
        avg_lab_time = round((total_lab_time_seconds / verified_labs_count) / 60.0, 2)
        
    total_visits = len(visits)
    unique_patients = len(patient_ids)
    avg_visits_patient = 0.0
    if unique_patients > 0:
        avg_visits_patient = round(total_visits / unique_patients, 2)
        
    return OperationalReportResponse(
        total_visits_count=total_visits,
        unique_patients_count=unique_patients,
        average_visits_per_patient=avg_visits_patient,
        daily_visits=daily_visits,
        average_consultation_time_mins=avg_consult_time,
        average_lab_turnaround_time_mins=avg_lab_time
    )

@router.get("/dashboard-summary")
@router.get("/dashboard-summary/")
async def get_dashboard_summary(current_user: dict = Depends(get_current_user)):
    # Establish base tenant/branch query filter
    query = get_branch_filter(current_user)
    
    # Calculate boundaries for "today" in local/UTC time
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    today_end = today_start + timedelta(days=1) - timedelta(microseconds=1)
    
    # Create time filter for today
    today_filter = {"$gte": today_start, "$lte": today_end}
    
    stats = {}
    role = current_user.get("role")
    
    # 1. Total Tenants & Branches for Super Admin
    if role == "super_admin":
        db = get_db()
        stats["total_tenants"] = await db.tenants.count_documents({})
        stats["total_branches"] = await db.branches.count_documents({})
        stats["active_admins"] = await db.users.count_documents({"role": {"$in": ["hospital_admin", "branch_admin"]}})
        return stats

    # For hospital_admin, branch_admin, doctor, nurse, receptionist, etc.
    # Today's Patients registered
    patients_col = get_patients_collection()
    patients_query = query.copy()
    patients_query["created_at"] = today_filter
    stats["today_patients"] = await patients_col.count_documents(patients_query)
    
    # Appointments booked (scheduled for today)
    appts_col = get_appointments_collection()
    appts_query = query.copy()
    # Check if appointment_date is today or stores as datetime
    # Support both datetime and date string filters
    appts_query["$or"] = [
        {"appointment_date": today_filter},
        {"appointment_date": now.strftime("%Y-%m-%d")}
    ]
    stats["appointments_booked"] = await appts_col.count_documents(appts_query)
    
    # Active Queue Tokens
    tokens_col = get_queue_tokens_collection()
    tokens_query = query.copy()
    tokens_query["status"] = {"$in": ["waiting", "serving"]}
    stats["active_queue_tokens"] = await tokens_col.count_documents(tokens_query)
    
    # Today's Collections (Payments)
    payments_col = get_payments_collection()
    payments_query = query.copy()
    payments_query["created_at"] = today_filter
    payments = await payments_col.find(payments_query).to_list(None)
    stats["today_collections"] = round(sum(p.get("amount_paid", 0.0) for p in payments), 2)
    
    # Active Doctors (All doctors in the branch/tenant)
    users_col = get_users_collection()
    doctors_query = query.copy()
    doctors_query["role"] = {"$in": ["doctor", "surgeon", "anesthetist"]}
    stats["active_doctors"] = await users_col.count_documents(doctors_query)
    
    # OT Rooms Occupied
    ot_bookings_col = get_ot_bookings_collection()
    ot_query = query.copy()
    ot_query["status"] = {"$in": ["scheduled", "in_progress"]}
    ot_query["scheduled_start"] = today_filter
    stats["ot_rooms_occupied"] = await ot_bookings_col.count_documents(ot_query)
    
    # Doctor specific stats (if user is a doctor)
    if role in ["doctor", "surgeon", "anesthetist"]:
        doctor_id = current_user.get("_id")
        
        # Today's consultations done by this doctor
        visits_col = get_visits_collection()
        visits_query = query.copy()
        visits_query["doctor_id"] = ObjectId(doctor_id)
        visits_query["status"] = "completed"
        visits_query["visit_date"] = today_filter
        stats["doctor_consultations_done"] = await visits_col.count_documents(visits_query)
        
        # Pending lab reviews for patients of this doctor
        labs_col = get_lab_orders_collection()
        labs_query = query.copy()
        labs_query["doctor_id"] = ObjectId(doctor_id)
        labs_query["status"] = "completed"
        stats["doctor_pending_labs"] = await labs_col.count_documents(labs_query)
        
        # Pending prescriptions
        rx_col = get_prescriptions_collection()
        rx_query = query.copy()
        rx_query["doctor_id"] = ObjectId(doctor_id)
        rx_query["status"] = "pending"
        stats["doctor_pending_rx"] = await rx_col.count_documents(rx_query)
        
        # Upcoming OT bookings for this doctor today
        ot_doctor_query = query.copy()
        ot_doctor_query["surgeon_id"] = ObjectId(doctor_id)
        ot_doctor_query["scheduled_start"] = today_filter
        stats["doctor_upcoming_ot"] = await ot_bookings_col.count_documents(ot_doctor_query)
        
    return stats

@router.get("/doctor-summary")
@router.get("/doctor-summary/")
async def get_doctor_summary(current_user: dict = Depends(get_current_user)):
    """Fetch analytics/summary stats for the doctor's dashboard panel."""
    role = current_user.get("role")
    doctor_id = current_user.get("_id")
    tenant_id = current_user.get("tenant_id")
    
    # Standardize IDs
    try:
        doctor_oid = ObjectId(doctor_id)
        tenant_oid = ObjectId(tenant_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid session credentials")
        
    # Establish date ranges
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = datetime.utcnow().replace(hour=23, minute=59, second=59, microsecond=999999)
    last_30_days = datetime.utcnow() - timedelta(days=30)
    
    # Collection handles
    visits_col = get_visits_collection()
    appointments_col = get_appointments_collection()
    lab_col = get_lab_orders_collection()
    radiology_col = get_radiology_orders_collection()
    
    # 1. Today's Appointments/Queue count
    appointments_count = await appointments_col.count_documents({
        "tenant_id": tenant_oid,
        "doctor_id": doctor_oid,
        "appointment_date": {"$gte": today_start, "$lte": today_end},
        "status": {"$ne": "cancelled"}
    })
    
    # 2. Today's Completed Consultations
    completed_consults = await visits_col.count_documents({
        "tenant_id": tenant_oid,
        "doctor_id": doctor_oid,
        "created_at": {"$gte": today_start, "$lte": today_end},
        "status": "completed"
    })
    
    # 3. Pending Labs for Doctor's patients
    pending_labs = await lab_col.count_documents({
        "tenant_id": tenant_oid,
        "doctor_id": doctor_oid,
        "status": {"$in": ["ordered", "pending", "sample_collected"]}
    })
    
    # 4. Pending Radiology for Doctor's patients
    pending_radiology = await radiology_col.count_documents({
        "tenant_id": tenant_oid,
        "doctor_id": doctor_oid,
        "status": {"$in": ["ordered", "pending"]}
    })
    
    # 5. Monthly patients visited (Unique patient_ids)
    pipeline = [
        {
            "$match": {
                "tenant_id": tenant_oid,
                "doctor_id": doctor_oid,
                "created_at": {"$gte": last_30_days}
            }
        },
        {"$group": {"_id": "$patient_id"}},
        {"$count": "count"}
    ]
    cursor = visits_col.aggregate(pipeline)
    monthly_patients_res = await cursor.to_list(1)
    monthly_patients = monthly_patients_res[0]["count"] if monthly_patients_res else 0
    
    # 6. Monthly visits count
    monthly_visits = await visits_col.count_documents({
        "tenant_id": tenant_oid,
        "doctor_id": doctor_oid,
        "created_at": {"$gte": last_30_days}
    })
    
    return {
        "today_appointments": appointments_count,
        "today_completed": completed_consults,
        "pending_labs": pending_labs,
        "pending_radiology": pending_radiology,
        "monthly_patients": monthly_patients,
        "monthly_visits": monthly_visits
    }


@router.get("/audit-logs")
@router.get("/audit-logs/")
async def get_audit_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    user_name: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    entity: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    audit_col = get_audit_logs_collection()
    
    query = {}
    if current_user.get("role") != "super_admin":
        query["tenant_id"] = current_user.get("tenant_id")
        if current_user.get("role") != "hospital_admin" and current_user.get("branch_id"):
            query["branch_id"] = current_user.get("branch_id")
            
    if user_name:
        query["user_name"] = {"$regex": user_name, "$options": "i"}
    if action:
        query["action"] = action
    if entity:
        query["entity"] = entity
        
    date_query = {}
    if start_date:
        try:
            date_query["$gte"] = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format, use YYYY-MM-DD")
    if end_date:
        try:
            date_query["$lte"] = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1) - timedelta(microseconds=1)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format, use YYYY-MM-DD")
            
    if date_query:
        query["timestamp"] = date_query
        
    total = await audit_col.count_documents(query)
    
    cursor = audit_col.find(query).sort("timestamp", -1).skip((page - 1) * limit).limit(limit)
    logs = await cursor.to_list(limit)
    
    for log in logs:
        log["_id"] = str(log["_id"])
        if log.get("tenant_id"):
            log["tenant_id"] = str(log["tenant_id"])
        if log.get("branch_id"):
            log["branch_id"] = str(log["branch_id"])
        if log.get("timestamp"):
            log["timestamp"] = log["timestamp"].isoformat()
            
    return {
        "success": True,
        "total": total,
        "page": page,
        "limit": limit,
        "data": logs
    }

