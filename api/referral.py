from fastapi import APIRouter, Depends, HTTPException, status, Request
from bson import ObjectId
from datetime import datetime
from typing import List, Optional

from database import (
    get_db,
    get_referring_doctors_collection,
    get_referral_transactions_collection,
    get_invoices_collection,
    get_visits_collection
)
from middleware.auth import (
    get_current_user,
    get_tenant_filter,
    get_branch_filter,
    inject_audit_fields
)
from middleware.audit import create_audit_log
from models.referral import (
    ReferringDoctorCreate,
    ReferringDoctorUpdate,
    ReferringDoctorResponse,
    ReferralTransactionCreate,
    ReferralTransactionResponse,
    PayoutRequest,
    PayoutResponse
)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────
# REFERRING DOCTORS MASTER CRUD
# ─────────────────────────────────────────────────────────────────────

@router.post("/doctors", response_model=ReferringDoctorResponse)
async def create_referring_doctor(
    payload: ReferringDoctorCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Register a new external referring doctor with commission rules."""
    col = get_referring_doctors_collection()

    # Check duplicate by name + phone within same tenant
    dup_query = {
        "name": payload.name,
        "tenant_id": current_user["tenant_id"],
        "is_deleted": {"$ne": True}
    }
    if payload.phone:
        dup_query["phone"] = payload.phone
    existing = await col.find_one(dup_query)
    if existing:
        raise HTTPException(status_code=400, detail="Referring doctor with this name already exists")

    doc = payload.dict()
    doc["commission_rules"] = [r.dict() for r in payload.commission_rules]
    doc["is_active"] = True
    inject_audit_fields(current_user, doc)

    res = await col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])

    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="REFERRING_DOCTOR_CREATED",
        entity="referring_doctors",
        entity_id=doc["id"],
        details={"name": payload.name, "specialty": payload.specialty},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    return ReferringDoctorResponse(**doc)


@router.get("/doctors", response_model=List[ReferringDoctorResponse])
async def list_referring_doctors(
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """List all referring doctors for the current tenant."""
    col = get_referring_doctors_collection()
    query = get_tenant_filter(current_user)
    query["is_deleted"] = {"$ne": True}

    if is_active is not None:
        query["is_active"] = is_active
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"phone": {"$regex": search, "$options": "i"}},
            {"hospital_name": {"$regex": search, "$options": "i"}}
        ]

    docs = await col.find(query).sort("name", 1).to_list(None)
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["branch_id"] = str(doc["branch_id"])
        result.append(ReferringDoctorResponse(**doc))
    return result


@router.get("/doctors/{doctor_id}", response_model=ReferringDoctorResponse)
async def get_referring_doctor(
    doctor_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get a single referring doctor by ID."""
    col = get_referring_doctors_collection()
    try:
        oid = ObjectId(doctor_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid doctor_id format")

    doc = await col.find_one({"_id": oid, "tenant_id": current_user["tenant_id"], "is_deleted": {"$ne": True}})
    if not doc:
        raise HTTPException(status_code=404, detail="Referring doctor not found")

    doc["id"] = str(doc["_id"])
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    return ReferringDoctorResponse(**doc)


@router.put("/doctors/{doctor_id}", response_model=ReferringDoctorResponse)
async def update_referring_doctor(
    doctor_id: str,
    payload: ReferringDoctorUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Update referring doctor details or commission rules."""
    col = get_referring_doctors_collection()
    try:
        oid = ObjectId(doctor_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid doctor_id format")

    doc = await col.find_one({"_id": oid, "tenant_id": current_user["tenant_id"], "is_deleted": {"$ne": True}})
    if not doc:
        raise HTTPException(status_code=404, detail="Referring doctor not found")

    update_data = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    if "commission_rules" in update_data and update_data["commission_rules"] is not None:
        update_data["commission_rules"] = [r if isinstance(r, dict) else r.dict() for r in update_data["commission_rules"]]

    now = datetime.utcnow()
    update_data["updated_at"] = now
    update_data["updated_by"] = str(current_user["_id"])

    await col.update_one({"_id": oid}, {"$set": update_data})

    updated = await col.find_one({"_id": oid})
    updated["id"] = str(updated["_id"])
    updated["tenant_id"] = str(updated["tenant_id"])
    updated["branch_id"] = str(updated["branch_id"])

    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="REFERRING_DOCTOR_UPDATED",
        entity="referring_doctors",
        entity_id=doctor_id,
        details=update_data,
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    return ReferringDoctorResponse(**updated)


# ─────────────────────────────────────────────────────────────────────
# REFERRAL TRANSACTIONS (Commission Log)
# ─────────────────────────────────────────────────────────────────────

@router.post("/transactions", response_model=ReferralTransactionResponse)
async def create_referral_transaction(
    payload: ReferralTransactionCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Log a referral commission transaction linked to an invoice."""
    txn_col = get_referral_transactions_collection()
    docs_col = get_referring_doctors_collection()
    inv_col = get_invoices_collection()

    try:
        ref_doc_oid = ObjectId(payload.referring_doctor_id)
        invoice_oid = ObjectId(payload.invoice_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format")

    # Verify referring doctor exists
    ref_doc = await docs_col.find_one({"_id": ref_doc_oid, "tenant_id": current_user["tenant_id"], "is_deleted": {"$ne": True}})
    if not ref_doc:
        raise HTTPException(status_code=404, detail="Referring doctor not found")

    # Verify invoice exists
    invoice = await inv_col.find_one({"_id": invoice_oid, "tenant_id": current_user["tenant_id"]})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Check for duplicate transaction on the same invoice + referring doctor
    existing = await txn_col.find_one({
        "invoice_id": invoice_oid,
        "referring_doctor_id": ref_doc_oid,
        "tenant_id": current_user["tenant_id"]
    })
    if existing:
        raise HTTPException(status_code=400, detail="Referral transaction already exists for this invoice")

    doc = {
        "invoice_id": invoice_oid,
        "referring_doctor_id": ref_doc_oid,
        "visit_id": ObjectId(payload.visit_id) if payload.visit_id else None,
        "commission_amount": payload.commission_amount,
        "payout_status": "pending",
        "paid_at": None
    }
    inject_audit_fields(current_user, doc)

    res = await txn_col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    doc["invoice_id"] = str(doc["invoice_id"])
    doc["referring_doctor_id"] = str(doc["referring_doctor_id"])
    doc["referring_doctor_name"] = ref_doc["name"]
    doc["visit_id"] = str(doc["visit_id"]) if doc["visit_id"] else None

    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="REFERRAL_TRANSACTION_CREATED",
        entity="referral_transactions",
        entity_id=doc["id"],
        details={
            "referring_doctor": ref_doc["name"],
            "commission_amount": payload.commission_amount,
            "invoice_id": payload.invoice_id
        },
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    return ReferralTransactionResponse(**doc)


@router.get("/transactions", response_model=List[ReferralTransactionResponse])
async def list_referral_transactions(
    referring_doctor_id: Optional[str] = None,
    payout_status: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """List referral transactions, optionally filtered by doctor or payout status."""
    txn_col = get_referral_transactions_collection()
    docs_col = get_referring_doctors_collection()

    query = get_branch_filter(current_user)

    if referring_doctor_id:
        try:
            query["referring_doctor_id"] = ObjectId(referring_doctor_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid referring_doctor_id format")

    if payout_status:
        if payout_status not in ("pending", "paid"):
            raise HTTPException(status_code=400, detail="payout_status must be 'pending' or 'paid'")
        query["payout_status"] = payout_status

    docs = await txn_col.find(query).sort("created_at", -1).to_list(None)
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["branch_id"] = str(doc["branch_id"])
        doc["invoice_id"] = str(doc["invoice_id"])
        doc["referring_doctor_id"] = str(doc["referring_doctor_id"])
        doc["visit_id"] = str(doc["visit_id"]) if doc.get("visit_id") else None

        # Resolve referring doctor name
        try:
            ref_doc = await docs_col.find_one({"_id": ObjectId(doc["referring_doctor_id"])})
            doc["referring_doctor_name"] = ref_doc["name"] if ref_doc else "Unknown"
        except Exception:
            doc["referring_doctor_name"] = "Unknown"

        result.append(ReferralTransactionResponse(**doc))
    return result


@router.get("/transactions/summary")
async def get_referral_summary(
    referring_doctor_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Get aggregated commission summary per referring doctor."""
    txn_col = get_referral_transactions_collection()
    docs_col = get_referring_doctors_collection()

    match_stage = {
        "tenant_id": current_user["tenant_id"],
        "branch_id": current_user["branch_id"]
    }
    if referring_doctor_id:
        try:
            match_stage["referring_doctor_id"] = ObjectId(referring_doctor_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid referring_doctor_id format")

    pipeline = [
        {"$match": match_stage},
        {"$group": {
            "_id": {
                "referring_doctor_id": "$referring_doctor_id",
                "payout_status": "$payout_status"
            },
            "total_amount": {"$sum": "$commission_amount"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id.referring_doctor_id": 1}}
    ]

    raw = await txn_col.aggregate(pipeline).to_list(None)

    # Restructure into per-doctor summary
    doctor_map = {}
    for entry in raw:
        doc_id = str(entry["_id"]["referring_doctor_id"])
        if doc_id not in doctor_map:
            doctor_map[doc_id] = {
                "referring_doctor_id": doc_id,
                "referring_doctor_name": "",
                "total_pending": 0.0,
                "total_paid": 0.0,
                "pending_count": 0,
                "paid_count": 0
            }
        if entry["_id"]["payout_status"] == "pending":
            doctor_map[doc_id]["total_pending"] = round(entry["total_amount"], 2)
            doctor_map[doc_id]["pending_count"] = entry["count"]
        elif entry["_id"]["payout_status"] == "paid":
            doctor_map[doc_id]["total_paid"] = round(entry["total_amount"], 2)
            doctor_map[doc_id]["paid_count"] = entry["count"]

    # Resolve doctor names
    for doc_id, summary in doctor_map.items():
        try:
            ref = await docs_col.find_one({"_id": ObjectId(doc_id)})
            summary["referring_doctor_name"] = ref["name"] if ref else "Unknown"
        except Exception:
            summary["referring_doctor_name"] = "Unknown"

    return list(doctor_map.values())


# ─────────────────────────────────────────────────────────────────────
# PAYOUTS (Settle pending commissions)
# ─────────────────────────────────────────────────────────────────────

@router.post("/payouts", response_model=PayoutResponse)
async def settle_payouts(
    payload: PayoutRequest,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Mark selected pending transactions as paid (settled)."""
    txn_col = get_referral_transactions_collection()
    docs_col = get_referring_doctors_collection()

    try:
        ref_doc_oid = ObjectId(payload.referring_doctor_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid referring_doctor_id format")

    ref_doc = await docs_col.find_one({"_id": ref_doc_oid, "tenant_id": current_user["tenant_id"]})
    if not ref_doc:
        raise HTTPException(status_code=404, detail="Referring doctor not found")

    # Validate transaction IDs
    txn_oids = []
    for tid in payload.transaction_ids:
        try:
            txn_oids.append(ObjectId(tid))
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid transaction_id: {tid}")

    # Verify all transactions belong to the same referring doctor and are pending
    pending_txns = await txn_col.find({
        "_id": {"$in": txn_oids},
        "referring_doctor_id": ref_doc_oid,
        "payout_status": "pending",
        "tenant_id": current_user["tenant_id"]
    }).to_list(None)

    if len(pending_txns) != len(txn_oids):
        raise HTTPException(
            status_code=400,
            detail=f"Some transactions are invalid, already paid, or don't belong to this doctor. Found {len(pending_txns)} valid pending transactions out of {len(txn_oids)} requested."
        )

    total_amount = sum(t["commission_amount"] for t in pending_txns)
    now = datetime.utcnow()

    # Bulk update to 'paid'
    await txn_col.update_many(
        {"_id": {"$in": txn_oids}},
        {"$set": {
            "payout_status": "paid",
            "paid_at": now,
            "updated_at": now,
            "updated_by": str(current_user["_id"])
        }}
    )

    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="REFERRAL_PAYOUT_SETTLED",
        entity="referral_transactions",
        entity_id=payload.referring_doctor_id,
        details={
            "settled_count": len(pending_txns),
            "total_amount": round(total_amount, 2),
            "payment_reference": payload.payment_reference,
            "transaction_ids": [str(t) for t in txn_oids]
        },
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )

    return PayoutResponse(
        settled_count=len(pending_txns),
        total_amount=round(total_amount, 2),
        referring_doctor_id=payload.referring_doctor_id,
        payment_reference=payload.payment_reference
    )
