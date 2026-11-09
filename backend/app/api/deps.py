"""Request dependencies. Swapping Mock* sources for Khalti ones, or the demo-user header for
real auth, happens here and nowhere else."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.models import User
from app.periods import today_npt
from app.seed import DEMO_USER_ID
from app.sources.base import BillSource, DepositSource, TransactionSource
from app.sources.mock import MockBillSource, MockDepositSource, MockTransactionSource


def get_session(request: Request) -> Iterator[Session]:
    """One session per request. Routes that write call session.commit() themselves."""
    with request.app.state.session_factory() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def get_user_id(
    session: SessionDep,
    x_user_id: Annotated[
        str | None,
        Header(description="Prototype only: which user. Real auth replaces this header."),
    ] = None,
) -> str:
    user_id = x_user_id or DEMO_USER_ID
    if session.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="unknown user")
    return user_id


def get_today() -> dt.date:
    """Today in Nepal time. Tests override this to pin the date."""
    return today_npt()


def get_transaction_source(session: SessionDep) -> TransactionSource:
    return MockTransactionSource(session)


TxSourceDep = Annotated[TransactionSource, Depends(get_transaction_source)]


def get_bill_source(transactions: TxSourceDep) -> BillSource:
    return MockBillSource(transactions)


def get_deposit_source(transactions: TxSourceDep) -> DepositSource:
    return MockDepositSource(transactions)


UserDep = Annotated[str, Depends(get_user_id)]
TodayDep = Annotated[dt.date, Depends(get_today)]
BillSourceDep = Annotated[BillSource, Depends(get_bill_source)]
DepositSourceDep = Annotated[DepositSource, Depends(get_deposit_source)]
