from fastapi import APIRouter, Depends, HTTPException, status, Request
from bson import ObjectId
from datetime import datetime
from typing import List, Optional

from database import (
    get_departments_collection, get_pricing_items_collection,
    get_lab_test_master_collection, get_rooms_collection,
    get_templates_collection
)
from middleware.auth import (
    require_role, get_current_user, get_tenant_filter, 
    get_branch_filter, inject_audit_fields
)
from middleware.audit import create_audit_log
from models.config import (
    DepartmentCreate, DepartmentResponse,
    PricingItemCreate, PricingItemResponse,
    LabTestMasterCreate, LabTestMasterResponse,
    RoomCreate, RoomResponse,
    TemplateCreate, TemplateResponse
)

router = APIRouter()

# ------------------------------------------------------------------
# DEPARTMENTS CRUD
# ------------------------------------------------------------------
@router.post("/departments", response_model=DepartmentResponse, dependencies=[Depends(require_role(["super_admin", "hospital_admin", "branch_admin"]))])
async def create_department(payload: DepartmentCreate, request: Request, current_user: dict = Depends(get_current_user)):
    col = get_departments_collection()
    doc = payload.dict()
    inject_audit_fields(current_user, doc)
    
    res = await col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    if doc.get("branch_id"):
        doc["branch_id"] = str(doc["branch_id"])
        
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="DEPARTMENT_CREATED",
        entity="departments",
        entity_id=doc["id"],
        details={"name": payload.name, "code": payload.code},
        ip_address=request.client.host if request.client else None,
        tenant_id=ObjectId(doc["tenant_id"]),
        branch_id=ObjectId(doc["branch_id"]) if doc.get("branch_id") else None
    )
    return DepartmentResponse(**doc)

@router.get("/departments", response_model=List[DepartmentResponse])
async def list_departments(current_user: dict = Depends(get_current_user)):
    col = get_departments_collection()
    query = get_tenant_filter(current_user)
    
    docs = await col.find(query).to_list(None)
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        if doc.get("branch_id"):
            doc["branch_id"] = str(doc["branch_id"])
        result.append(DepartmentResponse(**doc))
    return result

# ------------------------------------------------------------------
# PRICING ITEMS CRUD
# ------------------------------------------------------------------
@router.post("/pricing-items", response_model=PricingItemResponse, dependencies=[Depends(require_role(["super_admin", "hospital_admin", "branch_admin"]))])
async def create_pricing_item(payload: PricingItemCreate, request: Request, current_user: dict = Depends(get_current_user)):
    col = get_pricing_items_collection()
    doc = payload.dict()
    inject_audit_fields(current_user, doc)
    
    res = await col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    if doc.get("branch_id"):
        doc["branch_id"] = str(doc["branch_id"])
        
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="PRICING_ITEM_CREATED",
        entity="pricing_items",
        entity_id=doc["id"],
        details={"name": payload.name, "type": payload.item_type, "price": payload.price},
        ip_address=request.client.host if request.client else None,
        tenant_id=ObjectId(doc["tenant_id"]),
        branch_id=ObjectId(doc["branch_id"]) if doc.get("branch_id") else None
    )
    return PricingItemResponse(**doc)

@router.get("/pricing-items", response_model=List[PricingItemResponse])
async def list_pricing_items(item_type: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    col = get_pricing_items_collection()
    query = get_branch_filter(current_user)
    if item_type:
        query["item_type"] = item_type
        
    docs = await col.find(query).to_list(None)
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        if doc.get("branch_id"):
            doc["branch_id"] = str(doc["branch_id"])
        result.append(PricingItemResponse(**doc))
    return result

# ------------------------------------------------------------------
# LAB TESTS CRUD
# ------------------------------------------------------------------
@router.post("/lab-tests", response_model=LabTestMasterResponse, dependencies=[Depends(require_role(["super_admin", "hospital_admin", "branch_admin"]))])
async def create_lab_test(payload: LabTestMasterCreate, request: Request, current_user: dict = Depends(get_current_user)):
    col = get_lab_test_master_collection()
    doc = payload.dict()
    inject_audit_fields(current_user, doc)
    
    res = await col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    if doc.get("branch_id"):
        doc["branch_id"] = str(doc["branch_id"])
        
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="LAB_TEST_MASTER_CREATED",
        entity="lab_test_master",
        entity_id=doc["id"],
        details={"test_name": payload.test_name, "price": payload.price},
        ip_address=request.client.host if request.client else None,
        tenant_id=ObjectId(doc["tenant_id"]),
        branch_id=ObjectId(doc["branch_id"]) if doc.get("branch_id") else None
    )
    return LabTestMasterResponse(**doc)

