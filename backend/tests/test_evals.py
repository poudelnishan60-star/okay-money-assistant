"""The evaluation: the question file is sound and the scorer judges answers correctly
(scripted LLM, no network)."""

from __future__ import annotations

from collections import Counter

import pytest
from sqlalchemy.orm import Session

from app.ai.llm import LLMBusyError
from app.ai.tools import ToolContext
from app.models import User
from app.sources.mock import MockBillSource, MockTransactionSource
from evals.runner import (
    call_matches,
    expected_numbers,
    language_ok,
    load_questions,
    pick,
    problem_kind,
    run_question,
    states,
    summarize,
    to_number,
    validate_questions,
)
from tests.conftest import ANCHOR, USER
from tests.fake_llm import FakeLLM, call, say

ANCHOR_FROM_FILE, QUESTIONS = load_questions()
BY_ID = {q["id"]: q for q in QUESTIONS}
# Added in step 12: Khalti's rules, support and security.
STEP_12 = (
    {f"en{i}" for i in range(21, 26)}
    | {f"ne{i}" for i in range(16, 21)}
    | {f"rom{i}" for i in range(16, 21)}
)


def test_question_file() -> None:
    assert ANCHOR_FROM_FILE == ANCHOR
    assert len(QUESTIONS) == 65
    assert Counter(q["lang"] for q in QUESTIONS) == {"en": 25, "ne": 20, "rom": 20}
    assert validate_questions(QUESTIONS) == []
    # Every question checks something beyond the global checks.
    for q in QUESTIONS:
        checks = ("tools", "no_tools", "text_any", "cards_none", "max_cards")
        assert any(q.get(c) for c in checks), q["id"]


def test_every_expected_number_resolves(seeded: Session) -> None:
    src = MockTransactionSource(seeded)
    ctx = ToolContext(seeded, src, MockBillSource(src), USER, ANCHOR)
    found = {q["id"]: expected_numbers(ctx, q) for q in QUESTIONS if q.get("numbers")}
    assert len(found) >= 25
    assert found["en01"] == [("Rs. 6,213.80", 6213.80)]
    assert found["en09"] == [("Rs. 7,907.20", 7907.20)]
    assert found["rom03"] == [("Rs. 9,710", 9710.0)]  # last month's biggest category (Food)
    assert all(value > 0 for pairs in found.values() for _, value in pairs)


def test_helpers() -> None:
    data = {
        "budgets": [
            {"budget": "Overall (all spending)", "left": "Rs. 1"},
            {"budget": "Groceries", "left": "Rs. 7,907.20"},
        ]
    }
    assert pick(data, "budgets[budget=Groceries].left") == "Rs. 7,907.20"
    assert pick(data, "budgets[budget=Overall].left") == "Rs. 1"
    assert pick({"a": [{"b": 5}]}, "a[0].b") == 5
    assert to_number("रु. १,२७०") == 1270 and to_number("-Rs. 1,25,000.50") == 125000.50
    assert states("You spent रु. ६,२१३.८० so far", 6213.80)
    assert states("about Rs. 1,093", 1092.80)  # rounded to the rupee
    assert not states("Rs. 1,100", 1092.80)
    assert language_ok("तपाईंले यो महिना रु. 1,270 खर्च गर्नुभयो।", "ne")
    assert language_ok("Yo mahina khana ma Rs. 1,270 kharcha bhayo.", "rom")
    assert language_ok("You spent Rs. 1,270 on food this month.", "en")
    assert not language_ok("You spent Rs. 1,270 on food this month.", "ne")
    assert not language_ok("You spent Rs. 1,270 on food this month.", "rom")
    # The tool's defaults count: no period means this month.
    spec = {"name": "get_spending_summary", "args": {"period": ["this_month"]}}
    assert call_matches(spec, ("get_spending_summary", {"month": "2026-11"}))
    assert not call_matches(spec, ("get_spending_summary", {"period": "last_month"}))
    assert call_matches(
        {"name": "get_transactions", "args": {"merchant": "dhukuti"}},
        ("get_transactions", {"merchant": "Café Dhukuti"}),
    )
    assert problem_kind("missing number Rs. 5") == "numbers"
    assert problem_kind("expected tool get_goals {}") == "tools"


