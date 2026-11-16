"""Follow-up chips: more questions after a file, new ones as the chat goes on, and only the
questions a sheet's report can answer."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.ai.attachments import Upload, read
from app.ai.cards import Suggestion
from app.ai.file_memory import FileMemory
from app.ai.safety import Lang, detect_language
from app.ai.sheets import report_parts
from app.ai.suggestions import _CHIPS, suggestions_for
from tests.fake_llm import FakeLLM, say
from tests.test_file_answers import STATEMENT, _service


def _texts(chips: list[Suggestion]) -> list[str]:
    return [c.text for c in chips]


def test_every_chip_is_read_back_in_its_own_language() -> None:
    # A tapped chip is sent as the user's message, so it must get a reply in its language.
    for chip, texts in _CHIPS.items():
        for lang, text in texts.items():
            assert detect_language(text) is lang, (chip, text)


def test_a_statement_gets_five_questions_and_new_ones_as_they_are_asked() -> None:
    parts = report_parts(read(STATEMENT, FakeLLM()).content)
    assert parts == {"in_out", "balance", "periods", "types", "biggest"}
    first = suggestions_for({"attachment_table"}, Lang.EN, "analyze this", file_parts=parts)
    assert _texts(first) == [
        "Break the file down by type",
        "Biggest payments in the file",
        "Anything unusual in the file?",
        "Where can I cut back?",
        "Week by week in the file",
    ]
    later = suggestions_for(
        {"attachment_table"},
        Lang.EN,
        "Biggest payments in the file",
        asked_before=["analyze this", "Break the file down by type"],
        file_parts=parts,
    )
    assert _texts(later) == [
        "Anything unusual in the file?",
        "Where can I cut back?",
        "Week by week in the file",
        "Compare the file with my Khalti account",
        "Money in vs money out in the file",
    ]


def test_a_sheet_only_gets_the_questions_its_report_answers() -> None:
    # One signed Amount column and a description: no types, dates, balance or in/out split.
    plain = read(Upload("plain.csv", b"Description,Amount\nTea,100\nBus,-50\nShop,200\n"), None)
    parts = report_parts(plain.content)
    assert parts == {"biggest"}
    chips = suggestions_for({"attachment_table"}, Lang.EN, "what is this?", file_parts=parts)
    assert _texts(chips) == [
        "Biggest payments in the file",
        "Anything unusual in the file?",
        "Where can I cut back?",
        "Compare the file with my Khalti account",
        "Sum up the file in 3 lines",
    ]
    # Rows that look like report lines don't count: only the worked-out lines are read.
    assert report_parts("All 1 row:\nNote\n- By Type: x") == set()


def test_a_receipt_or_bill_gets_its_own_questions() -> None:
    chips = suggestions_for({"attachment"}, Lang.ROM, "yo ke ho?")
    assert _texts(chips) == [
        "Maile ke ko lagi tirey?",
        "File lai 3 line ma bhana",
        "Yo mero kharcha sanga kasto chha?",
        "Mero paisa kaha gayo?",
        "Mero budget dekhau",
    ]


def test_account_answers_keep_three_chips_and_repeat_only_when_all_were_asked() -> None:
    assert len(suggestions_for({"spending"}, Lang.EN)) == 3
    chips = suggestions_for(
        {"goals"}, Lang.EN, "How are my goals?", asked_before=["Will I run low this month?"]
    )
    assert _texts(chips) == ["Where did my money go?", "Smart Deposit"]
    # Everything was asked already: offered again, but never the question just asked.
    chips = suggestions_for(
        {"goals"}, Lang.EN, "Where did my money go?", asked_before=["Will I run low this month?"]
    )
    assert _texts(chips) == ["Will I run low this month?", "Smart Deposit"]


def test_chips_move_on_to_questions_not_asked_yet_in_the_chat(seeded: Session) -> None:
    files = FileMemory()
    llm = FakeLLM(
        say("It is a statement."),
        say("By type it is mostly Scan and Pay."),
        say("Ratna Mart is the biggest."),
    )
    list(_service(seeded, llm, files).respond("analyze this", "auto", [STATEMENT]))
    list(_service(seeded, llm, files).respond("Break the file down by type"))
    third = list(_service(seeded, llm, files).respond("Biggest payments in the file"))
    assert [s["text"] for s in third[-1].data["suggestions"]] == [
        "Anything unusual in the file?",
        "Where can I cut back?",
        "Week by week in the file",
        "Compare the file with my Khalti account",
        "Money in vs money out in the file",
    ]
