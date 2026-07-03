import asyncio
import sys
import os

# Ensure backend directory is in path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(backend_dir)

# Load environment variables from backend/.env explicitly before importing settings
from dotenv import load_dotenv
load_dotenv(os.path.join(backend_dir, '.env'))

from main import app
import database
from config import settings
from httpx import AsyncClient, ASGITransport
from datetime import datetime
from middleware.auth import get_password_hash

async def run_integration_tests():
    print("Starting SaaS Integration Tests...", flush=True)
    
    # Use real Atlas MongoDB URI but with a separate runner database
    print(f"Connecting to MongoDB database 'hmis_test_runner' on Atlas...", flush=True)
    from motor.motor_asyncio import AsyncIOMotorClient
    test_client = AsyncIOMotorClient(settings.MONGODB_URI)
    
    # Drop database first to guarantee clean state
    print("Cleaning database...", flush=True)
    await test_client.drop_database("hmis_test_runner")
    
    test_database = test_client.get_database("hmis_test_runner")
    
    # Save original database configurations
    orig_client = database.client
    orig_database = database.database
    
    database.client = test_client
    database.database = test_database
    
    # Initialize indexes
    print("Initializing indexes...", flush=True)
    await database.create_indexes()
    
    # Seeding
    print("Seeding SaaS plans...", flush=True)
    from database import seed_saas_plans
    await seed_saas_plans()
    
    # Create test tenant, branch, user for authentication testing
    print("Creating test tenant and branch...", flush=True)
    tenant_doc = {
        "name": "Test Hospital SaaS Inc",
        "subdomain": "saastest",
        "contact_email": "admin@saastest.com",
        "status": "active",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    tenant_res = await test_database.tenants.insert_one(tenant_doc)
    tenant_id = tenant_res.inserted_id
    
    branch_doc = {
        "name": "Test Branch Delhi",
        "code": "TBD",
        "address": "Delhi Test Road 42",
        "contact_number": "9876543210",
        "tenant_id": tenant_id,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    branch_res = await test_database.branches.insert_one(branch_doc)
    branch_id = branch_res.inserted_id
    
    print("Creating test staff user...", flush=True)
    user_doc = {
        "name": "Dr. Test Doctor",
        "email": "doctor@saastest.com",
        "password_hash": get_password_hash("password123"),
        "role": "doctor",
        "tenant_id": tenant_id,
        "branch_id": branch_id,
        "status": "active",
        "is_active": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    user_res = await test_database.users.insert_one(user_doc)
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # A. Test SaaS Plans listing
        print("Testing: GET /api/saas/plans...", flush=True)
        response = await client.get("/api/saas/plans")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        plans = response.json()
        assert len(plans) >= 4, f"Expected at least 4 plans, got {len(plans)}"
        print("[PASS] SaaS Plans listing passed!", flush=True)
        
        # B. Test Login to get authentication token
        print("Testing: User Login...", flush=True)
        login_payload = {
            "email": "doctor@saastest.com",
            "password": "password123"
        }
        login_res = await client.post("/api/auth/login", json=login_payload)
        assert login_res.status_code == 200, f"Expected 200, got {login_res.status_code}"
        tokens = login_res.json()
        access_token = tokens["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        print("[PASS] Login passed!", flush=True)
        
        # C. Test SaaS Subscription Status
        print("Testing: GET /api/saas/subscription/status...", flush=True)
        status_res = await client.get("/api/saas/subscription/status", headers=headers)
        assert status_res.status_code == 200, f"Expected 200, got {status_res.status_code}"
        status_data = status_res.json()
        assert "subscription" in status_data, "Subscription details missing in response"
        assert "limits" in status_data, "Limits details missing in response"
        print("[PASS] SaaS Subscription Status passed!", flush=True)
        
    # Clean up test database
    print("Dropping test runner database...", flush=True)
    await test_client.drop_database("hmis_test_runner")
    test_client.close()
    
    # Restore original database config
    database.client = orig_client
    database.database = orig_database
    
    print("\nAll SaaS integration tests completed successfully!", flush=True)

if __name__ == "__main__":
    asyncio.run(run_integration_tests())
