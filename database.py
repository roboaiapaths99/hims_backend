from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING
from config import settings

client = None
database = None

class DatabaseUnavailableError(RuntimeError):
    """Raised when MongoDB is unreachable"""

async def connect_to_mongo():
    global client, database
    try:
        client = AsyncIOMotorClient(settings.MONGODB_URI)
        try:
            database = client.get_default_database()
        except Exception:
            database = None
        if database is None:
            database = client.hmis_db
        # Test connection
        await database.command('ping')
        print("Connected to MongoDB for HMIS")
        await create_indexes()
        await seed_saas_plans()
        return True
    except Exception as e:
        print(f"Error connecting to MongoDB: {e}")
        client = None
        database = None
        return False

async def close_mongo_connection():
    global client
    if client:
        client.close()
        print("MongoDB connection closed for HMIS")

def get_db():
    if database is None:
        raise DatabaseUnavailableError("Database is currently unavailable.")
    return database

# Basic tenant organization collections
def get_tenants_collection():
    return get_db().tenants

def get_branches_collection():
    return get_db().branches

def get_users_collection():
    return get_db().users

def get_roles_collection():
    return get_db().roles

def get_audit_logs_collection():
    return get_db().audit_logs

# Config collections
def get_departments_collection():
    return get_db().departments

def get_pricing_items_collection():
    return get_db().pricing_items

def get_lab_test_master_collection():
    return get_db().lab_test_master

def get_rooms_collection():
    return get_db().rooms

def get_ot_rooms_collection():
    return get_db().ot_rooms

def get_templates_collection():
    return get_db().templates

# Patient collections
def get_patients_collection():
    return get_db().patients

def get_vitals_collection():
    return get_db().vitals

def get_visits_collection():
    return get_db().visits

def get_lab_orders_collection():
    return get_db().lab_orders

def get_lab_results_collection():
    return get_db().lab_results

def get_prescriptions_collection():
    return get_db().prescriptions

def get_invoices_collection():
    return get_db().invoices

def get_payments_collection():
    return get_db().payments

def get_payu_transactions_collection():
    return get_db().payu_transactions

def get_online_transactions_collection():
    return get_db().online_transactions

def get_appointments_collection():
    return get_db().appointments

def get_queue_tokens_collection():
    return get_db().queue_tokens

def get_ot_bookings_collection():
    return get_db().ot_bookings

def get_ot_checklists_collection():
    return get_db().ot_checklists

def get_telemedicine_sessions_collection():
    return get_db().telemedicine_sessions

def get_notifications_logs_collection():
    return get_db().notification_logs

def get_notifications_collection():
    return get_db().notifications

def get_inventory_sync_logs_collection():
    return get_db().inventory_sync_logs

def get_family_members_collection():
    return get_db().family_members

def get_patient_documents_collection():
    return get_db().patient_documents

def get_advance_payments_collection():
    return get_db().advance_payments





def get_ai_generated_summaries_collection():
    return get_db().ai_generated_summaries

def get_stored_files_collection():
    return get_db().stored_files

def get_ipd_admissions_collection():
    return get_db().ipd_admissions

def get_bed_transfers_collection():
    return get_db().bed_transfers

def get_ipd_charges_collection():
    return get_db().ipd_charges

def get_tpa_providers_collection():
    return get_db().tpa_providers

def get_patient_policies_collection():
    return get_db().patient_policies

def get_insurance_claims_collection():
    return get_db().insurance_claims

def get_radiology_orders_collection():
    return get_db().radiology_orders

def get_radiology_results_collection():
    return get_db().radiology_results

def get_referring_doctors_collection():
    return get_db().referring_doctors

def get_referral_transactions_collection():
    return get_db().referral_transactions

def get_emergency_admissions_collection():
    return get_db().emergency_admissions

def get_ambulance_bookings_collection():
    return get_db().ambulance_bookings

def get_visitor_passes_collection():
    return get_db().visitor_passes

def get_diet_orders_collection():
    return get_db().diet_orders

def get_feedback_surveys_collection():
    return get_db().feedback_surveys

def get_saas_plans_collection():
    return get_db().saas_plans

def get_saas_payments_collection():
    return get_db().saas_payments

