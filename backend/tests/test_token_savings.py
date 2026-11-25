"""Fewer tokens per question (25 Nov 2026): the free tier allows the main model about 200,000
tokens a day for every visitor together, and every request carries the system prompt, the
tool list and the chat history."""

from __future__ import annotations

import datetime as dt
import json

from sqlalchemy.orm import Session

from app.ai.chat import OLDER_ANSWER_CHARS, ChatService
from app.ai.prompt import system_prompt
from app.ai.safety import Lang
from app.ai.tools import compact_tool_specs, openai_tool_specs
from app.models import ChatMessage
from app.sources.mock import MockBillSource, MockTransactionSource
from tests.conftest import ANCHOR, USER
from tests.fake_llm import FakeLLM, call, say

TODAY = dt.date(2026, 11, 25)


def _service(session: Session, llm: FakeLLM) -> ChatService:
    source = MockTransactionSource(session)
    return ChatService(session, llm, source, MockBillSource(source), USER, ANCHOR)


def test_the_files_rule_only_when_a_file_is_involved() -> None:
    plain = system_prompt(TODAY, Lang.EN, kyc_verified=True)
    with_files = system_prompt(TODAY, Lang.EN, kyc_verified=True, files=True)
    assert "<attachment>" not in plain and "Worked out in code" not in plain
    assert "<attachment>" in with_files and with_files.startswith(plain)
    assert len(with_files) - len(plain) > 700


def test_a_chat_with_an_earlier_file_still_gets_the_files_rule(seeded: Session) -> None:
    seeded.add(ChatMessage(user_id=USER, role="user", content="what is this?"))
    seeded.add(ChatMessage(user_id=USER, role="assistant", content="A statement."))
    seeded.commit()
    llm = FakeLLM(say("ok"))
    list(_service(seeded, llm).respond("hello"))
    assert "<attachment>" not in llm.calls[0][0][0]["content"]  # no file anywhere yet

    row = seeded.query(ChatMessage).filter_by(content="what is this?").one()
    row.attachments_json = json.dumps([{"name": "may.xlsx", "kind": "spreadsheet"}])
    seeded.commit()
    llm = FakeLLM(say("ok"))
    list(_service(seeded, llm).respond("and the total?"))
    assert "<attachment>" in llm.calls[0][0][0]["content"]


def test_rounds_after_the_first_get_the_tools_without_descriptions(seeded: Session) -> None:
    llm = FakeLLM(call(("get_budgets", {})), say("You have 3 budgets."))
    list(_service(seeded, llm).respond("how are my budgets?"))
    first, second = llm.calls[0][1], llm.calls[1][1]
    assert all("description" in t["function"] for t in first)
    assert second == compact_tool_specs(first)
    assert [t["function"]["name"] for t in second] == [t["function"]["name"] for t in first]
    assert "description" not in json.dumps(second)
    full, compact = len(json.dumps(first)), len(json.dumps(second))
    assert compact < full * 0.8
    # the schemas themselves (enums, required) are kept
    assert compact_tool_specs(openai_tool_specs()) == compact_tool_specs(
        compact_tool_specs(openai_tool_specs())
    )


def test_older_answers_are_shortened_but_still_count_as_known(seeded: Session) -> None:
    old = "Your food spending was Rs. 4,410 this month. " + "Details. " * 120
    for role, text in [
        ("user", "food?"),
        ("assistant", old),
        ("user", "and groceries?"),
        ("assistant", "Groceries: Rs. 1,092.80 so far. " + "More. " * 100),
    ]:
        seeded.add(ChatMessage(user_id=USER, role=role, content=text))
    seeded.commit()
    # The answer repeats an amount from the OLDER answer: still grounded (no correction).
    llm = FakeLLM(say("Food was Rs. 4,410."))
    events = list(_service(seeded, llm).respond("remind me the food total"))
    sent = llm.calls[0][0]
    answers = [m["content"] for m in sent if m["role"] == "assistant"]
    assert len(answers[0]) <= OLDER_ANSWER_CHARS + 2 and answers[0].endswith(" …")
    assert answers[1].startswith("Groceries: Rs. 1,092.80") and len(answers[1]) > 600
    assert len(llm.calls) == 1  # no correction round
    assert "".join(e.data["text"] for e in events if e.event == "token") == "Food was Rs. 4,410."
