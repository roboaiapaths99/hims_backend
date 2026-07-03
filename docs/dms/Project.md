# Hospital AI Document Management System

## Project Overview

This project is a **single-hospital AI-powered Document Management System**. It helps hospital staff securely upload, organize, search, review, and understand patient documents.

The system is focused on document intelligence, not full hospital operations. It is **not** a complete Hospital Management System. It does not manage appointments, billing workflows, pharmacy stock, admissions workflow, live consultation, or treatment decisions.

Its main purpose is simple:

> Turn uploaded hospital documents into searchable, patient-wise, clinically useful information.

---

## Why This Project Was Made

Hospitals handle many scanned documents every day:

- Prescriptions
- Lab reports
- Radiology reports
- Admission documents
- Discharge summaries
- Bills
- Doctor notes
- Registration or referral documents
- Scanned PDFs and images

Without intelligence, these files become difficult to use. Staff may save them in folders, but doctors still need to open each file manually to understand the patient history.

This project was made to solve that problem by combining secure storage, text extraction, AI processing, patient matching, patient summaries, timelines, search, and role-based access control.

---

## What Makes This Project Special

Most document management systems can upload and store files. This project goes further.

It can:

- Save original files privately.
- Extract text from PDFs and supported images.
- Use Gemini AI to read hospital documents.
- Extract patient details, doctor details, hospital details, diagnosis, medicine, and report information.
- Match documents to the correct patient.
- Generate document-level summaries.
- Generate a broad patient clinical summary from all uploaded documents.
- Update patient summaries automatically after new uploads.
- Build patient timelines.
- Search patients in real time using patient data and clinical summary content.
- Protect APIs using role-based access control.
- Serve documents only through authenticated backend endpoints.

---

## Current Technology Stack

```mermaid
flowchart TB
    subgraph Frontend
        F1[Next.js 14]
        F2[TypeScript]
        F3[Tailwind CSS]
        F4[Lucide Icons]
    end

    subgraph Backend
        B1[FastAPI]
        B2[Python Services]
        B3[JWT Authentication]
        B4[Permission-Based RBAC]
    end

    subgraph AI
        A1[Gemini AI]
        A2[pypdf PDF Text Extraction]
        A3[Optional Tesseract OCR]
    end

    subgraph Storage
        S1[MongoDB]
        S2[Private Upload Folder]
    end

    F1 --> B1
    B1 --> B2
    B2 --> A1
    B2 --> A2
    B2 --> A3
    B2 --> S1
    B2 --> S2
```

---

## Project Folder Structure

```text
DMS main/
  backend/
    app/
      auth/
      models/
      routes/
      schemas/
      services/
      utils/
    uploads/
    requirements.txt
    Dockerfile

  frontend/
    app/
    components/
    lib/
    package.json
    Dockerfile

  docker-compose.yml
  README.md
  Project.md
```

---

## Main Workflow

```mermaid
flowchart TD
    A[User Logs In] --> B[JWT Token Issued]
    B --> C[Role Permissions Loaded]
    C --> D[User Uploads Document]
    D --> E[Backend Validates File Type and Size]
    E --> F[File Saved Privately]
    F --> G[Document Metadata Saved in MongoDB]
    G --> H[Text Extraction]
    H --> I[Gemini AI Extraction]
    I --> J[Patient Matching]
    J --> K{Strong Patient Match?}
    K -- Yes --> L[Link Document to Patient]
    K -- No --> M[Manual Review or Safe Auto-create]
    L --> N[Save Document Summary]
    M --> N
    N --> O[Refresh Patient Clinical Summary]
    O --> P[Doctor Opens Patient Profile]
    P --> Q[Latest Clinical Summary Is Displayed]
```

---

## Authentication And RBAC

The project uses JWT authentication and backend-enforced role-based access control.

Frontend hiding is only for user experience. Real security is enforced in the backend.

### Supported Roles

1. Admin
2. Doctor
3. Document Staff
4. Receptionist

### Permission Flow

```mermaid
flowchart LR
    A[Login] --> B[JWT Token]
    B --> C[Current User Loaded]
    C --> D[Permissions Calculated From Role]
    D --> E[Frontend Hides Restricted UI]
    D --> F[Backend Validates Every Sensitive API]
    F --> G{Allowed?}
    G -- Yes --> H[Return Data]
    G -- No --> I[Return 401 or 403]
```

