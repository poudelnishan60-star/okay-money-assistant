"""Live check against the real LLM (needs GROQ_API_KEY in backend/.env). Uses a throwaway
in-memory copy of the demo data, so nothing on disk changes. Sends mock data only.

    python scripts/live_chat_check.py            # all questions
    python scripts/live_chat_check.py 2 5        # only questions 2 and 5
    python scripts/live_chat_check.py --pause=0  # no pause between questions (default 20 s,
                                                 # to stay inside 8,000 tokens/min per model)

For each question it prints the tools called, the answer, the cards, and a grounding check:
every "Rs. ..." amount in the answer must appear in a tool result the model received.
"""

from __future__ import annotations

import re
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ai.chat import ChatService  # noqa: E402
from app.ai.classifier import categorize_unknown_merchants  # noqa: E402
from app.ai.llm import GroqLLMClient, LLMEvent, Message  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import init_db, make_engine, make_session_factory  # noqa: E402
from app.periods import today_npt  # noqa: E402
from app.seed import DEMO_USER_ID, seed_database  # noqa: E402
from app.sources.mock import MockBillSource, MockTransactionSource  # noqa: E402

QUESTIONS = [
    "How much did I spend on food this month?",
    "yo mahina khana ma kati kharcha bhayo?",
    "मेरो बिजुलीको बिल कहिले तिर्नुपर्छ र कति हुन्छ?",
    "Where did my money go last month?",
    "Set a food budget of 6000",
    "Pay my electricity bill",
    "Show the money people sent me in the last 30 days",
    "my mpin is 4321, will I run low this month?",
    "Which stock should I buy to get rich?",
    "How do I reset my MPIN?",
]

AMOUNT = re.compile(r"(?:Rs\.?|रु\.?)\s?[\d,०-९]+(?:\.\d+)?")


class RecordingLLM:
    """Delegates to the real client and remembers what the model was shown."""

    def __init__(self, inner: GroqLLMClient) -> None:
        self.inner = inner
        self.tool_text: list[str] = []
        self.calls = 0

    def stream_chat(
        self, messages: list[Message], tools: list[dict[str, Any]] | None
    ) -> Iterator[LLMEvent]:
        self.calls += 1
        self.tool_text = [m["content"] for m in messages if m.get("role") == "tool"]
        yield from self.inner.stream_chat(messages, tools)

    def complete(self, messages: list[Message], *, json_object: bool = False) -> str:
        self.calls += 1
        return self.inner.complete(messages, json_object=json_object)


def _norm(amount: str) -> str:
    return re.sub(r"[^\d.]", "", amount.translate(str.maketrans("०१२३४५६७८९", "0123456789")))


def main() -> None:
    pause = next(
        (float(a.split("=", 1)[1]) for a in sys.argv[1:] if a.startswith("--pause=")), 20.0
    )
    picked = {int(a) for a in sys.argv[1:] if a.isdigit()}
    settings = get_settings()
    if settings.groq_api_key is None or not settings.groq_api_key.get_secret_value():
        sys.exit("No GROQ_API_KEY in backend/.env")
    engine = make_engine("sqlite://")
    init_db(engine)
    session = make_session_factory(engine)()
    seed_database(session, today_npt())
    llm = RecordingLLM(GroqLLMClient(settings))

    print("== unknown merchants (LLM fallback, cached per merchant)")
    print("  ", categorize_unknown_merchants(session, llm))

    source = MockTransactionSource(session)
    problems = 0
    for i, q in enumerate(QUESTIONS, start=1):
        if picked and i not in picked:
            continue
        if i > 1 and pause:
            time.sleep(pause)
        svc = ChatService(
            session,
            llm,
            source,
            MockBillSource(source),
            DEMO_USER_ID,
            today_npt(),
            history_messages=0,
        )
        calls_before = llm.calls
        started = time.perf_counter()
        tools, text, done = [], [], {}
        for ev in svc.respond(q):
            if ev.event == "status":
                tools.append(ev.data["tool"])
            elif ev.event == "token":
                text.append(ev.data["text"])
            else:
                done = ev.data
        answer = "".join(text).strip()
        grounded = " ".join(llm.tool_text)
        ungrounded = [
            a
            for a in AMOUNT.findall(answer)
            if _norm(a) and _norm(a) not in {_norm(x) for x in AMOUNT.findall(grounded)}
        ]
        print(f"\n== Q{i} [{done.get('language')}] {q}")
        print(
            f"   tools: {tools or '-'}   llm calls: {llm.calls - calls_before}   "
            f"{time.perf_counter() - started:.1f}s   error: {done.get('error')}"
        )
        print("   answer:", answer.replace("\n", " ")[:600])
        print(
            "   cards:",
            [c["type"] for c in done.get("cards", [])],
            "  chips:",
            [s["text"] for s in done.get("suggestions", [])],
        )
        if ungrounded:
            problems += 1
            print("   !! amounts not found in any tool result:", ungrounded)
    print(f"\n{problems} answer(s) with ungrounded amounts")


if __name__ == "__main__":
    main()
