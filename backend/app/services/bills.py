"""Bills & subscriptions as the user sees them: detected bills from the BillSource plus the
user's own confirm / dismiss choices (assistant-owned data)."""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RecurringFeedback
from app.sources.base import BillSource, UpcomingBill

DEFAULT_WITHIN_DAYS = 45
_LOOKUP_WITHIN_DAYS = 400  # wide enough to find any detected series by id


class BillStatus(StrEnum):
    DETECTED = "detected"  # found by the detector, user has not said anything yet
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"


@dataclass(frozen=True, slots=True)
class BillView:
    id: str
    bill: UpcomingBill
    status: BillStatus
    days_until_due: int  # negative = overdue
    overdue: bool


def bill_id(series_key: str) -> str:
    """Short, URL-safe, stable id for a recurring series."""
    return hashlib.sha1(series_key.encode(), usedforsecurity=False).hexdigest()[:12]


def _feedback(session: Session, user_id: str) -> dict[str, RecurringFeedback]:
    rows = session.scalars(select(RecurringFeedback).where(RecurringFeedback.user_id == user_id))
    return {r.series_key: r for r in rows}


def _view(bill: UpcomingBill, status: BillStatus, today: dt.date) -> BillView:
    days = (bill.due_date - today).days
    return BillView(bill_id(bill.series_key), bill, status, days, days < 0)


def list_bills(
    session: Session,
    bills: BillSource,
    user_id: str,
    today: dt.date,
    within_days: int = DEFAULT_WITHIN_DAYS,
    *,
    include_dismissed: bool = False,
) -> list[BillView]:
    feedback = _feedback(session, user_id)
    views = []
    for bill in bills.upcoming_bills(user_id, today, within_days):
        fb = feedback.get(bill.series_key)
        status = BillStatus(fb.status) if fb else BillStatus.DETECTED
        if status is BillStatus.DISMISSED and not include_dismissed:
            continue
        views.append(_view(bill, status, today))
    return views


def set_bill_status(
    session: Session,
    bills: BillSource,
    user_id: str,
    today: dt.date,
    id_: str,
    status: BillStatus,
) -> BillView:
    """Confirm, dismiss, or (status=detected) undo a previous choice. LookupError if unknown."""
    match = next(
        (
            v
            for v in list_bills(
                session, bills, user_id, today, _LOOKUP_WITHIN_DAYS, include_dismissed=True
            )
            if v.id == id_
        ),
        None,
    )
    if match is None:
        raise LookupError(id_)
    key = match.bill.series_key
    row = session.scalar(
        select(RecurringFeedback).where(
            RecurringFeedback.user_id == user_id, RecurringFeedback.series_key == key
        )
    )
    if status is BillStatus.DETECTED:
        if row is not None:
            session.delete(row)
    elif row is None:
        session.add(RecurringFeedback(user_id=user_id, series_key=key, status=status.value))
    else:
        row.status = status.value
    session.flush()
    return _view(match.bill, status, today)
