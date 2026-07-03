from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from bson import ObjectId
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

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
        
    presc = await presc_col.find_one({"_id": presc_oid, "tenant_id": current_user["tenant_id"]})
    if not presc:
        raise HTTPException(status_code=404, detail="Prescription profile not found")
        
    if presc.get("status") != "pending":
        raise HTTPException(status_code=400, detail=f"Prescription cannot be dispensed. Current status: {presc.get('status')}")
        
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
        raise HTTPException(
            status_code=400,
            detail=f"Pharmacy stock deduction failed: {str(e)}"
        )
        
    # Update prescription status
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

