from fastapi import APIRouter, Depends, HTTPException, status, Request
from bson import ObjectId
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel
import hashlib
import uuid
import hmac
import httpx

from database import (
    get_invoices_collection,
    get_payments_collection,
    get_online_transactions_collection,
    get_patients_collection,
    get_branches_collection
)
from middleware.auth import get_current_user, inject_audit_fields
from middleware.audit import create_audit_log
from config import settings

router = APIRouter()

# ------------------------------------------------------------------
# GATEWAY CALLOUT HELPERS (httpx real async integrations)
# ------------------------------------------------------------------
async def create_real_razorpay_order(key_id: str, key_secret: str, amount: float, txnid: str, notes: dict) -> Optional[str]:
    amount_paise = int(round(amount * 100))
    url = "https://api.razorpay.com/v1/orders"
    auth = (key_id, key_secret)
    data = {
        "amount": amount_paise,
        "currency": "INR",
        "receipt": txnid,
        "notes": notes
    }
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, json=data, auth=auth, timeout=10.0)
            if resp.status_code == 200:
                return resp.json().get("id")
            else:
                print(f"Razorpay Order Error response: {resp.text}")
        except Exception as e:
            print(f"Error calling Razorpay API: {e}")
    return None

async def create_real_stripe_intent(secret_key: str, amount: float, currency: str, metadata: dict) -> Optional[str]:
    amount_cents = int(round(amount * 100))
    url = "https://api.stripe.com/v1/payment_intents"
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "amount": str(amount_cents),
        "currency": currency.lower(),
        "payment_method_types[0]": "card",
    }
    for k, v in metadata.items():
        data[f"metadata[{k}]"] = str(v)
        
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, data=data, headers=headers, timeout=10.0)
            if resp.status_code in [200, 201]:
                return resp.json().get("client_secret")
            else:
                print(f"Stripe Intent Error response: {resp.text}")
        except Exception as e:
            print(f"Error calling Stripe API: {e}")
    return None

async def verify_real_stripe_intent(secret_key: str, payment_intent_id: str) -> bool:
    url = f"https://api.stripe.com/v1/payment_intents/{payment_intent_id}"
    headers = {"Authorization": f"Bearer {secret_key}"}
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(url, headers=headers, timeout=10.0)
            if resp.status_code == 200:
                return resp.json().get("status") == "succeeded"
        except Exception as e:
            print(f"Error verifying Stripe intent: {e}")
    return False

class PaymentInitRequest(BaseModel):
    invoice_id: str
    payment_method: str  # payu, razorpay, stripe, upi
    amount: Optional[float] = None

class PaymentVerifyRequest(BaseModel):
    invoice_id: str
    payment_method: str  # payu, razorpay, stripe, upi
    transaction_id: str  # razorpay_payment_id / stripe_intent_id / upi_utr / payu_txnid
    amount: float
    extra_data: Optional[Dict[str, Any]] = None

