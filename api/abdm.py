from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from typing import Optional, Dict
from datetime import datetime
import httpx

from config import settings
from database import get_patients_collection
from middleware.auth import get_current_user
from bson import ObjectId

router = APIRouter()

# Schemas
class VerifyAbhaRequest(BaseModel):
    abha_number: str

class LinkAbhaRequest(BaseModel):
    patient_id: str
    abha_number: str
    otp: str

class ScanShareRequest(BaseModel):
    qr_data: str

# In-memory storage for active OTP transactions (simulating redis or stateful session)
# Key: abha_number, Value: transaction_id (or mock mapping)
abha_sessions = {}

async def get_abdm_token() -> Optional[str]:
    """Retrieves access token from official ABDM Gateway if credentials are set"""
    if not settings.ABDM_CLIENT_ID or not settings.ABDM_CLIENT_SECRET:
        return None
        
    url = f"{settings.ABDM_GATEWAY_URL}/v0.5/sessions"
    payload = {
        "clientId": settings.ABDM_CLIENT_ID,
        "clientSecret": settings.ABDM_CLIENT_SECRET
    }
    
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(url, json=payload, timeout=5.0)
            if res.status_code == 200:
                return res.json().get("accessToken")
    except Exception as e:
        print(f"ABDM Token fetch failed: {e}")
    return None

@router.post("/verify-abha")
async def verify_abha(payload: VerifyAbhaRequest, current_user: dict = Depends(get_current_user)):
    """Initiates ABHA verification - requests OTP via SMS"""
    token = await get_abdm_token()
    
    # Clean ABHA input (remove dashes)
    abha_clean = payload.abha_number.replace("-", "").strip()
    
    if not token:
        # Mock Sandbox Gateway Mode
        # Generate and save a mock transaction ID
        mock_txn_id = f"mock-txn-{ObjectId()}"
        abha_sessions[abha_clean] = {
            "txn_id": mock_txn_id,
            "abha_number": payload.abha_number,
            "timestamp": datetime.utcnow()
        }
        return {
            "status": "success",
            "message": "OTP has been sent to the mobile number registered with Aadhaar (Sandbox Mock Mode)",
            "transaction_id": mock_txn_id,
            "is_mock": True
        }
        
    # Real ABDM Integration
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-CM-ID": "sbx" # Sandbox Consent Manager ID
    }
    
    # Step 1: Initialize auth with Aadhaar OTP or Mobile OTP
    init_url = f"{settings.ABDM_GATEWAY_URL}/v1/auth/init"
    init_payload = {
        "authMethod": "MOBILE_OTP",
        "healthid": payload.abha_number
    }
    
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(init_url, json=init_payload, headers=headers, timeout=10.0)
            if res.status_code != 200:
                raise HTTPException(
                    status_code=res.status_code,
                    detail=f"ABDM Gateway Error: {res.text}"
                )
                
            data = res.json()
            txn_id = data.get("transactionId")
            
            abha_sessions[abha_clean] = {
                "txn_id": txn_id,
                "abha_number": payload.abha_number,
                "timestamp": datetime.utcnow()
            }
            
            return {
                "status": "success",
                "message": "OTP has been sent to patient's registered mobile number",
                "transaction_id": txn_id,
                "is_mock": False
            }
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"ABDM Gateway unreachable: {e}"
        )

