# HMIS Platform — Enterprise Fix Plan

**Based On:** ENTERPRISE_APP_AUDIT.md (2026-06-26)  
**Execution Strategy:** Fix in priority order — security first, then core workflow gaps, then polish

---

## Phase 1: Security Hardening (CRITICAL — Day 1)

> [!CAUTION]
> These issues MUST be fixed before any real hospital data enters the system.

### 1.1 Fix CORS Policy
- **File:** `backend/main.py:36-42`
- **Fix:** Replace `allow_origins=["*"]` with env-configurable whitelist
- **Add:** `ALLOWED_ORIGINS` to `config.py` and `.env.example`

### 1.2 Secure File Uploads (Remove Public Static Mount)
- **File:** `backend/main.py:71-74`
- **Fix:** Remove `StaticFiles(directory="uploads")` mount
- **Replace:** All file access must go through authenticated `GET /api/storage/files/{id}` endpoint
- **Add:** Signed URL generation with expiry for file downloads

### 1.3 Add Rate Limiting
- **File:** `backend/main.py`, `backend/requirements.txt`
- **Add:** `slowapi` dependency
- **Apply:** Rate limits on `/api/auth/login` (5/min), `/api/auth/patient/login-phone` (3/min), `/api/auth/bootstrap` (1/hour)

### 1.4 Real OTP System Structure
- **Files:** `backend/api/auth.py:84-123`, `backend/tasks.py`
- **Fix:** Generate random 6-digit OTP, store in Redis with 5-min TTL
- **Add:** OTP send task via SMS gateway (WhatsApp/MSG91 as configurable)
- **Keep:** Dev mode fallback with `1234` when `ENVIRONMENT=development`

### 1.5 Health & Readiness Endpoints
- **File:** `backend/main.py`
- **Add:** `GET /health` (always 200), `GET /ready` (checks MongoDB + Redis connectivity)

### 1.6 Fix Auth Store TypeScript Error
- **File:** `frontend/src/store/auth.ts:5`
- **Fix:** `name: str` → `name: string`

### 1.7 Secure Bootstrap Endpoint
- **File:** `backend/api/auth.py:231-262`
- **Fix:** Add rate limiting + environment check (disable in production)
- **Add:** Hash password, don't return it in response

### 1.8 MongoDB Authentication
- **File:** `docker-compose.yml`
- **Add:** `MONGO_INITDB_ROOT_USERNAME` and `MONGO_INITDB_ROOT_PASSWORD`
- **Update:** `MONGODB_URI` to include credentials

---

## Phase 2: Core Workflow Completeness (Day 1-2)

### 2.1 Fix MRN Race Condition
- **File:** `backend/api/patient.py:30-55`
- **Fix:** Use MongoDB `$inc` on atomic counter collection instead of count-based MRN
- **New Collection:** `mrn_counters` with `{branch_id, date, seq}` atomic increment

### 2.2 Add Patient Duplicate Detection
- **File:** `backend/api/patient.py`, `frontend/src/pages/reception/Patients.tsx`
- **Backend:** `GET /api/patients/duplicate-check?phone=&name=&dob=`
- **Frontend:** Call before registration form submit, show warning modal

### 2.3 Add Referring Doctor to Registration
- **Files:**
  - `backend/models/patient.py` — Add `referred_by_doctor_id: Optional[str]`
  - `backend/api/patient.py` — Store referral link on create
  - `frontend/src/pages/reception/Patients.tsx` — Add searchable dropdown

### 2.4 Register PatientPortal Route
- **File:** `frontend/src/App.tsx`
- **Fix:** Import `PatientPortal` and add route `/patient/portal` with `allowedRoles={['patient']}`

