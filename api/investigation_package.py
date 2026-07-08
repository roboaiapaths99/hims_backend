from fastapi import APIRouter, Depends, HTTPException, status, Request
from bson import ObjectId
from datetime import datetime
from typing import List, Optional

from database import (
    get_investigation_packages_collection,
    get_patients_collection,
    get_users_collection,
    get_db
)
from middleware.auth import get_current_user, inject_audit_fields
from middleware.audit import create_audit_log
from models.investigation_package import (
    InvestigationPackageCreate,
    InvestigationPackageResponse,
    BookPackageRequest,
    PackageTestItem
)

router = APIRouter()

@router.post("/packages", response_model=InvestigationPackageResponse)
async def create_package(
    payload: InvestigationPackageCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Admin endpoint to create a new health checkup / investigation package."""
    role = current_user.get("role")
    if role not in ["super_admin", "hospital_admin", "branch_admin"]:
        raise HTTPException(status_code=403, detail="Access denied: admin rights required")
        
    col = get_investigation_packages_collection()
    
    tenant_oid = current_user["tenant_id"]
    branch_oid = current_user["branch_id"]
    
    now = datetime.utcnow()
    package_doc = {
        "tenant_id": tenant_oid,
        "branch_id": branch_oid,
        "name": payload.name.strip(),
        "description": payload.description,
        "price": payload.price,
        "items": [item.model_dump() for item in payload.items],
        "is_active": True,
        "created_at": now,
        "updated_at": now
    }
    
    res = await col.insert_one(package_doc)
    doc_id = str(res.inserted_id)
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="INVESTIGATION_PACKAGE_CREATED",
        entity="investigation_packages",
        entity_id=doc_id,
        details={"package_name": payload.name, "price": payload.price},
        ip_address=request.client.host if request.client else None,
        tenant_id=tenant_oid,
        branch_id=branch_oid
    )
    
    return InvestigationPackageResponse(
        id=doc_id,
        tenant_id=str(tenant_oid),
        branch_id=str(branch_oid),
        name=payload.name,
        description=payload.description,
        price=payload.price,
        items=payload.items,
        is_active=True,
        created_at=now,
        updated_at=now
    )

@router.get("/packages", response_model=List[InvestigationPackageResponse])
async def list_packages(
    current_user: dict = Depends(get_current_user)
):
    """List all available health checkup investigation packages."""
    col = get_investigation_packages_collection()
    
    tenant_oid = current_user["tenant_id"]
    branch_oid = current_user["branch_id"]
    
    cursor = col.find({"tenant_id": tenant_oid, "branch_id": branch_oid, "is_active": True})
    packages = await cursor.to_list(None)
    
    result = []
    for doc in packages:
        result.append(InvestigationPackageResponse(
            id=str(doc["_id"]),
            tenant_id=str(doc["tenant_id"]),
            branch_id=str(doc["branch_id"]),
            name=doc["name"],
            description=doc.get("description"),
            price=float(doc.get("price", 0.0)),
            items=[PackageTestItem(**item) for item in doc.get("items", [])],
            is_active=doc.get("is_active", True),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"]
        ))
    return result

@router.post("/packages/book")
async def book_package(
    payload: BookPackageRequest,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    """Book a health checkup package for a patient. Auto-creates lab/radiology orders and invoices."""
    db = get_db()
    packages_col = get_investigation_packages_collection()
    patients_col = get_patients_collection()
    users_col = get_users_collection()
    
    tenant_oid = current_user["tenant_id"]
    branch_oid = current_user["branch_id"]
    
    try:
        patient_oid = ObjectId(payload.patient_id)
        package_oid = ObjectId(payload.package_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient_id or package_id format")
        
    # 1. Fetch patient & package
    patient = await patients_col.find_one({"_id": patient_oid, "tenant_id": tenant_oid})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
        
    package = await packages_col.find_one({"_id": package_oid, "tenant_id": tenant_oid})
    if not package or not package.get("is_active", True):
        raise HTTPException(status_code=404, detail="Selected health package is unavailable")
        
    doctor_name = "Self Referral"
    doctor_oid = None
    if payload.doctor_id:
        try:
            doctor_oid = ObjectId(payload.doctor_id)
            doc_user = await users_col.find_one({"_id": doctor_oid, "tenant_id": tenant_oid})
            if doc_user:
                doctor_name = doc_user.get("name", "Doctor")
        except:
            pass
            
    now = datetime.utcnow()
    
    # 2. Record package booking
    booking_doc = {
        "tenant_id": tenant_oid,
        "branch_id": branch_oid,
        "patient_id": patient_oid,
        "package_id": package_oid,
        "package_name": package["name"],
        "price": package["price"],
        "booked_by": str(current_user["_id"]),
        "status": "pending",
        "created_at": now
    }
    booking_res = await db.patient_package_bookings.insert_one(booking_doc)
    booking_id = str(booking_res.inserted_id)
    
    # 3. Create individual lab/radiology orders
    lab_order_ids = []
    rad_order_ids = []
    
    for item in package.get("items", []):
        test_master_id = item["test_master_id"]
        test_name = item["test_name"]
        
        if item["test_type"] == "lab":
            lab_doc = {
                "tenant_id": tenant_oid,
                "branch_id": branch_oid,
                "patient_id": patient_oid,
                "patient_name": f"{patient.get('first_name')} {patient.get('last_name')}",
                "mrn": patient.get("mrn"),
                "doctor_id": doctor_oid,
                "doctor_name": doctor_name,
                "test_name": test_name,
                "items": [{"test_name": test_name, "status": "ordered"}],
                "status": "ordered",
                "payment_status": "paid",  # Paid as part of the bundle
                "created_at": now,
                "updated_at": now,
                "created_by": str(current_user["_id"])
            }
            order_res = await db.lab_orders.insert_one(lab_doc)
            lab_order_ids.append(str(order_res.inserted_id))
            
        elif item["test_type"] == "radiology":
            rad_doc = {
                "tenant_id": tenant_oid,
                "branch_id": branch_oid,
                "patient_id": patient_oid,
                "patient_name": f"{patient.get('first_name')} {patient.get('last_name')}",
                "mrn": patient.get("mrn"),
                "doctor_id": doctor_oid,
                "doctor_name": doctor_name,
                "test_name": test_name,
                "status": "ordered",
                "payment_status": "paid",
                "created_at": now,
                "updated_at": now,
                "created_by": str(current_user["_id"])
            }
            order_res = await db.radiology_orders.insert_one(rad_doc)
            rad_order_ids.append(str(order_res.inserted_id))
            
    # 4. Generate sequential invoice for the package
    from api.billing import generate_invoice_number
    invoice_number = await generate_invoice_number(tenant_oid, branch_oid)
    
    invoice_doc = {
        "tenant_id": tenant_oid,
        "branch_id": branch_oid,
        "patient_id": patient_oid,
        "invoice_number": invoice_number,
        "invoice_type": "opd",
        "doctor_id": doctor_oid,
        "doctor_name": doctor_name,
        "items": [{
            "description": f"Health Checkup Package: {package['name']}",
            "hsn_sac": "9993",
            "quantity": 1,
            "rate": package["price"],
            "unit_price": package["price"],
            "amount": package["price"]
        }],
        "subtotal": package["price"],
        "discount": 0.0,
        "tax_percentage": 0.0,
        "tax_amount": 0.0,
        "grand_total": package["price"],
        "amount_paid": package["price"],
        "payment_status": "paid",
        "created_at": now,
        "updated_at": now,
        "created_by": str(current_user["_id"])
    }
    
    await db.invoices.insert_one(invoice_doc)
    
    # 5. Create Payment receipt record
    payment_doc = {
        "tenant_id": tenant_oid,
        "branch_id": branch_oid,
        "invoice_id": invoice_doc["_id"],
        "patient_id": patient_oid,
        "amount": package["price"],
        "payment_method": payload.payment_method,
        "transaction_id": f"PKG-{booking_id[-8:].upper()}",
        "status": "success",
        "created_at": now,
        "created_by": str(current_user["_id"])
    }
    await db.payments.insert_one(payment_doc)
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="INVESTIGATION_PACKAGE_BOOKED",
        entity="patient_package_bookings",
        entity_id=booking_id,
        details={"package_name": package["name"], "price": package["price"], "lab_orders": len(lab_order_ids), "radiology_orders": len(rad_order_ids)},
        ip_address=request.client.host if request.client else None,
        tenant_id=tenant_oid,
        branch_id=branch_oid
    )
    
    return {
        "status": "success",
        "message": f"Package '{package['name']}' booked successfully. {len(lab_order_ids)} lab orders and {len(rad_order_ids)} radiology orders generated.",
        "booking_id": booking_id,
        "invoice_number": invoice_number,
        "lab_order_ids": lab_order_ids,
        "radiology_order_ids": rad_order_ids
    }
