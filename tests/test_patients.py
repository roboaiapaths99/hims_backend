import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_create_and_get_patient(client: AsyncClient, mock_staff, auth_headers):
    headers = auth_headers(mock_staff)
    
    # Define new patient payload
    patient_payload = {
        "first_name": "Alice",
        "last_name": "Smith",
        "phone": "9876543211",
        "email": "alice.smith@example.com",
        "dob": "1995-05-15T00:00:00Z",
        "gender": "Female",
        "blood_group": "A+",
        "address": "456 Test Blvd, New Delhi",
        "emergency_contact_name": "Bob Smith",
        "emergency_contact_phone": "9876543212"
    }
    
    # 1. Create Patient
    response = await client.post("/api/patients", json=patient_payload, headers=headers)
    assert response.status_code == 200
    
    patient_json = response.json()
    assert "mrn" in patient_json
    assert patient_json["first_name"] == "Alice"
    assert patient_json["last_name"] == "Smith"
    
    patient_id = patient_json["id"]
    
    # 2. Get list of patients
    get_response = await client.get("/api/patients", headers=headers)
    assert get_response.status_code == 200
    
    patients_list = get_response.json()
    assert len(patients_list) > 0
    assert any(p["id"] == patient_id for p in patients_list)
    
    # 3. Retrieve specific patient detail
    detail_response = await client.get(f"/api/patients/{patient_id}", headers=headers)
    assert detail_response.status_code == 200
    assert detail_response.json()["first_name"] == "Alice"
