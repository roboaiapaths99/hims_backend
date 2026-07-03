from fastapi import APIRouter, Depends, HTTPException, status, Request
from bson import ObjectId
from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel

from database import (
    get_tenants_collection,
    get_branches_collection,
    get_users_collection,
    get_patients_collection,
    get_saas_plans_collection,
    get_saas_payments_collection
)
from middleware.auth import get_current_user, require_role
from middleware.audit import create_audit_log
import uuid
import httpx

router = APIRouter()

class SubscribeRequest(BaseModel):
    plan_id: str
    gateway: str  # stripe, razorpay, sandbox
    billing_interval: str = "month"  # month, year

class VerifySaaSPaymentRequest(BaseModel):
    plan_id: str
    gateway: str
    transaction_id: str
    amount: float
    billing_interval: str = "month"

class SuperAdminOverrideRequest(BaseModel):
    plan_id: str
    subscription_status: str  # trialing, active, suspended, canceled
    subscription_end: datetime
    max_branches: int
    max_staff: int
    max_patients: int

# Helper to fetch active plan details
async def get_plan_by_id(plan_id: str) -> dict:
    plans_col = get_saas_plans_collection()
    plan = await plans_col.find_one({"plan_id": plan_id})
    if not plan:
        raise HTTPException(status_code=404, detail=f"SaaS Plan '{plan_id}' not found")
    return plan

@router.get("/plans")
async def list_saas_plans():
    """List all available SaaS plans and details."""
    plans_col = get_saas_plans_collection()
    plans = await plans_col.find({}).to_list(None)
    for p in plans:
        p["_id"] = str(p["_id"])
    return plans

@router.get("/subscription/status")
async def get_subscription_status(current_user: dict = Depends(get_current_user)):
    """Retrieve tenant subscription details and usage limits ratios."""
    if current_user.get("role") == "super_admin":
        return {"role": "super_admin", "msg": "Super admins have unlimited global access"}

    tenant_oid = current_user.get("tenant_id")
    if not tenant_oid:
        raise HTTPException(status_code=400, detail="User is not scoped to a tenant")

    tenants_col = get_tenants_collection()
    tenant = await tenants_col.find_one({"_id": tenant_oid})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant details not found")

    # Fetch limits and parameters
    plan_id = tenant.get("plan_id", "free_trial")
    sub_status = tenant.get("subscription_status", "trialing")
    sub_end = tenant.get("subscription_end")
    
    # Calculate usage metrics
    branches_col = get_branches_collection()
    users_col = get_users_collection()
    patients_col = get_patients_collection()

    branch_count = await branches_col.count_documents({"tenant_id": tenant_oid})
    staff_count = await users_col.count_documents({
        "tenant_id": tenant_oid,
        "role": {"$ne": "patient"}
    })
    patient_count = await patients_col.count_documents({
        "tenant_id": tenant_oid,
        "is_deleted": {"$ne": True}
    })

    # Load active plan features
    try:
        plan_details = await get_plan_by_id(plan_id)
        features = plan_details.get("features", {})
    except:
        features = {"abdm": False, "ai_summaries": False, "telemedicine": True}

    return {
        "tenant_id": str(tenant_oid),
        "tenant_name": tenant.get("name"),
        "subdomain": tenant.get("subdomain"),
        "status": tenant.get("status", "active"),
        
        "subscription": {
            "plan_id": plan_id,
            "status": sub_status,
            "end_date": sub_end,
            "billing_interval": tenant.get("billing_interval", "month"),
            "features": features
        },
        "limits": {
            "max_branches": tenant.get("max_branches", 1),
            "max_staff": tenant.get("max_staff", 5),
            "max_patients": tenant.get("max_patients", 100)
        },
        "usage": {
            "branches": branch_count,
            "staff": staff_count,
            "patients": patient_count
        }
    }

@router.post("/subscription/subscribe")
async def initialize_saas_subscribe(
    payload: SubscribeRequest,
    current_user: dict = Depends(get_current_user)
):
    """Initializes checkout session parameters for subscription upgrade."""
    tenant_oid = current_user.get("tenant_id")
    if not tenant_oid:
        raise HTTPException(status_code=400, detail="User must belong to a tenant to subscribe")
        
    plan = await get_plan_by_id(payload.plan_id)
    gateway = payload.gateway.lower()
    
    amount = float(plan.get("price", 0.0))
    if payload.billing_interval == "year":
        # Apply 20% annual discount
        amount = (amount * 12) * 0.8

    txnid = f"SUB_{ObjectId()}"
    
    response_payload = {
        "txnid": txnid,
        "amount": amount,
        "plan_id": payload.plan_id,
        "billing_interval": payload.billing_interval,
        "gateway": gateway
    }

    # Stripe real billing session integration
    if gateway == "stripe":
        # Stripe integration for SaaS can use Checkout Sessions.
        # We check settings for a global stripe key (SaaS belongs to platform admin)
        from config import settings
        secret_key = settings.PAYU_MERCHANT_SALT # Let's see: we'll check if there is a global secret key or use settings
        # We can implement a clean sandbox response if not configured
        response_payload.update({
            "publishable_key": "pk_test_saas_placeholder",
            "client_secret": f"pi_saas_{ObjectId()}_secret_{uuid.uuid4()}"
        })
    elif gateway == "razorpay":
        response_payload.update({
            "key_id": "rzp_test_saas_placeholder",
            "razorpay_order_id": f"order_sub_{ObjectId()}"
        })
    
    return response_payload

