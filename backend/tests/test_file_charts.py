"""Chart cards for spreadsheets: worked out in code from every row (like the report the model
gets), shown with the answer, never stored, and narrowed to what a follow-up asks about."""

from __future__ import annotations

import datetime as dt
import json

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.attachments import Upload, read
from app.ai.cards import FileReportCard
from app.ai.chat import CHARTS_NOTE
from app.ai.file_memory import FileMemory
from app.models import ChatMessage
from tests.conftest import USER
from tests.fake_llm import FakeLLM, call, say
from tests.test_file_answers import STATEMENT, _service


def _chart(upload: Upload) -> FileReportCard | None:
    charts = read(upload, FakeLLM()).charts
    assert len(charts) <= 1
    return charts[0] if charts else None


def test_a_statement_gets_charts_worked_out_from_every_row() -> None:
    chart = _chart(STATEMENT)
    assert chart is not None
    assert chart.file_name == "new khalti statement.xlsx"
    assert (chart.rows, chart.start, chart.end) == (6, dt.date(2026, 10, 29), dt.date(2026, 11, 13))
    assert chart.measure == "out"
    # The same totals as the report's "Worked out in code" lines, in paisa.
    assert (chart.money_out_paisa, chart.money_in_paisa) == (4_794_31, 5_025_00)
    assert chart.type_column == "Type"
    assert [(s.label, s.paisa, s.share_percent, s.rows) for s in chart.by_type] == [
        ("Scan and Pay", 2_075_00, 43.3, 2),
        ("Transfer", 1_450_00, 30.2, 1),
        ("Service payment", 1_269_31, 26.5, 1),
    ]
    assert [(s.label, s.paisa, s.share_percent) for s in chart.in_by_type] == [
        ("Khalti hub load", 5_000_00, 99.5),
        ("Cashback", 25_00, 0.5),
    ]
    assert chart.period == "week"
    assert [(p.start, p.label, p.paisa, p.in_paisa) for p in chart.periods] == [
        (dt.date(2026, 10, 26), "26 Oct-1 Nov", 982_20, 5_000_00),
        (dt.date(2026, 11, 2), "2 Nov-8 Nov", 1_450_00, 0),
        (dt.date(2026, 11, 9), "9 Nov-15 Nov", 2_362_11, 25_00),
    ]
    assert chart.biggest_column == "Description"
    assert [(s.label, s.paisa, s.rows) for s in chart.biggest] == [
        ("Ratna Mart", 2_075_00, 2),
        ("Fund transfer to [phone]", 1_450_00, 1),
        ("NEA Electricity", 1_269_31, 1),
    ]
    # The balance as written in the file, oldest first: never added up.
    assert [(p.date, p.paisa) for p in chart.balance] == [
        (dt.date(2026, 10, 29), 14_017_80),
        (dt.date(2026, 11, 1), 19_017_80),
        (dt.date(2026, 11, 3), 17_567_80),
        (dt.date(2026, 11, 9), 16_475_00),
        (dt.date(2026, 11, 10), 16_500_00),
        (dt.date(2026, 11, 13), 15_230_69),
    ]
    assert (chart.balance_check, chart.balance_rows_checked, chart.balance_rows_off) == (
        "ok",
        5,
        0,
    )
    assert chart.sections == ["types", "periods", "biggest", "balance"]
    # Masked like the report: no title block (owner, phone), no numbers from cells.
    raw = chart.model_dump_json()
    assert "Sita" not in raw and "9801234567" not in raw and "9841234567" not in raw


def test_small_types_are_folded_into_other_so_the_pie_adds_up() -> None:
    lines = ["Date,Type,Debit"] + [
        f"2026-11-{d:02d},{t},{a}"
        for d, (t, a) in enumerate(
            [("A", 600), ("B", 500), ("C", 400), ("D", 300), ("E", 200), ("F", 60), ("G", 40)] * 2,
            start=1,
        )
    ]
    chart = _chart(Upload("t.csv", "\n".join(lines).encode()))
    assert chart is not None
    assert [s.label for s in chart.by_type] == ["A", "B", "C", "D", "E", "Other"]
    other = chart.by_type[-1]
    assert (other.is_other, other.paisa, other.rows, other.share_percent) == (True, 200_00, 4, 4.8)
    assert sum(s.paisa for s in chart.by_type) == chart.money_out_paisa


def test_a_sheet_with_one_amount_column_of_one_sign_is_charted_as_amounts() -> None:
    data = (
        b"Date,Category,Item,Amount\n2026-11-01,Food,Momo,250\n2026-11-02,Food,Tea,40\n"
        b"2026-11-03,Travel,Bus,50\n2026-11-10,Travel,Taxi,400\n"
    )
    chart = _chart(Upload("expenses.csv", data))
    assert chart is not None
    assert (chart.measure, chart.total_paisa, chart.money_out_paisa) == ("amount", 740_00, None)
    assert [(s.label, s.paisa) for s in chart.by_type] == [("Travel", 450_00), ("Food", 290_00)]
    assert [p.paisa for p in chart.periods] == [250_00, 90_00, 400_00]  # 1 Nov is a Sunday
    assert chart.sections == ["types", "periods", "biggest"]


