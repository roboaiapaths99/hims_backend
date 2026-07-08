from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from bson import ObjectId
from middleware.auth import get_current_user
from database import (
    get_blood_donors_collection,
    get_blood_donations_collection,
    get_blood_stock_collection,
    get_blood_requisitions_collection,
    get_blood_transfusions_collection,
    get_patients_collection
)
from models.blood_bank import (
    BloodDonorCreate,
    BloodDonorResponse,
    DonorScreeningBase,
    BloodDonationCreate,
    BloodDonationResponse,
    LabTestingUpdate,
    BloodRequisitionCreate,
    BloodRequisitionResponse,
    BloodCrossmatchCreate,
    BloodTransfusionCreate
)

router = APIRouter()

# Compatibility check helper
def check_compatibility(donor_group: str, recipient_group: str) -> bool:
    if donor_group == "O-":
        return True
    if donor_group == "O+" and recipient_group.endswith("+"):
        return True
    if recipient_group == "AB+":
        return True
    if donor_group == recipient_group:
        return True
    if donor_group == "A-":
        return recipient_group in ["A-", "A+", "AB-", "AB+"]
    if donor_group == "A+":
        return recipient_group in ["A+", "AB+"]
    if donor_group == "B-":
        return recipient_group in ["B-", "B+", "AB-", "AB+"]
    if donor_group == "B+":
        return recipient_group in ["B+", "AB+"]
    if donor_group == "AB-":
        return recipient_group in ["AB-", "AB+"]
    return False

def get_request_branch_id(request: Request, current_user: dict) -> ObjectId:
    branch_id_str = request.headers.get("x-branch-id") or request.headers.get("X-Branch-ID") or current_user.get("branch_id")
    if not branch_id_str:
        raise HTTPException(status_code=400, detail="Branch scope context missing. Please select a branch first.")
    try:
        return ObjectId(str(branch_id_str))
    except:
        raise HTTPException(status_code=400, detail="Invalid branch ID format")

# ------------------------------------------------------------------
# STOCK ENDPOINTS
# ------------------------------------------------------------------
@router.get("/stock")
async def get_blood_stock(request: Request, current_user: dict = Depends(get_current_user)):
    stock_col = get_blood_stock_collection()
    tenant_id = current_user.get("tenant_id")
    branch_id = get_request_branch_id(request, current_user)
    
    # Get available stock detailed list
    cursor = stock_col.find({
        "tenant_id": tenant_id,
        "branch_id": branch_id,
        "status": "available"
    })
    bags = await cursor.to_list(None)
    
    # Formulate grouping summary
    summary = {}
    for bag in bags:
        grp = bag["blood_group"]
        comp = bag["component_type"]
        key = f"{grp}_{comp}"
        summary[key] = summary.get(key, 0) + 1
        
    detailed_bags = []
    for b in bags:
        b["id"] = str(b["_id"])
        if "donor_id" in b:
            b["donor_id"] = str(b["donor_id"])
        b["expiry_date"] = b["expiry_date"].isoformat() if isinstance(b["expiry_date"], datetime) else b["expiry_date"]
        detailed_bags.append(b)
        
    return {
        "summary": summary,
        "bags": detailed_bags
    }

@router.post("/stock/adjust")
async def adjust_blood_stock(payload: dict, request: Request, current_user: dict = Depends(get_current_user)):
    stock_col = get_blood_stock_collection()
    tenant_id = current_user.get("tenant_id")
    branch_id = get_request_branch_id(request, current_user)
    
    bag_number = payload.get("bag_number")
    action = payload.get("action")  # discard
    reason = payload.get("reason", "manual adjustment")
    
    if not bag_number:
        raise HTTPException(status_code=400, detail="bag_number is required")
        
    bag = await stock_col.find_one({
        "bag_number": bag_number,
        "tenant_id": tenant_id,
        "branch_id": branch_id
    })
    if not bag:
        raise HTTPException(status_code=404, detail="Blood bag not found")
        
    if action == "discard":
        await stock_col.update_one(
            {"_id": bag["_id"]},
            {"$set": {
                "status": "discarded",
                "discard_reason": reason,
                "updated_at": datetime.utcnow()
            }}
        )
        return {"status": "success", "message": f"Bag {bag_number} has been discarded."}
        
    raise HTTPException(status_code=400, detail="Invalid action specified")

