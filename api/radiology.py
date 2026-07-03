from fastapi import APIRouter, Depends, HTTPException, status, Request
from bson import ObjectId
from datetime import datetime
from typing import List, Optional

from database import (
    get_db,
    get_radiology_orders_collection,
    get_radiology_results_collection,
    get_patients_collection,
    get_users_collection
)
from middleware.auth import (
    get_current_user,
    get_tenant_filter,
    get_branch_filter,
    inject_audit_fields
)
from middleware.audit import create_audit_log
from models.radiology import (
    RadiologyOrderCreate,
    RadiologyOrderResponse,
    RadiologyResultCreate,
    RadiologyResultResponse
)

router = APIRouter()

@router.post("/orders", response_model=RadiologyOrderResponse)
async def create_radiology_order(
    payload: RadiologyOrderCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    orders_col = get_radiology_orders_collection()
    patients_col = get_patients_collection()
    
    try:
        patient_oid = ObjectId(payload.patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient_id format")
        
    patient = await patients_col.find_one({"_id": patient_oid, "tenant_id": current_user["tenant_id"]})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
        
    if payload.modality.upper() not in ["XRAY", "MRI", "CT", "US"]:
        raise HTTPException(status_code=400, detail="Invalid modality type. Supported: XRAY, MRI, CT, US")
        
    doc = payload.dict()
    doc["patient_id"] = patient_oid
    doc["modality"] = payload.modality.upper()
    if payload.visit_id:
        try:
            doc["visit_id"] = ObjectId(payload.visit_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid visit_id format")
            
    doc["status"] = "ordered"
    inject_audit_fields(current_user, doc)
    
    res = await orders_col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    doc["patient_id"] = str(doc["patient_id"])
    if doc.get("visit_id"):
        doc["visit_id"] = str(doc["visit_id"])
        
    doc["patient_name"] = f"{patient.get('first_name', '')} {patient.get('last_name', '')}"
    doc["patient_mrn"] = patient.get("mrn", "")
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="RADIOLOGY_ORDER_CREATED",
        entity="radiology_orders",
        entity_id=doc["id"],
        details={"test_name": payload.test_name, "modality": doc["modality"]},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    return RadiologyOrderResponse(**doc)

@router.get("/orders", response_model=List[RadiologyOrderResponse])
async def list_radiology_orders(
    status_filter: Optional[str] = None,
    modality_filter: Optional[str] = None,
    patient_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    orders_col = get_radiology_orders_collection()
    patients_col = get_patients_collection()
    
    query = get_branch_filter(current_user)
    if status_filter:
        query["status"] = status_filter
    if modality_filter:
        query["modality"] = modality_filter.upper()
    if patient_id:
        try:
            query["patient_id"] = ObjectId(patient_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid patient_id format")
            
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
            doc["patient_mrn"] = patient.get("mrn", "")
        else:
            doc["patient_name"] = "Unknown Patient"
            doc["patient_mrn"] = "N/A"
            
        doc["patient_id"] = str(doc["patient_id"])
        if doc.get("visit_id"):
            doc["visit_id"] = str(doc["visit_id"])
            
        result.append(RadiologyOrderResponse(**doc))
    return result

@router.post("/orders/{id}/perform", response_model=RadiologyOrderResponse)
async def perform_radiology_order(
    id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    orders_col = get_radiology_orders_collection()
    patients_col = get_patients_collection()
    
    try:
        order_oid = ObjectId(id)
    except:
        raise HTTPException(status_code=400, detail="Invalid order ID format")
        
    order = await orders_col.find_one({"_id": order_oid, "tenant_id": current_user["tenant_id"]})
    if not order:
        raise HTTPException(status_code=404, detail="Radiology order not found")
        
    now = datetime.utcnow()
    await orders_col.update_one(
        {"_id": order_oid},
        {"$set": {
            "status": "performed",
            "updated_at": now,
            "updated_by": str(current_user["_id"])
        }}
    )
    
    patient = await patients_col.find_one({"_id": order["patient_id"]})
    
    order["status"] = "performed"
    order["updated_at"] = now
    order["updated_by"] = str(current_user["_id"])
    order["id"] = str(order["_id"])
    order["tenant_id"] = str(order["tenant_id"])
    order["branch_id"] = str(order["branch_id"])
    order["patient_id"] = str(order["patient_id"])
    if order.get("visit_id"):
        order["visit_id"] = str(order["visit_id"])
        
    order["patient_name"] = f"{patient.get('first_name', '')} {patient.get('last_name', '')}" if patient else "Unknown Patient"
    order["patient_mrn"] = patient.get("mrn", "") if patient else "N/A"
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="RADIOLOGY_ORDER_PERFORMED",
        entity="radiology_orders",
        entity_id=id,
        details={"test_name": order["test_name"], "modality": order["modality"]},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    return RadiologyOrderResponse(**order)

@router.post("/orders/{id}/results", response_model=RadiologyResultResponse)
async def submit_radiology_results(
    id: str,
    payload: RadiologyResultCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    orders_col = get_radiology_orders_collection()
    results_col = get_radiology_results_collection()
    users_col = get_users_collection()
    
    try:
        order_oid = ObjectId(id)
    except:
        raise HTTPException(status_code=400, detail="Invalid order ID format")
        
    order = await orders_col.find_one({"_id": order_oid, "tenant_id": current_user["tenant_id"]})
    if not order:
        raise HTTPException(status_code=404, detail="Radiology order record not found")
        
    # Check if duplicate result
    existing = await results_col.find_one({"order_id": order_oid})
    if existing:
        raise HTTPException(status_code=400, detail="Results already reported for this radiology order")
        
    result_doc = payload.dict()
    result_doc["order_id"] = order_oid
    result_doc["reported_by"] = str(current_user["_id"])
    inject_audit_fields(current_user, result_doc)
    
    res = await results_col.insert_one(result_doc)
    
    # Transition status of order to reported
    await orders_col.update_one(
        {"_id": order_oid},
        {"$set": {
            "status": "reported",
            "updated_at": datetime.utcnow(),
            "updated_by": str(current_user["_id"])
        }}
    )
    
    result_doc["id"] = str(res.inserted_id)
    result_doc["tenant_id"] = str(result_doc["tenant_id"])
    result_doc["branch_id"] = str(result_doc["branch_id"])
    result_doc["order_id"] = str(result_doc["order_id"])
    result_doc["reported_by_name"] = current_user["name"]
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="RADIOLOGY_REPORT_SUBMITTED",
        entity="radiology_results",
        entity_id=result_doc["id"],
        details={"order_id": id, "impression": payload.impression},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    return RadiologyResultResponse(**result_doc)

@router.get("/orders/{id}/results", response_model=RadiologyResultResponse)
async def get_radiology_results(
    id: str,
    current_user: dict = Depends(get_current_user)
):
    orders_col = get_radiology_orders_collection()
    results_col = get_radiology_results_collection()
    users_col = get_users_collection()
    
    try:
        order_oid = ObjectId(id)
    except:
        raise HTTPException(status_code=400, detail="Invalid order ID format")
        
    order = await orders_col.find_one({"_id": order_oid, "tenant_id": current_user["tenant_id"]})
    if not order:
        raise HTTPException(status_code=404, detail="Radiology order not found")
        
    res_doc = await results_col.find_one({"order_id": order_oid, "tenant_id": current_user["tenant_id"]})
    if not res_doc:
        raise HTTPException(status_code=404, detail="No diagnostic results recorded for this order yet")
        
    res_doc["id"] = str(res_doc["_id"])
    res_doc["tenant_id"] = str(res_doc["tenant_id"])
    res_doc["branch_id"] = str(res_doc["branch_id"])
    res_doc["order_id"] = str(res_doc["order_id"])
    
    reporter = await users_col.find_one({"_id": ObjectId(res_doc["reported_by"])})
    res_doc["reported_by_name"] = reporter.get("name") if reporter else "Staff Radiologist"
    
    return RadiologyResultResponse(**res_doc)
