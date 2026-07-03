# Project Code Understanding - Hospital AI DMS

This file is a one-read handoff for another AI/developer. It documents the current codebase as inspected from the repository, including backend logic, frontend logic, MongoDB collections, APIs, upload flow, patient matching, similar-case matching, vector search, RBAC, and known issues.

## 1. Project Overview

This project is a single-hospital AI Document Management System. It lets hospital staff upload PDF/image/text documents, stores the original files privately, extracts text and structured clinical metadata, links the document to a patient, refreshes patient summaries, builds patient timelines, and finds possible similar clinical cases from older documents.

The system is document intelligence software, not a full Hospital Management System. It does not manage appointments, admissions operations, pharmacy inventory, billing workflow, treatment decisions, or final diagnosis. Medical/clinical output is intended for review by qualified hospital staff.

Main capabilities:

- Secure login with JWT and role-based permissions.
- Upload PDF, JPG, JPEG, PNG, and TXT files.
- Store originals under `backend/uploads`.
- Extract readable text using local PDF/image/text extraction.
- Use Gemini to extract structured hospital document data.
- Match uploaded documents to existing patients or create a new patient when safe.
- Put unreadable/unmatched documents into manual review.
- Generate document summaries and patient-level summaries.
- Store patient timeline entries.
- Search patients and documents.
- Recommend possible similar clinical cases using embeddings and MongoDB Atlas Vector Search.
- Serve document preview/download through protected backend APIs.
- Log important actions in audit logs.

## 2. Tech Stack

Frontend:

- Next.js 14 app router.
- TypeScript.
- React 18.
- Tailwind CSS.
- Lucide React icons.
- Browser `localStorage` for JWT and current user cache.

Backend:

- FastAPI.
- Python 3.12 in Docker.
- Motor async MongoDB driver.
- PyMongo.
- Pydantic / pydantic-settings.
- JWT via `python-jose`.
- Password hashing via `bcrypt`.

Database:

- MongoDB Atlas or local MongoDB-compatible URI.
- MongoDB Compass is used manually for viewing/managing data.
- Atlas Vector Search is required for similar-case vector search.

AI and extraction:

- Gemini `generateContent` for structured document extraction.
- Gemini `models/text-embedding-004` for embeddings.
- `pypdf` for PDF text extraction.
- Pillow + pytesseract for image OCR if local Tesseract is installed/configured.

Storage:

- Local private file storage under `backend/uploads`.
- Docker Compose mounts `./backend/uploads:/app/uploads`.

Auth/security:

- JWT bearer auth.
- Backend-enforced permission checks with `require_permission`.
- Frontend hides UI based on permissions but does not provide real security.

Deployment/dev:

- `backend/Dockerfile`.
- `frontend/Dockerfile`.
- `docker-compose.yml`.
- Backend default port: `8000`.
- Frontend default port: `3000`.

## 3. Folder Structure

Important project structure:

```text
DMS main/
  README.md
  Project.md
  matching.md
  PROJECT_CODE_UNDERSTANDING.md
  docker-compose.yml

  backend/
    Dockerfile
    requirements.txt
    uploads/
    app/
      __init__.py
      main.py
      config.py
      database.py
      auth/
        dependencies.py
        permissions.py
      models/
        user_model.py
        document_model.py
      schemas/
        user_schema.py
        patient_schema.py
        document_schema.py
      routes/
        auth.py
        users.py
        patients.py
        documents.py
        similar_cases.py
        search.py
        dashboard.py
        audit.py
      services/
        audit_service.py
        document_summary_service.py
        document_text_extraction_service.py
        embedding_service.py
        file_service.py
        gemini_service.py
        patient_match_service.py
        patient_summary_service.py
        similar_case_service.py
        timeline_service.py
      utils/
        id_generator.py
        response.py
        security.py

  frontend/
    Dockerfile
    package.json
    next.config.mjs
    tailwind.config.ts
    tsconfig.json
    app/
      layout.tsx
      page.tsx
      globals.css
      login/page.tsx
      dashboard/page.tsx
      patients/page.tsx
      patients/[id]/page.tsx
      documents/upload/page.tsx
      documents/[id]/page.tsx
      search/page.tsx
      users/page.tsx
      audit-logs/page.tsx
    components/
      SimilarCasesCard.tsx
      layout/AppShell.tsx
      ui/Button.tsx
      ui/Field.tsx
    lib/
      api.ts
      auth.ts
      types.ts
```

Important backend files:

- `backend/app/main.py`
  - What it does: Creates the FastAPI app, configures CORS, creates upload directory on startup, calls `ensure_indexes()`, registers routers, exposes `/health`.
  - Called by: Uvicorn command in `backend/Dockerfile` and local dev command.
  - Calls: `get_settings`, `ensure_indexes`, route modules.
  - Importance: App entry point.

- `backend/app/config.py`
  - What it does: Defines `Settings` loaded from `backend/.env`.
  - Called by: Most backend services/routes through `get_settings()`.
  - Calls: Pydantic settings.
  - Importance: Central source for MongoDB URI, JWT config, Gemini config, upload config, CORS.

- `backend/app/database.py`
  - What it does: Creates lazy `AsyncIOMotorClient`, exposes `db`, creates indexes.
  - Called by: All routes/services needing MongoDB.
  - Calls: `AsyncIOMotorClient`.
  - Importance: Database connection and collection index definitions.

- `backend/app/auth/dependencies.py`
  - What it does: Decodes JWT, loads active user, exposes `get_current_user`, `require_permission`, `require_roles`, `require_any_permission`.
  - Called by: Protected routes.
  - Calls: `decode_token`, `db.users`, `has_permission`.
  - Importance: Backend auth gate.

- `backend/app/auth/permissions.py`
  - What it does: Defines all permissions, role permission sets, helper `has_permission`, document access rules, and `public_user`.
  - Called by: Auth dependencies, frontend-facing auth routes, document route.
  - Calls: `UserRole`.
  - Importance: RBAC policy source.

- `backend/app/routes/auth.py`
  - What it does: Admin seed, login, current user endpoint.
  - Called by: Frontend login and `AppShell`.
  - Calls: `db.users`, password hashing/verification, JWT creation, audit logging.
  - Importance: Authentication flow.

- `backend/app/routes/users.py`
  - What it does: Admin user management.
  - Called by: `frontend/app/users/page.tsx`.
  - Calls: `db.users`, `hash_password`, `log_action`.
  - Importance: Staff/account management.

- `backend/app/routes/patients.py`
  - What it does: Create/list/search/get/update patients, fetch patient summary/documents/timeline.
  - Called by: patients pages and document verification page.
  - Calls: `db.patients`, `db.documents`, `db.patient_timeline`, `refresh_patient_summary`.
  - Importance: Patient profile and summary APIs.

- `backend/app/routes/documents.py`
  - What it does: Upload, process, list, detail, preview/download, Gemini reprocess, verify, reject, soft-delete documents.
  - Called by: upload page, document detail page, patient page downloads.
  - Calls: file saving, text extraction, Gemini extraction, patient matching, document summary, patient summary refresh, timeline service, similar-case service.
  - Importance: Core workflow file.

- `backend/app/routes/similar_cases.py`
  - What it does: Fetch recommendations for one document or patient; store doctor feedback.
  - Called by: `SimilarCasesCard`.
  - Calls: `db.similar_case_recommendations`, `db.documents`, `db.patients`, audit logging.
  - Importance: Similar-case display and feedback APIs.

- `backend/app/routes/search.py`
  - What it does: Search patients and documents.
  - Called by: document detail patient search and search page.
  - Calls: `db.patients`, `db.documents`, `db.document_extractions`.
  - Importance: Manual patient selection and document discovery.

- `backend/app/routes/dashboard.py`
  - What it does: Dashboard counts and recent uploads.
  - Called by: dashboard page.
  - Calls: `db.patients`, `db.documents`.
  - Importance: Admin/overview metrics.

- `backend/app/routes/audit.py`
  - What it does: Returns recent audit logs.
  - Called by: audit logs page.
  - Calls: `db.audit_logs`.
  - Importance: Administrative audit view.

- `backend/app/services/file_service.py`
  - What it does: Validates extension/MIME/size and saves uploaded file privately.
  - Called by: `routes/documents.py`.
  - Calls: filesystem via `Path`.
  - Importance: Upload security/storage boundary.

- `backend/app/services/document_text_extraction_service.py`
  - What it does: Extracts text from PDFs, images, and text files.
  - Called by: document processing.
  - Calls: `pypdf`, `pytesseract`, Pillow.
  - Importance: Local text extraction before AI summary/matching.

- `backend/app/services/gemini_service.py`
  - What it does: Sends files to Gemini for structured extraction, validates JSON schema, merges local PDF fallback extraction.
  - Called by: document processing.
  - Calls: Gemini API over `httpx`.
  - Importance: Main AI extraction logic.

- `backend/app/services/document_summary_service.py`
  - What it does: Builds a document-level summary from extracted fields or text fallback.
  - Called by: document processing.
  - Importance: Summary shown in patient documents and search.

- `backend/app/services/patient_match_service.py`
  - What it does: Scores extracted patient data against existing patients.
  - Called by: document processing.
  - Calls: `db.patients`.
  - Importance: Existing-patient linking.

- `backend/app/services/patient_summary_service.py`
  - What it does: Builds patient-level summary from all patient documents/extractions, optionally refines with Gemini, saves embedded summary on patient.
  - Called by: patient summary route and document processing after link/verify.
  - Calls: `db.patients`, `db.documents`, `db.document_extractions`, Gemini API.
  - Importance: Clinical summary on patient profile.

- `backend/app/services/embedding_service.py`
  - What it does: Creates embeddings using Gemini `models/text-embedding-004`; includes cosine helper retained for compatibility.
  - Called by: `similar_case_service.py`.
  - Calls: Gemini embedding API.
  - Importance: Embedding generation for vector search.

- `backend/app/services/similar_case_service.py`
  - What it does: Builds clinical text, creates embeddings, stores embedding fields on document, runs MongoDB Atlas `$vectorSearch`, applies clinical safety gates, saves current-document recommendations.
  - Called by: document upload/verify processing.
  - Calls: `db.documents`, `db.document_extractions`, `db.similar_case_recommendations`, `db.patients`, `create_embedding`, audit logging.
  - Importance: Similar clinical case recommendation engine.

- `backend/app/services/timeline_service.py`
  - What it does: Inserts patient timeline entries.
  - Called by: document upload/verify.
  - Calls: `db.patient_timeline`.
  - Importance: Patient profile timeline.

- `backend/app/services/audit_service.py`
  - What it does: Inserts audit log entries.
  - Called by: auth/user/patient/document/similar-case flows.
  - Calls: `db.audit_logs`.
  - Importance: Traceability.

- `backend/app/utils/id_generator.py`
  - What it does: Generates sequence IDs using `settings` collection counters.
  - Called by: patient/document/similar-case creation.
  - Calls: `db.settings.find_one_and_update`.
  - Importance: Creates IDs like `HSP-000001`, `DOC-000001`, `SIM-000001`.

- `backend/app/utils/response.py`
  - What it does: Serializes ObjectIds/datetimes and removes private file path keys.
  - Called by: most routes.
  - Importance: Prevents raw local paths from leaking.

- `backend/app/utils/security.py`
  - What it does: Password hashing, password verification, JWT create/decode.
  - Called by: auth routes and auth dependencies.
  - Importance: Auth token lifecycle.

Important frontend files:

- `frontend/lib/api.ts`
  - What it does: Defines `API_URL`, `api<T>()`, bearer header injection, JSON error formatting, 401 logout/redirect, helper calls for patient summary/documents.
  - Called by: Nearly all frontend pages/components.
  - Calls: `getToken`, `clearToken`, browser `fetch`.
  - Importance: Frontend API client.

- `frontend/lib/auth.ts`
  - What it does: Stores/gets token and current user in localStorage; checks permissions.
  - Called by: login page, AppShell, pages/components.
  - Importance: Frontend auth state.

- `frontend/lib/types.ts`
  - What it does: Defines TypeScript types for users, patients, summaries, documents, similar-case recommendations, document types.
  - Called by: pages/components.
  - Importance: Frontend data contracts.