### Current Permission Model

| Role | Main Access |
|---|---|
| Admin | Users, roles, audit logs, all patients, all documents, clinical summaries, downloads, archive |
| Doctor | Patient clinical view, summaries, timeline, clinical documents, downloads |
| Document Staff | Upload, document metadata, extraction status, matching, verification, basic patient data |
| Receptionist | Create/update basic patient details, search patients, upload/basic metadata only |

### Important Security Rules

- Inactive users cannot access APIs.
- Users cannot change their own role.
- Documents are not exposed through public file paths.
- Download/preview goes through authenticated backend endpoints.
- Clinical summary is restricted to roles with `summary.view_clinical`.
- Verification controls are restricted to roles with `documents.verify`.

---

## Document Upload Workflow

The upload page now shows a staged progress experience:

- Uploading
- Saving
- Extracting
- Processing

The browser can measure real upload percentage. Saving, extraction, and AI processing are shown as smooth estimated progress until the backend response completes.

```mermaid
sequenceDiagram
    participant User
    participant UI as Next.js Upload Page
    participant API as FastAPI Backend
    participant FileStore as Private Upload Folder
    participant DB as MongoDB
    participant AI as Text Extraction + Gemini

    User->>UI: Select PDF/Image/TXT
    UI->>API: POST /documents/upload
    UI-->>User: Show staged progress
    API->>FileStore: Save file privately
    API->>DB: Save document metadata
    API->>AI: Extract text and structured data
    AI-->>API: Extracted fields and summary
    API->>DB: Save extracted text, status, summary
    API->>DB: Match/link patient
    API->>DB: Refresh patient summary
    API-->>UI: Return processed documents
```

### Upload Validation

The backend validates:

- File extension
- MIME type
- File size
- Private storage path

Supported upload types include:

- PDF
- JPG/JPEG
- PNG
- TXT

---

## Document Storage

The project stores files and metadata separately.

```mermaid
flowchart LR
    A[Uploaded File] --> B[Private Upload Folder]
    A --> C[Metadata in MongoDB]
    C --> D[File Name]
    C --> E[File Size]
    C --> F[MIME Type]
    C --> G[Patient ID]
    C --> H[Extracted Text]
    C --> I[Summary]
    C --> J[Storage Type]
```

The actual file is stored in `backend/uploads`. MongoDB stores metadata, extracted text, summaries, status fields, and the internal storage path. Raw local paths are not shown in the frontend.

---

## Text Extraction

The system extracts readable text before summary generation.

```mermaid
flowchart TD
    A[Uploaded Document] --> B{File Type}
    B -- PDF --> C[pypdf Text Extraction]
    B -- Image --> D[Optional OCR with Tesseract]
    B -- TXT --> E[Read Text Directly]
    C --> F[Save extracted_text]
    D --> F
    E --> F
    F --> G[Save extraction_status]
    F --> H[Save extraction_error if needed]
```

If extraction fails, upload still continues. The database stores `extraction_status` and `extraction_error`.

---

## Gemini AI Processing

Gemini is used to extract structured hospital document information.

It can extract:

- Patient name
- UHID/patient code
- Mobile number
- Age
- Gender
- Document date
- Document type
- Doctor details
- Hospital details
- Diagnosis
- Symptoms
- Medicines
- Lab information
- Procedures
- Follow-up advice
- Summary

If the Gemini API key is missing or AI fails, upload still works with fallback behavior.

---

## Patient Matching

After extraction, the system tries to connect the document to the right patient.

```mermaid
flowchart TD
    A[Extracted Patient Data] --> B{UHID Match}
    B -- Yes --> G[Link Existing Patient]
    B -- No --> C{Mobile Match}
    C -- Yes --> G
    C -- No --> D{Name Similarity}
    D --> E{Age/Gender Support Match}
    E -- Strong --> G
    E -- Weak --> F[Manual Review]
    F --> H[Pending Verification]
    G --> I[Verified/Linked Document]
```

Matching uses:

- UHID/patient ID
- Mobile number
- Patient name similarity
- Age
- Gender

---

## Patient Clinical Summary

The patient profile shows the latest saved patient summary at the top.

There is **no manual Regenerate Summary button**. Summary refresh happens internally when a document is linked or verified.

