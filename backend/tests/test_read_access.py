"""Settings, "Let O-Kay read my transactions" (step 12): on by default; off, every tool that
reads the user's money returns a note instead and O-Kay answers help questions only. Support
and blocking the wallet still work."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.ai.chat import ChatService
from app.ai.file_memory import FileMemory
from app.ai.tools import MONEY_TOOLS, NO_MONEY_ACCESS, ToolContext, run_tool
from app.domain import TxnStatus
from app.services.user_settings import load_settings, save_settings
from app.sources.mock import MockBillSource, MockTransactionSource
from tests.conftest import ANCHOR, USER
from tests.fake_llm import FakeLLM, call, say

ARGS = {
    "get_spending_summary": {},
    "get_transactions": {},
    "get_transaction_status": {"transaction_id": "txn_0001"},
    "get_budgets": {},
    "upsert_budget": {"category": "Groceries", "limit_amount": 5000},
    "get_goals": {},
    "upsert_goal": {"name": "Bike", "target_amount": 90000, "deadline": "2027-06-01"},
    "get_recurring_payments": {},
    "get_balance_forecast": {},
}


@pytest.fixture
def off(seeded: Session) -> ToolContext:
    source = MockTransactionSource(seeded)
    return ToolContext(seeded, source, MockBillSource(source), USER, ANCHOR, can_read_money=False)


def test_on_by_default(seeded: Session, make_client) -> None:
    assert load_settings(seeded, USER).read_transactions is True
    assert make_client().get("/me/settings").json()["read_transactions"] is True


@pytest.mark.parametrize("name", sorted(MONEY_TOOLS))
def test_off_the_money_tools_return_a_note(off: ToolContext, name: str) -> None:
    assert set(ARGS) == MONEY_TOOLS
    r = run_tool(off, name, ARGS[name])
    assert r.data == NO_MONEY_ACCESS and r.cards == []


def test_off_rules_and_help_still_answer(off: ToolContext) -> None:
    rules = run_tool(off, "get_wallet_rules", {"topic": "all"}).data
    assert rules["limits"]["Wallet to wallet"].startswith("Rs. 50,000 per transaction")
    assert rules["your_usage"] == NO_MONEY_ACCESS["note"]
    assert "balance_now" not in rules and "deposits_today" not in rules
    assert rules["overnight_balance_cap"] == "Rs. 50,000"
    assert run_tool(off, "search_help_articles", {"query": "lost phone"}).data["articles"]


def test_off_no_money_buttons_but_support_and_blocking_work(off: ToolContext) -> None:
    for flow in ("send_money", "bill_payment", "load_money", "request_money"):
        args = {"flow": flow, "amount": 500, "service": "electricity"}
        assert run_tool(off, "open_app_flow", args).cards == [], flow
    assert run_tool(off, "open_app_flow", {"flow": "block_wallet"}).cards[0].flow == "block_wallet"
    failed = next(t for t in off.source.list_transactions(USER) if t.status is TxnStatus.FAILED)
    support = run_tool(off, "open_app_flow", {"flow": "support", "transaction_id": failed.id})
    assert support.cards[0].flow == "support"
    assert support.cards[0].prefill.transaction_id is None  # attaching it would read the history


def test_the_chat_follows_the_setting(seeded: Session) -> None:
    s = load_settings(seeded, USER)
    save_settings(seeded, USER, s.model_copy(update={"read_transactions": False}))
    source = MockTransactionSource(seeded)
    llm = FakeLLM(
        call(("get_spending_summary", {"period": "this_month"})),
        say("I can't see your transactions now: turn it on in Settings."),
    )
    service = ChatService(
        seeded, llm, source, MockBillSource(source), USER, ANCHOR, files=FileMemory()
    )
    events = list(service.respond("How much did I spend this month?"))
    tool_message = llm.calls[1][0][-1]["content"]
    assert "turned off 'Let O-Kay read my transactions'" in tool_message
    assert events[-1].data["cards"] == []
    # A money-flow question gets no stand-in diagram either.
    llm2 = FakeLLM(say("I can't see your money now."))
    service2 = ChatService(
        seeded, llm2, source, MockBillSource(source), USER, ANCHOR, files=FileMemory()
    )
    flow = list(service2.respond("Show my money flow"))
    assert flow[-1].data["cards"] == []
