# HIMS & DMS Bridge Integration Implementation Plan

## 1. Phase-by-Phase Implementation Order
* **Phase 1: Environment & Diagnostics**: Set up config files, environment variables, server-to-server security credentials, HIMS bridge client (`dms_bridge_service.py`), and health check APIs (`GET /bridge/health` on DMS and `GET /api/integrations/dms/status` on HIMS).
* **Phase 2: Database Layer**: Create local cache collections in HIMS (`dms_patient_sync`, `dms_document_refs`, `dms_webhook_events`, `dms_similar_case_searches`) and linked patient reference model in DMS (`hims_patient_refs`). Initialize indices.
* **Phase 3: Patient Sync & Backfill**: Implement `POST /bridge/patients/upsert` on DMS, patient sync service on HIMS, register hooks in HIMS patient creation/updates, and create a command-line script + admin UI for backfilling existing patients.
* **Phase 4: Document Upload Proxy**: Establish secure file upload proxy from HIMS to DMS using multipart forms, local HIMS tracking refs, and signed preview token mechanisms.
* **Phase 5: Webhooks & Event Processing**: Set up idempotent webhook listener in HIMS and delivery worker in DMS to keep document statuses, summaries, and timelines updated.
* **Phase 6: Clinical Integrations**: Add clinical timeline tabs,Merged doctor consultation summaries, similar cases searches (excluding self, matching tenant), clinical visits uploads, and feedback loops.
* **Phase 7: Security Hardening & QA**: Implement file MIME/size checks, signed previews, tenant isolation verification, and end-to-end tests.

