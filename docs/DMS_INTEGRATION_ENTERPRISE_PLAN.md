# DMS to HIMS Integration and Enterprise Readiness Plan

## Executive Direction

The existing HIMS project should remain the system of record for hospital operations: tenants, branches, users, patients, appointments, queue, consultation, lab, radiology, pharmacy, billing, IPD, OT, telemedicine, reports, audit, and mobile apps.

`DMS-Project` should not be integrated as a second standalone application. Its strongest parts should be merged into HIMS as a Clinical Document Intelligence module:

- secure document ingestion
- text extraction from PDF/image/TXT
- Gemini structured extraction
- patient matching against HIMS patients
- manual verification workflow
- patient document timeline
- patient clinical summary refresh
- document and patient search
- similar old case recommendations
- protected document preview/download
- document audit trail

This gives HIMS a real enterprise feature hospitals care about: old records become searchable and clinically useful inside the same patient journey.

## Current Architecture Findings

### HIMS Strengths

- FastAPI backend with many operational modules already registered in `backend/main.py`.
- SaaS and branch scoping through `tenant_id` and `branch_id`.
- Role and permission middleware in `backend/middleware/auth.py`.
- Atomic branch-wise MRN generation in `backend/api/patient.py`.
- Secure storage endpoint pattern in `backend/api/storage.py`.
- Health and readiness endpoints already exist.
- Patient duplicate check already exists.
- Web app already has routes for patient, doctor, lab, pharmacy, billing, IPD, OT, radiology, emergency, feedback, blood bank, and portal.
- Inventory bridge service already exists conceptually.

### DMS Strengths

- Mature document upload and processing flow in `DMS-Project/backend/app/routes/documents.py`.
- Local text extraction, Gemini extraction, structured data normalization, and medical document validation.
- Patient matching service.
- Patient summary service.
- Patient timeline service.
- Similar case service with embeddings and vector search.
- Document-specific RBAC model.
- Manual review/verify/reject workflow.
- Protected document file serving.

### Main Mismatch

HIMS patients use Mongo `_id`, `mrn`, `first_name`, `last_name`, `phone`, `dob`, `tenant_id`, and `branch_id`.

DMS patients use a simpler `patient_id`, `name`, `mobile`, `age`, `gender`, and `uhid` model.

The integration must adapt DMS services to HIMS patient shape instead of creating a parallel patient registry.

## Target Module Design

Add a HIMS module named Clinical Documents.

Recommended backend routes:

- `POST /api/clinical-documents/upload`
- `GET /api/clinical-documents`
- `GET /api/clinical-documents/{document_id}`
- `GET /api/clinical-documents/{document_id}/file`
- `PUT /api/clinical-documents/{document_id}/verify`
- `PUT /api/clinical-documents/{document_id}/reject`
- `DELETE /api/clinical-documents/{document_id}`
- `POST /api/clinical-documents/backfill-similarity-embeddings`
- `GET /api/patients/{patient_id}/clinical-documents`
- `GET /api/patients/{patient_id}/clinical-summary`
- `GET /api/patients/{patient_id}/timeline`
- `GET /api/search/clinical-documents`
- `GET /api/similar-cases/document/{document_id}`
- `POST /api/similar-cases/{recommendation_id}/feedback`

Recommended frontend pages:

- `/documents/upload`
- `/documents/review`
- `/documents/:id`
- Patient detail tab: `Documents`
- Patient detail tab: `Clinical Summary`
- Patient detail tab: `Timeline`
- Doctor consultation panel: old documents and similar old cases
- Admin diagnostics page for extraction, embedding, and vector search health

## Data Model Plan

Use HIMS tenant and branch fields on every DMS-derived collection.

New or extended collections:

- `clinical_documents`
- `clinical_document_extractions`
- `patient_timeline`
- `patient_clinical_summaries`
- `similar_case_recommendations`
- `clinical_document_embedding_jobs`

Important fields for `clinical_documents`:

- `tenant_id`
- `branch_id`
- `patient_id` as HIMS patient `_id`
- `mrn`
- `document_id`
- `document_type`
- `original_filename`
- `stored_file_id` or `stored_file_path`
- `status`
- `extracted_text`
- `summary`
- `is_medical_document`
- `patient_match_confidence`
- `suggested_patient_id`
- `requires_manual_review`
- `review_reason`
- `clinical_text_for_similarity`
- `clinical_embedding`
- `similar_case_status`
- `similar_case_error`
- audit fields from `inject_audit_fields`

Indexes:

- `tenant_id + branch_id + uploaded_at`
- `tenant_id + patient_id + uploaded_at`
- `tenant_id + document_id`, unique
- `status`
- `document_type`
- `deleted_at` or `is_deleted`
- Atlas Vector Search index on `clinical_embedding`, 768 dimensions, cosine similarity

## Integration Phases

### Phase 1: Backend Foundation

Create a HIMS-native clinical document router and collections.

Port these DMS services with HIMS imports and data shape changes:

