from fastapi import APIRouter, Depends, HTTPException, status, Request
from bson import ObjectId
from datetime import datetime
from typing import List, Optional

from database import (
    get_telemedicine_sessions_collection,
    get_appointments_collection
)
from middleware.auth import (
    get_current_user,
    inject_audit_fields
)
from middleware.audit import create_audit_log
from config import settings
from models.telemedicine import TelemedicineCreate, TelemedicineResponse

router = APIRouter()

@router.post("/create-room", response_model=TelemedicineResponse)
async def create_room(
    payload: TelemedicineCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    sessions_col = get_telemedicine_sessions_collection()
    appointments_col = get_appointments_collection()
    
    # 1. Verify appointment ID
    try:
        appt_oid = ObjectId(payload.appointment_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid appointment_id format")
        
    appointment = await appointments_col.find_one({
        "_id": appt_oid,
        "tenant_id": current_user["tenant_id"]
    })
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment record not found")
        
    # 2. Check if an active session already exists for this appointment
    existing_session = await sessions_col.find_one({
        "appointment_id": appt_oid,
        "status": "active"
    })
    
    if existing_session:
        # Map values to model schema expectations
        existing_session["id"] = str(existing_session["_id"])
        existing_session["tenant_id"] = str(existing_session["tenant_id"])
        existing_session["branch_id"] = str(existing_session["branch_id"])
        existing_session["appointment_id"] = str(existing_session["appointment_id"])
        existing_session["jitsi_domain"] = settings.JITSI_DOMAIN
        return TelemedicineResponse(**existing_session)
        
    # 3. Create a new active session
    room_suffix = str(ObjectId())
    room_name = f"HMIS-TELE-APPT-{payload.appointment_id}-{room_suffix}"
    
    session_doc = {
        "tenant_id": current_user["tenant_id"],
        "branch_id": current_user["branch_id"],
        "appointment_id": appt_oid,
        "room_name": room_name,
        "status": "active",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    inject_audit_fields(current_user, session_doc)
    
    res = await sessions_col.insert_one(session_doc)
    session_doc["id"] = str(res.inserted_id)
    session_doc["tenant_id"] = str(session_doc["tenant_id"])
    session_doc["branch_id"] = str(session_doc["branch_id"])
    session_doc["appointment_id"] = str(session_doc["appointment_id"])
    session_doc["jitsi_domain"] = settings.JITSI_DOMAIN
    
    # 4. Create audit trail log
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="TELEMEDICINE_SESSION_CREATED",
        entity="telemedicine_sessions",
        entity_id=session_doc["id"],
        details={"room_name": room_name, "appointment_id": payload.appointment_id},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    return TelemedicineResponse(**session_doc)

@router.put("/sessions/{id}/close", response_model=TelemedicineResponse)
async def close_session(
    id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    sessions_col = get_telemedicine_sessions_collection()
    
    try:
        session_oid = ObjectId(id)
    except:
        raise HTTPException(status_code=400, detail="Invalid session ID format")
        
    session = await sessions_col.find_one({
        "_id": session_oid,
        "tenant_id": current_user["tenant_id"]
    })
    if not session:
        raise HTTPException(status_code=404, detail="Telemedicine session not found")
        
    await sessions_col.update_one(
        {"_id": session_oid},
        {
            "$set": {
                "status": "closed",
                "updated_at": datetime.utcnow(),
                "updated_by": str(current_user["_id"])
            }
        }
    )
    
    # Create audit log
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="TELEMEDICINE_SESSION_CLOSED",
        entity="telemedicine_sessions",
        entity_id=id,
        details={"room_name": session.get("room_name")},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    updated = await sessions_col.find_one({"_id": session_oid})
    updated["id"] = str(updated["_id"])
    updated["tenant_id"] = str(updated["tenant_id"])
    updated["branch_id"] = str(updated["branch_id"])
    updated["appointment_id"] = str(updated["appointment_id"])
    updated["jitsi_domain"] = settings.JITSI_DOMAIN
    
    return TelemedicineResponse(**updated)

@router.get("/sessions/{id}", response_model=TelemedicineResponse)
async def get_session(
    id: str,
    current_user: dict = Depends(get_current_user)
):
    sessions_col = get_telemedicine_sessions_collection()
    
    try:
        session_oid = ObjectId(id)
    except:
        raise HTTPException(status_code=400, detail="Invalid session ID format")
        
    session = await sessions_col.find_one({
        "_id": session_oid,
        "tenant_id": current_user["tenant_id"]
    })
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    session["id"] = str(session["_id"])
    session["tenant_id"] = str(session["tenant_id"])
    session["branch_id"] = str(session["branch_id"])
    session["appointment_id"] = str(session["appointment_id"])
    session["jitsi_domain"] = settings.JITSI_DOMAIN
    
    return TelemedicineResponse(**session)

@router.get("/sessions/{id}/public", response_model=TelemedicineResponse)
async def get_public_session(
    id: str
):
    sessions_col = get_telemedicine_sessions_collection()
    
    try:
        session_oid = ObjectId(id)
    except:
        raise HTTPException(status_code=400, detail="Invalid session ID format")
        
    session = await sessions_col.find_one({
        "_id": session_oid
    })
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
        
    session["id"] = str(session["_id"])
    session["tenant_id"] = str(session["tenant_id"])
    session["branch_id"] = str(session["branch_id"])
    session["appointment_id"] = str(session["appointment_id"])
    session["jitsi_domain"] = settings.JITSI_DOMAIN
    
    return TelemedicineResponse(**session)

@router.get("/sessions/appointment/{appt_id}", response_model=TelemedicineResponse)
async def get_session_by_appointment(
    appt_id: str,
    current_user: dict = Depends(get_current_user)
):
    sessions_col = get_telemedicine_sessions_collection()
    
    try:
        appt_oid = ObjectId(appt_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid appointment ID format")
        
    session = await sessions_col.find_one({
        "appointment_id": appt_oid,
        "status": "active",
        "tenant_id": current_user["tenant_id"]
    })
    if not session:
        raise HTTPException(status_code=404, detail="No active telemedicine session found for this appointment")
        
    session["id"] = str(session["_id"])
    session["tenant_id"] = str(session["tenant_id"])
    session["branch_id"] = str(session["branch_id"])
    session["appointment_id"] = str(session["appointment_id"])
    session["jitsi_domain"] = settings.JITSI_DOMAIN
    
    return TelemedicineResponse(**session)
