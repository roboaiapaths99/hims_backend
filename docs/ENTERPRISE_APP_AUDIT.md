# HMIS Platform — Enterprise Readiness Audit Report

**Audit Date:** 2026-06-26  
**Auditor:** Enterprise Architecture Review Agent  
**Scope:** Full-stack analysis — Backend, Frontend Web, Patient Mobile, Doctor Mobile, Inventory Integration, Deployment

---

## 1. Executive Summary

The HMIS platform has a **strong architectural foundation** — SaaS multi-tenant structure, JWT+refresh auth with Redis blocklisting, role-based access, Socket.IO realtime, and 25+ backend API modules. The frontend web app covers ~30 pages across 13 role-scoped sections.

However, the application is **NOT enterprise-ready** in its current state. Critical issues exist across security, data validation, mobile integration, inventory sync, and operational completeness. This audit identifies **every gap** that must be fixed before hospitals can use this system in real operations.

---

## 2. Module-by-Module Audit Matrix

| # | Module | Frontend Status | Backend Status | Database Status | API Status | Integration Status | Issues Found | Risk Level |
|---|--------|----------------|----------------|-----------------|------------|-------------------|--------------|------------|
| 1 | **Auth & Login (Staff)** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | OTP hardcoded `1234`, no rate limiting, no real OTP provider | 🟡 Medium |
| 2 | **Auth (Patient OTP)** | ✅ Working | ⚠️ Partially Working | ✅ Working | ✅ Working | ✅ Wired | OTP `1234` hardcoded (mock), no SMS gateway, no OTP expiry/retry | 🔴 High |
| 3 | **Refresh Token Rotation** | ✅ Working | ✅ Working | N/A (Redis) | ✅ Working | ✅ Wired | Replay detection works, Redis fallback to in-memory mock | 🟢 Low |
| 4 | **Super Admin Console** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | Feature flags and subscription placeholder missing | 🟡 Medium |
| 5 | **Hospital Admin** | ⚠️ Partially Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | No hospital profile editor, no GST settings editor, no template management UI | 🟡 Medium |
| 6 | **Branch Admin** | ⚠️ Partially Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | Branch profile editing missing, limited to staff/dept management | 🟡 Medium |
| 7 | **Patient Registration** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | No `referred_by` field, no duplicate detection, no family member linking | 🟡 Medium |
| 8 | **Patient MRN Generation** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | Race condition risk under concurrent registration (count-based, not atomic counter) | 🔴 High |
| 9 | **Patient Search** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | No pagination on search results | 🟡 Medium |
| 10 | **Patient Details/Timeline** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | 45KB page — functional but needs visit timeline verification | 🟢 Low |
| 11 | **Appointments** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | No reschedule, no no-show marking, no follow-up linking | 🟡 Medium |
| 12 | **Queue / Token System** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired (Socket.IO) | Works well — token generation + realtime broadcast | 🟢 Low |
| 13 | **Nurse Vitals** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | No BMI auto-calc, no pain score field, no triage category | 🟡 Medium |
| 14 | **Doctor EMR/Consultation** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | 59KB page — comprehensive SOAP notes, Rx, lab orders. No visit finalization/locking | 🟡 Medium |
| 15 | **Doctor Dashboard** | ⚠️ Partially Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | No stats panel (today's consults, pending labs, etc.) | 🟡 Medium |
| 16 | **Lab Module** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | No "in_progress" status support, no cross-module links | 🟡 Medium |
| 17 | **Pharmacy/Prescription** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | No substitute approval flow, no partial dispense tracking | 🟡 Medium |
| 18 | **Billing & GST** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | No advance payment, no refund flow, no patient ledger | 🟡 Medium |
| 19 | **PayU Payment** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | Branch-level credentials implemented, webhook hash verification exists | 🟢 Low |
| 20 | **Custom Payment Methods** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | Branch-specific config with custom method support done | 🟢 Low |
| 21 | **OT / Surgery** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | No room double-booking check, no consumable inventory sync | 🟡 Medium |
| 22 | **IPD Admission** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | No bed transfer log linked, discharge summary weak | 🟡 Medium |
| 23 | **Telemedicine / Jitsi** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | Uses predictable room naming (session ID), needs UUID-based room | 🟡 Medium |
| 24 | **TPA / Insurance** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | User asked to skip insurance module for now | 🟢 Low |
| 25 | **Radiology** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | PDF upload exists, result workflow complete | 🟢 Low |
| 26 | **Referral & Commission** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | Not linked to patient registration form | 🟡 Medium |
| 27 | **Emergency / Ambulance** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | Functional but basic | 🟢 Low |
| 28 | **Kitchen / Diet** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | Basic CRUD functional | 🟢 Low |
| 29 | **Feedback** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | Admin analytics present, patient submission via portal | 🟢 Low |
| 30 | **Patient Portal (Web)** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ⚠️ Route Missing | Portal page exists but not registered in `App.tsx` routes | 🟡 Medium |
| 31 | **Reports & Analytics** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | 33KB report dashboard — comprehensive | 🟢 Low |
| 32 | **Dashboard (Main)** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | Dynamic stats fetched from API | 🟢 Low |
| 33 | **ABDM / ABHA** | ⚠️ Partially Working | ✅ Working | ✅ Working | ✅ Working | ⚠️ Sandbox Only | Sandbox mode, fields exist, but no real verification flow | 🟡 Medium |
| 34 | **AI Clinical Services** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ✅ Wired | Uses Gemini API for summaries — optional feature | 🟢 Low |
| 35 | **Notifications** | 🔴 Missing UI | ⚠️ Partially Working | ✅ Working | ✅ Working | 🔴 Not Wired | Backend has log endpoint only, no bell/toast in frontend, SMS is mock | 🔴 High |
| 36 | **File Storage** | ✅ Working | ✅ Working | ✅ Working | ✅ Working | ⚠️ Partial | Uses local `uploads/` dir, S3 config exists but not enforced | 🟡 Medium |
| 37 | **Audit Logs** | ✅ Backend | 🔴 Missing UI | ✅ Working | ✅ Working | ⚠️ Partial | Logs created on login/logout and some actions, but no admin viewer, many actions unaudited | 🟡 Medium |
| 38 | **Inventory Integration** | N/A (external) | ✅ Bridge Service | N/A | ⚠️ Partially Working | ⚠️ Not Verified | Bridge client coded, but inventory app may not have matching APIs. Never tested end-to-end | 🔴 High |
| 39 | **Patient Mobile App** | ⚠️ Partially Working | ✅ Working | ✅ Working | ✅ Working | ⚠️ Partial | 5 screens only. Missing: lab reports, prescription view, document upload, invoice download, ABHA, family, notifications | 🔴 High |
| 40 | **Doctor Mobile App** | ⚠️ Partially Working | ✅ Working | ✅ Working | ✅ Working | ⚠️ Partial | 5 screens only. Missing: lab results, full EMR, patient history, push notifications | 🔴 High |

---

## 3. Security Audit

### 🔴 Critical Security Issues

| # | Issue | File(s) | Severity | Details |
|---|-------|---------|----------|---------|
| S1 | **CORS allows all origins** | `main.py:38` | 🔴 Critical | `allow_origins=["*"]` — any website can make authenticated API calls |
| S2 | **OTP hardcoded to `1234`** | `auth.py:92`, patient-mobile `LoginScreen.tsx:35` | 🔴 Critical | No real OTP generation, verification, or rate limiting |
| S3 | **No rate limiting** | All API routes | 🔴 Critical | No `slowapi` or equivalent — login/OTP can be brute-forced |
| S4 | **Uploads served as static files** | `main.py:74` | 🔴 Critical | `StaticFiles(directory="uploads")` — medical files publicly accessible without auth |
| S5 | **Bootstrap endpoint always accessible** | `auth.py:231` | 🟡 High | `/api/auth/bootstrap` creates superadmin — only check is user count > 0 |
| S6 | **JWT secret in code** | `config.py:12` | 🟡 High | Default secret in source code, must be env-only |
| S7 | **No health/ready endpoints** | `main.py` | 🟡 Medium | Missing `/health`, `/ready` for load balancer checks |
| S8 | **`auth.ts:5` — TypeScript type error** | `store/auth.ts:5` | 🟡 Medium | `name: str` should be `name: string` — Python syntax in TS |
| S9 | **Patient data in console.log** | Various API files | 🟡 Medium | `print()` statements with patient data in backend |

### 🟡 Security Improvements Needed

| # | Item | Status |
|---|------|--------|
| S10 | Secure response headers (X-Frame-Options, CSP) | Only in Nginx, not in FastAPI |
| S11 | Input sanitization for XSS | Not implemented |
| S12 | File type validation on uploads | Basic only (extension-based) |
| S13 | File size limits on uploads | Only in Nginx (50MB), not in FastAPI |
| S14 | Signed URLs for file access | Not implemented — files are public |
| S15 | Password complexity requirements | Not enforced |
| S16 | Session/device tracking | Not implemented |
| S17 | MongoDB field-level encryption | Not implemented |

---

## 4. Database Audit

### Collections & Indexes

| Status | Details |
|--------|---------|
| ✅ | 40+ collection accessor functions in `database.py` |
| ✅ | Indexes created on startup for all major collections |
| ✅ | Tenant/branch compound indexes exist |
| ⚠️ | MRN uniqueness is tenant-scoped only, not branch-scoped in index |
| ⚠️ | No TTL indexes for temporary data |
| 🔴 | No backup/restore scripts |
| 🔴 | No MongoDB auth configured in docker-compose |

### Data Isolation

| Check | Status |
|-------|--------|
| Tenant filter on all queries | ✅ `get_tenant_filter()` consistently used |
| Branch filter on branch-scoped queries | ✅ `get_branch_filter()` consistently used |
| `is_deleted` soft-delete filter | ✅ Applied in filter helpers |
| Audit fields injection | ✅ `inject_audit_fields()` used on create/update |

---

## 5. Backend Architecture Audit

### API Routes (25 routers)

| Router | Prefix | Lines | Assessment |
|--------|--------|-------|------------|
| auth | `/api/auth` | 263 | ✅ Complete (login, refresh, logout, bootstrap, patient OTP) |
| org | `/api/org` | ~400 | ✅ Complete (tenants, branches, users, payment settings) |
| config | `/api/config` | ~300 | ✅ Complete (departments, pricing, rooms, lab tests, templates) |
| patient | `/api/patients` | 435 | ✅ Complete (CRUD, search, MRN, medical history, docs, portal) |
| abdm | `/api/abdm` | ~300 | ⚠️ Sandbox only — mock responses |
| appointment | `/api/appointments` | ~450 | ✅ Complete (book, queue, tokens, status transitions) |
| vitals | `/api/vitals` | ~120 | ✅ Working but basic |
| consultation | `/api/consultation` | ~350 | ✅ Complete (visit start, SOAP, notes, orders, finalize) |
| lab | `/api/labs` | ~480 | ✅ Complete (orders, results, PDF upload, verification) |
| pharmacy | `/api/pharmacy` | ~380 | ✅ Complete (queue, dispense, stock check via bridge) |
| billing | `/api/billing` | ~500 | ✅ Complete (invoices, payments, GST, line items) |
| payu | `/api/payu` | ~340 | ✅ Complete (create txn, callback, verify, dynamic credentials) |
| ot | `/api/ot` | ~550 | ✅ Complete (bookings, checklists, notes, room management) |
| telemedicine | `/api/telemedicine` | ~230 | ✅ Working (sessions, room generation) |
| notification | `/api/notifications` | 39 | 🔴 Minimal — only log listing, no send endpoint |
| ai | `/api/ai` | ~220 | ✅ Working (Gemini-based summaries) |
| reports | `/api/reports` | ~450 | ✅ Complete (dashboard summary, aggregations, date ranges) |
| storage | `/api/storage` | ~200 | ✅ Working (upload, list, metadata) |
| ipd | `/api/ipd` | ~480 | ✅ Complete (admit, daily notes, charges, discharge, transfers) |
| tpa | `/api/tpa` | ~400 | ✅ Complete (providers, policies, claims) |
| radiology | `/api/radiology` | ~300 | ✅ Complete (orders, results, PDF) |
| referral | `/api/referrals` | 449 | ✅ Complete (doctors, transactions, payouts, ledger) |
| emergency | `/api/emergency` | ~490 | ✅ Complete (ER admissions, ambulance, triage) |
| visitor_diet | `/api/ipd` (shared) | ~360 | ✅ Working (visitor passes, diet orders) |
| feedback | `/api/portal` | ~170 | ✅ Working (submit, list, analytics) |

### Missing Backend Endpoints

| Endpoint | Purpose | Priority |
|----------|---------|----------|
| `GET /health` | Health check for LB/Docker | 🔴 Critical |
| `GET /ready` | Readiness probe | 🔴 Critical |
| `POST /api/notifications/send` | Send notification to patient | 🟡 High |
| `GET /api/notifications/user` | Get user's unread notifications | 🟡 High |
| `POST /api/notifications/mark-read` | Mark notifications as read | 🟡 High |
| `GET /api/reports/audit-logs` | Admin audit log viewer | 🟡 High |
| `GET /api/patients/duplicate-check` | Pre-registration duplicate check | 🟡 Medium |

---

## 6. Frontend Architecture Audit

### Pages Inventory (36+ pages)

| Section | Pages | Total Size | Assessment |
|---------|-------|------------|------------|
| Auth | Login.tsx | 11KB | ✅ Staff + Patient login modes |
| SuperAdmin | SuperAdmin.tsx | 23KB | ✅ Tenant/Branch/User management |
| Dashboard | Dashboard.tsx | 12KB | ✅ Dynamic stats, role-based views |
| Admin Config | 9 pages | ~135KB | ✅ Departments, Pricing, Rooms, Staff, Referrals, Feedback, Reports, Payments |
| Reception | Patients, PatientDetails, Appointments, Queue | ~100KB | ✅ Full reception workflow |
| Nurse | Dashboard.tsx | ~8KB | ✅ Vitals entry |
| Doctor | Dashboard, Consultation, Teleconsultation | ~114KB | ✅ Most comprehensive section |
| Lab | Dashboard, EnterResults | ~35KB | ✅ Working workflow |
| Pharmacy | Dashboard, Dispense | ~25KB | ✅ Working workflow |
| Billing | 9 pages | ~145KB | ✅ Invoice, checkout, payments, claims, TPA |
| OT | 4 pages | ~60KB | ✅ Surgery booking, checklist, notes |
| IPD | 4 pages | ~70KB | ✅ Admit, workspace, discharge |
| Radiology | 2 pages | ~25KB | ✅ Orders and results |
| Emergency | 2 pages | ~30KB | ✅ ER and ambulance |
| Kitchen | 1 page | ~15KB | ✅ Diet orders |
| Patient | PatientPortal, PatientTeleconsultation | ~37KB | ⚠️ Portal route NOT registered in App.tsx |

### Frontend Issues Found

| # | Issue | File | Severity |
|---|-------|------|----------|
| F1 | `name: str` instead of `name: string` | `store/auth.ts:5` | 🔴 Compile Error |
| F2 | PatientPortal route missing | `App.tsx` | 🟡 Route never accessible |
| F3 | No notification bell/badge in header | `Layout.tsx` | 🟡 No realtime notifications to user |
| F4 | No global toast/snackbar system | All pages | 🟡 Success/error feedback inconsistent |
| F5 | No confirmation modals for destructive actions | Various pages | 🟡 Delete/cancel without confirmation |
| F6 | No pagination on list pages | Patients, Appointments, Invoices | 🟡 Performance issue with large datasets |
| F7 | No empty states on some dashboards | Various | 🟢 Minor UX |
| F8 | Referring doctor dropdown missing | Patients.tsx registration form | 🟡 Can't link referrals at registration |

---

## 7. Mobile App Audit

### Patient Mobile App (5 screens)

| Screen | Status | Backend Connected | Issues |
|--------|--------|-------------------|--------|
| LoginScreen | ✅ Working | ✅ Yes (OTP) | Mock OTP `1234` hardcoded in UI |
| DashboardScreen | ✅ Working | ✅ Yes | Shows appointments and basic info |
| BookAppointmentScreen | ✅ Working | ✅ Yes | Branch/doctor selection works |
| BillingScreen | ⚠️ Partial | ✅ Yes | Basic invoice view, no PayU flow |
| TelehealthScreen | ⚠️ Partial | ✅ Yes | Jitsi join, basic implementation |

**Missing Patient Screens:**

| Screen | Priority |
|--------|----------|
| Lab Reports viewer | 🔴 High |
| Prescription viewer | 🔴 High |
| Document upload | 🟡 Medium |
| Invoice PDF download | 🟡 Medium |
| Family members | 🟡 Medium |
| ABHA profile | 🟡 Medium |
| Push notification preferences | 🟡 Medium |
| Feedback submission | 🟢 Low |

### Doctor Mobile App (5 screens)

| Screen | Status | Backend Connected | Issues |
|--------|--------|-------------------|--------|
| LoginScreen | ✅ Working | ✅ Yes (staff login) | Email/password login |
| DashboardScreen | ✅ Working | ✅ Yes | Queue view |
| PatientVitalsScreen | ✅ Working | ✅ Yes | View patient vitals |
| QuickPrescriptionScreen | ✅ Working | ✅ Yes | Create prescription |
| TelehealthScreen | ⚠️ Partial | ✅ Yes | Jitsi join |

**Missing Doctor Screens:**

| Screen | Priority |
|--------|----------|
| Lab results viewer | 🔴 High |
| Patient history summary | 🟡 Medium |
| Push notifications | 🟡 Medium |
| OT schedule view | 🟢 Low |

---

## 8. Deployment Audit

| Component | Status | Issues |
|-----------|--------|--------|
| Backend Dockerfile | ✅ Exists | Multi-stage build, good |
| Frontend Dockerfile | ✅ Exists | Multi-stage build with nginx |
| docker-compose.yml | ✅ Exists | MongoDB, Redis, API, Web, Nginx |
| Nginx config | ✅ Exists | SSL, WebSocket, security headers |
| .env.example | ✅ Exists | All config vars documented |
| Celery worker | ⚠️ Configured | Not in docker-compose.yml (missing `hmis-worker` service) |
| Backup scripts | 🔴 Missing | No mongodump/mongorestore scripts |
| Restore scripts | 🔴 Missing | No documented restore procedure |
| Log rotation | 🔴 Missing | No logrotate config |
| MongoDB auth | 🔴 Missing | No MONGO_INITDB_ROOT_USERNAME/PASSWORD in docker-compose |
| MinIO/S3 service | 🔴 Missing | S3 config exists but no MinIO in docker-compose |

---

## 9. Testing Audit

| Test Type | Status |
|-----------|--------|
| Unit tests | 🔴 None exist |
| API/Integration tests | 🔴 None exist |
| E2E tests | 🔴 None exist |
| Frontend component tests | 🔴 None exist |
| Mobile app tests | 🔴 None exist |
| Load tests | 🔴 None exist |

---

## 10. Compliance & Standards Audit

| Standard | Status |
|----------|--------|
| HIPAA-ready structure | ⚠️ Partial — audit logs exist but incomplete coverage |
| ABDM/ABHA compliance | ⚠️ Sandbox only — no real HIP/HIU implementation |
| GST invoice compliance | ✅ Invoice number sequencing, GST fields present |
| Data retention policies | 🔴 Not implemented |
| Consent management | ⚠️ Checkbox exists, no consent document storage/versioning |
| API documentation (OpenAPI) | ✅ Auto-generated by FastAPI |

---

## 11. Risk Summary

### 🔴 Critical Risks (Must Fix Before Production)

1. **CORS `*` allows any origin to make authenticated requests**
2. **Medical files served publicly without authentication**
3. **No rate limiting — login/OTP brute-force possible**
4. **OTP hardcoded — no real verification system**
5. **MRN race condition under concurrent registration**
6. **No health endpoints — Docker/Kubernetes can't probe**
7. **MongoDB has no authentication in docker-compose**
8. **TypeScript compile error in auth store (`str` vs `string`)**
9. **Celery worker not included in docker-compose**

### 🟡 High Risks (Should Fix Before Production)

1. No notification system wired (backend exists but minimal)
2. No audit log viewer for admins
3. Inventory bridge never tested with real inventory APIs
4. Patient mobile app missing 8+ critical screens
5. Doctor mobile app missing lab results and notifications
6. No backup/restore scripts or procedures
7. No pagination on list endpoints/pages

### 🟢 Medium Risks (Can Ship But Should Fix Soon)

1. No referring doctor at registration
2. No visit finalization/locking
3. No OT room double-booking prevention
4. Jitsi uses session ID as room name (predictable)
5. No toast/snackbar feedback system
6. No confirmation modals for destructive actions