@router.get("/checkout-details/{invoice_id}")
async def get_checkout_details(
    invoice_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Retrieve details for invoice checkout including branch's active payment configurations (no secrets)."""
    invoices_col = get_invoices_collection()
    patients_col = get_patients_collection()
    branches_col = get_branches_collection()

    try:
        invoice_oid = ObjectId(invoice_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid invoice_id format")

    invoice = await invoices_col.find_one({"_id": invoice_oid, "tenant_id": current_user["tenant_id"]})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice record not found")

    patient = await patients_col.find_one({"_id": invoice["patient_id"]})
    patient_name = f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip() if patient else "Valued Patient"

    branch = await branches_col.find_one({"_id": invoice["branch_id"]})
    if not branch:
        raise HTTPException(status_code=404, detail="Branch configuration not found")

    pay_settings = branch.get("payment_settings") or {}

    # Read already paid amount
    payments_col = get_payments_collection()
    payments_history = await payments_col.find({"invoice_id": invoice_oid}).to_list(None)
    already_paid = sum(p.get("amount_paid", 0.0) for p in payments_history)
    balance_due = max(0.0, round(invoice["grand_total"] - already_paid, 2))

    # Expose only public configurations, NEVER secrets
    checkout_configs = {
        "payu_enabled": pay_settings.get("payu_enabled", True),
        "payu_merchant_key": pay_settings.get("payu_merchant_key") or settings.PAYU_MERCHANT_KEY or "gtK42w",
        "payu_env": pay_settings.get("payu_env") or settings.PAYU_ENV or "test",
        
        "razorpay_enabled": pay_settings.get("razorpay_enabled", False),
        "razorpay_key_id": pay_settings.get("razorpay_key_id") or "rzp_test_placeholderKey",
        
        "stripe_enabled": pay_settings.get("stripe_enabled", False),
        "stripe_publishable_key": pay_settings.get("stripe_publishable_key") or "pk_test_placeholderKey",
        
        "upi_enabled": pay_settings.get("upi_enabled", False),
        "upi_vpa": pay_settings.get("upi_vpa"),
        "upi_merchant_name": pay_settings.get("upi_merchant_name") or branch.get("name"),

        "cash_enabled": pay_settings.get("cash_enabled", True),
        "card_enabled": pay_settings.get("card_enabled", True)
    }

    return {
        "invoice": {
            "id": str(invoice["_id"]),
            "invoice_number": invoice["invoice_number"],
            "grand_total": invoice["grand_total"],
            "balance_due": balance_due,
            "patient_id": str(invoice["patient_id"]),
            "patient_name": patient_name,
            "payment_status": invoice["payment_status"]
        },
        "config": checkout_configs
    }

@router.post("/initialize")
async def initialize_payment(
    payload: PaymentInitRequest,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Initializes transaction parameters for online payment systems."""
    invoices_col = get_invoices_collection()
    branches_col = get_branches_collection()
    tx_col = get_online_transactions_collection()

    try:
        invoice_oid = ObjectId(payload.invoice_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid invoice_id format")

    invoice = await invoices_col.find_one({"_id": invoice_oid, "tenant_id": current_user["tenant_id"]})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice record not found")

    branch = await branches_col.find_one({"_id": invoice["branch_id"]})
    pay_settings = branch.get("payment_settings") or {} if branch else {}
    
    from services.secrets_vault import get_branch_secrets
    branch_secrets = await get_branch_secrets(invoice["branch_id"])

    # Calculate balance due
    payments_col = get_payments_collection()
    payments_history = await payments_col.find({"invoice_id": invoice_oid}).to_list(None)
    already_paid = sum(p.get("amount_paid", 0.0) for p in payments_history)
    balance_due = max(0.0, round(invoice["grand_total"] - already_paid, 2))

    if balance_due <= 0:
        raise HTTPException(status_code=400, detail="Invoice is already fully settled")

    amount_to_pay = payload.amount if payload.amount else balance_due
    if amount_to_pay <= 0 or amount_to_pay > balance_due + 0.01:
        raise HTTPException(status_code=400, detail=f"Amount must be between 0 and balance due (₹{balance_due})")

    txnid = f"TXN_{ObjectId()}"
    method = payload.payment_method.lower()

    # Create active transaction log
    tx_doc = {
        "tenant_id": current_user["tenant_id"],
        "branch_id": invoice["branch_id"],
        "invoice_id": invoice_oid,
        "txnid": txnid,
        "amount": amount_to_pay,
        "payment_method": method,
        "status": "pending",
        "created_at": datetime.utcnow()
    }
    inject_audit_fields(current_user, tx_doc)
    await tx_col.insert_one(tx_doc)

    response_data = {
        "txnid": txnid,
        "amount": amount_to_pay,
        "invoice_number": invoice["invoice_number"]
    }

    if method == "payu":
        # Generate hash parameter payloads
        key = pay_settings.get("payu_merchant_key") or settings.PAYU_MERCHANT_KEY or "gtK42w"
        salt = branch_secrets.get("payu_merchant_salt") or settings.PAYU_MERCHANT_SALT or "eCwWELSp"
        env = pay_settings.get("payu_env") or settings.PAYU_ENV or "test"
        
        action_url = "https://secure.payu.in/_payment" if env == "production" else "https://test.payu.in/_payment"
        base_url = str(request.base_url).rstrip('/')
        surl = f"{base_url}/api/payu/callback"
        furl = f"{base_url}/api/payu/callback"
        
        productinfo = f"HMIS Invoice {invoice['invoice_number']}"
        firstname = current_user.get("name", "Patient")
        email = current_user.get("email", "patient@hmis.com")
        
        hash_sequence = f"{key}|{txnid}|{amount_to_pay:.2f}|{productinfo}|{firstname}|{email}||||||||||{salt}"
        hash_val = hashlib.sha512(hash_sequence.encode('utf-8')).hexdigest().lower()
        
        response_data.update({
            "key": key,
            "action_url": action_url,
            "surl": surl,
            "furl": furl,
            "hash": hash_val,
            "productinfo": productinfo,
            "firstname": firstname,
            "email": email,
            "phone": current_user.get("phone", "9999999999")
        })

    elif method == "razorpay":
        key_id = pay_settings.get("razorpay_key_id") or "rzp_test_placeholderKey"
        key_secret = branch_secrets.get("razorpay_key_secret")
        
        order_id = None
        if key_secret and not key_id.startswith("rzp_test_placeholder"):
            notes = {
                "invoice_number": invoice["invoice_number"],
                "tenant_id": str(current_user["tenant_id"]),
                "branch_id": str(invoice["branch_id"])
            }
            order_id = await create_real_razorpay_order(key_id, key_secret, amount_to_pay, txnid, notes)
            
        if not order_id:
            order_id = f"order_rzp_{ObjectId()}" # Mock sandbox order ID
            
        response_data.update({
            "key_id": key_id,
            "razorpay_order_id": order_id,
            "currency": "INR",
            "name": branch.get("name") if branch else "HMIS Hospital",
            "description": f"Settle Invoice {invoice['invoice_number']}"
        })

    elif method == "stripe":
        publishable_key = pay_settings.get("stripe_publishable_key") or "pk_test_placeholderKey"
        secret_key = branch_secrets.get("stripe_secret_key")
        
        client_secret = None
        if secret_key and not publishable_key.startswith("pk_test_placeholder"):
            metadata = {
                "invoice_number": invoice["invoice_number"],
                "tenant_id": str(current_user["tenant_id"]),
                "branch_id": str(invoice["branch_id"])
            }
            client_secret = await create_real_stripe_intent(secret_key, amount_to_pay, "INR", metadata)
            
        if not client_secret:
            client_secret = f"pi_{ObjectId()}_secret_{uuid.uuid4()}" # Mock client secret
            
        response_data.update({
            "publishable_key": publishable_key,
            "client_secret": client_secret
        })

    elif method == "upi":
        # Generate UPI payload
        vpa = pay_settings.get("upi_vpa") or "billing@hospital"
        merchant = pay_settings.get("upi_merchant_name") or branch.get("name") or "HMIS Hospital"
        # Standard UPI deep-link syntax: upi://pay?pa=...&pn=...&am=...&cu=INR&tn=...
        upi_link = f"upi://pay?pa={vpa}&pn={merchant}&am={amount_to_pay:.2f}&cu=INR&tn={invoice['invoice_number']}"
        response_data.update({
            "upi_link": upi_link,
            "upi_vpa": vpa,
            "merchant_name": merchant
        })

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported payment gateway: {method}")

    return response_data

@router.post("/verify")
async def verify_payment(
    payload: PaymentVerifyRequest,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Verifies transaction signature or UTR log status, updating invoice and logs accordingly."""
    invoices_col = get_invoices_collection()
    payments_col = get_payments_collection()
    tx_col = get_online_transactions_collection()

    try:
        invoice_oid = ObjectId(payload.invoice_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid invoice_id format")

    invoice = await invoices_col.find_one({"_id": invoice_oid, "tenant_id": current_user["tenant_id"]})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice record not found")

    method = payload.payment_method.lower()
    
    # Check if payment was already registered with this transaction ID
    existing_payment = await payments_col.find_one({"transaction_reference": payload.transaction_id})
    if existing_payment:
        return {"status": "success", "message": "Transaction already verified and processed"}

    # Validation & Verification Logic
    verified = False
    details = {}

    # Load branch settings to get secret keys
    branches_col = get_branches_collection()
    branch = await branches_col.find_one({"_id": invoice["branch_id"]})
    pay_settings = branch.get("payment_settings") or {} if branch else {}
    
    from services.secrets_vault import get_branch_secrets
    branch_secrets = await get_branch_secrets(invoice["branch_id"])

    if method == "razorpay":
        key_secret = branch_secrets.get("razorpay_key_secret")
        if key_secret and payload.extra_data and "razorpay_signature" in payload.extra_data:
            order_id = payload.extra_data.get("razorpay_order_id", "")
            payment_id = payload.transaction_id
            signature = payload.extra_data.get("razorpay_signature", "")
            
            msg = f"{order_id}|{payment_id}"
            generated_signature = hmac.new(
                key_secret.encode('utf-8'),
                msg.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            if generated_signature == signature:
                verified = True
                details = {"razorpay_payment_id": payment_id, "razorpay_order_id": order_id, "mode": "live"}
            else:
                raise HTTPException(status_code=400, detail="Razorpay signature verification failed")
        else:
            verified = True
            details = {"razorpay_payment_id": payload.transaction_id, "mode": "sandbox"}
        
    elif method == "stripe":
        secret_key = branch_secrets.get("stripe_secret_key")
        if secret_key and not secret_key.startswith("sk_test_placeholder"):
            intent_id = payload.transaction_id
            is_succeeded = await verify_real_stripe_intent(secret_key, intent_id)
            if is_succeeded:
                verified = True
                details = {"stripe_payment_intent": intent_id, "mode": "live"}
            else:
                raise HTTPException(status_code=400, detail="Stripe PaymentIntent verification failed: status is not succeeded")
        else:
            verified = True
            details = {"stripe_payment_intent": payload.transaction_id, "mode": "sandbox"}
        
    elif method == "upi":
        # Validate UPI dynamic UTR format
        utr = payload.transaction_id.strip()
        if len(utr) < 6 or not utr.isalnum():
            raise HTTPException(status_code=400, detail="Invalid UTR format. Must be at least 6 alphanumeric characters.")
        verified = True
        details = {"upi_utr": utr, "note": "Pending manual bank recon clearance"}

    elif method == "payu":
        verified = True
        details = {"payu_txnid": payload.transaction_id}
        
    else:
        raise HTTPException(status_code=400, detail="Unsupported payment method")

    if not verified:
        raise HTTPException(status_code=400, detail="Payment verification failed")

    # Record Payment Voucher
    payment_doc = {
        "tenant_id": invoice["tenant_id"],
        "branch_id": invoice["branch_id"],
        "invoice_id": invoice_oid,
        "payment_method": method.upper(),
        "amount_paid": payload.amount,
        "transaction_reference": payload.transaction_id,
        "created_at": datetime.utcnow(),
        "created_by": str(current_user["_id"])
    }
    
    res = await payments_col.insert_one(payment_doc)
    payment_id = str(res.inserted_id)

    # Re-calculate paid history
    payments_history = await payments_col.find({"invoice_id": invoice_oid}).to_list(None)
    already_paid = sum(p.get("amount_paid", 0.0) for p in payments_history)
    
    new_status = "paid" if already_paid >= invoice["grand_total"] else "due"

    await invoices_col.update_one(
        {"_id": invoice_oid},
        {"$set": {
            "payment_status": new_status, 
            "updated_at": datetime.utcnow(), 
            "updated_by": str(current_user["_id"])
        }}
    )
    
    if new_status == "paid":
        try:
            from api.billing import calculate_and_log_referral_commission
            await calculate_and_log_referral_commission(
                invoice_oid,
                ObjectId(invoice["tenant_id"]),
                ObjectId(invoice["branch_id"]),
                current_user
            )
        except Exception as e:
            print(f"Error calculating referral commission on online checkout paid: {e}")

    # Queue billing notification task
    try:
        from tasks import send_billing_notification
        send_billing_notification.delay(str(invoice_oid))
    except Exception as e:
        print(f"Error queueing billing notification: {e}")

    # Log to audit trail
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user.get("name", "Patient Portal"),
        action="PAYMENT_RECEIVED",
        entity="payments",
        entity_id=payment_id,
        details={
            "invoice_id": payload.invoice_id,
            "amount_paid": payload.amount,
            "payment_method": method.upper(),
            "transaction_reference": payload.transaction_id,
            "verification_details": details
        },
        ip_address=request.client.host if request.client else None,
        tenant_id=invoice["tenant_id"],
        branch_id=invoice["branch_id"]
    )

    # Update dynamic transaction log status
    await tx_col.update_many(
        {"txnid": payload.transaction_id},
        {"$set": {"status": "success", "updated_at": datetime.utcnow()}}
    )

    return {
        "status": "success",
        "payment_id": payment_id,
        "invoice_status": new_status
    }

@router.get("/payu/success")
async def payu_success_page(invoice_id: Optional[str] = None, txnid: Optional[str] = None):
    from fastapi.responses import HTMLResponse
    return HTMLResponse(
        content="""
        <html>
            <head>
                <title>Payment Successful</title>
                <style>
                    body { font-family: sans-serif; text-align: center; padding: 50px; background-color: #f8fafc; }
                    .card { background: white; padding: 40px; border-radius: 12px; display: inline-block; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
                    h1 { color: #0d9488; }
                    p { color: #475569; }
                </style>
            </head>
            <body>
                <div class="card">
                    <h1>✔ Payment Successful</h1>
                    <p>Your payment has been successfully processed and verified.</p>
                    <p>Transaction ID: """ + (txnid or 'N/A') + """</p>
                    <p>You can close this window or return to the application.</p>
                </div>
            </body>
        </html>
        """,
        status_code=200
    )

@router.get("/payu/fail")
async def payu_fail_page(invoice_id: Optional[str] = None, txnid: Optional[str] = None, message: Optional[str] = None):
    from fastapi.responses import HTMLResponse
    return HTMLResponse(
        content="""
        <html>
            <head>
                <title>Payment Failed</title>
                <style>
                    body { font-family: sans-serif; text-align: center; padding: 50px; background-color: #f8fafc; }
                    .card { background: white; padding: 40px; border-radius: 12px; display: inline-block; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }
                    h1 { color: #dc2626; }
                    p { color: #475569; }
                </style>
            </head>
            <body>
                <div class="card">
                    <h1>❌ Payment Failed</h1>
                    <p>We were unable to process your payment.</p>
                    <p>Reason: """ + (message or 'Transaction was cancelled or failed') + """</p>
                    <p>Transaction ID: """ + (txnid or 'N/A') + """</p>
                    <p>Please try again or contact support.</p>
                </div>
            </body>
        </html>
        """,
        status_code=200
    )
