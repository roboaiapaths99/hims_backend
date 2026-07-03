from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import socketio
import uvicorn
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from middleware.rate_limit import limiter

from config import settings
from database import connect_to_mongo, close_mongo_connection, DatabaseUnavailableError
from api import auth, org, saas, config, patient, abdm, appointment, vitals, consultation, lab, pharmacy, billing, payu, ot, telemedicine, notification, ai, reports, storage, ipd, tpa, radiology, referral, emergency, visitor_diet, feedback, payments, blood_bank, dms_integration


# Socket.IO Realtime Server Setup
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
sio_app = socketio.ASGIApp(sio)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup Database Setup
    mongo_ready = await connect_to_mongo()
    if not mongo_ready:
        print("Warning: Starting HMIS in degraded mode - MongoDB is unreachable")
    yield
    # Shutdown Database cleanup
    await close_mongo_connection()

from fastapi.exceptions import RequestValidationError

app = FastAPI(
    title="HMIS Platform API",
    description="SaaS Multi-Branch Hospital Management Information System API",
    version="1.0.0",
    lifespan=lifespan
)
app.state.sio = sio
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- GLOBAL USER-FRIENDLY EXCEPTION HANDLERS ---
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    
    # Map technical detail messages to clean, patient/staff friendly wording
    friendly_mappings = {
        "invalid ... format": "The selected record or identifier has an invalid format.",
        "invalid objectid": "The requested item identifier is invalid.",
        "not found": "The requested record or resource could not be found.",
        "already exists": "This record already exists in the system.",
        "must be": "Please ensure all selection fields are correct.",
        "greater than": "Please enter a valid numeric value.",
        "required": "Please fill in all required fields.",
        "failed to": "A system error occurred. Please try again.",
        "db": "A database error occurred. Please contact system support.",
        "mongo": "A database error occurred. Please contact system support.",
        "s3": "Could not retrieve the file. Please contact system support.",
        "connection": "Network connection error. Please try again.",
        "expired": "Your session or link has expired. Please log in again.",
        "invalid token": "Your authorization session is invalid. Please log in again."
    }
    
    if isinstance(detail, str):
        detail_lower = detail.lower()
        # Only override if it looks like a technical developer error
        is_technical = any(word in detail_lower for word in ["format", "invalid id", "objectid", "exception", "bson", "unhandled", "error", "s3", "mongo", "db"])
        if is_technical:
            for pattern, friendly_msg in friendly_mappings.items():
                if pattern in detail_lower:
                    detail = friendly_msg
                    break
            else:
                detail = "The request could not be processed due to an invalid parameter."
                
    return JSONResponse(
        status_code=exc.status_code,
        headers=getattr(exc, "headers", None),
        content={"detail": detail}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    friendly_msg = "The form submission details are incomplete or invalid. Please verify all fields."
    
    if errors:
        first_error = errors[0]
        field_name = first_error.get("loc", ["field"])[-1]
        msg_type = first_error.get("type", "")
        if "missing" in msg_type:
            friendly_msg = f"The field '{field_name}' is required. Please fill it in."
        elif "type_error" in msg_type or "value_error" in msg_type:
            friendly_msg = f"The value provided for '{field_name}' is invalid. Please check the format."
            
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": friendly_msg}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    import traceback
    traceback.print_exc()
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "A system error occurred. The technical team has been notified. Please try again."}
    )

