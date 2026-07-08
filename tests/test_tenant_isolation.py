import pytest
from httpx import AsyncClient
from bson import ObjectId
from datetime import datetime
from middleware.auth import get_password_hash

@pytest.fixture
async def mock_second_tenant(test_db):
    tenant_col = test_db.tenants
    tenant_doc = {
        "name": "Second Hospital Group",
        "subdomain": "secondgroup",
        "contact_email": "admin@secondgroup.com",
        "status": "active",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    res = await tenant_col.insert_one(tenant_doc)
    tenant_doc["_id"] = res.inserted_id
    yield tenant_doc
    await tenant_col.delete_one({"_id": res.inserted_id})

@pytest.fixture
async def mock_second_branch(test_db, mock_second_tenant):
    branch_col = test_db.branches
    branch_doc = {
        "name": "Second Branch Delhi",
        "code": "SBD",
        "address": "Delhi Test Road 84",
        "contact_number": "9876543211",
        "tenant_id": mock_second_tenant["_id"],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    res = await branch_col.insert_one(branch_doc)
    branch_doc["_id"] = res.inserted_id
    yield branch_doc
    await branch_col.delete_one({"_id": res.inserted_id})

@pytest.fixture
async def mock_second_staff(test_db, mock_second_tenant, mock_second_branch):
    users_col = test_db.users
    user_doc = {
        "name": "Dr. Second Doctor",
        "email": "doctor@secondgroup.com",
        "password_hash": get_password_hash("password123"),
        "role": "receptionist",
        "is_active": True,
        "tenant_id": mock_second_tenant["_id"],
        "branch_id": mock_second_branch["_id"],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    res = await users_col.insert_one(user_doc)
    user_doc["_id"] = res.inserted_id
    yield user_doc
    await users_col.delete_one({"_id": res.inserted_id})

@pytest.mark.asyncio
async def test_tenant_isolation_enforcement(client: AsyncClient, mock_staff, mock_second_staff, auth_headers):
    headers_a = auth_headers(mock_staff)
    headers_b = auth_headers(mock_second_staff)
    
    # 1. Create Patient on Tenant A
    patient_payload = {
        "first_name": "Alice",
        "last_name": "TenantA",
        "phone": "9876543211",
        "email": "alice@tenant-a.com",
        "dob": "1995-05-15T00:00:00Z",
        "gender": "Female",
        "blood_group": "A+",
        "address": "456 Test Blvd, Tenant A",
        "emergency_contact_name": "Bob Smith",
        "emergency_contact_phone": "9876543212"
    }
    
    response_create = await client.post("/api/patients", json=patient_payload, headers=headers_a)
    assert response_create.status_code == 200
    patient_a_id = response_create.json()["id"]
    
    # 2. Retrieve patients list from Tenant A -> Should contain Alice
    response_list_a = await client.get("/api/patients", headers=headers_a)
    assert response_list_a.status_code == 200
    patients_a = response_list_a.json()
    assert any(p["id"] == patient_a_id for p in patients_a)
    
    # 3. Retrieve patients list from Tenant B -> Should NOT contain Alice
    response_list_b = await client.get("/api/patients", headers=headers_b)
    assert response_list_b.status_code == 200
    patients_b = response_list_b.json()
    assert not any(p["id"] == patient_a_id for p in patients_b)
    
    # 4. Direct GET request to patient A detail using Tenant B authorization should fail / return 404
    response_detail_b = await client.get(f"/api/patients/{patient_a_id}", headers=headers_b)
    assert response_detail_b.status_code == 404
