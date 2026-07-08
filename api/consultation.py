from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from pydantic import BaseModel
from bson import ObjectId
from datetime import datetime
from typing import List, Optional

from database import (
    get_visits_collection, get_appointments_collection, 
    get_queue_tokens_collection, get_patients_collection, get_vitals_collection
)
from middleware.auth import get_current_user, get_tenant_filter, inject_audit_fields
from middleware.audit import create_audit_log
from models.visit import VisitCreate, VisitResponse, VisitUpdate, VisitAmendmentCreate

router = APIRouter()


class StartConsultationRequest(BaseModel):
    """Validated payload for starting a new consultation visit."""
    appointment_id: str

# Simple ICD-10 common diagnostic repository
ICD10_DB = [
    {"code": "A09", "name": "Infectious gastroenteritis and colitis"},
    {"code": "E11", "name": "Type 2 diabetes mellitus"},
    {"code": "I10", "name": "Essential (primary) hypertension"},
    {"code": "J00", "name": "Acute nasopharyngitis (common cold)"},
    {"code": "J06", "name": "Acute upper respiratory infection, unspecified"},
    {"code": "J45", "name": "Asthma"},
    {"code": "K21", "name": "Gastro-esophageal reflux disease (GERD)"},
    {"code": "M54.5", "name": "Low back pain"},
    {"code": "N39.0", "name": "Urinary tract infection, site not specified"},
    {"code": "R50.9", "name": "Fever, unspecified"},
    {"code": "R51", "name": "Headache"},
    {"code": "S09.9", "name": "Unspecified injury of head"}
]

@router.get("/icd10")
async def search_icd10(q: Optional[str] = None):
    """Diagnoses autocomplete repository search"""
    if not q:
        return ICD10_DB[:5]
    q_lower = q.lower()
    matches = [
        item for item in ICD10_DB
        if q_lower in item["code"].lower() or q_lower in item["name"].lower()
    ]
    return matches[:10]

@router.post("/visit/start", response_model=VisitResponse)
async def start_consultation(payload: StartConsultationRequest, request: Request, current_user: dict = Depends(get_current_user)):
    visits_col = get_visits_collection()
    appointments_col = get_appointments_collection()
    tokens_col = get_queue_tokens_collection()
    
    tenant_oid = current_user["tenant_id"]
    branch_oid = current_user["branch_id"]
    
    app_id = payload.appointment_id
        
    try:
        app_oid = ObjectId(app_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid appointment ID format")
        
    # Verify appointment
    app = await appointments_col.find_one({"_id": app_oid, "tenant_id": tenant_oid})
    if not app:
        raise HTTPException(status_code=404, detail="Appointment not found")
        
    # Check if visit already exists
    existing = await visits_col.find_one({"appointment_id": app_oid})
    if existing:
        # If it exists, update appointment and queue to in_consultation
        await appointments_col.update_one({"_id": app_oid}, {"$set": {"status": "in_consultation"}})
        await tokens_col.update_one({"appointment_id": app_oid}, {"$set": {"status": "in_consultation"}})
        
        # Emit Socket
        sio = getattr(request.app.state, "sio", None)
        if sio:
            await sio.emit("queue.updated", {"branch_id": str(branch_oid)}, room=f"branch_{branch_oid}")
            
        existing["id"] = str(existing["_id"])
        existing["tenant_id"] = str(existing["tenant_id"])
        existing["branch_id"] = str(existing["branch_id"])
        existing["patient_id"] = str(existing["patient_id"])
        existing["doctor_id"] = str(existing["doctor_id"])
        existing["appointment_id"] = str(existing["appointment_id"])
        return VisitResponse(**existing)
        
    # Create new visit
    visit_doc = {
        "tenant_id": tenant_oid,
        "branch_id": branch_oid,
        "patient_id": app["patient_id"],
        "doctor_id": app["doctor_id"],
        "appointment_id": app_oid,
        "symptoms": app.get("reason", ""),
        "clinical_notes": "",
        "diagnosis": [],
        "treatment_plan": "",
        "status": "active",
        "visit_date": datetime.utcnow(),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "created_by": current_user["_id"],
        "updated_by": current_user["_id"]
    }
    
    res = await visits_col.insert_one(visit_doc)
    visit_doc["id"] = str(res.inserted_id)
    visit_doc["tenant_id"] = str(visit_doc["tenant_id"])
    visit_doc["branch_id"] = str(visit_doc["branch_id"])
    visit_doc["patient_id"] = str(visit_doc["patient_id"])
    visit_doc["doctor_id"] = str(visit_doc["doctor_id"])
    visit_doc["appointment_id"] = str(visit_doc["appointment_id"])
    
    # Update appointment and queue statuses
    await appointments_col.update_one({"_id": app_oid}, {"$set": {"status": "in_consultation"}})
    await tokens_col.update_one({"appointment_id": app_oid}, {"$set": {"status": "in_consultation"}})
    
    # Emit socket
    sio = getattr(request.app.state, "sio", None)
    if sio:
        await sio.emit("queue.updated", {"branch_id": str(branch_oid)}, room=f"branch_{branch_oid}")
        
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="CLINICAL_VISIT_STARTED",
        entity="visits",
        entity_id=visit_doc["id"],
        details={"patient_id": visit_doc["patient_id"]},
        ip_address=request.client.host if request.client else None,
        tenant_id=ObjectId(visit_doc["tenant_id"]),
        branch_id=ObjectId(visit_doc["branch_id"])
    )
    return VisitResponse(**visit_doc)

