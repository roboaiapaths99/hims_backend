# HIMS and DMS Bridge Integration Enterprise Plan

## Core Decision

Do not rebuild DMS inside HIMS first.

Keep both apps separate:

- HIMS is the main hospital operations system.
- DMS is the clinical document intelligence system.
- Users work mostly inside HIMS.
- HIMS and DMS communicate through secure bridge APIs and webhooks.

This gives a real enterprise setup without forcing a risky rewrite.

## Login and User Experience

### Normal Staff and Doctors

Doctors, reception, nurses, lab staff, billing staff, and admins log in to HIMS only.

They should not need to open DMS for daily work.

HIMS will:

- verify the logged-in user's role and permissions
- call DMS through backend bridge APIs
- show DMS documents, summaries, timelines, and similar cases inside HIMS screens
- generate secure document preview links from DMS

### DMS Admin Users

DMS login can still exist, but only for:

- DMS administrators
- document processing supervisors
- failed extraction review
- vector search/index diagnostics
- DMS-only maintenance

## System-to-System Security

Use bridge API authentication between HIMS and DMS.

Every bridge request should include:

```http
x-bridge-api-key: long-random-secret
x-source-system: HIMS
x-request-id: uuid
```

Recommended environment variables:

HIMS:

```env
DMS_API_BASE_URL=http://dms-backend:8000
DMS_BRIDGE_API_KEY=change-me-long-random-secret
DMS_WEBHOOK_SECRET=change-me-webhook-secret
```

DMS:

```env
HIMS_API_BASE_URL=http://hims-api:8000
HIMS_BRIDGE_API_KEY=change-me-long-random-secret
DMS_WEBHOOK_SECRET=change-me-webhook-secret
```

Do not share normal user JWT tokens between HIMS and DMS in phase 1. Keep the bridge server-to-server.

## Patient Sync

When a patient is created or updated in HIMS, HIMS sends the patient identity to DMS.

HIMS -> DMS:

```http
POST /bridge/patients/upsert
```

Payload:

```json
{
  "hims_patient_id": "64...",
  "mrn": "DEL-PID-20260702-0001",
  "first_name": "Ritika",
  "last_name": "Aggarwal",
  "phone": "9999999999",
  "dob": "1984-02-12",
  "age": 42,
  "gender": "Female",
  "tenant_id": "64...",
  "branch_id": "64...",
  "abha_number": null,
  "abha_address": null,
  "updated_at": "2026-07-02T10:00:00Z"
}
```

DMS stores this as a linked patient reference, not as an independent hospital patient master.

Important DMS fields:

- `source_system = "HIMS"`
- `hims_patient_id`
- `hims_mrn`
- `tenant_id`
- `branch_id`
- `name`
- `phone`
- `dob`
- `gender`

## Document Upload Flow

Users upload documents from HIMS.

HIMS -> DMS:

```http
POST /bridge/documents/upload
```

The request includes:

- file
- HIMS patient ID if known
- MRN if known
- document category if selected
- tenant and branch
- uploader ID and role

DMS will:

- save original file securely
- extract readable text
- run Gemini structured extraction
- identify document type
- match patient
- create summary
- create patient timeline entry
- create embedding
- find similar previous cases
- send processing status back to HIMS

## DMS Webhooks Back to HIMS

DMS should notify HIMS when important events happen.

DMS -> HIMS:

```http
POST /api/integrations/dms/webhook
```

Events:

- `document.uploaded`
- `document.processing_started`
- `document.processed`
- `document.needs_review`
- `document.verified`
- `document.rejected`
- `summary.updated`
- `timeline.updated`
- `similar_cases.found`
- `similar_cases.failed`
- `extraction.failed`
- `embedding.failed`

HIMS stores a lightweight local reference so screens can load fast:

- DMS document ID
- patient ID
- status
- document type
- summary snippet
- last processed time
- needs review flag

Original files and heavy extraction data remain in DMS.

## Doctor Similar Case Workflow

This is the key feature you asked for.

When a doctor sees a new or unusual case in HIMS, they should be able to check whether the hospital has seen similar patients before.

### Doctor Flow

