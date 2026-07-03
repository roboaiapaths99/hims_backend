from fastapi import APIRouter, Depends, HTTPException, status, Request
from bson import ObjectId
from datetime import datetime, timedelta
from typing import List, Optional

from database import (
    get_ot_bookings_collection,
    get_ot_checklists_collection,
    get_patients_collection,
    get_users_collection,
    get_rooms_collection
)
from middleware.auth import (
    get_current_user,
    get_branch_filter,
    inject_audit_fields
)
from middleware.audit import create_audit_log
from models.ot import (
    OTBookingCreate,
    OTBookingUpdate,
    OTBookingResponse,
    OTChecklistSave,
    OTChecklistResponse,
    OTConsumablesDeduct
)
from services.inventory_bridge_service import inventory_bridge

router = APIRouter()

async def resolve_booking_details(doc: dict) -> dict:
    """Helper to resolve OIDs to human-readable names for patient, staff, and room"""
    patients_col = get_patients_collection()
    users_col = get_users_collection()
    rooms_col = get_rooms_collection()
    
    doc["id"] = str(doc["_id"])
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    
    # 1. Patient Details
    patient = await patients_col.find_one({"_id": doc["patient_id"]})
    if patient:
        doc["patient_name"] = f"{patient.get('first_name', '')} {patient.get('last_name', '')}"
        doc["patient_mrn"] = patient.get("mrn", "N/A")
    else:
        doc["patient_name"] = "Unknown Patient"
        doc["patient_mrn"] = "N/A"
    doc["patient_id"] = str(doc["patient_id"])
        
    # 2. Surgeon Details
    surgeon = await users_col.find_one({"_id": doc["surgeon_id"]})
    doc["surgeon_name"] = surgeon.get("name", "Unknown Surgeon") if surgeon else "Unknown Surgeon"
    doc["surgeon_id"] = str(doc["surgeon_id"])
    
    # 3. Anesthetist Details
    anesthetist = await users_col.find_one({"_id": doc["anesthetist_id"]})
    doc["anesthetist_name"] = anesthetist.get("name", "Unknown Anesthetist") if anesthetist else "Unknown Anesthetist"
    doc["anesthetist_id"] = str(doc["anesthetist_id"])
    
    # 4. Room Details
    room = await rooms_col.find_one({"_id": doc["room_id"]})
    doc["room_number"] = f"OT Room {room.get('room_number')}" if room else "Unknown Room"
    doc["room_id"] = str(doc["room_id"])
    
    return doc

