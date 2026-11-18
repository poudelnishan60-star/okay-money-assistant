"""The money-flow view of the account (get_spending_summary group_by=flow): every credit by
source and every debit by use, worked out in code, with both sides adding up."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.attachments import read
from app.ai.chat import ChatService
from app.ai.file_memory import FileMemory
from app.ai.tools import ToolContext, openai_tool_specs, run_tool
from app.domain import NON_SPENDING
from app.models import ToolCallLog
from app.money import format_npr
from app.sources.base import TransactionFilter
from app.sources.mock import MockBillSource, MockTransactionSource
from tests.conftest import ANCHOR, USER
from tests.fake_llm import FakeLLM, call, say
from tests.test_file_answers import STATEMENT


@pytest.fixture
def ctx(seeded: Session) -> ToolContext:
    source = MockTransactionSource(seeded)
    return ToolContext(seeded, source, MockBillSource(source), USER, ANCHOR)


def test_the_model_can_ask_for_the_flow() -> None:
    spec = next(s for s in openai_tool_specs() if s["function"]["name"] == "get_spending_summary")
    assert "flow" in spec["function"]["parameters"]["properties"]["group_by"]["enum"]
    assert "group_by=flow" in spec["function"]["description"]


def test_money_flow_matches_every_transaction_of_the_period(ctx: ToolContext) -> None:
    result = run_tool(ctx, "get_spending_summary", {"period": "last_30_days", "group_by": "flow"})
    assert [c.type for c in result.cards] == ["spending_summary", "money_flow"]  # type: ignore[attr-defined]
    card = result.cards[1]
    flow = card.flow  # type: ignore[attr-defined]

    period = card.link.filters  # type: ignore[attr-defined]
    txns = ctx.source.list_transactions(USER, TransactionFilter())
    inside = [
        t for t in txns if period["start"] <= t.occurred_at.date().isoformat() <= period["end"]
    ]
    credits = sum(t.amount_paisa for t in inside if not t.is_debit)
    debits = sum(t.amount_paisa for t in inside if t.is_debit)
    spent = sum(t.amount_paisa for t in inside if t.is_debit and t.category not in NON_SPENDING)
    assert (flow.money_in_paisa, flow.money_out_paisa) == (credits, debits)
    assert card.link.count == len(inside)  # type: ignore[attr-defined]

    # Both sides add up to the same total, evened by the balance.
    assert sum(i.paisa for i in flow.sources) == sum(i.paisa for i in flow.uses)
    assert sum(i.paisa for i in flow.uses if i.kind == "out") == spent
    kinds = {i.label: i.kind for i in [*flow.sources, *flow.uses]}
    assert kinds["Remittance"] == "in"
    assert kinds.get("Transfers out", "moved") == "moved"
    assert kinds.get("Smart Deposit", "moved") == "moved"
    assert len([i for i in flow.uses if i.kind == "out"]) <= 5  # four biggest + the rest

    # What the model reads: the same figures, already formatted (it never adds them up).
    data = result.data
    assert data["money_in"] == format_npr(credits)
    assert data["money_out"] == format_npr(debits)
    assert {u["use"] for u in data["money_out_by_use"]} == {
        i.label for i in flow.uses if i.kind != "balance"
    }
    if credits > debits:
        assert data["left_over"] == format_npr(credits - debits)
    elif debits > credits:
        assert data["taken_from_balance"] == format_npr(debits - credits)


def test_the_usual_summary_has_no_flow(ctx: ToolContext) -> None:
    result = run_tool(ctx, "get_spending_summary", {"period": "this_month"})
    assert "money_flow" not in [c.type for c in result.cards]  # type: ignore[attr-defined]
    assert "money_in_by_source" not in result.data


def test_a_month_before_the_history_has_no_flow(ctx: ToolContext) -> None:
    month = f"{ANCHOR.year - 2}-01"
    result = run_tool(
        ctx, "get_spending_summary", {"period": "month", "month": month, "group_by": "flow"}
    )
    assert result.cards == []


def test_flow_is_the_whole_account_even_if_a_category_is_given(ctx: ToolContext) -> None:
    # Seen live: "Show my money flow" came with category=Shopping and got no flow.
    result = run_tool(ctx, "get_spending_summary", {"group_by": "flow", "category": "Shopping"})
    assert "money_flow" in [c.type for c in result.cards]  # type: ignore[attr-defined]


# --- in the chat ------------------------------------------------------------------------------


def _service(session: Session, llm: FakeLLM, files: FileMemory | None = None) -> ChatService:
    source = MockTransactionSource(session)
    return ChatService(
        session, llm, source, MockBillSource(source), USER, ANCHOR, files=files or FileMemory()
    )


def _cards(events: list) -> list[str]:  # type: ignore[type-arg]
    return [c["type"] for c in events[-1].data["cards"]]


@pytest.mark.parametrize(
    "question",
    ["मेरो पैसाको आवतजावत देखाऊ", "Show my money flow", "Mero paisa kaha bata aayo, kaha gayo?"],
)
def test_a_flow_question_gets_the_diagram_even_if_the_model_looks_elsewhere(
    seeded: Session, question: str
) -> None:
    # Seen live: a Nepali flow question went to get_transactions, so no diagram.
    llm = FakeLLM(call(("get_transactions", {"period": "last_7_days"})), say("Here it is."))
    events = list(_service(seeded, llm).respond(question))
    assert _cards(events) == ["transactions_preview", "money_flow"]
    # Same period as the card the model got; logged like any tool call.
    flow = events[-1].data["cards"][1]
    preview = events[-1].data["cards"][0]
    assert flow["link"]["filters"]["start"] == preview["link"]["filters"]["start"]
    logged = seeded.scalars(select(ToolCallLog.arguments_json)).all()
    assert any('"group_by": "flow"' in a for a in logged)


def test_where_did_my_money_go_keeps_its_categories_only(seeded: Session) -> None:
    llm = FakeLLM(call(("get_spending_summary", {"period": "this_month"})), say("Here it is."))
    events = list(_service(seeded, llm).respond("Where did my money go?"))
    assert _cards(events) == ["spending_summary", "category_breakdown"]


def test_no_account_flow_added_when_the_question_is_about_a_file(seeded: Session) -> None:
    files = FileMemory()
    files.remember(USER, [read(STATEMENT, FakeLLM())])
    llm = FakeLLM(say("Most came from loads."))
    events = list(_service(seeded, llm, files).respond("Money flow in the file"))
    assert _cards(events) == ["file_report"]
