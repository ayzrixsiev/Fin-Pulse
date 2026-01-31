# app/core/routers/accounts.py
import logging
from typing import List, Annotated
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core import schemas, models
from app.core.database import get_db
from app.core.security import get_current_user

router = APIRouter(prefix="/accounts", tags=["Accounts"])

db_dep = Annotated[AsyncSession, Depends(get_db)]


@router.get(
    "", response_model=List[schemas.AccountResponse], status_code=status.HTTP_200_OK
)
async def get_accounts(
    current_user: Annotated[models.User, Depends(get_current_user)], db: db_dep
):
    query = select(models.Account).where(models.Account.owner_id == current_user.id)
    result = await db.execute(query)
    accounts = result.scalars().all()
    return accounts


@router.post(
    "", response_model=schemas.AccountResponse, status_code=status.HTTP_201_CREATED
)
async def create_account(
    account: schemas.AccountCreate,
    db: db_dep,
    current_user: Annotated[models.User, Depends(get_current_user)],
):
    try:
        new_account = models.Account(**account.model_dump(), owner_id=current_user.id)
        db.add(new_account)
        await db.commit()
        await db.refresh(new_account)
        return new_account
    except Exception as error:
        await db.rollback()
        logging.error(f"Failed to create account: {error}")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to create account"
        )


@router.patch("/{account_id}", response_model=schemas.AccountResponse)
async def update_account(
    account_id: int,
    payload: schemas.AccountUpdate,
    db: db_dep,
    current_user: Annotated[models.User, Depends(get_current_user)],
):
    query = select(models.Account).where(
        models.Account.id == account_id, models.Account.owner_id == current_user.id
    )
    result = await db.execute(query)
    acc = result.scalars().first()
    if not acc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    changes = payload.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(acc, k, v)
    try:
        db.add(acc)
        await db.commit()
        await db.refresh(acc)
        return acc
    except Exception as error:
        await db.rollback()
        logging.error(f"Failed to update account {account_id}: {error}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Update failed")


@router.delete("/{account_id}")
async def delete_account(
    account_id: int,
    db: db_dep,
    current_user: Annotated[models.User, Depends(get_current_user)],
):
    query = select(models.Account).where(
        models.Account.id == account_id, models.Account.owner_id == current_user.id
    )
    result = await db.execute(query)
    acc = result.scalars().first()
    if not acc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    try:
        await db.delete(acc)
        await db.commit()
        return {"message": "Deleted account"}
    except Exception as error:
        await db.rollback()
        logging.error(f"Failed to delete account: {error}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Delete failed")