```text
HIMS login
-> Doctor dashboard
-> Consultation page
-> Open patient
-> Enter symptoms, diagnosis, findings, lab values, notes
-> Click "Find Similar Cases"
-> HIMS sends current clinical context to DMS
-> DMS searches old verified documents and cases
-> Doctor sees matching previous patients/cases inside HIMS
```

### HIMS -> DMS Similar Case API

```http
POST /bridge/similar-cases/search
```

Payload:

```json
{
  "tenant_id": "64...",
  "branch_id": "64...",
  "current_patient_id": "64...",
  "visit_id": "64...",
  "doctor_id": "64...",
  "clinical_context": {
    "chief_complaint": "persistent high blood sugar and fatigue",
    "symptoms": ["polyuria", "fatigue"],
    "diagnosis": ["Type 2 Diabetes Mellitus"],
    "vitals": {
      "bp": "140/90",
      "pulse": 88
    },
    "lab_findings": [
      "HbA1c 8.9",
      "fasting glucose 168"
    ],
    "medications": ["metformin"],
    "doctor_notes": "newly detected uncontrolled diabetes"
  },
  "filters": {
    "exclude_same_patient": true,
    "same_branch_only": false,
    "verified_documents_only": true,
    "minimum_score": 75
  }
}
```

DMS returns:

```json
{
  "matches": [
    {
      "matched_patient_id": "64...",
      "matched_mrn": "DEL-PID-20260625-0008",
      "matched_patient_name": "Madhu Chopra",
      "matched_document_id": "DOC-000091",
      "document_type": "Doctor Note",
      "similarity_score": 87,
      "match_strength": "High",
      "matched_reasons": [
        "Same disease category: diabetes",
        "Similar symptoms: fatigue, polyuria",
        "Similar lab pattern: high HbA1c and fasting glucose"
      ],
      "summary": "Previous patient had uncontrolled type 2 diabetes with similar glucose pattern.",
      "document_date": "2026-06-14",
      "preview_url_token_required": true
    }
  ]
}
```

### What Doctor Can Do

Inside HIMS, doctor can:

- see similar previous cases
- open old document preview
- compare symptoms, findings, diagnosis, labs, medicines
- see patient timeline summary
- mark result as useful or not useful
- add feedback if match is wrong

Doctor cannot:

- auto-copy diagnosis
- auto-copy medicines
- auto-change treatment
- view restricted patient identity if permission does not allow it

This keeps it clinically helpful but safe.

## Similar Case Safety Rules

Enterprise rules:

- Search only within same tenant by default.
- Hospital admin can allow cross-branch search within same tenant.
- Never search across unrelated hospitals.
- Exclude same patient by default.
- Use only verified medical documents and finalized consultation notes.
- Show match reasons.
- Show original source documents.
- Add doctor feedback.
- Log every similar-case search.
- Make clear that results are reference only and need doctor verification.

## Features That Will Work in HIMS

### Patient Profile

HIMS patient profile should show:

- DMS documents tab
- old prescriptions
- lab reports
- radiology reports
- discharge summaries
- admission papers
- referral letters
- bills/insurance docs if allowed
- document status
- document preview
- extracted summary
- clinical timeline
- verification status

### Doctor Consultation

Doctor screen should show:

- old clinical summary from DMS
- recent document timeline
- important past diagnosis
- old prescriptions
- lab/radiology report summaries
- similar previous cases
- button to find similar cases from current notes
- button to attach current visit summary to DMS after finalization

### Reception and Document Staff

Reception/document staff should be able to:

- upload old files
- see processing status
- fix unmatched documents
- verify patient match
- edit document type
- reject duplicate/wrong documents
- request reprocessing

### Lab and Radiology

Lab and radiology should be able to:

- send final report PDFs to DMS
- attach report to patient timeline
- allow doctors to view report summary and original PDF in HIMS

### Patient Portal and Mobile

Patients should be able to:

- view approved documents
- upload external old records for review
- see lab/radiology reports when published
- download allowed summaries or reports

Uploads from patients must go to manual review before becoming trusted clinical records.

## Features That Remain in DMS

DMS continues to own:

