from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File, Form
from bson import ObjectId
from datetime import datetime
import os
import aiofiles
from typing import List, Optional

from database import (
    get_lab_orders_collection,
    get_lab_results_collection,
    get_patients_collection,
    get_visits_collection,
    get_lab_test_master_collection
)
from middleware.auth import (
    get_current_user,
    get_tenant_filter,
    get_branch_filter,
    inject_audit_fields,
    require_role,
    require_permission
)
from middleware.audit import create_audit_log
from models.lab import (
    LabOrderCreate,
    LabOrderResponse,
    LabResultCreate,
    LabResultResponse,
    LabResultEntry
)

router = APIRouter()

def check_abnormal(value_str: str, normal_range_str: str) -> bool:
    if not normal_range_str or not value_str:
        return False
    try:
        # Strip all whitespace
        val = float(value_str.strip())
        nr = normal_range_str.strip().lower()
        
        if "-" in nr:
            parts = nr.split("-")
            low = float(parts[0].strip())
            high = float(parts[1].strip())
            return not (low <= val <= high)
        elif "<" in nr:
            limit = float(nr.replace("<", "").strip())
            return not (val < limit)
        elif ">" in nr:
            limit = float(nr.replace(">", "").strip())
            return not (val > limit)
        elif "less than" in nr:
            limit = float(nr.replace("less than", "").strip())
            return not (val < limit)
        elif "more than" in nr:
            limit = float(nr.replace("more than", "").strip())
            return not (val > limit)
    except ValueError:
        # Fallback to qualitative/string match
        val_clean = value_str.strip().lower()
        nr_clean = normal_range_str.strip().lower()
        if val_clean != nr_clean and nr_clean:
            if "neg" in nr_clean and "pos" in val_clean:
                return True
            if "pos" in nr_clean and "neg" in val_clean:
                return True
    return False