- `frontend/components/layout/AppShell.tsx`
  - What it does: Authenticated layout, navigation, theme toggle, `/auth/me` refresh, permission-based nav filtering, logout.
  - Called by: most pages except login and document-only iframe view.
  - Calls: `api("/auth/me")`, local auth helpers.
  - Importance: Frontend shell and route guard behavior.

- `frontend/components/SimilarCasesCard.tsx`
  - What it does: Displays possible similar case recommendations, fetches by document/patient when not given direct props, supports doctor feedback and inline document preview.
  - Called by: upload page and document detail page.
  - Calls: similar-case APIs and document preview route.
  - Importance: Similar-case UI.

- `frontend/app/documents/upload/page.tsx`
  - What it does: Uploads files using XMLHttpRequest progress, clears old similar cases, stores response, displays uploaded documents and current matches.
  - Calls: `POST /documents/upload`, `SimilarCasesCard`.
  - Importance: Upload UX and fresh similar-case display rule.

- `frontend/app/documents/[id]/page.tsx`
  - What it does: Document preview/review page, patient search, verify/reject, protected file preview/download, compact similar-case card.
  - Calls: `/documents/{id}`, `/documents/{id}/file`, `/documents/{id}/verify`, `/documents/{id}/reject`, `/search/patients`.
  - Importance: Manual review and document viewing.

- `frontend/app/patients/page.tsx`
  - What it does: Debounced patient search and patient creation.
  - Calls: `/patients`, `POST /patients`.
  - Importance: Patient list and receptionist/admin workflow.

- `frontend/app/patients/[id]/page.tsx`
  - What it does: Patient profile, clinical summary, documents list/download, timeline, edit patient details.
  - Calls: `/patients/{id}`, `/patients/{id}/summary`, `/patients/{id}/documents`, `/patients/{id}/timeline`, `PUT /patients/{id}`.
  - Importance: Main patient view.

- `frontend/app/search/page.tsx`
  - What it does: Document search UI.
  - Calls: `/search/documents`.
  - Importance: Search workflow.

- `frontend/app/users/page.tsx`
  - What it does: Create/list users.
  - Calls: `/users`.
  - Importance: Admin user management.

- `frontend/app/dashboard/page.tsx`
  - What it does: Dashboard metrics and recent uploads.
  - Calls: `/dashboard/stats`.
  - Importance: Admin overview.

- `frontend/app/audit-logs/page.tsx`
  - What it does: Audit log list.
  - Calls: `/audit-logs`.
  - Importance: Audit trail UI.

## 4. Backend Architecture

FastAPI entry point:

- `backend/app/main.py`
- Instantiates `FastAPI(title=settings.app_name)`.
- Configures `CORSMiddleware` from comma-separated `settings.cors_origins`.
- Startup handler:
  - Creates `settings.upload_path`.
  - Calls `ensure_indexes()`.
- Health check: `GET /health`.
- Registered routers:
  - `auth.router`
  - `users.router`
  - `patients.router`
  - `documents.router`
  - `similar_cases.router`
  - `search.router`
  - `dashboard.router`
  - `audit.router`

Database:

- `backend/app/database.py`
- `get_database()` lazily creates `AsyncIOMotorClient(settings.mongodb_uri)`.
- Returns `client[settings.database_name]`.
- `DatabaseProxy` exposes dynamic collection attributes like `db.users`.
- `ensure_indexes()` creates normal MongoDB indexes. It does not create Atlas Vector Search indexes.

Auth/JWT flow:

1. User calls `POST /auth/login`.
2. `routes/auth.py` finds active user by lowercased email.
3. Password is checked by `verify_password`.
4. `create_access_token(user["email"], user["role"])` creates JWT with `sub`, `role`, `exp`.
5. Frontend stores token in `localStorage` key `dms_token`.
6. `api<T>()` sends `Authorization: Bearer <token>`.
7. Backend `get_current_user()` decodes token and loads active user from `db.users`.
8. Protected routes use `require_permission("permission.name")`.

RBAC:

- Permissions live in `backend/app/auth/permissions.py`.
- Backend permission checks are real enforcement.
- Frontend permission checks are UI hiding only.
- Inactive users are rejected because `get_current_user()` queries `{"email": payload["sub"], "is_active": True}`.

Models/schemas:

- User role enum: `backend/app/models/user_model.py`.
- Document status enum and allowed document types: `backend/app/models/document_model.py`.
- Request schemas:
  - `UserCreate`, `UserUpdate`, `LoginRequest`.
  - `PatientCreate`, `PatientUpdate`.
  - `DocumentVerify`, `DocumentReject`.
- MongoDB documents are mostly plain dictionaries built in routes/services, not ODM models.

Services:

- File validation/storage: `file_service.py`.
- Text extraction: `document_text_extraction_service.py`.
- Gemini extraction: `gemini_service.py`.
- Document summary: `document_summary_service.py`.
- Patient matching: `patient_match_service.py`.
- Patient summary: `patient_summary_service.py`.
- Embeddings: `embedding_service.py`.
- Similar cases: `similar_case_service.py`.
- Timeline: `timeline_service.py`.
- Audit logs: `audit_service.py`.

Utilities:

- `security.py`: password/JWT.
- `response.py`: serialization and private field removal.
- `id_generator.py`: sequence IDs in `settings` collection.

## 5. Frontend Architecture

Next.js app structure:

- Uses app router under `frontend/app`.
- Root redirect: `frontend/app/page.tsx` redirects to `/login`.
- Global layout: `frontend/app/layout.tsx`.
- Authenticated pages use `AppShell`.

Main pages:

- `/login`: `frontend/app/login/page.tsx`.
- `/dashboard`: `frontend/app/dashboard/page.tsx`.
- `/patients`: `frontend/app/patients/page.tsx`.
- `/patients/[id]`: `frontend/app/patients/[id]/page.tsx`.
- `/documents/upload`: `frontend/app/documents/upload/page.tsx`.
- `/documents/[id]`: `frontend/app/documents/[id]/page.tsx`.
- `/search`: `frontend/app/search/page.tsx`.
- `/users`: `frontend/app/users/page.tsx`.
- `/audit-logs`: `frontend/app/audit-logs/page.tsx`.

API client:

- `frontend/lib/api.ts`.
- `API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"`.
- Adds JSON `Content-Type` unless body is `FormData`.
- Adds bearer token if present.
- On 401, clears auth and redirects to `/login`.

Auth handling:

- `frontend/lib/auth.ts`.
- Stores:
  - `dms_token`
  - `dms_user`
  - `dms_theme`
- `AppShell` refreshes user with `/auth/me`.
- `hasPermission()` checks cached user permissions.

Upload state management:

- `frontend/app/documents/upload/page.tsx`.
- State:
  - `files`
  - `documents`
  - `similarCases`
  - `uploadResult`
  - `uploadState`
  - `progress`
  - `serverProgress`
  - `estimatedTotalSeconds`
- Before upload:
  - `setDocuments([])`
  - `setSimilarCases([])`
  - `setUploadResult(null)`
- After upload:
  - `setUploadResult(result)`
  - `setDocuments(result.documents)`
  - `setSimilarCases(result.similar_cases || [])`
- Per document:
  - `similarCasesForDocument(doc.document_id)` filters current response matches.
  - Similar card is rendered only when `documentSimilarCases.length > 0`.
  - Current UI also shows `No Matching` below details saved when there are no matches for that document.

Patient page:

- `frontend/app/patients/[id]/page.tsx`.
- Loads patient, documents, optional timeline, optional clinical summary.
- Shows structured clinical summary sections.
- Allows edit if `patients.update_basic`.
- Allows downloads if `documents.download`.

Document detail page:

- `frontend/app/documents/[id]/page.tsx`.
- Loads document/extraction.
- Displays preview through protected file route with token query parameter.
- Allows patient search, verify, reject if permitted.
- Embeds compact `SimilarCasesCard documentId={id}`.
- Has special `?view=document` mode for iframe-only preview from similar-case card.

Similar case card:

- If `similarCases` prop is provided, uses those cases only.
- If no prop is provided, fetches:
  - `/documents/{documentId}/similar-cases`
  - or `/patients/{patientId}/similar-cases`
- Compact empty mode returns `null`.
- Non-compact empty mode renders `No similar clinical cases found above 75% similarity.`

## 6. Database Structure

Collection: `users`

- Purpose: User accounts for staff/admin.
- Example shape:

```json
{
  "_id": "...",
  "name": "Admin",
  "email": "admin@example.com",
  "password_hash": "...",
  "role": "admin",
  "permissions": [],
  "is_active": true,
  "created_at": "2026-06-17T00:00:00Z",
  "updated_at": "2026-06-17T00:00:00Z"
}
```

- Important fields: `email`, `password_hash`, `role`, `permissions`, `is_active`.
- Indexes:
  - `email` unique.
- Read/write files:
  - `routes/auth.py`
  - `routes/users.py`
  - `auth/dependencies.py`
  - `routes/documents.py` file access token path.

Collection: `patients`

- Purpose: Patient records and embedded patient summaries.
- Example shape:

```json
{
  "_id": "...",
  "patient_id": "HSP-000001",
  "uhid": "UHID123",
  "name": "Patient Name",
  "mobile": "9999999999",
  "email": "",
  "age": 40,
  "gender": "Male",
  "address": "",
  "blood_group": "",
  "patient_summary": {
    "patient_id": "HSP-000001",
    "broad_description": "...",
    "structured_summary_json": {},
    "source_document_ids": ["DOC-000001"],
    "generation_status": "success",
    "generation_error": null,
    "last_generated_at": "..."
  },
  "summary_updated_at": "...",
  "created_at": "...",
  "updated_at": "..."
}
```

- Important fields: `patient_id`, `uhid`, `name`, `mobile`, `age`, `gender`, `patient_summary`.
- Indexes:
  - `patient_id` unique.
  - text index on `name`, `mobile`, `patient_id`.
  - `name`, `mobile`, `uhid`, `gender`, `created_at`.
- Read/write files:
  - `routes/patients.py`
  - `routes/documents.py`
  - `routes/search.py`
  - `routes/dashboard.py`
  - `services/patient_match_service.py`
  - `services/patient_summary_service.py`
  - `services/similar_case_service.py`
  - `routes/similar_cases.py`

Collection: `documents`

- Purpose: Metadata/status for uploaded files; links files to patients; stores extraction status, summaries, embeddings.
- Example shape:

```json
{
  "_id": "...",
  "document_id": "DOC-000001",
  "patient_id": "HSP-000001",
  "patient_name": "Patient Name",
  "mobile_number": "9999999999",
  "age": 40,
  "gender": "Male",
  "address": "",
  "document_type": "Prescription",
  "status": "verified",
  "patient_match_confidence": 0.85,
  "suggested_patient_id": "HSP-000001",
  "match_reason": ["Name exact match"],
  "file_name": "report.pdf",
  "original_filename": "report.pdf",
  "stored_file_path": "uploads/DOC-000001/uuid.pdf",
  "storage_type": "local_private",
  "file_type": "pdf",
  "mime_type": "application/pdf",
  "file_size": 12345,
  "size_bytes": 12345,
  "extracted_text": "...",
  "extraction_status": "success",
  "extraction_error": null,
  "summary": "...",
  "summary_status": "success",
  "summary_error": null,
  "ai_status": "success",
  "ai_error": null,
  "clinical_text_for_similarity": "Diagnosis: ...",
  "clinical_embedding": [0.012, -0.045],
  "similar_case_status": "processed",
  "verified_by": "system_auto_match",
  "verified_at": "...",
  "requires_manual_review": false,
  "review_reason": null,
  "uploaded_by": "staff@example.com",
  "uploaded_at": "...",
  "upload_date": "...",
  "deleted_at": null,
  "created_at": "...",
  "updated_at": "..."
}
```

