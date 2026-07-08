from fastapi import APIRouter, Depends, HTTPException, status, Request
from bson import ObjectId
from datetime import datetime
from typing import List, Optional

from database import (
    get_ipd_admissions_collection,
    get_bed_transfers_collection,
    get_ipd_charges_collection,
    get_patients_collection,
    get_users_collection,
    get_rooms_collection
)
from middleware.auth import (
    get_current_user,
    get_branch_filter,
    inject_audit_fields
)
from middleware.audit import create_audit_log
from models.ipd import (
    IPDAdmissionCreate,
    IPDAdmissionResponse,
    BedTransferRequest,
    IPDChargeCreate,
    IPDChargeResponse
)

router = APIRouter()

async def resolve_admission_details(doc: dict) -> dict:
    """Helper to resolve OIDs to human-readable names for patient, doctor, and room"""
    patients_col = get_patients_collection()
    users_col = get_users_collection()
    rooms_col = get_rooms_collection()
    
    doc["id"] = str(doc["_id"])
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    
    # 1. Patient Details
    patient = await patients_col.find_one({"_id": doc["patient_id"]})
    if patient:
        doc["patient_name"] = f"{patient.get('first_name', '')} {patient.get('last_name', '')}"
        doc["patient_mrn"] = patient.get("mrn", "N/A")
    else:
        doc["patient_name"] = "Unknown Patient"
        doc["patient_mrn"] = "N/A"
    doc["patient_id"] = str(doc["patient_id"])
        
    # 2. Doctor Details
    doctor = await users_col.find_one({"_id": doc["doctor_id"]})
    doc["doctor_name"] = doctor.get("name", "Unknown Doctor") if doctor else "Unknown Doctor"
    doc["doctor_id"] = str(doc["doctor_id"])
    
    # 3. Room Details
    room = await rooms_col.find_one({"_id": doc["room_id"]})
    if room:
        doc["room_number"] = room.get("room_number", "Unknown")
        doc["room_type"] = room.get("room_type", "Unknown")
    else:
        doc["room_number"] = "Unknown"
        doc["room_type"] = "Unknown"
    doc["room_id"] = str(doc["room_id"])
    
    return doc

