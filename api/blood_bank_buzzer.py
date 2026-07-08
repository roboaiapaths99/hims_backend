from fastapi import APIRouter, Depends, HTTPException, status, Request
from bson import ObjectId
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, List

from database import (
    get_db,
    get_patients_collection,
    get_saas_plans_collection
)
from middleware.auth import get_current_user, inject_audit_fields
from middleware.audit import create_audit_log

router = APIRouter()

class BuzzerBroadcastRequest(BaseModel):
    blood_group: str

class BuzzerResponseRequest(BaseModel):
    response: str  # accept, decline

@router.post("/broadcast-buzzer")
async def broadcast_buzzer(
    payload: BuzzerBroadcastRequest,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Broadcasts a real-time blood donation request buzzer to all connected patients."""
    tenant_id = current_user.get("tenant_id")
    branch_id = current_user.get("branch_id")
    if not tenant_id or not branch_id:
        raise HTTPException(status_code=400, detail="User must belong to a tenant and branch")
        
    db = get_db()
    broadcast_doc = {
        "tenant_id": ObjectId(tenant_id),
        "branch_id": ObjectId(branch_id),
        "blood_group": payload.blood_group.upper(),
        "status": "active",
        "created_at": datetime.utcnow(),
        "created_by": str(current_user["_id"])
    }
    res = await db.blood_donation_buzzers.insert_one(broadcast_doc)
    broadcast_id = str(res.inserted_id)
    
    # Broadcast to Socket.IO 'patients' room
    sio = request.app.state.sio
    await sio.emit(
        "blood_donation_buzzer",
        {
            "broadcast_id": broadcast_id,
            "blood_group": payload.blood_group.upper(),
            "hospital_name": current_user.get("name", "MediCloud Hospital")
        },
        room="patients"
    )
    
    # Query matching or fallback patients in tenant to trigger push notifications / SMS alerts
    try:
        patients_cursor = db.patients.find({
            "tenant_id": ObjectId(tenant_id),
            "blood_group": payload.blood_group.upper()
        })
        target_patients = await patients_cursor.to_list(None)
        if not target_patients:
            # Fallback to all patients in this branch
            patients_cursor = db.patients.find({"tenant_id": ObjectId(tenant_id)})
            target_patients = await patients_cursor.to_list(None)
            
        from services.notification import create_user_notification
        for p in target_patients:
            await create_user_notification(
                tenant_id=ObjectId(tenant_id),
                branch_id=ObjectId(branch_id),
                user_id=p["_id"],
                title=f"🚨 Urgent Blood Need: {payload.blood_group.upper()}",
                message=f"MediCloud Hospital has an emergency requirement for {payload.blood_group.upper()} blood. Open App to respond.",
                notification_type="blood_alert"
            )
    except Exception as n_err:
        print(f"Error dispatching blood buzzer mobile push notifications: {n_err}")
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user.get("name", "Staff Admin"),
        action="BLOOD_BUZZER_BROADCASTED",
        entity="blood_bank",
        entity_id=broadcast_id,
        details={"blood_group": payload.blood_group},
        ip_address=request.client.host if request.client else None,
        tenant_id=ObjectId(tenant_id),
        branch_id=ObjectId(branch_id)
    )
    
    return {"status": "success", "broadcast_id": broadcast_id}

@router.post("/buzzer/{broadcast_id}/respond")
async def respond_to_buzzer(
    broadcast_id: str,
    payload: BuzzerResponseRequest,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Processes patient response. If accepted, captures contact details and alerts admins in real-time."""
    db = get_db()
    try:
        b_oid = ObjectId(broadcast_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid broadcast ID format")
        
    broadcast = await db.blood_donation_buzzers.find_one({"_id": b_oid})
    if not broadcast:
        raise HTTPException(status_code=404, detail="Buzzer broadcast not found")
        
    response_doc = {
        "broadcast_id": b_oid,
        "tenant_id": broadcast["tenant_id"],
        "branch_id": broadcast["branch_id"],
        "user_id": current_user["_id"],
        "response": payload.response.lower(),
        "created_at": datetime.utcnow()
    }
    
    # If accepted, attach patient details
    if payload.response.lower() == "accept":
        # Resolve patient contact details
        patients_col = get_patients_collection()
        patient = await patients_col.find_one({"_id": current_user["_id"]})
        if patient:
            response_doc.update({
                "patient_name": f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip(),
                "phone": patient.get("phone", ""),
                "email": patient.get("email", ""),
                "blood_group": patient.get("blood_group", "Unknown")
            })
        else:
            response_doc.update({
                "patient_name": current_user.get("name", "Anonymous Donor"),
                "phone": current_user.get("phone", ""),
                "email": current_user.get("email", ""),
                "blood_group": "Unknown"
            })
            
        # Emit real-time response update to admins room
        sio = request.app.state.sio
        await sio.emit(
            "donation_accepted",
            {
                "broadcast_id": broadcast_id,
                "patient_name": response_doc["patient_name"],
                "phone": response_doc["phone"],
                "email": response_doc["email"],
                "blood_group": response_doc["blood_group"],
                "time": datetime.utcnow().isoformat()
            },
            room="admins"
        )
        
    await db.blood_donation_buzzer_responses.insert_one(response_doc)
    return {"status": "success", "response": payload.response}

@router.get("/buzzer/{broadcast_id}/responses")
async def list_buzzer_responses(
    broadcast_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Retrieves all accepted patient responses for a broadcast, displaying contact details."""
    db = get_db()
    try:
        b_oid = ObjectId(broadcast_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid broadcast ID format")
        
    cursor = db.blood_donation_buzzer_responses.find({
        "broadcast_id": b_oid,
        "response": "accept"
    }).sort("created_at", -1)
    
    responses = await cursor.to_list(None)
    result = []
    for r in responses:
        result.append({
            "id": str(r["_id"]),
            "patient_name": r.get("patient_name", "Unknown"),
            "phone": r.get("phone", ""),
            "email": r.get("email", ""),
            "blood_group": r.get("blood_group", "Unknown"),
            "time": r["created_at"].isoformat()
        })
    return result

@router.post("/buzzer/{broadcast_id}/stop")
async def stop_buzzer(
    broadcast_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Deactivates a broadcast buzzer."""
    db = get_db()
    try:
        b_oid = ObjectId(broadcast_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid broadcast ID format")
        
    await db.blood_donation_buzzers.update_one(
        {"_id": b_oid},
        {"$set": {"status": "stopped", "stopped_at": datetime.utcnow()}}
    )
    return {"status": "success", "message": "Buzzer stopped successfully"}