@router.get("/lab-tests", response_model=List[LabTestMasterResponse])
async def list_lab_tests(current_user: dict = Depends(get_current_user)):
    col = get_lab_test_master_collection()
    query = get_tenant_filter(current_user)
    
    docs = await col.find(query).to_list(None)
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        if doc.get("branch_id"):
            doc["branch_id"] = str(doc["branch_id"])
        result.append(LabTestMasterResponse(**doc))
    return result

# ------------------------------------------------------------------
# ROOMS & OT ROOMS CRUD
# ------------------------------------------------------------------
@router.post("/rooms", response_model=RoomResponse, dependencies=[Depends(require_role(["super_admin", "hospital_admin", "branch_admin"]))])
async def create_room(payload: RoomCreate, request: Request, current_user: dict = Depends(get_current_user)):
    col = get_rooms_collection()
    doc = payload.dict()
    inject_audit_fields(current_user, doc)
    
    # Require branch_id explicitly for rooms
    if "branch_id" not in doc or not doc["branch_id"]:
        raise HTTPException(status_code=400, detail="branch_id is required for room configuration")
        
    res = await col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="ROOM_CREATED",
        entity="rooms",
        entity_id=doc["id"],
        details={"room_number": payload.room_number, "type": payload.room_type},
        ip_address=request.client.host if request.client else None,
        tenant_id=ObjectId(doc["tenant_id"]),
        branch_id=ObjectId(doc["branch_id"])
    )
    return RoomResponse(**doc)

@router.get("/rooms", response_model=List[RoomResponse])
async def list_rooms(current_user: dict = Depends(get_current_user)):
    col = get_rooms_collection()
    query = get_branch_filter(current_user)
    
    docs = await col.find(query).to_list(None)
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["branch_id"] = str(doc["branch_id"])
        result.append(RoomResponse(**doc))
    return result

# ------------------------------------------------------------------
# DOCUMENT TEMPLATES CRUD
# ------------------------------------------------------------------
@router.post("/templates", response_model=TemplateResponse, dependencies=[Depends(require_role(["super_admin", "hospital_admin", "branch_admin"]))])
async def create_template(payload: TemplateCreate, request: Request, current_user: dict = Depends(get_current_user)):
    col = get_templates_collection()
    doc = payload.dict()
    inject_audit_fields(current_user, doc)
    
    res = await col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    if doc.get("branch_id"):
        doc["branch_id"] = str(doc["branch_id"])
        
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="TEMPLATE_CREATED",
        entity="templates",
        entity_id=doc["id"],
        details={"name": payload.name, "type": payload.template_type},
        ip_address=request.client.host if request.client else None,
        tenant_id=ObjectId(doc["tenant_id"]),
        branch_id=ObjectId(doc["branch_id"]) if doc.get("branch_id") else None
    )
    return TemplateResponse(**doc)

@router.get("/templates", response_model=List[TemplateResponse])
async def list_templates(template_type: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    col = get_templates_collection()
    query = get_tenant_filter(current_user)
    if template_type:
        query["template_type"] = template_type
        
    docs = await col.find(query).to_list(None)
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        if doc.get("branch_id"):
            doc["branch_id"] = str(doc["branch_id"])
        result.append(TemplateResponse(**doc))
    return result
