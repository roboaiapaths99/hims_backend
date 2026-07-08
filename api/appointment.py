from fastapi import APIRouter, Depends, HTTPException, status, Request
from bson import ObjectId
from datetime import datetime, time
from typing import Optional, List, Dict

from database import (
    get_appointments_collection, get_queue_tokens_collection, 
    get_patients_collection, get_users_collection, get_departments_collection
)
from middleware.auth import (
    get_current_user, get_tenant_filter, get_branch_filter, inject_audit_fields
)
from middleware.audit import create_audit_log
from models.appointment import (
    AppointmentCreate, AppointmentResponse, AppointmentUpdate,
    QueueTokenResponse
)

router = APIRouter()

# Helper to check doctor slot availability
async def check_doctor_availability(
    tenant_id: ObjectId, 
    branch_id: ObjectId, 
    doctor_id: ObjectId, 
    app_date: datetime, 
    start_time: str, 
    end_time: str,
    exclude_appointment_id: Optional[ObjectId] = None
) -> bool:
    from database import get_doctor_schedules_collection, get_doctor_leaves_collection
    schedules_col = get_doctor_schedules_collection()
    leaves_col = get_doctor_leaves_collection()
    appointments_col = get_appointments_collection()
    
    # 1. Check if doctor is on leave
    start_of_day = datetime.combine(app_date.date(), time.min)
    end_of_day = datetime.combine(app_date.date(), time.max)
    
    leave_query = {
        "doctor_id": doctor_id,
        "tenant_id": tenant_id,
        "status": "approved",
        "start_date": {"$lte": end_of_day},
        "end_date": {"$gte": start_of_day}
    }
    on_leave = await leaves_col.find_one(leave_query)
    if on_leave:
        return False
        
    # 2. Check weekly schedule
    schedule = await schedules_col.find_one({"doctor_id": doctor_id, "tenant_id": tenant_id})
    if schedule:
        day_idx = app_date.weekday()
        day_config = None
        for ws in schedule.get("weekly_schedules", []):
            if ws.get("day_of_week") == day_idx:
                day_config = ws
                break
                
        if not day_config or not day_config.get("is_available", True):
            return False
            
        # Verify requested slot falls within at least one active shift window
        fits_shift = False
        for shift in day_config.get("shifts", []):
            if start_time >= shift["start_time"] and end_time <= shift["end_time"]:
                fits_shift = True
                break
        if not fits_shift:
            return False
            
    # 3. Query overlap
    query = {
        "tenant_id": tenant_id,
        "branch_id": branch_id,
        "doctor_id": doctor_id,
        "appointment_date": app_date,
        "status": {"$ne": "cancelled"},
        "$or": [
            # Case 1: Start time is between another appointment
            {"start_time": {"$lte": start_time}, "end_time": {"$gt": start_time}},
            # Case 2: End time is between another appointment
            {"start_time": {"$lt": end_time}, "end_time": {"$gte": end_time}},
            # Case 3: Another appointment is completely inside this slot
            {"start_time": {"$gte": start_time}, "end_time": {"$lte": end_time}}
        ]
    }
    
    if exclude_appointment_id:
        query["_id"] = {"$ne": exclude_appointment_id}
        
    overlap = await appointments_col.find_one(query)
    return overlap is None

# Helper to check patient slot availability
async def check_patient_availability(
    tenant_id: ObjectId, 
    branch_id: ObjectId, 
    patient_id: ObjectId, 
    app_date: datetime, 
    start_time: str, 
    end_time: str,
    exclude_appointment_id: Optional[ObjectId] = None
) -> bool:
    appointments_col = get_appointments_collection()
    
    query = {
        "tenant_id": tenant_id,
        "branch_id": branch_id,
        "patient_id": patient_id,
        "appointment_date": app_date,
        "status": {"$ne": "cancelled"},
        "$or": [
            {"start_time": {"$lte": start_time}, "end_time": {"$gt": start_time}},
            {"start_time": {"$lt": end_time}, "end_time": {"$gte": end_time}},
            {"start_time": {"$gte": start_time}, "end_time": {"$lte": end_time}}
        ]
    }
    
    if exclude_appointment_id:
        query["_id"] = {"$ne": exclude_appointment_id}
        
    overlap = await appointments_col.find_one(query)
    return overlap is None

