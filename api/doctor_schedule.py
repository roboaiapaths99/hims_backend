from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from bson import ObjectId
from datetime import datetime, timedelta, date, time
from typing import List, Optional

from database import (
    get_doctor_schedules_collection,
    get_doctor_leaves_collection,
    get_appointments_collection,
    get_users_collection
)
from middleware.auth import get_current_user, inject_audit_fields
from middleware.audit import create_audit_log
from models.doctor_schedule import (
    DoctorScheduleSaveRequest,
    DoctorScheduleResponse,
    LeaveScheduleRequest,
    DoctorLeaveResponse,
    DaySchedule
)

router = APIRouter()

def parse_time_str(time_str: str) -> time:
    """Helper to parse HH:MM string to datetime.time."""
    parts = time_str.split(":")
    return time(hour=int(parts[0]), minute=int(parts[1]))

def format_time(t: time) -> str:
    """Helper to format datetime.time to HH:MM."""
    return t.strftime("%H:%M")

@router.post("/schedules", response_model=DoctorScheduleResponse)
async def save_doctor_schedule(
    payload: DoctorScheduleSaveRequest,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Save or update weekly shift schedule and slot duration configuration for a doctor."""
    schedules_col = get_doctor_schedules_collection()
    users_col = get_users_collection()
    
    tenant_oid = current_user["tenant_id"]
    branch_oid = current_user["branch_id"]
    
    try:
        doctor_oid = ObjectId(payload.doctor_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid doctor ID format")
        
    # Verify doctor exists and belongs to this tenant/branch
    doctor = await users_col.find_one({"_id": doctor_oid, "tenant_id": tenant_oid})
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found in this branch")
        
    # Validate shift times
    for ds in payload.weekly_schedules:
        for shift in ds.shifts:
            try:
                start = parse_time_str(shift.start_time)
                end = parse_time_str(shift.end_time)
                if start >= end:
                    raise HTTPException(status_code=400, detail=f"Shift start time {shift.start_time} must be before end time {shift.end_time}")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid shift time format. Must be HH:MM")

    now = datetime.utcnow()
    existing = await schedules_col.find_one({"doctor_id": doctor_oid, "tenant_id": tenant_oid})
    
    doc_data = {
        "tenant_id": tenant_oid,
        "branch_id": branch_oid,
        "doctor_id": doctor_oid,
        "weekly_schedules": [ds.model_dump() for ds in payload.weekly_schedules],
        "slot_duration_minutes": payload.slot_duration_minutes,
        "updated_at": now
    }
    
    if existing:
        await schedules_col.update_one({"_id": existing["_id"]}, {"$set": doc_data})
        doc_id = str(existing["_id"])
        created_at = existing.get("created_at", now)
    else:
        doc_data["created_at"] = now
        res = await schedules_col.insert_one(doc_data)
        doc_id = str(res.inserted_id)
        created_at = now
        
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="DOCTOR_SCHEDULE_UPDATED",
        entity="doctor_schedules",
        entity_id=doc_id,
        details={"doctor_id": payload.doctor_id, "slot_duration": payload.slot_duration_minutes},
        ip_address=request.client.host if request.client else None,
        tenant_id=tenant_oid,
        branch_id=branch_oid
    )
    
    return DoctorScheduleResponse(
        id=doc_id,
        tenant_id=str(tenant_oid),
        branch_id=str(branch_oid),
        doctor_id=payload.doctor_id,
        weekly_schedules=payload.weekly_schedules,
        slot_duration_minutes=payload.slot_duration_minutes,
        created_at=created_at,
        updated_at=now
    )

@router.get("/schedules/{doctor_id}", response_model=DoctorScheduleResponse)
async def get_doctor_schedule(
    doctor_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Retrieve active weekly schedule and slot duration configuration for a doctor."""
    schedules_col = get_doctor_schedules_collection()
    
    try:
        doctor_oid = ObjectId(doctor_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid doctor ID format")
        
    doc = await schedules_col.find_one({"doctor_id": doctor_oid, "tenant_id": current_user["tenant_id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="No schedule configuration found for this doctor")
        
    return DoctorScheduleResponse(
        id=str(doc["_id"]),
        tenant_id=str(doc["tenant_id"]),
        branch_id=str(doc["branch_id"]),
        doctor_id=str(doc["doctor_id"]),
        weekly_schedules=[DaySchedule(**ds) for ds in doc.get("weekly_schedules", [])],
        slot_duration_minutes=doc.get("slot_duration_minutes", 15),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"]
    )

@router.post("/leaves", response_model=DoctorLeaveResponse)
async def schedule_leave(
    payload: LeaveScheduleRequest,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Register planned leaves for a doctor. Prevents slots booking during these dates."""
    leaves_col = get_doctor_leaves_collection()
    users_col = get_users_collection()
    
    tenant_oid = current_user["tenant_id"]
    branch_oid = current_user["branch_id"]
    
    try:
        doctor_oid = ObjectId(payload.doctor_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid doctor ID format")
        
    doctor = await users_col.find_one({"_id": doctor_oid, "tenant_id": tenant_oid})
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor not found")
        
    if payload.start_date > payload.end_date:
        raise HTTPException(status_code=400, detail="Start date must be before end date")
        
    leave_doc = {
        "tenant_id": tenant_oid,
        "branch_id": branch_oid,
        "doctor_id": doctor_oid,
        "start_date": payload.start_date,
        "end_date": payload.end_date,
        "reason": payload.reason,
        "status": "approved",
        "created_at": datetime.utcnow()
    }
    
    res = await leaves_col.insert_one(leave_doc)
    doc_id = str(res.inserted_id)
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="DOCTOR_LEAVE_APPROVED",
        entity="doctor_leaves",
        entity_id=doc_id,
        details={"doctor_id": payload.doctor_id, "start": payload.start_date.isoformat(), "end": payload.end_date.isoformat()},
        ip_address=request.client.host if request.client else None,
        tenant_id=tenant_oid,
        branch_id=branch_oid
    )
    
    return DoctorLeaveResponse(
        id=doc_id,
        tenant_id=str(tenant_oid),
        branch_id=str(branch_oid),
        doctor_id=payload.doctor_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason,
        status="approved",
        created_at=leave_doc["created_at"]
    )

@router.get("/slots")
async def get_available_slots(
    doctor_id: str,
    target_date: str = Query(..., description="YYYY-MM-DD format"),
    current_user: dict = Depends(get_current_user)
):
    """Retrieve list of available time slots for a doctor on a specific date, excluding leaves and overlaps."""
    schedules_col = get_doctor_schedules_collection()
    leaves_col = get_doctor_leaves_collection()
    appointments_col = get_appointments_collection()
    
    try:
        doctor_oid = ObjectId(doctor_id)
        target_dt = datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Must be YYYY-MM-DD")
    except:
        raise HTTPException(status_code=400, detail="Invalid doctor ID format")
        
    tenant_oid = current_user["tenant_id"]
    
    # 1. Check if doctor is on leave on the target date
    start_of_day = datetime.combine(target_dt.date(), time.min)
    end_of_day = datetime.combine(target_dt.date(), time.max)
    
    leave_query = {
        "doctor_id": doctor_oid,
        "tenant_id": tenant_oid,
        "status": "approved",
        "start_date": {"$lte": end_of_day},
        "end_date": {"$gte": start_of_day}
    }
    on_leave = await leaves_col.find_one(leave_query)
    if on_leave:
        return {"date": target_date, "available": False, "reason": "Doctor is on leave", "slots": []}
        
    # 2. Get weekly schedule template
    schedule = await schedules_col.find_one({"doctor_id": doctor_oid, "tenant_id": tenant_oid})
    if not schedule:
        return {"date": target_date, "available": False, "reason": "No schedule configured for doctor", "slots": []}
        
    day_idx = target_dt.weekday()  # 0=Monday, 6=Sunday
    day_config = None
    for ws in schedule.get("weekly_schedules", []):
        if ws.get("day_of_week") == day_idx:
            day_config = ws
            break
            
    if not day_config or not day_config.get("is_available", True):
        return {"date": target_date, "available": False, "reason": "Doctor is not scheduled to work on this weekday", "slots": []}
        
    slot_duration = schedule.get("slot_duration_minutes", 15)
    
    # 3. Query all active appointments for this doctor on target date
    appointments = await appointments_col.find({
        "doctor_id": doctor_oid,
        "tenant_id": tenant_oid,
        "appointment_date": start_of_day,
        "status": {"$ne": "cancelled"}
    }).to_list(None)
    
    booked_slots = []
    for app in appointments:
        booked_slots.append({
            "start": app["start_time"],
            "end": app["end_time"]
        })
        
    # 4. Generate all slots within the shift windows
    available_slots = []
    
    for shift in day_config.get("shifts", []):
        try:
            start_time = parse_time_str(shift["start_time"])
            end_time = parse_time_str(shift["end_time"])
        except:
            continue
            
        current_time = datetime.combine(target_dt.date(), start_time)
        shift_end = datetime.combine(target_dt.date(), end_time)
        
        while current_time + timedelta(minutes=slot_duration) <= shift_end:
            slot_start = current_time.time()
            slot_end = (current_time + timedelta(minutes=slot_duration)).time()
            
            start_str = format_time(slot_start)
            end_str = format_time(slot_end)
            
            # Check overlap with booked appointments
            is_booked = False
            for bs in booked_slots:
                # Overlap checking
                if (start_str >= bs["start"] and start_str < bs["end"]) or \
                   (end_str > bs["start"] and end_str <= bs["end"]) or \
                   (start_str <= bs["start"] and end_str >= bs["end"]):
                    is_booked = True
                    break
                    
            available_slots.append({
                "start_time": start_str,
                "end_time": end_str,
                "status": "booked" if is_booked else "available"
            })
            
            current_time += timedelta(minutes=slot_duration)
            
    return {
        "date": target_date,
        "available": True,
        "slot_duration_minutes": slot_duration,
        "slots": available_slots
    }
