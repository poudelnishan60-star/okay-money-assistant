"""Khalti support's numbers end every answer where support comes up (decided 25 Nov 2026)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.chat import ChatService, support_line
from app.ai.safety import Lang
from app.models import ChatMessage
from app.rules import SUPPORT_LANDLINE, SUPPORT_TOLL_FREE, SUPPORT_WHATSAPP_VIBER
from app.sources.mock import MockBillSource, MockTransactionSource
from tests.conftest import ANCHOR, USER
from tests.fake_llm import FakeLLM, say


@pytest.mark.parametrize(
    "question",
    [
        "How do I contact Khalti support?",
        "I want to talk to a person",
        "where do I complain about a payment?",
        "ग्राहक सेवा को नम्बर के हो?",
        "khalti ko sampark number deu",
        "gunaso kaha garne?",
    ],
)
def test_support_questions_get_the_numbers(question: str) -> None:
    line = support_line(question, "Sure.", Lang.EN)
    assert line and SUPPORT_LANDLINE in line and SUPPORT_TOLL_FREE in line
    assert SUPPORT_WHATSAPP_VIBER in line


def test_an_answer_that_mentions_support_gets_the_numbers() -> None:
    assert support_line("my payment failed", "Contact Khalti support with the ID.", Lang.EN)


@pytest.mark.parametrize(
    "question", ["How much did I spend on food?", "What are the contactless card limits?"]
)
def test_other_questions_do_not(question: str) -> None:
    assert support_line(question, "Rs. 4,410 this month.", Lang.EN) is None


def test_not_twice_when_the_answer_already_has_them() -> None:
    assert support_line("contact?", f"Call {SUPPORT_LANDLINE}.", Lang.EN) is None


def test_nepali_label() -> None:
    assert "Khalti सहायता" in (support_line("सम्पर्क", "", Lang.NE) or "")


def test_chat_adds_and_keeps_the_numbers_unmasked(seeded: Session) -> None:
    source = MockTransactionSource(seeded)
    chat = ChatService(
        seeded,
        FakeLLM(say("You can reach Khalti any time.")),
        source,
        MockBillSource(source),
        USER,
        ANCHOR,
    )
    events = list(chat.respond("What is Khalti's customer care number?"))
    text = "".join(e.data["text"] for e in events if e.event == "token")
    assert SUPPORT_WHATSAPP_VIBER in text and SUPPORT_LANDLINE in text
    stored = seeded.scalars(
        select(ChatMessage).where(ChatMessage.role == "assistant").order_by(ChatMessage.id.desc())
    ).first()
    assert stored is not None and SUPPORT_WHATSAPP_VIBER in stored.content
