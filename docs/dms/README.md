# Single-Hospital AI Document Management System MVP

This repository contains a production-ready MVP scaffold for a single-hospital AI Document Management System. It starts after documents are scanned or uploaded, then stores originals, extracts structured data with Gemini, suggests patient matches by confidence, lets staff verify the result, and saves documents patient-wise, category-wise, and date-wise.

It is intentionally not a Hospital Management System. It does not include appointments, billing workflows, live consultation, pharmacy, admissions workflow, or patient treatment workflow.

## Stack

- Frontend: Next.js, Tailwind CSS
- Backend: FastAPI
- Database: MongoDB Atlas or local MongoDB-compatible URI
- AI extraction: Gemini API
- File storage: local `backend/uploads`, with storage isolated behind `file_service.py`
- Auth: JWT with role-based access
- Deployment: Dockerfile and `docker-compose.yml`

## Setup

1. Create a MongoDB Atlas database and copy its connection string.
2. Copy `backend/.env.example` to `backend/.env`, then set `MONGODB_URI`, `JWT_SECRET`, and `GEMINI_API_KEY`.
3. Copy `frontend/.env.example` to `frontend/.env`.
4. Run the backend:

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

5. Run the frontend:

```bash
cd frontend
npm install
npm run dev
```

6. Create the first admin user:

```bash
curl -X POST http://localhost:8000/auth/register-admin-seed \
  -H "Content-Type: application/json" \
  -d "{\"name\":\"Admin\",\"email\":\"admin@example.com\",\"password\":\"ChangeMe123!\",\"role\":\"admin\"}"
```

7. Sign in at `http://localhost:3000/login`, create staff/patients, then upload the first document.

## Docker

Create both `.env` files, then run:

```bash
docker compose up --build
```

The frontend will be available at `http://localhost:3000`; the API will be available at `http://localhost:8000`.

## Main Workflow

1. Staff uploads PDF or image files.
2. Backend stores the original file immediately under `backend/uploads`.
3. Backend sends the file to Gemini.
4. Gemini returns structured JSON only.
5. The system classifies document type and extracts patient fields.
6. Patient matching checks UHID, mobile, fuzzy name, age, and gender.
7. Confidence `>= 0.75` shows a suggested patient.
8. Confidence `< 0.75` requires manual patient search and selection.
9. Staff edits extracted data, confirms document type, and saves.
10. The document is linked to the patient timeline and is searchable later.

## Key API Groups

- Auth: `/auth/login`, `/auth/register-admin-seed`, `/auth/me`
- Users: `/users`
- Patients: `/patients`
- Documents: `/documents/upload`, `/documents/{document_id}`, `/documents/{document_id}/file`, `/documents/{document_id}/verify`
- Search: `/search/documents`, `/search/patients`
- Dashboard: `/dashboard/stats`
- Audit: `/audit-logs`

## Notes

- If `GEMINI_API_KEY` is missing, the backend returns a safe mock extraction warning instead of failing uploads.
- Raw file paths are never returned for public use; files are served through an authenticated endpoint.
- Document deletion is a soft delete using `deleted_at`.
- Future similar-case intelligence can be added by embedding verified summaries from `document_extractions` and linking matches back to uploaded records as “similar old record found,” not as medical advice.
