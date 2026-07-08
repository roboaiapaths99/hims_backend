from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File, Query
from fastapi.responses import FileResponse
from bson import ObjectId
from datetime import datetime, timedelta
import os
import shutil
import uuid
from jose import jwt

from config import settings
from database import get_stored_files_collection, get_db
from middleware.auth import get_current_user, inject_audit_fields
from middleware.audit import create_audit_log
from models.storage import FileUploadResponse, FileDownloadResponse

import boto3
from botocore.exceptions import ClientError

def get_s3_client():
    if not (settings.S3_ACCESS_KEY and settings.S3_SECRET_KEY and settings.S3_BUCKET_NAME):
        return None
    session = boto3.session.Session()
    return session.client(
        's3',
        region_name=settings.S3_REGION_NAME,
        endpoint_url=settings.S3_ENDPOINT_URL,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY
    )

router = APIRouter()

# Forbidden list of script/executable extensions
FORBIDDEN_EXTENSIONS = {'exe', 'dll', 'bat', 'sh', 'py', 'js', 'vbs', 'msi', 'cmd', 'scr', 'jar'}

@router.post("/upload", response_model=FileUploadResponse)
@router.post("/upload/", response_model=FileUploadResponse)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    # Validate extension
    filename = file.filename or "unnamed_file"
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    if ext in FORBIDDEN_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Executable or script uploads are forbidden for security reasons."
        )
        
    # Get file size
    try:
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
    except Exception:
        size = 0

    # Ensure uploads folder exists
    os.makedirs("uploads", exist_ok=True)
    
    # Save file physically with high-entropy unique prefix
    unique_filename = f"{uuid.uuid4()}_{filename}"
    file_path = os.path.join("uploads", unique_filename)
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to write file to storage: {str(e)}"
        )
        
    # S3 Upload
    s3_client = get_s3_client()
    if s3_client:
        try:
            s3_client.upload_file(file_path, settings.S3_BUCKET_NAME, unique_filename)
            # Remove local file if S3 is active
            os.remove(file_path)
        except Exception as e:
            if os.path.exists(file_path):
                os.remove(file_path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload file to S3: {str(e)}"
            )
        
    # Insert metadata in DB
    files_col = get_stored_files_collection()
    doc = {
        "tenant_id": current_user["tenant_id"],
        "branch_id": current_user["branch_id"],
        "filename": unique_filename,
        "original_name": filename,
        "mime_type": file.content_type or "application/octet-stream",
        "size": size,
        "created_at": datetime.utcnow()
    }
    
    inject_audit_fields(current_user, doc)
    res = await files_col.insert_one(doc)
    file_id = str(res.inserted_id)
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="FILE_UPLOADED",
        entity="stored_files",
        entity_id=file_id,
        details={"original_name": filename, "mime_type": doc["mime_type"]},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    return FileUploadResponse(
        id=file_id,
        filename=unique_filename,
        original_name=filename,
        mime_type=doc["mime_type"],
        size=size,
        url=f"/uploads/{unique_filename}"
    )

