"""Answers about files: the sheet report worked out in code, follow-up questions (the
reading is remembered for an hour), never passing the account's figures off as the file's,
and keeping requests under Groq's size limit."""

from __future__ import annotations

import io
import json

import httpx
import openai
import pytest
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.attachments import Reading, Upload, read
from app.ai.chat import ChatService
from app.ai.file_memory import FileMemory
from app.ai.llm import LLMTooLargeError
from app.ai.safety import MESSAGES, Lang
from app.ai.sheets import rupees
from app.ai.tools import openai_tool_specs
from app.models import ChatMessage
from app.sources.mock import MockBillSource, MockTransactionSource
from tests.conftest import ANCHOR, USER
from tests.fake_llm import FakeLLM, call, say
from tests.test_ai_safety_llm import REQ, _chunk, _client

HEADER = [
    "S.N.",
    "Date",
    "Transaction ID",
    "Description",
    "Type",
    "Amount(-) Rs",
    "Amount(+) Rs",
    "Balance",
    "Status",
]
# Newest first, like a wallet statement. Balance runs from Rs. 15,000 before the first entry.
ROWS = [
    [
        1,
        "2026-11-13 18:20",
        "TXN8812345678",
        "NEA Electricity",
        "Service payment",
        1269.31,
        None,
        15230.69,
        "Completed",
    ],  # noqa: E501
    [
        2,
        "2026-11-10 09:15",
        "TXN8812345679",
        "Cashback on Scan and Pay",
        "Cashback",
        None,
        25,
        16500,
        "Completed",
    ],  # noqa: E501
    [
        3,
        "2026-11-09 12:00",
        "TXN8812345680",
        "Ratna Mart",
        "Scan and Pay",
        1092.80,
        None,
        16475,
        "Completed",
    ],  # noqa: E501
    [
        4,
        "2026-11-03 08:00",
        "TXN8812345681",
        "Fund transfer to 9841234567",
        "Transfer",
        1450,
        None,
        17567.80,
        "Completed",
    ],  # noqa: E501
    [
        5,
        "2026-11-01 10:00",
        "TXN8812345682",
        "Load from bank",
        "Khalti hub load",
        None,
        5000,
        19017.80,
        "Completed",
    ],  # noqa: E501
    [
        6,
        "2026-10-29 19:30",
        "TXN8812345683",
        "Ratna Mart",
        "Scan and Pay",
        982.20,
        None,
        14017.80,
        "Completed",
    ],  # noqa: E501
]


def statement() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Statement"
    ws.append(["Khalti Wallet Statement"])
    ws.append(["Name: Sita Sharma", None, "Mobile: 9801234567"])
    ws.append([])
    ws.append(HEADER)
    for row in ROWS:
        ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


STATEMENT = Upload("new khalti statement.xlsx", statement())


# --- the sheet report -------------------------------------------------------------------------


def test_a_statement_is_reported_from_every_row() -> None:
    text = read(STATEMENT, FakeLLM()).content
    assert text.startswith(
        "Sheet 'Statement': 6 rows, dated 29 Oct 2026 to 13 Nov 2026. Columns: S.N., Date, "
        "Transaction ID, Description, Type, Amount(-) Rs, Amount(+) Rs, Balance, Status."
    )
    for line in [
        "Worked out in code from all 6 rows (complete; use these for totals):",
        "- Amount(-) Rs (money out): Rs. 4,794.31 over 4 rows, largest Rs. 1,450.",
        "- Amount(+) Rs (money in): Rs. 5,025 over 2 rows, largest Rs. 5,000.",
        "- Money in minus money out: Rs. 230.69.",
        # A running balance is never added up: its value after the oldest and newest entry.
        "- Balance: Rs. 14,017.80 after the oldest entry (29 Oct 2026), Rs. 15,230.69 after "
        "the newest entry (13 Nov 2026), up Rs. 1,212.89 between them. It is a running "
        "balance, so it is not added up.",
        "- Balance check (done in code, row by row): Balance follows money in and out on "
        "every row (5 rows checked).",
        "- By Type: Scan and Pay: 2 rows, out Rs. 2,075; Transfer: 1 row, out Rs. 1,450; "
        "Service payment: 1 row, out Rs. 1,269.31; Khalti hub load: 1 row, in Rs. 5,000; "
        "Cashback: 1 row, in Rs. 25.",
        "- Biggest money out by Description: Ratna Mart: Rs. 2,075 (2 rows); Fund transfer "
        "to [phone]: Rs. 1,450 (1 row); NEA Electricity: Rs. 1,269.31 (1 row).",
        "- By week (Monday to Sunday): 26 Oct-1 Nov: 2 rows, out Rs. 982.20, in Rs. 5,000; "
        "2 Nov-8 Nov: 1 row, out Rs. 1,450; 9 Nov-15 Nov: 3 rows, out Rs. 2,362.11, in Rs. 25.",
        "All 6 rows:",
    ]:
        assert line in text, line
    # Not summed: row numbers, IDs, the balance. Not a type: the one-value Status column.
    assert "S.N.:" not in text and "Transaction ID:" not in text and "By Status" not in text
    # The title block (owner's name and phone) is left out; numbers in cells are masked.
    assert "Sita" not in text and "9801234567" not in text and "9841234567" not in text
    assert "8812345678" not in text


