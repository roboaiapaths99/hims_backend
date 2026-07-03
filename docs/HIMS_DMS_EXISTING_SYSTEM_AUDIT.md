# HIMS & DMS Existing System Audit

## 1. Current HIMS Architecture
* **Core Framework**: FastAPI (python-based asynchronous backend).
* **Database**: MongoDB (via `pymongo` and `motor` asynchronous driver).
* **Task Queue**: Celery (using Redis as the message broker and backend).
* **Authentication**: JWT token-based authentication with Access and Refresh tokens (via `jose` library).
* **RBAC & Scoping**: Multi-tenant and branch level scoping with specific roles and permission checks enforced via FastAPI Depends injection.

## 2. Current DMS Architecture
* **Core Framework**: FastAPI standalone backend for document processing and intelligence.
* **Database**: MongoDB (via `pymongo` and `motor`).
* **AI & Extraction Engine**: Gemini AI integration (Google Generative AI SDK), PDF text extraction via `pypdf`, and optional Tesseract OCR.
* **Workflows**: Synchronous text extraction, Gemini AI structured extraction, automatic patient matching, document-level summary generation, broad patient-level clinical summary generation, timeline building, and real-time partial search.
* **Authentication**: JWT token-based authentication using user roles (Admin, Doctor, Document Staff, Receptionist).