```mermaid
flowchart TB
    A[Old Saved Patient Summary] --> D[Patient Summary Service]
    B[All Patient Documents] --> D
    C[Latest Uploaded Document Text] --> D
    E[Document Summaries] --> D
    D --> F[Merge Old + New Data]
    F --> G[Remove Duplicate Details]
    G --> H[Save Latest Summary in Patient Record]
    H --> I[Patient Profile Shows Latest Summary]
```

### Saved Summary Fields

The patient summary stores:

- `patient_id`
- `broad_description`
- `structured_summary_json`
- `source_document_ids`
- `total_documents`
- `latest_document_date`
- `last_generated_at`
- `generation_status`
- `generation_error`

### Summary Sections

The summary includes:

- Broad patient description
- Patient overview
- Old disease/past medical history
- Current diagnosis
- Symptoms
- Treatment history
- Current and previous medications
- Hospital/clinic names
- Doctor names
- Medical procedures
- Lab report highlights
- Radiology report highlights
- Admission/discharge details
- Allergies and risk alerts
- Follow-up and pending actions
- Billing/insurance details
- Timeline
- Missing information

### AI Safety Rules

The AI must:

- Use only uploaded documents.
- Not invent medical facts.
- Write "Not mentioned in uploaded documents." when information is missing.
- Write "Needs doctor verification." when information is unclear.
- Avoid final medical advice.
- Avoid marking a medication as current unless the latest document clearly supports it.

---

## What "Needs Doctor Verification" Means

This label means the system found possible medical information but cannot confidently confirm it.

It may appear when:

- OCR text is unclear.
- The scan is blurred or cropped.
- Handwriting is difficult.
- AI finds a possible diagnosis/medicine but the context is uncertain.
- A lab/radiology result looks important but needs professional review.

This is a safety feature. It tells the doctor to check the original document before relying on that detail.

---

## Timeline

The project stores patient timeline entries when documents are linked.

```mermaid
flowchart LR
    A[Verified Document] --> B[Timeline Entry]
    B --> C[Patient ID]
    B --> D[Document ID]
    B --> E[Document Type]
    B --> F[Short Summary]
    B --> G[Created Date]
    G --> H[Timeline Shown on Patient Profile]
```

---

## Real-Time Patient Search

Patient search works while typing with a 300ms debounce.

It searches:

- Patient name
- Patient ID/UHID
- Mobile number
- Age
- Gender
- Address
- Email
- Blood group
- Broad summary
- Diagnosis/history/treatment
- Medicines
- Doctor names
- Hospital names
- Procedures
- Lab/radiology highlights
- Timeline events

```mermaid
flowchart LR
    A[Type in Search Box] --> B[Debounce 300ms]
    B --> C[GET /patients?search=keyword]
    C --> D[Backend Partial Case-Insensitive Search]
    D --> E[Return Matching Patients Only]
    E --> F[Frontend Updates List]
    F --> G{No Match?}
    G -- Yes --> H[Show No matching patients found]
    G -- No --> I[Show Patient Rows]
```

---

## Secure Document View And Download

Documents are served only through authenticated backend routes.

```mermaid
flowchart TD
    A[User Opens Document] --> B[JWT Token Checked]
    B --> C[Permission Checked]
    C --> D{Allowed?}
    D -- Yes --> E[Read Private File]
    E --> F[Return FileResponse]
    D -- No --> G[Return 403 or 404]
```

The frontend never receives raw local upload paths.

---

## Audit Logs

Audit logging exists for important actions such as:

- Login
- Admin seed creation
- User creation/update/disable
- Document upload
- Document view
- Document download
- Document verification
- Document rejection
- Document archive/soft delete
- Patient summary view
- Denied document access attempts

Audit logs are visible only to users with audit permission, normally Admin.

---

## Timezone Handling

Backend timestamps are stored in UTC, which is the recommended database practice.

The backend serializer returns timezone-aware timestamps like:

```text
2026-06-15T07:34:00+00:00
```

The browser converts this to the user's local timezone. For India, UTC + 5:30 displays correctly as IST.

```mermaid
flowchart LR
    A[Backend Stores UTC] --> B[API Sends +00:00 Offset]
    B --> C[Browser Parses Timestamp]
    C --> D[Display in Local Timezone]
```

---

## Database Overview