- original document storage
- extraction pipeline
- OCR/text extraction
- Gemini structured extraction
- patient matching logic
- document verification state
- document summaries
- patient document timeline
- vector embeddings
- similar case recommendations
- document search
- DMS audit logs
- DMS admin diagnostics

## Features That HIMS Owns

HIMS continues to own:

- login and role permissions for normal users
- tenants and branches
- patient master record
- appointment and queue
- vitals
- consultation and EMR
- lab orders
- radiology orders
- pharmacy and prescription
- billing and payments
- IPD and OT workflows
- notifications
- patient portal and mobile apps
- management reports

## Bridge APIs to Build

### In DMS

- `POST /bridge/patients/upsert`
- `GET /bridge/patients/{hims_patient_id}`
- `POST /bridge/documents/upload`
- `GET /bridge/patients/{hims_patient_id}/documents`
- `GET /bridge/patients/{hims_patient_id}/summary`
- `GET /bridge/patients/{hims_patient_id}/timeline`
- `GET /bridge/documents/{document_id}`
- `GET /bridge/documents/{document_id}/preview-token`
- `PUT /bridge/documents/{document_id}/verify`
- `PUT /bridge/documents/{document_id}/reject`
- `POST /bridge/documents/{document_id}/reprocess`
- `POST /bridge/similar-cases/search`
- `GET /bridge/similar-cases/document/{document_id}`
- `POST /bridge/similar-cases/{recommendation_id}/feedback`
- `GET /bridge/health`

### In HIMS

- `POST /api/integrations/dms/webhook`
- `POST /api/integrations/dms/patients/{patient_id}/sync`
- `POST /api/integrations/dms/documents/upload`
- `GET /api/integrations/dms/patients/{patient_id}/documents`
- `GET /api/integrations/dms/patients/{patient_id}/summary`
- `GET /api/integrations/dms/patients/{patient_id}/timeline`
- `POST /api/integrations/dms/similar-cases/search`
- `POST /api/integrations/dms/similar-cases/{id}/feedback`
- `GET /api/integrations/dms/status`

HIMS APIs should call DMS through a backend service, not directly from the browser.

## Enterprise Build Plan

### Phase 1: Bridge Foundation

- Add bridge API key validation in DMS.
- Add HIMS DMS bridge service using `httpx`.
- Add HIMS config variables for DMS URL and bridge key.
- Add DMS config variables for HIMS webhook URL and secret.
- Add request ID logging.
- Add retry-safe webhook handling.

### Phase 2: Patient Sync

- Sync HIMS patient create/update to DMS.
- Store HIMS patient references in DMS.
- Add patient sync status in HIMS admin diagnostics.
- Add backfill script for existing HIMS patients.

### Phase 3: Document Upload from HIMS

- Add HIMS upload proxy to DMS.
- Add DMS document upload bridge endpoint.
- Add HIMS patient profile document tab.
- Add upload progress and processing status.
- Add secure document preview through DMS preview token.

### Phase 4: Review and Verification in HIMS

- Show pending DMS document review queue in HIMS.
- Allow document staff to verify patient match.
- Allow document staff to edit document type.
- Allow reject/reprocess.
- Write all verification actions back to DMS.

### Phase 5: Doctor Clinical View

- Add DMS summary panel in consultation.
- Add patient timeline panel.
- Add old document list and previews.
- Add “Find Similar Cases” button.
- Add similar-case result cards with source summary, match reasons, score, and preview.

### Phase 6: Current Visit Sync to DMS

- After doctor finalizes a visit, HIMS sends a visit summary to DMS.
- DMS stores it as a clinical record source.
- DMS creates embeddings for finalized visits too, not only uploaded PDFs.
- Future similar-case searches can compare against old documents and old finalized visits.

### Phase 7: Lab/Radiology/IPD/Billing Hooks

- Lab verified report -> send PDF/result summary to DMS.
- Radiology verified report -> send PDF/result summary to DMS.
- IPD admission/discharge summary -> send to DMS.
- Billing/TPA docs -> send to DMS with restricted document category.
- Patient portal uploads -> send to DMS as unverified external records.

### Phase 8: Notifications

- DMS webhook creates HIMS notifications:
  - document ready
  - document needs review
  - similar cases found
  - extraction failed