def test_amounts_with_both_signs_are_only_totalled_not_broken_down() -> None:
    # "+" may mean spent or received, as in the text report: no pie of mixed signs.
    data = b"Date,Type,Amount\n2026-11-01,Load,1000\n2026-11-02,Pay,-300\n2026-11-03,Pay,-200\n"
    chart = _chart(Upload("signed.csv", data))
    assert chart is not None
    assert (chart.measure, chart.total_paisa, chart.sections) == (None, 500_00, [])


def test_a_sheet_without_money_has_no_chart() -> None:
    assert _chart(Upload("names.csv", b"Name,City\nSita,Pokhara\nRam,Butwal\n")) is None


# --- in the chat ------------------------------------------------------------------------------


def _done(events: list) -> dict:  # type: ignore[type-arg]
    assert events[-1].event == "done"
    return events[-1].data  # type: ignore[no-any-return]


def test_a_new_file_shows_every_chart_but_it_is_never_stored(seeded: Session) -> None:
    llm = FakeLLM(say("Money out was Rs. 4,794.31."))
    done = _done(list(_service(seeded, llm).respond("analyze this", "auto", [STATEMENT])))
    (card,) = done["cards"]
    assert card["type"] == "file_report"
    assert card["sections"] == ["types", "periods", "biggest", "balance"]
    # What was read from a file stays in memory only: the stored answer has no chart.
    stored = seeded.scalars(select(ChatMessage).where(ChatMessage.id == done["message_id"])).one()
    assert json.loads(stored.cards_json) == []
    assert "Ratna Mart" not in stored.cards_json


@pytest.mark.parametrize(
    ("question", "sections"),
    [
        ("Week by week in the file", ["periods"]),
        ("Break the file down by type", ["types"]),
        ("Biggest payments in the file", ["biggest"]),
        ("How did the balance change?", ["balance"]),
        ("Where can I cut back?", ["types", "biggest"]),
        ("Money in vs money out in the file", ["periods"]),
        ("Sum up the file in 3 lines", ["types", "periods", "biggest", "balance"]),
        ("Anything unusual in the file?", ["types", "periods", "biggest", "balance"]),
        ("फाइलमा हप्ता अनुसार", ["periods"]),
        ("ब्यालेन्स कसरी बदलियो?", ["balance"]),
        ("File lai type anusar chhutyau", ["types"]),
        ("File ka sabai bhanda thula payment", ["biggest"]),
    ],
)
def test_a_follow_up_shows_the_charts_it_asks_about(
    seeded: Session, question: str, sections: list[str]
) -> None:
    files = FileMemory()
    files.remember(USER, [read(STATEMENT, FakeLLM())])
    llm = FakeLLM(say("Most went to Ratna Mart: Rs. 2,075."))
    (card,) = _done(list(_service(seeded, llm, files).respond(question)))["cards"]
    assert card["sections"] == sections


def test_a_follow_up_that_names_no_chart_gets_none(seeded: Session) -> None:
    files = FileMemory()
    files.remember(USER, [read(STATEMENT, FakeLLM())])
    llm = FakeLLM(say("Ratna Mart is a shop."))
    assert _done(list(_service(seeded, llm, files).respond("what is Ratna Mart?")))["cards"] == []


def test_a_question_about_the_account_gets_no_file_chart(seeded: Session) -> None:
    files = FileMemory()
    files.remember(USER, [read(STATEMENT, FakeLLM())])
    llm = FakeLLM(call(("get_budgets", {})), say("You have 4 budgets."))
    cards = _done(list(_service(seeded, llm, files).respond("show my budgets by type")))["cards"]
    assert "file_report" not in [c["type"] for c in cards]


def test_the_charts_come_even_when_the_ai_is_busy(seeded: Session) -> None:
    # Worked out in code, so a busy AI service doesn't take them away.
    from app.ai.llm import LLMBusyError

    class Busy(FakeLLM):
        def stream_chat(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise LLMBusyError("busy")
            yield  # pragma: no cover

    done = _done(list(_service(seeded, Busy()).respond("analyze this", "auto", [STATEMENT])))
    assert done["error"] == "busy"
    assert [c["type"] for c in done["cards"]] == ["file_report"]


def test_the_model_is_told_the_charts_are_under_its_answer(seeded: Session) -> None:
    # Seen live: with the charts under it, an answer listing every type, week and payment
    # said everything twice.
    llm = FakeLLM(say("Money out was Rs. 4,794.31."))
    list(_service(seeded, llm).respond("analyze this", "auto", [STATEMENT]))
    assert CHARTS_NOTE in llm.calls[0][0][-1]["content"]

    files = FileMemory()
    files.remember(USER, [read(STATEMENT, FakeLLM())])
    llm = FakeLLM(say("Ratna Mart is a shop."))
    list(_service(seeded, llm, files).respond("what is Ratna Mart?"))  # gets no chart
    assert CHARTS_NOTE not in llm.calls[0][0][-1]["content"]