def test_the_balance_is_checked_row_by_row_in_code() -> None:
    # Seen live: asked "anything unusual?", a model checked the rows itself and called a
    # correct statement wrong. Now code checks, and says which rows don't follow.
    head = b"Date,Description,Debit,Credit,Balance\n"
    wrong = head + (
        b"2026-11-01,Load,,1000,1000\n2026-11-02,Tea,100,,900\n"
        b"2026-11-03,Bus,50,,800\n2026-11-04,Shop,200,,600\n"
    )
    text = read(Upload("w.csv", wrong), None).content
    assert (
        "- Balance check (done in code, row by row): Balance does not follow money in and "
        "out on 1 of 3 rows checked, for example: 3 Nov 2026, Bus." in text
    )
    # Newest first, as statements often are: still checked oldest to newest.
    newest_first = head + b"2026-11-02,Tea,100,,900\n2026-11-01,Load,,1000,1000\n"
    assert (
        "follows money in and out on every row (1 row checked)"
        in read(Upload("n.csv", newest_first), None).content
    )
    # Rows out of date order: most don't follow, so nothing is said rather than a false alarm.
    shuffled = head + (
        b"2026-11-03,Bus,50,,850\n2026-11-01,Load,,1000,1000\n"
        b"2026-11-04,Shop,200,,650\n2026-11-02,Tea,100,,900\n"
    )
    assert "Balance check" not in read(Upload("x.csv", shuffled), None).content


def test_amounts_use_nepali_grouping() -> None:
    from decimal import Decimal

    assert rupees(Decimal("1015410.86")) == "Rs. 10,15,410.86"
    assert rupees(Decimal("-350.00")) == "-Rs. 350"
    assert rupees(Decimal("12"), prefix=False) == "12"


def test_a_long_sheet_shows_the_report_and_only_the_rows_that_fit() -> None:
    rows = [["Date", "Description", "Debit", "Credit"]] + [
        [f"2026-11-{1 + i % 28:02d}", f"Shop {i}", 100 + (i * 7) % 50, None] for i in range(400)
    ]
    data = "\n".join(",".join("" if c is None else str(c) for c in r) for r in rows).encode()
    text = read(Upload("long.csv", data), FakeLLM()).content
    # 400 x 100, plus each of 0..49 eight times.
    assert "Debit (money out): Rs. 49,800 over 400 rows" in text
    # The listed rows are said to be a sample, so the model doesn't think it is missing data.
    assert "Worked out in code from all 400 rows (complete; use these for totals):" in text
    assert " of 400 rows, only a sample (the worked-out lines above cover all 400 rows):" in text
    assert len(text) <= 5_000


# --- remembering a file for follow-ups --------------------------------------------------------


def _reading(name: str) -> Reading:
    return Reading(name=name, kind="spreadsheet", content=f"rows of {name}")


def test_file_memory_expires_and_forgets() -> None:
    now = [0.0]
    memory = FileMemory(60, clock=lambda: now[0])
    memory.remember("u1", [_reading("a.csv")])
    now[0] = 30 * 60
    memory.remember("u1", [_reading("b.csv"), _reading("a.csv")])  # same name: replaced
    assert [r.name for r in memory.recall("u1")] == ["b.csv", "a.csv"]
    assert memory.recall("u2") == []
    now[0] = 61 * 60  # the first a.csv would have expired; the new one hasn't
    assert [r.name for r in memory.recall("u1")] == ["b.csv", "a.csv"]
    now[0] = 91 * 60
    assert memory.recall("u1") == []
    memory.remember("u1", [_reading(f"{i}.csv") for i in range(5)])
    assert [r.name for r in memory.recall("u1")] == ["2.csv", "3.csv", "4.csv"]  # latest 3
    memory.forget("u1")
    assert memory.recall("u1") == []
    off = FileMemory(0)
    off.remember("u1", [_reading("a.csv")])
    assert off.recall("u1") == []