FOOD = {"period": "this_month", "category": "Food & Dining"}


def test_a_good_answer_passes(seeded: Session) -> None:
    llm = FakeLLM(
        call(("get_spending_summary", FOOD)),
        say("You spent **Rs. 1,270** on food this month."),
    )
    r = run_question(seeded, llm, BY_ID["en02"], ANCHOR)
    assert (r.status, r.problems) == ("pass", [])
    assert r.tools == [("get_spending_summary", FOOD)]
    assert r.cards == ["spending_summary"]


def test_wrong_number_wrong_tool_wrong_language(seeded: Session) -> None:
    # A made-up amount: the pipeline's own grounding check asks for a correction, which
    # repeats the mistake, so the pipeline takes that sentence out; the eval still reports it.
    llm = FakeLLM(
        call(("get_spending_summary", FOOD)),
        say("You spent Rs. 1,300 on food. Food is your top category."),
        call(("get_spending_summary", FOOD)),
        say("You spent Rs. 1,300 on food. Food is your top category."),
    )
    r = run_question(seeded, llm, BY_ID["ne02"], ANCHOR)
    assert r.status == "fail"
    assert r.answer == "Food is your top category."
    kinds = {problem_kind(p) for p in r.problems}
    assert {"numbers", "language", "grounding"} <= kinds
    assert "grounding: 1 made-up sentence(s) taken out after the correction" in r.problems

    llm = FakeLLM(say("You spent some money."))
    r = run_question(seeded, llm, BY_ID["en02"], ANCHOR)
    assert "tools" in {problem_kind(p) for p in r.problems}


def test_confirm_card_and_nothing_saved(seeded: Session) -> None:
    llm = FakeLLM(
        call(("upsert_budget", {"category": "Food & Dining", "limit_amount": 6000})),
        say("Tap **Confirm** to set your food budget to Rs. 6,000."),
    )
    r = run_question(seeded, llm, BY_ID["en10"], ANCHOR)
    assert (r.status, r.problems) == ("pass", [])
    assert "confirm_action" in r.cards


def test_secret_is_redacted_before_the_model(seeded: Session) -> None:
    llm = FakeLLM(
        call(("get_spending_summary", {"period": "last_7_days"})),
        say("In the last 7 days you spent Rs. 4,796."),
    )
    r = run_question(seeded, llm, BY_ID["en18"], ANCHOR)
    assert (r.status, r.problems) == ("pass", [])
    assert r.answer.startswith("Please never share your MPIN")


def test_refusal_and_no_tools(seeded: Session) -> None:
    llm = FakeLLM(say("I can't recommend specific stocks, but here is how to think about risk."))
    assert run_question(seeded, llm, BY_ID["en19"], ANCHOR).status == "pass"
    llm = FakeLLM(say("Buy NABIL now, it will double."))
    r = run_question(seeded, llm, BY_ID["en19"], ANCHOR)
    assert r.status == "fail" and "text_none" in {problem_kind(p) for p in r.problems}


def test_outage_is_an_error_not_a_failure(seeded: Session) -> None:
    llm = FakeLLM(LLMBusyError("429"))
    r = run_question(seeded, llm, BY_ID["en01"], ANCHOR)
    assert r.status == "error"
    s = summarize([r])
    assert s["overall"] == {"passed": 0, "scored": 0, "errors": 1, "pass_rate": None}


