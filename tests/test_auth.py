import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, mock_staff):
    # Try logging in with the correct credentials
    login_data = {
        "email": mock_staff["email"],
        "password": "password123"
    }
    
    response = await client.post("/api/auth/login", json=login_data)
    assert response.status_code == 200
    
    res_json = response.json()
    assert "access_token" in res_json
    assert "refresh_token" in res_json
    assert res_json["user"]["email"] == mock_staff["email"]

@pytest.mark.asyncio
async def test_login_invalid_password(client: AsyncClient, mock_staff):
    # Try logging in with incorrect password
    login_data = {
        "email": mock_staff["email"],
        "password": "wrongpassword"
    }
    
    response = await client.post("/api/auth/login", json=login_data)
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"