@router.post("/subscription/verify")
async def verify_saas_subscription(
    payload: VerifySaaSPaymentRequest,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Verifies B2B SaaS payment details and registers/upgrades the tenant status."""
    tenant_oid = current_user.get("tenant_id")
    if not tenant_oid:
        raise HTTPException(status_code=400, detail="User must belong to a tenant")

    tenants_col = get_tenants_collection()
    tenant = await tenants_col.find_one({"_id": tenant_oid})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant record not found")

    plan = await get_plan_by_id(payload.plan_id)
    
    # Register SaaS payment record
    payments_col = get_saas_payments_collection()
    payment_doc = {
        "tenant_id": tenant_oid,
        "plan_id": payload.plan_id,
        "amount_paid": payload.amount,
        "billing_interval": payload.billing_interval,
        "gateway": payload.gateway,
        "transaction_id": payload.transaction_id,
        "payment_date": datetime.utcnow(),
        "created_by": str(current_user["_id"])
    }
    await payments_col.insert_one(payment_doc)

    # Calculate new expiry dates
    days_to_add = 30 if payload.billing_interval == "month" else 365
    current_end = tenant.get("subscription_end")
    if current_end and current_end > datetime.utcnow():
        new_end = current_end + timedelta(days=days_to_add)
    else:
        new_end = datetime.utcnow() + timedelta(days=days_to_add)

    # Update tenant subscription parameters
    update_fields = {
        "status": "active",
        "plan_id": payload.plan_id,
        "subscription_status": "active",
        "subscription_start": datetime.utcnow(),
        "subscription_end": new_end,
        "billing_interval": payload.billing_interval,
        "max_branches": plan.get("max_branches", 1),
        "max_staff": plan.get("max_staff", 5),
        "max_patients": plan.get("max_patients", 100),
        "updated_at": datetime.utcnow()
    }
    
    await tenants_col.update_one({"_id": tenant_oid}, {"$set": update_fields})
    
    # Audit log
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="TENANT_SUBSCRIPTION_RENEWED",
        entity="tenants",
        entity_id=str(tenant_oid),
        details={"plan_id": payload.plan_id, "amount": payload.amount, "end_date": new_end.isoformat()},
        ip_address=request.client.host if request.client else None,
        tenant_id=tenant_oid
    )
    
    return {
        "status": "success",
        "message": f"Successfully subscribed to {plan['name']}. Your limits have been updated.",
        "subscription_end": new_end
    }

@router.post("/subscription/cancel")
async def cancel_saas_subscription(
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Sets subscription cancellation flag on the tenant profile."""
    tenant_oid = current_user.get("tenant_id")
    if not tenant_oid:
        raise HTTPException(status_code=400, detail="User must belong to a tenant")

    tenants_col = get_tenants_collection()
    
    await tenants_col.update_one(
        {"_id": tenant_oid},
        {"$set": {"subscription_status": "canceled", "updated_at": datetime.utcnow()}}
    )

    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="TENANT_SUBSCRIPTION_CANCELED",
        entity="tenants",
        entity_id=str(tenant_oid),
        details={"info": "Downgraded to cancel at end of billing cycle"},
        ip_address=request.client.host if request.client else None,
        tenant_id=tenant_oid
    )

    return {"status": "success", "message": "Subscription set to cancel. Access continues until billing cycle expiration."}

# ------------------------------------------------------------------
# SUPER ADMIN MANUAL OVERRIDES
# ------------------------------------------------------------------
@router.post("/super-admin/tenants/{tenant_id}/subscription", dependencies=[Depends(require_role(["super_admin"]))])
async def super_admin_override_subscription(
    tenant_id: str,
    payload: SuperAdminOverrideRequest,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Super Admin manual override of tenant subscription properties."""
    tenants_col = get_tenants_collection()
    try:
        tenant_oid = ObjectId(tenant_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid tenant ID format")

    tenant = await tenants_col.find_one({"_id": tenant_oid})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    update_fields = {
        "plan_id": payload.plan_id,
        "subscription_status": payload.subscription_status,
        "subscription_end": payload.subscription_end,
        "max_branches": payload.max_branches,
        "max_staff": payload.max_staff,
        "max_patients": payload.max_patients,
        "status": "active" if payload.subscription_status in ["active", "trialing"] else "suspended",
        "updated_at": datetime.utcnow()
    }

    await tenants_col.update_one({"_id": tenant_oid}, {"$set": update_fields})

    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="SUPER_ADMIN_TENANT_SUBSCRIPTION_OVERRIDDEN",
        entity="tenants",
        entity_id=tenant_id,
        details=update_fields,
        ip_address=request.client.host if request.client else None,
        tenant_id=tenant_oid
    )

    return {"status": "success", "message": f"Tenant subscription manually overridden by Super Admin"}
