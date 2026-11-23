"""Khalti's wallet rules (step 10): the rules as data, the user's usage worked out in code,
get_wallet_rules, the limit and KYC checks before any open_app_flow button, and the prompt
that sends the model to the tool instead of quoting limits itself."""

from __future__ import annotations

import datetime as dt
import itertools
import json
import re

import pytest
from sqlalchemy.orm import Session

from app.ai.chat import ChatService
from app.ai.file_memory import FileMemory
from app.ai.prompt import system_prompt
from app.ai.safety import Lang
from app.ai.tools import ToolContext, run_tool
from app.domain import Category, Direction, KycStatus, TxnType
from app.models import TransactionRow, User
from app.money import format_npr
from app.rules import (
    FLOW_LIMITS,
    LAST_CHECKED,
    LIMITS,
    NO_LIMIT_SERVICES,
    OVERNIGHT_BALANCE_CAP_PAISA,
    SOURCE,
    Limit,
)
from app.services.wallet_limits import LimitUse, check_amount, usage
from app.sources.base import TransactionFilter
from app.sources.mock import MockBillSource, MockTransactionSource
from tests.conftest import ANCHOR, USER
from tests.fake_llm import FakeLLM, call, say

NOW = dt.datetime.combine(ANCHOR, dt.time(10))  # "today" in the tests is ANCHOR


@pytest.fixture
def ctx(seeded: Session) -> ToolContext:
    source = MockTransactionSource(seeded)
    return ToolContext(seeded, source, MockBillSource(source), USER, ANCHOR)


_ids = itertools.count(1)


def _add(
    session: Session,
    rupees: int,
    *,
    when: dt.datetime = NOW,
    type: TxnType = TxnType.TRANSFER,
    direction: Direction = Direction.DEBIT,
    service: str | None = None,
    merchant: str = "Sita Rai",
) -> None:
    """A transaction today, keeping the running balance right."""
    balance = MockTransactionSource(session).get_balance(USER)
    paisa = rupees * 100
    session.add(
        TransactionRow(
            id=f"x_{next(_ids)}",
            user_id=USER,
            occurred_at=when,
            type=type.value,
            direction=direction.value,
            amount_paisa=paisa,
            merchant=merchant,
            merchant_key=merchant.lower(),
            service=service,
            balance_after_paisa=balance + (paisa if direction is Direction.CREDIT else -paisa),
            category=Category.TRANSFERS.value,
            category_source="rule_type",
        )
    )
    session.commit()


def _set_kyc(session: Session, status: KycStatus) -> None:
    session.get(User, USER).kyc_status = status.value
    session.commit()


# --- the rules as data ------------------------------------------------------------------------


def test_the_rules_hold_the_values_from_the_source() -> None:
    assert SOURCE.startswith("Khalti Terms & Conditions and Transaction Limits page")
    assert dt.date(2026, 11, 20) == LAST_CHECKED
    assert OVERNIGHT_BALANCE_CAP_PAISA == 50_000_00

    def rs(lim: Limit) -> tuple[str, str, str, str]:
        return (
            format_npr(lim.per_txn_paisa),
            format_npr(lim.per_day_paisa),
            format_npr(lim.per_month_paisa),
            format_npr(lim.min_paisa),
        )

    assert rs(LIMITS["merchant_payment"]) == (
        "Rs. 2,00,000",
        "Rs. 2,00,000",
        "Rs. 10,00,000",
        "Rs. 10",
    )
    for key in ("bank_to_wallet", "wallet_to_bank"):
        assert rs(LIMITS[key]) == ("Rs. 2,00,000", "Rs. 2,00,000", "Rs. 10,00,000", "Rs. 10")
    assert rs(LIMITS["wallet_to_wallet"]) == ("Rs. 50,000", "Rs. 50,000", "Rs. 5,00,000", "Rs. 10")
    assert rs(LIMITS["escrow"]) == ("Rs. 25,000", "Rs. 50,000", "Rs. 5,00,000", "Rs. 100")
    assert rs(LIMITS["card_load_visa_mastercard"])[:3] == (
        "Rs. 1,00,000",
        "Rs. 2,00,000",
        "Rs. 10,00,000",
    )
    assert rs(LIMITS["card_load_sct"])[:3] == ("Rs. 1,00,000", "Rs. 2,00,000", "Rs. 5,00,000")
    assert FLOW_LIMITS == {
        "send_money": "wallet_to_wallet",
        "load_money": "bank_to_wallet",
        "withdraw_to_bank": "wallet_to_bank",
    }