- Add notification bell in HIMS.
- Add role-specific notification routing.

### Phase 9: Enterprise Security

- Replace hardcoded/mock OTP with real SMS/WhatsApp provider.
- Add OTP expiry, retry limit, lockout, and audit.
- Add strict upload MIME validation and file size enforcement in both apps.
- Add antivirus/malware scan for files.
- Use S3/MinIO for DMS original files.
- Encrypt sensitive storage.
- Add signed preview/download links.
- Ensure no public static medical files.
- Add full audit coverage for all document views/downloads/searches.
- Add tenant isolation tests.

### Phase 10: Background Jobs and Reliability

- Move DMS extraction, summaries, and embeddings to background jobs.
- Add retry queue.
- Add failed job dashboard.
- Add idempotency keys for uploads and webhooks.
- Add dead-letter queue for failed bridge events.
- Add health checks for HIMS, DMS, MongoDB, Redis, Gemini, and vector search.

### Phase 11: Reporting and Admin Control

- HIMS admin dashboard:
  - documents uploaded today
  - pending verification
  - failed processing
  - average processing time
  - similar-case searches
  - doctor feedback stats
- DMS admin dashboard:
  - extraction failures
  - vector index health
  - embedding failures
  - storage usage
  - webhook delivery status

### Phase 12: Mobile Apps

Patient mobile:

- view approved documents
- upload external records
- view lab/radiology reports
- download invoices/reports
- notifications when report is ready

Doctor mobile:

- view patient old documents
- view patient summary
- view lab/radiology reports
- run similar-case search from quick notes
- receive alerts when DMS finds important related records

### Phase 13: QA and Production Verification

End-to-end tests:

- HIMS patient create -> DMS patient sync
- HIMS document upload -> DMS process -> HIMS webhook -> HIMS display
- DMS manual review -> HIMS status update
- Doctor current case -> similar old cases found
- Same-patient similar case is excluded
- Wrong tenant data never appears
- Document preview is denied without valid permission
- Patient portal upload requires review
- Lab report finalization appears in patient timeline

## Final Enterprise Product Shape

Final system should work like this:

- One HIMS login for hospital staff and doctors.
- DMS runs behind the scenes as document intelligence.
- Staff upload and verify documents from HIMS.
- Doctors view old records, summaries, and similar previous cases inside HIMS.
- New finalized visits flow back to DMS so the knowledge base grows.
- DMS can find similar patients from old PDFs and old consultation records.
- HIMS stays the operational source of truth.
- DMS stays the document and case intelligence source.
- All access is permission-controlled, tenant-isolated, audited, and secure.

This gives you an enterprise-level HIMS plus DMS setup without forcing one app to swallow the other too early.

## MVP Scope for First Working Release

Build the first release around the smallest workflow that proves the bridge is real:

1. HIMS patient is synced to DMS.
2. Staff uploads a document from HIMS patient profile.
3. DMS processes the document.
4. DMS sends a webhook to HIMS.
5. HIMS shows document status, summary, and preview link.
6. Doctor opens consultation and sees old documents.
7. Doctor clicks `Find Similar Cases`.
8. DMS returns previous matching cases.
9. Doctor gives feedback on the match.

Do not start with every module. Start with patient profile, document upload, doctor view, and similar cases.

## Detailed Build Checklist

### HIMS Backend Files to Add

Add:

- `backend/services/dms_bridge_service.py`
- `backend/api/dms_integration.py`
- `backend/models/dms_integration.py`
- `backend/tests/test_dms_integration.py`

Update:

- `backend/main.py` to include `dms_integration.router`
- `backend/config.py` to add DMS bridge settings
- `backend/database.py` to add DMS reference collection helpers and indexes
- `backend/api/patient.py` to trigger patient sync after create/update
- `backend/api/consultation.py` to send finalized visit summary to DMS
- `backend/api/lab.py` and `backend/api/radiology.py` later for report sync

### DMS Backend Files to Add

Add:

