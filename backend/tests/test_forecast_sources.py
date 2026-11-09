from __future__ import annotations

import datetime as dt

import pytest

from app.domain import Category, Direction, TxnType
from app.services.forecast import (
    average_daily_spend,
    balance_forecast,
    forecast_balance,
    month_end_forecast,
)
from app.sources.base import TransactionFilter
from app.sources.mock import MockTransactionSource
from tests.conftest import ANCHOR, USER, make_txn

AS_OF = dt.date(2026, 11, 9)


def _daily(rupees: int, days: int = 30, end: dt.date = AS_OF):
    return [
        make_txn(end - dt.timedelta(days=i), rupees, f"Café {i}", category=Category.FOOD)
        for i in range(days)
    ]


def test_flat_spend_only() -> None:
    f = forecast_balance(_daily(100), 10_000_00, AS_OF, AS_OF + dt.timedelta(days=10))
    assert f.avg_daily_spend_paisa == 100_00
    assert len(f.points) == 10
    assert f.projected_end_balance_paisa == 9_000_00
    assert not f.below_threshold


def test_recurring_bill_is_scheduled_and_not_double_counted() -> None:
    bills = [
        make_txn(
            d,
            1300,
            "Gurans Fibernet",
            type=TxnType.BILL_PAYMENT,
            service="internet",
            category=Category.BILLS,
        )
        for d in ("2026-08-21", "2026-09-21", "2026-10-21")
    ]
    history = _daily(100) + bills
    f = forecast_balance(history, 10_000_00, AS_OF, dt.date(2026, 11, 30))
    assert f.avg_daily_spend_paisa == 100_00  # the bill is not part of the daily average
    [item] = f.scheduled
    assert item.date == dt.date(2026, 11, 20) and item.amount_paisa == -1_300_00
    assert f.projected_end_balance_paisa == 10_000_00 - 21 * 100_00 - 1_300_00


def test_recurring_income_is_added() -> None:
    remit = [
        make_txn(
            d,
            28_000,
            "Sagarmatha Remit",
            type=TxnType.REMITTANCE,
            direction=Direction.CREDIT,
            category=Category.REMITTANCE,
        )
        for d in ("2026-08-15", "2026-09-15", "2026-10-15")
    ]
    f = forecast_balance(remit, 5_000_00, AS_OF, dt.date(2026, 11, 30))
    assert [i.amount_paisa for i in f.scheduled] == [28_000_00]
    assert f.projected_end_balance_paisa == 33_000_00


def test_overdue_bill_is_expected_tomorrow() -> None:
    bills = [
        make_txn(
            d,
            1000,
            "NEA",
            type=TxnType.BILL_PAYMENT,
            service="electricity",
            category=Category.BILLS,
        )
        for d in ("2026-08-01", "2026-09-01", "2026-10-01")
    ]
    f = forecast_balance(bills, 5_000_00, AS_OF, dt.date(2026, 11, 30))
    # expected 31 Oct, not seen: assume tomorrow; the next cycle (30 Nov) still comes
    assert [i.date for i in f.scheduled] == [AS_OF + dt.timedelta(days=1), dt.date(2026, 11, 30)]


def test_low_balance_warning() -> None:
    f = forecast_balance(
        _daily(500), 3_000_00, AS_OF, AS_OF + dt.timedelta(days=10), threshold_paisa=1_000_00
    )
    # 3,000 - 500/day: 2,500 2,000 1,500 1,000 500 ...  first below Rs 1,000 on day 5
    assert f.below_threshold
    assert f.first_below_date == AS_OF + dt.timedelta(days=5)
    assert f.lowest_balance_paisa == 3_000_00 - 10 * 500_00
    assert f.lowest_date == AS_OF + dt.timedelta(days=10)


def test_bookings_and_old_spend_are_left_out_of_the_average() -> None:
    history = _daily(100) + [
        make_txn(
            AS_OF - dt.timedelta(days=3),
            3200,
            "Fewa Lakeview Hotel",
            type=TxnType.BOOKING,
            service="hotel",
            category=Category.TRAVEL,
        ),
        make_txn(AS_OF - dt.timedelta(days=45), 9999, "Long ago", category=Category.SHOPPING),
    ]
    assert average_daily_spend(history, set(), AS_OF) == 100_00


def test_horizon_validation() -> None:
    with pytest.raises(ValueError):
        forecast_balance([], 0, AS_OF, AS_OF - dt.timedelta(days=1))


def test_seeded_forecasts(source: MockTransactionSource) -> None:
    f = month_end_forecast(source, USER, ANCHOR)
    assert f.horizon_end == dt.date(2026, 11, 30)
    assert f.current_balance_paisa == source.get_balance(USER)
    days = (f.horizon_end - ANCHOR).days
    # The projection is exactly: balance + scheduled items - daily average * days.
    assert f.projected_end_balance_paisa == (
        f.current_balance_paisa
        + sum(i.amount_paisa for i in f.scheduled)
        - f.avg_daily_spend_paisa * days
    )
    merchants = [i.merchant for i in f.scheduled]
    assert "Nepal Electricity Authority" in merchants and "Gurans Fibernet" in merchants

    week = balance_forecast(source, USER, ANCHOR, 7)
    assert len(week.points) == 7


# --- TransactionSource ---------------------------------------------------------------------


def test_source_filters(source: MockTransactionSource) -> None:
    all_txns = source.list_transactions(USER)
    food = source.list_transactions(USER, TransactionFilter(category=Category.FOOD))
    assert food and all(t.category is Category.FOOD for t in food)

    momo = source.list_transactions(USER, TransactionFilter(merchant="MOMO"))
    assert momo and all("momo" in t.merchant.lower() for t in momo)

    bills = source.list_transactions(USER, TransactionFilter(type=TxnType.BILL_PAYMENT))
    assert len(bills) == 12

    credits = source.list_transactions(USER, TransactionFilter(direction=Direction.CREDIT))
    assert credits and all(not t.is_debit for t in credits)

    mid = source.list_transactions(USER, TransactionFilter(min_paisa=1_000_00, max_paisa=2_000_00))
    assert mid and all(1_000_00 <= t.amount_paisa <= 2_000_00 for t in mid)

    one_day = all_txns[-1].occurred_at.date()
    same_day = source.list_transactions(USER, TransactionFilter(start=one_day, end=one_day))
    assert same_day and all(t.occurred_at.date() == one_day for t in same_day)  # end inclusive
    assert [t.occurred_at for t in all_txns] == sorted(t.occurred_at for t in all_txns)


def test_source_isolates_users(source: MockTransactionSource) -> None:
    txn = source.list_transactions(USER)[0]
    assert source.get_transaction(USER, txn.id) == txn
    assert source.get_transaction("someone_else", txn.id) is None
    assert source.list_transactions("someone_else") == []
    assert source.get_balance("someone_else") == 0
