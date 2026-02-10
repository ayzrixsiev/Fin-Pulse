import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user):
    """Login returns 200 with access_token for a valid user."""
    login_payload = {"email": test_user.email, "password": "password123"}
    response = await client.post("/profile/login", json=login_payload)

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert isinstance(data["access_token"], str)
    assert len(data["access_token"]) > 20


@pytest.mark.asyncio
async def test_login_invalid_password(client: AsyncClient, test_user):
    """Login returns 401 for an invalid password."""
    login_payload = {"email": test_user.email, "password": "wrongpass"}
    response = await client.post("/profile/login", json=login_payload)

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect password"


@pytest.mark.asyncio
async def test_login_unknown_user(client: AsyncClient):
    """Login returns 404 for a missing user."""
    login_payload = {"email": "missing@example.com", "password": "password123"}
    response = await client.post("/profile/login", json=login_payload)

    assert response.status_code == 404
    assert response.json()["detail"] == "User does not exists"
