import logging
from datetime import datetime
from bson import ObjectId
from typing import Dict, Any
from database import (
    get_visits_collection,
    get_prescriptions_collection,
    get_lab_results_collection
)
from services.dms_bridge_service import dms_bridge
from config import settings

logger = logging.getLogger(__name__)

async def sync_visit_to_dms(visit_id: str) -> Dict[str, Any]:
    if not settings.DMS_INTEGRATION_ENABLED:
        return {"success": False, "error": "DMS integration is disabled"}
        
    try:
        v_oid = ObjectId(visit_id)
    except:
        return {"success": False, "error": "Invalid visit ID format"}
        
    visits_col = get_visits_collection()
    visit = await visits_col.find_one({"_id": v_oid})
    if not visit:
        return {"success": False, "error": "Visit not found"}
        
    # Get prescriptions
    presc_col = get_prescriptions_collection()
    prescriptions = []
    cursor = presc_col.find({"$or": [{"visit_id": v_oid}, {"visit_id": str(v_oid)}]})
    presc_list = await cursor.to_list(None)
    for p in presc_list:
        medicines = p.get("medicines") or []
        for m in medicines:
            prescriptions.append({
                "name": m.get("name") or m.get("medicine_name") or "Unknown",
                "dosage": m.get("dosage") or m.get("instructions") or "As directed",
                "duration": m.get("duration") or ""
            })
            
    # Get lab results
    lab_col = get_lab_results_collection()
    lab_results = []
    cursor = lab_col.find({"$or": [{"visit_id": v_oid}, {"visit_id": str(v_oid)}]})
    lab_list = await cursor.to_list(None)
    for l in lab_list:
        lab_results.append({
            "test_name": l.get("test_name") or l.get("parameter_name") or "Lab Parameter",
            "result": l.get("result_value") or l.get("result") or "Pending",
            "status": l.get("status") or "completed"
        })
        
    # Format payload
    diagnosis_data = visit.get("diagnosis") or []
    if isinstance(diagnosis_data, list):
        diagnosis_str = ", ".join([d.get("name") if isinstance(d, dict) else str(d) for d in diagnosis_data])
    else:
        diagnosis_str = str(diagnosis_data)
        
    payload = {
        "visit_id": str(visit["_id"]),
        "patient_id": str(visit["patient_id"]),
        "doctor_id": str(visit["doctor_id"]),
        "tenant_id": str(visit["tenant_id"]),
        "branch_id": str(visit["branch_id"]),
        "diagnosis": diagnosis_str,
        "prescriptions": prescriptions,
        "lab_results": lab_results,
        "notes": visit.get("clinical_notes") or visit.get("treatment_plan") or "",
        "record_date": visit.get("visit_date").isoformat() + "Z" if isinstance(visit.get("visit_date"), datetime) else str(visit.get("visit_date") or datetime.utcnow().isoformat())
    }
    
    res = await dms_bridge.upsert_clinical_record(payload)
    return res
