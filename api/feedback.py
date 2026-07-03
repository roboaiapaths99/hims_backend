from fastapi import APIRouter, Depends, HTTPException, Request
from bson import ObjectId
from datetime import datetime
from typing import List, Optional

from database import (
    get_feedback_surveys_collection,
    get_patients_collection
)
from middleware.auth import (
    get_current_user,
    get_tenant_filter,
    get_branch_filter,
    inject_audit_fields
)
from middleware.audit import create_audit_log
from models.hr_feedback import FeedbackCreate, FeedbackResponse

router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    payload: FeedbackCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Submit a patient feedback survey response."""
    col = get_feedback_surveys_collection()
    patients_col = get_patients_collection()

    doc = payload.dict()
    patient_name = None

    if payload.patient_id:
        try:
            patient_oid = ObjectId(payload.patient_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid patient_id format")
        patient = await patients_col.find_one({"_id": patient_oid, "tenant_id": current_user["tenant_id"]})
        if patient:
            patient_name = f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip()
            doc["patient_id"] = patient_oid
    else:
        doc["patient_id"] = None

    if payload.visit_id:
        try:
            doc["visit_id"] = ObjectId(payload.visit_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid visit_id format")
    else:
        doc["visit_id"] = None

    inject_audit_fields(current_user, doc)

    res = await col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    doc["patient_id"] = str(doc["patient_id"]) if doc.get("patient_id") else None
    doc["visit_id"] = str(doc["visit_id"]) if doc.get("visit_id") else None
    doc["patient_name"] = patient_name

    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="FEEDBACK_SUBMITTED",
        entity="feedback_surveys",
        entity_id=doc["id"],
        details={"rating": payload.rating, "category": payload.category},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    return FeedbackResponse(**doc)


@router.get("/feedback", response_model=List[FeedbackResponse])
async def list_feedback(
    rating: Optional[int] = None,
    category: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """List all feedback surveys for the current branch."""
    col = get_feedback_surveys_collection()
    patients_col = get_patients_collection()

    query = get_branch_filter(current_user)

    if rating is not None:
        query["rating"] = rating
    if category:
        query["category"] = category

    docs = await col.find(query).sort("created_at", -1).to_list(None)
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["branch_id"] = str(doc["branch_id"])

        patient_name = None
        if doc.get("patient_id"):
            try:
                patient = await patients_col.find_one({"_id": doc["patient_id"]})
                if patient:
                    patient_name = f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip()
            except Exception:
                pass
            doc["patient_id"] = str(doc["patient_id"])
        doc["visit_id"] = str(doc["visit_id"]) if doc.get("visit_id") else None
        doc["patient_name"] = patient_name

        result.append(FeedbackResponse(**doc))
    return result


@router.get("/feedback/stats")
async def get_feedback_stats(current_user: dict = Depends(get_current_user)):
    """Get aggregated feedback statistics."""
    col = get_feedback_surveys_collection()

    pipeline = [
        {"$match": {
            "tenant_id": current_user["tenant_id"],
            "branch_id": current_user["branch_id"]
        }},
        {"$group": {
            "_id": "$category",
            "avg_rating": {"$avg": "$rating"},
            "count": {"$sum": 1},
            "rating_1": {"$sum": {"$cond": [{"$eq": ["$rating", 1]}, 1, 0]}},
            "rating_2": {"$sum": {"$cond": [{"$eq": ["$rating", 2]}, 1, 0]}},
            "rating_3": {"$sum": {"$cond": [{"$eq": ["$rating", 3]}, 1, 0]}},
            "rating_4": {"$sum": {"$cond": [{"$eq": ["$rating", 4]}, 1, 0]}},
            "rating_5": {"$sum": {"$cond": [{"$eq": ["$rating", 5]}, 1, 0]}}
        }},
        {"$sort": {"_id": 1}}
    ]

    raw = await col.aggregate(pipeline).to_list(None)

    total_count = sum(e["count"] for e in raw)
    total_avg = round(sum(e["avg_rating"] * e["count"] for e in raw) / total_count, 2) if total_count > 0 else 0

    return {
        "total_responses": total_count,
        "overall_avg_rating": total_avg,
        "by_category": [
            {
                "category": e["_id"] or "general",
                "avg_rating": round(e["avg_rating"], 2),
                "count": e["count"],
                "distribution": {
                    "1": e["rating_1"], "2": e["rating_2"], "3": e["rating_3"],
                    "4": e["rating_4"], "5": e["rating_5"]
                }
            }
            for e in raw
        ]
    }