async def seed_saas_plans():
    try:
        col = get_saas_plans_collection()
        count = await col.count_documents({})
        if count == 0:
            default_plans = [
                {
                    "plan_id": "free_trial",
                    "name": "Free Trial",
                    "price": 0.0,
                    "interval": "month",
                    "currency": "INR",
                    "max_branches": 1,
                    "max_staff": 5,
                    "max_patients": 100,
                    "features": {
                        "abdm": False,
                        "ai_summaries": False,
                        "telemedicine": True
                    },
                    "description": "Perfect for small clinics or starting out. Try all basic EMR features for free."
                },
                {
                    "plan_id": "basic_plan",
                    "name": "Basic Plan",
                    "price": 4999.0,
                    "interval": "month",
                    "currency": "INR",
                    "max_branches": 2,
                    "max_staff": 15,
                    "max_patients": 1000,
                    "features": {
                        "abdm": False,
                        "ai_summaries": False,
                        "telemedicine": True
                    },
                    "description": "Designed for growing clinics. Offers expanded branches and staff capabilities."
                },
                {
                    "plan_id": "standard_plan",
                    "name": "Standard Plan",
                    "price": 9999.0,
                    "interval": "month",
                    "currency": "INR",
                    "max_branches": 5,
                    "max_staff": 50,
                    "max_patients": 5000,
                    "features": {
                        "abdm": True,
                        "ai_summaries": False,
                        "telemedicine": True
                    },
                    "description": "Complete suite for medium hospitals. Includes ABDM Sandbox support."
                },
                {
                    "plan_id": "premium_plan",
                    "name": "Premium Plan",
                    "price": 19999.0,
                    "interval": "month",
                    "currency": "INR",
                    "max_branches": 99999,  # Unlimited
                    "max_staff": 99999,     # Unlimited
                    "max_patients": 999999, # Unlimited
                    "features": {
                        "abdm": True,
                        "ai_summaries": True,
                        "telemedicine": True
                    },
                    "description": "Unlimited enterprise scale. Access premium clinical AI Summaries and full features."
                }
            ]
            await col.insert_many(default_plans)
            print("Seeded SaaS subscription plans into MongoDB")
    except Exception as e:
        print(f"Error seeding SaaS plans: {e}")

