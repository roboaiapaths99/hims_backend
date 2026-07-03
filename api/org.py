from fastapi import APIRouter, Depends, HTTPException, status, Request
from bson import ObjectId
from datetime import datetime
from typing import List, Optional

from database import get_tenants_collection, get_branches_collection, get_users_collection, get_roles_collection
from middleware.auth import require_role, require_permission, get_current_user
from middleware.audit import create_audit_log
from models.org import (
    TenantCreate, TenantResponse, TenantUpdate,
    BranchCreate, BranchResponse, BranchProfile,
    UserCreate, UserResponse, UserUpdate,
    BranchPaymentSettings, RoleBase, RoleCreate, RoleResponse
)
from middleware.auth import get_password_hash

router = APIRouter()

# ------------------------------------------------------------------
# TENANTS MANAGEMENT (Super Admin Only)
# ------------------------------------------------------------------
@router.post("/tenants", response_model=TenantResponse, dependencies=[Depends(require_role(["super_admin"]))])
async def create_tenant(payload: TenantCreate, request: Request, current_user: dict = Depends(get_current_user)):
    tenants_col = get_tenants_collection()
    
    # Check subdomain uniqueness
    existing = await tenants_col.find_one({"subdomain": payload.subdomain})
    if existing:
        raise HTTPException(status_code=400, detail="Subdomain already in use")
        
    tenant_doc = payload.dict()
    tenant_doc["created_at"] = datetime.utcnow()
    tenant_doc["updated_at"] = datetime.utcnow()
    
    res = await tenants_col.insert_one(tenant_doc)
    tenant_doc["id"] = str(res.inserted_id)
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="TENANT_CREATED",
        entity="tenants",
        entity_id=str(res.inserted_id),
        details={"name": payload.name, "subdomain": payload.subdomain},
        ip_address=request.client.host if request.client else None
    )
    return TenantResponse(**tenant_doc)

@router.get("/tenants", response_model=List[TenantResponse], dependencies=[Depends(require_role(["super_admin"]))])
async def list_tenants():
    tenants_col = get_tenants_collection()
    docs = await tenants_col.find({}).to_list(None)
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        result.append(TenantResponse(**doc))
    return result

# ------------------------------------------------------------------
# BRANCHES MANAGEMENT (Hospital Admin & Super Admin)
# ------------------------------------------------------------------
@router.post("/branches", response_model=BranchResponse, dependencies=[Depends(require_role(["super_admin", "hospital_admin"]))])
async def create_branch(payload: BranchCreate, request: Request, current_user: dict = Depends(get_current_user)):
    branches_col = get_branches_collection()
    
    # If not super_admin, verify user belongs to the specified tenant
    if current_user["role"] != "super_admin":
        if str(current_user["tenant_id"]) != payload.tenant_id:
            raise HTTPException(status_code=403, detail="Not authorized to create branch for this tenant")
            
    # Tenant SaaS branches quota check
    if current_user["role"] != "super_admin":
        from database import get_tenants_collection
        tenants_col = get_tenants_collection()
        tenant = await tenants_col.find_one({"_id": ObjectId(payload.tenant_id)})
        if tenant:
            max_branches = tenant.get("max_branches", 1)
            current_branches = await branches_col.count_documents({"tenant_id": ObjectId(payload.tenant_id)})
            if current_branches >= max_branches:
                raise HTTPException(
                    status_code=400,
                    detail=f"Branch limit reached ({current_branches}/{max_branches}). Please upgrade your SaaS subscription."
                )
            
    existing = await branches_col.find_one({
        "tenant_id": ObjectId(payload.tenant_id),
        "code": payload.code
    })
    if existing:
        raise HTTPException(status_code=400, detail="Branch code already exists for this tenant")
        
    branch_doc = {
        "name": payload.name,
        "code": payload.code,
        "address": payload.address,
        "contact_number": payload.contact_number,
        "tenant_id": ObjectId(payload.tenant_id),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    res = await branches_col.insert_one(branch_doc)
    branch_doc["id"] = str(res.inserted_id)
    branch_doc["tenant_id"] = str(branch_doc["tenant_id"])
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="BRANCH_CREATED",
        entity="branches",
        entity_id=str(res.inserted_id),
        details={"name": payload.name, "code": payload.code},
        ip_address=request.client.host if request.client else None,
        tenant_id=ObjectId(payload.tenant_id)
    )
    return BranchResponse(**branch_doc)

