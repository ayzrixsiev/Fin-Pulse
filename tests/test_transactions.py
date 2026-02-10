import uuid
import pytest
from httpx import AsyncClient


async def create_account(client: AsyncClient, headers):
    payload = {
        "name": f"Txn Account {uuid.uuid4().hex[:6]}",
        "provider": "csv",
        "currency": "UZS",
    }
    response = await client.post("/accounts", json=payload, headers=headers)
    assert response.status_code == 201
    return response.json()


@pytest.mark.asyncio
async def test_create_transaction(client: AsyncClient, auth_headers_user):
    account = await create_account(client, auth_headers_user)
    payload = {
        "amount": -15000,
        "currency": "UZS",
        "merchant": "Test Merchant",
        "category": "Food & Restaurants",
        "description": "Lunch",
        "account_id": account["id"],
    }
    response = await client.post("/transactions", json=payload, headers=auth_headers_user)

    assert response.status_code == 201
    data = response.json()
    assert float(data["amount"]) == float(payload["amount"])
    assert data["processed"] is False
    assert data["account_id"] == account["id"]


@pytest.mark.asyncio
async def test_get_raw_transactions(client: AsyncClient, auth_headers_user):
    account = await create_account(client, auth_headers_user)
    for _ in range(2):
        payload = {
            "amount": -5000,
            "currency": "UZS",
            "merchant": f"Merchant {uuid.uuid4().hex[:6]}",
            "category": "Shopping & Retail",
            "description": "Test purchase",
            "account_id": account["id"],
        }
        await client.post("/transactions", json=payload, headers=auth_headers_user)

    response = await client.get("/transactions/raw", headers=auth_headers_user)
    assert response.status_code == 200
    txs = response.json()
    assert len(txs) >= 2


@pytest.mark.asyncio
async def test_upload_csv(client: AsyncClient, auth_headers_user):
    today = "2026-02-10"
    unique = uuid.uuid4().hex[:6]
    csv_data = (
        "date,amount,merchant,category,description\n"
        f"{today},-10000,CSV Merchant {unique},Food & Restaurants,Test\n"
    )
    files = {"file": ("transactions.csv", csv_data, "text/csv")}

    response = await client.post(
        "/transactions/upload-csv", files=files, headers=auth_headers_user
    )
    assert response.status_code == 200
    assert response.json()["inserted"] >= 1
