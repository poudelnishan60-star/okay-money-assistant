"""Tools on the seeded data: numbers match the services, PII never reaches the model,
proposals are not saved, app flows never move money."""

from __future__ import annotations

import datetime as dt
import json
import re

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.tools import TOOLS, ToolContext, ToolError, openai_tool_specs, run_tool
from app.domain import Category
from app.models import Budget, Goal
from app.money import format_npr
from app.periods import month_period
from app.services.forecast import month_end_forecast
from app.services.insights import summarize
from app.sources.base import TransactionFilter
from app.sources.mock import MockBillSource, MockTransactionSource
from tests.conftest import ANCHOR, USER


@pytest.fixture
def ctx(seeded: Session) -> ToolContext:
    source = MockTransactionSource(seeded)
    return ToolContext(seeded, source, MockBillSource(source), USER, ANCHOR)


def _no_pii(data: object) -> None:
    text = json.dumps(data, ensure_ascii=False)
    assert not re.search(r"9[678]\d{8}", text), "phone number leaked"
    assert not re.search(r"\b(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{11}\b", text), "reference"
    assert "SRN" not in text and "0010" not in text


def test_tool_specs_are_valid_json_schema() -> None:
    specs = openai_tool_specs()
    assert {s["function"]["name"] for s in specs} == {
        "get_spending_summary",
        "get_transactions",
        "get_budgets",
        "upsert_budget",
        "get_goals",
        "upsert_goal",
        "get_recurring_payments",
        "get_balance_forecast",
        "search_help_articles",
        "open_app_flow",
    }
    json.dumps(specs)  # serializable
    assert all(s["function"]["parameters"]["type"] == "object" for s in specs)


def test_spending_summary_matches_the_insights_service(ctx: ToolContext) -> None:
    r = run_tool(ctx, "get_spending_summary", {"period": "this_month"})
    nov = month_period(ANCHOR)
    oct_ = month_period(dt.date(2026, 10, 1))
    txns = ctx.source.list_transactions(USER, TransactionFilter(start=dt.date(2026, 8, 1)))
    s = summarize(txns, nov, oct_, ANCHOR)
    assert r.data["total_spent"] == format_npr(s.total_spent_paisa)
    assert r.data["compared_with"] == "the same days of Oct 2026"
    assert r.data["change"] == "64.7% less"
    summary_card, breakdown = r.cards
    assert summary_card.total_paisa == s.total_spent_paisa
    assert summary_card.link.filters["spending_only"] is True
    assert summary_card.link.count == s.transaction_count
    assert sum(i.spent_paisa for i in breakdown.items) == s.total_spent_paisa
    _no_pii(r.data)


def test_spending_summary_for_one_category_in_romanized_question_style(ctx: ToolContext) -> None:
    r = run_tool(ctx, "get_spending_summary", {"period": "this_month", "category": "Food & Dining"})
    food = [
        t
        for t in ctx.source.list_transactions(
            USER, TransactionFilter(start=dt.date(2026, 11, 1), category=Category.FOOD)
        )
        if t.is_debit
    ]
    assert r.data["spent"] == format_npr(sum(t.amount_paisa for t in food))
    assert r.data["transactions"] == len(food)
    assert r.cards[0].link.filters == {
        "start": "2026-11-01",
        "end": "2026-11-09",
        "category": "Food & Dining",
        "direction": "debit",
    }


def test_past_month_flags_unusual_spending_and_bs_months_work(ctx: ToolContext) -> None:
    oct_ = run_tool(ctx, "get_spending_summary", {"period": "month", "month": "2026-10"})
    assert oct_.data["unusual_spending"][0]["category"] == "Shopping"
    assert oct_.data["unusual_spending"][0]["times_usual"] == "6.9x"
    kartik = run_tool(
        ctx, "get_spending_summary", {"period": "month", "month": "2083-07", "calendar": "BS"}
    )
    assert kartik.data["period"] == "Kartik 2083"


def test_get_transactions_hides_pii_and_counts_right(ctx: ToolContext) -> None:
    r = run_tool(ctx, "get_transactions", {"period": "last_30_days", "type": "transfer"})
    expected = ctx.source.list_transactions(
        USER, TransactionFilter(start=ANCHOR - dt.timedelta(days=29), end=ANCHOR)
    )
    transfers = [t for t in expected if t.type.value == "transfer"]
    assert r.data["count"] == len(transfers)
    assert len(r.data["latest"]) <= 10
    _no_pii(r.data)
    assert r.cards[0].link.filters["type"] == "transfer"


def test_injection_remark_reaches_the_model_only_as_data(ctx: ToolContext) -> None:
    r = run_tool(
        ctx,
        "get_transactions",
        {"period": "custom", "start": "2026-08-11", "end": "2026-11-08", "direction": "credit"},
    )
    notes = [i["note"] for i in r.data["latest"]] + [""]
    # it is just a string field; no tags or markup that could break out of the tool result
    assert all("<" not in (n or "") and ">" not in (n or "") for n in notes)


