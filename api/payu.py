from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from bson import ObjectId
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any

from database import (
    get_invoices_collection,
    get_payments_collection,
    get_payu_transactions_collection,
    get_patients_collection
)
from middleware.auth import (
    get_current_user,
    inject_audit_fields
)
from middleware.audit import create_audit_log
from config import settings
from models.payu import PayUCreateRequest, PayUCreateResponse

router = APIRouter()

# Default test sandbox credentials if none provided
TEST_MERCHANT_KEY = "gtK42w"
TEST_MERCHANT_SALT = "eCwWELSp"

@router.post("/create-payment", response_model=PayUCreateResponse)
async def create_payment(
    payload: PayUCreateRequest,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    invoices_col = get_invoices_collection()
    payments_col = get_payments_collection()
    payu_tx_col = get_payu_transactions_collection()
    patients_col = get_patients_collection()
    
    # 1. Fetch and validate invoice
    try:
        invoice_oid = ObjectId(payload.invoice_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid invoice_id format")
        
    invoice = await invoices_col.find_one({"_id": invoice_oid, "tenant_id": current_user["tenant_id"]})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice record not found")
        
    # 2. Calculate balance due
    payments_history = await payments_col.find({"invoice_id": invoice_oid}).to_list(None)
    already_paid = sum(p.get("amount_paid", 0.0) for p in payments_history)
    balance_due = max(0.0, round(invoice["grand_total"] - already_paid, 2))
    
    if balance_due <= 0:
        raise HTTPException(status_code=400, detail="This invoice has already been fully paid")
        
    # Determine amount to pay
    amount_to_pay = balance_due
    if payload.amount is not None:
        if payload.amount <= 0 or payload.amount > balance_due + 0.01:
            raise HTTPException(status_code=400, detail=f"Amount must be between 0 and balance due (₹{balance_due})")
        amount_to_pay = payload.amount
        
    # 3. Load patient demographics for PayU payload
    patient = await patients_col.find_one({"_id": invoice["patient_id"]})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
        
    firstname = patient.get("first_name", "Patient")
    email = patient.get("email") or "patient@hmis.com"
    phone = patient.get("phone") or "9999999999"
    productinfo = f"HMIS Invoice {invoice['invoice_number']}"
    
    # 4. Generate transaction reference
    txnid = f"TXN_{ObjectId()}"
    
    # 5. Resolve PayU configs
    # Try fetching from branch payment settings first
    from database import get_branches_collection
    branches_col = get_branches_collection()
    branch = await branches_col.find_one({"_id": current_user.get("branch_id")}) if current_user.get("branch_id") else None
    pay_settings = branch.get("payment_settings", {}) if branch else {}
    
    key = pay_settings.get("payu_merchant_key") or settings.PAYU_MERCHANT_KEY or TEST_MERCHANT_KEY
    
    from services.secrets_vault import get_branch_secrets
    branch_secrets = await get_branch_secrets(current_user.get("branch_id"))
    salt = branch_secrets.get("payu_merchant_salt") or settings.PAYU_MERCHANT_SALT or TEST_MERCHANT_SALT
    env = pay_settings.get("payu_env") or settings.PAYU_ENV or "test"
    
    action_url = "https://secure.payu.in/_payment" if env == "production" else "https://test.payu.in/_payment"
    
    # Reconstruct server base url dynamically for callbacks
    base_url = str(request.base_url).rstrip('/')
    surl = f"{base_url}/api/payu/callback"
    furl = f"{base_url}/api/payu/callback"
    
    # Format amount to two decimals
    amount_str = f"{amount_to_pay:.2f}"
    
    # 6. Generate request hash
    # Formula: sha512(key|txnid|amount|productinfo|firstname|email|udf1|udf2|udf3|udf4|udf5||||||SALT)
    hash_sequence = f"{key}|{txnid}|{amount_str}|{productinfo}|{firstname}|{email}||||||||||{salt}"
    hash_val = hashlib.sha512(hash_sequence.encode('utf-8')).hexdigest().lower()
    
    # 7. Record transaction in database
    tx_doc = {
        "tenant_id": current_user["tenant_id"],
        "branch_id": current_user["branch_id"],
        "invoice_id": invoice_oid,
        "txnid": txnid,
        "amount": amount_to_pay,
        "status": "pending",
        "hash_sent": hash_val,
        "hash_received": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    inject_audit_fields(current_user, tx_doc)
    await payu_tx_col.insert_one(tx_doc)
    
    # 8. Return credentials
    return PayUCreateResponse(
        key=key,
        txnid=txnid,
        amount=amount_str,
        productinfo=productinfo,
        firstname=firstname,
        email=email,
        phone=phone,
        surl=surl,
        furl=furl,
        hash=hash_val,
        action_url=action_url
    )

@router.post("/callback")
async def payu_callback(request: Request):
    """Processes Form POST response redirect from PayU, verifies hash, logs payment, and redirects user to frontend success/failure."""
    form_data = await request.form()
    data = dict(form_data)
    
    txnid = data.get("txnid")
    status_val = data.get("status")
    received_hash = data.get("hash")
    
    if not txnid or not status_val or not received_hash:
        return HTMLResponse(
            content="<h3>Invalid Callback Request from Gateway: Missing Parameters</h3>",
            status_code=400
        )
        
    payu_tx_col = get_payu_transactions_collection()
    invoices_col = get_invoices_collection()
    payments_col = get_payments_collection()
    
    # Find matching transaction
    tx_doc = await payu_tx_col.find_one({"txnid": txnid})
    if not tx_doc:
        return HTMLResponse(
            content=f"<h3>Payment Transaction ID {txnid} not found in records</h3>",
            status_code=404
        )
        
    # Resolve salt using branch payment settings
    from database import get_branches_collection
    branches_col = get_branches_collection()
    branch = await branches_col.find_one({"_id": tx_doc.get("branch_id")}) if tx_doc.get("branch_id") else None
    pay_settings = branch.get("payment_settings", {}) if branch else {}
    from services.secrets_vault import get_branch_secrets
    branch_secrets = await get_branch_secrets(tx_doc.get("branch_id"))
    salt = branch_secrets.get("payu_merchant_salt") or settings.PAYU_MERCHANT_SALT or TEST_MERCHANT_SALT
    
    # Calculate response hash
    additional_charges = data.get("additionalCharges", "")
    key = data.get("key", "")
    firstname = data.get("firstname", "")
    email = data.get("email", "")
    productinfo = data.get("productinfo", "")
    amount = data.get("amount", "")
    
    udf1 = data.get("udf1", "")
    udf2 = data.get("udf2", "")
    udf3 = data.get("udf3", "")
    udf4 = data.get("udf4", "")
    udf5 = data.get("udf5", "")
    
    if additional_charges:
        hash_string = f"{additional_charges}|{salt}|{status_val}||||||{udf5}|{udf4}|{udf3}|{udf2}|{udf1}|{email}|{firstname}|{productinfo}|{amount}|{txnid}|{key}"
    else:
        hash_string = f"{salt}|{status_val}||||||{udf5}|{udf4}|{udf3}|{udf2}|{udf1}|{email}|{firstname}|{productinfo}|{amount}|{txnid}|{key}"
        
    calculated_hash = hashlib.sha512(hash_string.encode('utf-8')).hexdigest().lower()
    
    # Redirect URLs configured in settings
    success_redirect_base = settings.PAYU_SUCCESS_URL or "http://localhost:3000/payment/success"
    failure_redirect_base = settings.PAYU_FAILURE_URL or "http://localhost:3000/payment/failure"
    
    # Verify hash integrity
    if calculated_hash != received_hash.lower():
        # Invalid hash detection (possible tampering)
        await payu_tx_col.update_one(
            {"_id": tx_doc["_id"]},
            {"$set": {"status": "failed", "hash_received": received_hash, "updated_at": datetime.utcnow()}}
        )
        redirect_url = f"{failure_redirect_base}?invoice_id={tx_doc['invoice_id']}&txnid={txnid}&message=Signature+integrity+check+failed"
        return RedirectResponse(url=redirect_url, status_code=303)
        
    # Transaction is authentic
    invoice_oid = tx_doc["invoice_id"]
    invoice = await invoices_col.find_one({"_id": invoice_oid})
    if not invoice:
        redirect_url = f"{failure_redirect_base}?invoice_id={invoice_oid}&txnid={txnid}&message=Invoice+record+not+found"
        return RedirectResponse(url=redirect_url, status_code=303)
        
    if status_val == "success":
        # Check if this transaction has already been processed to prevent double logging
        if tx_doc.get("status") == "success":
            redirect_url = f"{success_redirect_base}?invoice_id={invoice_oid}&txnid={txnid}"
            return RedirectResponse(url=redirect_url, status_code=303)
            
        # Log payment record
        payment_doc = {
            "tenant_id": tx_doc["tenant_id"],
            "branch_id": tx_doc["branch_id"],
            "invoice_id": invoice_oid,
            "payment_method": "PayU",
            "amount_paid": tx_doc["amount"],
            "transaction_reference": txnid,
            "created_at": datetime.utcnow(),
            "created_by": str(tx_doc.get("created_by") or "system")
        }
        await payments_col.insert_one(payment_doc)
        
        # Calculate balance and update invoice status
        payments_history = await payments_col.find({"invoice_id": invoice_oid}).to_list(None)
        already_paid = sum(p.get("amount_paid", 0.0) for p in payments_history)
        
        if already_paid >= invoice["grand_total"]:
            new_status = "paid"
        else:
            new_status = "due"
            
        await invoices_col.update_one(
            {"_id": invoice_oid},
            {"$set": {"payment_status": new_status, "updated_at": datetime.utcnow(), "updated_by": str(tx_doc.get("created_by") or "system")}}
        )
        
        # Update transaction status
        await payu_tx_col.update_one(
            {"_id": tx_doc["_id"]},
            {"$set": {"status": "success", "hash_received": received_hash, "updated_at": datetime.utcnow()}}
        )
        
        # Create audit log
        await create_audit_log(
            user_id=str(tx_doc.get("created_by") or "system"),
            user_name="Online Patient Portal",
            action="PAYMENT_RECEIVED",
            entity="payments",
            entity_id=str(payment_doc.get("_id", txnid)),
            details={"invoice_id": str(invoice_oid), "amount_paid": tx_doc["amount"], "status": new_status, "channel": "PayU"},
            ip_address=request.client.host if request.client else None,
            tenant_id=tx_doc["tenant_id"],
            branch_id=tx_doc["branch_id"]
        )
        
        redirect_url = f"{success_redirect_base}?invoice_id={invoice_oid}&txnid={txnid}"
        return RedirectResponse(url=redirect_url, status_code=303)
        
    else:
        # Transaction failed
        await payu_tx_col.update_one(
            {"_id": tx_doc["_id"]},
            {"$set": {"status": "failed", "hash_received": received_hash, "updated_at": datetime.utcnow()}}
        )
        
        message = data.get("error_Message") or "Transaction failed or was cancelled by user"
        redirect_url = f"{failure_redirect_base}?invoice_id={invoice_oid}&txnid={txnid}&message={message}"
        return RedirectResponse(url=redirect_url, status_code=303)
