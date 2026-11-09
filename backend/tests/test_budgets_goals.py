from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.orm import Session

from app.domain import Category, Direction, TxnType
from app.periods import CalendarSystem, month_period
from app.services.budgets import (
    BudgetLevel,
    alerts_for,
    budget_statuses,
    evaluate_budget,
    level_for,
    spent_in_period,
)
from app.services.goals import GoalState, goal_progress
from app.sources.mock import MockTransactionSource
from tests.conftest import ANCHOR, USER, make_txn

# --- levels and alerts -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spent", "level", "alerts"),
    [
        (0, BudgetLevel.OK, ()),
        (7_999, BudgetLevel.OK, ()),  # 79.99%
        (8_000, BudgetLevel.WARNING, (80,)),  # exactly 80% -> amber + alert
        (10_000, BudgetLevel.WARNING, (80, 100)),  # exactly 100% is still amber, both alerts
        (10_001, BudgetLevel.OVER, (80, 100)),  # over 100% -> red
    ],
)
def test_levels_and_alerts(spent: int, level: BudgetLevel, alerts: tuple[int, ...]) -> None:
    assert level_for(spent, 10_000) is level
    assert alerts_for(spent, 10_000) == alerts


def test_evaluate_budget_pace_and_allowance() -> None:
    nov = month_period(dt.date(2026, 11, 10))
    s = evaluate_budget(
        limit_paisa=6_000_00,
        spent_paisa=2_500_00,
        period=nov,
        today=dt.date(2026, 11, 10),
        category=Category.FOOD,
    )
    assert s.remaining_paisa == 3_500_00
    assert s.days_left == 21  # 10th..30th inclusive
    assert s.daily_allowance_paisa == 3_500_00 // 21
    assert s.projected_spend_paisa == 2_500_00 * 30 // 10
    assert s.percent_used == 41.7


def test_evaluate_budget_over_limit_and_bad_limit() -> None:
    nov = month_period(dt.date(2026, 11, 1))
    s = evaluate_budget(
        limit_paisa=1_000_00, spent_paisa=1_250_00, period=nov, today=dt.date(2026, 11, 30)
    )
    assert s.remaining_paisa == -250_00 and s.daily_allowance_paisa == 0 and s.days_left == 1
    with pytest.raises(ValueError):
        evaluate_budget(limit_paisa=0, spent_paisa=0, period=nov, today=dt.date(2026, 11, 1))


def test_only_spending_counts() -> None:
    nov = month_period(dt.date(2026, 11, 1))
    txns = [
        make_txn("2026-11-02", 500, "Newa Momo House", category=Category.FOOD),
        make_txn("2026-11-03", 2000, "Friend", type=TxnType.TRANSFER, category=Category.TRANSFERS),
        make_txn(
            "2026-11-04", 2000, "Smart Deposit", type=TxnType.DEPOSIT, category=Category.SAVINGS
        ),
        make_txn("2026-11-05", 300, "Refund", direction=Direction.CREDIT, category=Category.FOOD),
        make_txn("2026-10-31", 999, "Old", category=Category.FOOD),  # previous month
    ]
    assert spent_in_period(txns, nov) == 500_00
    assert spent_in_period(txns, nov, Category.FOOD) == 500_00
    assert spent_in_period(txns, nov, Category.GROCERIES) == 0


def test_seeded_budget_statuses(seeded: Session, source: MockTransactionSource) -> None:
    statuses = budget_statuses(seeded, source, USER, ANCHOR)
    assert statuses[0].category is None  # overall first
    by_cat = {s.category: s for s in statuses}

    overall = by_cat[None]
    expected = sum(
        t.amount_paisa
        for t in source.list_transactions(USER)
        if t.is_spending and t.occurred_at.date() >= dt.date(2026, 11, 1)
    )
    assert overall.spent_paisa == expected
    assert overall.period.label == "Nov 2026"

    shopping = by_cat[Category.SHOPPING]  # a BS budget
    assert shopping.calendar is CalendarSystem.BS
    assert shopping.period.label == "Kartik 2083"
    expected_shop = sum(
        t.amount_paisa
        for t in source.list_transactions(USER)
        if t.category is Category.SHOPPING
        and dt.date(2026, 10, 18) <= t.occurred_at.date() <= dt.date(2026, 11, 16)
    )
    assert shopping.spent_paisa == expected_shop


# --- goals ---------------------------------------------------------------------------------


def test_goal_required_monthly_saving() -> None:
    g = goal_progress(
        target_paisa=1_20_000_00,
        saved_paisa=18_000_00,
        deadline=dt.date(2027, 9, 1),
        today=dt.date(2026, 11, 9),
    )
    assert g.state is GoalState.ACTIVE
    assert g.remaining_paisa == 1_02_000_00
    assert g.days_left == 296 and g.months_left == 10  # 9.7 months -> 10
    assert g.required_monthly_paisa == 10_200_00
    assert g.percent == 15.0


def test_goal_monthly_amount_rounds_up_to_whole_rupee() -> None:
    g = goal_progress(
        target_paisa=1_000_01,
        saved_paisa=0,
        deadline=dt.date(2027, 2, 1),
        today=dt.date(2026, 11, 9),
    )
    assert g.months_left == 3
    assert g.required_monthly_paisa == 334_00  # 333.34 -> 334
    assert g.required_monthly_paisa * g.months_left >= g.remaining_paisa


def test_goal_done_and_overdue() -> None:
    done = goal_progress(
        target_paisa=50_000_00,
        saved_paisa=52_000_00,
        deadline=dt.date(2027, 1, 1),
        today=dt.date(2026, 11, 9),
    )
    assert done.state is GoalState.DONE and done.required_monthly_paisa == 0
    assert done.percent == 100.0
    late = goal_progress(
        target_paisa=50_000_00,
        saved_paisa=40_000_50,
        deadline=dt.date(2026, 11, 1),
        today=dt.date(2026, 11, 9),
    )
    assert late.state is GoalState.OVERDUE and late.required_monthly_paisa == 10_000_00
    with pytest.raises(ValueError):
        goal_progress(
            target_paisa=0, saved_paisa=0, deadline=dt.date(2027, 1, 1), today=dt.date(2026, 11, 9)
        )
