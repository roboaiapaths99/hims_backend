from fastapi import APIRouter, Depends, HTTPException, status, Request
from bson import ObjectId
from datetime import datetime
from typing import List, Optional
from services.notification import create_user_notification

from database import (
    get_db,
    get_visitor_passes_collection,
    get_diet_orders_collection,
    get_ipd_admissions_collection,
    get_patients_collection,
    get_rooms_collection
)
from middleware.auth import (
    get_current_user,
    get_tenant_filter,
    get_branch_filter,
    inject_audit_fields
)
from middleware.audit import create_audit_log
from models.visitor_diet import (
    VisitorPassCreate,
    VisitorPassResponse,
    DietOrderCreate,
    DietOrderUpdate,
    DietOrderResponse
)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────
# VISITOR PASSES
# ─────────────────────────────────────────────────────────────────────

async def _resolve_admission_patient(admission_id: str, tenant_id):
    """Helper to get patient name from an IPD admission."""
    admissions_col = get_ipd_admissions_collection()
    patients_col = get_patients_collection()
    try:
        adm = await admissions_col.find_one({"_id": ObjectId(admission_id), "tenant_id": tenant_id})
    except Exception:
        return None, None
    if not adm:
        return None, None
    patient_name = None
    room_number = None
    if adm.get("patient_id"):
        patient = await patients_col.find_one({"_id": adm["patient_id"]})
        if patient:
            patient_name = f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip()
    if adm.get("room_id"):
        rooms_col = get_rooms_collection()
        room = await rooms_col.find_one({"_id": adm["room_id"]})
        if room:
            room_number = room.get("room_number", "")
    return patient_name, room_number


