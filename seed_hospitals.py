import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from config import settings

async def seed_test_hospital():
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client.hmis_db
    
    # Check if tenants exist
    tenants = db.tenants
    count = await tenants.count_documents({})
    print(f"Existing tenants: {count}")
    
    if count == 0:
        # Insert test hospital/tenant
        tenant = {
            "name": "City Hospital",
            "subdomain": "city-hospital",
            "status": "active",
            "subscription_plan": "standard_plan",
            "created_at": "2024-01-01"
        }
        result = await tenants.insert_one(tenant)
        tenant_id = result.inserted_id
        print(f"✓ Created tenant: {tenant}")
        
        # Create branches
        branches = db.branches
        branch = {
            "tenant_id": tenant_id,
            "name": "Main Campus",
            "code": "MAIN",
            "address": "123 Hospital Road",
            "city": "Mumbai",
            "state": "Maharashtra"
        }
        await branches.insert_one(branch)
        print(f"✓ Created branch: {branch}")
    else:
        print("✓ Tenants already exist in database")
    
    client.close()

asyncio.run(seed_test_hospital())
print("✓ Database seeding complete!")
