import uuid
import pytest
from datetime import date
from httpx import AsyncClient


async def create_account(client: AsyncClient, headers):
    payload = {
        "name": f"ETL Account {uuid.uuid4().hex[:6]}",
        "provider": "csv",
        "currency": "UZS",
    }
    response = await client.post("/accounts", json=payload, headers=headers)
    assert response.status_code == 201
    return response.json()


def build_csv_payload() -> str:
    today = date.today().isoformat()
    unique = uuid.uuid4().hex[:6]
    return (
        "date,amount,merchant,category,description\n"
        f"{today},-12000,Shop {unique},Shopping & Retail,Test expense\n"
        f"{today},50000,Employer {unique},Salary & Income,Salary\n"
    )


@pytest.mark.asyncio
async def test_run_csv_pipeline(client: AsyncClient, auth_headers_user):
    account = await create_account(client, auth_headers_user)
    csv_data = build_csv_payload()
    files = {"file": ("etl.csv", csv_data, "text/csv")}

    response = await client.post(
        "/etl/run-csv",
        params={"account_id": account["id"]},
        files=files,
        headers=auth_headers_user,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert "step_results" in data
    assert "load" in data["step_results"]
    assert "aggregate" in data["step_results"]


@pytest.mark.asyncio
async def test_transform_load_aggregate_only(client: AsyncClient, auth_headers_user):
    account = await create_account(client, auth_headers_user)
    payload = {
        "amount": -7000,
        "currency": "UZS",
        "merchant": f"Evos {uuid.uuid4().hex[:6]}",
        "description": "Dinner",
        "account_id": account["id"],
    }
    await client.post("/transactions", json=payload, headers=auth_headers_user)

    transform_resp = await client.post("/etl/transform-only", headers=auth_headers_user)
    assert transform_resp.status_code == 200
    assert transform_resp.json()["status"] == "completed"

    load_resp = await client.post("/etl/load-only", headers=auth_headers_user)
    assert load_resp.status_code == 200
    assert load_resp.json()["status"] == "completed"
    assert "user_stats" in load_resp.json()["result"]

    aggregate_resp = await client.post(
        "/etl/aggregate-only", headers=auth_headers_user
    )
    assert aggregate_resp.status_code == 200
    assert aggregate_resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_pipeline_status_flags_unprocessed(client: AsyncClient, auth_headers_user):
    account = await create_account(client, auth_headers_user)
    payload = {
        "amount": -3000,
        "currency": "UZS",
        "merchant": f"Taxi {uuid.uuid4().hex[:6]}",
        "description": "Ride",
        "account_id": account["id"],
    }
    await client.post("/transactions", json=payload, headers=auth_headers_user)

    status_resp = await client.get("/etl/status", headers=auth_headers_user)
    assert status_resp.status_code == 200
    status = status_resp.json()
    assert status["needs_processing"] is True
    assert status["unprocessed_transactions"] >= 1


@pytest.mark.asyncio
async def test_health_check_permissions(
    client: AsyncClient, auth_headers_user, auth_headers_admin
):
    user_resp = await client.get("/etl/health", headers=auth_headers_user)
    assert user_resp.status_code == 403

    admin_resp = await client.get("/etl/health", headers=auth_headers_admin)
    assert admin_resp.status_code == 200
    assert "overall_status" in admin_resp.json()
