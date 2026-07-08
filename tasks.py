import asyncio
from datetime import datetime
from bson import ObjectId
from celery_app import celery_app
from database import (
    connect_to_mongo,
    get_appointments_collection,
    get_patients_collection,
    get_invoices_collection,
    get_notifications_logs_collection,
    get_db
)

# Helper to run async database coroutines synchronously inside Celery tasks
def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

async def process_appointment_notification(appointment_id: str):
    await connect_to_mongo()
    
    appt_col = get_appointments_collection()
    patients_col = get_patients_collection()
    logs_col = get_notifications_logs_collection()
    
    try:
        appt_oid = ObjectId(appointment_id)
    except:
        print(f"Invalid appointment_id format: {appointment_id}")
        return
        
    appt = await appt_col.find_one({"_id": appt_oid})
    if not appt:
        print(f"Appointment not found for notification: {appointment_id}")
        return
        
    patient = await patients_col.find_one({"_id": appt["patient_id"]})
    if not patient:
        print(f"Patient not found for notification: {appt['patient_id']}")
        return
        
    patient_name = f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip()
    appt_date = appt["appointment_date"].strftime("%Y-%m-%d")
    
    # 1. Draft messaging templates
    sms_message = (
        f"Dear {patient_name}, your clinical consultation slot is confirmed for {appt_date} "
        f"at {appt['start_time']}. Thank you for choosing HMIS."
    )
    
    # 2. Simulate external SMS Gateway call
    print(f"\n[GATEWAY OUTBOUND SMS] To: {patient.get('phone')} | Content: {sms_message}\n")
    
    # 3. Log transaction
    log_doc = {
        "tenant_id": appt["tenant_id"],
        "branch_id": appt["branch_id"],
        "recipient_id": appt["patient_id"],
        "recipient_phone": patient.get("phone"),
        "recipient_email": patient.get("email"),
        "channel": "sms",
        "template_name": "appointment_confirmed",
        "status": "sent",
        "details": {"message": sms_message, "gateway": "mock_sms_gateway"},
        "created_at": datetime.utcnow()
    }
    
    await logs_col.insert_one(log_doc)
    print(f"Notification log recorded for appointment: {appointment_id}")

async def process_billing_notification(invoice_id: str):
    await connect_to_mongo()
    
    invoice_col = get_invoices_collection()
    patients_col = get_patients_collection()
    logs_col = get_notifications_logs_collection()
    
    try:
        inv_oid = ObjectId(invoice_id)
    except:
        print(f"Invalid invoice_id format: {invoice_id}")
        return
        
    invoice = await invoice_col.find_one({"_id": inv_oid})
    if not invoice:
        print(f"Invoice not found for notification: {invoice_id}")
        return
        
    patient = await patients_col.find_one({"_id": invoice["patient_id"]})
    if not patient:
        print(f"Patient not found for invoice notification: {invoice['patient_id']}")
        return
        
    patient_name = f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip()
    
    # 1. Draft messaging templates
    sms_message = (
        f"Dear {patient_name}, payment of INR {invoice['grand_total']} was successfully received "
        f"for invoice record {invoice['invoice_number']}. Receipt cleared."
    )
    
    # 2. Simulate external SMS Gateway call
    print(f"\n[GATEWAY OUTBOUND SMS] To: {patient.get('phone')} | Content: {sms_message}\n")
    
    # 3. Log transaction
    log_doc = {
        "tenant_id": invoice["tenant_id"],
        "branch_id": invoice["branch_id"],
        "recipient_id": invoice["patient_id"],
        "recipient_phone": patient.get("phone"),
        "recipient_email": patient.get("email"),
        "channel": "sms",
        "template_name": "bill_paid",
        "status": "sent",
        "details": {"message": sms_message, "gateway": "mock_sms_gateway"},
        "created_at": datetime.utcnow()
    }
    
    await logs_col.insert_one(log_doc)
    print(f"Notification log recorded for invoice: {invoice_id}")


# Celery Tasks
@celery_app.task(name="tasks.send_appointment_notification")
def send_appointment_notification(appointment_id: str):
    run_async(process_appointment_notification(appointment_id))

@celery_app.task(name="tasks.send_billing_notification")
def send_billing_notification(invoice_id: str):
    run_async(process_billing_notification(invoice_id))

async def process_otp_notification(phone: str, otp: str):
    await connect_to_mongo()
    sms_message = f"Welcome to AGPK Academy login. Your verification code is {otp}. This OTP will expire in 5 minutes"
    print(f"\n[GATEWAY OUTBOUND SMS] To: {phone} | Content: {sms_message}\n")

@celery_app.task(name="tasks.send_otp_notification")
def send_otp_notification(phone: str, otp: str):
    run_async(process_otp_notification(phone, otp))

