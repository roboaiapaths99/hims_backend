from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from bson import ObjectId
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from database import (
    get_invoices_collection,
    get_payments_collection,
    get_patients_collection,
    get_visits_collection,
    get_branches_collection,
    get_lab_orders_collection,
    get_pricing_items_collection
)
from middleware.auth import (
    get_current_user,
    get_tenant_filter,
    get_branch_filter,
    inject_audit_fields
)
from middleware.audit import create_audit_log
from models.invoice import (
    InvoiceCreate,
    InvoiceResponse,
    PaymentCreate,
    PaymentResponse,
    InvoiceItem
)

router = APIRouter()

async def generate_invoice_number(tenant_id: ObjectId, branch_id: ObjectId) -> str:
    """Generate sequential invoice number: [BRANCH_PREFIX]-INV-[YYYYMMDD]-[SEQUENCE]"""
    branches_col = get_branches_collection()
    branch = await branches_col.find_one({"_id": branch_id})
    if not branch:
        raise HTTPException(status_code=400, detail="Invalid branch profile specified")
    branch_prefix = branch.get("code", "HOSP").upper()
    
    today_str = datetime.utcnow().strftime("%Y%m%d")
    
    # Count invoices created today for this branch
    invoices_col = get_invoices_collection()
    start_date = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = datetime.utcnow().replace(hour=23, minute=59, second=59, microsecond=999999)
    
    today_count = await invoices_col.count_documents({
        "tenant_id": tenant_id,
        "branch_id": branch_id,
        "created_at": {"$gte": start_date, "$lte": end_date}
    })
    
    sequence_num = str(today_count + 1).zfill(4)
    return f"{branch_prefix}-INV-{today_str}-{sequence_num}"

