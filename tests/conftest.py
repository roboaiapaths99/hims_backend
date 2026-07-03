import pytest
import asyncio
from datetime import datetime
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

import sys
import os
# Ensure backend directory is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
import database

@pytest.fixture(scope="session")
def event_loop():
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session", autouse=True)
async def test_db():
    from config import settings
    # Override database variables in database.py module
    test_client = AsyncIOMotorClient(settings.MONGODB_URI)
    test_database = test_client.get_database("hmis_test_db")
    
    # Save original database config to restore if needed
    orig_client = database.client
    orig_database = database.database
    
    database.client = test_client
    database.database = test_database
    
    # Auto-initialize indexes
    await database.create_indexes()
    
    # Seed SaaS plans
    await database.seed_saas_plans()
    
    yield test_database
    
    # Tear down
    await test_client.drop_database("hmis_test_db")
    test_client.close()
    
    # Restore
    database.client = orig_client
    database.database = orig_database

@pytest.fixture
async def client():
    from httpx import AsyncClient, ASGITransport
    # FastAPI 0.110+ uses ASGITransport for testing
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

@pytest.fixture
async def mock_tenant(test_db):
    tenant_col = test_db.tenants
    tenant_doc = {
        "name": "Test Hospital Group",
        "subdomain": "testgroup",
        "contact_email": "admin@testgroup.com",
        "status": "active",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    res = await tenant_col.insert_one(tenant_doc)
    tenant_doc["_id"] = res.inserted_id
    yield tenant_doc
    await tenant_col.delete_one({"_id": res.inserted_id})

@pytest.fixture
async def mock_branch(test_db, mock_tenant):
    branch_col = test_db.branches
    branch_doc = {
        "name": "Test Branch Delhi",
        "code": "TBD",
        "address": "Delhi Test Road 42",
        "contact_number": "9876543210",
        "tenant_id": mock_tenant["_id"],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    res = await branch_col.insert_one(branch_doc)
    branch_doc["_id"] = res.inserted_id
    yield branch_doc
    await branch_col.delete_one({"_id": res.inserted_id})

@pytest.fixture
async def mock_staff(test_db, mock_tenant, mock_branch):
    from middleware.auth import get_password_hash
    users_col = test_db.users
    user_doc = {
        "name": "Dr. Test Doctor",
        "email": "doctor@testgroup.com",
        "password_hash": get_password_hash("password123"),
        "role": "receptionist",
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
def auth_headers():
    from middleware.auth import create_access_token
    def _auth_headers(user):
        token = create_access_token({
            "sub": str(user["_id"]),
            "role": user["role"],
            "tenant_id": str(user["tenant_id"]),
            "branch_id": str(user["branch_id"])
        })
        return {"Authorization": f"Bearer {token}"}
    return _auth_headers
