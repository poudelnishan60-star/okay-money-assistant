"""Answers with full detail, but not long: the cards under an answer show the lists, so its
words are cut in code to whole sentences up to SHORT_ANSWER_CHARS (lists and closing offers
left out). Since 24 Nov 2026; before, one very short sentence. Only text is taken out, so
no figure ever changes."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.chat import SHORT_ANSWER_CHARS, ChatService, shorten
from app.ai.file_memory import FileMemory
from app.ai.prompt import system_prompt
from app.ai.safety import Lang
from app.models import ChatMessage
from app.sources.mock import MockBillSource, MockTransactionSource
from tests.conftest import ANCHOR, USER
from tests.fake_llm import FakeLLM, call, say

# Seen live under a money-flow diagram.
LIVE = (
    "**Money in — Rs. 34,550**\n"
    "- Remittance: Rs. 27,500\n"
    "- Transfers in: Rs. 7,050\n\n"
    "**Money out — Rs. 25,822.33**\n"
    "- Transfers out: Rs. 3,600\n"
    "- Groceries: Rs. 6,402.02\n\n"
    "Your **total spent (excluding transfers and Smart Deposit) is Rs. 20,222.33** and you "
    "have **Rs. 8,727.67 left over** for the rest of the month."
)


@pytest.mark.parametrize(
    ("text", "short"),
    [
        (
            LIVE,
            "**Money in — Rs. 34,550**\n**Money out — Rs. 25,822.33**\n"
            "Your **total spent (excluding transfers and Smart Deposit) is Rs. 20,222.33** and "
            "you have **Rs. 8,727.67 left over** for the rest of the month.",
        ),
        (
            "You spent **Rs. 6,213.80** so far this month, 64.7% less than the same days of "
            "last month. Education was the biggest share. Want me to set a budget?",
            "You spent **Rs. 6,213.80** so far this month, 64.7% less than the same days of "
            "last month. Education was the biggest share.",
        ),
        (
            "Here are your budgets:\n- Food: Rs. 3,000 of Rs. 5,000\n- Groceries: Rs. 2,000",
            "Food: Rs. 3,000 of Rs. 5,000",
        ),
        (
            "यो महिना तपाईंले रु. 20,222.33 खर्च गर्नुभयो। किराना सबैभन्दा धेरै थियो। अरू केही चाहिन्छ?",
            "यो महिना तपाईंले रु. 20,222.33 खर्च गर्नुभयो। किराना सबैभन्दा धेरै थियो।",
        ),
        (
            "Yo mahina Rs. 20,222.33 kharcha bhayo. Groceries ma dherai gayo. Aru kehi?",
            "Yo mahina Rs. 20,222.33 kharcha bhayo. Groceries ma dherai gayo.",
        ),
    ],
)
def test_answers_are_cut_to_a_sentence_or_two(text: str, short: str) -> None:
    assert shorten(text) == short


def test_shortening_only_takes_text_out() -> None:
    out = shorten(LIVE)
    for part in out.split("\n"):
        assert part in LIVE  # nothing new, nothing reworded
    # One long sentence is kept whole, never cut in the middle.
    long = "You spent " + "a lot " * 60 + "on Rs. 1,270 worth of food."
    assert shorten(long) == long and len(long) > SHORT_ANSWER_CHARS
    # A bold part cut in two loses its stars instead of breaking the text.
    assert "**" not in shorten("**Total Rs. 500. Then more.** More text here " + "x" * 200)


def test_the_model_is_told_to_give_full_detail_but_briefly() -> None:
    prompt = system_prompt(dt.date(2026, 11, 18), Lang.EN)
    assert "Full detail, not long: give every detail the question needs" in prompt
    assert "Very short" not in prompt
    assert "never list what they show" in prompt


# --- in the chat ------------------------------------------------------------------------------


def _service(session: Session, llm: FakeLLM) -> ChatService:
    source = MockTransactionSource(session)
    return ChatService(
        session, llm, source, MockBillSource(source), USER, ANCHOR, files=FileMemory()
    )


def _final(events: list) -> str:  # type: ignore[type-arg]
    """The text left on screen: what came after the last reset."""
    resets = [i for i, e in enumerate(events) if e.event == "reset"]
    tail = events[resets[-1] + 1 :] if resets else events
    return "".join(e.data["text"] for e in tail if e.event == "token")


def _stored(session: Session) -> str:
    rows = session.scalars(select(ChatMessage).where(ChatMessage.role == "assistant")).all()
    return rows[-1].content


def test_an_answer_with_cards_is_cut_short(seeded: Session) -> None:
    words = (
        "You spent Rs. 1,270 on food this month.\n"
        "- Momo House\n- Bakery\n"
        "Want me to set a food budget?"
    )
    food = {"period": "this_month", "category": "Food & Dining"}
    llm = FakeLLM(call(("get_spending_summary", food)), say(words))
    events = list(_service(seeded, llm).respond("food spending?"))
    assert _final(events) == "You spent Rs. 1,270 on food this month."
    assert _stored(seeded) == "You spent Rs. 1,270 on food this month."
    assert events[-1].data["cards"]  # the card shows the details


def test_a_short_answer_is_left_alone(seeded: Session) -> None:
    food = {"period": "this_month", "category": "Food & Dining"}
    llm = FakeLLM(call(("get_spending_summary", food)), say("You spent Rs. 1,270 on food."))
    events = list(_service(seeded, llm).respond("food spending?"))
    assert "reset" not in [e.event for e in events]
    assert _final(events) == "You spent Rs. 1,270 on food."


def test_steps_without_a_card_keep_their_content(seeded: Session) -> None:
    # No card shows the details here (a how-to): the words are the answer.
    steps = "To load money:\n- Open Khalti\n- Tap Load Money\n- Choose your bank"
    llm = FakeLLM(say(steps))
    events = list(_service(seeded, llm).respond("how do I load money?"))
    assert "reset" not in [e.event for e in events]
    assert _final(events) == steps


def test_one_sentence_that_lists_everything_is_cut_between_two_items() -> None:
    # Seen live: 295 characters for every upcoming bill in one sentence.
    bills = (
        "Upcoming bills: **Rs. 1,300** Internet/TV (Gurans Fibernet) due in 4 days, "
        "**Rs. 450** Internet/TV (Sajilo DTH) due in 6 days, **Rs. 3,500** Education "
        "(Sikshya Language Institute) due in 18 days, **Rs. 499** Topup & Data (Ncell) due in "
        "22 days, **Rs. 1,140.67** Electricity (NEA) due in 25 days."
    )
    assert shorten(bills) == bills  # under the limit now: the whole sentence stays
    short = shorten(bills, 140)  # over a limit: cut between two items
    assert short == (
        "Upcoming bills: **Rs. 1,300** Internet/TV (Gurans Fibernet) due in 4 days, "
        "**Rs. 450** Internet/TV (Sajilo DTH) due in 6 days…"
    )
    assert len(short) <= 140 + 1
    assert bills.startswith(short.removesuffix("…"))  # a cut, nothing reworded
    assert "Rs. 1," not in short.split("…")[-1]  # never inside a number


def test_steps_with_only_a_button_are_kept(seeded: Session) -> None:
    # Seen live: a lost-phone answer's reporting steps were cut, as if a card listed them.
    steps = (
        "Tap Block my wallet below.\n"
        "- Report it to Khalti right away.\n"
        "- If you call, follow up in writing within 24 hours."
    )
    llm = FakeLLM(call(("open_app_flow", {"flow": "block_wallet"})), say(steps))
    events = list(_service(seeded, llm).respond("I lost my phone"))
    assert "reset" not in [e.event for e in events]
    assert _final(events) == steps
    assert [c["type"] for c in events[-1].data["cards"]] == ["open_app_flow"]


def test_the_model_shapes_the_answer_by_the_question() -> None:
    # The user chose (24 Nov 2026): each format for what it suits best.
    prompt = system_prompt(dt.date(2026, 11, 24), Lang.EN)
    for rule in (
        "a total: **the figure** first",
        "this vs that: both figures and the change",
        "Can I/Is it/Did I: **Yes.** or **No.** first",
        "(never for how-to or requests)",  # seen live: "Yes." before MPIN steps
        "how-to: numbered steps, only from a tool result (no made-up menus)",  # a made-up menu
        'facts, contacts, limits: "Label: value" lines',
        "a failed, pending or refunded payment: **status** · amount · merchant · date",
        "(· only there)",
        "a scam, shared OTP/MPIN or refused amount: the warning first, in bold",
        'a request with a button: what it does, then "Next:"',
    ):
        assert rule in prompt, rule
    assert "in the user's language" in prompt
