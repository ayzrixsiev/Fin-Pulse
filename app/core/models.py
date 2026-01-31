# app/core/models.py
"""
DATABASE MODELS for Fin-Pulse

Design Philosophy:
- Transactions table is the RAW LAYER (ingest everything as-is)
- Keep original data in raw_payload for debugging/reprocessing
- Use 'processed' flag to track ETL progress
- Add hash for deduplication
- Keep it simple and scalable
"""

from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    String,
    Numeric,
    Boolean,
    TIMESTAMP,
    Text,
    JSON,
    Index,
    func,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


# =========================
# User
# =========================
class User(Base):
    __tablename__ = "users_table"

    id = Column(Integer, primary_key=True, autoincrement=True)

    email = Column(String, nullable=False, unique=True, index=True)
    password = Column(String, nullable=False)
    role = Column(String, nullable=False, server_default="user")

    created_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    accounts = relationship(
        "Account",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    transactions = relationship(
        "Transaction",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


# =========================
# Account (data source)
# =========================
class Account(Base):
    """
    Represents a financial source:
    - bank account (Uzum Bank, Kapital Bank)
    - e-wallet (Payme, Click, Humo)
    - manual CSV upload
    - API integration (future: Plaid, etc.)

    Why separate accounts?
    - Track balance per source
    - Know where money comes from
    - Filter transactions by account
    """

    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)

    name = Column(String, nullable=False)  # "Uzum Bank Salary", "Payme Wallet"
    provider = Column(String, nullable=False)  # uzum/payme/csv/manual/api

    # Account type helps categorization
    account_type = Column(String)  # checking/savings/credit_card/wallet

    currency = Column(String, default="UZS", nullable=False)

    # Current balance (updated after ETL)
    balance = Column(Numeric(15, 2), default=0)

    owner_id = Column(
        Integer,
        ForeignKey("users_table.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Track if account is active
    is_active = Column(Boolean, default=True)

    created_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at = Column(
        TIMESTAMP(timezone=True),
        nullable=True,
        onupdate=func.now(),
    )

    # Relationships
    owner = relationship("User", back_populates="accounts")
    transactions = relationship(
        "Transaction",
        back_populates="account",
        cascade="all, delete-orphan",
    )


# =========================
# Transaction (RAW DATA LAYER)
# =========================
class Transaction(Base):
    """
    CORE TABLE - RAW TRANSACTION DATA

    This is where ALL transactions start their journey:
    CSV → here → transform.py cleans it → aggregate.py analyzes it

    Design decisions:
    1. Keep EVERYTHING in raw_payload (original data)
    2. Use 'processed' flag for ETL pipeline tracking
    3. Add transaction_hash for deduplication
    4. Store both created_at (transaction time) and ingested_at (when we got it)

    Common transaction data shapes from different sources:

    Bank CSV:
        {
            "date": "2025-01-15",
            "amount": "1,500,000.00",
            "merchant": "MAKRO TASHKENT",
            "description": "POS Purchase"
        }

    Payme/Click API:
        {
            "created_time": "2025-01-15T10:30:00",
            "amount": 50000,
            "recipient": "Starbucks",
            "state": 2  # completed
        }

    Manual entry:
        {
            "date": "2025-01-15",
            "amount": "-50000",
            "category": "Food",
            "note": "Lunch"
        }
    """

    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # --- OWNERSHIP ---
    owner_id = Column(
        Integer,
        ForeignKey("users_table.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    account_id = Column(
        Integer,
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=True,  # Can be NULL for manual entries without account
        index=True,
    )

    # --- CORE FINANCIAL DATA ---
    # Amount is stored as-is from source (will be cleaned in transform.py)
    amount = Column(
        Numeric(15, 2), nullable=False
    )  # Positive = income, Negative = expense

    currency = Column(String(3), default="UZS", nullable=False)

    # --- TRANSACTION DETAILS ---
    merchant = Column(String(255))  # Who you paid/received from
    category = Column(String(100), index=True)  # Food, Transport, etc.
    description = Column(Text)  # Additional notes

    # --- ETL METADATA ---
    # Keep original data for debugging and reprocessing
    raw_payload = Column(JSON, nullable=True)

    # Deduplication: hash of (amount, merchant, date) to avoid duplicates
    transaction_hash = Column(String(64), unique=True, index=True)

    # ETL pipeline tracking
    processed = Column(Boolean, default=False, index=True)

    # External ID from source system (bank transaction ID, API ID, etc.)
    external_id = Column(String(255), index=True)

    # --- TIMESTAMPS ---
    created_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,  # Index for date range queries
    )  # When the transaction actually happened

    ingested_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )  # When we imported it

    updated_at = Column(
        TIMESTAMP(timezone=True),
        nullable=True,
        onupdate=func.now(),
    )  # Last modification

    # --- RELATIONSHIPS ---
    owner = relationship("User", back_populates="transactions")
    account = relationship("Account", back_populates="transactions")

    # --- COMPOSITE INDEXES FOR PERFORMANCE ---
    # Common query: "Get all unprocessed transactions for a user"
    __table_args__ = (
        Index("idx_owner_processed", "owner_id", "processed"),
        Index("idx_owner_date", "owner_id", "created_at"),
    )


# =========================
# WHAT TRANSACTION DATA LOOKS LIKE FROM DIFFERENT SOURCES
# =========================

"""
1. UZBEKISTAN BANK CSV (Uzum Bank, Kapital Bank, etc.):
   -------------------------------------------------------
   Date        | Amount      | Merchant              | Description
   15.01.2025  | -1,500,000  | MAKRO TASHKENT        | Card payment
   16.01.2025  | +5,000,000  | Salary                | Transfer in
   
   Raw dict:
   {
       "Date": "15.01.2025",
       "Amount": "-1,500,000",
       "Merchant": "MAKRO TASHKENT",
       "Description": "Card payment"
   }


2. PAYME API RESPONSE:
   --------------------
   {
       "jsonrpc": "2.0",
       "result": {
           "transactions": [
               {
                   "id": "63c4d1f2e...",
                   "time": 1674567890000,  # Unix timestamp
                   "amount": 50000,
                   "account": {
                       "order_id": "ORD123"
                   },
                   "state": 2,  # 2 = completed
                   "reason": null
               }
           ]
       }
   }


3. CLICK API RESPONSE:
   --------------------
   {
       "transactions": [
           {
               "payment_id": 123456,
               "created_datetime": "2025-01-15 10:30:00",
               "amount": 25000,
               "merchant_trans_id": "TXN789",
               "status": 2  # success
           }
       ]
   }


4. MANUAL CSV UPLOAD (User creates their own):
   ---------------------------------------------
   date,amount,category,description
   2025-01-15,-50000,Food,Lunch at Evos
   2025-01-16,-200000,Transport,Taxi
   
   Raw dict:
   {
       "date": "2025-01-15",
       "amount": "-50000",
       "category": "Food",
       "description": "Lunch at Evos"
   }


5. INTERNATIONAL BANK CSV (if user works abroad):
   -----------------------------------------------
   Date       | Amount  | Currency | Merchant      | Type
   2025-01-15 | -100.50 | USD      | Amazon        | Debit
   2025-01-16 | 2500.00 | USD      | Paycheck      | Credit


COMMON CHALLENGES (that transform.py will fix):
================================================
❌ Different date formats: "15.01.2025" vs "2025-01-15" vs unix timestamp
❌ Different amount formats: "1,500,000" vs "1500000.00" vs "-50000"
❌ Currency symbols: "1,500,000 so'm" vs "1500000 UZS" vs "$100"
❌ Merchant names: "MAKRO TASHKENT" vs "Makro" vs "MAKRO YUNUSOBOD"
❌ Missing categories (need auto-categorization)
❌ Duplicates from re-uploads
"""