- Important fields: `document_id`, `patient_id`, `document_type`, `status`, `stored_file_path`, `summary`, `clinical_embedding`, `similar_case_status`, `deleted_at`.
- Indexes:
  - `document_id` unique.
  - compound `(patient_id, document_type, uploaded_at desc)`.
  - `patient_id`, `deleted_at`, `document_type`, `uploaded_at`, `patient_name`, `mobile_number`.
  - partial normal index named `documents_clinical_embedding_exists` on `document_id` when `clinical_embedding` exists.
  - Atlas Vector Search index must be created manually; see section 11.
- Read/write files:
  - `routes/documents.py`
  - `routes/patients.py`
  - `routes/search.py`
  - `routes/dashboard.py`
  - `routes/similar_cases.py`
  - `services/patient_summary_service.py`
  - `services/similar_case_service.py`

Collection: `document_extractions`

- Purpose: Stores Gemini/local extracted structured data and verified data for each document.
- Example shape:

```json
{
  "_id": "...",
  "document_id": "DOC-000001",
  "gemini_raw_output": {},
  "extracted_text": "...",
  "extraction_status": "success",
  "extraction_error": null,
  "extracted_data": {
    "patient_name": "...",
    "document_type": "Prescription",
    "medical_data": {
      "symptoms": [],
      "diagnosis": [],
      "medicines": [],
      "lab_tests": [],
      "procedures": [],
      "advice": [],
      "follow_up": ""
    }
  },
  "verified_data": {},
  "confidence_score": 80,
  "warnings": [],
  "summary": "...",
  "summary_status": "success",
  "summary_error": null,
  "ai_status": "success",
  "ai_error": null,
  "created_at": "...",
  "updated_at": "..."
}
```

- Important fields: `document_id`, `extracted_data`, `verified_data`, `extracted_text`, `summary`.
- Indexes: Not found in `ensure_indexes()`.
- Read/write files:
  - `routes/documents.py`
  - `routes/search.py`
  - `services/patient_summary_service.py`
  - `services/similar_case_service.py`

Collection: `patient_timeline`

- Purpose: Timeline events created when a document is linked/verified.
- Example shape:

```json
{
  "_id": "...",
  "patient_id": "HSP-000001",
  "document_id": "DOC-000001",
  "document_type": "Prescription",
  "summary": "Auto-saved verified document.",
  "event_date": "...",
  "doctor_name": "Dr X",
  "hospital_name": "Hospital",
  "created_at": "..."
}
```

- Important fields: `patient_id`, `document_id`, `document_type`, `event_date`.
- Indexes: Not found in `ensure_indexes()`.
- Read/write files:
  - `services/timeline_service.py`
  - `routes/patients.py`

Collection: `similar_case_recommendations`

- Purpose: Stores fresh recommendation records generated for a specific new document.
- Example shape:

```json
{
  "_id": "...",
  "recommendation_id": "SIM-000001",
  "new_document_id": "DOC-000044",
  "new_patient_id": "HSP-000044",
  "matched_document_id": "DOC-000040",
  "matched_patient_id": "HSP-000040",
  "similarity_score": 82.4,
  "match_strength": "possible",
  "matched_reasons": ["Similar diagnosis found: sinusitis"],
  "status": "doctor_review_required",
  "doctor_feedback": null,
  "safety_warning": "Possible similar clinical case found. Doctor verification required.",
  "created_at": "...",
  "updated_at": "..."
}
```

- Important fields: `recommendation_id`, `new_document_id`, `matched_document_id`, `similarity_score`, `match_strength`, `doctor_feedback`.
- Indexes:
  - `recommendation_id` unique.
  - `new_document_id`, `new_patient_id`, `matched_patient_id`, `similarity_score`, `created_at`.
- Read/write files:
  - `services/similar_case_service.py`
  - `routes/similar_cases.py`

Collection: `audit_logs`

- Purpose: Stores audit trail.
- Example shape:

```json
{
  "_id": "...",
  "action": "document_uploaded",
  "user_email": "staff@example.com",
  "user_role": "document_staff",
  "metadata": {
    "document_id": "DOC-000001"
  },
  "created_at": "..."
}
```

- Important fields: `action`, `user_email`, `user_role`, `metadata`, `created_at`.
- Indexes:
  - `created_at`.
- Read/write files:
  - `services/audit_service.py`
  - `routes/audit.py`

Collection: `settings`

- Purpose: Stores counters for generated IDs.
- Example shape:

```json
{
  "_id": "...",
  "key": "counter:documents",
  "value": 1
}
```

- Important fields: `key`, `value`.
- Indexes: Not found in `ensure_indexes()`.
- Read/write files:
  - `utils/id_generator.py`.

Collection: `patient_summary`

- Separate collection not found. Patient summary is embedded under `patients.patient_summary`.

## 7. API Documentation

All protected APIs use JWT bearer token unless explicitly noted.

### Health

- Method: `GET`
- URL: `/health`
- Request: none.
- Response: `{ "status": "ok" }`
- Auth: none.
- Backend: `backend/app/main.py::health`.
- Collections: none.
- Frontend caller: Not found.

### Auth

- Method: `POST`
- URL: `/auth/register-admin-seed`
- Body: `UserCreate` with role `admin`.
- Response: `{ "message": "Admin created" }`
- Auth: none.
- Backend: `routes/auth.py::register_admin_seed`.
- Collections: reads/writes `users`, writes `audit_logs`.
- Frontend caller: Not found; README uses curl.

- Method: `POST`
- URL: `/auth/login`
- Body: `{ "email": "...", "password": "..." }`
- Response:

```json
{
  "access_token": "...",
  "token_type": "bearer",
  "user": {
    "name": "...",
    "email": "...",
    "role": "admin",
    "permissions": []
  }
}
```

- Auth: none.
- Backend: `routes/auth.py::login`.
- Collections: reads `users`, writes `audit_logs`.
- Frontend caller: `frontend/app/login/page.tsx`.

- Method: `GET`
- URL: `/auth/me`
- Request: bearer token.
- Response: public user object.
- Auth: active user.
- Backend: `routes/auth.py::me`.
- Collections: reads `users`.
- Frontend caller: `frontend/components/layout/AppShell.tsx`.

### Users

- Method: `GET`
- URL: `/users`
- Response: array of public users.
- Auth permission: `users.manage`.
- Backend: `routes/users.py::list_users`.
- Collections: reads `users`.
- Frontend caller: `frontend/app/users/page.tsx`.

- Method: `POST`
- URL: `/users`
- Body: `UserCreate`.
- Response: public user.
- Auth permission: `users.manage`.
- Backend: `routes/users.py::create_user`.
- Collections: writes `users`, writes `audit_logs`.
- Frontend caller: `frontend/app/users/page.tsx`.

- Method: `PUT`
- URL: `/users/{user_id}`
- Path params: `user_id` is email.
- Body: `UserUpdate`.
- Response: updated user without password hash.
- Auth permission: `users.manage`.
- Backend: `routes/users.py::update_user`.
- Collections: updates `users`, writes `audit_logs`.
- Frontend caller: Not found.

- Method: `DELETE`
- URL: `/users/{user_id}`
- Path params: `user_id` is email.
- Response: `{ "message": "User disabled" }`
- Auth permission: `users.manage`.
- Backend: `routes/users.py::delete_user`.
- Collections: updates `users`, writes `audit_logs`.
- Frontend caller: Not found.

### Patients

- Method: `POST`
- URL: `/patients`
- Body: `PatientCreate`.
- Response: created patient.
- Auth permission: `patients.create`.
- Backend: `routes/patients.py::create_patient`.
- Collections: writes `patients`, `settings`, `audit_logs`.
- Frontend caller: `frontend/app/patients/page.tsx`.

- Method: `GET`
- URL: `/patients?search=...` or `/patients?query=...`
- Response: array of patients.
- Auth permission: `patients.search`.
- Backend: `routes/patients.py::list_patients`.
- Collections: reads `patients`.
- Frontend caller: `frontend/app/patients/page.tsx`.

- Method: `GET`
- URL: `/patients/{patient_id}`
- Response: patient object.
- Auth permission: `patients.view_basic`.
- Backend: `routes/patients.py::get_patient`.
- Collections: reads `patients`.
- Frontend caller: `frontend/app/patients/[id]/page.tsx`.

- Method: `PUT`
- URL: `/patients/{patient_id}`
- Body: `PatientUpdate`.
- Response: updated patient.
- Auth permission: `patients.update_basic`.
- Backend: `routes/patients.py::update_patient`.
- Collections: updates `patients`, writes `audit_logs`.
- Frontend caller: `frontend/app/patients/[id]/page.tsx`.

- Method: `GET`
- URL: `/patients/{patient_id}/summary`
- Response: patient summary object.
- Auth permission: `summary.view_clinical`.
- Backend: `routes/patients.py::patient_summary`.
- Collections: reads/writes `patients`, reads `documents`, reads `document_extractions`, writes `audit_logs`.
- Frontend caller: `frontend/lib/api.ts::getPatientSummary`, patient detail page.

- Method: `GET`
- URL: `/patients/{patient_id}/documents`
- Response: documents for patient.
- Auth permission: `documents.view_metadata`.
- Backend: `routes/patients.py::patient_documents`.
- Collections: reads `documents`.
- Frontend caller: `frontend/lib/api.ts::getPatientDocuments`, patient detail page.

- Method: `GET`
- URL: `/patients/{patient_id}/timeline`
- Response: timeline entries.
- Auth permission: `timeline.view`.
- Backend: `routes/patients.py::patient_timeline`.
- Collections: reads `patient_timeline`.
- Frontend caller: patient detail page.

### Documents

- Method: `POST`
- URL: `/documents/upload`
- Body: multipart form field `files`, list of uploaded files.
- Response:

```json
{
  "message": "Document uploaded successfully",
  "documents": [],
  "document": {},
  "patient": {},
  "similar_cases": [],
  "similar_case_status": "processed"
}
```

- Auth permission: `documents.upload`.
- Backend: `routes/documents.py::upload_documents`.
- Collections: writes/reads `documents`, `document_extractions`, `patients`, `patient_timeline`, `similar_case_recommendations`, `settings`, `audit_logs`.
- Frontend caller: `frontend/app/documents/upload/page.tsx`.

- Method: `GET`
- URL: `/documents?status=...`
- Response: list of documents.
- Auth permission: `documents.view_metadata`.
- Backend: `routes/documents.py::list_documents`.
- Collections: reads `documents`.
- Frontend caller: Not found.

- Method: `GET`
- URL: `/documents/{document_id}`
- Response: `{ "document": ..., "extraction": ... }`
- Auth permission: `documents.view_metadata`; extraction content may be reduced based on `documents.view_extraction` / `documents.view_summary`.
- Backend: `routes/documents.py::get_document`.
- Collections: reads `documents`, `document_extractions`, writes `audit_logs`.
- Frontend caller: `frontend/app/documents/[id]/page.tsx`.

- Method: `GET`
- URL: `/documents/{document_id}/file`
- Query/header: bearer token or `?token=...`.
- Response: `FileResponse`.
- Auth: token required; content access checked by `can_access_document`.
- Backend: `routes/documents.py::get_document_file`.
- Collections: reads `users`, `documents`, writes `audit_logs`.
- Frontend caller: document detail page preview.

- Method: `GET`
- URL: `/documents/{document_id}/download`
- Same function/behavior as `/file`.
- Frontend caller: patient page and document detail download.

- Method: `POST`
- URL: `/documents/{document_id}/process-gemini`
- Response: processed document.
- Auth permission: `documents.verify`.
- Backend: `routes/documents.py::process_gemini`.
- Collections: reads/writes same processing collections as upload.
- Frontend caller: Not found.

- Method: `PUT`
- URL: `/documents/{document_id}/verify`
- Body:

```json
{
  "patient_id": "HSP-000001",
  "document_type": "Prescription",
  "verified_data": {}
}
```

- Response: updated document with `similar_cases`.
- Auth permission: `documents.verify`.
- Backend: `routes/documents.py::verify_document`.
- Collections: reads/writes `documents`, `patients`, `document_extractions`, `patient_timeline`, `similar_case_recommendations`, `audit_logs`.
- Frontend caller: document detail page.