@router.post("/invoices", response_model=InvoiceResponse)
async def create_invoice(
    payload: InvoiceCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    invoices_col = get_invoices_collection()
    patients_col = get_patients_collection()
    
    # Verify patient profile
    try:
        patient_oid = ObjectId(payload.patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient_id format")
        
    patient = await patients_col.find_one({"_id": patient_oid, "tenant_id": current_user["tenant_id"]})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
        
    # Verify discount authorization limits
    calc_subtotal = sum(item.base_price * item.quantity for item in payload.items)
    is_excessive_discount = False
    if calc_subtotal > 0 and (payload.discount_amount / calc_subtotal) > 0.10:
        is_excessive_discount = True
    for item in payload.items:
        if item.discount_percentage > 10.0:
            is_excessive_discount = True
            
    if is_excessive_discount:
        user_role = current_user.get("role")
        if user_role not in ["admin", "billing_manager"]:
            if payload.discount_approval_code != "MANAGER10":
                raise HTTPException(
                    status_code=403,
                    detail="Discounts exceeding 10% require approval from a billing manager or admin."
                )
                
    doc = payload.dict()
    inject_audit_fields(current_user, doc)
    
    doc["patient_id"] = patient_oid
    if payload.visit_id:
        try:
            doc["visit_id"] = ObjectId(payload.visit_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid visit_id format")
            
    # Recalculate line totals and aggregate subtotals on the server (prevention of FE tampering)
    subtotal = 0.0
    gst_total = 0.0
    taxable_subtotal = 0.0
    
    recalculated_items = []
    for item in payload.items:
        # Calculate line item discount
        discount_reduction = item.base_price * (item.discount_percentage / 100.0)
        net_price = item.base_price - discount_reduction
        taxable_line = net_price * item.quantity
        gst_tax = taxable_line * (item.gst_rate / 100.0)
        line_total = taxable_line + gst_tax
        
        # Format item values
        item_dict = item.dict()
        item_dict["tax_amount"] = round(gst_tax, 2)
        item_dict["line_total"] = round(line_total, 2)
        recalculated_items.append(item_dict)
        
        # Increment aggregates
        subtotal += round(item.base_price * item.quantity, 2)
        gst_total += round(gst_tax, 2)
        taxable_subtotal += round(taxable_line, 2)
        
    grand_total = max(0.0, round(taxable_subtotal + gst_total - payload.discount_amount, 2))
    
    doc["items"] = recalculated_items
    doc["subtotal"] = round(subtotal, 2)
    doc["gst_total"] = round(gst_total, 2)
    doc["grand_total"] = grand_total
    doc["payment_status"] = "unpaid"
    
    # Generate sequential invoice number
    doc["invoice_number"] = await generate_invoice_number(doc["tenant_id"], doc["branch_id"])
    
    res = await invoices_col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    doc["patient_id"] = str(doc["patient_id"])
    if doc.get("visit_id"):
        doc["visit_id"] = str(doc["visit_id"])
    doc["patient_name"] = f"{patient.get('first_name', '')} {patient.get('last_name', '')}"
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="INVOICE_CREATED",
        entity="invoices",
        entity_id=doc["id"],
        details={"invoice_number": doc["invoice_number"], "grand_total": doc["grand_total"]},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    return InvoiceResponse(**doc)

@router.get("/invoices", response_model=List[InvoiceResponse])
async def list_invoices(
    payment_status: Optional[str] = None,
    patient_id: Optional[str] = None,
    invoice_number: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    invoices_col = get_invoices_collection()
    patients_col = get_patients_collection()
    
    query = get_branch_filter(current_user)
    
    if payment_status:
        query["payment_status"] = payment_status
    if patient_id:
        try:
            query["patient_id"] = ObjectId(patient_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid patient_id format")
    if invoice_number:
        import re
        query["invoice_number"] = {"$regex": re.escape(invoice_number), "$options": "i"}
        
    docs = await invoices_col.find(query).sort("created_at", -1).to_list(None)
    result = []
    
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["branch_id"] = str(doc["branch_id"])
        
        # Populate patient details
        patient = await patients_col.find_one({"_id": doc["patient_id"]})
        if patient:
            doc["patient_name"] = f"{patient.get('first_name', '')} {patient.get('last_name', '')}"
        else:
            doc["patient_name"] = "Unknown Patient"
            
        doc["patient_id"] = str(doc["patient_id"])
        if doc.get("visit_id"):
            doc["visit_id"] = str(doc["visit_id"])
            
        result.append(InvoiceResponse(**doc))
        
    return result

@router.get("/invoices/{id}", response_model=InvoiceResponse)
async def get_invoice(id: str, current_user: dict = Depends(get_current_user)):
    invoices_col = get_invoices_collection()
    patients_col = get_patients_collection()
    
    try:
        invoice_oid = ObjectId(id)
    except:
        raise HTTPException(status_code=400, detail="Invalid invoice ID format")
        
    doc = await invoices_col.find_one({"_id": invoice_oid, "tenant_id": current_user["tenant_id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="Invoice record not found")
        
    doc["id"] = str(doc["_id"])
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    
    patient = await patients_col.find_one({"_id": doc["patient_id"]})
    if patient:
        doc["patient_name"] = f"{patient.get('first_name', '')} {patient.get('last_name', '')}"
    else:
        doc["patient_name"] = "Unknown Patient"
        
    doc["patient_id"] = str(doc["patient_id"])
    if doc.get("visit_id"):
        doc["visit_id"] = str(doc["visit_id"])
        
    return InvoiceResponse(**doc)

@router.post("/invoices/compile-draft")
async def compile_draft_charges(payload: dict, current_user: dict = Depends(get_current_user)):
    """Pre-fills consultation & lab charges for a patient's current visit or active IPD admission"""
    visit_id = payload.get("visit_id")
    patient_id = payload.get("patient_id")
    
    if not visit_id and not patient_id:
        raise HTTPException(status_code=400, detail="Either visit_id or patient_id parameter is required")
        
    draft_items = []
    patient_oid = None
    
    if visit_id:
        try:
            visit_oid = ObjectId(visit_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid visit_id format")
            
        visits_col = get_visits_collection()
        pricing_col = get_pricing_items_collection()
        labs_col = get_lab_orders_collection()
        
        visit = await visits_col.find_one({"_id": visit_oid, "tenant_id": current_user["tenant_id"]})
        if not visit:
            raise HTTPException(status_code=404, detail="Visit record profile not found")
            
        patient_oid = visit["patient_id"]
        
        # 1. Compile Consultation Fee from config registry
        consultation_fee = 500.0  # standard fallback
        pricing_item = None
        if visit.get("doctor_id"):
            # Look up doctor specific consultation charge
            pricing_item = await pricing_col.find_one({
                "tenant_id": current_user["tenant_id"],
                "item_type": "consultation",
                "doctor_id": str(visit["doctor_id"]),
                "is_active": True
            })
        if not pricing_item:
            # Look up generic department consultation charge
            pricing_item = await pricing_col.find_one({
                "tenant_id": current_user["tenant_id"],
                "item_type": "consultation",
                "doctor_id": None,
                "is_active": True
            })
        if pricing_item:
            consultation_fee = pricing_item["price"]
            
        draft_items.append({
            "description": "OPD Consultation Charge",
            "quantity": 1,
            "base_price": consultation_fee,
            "gst_rate": 0.0,
            "discount_percentage": 0.0
        })
        
        # 2. Compile Lab tests from orders
        lab_orders = await labs_col.find({"visit_id": visit_oid, "is_deleted": {"$ne": True}}).to_list(None)
        for order in lab_orders:
            for item in order.get("items", []):
                draft_items.append({
                    "description": f"Lab Test: {item.get('test_name')}",
                    "quantity": 1,
                    "base_price": item.get("price", 0.0),
                    "gst_rate": 0.0,  # diagnostic services are generally GST exempt
                    "discount_percentage": 0.0
                })
    else:
        try:
            patient_oid = ObjectId(patient_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid patient_id format")

    # 3. Compile IPD charges if patient is currently admitted
    from database import get_ipd_admissions_collection, get_ipd_charges_collection, get_rooms_collection
    ipd_col = get_ipd_admissions_collection()
    ipd_admission = await ipd_col.find_one({
        "patient_id": patient_oid,
        "status": "admitted",
        "tenant_id": current_user["tenant_id"]
    })
    if ipd_admission:
        # Calculate bed charges
        admission_date = ipd_admission["admission_date"]
        elapsed = datetime.utcnow() - admission_date
        days = max(1, elapsed.days)  # Minimum 1 day charge
        
        # Fetch room rate
        rooms_col = get_rooms_collection()
        room = await rooms_col.find_one({"_id": ipd_admission["room_id"]})
        room_rate = room.get("hourly_rate", 500.0) if room else 500.0
        room_number = room.get("room_number", "Ward") if room else "Ward"
        room_type = room.get("room_type", "General") if room else "General"
        
        draft_items.append({
            "description": f"IPD Room Bed Rent: {room_type} Room {room_number} ({days} days)",
            "quantity": days,
            "base_price": room_rate,
            "gst_rate": 0.0,
            "discount_percentage": 0.0
        })
        
        # Fetch all posted charges
        ipd_charges_col = get_ipd_charges_collection()
        ipd_charges = await ipd_charges_col.find({"admission_id": ipd_admission["_id"]}).to_list(None)
        for charge in ipd_charges:
            draft_items.append({
                "description": f"IPD Ledger: {charge.get('description')}",
                "quantity": 1,
                "base_price": charge.get("amount", 0.0),
                "gst_rate": charge.get("gst_rate", 0.0),
                "discount_percentage": 0.0
            })
            
    return {
        "patient_id": str(patient_oid),
        "visit_id": visit_id,
        "items": draft_items
    }

async def calculate_and_log_referral_commission(
    invoice_id: ObjectId, 
    tenant_id: ObjectId, 
    branch_id: ObjectId, 
    current_user: dict
):
    from database import get_db
    db = get_db()
    
    # 1. Fetch invoice
    invoice = await db.invoices.find_one({"_id": invoice_id})
    if not invoice:
        return
        
    # 2. Fetch patient
    patient_id = invoice.get("patient_id")
    if not patient_id:
        return
    patient = await db.patients.find_one({"_id": patient_id})
    if not patient:
        return
        
    referred_by_id = patient.get("referred_by_doctor_id")
    if not referred_by_id:
        return
        
    try:
        ref_doc_oid = ObjectId(referred_by_id)
    except:
        return
        
    # 3. Fetch referring doctor
    ref_doc = await db.referring_doctors.find_one({"_id": ref_doc_oid, "is_deleted": {"$ne": True}})
    if not ref_doc or not ref_doc.get("is_active", True):
        return
        
    # 4. Check duplicate transaction
    existing = await db.referral_transactions.find_one({
        "invoice_id": invoice_id,
        "referring_doctor_id": ref_doc_oid
    })
    if existing:
        return
        
    # 5. Compute commission per item
    commission_rules = ref_doc.get("commission_rules", [])
    rules_dict = {r["department_or_service"].lower(): r["percentage"] for r in commission_rules}
    
    total_commission = 0.0
    for item in invoice.get("items", []):
        desc = item.get("description", "").lower()
        dept = "other"
        if "lab" in desc or "test" in desc or "blood" in desc or "cbc" in desc:
            dept = "lab"
        elif "x-ray" in desc or "ct" in desc or "mri" in desc or "scan" in desc or "radiology" in desc or "ultrasound" in desc:
            dept = "radiology"
        elif "consultation" in desc or "opd" in desc or "visit" in desc or "checkup" in desc:
            dept = "consultation"
            
        percentage = rules_dict.get(dept, rules_dict.get("other", 0.0))
        item_total = item.get("line_total", 0.0)
        total_commission += item_total * (percentage / 100.0)
        
    if total_commission <= 0:
        return
        
    # 6. Insert transaction
    txn_doc = {
        "invoice_id": invoice_id,
        "referring_doctor_id": ref_doc_oid,
        "visit_id": invoice.get("visit_id"),
        "commission_amount": round(total_commission, 2),
        "payout_status": "pending",
        "paid_at": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "created_by": str(current_user["_id"]),
        "updated_by": str(current_user["_id"]),
        "tenant_id": tenant_id,
        "branch_id": branch_id
    }
    await db.referral_transactions.insert_one(txn_doc)

@router.post("/payments", response_model=PaymentResponse)
async def log_payment(
    payload: PaymentCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    payments_col = get_payments_collection()
    invoices_col = get_invoices_collection()
    
    # 1. Verify invoice profile
    try:
        invoice_oid = ObjectId(payload.invoice_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid invoice_id format")
        
    invoice = await invoices_col.find_one({"_id": invoice_oid, "tenant_id": current_user["tenant_id"]})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice record not found")
        
    # Calculate balance due
    payments_history = await payments_col.find({"invoice_id": invoice_oid}).to_list(None)
    already_paid = sum(p.get("amount_paid", 0.0) for p in payments_history)
    balance_due = max(0.0, round(invoice["grand_total"] - already_paid, 2))
    
    if balance_due <= 0:
        raise HTTPException(status_code=400, detail="This invoice has already been fully paid")
        
    # Ensure payment amount doesn't overflow grand total balance limits
    amount_to_pay = min(payload.amount_paid, balance_due)
    
    # Check advance payment mode
    if payload.payment_method.lower() == "advance":
        patients_col = get_patients_collection()
        patient_oid = invoice["patient_id"]
        patient = await patients_col.find_one({"_id": patient_oid})
        if not patient or patient.get("advance_balance", 0.0) < amount_to_pay:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient advance balance. Available: INR {patient.get('advance_balance', 0.0) if patient else 0.0}"
            )
            
        # Deduct from advance balance
        new_balance = round(patient["advance_balance"] - amount_to_pay, 2)
        await patients_col.update_one(
            {"_id": patient_oid},
            {"$set": {"advance_balance": new_balance, "updated_at": datetime.utcnow()}}
        )
        
        # Log to advance_payments
        adv_col = get_advance_payments_collection()
        adv_doc = {
            "patient_id": patient_oid,
            "amount": amount_to_pay,
            "payment_method": "Advance",
            "invoice_id": invoice_oid,
            "type": "usage",
            "created_at": datetime.utcnow()
        }
        inject_audit_fields(current_user, adv_doc)
        await adv_col.insert_one(adv_doc)
        
    # Log payment record
    doc = payload.dict()
    inject_audit_fields(current_user, doc)
    
    doc["invoice_id"] = invoice_oid
    doc["amount_paid"] = amount_to_pay
    
    res = await payments_col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    doc["invoice_id"] = str(doc["invoice_id"])
    
    # Update parent invoice status
    new_paid_total = round(already_paid + amount_to_pay, 2)
    if new_paid_total >= invoice["grand_total"]:
        new_status = "paid"
    else:
        new_status = "due"
        
    await invoices_col.update_one(
        {"_id": invoice_oid},
        {"$set": {"payment_status": new_status, "updated_at": datetime.utcnow(), "updated_by": str(current_user["_id"])}}
    )
    
    if new_status == "paid":
        try:
            await calculate_and_log_referral_commission(
                invoice_oid,
                ObjectId(invoice["tenant_id"]),
                ObjectId(invoice["branch_id"]),
                current_user
            )
        except Exception as e:
            print(f"Error calculating referral commission on invoice paid: {e}")
    
    # Queue billing payment confirmation notification
    try:
        from tasks import send_billing_notification
        send_billing_notification.delay(str(invoice_oid))
    except Exception as e:
        print(f"Error queuing background billing notification: {e}")
        
    try:
        from services.notification_service import NotificationService
        from database import get_patients_collection
        patients_col = get_patients_collection()
        patient = await patients_col.find_one({"_id": ObjectId(invoice["patient_id"])})
        patient_phone = patient.get("phone") if patient else None
        patient_push_token = patient.get("expo_push_token") if patient else None
        
        await NotificationService.dispatch(
            tenant_id=ObjectId(invoice["tenant_id"]),
            branch_id=ObjectId(invoice["branch_id"]),
            user_id=ObjectId(invoice["patient_id"]),
            title="Payment Received",
            message=f"A payment of INR {amount_to_pay} was successfully processed for invoice {invoice.get('invoice_number')}. Current status: {new_status.upper()}.",
            notification_type="success",
            phone_number=patient_phone,
            expo_push_token=patient_push_token
        )
    except Exception as ne:
        print(f"Error dispatching patient notification for payment: {ne}")
        
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="PAYMENT_RECEIVED",
        entity="payments",
        entity_id=doc["id"],
        details={"invoice_id": payload.invoice_id, "amount_paid": amount_to_pay, "status": new_status},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    return PaymentResponse(**doc)

@router.get("/invoices/{id}/payments", response_model=List[PaymentResponse])
async def get_invoice_payments(id: str, current_user: dict = Depends(get_current_user)):
    payments_col = get_payments_collection()
    
    try:
        invoice_oid = ObjectId(id)
    except:
        raise HTTPException(status_code=400, detail="Invalid invoice ID format")
        
    docs = await payments_col.find({"invoice_id": invoice_oid}).to_list(None)
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["branch_id"] = str(doc["branch_id"])
        doc["invoice_id"] = str(doc["invoice_id"])
        result.append(PaymentResponse(**doc))
        
    return result

from fastapi.responses import Response

@router.get("/invoices/{id}/pdf")
async def download_invoice_pdf(id: str, current_user: dict = Depends(get_current_user)):
    invoices_col = get_invoices_collection()
    patients_col = get_patients_collection()
    
    try:
        invoice_oid = ObjectId(id)
    except:
        raise HTTPException(status_code=400, detail="Invalid invoice ID format")
        
    invoice = await invoices_col.find_one({"_id": invoice_oid, "tenant_id": current_user["tenant_id"]})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
        
    patient = await patients_col.find_one({"_id": invoice["patient_id"]})
    patient_name = f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip() if patient else "Unknown Patient"
    
    invoice_num = invoice.get("invoice_number", "N/A")
    grand_total = invoice.get("grand_total", 0.0)
    status = invoice.get("payment_status", "due").upper()
    
    # Construct a valid minimal PDF 1.4 byte stream
    pdf_template = f"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 595 842] /Contents 5 0 R >>
endobj
4 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
5 0 obj
<< /Length 200 >>
stream
BT
/F1 20 Tf
50 750 Td
(HOSPITAL RECEIPT) Tj
/F1 12 Tf
0 -40 Td
(Invoice Number: {invoice_num}) Tj
0 -20 Td
(Patient Name: {patient_name}) Tj
0 -20 Td
(Grand Total: INR {grand_total}) Tj
0 -20 Td
(Payment Status: {status}) Tj
ET
endstream
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000056 00000 n 
0000000111 00000 n 
0000000244 00000 n 
0000000319 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
490
%%EOF"""
    
    headers = {
        "Content-Disposition": f"attachment; filename=invoice_{invoice_num}.pdf"
    }
    return Response(content=pdf_template, media_type="application/pdf", headers=headers)

class AdvanceDepositRequest(BaseModel):
    patient_id: str
    amount: float = Field(..., gt=0)
    payment_method: str
    transaction_reference: Optional[str] = None

class RefundRequest(BaseModel):
    patient_id: str
    invoice_id: Optional[str] = None
    amount: float = Field(..., gt=0)
    payment_method: str
    reason: str

@router.post("/advance-payment")
async def record_advance_payment(
    payload: AdvanceDepositRequest,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    from database import get_advance_payments_collection
    try:
        patient_oid = ObjectId(payload.patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient_id format")
        
    patients_col = get_patients_collection()
    patient = await patients_col.find_one({"_id": patient_oid, "tenant_id": current_user["tenant_id"]})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
        
    # Increment advance balance on patient record
    current_balance = patient.get("advance_balance", 0.0)
    new_balance = round(current_balance + payload.amount, 2)
    await patients_col.update_one(
        {"_id": patient_oid},
        {"$set": {"advance_balance": new_balance, "updated_at": datetime.utcnow()}}
    )
    
    # Log to advance_payments collection
    adv_col = get_advance_payments_collection()
    adv_doc = {
        "patient_id": patient_oid,
        "amount": payload.amount,
        "payment_method": payload.payment_method,
        "transaction_reference": payload.transaction_reference,
        "type": "deposit",
        "created_at": datetime.utcnow()
    }
    inject_audit_fields(current_user, adv_doc)
    await adv_col.insert_one(adv_doc)
    adv_doc["id"] = str(adv_doc["_id"])
    adv_doc["patient_id"] = str(adv_doc["patient_id"])
    adv_doc["tenant_id"] = str(adv_doc["tenant_id"])
    adv_doc["branch_id"] = str(adv_doc["branch_id"])
    
    # Also log inside payments for central tracking
    payments_col = get_payments_collection()
    pmt_doc = {
        "invoice_id": None,
        "payment_method": payload.payment_method,
        "amount_paid": payload.amount,
        "transaction_reference": payload.transaction_reference,
        "payment_type": "advance_deposit",
        "patient_id": patient_oid,
        "created_at": datetime.utcnow()
    }
    inject_audit_fields(current_user, pmt_doc)
    await payments_col.insert_one(pmt_doc)
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="ADVANCE_PAYMENT_DEPOSITED",
        entity="patients",
        entity_id=payload.patient_id,
        details={"amount": payload.amount, "new_balance": new_balance},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    return {"status": "success", "advance_balance": new_balance, "transaction": adv_doc}

@router.post("/refunds")
async def issue_refund(
    payload: RefundRequest,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    from database import get_advance_payments_collection
    try:
        patient_oid = ObjectId(payload.patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient_id format")
        
    patients_col = get_patients_collection()
    patient = await patients_col.find_one({"_id": patient_oid, "tenant_id": current_user["tenant_id"]})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
        
    payments_col = get_payments_collection()
    invoices_col = get_invoices_collection()
    
    if payload.invoice_id:
        # Invoice refund
        try:
            invoice_oid = ObjectId(payload.invoice_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid invoice_id format")
            
        invoice = await invoices_col.find_one({"_id": invoice_oid, "tenant_id": current_user["tenant_id"]})
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice record not found")
            
        # Check already paid amount
        payments_history = await payments_col.find({"invoice_id": invoice_oid}).to_list(None)
        already_paid = sum(p.get("amount_paid", 0.0) for p in payments_history)
        
        if payload.amount > already_paid:
            raise HTTPException(
                status_code=400,
                detail=f"Refund amount exceeds total paid amount of INR {already_paid}"
            )
            
        # Log negative payment in payments
        pmt_doc = {
            "invoice_id": invoice_oid,
            "payment_method": payload.payment_method,
            "amount_paid": -payload.amount,
            "transaction_reference": f"REFUND: {payload.reason[:30]}",
            "payment_type": "refund",
            "patient_id": patient_oid,
            "created_at": datetime.utcnow()
        }
        inject_audit_fields(current_user, pmt_doc)
        await payments_col.insert_one(pmt_doc)
        
        # Update invoice payment status to due or unpaid
        new_paid_total = round(already_paid - payload.amount, 2)
        if new_paid_total >= invoice["grand_total"]:
            new_status = "paid"
        elif new_paid_total > 0:
            new_status = "due"
        else:
            new_status = "unpaid"
            
        await invoices_col.update_one(
            {"_id": invoice_oid},
            {"$set": {"payment_status": new_status, "updated_at": datetime.utcnow(), "updated_by": str(current_user["_id"])}}
        )
        
    else:
        # Advance balance refund
        current_balance = patient.get("advance_balance", 0.0)
        if payload.amount > current_balance:
            raise HTTPException(
                status_code=400,
                detail=f"Refund amount exceeds available advance balance of INR {current_balance}"
            )
            
        new_balance = round(current_balance - payload.amount, 2)
        await patients_col.update_one(
            {"_id": patient_oid},
            {"$set": {"advance_balance": new_balance, "updated_at": datetime.utcnow()}}
        )
        
        # Log to advance_payments
        adv_col = get_advance_payments_collection()
        adv_doc = {
            "patient_id": patient_oid,
            "amount": -payload.amount,
            "payment_method": payload.payment_method,
            "type": "refund",
            "created_at": datetime.utcnow()
        }
        inject_audit_fields(current_user, adv_doc)
        await adv_col.insert_one(adv_doc)
        
        # Also log to payments
        pmt_doc = {
            "invoice_id": None,
            "payment_method": payload.payment_method,
            "amount_paid": -payload.amount,
            "transaction_reference": f"REFUND: {payload.reason[:30]}",
            "payment_type": "advance_refund",
            "patient_id": patient_oid,
            "created_at": datetime.utcnow()
        }
        inject_audit_fields(current_user, pmt_doc)
        await payments_col.insert_one(pmt_doc)
        
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="REFUND_ISSUED",
        entity="patients",
        entity_id=payload.patient_id,
        details={"amount": payload.amount, "invoice_id": payload.invoice_id},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    return {"status": "success", "refund_amount": payload.amount}

@router.get("/patients/{patient_id}/ledger")
async def get_patient_financial_ledger(
    patient_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        patient_oid = ObjectId(patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient_id format")
        
    from database import get_db
    db = get_db()
    
    # 1. Verify patient exists
    patient = await db.patients.find_one({"_id": patient_oid, "tenant_id": ObjectId(current_user["tenant_id"])})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
        
    # 2. Get all invoices for this patient
    invoices = await db.invoices.find({"patient_id": patient_oid}).to_list(None)
    
    # 3. Get all payments (including advance deposits, refunds)
    invoice_ids = [inv["_id"] for inv in invoices]
    
    payments = await db.payments.find({
        "$or": [
            {"patient_id": patient_oid},
            {"invoice_id": {"$in": invoice_ids}}
        ]
    }).to_list(None)
    
    # Collate entries
    ledger_entries = []
    
    for inv in invoices:
        ledger_entries.append({
            "date": inv["created_at"],
            "type": "debit",
            "entry_type": "Invoice Generated",
            "description": f"Invoice: {inv.get('invoice_number', 'N/A')}",
            "amount": inv["grand_total"],
            "reference_id": str(inv["_id"])
        })
        
    for p in payments:
        amount = p.get("amount_paid", 0.0)
        if amount > 0:
            ledger_entries.append({
                "date": p["created_at"],
                "type": "credit",
                "entry_type": p.get("payment_type", "Invoice Payment").replace("_", " ").title(),
                "description": f"Payment via {p.get('payment_method')}",
                "amount": amount,
                "reference_id": str(p["_id"])
            })
        else:
            ledger_entries.append({
                "date": p["created_at"],
                "type": "debit",
                "entry_type": p.get("payment_type", "Refund").replace("_", " ").title(),
                "description": f"Refund issued via {p.get('payment_method')}",
                "amount": abs(amount),
                "reference_id": str(p["_id"])
            })
            
    # Sort chronologically by date
    ledger_entries.sort(key=lambda x: x["date"])
    
    # Compute running balance
    running_balance = 0.0
    formatted_entries = []
    for entry in ledger_entries:
        if entry["type"] == "debit":
            running_balance += entry["amount"]
        else:
            running_balance -= entry["amount"]
            
        entry["running_balance"] = round(running_balance, 2)
        entry["date"] = entry["date"].isoformat() if isinstance(entry["date"], datetime) else str(entry["date"])
        formatted_entries.append(entry)
        
    return {
        "patient": {
            "name": f"{patient.get('first_name', '')} {patient.get('last_name', '')}",
            "mrn": patient.get("mrn"),
            "advance_balance": patient.get("advance_balance", 0.0)
        },
        "entries": formatted_entries,
        "net_due": round(running_balance, 2)
    }


