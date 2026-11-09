from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.domain import Category, Direction, TxnType
from app.models import RecurringFeedback
from app.services.recurring import Cadence, _month_day, detect_recurring
from app.sources.mock import MockBillSource, MockDepositSource, MockTransactionSource
from tests.conftest import ANCHOR, USER, make_txn

BILL = TxnType.BILL_PAYMENT


def test_monthly_bill_with_varying_amount_follows_day_of_month() -> None:
    txns = [
        make_txn("2026-08-14", 1180.50, "NEA", type=BILL, service="electricity"),
        make_txn("2026-09-14", 1342.00, "NEA", type=BILL, service="electricity"),
        make_txn("2026-10-10", 1265.75, "NEA", type=BILL, service="electricity"),
    ]
    [s] = detect_recurring(txns, as_of=dt.date(2026, 11, 9))
    assert s.cadence is Cadence.MONTHLY and s.day_of_month == 14
    assert s.next_due == dt.date(2026, 11, 14)
    assert s.usual_amount_paisa == 126_575  # median
    assert s.occurrences == 3


def test_fixed_validity_pack_repeats_every_28_days() -> None:
    txns = [
        make_txn(d, 499, "Ncell", type=TxnType.TOPUP, service="data_pack")
        for d in ("2026-08-18", "2026-09-15", "2026-10-13")
    ]
    [s] = detect_recurring(txns, as_of=dt.date(2026, 11, 1))
    assert s.day_of_month is None and s.interval_days == 28
    assert s.next_due == dt.date(2026, 11, 10)
    assert s.following(s.next_due) == dt.date(2026, 12, 8)


def test_weekly_series() -> None:
    start = dt.date(2026, 10, 1)
    txns = [make_txn(start + dt.timedelta(days=7 * i), 300, "Weekly Class") for i in range(4)]
    [s] = detect_recurring(txns)
    assert s.cadence is Cadence.WEEKLY and s.next_due == start + dt.timedelta(days=28)


def test_not_recurring_cases() -> None:
    # only two payments
    assert (
        detect_recurring([make_txn("2026-09-01", 500, "A"), make_txn("2026-10-01", 500, "A")]) == []
    )
    # irregular gaps
    irregular = [make_txn(d, 500, "B") for d in ("2026-08-01", "2026-08-09", "2026-09-20")]
    assert detect_recurring(irregular) == []
    # weekly grocery runs whose amounts swing a lot are shopping, not a subscription
    swings = [
        make_txn(dt.date(2026, 10, 1) + dt.timedelta(days=7 * i), amt, "Ratna Mart")
        for i, amt in enumerate([400, 2900, 1200, 2600])
    ]
    assert detect_recurring(swings) == []
    # a series that stopped months ago
    old = [make_txn(d, 999, "Old Gym") for d in ("2026-03-01", "2026-04-01", "2026-05-01")]
    assert detect_recurring(old, as_of=dt.date(2026, 11, 1)) == []


def test_bills_tolerate_more_amount_variation_than_fixed_items() -> None:
    amounts = [1000, 1350, 1000]  # +35%: fine for a usage-based bill, not for a fixed item
    bill = [
        make_txn(d, a, "NEA", type=BILL, service="electricity")
        for d, a in zip(("2026-08-12", "2026-09-12", "2026-10-12"), amounts, strict=True)
    ]
    shop = [
        make_txn(d, a, "Gym")
        for d, a in zip(("2026-08-12", "2026-09-12", "2026-10-12"), amounts, strict=True)
    ]
    assert len(detect_recurring(bill)) == 1
    assert detect_recurring(shop) == []


def test_calendar_rollover_and_short_months() -> None:
    txns = [
        make_txn(d, 450, "Sajilo DTH", type=BILL, service="tv")
        for d in ("2026-10-31", "2026-11-28", "2026-12-31")
    ]
    [s] = detect_recurring(txns)
    assert s.day_of_month == 31
    assert s.next_due == dt.date(2027, 1, 31)
    assert s.following(s.next_due) == dt.date(2027, 2, 28)  # clamped
    assert _month_day(2028, 2, 31) == dt.date(2028, 2, 29)


def test_credits_are_detected_separately_from_debits() -> None:
    txns = [
        make_txn(d, 28000, "Sagarmatha Remit", type=TxnType.REMITTANCE, direction=Direction.CREDIT)
        for d in ("2026-09-01", "2026-10-02", "2026-11-03")
    ]
    [s] = detect_recurring(txns)
    assert s.direction is Direction.CREDIT


# --- seeded data -----------------------------------------------------------------------


EXPECTED_SERIES = {
    "Nepal Electricity Authority",
    "KUKL Khanepani",
    "Gurans Fibernet",
    "Sajilo DTH",
    "Ncell",
    "Smart Deposit - New laptop",
    "Sagarmatha Remit",
    "Sikshya Language Institute",
}


def test_seeded_recurring_series(source: MockTransactionSource) -> None:
    series = detect_recurring(source.list_transactions(USER), as_of=ANCHOR)
    assert {s.merchant for s in series} == EXPECTED_SERIES  # no cafés, marts or friends
    nea = next(s for s in series if s.merchant == "Nepal Electricity Authority")
    assert nea.next_due == dt.date(2026, 11, 14)


def test_bill_source_lists_upcoming_bills_and_respects_dismissals(
    seeded: Session, source: MockTransactionSource
) -> None:
    bills_src = MockBillSource(seeded, source)
    bills = bills_src.upcoming_bills(USER, ANCHOR, 30)
    names = [b.merchant for b in bills]
    assert "Smart Deposit - New laptop" not in names  # savings, not a bill
    assert "Sagarmatha Remit" not in names  # income
    assert names[0] == "Ncell"  # soonest first (due 10 Nov)
    assert [b.due_date for b in bills] == sorted(b.due_date for b in bills)
    assert all(b.category is not Category.SAVINGS for b in bills)

    ncell = bills[0]
    seeded.add(RecurringFeedback(user_id=USER, series_key=ncell.series_key, status="dismissed"))
    seeded.flush()
    assert "Ncell" not in [b.merchant for b in bills_src.upcoming_bills(USER, ANCHOR, 30)]


def test_deposit_source(source: MockTransactionSource) -> None:
    [plan] = MockDepositSource(source).smart_deposits(USER, ANCHOR)
    assert plan.installment_paisa == 2_000_00
    assert plan.total_deposited_paisa == 6_000_00
    assert plan.next_date is not None and plan.next_date > ANCHOR