## 3. Existing HIMS Patient Model
* Defined in [patient.py](file:///c:/Users/roboa/OneDrive/Desktop/hims/backend/models/patient.py).
* Fields:
  * `first_name` (str)
  * `last_name` (str)
  * `phone` (str, 10 digits)
  * `email` (EmailStr, optional)
  * `dob` (datetime)
  * `gender` (Male/Female/Other)
  * `blood_group` (optional)
  * `address` (str)
  * `emergency_contact_name` (str)
  * `emergency_contact_phone` (str)
  * `photo_url` (optional)
  * `abha_number` (optional)
  * `abha_address` (optional)
  * `consent_signed` (bool)
  * `referred_by_doctor_id` (optional)
  * System generated fields (returned in `PatientResponse`): `id`, `mrn` (format: `<BRANCH>-PID-<YYYYMMDD>-<SEQ>`), `tenant_id`, `branch_id`, `created_at`, `updated_at`.

## 4. Existing HIMS Auth/RBAC Model
* Enforced in [auth.py](file:///c:/Users/roboa/OneDrive/Desktop/hims/backend/middleware/auth.py).
* Roles include: `super_admin`, `hospital_admin`, `branch_admin`, `receptionist`, `doctor`, `nurse`, `lab_technician`, `pharmacist`, `billing_staff`, `ot_coordinator`, `surgeon`, `anesthetist`, `patient`.
* Role-based permissions are loaded from the database (`get_roles_collection()`) or default fallback role-to-permission mappings.
* Authentication uses HTTPBearer JWT validation. Patient login and staff login are handled separately but resolved in `get_current_user`.

## 5. Existing Tenant/Branch Model
* Multi-tenant structure where users and patients are scoped by `tenant_id` and `branch_id` (stored as ObjectIds).
* Access queries are automatically scoped using `get_tenant_filter` and `get_branch_filter` helpers.
* SaaS limits are stored in the `tenants` collection: `max_branches`, `max_staff`, `max_patients`.
* When a user creates/updates resources, `inject_audit_fields` injects the correct scopes.

## 6. Existing HIMS File/Document Flow
* HIMS stores basic external documents inside [patient.py](file:///c:/Users/roboa/OneDrive/Desktop/hims/backend/api/patient.py) under `POST /api/patients/{patient_id}/documents`.
* Documents are stored locally or uploaded to S3 if S3 config is present, then references are stored in the patient's record.

## 7. Existing DMS Document Flow
* User uploads file via `POST /documents/upload` (accepts multipart file).
* File is saved privately in the `uploads` directory.
* Metadata is stored in `documents` collection with status `uploaded`.
* Asynchronous (or blocking inline) `_process_document` runs:
  * Text extraction (pypdf/OCR).
  * Gemini AI extraction.
  * Patient matching by UHID, Mobile, Name similarity.
  * Summary generation.
  * Clinical timeline addition.
  * Merged patient clinical summary regeneration.

## 8. Existing DMS Patient/Document Model
* **DMS Patient**: `patient_id`, `uhid`, `name`, `mobile`, `age`, `gender`, `address`, `patient_summary`.
* **DMS Document**: `document_id`, `patient_id`, `document_type`, `file_name`, `file_size`, `mime_type`, `storage_type`, `summary`, `extracted_text`, `extraction_status`, `summary_status`, `uploaded_at`, `deleted_at`.
* **DMS Document Extraction**: `document_id`, `extracted_data`, `verified_data`, `extracted_text`, `extraction_status`, `summary`, `summary_status`.

## 9. Reusable APIs
* **DMS**:
  * Text extraction and Gemini processing pipelines.
  * Similarity scoring services (`similar_case_service.py`).
  * Patient summary and timeline generation logic.
* **HIMS**:
  * Core CRUD logic for patients, consultations, and audit logging.

## 10. Missing APIs
* **DMS Bridge Endpoints**:
  * Server-to-server health check: `GET /bridge/health`
  * Patient reference upsert: `POST /bridge/patients/upsert`
  * Document secure upload proxy target: `POST /bridge/documents/upload`
  * Signed preview token generation: `GET /bridge/documents/{document_id}/preview-token`
  * Document verification, rejection, and reprocessing endpoints under `/bridge/documents/{document_id}/*`
  * Clinical records sync endpoint: `POST /bridge/clinical-records/upsert`
  * Patient summaries, timelines, and documents bridge views.
  * Similar case search endpoint: `POST /bridge/similar-cases/search`
* **HIMS Integration Endpoints**:
  * Status checker: `GET /api/integrations/dms/status`
  * Patient manual sync: `POST /api/integrations/dms/patients/{patient_id}/sync`
  * Document upload proxy: `POST /api/integrations/dms/documents/upload`
  * Document list & status: `GET /api/integrations/dms/patients/{patient_id}/documents`
  * Webhook listener: `POST /api/integrations/dms/webhook`
  * Preview redirect: `GET /api/integrations/dms/documents/{document_id}/preview`
  * Document review queue views & actions.
  * Patient summary, timeline, and similar cases view.

## 11. Broken or Risky Areas
* **HIMS test runner bug**: In [run_tests.py](file:///c:/Users/roboa/OneDrive/Desktop/hims/backend/tests/run_tests.py), the seeded test user has `"status": "active"` but is missing `"is_active": True`. This causes a 401 Unauthorized during integration testing of `GET /api/saas/subscription/status` because the auth middleware strictly checks `elif not user.get("is_active"): raise 401`.
* **FastAPI Async client testing**: Under python 3.14, `pytest-asyncio` causes an error when run with pytest 8.4+: `AttributeError: 'FixtureDef' object has no attribute 'unittest'`. We should run tests using the direct Python script runner or fix this dependency discrepancy.

## 12. Data Corruption Risks
* Corrupting HIMS patient collection is a critical risk. To prevent this, HIMS must not store DMS-specific documents or raw AI state directly inside the core `patients` collection. Local reference collections must be used instead.
* Double-syncing or duplicate patient matching in DMS. The upsert endpoint must match strictly on `tenant_id` + `hims_patient_id`.

## 13. Safe Integration Approach
* Add bridge middleware/auth in DMS checking for client keys.
* Maintain HIMS as the single source of truth for patient demographics.
* Add local cache collections in HIMS so that HIMS never communicates with DMS directly during regular patient rendering (which avoids page load delays if DMS is down).
* Use non-blocking async HTTP calls and Celery retries for integration tasks.
* Strictly enforce tenant and branch isolation inside all bridge APIs.

## 14. Files to Add
* **HIMS**:
  * [dms_bridge_service.py](file:///c:/Users/roboa/OneDrive/Desktop/hims/backend/services/dms_bridge_service.py)
  * [dms_patient_sync_service.py](file:///c:/Users/roboa/OneDrive/Desktop/hims/backend/services/dms_patient_sync_service.py)
  * [dms_integration.py](file:///c:/Users/roboa/OneDrive/Desktop/hims/backend/api/dms_integration.py)
  * [backfill_dms_patients.py](file:///c:/Users/roboa/OneDrive/Desktop/hims/backend/scripts/backfill_dms_patients.py)
* **DMS**:
  * [bridge_auth.py](file:///c:/Users/roboa/OneDrive/Desktop/hims/DMS-Project/backend/app/auth/bridge_auth.py)
  * [bridge.py](file:///c:/Users/roboa/OneDrive/Desktop/hims/DMS-Project/backend/app/routes/bridge.py)
  * [hims_webhook_service.py](file:///c:/Users/roboa/OneDrive/Desktop/hims/DMS-Project/backend/app/services/hims_webhook_service.py)

## 15. Files to Modify
* **HIMS**:
  * `config.py` (add environment configurations)
  * `main.py` (register integration routes)
  * `api/patient.py` (trigger sync on create/update)
  * `api/consultation.py` (trigger sync on visit finalization)
  * `tests/run_tests.py` (fix the `is_active` field bug)
  * `frontend` files (add DMS integration diagnostics, upload, timeline, review queue, similar cases panel)
* **DMS**:
  * `app/config.py` (add HIMS configurations)
  * `app/main.py` (register bridge router)
  * `app/services/document_text_extraction_service.py` (add webhook firing hooks)
  * `app/routes/documents.py` (trigger webhook callbacks when document status updates)

## 16. Tests Needed Before Integration
* Run unit tests on HIMS (fixing `run_tests.py` first) and verify they pass.
* Run similarity test on DMS.

## 17. Rollback Risks
* If the bridge experiences errors or the keys mismatch, HIMS might fail patient registration if the code blocks. We must ensure the try-except wrapper catches all HTTP issues and returns status gracefully without aborting the main transactions.
