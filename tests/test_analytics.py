import uuid
import pytest
from datetime import date, timedelta
from httpx import AsyncClient


async def create_account(client: AsyncClient, headers):
    payload = {
        "name": f"Analytics Account {uuid.uuid4().hex[:6]}",
        "provider": "csv",
        "currency": "UZS",
    }
    response = await client.post("/accounts", json=payload, headers=headers)
    assert response.status_code == 201
    return response.json()


async def seed_pipeline_data(client: AsyncClient, headers):
    account = await create_account(client, headers)
    today = date.today().isoformat()
    unique = uuid.uuid4().hex[:6]
    csv_data = (
        "date,amount,merchant,category,description\n"
        f"{today},-15000,Store {unique},Shopping & Retail,Groceries\n"
        f"{today},60000,Employer {unique},Salary & Income,Salary\n"
    )
    files = {"file": ("analytics.csv", csv_data, "text/csv")}
    response = await client.post(
        "/etl/run-csv",
        params={"account_id": account["id"]},
        files=files,
        headers=headers,
    )
    assert response.status_code == 200
    return account["id"]


@pytest.mark.asyncio
async def test_dashboard(client: AsyncClient, auth_headers_user):
    await seed_pipeline_data(client, auth_headers_user)
    response = await client.get("/analytics/dashboard", headers=auth_headers_user)

    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "spending_by_category" in data
    assert "income_breakdown" in data
    assert "monthly_trend" in data
    assert "top_merchants" in data
    assert "budget_recommendations" in data
    assert "insights" in data
    assert "lifetime_summary" in data


@pytest.mark.asyncio
async def test_spending_by_category(client: AsyncClient, auth_headers_user):
    await seed_pipeline_data(client, auth_headers_user)
    start_date = (date.today() - timedelta(days=1)).isoformat()
    end_date = (date.today() + timedelta(days=1)).isoformat()

    response = await client.get(
        "/analytics/spending-by-category",
        params={"start_date": start_date, "end_date": end_date},
        headers=auth_headers_user,
    )

    assert response.status_code == 200
    data = response.json()
    assert "spending_by_category" in data
    assert len(data["spending_by_category"]) >= 1


@pytest.mark.asyncio
async def test_budget_recommendations(client: AsyncClient, auth_headers_user):
    await seed_pipeline_data(client, auth_headers_user)
    response = await client.get(
        "/analytics/budget-recommendations", headers=auth_headers_user
    )

    assert response.status_code == 200
    data = response.json()
    assert "budget_recommendations" in data


@pytest.mark.asyncio
async def test_user_stats(client: AsyncClient, auth_headers_user):
    await seed_pipeline_data(client, auth_headers_user)
    response = await client.get("/analytics/user-stats", headers=auth_headers_user)

    assert response.status_code == 200
    data = response.json()
    assert data["total_transactions"] >= 1
    assert data["total_income"] >= 0
    assert data["total_expense"] >= 0


@pytest.mark.asyncio
async def test_account_summary(client: AsyncClient, auth_headers_user):
    account_id = await seed_pipeline_data(client, auth_headers_user)
    response = await client.get("/analytics/account-summary", headers=auth_headers_user)

    assert response.status_code == 200
    summaries = response.json()
    assert any(summary["account_id"] == account_id for summary in summaries)