# CORS Policy configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Sub-Routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(org.router, prefix="/api/org", tags=["Organization & SaaS"])
app.include_router(saas.router, prefix="/api/saas", tags=["SaaS Subscriptions"])
app.include_router(config.router, prefix="/api/config", tags=["Hospital Configuration"])
app.include_router(patient.router, prefix="/api/patients", tags=["Patient Directory"])
app.include_router(abdm.router, prefix="/api/abdm", tags=["ABDM Sandbox Integration"])
app.include_router(appointment.router, prefix="/api/appointments", tags=["Appointment and Queue System"])
app.include_router(vitals.router, prefix="/api/vitals", tags=["Vitals Triage"])
app.include_router(consultation.router, prefix="/api/consultation", tags=["EMR Doctor Consultation"])
app.include_router(lab.router, prefix="/api/labs", tags=["Lab Module"])
app.include_router(pharmacy.router, prefix="/api/pharmacy", tags=["Pharmacy Module"])
app.include_router(billing.router, prefix="/api/billing", tags=["Billing Module"])
app.include_router(payu.router, prefix="/api/payu", tags=["PayU Payment Integration"])
app.include_router(payments.router, prefix="/api/payments", tags=["Unified Payments Module"])
app.include_router(ot.router, prefix="/api/ot", tags=["OT / Surgery Module"])
app.include_router(telemedicine.router, prefix="/api/telemedicine", tags=["Telemedicine"])
app.include_router(notification.router, prefix="/api/notifications", tags=["Notifications Logs"])
app.include_router(ai.router, prefix="/api/ai", tags=["Clinical AI Services"])
app.include_router(reports.router, prefix="/api/reports", tags=["Reports & Analytics"])
app.include_router(storage.router, prefix="/api/storage", tags=["File Storage Services"])
app.include_router(ipd.router, prefix="/api/ipd", tags=["IPD & Bed Admission Module"])
app.include_router(tpa.router, prefix="/api/tpa", tags=["TPA & Insurance Module"])
app.include_router(radiology.router, prefix="/api/radiology", tags=["Radiology Module"])
app.include_router(referral.router, prefix="/api/referrals", tags=["Referral & Commission Module"])
app.include_router(emergency.router, prefix="/api/emergency", tags=["Emergency & Ambulance Module"])
app.include_router(visitor_diet.router, prefix="/api/ipd", tags=["Visitor Logs & Kitchen Service"])
app.include_router(feedback.router, prefix="/api/portal", tags=["Patient Feedback Surveys"])
app.include_router(blood_bank.router, prefix="/api/blood-bank", tags=["Blood Bank Module"])
app.include_router(dms_integration.router)


import os
os.makedirs("uploads", exist_ok=True)
# Static mount removed for security hardening. File access must go through secure storage download endpoint.
from api.storage import resolve_secure_file
from typing import Optional

@app.get("/health", tags=["System Health"])
async def health_check():
    return {"status": "healthy"}

@app.get("/ready", tags=["System Health"])
async def readiness_check():
    # Verify MongoDB
    try:
        from database import get_db
        db = get_db()
        await db.command("ping")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database connection failed: {e}"
        )
    # Verify Redis
    try:
        from services.redis_client import redis_wrapper
        if not redis_wrapper.ping():
            raise Exception("Redis ping failed")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Redis connection failed: {e}"
        )
    return {"status": "ready"}


# Mount Socket.IO under ASGI route
app.mount("/socket.io", sio_app)

# ------------------------------------------------------------------
# SOCKET.IO REALTIME EVENT HANDLERS
# ------------------------------------------------------------------
@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")

@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")

@sio.on("join_branch")
async def handle_join_branch(sid, branch_id):
    """Client registers to receive updates scoped to their current branch queue"""
    await sio.enter_room(sid, f"branch_{branch_id}")
    print(f"Client {sid} joined room branch_{branch_id}")

# ------------------------------------------------------------------
# EXCEPTION OVERRIDES & CUSTOM HANDLERS
# ------------------------------------------------------------------
@app.exception_handler(DatabaseUnavailableError)
async def db_unavailable_exception_handler(request: Request, exc: DatabaseUnavailableError):
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "success": False,
            "message": str(exc),
            "detail": str(exc),
            "status": "degraded"
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "message": exc.detail,
            "detail": exc.detail,
            "errors": []
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "An unexpected error occurred on the server.",
            "detail": str(exc),
            "errors": [str(exc)]
        }
    )

@app.get("/health", tags=["System Health"])
async def health_check():
    return {"status": "healthy"}

@app.get("/ready", tags=["System Health"])
async def readiness_check():
    mongo_status = "unreachable"
    try:
        from database import get_db
        db = get_db()
        await db.command("ping")
        mongo_status = "connected"
    except Exception as e:
        mongo_status = f"error: {str(e)}"
        
    redis_status = "unreachable"
    try:
        from services.redis_client import redis_wrapper
        if redis_wrapper.client:
            redis_wrapper.client.ping()
            redis_status = "connected"
        else:
            redis_status = "degraded (in-memory mock)"
    except Exception as e:
        redis_status = f"error: {str(e)}"
        
    is_ready = mongo_status == "connected"
    status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if is_ready else "not_ready",
            "mongodb": mongo_status,
            "redis": redis_status
        }
    )

@app.get("/")
async def root():
    return {
        "platform": "SaaS Multi-Branch Hospital HMIS Platform",
        "status": "active",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.API_HOST, port=settings.API_PORT, reload=settings.DEBUG)