- `file_service.py`
- `document_text_extraction_service.py`
- `gemini_service.py`
- `document_summary_service.py`
- `patient_match_service.py`
- `patient_summary_service.py`
- `timeline_service.py`
- `embedding_service.py`
- `similar_case_service.py`

Keep HIMS middleware:

- use `get_current_user`
- use `require_permission`
- use `get_tenant_filter`
- use `get_branch_filter`
- use `inject_audit_fields`
- use `create_audit_log`

Do not copy DMS auth wholesale.

### Phase 2: Patient Matching Adapter

Map extracted DMS patient fields to HIMS patients:

- extracted `uhid` -> HIMS `mrn`
- extracted `mobile` -> HIMS `phone`
- extracted `name` -> HIMS `first_name + last_name`
- extracted `age` -> derived from HIMS `dob`
- extracted `gender` -> HIMS `gender`

Matching order:

1. exact MRN
2. exact phone within tenant
3. name + DOB or age + gender
4. fuzzy name with manual review

Never auto-create a HIMS patient unless minimum identity is strong: name plus phone, or name plus age/gender plus hospital context. In enterprise mode, prefer manual review over silent wrong linking.

### Phase 3: Secure Storage Unification

Use HIMS storage rules rather than DMS local-only paths.

Short term:

- store files in HIMS `uploads/clinical-documents`
- store metadata in `stored_files`
- serve only through authenticated signed routes

Production:

- move to S3 or MinIO
- encrypt at rest
- generate short-lived signed URLs
- audit every view/download

### Phase 4: Frontend Integration

Do not bring the Next.js DMS UI into the Vite HIMS frontend directly.

Rebuild the DMS screens as HIMS React pages using existing HIMS layout and route guards:

- upload queue with progress
- document review worklist
- document detail with preview, extraction, patient match, verify/reject
- patient detail document tab
- patient clinical timeline
- patient summary card for doctors
- similar cases card in doctor consultation

Recommended role access:

- Receptionist: upload basic documents, search basic patient documents
- Document staff: upload, review, verify, reject, view extraction
- Doctor: view clinical docs, summaries, similar cases, add feedback
- Lab/Radiology: view/upload result documents for their modules
- Admin/Branch admin: full access and diagnostics

### Phase 5: Clinical Workflow Hooks

Connect documents to real hospital workflows:

- Registration: upload ID proof, consent, old prescriptions
- Consultation: doctor sees old documents and summary before SOAP notes
- Lab: verified lab PDFs attach to patient timeline
- Radiology: verified imaging reports attach to patient timeline
- IPD: admission/discharge documents attach to patient timeline
- Billing/TPA: invoices and insurance documents attach with restricted access
- Patient portal/mobile: patients can view allowed documents and upload external records for review

### Phase 6: Similar Case Intelligence

Use DMS similar-case logic carefully as doctor support, not diagnosis.

Required production safeguards:

- only compare across same tenant unless explicitly allowed
- exclude same patient from recommendations
- require verified medical documents
- show reasons and source documents
- allow doctor feedback: useful, not useful, unsafe, wrong patient
- show “needs doctor verification” language
- never auto-change diagnosis, prescription, or treatment based on similarity

### Phase 7: Enterprise Hardening

Before production, prioritize:

- real OTP/SMS provider and OTP expiry/retry limits
- strict upload MIME validation, content sniffing, file size limits, antivirus scan
- S3/MinIO object storage, no public static medical files
- full audit coverage for document view/download/verify/reject/linking
- backup and restore scripts
- MongoDB auth in compose/deployment
- Celery worker in compose for document processing
- background jobs for extraction, summary, embedding, and retries
- admin diagnostics for failed extraction, failed AI, failed vector search
- pagination on all lists
- notification bell and unread notification API
- patient and doctor mobile document screens
- CI tests for auth, tenant isolation, patient matching, upload security, and document verification

## Recommended Implementation Order

1. Add HIMS clinical document collections, indexes, permissions, and router shell.
2. Port DMS text extraction and Gemini extraction into HIMS.
3. Add HIMS patient matching adapter.
4. Add upload, review, verify, reject APIs.
5. Add patient timeline and patient clinical summary APIs.
6. Add frontend upload/review/detail pages.
7. Add patient detail tabs for documents, timeline, summary.
8. Add doctor consultation document panel.
9. Port similar-case embedding and vector search.
10. Add background processing and backfill jobs.
11. Add storage hardening and enterprise audit coverage.
12. Add mobile document access and upload.
13. Run end-to-end patient lifecycle testing.

## Final Enterprise Vision

The final enterprise HIMS should feel like one connected hospital operating system:

- Reception registers patients and uploads old records.
- DMS intelligence extracts and links documents safely.
- Nurses record vitals.
- Doctors see the full history, summaries, old files, similar old cases, labs, prescriptions, and billing context in one place.
- Lab/radiology/pharmacy/billing/IPD/OT all write back to the same patient timeline.
- Patients can view their approved records, bills, appointments, and telehealth sessions.
- Admins can audit every sensitive action.
- Management can see operational and financial reports by tenant and branch.

The DMS module is the missing memory layer. Integrating it properly will make HIMS much closer to a real enterprise hospital product.
