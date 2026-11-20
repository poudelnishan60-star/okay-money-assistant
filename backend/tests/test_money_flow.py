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
from app.models import ChatMessage, ToolCallLog
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


# --- the diagram is the answer: no words that repeat it ------------------------------------

LONG = "Money in Rs. 29,500. Remittance Rs. 27,500. Groceries Rs. 6,999.60. Left over Rs. 1."


def _shown(events: list) -> str:  # type: ignore[type-arg]
    return "".join(e.data["text"] for e in events if e.event == "token")


def _stored(session: Session) -> str:
    rows = session.scalars(select(ChatMessage).where(ChatMessage.role == "assistant")).all()
    return rows[-1].content


@pytest.mark.parametrize(
    ("question", "caption"),
    [
        ("Show my money flow", "Here's where your money came from and where it went."),
        ("मेरो पैसाको आवतजावत देखाऊ", "तपाईंको पैसा कहाँबाट आयो र कहाँ गयो, तल हेर्नुहोस्।"),
        (
            "Mero paisa kaha bata aayo, kaha gayo?",
            "Tapai ko paisa kaha bata aayo ra kaha gayo, tala hernus.",
        ),
    ],
)
def test_a_flow_answer_is_the_diagram_with_one_fixed_line(
    seeded: Session, question: str, caption: str
) -> None:
    # Seen live: the words listed every line of the diagram. They are never shown now.
    llm = FakeLLM(call(("get_spending_summary", {"period": "this_month"})), say(LONG))
    events = list(_service(seeded, llm).respond(question))
    assert _shown(events) == caption  # nothing else was ever streamed
    assert "reset" not in [e.event for e in events]
    assert "status" in [e.event for e in events]  # the app still shows it's working
    assert "money_flow" in _cards(events)
    assert _stored(seeded) == caption


def test_the_spending_tool_gives_the_flow_for_a_flow_question(seeded: Session) -> None:
    # Seen live: "Show my money flow" came with category=Shopping and no group_by.
    args = {"period": "last_month", "category": "Shopping"}
    llm = FakeLLM(call(("get_spending_summary", args)), say(LONG))
    events = list(_service(seeded, llm).respond("Show my money flow"))
    flow = next(c for c in events[-1].data["cards"] if c["type"] == "money_flow")
    assert flow["period_label"] != "This month"  # the period the model chose is kept
    logged = seeded.scalars(select(ToolCallLog.arguments_json)).all()
    assert '"group_by": "flow"' in logged[-1] and "Shopping" not in logged[-1]


def test_no_data_for_the_period_asked_shows_the_words_not_a_guessed_diagram(
    seeded: Session,
) -> None:
    month = f"{ANCHOR.year - 2}-01"
    llm = FakeLLM(
        call(("get_spending_summary", {"period": "month", "month": month})),
        say("I don't have that data."),
    )
    events = list(_service(seeded, llm).respond(f"Money flow for {month}"))
    assert "money_flow" not in _cards(events)
    assert _shown(events) == "I don't have that data."


@pytest.mark.parametrize(
    ("question", "diagram"),
    [
        ("Show my money flow", True),  # this month: safe to look up
        ("Show my money flow for last month", False),  # never guessed as this month
        ("गत महिनाको पैसाको आवतजावत", False),
    ],
)
def test_with_nothing_looked_up_the_diagram_is_only_this_months(
    seeded: Session, question: str, diagram: bool
) -> None:
    llm = FakeLLM(say("You had money coming in and going out."))  # no tool at all
    events = list(_service(seeded, llm).respond(question))
    assert ("money_flow" in _cards(events)) is diagram
    assert _shown(events) == (
        "Here's where your money came from and where it went."
        if diagram
        else "You had money coming in and going out."
    )


def test_a_busy_ai_still_says_so(seeded: Session) -> None:
    from app.ai.llm import LLMBusyError

    llm = FakeLLM(LLMBusyError("busy"))
    events = list(_service(seeded, llm).respond("Show my money flow"))
    assert _shown(events) == "O-Kay is busy, please try again in a minute."
    assert events[-1].data["error"] == "busy"


def test_a_typed_mpin_warning_stays_above_the_diagram(seeded: Session) -> None:
    llm = FakeLLM(call(("get_spending_summary", {})), say(LONG))
    events = list(_service(seeded, llm).respond("my mpin is 4821, show my money flow"))
    shown = _shown(events)
    assert shown.endswith("Here's where your money came from and where it went.")
    assert "4821" not in shown and "Rs." not in shown
    assert len(shown) > len("Here's where your money came from and where it went.")


def test_a_file_flow_question_gets_the_files_line(seeded: Session) -> None:
    files = FileMemory()
    files.remember(USER, [read(STATEMENT, FakeLLM())])
    llm = FakeLLM(say("Most came from loads: Rs. 5,000."))
    events = list(_service(seeded, llm, files).respond("Money flow in the file"))
    assert _shown(events) == "Here's where the file's money came from and where it went."
    (card,) = events[-1].data["cards"]
    assert card["sections"] == ["flow"]


def test_where_did_most_of_my_money_go_keeps_its_words(seeded: Session) -> None:
    # Not a flow question: it wants the biggest uses, in words.
    llm = FakeLLM(call(("get_spending_summary", {"period": "this_month"})), say("Groceries."))
    events = list(_service(seeded, llm).respond("Where did most of my money go?"))
    assert _shown(events) == "Groceries."


def test_file_flow_words_are_checked_when_the_account_was_used_instead(seeded: Session) -> None:
    # The model looked at the account, so no file chart is shown: its words are shown, and
    # checked like any answer (a made-up amount is corrected).
    files = FileMemory()
    files.remember(USER, [read(STATEMENT, FakeLLM())])
    llm = FakeLLM(
        call(("get_spending_summary", {"period": "this_month"})),
        say("You got Rs. 99,999."),  # made up
        say("Your account shows money in and out."),
    )
    events = list(_service(seeded, llm, files).respond("Money flow in the file"))
    assert "file_report" not in _cards(events)
    assert _shown(events) == "Your account shows money in and out."


def test_other_questions_get_the_categories_not_the_flow(seeded: Session) -> None:
    # Seen live: "where did my money go?" got the flow view, though it has its own category
    # pie. The flow view is for flow questions only.
    llm = FakeLLM(
        call(("get_spending_summary", {"period": "this_month", "group_by": "flow"})),
        say("Groceries took the most."),
    )
    events = list(_service(seeded, llm).respond("Where did my money go?"))
    assert _cards(events) == ["spending_summary", "category_breakdown"]
    logged = seeded.scalars(select(ToolCallLog.arguments_json)).all()
    assert '"group_by": "category"' in logged[-1]
