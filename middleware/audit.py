from datetime import datetime
from bson import ObjectId
from typing import Any, Optional
from database import get_audit_logs_collection

async def create_audit_log(
    user_id: str,
    user_name: str,
    action: str,
    entity: str,
    entity_id: str,
    details: Optional[Any] = None,
    ip_address: Optional[str] = None,
    tenant_id: Optional[ObjectId] = None,
    branch_id: Optional[ObjectId] = None
):
    try:
        audit_col = get_audit_logs_collection()
        log_doc = {
            "user_id": user_id,
            "user_name": user_name,
            "action": action,
            "entity": entity,
            "entity_id": entity_id,
            "details": details,
            "ip_address": ip_address or "127.0.0.1",
            "tenant_id": tenant_id,
            "branch_id": branch_id,
            "timestamp": datetime.utcnow()
        }
        await audit_col.insert_one(log_doc)
    except Exception as e:
        # Avoid blocking standard business operations on audit log insertion failure
        print(f"Failed to record audit log: {e}")
