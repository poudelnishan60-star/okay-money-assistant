"""Pure tests for the insights service and the bills (confirm/dismiss) service."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.orm import Session

from app.domain import Category, Direction, TxnType
from app.periods import custom_period, month_period, previous_period
from app.services.bills import BillStatus, bill_id, list_bills, set_bill_status
from app.services.insights import (
    Severity,
    build_highlights,
    summarize,
    unusual_spending,
)
from app.sources.mock import MockBillSource, MockTransactionSource
from tests.conftest import ANCHOR, USER, make_txn

OCT = month_period(dt.date(2026, 10, 1))
SEP = month_period(dt.date(2026, 9, 1))
NOV = month_period(dt.date(2026, 11, 1))


def test_summary_of_a_finished_month() -> None:
    txns = [
        make_txn("2026-09-10", 1000, "Ratna Mart", category=Category.GROCERIES),
        make_txn("2026-10-02", 600, "Newa Momo House", category=Category.FOOD),
        make_txn("2026-10-02", 400, "Newa Momo House", category=Category.FOOD),
        make_txn("2026-10-20", 1500, "Ratna Mart", category=Category.GROCERIES),
        make_txn("2026-10-21", 5000, "Friend", type=TxnType.TRANSFER, category=Category.TRANSFERS),
        make_txn(
            "2026-10-22",
            28000,
            "Remit",
            type=TxnType.REMITTANCE,
            direction=Direction.CREDIT,
            category=Category.REMITTANCE,
        ),
    ]
    s = summarize(txns, OCT, SEP, today=dt.date(2026, 11, 9))
    assert not s.in_progress and s.comparison_basis == "full_period"
    assert s.total_spent_paisa == 2_500_00  # the transfer is not spending
    assert s.previous_compare_paisa == 1_000_00
    assert s.change_percent == 150.0
    assert s.income_paisa == 28_000_00 == s.money_in_paisa
    assert [(c.category, c.spent_paisa, c.share_percent) for c in s.by_category] == [
        (Category.GROCERIES, 1_500_00, 60.0),
        (Category.FOOD, 1_000_00, 40.0),
    ]
    assert s.by_category[0].previous_spent_paisa == 1_000_00
    assert s.top_merchants[0].merchant == "Ratna Mart"
    newa = s.top_merchants[1]
    assert (newa.merchant, newa.count, newa.spent_paisa) == ("Newa Momo House", 2, 1_000_00)
    assert len(s.daily) == 31 and sum(d.spent_paisa for d in s.daily) == 2_500_00


def test_summary_in_progress_compares_the_same_days() -> None:
    txns = [
        make_txn("2026-10-03", 700, "A", category=Category.FOOD),
        make_txn("2026-10-25", 9000, "B", category=Category.SHOPPING),  # later in October
        make_txn("2026-11-02", 1400, "A", category=Category.FOOD),
    ]
    s = summarize(txns, NOV, OCT, today=dt.date(2026, 11, 9))
    assert s.in_progress and s.comparison_basis == "same_days"
    assert s.covered_end == dt.date(2026, 11, 9) and len(s.daily) == 9
    assert s.previous_compare_paisa == 700_00  # only Oct 1-9
    assert s.previous_total_spent_paisa == 9_700_00
    assert s.change_percent == 100.0
    # Shopping on Oct 25 is outside the same-days window, so it is not in the comparison
    assert all(c.category is not Category.SHOPPING for c in s.by_category)


def test_change_percent_is_none_without_a_base() -> None:
    s = summarize(
        [make_txn("2026-10-03", 700, "A", category=Category.FOOD)],
        OCT,
        SEP,
        today=dt.date(2026, 11, 9),
    )
    assert s.change_percent is None


def _baseline(days: int, rupees_per_day: int, category: Category, end: dt.date):
    return [
        make_txn(end - dt.timedelta(days=i), rupees_per_day, f"M{i}", category=category)
        for i in range(days)
    ]


def test_unusual_spending_flags_2x() -> None:
    base = _baseline(60, 100, Category.FOOD, dt.date(2026, 9, 30))  # Rs 100/day "usual"
    october = [
        make_txn(dt.date(2026, 10, d), 250, f"N{d}", category=Category.FOOD) for d in range(1, 11)
    ]  # Rs 250/day for 10 days
    [u] = unusual_spending(base + october, OCT, today=dt.date(2026, 10, 10))
    assert (u.category, u.current_paisa, u.usual_paisa, u.ratio) == (
        Category.FOOD,
        2_500_00,
        1_000_00,
        2.5,
    )


def test_unusual_spending_ignores_small_and_recurring_and_thin_history() -> None:
    base = _baseline(60, 100, Category.FOOD, dt.date(2026, 9, 30))
    # 1.5x is not unusual
    mild = [
        make_txn(dt.date(2026, 10, d), 150, f"N{d}", category=Category.FOOD) for d in range(1, 11)
    ]
    assert unusual_spending(base + mild, OCT, today=dt.date(2026, 10, 10)) == []
    # 3x but only Rs 200 above usual: too small to mention
    tiny = _baseline(60, 1, Category.HEALTH, dt.date(2026, 9, 30))
    tiny += [make_txn("2026-10-05", 300, "Pharmacy", category=Category.HEALTH)]
    assert unusual_spending(tiny, OCT, today=dt.date(2026, 10, 10)) == []
    # a monthly class fee paid early in the month is expected, not unusual
    fee = [
        make_txn(d, 3500, "Language Institute", category=Category.EDUCATION)
        for d in ("2026-08-05", "2026-09-05", "2026-10-05")
    ]
    assert unusual_spending(base + fee, OCT, today=dt.date(2026, 10, 6)) == []
    # under two weeks of history: no flags at all
    short = _baseline(10, 100, Category.FOOD, dt.date(2026, 9, 30)) + october_spike()
    assert unusual_spending(short, OCT, today=dt.date(2026, 10, 10)) == []


def october_spike():
    return [make_txn("2026-10-03", 9000, "Digital Ghar", category=Category.SHOPPING)]


def test_new_spending_with_no_history_in_that_category() -> None:
    base = _baseline(60, 100, Category.FOOD, dt.date(2026, 9, 30))
    [u] = unusual_spending(base + october_spike(), OCT, today=dt.date(2026, 10, 10))
    assert (u.category, u.ratio, u.usual_paisa) == (Category.SHOPPING, None, 0)


def test_highlights_order_and_text() -> None:
    base = _baseline(60, 100, Category.FOOD, dt.date(2026, 9, 30))
    october = [
        make_txn(dt.date(2026, 10, d), 250, f"N{d}", category=Category.FOOD) for d in range(1, 32)
    ]
    txns = base + october
    s = summarize(txns, OCT, SEP, today=dt.date(2026, 11, 9))
    hl = build_highlights(s, unusual_spending(txns, OCT, dt.date(2026, 11, 9)))
    assert [h.kind for h in hl] == [
        "unusual_category",
        "month_over_month",
        "top_category",
        "top_merchant",
    ]
    assert hl[0].severity is Severity.WARNING
    assert (
        hl[0].message == "Food & Dining is at 2.5x its usual level: Rs. 7,750 vs about Rs. 3,100."
    )
    assert "Sep 2026" in hl[1].message


# --- bills service ---------------------------------------------------------------------------


def test_bill_ids_are_stable_and_short() -> None:
    assert bill_id("debit:electricity:nepal electricity authority") == bill_id(
        "debit:electricity:nepal electricity authority"
    )
    assert len(bill_id("x")) == 12


def test_dismiss_confirm_and_undo(seeded: Session, source: MockTransactionSource) -> None:
    bills = MockBillSource(source)
    views = list_bills(seeded, bills, USER, ANCHOR)
    assert {v.status for v in views} == {BillStatus.DETECTED}
    ncell = views[0]
    assert ncell.bill.merchant == "Ncell" and ncell.days_until_due == 1 and not ncell.overdue

    set_bill_status(seeded, bills, USER, ANCHOR, ncell.id, BillStatus.DISMISSED)
    assert ncell.id not in {v.id for v in list_bills(seeded, bills, USER, ANCHOR)}
    hidden = list_bills(seeded, bills, USER, ANCHOR, include_dismissed=True)
    assert next(v for v in hidden if v.id == ncell.id).status is BillStatus.DISMISSED

    set_bill_status(seeded, bills, USER, ANCHOR, ncell.id, BillStatus.DETECTED)  # undo
    assert ncell.id in {v.id for v in list_bills(seeded, bills, USER, ANCHOR)}

    set_bill_status(seeded, bills, USER, ANCHOR, ncell.id, BillStatus.CONFIRMED)
    assert list_bills(seeded, bills, USER, ANCHOR)[0].status is BillStatus.CONFIRMED

    with pytest.raises(LookupError):
        set_bill_status(seeded, bills, USER, ANCHOR, "nope", BillStatus.CONFIRMED)


def test_previous_and_custom_periods() -> None:
    c = custom_period(dt.date(2026, 10, 10), dt.date(2026, 10, 19))
    p = previous_period(c, None)
    assert (p.start, p.end, p.days) == (dt.date(2026, 9, 30), dt.date(2026, 10, 9), 10)
    with pytest.raises(ValueError):
        custom_period(dt.date(2026, 10, 10), dt.date(2026, 10, 1))
