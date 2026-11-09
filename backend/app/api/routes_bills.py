from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import BillSourceDep, SessionDep, TodayDep, UserDep
from app.api.schemas import BillOut, BillStatusIn
from app.services.bills import DEFAULT_WITHIN_DAYS, list_bills, set_bill_status

router = APIRouter(prefix="/bills", tags=["bills"])


@router.get("", response_model=list[BillOut])
def get_bills(
    session: SessionDep,
    user_id: UserDep,
    bills: BillSourceDep,
    today: TodayDep,
    within_days: Annotated[int, Query(ge=1, le=366)] = DEFAULT_WITHIN_DAYS,
    include_dismissed: bool = False,
) -> list[BillOut]:
    """Detected recurring bills and subscriptions, soonest due first (overdue included)."""
    views = list_bills(
        session, bills, user_id, today, within_days, include_dismissed=include_dismissed
    )
    return [BillOut.of(v) for v in views]


@router.put("/{bill_id}/status", response_model=BillOut)
def update_bill_status(
    bill_id: str,
    body: BillStatusIn,
    session: SessionDep,
    user_id: UserDep,
    bills: BillSourceDep,
    today: TodayDep,
) -> BillOut:
    """Confirm or dismiss a detection; status 'detected' undoes the choice."""
    try:
        view = set_bill_status(session, bills, user_id, today, bill_id, body.status)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="bill not found") from exc
    session.commit()
    return BillOut.of(view)