@router.post("/visit/{visit_id}/save", response_model=VisitResponse)
async def save_consultation(visit_id: str, payload: VisitUpdate, request: Request, current_user: dict = Depends(get_current_user)):
    visits_col = get_visits_collection()
    
    try:
        visit_oid = ObjectId(visit_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid visit ID format")
        
    visit = await visits_col.find_one({"_id": visit_oid, "tenant_id": current_user["tenant_id"]})
    if not visit:
        raise HTTPException(status_code=404, detail="Consultation visit profile not found")
        
    if visit.get("is_finalized"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This clinical visit has been finalized and locked. No further modifications are permitted."
        )
        
    update_data = payload.dict(exclude_unset=True)
    update_data["updated_at"] = datetime.utcnow()
    update_data["updated_by"] = current_user["_id"]
    
    await visits_col.update_one({"_id": visit_oid}, {"$set": update_data})
    
    updated = await visits_col.find_one({"_id": visit_oid})
    updated["id"] = str(updated["_id"])
    updated["tenant_id"] = str(updated["tenant_id"])
    updated["branch_id"] = str(updated["branch_id"])
    updated["patient_id"] = str(updated["patient_id"])
    updated["doctor_id"] = str(updated["doctor_id"])
    updated["appointment_id"] = str(updated["appointment_id"])

    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="CLINICAL_VISIT_SAVED",
        entity="visits",
        entity_id=visit_id,
        details={"patient_id": str(updated["patient_id"]), "diagnosis": updated.get("diagnosis", []), "clinical_notes": updated.get("clinical_notes", "")},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    return VisitResponse(**updated)

@router.post("/visit/{visit_id}/complete", response_model=VisitResponse)
async def complete_consultation(visit_id: str, payload: VisitUpdate, request: Request, current_user: dict = Depends(get_current_user)):
    visits_col = get_visits_collection()
    appointments_col = get_appointments_collection()
    tokens_col = get_queue_tokens_collection()
    
    try:
        visit_oid = ObjectId(visit_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid visit ID format")
        
    visit = await visits_col.find_one({"_id": visit_oid, "tenant_id": current_user["tenant_id"]})
    if not visit:
        raise HTTPException(status_code=404, detail="Consultation visit profile not found")
        
    if visit.get("is_finalized"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This clinical visit has been finalized and locked. No further modifications are permitted."
        )
        
    update_data = payload.dict(exclude_unset=True)
    update_data["status"] = "completed"
    update_data["is_finalized"] = True
    update_data["locked"] = True
    update_data["finalized_at"] = datetime.utcnow()
    update_data["finalized_by"] = str(current_user["_id"])
    update_data["updated_at"] = datetime.utcnow()
    update_data["updated_by"] = current_user["_id"]
    
    await visits_col.update_one({"_id": visit_oid}, {"$set": update_data})
    
    # 1. Update appointment status to completed
    await appointments_col.update_one({"_id": visit["appointment_id"]}, {"$set": {"status": "completed", "updated_at": datetime.utcnow()}})
    
    # 2. Update queue token status to completed
    await tokens_col.update_one({"appointment_id": visit["appointment_id"]}, {"$set": {"status": "completed"}})
    
    # Emit socket updates
    sio = getattr(request.app.state, "sio", None)
    if sio:
        await sio.emit("queue.updated", {"branch_id": str(visit["branch_id"])}, room=f"branch_{visit['branch_id']}")
        
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="CONSULTATION_COMPLETED",
        entity="visits",
        entity_id=visit_id,
        details={
            "patient_id": str(visit["patient_id"]), 
            "diagnosis": update_data.get("diagnosis", []), 
            "clinical_notes": update_data.get("clinical_notes", "")
        },
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    updated = await visits_col.find_one({"_id": visit_oid})
    updated["id"] = str(updated["_id"])
    updated["tenant_id"] = str(updated["tenant_id"])
    updated["branch_id"] = str(updated["branch_id"])
    updated["patient_id"] = str(updated["patient_id"])
    updated["doctor_id"] = str(updated["doctor_id"])
    updated["appointment_id"] = str(updated["appointment_id"])
    return VisitResponse(**updated)

@router.post("/visit/{visit_id}/finalize", response_model=VisitResponse)
async def finalize_consultation(visit_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    visits_col = get_visits_collection()
    appointments_col = get_appointments_collection()
    tokens_col = get_queue_tokens_collection()
    
    try:
        visit_oid = ObjectId(visit_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid visit ID format")
        
    visit = await visits_col.find_one({"_id": visit_oid, "tenant_id": current_user["tenant_id"]})
    if not visit:
        raise HTTPException(status_code=404, detail="Consultation visit profile not found")
        
    if visit.get("is_finalized"):
        visit["id"] = str(visit["_id"])
        visit["tenant_id"] = str(visit["tenant_id"])
        visit["branch_id"] = str(visit["branch_id"])
        visit["patient_id"] = str(visit["patient_id"])
        visit["doctor_id"] = str(visit["doctor_id"])
        visit["appointment_id"] = str(visit["appointment_id"])
        return VisitResponse(**visit)
        
    await visits_col.update_one(
        {"_id": visit_oid},
        {"$set": {
            "is_finalized": True,
            "locked": True,
            "status": "finalized",
            "finalized_at": datetime.utcnow(),
            "finalized_by": str(current_user["_id"]),
            "updated_at": datetime.utcnow(),
            "updated_by": current_user["_id"]
        }}
    )
    
    await appointments_col.update_one({"_id": visit["appointment_id"]}, {"$set": {"status": "completed", "updated_at": datetime.utcnow()}})
    await tokens_col.update_one({"appointment_id": visit["appointment_id"]}, {"$set": {"status": "completed"}})
    
    # Sync clinical record to DMS
    from config import settings
    from services.dms_clinical_sync_service import sync_visit_to_dms
    if settings.DMS_INTEGRATION_ENABLED:
        import asyncio
        asyncio.create_task(sync_visit_to_dms(visit_id))
        
    try:
        from services.notification_service import NotificationService
        doctor_name = current_user.get("name", "Your practitioner")
        
        from database import get_patients_collection
        patients_col = get_patients_collection()
        patient = await patients_col.find_one({"_id": ObjectId(visit["patient_id"])})
        patient_phone = patient.get("phone") if patient else None
        patient_push_token = patient.get("expo_push_token") if patient else None
        
        await NotificationService.dispatch(
            tenant_id=ObjectId(visit["tenant_id"]),
            branch_id=ObjectId(visit["branch_id"]),
            user_id=ObjectId(visit["patient_id"]),
            title="Prescription & EMR Finalized",
            message=f"Dr. {doctor_name} has finalized your prescription and consultation EMR records. You can now view them in your patient portal.",
            notification_type="success",
            phone_number=patient_phone,
            expo_push_token=patient_push_token
        )
    except Exception as ne:
        print(f"Error dispatching patient notification for consultation finalize: {ne}")
        
    sio = getattr(request.app.state, "sio", None)
    if sio:
        await sio.emit("queue.updated", {"branch_id": str(visit["branch_id"])}, room=f"branch_{visit['branch_id']}")
        
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="CONSULTATION_FINALIZED",
        entity="visits",
        entity_id=visit_id,
        details={
            "patient_id": str(visit["patient_id"])
        },
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    updated = await visits_col.find_one({"_id": visit_oid})
    updated["id"] = str(updated["_id"])
    updated["tenant_id"] = str(updated["tenant_id"])
    updated["branch_id"] = str(updated["branch_id"])
    updated["patient_id"] = str(updated["patient_id"])
    updated["doctor_id"] = str(updated["doctor_id"])
    updated["appointment_id"] = str(updated["appointment_id"])
    return VisitResponse(**updated)


@router.get("/visit/{visit_id}", response_model=VisitResponse)
async def get_visit_details(visit_id: str, current_user: dict = Depends(get_current_user)):
    visits_col = get_visits_collection()
    
    try:
        visit_oid = ObjectId(visit_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid visit ID format")
        
    doc = await visits_col.find_one({"_id": visit_oid, "tenant_id": current_user["tenant_id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Consultation visit profile not found")
        
    doc["id"] = str(doc["_id"])
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    doc["patient_id"] = str(doc["patient_id"])
    doc["doctor_id"] = str(doc["doctor_id"])
    doc["appointment_id"] = str(doc["appointment_id"])
    return VisitResponse(**doc)

@router.get("/patient/{patient_id}/history")
async def get_patient_consultation_history(
    patient_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    visits_col = get_visits_collection()
    
    try:
        patient_oid = ObjectId(patient_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid patient ID")
        
    query = {
        "tenant_id": current_user["tenant_id"],
        "patient_id": patient_oid
    }
    
    total = await visits_col.count_documents(query)
    docs = await visits_col.find(query).sort("visit_date", -1).skip((page - 1) * limit).limit(limit).to_list(limit)
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["branch_id"] = str(doc["branch_id"])
        doc["patient_id"] = str(doc["patient_id"])
        doc["doctor_id"] = str(doc["doctor_id"])
        doc["appointment_id"] = str(doc["appointment_id"])
        result.append(VisitResponse(**doc))
    return {"data": result, "total": total, "page": page, "limit": limit}


# ─── AMENDMENT: Append corrections to a finalized consultation ───

@router.post("/visit/{visit_id}/amend", response_model=VisitResponse)
async def amend_consultation(
    visit_id: str,
    amendment: VisitAmendmentCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Append a formal amendment to a finalized consultation visit.
    
    Only the original doctor or another authorised practitioner (role=doctor)
    may amend.  The original record is never mutated – amendments are
    appended to an `amendments[]` array and individually timestamped.
    """
    visits_col = get_visits_collection()

    try:
        visit_oid = ObjectId(visit_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid visit ID format")

    visit = await visits_col.find_one({
        "_id": visit_oid,
        "tenant_id": current_user["tenant_id"]
    })
    if not visit:
        raise HTTPException(status_code=404, detail="Consultation visit not found")

    # Guard: only finalized visits may be amended
    if not visit.get("is_finalized"):
        raise HTTPException(
            status_code=400,
            detail="Only finalized consultations can be amended. Save or complete the visit first."
        )

    # Guard: only doctors may amend
    if current_user.get("role") not in ("doctor", "admin"):
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions. Only doctors and admins may amend clinical records."
        )

    amendment_doc = {
        "id": str(ObjectId()),
        "reason": amendment.reason,
        "amended_symptoms": amendment.amended_symptoms,
        "amended_clinical_notes": amendment.amended_clinical_notes,
        "amended_diagnosis": amendment.amended_diagnosis,
        "amended_treatment_plan": amendment.amended_treatment_plan,
        "amended_by": str(current_user["_id"]),
        "amended_by_name": current_user.get("name", "Unknown"),
        "amended_at": datetime.utcnow()
    }

    # Atomically push into the amendments array
    await visits_col.update_one(
        {"_id": visit_oid},
        {
            "$push": {"amendments": amendment_doc},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )

    # Audit log
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="CLINICAL_VISIT_AMENDED",
        entity="visits",
        entity_id=visit_id,
        details={
            "amendment_id": amendment_doc["id"],
            "reason": amendment.reason,
            "patient_id": str(visit["patient_id"])
        },
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )

    # Return the updated visit
    updated = await visits_col.find_one({"_id": visit_oid})
    updated["id"] = str(updated["_id"])
    updated["tenant_id"] = str(updated["tenant_id"])
    updated["branch_id"] = str(updated["branch_id"])
    updated["patient_id"] = str(updated["patient_id"])
    updated["doctor_id"] = str(updated["doctor_id"])
    updated["appointment_id"] = str(updated["appointment_id"])
    return updated


@router.get("/visit/{visit_id}/amendments")
async def get_visit_amendments(
    visit_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Retrieve the amendment history for a specific consultation visit."""
    visits_col = get_visits_collection()

    try:
        visit_oid = ObjectId(visit_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid visit ID format")

    visit = await visits_col.find_one({
        "_id": visit_oid,
        "tenant_id": current_user["tenant_id"]
    })
    if not visit:
        raise HTTPException(status_code=404, detail="Consultation visit not found")

    amendments = visit.get("amendments", [])
    # Serialize datetime objects for JSON
    for a in amendments:
        if isinstance(a.get("amended_at"), datetime):
            a["amended_at"] = a["amended_at"].isoformat()
    return {"visit_id": visit_id, "amendments": amendments, "total": len(amendments)}
