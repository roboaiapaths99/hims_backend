import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_get_saas_plans(client: AsyncClient):
    # Verify that saas plans endpoint lists all seeded plans
    response = await client.get("/api/saas/plans")
    assert response.status_code == 200
    
    plans = response.json()
    assert len(plans) >= 4
    assert any(p["plan_id"] == "free_trial" for p in plans)
    assert any(p["plan_id"] == "premium_plan" for p in plans)

@pytest.mark.asyncio
async def test_get_subscription_status(client: AsyncClient, mock_staff, auth_headers):
    # Verify that subscription status endpoint returns limits and usage details
    headers = auth_headers(mock_staff)
    response = await client.get("/api/saas/subscription/status", headers=headers)
    assert response.status_code == 200
    
    data = response.json()
    assert "tenant_id" in data
    assert "subscription" in data
    assert "limits" in data
    assert "usage" in data