- Method: `PUT`
- URL: `/documents/{document_id}/reject`
- Body: `{ "reason": "..." }`
- Response: rejected document.
- Auth permission: `documents.verify`.
- Backend: `routes/documents.py::reject_document`.
- Collections: updates `documents`, writes `audit_logs`.
- Frontend caller: document detail page.

- Method: `DELETE`
- URL: `/documents/{document_id}`
- Response: `{ "message": "Document soft deleted" }`
- Auth permission: `documents.archive`.
- Backend: `routes/documents.py::delete_document`.
- Collections: updates `documents`, writes `audit_logs`.
- Frontend caller: Not found.

### Search

- Method: `GET`
- URL: `/search/patients?query=...`
- Response: up to 50 patients.
- Auth permission: `patients.search`.
- Backend: `routes/search.py::search_patients`.
- Collections: reads `patients`.
- Frontend caller: document detail page patient selection.

- Method: `GET`
- URL: `/search/documents?query=&patient_id=&document_type=&date_from=&date_to=&doctor=&diagnosis=&medicine=&lab_test=`
- Response: array of `{ document, patient, summary, match_field }`.
- Auth permission: `documents.view_metadata`.
- Backend: `routes/search.py::search_documents`.
- Collections: reads `documents`, `document_extractions`, `patients`.
- Frontend caller: `frontend/app/search/page.tsx`.

### Similar Cases

- Method: `GET`
- URL: `/documents/{document_id}/similar-cases`
- Response: recommendations where `new_document_id == document_id`.
- Auth permission: `similar_cases.view`.
- Backend: `routes/similar_cases.py::document_similar_cases`.
- Collections: reads `similar_case_recommendations`, `documents`, `patients`, writes `audit_logs`.
- Frontend caller: `SimilarCasesCard` when `documentId` prop is used.

- Method: `GET`
- URL: `/patients/{patient_id}/similar-cases`
- Response: recommendations where `new_patient_id == patient_id`.
- Auth permission: `similar_cases.view`.
- Backend: `routes/similar_cases.py::patient_similar_cases`.
- Collections: reads `similar_case_recommendations`, `documents`, `patients`, writes `audit_logs`.
- Frontend caller: `SimilarCasesCard` if `patientId` prop is used. Not found in current pages.

- Method: `PUT`
- URL: `/similar-cases/{recommendation_id}/doctor-feedback`
- Body: `{ "feedback": "useful" }`, allowed values: `useful`, `not_useful`, `same_issue`, `different_issue`, `needs_review`.
- Response: updated recommendation.
- Auth permission: `similar_cases.feedback`.
- Backend: `routes/similar_cases.py::update_doctor_feedback`.
- Collections: updates `similar_case_recommendations`, writes `audit_logs`.
- Frontend caller: `SimilarCasesCard`.

### Dashboard

- Method: `GET`
- URL: `/dashboard/stats`
- Response: totals, category counts, recent uploads.
- Auth permission: `audit.view`.
- Backend: `routes/dashboard.py::stats`.
- Collections: reads `patients`, `documents`.
- Frontend caller: dashboard page.

### Audit

- Method: `GET`
- URL: `/audit-logs`
- Response: recent audit logs.
- Auth permission: `audit.view`.
- Backend: `routes/audit.py::audit_logs`.
- Collections: reads `audit_logs`.
- Frontend caller: audit logs page.

## 8. Document Upload Flow

Frontend upload component:

1. File input accepts `.pdf,.jpg,.jpeg,.png,.txt`.
2. User clicks Upload and process.
3. `upload()` in `frontend/app/documents/upload/page.tsx` creates `FormData`.
4. Before starting, it clears old state:
   - `setDocuments([])`
   - `setSimilarCases([])`
   - `setUploadResult(null)`
5. `uploadDocumentsWithProgress()` sends `POST /documents/upload` using `XMLHttpRequest`.
6. Authorization header is set from `getToken()`.
7. Browser upload progress updates `progress`.
8. Server-side processing is represented with staged estimated progress: saving, extracting, processing.

Backend route:

1. `routes/documents.py::upload_documents` receives `files`.
2. Requires `documents.upload`.
3. For each file:
   - Creates `document_id = await next_sequence("documents", "DOC")`.
   - Calls `save_upload(file, document_id)`.
   - Inserts initial `documents` record with upload metadata and pending statuses.
   - Logs `document_uploaded`.
   - Calls `_process_document(document)`.

File validation/storage:

- `services/file_service.py::save_upload`.
- Allows extensions: `.pdf`, `.jpg`, `.jpeg`, `.png`, `.txt`.
- Allows MIME types: `application/pdf`, `image/*`, `text/*`.
- Enforces `settings.max_file_size_mb`.
- Stores file in `settings.upload_path / document_id / <uuid>.<ext>`.
- Returns metadata including private `stored_file_path`.

Text extraction:

- `_process_document()` calls `extract_text_from_file`.
- PDF: `pypdf`.
- Image: Pillow + pytesseract.
- Text: read as UTF-8 with errors ignored.
- Result is stored as `extracted_text`, `extraction_status`, `extraction_error`.

Gemini extraction:

- `_process_document()` calls `extract_document(document["stored_file_path"])`.
- Gemini returns JSON matching `GEMINI_RESPONSE_SCHEMA`.
- If Gemini API key is missing, `gemini_service.py` returns safe mock/fallback data.
- `_apply_patient_text_fallback()` may extract patient name from readable local text if Gemini missed it.

Document summary:

- `_process_document()` calls `build_document_summary(data, extracted_text)`.
- Existing Gemini `summary` wins.
- Otherwise summary is built from diagnosis, medicines, labs, procedures, advice, follow-up, dates, or text preview.

Patient matching/linking:

- `_normalized_patient(data)` extracts patient fields.
- `find_patient_match(extracted_patient)` checks existing patients.
- If match confidence >= `settings.patient_match_threshold` (default `0.75`), link to matched patient.
- If not matched but patient name exists, auto-create a patient.
- If no patient name, status becomes `pending_verification` and `requires_manual_review = True`.

Save extraction:

- `_process_document()` upserts into `document_extractions`.
- Saves `gemini_raw_output`, `extracted_data`, `verified_data` if auto-saved, summary fields, warnings, AI status.

Update document:

- `_process_document()` updates `documents` with patient fields, document type, status, match confidence, summary, extraction/AI statuses, verification fields, manual review fields.

Timeline and patient summary:

- If document can auto-save:
  - `add_timeline_entry(...)`.
  - `refresh_patient_summary(patient_id, now)`.
  - If moved from another patient, refresh previous patient summary too.

Similar case matching:

- `_process_document()` calls `_process_similar_cases_safely(document["document_id"])`.
- The safe wrapper catches errors and sets `similar_case_status = "failed"`.
- Returned items are filtered to:
  - `item["new_document_id"] == current document_id`
  - `similarity_score >= 75`

Upload response:

- `upload_documents()` returns:

```json
{
  "message": "Document uploaded successfully",
  "documents": [processed_documents],
  "document": "first document if exactly one file else null",
  "patient": "patient payload if one file and linked",
  "similar_cases": "only current upload fresh cases",
  "similar_case_status": "processed or failed"
}
```

Frontend display:

- After success:
  - `setUploadResult(result)`
  - `setDocuments(result.documents)`
  - `setSimilarCases(result.similar_cases || [])`
- For each uploaded document:
  - If review needed, show Review link.
  - If verified, show Details saved and current save message.
  - If current document has matches, render `SimilarCasesCard similarCases={documentSimilarCases}`.
  - If no matches, current UI shows `No Matching`.

## 9. Patient Matching Logic

File: `backend/app/services/patient_match_service.py`.

Function: `find_patient_match(extracted_patient: dict)`.

Data source:

- Loads up to 500 patients with `db.patients.find({}).to_list(length=500)`.

Matching score:

- UHID/patient ID exact match:
  - Compares extracted `uhid` with patient `patient_id` and patient `uhid`.
  - Adds `1.0`.
  - Reason: `UHID exact match`.

- Mobile exact match:
  - Adds `0.9`.
  - Reason: `Mobile exact match`.

- Name match:
  - Uses `difflib.SequenceMatcher`.
  - Ratio >= `0.95`: adds `0.85`, reason `Name exact match`.
  - Ratio >= `0.85`: adds `0.75`, reason `Name fuzzy match XX%`.

- Gender support:
  - Exact gender match adds `0.05`.

- Age support:
  - Exact age string match adds `0.05`.

- Final confidence:
  - `min(score, 1.0)`.
  - Rounded to two decimals.

Upload decision:

- In `routes/documents.py::_process_document`, matched patient is accepted only when `match["confidence"] >= settings.patient_match_threshold`.
- Default threshold is `0.75`.
- If no accepted match and extracted patient has required name, `_create_patient_from_extraction()` auto-creates a patient.
- If no patient name, document becomes `pending_verification` with review reason.

Important files:

- Patient normalization and auto-create: `backend/app/routes/documents.py`.
- Scoring: `backend/app/services/patient_match_service.py`.
- Settings threshold: `backend/app/config.py`.

## 10. Similar Case Matching Logic

This is implemented in `backend/app/services/similar_case_service.py`.

When it runs:

- During upload processing after document extraction, patient linking, document summary, timeline, and patient summary refresh.
- During manual document verification after the document is linked to a selected patient.

Current-document only rule:

- The service receives exactly one `current_uploaded_document_id`.
- It loads only that document:
  - `db.documents.find_one({"document_id": document_id, "deleted_at": None})`.
- It deletes old recommendations only for this document:
  - `db.similar_case_recommendations.delete_many({"new_document_id": document_id})`.
- It returns only fresh recommendations built during this run.
- Upload route filters again by current `document_id` and `similarity_score >= 75`.

Clinical text creation:

- Function: `build_clinical_text(extracted_data, document)`.
- Inputs:
  - `document_extractions.verified_data` or `document_extractions.extracted_data`.
  - `document.summary`.
- Sections:
  - Diagnosis
  - Symptoms
  - Lab Findings
  - Radiology Findings
  - Medicines
  - Procedures
  - Clinical Summary
  - Follow-up Advice
  - Allergies/Risk Alerts
- `_strip_non_clinical_text()` removes lines containing non-clinical terms such as file name, upload date, invoice, bill, billing, insurance, amount, hospital address, phone, mobile, email, footer/header, UHID/MRN/patient ID.

Embeddings:

- Function: `create_embedding(text)` in `embedding_service.py`.
- Model: Gemini `models/text-embedding-004`.
- Returns `list[float] | None`.
- If text is empty or API key missing/failing, returns `None`.
- If embedding is missing, document gets:
  - `similar_case_status = "skipped_no_embedding"`
  - `clinical_embedding = None`
  - upload still succeeds.

Vector search:

- Uses MongoDB Atlas `$vectorSearch` against `documents.clinical_embedding`.
- Index name: `clinical_embedding_index`.
- `numCandidates = 100`.
- `limit = 10`.
- Excludes current document and deleted documents.
- Projection includes document fields and score metadata:
  - `"score": {"$meta": "vectorSearchScore"}`

Candidate filtering:

- Same-patient documents are skipped if both documents have patient IDs and they are equal.
- Candidate clinical text is loaded from stored `clinical_text_for_similarity` or rebuilt from extraction.

Similarity score:

- Atlas vector score is treated as `0.0` to `1.0`.
- The code then applies additional clinical safety gates:
  - exact clinical text match check.
  - condition isolation gate.
  - Jaccard token overlap.
  - disease-specific medical keyword score.
  - care plan score.
  - clinical overlap score.
- Final score is still `0.0` to `1.0`.
- Recommendation only created when:

```python
final_score >= 0.75
```

- Stored/displayed score:

```python
similarity_score = round(final_score * 100, 2)
```

Match strength:

- `final_score >= 0.85`: `strong`.
- `0.75 <= final_score < 0.85`: `possible`.

Recommendation saving:

- Creates `recommendation_id = await next_sequence("similar_case_recommendations", "SIM")`.
- Inserts into `similar_case_recommendations`.
- Logs `similar_case_recommendation_created`.
- Response is hydrated with matched patient name and document metadata.

Frontend current-upload rule:

For upload result screen, use only:

```ts
response.similar_cases
```

Do not fetch global old recommendations after upload.

