"""Recurring-payment detection: same merchant or service, similar amount, regular interval.

A series needs at least MIN_OCCURRENCES transactions whose gaps all sit within the
tolerance of a known cadence (weekly / fortnightly / monthly) and whose amounts all sit
within a tolerance of the median amount. Bills are usage-based (electricity changes with
the season), so bill payments get a wider amount tolerance than fixed-price items.
"""

from __future__ import annotations

import calendar
import datetime as dt
import statistics
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from app.domain import Category, Direction, Transaction, TxnType
from app.text import normalize_merchant

MIN_OCCURRENCES = 3


class Cadence(StrEnum):
    WEEKLY = "weekly"
    FORTNIGHTLY = "fortnightly"
    MONTHLY = "monthly"


# cadence -> (nominal days, allowed deviation of each gap from the median gap, in days)
CADENCES: dict[Cadence, tuple[int, int]] = {
    Cadence.WEEKLY: (7, 2),
    Cadence.FORTNIGHTLY: (14, 3),
    Cadence.MONTHLY: (30, 5),
}

AMOUNT_TOLERANCE_BILLS = 0.40  # usage-based bills vary month to month
AMOUNT_TOLERANCE_DEFAULT = 0.25

# A series whose last payment is older than this many intervals is treated as stopped.
STALE_AFTER_INTERVALS = 2


@dataclass(frozen=True, slots=True)
class RecurringSeries:
    key: str  # stable id for confirm/dismiss feedback
    merchant: str
    service: str | None
    type: TxnType
    direction: Direction
    category: Category
    subcategory: str | None
    cadence: Cadence
    interval_days: int  # median gap between payments
    day_of_month: int | None  # set for calendar-monthly bills (paid "around the 14th")
    usual_amount_paisa: int  # median amount
    last_amount_paisa: int
    last_date: dt.date
    next_due: dt.date  # may be in the past = overdue
    occurrences: int
    transaction_ids: tuple[str, ...]

    def following(self, day: dt.date) -> dt.date:
        """The expected payment after the one expected on `day`."""
        if self.day_of_month is None:
            return day + dt.timedelta(days=self.interval_days)
        y, m = (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)
        return _month_day(y, m, self.day_of_month)


def _month_day(year: int, month: int, dom: int) -> dt.date:
    return dt.date(year, month, min(dom, calendar.monthrange(year, month)[1]))


def _calendar_next(last: dt.date, dom: int) -> dt.date:
    """First date on day `dom` that is more than half a month after `last`."""
    candidate = _month_day(last.year, last.month, dom)
    while candidate <= last + dt.timedelta(days=15):
        y, m = (
            (candidate.year + 1, 1)
            if candidate.month == 12
            else (candidate.year, candidate.month + 1)
        )
        candidate = _month_day(y, m, dom)
    return candidate


def series_key(txn: Transaction) -> str:
    return f"{txn.direction.value}:{txn.service or '-'}:{normalize_merchant(txn.merchant)}"


def _cadence_for(median_gap: float) -> Cadence | None:
    for cadence, (nominal, tol) in CADENCES.items():
        if abs(median_gap - nominal) <= tol:
            return cadence
    return None


def _median_int(values: list[int]) -> int:
    return int(round(statistics.median(values)))


def _analyse(key: str, txns: list[Transaction], as_of: dt.date) -> RecurringSeries | None:
    if len(txns) < MIN_OCCURRENCES:
        return None
    txns = sorted(txns, key=lambda t: t.occurred_at)
    dates = [t.occurred_at.date() for t in txns]
    gaps = [(b - a).days for a, b in zip(dates, dates[1:], strict=False)]
    median_gap = statistics.median(gaps)
    cadence = _cadence_for(median_gap)
    if cadence is None:
        return None
    _, gap_tol = CADENCES[cadence]
    if any(abs(g - median_gap) > gap_tol for g in gaps):
        return None

    amounts = [t.amount_paisa for t in txns]
    usual = _median_int(amounts)
    amount_tol = (
        AMOUNT_TOLERANCE_BILLS
        if txns[-1].type is TxnType.BILL_PAYMENT
        else AMOUNT_TOLERANCE_DEFAULT
    )
    if any(abs(a - usual) > amount_tol * usual for a in amounts):
        return None

    interval = int(round(median_gap))
    if (as_of - dates[-1]).days > STALE_AFTER_INTERVALS * interval:
        return None

    # Fixed-validity items (a 28-day data pack) repeat at an exact interval. Other monthly
    # payments drift around a day of the month (a bill paid on the 14th, 14th, 10th).
    fixed_interval = max(gaps) - min(gaps) <= 1
    day_of_month = None
    if cadence is Cadence.MONTHLY and not fixed_interval:
        day_of_month = _median_int([d.day for d in dates])
        next_due = _calendar_next(dates[-1], day_of_month)
    else:
        next_due = dates[-1] + dt.timedelta(days=interval)

    last = txns[-1]
    return RecurringSeries(
        key=key,
        merchant=last.merchant,
        service=last.service,
        type=last.type,
        direction=last.direction,
        category=last.category,
        subcategory=last.subcategory,
        cadence=cadence,
        interval_days=interval,
        day_of_month=day_of_month,
        usual_amount_paisa=usual,
        last_amount_paisa=last.amount_paisa,
        last_date=dates[-1],
        next_due=next_due,
        occurrences=len(txns),
        transaction_ids=tuple(t.id for t in txns),
    )


def detect_recurring(
    transactions: Iterable[Transaction], as_of: dt.date | None = None
) -> list[RecurringSeries]:
    """Recurring series in `transactions` (debits and credits), soonest next_due first."""
    groups: dict[str, list[Transaction]] = defaultdict(list)
    for txn in transactions:
        groups[series_key(txn)].append(txn)
    if not groups:
        return []
    if as_of is None:
        as_of = max(t.occurred_at.date() for g in groups.values() for t in g)
    found = [s for key, txns in groups.items() if (s := _analyse(key, txns, as_of)) is not None]
    return sorted(found, key=lambda s: (s.next_due, s.merchant))
