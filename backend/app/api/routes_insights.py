from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import SessionDep, TodayDep, TxSourceDep, UserDep
from app.api.schemas import (
    DashboardOut,
    ForecastOut,
    HighlightOut,
    SpendingSummaryOut,
    UnusualSpendOut,
)
from app.periods import (
    CalendarSystem,
    Period,
    custom_period,
    last_n_days,
    month_period,
    month_period_from_key,
    previous_period,
)
from app.services.budgets import budget_statuses
from app.services.forecast import (
    LOW_BALANCE_THRESHOLD_PAISA,
    balance_forecast,
    month_end_forecast,
)
from app.services.insights import BASELINE_DAYS, build_highlights, summarize, unusual_spending
from app.sources.base import TransactionFilter, TransactionSource

router = APIRouter(prefix="/insights", tags=["insights"])

SummaryKind = Literal["month", "week", "custom"]
MonthKey = Annotated[
    str | None,
    Query(
        pattern=r"^\d{4}-\d{2}$",
        description="YYYY-MM in the chosen calendar; default: the current month",
    ),
]


def resolve_periods(
    kind: SummaryKind,
    month: str | None,
    calendar: CalendarSystem,
    start: dt.date | None,
    end: dt.date | None,
    today: dt.date,
) -> tuple[Period, Period]:
    try:
        if kind == "custom":
            if start is None or end is None:
                raise ValueError("custom needs start and end")
            current = custom_period(start, end)
            return current, previous_period(current, None)
        if kind == "week":
            current = last_n_days(today, 7)
            return current, previous_period(current, None)
        current = month_period_from_key(month, calendar) if month else month_period(today, calendar)
        return current, previous_period(current, calendar)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _history(
    source: TransactionSource, user_id: str, current: Period, previous: Period, today: dt.date
):
    """Everything summary + unusual-spend need, in one query."""
    start = min(previous.start, current.start - dt.timedelta(days=BASELINE_DAYS))
    end = min(current.end, today)
    return source.list_transactions(user_id, TransactionFilter(start=start, end=end))


@router.get("/summary", response_model=SpendingSummaryOut)
def get_spending_summary(
    user_id: UserDep,
    source: TxSourceDep,
    today: TodayDep,
    period: SummaryKind = "month",
    month: MonthKey = None,
    calendar: CalendarSystem = CalendarSystem.AD,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> SpendingSummaryOut:
    current, previous = resolve_periods(period, month, calendar, start, end, today)
    txns = _history(source, user_id, current, previous, today)
    return SpendingSummaryOut.of(summarize(txns, current, previous, today))


@router.get("/forecast", response_model=ForecastOut)
def get_forecast(
    user_id: UserDep,
    source: TxSourceDep,
    today: TodayDep,
    days: Annotated[int | None, Query(ge=1, le=90, description="default: to month end")] = None,
    calendar: CalendarSystem = CalendarSystem.AD,
    threshold_paisa: Annotated[int, Query(ge=0)] = LOW_BALANCE_THRESHOLD_PAISA,
) -> ForecastOut:
    if days is not None:
        f = balance_forecast(source, user_id, today, days, threshold_paisa=threshold_paisa)
    else:
        f = month_end_forecast(source, user_id, today, calendar, threshold_paisa=threshold_paisa)
    return ForecastOut.of(f)


@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard(
    session: SessionDep,
    user_id: UserDep,
    source: TxSourceDep,
    today: TodayDep,
    month: MonthKey = None,
    calendar: CalendarSystem = CalendarSystem.AD,
    threshold_paisa: Annotated[int, Query(ge=0)] = LOW_BALANCE_THRESHOLD_PAISA,
) -> DashboardOut:
    """Everything the Insights screen needs in one round trip (slow mobile data)."""
    current, previous = resolve_periods("month", month, calendar, None, None, today)
    txns = _history(source, user_id, current, previous, today)
    summary = summarize(txns, current, previous, today)
    unusual = unusual_spending(txns, current, today)

    forecast = None
    budgets = []
    if summary.in_progress:
        forecast = month_end_forecast(
            source, user_id, today, calendar, threshold_paisa=threshold_paisa
        )
        budgets = budget_statuses(session, source, user_id, today)
    highlights = build_highlights(summary, unusual, budgets, forecast)
    return DashboardOut(
        summary=SpendingSummaryOut.of(summary),
        unusual=[UnusualSpendOut.of(u) for u in unusual],
        highlights=[HighlightOut.of(h) for h in highlights],
        forecast=ForecastOut.of(forecast) if forecast else None,
    )
