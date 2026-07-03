from fastapi import APIRouter, Depends, HTTPException, status, Request
from bson import ObjectId
from datetime import datetime
from typing import List, Optional

from database import (
    get_db,
    get_tpa_providers_collection,
    get_patient_policies_collection,
    get_insurance_claims_collection,
    get_patients_collection,
    get_invoices_collection
)
from middleware.auth import (
    get_current_user,
    get_tenant_filter,
    get_branch_filter,
    inject_audit_fields
)
from middleware.audit import create_audit_log
from models.tpa import (
    TPAProviderCreate,
    TPAProviderResponse,
    PatientPolicyCreate,
    PatientPolicyResponse,
    InsuranceClaimCreate,
    InsuranceClaimResponse
)

router = APIRouter()

@router.post("/providers", response_model=TPAProviderResponse)
async def create_tpa_provider(
    payload: TPAProviderCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    col = get_tpa_providers_collection()
    
    # Check duplicate code
    existing = await col.find_one({"code": payload.code.upper(), "tenant_id": current_user["tenant_id"]})
    if existing:
        raise HTTPException(status_code=400, detail="TPA provider code already registered")
        
    doc = payload.dict()
    doc["code"] = payload.code.upper()
    inject_audit_fields(current_user, doc)
    
    res = await col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="TPA_PROVIDER_CREATED",
        entity="tpa_providers",
        entity_id=doc["id"],
        details={"name": payload.name, "code": doc["code"]},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    return TPAProviderResponse(**doc)

@router.get("/providers", response_model=List[TPAProviderResponse])
async def list_tpa_providers(current_user: dict = Depends(get_current_user)):
    col = get_tpa_providers_collection()
    query = get_tenant_filter(current_user)
    
    docs = await col.find(query).to_list(None)
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        result.append(TPAProviderResponse(**doc))
    return result

@router.post("/policies", response_model=PatientPolicyResponse)
async def create_patient_policy(
    payload: PatientPolicyCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    col = get_patient_policies_collection()
    patients_col = get_patients_collection()
    
    try:
        patient_oid = ObjectId(payload.patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient_id format")
        
    patient = await patients_col.find_one({"_id": patient_oid, "tenant_id": current_user["tenant_id"]})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient profile not found")
        
    doc = payload.dict()
    doc["patient_id"] = patient_oid
    inject_audit_fields(current_user, doc)
    
    res = await col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["patient_id"] = str(doc["patient_id"])
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="PATIENT_POLICY_REGISTERED",
        entity="patient_policies",
        entity_id=doc["id"],
        details={"insurance_company": payload.insurance_company, "policy_number": payload.policy_number},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    return PatientPolicyResponse(**doc)

@router.get("/policies/patient/{patient_id}", response_model=List[PatientPolicyResponse])
async def list_patient_policies(patient_id: str, current_user: dict = Depends(get_current_user)):
    col = get_patient_policies_collection()
    try:
        patient_oid = ObjectId(patient_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid patient_id format")
        
    query = {"patient_id": patient_oid, "tenant_id": current_user["tenant_id"]}
    docs = await col.find(query).to_list(None)
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["patient_id"] = str(doc["patient_id"])
        result.append(PatientPolicyResponse(**doc))
    return result

@router.post("/claims", response_model=InsuranceClaimResponse)
async def create_claim(
    payload: InsuranceClaimCreate,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    claims_col = get_insurance_claims_collection()
    invoices_col = get_invoices_collection()
    policies_col = get_patient_policies_collection()
    tpas_col = get_tpa_providers_collection()
    
    try:
        invoice_oid = ObjectId(payload.invoice_id)
        policy_oid = ObjectId(payload.policy_id)
        tpa_oid = ObjectId(payload.tpa_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid ID parameter format")
        
    # 1. Verify invoice
    invoice = await invoices_col.find_one({"_id": invoice_oid, "tenant_id": current_user["tenant_id"]})
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice record not found")
        
    # 2. Verify policy
    policy = await policies_col.find_one({"_id": policy_oid, "tenant_id": current_user["tenant_id"]})
    if not policy:
        raise HTTPException(status_code=404, detail="Patient policy card not found")
        
    # 3. Verify TPA
    tpa = await tpas_col.find_one({"_id": tpa_oid, "tenant_id": current_user["tenant_id"]})
    if not tpa:
        raise HTTPException(status_code=404, detail="TPA provider not found")
        
    # Verify duplicate claims
    existing = await claims_col.find_one({"invoice_id": invoice_oid, "tenant_id": current_user["tenant_id"]})
    if existing:
        raise HTTPException(status_code=400, detail="Insurance claim already exists for this invoice")
        
    doc = {
        "invoice_id": invoice_oid,
        "policy_id": policy_oid,
        "tpa_id": tpa_oid,
        "pre_auth_amount": payload.pre_auth_amount,
        "approved_amount": 0.0,
        "co_pay_amount": invoice["grand_total"],
        "status": "pre_auth_pending"
    }
    inject_audit_fields(current_user, doc)
    
    res = await claims_col.insert_one(doc)
    doc["id"] = str(res.inserted_id)
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    doc["invoice_id"] = str(doc["invoice_id"])
    doc["policy_id"] = str(doc["policy_id"])
    doc["tpa_id"] = str(doc["tpa_id"])
    doc["tpa_name"] = tpa["name"]
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="INSURANCE_CLAIM_SUBMITTED",
        entity="insurance_claims",
        entity_id=doc["id"],
        details={"invoice_id": payload.invoice_id, "pre_auth_amount": payload.pre_auth_amount},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    return InsuranceClaimResponse(**doc)

@router.put("/claims/{id}/approve", response_model=InsuranceClaimResponse)
async def approve_claim(
    id: str,
    payload: dict,
    request: Request,
    current_user: dict = Depends(get_current_user)
):
    claims_col = get_insurance_claims_collection()
    invoices_col = get_invoices_collection()
    tpas_col = get_tpa_providers_collection()
    
    try:
        claim_oid = ObjectId(id)
    except:
        raise HTTPException(status_code=400, detail="Invalid claim ID format")
        
    claim = await claims_col.find_one({"_id": claim_oid, "tenant_id": current_user["tenant_id"]})
    if not claim:
        raise HTTPException(status_code=404, detail="Insurance claim record not found")
        
    approved_amt = float(payload.get("approved_amount", 0.0))
    if approved_amt <= 0:
        raise HTTPException(status_code=400, detail="approved_amount must be greater than 0")
        
    invoice = await invoices_col.find_one({"_id": claim["invoice_id"]})
    if not invoice:
        raise HTTPException(status_code=404, detail="Associated invoice not found")
        
    # Calculate Co-Pay: grand_total - approved_amount (ensure co-pay >= 0)
    co_pay = max(0.0, round(invoice["grand_total"] - approved_amt, 2))
    
    # Update claim status
    now = datetime.utcnow()
    await claims_col.update_one(
        {"_id": claim_oid},
        {"$set": {
            "status": "approved",
            "approved_amount": approved_amt,
            "co_pay_amount": co_pay,
            "updated_at": now,
            "updated_by": str(current_user["_id"])
        }}
    )
    
    # Update the linked invoice's grand_total to the co-pay amount (or keep reference and deduct due balance)
    # To maintain consistency, we will deduct due balance by updating billing payments logs, or adjust total
    # Let's adjust invoice due state by logging the approved_amount as a special Payment with method "Insurance"
    payments_col = get_db().payments
    ins_pay_entry = {
        "tenant_id": current_user["tenant_id"],
        "branch_id": current_user["branch_id"],
        "invoice_id": claim["invoice_id"],
        "payment_method": "Insurance",
        "amount_paid": approved_amt,
        "transaction_reference": f"Claim Approved ID: {id}",
        "created_at": now,
        "created_by": str(current_user["_id"])
    }
    await payments_col.insert_one(ins_pay_entry)
    
    # Check if co_pay is 0, then update invoice to paid, else update to due
    new_status = "paid" if co_pay == 0.0 else "due"
    await invoices_col.update_one(
        {"_id": claim["invoice_id"]},
        {"$set": {"payment_status": new_status, "updated_at": now, "updated_by": str(current_user["_id"])}}
    )
    
    tpa = await tpas_col.find_one({"_id": claim["tpa_id"]})
    
    await create_audit_log(
        user_id=str(current_user["_id"]),
        user_name=current_user["name"],
        action="INSURANCE_CLAIM_APPROVED",
        entity="insurance_claims",
        entity_id=id,
        details={"approved_amount": approved_amt, "co_pay_amount": co_pay},
        ip_address=request.client.host if request.client else None,
        tenant_id=current_user["tenant_id"],
        branch_id=current_user["branch_id"]
    )
    
    claim["status"] = "approved"
    claim["approved_amount"] = approved_amt
    claim["co_pay_amount"] = co_pay
    claim["id"] = str(claim["_id"])
    claim["tenant_id"] = str(claim["tenant_id"])
    claim["branch_id"] = str(claim["branch_id"])
    claim["invoice_id"] = str(claim["invoice_id"])
    claim["policy_id"] = str(claim["policy_id"])
    claim["tpa_id"] = str(claim["tpa_id"])
    claim["tpa_name"] = tpa["name"] if tpa else "TPA"
    return InsuranceClaimResponse(**claim)

@router.get("/claims", response_model=List[InsuranceClaimResponse])
async def list_claims(current_user: dict = Depends(get_current_user)):
    col = get_insurance_claims_collection()
    tpas_col = get_tpa_providers_collection()
    
    query = get_branch_filter(current_user)
    docs = await col.find(query).sort("created_at", -1).to_list(None)
    result = []
    for doc in docs:
        doc["id"] = str(doc["_id"])
        doc["tenant_id"] = str(doc["tenant_id"])
        doc["branch_id"] = str(doc["branch_id"])
        doc["invoice_id"] = str(doc["invoice_id"])
        doc["policy_id"] = str(doc["policy_id"])
        doc["tpa_id"] = str(doc["tpa_id"])
        
        tpa = await tpas_col.find_one({"_id": ObjectId(doc["tpa_id"])})
        doc["tpa_name"] = tpa["name"] if tpa else "TPA"
        result.append(InsuranceClaimResponse(**doc))
    return result

@router.get("/claims/invoice/{invoice_id}", response_model=InsuranceClaimResponse)
async def get_claim_by_invoice(invoice_id: str, current_user: dict = Depends(get_current_user)):
    col = get_insurance_claims_collection()
    tpas_col = get_tpa_providers_collection()
    
    try:
        invoice_oid = ObjectId(invoice_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid invoice_id format")
        
    doc = await col.find_one({"invoice_id": invoice_oid, "tenant_id": current_user["tenant_id"]})
    if not doc:
        raise HTTPException(status_code=404, detail="No claim logs found for this invoice")
        
    doc["id"] = str(doc["_id"])
    doc["tenant_id"] = str(doc["tenant_id"])
    doc["branch_id"] = str(doc["branch_id"])
    doc["invoice_id"] = str(doc["invoice_id"])
    doc["policy_id"] = str(doc["policy_id"])
    doc["tpa_id"] = str(doc["tpa_id"])
    
    tpa = await tpas_col.find_one({"_id": ObjectId(doc["tpa_id"])})
    doc["tpa_name"] = tpa["name"] if tpa else "TPA"
    return InsuranceClaimResponse(**doc)
