from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List, Optional
from bson import ObjectId

from database import get_notifications_logs_collection, get_notifications_collection
from middleware.auth import (
    get_current_user,
    get_branch_filter
)
from models.notification import NotificationLogResponse, NotificationResponse
from pydantic import BaseModel

router = APIRouter()

class MarkReadRequest(BaseModel):
    ids: Optional[List[str]] = None

@router.get("/logs", response_model=List[NotificationLogResponse])
async def list_notification_logs(
    channel: Optional[str] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    logs_col = get_notifications_logs_collection()
    
    query = get_branch_filter(current_user)
    if channel:
        query["channel"] = channel
    if status:
        query["status"] = status
        
    docs = await logs_col.find(query).sort("created_at", -1).to_list(None)
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["branch_id"] = str(doc["branch_id"])
        if doc.get("recipient_id"):
            doc["recipient_id"] = str(doc["recipient_id"])
        result.append(doc)
        
    return result

@router.get("/user", response_model=List[NotificationResponse])
async def get_user_notifications(
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    col = get_notifications_collection()
    user_id_str = str(current_user["_id"])
    try:
        user_id_oid = ObjectId(user_id_str)
        user_ids = [user_id_oid, user_id_str]
    except Exception:
        user_ids = [user_id_str]
    
    query = {
        "user_id": {"$in": user_ids}
    }
    
    docs = await col.find(query).sort("created_at", -1).limit(limit).to_list(None)
    results = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["branch_id"] = str(doc["branch_id"])
        doc["user_id"] = str(doc["user_id"])
        results.append(doc)
        
    return results

@router.post("/mark-read")
async def mark_notifications_as_read(
    payload: Optional[MarkReadRequest] = None,
    current_user: dict = Depends(get_current_user)
):
    col = get_notifications_collection()
    user_id_str = str(current_user["_id"])
    try:
        user_id_oid = ObjectId(user_id_str)
        user_ids = [user_id_oid, user_id_str]
    except Exception:
        user_ids = [user_id_str]
    
    query = {
        "user_id": {"$in": user_ids}
    }
    
    if payload and payload.ids:
        try:
            oids = [ObjectId(i) for i in payload.ids]
            query["_id"] = {"$in": oids}
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid notification ID format"
            )
            
    update_res = await col.update_many(query, {"$set": {"is_read": True}})
    
    return {
        "status": "success",
        "modified_count": update_res.modified_count
    }

@router.get("/count")
async def get_unread_notification_count(
    current_user: dict = Depends(get_current_user)
):
    col = get_notifications_collection()
    user_id_str = str(current_user["_id"])
    try:
        user_id_oid = ObjectId(user_id_str)
        user_ids = [user_id_oid, user_id_str]
    except Exception:
        user_ids = [user_id_str]
    
    query = {
        "user_id": {"$in": user_ids},
        "is_read": False
    }
    
    count = await col.count_documents(query)
    return {"count": count}

@router.get("/me", response_model=List[NotificationResponse])
async def get_my_notifications(
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    return await get_user_notifications(limit=limit, current_user=current_user)

@router.post("/{id}/read")
async def mark_single_notification_read(
    id: str,
    current_user: dict = Depends(get_current_user)
):
    req = MarkReadRequest(ids=[id])
    return await mark_notifications_as_read(payload=req, current_user=current_user)