```mermaid
erDiagram
    USERS ||--o{ DOCUMENTS : uploads
    PATIENTS ||--o{ DOCUMENTS : owns
    DOCUMENTS ||--|| DOCUMENT_EXTRACTIONS : has
    PATIENTS ||--o{ PATIENT_TIMELINE : has
    PATIENTS ||--|| PATIENT_SUMMARY : caches
    USERS ||--o{ AUDIT_LOGS : performs

    USERS {
        string email
        string name
        string role
        array permissions
        boolean is_active
        datetime created_at
        datetime updated_at
    }

    PATIENTS {
        string patient_id
        string uhid
        string name
        string mobile
        int age
        string gender
        string address
        object patient_summary
        datetime created_at
        datetime updated_at
    }

    DOCUMENTS {
        string document_id
        string patient_id
        string document_type
        string file_name
        int file_size
        string mime_type
        string storage_type
        string summary
        string extracted_text
        string extraction_status
        string summary_status
        datetime uploaded_at
        datetime deleted_at
    }

    DOCUMENT_EXTRACTIONS {
        string document_id
        object extracted_data
        object verified_data
        string extracted_text
        string extraction_status
        string summary
        string summary_status
    }

    PATIENT_TIMELINE {
        string patient_id
        string document_id
        string document_type
        string summary
        datetime created_at
    }

    AUDIT_LOGS {
        string action
        string user_email
        string user_role
        object metadata
        datetime created_at
    }
```

---

## API Groups

### Auth

- `POST /auth/login`
- `POST /auth/register-admin-seed`
- `GET /auth/me`

### Users

- `GET /users`
- `POST /users`
- `PUT /users/{user_id}`
- `DELETE /users/{user_id}`

### Patients

- `GET /patients`
- `POST /patients`
- `GET /patients/{patient_id}`
- `PUT /patients/{patient_id}`
- `GET /patients/{patient_id}/summary`
- `GET /patients/{patient_id}/documents`
- `GET /patients/{patient_id}/timeline`

### Documents

- `POST /documents/upload`
- `GET /documents`
- `GET /documents/{document_id}`
- `GET /documents/{document_id}/file`
- `GET /documents/{document_id}/download`
- `POST /documents/{document_id}/process-gemini`
- `PUT /documents/{document_id}/verify`
- `PUT /documents/{document_id}/reject`
- `DELETE /documents/{document_id}`

### Search, Dashboard, Audit

- `GET /search/patients`
- `GET /search/documents`
- `GET /dashboard/stats`
- `GET /audit-logs`

---

## Benefits

### For Doctors

- Quickly understand patient history.
- See old diseases, diagnosis, medications, lab/radiology findings, procedures, and timeline.
- Open original documents only when needed.

### For Document Staff

- Upload documents with visible progress.
- See extraction, matching, and summary status.
- Verify patient links and document type.

### For Receptionists

- Create and update basic patient information.
- Search patients quickly.
- Upload basic documents when permitted.

### For Admins

- Manage users and roles.
- View audit logs.
- Access system-wide dashboard and documents.

---

## Trust Level

You can trust this project for:

- Secure document storage.
- Patient-wise organization.
- Searchable document metadata.
- Helpful AI summaries.
- Audit trails.
- Role-based access enforcement.

You should not use it as:

- A replacement for doctors.
- A final medical diagnosis tool.
- A medication decision tool.
- Emergency medical advice.

The system is a **clinical document intelligence assistant**. Final medical judgment belongs to qualified medical professionals.

---

## Current Limitations

- OCR quality depends on scan quality.
- Tesseract must be installed for image OCR.
- AI extraction depends on document clarity.
- Doctor-patient assignment is not yet modeled separately, so doctor access follows current role-level visibility.
- This is not a full HMS.

---

## Future Improvements

Possible future enhancements:

- Doctor-patient assignment rules.
- Cloud object storage.
- Versioned patient summary history.
- Duplicate document detection.
- Better OCR for handwriting.
- Export patient summary as PDF.
- FHIR/HL7 integration.
- Similar old case discovery.
- More detailed document type taxonomy.

---

## Final Summary

This project securely stores hospital documents and turns them into patient-wise searchable intelligence.

It combines:

1. JWT authentication
2. Role-based permissions
3. Private document storage
4. Text extraction
5. Gemini AI extraction
6. Patient matching
7. Document summaries
8. Automatic patient clinical summaries
9. Patient timelines
10. Real-time patient search
11. Secure document preview/download
12. Audit logging

That makes it much more useful than a simple file storage system while still keeping the doctor in control of final clinical decisions.