# ------------------------------------------------------------------
# DONORS ENDPOINTS
# ------------------------------------------------------------------
@router.get("/donors", response_model=List[BloodDonorResponse])
async def list_donors(request: Request, current_user: dict = Depends(get_current_user)):
    donors_col = get_blood_donors_collection()
    tenant_id = current_user.get("tenant_id")
    branch_id = get_request_branch_id(request, current_user)
    
    cursor = donors_col.find({"tenant_id": tenant_id, "branch_id": branch_id})
    donors = await cursor.to_list(None)
    
    res = []
    for d in donors:
        d["id"] = str(d["_id"])
        d["tenant_id"] = str(d["tenant_id"])
        d["branch_id"] = str(d["branch_id"])
        res.append(BloodDonorResponse(**d))
    return res

@router.post("/donors", response_model=BloodDonorResponse)
async def register_donor(payload: BloodDonorCreate, request: Request, current_user: dict = Depends(get_current_user)):
    donors_col = get_blood_donors_collection()
    tenant_id = current_user.get("tenant_id")
    branch_id = get_request_branch_id(request, current_user)
    
    # Generate donor number dynamically
    count = await donors_col.count_documents({"tenant_id": tenant_id})
    donor_number = f"BDN-{count + 1001:04d}"
    
    donor_doc = payload.dict()
    donor_doc.update({
        "donor_number": donor_number,
        "tenant_id": tenant_id,
        "branch_id": branch_id,
        "screening_vitals": None,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    })
    
    res = await donors_col.insert_one(donor_doc)
    donor_doc["id"] = str(res.inserted_id)
    donor_doc["tenant_id"] = str(tenant_id)
    donor_doc["branch_id"] = str(branch_id)
    
    return BloodDonorResponse(**donor_doc)

@router.post("/donors/{id}/screening")
async def record_donor_screening(id: str, payload: DonorScreeningBase, current_user: dict = Depends(get_current_user)):
    donors_col = get_blood_donors_collection()
    tenant_id = current_user.get("tenant_id")
    
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid donor ID format")
        
    donor = await donors_col.find_one({"_id": ObjectId(id), "tenant_id": tenant_id})
    if not donor:
        raise HTTPException(status_code=404, detail="Donor record not found")
        
    await donors_col.update_one(
        {"_id": ObjectId(id)},
        {"$set": {
            "screening_vitals": payload.dict(),
            "updated_at": datetime.utcnow()
        }}
    )
    return {"status": "success", "message": "Donor screening vitals recorded successfully."}

