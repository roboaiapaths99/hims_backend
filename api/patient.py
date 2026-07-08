from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File, Form
from bson import ObjectId
from datetime import datetime
import os
from typing import Optional, List
import aiofiles



from database import (
    get_patients_collection, get_branches_collection, 
    get_db, get_audit_logs_collection, get_visits_collection,
    get_invoices_collection, get_lab_orders_collection,
    get_radiology_orders_collection, get_users_collection,
    get_stored_files_collection
)
from middleware.auth import (
    require_permission, get_current_user, get_tenant_filter, 
    get_branch_filter, inject_audit_fields
)
from middleware.audit import create_audit_log
from models.patient import (
    PatientCreate, PatientResponse, PatientUpdate,
    MedicalHistoryCreate, MedicalHistoryResponse,
    PatientDocumentCreate, PatientDocumentResponse,
    FamilyMemberCreate, FamilyMemberResponse
)
import uuid
import shutil
from api.storage import FORBIDDEN_EXTENSIONS, get_s3_client

router = APIRouter()

from pymongo import ReturnDocument

# Helper to generate unique branch-wise MRN
async def generate_patient_mrn(tenant_id: ObjectId, branch_id: ObjectId) -> str:
    # 1. Load branch code prefix
    branches_col = get_branches_collection()
    branch = await branches_col.find_one({"_id": branch_id})
    if not branch:
        raise HTTPException(status_code=400, detail="Invalid branch ID specified")
    branch_prefix = branch.get("code", "HOSP").upper()
    
    # 2. Get date strings
    today_str = datetime.utcnow().strftime("%Y%m%d")
    
    # 3. Atomic counter increment scoped by branch and day
    counters_col = get_db().mrn_counters
    counter_doc = await counters_col.find_one_and_update(
        {"branch_id": branch_id, "date_prefix": today_str},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    
    seq = counter_doc.get("seq", 1)
    sequence_num = str(seq).zfill(4)
    return f"{branch_prefix}-PID-{today_str}-{sequence_num}"


# ------------------------------------------------------------------
# PATIENT REGISTRATION & CRUD
# ------------------------------------------------------------------

@router.post("", response_model=PatientResponse, dependencies=[Depends(require_permission("register_patient"))])
@router.post("/", response_model=PatientResponse, dependencies=[Depends(require_permission("register_patient"))])
async def create_patient(payload: PatientCreate, request: Request, current_user: dict = Depends(get_current_user)):
    patients_col = get_patients_collection()
    
    tenant_oid = current_user["tenant_id"]
    branch_oid = current_user["branch_id"]
    
    if not tenant_oid or not branch_oid:
        raise HTTPException(
            status_code=400,
            detail="Staff user must be assigned to an active tenant and branch to register patients"
        )
        
    # Tenant SaaS patient quota check
    if current_user["role"] != "super_admin":
        from database import get_tenants_collection
        tenants_col = get_tenants_collection()
        tenant = await tenants_col.find_one({"_id": tenant_oid})
        if tenant:
            max_patients = tenant.get("max_patients", 100)
            current_patients = await patients_col.count_documents({
                "tenant_id": tenant_oid,
                "is_deleted": {"$ne": True}
            })
            if current_patients >= max_patients:
                raise HTTPException(
                    status_code=400,
                    detail=f"Patient registry limit reached ({current_patients}/{max_patients}). Please upgrade your SaaS subscription."
                )
        
    # Check duplicate by phone number within the same tenant
    existing = await patients_col.find_one({
        "phone": payload.phone,
        "tenant_id": tenant_oid,
        "is_deleted": {"$ne": True}
    })
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Patient with mobile number {payload.phone} is already registered under MRN: {existing.get('mrn')}"
        )
        
    doc = payload.dict()
    inject_audit_fields(current_user, doc)
    
    # Force generate sequential MRN
    doc["mrn"] = await generate_patient_mrn(tenant_oid, branch_oid)
    
    res = await patients_col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="PATIENT_REGISTERED",
        entity="patients",
        entity_id=doc["id"],
        details={"name": f"{payload.first_name} {payload.last_name}", "mrn": doc["mrn"], "phone": payload.phone},
        ip_address=request.client.host if request.client else None,
        tenant_id=tenant_oid,
        branch_id=branch_oid
    )
    
    # Non-blocking background sync to DMS
    from config import settings
    from services.dms_patient_sync_service import sync_patient_to_dms
    if settings.DMS_INTEGRATION_ENABLED:
        import asyncio
        asyncio.create_task(sync_patient_to_dms(doc["id"]))
        
    return PatientResponse(**doc)

