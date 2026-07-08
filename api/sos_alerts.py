from fastapi import APIRouter, Depends, HTTPException, status, Request
from bson import ObjectId
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, List

from database import (
    get_db,
    get_patients_collection,
    get_branches_collection
)
from middleware.auth import get_current_user, inject_audit_fields

router = APIRouter()

class SOSAlertRequest(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class SOSAcceptRequest(BaseModel):
    driver_name: str
    ambulance_no: str
    phone: str

@router.post("/sos")
async def trigger_sos(
    payload: SOSAlertRequest,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Triggers an SOS emergency alert, capturing geolocation with fallback parameters, and alerts drivers."""
    tenant_id = current_user.get("tenant_id")
    branch_id = current_user.get("branch_id")
    if not tenant_id or not branch_id:
        raise HTTPException(status_code=400, detail="User must belong to a tenant and branch")
        
    db = get_db()
    branches_col = get_branches_collection()
    
    # Geolocation fallback (hospital branch coordinates or default randomized city center)
    lat = payload.latitude
    lng = payload.longitude
    fallback_used = False
    
    if lat is None or lng is None:
        fallback_used = True
        branch = await branches_col.find_one({"_id": ObjectId(branch_id)})
        # Default to branch coordinates if configured, otherwise Pune city center default
        if branch and branch.get("latitude") and branch.get("longitude"):
            lat = branch["latitude"]
            lng = branch["longitude"]
        else:
            lat = 18.5204
            lng = 73.8567
            
    # Load patient contact details
    patients_col = get_patients_collection()
    patient = await patients_col.find_one({"_id": current_user["_id"]})
    
    patient_name = f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip() if patient else current_user.get("name", "Unknown Patient")
    phone = patient.get("phone", "") if patient else current_user.get("phone", "")
    mrn = patient.get("mrn", "Unknown") if patient else "Unknown"
    
    sos_doc = {
        "tenant_id": ObjectId(tenant_id),
        "branch_id": ObjectId(branch_id),
        "patient_id": current_user["_id"],
        "patient_name": patient_name,
        "phone": phone,
        "mrn": mrn,
        "latitude": lat,
        "longitude": lng,
        "fallback_used": fallback_used,
        "status": "pending",
        "created_at": datetime.utcnow(),
        "dispatched_at": None,
        "driver_info": None
    }
    
    res = await db.emergency_sos.insert_one(sos_doc)
    sos_id = str(res.inserted_id)
    
    # Broadcast to Socket.IO 'drivers' room
    sio = request.app.state.sio
    await sio.emit(
        "sos_emergency_alert",
        {
            "sos_id": sos_id,
            "patient_name": patient_name,
            "phone": phone,
            "mrn": mrn,
            "latitude": lat,
            "longitude": lng,
            "fallback_used": fallback_used,
            "time": datetime.utcnow().isoformat()
        },
        room="drivers"
    )
    
    # Query drivers / ambulance workers in this branch to dispatch real-time mobile push / SMS alerts
    try:
        drivers_cursor = db.users.find({
            "tenant_id": ObjectId(tenant_id),
            "branch_id": ObjectId(branch_id),
            "role": {"$in": ["driver", "ambulance_driver", "staff", "branch_admin"]}
        })
        branch_drivers = await drivers_cursor.to_list(None)
        
        from services.notification import create_user_notification
        for d in branch_drivers:
            await create_user_notification(
                tenant_id=ObjectId(tenant_id),
                branch_id=ObjectId(branch_id),
                user_id=d["_id"],
                title="🚨 SOS PANIC ALARM",
                message=f"Patient {patient_name} triggered SOS! Coordinates: Lat {lat}, Lng {lng}. Open app to claim.",
                notification_type="sos_alert"
            )
    except Exception as n_err:
        print(f"Error dispatching driver SOS push notifications: {n_err}")
        
    return {"status": "success", "sos_id": sos_id, "latitude": lat, "longitude": lng, "fallback_used": fallback_used}

@router.post("/sos/{sos_id}/accept")
async def accept_sos(
    sos_id: str,
    payload: SOSAcceptRequest,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Allows an ambulance driver to claim the emergency. Updates status and alerts patient."""
    db = get_db()
    try:
        s_oid = ObjectId(sos_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid SOS ID format")
        
    sos = await db.emergency_sos.find_one({"_id": s_oid})
    if not sos:
        raise HTTPException(status_code=404, detail="SOS alert record not found")
        
    driver_info = {
        "driver_name": payload.driver_name,
        "ambulance_no": payload.ambulance_no,
        "phone": payload.phone,
        "user_id": str(current_user["_id"])
    }
    
    await db.emergency_sos.update_one(
        {"_id": s_oid},
        {
            "$set": {
                "status": "dispatched",
                "dispatched_at": datetime.utcnow(),
                "driver_info": driver_info
            }
        }
    )
    
    # Alert the patient via Socket.IO room or dynamic broadcast
    sio = request.app.state.sio
    await sio.emit(
        "sos_dispatched",
        {
            "sos_id": sos_id,
            "driver_name": payload.driver_name,
            "ambulance_no": payload.ambulance_no,
            "phone": payload.phone
        },
        room=f"patient_user_{sos['patient_id']}"
    )
    
    return {"status": "success", "message": "SOS emergency dispatch registered successfully"}

@router.get("/sos/active")
async def list_active_sos(
    current_user: dict = Depends(get_current_user)
):
    """Retrieves all active, unclaimed SOS emergencies for the branch."""
    tenant_id = current_user.get("tenant_id")
    branch_id = current_user.get("branch_id")
    if not tenant_id or not branch_id:
        raise HTTPException(status_code=400, detail="User scope validation failed")
        
    db = get_db()
    cursor = db.emergency_sos.find({
        "tenant_id": ObjectId(tenant_id),
        "branch_id": ObjectId(branch_id),
        "status": "pending"
    }).sort("created_at", -1)
    
    docs = await cursor.to_list(None)
    result = []
    for doc in docs:
        result.append({
            "id": str(doc["_id"]),
            "patient_name": doc["patient_name"],
            "phone": doc["phone"],
            "mrn": doc["mrn"],
            "latitude": doc["latitude"],
            "longitude": doc["longitude"],
            "fallback_used": doc.get("fallback_used", False),
            "time": doc["created_at"].isoformat()
        })
    return result
