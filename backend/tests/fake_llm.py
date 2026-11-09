"""A scripted stand-in for the LLM: each stream_chat call plays the next step."""

from __future__ import annotations

import copy
import itertools
import json
from collections.abc import Iterator
from typing import Any

from app.ai.llm import LLMEvent, Message, TextDelta, ToolCall, ToolCallsReady

_ids = itertools.count(1)


def say(*parts: str) -> list[LLMEvent]:
    return [TextDelta(p) for p in parts]


def call(*calls: tuple[str, dict[str, Any]]) -> list[LLMEvent]:
    return [
        ToolCallsReady(
            [ToolCall(f"call_{next(_ids)}", name, json.dumps(args)) for name, args in calls]
        )
    ]


class FakeLLM:
    def __init__(
        self,
        *steps: list[LLMEvent] | Exception,
        complete: list[str] | None = None,
        repeat_last: bool = False,
    ) -> None:
        self.steps = list(steps)
        self.complete_answers = list(complete or [])
        self.repeat_last = repeat_last
        self.calls: list[tuple[list[Message], list[dict[str, Any]] | None]] = []
        self.tool_choices: list[str] = []

    def stream_chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None,
        tool_choice: str = "auto",
    ) -> Iterator[LLMEvent]:
        self.calls.append((copy.deepcopy(messages), tools))
        self.tool_choices.append(tool_choice)
        step = self.steps[0] if (self.repeat_last and len(self.steps) == 1) else self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        yield from step

    def complete(self, messages: list[Message], *, json_object: bool = False) -> str:
        self.calls.append((copy.deepcopy(messages), None))
        return self.complete_answers.pop(0)
