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
    user_id = current_user["_id"]
    tenant_id_val = current_user.get("tenant_id")
    tenant_id = ObjectId(str(tenant_id_val)) if tenant_id_val else None
    
    query = {
        "user_id": user_id,
        "tenant_id": tenant_id
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
    user_id = current_user["_id"]
    tenant_id_val = current_user.get("tenant_id")
    tenant_id = ObjectId(str(tenant_id_val)) if tenant_id_val else None
    
    query = {
        "user_id": user_id,
        "tenant_id": tenant_id
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
    user_id = current_user["_id"]
    tenant_id_val = current_user.get("tenant_id")
    tenant_id = ObjectId(str(tenant_id_val)) if tenant_id_val else None
    
    query = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "is_read": False
    }
    
    count = await col.count_documents(query)
    return {"count": count}