- `DMS-Project/backend/app/routes/bridge.py`
- `DMS-Project/backend/app/auth/bridge_auth.py`
- `DMS-Project/backend/app/services/hims_webhook_service.py`
- `DMS-Project/backend/app/services/hims_patient_adapter.py`
- `DMS-Project/backend/app/schemas/bridge_schema.py`
- `DMS-Project/backend/app/tests/test_bridge.py`

Update:

- `DMS-Project/backend/app/main.py` to include bridge routes
- `DMS-Project/backend/app/config.py` to add HIMS bridge settings
- `DMS-Project/backend/app/database.py` to add bridge indexes
- DMS document processing flow to emit webhooks
- DMS similar-case service to accept live clinical context from HIMS

## HIMS Local Cache Collections

HIMS should not duplicate DMS storage, but it should keep small references for speed and dashboard counts.

### `dms_patient_sync`

Purpose: track whether a HIMS patient exists in DMS.

Fields:

- `_id`
- `tenant_id`
- `branch_id`
- `patient_id`
- `mrn`
- `dms_patient_id`
- `sync_status`: `pending`, `synced`, `failed`
- `last_synced_at`
- `last_error`
- `retry_count`
- `created_at`
- `updated_at`

Indexes:

- `tenant_id + patient_id`, unique
- `sync_status`
- `last_synced_at`

### `dms_document_refs`

Purpose: show document lists quickly in HIMS.

Fields:

- `_id`
- `tenant_id`
- `branch_id`
- `patient_id`
- `mrn`
- `dms_document_id`
- `document_type`
- `original_filename`
- `status`
- `summary_snippet`
- `is_medical_document`
- `needs_review`
- `similar_case_count`
- `uploaded_by`
- `uploaded_at`
- `processed_at`
- `last_event_at`
- `last_error`

Indexes:

- `tenant_id + patient_id + uploaded_at`
- `tenant_id + dms_document_id`, unique
- `status`
- `needs_review`

### `dms_webhook_events`

Purpose: make webhooks idempotent and auditable.

Fields:

- `_id`
- `event_id`
- `event_type`
- `source_system`
- `dms_document_id`
- `patient_id`
- `payload`
- `processed`
- `processed_at`
- `error`
- `received_at`

Indexes:

- `event_id`, unique
- `event_type + received_at`
- `processed`

### `dms_similar_case_searches`

Purpose: audit doctor searches and feedback.

Fields:

- `_id`
- `tenant_id`
- `branch_id`
- `doctor_id`
- `patient_id`
- `visit_id`
- `query_context`
- `result_count`
- `top_score`
- `created_at`

Indexes:

- `tenant_id + doctor_id + created_at`
- `tenant_id + patient_id + created_at`

## DMS Bridge Collections

### `hims_patient_refs`

DMS should store HIMS-linked patient references separately or extend its patient documents.

Fields:

- `source_system`
- `hims_patient_id`
- `hims_mrn`
- `tenant_id`
- `branch_id`
- `name`
- `phone`
- `dob`
- `age`
- `gender`
- `abha_number`
- `abha_address`
- `last_synced_at`

Indexes:

- `tenant_id + hims_patient_id`, unique
- `tenant_id + hims_mrn`
- `tenant_id + phone`
- `tenant_id + name`

### `hims_clinical_records`

Use this for finalized HIMS visits that are not uploaded PDFs.

Fields:

- `tenant_id`
- `branch_id`
- `hims_patient_id`
- `hims_visit_id`
- `doctor_id`
- `record_type`: `consultation`, `lab_result`, `radiology_result`, `ipd_discharge`
- `clinical_text`
- `structured_data`
- `clinical_embedding`
- `summary`
- `record_date`
- `created_at`

These records become part of similar-case search along with uploaded documents.

## API Contract Details

### HIMS Upload Proxy

Browser calls HIMS:

```http
POST /api/integrations/dms/documents/upload
Authorization: Bearer <hims-user-token>
Content-Type: multipart/form-data
```

Form fields:

- `patient_id`
- `document_type`
- `file`
- `notes`

HIMS validates:

- user is logged in
- user has document upload permission
- patient belongs to same tenant/branch scope
- file size is allowed
- extension and MIME are allowed

Then HIMS forwards to DMS:

