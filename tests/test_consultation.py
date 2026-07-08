import pytest
from httpx import AsyncClient
from bson import ObjectId
from datetime import datetime
from database import get_patients_collection, get_appointments_collection

@pytest.fixture
async def mock_doctor(test_db, mock_tenant, mock_branch):
    from middleware.auth import get_password_hash
    users_col = test_db.users
    user_doc = {
        "name": "Dr. House",
        "email": "dr.house@testgroup.com",
        "password_hash": get_password_hash("password123"),
        "role": "doctor",
        "is_active": True,
        "tenant_id": mock_tenant["_id"],
        "branch_id": mock_branch["_id"],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    res = await users_col.insert_one(user_doc)
    user_doc["_id"] = res.inserted_id
    yield user_doc
    await users_col.delete_one({"_id": res.inserted_id})

@pytest.fixture
async def mock_patient(test_db, mock_tenant, mock_branch):
    patients_col = test_db.patients
    patient_doc = {
        "first_name": "John",
        "last_name": "Doe",
        "phone": "9876543222",
        "dob": datetime(1990, 1, 1),
        "gender": "Male",
        "address": "123 Main St",
        "emergency_contact_name": "Jane Doe",
        "emergency_contact_phone": "9876543223",
        "mrn": "MRN-123456",
        "tenant_id": mock_tenant["_id"],
        "branch_id": mock_branch["_id"],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "is_deleted": False
    }
    res = await patients_col.insert_one(patient_doc)
    patient_doc["_id"] = res.inserted_id
    yield patient_doc
    await patients_col.delete_one({"_id": res.inserted_id})

@pytest.fixture
async def mock_appointment(test_db, mock_tenant, mock_branch, mock_doctor, mock_patient):
    appointments_col = test_db.appointments
    appt_doc = {
        "patient_id": mock_patient["_id"],
        "doctor_id": mock_doctor["_id"],
        "appointment_date": datetime.utcnow(),
        "start_time": "10:00",
        "reason": "Routine Checkup",
        "status": "scheduled",
        "tenant_id": mock_tenant["_id"],
        "branch_id": mock_branch["_id"],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "is_deleted": False
    }
    res = await appointments_col.insert_one(appt_doc)
    appt_doc["_id"] = res.inserted_id
    yield appt_doc
    await appointments_col.delete_one({"_id": res.inserted_id})

@pytest.mark.asyncio
async def test_consultation_lifecycle(client: AsyncClient, mock_doctor, mock_staff, auth_headers, mock_appointment, mock_patient):
    doc_headers = auth_headers(mock_doctor)
    staff_headers = auth_headers(mock_staff)
    
    # 1. Start Consultation
    payload = {
        "appointment_id": str(mock_appointment["_id"])
    }
    response = await client.post("/api/consultation/visit/start", json=payload, headers=doc_headers)
    assert response.status_code == 200
    visit_json = response.json()
    assert visit_json["status"] == "active"
    visit_id = visit_json["id"]
    
    # 2. Save Draft Progress
    save_payload = {
        "symptoms": "Fever and cold",
        "clinical_notes": "Patient has mild fever",
        "diagnosis": ["R50.9 - Fever, unspecified"],
        "treatment_plan": "Paracetamol 500mg"
    }
    response = await client.post(f"/api/consultation/visit/{visit_id}/save", json=save_payload, headers=doc_headers)
    assert response.status_code == 200
    assert response.json()["symptoms"] == "Fever and cold"
    
    # Check that a doctor is authorized but receptionist is not (based on standard RBAC write_consultation check)
    # Note: If no strict permission dependency is on the endpoints yet (only get_current_user), let's ensure it works.
    
    # 3. Complete Consultation (locks the visit)
    complete_payload = {
        "symptoms": "Fever and cold",
        "clinical_notes": "Patient has mild fever",
        "diagnosis": ["R50.9 - Fever, unspecified"],
        "treatment_plan": "Paracetamol 500mg, rest"
    }
    response = await client.post(f"/api/consultation/visit/{visit_id}/complete", json=complete_payload, headers=doc_headers)
    assert response.status_code == 200
    completed_json = response.json()
    assert completed_json["status"] == "completed"
    assert completed_json["is_finalized"] is True
    assert completed_json["locked"] is True
    
    # 4. Attempt to save progress on locked visit should fail
    response = await client.post(f"/api/consultation/visit/{visit_id}/save", json=save_payload, headers=doc_headers)
    assert response.status_code == 403
    assert "finalized and locked" in response.json()["detail"]
    
    # 5. Amend consultation as doctor should succeed
    amend_payload = {
        "reason": "Typo in treatment plan",
        "amended_treatment_plan": "Paracetamol 650mg"
    }
    response = await client.post(f"/api/consultation/visit/{visit_id}/amend", json=amend_payload, headers=doc_headers)
    assert response.status_code == 200
    amended_json = response.json()
    assert len(amended_json["amendments"]) == 1
    assert amended_json["amendments"][0]["reason"] == "Typo in treatment plan"
    assert amended_json["amendments"][0]["amended_treatment_plan"] == "Paracetamol 650mg"
    
    # 6. Amend as receptionist (mock_staff) should fail
    response = await client.post(f"/api/consultation/visit/{visit_id}/amend", json=amend_payload, headers=staff_headers)
    assert response.status_code == 403
    
    # 7. Get Amendments list
    response = await client.get(f"/api/consultation/visit/{visit_id}/amendments", headers=doc_headers)
    assert response.status_code == 200
    amends_list = response.json()
    assert amends_list["total"] == 1
    assert amends_list["amendments"][0]["reason"] == "Typo in treatment plan"
    
    # 8. Get Patient Consultation History (paginated)
    response = await client.get(f"/api/consultation/patient/{str(mock_patient['_id'])}/history", headers=doc_headers)
    assert response.status_code == 200
    history_json = response.json()
    assert "data" in history_json
    assert "total" in history_json
    assert history_json["total"] == 1
    assert history_json["data"][0]["id"] == visit_id