# Index initialization helper
async def create_indexes():
    db = get_db()
    try:
        # Tenants & Branches indexes
        await db.tenants.create_index("subdomain", unique=True, sparse=True)
        await db.branches.create_index([("tenant_id", ASCENDING), ("code", ASCENDING)], unique=True)
        
        # Users index (Scoped by email)
        await db.users.create_index("email", unique=True)
        await db.users.create_index([("tenant_id", ASCENDING), ("branch_id", ASCENDING)])
        
        # Patients index (Scoped by tenant and branch)
        await db.patients.create_index("phone")
        await db.patients.create_index([("tenant_id", ASCENDING), ("mrn", ASCENDING)], unique=True)
        
        # Appointments index
        await db.appointments.create_index([("tenant_id", ASCENDING), ("branch_id", ASCENDING), ("appointment_date", ASCENDING)])
        
        # Queue Tokens
        await db.queue_tokens.create_index([("branch_id", ASCENDING), ("assigned_at", ASCENDING)])
        
        # Invoices (GST Sequence is branch and tenant scoped)
        await db.invoices.create_index([("tenant_id", ASCENDING), ("invoice_number", ASCENDING)], unique=True)
        
        # Audit Logs
        await db.audit_logs.create_index([("tenant_id", ASCENDING), ("timestamp", DESCENDING)])
        
        # IPD Admissions Indexes
        await db.ipd_admissions.create_index([("tenant_id", ASCENDING), ("branch_id", ASCENDING)])
        await db.ipd_admissions.create_index("patient_id")
        await db.ipd_admissions.create_index("status")
        
        # IPD Charges Indexes
        await db.ipd_charges.create_index("admission_id")
        
        # TPA Module Indexes
        await db.patient_policies.create_index("patient_id")
        await db.insurance_claims.create_index("invoice_id")
        
        # Radiology Module Indexes
        await db.radiology_orders.create_index("patient_id")
        await db.radiology_orders.create_index([("tenant_id", ASCENDING), ("branch_id", ASCENDING)])
        await db.radiology_results.create_index("order_id")
        
        # Referral & Commission Module Indexes
        await db.referring_doctors.create_index([("tenant_id", ASCENDING), ("name", ASCENDING)])
        await db.referring_doctors.create_index("phone", sparse=True)
        await db.referral_transactions.create_index([("tenant_id", ASCENDING), ("branch_id", ASCENDING)])
        await db.referral_transactions.create_index("referring_doctor_id")
        await db.referral_transactions.create_index("invoice_id")
        await db.referral_transactions.create_index("payout_status")
        
        # Emergency Module Indexes
        await db.emergency_admissions.create_index([("tenant_id", ASCENDING), ("branch_id", ASCENDING)])
        await db.emergency_admissions.create_index("triage_category")
        await db.emergency_admissions.create_index("status")
        await db.ambulance_bookings.create_index([("tenant_id", ASCENDING), ("branch_id", ASCENDING)])
        await db.ambulance_bookings.create_index("status")
        
        # Visitor & Diet Module Indexes
        await db.visitor_passes.create_index("admission_id")
        await db.visitor_passes.create_index([("tenant_id", ASCENDING), ("branch_id", ASCENDING)])
        await db.diet_orders.create_index("admission_id")
        await db.diet_orders.create_index([("tenant_id", ASCENDING), ("branch_id", ASCENDING)])
        await db.diet_orders.create_index("status")
        
        # Feedback Survey Indexes
        await db.feedback_surveys.create_index([("tenant_id", ASCENDING), ("branch_id", ASCENDING)])
        await db.feedback_surveys.create_index("rating")
        await db.feedback_surveys.create_index("patient_id", sparse=True)
        
        # User In-App Notifications Indexes
        await db.notifications.create_index([("user_id", ASCENDING), ("is_read", ASCENDING), ("created_at", DESCENDING)])
        
        # Inventory Sync Logs Indexes
        await db.inventory_sync_logs.create_index([("success", ASCENDING), ("timestamp", DESCENDING)])
        
        # Family Members & Patient Documents Indexes
        await db.family_members.create_index("patient_id")
        await db.patient_documents.create_index("patient_id")
        
        # Advance Payments Indexes
        await db.advance_payments.create_index("patient_id")
        
        # SaaS Subscriptions Indexes
        await db.saas_plans.create_index("plan_id", unique=True)
        await db.saas_payments.create_index([("tenant_id", ASCENDING), ("payment_date", DESCENDING)])
        
        # Blood Bank Indexes
        await db.blood_donors.create_index("donor_number", unique=True)
        await db.blood_donors.create_index([("tenant_id", ASCENDING), ("branch_id", ASCENDING)])
        await db.blood_stock.create_index("bag_number", unique=True)
        await db.blood_stock.create_index([("tenant_id", ASCENDING), ("branch_id", ASCENDING), ("blood_group", ASCENDING), ("component_type", ASCENDING)])
        await db.blood_donations.create_index("bag_number")
        await db.blood_requisitions.create_index([("tenant_id", ASCENDING), ("branch_id", ASCENDING)])
        await db.blood_requisitions.create_index("patient_id")
        await db.blood_transfusions.create_index("requisition_id")
        
        # DMS Integration Indexes
        await db.dms_patient_sync.create_index([("tenant_id", ASCENDING), ("patient_id", ASCENDING)], unique=True)
        await db.dms_patient_sync.create_index("sync_status")
        await db.dms_patient_sync.create_index("last_synced_at")
        
        await db.dms_document_refs.create_index([("tenant_id", ASCENDING), ("patient_id", ASCENDING), ("uploaded_at", ASCENDING)])
        await db.dms_document_refs.create_index([("tenant_id", ASCENDING), ("dms_document_id", ASCENDING)], unique=True)
        await db.dms_document_refs.create_index("status")
        await db.dms_document_refs.create_index("needs_review")
        
        await db.dms_webhook_events.create_index("event_id", unique=True)
        await db.dms_webhook_events.create_index([("event_type", ASCENDING), ("received_at", ASCENDING)])
        await db.dms_webhook_events.create_index("processed")
        
        await db.dms_similar_case_searches.create_index([("tenant_id", ASCENDING), ("doctor_id", ASCENDING), ("created_at", ASCENDING)])
        await db.dms_similar_case_searches.create_index([("tenant_id", ASCENDING), ("patient_id", ASCENDING), ("created_at", ASCENDING)])
        
        print("HMIS MongoDB indexes created successfully")
    except Exception as e:
        print(f"Error creating HMIS indexes: {e}")

# Blood Bank accessors
def get_blood_donors_collection():
    return get_db().blood_donors

def get_blood_donations_collection():
    return get_db().blood_donations

def get_blood_stock_collection():
    return get_db().blood_stock

def get_blood_requisitions_collection():
    return get_db().blood_requisitions

def get_blood_transfusions_collection():
    return get_db().blood_transfusions

# DMS Integration accessors
def get_dms_patient_sync_collection():
    return get_db().dms_patient_sync

def get_dms_document_refs_collection():
    return get_db().dms_document_refs

def get_dms_webhook_events_collection():
    return get_db().dms_webhook_events

def get_dms_similar_case_searches_collection():
    return get_db().dms_similar_case_searches


