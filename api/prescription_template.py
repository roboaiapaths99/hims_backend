from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from bson import ObjectId
from datetime import datetime
from typing import List, Optional

from database import (
    get_drug_directory_collection,
    get_prescription_templates_collection
)
from middleware.auth import get_current_user, inject_audit_fields
from middleware.audit import create_audit_log
from models.prescription_template import (
    PrescriptionTemplateCreate,
    PrescriptionTemplateResponse,
    TemplateMedication
)

router = APIRouter()

@router.get("/drugs/search")
async def search_drug_directory(
    q: Optional[str] = Query(None, min_length=1),
    current_user: dict = Depends(get_current_user)
):
    """Autosuggest/search common drugs and generic medicines from the CDSCO-seeded directory."""
    col = get_drug_directory_collection()
    if not q:
        # Return first 10 items
        cursor = col.find({}).limit(10)
    else:
        # Search by trade name or generic name (case-insensitive)
        query = {
            "$or": [
                {"name": {"$regex": q, "$options": "i"}},
                {"generic_name": {"$regex": q, "$options": "i"}}
            ]
        }
        cursor = col.find(query).limit(20)
        
    drugs = await cursor.to_list(None)
    result = []
    for d in drugs:
        result.append({
            "id": str(d["_id"]),
            "name": d.get("name"),
            "generic_name": d.get("generic_name"),
            "strength": d.get("strength"),
            "form": d.get("form"),
            "manufacturer": d.get("manufacturer")
        })
    return result

@router.post("/prescription-templates", response_model=PrescriptionTemplateResponse)
async def create_prescription_template(
    payload: PrescriptionTemplateCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Save a customized prescription template (reusable medication group) for the doctor."""
    col = get_prescription_templates_collection()
    
    tenant_oid = current_user["tenant_id"]
    doctor_oid = current_user["_id"]
    
    now = datetime.utcnow()
    template_doc = {
        "tenant_id": tenant_oid,
        "doctor_id": doctor_oid,
        "name": payload.name.strip(),
        "description": payload.description,
        "medications": [med.model_dump() for med in payload.medications],
        "created_at": now,
        "updated_at": now
    }
    
    res = await col.insert_one(template_doc)
    doc_id = str(res.inserted_id)
    
    await create_audit_log(
        user_id=str(doctor_oid),
        user_name=current_user["name"],
        action="PRESCRIPTION_TEMPLATE_CREATED",
        entity="prescription_templates",
        entity_id=doc_id,
        details={"template_name": payload.name},
        ip_address=request.client.host if request.client else None,
        tenant_id=tenant_oid,
        branch_id=current_user["branch_id"]
    )
    
    return PrescriptionTemplateResponse(
        id=doc_id,
        tenant_id=str(tenant_oid),
        doctor_id=str(doctor_oid),
        name=payload.name,
        description=payload.description,
        medications=payload.medications,
        created_at=now,
        updated_at=now
    )

@router.get("/prescription-templates", response_model=List[PrescriptionTemplateResponse])
async def list_prescription_templates(
    current_user: dict = Depends(get_current_user)
):
    """List all saved templates for the authenticated doctor."""
    col = get_prescription_templates_collection()
    
    tenant_oid = current_user["tenant_id"]
    doctor_oid = current_user["_id"]
    
    cursor = col.find({"tenant_id": tenant_oid, "doctor_id": doctor_oid})
    templates = await cursor.to_list(None)
    
    result = []
    for doc in templates:
        result.append(PrescriptionTemplateResponse(
            id=str(doc["_id"]),
            tenant_id=str(doc["tenant_id"]),
            doctor_id=str(doc["doctor_id"]),
            name=doc["name"],
            description=doc.get("description"),
            medications=[TemplateMedication(**med) for med in doc.get("medications", [])],
            created_at=doc["created_at"],
            updated_at=doc["updated_at"]
        ))
    return result

@router.get("/prescription-templates/{template_id}", response_model=PrescriptionTemplateResponse)
async def get_prescription_template(
    template_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Retrieve detailed metadata of a saved prescription template."""
    col = get_prescription_templates_collection()
    
    try:
        template_oid = ObjectId(template_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid template ID format")
        
    doc = await col.find_one({"_id": template_oid, "tenant_id": current_user["tenant_id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Prescription template not found")
        
    return PrescriptionTemplateResponse(
        id=str(doc["_id"]),
        tenant_id=str(doc["tenant_id"]),
        doctor_id=str(doc["doctor_id"]),
        name=doc["name"],
        description=doc.get("description"),
        medications=[TemplateMedication(**med) for med in doc.get("medications", [])],
        created_at=doc["created_at"],
        updated_at=doc["updated_at"]
    )
