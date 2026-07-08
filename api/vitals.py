from fastapi import APIRouter, Depends, HTTPException, status, Request
from bson import ObjectId
from datetime import datetime
from typing import List

from database import (
    get_vitals_collection, get_appointments_collection, 
    get_queue_tokens_collection, get_db
)
from middleware.auth import get_current_user, get_branch_filter, inject_audit_fields
from middleware.audit import create_audit_log
from models.vitals import VitalsCreate, VitalsResponse

router = APIRouter()

def calculate_news_score(bp_sys: int, pulse: int, temp_f: float, spo2: int) -> int:
    score = 0
    if bp_sys <= 90 or bp_sys >= 220:
        score += 3
    elif (91 <= bp_sys <= 100) or (200 <= bp_sys <= 219):
        score += 2
    elif 101 <= bp_sys <= 110:
        score += 1

    if pulse <= 40 or pulse >= 131:
        score += 3
    elif 111 <= pulse <= 130:
        score += 2
    elif (41 <= pulse <= 50) or (91 <= pulse <= 110):
        score += 1

    if spo2 < 92:
        score += 3
    elif spo2 in (92, 93):
        score += 2
    elif spo2 in (94, 95):
        score += 1

    if temp_f <= 95.0 or temp_f >= 102.3:
        score += 3
    elif 100.5 <= temp_f <= 102.2:
        score += 2
    elif 95.1 <= temp_f <= 96.8:
        score += 1

    return score

@router.post("", response_model=VitalsResponse)
@router.post("/", response_model=VitalsResponse)
async def record_vitals(payload: VitalsCreate, request: Request, current_user: dict = Depends(get_current_user)):
    vitals_col = get_vitals_collection()
    appointments_col = get_appointments_collection()
    tokens_col = get_queue_tokens_collection()
    
    tenant_oid = current_user["tenant_id"]
    branch_oid = current_user["branch_id"]
    
    try:
        patient_oid = ObjectId(payload.patient_id)
        app_oid = ObjectId(payload.appointment_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient ID or appointment ID format")
        
    # Verify appointment exists
    appointment = await appointments_col.find_one({"_id": app_oid, "tenant_id": tenant_oid})
    if not appointment:
        raise HTTPException(status_code=404, detail="Associated patient appointment not found")
        
    # Calculate BMI: weight (kg) / height^2 (meters)
    height_m = payload.height / 100.0
    bmi = round(payload.weight / (height_m * height_m), 2)
    
    # Calculate NEWS score
    news = calculate_news_score(payload.bp_sys, payload.pulse, payload.temperature, payload.spo2)
    
    doc = payload.dict()
    doc["patient_id"] = patient_oid
    doc["appointment_id"] = app_oid
    doc["bmi"] = bmi
    doc["news_score"] = news
    
    if news >= 7:
        doc["triage_level"] = "red"
    elif news >= 5:
        doc["triage_level"] = "orange"
    elif news >= 4:
        doc["triage_level"] = "yellow"
    else:
        doc["triage_level"] = "green"
        
    inject_audit_fields(current_user, doc)
    
    res = await vitals_col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    doc["patient_id"] = str(doc["patient_id"])
    doc["appointment_id"] = str(doc["appointment_id"])
    
    # 1. Update appointment status to ready_for_doctor
    await appointments_col.update_one(
        {"_id": app_oid},
        {"$set": {"status": "ready_for_doctor", "updated_at": datetime.utcnow()}}
    )
    
    # 2. Update queue token status to ready_for_doctor
    await tokens_col.update_one(
        {"appointment_id": app_oid},
        {"$set": {"status": "ready_for_doctor"}}
    )
    
    try:
        app = await appointments_col.find_one({"_id": app_oid})
        if app:
            from services.notification_service import NotificationService
            from database import get_patients_collection, get_users_collection
            patients_col = get_patients_collection()
            users_col = get_users_collection()
            patient = await patients_col.find_one({"_id": patient_oid})
            patient_name = f"{patient.get('first_name')} {patient.get('last_name')}" if patient else "A patient"
            
            doctor_user = await users_col.find_one({"_id": app["doctor_id"]})
            doctor_phone = doctor_user.get("phone") if doctor_user else None
            doctor_push_token = doctor_user.get("expo_push_token") if doctor_user else None
            
            await NotificationService.dispatch(
                tenant_id=tenant_oid,
                branch_id=branch_oid,
                user_id=app["doctor_id"],
                title="Patient Vitals Ready",
                message=f"Vitals have been entered for {patient_name}. Triage level: {payload.triage_level}. Patient is ready in your consult queue.",
                notification_type="success",
                phone_number=doctor_phone,
                expo_push_token=doctor_push_token
            )
    except Exception as ne:
        print(f"Error dispatching doctor notification for vitals: {ne}")
    
    # Emit socket events to update screen panels in real-time
    sio = getattr(request.app.state, "sio", None)
    if sio:
        await sio.emit("queue.updated", {"branch_id": str(branch_oid)}, room=f"branch_{branch_oid}")
        await sio.emit("vitals.updated", {"patient_id": str(patient_oid), "branch_id": str(branch_oid)}, room=f"branch_{branch_oid}")
        if news >= 7:
            await sio.emit("news.critical", {
                "patient_id": str(patient_oid),
                "news_score": news,
                "branch_id": str(branch_oid)
            }, room=f"branch_{branch_oid}")
        
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="VITALS_RECORDED",
        entity="vitals",
        entity_id=doc["id"],
        details={"patient_id": payload.patient_id, "triage": doc["triage_level"], "news_score": news},
        ip_address=request.client.host if request.client else None,
        tenant_id=tenant_oid,
        branch_id=branch_oid
    )
    
    return VitalsResponse(**doc)

@router.get("/patient/{patient_id}", response_model=List[VitalsResponse])
async def get_patient_vitals_history(patient_id: str, current_user: dict = Depends(get_current_user)):
    """Fetch historic vitals tracking charts for a single patient"""
    vitals_col = get_vitals_collection()
    
    try:
        patient_oid = ObjectId(patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient ID format")
        
    query = {
        "tenant_id": current_user["tenant_id"],
        "patient_id": patient_oid
    }
    
    docs = await vitals_col.find(query).sort("created_at", -1).limit(20).to_list(None)
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["branch_id"] = str(doc["branch_id"])
        doc["patient_id"] = str(doc["patient_id"])
        doc["appointment_id"] = str(doc["appointment_id"])
        result.append(VitalsResponse(**doc))
    return result
