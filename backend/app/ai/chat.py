"""Chat orchestration: history, masking, the tool loop, cards, chips, persistence, audit log.

Events produced (sent as server-sent events by routes_chat):
  status  {"tool": "..."}                         a tool is running (optional for clients)
  token   {"text": "..."}                         streamed answer text
  reset   {}                                      drop the text so far: the answer failed
                                                  the grounding check and is redone (or,
                                                  if the redo fails too, sent again
                                                  without the sentences that fail it)
  done    {"message_id", "cards", "suggestions", "language", "error"}   always last
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
import time
from collections.abc import Generator, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.attachments import AttachmentError, Reading, Upload, as_block, kind_of, read
from app.ai.file_memory import FileMemory
from app.ai.llm import (
    LLMBusyError,
    LLMClient,
    LLMNotConfiguredError,
    LLMTooLargeError,
    LLMUnavailableError,
    Message,
    TextDelta,
    ToolCall,
    ToolCallsReady,
    parse_arguments,
)
from app.ai.prompt import system_prompt
from app.ai.safety import Lang, detect_language, mask_pii, message, redact_secrets
from app.ai.sheets import report_parts
from app.ai.suggestions import suggestions_for
from app.ai.tools import ToolContext, ToolError, ToolResult, openai_tool_specs, run_tool
from app.models import ChatMessage, ToolCallLog
from app.sources.base import BillSource, TransactionSource

log = logging.getLogger(__name__)
audit = logging.getLogger("okay.audit")

MAX_CARDS = 4
# Answers about a file may be a report: room for more than the usual short answer.
FILE_ANSWER_TOKENS = 900
_REPLY_IN = {
    Lang.NE: "Reply in Nepali, in Devanagari.",
    Lang.ROM: "Reply in Romanized Nepali.",
}

_AMOUNT = re.compile(r"(?:Rs\.?|रु\.?)\s?[\d,०-९]+(?:\.[\d०-९]+)?")
_BARE_NUMBER = re.compile(r"[\d०-९][\d,०-९]*(?:\.[\d०-९]+)?")
_CONFIRM_CLAIM = re.compile(
    r"(?:tap|press|click|thich\w*|थिच\w*)\W+(?:\w+\W+){0,3}?(?:\*\*)?confirm"
    r"|confirm(?:\*\*)?\W+(?:\w+\W+){0,2}?(?:thich\w*|थिच\w*)",
    re.IGNORECASE,
)
_BUTTON_CLAIM = re.compile(
    r"button below|tap the [^.]{0,40}button|I(?:'ve| have) opened|tala ko button|तलको बटन",
    re.IGNORECASE,
)


def _norm(number: str) -> str:
    """'Rs. 1,270.00' / 'रु. १,२७०' / '1270' -> '1270'."""
    number = re.sub(r"^(?:Rs\.?|रु\.?)\s*", "", number.strip())
    digits = number.translate(str.maketrans("०१२३४५६७८९", "0123456789"))
    digits = re.sub(r"[^\d.]", "", digits)
    return re.sub(r"\.0+$", "", digits)


def check_answer(
    text: str, cards: list[dict[str, Any]], grounded: str, *, files: bool = False
) -> str | None:
    """Code-level guard for "the LLM never makes up numbers or actions". Returns the
    problem to correct, or None if the answer is fine.

    - every "Rs." amount must appear in a tool result or a file this turn, or earlier in the
      chat;
    - "tap Confirm" needs a confirm_action card, "the button below" an open_app_flow card.

    `files`: the turn is about a file. Then the fix is to use the figures worked out from the
    file, not to call a tool: the tools read the Khalti account, a different set of numbers.
    """
    allowed = _allowed(grounded)
    bad = sorted({a for a in _AMOUNT.findall(text) if _norm(a) not in allowed})
    if bad and files:
        return (
            f"ungrounded amounts: {', '.join(bad)} are not in the file's worked-out figures "
            "or any tool result. Use only figures printed in the <attachment> (its 'Worked "
            "out in code' lines) or returned by tools; never add up or work out figures "
            "yourself. If the file doesn't show a figure, say so. Don't call tools for the "
            "file: they read the Khalti account, not the file."
        )
    if bad:
        return (
            f"ungrounded amounts: {', '.join(bad)} are not in any tool result. Call the "
            "right tool and use only the amounts it returns."
        )
    shown = {c.get("type") for c in cards}
    if _CONFIRM_CLAIM.search(text) and "confirm_action" not in shown:
        return (
            "missing confirm card: you told the user to tap Confirm, but no Confirm card "
            "was shown. Call upsert_budget or upsert_goal, or don't mention Confirm."
        )
    if _BUTTON_CLAIM.search(text) and "open_app_flow" not in shown:
        return (
            "missing button: you mentioned a button or an opened screen, but none was "
            "shown. Call open_app_flow, or don't mention it."
        )
    return None


def _allowed(grounded: str) -> set[str]:
    return {_norm(a) for a in _BARE_NUMBER.findall(grounded)}


# A sentence ends at . ! ? or । followed by a space, but not at the dot of "Rs." / "रु.".
_SENTENCE_END = re.compile(r"(?<=[.!?।])(?<!Rs\.)(?<!रु\.)\s+")
_LIST_MARKER = re.compile(r"\s*(?:[-*•]|\d{1,2}[.)])\s+")


def drop_ungrounded(text: str, cards: list[dict[str, Any]], grounded: str) -> tuple[str, int]:
    """Last resort when the corrected answer still fails check_answer: take out the sentences
    that state an amount no tool result or file gave (a sum the model added up itself, say),
    or that promise a card that isn't shown. The rest of the answer stays.

    Returns the cleaned text ("" if nothing is left) and how many sentences were taken out.
    A list's intro line ("Highlights:") goes too when every line under it was taken out.
    """
    allowed = _allowed(grounded)
    shown = {c.get("type") for c in cards}

    def fails(sentence: str) -> bool:
        return (
            any(_norm(a) not in allowed for a in _AMOUNT.findall(sentence))
            or bool(_CONFIRM_CLAIM.search(sentence) and "confirm_action" not in shown)
            or bool(_BUTTON_CLAIM.search(sentence) and "open_app_flow" not in shown)
        )

    dropped = 0
    lines: list[str | None] = []  # None: the whole line was taken out
    for line in text.split("\n"):
        if not fails(line):
            lines.append(line)
            continue
        marker = _LIST_MARKER.match(line)
        head = marker.group(0) if marker else ""
        parts = _SENTENCE_END.split(line[len(head) :])
        kept = [p for p in parts if not fails(p)]
        if len(kept) == len(parts):  # the claim spans sentences: nothing to take out
            lines.append(line)
            continue
        dropped += len(parts) - len(kept)
        rest = " ".join(kept).strip()
        if rest.count("**") % 2:  # a bold run lost its other half
            rest = rest.replace("**", "")
        lines.append(head + rest if rest else None)

    def is_intro(line: str | None) -> bool:
        return line is not None and line.strip().strip("*").strip().endswith(":")

    for i, line in enumerate(lines):
        if not is_intro(line):
            continue
        under = []  # the lines under the intro: up to the next blank line or intro
        for after in lines[i + 1 :]:
            if is_intro(after):
                break
            if after is not None and not after.strip():
                if under:
                    break
                continue
            under.append(after)
        if under and all(u is None for u in under):
            lines[i] = None

    out: list[str] = []
    for line in lines:
        if line is None or (not line.strip() and (not out or not out[-1].strip())):
            continue
        out.append(line)
    return "\n".join(out).strip(), dropped


class _NothingToAsk(Exception):
    """Every attached file failed to read and the user typed nothing: no model call."""


def _file_topic(readings: Sequence[Reading]) -> str:
    """Chips about the file: a sheet can be broken down; a photo or PDF compared."""
    return "attachment_table" if any(r.kind == "spreadsheet" for r in readings) else "attachment"


MAX_CHART_CARDS = 3
_FILE_TOPICS = {"attachment", "attachment_table"}
CHARTS_NOTE = (
    "Under your answer the app shows charts of the file's worked-out figures (money in and "
    "out, by type, week by week, biggest payments, balance). So keep the text short: the main "
    "totals and the 2-3 points that matter most, not every type, week or payment."
)
# Which of a sheet's charts a follow-up is about, in English, Nepali or Romanized Nepali. A
# new file shows every chart; a follow-up that names none shows none (the text answers it).
_ALL_CHARTS = re.compile(
    r"sum ?up|summar|overview|analy[sz]|unusual|asamanya|असामान्य|\b3 lines?\b|३ लाइन|"
    r"saransh|सारांश|chart|graph|visual|dekhau|देखाऊ",
    re.IGNORECASE,
)
_CHART_WORDS: dict[str, re.Pattern[str]] = {
    "types": re.compile(
        r"\btypes?\b|\bkinds?\b|break\w* (?:it |the file )?down|breakdown|prakar|प्रकार|kisim"
        r"|किसिम|categor|cut back|kam garna|कम गर्न",
        re.IGNORECASE,
    ),
    "periods": re.compile(
        r"\bweek|hapta|हप्ता|\bmonth|mahina|महिना|money in|\bin vs|in and out|aayeko|आएको"
        r"|gayeko|गएको",
        re.IGNORECASE,
    ),
    "biggest": re.compile(
        r"biggest|largest|\btop\b|thul[oa]|ठूल|sabai ?bhanda|सबैभन्दा|cut back|kam garna"
        r"|कम गर्न|paid for|ke ko lagi|केको लागि|spen[dt] (?:the )?most",
        re.IGNORECASE,
    ),
    "balance": re.compile(r"balance|ब्यालेन्स|मौज्दात", re.IGNORECASE),
}


def chart_cards(
    readings: Sequence[Reading], remembered: Sequence[Reading], question: str, *, account: bool
) -> list[dict[str, Any]]:
    """Chart cards for spreadsheets: every chart for files added with this message; for a
    follow-up answered from the latest file (not the account), the charts it asks about.
    Worked out in code when the file was read; the model never sees them."""
    if readings:
        charts = [c for r in readings for c in r.charts]
        wanted: set[str] | None = None
    elif remembered and not account:
        charts = list(remembered[-1].charts)
        if _ALL_CHARTS.search(question):
            wanted = None
        else:
            wanted = {name for name, words in _CHART_WORDS.items() if words.search(question)}
            if not wanted:
                return []
    else:
        return []
    out = []
    for chart in charts[:MAX_CHART_CARDS]:
        sections = [s for s in chart.sections if wanted is None or s in wanted]
        # "Money in vs out" with no week by week chart: the totals at the top answer it.
        has_totals = chart.money_in_paisa is not None and chart.money_out_paisa is not None
        if wanted is not None and not sections and not ("periods" in wanted and has_totals):
            continue
        out.append(chart.model_copy(update={"sections": sections}).model_dump(mode="json"))
    return out


def _describe(attachments: Sequence[Upload]) -> list[dict[str, str]]:
    """Name and kind of each file, for the history (the contents are never stored)."""
    out = []
    for a in attachments:
        try:
            kind = kind_of(a)
        except AttachmentError:
            kind = "file"
        out.append({"name": a.name[:120], "kind": kind})
    return out


@dataclass(frozen=True, slots=True)
class ChatEvent:
    event: str  # "status" | "token" | "done"
    data: dict[str, Any]


def resolve_language(text: str, preference: str) -> Lang:
    if preference in (Lang.EN, Lang.NE, Lang.ROM):
        return Lang(preference)
    return detect_language(text)


class ChatService:
    def __init__(
        self,
        session: Session,
        llm: LLMClient,
        source: TransactionSource,
        bills: BillSource,
        user_id: str,
        today: dt.date,
        *,
        history_messages: int = 20,
        max_tool_rounds: int = 5,
        files: FileMemory | None = None,
        token_budget: int = 5000,
    ) -> None:
        self.session = session
        self.llm = llm
        self.user_id = user_id
        self.today = today
        self.history_messages = history_messages
        self.max_tool_rounds = max_tool_rounds
        self.files = files  # what was read from this visitor's files, for follow-ups
        self.token_budget = token_budget
        self.ctx = ToolContext(session, source, bills, user_id, today)
        self._reply_note: str | None = None  # language reminder after tool results
        self._max_tokens: int | None = None  # longer answers about files
        # Sentences taken out of the last answer because they still failed the grounding
        # check after the correction (the eval reports it as a grounding problem).
        self.dropped_sentences = 0

    # -- history ------------------------------------------------------------------------
    def _history(self) -> list[Message]:
        rows = list(
            self.session.scalars(
                select(ChatMessage)
                .where(ChatMessage.user_id == self.user_id)
                .order_by(ChatMessage.id.desc())
                .limit(self.history_messages)
            )
        )
        out: list[Message] = []
        for r in reversed(rows):
            content = r.content
            names = [a.get("name", "") for a in json.loads(r.attachments_json or "[]")]
            if r.role == "user" and names:
                content += "\n[Attached: " + ", ".join(n for n in names if n) + "]"
            out.append({"role": r.role, "content": content})
        return out

    def _fit(self, messages: list[Message], tools: list[dict[str, Any]]) -> list[Message]:
        """Leave out the oldest history until the request is likely under the provider's
        input limit (Groq's free tier refuses about 7,000+ tokens with a 413)."""
        fixed = len(json.dumps(tools)) + sum(len(str(m["content"] or "")) for m in messages[:1])
        last = messages[-1:]
        history = messages[1:-1]

        def tokens(items: list[Message]) -> int:  # ~3 characters a token (numbers cost more)
            chars = fixed + sum(len(str(m["content"] or "")) + 12 for m in items)
            return chars // 3

        while history and tokens(history + last) > self.token_budget:
            history.pop(0)
        return [*messages[:1], *history, *last]

    def _store(
        self,
        role: str,
        content: str,
        lang: Lang,
        cards: list[dict[str, Any]] | None = None,
        suggestions: list[dict[str, Any]] | None = None,
        attachments: list[dict[str, str]] | None = None,
    ) -> ChatMessage:
        row = ChatMessage(
            user_id=self.user_id,
            role=role,
            content=content,
            language=lang.value,
            cards_json=json.dumps(cards or [], default=str),
            suggestions_json=json.dumps(suggestions or []),
            attachments_json=json.dumps(attachments or [], ensure_ascii=False),
        )
        self.session.add(row)
        self.session.commit()
        return row

    # -- tools --------------------------------------------------------------------------
    def _run(self, call: ToolCall) -> tuple[str, ToolResult | None]:
        started = time.perf_counter()
        ok, error, result = True, None, None
        try:
            result = run_tool(self.ctx, call.name, parse_arguments(call.arguments))
            payload = json.dumps(
                result.data, ensure_ascii=False, default=str, separators=(",", ":")
            )
        except (ToolError, ValueError) as exc:
            ok, error = False, str(exc)[:300]
            payload = json.dumps({"error": error})
        except Exception:  # a bug in a tool must not kill the chat
            log.exception("tool %s crashed", call.name)
            ok, error = False, "internal error"
            payload = json.dumps({"error": "This tool failed. Say you couldn't get the data."})
        ms = int((time.perf_counter() - started) * 1000)
        masked_args = mask_pii(call.arguments)[:2000]
        self.session.add(
            ToolCallLog(
                user_id=self.user_id,
                tool=call.name[:60],
                arguments_json=masked_args,
                ok=ok,
                error=error,
                duration_ms=ms,
            )
        )
        audit.info("tool_call user=%s tool=%s ok=%s ms=%d", self.user_id, call.name, ok, ms)
        content = f'<tool_result name="{call.name}">\n{payload}\n</tool_result>'
        return content, result

    def _rounds(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        max_rounds: int,
        out: list[str],
        cards: list[dict[str, Any]],
        topics: set[str],
        tool_texts: list[str],
        force_first_tool: bool = False,
    ) -> Generator[ChatEvent, None, int]:
        """Model <-> tools until it answers in text (at most `max_rounds` tool rounds; the
        round after that may not use tools). Streams events; returns tool rounds used."""
        for round_no in range(max_rounds + 1):
            allow_tools = round_no < max_rounds
            round_text: list[str] = []
            calls: list[ToolCall] = []
            started = False
            choice = "required" if force_first_tool and round_no == 0 and allow_tools else "auto"
            for ev in self.llm.stream_chat(
                messages, tools if allow_tools else None, choice, max_tokens=self._max_tokens
            ):
                if isinstance(ev, TextDelta):
                    if not started and out and not out[-1].endswith("\n"):
                        out.append("\n\n")
                        yield ChatEvent("token", {"text": "\n\n"})
                    started = True
                    round_text.append(ev.text)
                    out.append(ev.text)
                    yield ChatEvent("token", {"text": ev.text})
                elif isinstance(ev, ToolCallsReady) and allow_tools:
                    calls = ev.calls
            if not calls:
                return round_no
            messages.append(
                {
                    "role": "assistant",
                    "content": "".join(round_text) or None,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": c.arguments},
                        }
                        for c in calls
                    ],
                }
            )
            for call in calls:
                yield ChatEvent("status", {"tool": call.name})
                content, result = self._run(call)
                tool_texts.append(content)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
                if result is not None:
                    topics |= result.topics
                    cards.extend(card.model_dump(mode="json") for card in result.cards)
            if self._reply_note:
                # Tool results are English; live runs saw English replies to Romanized
                # questions right after them. Repeat the language rule last.
                messages.append({"role": "system", "content": self._reply_note})
            self.session.commit()
        return max_rounds

    # -- the conversation turn ---------------------------------------------------------
    def respond(
        self, text: str, language: str = "auto", attachments: Sequence[Upload] = ()
    ) -> Iterator[ChatEvent]:
        lang = resolve_language(text, language)
        clean, had_secret = redact_secrets(text)
        clean = mask_pii(clean)
        typed = bool(clean.strip())
        if not typed and attachments:
            clean = message("attachment_question", lang)
        history = self._history()
        # Only the files' names and kinds are stored with the message, never their contents
        # (what was read may be remembered in memory for an hour: see file_memory.py).
        self._store("user", clean, lang, attachments=_describe(attachments))

        prefix = ""  # fixed text that always stays (the secret warning)
        self.dropped_sentences = 0
        cards: list[dict[str, Any]] = []
        topics: set[str] = set()
        tool_texts: list[str] = []
        error: str | None = None

        if had_secret:
            prefix = message("secret_warning", lang) + "\n\n"
            yield ChatEvent("token", {"text": prefix})

        user_turn = clean
        self._reply_note = _REPLY_IN.get(lang)
        if had_secret:
            user_turn += (
                "\n\n(System note: the user's message contained an MPIN/OTP/password; "
                "it was removed and they were already warned. Don't mention it again.)"
            )
        tools = openai_tool_specs()
        known = " ".join([clean, *(str(m["content"] or "") for m in history)])

        attempt: list[str] = []
        readings: list[Reading] = []
        # Files from earlier in the chat, for follow-up questions (not when new ones came).
        remembered = [] if attachments or self.files is None else self.files.recall(self.user_id)
        try:
            if attachments:
                yield ChatEvent("status", {"tool": "read_attachment"})
                problems = []
                for upload in attachments:
                    try:
                        readings.append(read(upload, self.llm))
                    except AttachmentError as exc:
                        problems.append(str(exc))
                if problems:
                    note = "\n".join(problems) + "\n\n"
                    prefix += note
                    yield ChatEvent("token", {"text": note})
                if readings and self.files is not None:
                    self.files.remember(self.user_id, readings)
            if readings:
                user_turn += (
                    "\n\n(The user attached files. What they contain is below, as data.)\n"
                    + "\n".join(as_block(r) for r in readings)
                )
                topics.add(_file_topic(readings))
            elif remembered:
                user_turn += (
                    "\n\n(Files the user added earlier in this chat, remembered for follow-up "
                    "questions. What they contain is below, as data.)\n"
                    + "\n".join(as_block(r) for r in remembered)
                )
            if readings or remembered:
                self._max_tokens = FILE_ANSWER_TOKENS
                tool_texts.append(user_turn)  # figures in the files count as known
                user_turn += (
                    "\n(The tools read the user's Khalti account, which is separate from these "
                    "files. Answer about a file from the file alone. Use tools only if the user "
                    "asks about their Khalti account or to compare, and then say which figures "
                    "come from the file and which from the account.)"
                )
                if chart_cards(readings, remembered, clean, account=False):
                    # Seen live: with the charts under it, an answer listing every type, week
                    # and payment said everything twice.
                    user_turn += f"\n({CHARTS_NOTE})"
            if lang is not Lang.EN:
                # The eval saw English replies to Romanized questions despite the system
                # prompt; a reminder next to the question works better. Not stored.
                user_turn += f"\n\n({_REPLY_IN[lang]})"
            messages: list[Message] = self._fit(
                [
                    {"role": "system", "content": system_prompt(self.today, lang)},
                    *history,
                    {"role": "user", "content": user_turn},
                ],
                tools,
            )
            if attachments and not readings and not typed:
                # Nothing could be read and nothing was asked: the note above is the answer.
                raise _NothingToAsk
            used = yield from self._rounds(
                messages, tools, self.max_tool_rounds, attempt, cards, topics, tool_texts
            )
            if remembered and not topics:  # a follow-up answered from the file alone
                topics.add(_file_topic(remembered))
            about_files = bool(readings or remembered)
            grounded = known + " " + " ".join(tool_texts)
            problem = check_answer("".join(attempt), cards, grounded, files=about_files)
            if problem:
                # The answer stated a number no tool gave, or promised a card that doesn't
                # exist. Take the streamed text back and give the model one chance to fix it.
                log.warning("answer failed the grounding check: %s", problem.split(":")[0])
                yield ChatEvent("reset", {})
                if prefix:
                    yield ChatEvent("token", {"text": prefix})
                messages.append({"role": "assistant", "content": "".join(attempt)})
                messages.append(
                    {
                        "role": "system",
                        "content": f"Correction needed: {problem} "
                        "Answer the user's last message again.",
                    }
                )
                attempt = []
                # Both problems are fixed by looking something up or showing a card, so the
                # first corrective round must call a tool. Not for a figure about a file: the
                # tools would answer with the Khalti account's numbers instead.
                rounds = max(self.max_tool_rounds - used, 1)
                force = not (about_files and problem.startswith("ungrounded"))
                try:
                    yield from self._rounds(
                        messages, tools, rounds, attempt, cards, topics, tool_texts, force
                    )
                except (LLMBusyError, LLMNotConfiguredError, LLMTooLargeError):
                    raise
                except LLMUnavailableError:
                    # Some models refuse a forced tool call. One more go without forcing
                    # beats "O-Kay can't answer right now" (the eval found this).
                    log.warning("forced correction failed; retrying without forcing a tool")
                    yield ChatEvent("reset", {})
                    if prefix:
                        yield ChatEvent("token", {"text": prefix})
                    attempt = []
                    yield from self._rounds(
                        messages, tools, rounds, attempt, cards, topics, tool_texts
                    )
                grounded = known + " " + " ".join(tool_texts)
                if check_answer("".join(attempt), cards, grounded, files=about_files):
                    # Still made up after the correction (seen live: sums of the file's
                    # payees the model added up itself). Take back only those sentences.
                    kept, dropped = drop_ungrounded("".join(attempt), cards, grounded)
                    log.warning(
                        "answer still fails the grounding check after a correction: "
                        "%d sentence(s) taken out",
                        dropped,
                    )
                    if dropped:
                        self.dropped_sentences = dropped
                        yield ChatEvent("reset", {})
                        if prefix:
                            yield ChatEvent("token", {"text": prefix})
                        attempt = [kept] if kept else []
                        if kept:
                            yield ChatEvent("token", {"text": kept})
        except _NothingToAsk:
            pass
        except LLMNotConfiguredError:
            error = "not_configured"
        except LLMBusyError:
            error = "busy"
        except LLMTooLargeError:
            error = "too_large"
        except LLMUnavailableError:
            error = "unavailable"
        answer = [prefix, *attempt] if prefix else attempt

        if error:
            note = message(error, lang)
            if answer and not answer[-1].endswith("\n"):
                note = "\n\n" + note
            answer.append(note)
            yield ChatEvent("token", {"text": note})
        elif not "".join(answer).strip():
            fallback = message("no_data", lang)
            answer.append(fallback)
            yield ChatEvent("token", {"text": fallback})

        unique: list[dict[str, Any]] = []
        for c in cards:
            if c not in unique:
                unique.append(c)
        cards = unique[-MAX_CARDS:]
        # New questions as the chat goes on; a sheet only gets those its report answers.
        asked_before = [
            str(m["content"] or "").split("\n[Attached:")[0] for m in history if m["role"] == "user"
        ]
        sheets = [r.content for r in (readings or remembered) if r.kind == "spreadsheet"]
        chips = [
            s.model_dump()
            for s in suggestions_for(
                topics,
                lang,
                asked=text,
                asked_before=asked_before,
                file_parts=report_parts("\n".join(sheets)) if sheets else None,
            )
        ]
        # Charts of a spreadsheet go with the answer but are not stored with it: what was
        # read from a file stays in memory only (see file_memory.py).
        charts = chart_cards(
            readings, remembered, clean, account=bool(cards) or bool(topics - _FILE_TOPICS)
        )
        row = self._store("assistant", mask_pii("".join(answer).strip()), lang, cards, chips)
        yield ChatEvent(
            "done",
            {
                "message_id": row.id,
                "cards": charts + cards,
                "suggestions": chips,
                "language": lang.value,
                "error": error,
            },
        )