```http
POST /bridge/documents/upload
x-bridge-api-key: ...
x-request-id: ...
Content-Type: multipart/form-data
```

DMS returns:

```json
{
  "dms_document_id": "DOC-000123",
  "status": "processing",
  "patient_id": "64...",
  "message": "Document accepted for processing"
}
```

HIMS creates/updates `dms_document_refs`.

### DMS Webhook Payload

```json
{
  "event_id": "evt_20260702_000001",
  "event_type": "document.processed",
  "occurred_at": "2026-07-02T10:15:00Z",
  "tenant_id": "64...",
  "branch_id": "64...",
  "hims_patient_id": "64...",
  "hims_mrn": "DEL-PID-20260702-0001",
  "dms_document_id": "DOC-000123",
  "document": {
    "document_type": "Lab Report",
    "status": "verified",
    "original_filename": "old-lab.pdf",
    "summary_snippet": "HbA1c elevated with fasting glucose abnormal.",
    "is_medical_document": true,
    "needs_review": false,
    "similar_case_count": 3,
    "processed_at": "2026-07-02T10:15:00Z"
  }
}
```

HIMS must:

- verify webhook secret
- reject duplicate `event_id`
- update local references
- create notification if needed
- write audit log
- return success quickly

## Permission Matrix

Recommended HIMS permissions:

- `dms.documents.upload`
- `dms.documents.view`
- `dms.documents.preview`
- `dms.documents.verify`
- `dms.documents.reject`
- `dms.documents.reprocess`
- `dms.summary.view`
- `dms.timeline.view`
- `dms.similar_cases.search`
- `dms.similar_cases.feedback`
- `dms.admin.diagnostics`

Default role mapping:

- Receptionist: upload, view basic document metadata, preview basic documents.
- Document staff: upload, view, preview, verify, reject, reprocess.
- Doctor: view clinical documents, preview, summary, timeline, similar-case search, feedback.
- Nurse: view summary and timeline if assigned to patient workflow.
- Lab technician: upload/view lab documents.
- Radiologist: upload/view radiology documents.
- Billing staff: upload/view billing documents only.
- Hospital admin: all DMS permissions within tenant.
- Branch admin: all DMS permissions within branch.
- Patient: view approved patient-facing documents only.

## UI Screens to Build in HIMS

### Patient Profile: Documents Tab

Must show:

- upload button
- document table
- status badge
- type
- uploaded date
- processed date
- summary snippet
- preview action
- review action if permission allows

Filters:

- all
- clinical
- lab
- radiology
- billing
- pending review
- failed

### Patient Profile: Clinical Timeline Tab

Merged timeline:

- HIMS visits
- vitals
- lab/radiology orders
- DMS uploaded records
- discharge summaries
- prescriptions

DMS events should be visually normal, not branded as AI.

### Doctor Consultation: Previous Records Panel

Compact panel with:

- latest DMS summary
- last 5 documents
- abnormal lab/radiology highlights
- old prescriptions
- preview links

### Doctor Consultation: Similar Cases Panel

Must show:

- `Find Similar Cases` button
- loading state
- match cards
- score
- reasons
- source date
- document type
- view source
- feedback buttons: useful, not useful, wrong match, unsafe

Do not auto-fill treatment from similar cases.

### Document Review Queue

For document staff:

- pending match
- extraction failed
- needs manual verification
- duplicate suspected
- reprocess option
- verify patient link
- reject document

### Admin Diagnostics

For admin:

- DMS connection status
- webhook status
- failed events
- failed syncs
- extraction failures
- embedding/vector failures
- retry button

## Sync Rules and Conflict Handling

### Patient Updates

HIMS is the source of truth for patient demographics.

If patient phone/name/MRN changes in HIMS:

- HIMS sends update to DMS.
- DMS updates linked patient reference.
- DMS does not overwrite HIMS demographics.

If DMS extracts a different name/phone from an uploaded document:

- DMS marks it as possible mismatch.
- HIMS shows it in review queue.
- Staff decides whether it is wrong patient, old phone, spelling difference, or new patient.

### Document Status

DMS is the source of truth for document processing status.

HIMS only caches status for display.

### Similar Case Results

DMS is the source of truth for similarity scoring.

