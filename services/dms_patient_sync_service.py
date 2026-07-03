import logging
from datetime import datetime
from bson import ObjectId
from typing import Union, Dict, Any
from database import get_patients_collection, get_dms_patient_sync_collection
from services.dms_bridge_service import dms_bridge
from config import settings

logger = logging.getLogger(__name__)

async def sync_patient_to_dms(patient_id: Union[str, ObjectId]) -> Dict[str, Any]:
    if not settings.DMS_INTEGRATION_ENABLED:
        return {"success": False, "status": "disabled", "error": "DMS integration is disabled."}
        
    p_oid = ObjectId(str(patient_id))
    patients_col = get_patients_collection()
    sync_col = get_dms_patient_sync_collection()
    
    patient = await patients_col.find_one({"_id": p_oid})
    if not patient:
        logger.error(f"Patient not found for DMS sync: {patient_id}")
        return {"success": False, "status": "failed", "error": "Patient not found."}
        
    # Get current sync record (if any) to read retry count
    sync_rec = await sync_col.find_one({"patient_id": p_oid})
    retry_count = sync_rec.get("retry_count", 0) if sync_rec else 0
    
    # Calculate age
    dob = patient.get("dob")
    age = 0
    if isinstance(dob, datetime):
        age = datetime.utcnow().year - dob.year
    elif isinstance(dob, str):
        try:
            parsed_dob = datetime.fromisoformat(dob.replace("Z", "+00:00"))
            age = datetime.utcnow().year - parsed_dob.year
            dob = parsed_dob
        except:
            age = 0
            
    payload = {
        "hims_patient_id": str(patient["_id"]),
        "mrn": patient.get("mrn", ""),
        "first_name": patient.get("first_name", ""),
        "last_name": patient.get("last_name", ""),
        "phone": patient.get("phone", ""),
        "dob": dob.isoformat() + "Z" if isinstance(dob, datetime) else str(dob),
        "age": age,
        "gender": patient.get("gender", "Other"),
        "tenant_id": str(patient["tenant_id"]),
        "branch_id": str(patient["branch_id"]),
        "abha_number": patient.get("abha_number"),
        "abha_address": patient.get("abha_address"),
        "updated_at": datetime.utcnow().isoformat() + "Z"
    }
    
    # Call bridge
    res = await dms_bridge.upsert_patient(payload)
    now = datetime.utcnow()
    
    if res.get("success"):
        dms_patient_id = res["data"]["data"]["dms_patient_id"]
        sync_data = {
            "tenant_id": patient["tenant_id"],
            "branch_id": patient["branch_id"],
            "patient_id": p_oid,
            "mrn": patient.get("mrn", ""),
            "dms_patient_id": dms_patient_id,
            "sync_status": "synced",
            "last_synced_at": now,
            "last_error": None,
            "retry_count": 0,
            "updated_at": now
        }
        await sync_col.update_one(
            {"patient_id": p_oid},
            {"$set": sync_data, "$setOnInsert": {"created_at": now}},
            upsert=True
        )
        return {"success": True, "status": "synced", "dms_patient_id": dms_patient_id}
    else:
        error_msg = res.get("error", "Unknown bridge error")
        sync_data = {
            "tenant_id": patient["tenant_id"],
            "branch_id": patient["branch_id"],
            "patient_id": p_oid,
            "mrn": patient.get("mrn", ""),
            "sync_status": "failed",
            "last_synced_at": now,
            "last_error": error_msg,
            "retry_count": retry_count + 1,
            "updated_at": now
        }
        await sync_col.update_one(
            {"patient_id": p_oid},
            {"$set": sync_data, "$setOnInsert": {"created_at": now}},
            upsert=True
        )
        return {"success": False, "status": "failed", "error": error_msg}