@router.post("/orders", response_model=LabOrderResponse)
async def create_lab_order(payload: LabOrderCreate, request: Request, current_user: dict = Depends(get_current_user)):
    orders_col = get_lab_orders_collection()
    patients_col = get_patients_collection()
    
    # Verify patient exists
    try:
        patient_oid = ObjectId(payload.patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient ID format")
        
    patient = await patients_col.find_one({"_id": patient_oid, "tenant_id": current_user["tenant_id"]})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
        
    doc = payload.dict()
    inject_audit_fields(current_user, doc)
    
    # Store ObjectIds internally for queries
    doc["patient_id"] = patient_oid
    try:
        doc["visit_id"] = ObjectId(payload.visit_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid visit ID format")
        
    # Default status to ordered
    doc["status"] = "ordered"
    
    res = await orders_col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    doc["patient_id"] = str(doc["patient_id"])
    doc["visit_id"] = str(doc["visit_id"])
    doc["patient_name"] = f"{patient.get('first_name', '')} {patient.get('last_name', '')}"
    doc["doctor_name"] = current_user.get("name", "Doctor")
    
    # Auto-post lab charges to billing
    try:
        from services.auto_charge_service import post_auto_charges
        billing_items = [
            {
                "description": f"Lab Test: {item.test_name} ({item.test_code})",
                "quantity": 1,
                "base_price": item.price,
                "gst_rate": 0.0
            }
            for item in payload.items if item.price > 0
        ]
        await post_auto_charges(
            tenant_id=current_user["tenant_id"],
            branch_id=current_user["branch_id"],
            patient_id=payload.patient_id,
            visit_id=payload.visit_id,
            line_items=billing_items,
            source="lab",
            source_order_id=doc["id"],
            created_by=str(current_user["_id"]),
            created_by_name=current_user.get("name", "System")
        )
    except Exception as e:
        # Non-blocking: log error but don't fail the lab order
        import traceback
        traceback.print_exc()
        print(f"[AUTO-CHARGE] Lab charge capture failed: {e}")
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="LAB_ORDER_CREATED",
        entity="lab_orders",
        entity_id=doc["id"],
        details={"tests_count": len(payload.items)},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    return LabOrderResponse(**doc)

@router.get("/orders", response_model=List[LabOrderResponse])
async def list_lab_orders(
    status: Optional[str] = None,
    patient_id: Optional[str] = None,
    visit_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    orders_col = get_lab_orders_collection()
    patients_col = get_patients_collection()
    
    query = get_branch_filter(current_user)
    
    if status:
        query["status"] = status
    if patient_id:
        try:
            query["patient_id"] = ObjectId(patient_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid patient_id format")
    if visit_id:
        try:
            query["visit_id"] = ObjectId(visit_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid visit_id format")
            
    docs = await orders_col.find(query).sort("created_at", -1).to_list(None)
    result = []
    
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["branch_id"] = str(doc["branch_id"])
        
        # Populate patient details
        patient = await patients_col.find_one({"_id": doc["patient_id"]})
        if patient:
            doc["patient_name"] = f"{patient.get('first_name', '')} {patient.get('last_name', '')}"
        else:
            doc["patient_name"] = "Unknown Patient"
            
        doc["patient_id"] = str(doc["patient_id"])
        doc["visit_id"] = str(doc["visit_id"])
        
        # Fetch creator details (doctor)
        doc["doctor_name"] = "Clinical Doctor"
        creator_id = doc.get("created_by")
        if creator_id:
            try:
                # Import get_users_collection inline to avoid cyclic dependencies
                from database import get_users_collection
                creator = await get_users_collection().find_one({"_id": ObjectId(creator_id)})
                if creator:
                    doc["doctor_name"] = creator.get("name", "Doctor")
            except:
                pass
                
        result.append(LabOrderResponse(**doc))
        
    return result

@router.get("/orders/{order_id}", response_model=LabOrderResponse)
async def get_lab_order(order_id: str, current_user: dict = Depends(get_current_user)):
    orders_col = get_lab_orders_collection()
    patients_col = get_patients_collection()
    
    try:
        order_oid = ObjectId(order_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid order ID format")
        
    doc = await orders_col.find_one({"_id": order_oid, "tenant_id": current_user["tenant_id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Lab order profile not found")
        
    doc["id"] = str(doc["_id"])
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    
    # Populate patient
    patient = await patients_col.find_one({"_id": doc["patient_id"]})
    if patient:
        doc["patient_name"] = f"{patient.get('first_name', '')} {patient.get('last_name', '')}"
    else:
        doc["patient_name"] = "Unknown Patient"
        
    doc["patient_id"] = str(doc["patient_id"])
    doc["visit_id"] = str(doc["visit_id"])
    
    doc["doctor_name"] = "Clinical Doctor"
    creator_id = doc.get("created_by")
    if creator_id:
        try:
            from database import get_users_collection
            creator = await get_users_collection().find_one({"_id": ObjectId(creator_id)})
            if creator:
                doc["doctor_name"] = creator.get("name", "Doctor")
        except:
            pass
            
    return LabOrderResponse(**doc)

@router.put("/orders/{order_id}/status")
async def update_lab_order_status(
    order_id: str,
    status: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    orders_col = get_lab_orders_collection()
    
    if status not in ["ordered", "sample_collected", "result_entered", "verified"]:
        raise HTTPException(status_code=400, detail="Invalid status code specified")
        
    try:
        order_oid = ObjectId(order_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid order ID format")
        
    order = await orders_col.find_one({"_id": order_oid, "tenant_id": current_user["tenant_id"]})
    if not order:
        raise HTTPException(status_code=404, detail="Lab order profile not found")
        
    await orders_col.update_one(
        {"_id": order_oid},
        {"$set": {"status": status, "updated_at": datetime.utcnow(), "updated_by": str(current_user["_id"])}}
    )
    
    # Emit realtime Socket event
    sio = getattr(request.app.state, "sio", None)
    if sio:
        branch_id = str(order["branch_id"])
        await sio.emit("queue.updated", {"branch_id": branch_id}, room=f"branch_{branch_id}")
        
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="LAB_ORDER_STATUS_UPDATED",
        entity="lab_orders",
        entity_id=order_id,
        details={"new_status": status},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    return {"status": "success", "message": f"Order status updated to {status}"}

@router.post("/orders/{order_id}/results", response_model=LabResultResponse)
async def enter_lab_results(
    order_id: str,
    payload: LabResultCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    orders_col = get_lab_orders_collection()
    results_col = get_lab_results_collection()
    master_col = get_lab_test_master_collection()
    
    try:
        order_oid = ObjectId(order_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid order ID format")
        
    order = await orders_col.find_one({"_id": order_oid, "tenant_id": current_user["tenant_id"]})
    if not order:
        raise HTTPException(status_code=404, detail="Lab order profile not found")
        
    # Check each result item, find its master test, and check normal range flags
    processed_results = []
    for entry in payload.results:
        normal_range = entry.normal_range
        unit = entry.unit
        
        # Try to pull thresholds from lab master database if not provided
        try:
            test_master = await master_col.find_one({"test_code": entry.test_id})
            if not test_master:
                # fallback query on test_name
                test_master = await master_col.find_one({"test_name": entry.test_name})
            
            if test_master:
                if not normal_range:
                    normal_range = test_master.get("normal_range", "")
                if not unit:
                    unit = test_master.get("unit", "")
        except:
            pass
            
        abnormal = check_abnormal(entry.result_value, normal_range)
        
        processed_results.append({
            "test_id": entry.test_id,
            "test_name": entry.test_name,
            "result_value": entry.result_value,
            "normal_range": normal_range,
            "unit": unit,
            "abnormal_flag": abnormal
        })
        
    # Check if a result doc already exists for this lab order
    existing_result = await results_col.find_one({"lab_order_id": order_oid})
    
    result_doc = {
        "lab_order_id": order_oid,
        "results": processed_results,
        "pdf_url": payload.pdf_url or (existing_result.get("pdf_url") if existing_result else None)
    }
    
    inject_audit_fields(current_user, result_doc, is_create=(existing_result is None))
    
    if existing_result:
        await results_col.update_one({"_id": existing_result["_id"]}, {"$set": result_doc})
        result_doc["id"] = str(existing_result["_id"])
    else:
        res = await results_col.insert_one(result_doc)
        result_doc["id"] = str(res.inserted_id)
        
    # Update order status to result_entered
    await orders_col.update_one(
        {"_id": order_oid},
        {"$set": {"status": "result_entered", "updated_at": datetime.utcnow(), "updated_by": str(current_user["_id"])}}
    )
    
    # Emit Socket updates
    sio = getattr(request.app.state, "sio", None)
    if sio:
        branch_id = str(order["branch_id"])
        await sio.emit("queue.updated", {"branch_id": branch_id}, room=f"branch_{branch_id}")
        
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="LAB_RESULTS_ENTERED",
        entity="lab_results",
        entity_id=result_doc["id"],
        details={"lab_order_id": order_id},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    result_doc["lab_order_id"] = str(result_doc["lab_order_id"])
    result_doc["results"] = [LabResultEntry(**r) for r in processed_results]
    return LabResultResponse(**result_doc)

@router.post("/orders/{order_id}/upload-report")
async def upload_lab_pdf_report(
    order_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    orders_col = get_lab_orders_collection()
    results_col = get_lab_results_collection()
    
    try:
        order_oid = ObjectId(order_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid order ID format")
        
    order = await orders_col.find_one({"_id": order_oid, "tenant_id": current_user["tenant_id"]})
    if not order:
        raise HTTPException(status_code=404, detail="Lab order profile not found")
        
    # Validate PDF format
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF document files can be uploaded as reports")
        
    # Validate size limit (< 15MB)
    max_size = 15 * 1024 * 1024
    contents = await file.read()
    if len(contents) > max_size:
        raise HTTPException(status_code=400, detail="File exceeds maximum allowed size of 15MB")
    await file.seek(0)
    
    # Save file locally under static mount uploads/labs/{order_id}/
    upload_dir = os.path.join(os.getcwd(), "uploads", "labs", order_id)
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, file.filename)
    
    async with aiofiles.open(file_path, "wb") as out_file:
        await out_file.write(contents)
        
    relative_url = f"/uploads/labs/{order_id}/{file.filename}"
    
    # Update results doc
    result_doc = await results_col.find_one({"lab_order_id": order_oid})
    if result_doc:
        await results_col.update_one(
            {"_id": result_doc["_id"]},
            {"$set": {"pdf_url": relative_url, "updated_at": datetime.utcnow(), "updated_by": str(current_user["_id"])}}
        )
    else:
        # Create a stub result doc
        stub_doc = {
            "lab_order_id": order_oid,
            "results": [],
            "pdf_url": relative_url
        }
        inject_audit_fields(current_user, stub_doc, is_create=True)
        await results_col.insert_one(stub_doc)
        
    # Update order status to result_entered if it was less advanced
    if order.get("status") in ["ordered", "sample_collected"]:
        await orders_col.update_one(
            {"_id": order_oid},
            {"$set": {"status": "result_entered", "updated_at": datetime.utcnow(), "updated_by": str(current_user["_id"])}}
        )
        
    return {"status": "success", "pdf_url": relative_url}

@router.get("/orders/{order_id}/results", response_model=LabResultResponse)
async def get_lab_order_results(order_id: str, current_user: dict = Depends(get_current_user)):
    results_col = get_lab_results_collection()
    
    try:
        order_oid = ObjectId(order_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid order ID format")
        
    doc = await results_col.find_one({"lab_order_id": order_oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Lab results not found for this order")
        
    doc["id"] = str(doc["_id"])
    doc["lab_order_id"] = str(doc["lab_order_id"])
    return LabResultResponse(**doc)


@router.get("/results", response_model=List[LabResultResponse])
async def get_lab_results_by_visit(
    visit_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        visit_oid = ObjectId(visit_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid visit ID format")
        
    orders_col = get_lab_orders_collection()
    results_col = get_lab_results_collection()
    
    orders = await orders_col.find({"visit_id": visit_oid, "tenant_id": current_user["tenant_id"]}).to_list(None)
    order_ids = [o["_id"] for o in orders]
    
    results = await results_col.find({"lab_order_id": {"$in": order_ids}}).to_list(None)
    
    response = []
    for r in results:
        r["id"] = str(r["_id"])
        r["lab_order_id"] = str(r["lab_order_id"])
        response.append(r)
        
    return response

@router.get("/results/patient", response_model=List[LabOrderResponse])
async def list_patient_lab_results(current_user: dict = Depends(get_current_user)):
    """Allow patient to retrieve their own lab orders list."""
    if current_user.get("role") != "patient":
        raise HTTPException(status_code=403, detail="Access denied: patient role required")
        
    orders_col = get_lab_orders_collection()
    patients_col = get_patients_collection()
    patient_oid = ObjectId(current_user["_id"])
    
    docs = await orders_col.find({"patient_id": patient_oid}).sort("created_at", -1).to_list(None)
    result = []
    
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["branch_id"] = str(doc["branch_id"])
        doc["patient_id"] = str(doc["patient_id"])
        doc["visit_id"] = str(doc["visit_id"])
        
        doc["doctor_name"] = "Clinical Doctor"
        creator_id = doc.get("created_by")
        if creator_id:
            try:
                from database import get_users_collection
                creator = await get_users_collection().find_one({"_id": ObjectId(creator_id)})
                if creator:
                    doc["doctor_name"] = creator.get("name", "Doctor")
            except:
                pass
                
        patient = await patients_col.find_one({"_id": patient_oid})
        doc["patient_name"] = f"{patient.get('first_name', '')} {patient.get('last_name', '')}" if patient else "Patient"
        
        result.append(LabOrderResponse(**doc))
        
    return result

@router.get("/results/patient/{order_id}", response_model=LabOrderResponse)
async def get_patient_lab_result_detail(order_id: str, current_user: dict = Depends(get_current_user)):
    """Allow patient to retrieve details of a specific lab order/result."""
    if current_user.get("role") != "patient":
        raise HTTPException(status_code=403, detail="Access denied: patient role required")
        
    try:
        order_oid = ObjectId(order_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid order ID format")
        
    orders_col = get_lab_orders_collection()
    patients_col = get_patients_collection()
    
    doc = await orders_col.find_one({"_id": order_oid, "patient_id": ObjectId(current_user["_id"])})
    if not doc:
        raise HTTPException(status_code=404, detail="Lab order not found or access denied")
        
    doc["id"] = str(doc["_id"])
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    doc["patient_id"] = str(doc["patient_id"])
    doc["visit_id"] = str(doc["visit_id"])
    
    doc["doctor_name"] = "Clinical Doctor"
    creator_id = doc.get("created_by")
    if creator_id:
        try:
            from database import get_users_collection
            creator = await get_users_collection().find_one({"_id": ObjectId(creator_id)})
            if creator:
                doc["doctor_name"] = creator.get("name", "Doctor")
        except:
            pass
            
    patient = await patients_col.find_one({"_id": ObjectId(current_user["_id"])})
    doc["patient_name"] = f"{patient.get('first_name', '')} {patient.get('last_name', '')}" if patient else "Patient"
    
    return LabOrderResponse(**doc)

@router.get("/results/patient/{order_id}/pdf")
async def download_lab_result_pdf(order_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Generate and download a PDF version of the patient's lab results."""
    from fastapi.responses import Response
    orders_col = get_lab_orders_collection()
    patients_col = get_patients_collection()
    results_col = get_lab_results_collection()
    from database import get_users_collection, get_tenants_collection
    users_col = get_users_collection()
    tenants_col = get_tenants_collection()
    
    try:
        order_oid = ObjectId(order_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid order ID format")
        
    doc = await orders_col.find_one({"_id": order_oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Lab order not found")
        
    if current_user.get("role") != "super_admin":
        if str(doc.get("tenant_id")) != str(current_user.get("tenant_id")):
            raise HTTPException(status_code=403, detail="Access denied")
        # Allow viewing for patient OR staff
        if current_user.get("role") == "patient" and str(doc.get("patient_id")) != str(current_user["_id"]):
            raise HTTPException(status_code=403, detail="Access denied: patient mismatch")
            
    patient = await patients_col.find_one({"_id": doc["patient_id"]})
    if not patient:
        patient = {}
        
    # Get referring doctor details
    doctor_name = "Self Referral"
    doctor_id = doc.get("created_by") or doc.get("doctor_id")
    if doctor_id:
        try:
            db_doc = await users_col.find_one({"_id": ObjectId(doctor_id)})
            if db_doc:
                doctor_name = db_doc.get("name", "Doctor")
        except:
            pass

    tenant = await tenants_col.find_one({"_id": doc["tenant_id"]})
    hospital_info = {
        "name": tenant.get("name", "MediCloud HIMS") if tenant else "MediCloud HIMS",
        "address": tenant.get("address", "Registered Office Address") if tenant else "Registered Office Address",
        "phone": tenant.get("phone", "") if tenant else "",
        "email": tenant.get("email", "") if tenant else "",
        "gstin": tenant.get("gstin", "") if tenant else ""
    }
    
    # Query results
    db_results = await results_col.find({"order_id": order_oid}).to_list(None)
    results_list = []
    
    if db_results:
        for r in db_results:
            results_list.append({
                "parameter": r.get("parameter", r.get("test_parameter", "Investigation")),
                "value": r.get("value", "—"),
                "unit": r.get("unit", ""),
                "normal_range": r.get("normal_range", ""),
                "is_abnormal": r.get("is_abnormal", False)
            })
    else:
        # Fallback to items if no results entered
        for item in doc.get("items", []):
            results_list.append({
                "parameter": item.get("test_name", "Test Parameter"),
                "value": "Pending",
                "unit": "",
                "normal_range": "",
                "is_abnormal": False
            })
            
    from services.pdf_service import generate_lab_report_pdf
    
    base_url = str(request.base_url).rstrip('/')
    pdf_bytes = generate_lab_report_pdf(
        lab_order=doc,
        results=results_list,
        patient=patient,
        hospital=hospital_info,
        doctor_name=doctor_name,
        base_url=base_url
    )
    
    headers = {
        "Content-Disposition": f"attachment; filename=lab_results_{str(doc['_id'])[:8]}.pdf"
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)