@router.get("/branches", response_model=List[BranchResponse])
async def list_branches(tenant_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    branches_col = get_branches_collection()
    
    query = {}
    if current_user["role"] != "super_admin":
        query["tenant_id"] = current_user["tenant_id"]
    elif tenant_id:
        query["tenant_id"] = ObjectId(tenant_id)
        
    docs = await branches_col.find(query).to_list(None)
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        result.append(BranchResponse(**doc))
    return result

# ------------------------------------------------------------------
# USERS & STAFF MANAGEMENT (Branch Admin and above)
# ------------------------------------------------------------------
@router.post("/users", response_model=UserResponse, dependencies=[Depends(require_role(["super_admin", "hospital_admin", "branch_admin"]))])
async def create_user(payload: UserCreate, request: Request, current_user: dict = Depends(get_current_user)):
    users_col = get_users_collection()
    
    # Check email uniqueness
    existing = await users_col.find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
        
    # Tenant SaaS staff quota check
    if current_user["role"] != "super_admin":
        from database import get_tenants_collection
        tenants_col = get_tenants_collection()
        tenant = await tenants_col.find_one({"_id": current_user["tenant_id"]})
        if tenant:
            max_staff = tenant.get("max_staff", 5)
            current_staff = await users_col.count_documents({
                "tenant_id": current_user["tenant_id"],
                "role": {"$ne": "patient"}
            })
            if current_staff >= max_staff:
                raise HTTPException(
                    status_code=400,
                    detail=f"Staff limit reached ({current_staff}/{max_staff}). Please upgrade your SaaS subscription."
                )
        
    # Set tenant scopes
    tenant_oid = None
    hospital_oid = None
    branch_oid = None
    
    if current_user["role"] == "super_admin":
        if not payload.tenant_id:
            raise HTTPException(status_code=400, detail="tenant_id is required for super admin creating users")
        tenant_oid = ObjectId(payload.tenant_id)
        hospital_oid = ObjectId(payload.hospital_id) if payload.hospital_id else None
        branch_oid = ObjectId(payload.branch_id) if payload.branch_id else None
    else:
        tenant_oid = current_user["tenant_id"]
        hospital_oid = current_user.get("hospital_id")
        if payload.branch_id:
            branch_oid = ObjectId(payload.branch_id)
            
    # Validate branch belongs to tenant
    if branch_oid:
        branches_col = get_branches_collection()
        branch = await branches_col.find_one({"_id": branch_oid, "tenant_id": tenant_oid})
        if not branch:
            raise HTTPException(status_code=400, detail="Invalid branch ID for this tenant")
            
    hashed_password = get_password_hash(payload.password)
    user_doc = {
        "name": payload.name,
        "email": payload.email,
        "password_hash": hashed_password,
        "role": payload.role,
        "is_active": payload.is_active,
        "tenant_id": tenant_oid,
        "hospital_id": hospital_oid,
        "branch_id": branch_oid,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    res = await users_col.insert_one(user_doc)
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="USER_CREATED",
        entity="users",
        entity_id=str(res.inserted_id),
        details={"name": payload.name, "email": payload.email, "role": payload.role},
        ip_address=request.client.host if request.client else None,
        tenant_id=tenant_oid,
        branch_id=branch_oid
    )
    
    user_doc["id"] = str(res.inserted_id)
    user_doc["tenant_id"] = str(user_doc["tenant_id"]) if user_doc["tenant_id"] else None
    user_doc["hospital_id"] = str(user_doc["hospital_id"]) if user_doc["hospital_id"] else None
    user_doc["branch_id"] = str(user_doc["branch_id"]) if user_doc["branch_id"] else None
    
    return UserResponse(**user_doc)

@router.get("/users", response_model=List[UserResponse])
async def list_users(branch_id: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    users_col = get_users_collection()
    
    query = {}
    if current_user["role"] != "super_admin":
        query["tenant_id"] = current_user["tenant_id"]
        # Branch Admins and below can only see users in their branch
        if current_user["role"] in ["branch_admin", "doctor", "nurse", "pharmacist", "billing_staff"]:
            query["branch_id"] = current_user["branch_id"]
            
    if branch_id:
        try:
            query["branch_id"] = ObjectId(branch_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid branch_id")
            
    docs = await users_col.find(query).to_list(None)
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"]) if doc.get("tenant_id") else None
        doc["hospital_id"] = str(doc["hospital_id"]) if doc.get("hospital_id") else None
        doc["branch_id"] = str(doc["branch_id"]) if doc.get("branch_id") else None
        result.append(UserResponse(**doc))
    return result

@router.put("/users/{user_id}", response_model=UserResponse, dependencies=[Depends(require_role(["super_admin", "hospital_admin", "branch_admin"]))])
async def update_user(user_id: str, payload: UserUpdate, request: Request, current_user: dict = Depends(get_current_user)):
    users_col = get_users_collection()
    try:
        user_oid = ObjectId(user_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid user ID format")
        
    user = await users_col.find_one({"_id": user_oid})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Guard authorization check
    if current_user["role"] != "super_admin":
        if user.get("tenant_id") != current_user["tenant_id"]:
            raise HTTPException(status_code=403, detail="Unauthorized access")
            
    update_data = payload.dict(exclude_unset=True)
    if "branch_id" in update_data and update_data["branch_id"]:
        update_data["branch_id"] = ObjectId(update_data["branch_id"])
        
    update_data["updated_at"] = datetime.utcnow()
    
    await users_col.update_one({"_id": user_oid}, {"$set": update_data})
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="USER_UPDATED",
        entity="users",
        entity_id=user_id,
        details=list(update_data.keys()),
        ip_address=request.client.host if request.client else None,
        tenant_id=user.get("tenant_id"),
        branch_id=user.get("branch_id")
    )
    
    updated = await users_col.find_one({"_id": user_oid})
    updated["id"] = str(updated["_id"])
    updated["tenant_id"] = str(updated["tenant_id"]) if updated.get("tenant_id") else None
    updated["hospital_id"] = str(updated["hospital_id"]) if updated.get("hospital_id") else None
    updated["branch_id"] = str(updated["branch_id"]) if updated.get("branch_id") else None
    
    return UserResponse(**updated)

# ------------------------------------------------------------------
# BRANCH PAYMENT CONFIGURATION SETTINGS
# ------------------------------------------------------------------
@router.get("/branches/settings/payments", response_model=BranchPaymentSettings)
async def get_branch_payment_settings(current_user: dict = Depends(get_current_user)):
    if not current_user.get("branch_id"):
        raise HTTPException(status_code=400, detail="User is not associated with any branch")
        
    branches_col = get_branches_collection()
    branch = await branches_col.find_one({"_id": current_user["branch_id"]})
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
        
    settings_dict = branch.get("payment_settings") or {}
    return BranchPaymentSettings(**settings_dict)

@router.put("/branches/settings/payments", response_model=BranchPaymentSettings, dependencies=[Depends(require_role(["super_admin", "hospital_admin", "branch_admin"]))])
async def update_branch_payment_settings(
    payload: BranchPaymentSettings,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    if not current_user.get("branch_id"):
        raise HTTPException(status_code=400, detail="User is not associated with any branch")
        
    branches_col = get_branches_collection()
    branch = await branches_col.find_one({"_id": current_user["branch_id"]})
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
        
    settings_dict = payload.dict()
    
    await branches_col.update_one(
        {"_id": current_user["branch_id"]},
        {"$set": {"payment_settings": settings_dict, "updated_at": datetime.utcnow()}}
    )
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="BRANCH_PAYMENT_SETTINGS_UPDATED",
        entity="branches",
        entity_id=str(current_user["branch_id"]),
        details={"payu_env": payload.payu_env, "cash_enabled": payload.cash_enabled},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user.get("tenant_id"),
        branch_id=current_user.get("branch_id")
    )
    
    return payload


@router.get("/branches/current/profile", response_model=BranchProfile)
async def get_branch_profile(current_user: dict = Depends(get_current_user)):
    if not current_user.get("branch_id"):
        raise HTTPException(status_code=400, detail="User is not associated with any branch")
        
    branches_col = get_branches_collection()
    branch = await branches_col.find_one({"_id": current_user["branch_id"]})
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
        
    return BranchProfile(
        name=branch.get("name", ""),
        code=branch.get("code", ""),
        address=branch.get("address", ""),
        contact_number=branch.get("contact_number", ""),
        gst_number=branch.get("gst_number"),
        logo_url=branch.get("logo_url"),
        letterhead_text=branch.get("letterhead_text")
    )


@router.put("/branches/current/profile", response_model=BranchProfile, dependencies=[Depends(require_role(["super_admin", "hospital_admin", "branch_admin"]))])
async def update_branch_profile(
    payload: BranchProfile,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    if not current_user.get("branch_id"):
        raise HTTPException(status_code=400, detail="User is not associated with any branch")
        
    branches_col = get_branches_collection()
    branch = await branches_col.find_one({"_id": current_user["branch_id"]})
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
        
    update_dict = payload.dict()
    update_dict["updated_at"] = datetime.utcnow()
    
    await branches_col.update_one(
        {"_id": current_user["branch_id"]},
        {"$set": update_dict}
    )
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="BRANCH_PROFILE_UPDATED",
        entity="branches",
        entity_id=str(current_user["branch_id"]),
        details={"name": payload.name, "gst_number": payload.gst_number},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user.get("tenant_id"),
        branch_id=current_user.get("branch_id")
    )
    
    return payload


# ------------------------------------------------------------------
# ROLE & PERMISSIONS MANAGEMENT (Hospital Admin & Branch Admin)
# ------------------------------------------------------------------
@router.get("/roles", response_model=List[RoleResponse])
async def list_roles(current_user: dict = Depends(get_current_user)):
    roles_col = get_roles_collection()
    
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User not associated with a tenant")
        
    cursor = roles_col.find({"tenant_id": tenant_id})
    roles = await cursor.to_list(None)
    
    res = []
    for r in roles:
        r["id"] = str(r["_id"])
        r["tenant_id"] = str(r["tenant_id"])
        res.append(RoleResponse(**r))
    return res


@router.post("/roles", response_model=RoleResponse, dependencies=[Depends(require_role(["super_admin", "hospital_admin"]))])
async def create_role(payload: RoleBase, request: Request, current_user: dict = Depends(get_current_user)):
    roles_col = get_roles_collection()
    
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User not associated with a tenant")
        
    # Check if duplicate name
    existing = await roles_col.find_one({"tenant_id": tenant_id, "name": payload.name})
    if existing:
        raise HTTPException(status_code=400, detail="Role name already exists")
        
    doc = payload.dict()
    doc["tenant_id"] = tenant_id
    doc["created_at"] = datetime.utcnow()
    
    res = await roles_col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="ROLE_CREATED",
        entity="roles",
        entity_id=doc["id"],
        details={"name": payload.name, "permissions": payload.permissions},
        ip_address=request.client.host if request.client else None,
        tenant_id=tenant_id,
        branch_id=current_user.get("branch_id")
    )
    
    return RoleResponse(**doc)


@router.put("/roles/{role_id}", response_model=RoleResponse, dependencies=[Depends(require_role(["super_admin", "hospital_admin"]))])
async def update_role(
    role_id: str,
    payload: RoleBase,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    roles_col = get_roles_collection()
    
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User not associated with a tenant")
        
    try:
        role_oid = ObjectId(role_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid role ID format")
        
    existing = await roles_col.find_one({"_id": role_oid, "tenant_id": tenant_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Role not found")
        
    await roles_col.update_one(
        {"_id": role_oid, "tenant_id": tenant_id},
        {"$set": {"name": payload.name, "permissions": payload.permissions, "updated_at": datetime.utcnow()}}
    )
    
    updated_doc = {
        "id": role_id,
        "name": payload.name,
        "permissions": payload.permissions,
        "tenant_id": str(tenant_id)
    }
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="ROLE_UPDATED",
        entity="roles",
        entity_id=role_id,
        details={"name": payload.name, "permissions": payload.permissions},
        ip_address=request.client.host if request.client else None,
        tenant_id=tenant_id,
        branch_id=current_user.get("branch_id")
    )
    
    return RoleResponse(**updated_doc)


@router.delete("/roles/{role_id}", dependencies=[Depends(require_role(["super_admin", "hospital_admin"]))])
async def delete_role(
    role_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    roles_col = get_roles_collection()
    
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User not associated with a tenant")
        
    try:
        role_oid = ObjectId(role_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid role ID format")
        
    existing = await roles_col.find_one({"_id": role_oid, "tenant_id": tenant_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Role not found")
        
    # Prevent deleting built-in roles
    if existing.get("name") in ["hospital_admin", "branch_admin", "doctor", "nurse", "pharmacist", "lab_technician", "billing_staff", "receptionist"]:
        raise HTTPException(status_code=400, detail="Cannot delete built-in system role profiles")
        
    await roles_col.delete_one({"_id": role_oid, "tenant_id": tenant_id})
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="ROLE_DELETED",
        entity="roles",
        entity_id=role_id,
        details={"name": existing.get("name")},
        ip_address=request.client.host if request.client else None,
        tenant_id=tenant_id,
        branch_id=current_user.get("branch_id")
    )
    
    return {"success": True, "message": "Role successfully deleted"}
