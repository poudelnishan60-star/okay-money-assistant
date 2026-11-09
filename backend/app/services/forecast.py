"""Cash-flow forecast: projected wallet balance day by day.

projected balance = current balance
                  + expected recurring items (bills, data packs, Smart Deposit, remittance)
                  - average daily everyday spend * days

"Everyday spend" is the average of the last LOOKBACK_DAYS of debits that are not part of a
recurring series and are not bookings (a bus ticket or hotel is a one-off, not a daily habit).
Irregular income (a friend paying you back) is left out, so the forecast leans cautious.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass

from app.domain import Category, Direction, Transaction, TxnType
from app.periods import CalendarSystem, month_period
from app.services.recurring import detect_recurring
from app.sources.base import TransactionFilter, TransactionSource

LOOKBACK_DAYS = 30
LOW_BALANCE_THRESHOLD_PAISA = 1_000_00  # Rs. 1,000 default warning line


@dataclass(frozen=True, slots=True)
class ScheduledItem:
    date: dt.date
    merchant: str
    category: Category
    amount_paisa: int  # signed: negative = money out
    series_key: str


@dataclass(frozen=True, slots=True)
class ForecastPoint:
    date: dt.date
    balance_paisa: int  # end-of-day projection


@dataclass(frozen=True, slots=True)
class BalanceForecast:
    as_of: dt.date
    horizon_end: dt.date
    current_balance_paisa: int
    avg_daily_spend_paisa: int
    lookback_days: int
    scheduled: tuple[ScheduledItem, ...]
    points: tuple[ForecastPoint, ...]
    projected_end_balance_paisa: int
    lowest_balance_paisa: int
    lowest_date: dt.date
    threshold_paisa: int
    below_threshold: bool
    first_below_date: dt.date | None


def average_daily_spend(
    history: Sequence[Transaction],
    recurring_ids: set[str],
    as_of: dt.date,
    lookback_days: int = LOOKBACK_DAYS,
) -> int:
    start = as_of - dt.timedelta(days=lookback_days - 1)
    total = sum(
        t.amount_paisa
        for t in history
        if t.is_debit
        and t.id not in recurring_ids
        and t.type is not TxnType.BOOKING
        and start <= t.occurred_at.date() <= as_of
    )
    return int(round(total / lookback_days))


def forecast_balance(
    history: Sequence[Transaction],
    current_balance_paisa: int,
    as_of: dt.date,
    horizon_end: dt.date,
    *,
    threshold_paisa: int = LOW_BALANCE_THRESHOLD_PAISA,
    lookback_days: int = LOOKBACK_DAYS,
) -> BalanceForecast:
    """Pure forecast from a transaction history. Projects as_of+1 .. horizon_end."""
    if horizon_end < as_of:
        raise ValueError("horizon_end is before as_of")
    series = detect_recurring(history, as_of=as_of)
    recurring_ids = {tid for s in series for tid in s.transaction_ids}
    avg = average_daily_spend(history, recurring_ids, as_of, lookback_days)

    scheduled: list[ScheduledItem] = []
    first_day = as_of + dt.timedelta(days=1)
    for s in series:
        sign = -1 if s.direction is Direction.DEBIT else 1
        dates: list[dt.date] = []
        due = s.next_due
        if due < first_day:  # overdue: expect it tomorrow, then the cycle carries on
            dates.append(first_day)
            while due <= first_day:
                due = s.following(due)
        while due <= horizon_end:
            dates.append(due)
            due = s.following(due)
        scheduled.extend(
            ScheduledItem(d, s.merchant, s.category, sign * s.usual_amount_paisa, s.key)
            for d in dates
            if d <= horizon_end
        )
    scheduled.sort(key=lambda i: (i.date, i.merchant))

    by_day: dict[dt.date, int] = {}
    for item in scheduled:
        by_day[item.date] = by_day.get(item.date, 0) + item.amount_paisa

    balance = current_balance_paisa
    points: list[ForecastPoint] = []
    day = first_day
    while day <= horizon_end:
        balance += by_day.get(day, 0) - avg
        points.append(ForecastPoint(day, balance))
        day += dt.timedelta(days=1)

    if points:
        lowest = min(points, key=lambda p: (p.balance_paisa, p.date))
        lowest_balance, lowest_date = lowest.balance_paisa, lowest.date
        end_balance = points[-1].balance_paisa
    else:
        lowest_balance, lowest_date, end_balance = balance, as_of, balance
    first_below = next((p.date for p in points if p.balance_paisa < threshold_paisa), None)

    return BalanceForecast(
        as_of=as_of,
        horizon_end=horizon_end,
        current_balance_paisa=current_balance_paisa,
        avg_daily_spend_paisa=avg,
        lookback_days=lookback_days,
        scheduled=tuple(scheduled),
        points=tuple(points),
        projected_end_balance_paisa=end_balance,
        lowest_balance_paisa=lowest_balance,
        lowest_date=lowest_date,
        threshold_paisa=threshold_paisa,
        below_threshold=first_below is not None,
        first_below_date=first_below,
    )


def balance_forecast(
    source: TransactionSource,
    user_id: str,
    today: dt.date,
    days: int,
    *,
    threshold_paisa: int = LOW_BALANCE_THRESHOLD_PAISA,
) -> BalanceForecast:
    """Forecast for the next `days` days (backs the get_balance_forecast tool)."""
    if days < 1:
        raise ValueError("days must be >= 1")
    history = source.list_transactions(user_id, TransactionFilter(end=today))
    return forecast_balance(
        history,
        source.get_balance(user_id),
        today,
        today + dt.timedelta(days=days),
        threshold_paisa=threshold_paisa,
    )


def month_end_forecast(
    source: TransactionSource,
    user_id: str,
    today: dt.date,
    calendar: CalendarSystem = CalendarSystem.AD,
    *,
    threshold_paisa: int = LOW_BALANCE_THRESHOLD_PAISA,
) -> BalanceForecast:
    history = source.list_transactions(user_id, TransactionFilter(end=today))
    return forecast_balance(
        history,
        source.get_balance(user_id),
        today,
        month_period(today, calendar).end,
        threshold_paisa=threshold_paisa,
    )