@router.post("/visitor-passes", response_model=VisitorPassResponse)
async def create_visitor_pass(
    payload: VisitorPassCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Issue a visitor pass for an IPD patient."""
    col = get_visitor_passes_collection()

    if payload.pass_type not in ("day_pass", "night_attendant"):
        raise HTTPException(status_code=400, detail="pass_type must be 'day_pass' or 'night_attendant'")

    # Verify admission exists
    try:
        adm_oid = ObjectId(payload.admission_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid admission_id format")

    admissions_col = get_ipd_admissions_collection()
    adm = await admissions_col.find_one({"_id": adm_oid, "tenant_id": current_user["tenant_id"]})
    if not adm:
        raise HTTPException(status_code=404, detail="IPD admission not found")

    patient_name, _ = await _resolve_admission_patient(payload.admission_id, current_user["tenant_id"])

    doc = payload.dict()
    doc["admission_id"] = adm_oid
    doc["is_active"] = True
    inject_audit_fields(current_user, doc)

    res = await col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    doc["admission_id"] = str(doc["admission_id"])
    doc["patient_name"] = patient_name

    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="VISITOR_PASS_ISSUED",
        entity="visitor_passes",
        entity_id=doc["id"],
        details={"visitor_name": payload.visitor_name, "pass_type": payload.pass_type},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    return VisitorPassResponse(**doc)


@router.get("/visitor-passes/admission/{admission_id}", response_model=List[VisitorPassResponse])
async def list_visitor_passes(
    admission_id: str,
    current_user: dict = Depends(get_current_user)
):
    """List all visitor passes for a given IPD admission."""
    col = get_visitor_passes_collection()
    try:
        adm_oid = ObjectId(admission_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid admission_id format")

    patient_name, _ = await _resolve_admission_patient(admission_id, current_user["tenant_id"])

    docs = await col.find({
        "admission_id": adm_oid,
        "tenant_id": current_user["tenant_id"]
    }).sort("created_at", -1).to_list(None)

    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["branch_id"] = str(doc["branch_id"])
        doc["admission_id"] = str(doc["admission_id"])
        doc["patient_name"] = patient_name
        result.append(VisitorPassResponse(**doc))
    return result


@router.put("/visitor-passes/{pass_id}/revoke")
async def revoke_visitor_pass(
    pass_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Revoke (deactivate) a visitor pass."""
    col = get_visitor_passes_collection()
    try:
        oid = ObjectId(pass_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid pass_id format")

    doc = await col.find_one({"_id": oid, "tenant_id": current_user["tenant_id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Visitor pass not found")

    now = datetime.utcnow()
    await col.update_one({"_id": oid}, {"$set": {
        "is_active": False,
        "updated_at": now,
        "updated_by": str(current_user["_id"])
    }})

    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="VISITOR_PASS_REVOKED",
        entity="visitor_passes",
        entity_id=pass_id,
        details={"visitor_name": doc.get("visitor_name")},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    return {"status": "revoked", "pass_id": pass_id}


# ─────────────────────────────────────────────────────────────────────
# KITCHEN / DIET ORDERS
# ─────────────────────────────────────────────────────────────────────

@router.post("/diet-orders", response_model=DietOrderResponse)
async def create_diet_order(
    payload: DietOrderCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Create a dietary prescription for an IPD patient."""
    col = get_diet_orders_collection()

    valid_meals = ("breakfast", "lunch", "dinner", "snack")
    valid_diets = ("regular", "diabetic", "liquid", "low_sodium", "soft", "npo")

    if payload.meal_type not in valid_meals:
        raise HTTPException(status_code=400, detail=f"meal_type must be one of: {', '.join(valid_meals)}")
    if payload.diet_type not in valid_diets:
        raise HTTPException(status_code=400, detail=f"diet_type must be one of: {', '.join(valid_diets)}")

    # Verify admission
    try:
        adm_oid = ObjectId(payload.admission_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid admission_id format")

    admissions_col = get_ipd_admissions_collection()
    adm = await admissions_col.find_one({"_id": adm_oid, "tenant_id": current_user["tenant_id"]})
    if not adm:
        raise HTTPException(status_code=404, detail="IPD admission not found")

    patient_name, room_number = await _resolve_admission_patient(payload.admission_id, current_user["tenant_id"])

    # Resolve admin configured meal pricing dynamically
    resolved_price = payload.price
    if not resolved_price or resolved_price <= 0.0:
        try:
            from database import get_pricing_items_collection
            pricing_col = get_pricing_items_collection()
            pricing_item = await pricing_col.find_one({
                "tenant_id": current_user["tenant_id"],
                "item_type": {"$in": ["diet", "catering"]},
                "code": payload.meal_type.lower(),
                "is_active": True
            })
            if not pricing_item:
                pricing_item = await pricing_col.find_one({
                    "tenant_id": current_user["tenant_id"],
                    "item_type": {"$in": ["diet", "catering"]},
                    "name": payload.meal_type.lower(),
                    "is_active": True
                })
            
            if pricing_item:
                resolved_price = pricing_item["price"]
            else:
                # Fallback hardcoded defaults
                meal_fallbacks = {
                    "breakfast": 120.0,
                    "lunch": 220.0,
                    "dinner": 220.0,
                    "snack": 60.0
                }
                resolved_price = meal_fallbacks.get(payload.meal_type.lower(), 150.0)
        except Exception as e:
            print(f"Error querying admin meal price: {e}")
            resolved_price = 150.0

    doc = payload.dict()
    doc["price"] = resolved_price
    doc["admission_id"] = adm_oid
    doc["status"] = "ordered"
    doc["created_by_role"] = "patient" if current_user.get("role") == "patient" else "staff"
    inject_audit_fields(current_user, doc)

    res = await col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    doc["admission_id"] = str(doc["admission_id"])
    doc["patient_name"] = patient_name
    doc["room_number"] = room_number
    doc["created_by_role"] = doc.get("created_by_role", "staff")

    try:
        await create_user_notification(
            tenant_id=ObjectId(doc["tenant_id"]),
            branch_id=ObjectId(doc["branch_id"]),
            user_id=adm["patient_id"],
            title="Meal Request Registered",
            message=f"Your request for {payload.meal_type.upper()} ({payload.diet_type.replace('_', ' ').title()} Diet) is registered.",
            notification_type="info"
        )
    except Exception as ne:
        print(f"Failed to create notification: {ne}")

    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="DIET_ORDER_CREATED",
        entity="diet_orders",
        entity_id=doc["id"],
        details={"meal_type": payload.meal_type, "diet_type": payload.diet_type},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    return DietOrderResponse(**doc)


@router.get("/diet-orders", response_model=List[DietOrderResponse])
async def list_diet_orders(
    status_filter: Optional[str] = None,
    meal_type: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """List all diet orders for the kitchen dashboard."""
    col = get_diet_orders_collection()
    query = get_branch_filter(current_user)

    if status_filter:
        query["status"] = status_filter
    if meal_type:
        query["meal_type"] = meal_type

    docs = await col.find(query).sort("created_at", -1).to_list(None)
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["branch_id"] = str(doc["branch_id"])
        admission_id_str = str(doc["admission_id"])
        doc["admission_id"] = admission_id_str

        patient_name, room_number = await _resolve_admission_patient(admission_id_str, doc["tenant_id"])
        doc["patient_name"] = patient_name
        doc["room_number"] = room_number

        doc["created_by_role"] = doc.get("created_by_role", "staff")
        result.append(DietOrderResponse(**doc))
    return result


@router.put("/diet-orders/{order_id}", response_model=DietOrderResponse)
async def update_diet_order(
    order_id: str,
    payload: DietOrderUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Update diet order status (preparing → prepared → delivered)."""
    col = get_diet_orders_collection()

    try:
        oid = ObjectId(order_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid order_id format")

    doc = await col.find_one({"_id": oid, "tenant_id": current_user["tenant_id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Diet order not found")

    update_data = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}

    if "status" in update_data:
        valid_statuses = ("ordered", "preparing", "prepared", "delivered")
        if update_data["status"] not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(valid_statuses)}")

    now = datetime.utcnow()
    update_data["updated_at"] = now
    update_data["updated_by"] = str(current_user["_id"])

    await col.update_one({"_id": oid}, {"$set": update_data})

    updated = await col.find_one({"_id": oid})
    updated["id"] = str(updated["_id"])
    updated["tenant_id"] = str(updated["tenant_id"])
    updated["branch_id"] = str(updated["branch_id"])
    admission_id_str = str(updated["admission_id"])
    updated["admission_id"] = admission_id_str

    patient_name, room_number = await _resolve_admission_patient(admission_id_str, updated["tenant_id"])
    updated["patient_name"] = patient_name
    updated["room_number"] = room_number
    updated["created_by_role"] = updated.get("created_by_role", "staff")

    if update_data.get("status") == "delivered":
        try:
            admissions_col = get_ipd_admissions_collection()
            adm = await admissions_col.find_one({"_id": ObjectId(admission_id_str)})
            if adm:
                await create_user_notification(
                    tenant_id=ObjectId(updated["tenant_id"]),
                    branch_id=ObjectId(updated["branch_id"]),
                    user_id=adm["patient_id"],
                    title="Meal Delivered! 🍽️",
                    message=f"Your {updated.get('meal_type', '').upper()} has been prepared and delivered to Room {room_number}. {updated.get('special_instructions', '')}",
                    notification_type="success"
                )
        except Exception as ne:
            print(f"Failed to create update notification: {ne}")

    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="DIET_ORDER_UPDATED",
        entity="diet_orders",
        entity_id=order_id,
        details=update_data,
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    return DietOrderResponse(**updated)