Frontend must clear old state before each upload:

```ts
setSimilarCases([]);
setUploadResult(null);
```

After upload success:

```ts
setUploadResult(response);
setSimilarCases(response?.similar_cases || []);
```

Render only current matches:

```tsx
{similarCases.length > 0 && (
  <SimilarCasesCard similarCases={similarCases} />
)}
```

Current implementation renders the card per uploaded document only when `documentSimilarCases.length > 0`.

Safety language:

- Card title: `Possible Similar Clinical Case Found`.
- Warning: `Doctor verification required. This is not a final diagnosis.`
- It must not say diagnosis/treatment/medicine is confirmed.

## 11. MongoDB Atlas Vector Search

Implementation status: Implemented in `backend/app/services/similar_case_service.py`, but the Atlas Vector Search index must be created manually in MongoDB Atlas.

Embedding field:

- `documents.clinical_embedding`

Clinical text field:

- `documents.clinical_text_for_similarity`

Status field:

- `documents.similar_case_status`

Embedding model:

- Gemini `models/text-embedding-004`

Embedding dimension:

- 768 dimensions for Gemini `text-embedding-004`.

Vector index name:

- `clinical_embedding_index`

Vector index JSON:

```json
{
  "name": "clinical_embedding_index",
  "type": "vectorSearch",
  "definition": {
    "fields": [
      {
        "type": "vector",
        "path": "clinical_embedding",
        "numDimensions": 768,
        "similarity": "cosine"
      }
    ]
  }
}
```

Aggregation pipeline shape:

```python
pipeline = [
    {
        "$vectorSearch": {
            "index": "clinical_embedding_index",
            "path": "clinical_embedding",
            "queryVector": embedding,
            "numCandidates": 100,
            "limit": 10,
        }
    },
    {
        "$match": {
            "document_id": {"$ne": document_id},
            "$or": [
                {"deleted_at": {"$exists": False}},
                {"deleted_at": None},
            ],
        }
    },
    {
        "$project": {
            "document_id": 1,
            "patient_id": 1,
            "patient_name": 1,
            "document_type": 1,
            "document_date": 1,
            "upload_date": 1,
            "uploaded_at": 1,
            "clinical_text_for_similarity": 1,
            "summary": 1,
            "extracted_data": 1,
            "score": {"$meta": "vectorSearchScore"},
        }
    },
]
```

Score interpretation:

- Atlas vector score is treated as `0.0` to `1.0`.
- Code converts final score to percent with `round(score * 100, 2)`.
- Code does not compare score to `75`; it compares final score to `0.75`.

Fallback/failure:

- If no clinical text: status `skipped_no_clinical_text`, returns `[]`.
- If no embedding: status `skipped_no_embedding`, returns `[]`.
- If vector search or any service step fails: status `failed`, saves `similar_case_error`, returns `[]`.
- Upload still succeeds.

Debug logs:

- `VECTOR_SIMILAR_CASE_START`
- `VECTOR_EMBEDDING_CREATED`
- `VECTOR_SEARCH_RESULTS`
- `VECTOR_SIMILAR_CASE_COMPARE`
- `VECTOR_SIMILAR_CASE_RETURN`
- `VECTOR_SIMILAR_CASE_FRESH_RESULT`

## 12. AI / Gemini Logic

Configuration:

- `backend/app/config.py`
- Env/settings:
  - `gemini_api_key`
  - `gemini_model`
  - `gemini_fallback_models`

Document extraction:

- File: `backend/app/services/gemini_service.py`.
- Main function: `extract_document(file_path: str)`.
- Sends file content to Gemini as base64 inline data.
- Uses `EXTRACTION_SYSTEM_INSTRUCTIONS`.
- Uses `GEMINI_RESPONSE_SCHEMA`.
- Requests `response_mime_type = "application/json"` and `response_schema`.
- Tries primary model then fallback models from settings.

Extraction schema:

- Patient code/name/contact/document date.
- Additional details.
- Document type.
- Doctor details.
- Hospital details.
- Dates.
- Medical data:
  - symptoms
  - diagnosis
  - medicines
  - lab_tests
  - procedures
  - advice
  - follow_up
- Summary.
- Warnings.
- Confidence score.
- Source page.

Local fallback:

- If no `GEMINI_API_KEY`, returns mock raw output and empty extraction merged with local PDF extraction when possible.
- Local PDF parsing can detect patient fields from embedded PDF text.
- `_merge_local_extraction()` can fill patient name/code/contact/date from local extraction.

Document summary:

- `backend/app/services/document_summary_service.py`.
- Deterministic fallback summary if Gemini summary is absent.

Patient summary:

- `backend/app/services/patient_summary_service.py`.
- Deterministic summary is built from all patient documents/extractions.
- Optional Gemini refinement via `_generate_ai_patient_summary`.
- Safety prompt says:
  - Use uploaded documents only.
  - Do not invent medical facts.
  - Missing fields should say `Not mentioned in uploaded documents.`
  - Uncertain findings should say `Needs doctor verification.`
  - Do not provide final medical advice.
  - Do not mark medication current unless latest document supports it.

Error fallback:

- Missing Gemini key or API failure does not break upload.
- Patient summary status can become `fallback`.
- Document AI status can become `fallback` or `failed`.

## 13. File Storage / Document Preview / Download

Storage:

- Files are stored locally under `backend/uploads`.
- Each document gets its own folder:
  - `uploads/<document_id>/<uuid>.<ext>`
- File metadata is saved in `documents`.
- Private path key is `stored_file_path`.

Privacy:

- `utils/response.py` removes:
  - `stored_file_path`
  - `file_path`
  - `local_path`
- Raw local paths are not returned in JSON responses.

Preview/download APIs:

- `GET /documents/{document_id}/file`
- `GET /documents/{document_id}/download`
- Both use `routes/documents.py::get_document_file`.
- Token can be provided through:
  - Authorization header, or
  - query parameter `?token=...`
- Used because iframe/img/a links can pass token in URL.

Access checks:

- Token decoded with `decode_token`.
- User loaded from `db.users` with `is_active = True`.
- Document loaded with `deleted_at = None`.
- `can_access_document(current_user, document, content=True)` checks role/permissions/type.
- Admin can view content.
- Doctor can view content for clinical/lab/radiology/basic document types.
- Other roles need metadata but generally cannot view content unless access function allows it.

Frontend:

- Document detail page builds:
  - `fileUrl = API_URL + /documents/{id}/file?token=...`
  - PDF preview uses iframe with `#page=source_page`.
  - Images use `<img>`.
- Patient page download links use `/documents/{document_id}/download?token=...`.

Security note:

- Query-token URLs can appear in browser history/logs. This is implemented currently; consider short-lived file access tokens for production.

## 14. RBAC and Security

Roles:

- `admin`
- `doctor`
- `document_staff`
- `receptionist`

Permissions:

- `users.manage`
- `roles.manage`
- `patients.create`
- `patients.view_basic`
- `patients.view_clinical`
- `patients.update_basic`
- `patients.search`
- `documents.upload`
- `documents.view_metadata`
- `documents.view_content`
- `documents.download`
- `documents.archive`
- `documents.verify`
- `documents.match_patient`
- `documents.view_extraction`
- `documents.view_summary`
- `summary.view_clinical`
- `timeline.view`
- `similar_cases.view`
- `similar_cases.feedback`
- `audit.view`

Role mapping:

- Admin: all permissions.
- Doctor: patient basic/clinical/search, upload, metadata/content/download, summary, timeline, similar cases.
- Document staff: create/view/search patients, upload, view metadata/extraction/summary, match/verify documents.
- Receptionist: create/update/view/search patients, upload, view document metadata.

Backend checks:

- `require_permission()` in route dependencies.
- `get_current_user()` rejects invalid token and inactive user.
- `can_access_document()` controls file content access.

Frontend hiding:

- `AppShell` filters nav items by permissions.
- Pages/components call `hasPermission()` to hide controls.
- This is not security; backend checks remain required.

JWT:

- Created in `utils/security.py::create_access_token`.
- Contains `sub`, `role`, `exp`.
- Expiry from `access_token_expire_minutes`, default 12 hours.

Inactive users:

- Deleting a user sets `is_active = False`.
- Inactive users cannot login or use existing token because backend reloads only active users.

Audit logging:

- Important flows call `log_action()`.
- Stored in `audit_logs`.

## 15. Audit Logs

Service:

- `backend/app/services/audit_service.py::log_action`.

Collection:

- `audit_logs`.

Shape:

```json
{
  "action": "login",
  "user_email": "admin@example.com",
  "user_role": "admin",
  "metadata": {},
  "created_at": "..."
}
```

Actions found in code:

- `admin_seed_created`
- `login`
- `user_created`
- `user_updated`
- `user_disabled`
- `patient_created`
- `patient_summary_viewed`
- `patient_updated`
- `document_uploaded`
- `document_viewed`
- `document_access_denied`
- `document_downloaded`
- `document_processed`
- `document_verified`
- `document_rejected`
- `document_soft_deleted`
- `similar_case_recommendation_created`
- `similar_case_viewed`
- `similar_case_feedback_updated`

Audit API:

- `GET /audit-logs`
- Requires `audit.view`.
- Returns last 300 logs sorted newest first.

## 16. Important Current Bug/Requirement

Exact requirement:

When a new document is uploaded, the system must show `Possible Similar Clinical Case Found` only if the current uploaded document matches an old document by 75% or more.

It must not show:

- old matches from previous uploads
- all stored recommendations
- global similar cases
- empty card
- `No similar patient found` in production UI

Correct behavior:

- If File A matches File 123, show File 123 below File A upload result.
- If next File B is different, show no similar case section at all for File B.

Current implementation:

- Backend upload response uses only fresh `similar_cases` from current upload processing.
- Backend deletes old recommendations only for the current `new_document_id`.
- Frontend upload page clears `similarCases` before upload.
- Frontend upload page renders `SimilarCasesCard` only when `documentSimilarCases.length > 0`.
- Document detail page compact similar-case card returns `null` when no recommendations exist.

Potential conflict:

- `SimilarCasesCard` in non-compact mode renders an empty message if it receives no items. Upload page avoids this by not rendering the card for empty matches.
- Upload result currently displays `No Matching` below saved details when no current matches exist. If production must show no no-match text at all, remove that line from `frontend/app/documents/upload/page.tsx`.

## 17. Environment Variables

Backend env variables are loaded by `backend/app/config.py`.

- `APP_NAME`
  - Purpose: FastAPI title.
  - Where used: `main.py`.
  - Example: `APP_NAME=Single Hospital AI DMS`

- `MONGODB_URI`
  - Purpose: MongoDB Atlas/local connection string.
  - Where used: `database.py`.
  - Example: `MONGODB_URI=your_mongodb_uri_here`

- `DATABASE_NAME`
  - Purpose: MongoDB database name.
  - Where used: `database.py`.
  - Example: `DATABASE_NAME=hospital_dms`

- `JWT_SECRET`
  - Purpose: JWT signing secret.
  - Where used: `utils/security.py`.
  - Example: `JWT_SECRET=your_secret_here`

- `JWT_ALGORITHM`
  - Purpose: JWT algorithm.
  - Where used: `utils/security.py`.
  - Example: `JWT_ALGORITHM=HS256`

- `ACCESS_TOKEN_EXPIRE_MINUTES`
  - Purpose: JWT expiry.
  - Where used: `utils/security.py`.
  - Example: `ACCESS_TOKEN_EXPIRE_MINUTES=720`

- `GEMINI_API_KEY`
  - Purpose: Gemini extraction, patient summary, embeddings.
  - Where used: `gemini_service.py`, `patient_summary_service.py`, `embedding_service.py`.
  - Example: `GEMINI_API_KEY=your_key_here`

- `GEMINI_MODEL`
  - Purpose: Primary Gemini generateContent model.
  - Where used: `gemini_service.py`, `patient_summary_service.py`.
  - Example: `GEMINI_MODEL=gemini-2.5-flash`

- `GEMINI_FALLBACK_MODELS`
  - Purpose: Comma-separated fallback generateContent models.
  - Where used: `gemini_service.py`, `patient_summary_service.py`.
  - Example: `GEMINI_FALLBACK_MODELS=gemini-2.5-flash-lite,gemini-2.0-flash`

