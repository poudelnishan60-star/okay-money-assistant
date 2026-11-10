"""The evaluation: the question file is sound and the scorer judges answers correctly
(scripted LLM, no network)."""

from __future__ import annotations

from collections import Counter

import pytest
from sqlalchemy.orm import Session

from app.ai.llm import LLMBusyError
from app.ai.tools import ToolContext
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


def test_question_file() -> None:
    assert ANCHOR_FROM_FILE == ANCHOR
    assert len(QUESTIONS) == 50
    assert Counter(q["lang"] for q in QUESTIONS) == {"en": 20, "ne": 15, "rom": 15}
    assert validate_questions(QUESTIONS) == []
    # Every question checks something beyond the global checks.
    for q in QUESTIONS:
        assert q.get("tools") or q.get("no_tools") or q.get("text_any"), q["id"]


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
    # repeats the mistake; the eval reports both problems.
    llm = FakeLLM(
        call(("get_spending_summary", FOOD)),
        say("You spent Rs. 1,300 on food."),
        call(("get_spending_summary", FOOD)),
        say("You spent Rs. 1,300 on food."),
    )
    r = run_question(seeded, llm, BY_ID["ne02"], ANCHOR)
    assert r.status == "fail"
    kinds = {problem_kind(p) for p in r.problems}
    assert {"numbers", "language", "grounding"} <= kinds

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