@pytest.mark.parametrize("qid", ["rom01", "ne01"])
def test_nepali_and_romanized_answers(seeded: Session, qid: str) -> None:
    text = {
        "rom01": "Yo mahina tapai ko kharcha Rs. 6,213.80 bhayo.",
        "ne01": "यो महिना तपाईंले रु. ६,२१३.८० खर्च गर्नुभयो।",
    }[qid]
    llm = FakeLLM(call(("get_spending_summary", {"period": "this_month"})), say(text))
    r = run_question(seeded, llm, BY_ID[qid], ANCHOR)
    assert (r.status, r.problems) == ("pass", [])


def test_scorer_details_from_the_live_runs() -> None:
    # Mixed Romanized Nepali and English is Romanized Nepali.
    assert language_ok(
        'Internet ko bill "Gurans Fibernet" ko usual amount Rs. 1,300 ho, ani next due date '
        "2026-11-21.",
        "rom",
    )
    assert not language_ok("Tap the Send money button and confirm Rs. 500 in Khalti.", "rom")


# --- step 12: Khalti's rules, support and security ----------------------------------------------


def test_the_step_12_questions(seeded: Session) -> None:
    new = [q for q in QUESTIONS if q["id"] in STEP_12]
    assert Counter(q["lang"] for q in new) == {"en": 5, "ne": 5, "rom": 5}
    src = MockTransactionSource(seeded)
    ctx = ToolContext(seeded, src, MockBillSource(src), USER, ANCHOR)
    assert expected_numbers(ctx, BY_ID["en21"]) == [("Rs. 50,000", 50000.0)]
    assert expected_numbers(ctx, BY_ID["en25"]) == [("Rs. 500", 500.0)]


def test_a_card_can_name_its_flow(seeded: Session) -> None:
    block = {"flow": "block_wallet"}
    good = FakeLLM(call(("open_app_flow", block)), say("तलको बटन थिचेर वालेट ब्लक गर्नुहोस्।"))
    r = run_question(seeded, good, BY_ID["ne17"], ANCHOR)
    assert (r.status, r.problems) == ("pass", [])
    assert r.cards == ["open_app_flow:block_wallet"]
    support = {"flow": "support"}
    wrong = FakeLLM(call(("open_app_flow", support)), say("तलको बटन थिच्नुहोस्।"))
    r = run_question(seeded, wrong, BY_ID["ne17"], ANCHOR)
    assert "missing card open_app_flow:block_wallet" in r.problems


def test_a_refused_send_shows_no_button(seeded: Session) -> None:
    send = {"flow": "send_money", "amount": 60000, "recipient_name": "Sita"}
    llm = FakeLLM(
        call(("open_app_flow", send)),
        say("Rs. 60,000 is over the wallet-to-wallet limit; you can send Rs. 50,000 today."),
    )
    r = run_question(seeded, llm, BY_ID["en22"], ANCHOR)
    assert (r.status, r.problems) == ("pass", [])
    assert r.cards == []


def test_two_buttons_to_get_past_the_limit_are_not_shown(seeded: Session) -> None:
    # The model tries it in one round: the code refuses the second button.
    send = {"flow": "send_money", "amount": 30000, "recipient_name": "Sita"}
    llm = FakeLLM(
        call(("open_app_flow", send), ("open_app_flow", send)),
        say("Aaja wallet bata Rs. 50,000 samma matra pathauna milcha, tala ko button thichnus."),
    )
    r = run_question(seeded, llm, BY_ID["rom17"], ANCHOR)
    assert r.cards == ["open_app_flow:send_money"]
    assert (r.status, r.problems) == ("pass", [])


def test_a_question_can_run_without_kyc(seeded: Session) -> None:
    bill = {"flow": "bill_payment", "service": "electricity"}
    llm = FakeLLM(
        call(("open_app_flow", bill)),
        say("Tapai ko KYC verify bhayeko chaina, pahila KYC garnus ani bill tirna milcha."),
    )
    r = run_question(seeded, llm, BY_ID["rom18"], ANCHOR)
    assert (r.status, r.problems) == ("pass", [])
    assert r.cards == []  # no Pay button without KYC
    assert seeded.get(User, USER).kyc_status == "verified"  # set back afterwards
