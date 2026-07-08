from fastapi import APIRouter, Depends, HTTPException, status, Request
from bson import ObjectId
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

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
async def list_departments(tenant_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    col = get_departments_collection()
    query = get_tenant_filter(current_user)
    
    if current_user.get("role") == "patient" and tenant_id:
        try:
            query = {"tenant_id": ObjectId(tenant_id)}
        except:
            raise HTTPException(status_code=400, detail="Invalid tenant_id format")
            
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

# ------------------------------------------------------------------
# PAYMENT SETTINGS WITH SECRETS VAULT
# ------------------------------------------------------------------
class PaymentSettingsUpdateRequest(BaseModel):
    payu_enabled: bool = False
    payu_merchant_key: Optional[str] = None
    payu_merchant_salt: Optional[str] = None
    payu_env: str = "test"
    
    razorpay_enabled: bool = False
    razorpay_key_id: Optional[str] = None
    razorpay_key_secret: Optional[str] = None
    
    stripe_enabled: bool = False
    stripe_publishable_key: Optional[str] = None
    stripe_secret_key: Optional[str] = None
    
    upi_enabled: bool = False
    upi_vpa: Optional[str] = None
    upi_merchant_name: Optional[str] = None
    
    cash_enabled: bool = True
    card_enabled: bool = True

@router.get("/payment-settings", dependencies=[Depends(require_role(["super_admin", "hospital_admin", "branch_admin"]))])
async def get_payment_settings(current_user: dict = Depends(get_current_user)):
    branch_id = current_user.get("branch_id")
    if not branch_id:
        raise HTTPException(status_code=400, detail="User must belong to a branch")
        
    from database import get_branches_collection
    branches_col = get_branches_collection()
    branch = await branches_col.find_one({"_id": ObjectId(branch_id)})
    if not branch:
        raise HTTPException(status_code=404, detail="Branch record not found")
        
    pay_settings = branch.get("payment_settings") or {}
    
    from services.secrets_vault import get_branch_secrets
    branch_secrets = await get_branch_secrets(branch_id)
    
    return {
        "payu_enabled": pay_settings.get("payu_enabled", False),
        "payu_merchant_key": pay_settings.get("payu_merchant_key", ""),
        "payu_merchant_salt": "***" if branch_secrets.get("payu_merchant_salt") else "",
        "payu_env": pay_settings.get("payu_env", "test"),
        
        "razorpay_enabled": pay_settings.get("razorpay_enabled", False),
        "razorpay_key_id": pay_settings.get("razorpay_key_id", ""),
        "razorpay_key_secret": "***" if branch_secrets.get("razorpay_key_secret") else "",
        
        "stripe_enabled": pay_settings.get("stripe_enabled", False),
        "stripe_publishable_key": pay_settings.get("stripe_publishable_key", ""),
        "stripe_secret_key": "***" if branch_secrets.get("stripe_secret_key") else "",
        
        "upi_enabled": pay_settings.get("upi_enabled", False),
        "upi_vpa": pay_settings.get("upi_vpa", ""),
        "upi_merchant_name": pay_settings.get("upi_merchant_name", ""),
        
        "cash_enabled": pay_settings.get("cash_enabled", True),
        "card_enabled": pay_settings.get("card_enabled", True)
    }

@router.put("/payment-settings", dependencies=[Depends(require_role(["super_admin", "hospital_admin", "branch_admin"]))])
async def update_payment_settings(
    payload: PaymentSettingsUpdateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    branch_id = current_user.get("branch_id")
    tenant_id = current_user.get("tenant_id")
    if not branch_id or not tenant_id:
        raise HTTPException(status_code=400, detail="User must belong to a tenant and branch")
        
    from database import get_branches_collection
    branches_col = get_branches_collection()
    branch = await branches_col.find_one({"_id": ObjectId(branch_id)})
    if not branch:
        raise HTTPException(status_code=404, detail="Branch record not found")
        
    public_settings = {
        "payu_enabled": payload.payu_enabled,
        "payu_merchant_key": payload.payu_merchant_key or "",
        "payu_env": payload.payu_env,
        "razorpay_enabled": payload.razorpay_enabled,
        "razorpay_key_id": payload.razorpay_key_id or "",
        "stripe_enabled": payload.stripe_enabled,
        "stripe_publishable_key": payload.stripe_publishable_key or "",
        "upi_enabled": payload.upi_enabled,
        "upi_vpa": payload.upi_vpa or "",
        "upi_merchant_name": payload.upi_merchant_name or "",
        "cash_enabled": payload.cash_enabled,
        "card_enabled": payload.card_enabled
    }
    
    await branches_col.update_one(
        {"_id": ObjectId(branch_id)},
        {"$set": {"payment_settings": public_settings, "updated_at": datetime.utcnow()}}
    )
    
    secrets_to_save = {}
    if payload.payu_merchant_salt and payload.payu_merchant_salt != "***":
        secrets_to_save["payu_merchant_salt"] = payload.payu_merchant_salt
    if payload.razorpay_key_secret and payload.razorpay_key_secret != "***":
        secrets_to_save["razorpay_key_secret"] = payload.razorpay_key_secret
    if payload.stripe_secret_key and payload.stripe_secret_key != "***":
        secrets_to_save["stripe_secret_key"] = payload.stripe_secret_key
        
    if secrets_to_save:
        from services.secrets_vault import save_branch_secrets
        await save_branch_secrets(branch_id, tenant_id, secrets_to_save)
        
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="PAYMENT_SETTINGS_UPDATED",
        entity="branches",
        entity_id=str(branch_id),
        details={"payu_enabled": payload.payu_enabled, "razorpay_enabled": payload.razorpay_enabled, "stripe_enabled": payload.stripe_enabled, "upi_enabled": payload.upi_enabled},
        ip_address=request.client.host if request.client else None,
        tenant_id=ObjectId(tenant_id),
        branch_id=ObjectId(branch_id)
    )
    
    return {"status": "success", "message": "Payment settings updated successfully"}