@router.get("/download/{file_id}", response_model=FileDownloadResponse)
@router.get("/download/{file_id}/", response_model=FileDownloadResponse)
async def generate_download_url(
    file_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        file_oid = ObjectId(file_id)
    except:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file ID format")
        
    files_col = get_stored_files_collection()
    doc = await files_col.find_one({"_id": file_oid, "tenant_id": current_user["tenant_id"]})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File metadata record not found")
        
    # Generate temporary JWT access signature (expires in 1 hour)
    expires_at = datetime.utcnow() + timedelta(hours=1)
    token_payload = {
        "file_id": file_id,
        "sub": str(current_user["_id"]),
        "exp": int(expires_at.timestamp())
    }
    
    token = jwt.encode(token_payload, settings.JWT_SECRET, algorithm="HS256")
    download_url = f"/api/storage/view/{file_id}?token={token}"
    
    return FileDownloadResponse(
        download_url=download_url,
        expires_at=expires_at
    )

@router.get("/view/{file_id}")
@router.get("/view/{file_id}/")
async def view_file(
    file_id: str,
    request: Request,
    token: str = Query(...)
):
    # Validate token signature and expiration
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Temporary access link has expired")
    except jwt.JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid temporary access token signature")
        
    # Check that token file_id matches request file_id
    if payload.get("file_id") != file_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token is not valid for this file")
        
    try:
        file_oid = ObjectId(file_id)
    except:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file ID format")
        
    files_col = get_stored_files_collection()
    doc = await files_col.find_one({"_id": file_oid})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File metadata record not found")
        
    file_path = os.path.join("uploads", doc["filename"])
    if not os.path.exists(file_path):
        s3_client = get_s3_client()
        if s3_client:
            try:
                s3_client.download_file(settings.S3_BUCKET_NAME, doc["filename"], file_path)
            except ClientError:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found in S3 storage")
            except Exception as e:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to retrieve file from S3: {e}")
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Physical file does not exist on storage disk")
        
    # Log to audit trail
    user_id = payload.get("sub", "anonymous_downloader")
    
    # Try resolving user's name from db if possible, otherwise use a placeholder
    user_name = "Authorized Downloader"
    try:
        from database import get_users_collection
        user_doc = await get_users_collection().find_one({"_id": ObjectId(user_id)})
        if user_doc:
            user_name = user_doc.get("name", "Authorized Downloader")
    except:
        pass
        
    await create_audit_log(
        user_id=user_id,
        user_name=user_name,
        action="FILE_DOWNLOADED",
        entity="stored_files",
        entity_id=file_id,
        details={"original_name": doc["original_name"]},
        ip_address=request.client.host if request.client else None,
        tenant_id=doc["tenant_id"],
        branch_id=doc["branch_id"]
    )
    
    return FileResponse(
        file_path,
        media_type=doc["mime_type"],
        filename=doc["original_name"]
    )

@router.get("/files/{file_id}/download")
async def secure_file_download_proxy(
    file_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    try:
        file_oid = ObjectId(file_id)
    except:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file ID format")
        
    files_col = get_stored_files_collection()
    doc = await files_col.find_one({"_id": file_oid})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File metadata record not found")
        
    # Scoping checks
    if current_user.get("role") != "super_admin":
        if str(doc.get("tenant_id")) != str(current_user.get("tenant_id")):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: tenant mismatch")
        if doc.get("branch_id") and current_user.get("branch_id"):
            if str(doc.get("branch_id")) != str(current_user.get("branch_id")):
                if current_user.get("role") not in ["hospital_admin", "patient"]:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: branch mismatch")

    if current_user.get("role") == "patient":
        patient_docs_col = get_db().patient_documents
        patient_doc = await patient_docs_col.find_one({
            "$or": [
                {"file_url": {"$regex": file_id}},
                {"file_id": file_oid}
            ]
        })
        if patient_doc and str(patient_doc.get("patient_id")) != str(current_user["_id"]):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: you do not own this document")

    file_path = os.path.join("uploads", doc["filename"])
    if not os.path.exists(file_path):
        if "patients" in doc.get("filename", ""):
            file_path = doc["filename"]
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Physical file not found on disk")
            
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user.get("name", "User"),
        action="FILE_DOWNLOADED",
        entity="stored_files",
        entity_id=file_id,
        details={"original_name": doc.get("original_name")},
        ip_address=request.client.host if request.client else None,
        tenant_id=doc.get("tenant_id"),
        branch_id=doc.get("branch_id")
    )
    
    return FileResponse(
        file_path,
        media_type=doc.get("mime_type", "application/octet-stream"),
        filename=doc.get("original_name")
    )

@router.get("/files/{file_id}/preview")
async def secure_file_preview_proxy(
    file_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    try:
        file_oid = ObjectId(file_id)
    except:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file ID format")
        
    files_col = get_stored_files_collection()
    doc = await files_col.find_one({"_id": file_oid})
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File metadata record not found")
        
    # Scoping checks
    if current_user.get("role") != "super_admin":
        if str(doc.get("tenant_id")) != str(current_user.get("tenant_id")):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: tenant mismatch")
        if doc.get("branch_id") and current_user.get("branch_id"):
            if str(doc.get("branch_id")) != str(current_user.get("branch_id")):
                if current_user.get("role") not in ["hospital_admin", "patient"]:
                    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: branch mismatch")

    if current_user.get("role") == "patient":
        patient_docs_col = get_db().patient_documents
        patient_doc = await patient_docs_col.find_one({
            "$or": [
                {"file_url": {"$regex": file_id}},
                {"file_id": file_oid}
            ]
        })
        if patient_doc and str(patient_doc.get("patient_id")) != str(current_user["_id"]):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: you do not own this document")

    file_path = os.path.join("uploads", doc["filename"])
    if not os.path.exists(file_path):
        if "patients" in doc.get("filename", ""):
            file_path = doc["filename"]
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Physical file not found on disk")
            
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user.get("name", "User"),
        action="FILE_PREVIEWED",
        entity="stored_files",
        entity_id=file_id,
        details={"original_name": doc.get("original_name")},
        ip_address=request.client.host if request.client else None,
        tenant_id=doc.get("tenant_id"),
        branch_id=doc.get("branch_id")
    )
    
    return FileResponse(
        file_path,
        media_type=doc.get("mime_type", "application/octet-stream")
    )

from typing import Optional

async def resolve_secure_file(filename: str, token: Optional[str] = None):
    files_col = get_stored_files_collection()
    doc = await files_col.find_one({"filename": filename})
    if not doc:
        raise HTTPException(status_code=404, detail="File metadata not found")
        
    if settings.ENVIRONMENT == "production":
        if not token:
            raise HTTPException(status_code=401, detail="Authentication token required for secure file access")
        try:
            payload = jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
            if payload.get("file_id") != str(doc["_id"]):
                raise HTTPException(status_code=403, detail="Invalid token for this file")
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Temporary access link has expired")
        except jwt.JWTError:
            raise HTTPException(status_code=401, detail="Invalid temporary access token signature")
            
    file_path = os.path.join("uploads", filename)
    if not os.path.exists(file_path):
        s3_client = get_s3_client()
        if s3_client:
            try:
                s3_client.download_file(settings.S3_BUCKET_NAME, filename, file_path)
            except ClientError:
                raise HTTPException(status_code=404, detail="File not found in S3 storage")
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to retrieve file from S3: {e}")
        else:
            raise HTTPException(status_code=404, detail="Physical file does not exist on storage disk")
        
    return FileResponse(
        file_path,
        media_type=doc.get("mime_type", "application/octet-stream"),
        filename=doc.get("original_name")
    )