@router.post("/bookings", response_model=OTBookingResponse)
async def create_booking(
    payload: OTBookingCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    ot_bookings_col = get_ot_bookings_collection()
    patients_col = get_patients_collection()
    users_col = get_users_collection()
    rooms_col = get_rooms_collection()
    
    # 1. Parse ObjectIds
    try:
        patient_oid = ObjectId(payload.patient_id)
        surgeon_oid = ObjectId(payload.surgeon_id)
        anesthetist_oid = ObjectId(payload.anesthetist_id)
        room_oid = ObjectId(payload.room_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid ID parameter format")
        
    # 2. Verify targets exist
    patient = await patients_col.find_one({"_id": patient_oid, "tenant_id": current_user["tenant_id"]})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
        
    surgeon = await users_col.find_one({"_id": surgeon_oid, "tenant_id": current_user["tenant_id"]})
    if not surgeon:
        raise HTTPException(status_code=404, detail="Surgeon staff profile not found")
        
    anesthetist = await users_col.find_one({"_id": anesthetist_oid, "tenant_id": current_user["tenant_id"]})
    if not anesthetist:
        raise HTTPException(status_code=404, detail="Anesthetist staff profile not found")
        
    room = await rooms_col.find_one({"_id": room_oid, "tenant_id": current_user["tenant_id"]})
    if not room:
        raise HTTPException(status_code=404, detail="Operating room configuration not found")
        
    # 3. Double-Booking checks (2-hour buffer window)
    start_buffer = payload.schedule_date - timedelta(hours=2)
    end_buffer = payload.schedule_date + timedelta(hours=2)
    
    room_conflict = await ot_bookings_col.find_one({
        "room_id": room_oid,
        "status": {"$ne": "cancelled"},
        "schedule_date": {"$gte": start_buffer, "$lte": end_buffer}
    })
    if room_conflict:
        raise HTTPException(status_code=400, detail="Room is already booked for another surgery in this time window")
        
    surgeon_conflict = await ot_bookings_col.find_one({
        "surgeon_id": surgeon_oid,
        "status": {"$ne": "cancelled"},
        "schedule_date": {"$gte": start_buffer, "$lte": end_buffer}
    })
    if surgeon_conflict:
        raise HTTPException(status_code=400, detail="Surgeon is scheduled for another surgery in this time window")
        
    # 4. Insert booking
    doc = payload.dict()
    inject_audit_fields(current_user, doc)
    
    doc["patient_id"] = patient_oid
    doc["surgeon_id"] = surgeon_oid
    doc["anesthetist_id"] = anesthetist_oid
    doc["room_id"] = room_oid
    doc["status"] = "planned"
    
    res = await ot_bookings_col.insert_one(doc)
    doc["_id"] = res.inserted_id
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="OT_BOOKING_CREATED",
        entity="ot_bookings",
        entity_id=str(res.inserted_id),
        details={"surgery_name": payload.surgery_name, "schedule_date": payload.schedule_date.isoformat()},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    resolved = await resolve_booking_details(doc)
    return OTBookingResponse(**resolved)

@router.get("/bookings", response_model=List[OTBookingResponse])
async def list_bookings(
    status_filter: Optional[str] = None,
    room_id: Optional[str] = None,
    surgeon_id: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    ot_bookings_col = get_ot_bookings_collection()
    query = get_branch_filter(current_user)
    
    if status_filter:
        query["status"] = status_filter
    if room_id:
        try:
            query["room_id"] = ObjectId(room_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid room_id format")
    if surgeon_id:
        try:
            query["surgeon_id"] = ObjectId(surgeon_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid surgeon_id format")
            
    docs = await ot_bookings_col.find(query).sort("schedule_date", 1).to_list(None)
    result = []
    for doc in docs:
        resolved = await resolve_booking_details(doc)
        result.append(OTBookingResponse(**resolved))
    return result

@router.get("/bookings/{id}", response_model=OTBookingResponse)
async def get_booking(id: str, current_user: dict = Depends(get_current_user)):
    ot_bookings_col = get_ot_bookings_collection()
    try:
        booking_oid = ObjectId(id)
    except:
        raise HTTPException(status_code=400, detail="Invalid booking ID format")
        
    doc = await ot_bookings_col.find_one({"_id": booking_oid, "tenant_id": current_user["tenant_id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="OT Booking record not found")
        
    resolved = await resolve_booking_details(doc)
    return OTBookingResponse(**resolved)

@router.put("/bookings/{id}/checklist", response_model=OTChecklistResponse)
async def save_checklist(
    id: str,
    payload: OTChecklistSave,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    ot_bookings_col = get_ot_bookings_collection()
    checklists_col = get_ot_checklists_collection()
    
    try:
        booking_oid = ObjectId(id)
    except:
        raise HTTPException(status_code=400, detail="Invalid booking ID format")
        
    # Verify booking exists
    booking = await ot_bookings_col.find_one({"_id": booking_oid, "tenant_id": current_user["tenant_id"]})
    if not booking:
        raise HTTPException(status_code=404, detail="Surgical booking session not found")
        
    now = datetime.utcnow()
    existing = await checklists_col.find_one({"booking_id": booking_oid})
    
    doc = payload.dict()
    doc["updated_at"] = now
    doc["updated_by"] = str(current_user["_id"])
    
    if existing:
        await checklists_col.update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "items_checked": payload.items_checked,
                "signed_off_by": payload.signed_off_by,
                "updated_at": now,
                "updated_by": str(current_user["_id"])
            }}
        )
        doc_id = str(existing["_id"])
        created_at = existing["created_at"]
        created_by = existing["created_by"]
    else:
        new_doc = {
            "tenant_id": current_user["tenant_id"],
            "branch_id": current_user["branch_id"],
            "booking_id": booking_oid,
            "items_checked": payload.items_checked,
            "signed_off_by": payload.signed_off_by,
            "created_at": now,
            "updated_at": now,
            "created_by": str(current_user["_id"]),
            "updated_by": str(current_user["_id"])
        }
        res = await checklists_col.insert_one(new_doc)
        doc_id = str(res.inserted_id)
        created_at = now
        created_by = str(current_user["_id"])
        
    # Advance booking status automatically to pre_op_pending upon checklist save
    if booking["status"] == "planned":
        await ot_bookings_col.update_one(
            {"_id": booking_oid},
            {"$set": {"status": "pre_op_pending", "updated_at": now, "updated_by": str(current_user["_id"])}}
        )
        
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="OT_CHECKLIST_UPDATED",
        entity="ot_checklists",
        entity_id=doc_id,
        details={"booking_id": id},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    return OTChecklistResponse(
        id=doc_id,
        tenant_id=str(current_user["tenant_id"]),
        branch_id=str(current_user["branch_id"]),
        booking_id=id,
        items_checked=payload.items_checked,
        signed_off_by=payload.signed_off_by,
        created_at=created_at,
        updated_at=now,
        created_by=created_by,
        updated_by=str(current_user["_id"])
    )

@router.get("/bookings/{id}/checklist", response_model=OTChecklistResponse)
async def get_checklist(id: str, current_user: dict = Depends(get_current_user)):
    checklists_col = get_ot_checklists_collection()
    
    try:
        booking_oid = ObjectId(id)
    except:
        raise HTTPException(status_code=400, detail="Invalid booking ID")
        
    doc = await checklists_col.find_one({"booking_id": booking_oid})
    if not doc:
        # Return default empty checklist configuration
        return OTChecklistResponse(
            id="",
            tenant_id=str(current_user["tenant_id"]),
            branch_id=str(current_user["branch_id"]),
            booking_id=id,
            items_checked={},
            signed_off_by=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            created_by="",
            updated_by=""
        )
        
    doc["id"] = str(doc["_id"])
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    doc["booking_id"] = str(doc["booking_id"])
    return OTChecklistResponse(**doc)

@router.post("/bookings/{id}/consumables")
async def record_consumables(
    id: str,
    payload: OTConsumablesDeduct,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    ot_bookings_col = get_ot_bookings_collection()
    try:
        booking_oid = ObjectId(id)
    except:
        raise HTTPException(status_code=400, detail="Invalid booking ID format")
        
    booking = await ot_bookings_col.find_one({"_id": booking_oid, "tenant_id": current_user["tenant_id"]})
    if not booking:
        raise HTTPException(status_code=404, detail="Surgical booking session not found")
        
    # Bulk deduct stock from Inventory sync bridge client
    deductions_success = []
    deductions_errors = []
    
    for item in payload.items:
        try:
            res = await inventory_bridge.deduct_stock(
                medicine_id=item.medicine_id,
                quantity=item.quantity,
                warehouse_id=item.warehouse_id,
                reference_id=id,
                batch_id=item.batch_id
            )
            deductions_success.append({
                "medicine_id": item.medicine_id,
                "quantity": item.quantity,
                "status": "deducted"
            })
        except Exception as e:
            deductions_errors.append({
                "medicine_id": item.medicine_id,
                "error": str(e)
            })
            
    # Auto advance booking status to completed if consumables are fully processed
    if not deductions_errors:
        await ot_bookings_col.update_one(
            {"_id": booking_oid},
            {"$set": {"status": "completed", "updated_at": datetime.utcnow(), "updated_by": str(current_user["_id"])}}
        )
        
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="OT_CONSUMABLES_DEDUCTED",
        entity="ot_bookings",
        entity_id=id,
        details={"success_count": len(deductions_success), "error_count": len(deductions_errors)},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    return {
        "booking_id": id,
        "success": deductions_success,
        "failed": deductions_errors,
        "status": "completed" if not deductions_errors else "degraded"
    }

@router.put("/bookings/{id}/status", response_model=OTBookingResponse)
async def update_booking_status(
    id: str,
    payload: dict,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    new_status = payload.get("status")
    if not new_status or new_status not in ["planned", "pre_op_pending", "in_surgery", "completed", "cancelled"]:
        raise HTTPException(status_code=400, detail="Invalid surgery status parameter")
        
    ot_bookings_col = get_ot_bookings_collection()
    try:
        booking_oid = ObjectId(id)
    except:
        raise HTTPException(status_code=400, detail="Invalid booking ID format")
        
    booking = await ot_bookings_col.find_one({"_id": booking_oid, "tenant_id": current_user["tenant_id"]})
    if not booking:
        raise HTTPException(status_code=404, detail="Surgical booking session not found")
        
    # If transitioning to cancelled or completed, release any remaining reserved stock on inventory bridge
    if new_status in ["cancelled", "completed"]:
        try:
            await inventory_bridge.release_stock(reference_id=id)
        except Exception as e:
            # log warning but proceed with local status update
            print(f"Warning: Failed to release inventory stocks: {e}")
            
    await ot_bookings_col.update_one(
        {"_id": booking_oid},
        {"$set": {"status": new_status, "updated_at": datetime.utcnow(), "updated_by": str(current_user["_id"])}}
    )
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="OT_BOOKING_STATUS_CHANGED",
        entity="ot_bookings",
        entity_id=id,
        details={"old_status": booking["status"], "new_status": new_status},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    updated = await ot_bookings_col.find_one({"_id": booking_oid})
    resolved = await resolve_booking_details(updated)
    return OTBookingResponse(**resolved)

@router.put("/bookings/{id}", response_model=OTBookingResponse)
async def update_booking(
    id: str,
    payload: OTBookingUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    ot_bookings_col = get_ot_bookings_collection()
    try:
        booking_oid = ObjectId(id)
    except:
        raise HTTPException(status_code=400, detail="Invalid booking ID format")
        
    booking = await ot_bookings_col.find_one({"_id": booking_oid, "tenant_id": current_user["tenant_id"]})
    if not booking:
        raise HTTPException(status_code=404, detail="Surgical booking session not found")
        
    update_data = payload.dict(exclude_unset=True)
    if "surgeon_id" in update_data and update_data["surgeon_id"]:
        update_data["surgeon_id"] = ObjectId(update_data["surgeon_id"])
    if "anesthetist_id" in update_data and update_data["anesthetist_id"]:
        update_data["anesthetist_id"] = ObjectId(update_data["anesthetist_id"])
    if "room_id" in update_data and update_data["room_id"]:
        update_data["room_id"] = ObjectId(update_data["room_id"])
        
    update_data["updated_at"] = datetime.utcnow()
    update_data["updated_by"] = str(current_user["_id"])
    
    # If status is transitioning to cancelled, release any reserved stock on inventory bridge
    if update_data.get("status") == "cancelled" and booking["status"] != "cancelled":
        try:
            await inventory_bridge.release_stock(reference_id=id)
        except Exception as e:
            print(f"Warning: Failed to release inventory stocks: {e}")
            
    await ot_bookings_col.update_one({"_id": booking_oid}, {"$set": update_data})
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="OT_BOOKING_UPDATED",
        entity="ot_bookings",
        entity_id=id,
        details=list(update_data.keys()),
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    updated = await ot_bookings_col.find_one({"_id": booking_oid})
    resolved = await resolve_booking_details(updated)
    return OTBookingResponse(**resolved)
