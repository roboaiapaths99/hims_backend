import hmac
import hashlib
import json
import logging
import os
import io
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Request, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from jose import jwt
from bson import ObjectId

from config import settings
from database import (
    get_patients_collection,
    get_dms_patient_sync_collection,
    get_dms_document_refs_collection,
    get_dms_webhook_events_collection,
    get_dms_similar_case_searches_collection
)
from services.dms_bridge_service import dms_bridge
from services.dms_patient_sync_service import sync_patient_to_dms
from middleware.auth import get_current_user
from middleware.audit import create_audit_log

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/integrations/dms", tags=["DMS Integration"])

# Preview token helper utilities
def create_preview_token(document_id: str, tenant_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode = {
        "exp": expire,
        "document_id": document_id,
        "tenant_id": tenant_id,
        "type": "dms_preview"
    }
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm="HS256")

def decode_preview_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") != "dms_preview":
            return None
        return payload
    except Exception:
        return None

@router.get("/status")
async def get_dms_status(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("super_admin", "hospital_admin", "branch_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Administrative access required"
        )
        
    enabled = settings.DMS_INTEGRATION_ENABLED
    reachable = False
    error = None
    data = None
    
    if enabled:
        health_res = await dms_bridge.check_health()
        reachable = health_res.get("reachable", False)
        error = health_res.get("error")
        data = health_res.get("data")
        
    return {
        "enabled": enabled,
        "reachable": reachable,
        "last_checked_at": datetime.utcnow().isoformat() + "Z",
        "error": error,
        "data": data
    }

@router.post("/patients/{patient_id}/sync")
async def trigger_single_patient_sync(
    patient_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") not in ("super_admin", "hospital_admin", "branch_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Missing permissions"
        )
        
    try:
        p_oid = ObjectId(patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient ID format")
        
    patients_col = get_patients_collection()
    patient = await patients_col.find_one({"_id": p_oid})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
        
    if current_user.get("role") != "super_admin":
        if patient.get("tenant_id") != current_user.get("tenant_id"):
            raise HTTPException(status_code=403, detail="Patient tenant mismatch")
            
    res = await sync_patient_to_dms(p_oid)
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="DMS_PATIENT_SYNCED",
        entity="patients",
        entity_id=patient_id,
        details={"success": res.get("success"), "status": res.get("status"), "error": res.get("error")},
        ip_address=request.client.host if request.client else None,
        tenant_id=patient.get("tenant_id"),
        branch_id=patient.get("branch_id")
    )
    
    return res

@router.get("/patients/{patient_id}/sync-status")
async def get_patient_sync_status(
    patient_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        p_oid = ObjectId(patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient ID format")
        
    sync_col = get_dms_patient_sync_collection()
    sync_rec = await sync_col.find_one({"patient_id": p_oid})
    if not sync_rec:
        return {"synced": False, "status": "not_started", "last_error": None}
        
    return {
        "synced": sync_rec.get("sync_status") == "synced",
        "status": sync_rec.get("sync_status"),
        "dms_patient_id": sync_rec.get("dms_patient_id"),
        "last_synced_at": sync_rec.get("last_synced_at").isoformat() + "Z" if sync_rec.get("last_synced_at") else None,
        "last_error": sync_rec.get("last_error"),
        "retry_count": sync_rec.get("retry_count", 0)
    }

async def run_backfill_background(tenant_id: str, force: bool):
    from scripts.backfill_dms_patients import run_backfill
    await run_backfill(tenant_id=tenant_id, force=force)

@router.post("/patients/backfill")
async def trigger_patients_backfill(
    background_tasks: BackgroundTasks,
    force: bool = False,
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") not in ("super_admin", "hospital_admin"):
        raise HTTPException(status_code=403, detail="Administrative access required")
        
    tenant_id = str(current_user["tenant_id"]) if current_user.get("role") != "super_admin" else None
    
    background_tasks.add_task(run_backfill_background, tenant_id, force)
    
    return {
        "success": True,
        "message": "Patient backfill sync task started in the background"
    }

@router.post("/documents/upload")
async def upload_document_proxy(
    request: Request,
    patient_id: str = Form(...),
    document_type: str = Form("Other"),
    notes: Optional[str] = Form(None),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") not in ("super_admin", "hospital_admin", "branch_admin", "doctor", "nurse", "receptionist"):
        raise HTTPException(status_code=403, detail="Unauthorized upload access")
        
    try:
        p_oid = ObjectId(patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient ID format")
        
    patients_col = get_patients_collection()
    patient = await patients_col.find_one({"_id": p_oid})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
        
    if current_user.get("role") != "super_admin":
        if patient.get("tenant_id") != current_user.get("tenant_id"):
            raise HTTPException(status_code=403, detail="Patient scope mismatch")
            
    ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".txt"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file extension. Allowed: PDF, JPG, PNG, TXT")
        
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds the maximum limit of 25MB")
        
    sync_col = get_dms_patient_sync_collection()
    sync_rec = await sync_col.find_one({"patient_id": p_oid, "sync_status": "synced"})
    if not sync_rec:
        logger.info(f"Patient {patient_id} not synced to DMS. Syncing now before document upload...")
        sync_res = await sync_patient_to_dms(p_oid)
        if not sync_res.get("success"):
            raise HTTPException(
                status_code=500,
                detail=f"Cannot upload document: Failed to sync patient demographics to DMS: {sync_res.get('error')}"
            )
            
    files_param = {
        "file": (file.filename, content, file.content_type)
    }
    data_param = {
        "hims_patient_id": str(patient["_id"]),
        "mrn": patient.get("mrn", ""),
        "document_type": document_type,
        "notes": notes or "",
        "tenant_id": str(current_user["tenant_id"]),
        "branch_id": str(current_user["branch_id"]),
        "uploader_id": str(current_user["_id"]),
        "uploader_role": current_user["role"]
    }
    
    res = await dms_bridge.upload_document(files=files_param, data=data_param)
    
    if not res.get("success"):
        raise HTTPException(
            status_code=502,
            detail=f"DMS bridge upload failed: {res.get('error')}"
        )
        
    dms_doc_id = res["data"]["data"]["dms_document_id"]
    
    doc_refs_col = get_dms_document_refs_collection()
    ref_doc = {
        "tenant_id": current_user["tenant_id"],
        "branch_id": current_user["branch_id"],
        "patient_id": p_oid,
        "mrn": patient.get("mrn", ""),
        "dms_document_id": dms_doc_id,
        "document_type": document_type,
        "original_filename": file.filename,
        "status": "processing",
        "summary_snippet": None,
        "is_medical_document": True,
        "needs_review": False,
        "similar_case_count": 0,
        "uploaded_by": str(current_user["_id"]),
        "uploaded_at": datetime.utcnow(),
        "processed_at": None,
        "last_event_at": datetime.utcnow(),
        "last_error": None
    }
    await doc_refs_col.insert_one(ref_doc)
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="DMS_DOCUMENT_UPLOADED",
        entity="documents",
        entity_id=dms_doc_id,
        details={"original_filename": file.filename, "document_type": document_type},
        ip_address=request.client.host if request.client else None,
        tenant_id=patient.get("tenant_id"),
        branch_id=patient.get("branch_id")
    )
    
    return {
        "success": True,
        "message": "Document uploaded successfully",
        "dms_document_id": dms_doc_id
    }

@router.post("/webhook")
async def receive_dms_webhook(request: Request):
    signature = request.headers.get("x-webhook-signature")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing webhook signature")
        
    body = await request.body()
    calculated_sig = hmac.new(
        settings.DMS_WEBHOOK_SECRET.encode('utf-8'),
        body,
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(calculated_sig, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")
        
    payload = json.loads(body)
    event_id = payload.get("event_id")
    event_type = payload.get("event_type")
    dms_doc_id = payload.get("dms_document_id")
    
    webhook_col = get_dms_webhook_events_collection()
    existing = await webhook_col.find_one({"event_id": event_id})
    if existing:
        return {"success": True, "message": "Event already processed"}
        
    now = datetime.utcnow()
    event_doc = {
        "event_id": event_id,
        "event_type": event_type,
        "source_system": payload.get("source_system", "DMS"),
        "dms_document_id": dms_doc_id,
        "patient_id": ObjectId(payload["hims_patient_id"]) if payload.get("hims_patient_id") else None,
        "payload": payload,
        "processed": True,
        "processed_at": now,
        "error": None,
        "received_at": now
    }
    await webhook_col.insert_one(event_doc)
    
    doc_refs_col = get_dms_document_refs_collection()
    doc_info = payload.get("document") or {}
    status_val = doc_info.get("status", "processing")
    
    update_fields = {
        "status": status_val,
        "last_event_at": now,
    }
    if "document_type" in doc_info:
        update_fields["document_type"] = doc_info["document_type"]
    if "original_filename" in doc_info:
        update_fields["original_filename"] = doc_info["original_filename"]
    if "summary_snippet" in doc_info:
        update_fields["summary_snippet"] = doc_info["summary_snippet"]
    if "is_medical_document" in doc_info:
        update_fields["is_medical_document"] = doc_info["is_medical_document"]
    if "needs_review" in doc_info:
        update_fields["needs_review"] = doc_info["needs_review"]
    if "similar_case_count" in doc_info:
        update_fields["similar_case_count"] = doc_info["similar_case_count"]
    if "processed_at" in doc_info:
        try:
            update_fields["processed_at"] = datetime.fromisoformat(doc_info["processed_at"].replace("Z", "+00:00"))
        except:
            update_fields["processed_at"] = now
    if "last_error" in doc_info:
        update_fields["last_error"] = doc_info["last_error"]
        
    await doc_refs_col.update_one(
        {"dms_document_id": dms_doc_id},
        {"$set": update_fields}
    )
    
    ref = await doc_refs_col.find_one({"dms_document_id": dms_doc_id})
    if ref and ref.get("uploaded_by"):
        try:
            from services.notification_service import NotificationService
            title = "Document Processed"
            msg = f"Document {ref.get('original_filename')} has been successfully processed by DMS."
            notif_type = "success"
            
            if event_type == "document.needs_review":
                title = "Document Needs Review"
                msg = f"Document {ref.get('original_filename')} requires manual link verification."
                notif_type = "warning"
            elif event_type == "extraction.failed":
                title = "Document Processing Failed"
                msg = f"DMS failed to extract data from {ref.get('original_filename')}."
                notif_type = "error"
                
            await NotificationService.create_in_app_notification(
                tenant_id=ref["tenant_id"],
                branch_id=ref["branch_id"],
                user_id=ObjectId(ref["uploaded_by"]),
                title=title,
                message=msg,
                notification_type=notif_type
            )
        except Exception as notif_err:
            logger.error(f"Failed to generate webhook in-app notification: {notif_err}")
            
    return {"success": True, "message": "Webhook processed successfully"}

@router.get("/queue")
async def get_document_review_queue(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("super_admin", "hospital_admin", "branch_admin", "doctor"):
        raise HTTPException(status_code=403, detail="Unauthorized queue access")
        
    doc_refs_col = get_dms_document_refs_collection()
    query = {"tenant_id": current_user["tenant_id"]}
    query["$or"] = [
        {"needs_review": True},
        {"status": {"$in": ["pending_verification", "failed"]}}
    ]
    
    cursor = doc_refs_col.find(query).sort("uploaded_at", -1)
    docs = await cursor.to_list(None)
    
    formatted_docs = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["patient_id"] = str(doc["patient_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["branch_id"] = str(doc["branch_id"])
        del doc["_id"]
        formatted_docs.append(doc)
        
    return formatted_docs

@router.put("/documents/{document_id}/verify")
async def verify_dms_document(
    document_id: str,
    payload: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") not in ("super_admin", "hospital_admin", "branch_admin", "doctor"):
        raise HTTPException(status_code=403, detail="Unauthorized action")
        
    res = await dms_bridge.verify_document(document_id, payload)
    if not res.get("success"):
        raise HTTPException(status_code=502, detail=f"DMS verification failed: {res.get('error')}")
        
    doc_refs_col = get_dms_document_refs_collection()
    await doc_refs_col.update_one(
        {"dms_document_id": document_id},
        {"$set": {
            "status": "verified",
            "needs_review": False,
            "last_event_at": datetime.utcnow()
        }}
    )
    return {"success": True, "message": "Document verified successfully"}

@router.put("/documents/{document_id}/reject")
async def reject_dms_document(
    document_id: str,
    payload: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") not in ("super_admin", "hospital_admin", "branch_admin", "doctor"):
        raise HTTPException(status_code=403, detail="Unauthorized action")
        
    res = await dms_bridge.reject_document(document_id, payload)
    if not res.get("success"):
        raise HTTPException(status_code=502, detail=f"DMS rejection failed: {res.get('error')}")
        
    doc_refs_col = get_dms_document_refs_collection()
    await doc_refs_col.update_one(
        {"dms_document_id": document_id},
        {"$set": {
            "status": "rejected",
            "needs_review": False,
            "last_event_at": datetime.utcnow()
        }}
    )
    return {"success": True, "message": "Document rejected successfully"}

@router.post("/documents/{document_id}/reprocess")
async def reprocess_dms_document(
    document_id: str,
    payload: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") not in ("super_admin", "hospital_admin", "branch_admin", "doctor"):
        raise HTTPException(status_code=403, detail="Unauthorized action")
        
    res = await dms_bridge.reprocess_document(document_id, payload)
    if not res.get("success"):
        raise HTTPException(status_code=502, detail=f"DMS reprocessing trigger failed: {res.get('error')}")
        
    doc_refs_col = get_dms_document_refs_collection()
    await doc_refs_col.update_one(
        {"dms_document_id": document_id},
        {"$set": {
            "status": "processing",
            "needs_review": False,
            "last_event_at": datetime.utcnow()
        }}
    )
    return {"success": True, "message": "Reprocessing started"}

@router.get("/patients/{patient_id}/documents")
async def get_patient_documents(
    patient_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        p_oid = ObjectId(patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient ID format")
        
    doc_refs_col = get_dms_document_refs_collection()
    query = {
        "tenant_id": current_user["tenant_id"],
        "patient_id": p_oid
    }
    
    cursor = doc_refs_col.find(query).sort("uploaded_at", -1)
    docs = await cursor.to_list(None)
    
    formatted_docs = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["patient_id"] = str(doc["patient_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["branch_id"] = str(doc["branch_id"])
        del doc["_id"]
        formatted_docs.append(doc)
        
    return formatted_docs

@router.get("/patients/{patient_id}/summary")
async def get_patient_summary_proxy(
    patient_id: str,
    current_user: dict = Depends(get_current_user)
):
    sync_col = get_dms_patient_sync_collection()
    sync_rec = await sync_col.find_one({"patient_id": ObjectId(patient_id)})
    if not sync_rec or not sync_rec.get("dms_patient_id"):
        raise HTTPException(status_code=404, detail="Patient clinical summary not available (not synced to DMS)")
        
    res = await dms_bridge.get_patient_summary(sync_rec["dms_patient_id"])
    if not res.get("success"):
        raise HTTPException(status_code=502, detail=f"DMS bridge error: {res.get('error')}")
        
    return res["data"]

@router.get("/patients/{patient_id}/timeline")
async def get_patient_timeline_proxy(
    patient_id: str,
    current_user: dict = Depends(get_current_user)
):
    sync_col = get_dms_patient_sync_collection()
    sync_rec = await sync_col.find_one({"patient_id": ObjectId(patient_id)})
    if not sync_rec or not sync_rec.get("dms_patient_id"):
        return []
        
    res = await dms_bridge.get_patient_timeline(sync_rec["dms_patient_id"])
    if not res.get("success"):
        raise HTTPException(status_code=502, detail=f"DMS bridge error: {res.get('error')}")
        
    return res["data"]

@router.get("/documents/{document_id}/preview-token")
async def get_document_preview_token(
    document_id: str,
    current_user: dict = Depends(get_current_user)
):
    # Verify document exists in references
    doc_refs_col = get_dms_document_refs_collection()
    doc_ref = await doc_refs_col.find_one({
        "dms_document_id": document_id,
        "tenant_id": current_user["tenant_id"]
    })
    if not doc_ref:
        raise HTTPException(status_code=404, detail="Document reference not found")
        
    token = create_preview_token(document_id, str(current_user["tenant_id"]))
    url = f"/api/integrations/dms/documents/{document_id}/preview?token={token}"
    return {"token": token, "url": url}

@router.get("/documents/{document_id}/preview")
async def preview_document(
    document_id: str,
    token: str
):
    payload = decode_preview_token(token)
    if not payload or payload.get("document_id") != document_id:
        raise HTTPException(status_code=401, detail="Invalid or expired preview token")
        
    try:
        res = await dms_bridge._request("GET", f"/bridge/documents/{document_id}/download")
        if res.status_code != 200:
            raise HTTPException(status_code=502, detail=f"DMS returned error status: {res.status_code}")
            
        return StreamingResponse(
            io.BytesIO(res.content),
            media_type=res.headers.get("Content-Type", "application/pdf")
        )
    except Exception as e:
        logger.error(f"Failed to fetch document file {document_id} from DMS for preview: {e}")
        raise HTTPException(status_code=502, detail=str(e))

@router.post("/similar-cases/search")
async def proxy_similar_cases_search(
    payload: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") not in ("super_admin", "hospital_admin", "branch_admin", "doctor"):
        raise HTTPException(status_code=403, detail="Unauthorized similarity search access")
        
    query_text = payload.get("text", "").strip()
    if not query_text:
        raise HTTPException(status_code=400, detail="Query search text is required")
        
    # Log the search in cache
    searches_col = get_dms_similar_case_searches_collection()
    search_log = {
        "tenant_id": current_user["tenant_id"],
        "branch_id": current_user.get("branch_id"),
        "doctor_id": ObjectId(current_user["_id"]),
        "patient_id": ObjectId(payload["patient_id"]) if payload.get("patient_id") else None,
        "query_text": query_text,
        "created_at": datetime.utcnow()
    }
    await searches_col.insert_one(search_log)
    
    # Forward search request to DMS bridge
    bridge_payload = {
        "text": query_text,
        "max_results": payload.get("max_results", 5),
        "tenant_id": str(current_user["tenant_id"])
    }
    
    res = await dms_bridge.search_similar_cases(bridge_payload)
    if not res.get("success"):
        raise HTTPException(status_code=502, detail=f"DMS bridge error: {res.get('error')}")
        
    formatted = []
    for doc in (res.get("data") or []):
        score_val = doc.get("similarity_score", 75.0)
        decimal_score = score_val / 100.0 if score_val > 1.0 else score_val
        formatted.append({
            "recommendation_id": doc.get("dms_document_id") or doc.get("recommendation_id"),
            "dms_document_id": doc.get("dms_document_id"),
            "score": decimal_score,
            "similarity_score": score_val,
            "diagnosis": doc.get("document_type") or doc.get("diagnosis") or "Clinical Record",
            "notes": doc.get("summary") or doc.get("notes") or "",
            "masked_patient_name": doc.get("masked_patient_name") or "Masked Patient",
            "doctor_feedback": doc.get("doctor_feedback")
        })
        
    return formatted

@router.put("/similar-cases/{recommendation_id}/feedback")
async def proxy_similar_case_feedback(
    recommendation_id: str,
    payload: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") not in ("super_admin", "hospital_admin", "branch_admin", "doctor"):
        raise HTTPException(status_code=403, detail="Unauthorized action")
        
    bridge_payload = {
        "feedback": payload.get("feedback"),
        "doctor_email": current_user.get("email", "HIMS Doctor")
    }
    
    res = await dms_bridge._request(
        "PUT",
        f"/bridge/similar-cases/{recommendation_id}/feedback",
        json=bridge_payload
    )
    if res.status_code != 200:
        raise HTTPException(status_code=502, detail=f"DMS bridge error status {res.status_code}: {res.text}")
        
    return res.json()
