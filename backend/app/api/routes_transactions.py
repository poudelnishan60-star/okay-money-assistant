from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import SessionDep, TodayDep, TxSourceDep, UserDep
from app.api.schemas import RecategorizeIn, RecategorizeOut, TransactionOut, TransactionPage
from app.domain import Category, Direction, TxnType
from app.periods import CalendarSystem, last_n_days, month_period
from app.services.categorizer import InvalidCategoryError, recategorize
from app.sources.base import TransactionFilter

router = APIRouter(prefix="/transactions", tags=["transactions"])

PeriodChip = Literal["7d", "14d", "30d", "this_month"]


def resolve_range(
    period: PeriodChip | None,
    start: dt.date | None,
    end: dt.date | None,
    calendar: CalendarSystem,
    today: dt.date,
) -> tuple[dt.date | None, dt.date | None]:
    """Period chips (7/14/30 days, this month) or an explicit start/end ("Custom")."""
    if period is not None:
        if period == "this_month":
            p = month_period(today, calendar)
            return p.start, today
        p = last_n_days(today, int(period.removesuffix("d")))
        return p.start, p.end
    if start and end and end < start:
        raise HTTPException(status_code=422, detail="end is before start")
    return start, end


@router.get("", response_model=TransactionPage)
def list_transactions(
    user_id: UserDep,
    source: TxSourceDep,
    today: TodayDep,
    period: Annotated[PeriodChip | None, Query(description="Overrides start/end.")] = None,
    start: dt.date | None = None,
    end: dt.date | None = None,
    calendar: CalendarSystem = CalendarSystem.AD,
    category: Category | None = None,
    merchant: Annotated[str | None, Query(max_length=100)] = None,
    type: TxnType | None = None,  # noqa: A002  (public query parameter name)
    direction: Direction | None = None,
    min_paisa: Annotated[int | None, Query(ge=0)] = None,
    max_paisa: Annotated[int | None, Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TransactionPage:
    start, end = resolve_range(period, start, end, calendar, today)
    txns = source.list_transactions(
        user_id,
        TransactionFilter(
            start=start,
            end=end,
            category=category,
            merchant=merchant,
            type=type,
            direction=direction,
            min_paisa=min_paisa,
            max_paisa=max_paisa,
        ),
    )
    txns.reverse()  # newest first
    return TransactionPage(
        items=[TransactionOut.of(t) for t in txns[offset : offset + limit]],
        total=len(txns),
        total_debit_paisa=sum(t.amount_paisa for t in txns if t.is_debit),
        total_credit_paisa=sum(t.amount_paisa for t in txns if not t.is_debit),
        limit=limit,
        offset=offset,
        start=start,
        end=end,
    )


@router.get("/{txn_id}", response_model=TransactionOut)
def get_transaction(txn_id: str, user_id: UserDep, source: TxSourceDep) -> TransactionOut:
    txn = source.get_transaction(user_id, txn_id)
    if txn is None:
        raise HTTPException(status_code=404, detail="transaction not found")
    return TransactionOut.of(txn)


@router.patch("/{txn_id}/category", response_model=RecategorizeOut)
def set_transaction_category(
    txn_id: str,
    body: RecategorizeIn,
    session: SessionDep,
    user_id: UserDep,
    source: TxSourceDep,
) -> RecategorizeOut:
    try:
        result = recategorize(
            session,
            source,
            user_id,
            txn_id,
            body.category,
            body.subcategory,
            apply_to_merchant=body.apply_to_merchant,
        )
    except InvalidCategoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="transaction not found") from exc
    session.commit()
    txn = source.get_transaction(user_id, txn_id)
    assert txn is not None  # noqa: S101
    return RecategorizeOut(
        transaction=TransactionOut.of(txn),
        updated_ids=result.updated_ids,
        applied_to_merchant=result.applied_to_merchant,
    )