- `UPLOAD_DIR`
  - Purpose: Private upload directory.
  - Where used: `config.py`, `file_service.py`, `main.py`.
  - Example: `UPLOAD_DIR=uploads`

- `MAX_FILE_SIZE_MB`
  - Purpose: Upload size limit.
  - Where used: `file_service.py`.
  - Example: `MAX_FILE_SIZE_MB=25`

- `PATIENT_MATCH_THRESHOLD`
  - Purpose: Auto-link threshold for patient matching.
  - Where used: `routes/documents.py`.
  - Example: `PATIENT_MATCH_THRESHOLD=0.75`

- `CORS_ORIGINS`
  - Purpose: Comma-separated allowed frontend origins.
  - Where used: `main.py`.
  - Example: `CORS_ORIGINS=http://localhost:3000`

Frontend env variable:

- `NEXT_PUBLIC_API_URL`
  - Purpose: Backend API base URL.
  - Where used: `frontend/lib/api.ts`.
  - Example: `NEXT_PUBLIC_API_URL=http://localhost:8000`

Do not commit real secret values.

## 18. How to Run Project

Backend setup:

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend `.env` example:

```env
MONGODB_URI=your_mongodb_uri_here
DATABASE_NAME=hospital_dms
JWT_SECRET=your_secret_here
GEMINI_API_KEY=your_key_here
CORS_ORIGINS=http://localhost:3000
UPLOAD_DIR=uploads
MAX_FILE_SIZE_MB=25
PATIENT_MATCH_THRESHOLD=0.75
```

Frontend setup:

```bash
cd frontend
npm install
npm run dev
```

Frontend `.env` example:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Create first admin:

```bash
curl -X POST http://localhost:8000/auth/register-admin-seed ^
  -H "Content-Type: application/json" ^
  -d "{\"name\":\"Admin\",\"email\":\"admin@example.com\",\"password\":\"ChangeMe123!\",\"role\":\"admin\"}"
```

Docker:

```bash
docker compose up --build
```

Common errors:

- `GEMINI_API_KEY not configured`: Upload can continue with fallback extraction, but AI extraction/summary/embeddings will be limited or skipped.
- Image OCR fails: Install/configure Tesseract binary; Python packages alone are not enough.
- Atlas vector search error: Create `clinical_embedding_index` in MongoDB Atlas; normal `ensure_indexes()` cannot create this Atlas Search index.
- CORS error: Set `CORS_ORIGINS` to include frontend URL.
- 401 in frontend: Token expired/invalid; frontend clears token and redirects to `/login`.
- File preview does not load: Check `documents.view_content` / `documents.download` permission and file exists at stored path.

How to test upload:

1. Login as admin/doctor/document_staff with `documents.upload`.
2. Go to `/documents/upload`.
3. Upload supported file.
4. Watch staged progress.
5. Confirm response appears as verified or review-needed.
6. Open Review if manual verification is required.
7. Check MongoDB `documents`, `document_extractions`, `patients`, `patient_timeline`, and `audit_logs`.

## 19. Testing Guide

Positive similar case:

1. Ensure Atlas vector index exists.
2. Ensure `GEMINI_API_KEY` is configured.
3. Upload Report 40 Acute Sinusitis first.
4. Expected: upload succeeds, `similar_cases: []`.
5. Upload Report 44 Similar Sinusitis second.
6. Expected:
   - `similar_cases` contains only Report 40 if score is >= 75%.
   - UI shows `Possible Similar Clinical Case Found` below Report 44 result.
   - Recommendation `new_document_id` equals Report 44 document ID.

Negative non-clinical case:

1. Upload non-hospital office inventory PDF.
2. Expected:
   - Ideally no patient auto-create if no patient name is found.
   - No diagnosis.
   - `similar_cases: []`.
   - No similar case card on upload result.

Fresh upload state test:

1. Upload File A that matches an old document.
2. Confirm File A shows the matched old document.
3. Upload File B that is different.
4. Expected:
   - Upload page clears old state.
   - File B response has `similar_cases: []`.
   - File B does not show previous File A matches.

Manual review test:

1. Upload a file without readable patient name.
2. Expected:
   - Document status `pending_verification`.
   - `requires_manual_review = true`.
   - Review link appears.
   - User can search/select patient and verify.

File preview/download test:

1. Login as role with download/content permission.
2. Open document detail page.
3. Expected PDF iframe/image preview loads through `/documents/{id}/file?token=...`.
4. Download link returns file.

RBAC test:

1. Login as receptionist.
2. Expected no Users/Audit/Dashboard nav unless permissions allow.
3. Backend should reject direct restricted API calls with 403.

## 20. Known Issues / TODO

- Atlas Vector Search index is documented but must be created manually in MongoDB Atlas. `ensure_indexes()` creates normal MongoDB indexes only.
- `document_extractions`, `patient_timeline`, and `settings` do not have explicit indexes in `ensure_indexes()`. Consider adding indexes on `document_extractions.document_id`, `patient_timeline.patient_id`, and `settings.key`.
- Patient matching loads up to 500 patients and manually scores them. This may become slow or incomplete as patient count grows.
- `dashboard/stats` requires `audit.view`, which means dashboard is effectively admin-only. Verify whether that is intended.
- README mentions `.env.example` files, but actual `.env.example` files were not found during inspection.
- `SimilarCasesCard` non-compact empty state displays an empty-card message. Upload avoids this, but if production must never show empty similar-case cards anywhere, keep using compact mode or remove the empty state.
- Upload result currently shows `No Matching` below details saved when no matches exist. This was requested earlier, but it may conflict with the newer requirement that no no-match production UI be shown.
- Query-token document preview works but can expose tokens in browser history/server logs. Consider short-lived file tokens or cookie-based authenticated file access.
- Similar-case patient endpoint returns recommendations by `new_patient_id`. This is not used after upload, but be careful not to use it for upload result screens.
- Local `backend/uploads` contains many uploaded PDF files in the workspace. Confirm whether these should be committed/tracked or ignored.
- No automated backend/frontend tests were found.
- `npm run lint` may prompt to configure ESLint if config is missing.

## 21. Summary for ChatGPT

Quick Context for ChatGPT:

This is a Hospital AI Document Management System built with FastAPI, Next.js, MongoDB Atlas, and Gemini. The core feature is document upload: the frontend uploads files to `POST /documents/upload`; the backend saves the file privately, extracts text, asks Gemini for structured metadata, matches or creates a patient, saves document/extraction records, refreshes patient summary/timeline, runs similar-case matching, and returns only the current upload's fresh `similar_cases`.

Main backend files:

- `backend/app/main.py`: FastAPI app and router registration.
- `backend/app/routes/documents.py`: Upload, processing, preview/download, verify/reject.
- `backend/app/services/gemini_service.py`: Gemini extraction.
- `backend/app/services/patient_match_service.py`: Patient matching.
- `backend/app/services/patient_summary_service.py`: Patient clinical summary.
- `backend/app/services/similar_case_service.py`: Clinical text, embeddings, Atlas Vector Search, recommendations.
- `backend/app/services/embedding_service.py`: Gemini embeddings.
- `backend/app/auth/permissions.py`: RBAC.
- `backend/app/database.py`: MongoDB connection/indexes.

Main frontend files:

- `frontend/app/documents/upload/page.tsx`: Upload UI and current response similar-case display.
- `frontend/components/SimilarCasesCard.tsx`: Similar case display/feedback/preview.
- `frontend/app/documents/[id]/page.tsx`: Review and preview page.
- `frontend/app/patients/[id]/page.tsx`: Patient profile, summaries, documents, timeline.
- `frontend/lib/api.ts`: API client.
- `frontend/lib/auth.ts`: local auth state.

Main DB collections:

- `users`
- `patients`
- `documents`
- `document_extractions`
- `patient_timeline`
- `similar_case_recommendations`
- `audit_logs`
- `settings`

Current similar-case rule:

- Upload result screen must use only `response.similar_cases`.
- Do not fetch global old recommendations after upload.
- Clear frontend state before every upload with `setSimilarCases([])` and `setUploadResult(null)`.
- Render `SimilarCasesCard` only when the current upload has one or more matches.
- A match is valid only if final score is >= `0.75`, displayed as percent.

What should be fixed next:

- Create/verify the MongoDB Atlas Vector Search index `clinical_embedding_index`.
- Decide whether upload no-match UI should show `No Matching` or show nothing.
- Add missing indexes for `document_extractions.document_id`, `patient_timeline.patient_id`, and `settings.key`.
- Add `.env.example` files and automated tests.

## Similar Case Matching Failure Debug - Diabetes Reports 01 and 09

This section documents the real code path for the failing diabetes test pair:

- `DMS_NEW_01_Diabetes_Ritika_Aggarwal.pdf`
- `DMS_NEW_09_Diabetes_Similar_Madhu_Chopra.pdf`

Expected clinical behavior: Report 09 should match Report 01 above 75% because both describe Type 2 Diabetes Mellitus with overlapping hyperglycemia, thirst/urination/fatigue/blurred vision, fasting/post-prandial sugar, HbA1c, urine sugar, diet control, glucose monitoring, exercise, and repeat HbA1c follow-up.

Important limitation: this inspection used source code only. Whether each specific uploaded PDF reached each stage must be verified in MongoDB Compass/logs because the runtime document records for these two filenames were not inspected here.

### 1. Upload Flow

File: `backend/app/routes/documents.py`

Function: `upload_documents()`

Code path:

- Creates a `documents` record with `status="uploaded"`, `clinical_text_for_similarity=""`, `clinical_embedding=None`, and `similar_case_status="pending"`.
- Calls `_process_document(document)` synchronously before returning the upload response.
- After processing, filters returned matches to only:
  - `item.new_document_id == current uploaded document_id`
  - `similarity_score >= 75`
- Returns `documents`, `document`, `similar_cases`, and `similar_case_status`.

Function: `_process_document()`

Code path:

- Reads raw text through `extract_text_from_file()`.
- Runs Gemini extraction through `extract_document()`.
- Applies text fallback for patient identity.
- Builds a summary.
- Applies `Condition` fallback into diagnosis.
- Builds initial clinical text with `build_clinical_text()`.
- Runs medical validation via `has_medical_signals()` and, if needed, `is_medical_document()`.
- If the document can be auto-saved to a patient, calls `_process_similar_cases_safely(document_id)`.

Runtime checks needed:

- Report 01:
  - Is `status` `verified`?
  - Is `is_medical_document` true?
  - Is `patient_id` present?
  - Is `requires_manual_review` false?
  - Is `clinical_text_for_similarity` non-empty after processing?
  - Is `clinical_embedding` present after processing?
  - Is `similar_case_status` `processed`, `skipped_no_embedding`, `skipped_no_clinical_text`, `failed_vector_search`, `unknown_low_confidence`, or `skipped_non_medical`?
- Report 09:
  - Same fields as Report 01.
  - Confirm `similar_case_status` after upload and whether `similar_cases` in response was empty.

Most important code fact: Report 09 can only find Report 01 if Report 01 already has `clinical_embedding` saved in the `documents` collection before Report 09 vector search runs.

### 2. Clinical Text Creation

File: `backend/app/services/similar_case_service.py`

Function: `build_clinical_text(extracted_data, document)`

The current clinical text builder uses only structured extraction fields plus document summary. It builds these sections:

