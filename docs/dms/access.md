# Role Access

Access is role-based. Extra custom permissions may be added per user.

| Role | Access |
| --- | --- |
| Admin | Full dashboard and full access to users, patients, documents, summaries, similar cases, audit logs, upload, verify, download, archive. |
| Doctor | Doctor dashboard, patients, allowed medical/basic documents, clinical summaries/timeline, similar cases, feedback, upload. |
| Document Staff | Processing dashboard, create/search patients, upload, view/download documents for review, OCR/extraction, match patients, verify/reject. |
| Receptionist | Reception dashboard, create/search/update basic patients, upload documents, view document metadata/status. |

## Document Content Rules

- Admin can access all document content.
- Doctor can access content for clinical, lab, radiology, and basic documents.
- Document Staff can access original document content/download for review.
- Receptionist can view metadata, but not original document content/download unless given custom permission and allowed by backend rules.
- Similar cases are admin and doctor only.

## Restricted By Default

- Audit logs: Admin only.
- User management: Admin only.
- Clinical patient summaries: Admin and Doctor.
- Similar-case feedback: Admin and Doctor.
