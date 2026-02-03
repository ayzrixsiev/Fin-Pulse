import csv
import io
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from app.core import models


# Decode, clean empty rows, make dict - CSV
def read_csv_file(file_bytes: bytes) -> list[dict]:
    try:
        text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = file_bytes.decode("windows-1251")

    reader = csv.DictReader(io.StringIO(text))
    rows = [row for row in reader if any(row.values())]
    return rows


# Fetch, normalize data into JSON from dict[list] - API
def normalize_api_response(data: Any) -> list[dict]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return (
            data.get("data")
            or data.get("transactions")
            or data.get("result", {}).get("transactions")
            or []
        )
    raise ValueError(f"Unexpected API response type: {type(data)}")


async def fetch_from_api(
    url: str, headers: dict, params: Optional[Dict[str, Any]] = None
) -> list[dict]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        data: Any = response.json()

        return normalize_api_response(data)


# Fetch data from Uzum
def uzum_webhook_to_standard(payload: dict, event_type: str) -> dict:
    ts_ms = (
        payload.get("timestamp")
        or payload.get("transTime")
        or payload.get("confirmTime")
    )
    date = datetime.fromtimestamp(ts_ms / 1000).isoformat() if ts_ms else None

    return {
        "date": date,
        "amount": payload.get("amount"),
        "merchant": "Uzum Bank",
        "category": None,
        "description": f"Uzum webhook: {event_type}",
        "external_id": payload.get("transId"),
        "raw_payload": payload,
        "source": "uzum_webhook",
    }


# Create a standart format
def to_standard_format(raw_row: Dict[str, Any], source: str = "csv") -> dict:

    date = (
        raw_row.get("date")
        or raw_row.get("Date")
        or raw_row.get("created_at")
        or raw_row.get("timestamp")
        or raw_row.get("Дата")
    )

    amount = (
        raw_row.get("amount")
        or raw_row.get("Amount")
        or raw_row.get("Сумма")
        or raw_row.get("value")
    )

    merchant = (
        raw_row.get("merchant")
        or raw_row.get("Merchant")
        or raw_row.get("recipient")
        or raw_row.get("payee")
        or raw_row.get("Получатель")
    )

    category = (
        raw_row.get("category") or raw_row.get("Category") or raw_row.get("Категория")
    )

    description = (
        raw_row.get("description")
        or raw_row.get("Description")
        or raw_row.get("note")
        or raw_row.get("Описание")
    )

    external_id = (
        raw_row.get("id") or raw_row.get("transaction_id") or raw_row.get("payment_id")
    )

    raw_payload = raw_row.get("raw_payload", raw_row)

    standard = {
        "date": date,
        "amount": amount,
        "merchant": merchant,
        "category": category,
        "description": description,
        "external_id": str(external_id) if external_id else None,
        "raw_payload": raw_payload,
        "source": source,
    }
    standard["transaction_hash"] = generate_hash(standard)

    return standard


# Make each transaction unique with it's own hash
def generate_hash(tnx: dict) -> str:
    key = f"{tnx.get('date')}|{tnx.get('amount')}|{tnx.get('merchant')}|{tnx.get('source')}"
    return hashlib.sha256(key.encode()).hexdigest()


# Save transactions to db without duplicates
async def save_to_database(
    transactions: List[Dict[str, Any]],
    user_id: int,
    account_id: Optional[int],
    db: AsyncSession,
) -> Dict[str, Any]:

    saved = 0
    duplicates = 0
    errors: list[str] = []

    for idx, txn in enumerate(transactions, start=1):
        # Deduplication
        try:
            existing = await db.execute(
                models.Transaction.__table__.select().where(
                    models.Transaction.transaction_hash == txn["transaction_hash"]
                )
            )
            if existing.first():
                duplicates += 1
                continue

            transaction = models.Transaction(
                owner_id=user_id,
                account_id=account_id,
                amount=str(txn["amount"]),
                merchant=txn["merchant"],
                category=txn["category"],
                description=txn["description"],
                external_id=txn["external_id"],
                raw_payload=txn["raw_payload"],
                transaction_hash=txn["transaction_hash"],
                processed=False,
            )

            db.add(transaction)
            saved += 1

        except Exception as e:
            errors.append(f"Row {idx}: {str(e)}")

    try:
        await db.commit()
        print(f"Saved {saved} transactions, skipped {duplicates} duplicates")
    except Exception as e:
        await db.rollback()
        print(f"Database error: {e}")
        raise

    return {"saved": saved, "duplicates": duplicates, "errors": errors}


# Orchestrate the whole process for CSV
async def ingest_from_csv(
    file_content: bytes, user_id: int, account_id: Optional[int], db: AsyncSession, source: str = "csv"
) -> Dict[str, Any]:

    rows = read_csv_file(file_content)
    transactions = [to_standard_format(row, source=source) for row in rows]
    result = await save_to_database(transactions, user_id, account_id, db)

    return {"total": len(rows), **result}


# Orchestrate the whole process for API
async def ingest_from_api(
    url: str,
    headers: dict,
    user_id: int,
    account_id: int,
    db: AsyncSession,
    source: str = "api",
) -> Dict[str, Any]:
    rows = await fetch_from_api(url, headers)
    transactions = [to_standard_format(r, source=source) for r in rows]
    result = await save_to_database(transactions, user_id, account_id, db)
    return {"total": len(rows), **result}


# Orchestrate the whole process for Uzum
async def ingest_from_uzum_webhook(
    payload: dict,
    event_type: str,
    user_id: int,
    account_id: int,
    db: AsyncSession,
) -> Dict[str, Any]:
    txn = to_standard_format(
        uzum_webhook_to_standard(payload, event_type), source="uzum_webhook"
    )
    result = await save_to_database([txn], user_id, account_id, db)
    return {"total": 1, **result}
