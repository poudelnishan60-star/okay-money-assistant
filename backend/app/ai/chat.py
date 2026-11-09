"""Chat orchestration: history, masking, the tool loop, cards, chips, persistence, audit log.

Events produced (sent as server-sent events by routes_chat):
  status  {"tool": "..."}                         a tool is running (optional for clients)
  token   {"text": "..."}                         streamed answer text
  done    {"message_id", "cards", "suggestions", "language", "error"}   always last
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.llm import (
    LLMBusyError,
    LLMClient,
    LLMNotConfiguredError,
    LLMUnavailableError,
    Message,
    TextDelta,
    ToolCall,
    ToolCallsReady,
    parse_arguments,
)
from app.ai.prompt import system_prompt
from app.ai.safety import Lang, detect_language, mask_pii, message, redact_secrets
from app.ai.suggestions import suggestions_for
from app.ai.tools import ToolContext, ToolError, ToolResult, openai_tool_specs, run_tool
from app.models import ChatMessage, ToolCallLog
from app.sources.base import BillSource, TransactionSource

log = logging.getLogger(__name__)
audit = logging.getLogger("okay.audit")

MAX_CARDS = 4


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
    ) -> None:
        self.session = session
        self.llm = llm
        self.user_id = user_id
        self.today = today
        self.history_messages = history_messages
        self.max_tool_rounds = max_tool_rounds
        self.ctx = ToolContext(session, source, bills, user_id, today)

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
        return [{"role": r.role, "content": r.content} for r in reversed(rows)]

    def _store(
        self,
        role: str,
        content: str,
        lang: Lang,
        cards: list[dict[str, Any]] | None = None,
        suggestions: list[dict[str, Any]] | None = None,
    ) -> ChatMessage:
        row = ChatMessage(
            user_id=self.user_id,
            role=role,
            content=content,
            language=lang.value,
            cards_json=json.dumps(cards or [], default=str),
            suggestions_json=json.dumps(suggestions or []),
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

    # -- the conversation turn ---------------------------------------------------------
    def respond(self, text: str, language: str = "auto") -> Iterator[ChatEvent]:
        lang = resolve_language(text, language)
        clean, had_secret = redact_secrets(text)
        clean = mask_pii(clean)
        history = self._history()
        self._store("user", clean, lang)

        answer: list[str] = []
        cards: list[dict[str, Any]] = []
        topics: set[str] = set()
        error: str | None = None

        if had_secret:
            warning = message("secret_warning", lang) + "\n\n"
            answer.append(warning)
            yield ChatEvent("token", {"text": warning})

        user_turn = clean
        if had_secret:
            user_turn += (
                "\n\n(System note: the user's message contained an MPIN/OTP/password; "
                "it was removed and they were already warned. Don't mention it again.)"
            )
        messages: list[Message] = [
            {"role": "system", "content": system_prompt(self.today, lang)},
            *history,
            {"role": "user", "content": user_turn},
        ]
        tools = openai_tool_specs()

        try:
            for round_no in range(self.max_tool_rounds + 1):
                allow_tools = round_no < self.max_tool_rounds
                round_text: list[str] = []
                calls: list[ToolCall] = []
                started_text = False
                for ev in self.llm.stream_chat(messages, tools if allow_tools else None):
                    if isinstance(ev, TextDelta):
                        if not started_text and answer and not answer[-1].endswith("\n"):
                            answer.append("\n\n")
                            yield ChatEvent("token", {"text": "\n\n"})
                        started_text = True
                        round_text.append(ev.text)
                        answer.append(ev.text)
                        yield ChatEvent("token", {"text": ev.text})
                    elif isinstance(ev, ToolCallsReady) and allow_tools:
                        calls = ev.calls
                if not calls:
                    break
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
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
                    if result is not None:
                        topics |= result.topics
                        for card in result.cards:
                            cards.append(card.model_dump(mode="json"))
                self.session.commit()
        except LLMNotConfiguredError:
            error = "not_configured"
        except LLMBusyError:
            error = "busy"
        except LLMUnavailableError:
            error = "unavailable"

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
        chips = [s.model_dump() for s in suggestions_for(topics, lang, asked=text)]
        row = self._store("assistant", mask_pii("".join(answer).strip()), lang, cards, chips)
        yield ChatEvent(
            "done",
            {
                "message_id": row.id,
                "cards": cards,
                "suggestions": chips,
                "language": lang.value,
                "error": error,
            },
        )
