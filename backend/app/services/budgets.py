"""Budget math. A budget is a standing monthly limit, overall or for one category, measured
over an AD or BS month. Only spending counts (see domain.NON_SPENDING).

Colour levels (spec): green under 80%, amber 80-100%, red over 100%.
Alerts fire at 80% and at 100%.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import Category, Transaction
from app.models import Budget
from app.periods import CalendarSystem, Period, month_period
from app.sources.base import TransactionFilter, TransactionSource

ALERT_THRESHOLDS: tuple[int, ...] = (80, 100)


class BudgetLevel(StrEnum):
    OK = "ok"  # < 80%
    WARNING = "warning"  # 80% - 100%
    OVER = "over"  # > 100%


@dataclass(frozen=True, slots=True)
class BudgetStatus:
    budget_id: int | None
    category: Category | None  # None = overall
    calendar: CalendarSystem
    period: Period
    limit_paisa: int
    spent_paisa: int
    remaining_paisa: int  # negative when over
    percent_used: float  # one decimal, for display only; decisions use integer math
    level: BudgetLevel
    alerts_reached: tuple[int, ...]  # thresholds crossed so far this period, e.g. (80,)
    days_left: int  # including today
    daily_allowance_paisa: int  # what can still be spent per remaining day (>= 0)
    projected_spend_paisa: int  # spend by period end at the current pace


def spent_in_period(
    transactions: Iterable[Transaction], period: Period, category: Category | None = None
) -> int:
    return sum(
        t.amount_paisa
        for t in transactions
        if t.is_spending
        and period.contains(t.occurred_at.date())
        and (category is None or t.category is category)
    )


def level_for(spent_paisa: int, limit_paisa: int) -> BudgetLevel:
    if spent_paisa > limit_paisa:
        return BudgetLevel.OVER
    if spent_paisa * 100 >= limit_paisa * 80:
        return BudgetLevel.WARNING
    return BudgetLevel.OK


def alerts_for(spent_paisa: int, limit_paisa: int) -> tuple[int, ...]:
    return tuple(t for t in ALERT_THRESHOLDS if spent_paisa * 100 >= limit_paisa * t)


def evaluate_budget(
    *,
    limit_paisa: int,
    spent_paisa: int,
    period: Period,
    today: dt.date,
    category: Category | None = None,
    calendar: CalendarSystem = CalendarSystem.AD,
    budget_id: int | None = None,
) -> BudgetStatus:
    if limit_paisa <= 0:
        raise ValueError("budget limit must be positive")
    remaining = limit_paisa - spent_paisa
    elapsed = period.days_elapsed(today)  # includes today
    if today < period.start:
        days_left = period.days
    elif today > period.end:
        days_left = 0
    else:
        days_left = (period.end - today).days + 1  # today still counts
    projected = (spent_paisa * period.days) // elapsed if elapsed else spent_paisa
    return BudgetStatus(
        budget_id=budget_id,
        category=category,
        calendar=calendar,
        period=period,
        limit_paisa=limit_paisa,
        spent_paisa=spent_paisa,
        remaining_paisa=remaining,
        percent_used=round(spent_paisa * 100 / limit_paisa, 1),
        level=level_for(spent_paisa, limit_paisa),
        alerts_reached=alerts_for(spent_paisa, limit_paisa),
        days_left=days_left,
        daily_allowance_paisa=max(remaining, 0) // days_left if days_left else 0,
        projected_spend_paisa=projected,
    )


def budget_statuses(
    session: Session, source: TransactionSource, user_id: str, today: dt.date
) -> list[BudgetStatus]:
    """Status of every budget the user has, for the month (AD or BS) containing today.
    Overall budget first, then categories alphabetically."""
    budgets = list(session.scalars(select(Budget).where(Budget.user_id == user_id)))
    if not budgets:
        return []
    periods = {b.id: month_period(today, CalendarSystem(b.calendar)) for b in budgets}
    earliest = min(p.start for p in periods.values())
    latest = max(p.end for p in periods.values())
    txns = source.list_transactions(user_id, TransactionFilter(start=earliest, end=latest))

    statuses = []
    for b in budgets:
        period = periods[b.id]
        category = Category(b.category) if b.category else None
        statuses.append(
            evaluate_budget(
                limit_paisa=b.limit_paisa,
                spent_paisa=spent_in_period(txns, period, category),
                period=period,
                today=today,
                category=category,
                calendar=CalendarSystem(b.calendar),
                budget_id=b.id,
            )
        )
    return sorted(statuses, key=lambda s: (s.category is not None, s.category or ""))