def _service(session: Session, llm: FakeLLM, files: FileMemory | None = None) -> ChatService:
    source = MockTransactionSource(session)
    return ChatService(
        session, llm, source, MockBillSource(source), USER, ANCHOR, files=files or FileMemory()
    )


def _text(events: list) -> str:  # type: ignore[type-arg]
    return "".join(e.data["text"] for e in events if e.event == "token")


def test_follow_up_questions_still_see_the_file(seeded: Session) -> None:
    files = FileMemory()
    llm = FakeLLM(
        say("Money out was Rs. 4,794.31 and money in Rs. 5,025."),
        say("Most went to Ratna Mart: Rs. 2,075 over 2 payments."),
    )
    first = list(_service(seeded, llm, files).respond("analyze this", "auto", [STATEMENT]))
    assert "reset" not in [e.event for e in first]
    chips = [s["text"] for s in first[-1].data["suggestions"]]
    assert chips == [
        "Break the file down by type",
        "Biggest payments in the file",
        "Anything unusual in the file?",
        "Where can I cut back?",
        "Week by week in the file",
    ]

    second = list(_service(seeded, llm, files).respond("where did most of my money go?"))
    assert "reset" not in [e.event for e in second]  # Rs. 2,075 is in the remembered file
    assert _text(second) == "Most went to Ratna Mart: Rs. 2,075 over 2 payments."
    messages = llm.calls[1][0]
    turn = messages[-1]["content"]
    assert turn.startswith("where did most of my money go?")
    assert "Files the user added earlier in this chat" in turn
    assert '<attachment name="new khalti statement.xlsx" kind="spreadsheet">' in turn
    assert "separate from these files" in turn
    # The history says which message had the file.
    assert messages[1] == {
        "role": "user",
        "content": "analyze this\n[Attached: new khalti statement.xlsx]",
    }
    assert second[-1].data["suggestions"][0]["text"] == "Break the file down by type"
    assert llm.max_tokens == [900, 900]  # room for a report about the file

    # The file itself is never stored; only its name.
    stored = " ".join(seeded.scalars(select(ChatMessage.content)))
    assert "Ratna Mart: Rs. 2,075" in stored  # the answer, as said
    assert "Amount(-) Rs (money out)" not in stored


def test_once_forgotten_the_model_is_told_the_file_is_gone(seeded: Session) -> None:
    files = FileMemory()
    llm = FakeLLM(say("It is a statement."), say("I can no longer see that file."))
    list(_service(seeded, llm, files).respond("what is this?", "auto", [STATEMENT]))
    files.forget(USER)
    list(_service(seeded, llm, files).respond("and by week?"))
    assert llm.max_tokens == [900, None]  # usual short answers again
    turn = llm.calls[1][0][-1]["content"]
    assert "<attachment" not in turn
    assert llm.calls[1][0][1]["content"].endswith("[Attached: new khalti statement.xlsx]")


def test_a_question_about_another_topic_uses_tools_and_gets_their_chips(seeded: Session) -> None:
    files = FileMemory()
    files.remember(USER, [read(STATEMENT, FakeLLM())])
    llm = FakeLLM(call(("get_budgets", {})), say("You have 4 budgets."))
    events = list(_service(seeded, llm, files).respond("show my budgets"))
    chips = [s["text"] for s in events[-1].data["suggestions"]]
    assert "Break the file down by type" not in chips


# --- never passing the account's figures off as the file's ------------------------------------


def test_a_made_up_figure_about_a_file_is_corrected_from_the_file(seeded: Session) -> None:
    llm = FakeLLM(
        say("Groceries were Rs. 9,999."),  # worked out by the model: not in the file
        say("Ratna Mart took Rs. 2,075."),
    )
    events = list(_service(seeded, llm).respond("detailed report", "auto", [STATEMENT]))
    assert [e.event for e in events].count("reset") == 1
    assert _text(events[[e.event for e in events].index("reset") :]) == "Ratna Mart took Rs. 2,075."
    correction = llm.calls[1][0][-1]
    assert correction["role"] == "system"
    assert "not in the file's worked-out figures" in correction["content"]
    assert "Don't call tools for the file" in correction["content"]
    # Not forced to call a tool: the tools would answer with the account's numbers.
    assert llm.tool_choices == ["auto", "auto"]
    # No account cards: only the file's own chart, worked out in code.
    assert [c["type"] for c in events[-1].data["cards"]] == ["file_report"]