HIMS stores search audit and doctor feedback.

### Visit Summaries

HIMS is the source of truth for finalized visit notes.

DMS stores a copy only for search, summary, and similarity intelligence.

## Failure Handling

### If DMS Is Down

HIMS should:

- keep HIMS workflows working
- show DMS status as unavailable
- queue patient sync/document upload attempts if possible
- allow retry later

Doctor consultation should still work without DMS.

### If HIMS Webhook Fails

DMS should:

- retry webhook delivery
- store delivery status
- show failed webhook in DMS admin diagnostics
- not reprocess document unnecessarily

### If Gemini Fails

DMS should:

- save original document
- save local extracted text if available
- mark AI status failed
- allow manual review
- allow reprocess

### If Vector Search Fails

DMS should:

- still process and save document
- mark similar-case status failed
- show admin diagnostic
- allow backfill/retry after index is fixed

## Production Deployment Shape

Recommended services:

- `hims-api`
- `hims-web`
- `hims-worker`
- `dms-api`
- `dms-web`
- `dms-worker`
- `mongodb`
- `redis`
- `minio` or external S3
- `nginx`

Recommended URLs:

- `https://hims.example.com`
- `https://dms-admin.example.com`
- internal API: `http://dms-api:8000`
- internal API: `http://hims-api:8000`

Only HIMS should be the primary URL for hospital staff.

DMS admin URL should be restricted by role, VPN, IP allowlist, or admin-only access policy.

## Development Milestones

### Milestone 1: Bridge Health

Done when:

- HIMS can call DMS `/bridge/health`.
- DMS can call HIMS webhook test endpoint.
- Both requests are API-key protected.
- Request IDs appear in logs.

### Milestone 2: Patient Sync

Done when:

- creating a HIMS patient creates DMS patient reference
- updating HIMS patient updates DMS patient reference
- failed sync is visible in HIMS diagnostics
- backfill existing patients works

### Milestone 3: Document Upload and Status

Done when:

- HIMS uploads document to DMS
- DMS processes document
- HIMS receives webhook
- patient profile shows document
- secure preview opens

### Milestone 4: Review Workflow

Done when:

- unmatched document appears in HIMS review queue
- staff can link to correct patient
- staff can reject/reprocess
- DMS and HIMS statuses stay aligned

### Milestone 5: Doctor View

Done when:

- consultation page shows DMS summary and documents
- doctor can open old documents
- doctor can search similar previous cases
- doctor feedback is saved

### Milestone 6: Enterprise Hardening

Done when:

- audit logs cover all sensitive actions
- tenant isolation tests pass
- upload security tests pass
- background jobs and retries work
- admin diagnostics works
- backup/restore procedure exists

## Implementation Priority

Build in this exact order:

1. DMS bridge auth dependency.
2. DMS `/bridge/health`.
3. HIMS `dms_bridge_service.py`.
4. HIMS `/api/integrations/dms/status`.
5. DMS patient upsert endpoint.
6. HIMS patient sync endpoint and trigger.
7. DMS document upload bridge endpoint.
8. HIMS document upload proxy.
9. HIMS webhook receiver.
10. HIMS patient document tab.
11. HIMS document review queue.
12. DMS similar-case live-context endpoint.
13. HIMS doctor similar-case panel.
14. Visit finalization sync from HIMS to DMS.
15. Lab/radiology/IPD hooks.
16. Notifications and admin diagnostics.
17. Security, tests, deployment hardening.

## Final Acceptance Checklist

The system is enterprise-ready only when all are true:

- HIMS is the only daily login needed by normal users.
- DMS can run independently if HIMS is temporarily unavailable.
- HIMS can run core hospital workflows if DMS is temporarily unavailable.
- Every document view/download is audited.
- Every similar-case search is audited.
- Same-patient matches are excluded by default.
- Cross-tenant data never appears.
- Patient-uploaded files require staff verification.
- Similar cases are clearly reference-only.
- DMS failures are visible to admins, not hidden from workflow owners.
- Background jobs can retry safely.
- Webhooks are idempotent.
- Uploads are secure and not publicly exposed.
- Backups and restores are documented and tested.
