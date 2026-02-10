import uuid
import pytest
from httpx import AsyncClient


async def create_account(client: AsyncClient, headers):
    payload = {
        "name": f"Test Account {uuid.uuid4().hex[:6]}",
        "provider": "csv",
        "currency": "UZS",
    }
    response = await client.post("/accounts", json=payload, headers=headers)
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_create_account(client: AsyncClient, auth_headers_user):
    account = await create_account(client, auth_headers_user)
    assert account["name"].startswith("Test Account")
    assert account["provider"] == "csv"
    assert "id" in account


@pytest.mark.asyncio
async def test_get_accounts(client: AsyncClient, auth_headers_user):
    created = await create_account(client, auth_headers_user)
    response = await client.get("/accounts", headers=auth_headers_user)

    assert response.status_code == 200
    accounts = response.json()
    assert any(acc["id"] == created["id"] for acc in accounts)


@pytest.mark.asyncio
async def test_update_account(client: AsyncClient, auth_headers_user):
    created = await create_account(client, auth_headers_user)
    update_payload = {"name": "Updated Account", "currency": "USD"}
    response = await client.patch(
        f"/accounts/{created['id']}", json=update_payload, headers=auth_headers_user
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["name"] == "Updated Account"
    assert updated["currency"] == "USD"


@pytest.mark.asyncio
async def test_delete_account(client: AsyncClient, auth_headers_user):
    created = await create_account(client, auth_headers_user)
    response = await client.delete(
        f"/accounts/{created['id']}", headers=auth_headers_user
    )

    assert response.status_code == 200
    list_response = await client.get("/accounts", headers=auth_headers_user)
    accounts = list_response.json()
    assert not any(acc["id"] == created["id"] for acc in accounts)