@router.post("/donors/{id}/donate")
async def collect_donation(id: str, payload: BloodDonationCreate, request: Request, current_user: dict = Depends(get_current_user)):
    donors_col = get_blood_donors_collection()
    donations_col = get_blood_donations_collection()
    stock_col = get_blood_stock_collection()
    tenant_id = current_user.get("tenant_id")
    branch_id = get_request_branch_id(request, current_user)
    
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid donor ID format")
        
    donor = await donors_col.find_one({"_id": ObjectId(id), "tenant_id": tenant_id})
    if not donor:
        raise HTTPException(status_code=404, detail="Donor record not found")
        
    if not donor.get("screening_vitals") or not donor["screening_vitals"].get("eligible"):
        raise HTTPException(status_code=400, detail="Donor screening pending or ineligible for donation")
        
    # Generate unique bag ID
    don_count = await donations_col.count_documents({"tenant_id": tenant_id})
    bag_number = f"BAG-{don_count + 10001:05d}"
    
    donation_doc = {
        "donor_id": ObjectId(id),
        "bag_number": bag_number,
        "volume_ml": payload.volume_ml,
        "collection_date": payload.collection_date or datetime.utcnow(),
        "technician": payload.technician,
        "testing_status": "pending",
        "testing_results": None,
        "tenant_id": tenant_id,
        "branch_id": branch_id
    }
    
    # Auto compute standard 35 days expiry date for whole blood / packed red cells
    expiry_date = (donation_doc["collection_date"] + timedelta(days=35))
    
    stock_doc = {
        "bag_number": bag_number,
        "blood_group": donor["blood_group"],
        "component_type": "Whole Blood",  # Default component
        "volume_ml": payload.volume_ml,
        "donor_id": ObjectId(id),
        "status": "testing_pending",
        "expiry_date": expiry_date,
        "tenant_id": tenant_id,
        "branch_id": branch_id,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    await donations_col.insert_one(donation_doc)
    await stock_col.insert_one(stock_doc)
    
    return {
        "status": "success",
        "bag_number": bag_number,
        "message": f"Blood bag {bag_number} registered successfully and routed to infectious testing laboratory."
    }

@router.post("/donations/{bag_number}/testing")
async def log_testing_outcome(bag_number: str, payload: LabTestingUpdate, request: Request, current_user: dict = Depends(get_current_user)):
    donations_col = get_blood_donations_collection()
    stock_col = get_blood_stock_collection()
    tenant_id = current_user.get("tenant_id")
    branch_id = get_request_branch_id(request, current_user)
    
    donation = await donations_col.find_one({"bag_number": bag_number, "tenant_id": tenant_id})
    if not donation:
        raise HTTPException(status_code=404, detail="Donation record not found")
        
    results = payload.dict()
    is_reactive = any(
        val == "Reactive" for val in [
            payload.hiv_status,
            payload.hepb_status,
            payload.hepc_status,
            payload.syphilis_status,
            payload.malaria_status
        ]
    )
    
    testing_status = "reactive" if is_reactive else "approved"
    bag_status = "discarded" if is_reactive else "available"
    discard_reason = "infectious testing positive" if is_reactive else None
    
    # Update donation
    await donations_col.update_one(
        {"_id": donation["_id"]},
        {"$set": {
            "testing_status": testing_status,
            "testing_results": results
        }}
    )
    
    # Update stock bag
    await stock_col.update_one(
        {"bag_number": bag_number, "tenant_id": tenant_id},
        {"$set": {
            "status": bag_status,
            "discard_reason": discard_reason,
            "updated_at": datetime.utcnow()
        }}
    )
    
    return {
        "status": "success",
        "testing_status": testing_status,
        "message": f"Infectious tests verified. Blood bag {bag_number} is now {bag_status}."
    }

# ------------------------------------------------------------------
# REQUISITIONS & TRANSFUSION ENDPOINTS
# ------------------------------------------------------------------
@router.get("/requisitions", response_model=List[BloodRequisitionResponse])
async def list_requisitions(request: Request, current_user: dict = Depends(get_current_user)):
    req_col = get_blood_requisitions_collection()
    tenant_id = current_user.get("tenant_id")
    branch_id = get_request_branch_id(request, current_user)
    
    cursor = req_col.find({"tenant_id": tenant_id, "branch_id": branch_id})
    reqs = await cursor.to_list(None)
    
    res = []
    for r in reqs:
        r["id"] = str(r["_id"])
        r["patient_id"] = str(r["patient_id"])
        r["tenant_id"] = str(r["tenant_id"])
        r["branch_id"] = str(r["branch_id"])
        res.append(BloodRequisitionResponse(**r))
    return res

@router.post("/requisitions", response_model=BloodRequisitionResponse)
async def create_requisition(payload: BloodRequisitionCreate, request: Request, current_user: dict = Depends(get_current_user)):
    req_col = get_blood_requisitions_collection()
    pat_col = get_patients_collection()
    tenant_id = current_user.get("tenant_id")
    branch_id = get_request_branch_id(request, current_user)
    
    if not ObjectId.is_valid(payload.patient_id):
        raise HTTPException(status_code=400, detail="Invalid Patient ID format")
        
    patient = await pat_col.find_one({"_id": ObjectId(payload.patient_id), "tenant_id": tenant_id})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
        
    count = await req_col.count_documents({"tenant_id": tenant_id})
    request_number = f"BRQ-{count + 1001:04d}"
    
    req_doc = payload.dict()
    req_doc.update({
        "request_number": request_number,
        "patient_name": f"{patient['first_name']} {patient['last_name']}",
        "status": "pending",
        "allocated_bags": [],
        "tenant_id": tenant_id,
        "branch_id": branch_id,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    })
    
    res = await req_col.insert_one(req_doc)
    req_doc["id"] = str(res.inserted_id)
    req_doc["patient_id"] = str(payload.patient_id)
    req_doc["tenant_id"] = str(tenant_id)
    req_doc["branch_id"] = str(branch_id)
    
    return BloodRequisitionResponse(**req_doc)

@router.post("/requisitions/{id}/crossmatch")
async def crossmatch_requisition(id: str, payload: BloodCrossmatchCreate, current_user: dict = Depends(get_current_user)):
    req_col = get_blood_requisitions_collection()
    stock_col = get_blood_stock_collection()
    tenant_id = current_user.get("tenant_id")
    
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid Requisition ID format")
        
    req = await req_col.find_one({"_id": ObjectId(id), "tenant_id": tenant_id})
    if not req:
        raise HTTPException(status_code=404, detail="Requisition not found")
        
    bag = await stock_col.find_one({"bag_number": payload.bag_number, "tenant_id": tenant_id})
    if not bag:
        raise HTTPException(status_code=404, detail="Blood bag not found in inventory")
        
    if bag["status"] != "available":
        raise HTTPException(status_code=400, detail=f"Blood bag is currently in status: {bag['status']}")
        
    # Validate type compatibility
    compatible = check_compatibility(bag["blood_group"], req["blood_group"])
    if not compatible:
        raise HTTPException(
            status_code=400,
            detail=f"Incompatible crossmatch! Donor group {bag['blood_group']} cannot be given to Recipient group {req['blood_group']}."
        )
        
    # Allocate bag
    await stock_col.update_one(
        {"_id": bag["_id"]},
        {"$set": {"status": "allocated", "updated_at": datetime.utcnow()}}
    )
    
    await req_col.update_one(
        {"_id": ObjectId(id)},
        {
            "$addToSet": {"allocated_bags": payload.bag_number},
            "$set": {"status": "crossmatched", "updated_at": datetime.utcnow()}
        }
    )
    
    return {"status": "success", "message": f"Bag {payload.bag_number} crossmatched and allocated for request {req['request_number']}."}

@router.post("/requisitions/{id}/transfuse")
async def record_transfusion(id: str, payload: BloodTransfusionCreate, request: Request, current_user: dict = Depends(get_current_user)):
    req_col = get_blood_requisitions_collection()
    stock_col = get_blood_stock_collection()
    trans_col = get_blood_transfusions_collection()
    tenant_id = current_user.get("tenant_id")
    branch_id = get_request_branch_id(request, current_user)
    
    if not ObjectId.is_valid(id):
        raise HTTPException(status_code=400, detail="Invalid Requisition ID format")
        
    req = await req_col.find_one({"_id": ObjectId(id), "tenant_id": tenant_id})
    if not req:
        raise HTTPException(status_code=404, detail="Requisition not found")
        
    bag = await stock_col.find_one({"bag_number": payload.bag_number, "tenant_id": tenant_id})
    if not bag or bag["status"] != "allocated":
        raise HTTPException(status_code=400, detail="Blood bag is not allocated or not found")
        
    trans_doc = payload.dict()
    trans_doc.update({
        "requisition_id": ObjectId(id),
        "patient_id": ObjectId(req["patient_id"]),
        "tenant_id": tenant_id,
        "branch_id": branch_id,
        "created_at": datetime.utcnow()
    })
    
    await trans_col.insert_one(trans_doc)
    
    # Update bag status to transfused
    await stock_col.update_one(
        {"_id": bag["_id"]},
        {"$set": {"status": "transfused", "updated_at": datetime.utcnow()}}
    )
    
    # Update Requisition status to transfused
    await req_col.update_one(
        {"_id": ObjectId(id)},
        {"$set": {"status": "transfused", "updated_at": datetime.utcnow()}}
    )
    
    return {"status": "success", "message": f"Transfusion of bag {payload.bag_number} recorded successfully."}