## 2. Exact HIMS Backend Files to Add
* [dms_bridge_service.py](file:///c:/Users/roboa/OneDrive/Desktop/hims/backend/services/dms_bridge_service.py): Safe client communication handler using `httpx`.
* [dms_patient_sync_service.py](file:///c:/Users/roboa/OneDrive/Desktop/hims/backend/services/dms_patient_sync_service.py): Synchronizes patients on CRUD triggers.
* [dms_integration.py](file:///c:/Users/roboa/OneDrive/Desktop/hims/backend/api/dms_integration.py): Integrations status, sync, upload proxy, timeline, queue, and webhook routes.
* [backfill_dms_patients.py](file:///c:/Users/roboa/OneDrive/Desktop/hims/backend/scripts/backfill_dms_patients.py): Bulk backfill CLI.

## 3. Exact HIMS Backend Files to Update
* `config.py`: Add environment configurations.
* `main.py`: Include `dms_integration` router.
* `database.py`: Define `dms_patient_sync`, `dms_document_refs`, `dms_webhook_events`, `dms_similar_case_searches` collection getters and safe index creation.
* `api/patient.py`: Trigger sync after patient registration or updates.
* `api/consultation.py`: Send finalized visit clinical context to DMS.
* `tests/run_tests.py`: Set `"is_active": True` in user seeds to pass tests.

## 4. Exact DMS Backend Files to Add
* [bridge_auth.py](file:///c:/Users/roboa/OneDrive/Desktop/hims/DMS-Project/backend/app/auth/bridge_auth.py): Checks `x-bridge-api-key`, `x-source-system: HIMS`, and request-id.
* [bridge.py](file:///c:/Users/roboa/OneDrive/Desktop/hims/DMS-Project/backend/app/routes/bridge.py): Routes for server-to-server operations.
* [hims_webhook_service.py](file:///c:/Users/roboa/OneDrive/Desktop/hims/DMS-Project/backend/app/services/hims_webhook_service.py): Sign payloads and deliver status webhooks to HIMS.

## 5. Exact DMS Backend Files to Update
* `app/config.py`: Add `hims_api_base_url`, `hims_bridge_api_key`, `dms_webhook_secret`.
* `app/main.py`: Mount `bridge` router.
* `app/routes/documents.py` / `app/services/similar_case_service.py`: Fling webhooks back to HIMS on transition to processed, verified, rejected, etc.

## 6. Exact HIMS Frontend Screens to Add/Update
* **DMS Integration Diagnostics Screen**: View status, test connectivity, trigger patient backfill.
* **Patient Profile -> Documents Tab**: Table showing files, status badges, previews, action triggers.
* **Patient Profile -> Clinical Timeline Tab**: Merged history of vitals, lab reports, and DMS summaries.
* **Doctor Consultation -> Similar Cases Panel**: Find similar cases, view score/match reasons, submit feedback.
* **Document Review Queue**: Filter by pending review, matches, errors. Manage linkings.

## 7. Exact Database Collections to Add in HIMS
* `dms_patient_sync`
* `dms_document_refs`
* `dms_webhook_events`
* `dms_similar_case_searches`

## 8. Exact Database Collections to Add in DMS
* `hims_patient_refs`
* `hims_clinical_records`

## 9. Environment Variables
* **HIMS**:
  * `DMS_API_BASE_URL=http://localhost:8000` (or `http://dms-backend:8000`)
  * `DMS_BRIDGE_API_KEY=change-me-long-random-secret`
  * `DMS_WEBHOOK_SECRET=change-me-webhook-secret`
  * `DMS_INTEGRATION_ENABLED=true`
  * `DMS_REQUEST_TIMEOUT_SECONDS=15`
* **DMS**:
  * `HIMS_API_BASE_URL=http://localhost:8002` (or `http://hims-api:8002`)
  * `HIMS_BRIDGE_API_KEY=change-me-long-random-secret`
  * `DMS_WEBHOOK_SECRET=change-me-webhook-secret`
  * `HIMS_WEBHOOK_TIMEOUT_SECONDS=15`

## 10. API Contracts
* See details in the main implementation plan. Health checks, upserts, uploads, similar-case searches, and verification actions are standardized.

## 11. Webhook Contracts
* Path: `POST /api/integrations/dms/webhook`
* Payload: includes `event_id`, `event_type`, `occurred_at`, `tenant_id`, `branch_id`, `hims_patient_id`, `dms_document_id`, and `document` dictionary. Signed with HMAC SHA256 using the webhook secret.

## 12. Permission Matrix
* `dms.integration.status` or admin: check health status and run diagnostics.
* `dms.patient.sync` or admin: trigger individual or bulk patient syncs.
* `dms.documents.upload`: proxy uploads files to DMS.
* `dms.documents.preview`: request preview tokens.
* `dms.documents.review`: view/manage the Document Review Queue.

## 13. Audit Log Plan
* Log each action in the HIMS audit collection (`get_audit_logs_collection()`):
  * `DMS_PATIENT_SYNCED`
  * `DMS_DOCUMENT_UPLOADED`
  * `DMS_DOCUMENT_PREVIEWED`
  * `DMS_DOCUMENT_VERIFIED` / `DMS_DOCUMENT_REJECTED`
  * `DMS_SIMILAR_CASES_SEARCHED`
  * `DMS_SIMILAR_CASES_FEEDBACK_SUBMITTED`
* Log requests in DMS audit collection (`db.audit_logs`).

## 14. Retry/Error Handling Plan
* HIMS client wraps httpx requests in try-except. DMS down will update state to "failed" or skip but never abort HIMS core operations.
* Webhook receiver is idempotent; processed `event_id` is tracked.
* Background retries for patient sync and webhook deliveries will use Celery/BackgroundTasks.

## 15. Backfill Plan for Old Patients
* Python backfill CLI handles batch query on HIMS patients. Call DMS upsert per patient. Skip already synced unless `--force` is set.
* Admin panel provides a UI button to start this command-line runner cleanly.

## 16. Testing Plan
* HIMS Status, Patient Sync, Upload Proxy, Webhook, Preview, and Similar Case Search unit and E2E tests.

## 17. Rollback Plan
* Fallback configuration variable `DMS_INTEGRATION_ENABLED=false` disables the integration globally, bypassing all downstream checks and hiding DMS-related UI panels.