@router.get("", response_model=List[PatientResponse])
@router.get("/", response_model=List[PatientResponse])
async def search_patients(q: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    patients_col = get_patients_collection()
    query = get_tenant_filter(current_user)
    
    if q:
        import re
        escaped = re.escape(q)
        query["$or"] = [
            {"first_name": {"$regex": escaped, "$options": "i"}},
            {"last_name": {"$regex": escaped, "$options": "i"}},
            {"phone": {"$regex": escaped, "$options": "i"}},
            {"mrn": {"$regex": escaped, "$options": "i"}}
        ]
        
    docs = await patients_col.find(query).limit(50).to_list(None)
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["branch_id"] = str(doc["branch_id"])
        result.append(PatientResponse(**doc))
    return result

@router.get("/duplicate-check", response_model=List[PatientResponse])
async def duplicate_check(
    phone: Optional[str] = None,
    name: Optional[str] = None,
    dob: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    import re
    patients_col = get_patients_collection()
    tenant_filter = get_tenant_filter(current_user)
    
    or_clauses = []
    
    if phone:
        or_clauses.append({"phone": phone})
        
    if name and dob:
        name_parts = name.strip().split()
        if len(name_parts) >= 2:
            first = name_parts[0]
            last = " ".join(name_parts[1:])
            name_match = {
                "first_name": {"$regex": f"^{re.escape(first)}$", "$options": "i"},
                "last_name": {"$regex": f"^{re.escape(last)}$", "$options": "i"}
            }
        else:
            first = name_parts[0]
            name_match = {
                "first_name": {"$regex": f"^{re.escape(first)}$", "$options": "i"}
            }
            
        try:
            dob_dt = datetime.strptime(dob, "%Y-%m-%d")
            start_of_day = dob_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = dob_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
            dob_match = {"dob": {"$gte": start_of_day, "$lte": end_of_day}}
        except Exception:
            dob_match = {"dob": dob}
            
        or_clauses.append({
            "$and": [name_match, dob_match]
        })
        
    if not or_clauses:
        return []
        
    query = {"$and": [tenant_filter, {"$or": or_clauses}, {"is_deleted": {"$ne": True}}]}
    docs = await patients_col.find(query).limit(5).to_list(None)
    
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["branch_id"] = str(doc["branch_id"])
        result.append(PatientResponse(**doc))
    return result

@router.get("/portal/dashboard-data")
@router.get("/portal/dashboard-data/")
async def get_patient_portal_data(current_user: dict = Depends(get_current_user)):
    # Since patient logs in via login_patient_phone, their sub/id is their patient ID in the database
    patient_id_str = str(current_user["_id"])
    try:
        patient_oid = ObjectId(patient_id_str)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient session ID format")
        
    patients_col = get_patients_collection()
    patient = await patients_col.find_one({"_id": patient_oid})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
        
    # 1. Resolve Patient Info
    profile = {
        "id": patient_id_str,
        "mrn": patient.get("mrn"),
        "first_name": patient.get("first_name"),
        "last_name": patient.get("last_name"),
        "phone": patient.get("phone"),
        "email": patient.get("email"),
        "gender": patient.get("gender"),
        "dob": patient.get("dob"),
        "blood_group": patient.get("blood_group"),
        "address": patient.get("address")
    }
    
    # 2. Get historical visits
    visits_col = get_visits_collection()
    visits = await visits_col.find({"patient_id": patient_oid}).sort("visit_date", -1).to_list(None)
    
    users_col = get_users_collection()
    doctors_cache = {}
    
    formatted_visits = []
    for v in visits:
        doc_id = str(v.get("doctor_id")) if v.get("doctor_id") else None
        doc_name = "General Practitioner"
        if doc_id:
            if doc_id not in doctors_cache:
                doc_user = await users_col.find_one({"_id": ObjectId(doc_id)})
                doctors_cache[doc_id] = doc_user.get("name", "Doctor") if doc_user else "Doctor"
            doc_name = doctors_cache[doc_id]
            
        formatted_visits.append({
            "id": str(v["_id"]),
            "visit_date": v.get("visit_date").strftime("%Y-%m-%d") if isinstance(v.get("visit_date"), datetime) else str(v.get("visit_date")),
            "status": v.get("status"),
            "doctor_name": doc_name,
            "chief_complaint": v.get("chief_complaint"),
            "soap_notes": v.get("soap_notes"),
            "prescriptions": v.get("prescriptions", [])
        })
        
    # 3. Get invoices
    invoices_col = get_invoices_collection()
    invoices = await invoices_col.find({"patient_id": patient_oid}).sort("created_at", -1).to_list(None)
    formatted_invoices = []
    for inv in invoices:
        formatted_invoices.append({
            "id": str(inv["_id"]),
            "invoice_number": inv.get("invoice_number"),
            "grand_total": inv.get("grand_total"),
            "payment_status": inv.get("payment_status"),
            "created_at": inv.get("created_at").strftime("%Y-%m-%d") if isinstance(inv.get("created_at"), datetime) else str(inv.get("created_at")),
            "items": inv.get("items", [])
        })
        
    # 4. Get lab orders
    lab_col = get_lab_orders_collection()
    lab_orders = await lab_col.find({"patient_id": patient_oid}).sort("created_at", -1).to_list(None)
    formatted_labs = []
    for lo in lab_orders:
        doc_id = str(lo.get("doctor_id")) if lo.get("doctor_id") else None
        doc_name = "Doctor"
        if doc_id:
            if doc_id not in doctors_cache:
                doc_user = await users_col.find_one({"_id": ObjectId(doc_id)})
                doctors_cache[doc_id] = doc_user.get("name", "Doctor") if doc_user else "Doctor"
            doc_name = doctors_cache[doc_id]
            
        formatted_labs.append({
            "id": str(lo["_id"]),
            "order_number": lo.get("order_number") or f"LAB-{str(lo['_id'])[:8].upper()}",
            "status": lo.get("status"),
            "created_at": lo.get("created_at").strftime("%Y-%m-%d") if isinstance(lo.get("created_at"), datetime) else str(lo.get("created_at")),
            "doctor_name": doc_name,
            "items": lo.get("items", []),
            "results_summary": lo.get("results_summary")
        })
        
    # 5. Get radiology orders
    rad_col = get_radiology_orders_collection()
    rad_orders = await rad_col.find({"patient_id": patient_oid}).sort("created_at", -1).to_list(None)
    formatted_rad = []
    for ro in rad_orders:
        doc_id = str(ro.get("doctor_id")) if ro.get("doctor_id") else None
        doc_name = "Doctor"
        if doc_id:
            if doc_id not in doctors_cache:
                doc_user = await users_col.find_one({"_id": ObjectId(doc_id)})
                doctors_cache[doc_id] = doc_user.get("name", "Doctor") if doc_user else "Doctor"
            doc_name = doctors_cache[doc_id]
            
        formatted_rad.append({
            "id": str(ro["_id"]),
            "order_number": ro.get("order_number") or f"RAD-{str(ro['_id'])[:8].upper()}",
            "status": ro.get("status"),
            "created_at": ro.get("created_at").strftime("%Y-%m-%d") if isinstance(ro.get("created_at"), datetime) else str(ro.get("created_at")),
            "doctor_name": doc_name,
            "test_name": ro.get("test_name"),
            "clinical_indication": ro.get("clinical_indication"),
            "results_url": ro.get("results_url")
        })
        
    # 6. Check active IPD admission & diet orders
    from database import get_ipd_admissions_collection, get_rooms_collection, get_diet_orders_collection
    ipd_col = get_ipd_admissions_collection()
    active_adm = await ipd_col.find_one({"patient_id": patient_oid, "status": "admitted"})
    
    formatted_admission = None
    if active_adm:
        rooms_col = get_rooms_collection()
        room = await rooms_col.find_one({"_id": active_adm["room_id"]})
        room_number = room.get("room_number", "Ward") if room else "Ward"
        
        diet_col = get_diet_orders_collection()
        diet_orders = await diet_col.find({"admission_id": active_adm["_id"]}).sort("created_at", -1).to_list(None)
        
        formatted_diet_orders = []
        for d in diet_orders:
            formatted_diet_orders.append({
                "id": str(d["_id"]),
                "meal_type": d.get("meal_type"),
                "diet_type": d.get("diet_type"),
                "status": d.get("status"),
                "special_instructions": d.get("special_instructions"),
                "created_at": d.get("created_at").strftime("%Y-%m-%d %H:%M") if isinstance(d.get("created_at"), datetime) else str(d.get("created_at"))
            })
            
        formatted_admission = {
            "id": str(active_adm["_id"]),
            "room_number": room_number,
            "admission_date": active_adm["admission_date"].strftime("%Y-%m-%d") if isinstance(active_adm["admission_date"], datetime) else str(active_adm["admission_date"]),
            "diet_orders": formatted_diet_orders
        }
        
    return {
        "profile": profile,
        "visits": formatted_visits,
        "invoices": formatted_invoices,
        "labs": formatted_labs,
        "radiology": formatted_rad,
        "admission": formatted_admission
    }

@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient_details(patient_id: str, current_user: dict = Depends(get_current_user)):
    patients_col = get_patients_collection()
    try:
        patient_oid = ObjectId(patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient ID format")
        
    query = get_tenant_filter(current_user, {"_id": patient_oid})
    doc = await patients_col.find_one(query)
    if not doc:
        raise HTTPException(status_code=404, detail="Patient not found")
        
    doc["id"] = str(doc["_id"])
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    return PatientResponse(**doc)

@router.put("/{patient_id}", response_model=PatientResponse)
async def update_patient(patient_id: str, payload: PatientUpdate, request: Request, current_user: dict = Depends(get_current_user)):
    patients_col = get_patients_collection()
    try:
        patient_oid = ObjectId(patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient ID format")
        
    query = get_tenant_filter(current_user, {"_id": patient_oid})
    patient = await patients_col.find_one(query)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
        
    update_data = payload.dict(exclude_unset=True)
    inject_audit_fields(current_user, update_data, is_create=False)
    
    await patients_col.update_one({"_id": patient_oid}, {"$set": update_data})
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="PATIENT_UPDATED",
        entity="patients",
        entity_id=patient_id,
        details=list(update_data.keys()),
        ip_address=request.client.host if request.client else None,
        tenant_id=patient.get("tenant_id"),
        branch_id=patient.get("branch_id")
    )
    
    # Non-blocking background sync to DMS
    from config import settings
    from services.dms_patient_sync_service import sync_patient_to_dms
    if settings.DMS_INTEGRATION_ENABLED:
        import asyncio
        asyncio.create_task(sync_patient_to_dms(patient_id))
        
    updated = await patients_col.find_one({"_id": patient_oid})
    updated["id"] = str(updated["_id"])
    updated["tenant_id"] = str(updated["tenant_id"])
    updated["branch_id"] = str(updated["branch_id"])
    return PatientResponse(**updated)

# ------------------------------------------------------------------
# PATIENT MEDICAL HISTORY
# ------------------------------------------------------------------
@router.post("/{patient_id}/medical-history", response_model=MedicalHistoryResponse)
async def save_medical_history(patient_id: str, payload: MedicalHistoryCreate, current_user: dict = Depends(get_current_user)):
    col = get_db().patient_medical_history
    try:
        patient_oid = ObjectId(patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient ID format")
        
    # Upsert medical history for this patient
    now = datetime.utcnow()
    existing = await col.find_one({"patient_id": patient_oid})
    
    doc = payload.dict()
    doc["updated_at"] = now
    
    if existing:
        await col.update_one({"_id": existing["_id"]}, {"$set": doc})
        doc["id"] = str(existing["_id"])
        doc["patient_id"] = patient_id
        doc["created_at"] = existing["created_at"]
    else:
        doc["patient_id"] = patient_id
        doc["created_at"] = now
        res = await col.insert_one(doc)
        doc["id"] = str(res.inserted_id)
        
    return MedicalHistoryResponse(**doc)

@router.get("/{patient_id}/medical-history", response_model=MedicalHistoryResponse)
async def get_medical_history(patient_id: str, current_user: dict = Depends(get_current_user)):
    col = get_db().patient_medical_history
    try:
        patient_oid = ObjectId(patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient ID")
        
    doc = await col.find_one({"patient_id": patient_oid})
    if not doc:
        # Return empty default history instead of 404
        return MedicalHistoryResponse(
            id="",
            patient_id=patient_id,
            allergies=[],
            chronic_conditions=[],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
    doc["id"] = str(doc["_id"])
    doc["patient_id"] = str(doc["patient_id"])
    return MedicalHistoryResponse(**doc)

# ------------------------------------------------------------------
# PATIENT DOCUMENTS UPLOADS
# ------------------------------------------------------------------
@router.post("/{patient_id}/documents", response_model=PatientDocumentResponse)
async def upload_patient_document(
    patient_id: str,
    document_name: str = Form(...),
    document_type: str = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    try:
        patient_oid = ObjectId(patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient ID format")
        
    # Validate file size < 10MB
    max_size = 10 * 1024 * 1024
    contents = await file.read()
    if len(contents) > max_size:
        raise HTTPException(status_code=400, detail="File exceeds maximum allowed size of 10MB")
    await file.seek(0)
    
    # Validate extension
    filename = file.filename or "unnamed_file"
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    if ext in FORBIDDEN_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Executable or script uploads are forbidden for security reasons."
        )
        
    # Save file physically with high-entropy unique prefix
    os.makedirs("uploads", exist_ok=True)
    unique_filename = f"{uuid.uuid4()}_{filename}"
    file_path = os.path.join("uploads", unique_filename)
    
    try:
        with open(file_path, "wb") as buffer:
            buffer.write(contents)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to write file to storage: {str(e)}"
        )
        
    # S3 Upload
    s3_client = get_s3_client()
    if s3_client:
        try:
            s3_client.upload_file(file_path, settings.S3_BUCKET_NAME, unique_filename)
            os.remove(file_path)
        except Exception as e:
            if os.path.exists(file_path):
                os.remove(file_path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload file to S3: {str(e)}"
            )
            
    # Insert metadata in stored_files DB
    files_col = get_stored_files_collection()
    file_doc = {
        "tenant_id": current_user.get("tenant_id") or patient_oid,
        "branch_id": current_user.get("branch_id"),
        "filename": unique_filename,
        "original_name": filename,
        "mime_type": file.content_type or "application/octet-stream",
        "size": len(contents),
        "created_at": datetime.utcnow()
    }
    inject_audit_fields(current_user, file_doc)
    res_file = await files_col.insert_one(file_doc)
    file_id = str(res_file.inserted_id)
    
    # Map to patient_documents
    col = get_db().patient_documents
    doc_record = {
        "patient_id": patient_oid,
        "document_name": document_name,
        "document_type": document_type,
        "file_url": f"/api/storage/files/{file_id}/preview",
        "file_id": res_file.inserted_id,
        "uploaded_at": datetime.utcnow()
    }
    
    res = await col.insert_one(doc_record)
    doc_record["id"] = str(res.inserted_id)
    doc_record["patient_id"] = patient_id
    
    return doc_record

@router.get("/{patient_id}/documents", response_model=List[PatientDocumentResponse])
async def list_patient_documents(patient_id: str, current_user: dict = Depends(get_current_user)):
    col = get_db().patient_documents
    try:
        patient_oid = ObjectId(patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient ID")
        
    docs = await col.find({"patient_id": patient_oid}).to_list(None)
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["patient_id"] = str(doc["patient_id"])
        result.append(PatientDocumentResponse(**doc))
    return result



@router.get("/{patient_id}/family", response_model=List[FamilyMemberResponse])
async def get_patient_family_members(patient_id: str, current_user: dict = Depends(get_current_user)):
    try:
        patient_oid = ObjectId(patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient ID format")
    
    col = get_db().family_members
    patients_col = get_patients_collection()
    
    docs = await col.find({"patient_id": patient_oid}).to_list(None)
    result = []
    for doc in docs:
        doc_data = {
            "id": str(doc["_id"]),
            "patient_id": str(doc["patient_id"]),
            "relationship": doc["relationship"],
            "linked_patient_id": str(doc["linked_patient_id"]),
        }
        linked = await patients_col.find_one({"_id": doc["linked_patient_id"]})
        if linked:
            doc_data["name"] = f"{linked.get('first_name', '')} {linked.get('last_name', '')}"
            doc_data["phone"] = linked.get("phone")
            doc_data["gender"] = linked.get("gender")
            doc_data["dob"] = linked.get("dob")
        result.append(doc_data)
    return result

@router.post("/{patient_id}/family", response_model=FamilyMemberResponse)
async def add_patient_family_member(
    patient_id: str,
    payload: FamilyMemberCreate,
    current_user: dict = Depends(get_current_user)
):
    try:
        patient_oid = ObjectId(patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient ID format")
        
    col = get_db().family_members
    patients_col = get_patients_collection()
    
    patient = await patients_col.find_one({"_id": patient_oid})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
        
    linked = None
    linked_oid = None
    
    # 1. Try treating it as a direct MongoDB ObjectId
    if len(payload.linked_patient_id) == 24 and all(c in "0123456789abcdefABCDEF" for c in payload.linked_patient_id):
        try:
            linked_oid = ObjectId(payload.linked_patient_id)
            linked = await patients_col.find_one({"_id": linked_oid})
        except:
            pass

    # 2. Try looking up by Phone, MRN, or ABHA
    if not linked:
        search_key = payload.linked_patient_id.strip()
        linked = await patients_col.find_one({
            "$or": [
                {"phone": search_key},
                {"mrn": search_key},
                {"abha_number": search_key}
            ],
            "is_deleted": {"$ne": True}
        })
        if linked:
            linked_oid = linked["_id"]

    if not linked:
        raise HTTPException(
            status_code=404,
            detail="No family profile found. Please enter a valid Mobile Number, MRN, or ABHA ID."
        )
        
    existing = await col.find_one({"patient_id": patient_oid, "linked_patient_id": linked_oid})
    if existing:
        raise HTTPException(status_code=400, detail="Family member linkage already exists")
        
    new_link = {
        "patient_id": patient_oid,
        "linked_patient_id": linked_oid,
        "relationship": payload.relationship,
        "created_at": datetime.utcnow()
    }
    
    res = await col.insert_one(new_link)
    
    doc_data = {
        "id": str(res.inserted_id),
        "patient_id": patient_id,
        "relationship": payload.relationship,
        "linked_patient_id": str(linked_oid),
        "name": f"{linked.get('first_name', '')} {linked.get('last_name', '')}",
        "phone": linked.get("phone"),
        "gender": linked.get("gender"),
        "dob": linked.get("dob")
    }
    
    return doc_data

@router.get("/{patient_id}/portal-data")
async def get_patient_timeline_history(patient_id: str, current_user: dict = Depends(get_current_user)):
    try:
        patient_oid = ObjectId(patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient ID format")
        
    patients_col = get_patients_collection()
    patient = await patients_col.find_one({"_id": patient_oid})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
        
    profile = {
        "id": patient_id,
        "mrn": patient.get("mrn"),
        "first_name": patient.get("first_name"),
        "last_name": patient.get("last_name"),
        "phone": patient.get("phone"),
        "email": patient.get("email"),
        "gender": patient.get("gender"),
        "dob": patient.get("dob"),
        "blood_group": patient.get("blood_group"),
        "address": patient.get("address")
    }
    
    visits_col = get_visits_collection()
    visits = await visits_col.find({"patient_id": patient_oid}).sort("visit_date", -1).to_list(None)
    
    users_col = get_users_collection()
    doctors_cache = {}
    
    formatted_visits = []
    for v in visits:
        doc_id = str(v.get("doctor_id")) if v.get("doctor_id") else None
        doc_name = "General Practitioner"
        if doc_id:
            if doc_id not in doctors_cache:
                doc_user = await users_col.find_one({"_id": ObjectId(doc_id)})
                doctors_cache[doc_id] = doc_user.get("name", "Doctor") if doc_user else "Doctor"
            doc_name = doctors_cache[doc_id]
            
        formatted_visits.append({
            "id": str(v["_id"]),
            "visit_date": v.get("visit_date").strftime("%Y-%m-%d") if isinstance(v.get("visit_date"), datetime) else str(v.get("visit_date")),
            "status": v.get("status"),
            "doctor_name": doc_name,
            "chief_complaint": v.get("chief_complaint"),
            "soap_notes": v.get("soap_notes"),
            "prescriptions": v.get("prescriptions", [])
        })
        
    invoices_col = get_invoices_collection()
    invoices = await invoices_col.find({"patient_id": patient_oid}).sort("created_at", -1).to_list(None)
    formatted_invoices = []
    for inv in invoices:
        formatted_invoices.append({
            "id": str(inv["_id"]),
            "invoice_number": inv.get("invoice_number"),
            "grand_total": inv.get("grand_total"),
            "payment_status": inv.get("payment_status"),
            "created_at": inv.get("created_at").strftime("%Y-%m-%d") if isinstance(inv.get("created_at"), datetime) else str(inv.get("created_at")),
            "items": inv.get("items", [])
        })
        
    lab_col = get_lab_orders_collection()
    lab_orders = await lab_col.find({"patient_id": patient_oid}).sort("created_at", -1).to_list(None)
    formatted_labs = []
    for lo in lab_orders:
        doc_id = str(lo.get("doctor_id")) if lo.get("doctor_id") else None
        doc_name = "Doctor"
        if doc_id:
            if doc_id not in doctors_cache:
                doc_user = await users_col.find_one({"_id": ObjectId(doc_id)})
                doctors_cache[doc_id] = doc_user.get("name", "Doctor") if doc_user else "Doctor"
            doc_name = doctors_cache[doc_id]
            
        formatted_labs.append({
            "id": str(lo["_id"]),
            "order_number": lo.get("order_number") or f"LAB-{str(lo['_id'])[:8].upper()}",
            "status": lo.get("status"),
            "created_at": lo.get("created_at").strftime("%Y-%m-%d") if isinstance(lo.get("created_at"), datetime) else str(lo.get("created_at")),
            "doctor_name": doc_name,
            "items": lo.get("items", []),
            "results_summary": lo.get("results_summary")
        })
        
    rad_col = get_radiology_orders_collection()
    rad_orders = await rad_col.find({"patient_id": patient_oid}).sort("created_at", -1).to_list(None)
    formatted_rad = []
    for ro in rad_orders:
        doc_id = str(ro.get("doctor_id")) if ro.get("doctor_id") else None
        doc_name = "Doctor"
        if doc_id:
            if doc_id not in doctors_cache:
                doc_user = await users_col.find_one({"_id": ObjectId(doc_id)})
                doctors_cache[doc_id] = doc_user.get("name", "Doctor") if doc_user else "Doctor"
            doc_name = doctors_cache[doc_id]
            
        formatted_rad.append({
            "id": str(ro["_id"]),
            "order_number": ro.get("order_number") or f"RAD-{str(ro['_id'])[:8].upper()}",
            "status": ro.get("status"),
            "created_at": ro.get("created_at").strftime("%Y-%m-%d") if isinstance(ro.get("created_at"), datetime) else str(ro.get("created_at")),
            "doctor_name": doc_name,
            "test_name": ro.get("test_name"),
            "clinical_indication": ro.get("clinical_indication"),
            "results_url": ro.get("results_url")
        })
        
    return {
        "profile": profile,
        "visits": formatted_visits,
        "invoices": formatted_invoices,
        "labs": formatted_labs,
        "radiology": formatted_rad
    }

@router.get("/me/family", response_model=List[FamilyMemberResponse])
async def get_my_family_members(current_user: dict = Depends(get_current_user)):
    patient_id = str(current_user["_id"])
    return await get_patient_family_members(patient_id=patient_id, current_user=current_user)

@router.post("/me/family", response_model=FamilyMemberResponse)
async def add_my_family_member(payload: FamilyMemberCreate, current_user: dict = Depends(get_current_user)):
    patient_id = str(current_user["_id"])
    return await add_patient_family_member(patient_id=patient_id, payload=payload, current_user=current_user)

@router.put("/me/family/{link_id}", response_model=FamilyMemberResponse)
async def update_my_family_member(link_id: str, payload: FamilyMemberCreate, current_user: dict = Depends(get_current_user)):
    patient_id = str(current_user["_id"])
    try:
        link_oid = ObjectId(link_id)
        patient_oid = ObjectId(patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid ID formats")
        
    col = get_db().family_members
    res = await col.find_one_and_update(
        {"_id": link_oid, "patient_id": patient_oid},
        {"$set": {"relationship": payload.relationship}},
        return_document=ReturnDocument.AFTER
    )
    if not res:
        raise HTTPException(status_code=404, detail="Family member linkage not found")
        
    patients_col = get_patients_collection()
    linked = await patients_col.find_one({"_id": res["linked_patient_id"]})
    
    doc_data = {
        "id": str(res["_id"]),
        "patient_id": str(res["patient_id"]),
        "relationship": res["relationship"],
        "linked_patient_id": str(res["linked_patient_id"]),
    }
    if linked:
        doc_data["name"] = f"{linked.get('first_name', '')} {linked.get('last_name', '')}"
        doc_data["phone"] = linked.get("phone")
        doc_data["gender"] = linked.get("gender")
        doc_data["dob"] = linked.get("dob")
        
    return doc_data

@router.delete("/me/family/{link_id}")
async def delete_my_family_member(link_id: str, current_user: dict = Depends(get_current_user)):
    patient_id = str(current_user["_id"])
    try:
        link_oid = ObjectId(link_id)
        patient_oid = ObjectId(patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid ID formats")
        
    col = get_db().family_members
    res = await col.delete_one({"_id": link_oid, "patient_id": patient_oid})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Family member linkage not found")
    return {"status": "success", "message": "Family member link removed successfully"}

@router.post("/me/documents/upload", response_model=PatientDocumentResponse)
async def upload_my_document(
    document_name: str = Form(...),
    document_type: str = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") != "patient":
        raise HTTPException(status_code=403, detail="Access denied: patient role required")
    patient_id = str(current_user["_id"])
    return await upload_patient_document(
        patient_id=patient_id,
        document_name=document_name,
        document_type=document_type,
        file=file,
        current_user=current_user
    )

@router.get("/me/documents", response_model=List[PatientDocumentResponse])
async def get_my_documents(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "patient":
        raise HTTPException(status_code=403, detail="Access denied: patient role required")
    patient_id = str(current_user["_id"])
    return await list_patient_documents(patient_id=patient_id, current_user=current_user)

@router.get("/me/documents/{doc_id}/preview")
async def preview_my_document(
    doc_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") != "patient":
        raise HTTPException(status_code=403, detail="Access denied")
        
    try:
        doc_oid = ObjectId(doc_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid document ID format")
        
    col = get_db().patient_documents
    doc = await col.find_one({"_id": doc_oid, "patient_id": ObjectId(current_user["_id"])})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found or access denied")
        
    file_id = None
    if doc.get("file_id"):
        file_id = str(doc["file_id"])
    elif "files/" in doc.get("file_url", ""):
        file_id = doc["file_url"].split("files/")[1].split("/")[0]
        
    if not file_id:
        from api.storage import resolve_secure_file
        filename = doc["file_url"].split("/")[-1]
        return await resolve_secure_file(filename=filename)
        
    from api.storage import secure_file_preview_proxy
    return await secure_file_preview_proxy(file_id=file_id, request=request, current_user=current_user)

