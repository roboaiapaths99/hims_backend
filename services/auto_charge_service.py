"""
Auto-Charge Capture Service

When Lab, Radiology, or Pharmacy orders are created, this service automatically 
posts corresponding billing line items to the patient's running invoice (or creates 
a new draft invoice if none exists).

This eliminates the need for manual billing data entry — charges flow from clinical
workflows directly into the billing module.
"""

from bson import ObjectId
from datetime import datetime
from typing import List, Dict, Optional

from database import (
    get_invoices_collection,
    get_patients_collection,
    get_db
)


async def post_auto_charges(
    tenant_id,
    branch_id,
    patient_id,
    visit_id: Optional[str],
    line_items: List[Dict],
    source: str,
    source_order_id: str,
    created_by: str,
    created_by_name: str
):
    """
    Post auto-generated billing line items to the patient's draft invoice.
    
    If a draft invoice already exists for this patient + visit, append items.
    Otherwise, create a new draft invoice.
    
    Args:
        tenant_id: Tenant ObjectId
        branch_id: Branch ObjectId  
        patient_id: Patient ObjectId
        visit_id: Visit ID string (optional)
        line_items: List of dicts with keys: description, quantity, base_price, gst_rate
        source: Source module (e.g., "lab", "radiology", "pharmacy")
        source_order_id: The originating order ID for traceability
        created_by: Staff user ID
        created_by_name: Staff user name
    """
    if not line_items:
        return None

    invoices_col = get_invoices_collection()
    
    # Ensure ObjectId types
    tenant_oid = ObjectId(tenant_id) if isinstance(tenant_id, str) else tenant_id
    branch_oid = ObjectId(branch_id) if isinstance(branch_id, str) else branch_id
    patient_oid = ObjectId(patient_id) if isinstance(patient_id, str) else patient_id
    visit_oid = ObjectId(visit_id) if visit_id else None
    
    now = datetime.utcnow()
    
    # Compute line totals with GST
    computed_items = []
    for item in line_items:
        qty = item.get("quantity", 1)
        base_price = item.get("base_price", 0.0)
        gst_rate = item.get("gst_rate", 0.0)
        discount_pct = item.get("discount_percentage", 0.0)
        
        subtotal = base_price * qty
        discount_amt = subtotal * (discount_pct / 100.0)
        taxable = subtotal - discount_amt
        tax_amount = round(taxable * (gst_rate / 100.0), 2)
        line_total = round(taxable + tax_amount, 2)
        
        computed_items.append({
            "description": item.get("description", f"{source.title()} charge"),
            "quantity": qty,
            "base_price": base_price,
            "gst_rate": gst_rate,
            "discount_percentage": discount_pct,
            "tax_amount": tax_amount,
            "line_total": line_total,
            "auto_source": source,
            "source_order_id": source_order_id
        })
    
    # Try to find an existing draft invoice for this patient + visit
    draft_query = {
        "tenant_id": tenant_oid,
        "branch_id": branch_oid,
        "patient_id": patient_oid,
        "payment_status": "unpaid"
    }
    if visit_oid:
        draft_query["visit_id"] = visit_oid
    
    existing_draft = await invoices_col.find_one(draft_query, sort=[("created_at", -1)])
    
    if existing_draft:
        # Append items to existing draft invoice
        existing_items = existing_draft.get("items", [])
        all_items = existing_items + computed_items
        
        # Recalculate totals
        subtotal = sum(
            i.get("base_price", 0) * i.get("quantity", 1) for i in all_items
        )
        gst_total = sum(i.get("tax_amount", 0) for i in all_items)
        discount_amount = existing_draft.get("discount_amount", 0.0)
        grand_total = round(subtotal + gst_total - discount_amount, 2)
        
        await invoices_col.update_one(
            {"_id": existing_draft["_id"]},
            {
                "$set": {
                    "items": all_items,
                    "subtotal": round(subtotal, 2),
                    "gst_total": round(gst_total, 2),
                    "grand_total": grand_total,
                    "updated_at": now,
                    "updated_by": created_by
                }
            }
        )
        return str(existing_draft["_id"])
    else:
        # Create new draft invoice
        subtotal = sum(
            i.get("base_price", 0) * i.get("quantity", 1) for i in computed_items
        )
        gst_total = sum(i.get("tax_amount", 0) for i in computed_items)
        grand_total = round(subtotal + gst_total, 2)
        
        # Generate invoice number
        db = get_db()
        counter = await db.invoice_counters.find_one_and_update(
            {"branch_id": branch_oid},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=True
        )
        seq = counter.get("seq", 1)
        invoice_number = f"INV-{now.strftime('%Y%m%d')}-{str(seq).zfill(5)}"
        
        # Resolve patient name
        patients_col = get_patients_collection()
        patient_doc = await patients_col.find_one({"_id": patient_oid})
        patient_name = ""
        if patient_doc:
            patient_name = f"{patient_doc.get('first_name', '')} {patient_doc.get('last_name', '')}".strip()
        
        invoice_doc = {
            "tenant_id": tenant_oid,
            "branch_id": branch_oid,
            "patient_id": patient_oid,
            "visit_id": visit_oid,
            "invoice_number": invoice_number,
            "items": computed_items,
            "subtotal": round(subtotal, 2),
            "gst_total": round(gst_total, 2),
            "discount_amount": 0.0,
            "grand_total": grand_total,
            "payment_status": "unpaid",
            "auto_generated": True,
            "auto_source": source,
            "patient_name": patient_name,
            "created_at": now,
            "updated_at": now,
            "created_by": created_by,
            "updated_by": created_by,
            "created_by_name": created_by_name
        }
        
        result = await invoices_col.insert_one(invoice_doc)
        return str(result.inserted_id)
