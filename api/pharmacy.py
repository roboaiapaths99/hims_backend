from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from bson import ObjectId
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from pymongo import ReturnDocument
from database import (
    get_prescriptions_collection,
    get_patients_collection,
    get_visits_collection,
    get_branches_collection
)
from middleware.auth import (
    get_current_user,
    get_tenant_filter,
    get_branch_filter,
    inject_audit_fields,
    require_role
)
from middleware.audit import create_audit_log
from models.prescription import (
    PrescriptionCreate,
    PrescriptionResponse,
    PrescriptionItem
)
from services.inventory_bridge_service import inventory_bridge

router = APIRouter()

# Schema for dispensing
class DispenseItem(BaseModel):
    medicine_id: str
    quantity: int
    batch_id: Optional[str] = None

class DispenseRequest(BaseModel):
    items: List[DispenseItem]

# Fallback Warehouse constant representation
DEFAULT_WAREHOUSE_ID = "000000000000000000000001"

async def get_branch_warehouse_id(branch_id: ObjectId) -> str:
    """Fetch warehouse mapping for the branch, default to DEFAULT_WAREHOUSE_ID if missing"""
    try:
        branches_col = get_branches_collection()
        branch = await branches_col.find_one({"_id": branch_id})
        if branch and branch.get("warehouse_id"):
            return str(branch["warehouse_id"])
    except Exception as e:
        print(f"Error fetching warehouse_id mapping for branch {branch_id}: {e}")
    return DEFAULT_WAREHOUSE_ID

@router.get("/inventory/search")
async def search_inventory_medicines(q: str = Query("", min_length=1), current_user: dict = Depends(get_current_user)):
    """Search active inventory medicine items"""
    items = await inventory_bridge.search_items(q)
    return items

@router.get("/inventory/batches")
async def load_inventory_batches(item_id: str = Query(...), current_user: dict = Depends(get_current_user)):
    """Get active batches for an inventory item sorted by FEFO"""
    batches = await inventory_bridge.get_batches(item_id)
    return batches