# --- usage, worked out from the wallet history -------------------------------------------------


def test_usage_this_month_matches_the_transactions(seeded: Session) -> None:
    source = MockTransactionSource(seeded)
    nov = source.list_transactions(USER, TransactionFilter(start=dt.date(2026, 11, 1), end=ANCHOR))
    sent = sum(t.amount_paisa for t in nov if t.type is TxnType.TRANSFER and t.is_debit)
    loaded = sum(t.amount_paisa for t in nov if t.service == "bank_load")
    paid = sum(
        t.amount_paisa
        for t in nov
        if t.is_debit
        and t.type in (TxnType.SCAN_PAY, TxnType.BILL_PAYMENT, TxnType.TOPUP, TxnType.BOOKING)
        and t.service not in NO_LIMIT_SERVICES
    )
    assert sent and paid  # the seed has some of each this month

    use = usage(source, USER, ANCHOR)
    w2w = use.limits["wallet_to_wallet"]
    assert (w2w.used_month_paisa, w2w.used_today_paisa) == (sent, 0)  # the data ends yesterday
    assert w2w.left_today_paisa == 50_000_00
    assert w2w.left_month_paisa == 5_00_000_00 - sent
    assert use.limits["bank_to_wallet"].used_month_paisa == loaded
    assert use.limits["merchant_payment"].used_month_paisa == paid
    assert use.limits["wallet_to_bank"].used_month_paisa == 0
    assert use.balance_paisa == 21_944_86 and use.over_overnight_cap_paisa == 0


def test_todays_transfers_and_deposits_count(seeded: Session) -> None:
    _add(seeded, 12_000)  # to a friend
    _add(seeded, 5_000, direction=Direction.CREDIT, service="bank_load", merchant="Himal Bank")
    _add(seeded, 700, direction=Direction.CREDIT)  # from a friend
    _add(seeded, 1_300, type=TxnType.BILL_PAYMENT, service="electricity", merchant="NEA")
    use = usage(MockTransactionSource(seeded), USER, ANCHOR)
    assert use.limits["wallet_to_wallet"].used_today_paisa == 12_000_00
    assert use.limits["wallet_to_wallet"].left_today_paisa == 38_000_00
    assert use.limits["bank_to_wallet"].used_today_paisa == 5_000_00
    assert use.limits["merchant_payment"].used_today_paisa == 0  # electricity has no limit
    assert use.deposits_today == 2


@pytest.mark.parametrize(
    ("used_today", "used_month", "amount", "rule", "allowed"),
    [
        (0, 0, 9_00, "minimum", 10_00),
        (0, 0, 60_000_00, "per_transaction", 50_000_00),
        (30_000_00, 30_000_00, 30_000_00, "per_day", 20_000_00),
        (0, 4_90_000_00, 20_000_00, "per_month", 10_000_00),
        (0, 0, 50_000_00, None, None),
        (49_990_00, 49_990_00, 10_00, None, None),
    ],
)
def test_amounts_are_checked_against_every_limit(
    used_today: int, used_month: int, amount: int, rule: str | None, allowed: int | None
) -> None:
    use = LimitUse(LIMITS["wallet_to_wallet"], used_today, used_month)
    problem = check_amount(use, amount)
    if rule is None:
        assert problem is None
    else:
        assert problem is not None and (problem.rule, problem.allowed_paisa) == (rule, allowed)


# --- get_wallet_rules ----------------------------------------------------------------------------


