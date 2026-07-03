from fastapi import APIRouter, Depends, HTTPException, status, Request
from bson import ObjectId
from datetime import datetime
import httpx
from typing import List

from config import settings
from database import get_ai_generated_summaries_collection, get_patients_collection
from middleware.auth import get_current_user, inject_audit_fields
from middleware.audit import create_audit_log
from models.ai import VisitSummarizeRequest, SimplifyInstructionsRequest, AISummaryResponse

router = APIRouter()

async def call_gemini_api(prompt: str) -> str:
    # Check if API key is valid / exists
    if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "your_gemini_api_key_here" or "mock" in settings.GEMINI_API_KEY.lower():
        raise ValueError("Mock fallback triggered due to missing/default API key")
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={settings.GEMINI_API_KEY}"
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ]
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=payload)
        if response.status_code != 200:
            raise ValueError(f"Gemini API returned error: {response.text}")
            
        data = response.json()
        try:
            generated_text = data["candidates"][0]["content"]["parts"][0]["text"]
            return generated_text.strip()
        except (KeyError, IndexError) as e:
            raise ValueError(f"Failed to parse Gemini response payload: {e}")

@router.post("/visit-summarize", response_model=AISummaryResponse)
@router.post("/visit-summarize/", response_model=AISummaryResponse)
async def visit_summarize(payload: VisitSummarizeRequest, request: Request, current_user: dict = Depends(get_current_user)):
    tenant_oid = current_user["tenant_id"]
    branch_oid = current_user["branch_id"]
    
    try:
        patient_oid = ObjectId(payload.patient_id)
    except:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid patient ID format")
        
    patients_col = get_patients_collection()
    patient = await patients_col.find_one({"_id": patient_oid, "tenant_id": tenant_oid})
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient record not found")
        
    # Construct the clinical prompt
    prompt = (
        f"You are a clinical medical assistant. Summarize the following consultation record for patient "
        f"named {patient.get('first_name', '')} {patient.get('last_name', '')}. "
        f"Symptoms: {payload.symptoms}. "
        f"Clinical Notes: {payload.clinical_notes}. "
        f"Diagnoses: {', '.join(payload.diagnosis)}. "
        f"Please provide a concise clinical summary for the patient's medical history."
    )
    
    try:
        generated_text = await call_gemini_api(prompt)
    except Exception as e:
        print(f"Gemini API invocation failed, using local mock fallback: {e}")
        # Rule-based fallback summary text
        generated_text = (
            f"Clinical Summary: Patient presented with {payload.symptoms}. "
            f"Notes describe: {payload.clinical_notes}. "
            f"Diagnosed with: {', '.join(payload.diagnosis)}."
        )
        
    doc = {
        "tenant_id": tenant_oid,
        "branch_id": branch_oid,
        "patient_id": patient_oid,
        "source_type": "notes",
        "generated_text": generated_text,
        "approved_by_doctor": False,
        "created_at": datetime.utcnow()
    }
    
    inject_audit_fields(current_user, doc)
    
    summaries_col = get_ai_generated_summaries_collection()
    res = await summaries_col.insert_one(doc)
    
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    doc["patient_id"] = str(doc["patient_id"])
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="AI_VISIT_SUMMARIZED",
        entity="ai_generated_summaries",
        entity_id=doc["id"],
        details={"patient_id": payload.patient_id, "source_type": "notes"},
        ip_address=request.client.host if request.client else None,
        tenant_id=tenant_oid,
        branch_id=branch_oid
    )
    
    return AISummaryResponse(**doc)

@router.post("/simplify-instructions", response_model=AISummaryResponse)
@router.post("/simplify-instructions/", response_model=AISummaryResponse)
async def simplify_instructions(payload: SimplifyInstructionsRequest, request: Request, current_user: dict = Depends(get_current_user)):
    tenant_oid = current_user["tenant_id"]
    branch_oid = current_user["branch_id"]
    
    try:
        patient_oid = ObjectId(payload.patient_id)
    except:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid patient ID format")
        
    patients_col = get_patients_collection()
    patient = await patients_col.find_one({"_id": patient_oid, "tenant_id": tenant_oid})
    if not patient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Patient record not found")
        
    # Construct the instruction simplification prompt
    prompt = (
        f"You are a patient coordinator. Simplify the following medical instructions to be jargon-free "
        f"and easy to understand for patient named {patient.get('first_name', '')} {patient.get('last_name', '')}. "
        f"Instructions: {payload.instructions}. "
        f"Translate and return the final simplified instructions in this target language: {payload.target_language}."
    )
    
    try:
        generated_text = await call_gemini_api(prompt)
    except Exception as e:
        print(f"Gemini API invocation failed, using local mock fallback: {e}")
        # Rule-based fallback instructions text
        generated_text = (
            f"Simplified instructions ({payload.target_language}): "
            f"Please make sure to follow: {payload.instructions}. "
            f"Take care of your health."
        )
        
    doc = {
        "tenant_id": tenant_oid,
        "branch_id": branch_oid,
        "patient_id": patient_oid,
        "source_type": "history",
        "generated_text": generated_text,
        "approved_by_doctor": False,
        "created_at": datetime.utcnow()
    }
    
    inject_audit_fields(current_user, doc)
    
    summaries_col = get_ai_generated_summaries_collection()
    res = await summaries_col.insert_one(doc)
    
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    doc["patient_id"] = str(doc["patient_id"])
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="AI_INSTRUCTIONS_SIMPLIFIED",
        entity="ai_generated_summaries",
        entity_id=doc["id"],
        details={"patient_id": payload.patient_id, "source_type": "history"},
        ip_address=request.client.host if request.client else None,
        tenant_id=tenant_oid,
        branch_id=branch_oid
    )
    
    return AISummaryResponse(**doc)
