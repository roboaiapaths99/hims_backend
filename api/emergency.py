from fastapi import APIRouter, Depends, HTTPException, status, Request
from bson import ObjectId
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel
from database import (
    get_db,
    get_emergency_admissions_collection,
    get_ambulance_bookings_collection,
    get_patients_collection,
    get_users_collection,
    get_ipd_admissions_collection
)
from middleware.auth import (
    get_current_user,
    get_tenant_filter,
    get_branch_filter,
    inject_audit_fields
)
from middleware.audit import create_audit_log
from models.emergency import (
    EmergencyAdmissionCreate,
    EmergencyAdmissionUpdate,
    EmergencyAdmissionResponse,
    AmbulanceBookingCreate,
    AmbulanceBookingUpdate,
    AmbulanceBookingResponse
)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────
# EMERGENCY ADMISSIONS
# ─────────────────────────────────────────────────────────────────────

@router.post("/admissions", response_model=EmergencyAdmissionResponse)
async def create_emergency_admission(
    payload: EmergencyAdmissionCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Quick-register an emergency admission with triage classification."""
    col = get_emergency_admissions_collection()

    # Validate triage category
    if payload.triage_category.lower() not in ("red", "orange", "yellow", "green", "blue"):
        raise HTTPException(status_code=400, detail="triage_category must be 'red', 'orange', 'yellow', 'green', or 'blue'")

    doc = payload.dict()

    # If patient_id is provided, verify it exists and pull name
    attending_doctor_name = None
    if payload.patient_id:
        try:
            patient_oid = ObjectId(payload.patient_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid patient_id format")
        patients_col = get_patients_collection()
        patient = await patients_col.find_one({"_id": patient_oid, "tenant_id": current_user["tenant_id"]})
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")
        doc["patient_id"] = patient_oid
        doc["patient_name"] = f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip()
    else:
        doc["patient_id"] = None

    # Resolve attending doctor name if provided
    if payload.attending_doctor_id:
        try:
            doctor_oid = ObjectId(payload.attending_doctor_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid attending_doctor_id format")
        users_col = get_users_collection()
        doctor = await users_col.find_one({"_id": doctor_oid, "tenant_id": current_user["tenant_id"]})
        if doctor:
            attending_doctor_name = doctor.get("name", "")
            doc["attending_doctor_id"] = doctor_oid

    doc["status"] = "admitted"
    inject_audit_fields(current_user, doc)

    res = await col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    doc["patient_id"] = str(doc["patient_id"]) if doc.get("patient_id") else None
    doc["attending_doctor_id"] = str(doc["attending_doctor_id"]) if doc.get("attending_doctor_id") else None
    doc["attending_doctor_name"] = attending_doctor_name

    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="EMERGENCY_ADMISSION_CREATED",
        entity="emergency_admissions",
        entity_id=doc["id"],
        details={
            "patient_name": doc.get("patient_name"),
            "triage_category": payload.triage_category,
            "triage_score": payload.triage_score
        },
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    return EmergencyAdmissionResponse(**doc)


@router.get("/admissions", response_model=List[EmergencyAdmissionResponse])
async def list_emergency_admissions(
    status_filter: Optional[str] = None,
    triage_category: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """List emergency admissions for the current branch."""
    col = get_emergency_admissions_collection()
    users_col = get_users_collection()

    query = get_branch_filter(current_user)
    query["is_deleted"] = {"$ne": True}

    if status_filter:
        query["status"] = status_filter
    if triage_category:
        query["triage_category"] = triage_category

    docs = await col.find(query).sort("created_at", -1).to_list(None)
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["branch_id"] = str(doc["branch_id"])
        doc["patient_id"] = str(doc["patient_id"]) if doc.get("patient_id") else None

        # Resolve attending doctor name
        if doc.get("attending_doctor_id"):
            try:
                doctor = await users_col.find_one({"_id": doc["attending_doctor_id"]})
                doc["attending_doctor_name"] = doctor.get("name", "") if doctor else None
            except Exception:
                doc["attending_doctor_name"] = None
            doc["attending_doctor_id"] = str(doc["attending_doctor_id"])
        else:
            doc["attending_doctor_name"] = None

        result.append(EmergencyAdmissionResponse(**doc))
    return result


@router.get("/admissions/{admission_id}", response_model=EmergencyAdmissionResponse)
async def get_emergency_admission(
    admission_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get a single emergency admission by ID."""
    col = get_emergency_admissions_collection()
    users_col = get_users_collection()

    try:
        oid = ObjectId(admission_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid admission_id format")

    doc = await col.find_one({"_id": oid, "tenant_id": current_user["tenant_id"], "is_deleted": {"$ne": True}})
    if not doc:
        raise HTTPException(status_code=404, detail="Emergency admission not found")

    doc["id"] = str(doc["_id"])
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    doc["patient_id"] = str(doc["patient_id"]) if doc.get("patient_id") else None

    if doc.get("attending_doctor_id"):
        try:
            doctor = await users_col.find_one({"_id": doc["attending_doctor_id"]})
            doc["attending_doctor_name"] = doctor.get("name", "") if doctor else None
        except Exception:
            doc["attending_doctor_name"] = None
        doc["attending_doctor_id"] = str(doc["attending_doctor_id"])
    else:
        doc["attending_doctor_name"] = None

    return EmergencyAdmissionResponse(**doc)


@router.put("/admissions/{admission_id}", response_model=EmergencyAdmissionResponse)
async def update_emergency_admission(
    admission_id: str,
    payload: EmergencyAdmissionUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Update emergency admission status, triage, or attending doctor."""
    col = get_emergency_admissions_collection()
    users_col = get_users_collection()

    try:
        oid = ObjectId(admission_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid admission_id format")

    doc = await col.find_one({"_id": oid, "tenant_id": current_user["tenant_id"], "is_deleted": {"$ne": True}})
    if not doc:
        raise HTTPException(status_code=404, detail="Emergency admission not found")

    update_data = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}

    if "triage_category" in update_data:
        if update_data["triage_category"].lower() not in ("red", "orange", "yellow", "green", "blue"):
            raise HTTPException(status_code=400, detail="triage_category must be 'red', 'orange', 'yellow', 'green', or 'blue'")

    if "status" in update_data:
        valid_statuses = ("admitted", "ipd_transferred", "discharged")
        if update_data["status"] not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(valid_statuses)}")

    if "attending_doctor_id" in update_data:
        try:
            update_data["attending_doctor_id"] = ObjectId(update_data["attending_doctor_id"])
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid attending_doctor_id format")

    now = datetime.utcnow()
    update_data["updated_at"] = now
    update_data["updated_by"] = str(current_user["_id"])

    await col.update_one({"_id": oid}, {"$set": update_data})

    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="EMERGENCY_ADMISSION_UPDATED",
        entity="emergency_admissions",
        entity_id=admission_id,
        details=update_data,
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )

    # Return updated document
    updated = await col.find_one({"_id": oid})
    updated["id"] = str(updated["_id"])
    updated["tenant_id"] = str(updated["tenant_id"])
    updated["branch_id"] = str(updated["branch_id"])
    updated["patient_id"] = str(updated["patient_id"]) if updated.get("patient_id") else None

    if updated.get("attending_doctor_id"):
        try:
            doctor = await users_col.find_one({"_id": updated["attending_doctor_id"]})
            updated["attending_doctor_name"] = doctor.get("name", "") if doctor else None
        except Exception:
            updated["attending_doctor_name"] = None
        updated["attending_doctor_id"] = str(updated["attending_doctor_id"])
    else:
        updated["attending_doctor_name"] = None

    return EmergencyAdmissionResponse(**updated)


@router.get("/admissions/stats/summary")
async def get_emergency_stats(current_user: dict = Depends(get_current_user)):
    """Get live ER statistics: counts by triage category and status."""
    col = get_emergency_admissions_collection()

    pipeline = [
        {"$match": {
            "tenant_id": current_user["tenant_id"],
            "branch_id": current_user["branch_id"],
            "is_deleted": {"$ne": True}
        }},
        {"$group": {
            "_id": {
                "triage_category": "$triage_category",
                "status": "$status"
            },
            "count": {"$sum": 1}
        }}
    ]

    raw = await col.aggregate(pipeline).to_list(None)

    stats = {
        "total_active": 0,
        "by_triage": {"red": 0, "orange": 0, "yellow": 0, "green": 0, "blue": 0},
        "by_status": {"admitted": 0, "ipd_transferred": 0, "discharged": 0}
    }

    for entry in raw:
        cat = entry["_id"]["triage_category"]
        st = entry["_id"]["status"]
        count = entry["count"]

        if cat in stats["by_triage"]:
            stats["by_triage"][cat] += count
        if st in stats["by_status"]:
            stats["by_status"][st] += count
        if st == "admitted":
            stats["total_active"] += count

    return stats


class IPDTransferRequest(BaseModel):
    room_id: str
    doctor_id: str
    initial_deposit: float

@router.post("/admissions/{admission_id}/transfer-ipd")
async def transfer_to_ipd(
    admission_id: str,
    payload: IPDTransferRequest,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    col = get_emergency_admissions_collection()
    patients_col = get_patients_collection()
    ipd_col = get_ipd_admissions_collection()
    
    try:
        oid = ObjectId(admission_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid admission_id format")
        
    doc = await col.find_one({"_id": oid, "tenant_id": current_user["tenant_id"], "is_deleted": {"$ne": True}})
    if not doc:
        raise HTTPException(status_code=404, detail="Emergency admission not found")
        
    patient_id = doc.get("patient_id")
    if not patient_id:
        # Create a new patient profile (quick-registration conversion)
        patient_name = doc.get("patient_name") or "Emergency Patient"
        parts = patient_name.strip().split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""
        
        # Sequentially generate MRN
        today_str = datetime.utcnow().strftime("%Y%m%d")
        patient_count = await patients_col.count_documents({"tenant_id": current_user["tenant_id"]})
        mrn = f"MRN-{today_str}-{patient_count + 1}"
        
        new_patient = {
            "first_name": first_name,
            "last_name": last_name,
            "phone": doc.get("patient_phone") or "0000000000",
            "gender": doc.get("patient_gender") or "Other",
            "dob": datetime.utcnow(),  # default placeholder
            "mrn": mrn,
            "advance_balance": 0.0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        inject_audit_fields(current_user, new_patient)
        
        res = await patients_col.insert_one(new_patient)
        patient_oid = res.inserted_id
        await col.update_one({"_id": oid}, {"$set": {"patient_id": patient_oid, "patient_name": patient_name}})
    else:
        patient_oid = ObjectId(patient_id)
        
    # Verify IPD target parameters
    try:
        room_oid = ObjectId(payload.room_id)
        doctor_oid = ObjectId(payload.doctor_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid room_id or doctor_id format")
        
    # Insert IPD admission record
    ipd_doc = {
        "patient_id": patient_oid,
        "doctor_id": doctor_oid,
        "room_id": room_oid,
        "admission_date": datetime.utcnow(),
        "initial_deposit": payload.initial_deposit,
        "status": "admitted",
        "progress_notes": [],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    inject_audit_fields(current_user, ipd_doc)
    
    ipd_res = await ipd_col.insert_one(ipd_doc)
    
    # Update Emergency admission status to ipd_transferred
    await col.update_one(
        {"_id": oid},
        {"$set": {"status": "ipd_transferred", "updated_at": datetime.utcnow(), "updated_by": str(current_user["_id"])}}
    )
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="EMERGENCY_TRANSFER_IPD",
        entity="emergency_admissions",
        entity_id=admission_id,
        details={"ipd_admission_id": str(ipd_res.inserted_id), "room_id": payload.room_id, "doctor_id": payload.doctor_id},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    return {"status": "success", "ipd_admission_id": str(ipd_res.inserted_id)}


# ─────────────────────────────────────────────────────────────────────
# AMBULANCE BOOKINGS
# ─────────────────────────────────────────────────────────────────────

@router.post("/ambulance/book", response_model=AmbulanceBookingResponse)
async def book_ambulance(
    payload: AmbulanceBookingCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Dispatch an ambulance for emergency pickup."""
    col = get_ambulance_bookings_collection()

    doc = payload.dict()

    if payload.emergency_admission_id:
        try:
            doc["emergency_admission_id"] = ObjectId(payload.emergency_admission_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid emergency_admission_id format")
    else:
        doc["emergency_admission_id"] = None

    doc["status"] = "dispatched"
    inject_audit_fields(current_user, doc)

    res = await col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    doc["emergency_admission_id"] = str(doc["emergency_admission_id"]) if doc.get("emergency_admission_id") else None

    # Emit Socket.IO live update to refresh control room dashboards
    sio = getattr(request.app.state, "sio", None)
    if sio:
        await sio.emit("ambulance.updated", {"branch_id": str(current_user["branch_id"])}, room=f"branch_{current_user['branch_id']}")

    # Notify Assigned Driver
    if payload.driver_name:
        try:
            from database import get_users_collection
            users_col = get_users_collection()
            driver = await users_col.find_one({"name": payload.driver_name, "tenant_id": current_user["tenant_id"]})
            if driver:
                driver_phone = driver.get("phone")
                driver_push_token = driver.get("expo_push_token")
                from services.notification_service import NotificationService
                await NotificationService.dispatch(
                    tenant_id=current_user["tenant_id"],
                    branch_id=current_user["branch_id"],
                    user_id=driver["_id"],
                    title="Emergency Dispatch Task",
                    message=f"Ambulance Duty Assigned. Pickup address: {payload.pickup_address}. Vehicle: {payload.vehicle_number}.",
                    notification_type="warning",
                    phone_number=driver_phone,
                    expo_push_token=driver_push_token
                )
        except Exception as ne:
            print(f"Failed to dispatch notification to driver: {ne}")

    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="AMBULANCE_DISPATCHED",
        entity="ambulance_bookings",
        entity_id=doc["id"],
        details={
            "pickup_address": payload.pickup_address,
            "vehicle_number": payload.vehicle_number,
            "patient_name": payload.patient_name
        },
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    return AmbulanceBookingResponse(**doc)


@router.get("/ambulance", response_model=List[AmbulanceBookingResponse])
async def list_ambulance_bookings(
    status_filter: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """List ambulance bookings for the current branch."""
    col = get_ambulance_bookings_collection()
    query = get_branch_filter(current_user)

    if status_filter:
        query["status"] = status_filter

    docs = await col.find(query).sort("created_at", -1).to_list(None)
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["branch_id"] = str(doc["branch_id"])
        doc["emergency_admission_id"] = str(doc["emergency_admission_id"]) if doc.get("emergency_admission_id") else None
        result.append(AmbulanceBookingResponse(**doc))
    return result


@router.put("/ambulance/{booking_id}", response_model=AmbulanceBookingResponse)
async def update_ambulance_booking(
    booking_id: str,
    payload: AmbulanceBookingUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Update ambulance booking status (arrived, en_route_hospital, completed, cancelled)."""
    col = get_ambulance_bookings_collection()

    try:
        oid = ObjectId(booking_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid booking_id format")

    doc = await col.find_one({"_id": oid, "tenant_id": current_user["tenant_id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Ambulance booking not found")

    update_data = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}

    if "status" in update_data:
        valid_statuses = ("dispatched", "arrived", "en_route_hospital", "completed", "cancelled")
        if update_data["status"] not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(valid_statuses)}")

    now = datetime.utcnow()
    update_data["updated_at"] = now
    update_data["updated_by"] = str(current_user["_id"])

    await col.update_one({"_id": oid}, {"$set": update_data})

    updated = await col.find_one({"_id": oid})
    updated["id"] = str(updated["_id"])
    updated["tenant_id"] = str(updated["tenant_id"])
    updated["branch_id"] = str(updated["branch_id"])
    updated["emergency_admission_id"] = str(updated["emergency_admission_id"]) if updated.get("emergency_admission_id") else None

    # Emit Socket.IO live update
    sio = getattr(request.app.state, "sio", None)
    if sio:
        await sio.emit("ambulance.updated", {"branch_id": str(current_user["branch_id"])}, room=f"branch_{current_user['branch_id']}")

    # Notify Patient
    if "status" in update_data:
        try:
            from database import get_patients_collection
            patients_col = get_patients_collection()
            patient = await patients_col.find_one({"phone": updated.get("patient_phone"), "tenant_id": current_user["tenant_id"]})
            
            from services.notification_service import NotificationService
            status_msgs = {
                "arrived": "arrived at your pickup location.",
                "en_route_hospital": "heading to the hospital. Transit is now active.",
                "completed": "safely arrived and admitted at the hospital.",
                "cancelled": "been cancelled."
            }
            
            if update_data["status"] in status_msgs:
                msg = f"Ambulance {updated.get('vehicle_number') or ''} has {status_msgs[update_data['status']]}"
                patient_phone = updated.get("patient_phone")
                patient_push_token = patient.get("expo_push_token") if patient else None
                
                await NotificationService.dispatch(
                    tenant_id=current_user["tenant_id"],
                    branch_id=current_user["branch_id"],
                    user_id=patient["_id"] if patient else current_user["_id"],
                    title="Ambulance Trip Update",
                    message=msg,
                    notification_type="info",
                    phone_number=patient_phone,
                    expo_push_token=patient_push_token
                )
        except Exception as ne:
            print(f"Failed to notify patient of ambulance update: {ne}")

    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="AMBULANCE_STATUS_UPDATED",
        entity="ambulance_bookings",
        entity_id=booking_id,
        details=update_data,
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    return AmbulanceBookingResponse(**updated)