def test_wallet_rules_give_the_limits_and_what_is_left(ctx: ToolContext) -> None:
    r = run_tool(ctx, "get_wallet_rules", {})  # topic defaults to limits
    d = r.data
    assert d["source"] == SOURCE and d["last_checked"] == "20 Nov 2026"
    assert d["limits"]["Wallet to wallet"] == (
        "Rs. 50,000 per transaction, Rs. 50,000 a day, Rs. 5,00,000 a month"
    )
    assert d["limits"]["Khalti Escrow"].startswith("Rs. 25,000 per transaction")
    assert d["minimum"] == "Rs. 10 for any transfer or payment (Khalti Escrow: Rs. 100)"
    assert "electricity, telecom and drinking water" in d["no_limit"]
    w2w = d["your_usage"]["Wallet to wallet"]
    use = usage(ctx.source, USER, ANCHOR).limits["wallet_to_wallet"]
    assert w2w == {
        "used_today": "Rs. 0",
        "left_today": "Rs. 50,000",
        "used_this_month": format_npr(use.used_month_paisa),
        "left_this_month": format_npr(use.left_month_paisa),
    }
    assert d["deposits_today"] == "0 of 10 a day" and "Dashain" in d["deposits_note"]
    assert "overnight_balance_cap" not in d and r.cards == []
    text = json.dumps(d)
    assert not re.search(r"9[678]\d{8}", text) and "0010" not in text  # no phone or account


def test_balance_cap_says_when_the_wallet_is_over_it(ctx: ToolContext) -> None:
    under = run_tool(ctx, "get_wallet_rules", {"topic": "balance_cap"}).data
    assert under["overnight_balance_cap"] == "Rs. 50,000"
    assert under["balance_now"] == "Rs. 21,944.86" and under["over_overnight_cap"] is False
    assert "over_by" not in under and "before the day ends" in under["cap_rule"]

    _add(ctx.session, 30_000, direction=Direction.CREDIT, type=TxnType.REMITTANCE)
    over = run_tool(ctx, "get_wallet_rules", {"topic": "balance_cap"}).data
    assert over["balance_now"] == "Rs. 51,944.86"
    assert over["over_overnight_cap"] is True and over["over_by"] == "Rs. 1,944.86"


def test_the_other_topics(ctx: ToolContext) -> None:
    kyc = run_tool(ctx, "get_wallet_rules", {"topic": "kyc"}).data
    assert kyc["your_kyc"] == "verified" and "One wallet per KYC." in kyc["kyc_rules"]
    sec = run_tool(ctx, "get_wallet_rules", {"topic": "security"}).data
    assert any("within 24 hours" in s for s in sec["security"])
    refunds = run_tool(ctx, "get_wallet_rules", {"topic": "refunds"}).data
    assert any("72 hours" in s for s in refunds["refunds_and_complaints"])
    fees = run_tool(ctx, "get_wallet_rules", {"topic": "fees"}).data
    assert "shown in the Khalti app" in fees["fees"] and "Rs." not in json.dumps(fees)
    everything = run_tool(ctx, "get_wallet_rules", {"topic": "all"}).data
    for key in ("limits", "overnight_balance_cap", "kyc_rules", "security", "fees"):
        assert key in everything


# --- open_app_flow checks the limits and KYC in code -------------------------------------------


def test_sending_over_the_limit_gets_no_button(ctx: ToolContext) -> None:
    r = run_tool(
        ctx, "open_app_flow", {"flow": "send_money", "amount": 60000, "recipient_name": "Sita"}
    )
    assert r.cards == []
    assert r.data["status"].startswith("NOT opened")
    assert r.data["limit"] == "Wallet to wallet: Rs. 50,000 per transaction"
    assert r.data["over_by"] == "Rs. 10,000"  # worked out here, never by the model
    assert r.data["left_today"] == "Rs. 50,000"
    assert r.data["most_in_one_transaction_now"] == "Rs. 50,000"
    assert "splitting" in r.data["status"]

    small = run_tool(ctx, "open_app_flow", {"flow": "send_money", "amount": 5})
    assert small.cards == [] and small.data["limit"] == "The minimum is Rs. 10."


def test_two_buttons_in_one_message_count_against_the_day(ctx: ToolContext) -> None:
    first = run_tool(ctx, "open_app_flow", {"flow": "send_money", "amount": 30000})
    assert first.cards and first.cards[0].prefill.amount_paisa == 30_000_00
    second = run_tool(ctx, "open_app_flow", {"flow": "send_money", "amount": 30000})
    assert second.cards == []
    assert second.data["limit"] == "Wallet to wallet: Rs. 50,000 a day"
    assert second.data["left_today"] == "Rs. 20,000"
    assert second.data["over_by"] == "Rs. 10,000"
    assert second.data["used_today_includes"].startswith("Rs. 30,000 for buttons")