### 2.5 Doctor Dashboard Stats Panel
- **Files:**
  - `backend/api/reports.py` — Add `GET /api/reports/doctor-summary` (today's consults, pending labs, etc.)
  - `frontend/src/pages/doctor/Dashboard.tsx` — Add stats cards above queue

### 2.6 Visit Finalization / Locking
- **Files:**
  - `backend/api/consultation.py` — Add `POST /api/consultation/visit/{id}/finalize` (sets `is_finalized: true`)
  - `backend/api/consultation.py` — Block edits on finalized visits (return 403)
  - `frontend/src/pages/doctor/Consultation.tsx` — Add "Finalize Visit" button with confirmation

---

## Phase 3: Notification System (Day 2)

### 3.1 Backend Notification Service
- **New File:** `backend/services/notification_service.py`
- **Features:**
  - In-app notification creation (stored in `notifications` collection)
  - WhatsApp via configurable API (if WHATSAPP_API_TOKEN set)
  - Expo push via Expo API (if EXPO_ACCESS_TOKEN set)
  - SMS via gateway (if configured)
  - Graceful fallback — never crash main flow

### 3.2 Notification API Endpoints
- **File:** `backend/api/notification.py`
- **Add:**
  - `GET /api/notifications/user` — Get current user's unread notifications
  - `POST /api/notifications/mark-read` — Mark notification(s) as read
  - `GET /api/notifications/count` — Unread count for badge

### 3.3 Frontend Notification Bell
- **File:** `frontend/src/components/Layout.tsx`
- **Add:** Bell icon in header bar with unread count badge
- **Add:** Dropdown showing recent notifications
- **Add:** Poll every 30 seconds or Socket.IO push

---

## Phase 4: Inventory Integration Verification (Day 2-3)

### 4.1 Verify Inventory API Compatibility
- **Action:** Test `GET /api/inventory/items/search`, `GET /api/inventory/stock/check`, etc. against the live inventory app
- **File:** `backend/services/inventory_bridge_service.py`
- **Fix:** Adjust API paths/payloads to match actual inventory app API schema

### 4.2 Add Sync Logging
- **New Collection:** `inventory_sync_logs`
- **Log:** Every inventory API call (request, response, status, timestamp)
- **Add:** Retry mechanism for failed syncs

### 4.3 Pharmacy Stock Check Integration
- **File:** `frontend/src/pages/pharmacy/Dispense.tsx`
- **Verify:** Stock check happens before dispense confirmation
- **Add:** Visual stock availability indicator

### 4.4 OT Consumables Sync
- **File:** `backend/api/ot.py`
- **Add:** On surgery completion, deduct consumables from inventory via bridge

---

## Phase 5: Mobile App Enhancement (Day 3-4)

### 5.1 Patient Mobile — Missing Screens

| Screen | Backend API | Implementation |
|--------|------------|----------------|
| Lab Reports | `GET /api/labs/results/patient` | List + PDF viewer |
| Prescriptions | `GET /api/pharmacy/prescriptions/patient` | List + details |
| Documents Upload | `POST /api/storage/upload` | Camera + file picker |
| Invoice Download | `GET /api/billing/invoices/{id}/pdf` | PDF viewer |
| Family Members | New: `GET/POST /api/patients/{id}/family` | List + add |
| ABHA Profile | `GET /api/abdm/profile` | View + link |
| Push Notifications | Expo notification handler | Register token + listen |
| Feedback | `POST /api/portal/feedback` | Star rating + text |

### 5.2 Doctor Mobile — Missing Screens

| Screen | Backend API | Implementation |
|--------|------------|----------------|
| Lab Results | `GET /api/labs/results?visit_id=` | View results for current patient |
| Patient History | `GET /api/patients/{id}/portal-data` | Timeline view |
| Push Notifications | Expo notification handler | Register token + listen |

### 5.3 Push Notification Registration
- **Backend:** Add `POST /api/auth/register-push-token` — stores Expo push token
- **Mobile:** Register on login, send token to backend

---

## Phase 6: Finance & Billing Completeness (Day 4)

### 6.1 Advance Payment
- **Backend:** `POST /api/billing/advance` — Record advance payment against patient
- **Frontend:** Add advance payment form in billing dashboard
- **Link:** Advance payments auto-adjust on invoice creation

### 6.2 Refund Flow
- **Backend:** `POST /api/billing/refund` — Create refund record with audit
- **Frontend:** Refund button on paid invoices (admin/billing roles only)
- **Audit:** Refund must be logged with reason

### 6.3 Patient Ledger
- **Backend:** `GET /api/billing/patient-ledger/{patient_id}` — All financial transactions
- **Frontend:** Patient ledger tab in PatientDetails page

### 6.4 Discount Permissions
- **Backend:** Add `manage_discounts` permission
- **Frontend:** Only show discount field to authorized roles

---

## Phase 7: OT & Clinical Completeness (Day 4-5)

### 7.1 OT Room Double-Booking Prevention
- **File:** `backend/api/ot.py`
- **Add:** On booking creation, check for time overlap with existing bookings in same OT room
- **Return:** 409 Conflict if overlap detected

### 7.2 Jitsi Room Security
- **File:** `backend/api/telemedicine.py`
- **Fix:** Generate UUID-based room names instead of session IDs
- **Add:** JWT token for Jitsi room access (if self-hosted)

### 7.3 Nurse Vitals Enhancement
- **Files:** `backend/models/vitals.py`, `backend/api/vitals.py`, `frontend/src/pages/nurse/Dashboard.tsx`
- **Add:** BMI auto-calculation, pain score (0-10), triage category field

### 7.4 Cross-Module Navigation
- **Files:**
  - `frontend/src/pages/lab/Dashboard.tsx` — Add "View Consultation" link per order
  - `frontend/src/pages/pharmacy/Dashboard.tsx` — Add "View Prescription Source" link
  - `frontend/src/pages/doctor/Consultation.tsx` — Add "View Lab Results" link per order

---

## Phase 8: Admin Tools & Audit Viewer (Day 5)

### 8.1 Audit Log Viewer
- **Backend:** `GET /api/reports/audit-logs` — Paginated, filterable by action/user/date
- **Frontend:** New page `AuditLogs.tsx` — Table with filters, pagination
- **Route:** `/admin/audit-logs`

### 8.2 Expand Audit Coverage
- **Add audit logging to:** Patient view, EMR view/edit, lab result edit, prescription finalize, payment receive, refund, OT notes, file download, role change
- **File:** Add `create_audit_log()` calls in relevant API handlers

### 8.3 Hospital Profile Editor
- **Backend:** `PUT /api/org/tenants/{id}/profile` — Update hospital name, logo, address, GST details
- **Frontend:** Settings page for hospital admins

### 8.4 Template Management
- **Frontend:** Admin page for managing prescription, consent, and checklist templates
- **Backend:** Already has `templates` collection — needs CRUD UI

---

## Phase 9: Deployment Hardening (Day 5-6)

### 9.1 Add Celery Worker to docker-compose
- **File:** `docker-compose.yml`
- **Add:** `hmis-worker` service running `celery -A celery_app worker`

### 9.2 Add MinIO to docker-compose
- **File:** `docker-compose.yml`
- **Add:** MinIO service for S3-compatible file storage

### 9.3 Backup & Restore Scripts
- **New Files:**
  - `scripts/backup.sh` — mongodump + S3 upload
  - `scripts/restore.sh` — S3 download + mongorestore
  - `scripts/cron-backup.sh` — Cron-scheduled backup

### 9.4 Production README
- **New File:** `docs/PRODUCTION_DEPLOYMENT.md`
- **Contents:** Step-by-step VPS deployment, SSL setup, environment config, monitoring

### 9.5 Log Rotation
- **New File:** `docker-compose.yml` logging config
- **Add:** `max-size` and `max-file` logging options for all services

---

## Phase 10: Testing (Day 6-7)

### 10.1 Unit Tests
- **New Directory:** `backend/tests/`
- **Test Files:**
  - `test_mrn_generation.py` — Unique MRN under concurrent access
  - `test_tenant_guard.py` — Tenant isolation verification
  - `test_branch_guard.py` — Branch isolation verification
  - `test_gst_calculation.py` — Invoice total and GST math
  - `test_queue_token.py` — Token generation uniqueness
  - `test_ot_booking.py` — Double-booking prevention

### 10.2 API Integration Tests
- **Framework:** `pytest` + `httpx` async testing
- **Coverage:** Auth, Patients, Appointments, Billing, Lab, Pharmacy, OT
- **Fixtures:** Bootstrap test tenant, branch, users

### 10.3 E2E Flow Test
- **Script:** `tests/e2e/test_hospital_flow.py`
- **Flow:**
  1. Bootstrap super admin
  2. Create tenant + branch + staff
  3. Register patient → book appointment → check-in
  4. Nurse vitals → doctor consult → lab order → result entry
  5. Prescription → dispense → invoice → payment
  6. Verify audit trail

---

## Execution Order Summary

| Phase | Priority | Estimated Effort | Risk if Skipped |
|-------|----------|-----------------|-----------------|
| **Phase 1: Security** | 🔴 CRITICAL | 4-6 hours | System is exploitable |
| **Phase 2: Core Workflow** | 🔴 CRITICAL | 4-6 hours | MRN duplicates, missing routes |
| **Phase 3: Notifications** | 🟡 HIGH | 3-4 hours | Users have no realtime feedback |
| **Phase 4: Inventory** | 🟡 HIGH | 2-3 hours | Pharmacy/OT stock management broken |
| **Phase 5: Mobile Apps** | 🟡 HIGH | 6-8 hours | Patient/Doctor apps are incomplete |
| **Phase 6: Finance** | 🟡 HIGH | 3-4 hours | No refunds/advances/ledger |
| **Phase 7: OT & Clinical** | 🟡 MEDIUM | 3-4 hours | OT double-booking, Jitsi predictable |
| **Phase 8: Admin Tools** | 🟡 MEDIUM | 3-4 hours | No audit visibility for admins |
| **Phase 9: Deployment** | 🟡 MEDIUM | 2-3 hours | No worker, backup, or S3 in Docker |
| **Phase 10: Testing** | 🟡 MEDIUM | 4-6 hours | No automated verification |

**Total Estimated Effort: 35-48 hours**

---

## Files to Create/Modify

### New Files
| File | Purpose |
|------|---------|
| `backend/services/notification_service.py` | Unified notification dispatch |
| `backend/tests/__init__.py` | Test package |
| `backend/tests/test_mrn_generation.py` | MRN uniqueness tests |
| `backend/tests/test_tenant_guard.py` | Tenant isolation tests |
| `backend/tests/test_gst_calculation.py` | GST math tests |
| `backend/tests/e2e/test_hospital_flow.py` | Full E2E flow test |
| `frontend/src/pages/admin/AuditLogs.tsx` | Audit log viewer |
| `scripts/backup.sh` | MongoDB backup script |
| `scripts/restore.sh` | MongoDB restore script |
| `docs/PRODUCTION_DEPLOYMENT.md` | Production deployment guide |

### Modified Files
| File | Changes |
|------|---------|
| `backend/main.py` | CORS fix, remove static uploads, add health endpoints, rate limiting |
| `backend/config.py` | Add ALLOWED_ORIGINS, OTP config |
| `backend/requirements.txt` | Add slowapi, pytest, pytest-asyncio |
| `backend/api/auth.py` | Real OTP, secure bootstrap |
| `backend/api/patient.py` | Atomic MRN, duplicate check, referred_by |
| `backend/api/notification.py` | User notifications, mark-read |
| `backend/api/reports.py` | Doctor summary, audit log viewer |
| `backend/api/consultation.py` | Visit finalization |
| `backend/api/ot.py` | Double-booking check, consumable sync |
| `backend/api/telemedicine.py` | UUID room names |
| `backend/api/vitals.py` | BMI calc, pain score |
| `backend/api/billing.py` | Advance, refund, ledger |
| `backend/models/patient.py` | referred_by field |
| `backend/models/vitals.py` | Pain score, triage |
| `backend/database.py` | mrn_counters, notifications collections |
| `backend/middleware/audit.py` | Enhanced audit helper |
| `backend/tasks.py` | OTP send task, notification tasks |
| `docker-compose.yml` | Worker, MinIO, MongoDB auth, logging |
| `frontend/src/store/auth.ts` | Fix `str` → `string` |
| `frontend/src/App.tsx` | PatientPortal route, AuditLogs route |
| `frontend/src/components/Layout.tsx` | Notification bell, audit log link |
| `frontend/src/pages/doctor/Dashboard.tsx` | Stats panel |
| `frontend/src/pages/reception/Patients.tsx` | Referring doctor dropdown |
| `frontend/src/pages/lab/Dashboard.tsx` | Cross-module links |
| `frontend/src/pages/nurse/Dashboard.tsx` | BMI, pain score |

---

> [!IMPORTANT]
> **Shall I proceed with Phase 1 (Security Hardening) immediately?** This is the most critical phase and must be completed before any other work. I'll tackle each phase in order, providing working code for every fix.

> [!WARNING]
> The mobile apps (Phase 5) represent the largest effort. Consider whether to prioritize mobile completeness or web-first enterprise readiness.
