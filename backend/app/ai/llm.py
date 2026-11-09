"""LLM access behind a small interface, so the provider can be swapped later.

GroqLLMClient uses the official `openai` SDK pointed at Groq's OpenAI-compatible API.
On HTTP 429 it retries with exponential backoff (3 tries in total, the last one on the
fallback model, since Groq limits are per model), then raises LLMBusyError so the chat can
answer "O-Kay is busy, please try again in a minute".
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

import openai
from openai import OpenAI

from app.config import Settings

log = logging.getLogger(__name__)

Message = dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON text from the model


@dataclass(frozen=True, slots=True)
class TextDelta:
    text: str


@dataclass(frozen=True, slots=True)
class ToolCallsReady:
    calls: list[ToolCall] = field(default_factory=list)


LLMEvent = TextDelta | ToolCallsReady


class LLMUnavailableError(Exception):
    """The provider failed (network, 5xx, bad request) after retries."""


class LLMBusyError(LLMUnavailableError):
    """Still rate-limited (HTTP 429) after all retries."""


class LLMNotConfiguredError(LLMUnavailableError):
    """No API key on the server."""


class LLMClient(Protocol):
    def stream_chat(
        self, messages: list[Message], tools: list[dict[str, Any]] | None
    ) -> Iterator[LLMEvent]:
        """Stream text deltas; if the model wants tools, finish with one ToolCallsReady."""
        ...

    def complete(self, messages: list[Message], *, json_object: bool = False) -> str: ...


class ThinkFilter:
    """Removes <think>...</think> blocks from streamed text, even when a tag is split
    across chunks. Safety net: Qwen runs in instruct mode, but a stray block must never
    reach the user."""

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self) -> None:
        self._buf = ""
        self._inside = False

    def feed(self, chunk: str) -> str:
        self._buf += chunk
        out: list[str] = []
        while True:
            if not self._inside:
                i = self._buf.find(self.OPEN)
                if i >= 0:
                    out.append(self._buf[:i])
                    self._buf = self._buf[i + len(self.OPEN) :]
                    self._inside = True
                    continue
                keep = self._partial_suffix(self._buf, self.OPEN)
                out.append(self._buf[: len(self._buf) - keep])
                self._buf = self._buf[len(self._buf) - keep :]
                break
            i = self._buf.find(self.CLOSE)
            if i >= 0:
                self._buf = self._buf[i + len(self.CLOSE) :].lstrip()
                self._inside = False
                continue
            keep = self._partial_suffix(self._buf, self.CLOSE)
            self._buf = self._buf[len(self._buf) - keep :]
            break
        return "".join(out)

    def flush(self) -> str:
        rest, self._buf = ("" if self._inside else self._buf), ""
        return rest

    @staticmethod
    def _partial_suffix(text: str, tag: str) -> int:
        for n in range(min(len(tag) - 1, len(text)), 0, -1):
            if text.endswith(tag[:n]):
                return n
        return 0


class GroqLLMClient:
    BACKOFF_SECONDS = (1.0, 2.0)  # waits before try 2 and try 3

    def __init__(
        self,
        settings: Settings,
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if settings.groq_api_key is None and client is None:
            raise LLMNotConfiguredError("GROQ_API_KEY is not set")
        self.settings = settings
        self._sleep = sleep
        self._client = client or OpenAI(
            api_key=settings.groq_api_key.get_secret_value(),  # type: ignore[union-attr]
            base_url=settings.llm_base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,  # we do our own retries (and model fallback) below
        )

    # -- request plumbing ---------------------------------------------------------------
    def _params(self, model: str) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": model,
            "temperature": self.settings.llm_temperature,
            "max_completion_tokens": self.settings.llm_max_tokens,
        }
        if model.startswith("qwen/") and self.settings.llm_reasoning_effort:
            extra: dict[str, Any] = {"reasoning_effort": self.settings.llm_reasoning_effort}
            if self.settings.llm_reasoning_effort != "none":
                extra["reasoning_format"] = "hidden"  # required with tools; keeps it out
            params["extra_body"] = extra
        return params

    def _models(self) -> list[str]:
        primary, fallback = self.settings.llm_model, self.settings.llm_fallback_model
        return [primary, primary, fallback or primary]

    def _create(self, **kwargs: Any) -> Any:
        last_error: Exception | None = None
        models = self._models()
        for attempt, model in enumerate(models):
            if attempt > 0:
                self._sleep(self.BACKOFF_SECONDS[attempt - 1])
            try:
                return self._client.chat.completions.create(**self._params(model), **kwargs)
            except openai.RateLimitError as exc:
                log.warning("LLM rate limited (try %d, model %s)", attempt + 1, model)
                last_error = exc
            except (openai.APIConnectionError, openai.InternalServerError) as exc:
                log.warning(
                    "LLM unavailable (try %d, model %s): %s", attempt + 1, model, type(exc).__name__
                )
                last_error = exc
            except openai.NotFoundError as exc:  # model retired / renamed: go to fallback
                log.error("LLM model %s not found; trying fallback", model)
                last_error = exc
                if model != models[-1]:
                    models[attempt + 1 :] = [models[-1]] * (len(models) - attempt - 1)
            except openai.APIStatusError as exc:
                log.error("LLM request rejected: %s %s", exc.status_code, type(exc).__name__)
                raise LLMUnavailableError(str(exc.status_code)) from exc
        if isinstance(last_error, openai.RateLimitError):
            raise LLMBusyError("rate limited") from last_error
        raise LLMUnavailableError("provider unavailable") from last_error

    # -- public API ---------------------------------------------------------------------
    def stream_chat(
        self, messages: list[Message], tools: list[dict[str, Any]] | None
    ) -> Iterator[LLMEvent]:
        kwargs: dict[str, Any] = {"messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
            kwargs["parallel_tool_calls"] = True
        stream = self._create(**kwargs)
        think = ThinkFilter()
        pending: dict[int, dict[str, str]] = {}
        try:
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if getattr(delta, "content", None):
                    text = think.feed(delta.content)
                    if text:
                        yield TextDelta(text)
                for tc in getattr(delta, "tool_calls", None) or []:
                    slot = pending.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function is not None:
                        if tc.function.name:
                            slot["name"] += tc.function.name
                        if tc.function.arguments:
                            slot["arguments"] += tc.function.arguments
        except openai.APIError as exc:
            raise LLMUnavailableError("stream interrupted") from exc
        rest = think.flush()
        if rest:
            yield TextDelta(rest)
        if pending:
            yield ToolCallsReady(
                [
                    ToolCall(s["id"] or f"call_{i}", s["name"], s["arguments"] or "{}")
                    for i, s in sorted(pending.items())
                ]
            )

    def complete(self, messages: list[Message], *, json_object: bool = False) -> str:
        kwargs: dict[str, Any] = {"messages": messages}
        if json_object:
            kwargs["response_format"] = {"type": "json_object"}
        response = self._create(**kwargs)
        text = response.choices[0].message.content or ""
        think = ThinkFilter()
        return (think.feed(text) + think.flush()).strip()


class UnconfiguredLLMClient:
    """Used when GROQ_API_KEY is missing: every call says so (the chat shows a clear note)."""

    def stream_chat(
        self, messages: list[Message], tools: list[dict[str, Any]] | None
    ) -> Iterator[LLMEvent]:
        raise LLMNotConfiguredError("GROQ_API_KEY is not set")

    def complete(self, messages: list[Message], *, json_object: bool = False) -> str:
        raise LLMNotConfiguredError("GROQ_API_KEY is not set")


def build_llm_client(settings: Settings) -> LLMClient:
    if settings.groq_api_key is None or not settings.groq_api_key.get_secret_value():
        return UnconfiguredLLMClient()
    return GroqLLMClient(settings)


def parse_arguments(raw: str) -> dict[str, Any]:
    """Tool-call arguments as a dict ('' or 'null' -> {}). ValueError if not a JSON object."""
    if not raw or raw.strip() in ("", "null"):
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("arguments must be a JSON object")
    return value