def test_upsert_budget_proposes_but_never_saves(ctx: ToolContext) -> None:
    before = ctx.session.scalar(select(func.count()).select_from(Budget))
    r = run_tool(ctx, "upsert_budget", {"category": "Food & Dining", "limit_amount": 6000})
    assert ctx.session.scalar(select(func.count()).select_from(Budget)) == before
    card = r.cards[0]
    assert card.type == "confirm_action" and card.title == "Set Food & Dining budget"
    assert card.request.model_dump() == {
        "method": "POST",
        "path": "/budgets",
        "body": {"category": "Food & Dining", "limit_paisa": 6_000_00, "calendar": "AD"},
    }
    assert r.data["status"].startswith("NOT SAVED YET")

    change = run_tool(ctx, "upsert_budget", {"category": "Groceries", "limit_amount": 10000})
    assert change.cards[0].title == "Change Groceries budget"
    assert change.data["current_limit"] == "Rs. 9,000"

    with pytest.raises(ToolError, match="spending categories"):
        run_tool(ctx, "upsert_budget", {"category": "Transfers", "limit_amount": 100})


def test_upsert_goal_validates_and_proposes(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="after today"):
        run_tool(
            ctx, "upsert_goal", {"name": "Bike", "target_amount": 200000, "deadline": "2026-01-01"}
        )
    with pytest.raises(ToolError, match="no goal"):
        run_tool(
            ctx,
            "upsert_goal",
            {"name": "x", "target_amount": 1, "deadline": "2027-12-01", "goal_id": 999},
        )
    before = ctx.session.scalar(select(func.count()).select_from(Goal))
    r = run_tool(
        ctx,
        "upsert_goal",
        {"name": "Dashain trip", "target_amount": 25000, "deadline": "2027-09-15"},
    )
    assert ctx.session.scalar(select(func.count()).select_from(Goal)) == before
    assert r.cards[0].request.method == "POST"
    assert r.data["needs_per_month"] == "Rs. 2,273"  # 25,000 over 11 months, rounded up


def test_bills_forecast_and_goals(ctx: ToolContext) -> None:
    bills = run_tool(ctx, "get_recurring_payments", {})
    assert bills.data["bills"][0]["merchant"] == "Ncell"
    assert bills.data["bills"][0]["due"] == "in 1 days"
    assert bills.cards[0].items[0].usual_amount_paisa == 499_00

    f = run_tool(ctx, "get_balance_forecast", {})
    expected = month_end_forecast(ctx.source, USER, ANCHOR)
    assert f.data["projected_balance_at_end"] == format_npr(expected.projected_end_balance_paisa)
    assert f.cards == []

    goals = run_tool(ctx, "get_goals", {})
    assert [g["name"] for g in goals.data["goals"]] == ["New laptop", "Emergency fund"]
    assert goals.data["goals"][0]["needs_per_month"] == "Rs. 10,200"


def test_help_search(ctx: ToolContext) -> None:
    r = run_tool(ctx, "search_help_articles", {"query": "I forgot my MPIN"})
    assert r.data["articles"][0]["question"].startswith("I forgot my MPIN")
    assert run_tool(ctx, "search_help_articles", {"query": "zzzz"}).data["articles"] == []


def test_open_app_flow_prefills_and_never_pays(ctx: ToolContext) -> None:
    r = run_tool(ctx, "open_app_flow", {"flow": "bill_payment", "service": "electricity"})
    card = r.cards[0]
    assert card.type == "open_app_flow" and card.title == "Pay electricity bill"
    assert card.prefill.biller_name == "Nepal Electricity Authority"
    assert card.prefill.amount_paisa == 1_140_67  # the usual (median) NEA amount
    assert "NOTHING has been paid" in r.data["status"]
    with pytest.raises(ToolError):
        run_tool(ctx, "open_app_flow", {"flow": "bill_payment"})

    laptop = ctx.session.scalar(select(Goal).where(Goal.name == "New laptop"))
    sd = run_tool(ctx, "open_app_flow", {"flow": "smart_deposit", "goal_id": laptop.id})
    assert sd.cards[0].prefill.monthly_amount_paisa == 10_200_00


def test_bad_calls_come_back_as_tool_errors(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="unknown tool"):
        run_tool(ctx, "transfer_money", {})
    with pytest.raises(ToolError, match="invalid arguments"):
        run_tool(ctx, "get_spending_summary", {"period": "forever"})
    with pytest.raises(ToolError, match="needs month"):
        run_tool(ctx, "get_spending_summary", {"period": "month"})
    assert set(TOOLS) == {s["function"]["name"] for s in openai_tool_specs()}


def test_budget_category_must_be_explicit(ctx: ToolContext) -> None:
    """A dropped category must never silently become the overall budget."""
    with pytest.raises(ToolError, match="category"):
        run_tool(ctx, "upsert_budget", {"limit_amount": 6000})
    overall = run_tool(ctx, "upsert_budget", {"category": "Overall", "limit_amount": 35000})
    assert overall.cards[0].request.body["category"] is None
    assert overall.cards[0].title == "Change Overall budget"
    spec = next(s for s in openai_tool_specs() if s["function"]["name"] == "upsert_budget")
    assert spec["function"]["parameters"]["required"] == ["category", "limit_amount"]