@router.post("/link-abha")
async def link_abha(payload: LinkAbhaRequest, current_user: dict = Depends(get_current_user)):
    """Confirms OTP from user and maps verification metadata to the Patient profile"""
    patients_col = get_patients_collection()
    
    try:
        patient_oid = ObjectId(payload.patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient ID format")
        
    # Find patient
    patient = await patients_col.find_one({"_id": patient_oid})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
        
    abha_clean = payload.abha_number.replace("-", "").strip()
    session = abha_sessions.get(abha_clean)
    
    token = await get_abdm_token()
    
    if not token or (session and "mock-txn" in session["txn_id"]):
        # Mock Sandbox Gateway Completion Mode
        # Validate sandbox mock OTP code (always verify '123456' or any 6-digit number)
        if len(payload.otp) != 6:
            raise HTTPException(status_code=400, detail="Invalid OTP length. Enter a 6-digit numeric OTP.")
            
        # Update Patient
        update_data = {
            "abha_number": payload.abha_number,
            "abha_address": f"{patient['first_name'].lower()}{patient['last_name'].lower()}@abdm",
            "consent_signed": True,
            "updated_at": datetime.utcnow()
        }
        
        await patients_col.update_one({"_id": patient_oid}, {"$set": update_data})
        
        # Clean up session
        if abha_clean in abha_sessions:
            del abha_sessions[abha_clean]
            
        return {
            "status": "success",
            "message": "ABHA verification completed successfully (Sandbox Mock Mode)",
            "abha_number": payload.abha_number,
            "abha_address": update_data["abha_address"],
            "is_mock": True
        }
        
    # Real ABDM Integration OTP confirmation
    if not session:
        raise HTTPException(status_code=400, detail="No active verification request found for this ABHA number")
        
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-CM-ID": "sbx"
    }
    
    confirm_url = f"{settings.ABDM_GATEWAY_URL}/v1/auth/confirmWithMobileOTP"
    confirm_payload = {
        "otp": payload.otp,
        "transactionId": session["txn_id"]
    }
    
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(confirm_url, json=confirm_payload, headers=headers, timeout=10.0)
            if res.status_code != 200:
                raise HTTPException(
                    status_code=res.status_code,
                    detail=f"ABDM Verification Failed: {res.text}"
                )
                
            confirm_data = res.json()
            
            # Fetch patient profile details returned by ABDM
            # Extract ABHA details
            user_profile = confirm_data.get("profile", {})
            health_id_number = user_profile.get("healthIdNumber", payload.abha_number)
            phr_address = user_profile.get("healthId", f"{patient['first_name'].lower()}@abdm")
            
            # Sync fields
            update_data = {
                "abha_number": health_id_number,
                "abha_address": phr_address,
                "consent_signed": True,
                "updated_at": datetime.utcnow()
            }
            
            await patients_col.update_one({"_id": patient_oid}, {"$set": update_data})
            
            if abha_clean in abha_sessions:
                del abha_sessions[abha_clean]
                
            return {
                "status": "success",
                "message": "ABHA profile linked successfully under ABDM Consent manager",
                "abha_number": health_id_number,
                "abha_address": phr_address,
                "is_mock": False
            }
            
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"ABDM Gateway communication failure: {e}"
        )

@router.post("/scan-share")
async def scan_share(payload: ScanShareRequest, current_user: dict = Depends(get_current_user)):
    """
    Decodes an ABDM Scan & Share QR code payload.
    ABDM QR code data contains JSON payload including patient's basic details:
    { "hid": "abha-number", "phr": "abha-address", "name": "Name", "gender": "M/F", "dob": "DD/MM/YYYY" }
    """
    import json
    try:
        # Check if the qr_data is raw string JSON
        parsed_data = json.loads(payload.qr_data)
    except:
        # Standard ABDM QR Code formats might use custom XML or simple comma-separated key-value
        # For compatibility, parse simple key-value pairings if json parsing fails
        parsed_data = {}
        items = payload.qr_data.split(",")
        for item in items:
            if "=" in item:
                k, v = item.split("=", 1)
                parsed_data[k.strip().lower()] = v.strip()

    # Normalize fields from ABDM schema standard (hid, name, gender, dob, phr, mobile)
    raw_name = parsed_data.get("name") or parsed_data.get("first_name") or "Unknown"
    name_parts = raw_name.split(" ", 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else "Patient"
    
    raw_gender = parsed_data.get("gender") or parsed_data.get("g") or "Other"
    gender = "Male" if raw_gender.startswith("M") else "Female" if raw_gender.startswith("F") else "Other"
    
    # Parse DOB (e.g. DD/MM/YYYY or YYYY-MM-DD or DDMMYYYY)
    dob_str = parsed_data.get("dob") or parsed_data.get("d") or "1990-01-01"
    parsed_dob = None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d%m%Y"):
        try:
            parsed_dob = datetime.strptime(dob_str, fmt)
            break
        except:
            continue
            
    if not parsed_dob:
        parsed_dob = datetime(1990, 1, 1)

    return {
        "first_name": first_name,
        "last_name": last_name,
        "phone": parsed_data.get("mobile") or parsed_data.get("phone") or "",
        "gender": gender,
        "dob": parsed_dob.isoformat(),
        "abha_number": parsed_data.get("hid") or parsed_data.get("abha_number") or "",
        "abha_address": parsed_data.get("phr") or parsed_data.get("abha_address") or "",
        "address": parsed_data.get("address") or parsed_data.get("dist") or ""
    }

@router.get("/profile")
async def get_abha_profile(current_user: dict = Depends(get_current_user)):
    """Retrieves patient's linked ABHA profile details"""
    patient_id = current_user.get("id")
    if not patient_id or current_user.get("role") != "patient":
        patient_id = str(current_user.get("_id"))
        
    patients_col = get_patients_collection()
    try:
        patient = await patients_col.find_one({"_id": ObjectId(patient_id)})
    except:
        patient = None
        
    if not patient:
         raise HTTPException(status_code=404, detail="Patient profile not found")
         
    return {
        "abha_number": patient.get("abha_number"),
        "abha_address": patient.get("abha_address"),
        "name": f"{patient.get('first_name', '')} {patient.get('last_name', '')}",
        "gender": patient.get("gender"),
        "dob": patient.get("dob").isoformat() if isinstance(patient.get("dob"), datetime) else patient.get("dob")
    }