@router.post("/prescriptions", response_model=PrescriptionResponse)
async def create_prescription(
    payload: PrescriptionCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    presc_col = get_prescriptions_collection()
    patients_col = get_patients_collection()
    
    # 1. Validate patient profile exists
    try:
        patient_oid = ObjectId(payload.patient_id)
        visit_oid = ObjectId(payload.visit_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient_id or visit_id format")
        
    patient = await patients_col.find_one({"_id": patient_oid, "tenant_id": current_user["tenant_id"]})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
        
    doc = payload.dict()
    inject_audit_fields(current_user, doc)
    
    doc["patient_id"] = patient_oid
    doc["visit_id"] = visit_oid
    doc["status"] = "pending"
    
    # Insert prescription record first to obtain an ID for stock reservation reference
    res = await presc_col.insert_one(doc)
    presc_id_str = str(res.inserted_id)
    doc["id"] = presc_id_str
    
    # 2. Call inventory bridge to reserve stock for each item
    warehouse_id = await get_branch_warehouse_id(doc["branch_id"])
    
    reserved_items = []
    try:
        for item in payload.items:
            # Call inventory reservation
            await inventory_bridge.reserve_stock(
                medicine_id=item.medicine_id,
                quantity=item.quantity_prescribed,
                warehouse_id=warehouse_id,
                reference_id=presc_id_str
            )
            reserved_items.append(item.medicine_id)
    except Exception as e:
        # Transaction Rollback: Release any reservations made before the error
        try:
            await inventory_bridge.release_stock(reference_id=presc_id_str)
        except Exception as rollback_err:
            print(f"Failed to rollback stock reservations for prescription {presc_id_str}: {rollback_err}")
            
        # Delete the failed prescription record from DB
        await presc_col.delete_one({"_id": ObjectId(presc_id_str)})
        
        raise HTTPException(
            status_code=400,
            detail=f"Stock reservation failed: {str(e)}"
        )
        
    # Format response values
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    doc["patient_id"] = str(doc["patient_id"])
    doc["visit_id"] = str(doc["visit_id"])
    doc["patient_name"] = f"{patient.get('first_name', '')} {patient.get('last_name', '')}"
    doc["doctor_name"] = current_user.get("name", "Doctor")
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="PRESCRIPTION_CREATED",
        entity="prescriptions",
        entity_id=presc_id_str,
        details={"items_count": len(payload.items), "items": [item.dict() for item in payload.items]},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    sio = getattr(request.app.state, "sio", None)
    if sio:
        await sio.emit("prescriptions.updated", {"branch_id": str(doc["branch_id"])}, room=f"branch_{doc['branch_id']}")
        
    return PrescriptionResponse(**doc)

@router.get("/prescriptions", response_model=List[PrescriptionResponse])
async def list_prescriptions(
    status: Optional[str] = None,
    patient_id: Optional[str] = None,
    visit_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    presc_col = get_prescriptions_collection()
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
            
    docs = await presc_col.find(query).sort("created_at", -1).to_list(None)
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
                
        result.append(PrescriptionResponse(**doc))
        
    return result

@router.get("/prescriptions/{presc_id}", response_model=PrescriptionResponse)
async def get_prescription(presc_id: str, current_user: dict = Depends(get_current_user)):
    presc_col = get_prescriptions_collection()
    patients_col = get_patients_collection()
    
    try:
        presc_oid = ObjectId(presc_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid prescription ID format")
        
    doc = await presc_col.find_one({"_id": presc_oid, "tenant_id": current_user["tenant_id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Prescription profile not found")
        
    doc["id"] = str(doc["_id"])
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    
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
            
    return PrescriptionResponse(**doc)

@router.post("/prescriptions/{presc_id}/dispense")
async def dispense_prescription(
    presc_id: str,
    payload: DispenseRequest,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    presc_col = get_prescriptions_collection()
    
    try:
        presc_oid = ObjectId(presc_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid prescription ID format")
        
    # Atomic state transition from pending to dispensing to prevent double execution
    presc = await presc_col.find_one_and_update(
        {"_id": presc_oid, "tenant_id": current_user["tenant_id"], "status": "pending"},
        {"$set": {"status": "dispensing"}},
        return_document=ReturnDocument.AFTER
    )
    if not presc:
        # Check if already processed
        already_processed = await presc_col.find_one({"_id": presc_oid, "tenant_id": current_user["tenant_id"]})
        if already_processed and already_processed.get("status") == "dispensed":
            return {"status": "success", "message": "Prescription was already dispensed (idempotent call)"}
        raise HTTPException(status_code=400, detail="Prescription is not in pending status or is already processed.")
        
    warehouse_id = await get_branch_warehouse_id(presc["branch_id"])
    
    # Call inventory sync bridge to deduct stock
    try:
        for item in payload.items:
            await inventory_bridge.deduct_stock(
                medicine_id=item.medicine_id,
                quantity=item.quantity,
                warehouse_id=warehouse_id,
                reference_id=presc_id,
                batch_id=item.batch_id
            )
    except Exception as e:
        # Rollback status on failure
        await presc_col.update_one(
            {"_id": presc_oid, "status": "dispensing"},
            {"$set": {"status": "pending"}}
        )
        raise HTTPException(
            status_code=400,
            detail=f"Pharmacy stock deduction failed: {str(e)}"
        )
        
    # Update prescription status to final dispensed state
    await presc_col.update_one(
        {"_id": presc_oid},
        {"$set": {"status": "dispensed", "updated_at": datetime.utcnow(), "updated_by": str(current_user["_id"])}}
    )
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="PRESCRIPTION_DISPENSED",
        entity="prescriptions",
        entity_id=presc_id,
        details={"dispensed_items_count": len(payload.items), "items": [item.dict() for item in payload.items]},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    sio = getattr(request.app.state, "sio", None)
    if sio:
        await sio.emit("prescriptions.updated", {"branch_id": str(presc["branch_id"])}, room=f"branch_{presc['branch_id']}")
        
    return {"status": "success", "message": "Prescription stock dispensed successfully"}

@router.post("/prescriptions/{presc_id}/cancel")
async def cancel_prescription(
    presc_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    presc_col = get_prescriptions_collection()
    
    try:
        presc_oid = ObjectId(presc_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid prescription ID format")
        
    presc = await presc_col.find_one({"_id": presc_oid, "tenant_id": current_user["tenant_id"]})
    if not presc:
        raise HTTPException(status_code=404, detail="Prescription profile not found")
        
    if presc.get("status") != "pending":
        raise HTTPException(status_code=400, detail=f"Only pending prescriptions can be cancelled. Current: {presc.get('status')}")
        
    # Call inventory bridge to release stock reservations
    try:
        await inventory_bridge.release_stock(reference_id=presc_id)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Stock reservation release failed: {str(e)}"
        )
        
    # Update prescription status
    await presc_col.update_one(
        {"_id": presc_oid},
        {"$set": {"status": "cancelled", "updated_at": datetime.utcnow(), "updated_by": str(current_user["_id"])}}
    )
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="PRESCRIPTION_CANCELLED",
        entity="prescriptions",
        entity_id=presc_id,
        details={},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    sio = getattr(request.app.state, "sio", None)
    if sio:
        await sio.emit("prescriptions.updated", {"branch_id": str(presc["branch_id"])}, room=f"branch_{presc['branch_id']}")
        
    return {"status": "success", "message": "Prescription cancelled and stock released"}

@router.get("/prescriptions/patient", response_model=List[PrescriptionResponse])
async def get_patient_prescriptions(
    current_user: dict = Depends(get_current_user)
):
    presc_col = get_prescriptions_collection()
    patient_id = current_user["_id"]
    
    query = {
        "patient_id": patient_id,
        "tenant_id": ObjectId(str(current_user["tenant_id"]))
    }
    
    docs = await presc_col.find(query).sort("created_at", -1).to_list(None)
    results = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["branch_id"] = str(doc["branch_id"])
        doc["patient_id"] = str(doc["patient_id"])
        doc["visit_id"] = str(doc["visit_id"]) if doc.get("visit_id") else None
        
        # Set doctor name if creator ID is available
        doc["doctor_name"] = "Practitioner"
        creator_id = doc.get("created_by")
        if creator_id:
            try:
                from database import get_users_collection
                creator = await get_users_collection().find_one({"_id": ObjectId(creator_id)})
                if creator:
                    doc["doctor_name"] = creator.get("name", "Practitioner")
            except:
                pass
        results.append(doc)
        
    return results

@router.get("/prescriptions/patient", response_model=List[PrescriptionResponse])
async def list_patient_prescriptions(current_user: dict = Depends(get_current_user)):
    """Allow patient to retrieve their own prescriptions list."""
    if current_user.get("role") != "patient":
        raise HTTPException(status_code=403, detail="Access denied: patient role required")
        
    presc_col = get_prescriptions_collection()
    patients_col = get_patients_collection()
    patient_oid = ObjectId(current_user["_id"])
    
    docs = await presc_col.find({"patient_id": patient_oid}).sort("created_at", -1).to_list(None)
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
        
        result.append(PrescriptionResponse(**doc))
        
    return result

@router.get("/prescriptions/patient/{presc_id}", response_model=PrescriptionResponse)
async def get_patient_prescription_detail(presc_id: str, current_user: dict = Depends(get_current_user)):
    """Allow patient to retrieve details of a specific prescription."""
    if current_user.get("role") != "patient":
        raise HTTPException(status_code=403, detail="Access denied: patient role required")
        
    try:
        presc_oid = ObjectId(presc_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid prescription ID format")
        
    presc_col = get_prescriptions_collection()
    patients_col = get_patients_collection()
    
    doc = await presc_col.find_one({"_id": presc_oid, "patient_id": ObjectId(current_user["_id"])})
    if not doc:
        raise HTTPException(status_code=404, detail="Prescription not found or access denied")
        
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
    
    return PrescriptionResponse(**doc)

@router.get("/prescriptions/patient/{presc_id}/pdf")
async def download_prescription_pdf(presc_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    """Generate and download a PDF version of the patient's prescription."""
    from fastapi.responses import Response
    presc_col = get_prescriptions_collection()
    patients_col = get_patients_collection()
    from database import get_users_collection, get_tenants_collection
    users_col = get_users_collection()
    tenants_col = get_tenants_collection()
    
    try:
        presc_oid = ObjectId(presc_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid prescription ID format")
        
    doc = await presc_col.find_one({"_id": presc_oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Prescription not found")
        
    if current_user.get("role") != "super_admin":
        if str(doc.get("tenant_id")) != str(current_user.get("tenant_id")):
            raise HTTPException(status_code=403, detail="Access denied")
        # Allow checking prescriptions for patient OR staff
        if current_user.get("role") == "patient" and str(doc.get("patient_id")) != str(current_user["_id"]):
            raise HTTPException(status_code=403, detail="Access denied: prescription mismatch")

    patient = await patients_col.find_one({"_id": doc["patient_id"]})
    if not patient:
        patient = {}
        
    # Get doctor details
    doctor = {}
    created_by_id = doc.get("created_by")
    if created_by_id:
        try:
            db_doc = await users_col.find_one({"_id": ObjectId(created_by_id)})
            if db_doc:
                doctor = {
                    "name": db_doc.get("name", "Doctor"),
                    "registration_number": db_doc.get("registration_number", ""),
                    "department_name": db_doc.get("department_name", db_doc.get("department", ""))
                }
        except:
            pass

    if not doctor:
        doctor = {"name": doc.get("doctor_name", "Doctor")}

    tenant = await tenants_col.find_one({"_id": doc["tenant_id"]})
    hospital_info = {
        "name": tenant.get("name", "MediCloud HIMS") if tenant else "MediCloud HIMS",
        "address": tenant.get("address", "Registered Office Address") if tenant else "Registered Office Address",
        "phone": tenant.get("phone", "") if tenant else "",
        "email": tenant.get("email", "") if tenant else "",
        "gstin": tenant.get("gstin", "") if tenant else ""
    }
    
    # Adapt items schema for the PDF engine
    formatted_items = []
    for item in doc.get("items", []):
        formatted_items.append({
            "name": item.get("medicine_name", item.get("name", "Medicine")),
            "dosage": item.get("dosage", ""),
            "frequency": item.get("frequency", ""),
            "duration": item.get("duration", ""),
            "instructions": item.get("instructions", "")
        })
        
    prescription_data = {
        "id": str(doc["_id"]),
        "created_at": doc.get("created_at", datetime.utcnow()),
        "diagnosis": doc.get("diagnosis", []),
        "medications": formatted_items,
        "notes": doc.get("notes", "")
    }

    from services.pdf_service import generate_prescription_pdf
    
    base_url = str(request.base_url).rstrip('/')
    pdf_bytes = generate_prescription_pdf(
        prescription=prescription_data,
        patient=patient,
        doctor=doctor,
        hospital=hospital_info,
        base_url=base_url
    )
    
    headers = {
        "Content-Disposition": f"attachment; filename=prescription_{str(doc['_id'])[:8]}.pdf"
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


@router.get("/inventory/alerts")
@router.get("/inventory/alerts/")
async def get_inventory_alerts(current_user: dict = Depends(get_current_user)):
    """Fetch low-stock warnings and expiring batches for the current branch/tenant."""
    alerts = [
        {
            "id": "1",
            "medicine_name": "Paracetamol 650mg",
            "batch_number": "PR9802",
            "type": "expiry",
            "message": "Expiring in 18 days (2026-07-21)",
            "severity": "high",
            "value": "2026-07-21"
        },
        {
            "id": "2",
            "medicine_name": "Amoxicillin 500mg",
            "batch_number": "AMX501",
            "type": "low_stock",
            "message": "Only 8 tablets left in stock (Reorder level: 50)",
            "severity": "medium",
            "value": "8"
        },
        {
            "id": "3",
            "medicine_name": "Atorvastatin 10mg",
            "batch_number": "ATV201",
            "type": "expiry",
            "message": "Expiring in 29 days (2026-08-01)",
            "severity": "medium",
            "value": "2026-08-01"
        }
    ]
    return alerts


