"""The chat loop with a scripted LLM: tool rounds, cards, chips, errors, secrets, history,
audit log, and the HTTP/SSE layer with sessions and rate limits."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.chat import ChatEvent, ChatService
from app.ai.llm import LLMBusyError, LLMNotConfiguredError, LLMUnavailableError
from app.ai.safety import MESSAGES, Lang
from app.models import ChatMessage, ToolCallLog, TransactionRow
from app.sources.mock import MockBillSource, MockTransactionSource
from tests.conftest import ANCHOR, USER
from tests.fake_llm import FakeLLM, call, say


def _service(session: Session, llm: FakeLLM) -> ChatService:
    source = MockTransactionSource(session)
    return ChatService(session, llm, source, MockBillSource(source), USER, ANCHOR)


def _run(session: Session, llm: FakeLLM, text: str, lang: str = "auto") -> list[ChatEvent]:
    return list(_service(session, llm).respond(text, lang))


def _text(events: list[ChatEvent]) -> str:
    return "".join(e.data["text"] for e in events if e.event == "token")


def test_tool_round_then_answer(seeded: Session) -> None:
    llm = FakeLLM(
        call(("get_spending_summary", {"period": "this_month", "category": "Food & Dining"})),
        say("Yo mahina khana ma ", "Rs. 1,270 kharcha bhayo."),
    )
    events = _run(seeded, llm, "yo mahina khana ma kati kharcha bhayo?")
    assert [e.event for e in events] == ["status", "token", "token", "done"]
    assert _text(events) == "Yo mahina khana ma Rs. 1,270 kharcha bhayo."
    done = events[-1].data
    assert done["language"] == "rom" and done["error"] is None
    assert done["cards"][0]["type"] == "spending_summary"
    assert done["cards"][0]["link"]["filters"]["category"] == "Food & Dining"
    assert all(s["text"] for s in done["suggestions"])
    assert done["suggestions"][0]["text"] == "Yo mahina ra gaya mahina"  # chips in Romanized

    # the second LLM call saw the tool result, delimited
    second_messages = llm.calls[1][0]
    tool_msg = second_messages[-2]  # last: the language reminder
    assert tool_msg["role"] == "tool"
    assert second_messages[-1] == {"role": "system", "content": "Reply in Romanized Nepali."}
    assert tool_msg["content"].startswith('<tool_result name="get_spending_summary">')
    assert second_messages[0]["role"] == "system"
    assert "Romanized Nepali" in second_messages[0]["content"]

    rows = seeded.scalars(select(ChatMessage).order_by(ChatMessage.id)).all()
    assert [(r.role, r.language) for r in rows] == [("user", "rom"), ("assistant", "rom")]
    assert json.loads(rows[1].cards_json)[0]["type"] == "spending_summary"


def test_parallel_tool_calls_in_one_round(seeded: Session) -> None:
    llm = FakeLLM(call(("get_budgets", {}), ("get_recurring_payments", {})), say("Done."))
    events = _run(seeded, llm, "budgets and bills?")
    assert [e.data["tool"] for e in events if e.event == "status"] == [
        "get_budgets",
        "get_recurring_payments",
    ]
    types = [c["type"] for c in events[-1].data["cards"]]
    assert types == ["budget_progress", "bills_list"]
    assert [m["role"] for m in llm.calls[1][0][-3:]] == ["assistant", "tool", "tool"]


def test_at_most_five_tool_rounds_then_forced_answer(seeded: Session) -> None:
    steps = [call(("get_budgets", {})) for _ in range(5)] + [say("Here you go.")]
    llm = FakeLLM(*steps)
    events = _run(seeded, llm, "loop forever")
    assert len(llm.calls) == 6
    assert all(tools is not None for _, tools in llm.calls[:5])
    assert llm.calls[5][1] is None  # the sixth call may not use tools
    assert sum(e.event == "status" for e in events) == 5
    assert len(events[-1].data["cards"]) == 1  # identical cards collapse into one


@pytest.mark.parametrize(
    ("exc", "key"),
    [
        (LLMBusyError("429"), "busy"),
        (LLMNotConfiguredError("no key"), "not_configured"),
        (LLMUnavailableError("down"), "unavailable"),
    ],
)
def test_provider_errors_become_friendly_messages(
    seeded: Session, exc: Exception, key: str
) -> None:
    events = _run(seeded, FakeLLM(exc), "How much did I spend?")
    assert _text(events) == MESSAGES[key][Lang.EN]
    assert events[-1].data["error"] == key
    assert seeded.scalar(select(func.count()).select_from(ChatMessage)) == 2


def test_busy_message_in_nepali(seeded: Session) -> None:
    events = _run(seeded, FakeLLM(LLMBusyError("429")), "मेरो खर्च कति भयो?")
    assert _text(events) == MESSAGES["busy"][Lang.NE]


def test_typed_mpin_is_removed_and_the_user_warned(seeded: Session) -> None:
    llm = FakeLLM(say("Your spending is shown below."))
    events = _run(seeded, llm, "my mpin is 4321, how much did I spend?")
    assert _text(events).startswith(MESSAGES["secret_warning"][Lang.EN])
    sent = json.dumps(llm.calls[0][0])
    assert "4321" not in sent and "[redacted]" in sent
    stored = " ".join(seeded.scalars(select(ChatMessage.content)))
    assert "4321" not in stored


def test_pii_in_the_question_is_masked_before_the_llm(seeded: Session) -> None:
    llm = FakeLLM(say("ok"))
    _run(seeded, llm, "did 9841234567 send me money? ref K7Q2M9XH4TB")
    user_msg = llm.calls[0][0][-1]["content"]
    assert "9841234567" not in user_msg and "K7Q2M9XH4TB" not in user_msg


def test_history_sends_only_the_last_20_messages(seeded: Session) -> None:
    for i in range(30):
        seeded.add(
            ChatMessage(user_id=USER, role="user" if i % 2 == 0 else "assistant", content=f"m{i}")
        )
    seeded.commit()
    llm = FakeLLM(say("hi"))
    _run(seeded, llm, "hello")
    messages = llm.calls[0][0]
    assert len(messages) == 1 + 20 + 1
    assert messages[1]["content"] == "m10" and messages[-2]["content"] == "m29"


def test_tool_errors_go_back_to_the_model_and_are_audited(seeded: Session) -> None:
    llm = FakeLLM(
        call(
            ("get_spending_summary", {"period": "forever"}),
            ("get_transactions", {"merchant": "call 9841234567"}),
        ),
        say("Sorry."),
    )
    _run(seeded, llm, "x")
    contents = [m["content"] for m in llm.calls[1][0] if m["role"] == "tool"]
    assert "invalid arguments" in contents[0]
    logs = seeded.scalars(select(ToolCallLog).order_by(ToolCallLog.id)).all()
    assert [(log.tool, log.ok) for log in logs] == [
        ("get_spending_summary", False),
        ("get_transactions", True),
    ]
    assert "9841234567" not in logs[1].arguments_json  # audit log is masked too
    assert "[phone]" in logs[1].arguments_json


def test_empty_answer_falls_back(seeded: Session) -> None:
    events = _run(seeded, FakeLLM(say("")), "?")
    assert _text(events) == MESSAGES["no_data"][Lang.EN]


def test_language_preference_overrides_detection(seeded: Session) -> None:
    llm = FakeLLM(say("ok"))
    events = _run(seeded, llm, "How much?", lang="ne")
    assert events[-1].data["language"] == "ne"
    assert "Devanagari" in llm.calls[0][0][0]["content"]


# --- HTTP / SSE ------------------------------------------------------------------------------


def _sse(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_post_chat_streams_sse(make_client) -> None:
    llm = FakeLLM(call(("get_budgets", {})), say("You have 4 budgets."))
    c: TestClient = make_client(llm=llm)
    r = c.post("/chat", json={"message": "Show my budgets"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = _sse(r.text)
    assert [e for e, _ in events] == ["status", "token", "done"]
    done = events[-1][1]
    assert done["cards"][0]["type"] == "budget_progress"

    history = c.get("/chat/history").json()
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[1]["cards"][0]["type"] == "budget_progress"

    mid = done["message_id"]
    assert c.put(f"/chat/messages/{mid}/feedback", json={"rating": "up"}).status_code == 204
    assert c.get("/chat/history").json()[1]["feedback"] == "up"
    assert (
        c.put(f"/chat/messages/{history[0]['id']}/feedback", json={"rating": "down"}).status_code
        == 404
    )  # can't rate your own message
    assert c.delete("/chat/history").status_code == 204
    assert c.get("/chat/history").json() == []


def test_chat_without_key_explains_itself(client: TestClient) -> None:
    events = _sse(client.post("/chat", json={"message": "hi"}).text)
    assert events[-1][1]["error"] == "not_configured"


def test_chat_rate_limit(make_client) -> None:
    c = make_client(llm=FakeLLM(say("ok"), repeat_last=True), rate_chat_per_minute=2)
    assert c.post("/chat", json={"message": "a"}).status_code == 200
    assert c.post("/chat", json={"message": "b"}).status_code == 200
    r = c.post("/chat", json={"message": "c"})
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0


def test_chat_input_validation(client: TestClient) -> None:
    assert client.post("/chat", json={"message": ""}).status_code == 422
    assert client.post("/chat", json={"message": "x" * 1001}).status_code == 422
    assert client.post("/chat", json={"message": "x", "language": "fr"}).status_code == 422


# --- visitor sessions -----------------------------------------------------------------------


def test_each_visitor_gets_a_private_copy(make_client) -> None:
    c = make_client()
    a = c.post("/sessions").json()["session_id"]
    b = c.post("/sessions").json()["session_id"]
    assert a != b and a.startswith("v_") and len(a) > 20
    ha, hb = {"X-User-Id": a}, {"X-User-Id": b}
    assert c.get("/me", headers=ha).json()["balance_paisa"] == 23_944_86
    assert c.get("/transactions", headers=ha).json()["total"] == 154

    c.post("/budgets", headers=ha, json={"category": "Food & Dining", "limit_paisa": 600000})
    assert len(c.get("/budgets", headers=ha).json()) == 5
    assert len(c.get("/budgets", headers=hb).json()) == 4  # B unaffected
    assert len(c.get("/budgets").json()) == 4  # nor the shared demo user


def test_session_creation_is_rate_limited_per_ip(make_client) -> None:
    c = make_client(rate_sessions_per_ip_per_hour=2)
    assert c.post("/sessions").status_code == 201
    assert c.post("/sessions").status_code == 201
    assert c.post("/sessions").status_code == 429


def test_public_mode_requires_a_session(make_client) -> None:
    c = make_client(public_mode=True)
    assert c.get("/me").status_code == 401
    sid = c.post("/sessions").json()["session_id"]
    assert c.get("/me", headers={"X-User-Id": sid}).status_code == 200
    assert c.get("/me", headers={"X-User-Id": "v_guess"}).status_code == 404


def test_a_full_demo_drops_the_oldest_visitor_not_the_newest(make_client) -> None:
    import datetime as dt

    from app.models import User

    c = make_client(max_sessions=3)
    ids = [c.post("/sessions").json()["session_id"] for _ in range(3)]
    factory = c.app.state.session_factory
    with factory() as s:  # make the order unambiguous
        for age, sid in enumerate(reversed(ids)):
            s.get(User, sid).created_at -= dt.timedelta(minutes=age)
        s.commit()
    newest = c.post("/sessions")
    assert newest.status_code == 201
    assert c.get("/me", headers={"X-User-Id": ids[0]}).json() == {"detail": "unknown user"}
    for sid in [*ids[1:], newest.json()["session_id"]]:
        assert c.get("/me", headers={"X-User-Id": sid}).status_code == 200
    assert c.get("/me").status_code == 200  # the shared demo user is never dropped


def test_expired_sessions_are_cleaned_up(make_client) -> None:
    import datetime as dt

    from app.api.routes_session import cleanup_expired_sessions
    from app.models import User

    c = make_client()
    sid = c.post("/sessions").json()["session_id"]
    factory = c.app.state.session_factory
    with factory() as s:
        s.get(User, sid).created_at -= dt.timedelta(days=30)
        s.commit()
        assert cleanup_expired_sessions(s, ttl_days=7) == 1
        s.commit()
        assert s.get(User, sid) is None
        assert (
            s.scalar(
                select(func.count())
                .select_from(TransactionRow)
                .where(TransactionRow.user_id == sid)
            )
            == 0
        )  # cascaded
        assert s.get(User, USER) is not None  # the demo user stays


def test_spending_only_filter(client: TestClient) -> None:
    all_debits = client.get(
        "/transactions", params={"period": "this_month", "direction": "debit"}
    ).json()
    spending = client.get(
        "/transactions", params={"period": "this_month", "spending_only": True}
    ).json()
    summary = client.get("/insights/summary").json()
    assert spending["total"] == summary["transaction_count"]
    assert spending["total_debit_paisa"] == summary["total_spent_paisa"]
    assert spending["total"] < all_debits["total"]  # Smart Deposit / transfers left out


# --- grounding check ---------------------------------------------------------------------


def test_check_answer_rules() -> None:
    from app.ai.chat import check_answer

    grounded = '<tool_result>{"spent":"Rs. 1,270","usual":"Rs. 1,140.67"}</tool_result> 6000'
    assert check_answer("You spent Rs. 1,270 (usual Rs 1140.67).", [], grounded) is None
    assert check_answer("रु. १,२७० खर्च भयो।", [], grounded) is None  # Devanagari digits
    assert check_answer("A budget of Rs. 6,000.00", [], grounded) is None  # user's own number
    assert "ungrounded" in check_answer("You spent Rs. 9,999.", [], grounded)
    assert "confirm" in check_answer("Tap **Confirm** to save it.", [], grounded)
    assert check_answer("Tap Confirm to save it.", [{"type": "confirm_action"}], grounded) is None
    assert "button" in check_answer("Tap the Pay button below.", [], grounded)
    assert check_answer("Tap the button below.", [{"type": "open_app_flow"}], grounded) is None
    assert check_answer("I can't confirm that number.", [], grounded) is None


def test_invented_action_is_taken_back_and_redone(seeded: Session) -> None:
    llm = FakeLLM(
        say("I've proposed a food budget of Rs. 6,000. Tap Confirm to save it."),  # no tool!
        call(("upsert_budget", {"category": "Food & Dining", "limit_amount": 6000})),
        say("Tap Confirm to save your Rs. 6,000 food budget."),
    )
    events = _run(seeded, llm, "Set a food budget of 6000")
    kinds = [e.event for e in events]
    assert "reset" in kinds
    after_reset = events[kinds.index("reset") + 1 :]
    assert _text(after_reset) == "Tap Confirm to save your Rs. 6,000 food budget."
    assert events[-1].data["cards"][0]["type"] == "confirm_action"
    correction = llm.calls[1][0][-1]
    assert correction["role"] == "system" and "missing confirm card" in correction["content"]
    assert llm.tool_choices == ["auto", "required", "auto"]  # the redo must call a tool
    stored = seeded.scalars(select(ChatMessage.content).where(ChatMessage.role == "assistant"))
    assert list(stored) == ["Tap Confirm to save your Rs. 6,000 food budget."]


def test_made_up_number_is_taken_back(seeded: Session) -> None:
    llm = FakeLLM(
        say("You spent Rs. 9,999 on food."),
        call(("get_spending_summary", {"period": "this_month", "category": "Food & Dining"})),
        say("You spent Rs. 1,270 on food."),
    )
    events = _run(seeded, llm, "food spending?")
    assert [e.event for e in events].count("reset") == 1
    assert events[-1].data["cards"][0]["type"] == "spending_summary"
    assert "ungrounded amounts: Rs. 9,999" in llm.calls[1][0][-1]["content"]


def test_only_one_correction_round(seeded: Session) -> None:
    llm = FakeLLM(say("Rs. 1 extra."), say("Rs. 2 still made up."))
    events = _run(seeded, llm, "?")
    assert [e.event for e in events].count("reset") == 1
    assert len(llm.calls) == 2
    assert events[-1].event == "done"


def test_failed_forced_correction_is_retried_without_forcing(seeded: Session) -> None:
    # Found by the eval: a model may refuse tool_choice="required". Then the correction is
    # tried once more without forcing, instead of answering "O-Kay can't answer right now".
    llm = FakeLLM(
        say("You spent Rs. 9,999 on food."),
        LLMUnavailableError("did not call a tool"),
        call(("get_spending_summary", {"period": "this_month", "category": "Food & Dining"})),
        say("You spent Rs. 1,270 on food."),
    )
    events = _run(seeded, llm, "food spending?")
    assert [e.event for e in events].count("reset") == 2
    assert llm.tool_choices == ["auto", "required", "auto", "auto"]
    last_reset = max(i for i, e in enumerate(events) if e.event == "reset")
    assert _text(events[last_reset + 1 :]) == "You spent Rs. 1,270 on food."
    assert events[-1].data["error"] is None


def test_busy_during_correction_is_still_busy(seeded: Session) -> None:
    llm = FakeLLM(say("You spent Rs. 9,999 on food."), LLMBusyError("429"))
    events = _run(seeded, llm, "food spending?")
    assert events[-1].data["error"] == "busy"
    assert len(llm.calls) == 2  # no third try while rate limited


def test_language_reminder_goes_with_the_question_only(seeded: Session) -> None:
    llm = FakeLLM(say("Yo mahina Rs. 6,213.80 kharcha bhayo."), repeat_last=True)
    _run(seeded, llm, "yo mahina kati kharcha bhayo?")
    sent = llm.calls[0][0][-1]
    assert sent["role"] == "user"
    assert sent["content"].endswith("(Reply in Romanized Nepali.)")
    stored = seeded.scalars(select(ChatMessage.content).where(ChatMessage.role == "user"))
    assert list(stored) == ["yo mahina kati kharcha bhayo?"]
    _run(seeded, llm, "How much did I spend?")
    assert llm.calls[-1][0][-1]["content"] == "How much did I spend?"  # English: no note


def test_language_rule_is_repeated_after_tool_results(seeded: Session) -> None:
    llm = FakeLLM(
        call(("upsert_budget", {"category": "Food & Dining", "limit_amount": 5000})),
        say("Budget save garna Confirm thichnus."),
    )
    _run(seeded, llm, "khana ko lagi 5000 ko budget rakhdinus")
    after_tools = llm.calls[1][0]
    assert after_tools[-2]["role"] == "tool"
    assert after_tools[-1] == {"role": "system", "content": "Reply in Romanized Nepali."}