- `Diagnosis`: `medical_data.diagnosis`, `medical_data.condition`, `data.condition`, `data.diagnosis`, `data.current_diagnosis`
- `Symptoms`: `medical_data.symptoms`, `medical_data.chief_complaints`, `data.symptoms`
- `Chief Complaints`: `medical_data.chief_complaints`, `data.chief_complaints`, `data.complaints`
- `Vitals`: `medical_data.vitals`, `data.vitals`
- `Investigation Findings`: `medical_data.investigation_findings`, `data.investigation_findings`
- `Examination Findings`: `medical_data.examination_findings`, `medical_data.clinical_findings`, `data.examination_findings`, `data.clinical_findings`
- `Lab Findings`: `medical_data.lab_tests`, `data.lab_findings`, `data.lab_highlights`, `data.lab_tests`
- `Radiology Findings`: `medical_data.radiology`, `medical_data.radiology_findings`, `data.radiology_findings`, `data.radiology_highlights`
- `Medicines`: `medical_data.medicines`, `data.medicines`, `data.medications`
- `Procedures`: `medical_data.procedures`, `data.procedures`, `data.medical_procedures`
- `Clinical Summary`: `data.clinical_summary`, `data.summary`, `document.summary`
- `Follow-up Advice`: `medical_data.follow_up`, `medical_data.advice`, `data.follow_up`, `data.advice`
- `Allergies/Risk Alerts`: `data.allergies`, `data.risk_alerts`, `data.allergies_and_risk_alerts`

Current support status:

- `Condition: Type 2 Diabetes Mellitus`: supported if Gemini returns it as `medical_data.condition`, top-level `condition`, or if `_apply_condition_fallback()` maps it into diagnosis.
- `Chief Complaints`: supported as `medical_data.chief_complaints` or top-level complaint fields.
- `Investigation / Examination Findings`: supported only if Gemini maps it into `medical_data.investigation_findings`, `medical_data.examination_findings`, `medical_data.clinical_findings`, or related top-level fields.
- `Provisional / Working Diagnosis`: supported if Gemini maps it to `medical_data.diagnosis` or related diagnosis fields.
- `Clinical Summary`: supported through `data.clinical_summary`, `data.summary`, or document summary.

Bug risk from code:

- `build_clinical_text()` does not use raw `extracted_text` as a fallback when structured extraction is sparse.
- If Gemini misses the diabetes terms and summary does not include them, the final `clinical_text_for_similarity` can miss terms like `diabetes`, `type 2 diabetes mellitus`, `hyperglycemia`, `thirst`, `frequent urination`, `blurred vision`, `fasting blood sugar`, `post prandial sugar`, `HbA1c`, and `urine sugar`, even when the raw PDF text contains them.

Needs runtime verification in MongoDB Compass/logs:

- Open `documents.clinical_text_for_similarity` for Report 01 and Report 09.
- Confirm whether the final text includes:
  - `diabetes`
  - `type 2 diabetes mellitus`
  - `hyperglycemia`
  - `thirst`
  - `frequent urination`
  - `blurred vision`
  - `fasting blood sugar`
  - `post prandial sugar`
  - `HbA1c`
  - `urine sugar`

### 3. Gemini Extraction Issue

File: `backend/app/services/gemini_service.py`

Current schema:

- `medical_data.condition`
- `medical_data.chief_complaints`
- `medical_data.symptoms`
- `medical_data.diagnosis`
- `medical_data.vitals`
- `medical_data.investigation_findings`
- `medical_data.examination_findings`
- `medical_data.clinical_findings`
- `medical_data.medicines`
- `medical_data.lab_tests`
- `medical_data.radiology`
- `medical_data.procedures`
- `medical_data.advice`
- `medical_data.follow_up`

Current prompt includes clinical label mapping:

- `Condition` means diagnosis or primary disease.
- `Chief Complaints` means symptoms.
- `Investigation / Examination Findings` means lab, radiology, or clinical findings.
- `Provisional / Working Diagnosis` means diagnosis.
- `Advice / Plan` means follow-up/advice.
- `Clinical Summary` means summary.

Function: `_validated_extraction(data)`

Important code:

- If `medical_data.condition` exists and `medical_data.diagnosis` is empty, it copies condition into diagnosis.

Remaining mismatch risk:

- The schema supports the needed labels now, but Gemini can still return empty arrays for table rows or PDF text that is hard to read.
- `build_clinical_text()` trusts structured fields and summary; it does not append raw extracted text when those structured fields are empty.

Needs runtime verification:

- In `document_extractions.extracted_data.medical_data` for both PDFs, check whether Gemini actually extracted:
  - `condition`
  - `diagnosis`
  - `chief_complaints` or `symptoms`
  - `vitals`
  - `investigation_findings`
  - `examination_findings`
  - `lab_tests`
  - `advice`
  - `follow_up`

### 4. Raw Text Fallback Issue

File: `backend/app/services/document_text_extraction_service.py`

Function: `extract_text_from_file(file_path, mime_type)`

Code path:

- PDFs use `pypdf.PdfReader(page).extract_text()`.
- Images use `pytesseract`.
- Text files use direct UTF-8 read.
- Returns `{"status": "success", "text": text}` only when non-empty text exists.

File: `backend/app/routes/documents.py`

Function: `_process_document()`

Code path:

- Saves raw text into `data["extracted_text"]`.
- Uses raw text for patient identity fallback and medical validation.

File: `backend/app/services/similar_case_service.py`

Function: `build_clinical_text()`

Bug:

- Similarity text creation does not use `extracted_text` fallback.
- Therefore a PDF can be correctly recognized as medical from raw text but still get weak or incomplete `clinical_text_for_similarity` if Gemini structured extraction misses disease/symptom/lab details.

Impact:

- Report 01 may be accepted and saved but embedded with incomplete clinical text.
- Report 09 may be accepted and saved but embedded with incomplete clinical text.
- Vector search and scoring can then fail despite raw PDFs being clinically similar.

### 5. Medical Validation Issue

File: `backend/app/routes/documents.py`

Function: `has_medical_signals(extracted_data, extracted_text)`

Current validation is scored and accepts medical documents when score is at least `2`. It checks both structured data and raw text headings/keywords.

Signals include:

- diagnosis/condition
- symptoms/chief complaints
- investigation/examination/lab/radiology findings
- vitals
- patient name with age/gender
- doctor/consultant with department
- at least 3 clinical keywords
- multiple medical text headings
- hospital/clinic context with patient identity

Important statuses:

- If not medical: `_process_document()` sets `status="unsupported_non_medical"` and `patient_link_action="unsupported_non_medical"`.
- If medical but patient identity is ambiguous or missing: status may become `pending_verification`, and similar case processing does not run because it runs only when `can_auto_save` is true.
- If medical and auto-saved: similar case processing runs.

Most likely medical-validation outcome for these diabetes PDFs:

- After the recent validation changes, they should not be marked `unsupported_non_medical` if raw text contains `Condition`, `Chief Complaints`, `Vitals`, investigation findings, diagnosis, advice/plan, or clinical summary.

Needs runtime verification:

- Check `documents.status`, `documents.is_medical_document`, `documents.medical_validation`, `documents.patient_link_action`, and `documents.requires_manual_review` for both reports.

### 6. Embedding Issue

File: `backend/app/services/embedding_service.py`

Function: `create_embedding(text)`

Code facts:

- Requires `GEMINI_API_KEY`.
- Calls `https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent`.
- Payload uses `model: "models/text-embedding-004"`.
- Limits input to the first 12,000 characters.
- Returns `None` if:
  - text is empty
  - `GEMINI_API_KEY` is missing
  - API response lacks `embedding.values`
  - API call raises an exception

File: `backend/app/services/similar_case_service.py`

Function: `process_for_document()`

Embedding flow:

- Calls `embedding = await create_embedding(clinical_text)`.
- If embedding is missing, updates document:
  - `clinical_text_for_similarity`: current clinical text
  - `clinical_embedding`: `None`
  - `similar_case_status`: `skipped_no_embedding`
- Then returns `[]`.

Impact:

- If Report 01 has `similar_case_status="skipped_no_embedding"`, Report 09 cannot find it because the vector search `$match` requires `clinical_embedding` to exist and not be null.
- If Report 09 gets `skipped_no_embedding`, no vector search runs for Report 09 at all.

Needs runtime verification:

- Check whether both documents have `clinical_embedding` arrays.
- Check whether each embedding has 768 dimensions.
- Check logs for `Embedding skipped because GEMINI_API_KEY is not configured` or `Embedding API failed`.

### 7. MongoDB Atlas Vector Search Issue

File: `backend/app/services/similar_case_service.py`

Constants:

- `VECTOR_INDEX_NAME = "clinical_embedding_index"`
- Vector path: `clinical_embedding`
- Expected embedding model: Gemini `text-embedding-004`, normally 768 dimensions.
- Similarity intended: cosine.

File: `backend/app/database.py`

Function: `ensure_indexes()`

Code fact:

- Creates normal MongoDB indexes only.
- Creates a partial normal index named `documents_clinical_embedding_exists`.
- Does not create an Atlas Vector Search index.

Required manual Atlas index:

- Collection: `documents`
- Index name: `clinical_embedding_index`
- Type: Atlas Vector Search
- Path: `clinical_embedding`
- Dimensions: `768`
- Similarity: `cosine`

Failure behavior:

- If Atlas Vector Search index is missing or wrong, `db.documents.aggregate(pipeline)` raises an exception.
- The exception is caught in `process_for_document()`.
- Document is updated with:
  - `similar_case_status="failed_vector_search"`
  - `similar_case_error=str(exc)`
- Function returns `[]`, so frontend shows no matches.

Needs runtime verification:

- Check Report 09 `similar_case_status` and `similar_case_error`.
- Check Atlas UI for the vector search index.

### 8. Vector Search Filtering Issue

File: `backend/app/services/similar_case_service.py`

Function: `process_for_document()`

Vector pipeline:

- `$vectorSearch` against `clinical_embedding`.
- `$match` filters:
  - `document_id != current uploaded document_id`
  - `deleted_at` missing or null
  - `clinical_embedding` exists and is not null

There is no document status filter in the pipeline.

Post-vector candidate filters:

- Skip same patient:
  - If `new_patient_id` and candidate `old_patient_id` exist and are equal, log `SIMILAR_SKIP_SAME_PATIENT` and continue.
- Skip low vector:
  - If vector score `< 0.80`, log `SIMILAR_SKIP_LOW_VECTOR`.
- Skip category mismatch:
  - If both documents have categories and no shared category, log `SIMILAR_SKIP_CATEGORY_MISMATCH`.
- Skip no disease gate:
  - If categories are missing/not shared and disease score `< 0.40` and no exact disease overlap, then vector score must be `>= 0.92`; otherwise skip with `SIMILAR_SKIP_NO_DISEASE_GATE`.
- Skip low clinical overlap:
  - If max of disease/symptom/finding/medproc scores `< 0.30`, log `SIMILAR_SKIP_LOW_CLINICAL_OVERLAP`.
- Skip final score:
  - If weighted final score `< 0.75`, no recommendation is created.

Same-patient risk:

- If Report 01 and Report 09 are accidentally linked to the same patient, the code intentionally skips Report 01 for Report 09.
- This is correct for avoiding same-patient “similar case” recommendations, but it can cause this test to show no match if patient matching incorrectly links Madhu Chopra to Ritika Aggarwal or both share a bad/missing identifier.

Needs runtime verification:

- Compare `patient_id` for Report 01 and Report 09.
- If equal, check logs for `SIMILAR_SKIP_SAME_PATIENT`.

### 9. Disease Category Gate Issue

File: `backend/app/services/similar_case_service.py`

Constants and functions:

- `DISEASE_KEYWORDS["diabetes"]` includes:
  - `diabetes`
  - `diabetic`
  - `hyperglycemia`
  - `hba1c`
  - `fasting glucose`
  - `postprandial glucose`
  - `polyuria`
  - `polydipsia`
  - `metformin`
  - `insulin`
- `detect_disease_categories(text)` detects diabetes if:
  - an exact disease/category name such as `diabetes` appears, or
  - at least 2 diabetes keywords appear.
- `_detect_categories_with_stored(text)` also checks MongoDB `disease_similarity_categories`.

Current support:

- `Type 2 Diabetes Mellitus` should detect `diabetes` if it is present in `clinical_text_for_similarity`.
- `Condition` is included in clinical text only if structured extraction captured it or condition fallback populated diagnosis.

Failure risk:

- If `clinical_text_for_similarity` does not include `diabetes` or related keywords, category detection may return empty.
- If Gemini disease classification is unavailable or low confidence, status can become `unknown_low_confidence`.
- If Report 01 lacks categories and Report 09 categories are present, candidate gating may require disease score or exact overlap; if old clinical text is weak, candidate can be skipped.

