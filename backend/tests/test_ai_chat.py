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
    tool_msg = second_messages[-1]
    assert tool_msg["role"] == "tool"
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