# ------------------------------------------------------------------
# APPOINTMENT SERVICES
# ------------------------------------------------------------------

@router.post("", response_model=AppointmentResponse)
@router.post("/", response_model=AppointmentResponse)
async def create_appointment(payload: AppointmentCreate, request: Request, current_user: dict = Depends(get_current_user)):
    appointments_col = get_appointments_collection()
    patients_col = get_patients_collection()
    users_col = get_users_collection()
    depts_col = get_departments_collection()
    
    tenant_oid = current_user["tenant_id"]
    branch_oid = current_user["branch_id"]
    
    try:
        patient_oid = ObjectId(payload.patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient ID")
        
    # Support cross-hospital target tenant mapping for patients
    if current_user.get("role") == "patient":
        if payload.tenant_id:
            try:
                target_tenant_oid = ObjectId(payload.tenant_id)
            except:
                raise HTTPException(status_code=400, detail="Invalid target tenant_id format")
            
            if payload.branch_id:
                try:
                    target_branch_oid = ObjectId(payload.branch_id)
                except:
                    raise HTTPException(status_code=400, detail="Invalid target branch_id format")
            else:
                target_branch_oid = branch_oid
                
            if target_tenant_oid != tenant_oid:
                # Find patient details in their original home tenant
                source_patient = await patients_col.find_one({"_id": patient_oid, "tenant_id": tenant_oid})
                if not source_patient:
                    raise HTTPException(status_code=404, detail="Source patient profile not found")
                    
                # Check if patient profile already exists in target tenant by phone
                target_patient = await patients_col.find_one({"phone": source_patient["phone"], "tenant_id": target_tenant_oid})
                if not target_patient:
                    # Replicate basic patient profile to target tenant & branch
                    from api.patient import generate_patient_mrn
                    new_mrn = await generate_patient_mrn(target_tenant_oid, target_branch_oid)
                    
                    new_patient_doc = {
                        "tenant_id": target_tenant_oid,
                        "branch_id": target_branch_oid,
                        "first_name": source_patient.get("first_name"),
                        "last_name": source_patient.get("last_name"),
                        "phone": source_patient.get("phone"),
                        "email": source_patient.get("email"),
                        "dob": source_patient.get("dob"),
                        "gender": source_patient.get("gender"),
                        "address": source_patient.get("address"),
                        "emergency_contact_name": source_patient.get("emergency_contact_name", "Emergency"),
                        "emergency_contact_phone": source_patient.get("emergency_contact_phone", "9999999999"),
                        "mrn": new_mrn,
                        "created_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                    res_p = await patients_col.insert_one(new_patient_doc)
                    patient_oid = res_p.inserted_id
                    patient = new_patient_doc
                else:
                    patient_oid = target_patient["_id"]
                    patient = target_patient
                    
                # Re-route local scoping parameters to the target tenant
                tenant_oid = target_tenant_oid
                branch_oid = target_branch_oid
            else:
                patient = await patients_col.find_one({"_id": patient_oid, "tenant_id": tenant_oid})
        else:
            patient = await patients_col.find_one({"_id": patient_oid, "tenant_id": tenant_oid})
    else:
        patient = await patients_col.find_one({"_id": patient_oid, "tenant_id": tenant_oid})
        
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
        
    # Verify doctor is active
    try:
        doctor_oid = ObjectId(payload.doctor_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid doctor ID")
    doctor = await users_col.find_one({"_id": doctor_oid, "tenant_id": tenant_oid, "role": {"$in": ["doctor", "surgeon", "anesthetist"]}})
    if not doctor:
        raise HTTPException(status_code=404, detail="Practitioner doctor not found")
        
    # Verify department exists
    try:
        dept_oid = ObjectId(payload.department_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid department ID")
    dept = await depts_col.find_one({"_id": dept_oid, "tenant_id": tenant_oid})
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
        
    # Ensure date has no time parts (UTC midnight)
    app_date_utc = datetime.combine(payload.appointment_date.date(), time.min)
    
    # Check Doctor Slot Availability
    is_available = await check_doctor_availability(
        tenant_oid, branch_oid, doctor_oid, app_date_utc, payload.start_time, payload.end_time
    )
    if not is_available:
        raise HTTPException(
            status_code=400,
            detail=f"The selected time slot ({payload.start_time} - {payload.end_time}) is already booked for this doctor."
        )

    # Check Patient Slot Availability (double booking prevention)
    is_patient_available = await check_patient_availability(
        tenant_oid, branch_oid, patient_oid, app_date_utc, payload.start_time, payload.end_time
    )
    if not is_patient_available:
        raise HTTPException(
            status_code=400,
            detail=f"The patient is already scheduled for another consultation during this time window ({payload.start_time} - {payload.end_time})."
        )
        
    doc = payload.dict()
    doc["patient_id"] = patient_oid
    doc["doctor_id"] = doctor_oid
    doc["department_id"] = dept_oid
    doc["appointment_date"] = app_date_utc
    
    inject_audit_fields(current_user, doc)
    doc["tenant_id"] = tenant_oid
    doc["branch_id"] = branch_oid
    
    res = await appointments_col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    doc["patient_id"] = str(doc["patient_id"])
    doc["doctor_id"] = str(doc["doctor_id"])
    doc["department_id"] = str(doc["department_id"])
    
    response_data = {
        **doc,
        "mrn": patient.get("mrn"),
        "patient_name": f"{patient.get('first_name')} {patient.get('last_name')}",
        "doctor_name": doctor.get("name"),
        "department_name": dept.get("name")
    }
    
    # Emit socket updates if available
    sio = getattr(request.app.state, "sio", None)
    if sio:
        await sio.emit("appointment.created", {"appointment_id": doc["id"], "branch_id": doc["branch_id"]}, room=f"branch_{doc['branch_id']}")
        
    # Queue appointment confirmation notification
    try:
        from tasks import send_appointment_notification
        send_appointment_notification.delay(doc["id"])
    except Exception as e:
        print(f"Error queuing background appointment notification: {e}")
        
    try:
        from services.notification_service import NotificationService
        patient_name = f"{patient.get('first_name')} {patient.get('last_name')}"
        doctor_user = await users_col.find_one({"_id": doctor_oid})
        doctor_phone = doctor_user.get("phone") if doctor_user else None
        doctor_push_token = doctor_user.get("expo_push_token") if doctor_user else None
        
        await NotificationService.dispatch(
            tenant_id=tenant_oid,
            branch_id=branch_oid,
            user_id=doctor_oid,
            title="New Appointment Scheduled",
            message=f"Patient {patient_name} has been scheduled for {payload.start_time} - {payload.end_time} on {app_date_utc.strftime('%Y-%m-%d')}.",
            notification_type="info",
            phone_number=doctor_phone,
            expo_push_token=doctor_push_token
        )
    except Exception as ne:
        print(f"Error dispatching doctor notification for appointment: {ne}")
        
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="APPOINTMENT_CREATED",
        entity="appointments",
        entity_id=doc["id"],
        details={"patient": response_data["patient_name"], "date": payload.appointment_date.strftime("%Y-%m-%d")},
        ip_address=request.client.host if request.client else None,
        tenant_id=tenant_oid,
        branch_id=branch_oid
    )
    
    return AppointmentResponse(**response_data)

@router.get("", response_model=List[AppointmentResponse])
@router.get("/", response_model=List[AppointmentResponse])
async def list_appointments(
    date: Optional[str] = None, 
    doctor_id: Optional[str] = None, 
    patient_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    appointments_col = get_appointments_collection()
    patients_col = get_patients_collection()
    users_col = get_users_collection()
    depts_col = get_departments_collection()
    
    query = get_tenant_filter(current_user)
    
    if date:
        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
            app_date_utc = datetime.combine(dt.date(), time.min)
            query["appointment_date"] = app_date_utc
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")
            
    if doctor_id:
        try:
            query["doctor_id"] = ObjectId(doctor_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid doctor ID format")
            
    if patient_id:
        try:
            query["patient_id"] = ObjectId(patient_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid patient ID format")
            
    docs = await appointments_col.find(query).sort("start_time", 1).to_list(None)
    result = []
    
    # Pre-cache details to optimize DB lookups
    patient_cache = {}
    doctor_cache = {}
    dept_cache = {}
    
    for doc in docs:
        p_id = doc["patient_id"]
        d_id = doc["doctor_id"]
        dep_id = doc["department_id"]
        
        # Load Patient Details
        if p_id not in patient_cache:
            p_doc = await patients_col.find_one({"_id": p_id})
            patient_cache[p_id] = p_doc or {}
        p_info = patient_cache[p_id]
        
        # Load Doctor Details
        if d_id not in doctor_cache:
            d_doc = await users_col.find_one({"_id": d_id})
            doctor_cache[d_id] = d_doc or {}
        d_info = doctor_cache[d_id]
        
        # Load Dept Details
        if dep_id not in dept_cache:
            dep_doc = await depts_col.find_one({"_id": dep_id})
            dept_cache[dep_id] = dep_doc or {}
        dep_info = dept_cache[dep_id]
        
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["branch_id"] = str(doc["branch_id"])
        doc["patient_id"] = str(p_id)
        doc["doctor_id"] = str(d_id)
        doc["department_id"] = str(dep_id)
        
        res_item = {
            **doc,
            "mrn": p_info.get("mrn", "N/A"),
            "patient_name": f"{p_info.get('first_name', 'Unknown')} {p_info.get('last_name', '')}".strip(),
            "doctor_name": d_info.get("name", "Unknown"),
            "department_name": dep_info.get("name", "Unknown")
        }
        result.append(AppointmentResponse(**res_item))
        
    return result

@router.post("/{id}/check-in", response_model=QueueTokenResponse)
async def check_in_patient(id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Triggers patient check-in status updates and allocates sequential token based on department code"""
    appointments_col = get_appointments_collection()
    tokens_col = get_queue_tokens_collection()
    patients_col = get_patients_collection()
    users_col = get_users_collection()
    depts_col = get_departments_collection()
    
    tenant_oid = current_user["tenant_id"]
    branch_oid = current_user["branch_id"]
    
    try:
        app_oid = ObjectId(id)
    except:
        raise HTTPException(status_code=400, detail="Invalid appointment ID format")
        
    # Get active appointment
    app = await appointments_col.find_one({"_id": app_oid, "tenant_id": tenant_oid})
    if not app:
        raise HTTPException(status_code=404, detail="Appointment not found")
        
    if app["status"] != "scheduled":
        raise HTTPException(status_code=400, detail=f"Patient cannot check in, active status is: {app['status']}")
        
    # Get department code
    dept = await depts_col.find_one({"_id": app["department_id"]})
    dept_code = dept.get("code", "OPD").upper() if dept else "OPD"
    
    # Calculate sequential token for today for this department & branch
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = datetime.utcnow().replace(hour=23, minute=59, second=59, microsecond=999999)
    
    token_count = await tokens_col.count_documents({
        "tenant_id": tenant_oid,
        "branch_id": branch_oid,
        "assigned_at": {"$gte": today_start, "$lte": today_end},
        "token_number": {"$regex": f"^{dept_code}-"}
    })
    
    sequence = str(token_count + 1).zfill(3)
    token_number = f"{dept_code}-{sequence}"
    
    # Update appointment status to checked_in / waiting
    await appointments_col.update_one({"_id": app_oid}, {"$set": {"status": "waiting", "updated_at": datetime.utcnow()}})
    
    # Insert queue token
    token_doc = {
        "tenant_id": tenant_oid,
        "branch_id": branch_oid,
        "appointment_id": app_oid,
        "token_number": token_number,
        "status": "waiting",
        "assigned_at": datetime.utcnow()
    }
    
    res = await tokens_col.insert_one(token_doc)
    
    # Fetch names for response
    patient = await patients_col.find_one({"_id": app["patient_id"]})
    doctor = await users_col.find_one({"_id": app["doctor_id"]})
    
    response_data = {
        "id": str(res.inserted_id),
        "appointment_id": id,
        "token_number": token_number,
        "status": "waiting",
        "assigned_at": token_doc["assigned_at"],
        "patient_name": f"{patient.get('first_name')} {patient.get('last_name')}" if patient else "Unknown",
        "doctor_name": doctor.get("name") if doctor else "Unknown",
        "department_name": dept.get("name") if dept else "Unknown",
        "tenant_id": str(tenant_oid),
        "branch_id": str(branch_oid)
    }
    
    # Emit live Socket.IO update
    sio = getattr(request.app.state, "sio", None)
    if sio:
        await sio.emit("queue.updated", {"branch_id": str(branch_oid)}, room=f"branch_{branch_oid}")
        
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="PATIENT_CHECKED_IN",
        entity="appointments",
        entity_id=id,
        details={"token": token_number, "patient": response_data["patient_name"]},
        ip_address=request.client.host if request.client else None,
        tenant_id=tenant_oid,
        branch_id=branch_oid
    )
    
    return QueueTokenResponse(**response_data)

@router.get("/queue", response_model=List[QueueTokenResponse])
async def list_active_queue(current_user: dict = Depends(get_current_user)):
    """Fetch active tokens sorting by triage or arrival priority"""
    tokens_col = get_queue_tokens_collection()
    appointments_col = get_appointments_collection()
    patients_col = get_patients_collection()
    users_col = get_users_collection()
    depts_col = get_departments_collection()
    
    query = get_branch_filter(current_user)
    # Active tokens (not completed or skipped)
    query["status"] = {"$in": ["waiting", "in_vitals", "ready_for_doctor", "in_consultation"]}
    
    # Limit to tokens assigned today
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    query["assigned_at"] = {"$gte": today_start}
    
    docs = await tokens_col.find(query).sort("assigned_at", 1).to_list(None)
    result = []
    
    for doc in docs:
        app = await appointments_col.find_one({"_id": doc["appointment_id"]})
        if not app:
            continue
            
        patient = await patients_col.find_one({"_id": app["patient_id"]})
        doctor = await users_col.find_one({"_id": app["doctor_id"]})
        dept = await depts_col.find_one({"_id": app["department_id"]})
        
        item = {
            "id": str(doc["_id"]),
            "appointment_id": str(doc["appointment_id"]),
            "token_number": doc["token_number"],
            "status": doc["status"],
            "assigned_at": doc["assigned_at"],
            "patient_name": f"{patient.get('first_name', 'Unknown')} {patient.get('last_name', '')}".strip() if patient else "Unknown",
            "doctor_name": doctor.get("name", "Unknown") if doctor else "Unknown",
            "department_name": dept.get("name", "Unknown") if dept else "Unknown",
            "tenant_id": str(doc["tenant_id"]),
            "branch_id": str(doc["branch_id"])
        }
        result.append(QueueTokenResponse(**item))
        
    return result