Needs runtime verification:

- Check `documents.similar_case_categories` for both reports.
- Check logs:
  - `SIMILAR_NEW_CATEGORIES`
  - `SIMILAR_GEMINI_CLASSIFIED`
  - `SIMILAR_SKIP_CATEGORY_MISMATCH`
  - `SIMILAR_SKIP_NO_DISEASE_GATE`

### 10. Threshold and Scoring Issue

File: `backend/app/services/similar_case_service.py`

Thresholds:

- Final threshold: `FINAL_MATCH_THRESHOLD = 0.75`
- Vector candidate minimum: `VECTOR_CANDIDATE_MIN_SCORE = 0.80`
- Strict vector score without disease gate: `STRICT_VECTOR_SCORE_FOR_NO_CATEGORY = 0.92`
- Disease keyword minimum: `DISEASE_KEYWORD_MIN_SCORE = 0.40`
- Clinical overlap minimum: `CLINICAL_OVERLAP_MIN_SCORE = 0.30`

Final score formula:

```text
final_score =
  vector_score * 0.35
  + disease_score * 0.35
  + symptom_score * 0.15
  + finding_score * 0.10
  + medproc_score * 0.05
```

Important code evidence:

- Disease score has high weight, but it depends on keyword overlap inside the final clinical text, not raw PDF text.
- Symptom/finding/medproc overlap also reads structured extracted fields through `_field_values()`, not raw PDF text.
- Finding overlap currently checks lab/radiology/examination/clinical fields, but not `investigation_findings` in the scoring overlap call.
- If symptoms and findings are not extracted into expected structured fields, final score can stay below 75 even for clinically similar raw PDFs.

Likely rejection examples:

- `vector_score < 0.80`: candidate skipped before scoring.
- Report 01 not returned by vector search: no scoring happens.
- `disease_score = 0` because diabetes terms are missing from clinical text.
- `clinical_overlap < 0.30` because structured symptoms/findings are empty.
- `final_score < 0.75` because vector score alone cannot carry the match.

Needs runtime verification:

- Check logs for `SIMILAR_COMPARE current=<Report09DocId> matched=<Report01DocId> ... final=...`.
- If that log is absent, Report 01 was never scored, meaning the failure happened earlier.

### 11. Frontend Issue

File: `frontend/app/documents/upload/page.tsx`

Frontend upload behavior:

- Parses backend response into `UploadResponse`.
- Saves `result.similar_cases || []` into React state.
- Displays matches using:
  - `similarCasesForDocument(doc.document_id)`
  - filter: `item.new_document_id === doc.document_id`
- Shows `SimilarCasesCard` only if `documentSimilarCases.length > 0`.
- Shows `No matches found` for saved medical documents with zero current-upload matches.

File: `frontend/components/SimilarCasesCard.tsx`

Display behavior:

- If `similarCases` prop is passed, it uses provided cases and does not fetch from backend.
- If item list is empty, it returns `null`.

Frontend conclusion:

- The upload page is not hiding valid backend matches unless `new_document_id` does not equal the uploaded `doc.document_id`.
- The most likely failure is backend returning `similar_cases: []`, not frontend display.

Needs runtime verification:

- Inspect the upload API response in browser devtools.
- If `response.similar_cases` contains a Report 09 to Report 01 match but UI shows none, verify `new_document_id` equals Report 09 `document_id`.

## Root Cause Summary

```text
Root cause 1:
File: backend/app/services/similar_case_service.py
Function: build_clinical_text()
Problem: Similarity text is built from structured extraction fields and summary only; it does not append/use raw extracted_text when Gemini misses clinical details.
Evidence from code: _clinical_text_for_document() calls document.clinical_text_for_similarity or build_clinical_text(extracted_data, document). build_clinical_text() lists structured medical_data fields and summary but not extracted_text.
Impact: Diabetes terms present in the raw PDF can be absent from clinical_text_for_similarity, causing weak embeddings, missing disease category, low overlap scores, and no recommendation.
Fix needed: Add a controlled raw-text fallback for clinical sections/terms when structured extraction is sparse, while stripping patient identifiers and non-clinical boilerplate.

Root cause 2:
File: backend/app/services/similar_case_service.py
Function: process_for_document()
Problem: Report 09 can only find documents that already have clinical_embedding. If Report 01 failed embedding, skipped similarity, or was uploaded before the current pipeline populated embeddings, it is invisible to vector search.
Evidence from code: The vector pipeline matches only documents with clinical_embedding exists and not null. If create_embedding() returns None, process_for_document() sets similar_case_status=skipped_no_embedding and returns [].
Impact: Report 01 may be saved/medical but not searchable, so Report 09 returns no candidates and the frontend shows No matches found.
Fix needed: Backfill embeddings for previously uploaded medical documents and surface skipped_no_embedding/failed_vector_search clearly in logs/UI/admin diagnostics.

Root cause 3:
File: backend/app/database.py and backend/app/services/similar_case_service.py
Function: ensure_indexes() and process_for_document()
Problem: Atlas Vector Search index clinical_embedding_index is required but not created by ensure_indexes().
Evidence from code: ensure_indexes() creates normal indexes only; process_for_document() uses $vectorSearch with index clinical_embedding_index and catches aggregate exceptions as failed_vector_search.
Impact: If the Atlas vector index is missing/wrong, vector search returns no matches and document.similar_case_status becomes failed_vector_search.
Fix needed: Manually create/verify Atlas Vector Search index with path clinical_embedding, dimensions 768, cosine similarity, and document the setup in deployment docs.

Root cause 4:
File: backend/app/services/similar_case_service.py
Function: process_for_document()
Problem: Strict gates can reject clinically similar reports when structured fields are sparse.
Evidence from code: Candidate must pass vector >= 0.80, category/disease gate, clinical_overlap >= 0.30, and final_score >= 0.75. Symptom/finding/medproc overlap uses _field_values() from structured fields, not raw extracted text.
Impact: Even if vector search returns Report 01, the pair can be rejected if diabetes, symptoms, and lab findings were not extracted into expected fields.
Fix needed: Include investigation_findings in finding overlap, use raw-text-derived clinical terms as fallback, and consider a disease-exact-match scoring boost for same disease different patients.

Root cause 5:
File: backend/app/services/similar_case_service.py
Function: process_for_document()
Problem: Same-patient skip removes candidates when new and old documents share the same patient_id.
Evidence from code: If new_patient_id and old_patient_id are equal, the candidate is skipped with SIMILAR_SKIP_SAME_PATIENT.
Impact: If patient matching incorrectly links Report 09 to Report 01's patient, the expected diabetes match is intentionally skipped.
Fix needed: Verify patient_id values for both documents; if wrong, fix patient matching/identity normalization rather than similar-case scoring.
```

## What ChatGPT Should Fix Next

Exact next code fixes based on this inspection:

- In `backend/app/services/similar_case_service.py`, add sanitized raw `extracted_text` fallback to `build_clinical_text()` or `_clinical_text_for_document()` when structured medical sections are sparse.
- In `backend/app/services/similar_case_service.py`, include `investigation_findings` in `finding_overlap_score()` and the process-time finding overlap call.
- In `backend/app/services/similar_case_service.py`, make exact same-disease matches more tolerant when both clinical texts contain `diabetes` / `type 2 diabetes mellitus`.
- In `backend/app/services/similar_case_service.py`, add clearer logs for final-score rejection, not only the comparison log.
- In `backend/app/services/similar_case_service.py`, add a backfill/admin function or maintenance script to create `clinical_text_for_similarity` and `clinical_embedding` for older verified medical documents.
- In `backend/app/services/embedding_service.py`, keep current error logging but expose embedding failure status in upload diagnostics/admin UI.
- In `backend/app/database.py` or deployment docs, document that Atlas Vector Search index `clinical_embedding_index` must be created manually; normal indexes are not enough.
- In `backend/app/routes/documents.py`, ensure upload response exposes `similar_case_status` and `similar_case_error` clearly for debugging when no matches are found.
- In `frontend/app/documents/upload/page.tsx`, keep using `response.similar_cases`; if backend status is `failed_vector_search`, show a diagnostic/admin-only message rather than only `No matches found`.
- In MongoDB data, verify Report 01 and Report 09 are different patients; if not, fix patient matching inputs/normalization.

## MongoDB Compass Verification Checklist

Use MongoDB Compass before changing more code. Search by original filename first, then copy the `document_id`.

For Report 01 document (`DMS_NEW_01_Diabetes_Ritika_Aggarwal.pdf`) in `documents`:

- `document_id`
- `patient_id`
- `patient_name`
- `original_filename`
- `status`
- `is_medical_document`
- `medical_validation`
- `patient_link_action`
- `requires_manual_review`
- `review_reason`
- `extraction_status`
- `extraction_error`
- `ai_status`
- `ai_error`
- `extracted_text`
- `clinical_text_for_similarity`
- `clinical_embedding`
- embedding length, expected `768`
- `similar_case_categories`
- `similar_case_status`
- `similar_case_error`

For Report 09 document (`DMS_NEW_09_Diabetes_Similar_Madhu_Chopra.pdf`) in `documents`:

- `document_id`
- `patient_id`
- `patient_name`
- `original_filename`
- `status`
- `is_medical_document`
- `medical_validation`
- `patient_link_action`
- `requires_manual_review`
- `review_reason`
- `extraction_status`
- `extraction_error`
- `ai_status`
- `ai_error`
- `extracted_text`
- `clinical_text_for_similarity`
- `clinical_embedding`
- embedding length, expected `768`
- `similar_case_categories`
- `similar_case_status`
- `similar_case_error`

For `similar_case_recommendations`:

- Is there any record with `new_document_id` equal to Report 09 document ID?
- If yes, is `matched_document_id` equal to Report 01 document ID?
- What is `similarity_score`?
- What is `match_strength`?
- What are `matched_reasons`?
- What is `status`?
- Are there older stale recommendations for Report 09? Current code deletes recommendations by `new_document_id` before reprocessing.

For `document_extractions`:

- Report 01:
  - `document_id`
  - `extracted_text`
  - `extracted_data.medical_data.condition`
  - `extracted_data.medical_data.diagnosis`
  - `extracted_data.medical_data.chief_complaints`
  - `extracted_data.medical_data.symptoms`
  - `extracted_data.medical_data.vitals`
  - `extracted_data.medical_data.investigation_findings`
  - `extracted_data.medical_data.examination_findings`
  - `extracted_data.medical_data.clinical_findings`
  - `extracted_data.medical_data.lab_tests`
  - `extracted_data.medical_data.advice`
  - `verified_data` is present or null
- Report 09:
  - same fields as Report 01.

For Atlas Search / Vector Search:

- Confirm the `documents` collection has Atlas Vector Search index:
  - Name: `clinical_embedding_index`
  - Path: `clinical_embedding`
  - Dimensions: `768`
  - Similarity: `cosine`
- If missing, Report 09 will likely have `similar_case_status="failed_vector_search"` and `similar_case_error` containing an Atlas/vector index error.

Log lines to search:

- `SIMILAR_START document_id=<Report09DocId>`
- `SIMILAR_CASE: clinical_text_length=...`
- `SIMILAR_MEDICAL_CHECK document_id=<Report09DocId> is_medical=...`
- `SIMILAR_NEW_CATEGORIES document_id=<Report09DocId> categories=...`
- `VECTOR_EMBEDDING_CREATED document_id=<Report09DocId> dim=...`
- `SIMILAR_VECTOR_RESULTS document_id=<Report09DocId> count=...`
- `SIMILAR_SKIP_SAME_PATIENT`
- `SIMILAR_SKIP_LOW_VECTOR`
- `SIMILAR_SKIP_CATEGORY_MISMATCH`
- `SIMILAR_SKIP_NO_DISEASE_GATE`
- `SIMILAR_SKIP_LOW_CLINICAL_OVERLAP`
- `SIMILAR_COMPARE current=<Report09DocId> matched=<Report01DocId> ... final=...`
- `SIMILAR_CREATED current=<Report09DocId> matched=<Report01DocId> score=...`
- `Vector search failed for document <Report09DocId>`