def test_sums_the_model_adds_up_itself_are_taken_out_of_a_report(seeded: Session) -> None:
    # Seen live: a detailed report kept "food places total Rs. 26,706.50" after the
    # correction. The file's own figures stay; the self-made sum goes, with its heading.
    report = (
        "**From the file:**\n"
        "- Money out: Rs. 4,794.31\n"
        "- Money in: Rs. 5,025\n\n"
        "**Highlights:**\n"
        "- Ratna Mart and Himalayan Java together: **Rs. 3,141.59**"
    )
    llm = FakeLLM(say(report), say(report))
    service = _service(seeded, llm)
    events = list(service.respond("detailed report", "auto", [STATEMENT]))
    kept = "**From the file:**\n- Money out: Rs. 4,794.31\n- Money in: Rs. 5,025"
    last_reset = max(i for i, e in enumerate(events) if e.event == "reset")
    assert _text(events[last_reset + 1 :]) == kept
    assert service.dropped_sentences == 1
    stored = seeded.scalars(select(ChatMessage.content).where(ChatMessage.role == "assistant"))
    assert list(stored) == [kept]


def test_the_turn_says_tools_read_the_account_not_the_file(seeded: Session) -> None:
    llm = FakeLLM(say("ok"))
    list(_service(seeded, llm).respond("yo file ma kati kharcha bhayo?", "auto", [STATEMENT]))
    turn = llm.calls[0][0][-1]["content"]
    assert "The tools read the user's Khalti account" in turn
    assert turn.endswith("(Reply in Romanized Nepali.)")  # the language reminder stays last
    system = llm.calls[0][0][0]["content"]
    assert "never add rows up or check their arithmetic yourself" in system


# --- staying under the provider's size limit -------------------------------------------------


def test_old_history_is_left_out_to_fit_the_budget(seeded: Session) -> None:
    for i in range(20):
        role = "user" if i % 2 == 0 else "assistant"
        seeded.add(ChatMessage(user_id=USER, role=role, content=f"m{i} " + "x" * 1500))
    seeded.commit()
    llm = FakeLLM(say("hi"))
    list(_service(seeded, llm).respond("hello", "auto", [STATEMENT]))
    messages = llm.calls[0][0]
    assert messages[0]["role"] == "system" and messages[-1]["content"].startswith("hello")
    assert 1 < len(messages) < 22
    chars = len(json.dumps(openai_tool_specs())) + sum(len(m["content"]) + 12 for m in messages)
    assert chars // 3 <= 5000
    assert messages[1]["content"].startswith("m1")  # the newest history is kept


def test_413_moves_to_the_next_model() -> None:
    too_big = openai.APIStatusError(
        "Request too large", response=httpx.Response(413, request=REQ), body=None
    )
    llm, comp, _ = _client([too_big, [_chunk("ok")]])
    assert [e.text for e in llm.stream_chat([], None)] == ["ok"]
    assert [r["model"] for r in comp.requests] == ["qwen/qwen3.8-27b", "openai/gpt-oss-120b"]


def test_413_everywhere_says_too_much() -> None:
    too_big = openai.APIStatusError(
        "Request too large", response=httpx.Response(413, request=REQ), body=None
    )
    llm, _, _ = _client([too_big] * 3)
    with pytest.raises(LLMTooLargeError):
        list(llm.stream_chat([], None))


def test_too_large_in_the_chat(seeded: Session) -> None:
    llm = FakeLLM(LLMTooLargeError("413"))
    events = list(_service(seeded, llm).respond("analyze", "auto", [STATEMENT]))
    assert events[-1].data["error"] == "too_large"
    assert _text(events).endswith(MESSAGES["too_large"][Lang.EN])


def test_clearing_the_chat_forgets_the_files(make_client) -> None:
    import base64

    llm = FakeLLM(say("It is a statement."), say("ok"))
    c = make_client(llm=llm)
    body = {
        "message": "what is this?",
        "attachments": [
            {"name": STATEMENT.name, "data_base64": base64.b64encode(STATEMENT.data).decode()}
        ],
    }
    assert c.post("/chat", json=body).status_code == 200
    assert c.app.state.file_memory.recall(USER) != []
    assert c.delete("/chat/history").status_code == 204
    assert c.app.state.file_memory.recall(USER) == []