@router.post("/admissions", response_model=IPDAdmissionResponse)
async def create_admission(
    payload: IPDAdmissionCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    admissions_col = get_ipd_admissions_collection()
    patients_col = get_patients_collection()
    users_col = get_users_collection()
    rooms_col = get_rooms_collection()
    
    try:
        patient_oid = ObjectId(payload.patient_id)
        doctor_oid = ObjectId(payload.doctor_id)
        room_oid = ObjectId(payload.room_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid ID parameter format")
        
    # 1. Verify patient exists
    patient = await patients_col.find_one({"_id": patient_oid, "tenant_id": current_user["tenant_id"]})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
        
    # 2. Check if patient is already admitted
    existing = await admissions_col.find_one({
        "patient_id": patient_oid,
        "status": "admitted",
        "tenant_id": current_user["tenant_id"]
    })
    if existing:
        raise HTTPException(status_code=400, detail="Patient is already admitted")
        
    # 3. Verify doctor exists
    doctor = await users_col.find_one({"_id": doctor_oid, "tenant_id": current_user["tenant_id"]})
    if not doctor:
        raise HTTPException(status_code=404, detail="Doctor profile not found")
        
    # 4. Verify room exists and is available
    room = await rooms_col.find_one({"_id": room_oid, "tenant_id": current_user["tenant_id"]})
    if not room:
        raise HTTPException(status_code=404, detail="Room configuration not found")
        
    if room.get("status") != "available":
        raise HTTPException(status_code=400, detail="Requested room/bed is occupied or unavailable")
        
    # 5. Insert admission record
    doc = payload.dict()
    inject_audit_fields(current_user, doc)
    
    doc["patient_id"] = patient_oid
    doc["doctor_id"] = doctor_oid
    doc["room_id"] = room_oid
    doc["status"] = "admitted"
    
    res = await admissions_col.insert_one(doc)
    doc["_id"] = res.inserted_id
    
    # Update room status to occupied
    await rooms_col.update_one(
        {"_id": room_oid},
        {"$set": {"status": "occupied", "updated_at": datetime.utcnow(), "updated_by": str(current_user["_id"])}}
    )
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="IPD_ADMISSION_CREATED",
        entity="ipd_admissions",
        entity_id=str(res.inserted_id),
        details={"room_number": room.get("room_number"), "patient_name": f"{patient.get('first_name')} {patient.get('last_name')}"},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    resolved = await resolve_admission_details(doc)
    return IPDAdmissionResponse(**resolved)

@router.get("/admissions", response_model=List[IPDAdmissionResponse])
async def list_admissions(
    status_filter: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    admissions_col = get_ipd_admissions_collection()
    query = get_branch_filter(current_user)
    
    if status_filter:
        query["status"] = status_filter
        
    docs = await admissions_col.find(query).sort("admission_date", -1).to_list(None)
    result = []
    for doc in docs:
        resolved = await resolve_admission_details(doc)
        result.append(IPDAdmissionResponse(**resolved))
    return result

@router.get("/admissions/{id}", response_model=IPDAdmissionResponse)
async def get_admission(id: str, current_user: dict = Depends(get_current_user)):
    admissions_col = get_ipd_admissions_collection()
    
    try:
        admission_oid = ObjectId(id)
    except:
        raise HTTPException(status_code=400, detail="Invalid admission ID format")
        
    doc = await admissions_col.find_one({"_id": admission_oid, "tenant_id": current_user["tenant_id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Admission record not found")
        
    resolved = await resolve_admission_details(doc)
    return IPDAdmissionResponse(**resolved)

@router.post("/admissions/{id}/transfer", response_model=IPDAdmissionResponse)
async def transfer_bed(
    id: str,
    payload: BedTransferRequest,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    admissions_col = get_ipd_admissions_collection()
    transfers_col = get_bed_transfers_collection()
    rooms_col = get_rooms_collection()
    
    try:
        admission_oid = ObjectId(id)
        to_room_oid = ObjectId(payload.to_room_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid ID parameter format")
        
    # 1. Fetch admission
    admission = await admissions_col.find_one({"_id": admission_oid, "tenant_id": current_user["tenant_id"]})
    if not admission:
        raise HTTPException(status_code=404, detail="Admission profile not found")
        
    if admission.get("status") != "admitted":
        raise HTTPException(status_code=400, detail="Cannot transfer beds for a discharged admission")
        
    from_room_oid = admission["room_id"]
    if from_room_oid == to_room_oid:
        raise HTTPException(status_code=400, detail="Cannot transfer to the same bed/room")
        
    # 2. Check if destination room is available
    to_room = await rooms_col.find_one({"_id": to_room_oid, "tenant_id": current_user["tenant_id"]})
    if not to_room:
        raise HTTPException(status_code=404, detail="Target room not found")
        
    if to_room.get("status") != "available":
        raise HTTPException(status_code=400, detail="Target room/bed is occupied or unavailable")
        
    # 3. Log the transfer
    now = datetime.utcnow()
    transfer_doc = {
        "tenant_id": current_user["tenant_id"],
        "branch_id": current_user["branch_id"],
        "admission_id": admission_oid,
        "from_room_id": from_room_oid,
        "to_room_id": to_room_oid,
        "transfer_date": now,
        "reason": payload.reason,
        "created_at": now,
        "created_by": str(current_user["_id"])
    }
    await transfers_col.insert_one(transfer_doc)
    
    # 4. Free old room & occupy new room
    await rooms_col.update_one({"_id": from_room_oid}, {"$set": {"status": "available", "updated_at": now, "updated_by": str(current_user["_id"])}})
    await rooms_col.update_one({"_id": to_room_oid}, {"$set": {"status": "occupied", "updated_at": now, "updated_by": str(current_user["_id"])}})
    
    # 5. Update admission record
    await admissions_col.update_one(
        {"_id": admission_oid},
        {"$set": {"room_id": to_room_oid, "updated_at": now, "updated_by": str(current_user["_id"])}}
    )
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="IPD_BED_TRANSFER",
        entity="ipd_admissions",
        entity_id=id,
        details={"from_room_id": str(from_room_oid), "to_room_id": payload.to_room_id, "reason": payload.reason},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    updated = await admissions_col.find_one({"_id": admission_oid})
    resolved = await resolve_admission_details(updated)
    return IPDAdmissionResponse(**resolved)

@router.post("/admissions/{id}/discharge", response_model=IPDAdmissionResponse)
async def discharge_patient(
    id: str,
    payload: dict,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    admissions_col = get_ipd_admissions_collection()
    rooms_col = get_rooms_collection()
    
    try:
        admission_oid = ObjectId(id)
    except:
        raise HTTPException(status_code=400, detail="Invalid admission ID format")
        
    admission = await admissions_col.find_one({"_id": admission_oid, "tenant_id": current_user["tenant_id"]})
    if not admission:
        raise HTTPException(status_code=404, detail="Admission profile not found")
        
    if admission.get("status") == "discharged":
        raise HTTPException(status_code=400, detail="Admission is already discharged")
        
    summary = payload.get("discharge_summary", "Clinical discharge summary standard.")
    now = datetime.utcnow()
    
    # Update admission status
    await admissions_col.update_one(
        {"_id": admission_oid},
        {"$set": {
            "status": "discharged",
            "discharge_date": now,
            "discharge_summary": summary,
            "updated_at": now,
            "updated_by": str(current_user["_id"])
        }}
    )
    
    # Free the room status
    await rooms_col.update_one(
        {"_id": admission["room_id"]},
        {"$set": {"status": "available", "updated_at": now, "updated_by": str(current_user["_id"])}}
    )
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="IPD_DISCHARGE_COMPLETED",
        entity="ipd_admissions",
        entity_id=id,
        details={"discharge_summary": summary},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    updated = await admissions_col.find_one({"_id": admission_oid})
    resolved = await resolve_admission_details(updated)
    return IPDAdmissionResponse(**resolved)

@router.post("/admissions/{id}/charges", response_model=IPDChargeResponse)
async def post_ipd_charge(
    id: str,
    payload: IPDChargeCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    admissions_col = get_ipd_admissions_collection()
    charges_col = get_ipd_charges_collection()
    
    try:
        admission_oid = ObjectId(id)
    except:
        raise HTTPException(status_code=400, detail="Invalid admission ID format")
        
    admission = await admissions_col.find_one({"_id": admission_oid, "tenant_id": current_user["tenant_id"]})
    if not admission:
        raise HTTPException(status_code=404, detail="Admission profile not found")
        
    doc = payload.dict()
    now = datetime.utcnow()
    doc["tenant_id"] = current_user["tenant_id"]
    doc["branch_id"] = current_user["branch_id"]
    doc["admission_id"] = admission_oid
    doc["date"] = now
    doc["created_at"] = now
    doc["created_by"] = str(current_user["_id"])
    
    res = await charges_col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    doc["admission_id"] = str(doc["admission_id"])
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="IPD_CHARGE_POSTED",
        entity="ipd_charges",
        entity_id=doc["id"],
        details={"charge_type": payload.charge_type, "amount": payload.amount},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    return IPDChargeResponse(**doc)

@router.get("/admissions/{id}/charges", response_model=List[IPDChargeResponse])
async def list_ipd_charges(id: str, current_user: dict = Depends(get_current_user)):
    charges_col = get_ipd_charges_collection()
    
    try:
        admission_oid = ObjectId(id)
    except:
        raise HTTPException(status_code=400, detail="Invalid admission ID format")
        
    docs = await charges_col.find({"admission_id": admission_oid}).to_list(None)
    result = []
    for doc in docs:
      doc["id"] = str(doc["_id"])
      doc["tenant_id"] = str(doc["tenant_id"])
      doc["branch_id"] = str(doc["branch_id"])
      doc["admission_id"] = str(doc["admission_id"])
      result.append(IPDChargeResponse(**doc))
    return result

@router.post("/admissions/{id}/notes")
async def add_progress_note(
    id: str,
    payload: dict,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    admissions_col = get_ipd_admissions_collection()
    
    try:
        admission_oid = ObjectId(id)
    except:
        raise HTTPException(status_code=400, detail="Invalid admission ID format")
        
    admission = await admissions_col.find_one({"_id": admission_oid, "tenant_id": current_user["tenant_id"]})
    if not admission:
        raise HTTPException(status_code=404, detail="Admission profile not found")
        
    note = payload.get("note")
    if not note:
        raise HTTPException(status_code=400, detail="note parameter is required")
        
    new_note = {
        "date": datetime.utcnow(),
        "note": note,
        "by": current_user.get("name", "Staff")
    }
    
    await admissions_col.update_one(
        {"_id": admission_oid},
        {"$push": {"progress_notes": new_note}}
    )
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="IPD_PROGRESS_NOTE_ADDED",
        entity="ipd_admissions",
        entity_id=id,
        details={"note_snippet": note[:50]},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    # Format and return updated list of progress notes
    serialized_notes = []
    for n in (admission.get("progress_notes", []) or []) + [new_note]:
        serialized_notes.append({
            "date": n["date"].isoformat() if isinstance(n["date"], datetime) else n["date"],
            "note": n["note"],
            "by": n["by"]
        })
    return {"status": "success", "progress_notes": serialized_notes}


@router.post("/admin/accumulate-bed-charges")
async def trigger_bed_charge_accumulation(
    current_user: dict = Depends(get_current_user)
):
    """Admin endpoint to trigger daily bed charge accumulation for all active admissions."""
    role = current_user.get("role")
    if role not in ["super_admin", "hospital_admin", "branch_admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can trigger bed charge accumulation."
        )
    
    from services.bed_charge_service import accumulate_daily_bed_charges
    result = await accumulate_daily_bed_charges()
    
    return {"status": "success", "summary": result}


@router.get("/admissions/{id}/discharge-summary/pdf")
async def download_discharge_summary_pdf(
    id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Generate and download a PDF version of the patient's IPD discharge summary."""
    from fastapi.responses import Response
    admissions_col = get_ipd_admissions_collection()
    patients_col = get_patients_collection()
    users_col = get_users_collection()
    from database import get_tenants_collection, get_db
    tenants_col = get_tenants_collection()
    
    try:
        admission_oid = ObjectId(id)
    except:
        raise HTTPException(status_code=400, detail="Invalid admission ID format")
        
    admission = await admissions_col.find_one({"_id": admission_oid})
    if not admission:
        raise HTTPException(status_code=404, detail="IPD Admission record not found")
        
    if current_user.get("role") != "super_admin":
        if str(admission.get("tenant_id")) != str(current_user.get("tenant_id")):
            raise HTTPException(status_code=403, detail="Access denied")
            
    patient = await patients_col.find_one({"_id": admission["patient_id"]})
    if not patient:
        patient = {}
        
    doctor = {}
    doctor_id = admission.get("doctor_id")
    if doctor_id:
        try:
            db_doc = await users_col.find_one({"_id": ObjectId(doctor_id)})
            if db_doc:
                doctor = {
                    "name": db_doc.get("name", "Doctor"),
                    "registration_number": db_doc.get("registration_number", ""),
                    "department": db_doc.get("department", "")
                }
        except:
            pass
            
    tenant = await tenants_col.find_one({"_id": admission["tenant_id"]})
    hospital_info = {
        "name": tenant.get("name", "MediCloud HIMS") if tenant else "MediCloud HIMS",
        "address": tenant.get("address", "Registered Office Address") if tenant else "Registered Office Address",
        "phone": tenant.get("phone", "") if tenant else "",
        "email": tenant.get("email", "") if tenant else "",
        "gstin": tenant.get("gstin", "") if tenant else ""
    }
    
    # Structure discharge summary text & mock medication array if not embedded
    discharge_summary_text = admission.get("discharge_summary", "Clinical discharge summary guidelines followed.")
    
    admission_data = {
        "id": str(admission["_id"]),
        "admitted_at": admission.get("admitted_at", admission.get("created_at")),
        "discharged_at": admission.get("discharge_date", datetime.utcnow()),
        "diagnosis": [admission.get("diagnosis", "Under Investigation")],
        "treatment_given": "Standard inpatient medical care and monitoring were administered.",
        "history": "Patient presented with clinical symptoms requiring bed admission and management.",
        "condition_at_discharge": "Clinically stable, vitals within normal parameters.",
        "discharge_summary": discharge_summary_text,
        "follow_up": "Review in outpatient clinic after 1 week."
    }
    
    # Query for associated prescriptions to output real medications list
    presc_col = get_db().prescriptions
    recent_presc = await presc_col.find_one({"patient_id": admission["patient_id"]}, sort=[("created_at", -1)])
    meds_list = []
    if recent_presc:
        for item in recent_presc.get("items", []):
            meds_list.append({
                "name": item.get("medicine_name", "Medicine"),
                "dosage": item.get("dosage", ""),
                "frequency": item.get("frequency", ""),
                "duration": item.get("duration", "")
            })
            
    from services.pdf_service import generate_discharge_summary_pdf
    
    base_url = str(request.base_url).rstrip('/')
    pdf_bytes = generate_discharge_summary_pdf(
        admission=admission_data,
        patient=patient,
        hospital=hospital_info,
        doctor=doctor,
        medications=meds_list,
        base_url=base_url
    )
    
    headers = {
        "Content-Disposition": f"attachment; filename=discharge_summary_{str(admission['_id'])[:8]}.pdf"
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


@router.get("/wards/map")
async def get_wards_map(current_user: dict = Depends(get_current_user)):
    """Retrieve an aggregated, real-time map of all wards/beds and their current occupancy status."""
    rooms_col = get_rooms_collection()
    admissions_col = get_ipd_admissions_collection()
    
    tenant_oid = current_user["tenant_id"]
    branch_oid = current_user["branch_id"]
    
    # 1. Fetch all configured rooms/beds in this branch
    rooms = await rooms_col.find({"tenant_id": tenant_oid, "branch_id": branch_oid}).to_list(None)
    
    # 2. Fetch all active admissions (not discharged)
    active_admissions = await admissions_col.find({
        "tenant_id": tenant_oid,
        "branch_id": branch_oid,
        "status": "admitted"
    }).to_list(None)
    
    # Map room_id to admission details for easy lookup
    admit_map = {}
    for a in active_admissions:
        admit_map[str(a["room_id"])] = {
            "admission_id": str(a["_id"]),
            "patient_id": str(a["patient_id"]),
            "admitted_at": a.get("admitted_at", a.get("created_at")),
            "diagnosis": a.get("diagnosis", "Under Investigation")
        }
        
    # Get patients database references to attach patient names
    patients_col = get_patients_collection()
    
    # 3. Build floor map grouped by ward/room_type
    wards = {}
    for r in rooms:
        room_id_str = str(r["_id"])
        ward_name = r.get("ward_name", r.get("room_type", "General Ward")).strip()
        
        patient_info = None
        admission_details = admit_map.get(room_id_str)
        if admission_details:
            # Resolve patient name
            pat = await patients_col.find_one({"_id": ObjectId(admission_details["patient_id"])})
            if pat:
                patient_info = {
                    "name": f"{pat.get('first_name', '')} {pat.get('last_name', '')}".strip(),
                    "mrn": pat.get("mrn", "N/A"),
                    "gender": pat.get("gender", "N/A"),
                    "age": pat.get("age", "N/A")
                }
                
        room_entry = {
            "id": room_id_str,
            "room_number": r.get("room_number", "N/A"),
            "room_type": r.get("room_type", "General"),
            "status": r.get("status", "available"), # available, occupied, maintenance
            "price_per_day": float(r.get("price_per_day", 0.0) or r.get("rate", 0.0)),
            "admission": admission_details,
            "patient": patient_info
        }
        
        if ward_name not in wards:
            wards[ward_name] = []
        wards[ward_name].append(room_entry)
        
    # Format response
    result = []
    for ward, beds in wards.items():
        total_beds = len(beds)
        occupied = sum(1 for b in beds if b["status"] == "occupied")
        available = total_beds - occupied
        result.append({
            "ward_name": ward,
            "total_beds": total_beds,
            "occupied_beds": occupied,
            "available_beds": available,
            "beds": beds
        })
        
    return result