def test_money_already_sent_today_counts(ctx: ToolContext) -> None:
    _add(ctx.session, 45_000)
    r = run_tool(ctx, "open_app_flow", {"flow": "send_money", "amount": 6000})
    assert r.cards == [] and r.data["left_today"] == "Rs. 5,000"
    ok = run_tool(ctx, "open_app_flow", {"flow": "send_money", "amount": 5000})
    assert ok.cards and "NOTHING has been paid" in ok.data["status"]


@pytest.mark.parametrize("status", [KycStatus.PENDING, KycStatus.NOT_STARTED])
def test_no_money_button_without_kyc(ctx: ToolContext, status: KycStatus) -> None:
    _set_kyc(ctx.session, status)
    for args in (
        {"flow": "bill_payment", "service": "electricity"},
        {"flow": "send_money", "amount": 500},
        {"flow": "autopay"},
        {"flow": "smart_deposit"},
    ):
        r = run_tool(ctx, "open_app_flow", args)
        assert r.cards == [], args
        assert r.data["kyc"] == status.value and "search_help_articles" in r.data["status"]
    assert run_tool(ctx, "get_wallet_rules", {"topic": "kyc"}).data["your_kyc"] == status.value


# --- the prompt and the chat ----------------------------------------------------------------------


@pytest.mark.parametrize("lang", list(Lang))
def test_the_prompt_never_holds_the_limits(lang: Lang) -> None:
    today = dt.date(2026, 11, 20)
    for kyc in (True, False, None):
        prompt = system_prompt(today, lang, kyc_verified=kyc)
        for lim in LIMITS.values():
            for paisa in (lim.per_txn_paisa, lim.per_day_paisa, lim.per_month_paisa):
                assert format_npr(paisa) not in prompt
        assert format_npr(OVERNIGHT_BALANCE_CAP_PAISA) not in prompt
        assert "call get_wallet_rules and quote only what it returns" in prompt
        assert "You are an AI, not a person or Khalti staff." in prompt
    assert "KYC" not in system_prompt(today, lang).split("\n")[0]
    assert (
        system_prompt(today, lang, kyc_verified=True)
        .split("\n")[0]
        .endswith("The user's KYC is verified.")
    )
    assert "KYC is NOT verified" in system_prompt(today, lang, kyc_verified=False)


def _service(session: Session, llm: FakeLLM) -> ChatService:
    source = MockTransactionSource(session)
    return ChatService(
        session, llm, source, MockBillSource(source), USER, ANCHOR, files=FileMemory()
    )


def test_the_chat_tells_the_model_the_kyc_status(seeded: Session) -> None:
    llm = FakeLLM(say("Hi."))
    list(_service(seeded, llm).respond("hello"))
    assert "The user's KYC is verified." in llm.calls[0][0][0]["content"]

    _set_kyc(seeded, KycStatus.PENDING)
    pay = {"flow": "bill_payment", "service": "electricity"}
    llm = FakeLLM(call(("open_app_flow", pay)), say("Please finish your KYC first."))
    events = list(_service(seeded, llm).respond("pay my electricity bill"))
    assert "KYC is NOT verified" in llm.calls[0][0][0]["content"]
    assert events[-1].data["cards"] == []  # no Pay button


def test_each_message_starts_with_no_buttons_counted(seeded: Session) -> None:
    send = {"flow": "send_money", "amount": 30000}
    service = _service(seeded, FakeLLM(call(("open_app_flow", send)), say("Tap the button.")))
    first = list(service.respond("send 30000 to Sita"))
    assert [c["type"] for c in first[-1].data["cards"]] == ["open_app_flow"]
    service.llm = FakeLLM(call(("open_app_flow", send)), say("Tap the button."))
    again = list(service.respond("send 30000 to Ram"))  # nothing was sent: a new message
    assert [c["type"] for c in again[-1].data["cards"]] == ["open_app_flow"]
