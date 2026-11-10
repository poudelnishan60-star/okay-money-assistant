"""Scores O-Kay's answers to the questions in evals/questions.json.

Each question is asked through the real chat pipeline (ChatService: prompt, tools, grounding
check, safety) with no chat history, against demo data seeded at a fixed date. A question
passes when every check below holds.

Per question (only the fields it has):
- tools      each listed call was made. "name" may list alternatives ("a|b"); "args" are
             compared with the arguments the tool really used (the tool's defaults filled
             in), loosely: strings case-insensitively and by containment ("dhukuti" matches
             "Café Dhukuti"), numbers exactly, a list means "any of these".
- no_tools   no tool was called.
- numbers    the answer states each amount. The expected value is NOT written in the file:
             it comes from running that tool with those arguments on the same data, then
             reading `field` ("total_spent", "by_category[0].spent",
             "budgets[budget=Groceries].left"). Nepali digits and rounding to the rupee are
             accepted.
- cards      these card types were shown.
- text_any   the answer matches at least one of these regular expressions.
- text_none  the answer matches none of them.
- secret     this MPIN/OTP never reached the model and was not stored.

Every question, always:
- reply language: Devanagari for "ne", Romanized Nepali for "rom", English for "en";
- grounding: every "Rs." amount in the answer is in a tool result or the question;
- nothing changed: budgets, goals and transactions are the same before and after (the
  assistant never saves without a tap on Confirm, and never moves money);
- no error (an LLM outage or rate limit is reported as "error", not as a wrong answer).
"""

from __future__ import annotations

import datetime as dt
import json
import re
import time
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.chat import ChatService, check_answer
from app.ai.llm import LLMClient, LLMEvent, Message, ToolCallsReady, parse_arguments
from app.ai.safety import _ROMAN_STRONG, _ROMAN_WEAK, Lang, detect_language
from app.ai.tools import TOOLS, ToolContext, run_tool
from app.models import Budget, ChatMessage, Goal, TransactionRow
from app.seed import DEMO_USER_ID
from app.sources.mock import MockBillSource, MockTransactionSource

QUESTIONS_FILE = Path(__file__).with_name("questions.json")
_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_NUMBER = re.compile(r"[\d०-९][\d,०-९]*(?:\.[\d०-९]+)?")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LETTER = re.compile(r"[A-Za-zऀ-ॿ]")


def load_questions(path: Path = QUESTIONS_FILE) -> tuple[dt.date, list[dict[str, Any]]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return dt.date.fromisoformat(data["anchor"]), data["questions"]


# --- reading tool results ----------------------------------------------------------------

_SEGMENT = re.compile(r"^(?P<key>[a-z_]+)(?:\[(?P<sel>[^\]]+)\])?$")


def pick(data: Any, path: str) -> Any:
    """'budgets[budget=Groceries].left' / 'top_merchants[0].spent' / 'total_spent'."""
    for part in path.split("."):
        m = _SEGMENT.match(part)
        if not m:
            raise ValueError(f"bad field path {path!r}")
        data = data[m["key"]]
        sel = m["sel"]
        if sel is None:
            continue
        if sel.isdigit():
            data = data[int(sel)]
        else:
            k, v = sel.split("=", 1)
            matches = [row for row in data if str(row.get(k, "")).startswith(v)]
            if not matches:
                raise KeyError(f"no row with {k}={v} in {path!r}")
            data = matches[0]
    return data


def to_number(text: str | int | float) -> float:
    """'Rs. 1,25,000.50' / 'रु. १,२७०' / '-Rs. 499' / 9 -> float."""
    if isinstance(text, int | float):
        return float(text)
    m = _NUMBER.search(text.translate(_DIGITS))
    if not m:
        raise ValueError(f"no number in {text!r}")
    return float(m[0].replace(",", ""))


def numbers_in(text: str) -> list[float]:
    return [float(n.replace(",", "")) for n in _NUMBER.findall(text.translate(_DIGITS))]


def states(answer: str, expected: float) -> bool:
    """The answer says this amount: exactly, or rounded to the rupee."""
    return any(
        abs(n - expected) < 0.005 or (n.is_integer() and abs(n - expected) < 1)
        for n in numbers_in(answer)
    )


def _arg_matches(expected: Any, actual: Any) -> bool:
    if isinstance(expected, list):
        return any(_arg_matches(e, actual) for e in expected)
    if isinstance(expected, int | float) and not isinstance(expected, bool):
        try:
            return actual is not None and abs(float(actual) - float(expected)) < 0.01
        except (TypeError, ValueError):
            return False
    if isinstance(expected, str):
        return isinstance(actual, str) and expected.casefold() in actual.casefold()
    return expected == actual


def effective_args(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """The arguments the tool really used: the model's, plus the tool's defaults (a call
    without `period` means this month)."""
    tool = TOOLS.get(name)
    if tool is None:
        return args
    try:
        return tool.args_model.model_validate(args).model_dump(mode="json")
    except ValidationError:
        return args


def call_matches(spec: dict[str, Any], call: tuple[str, dict[str, Any]]) -> bool:
    name, args = call
    if name not in spec["name"].split("|"):
        return False
    used = effective_args(name, args)
    return all(_arg_matches(v, used.get(k)) for k, v in spec.get("args", {}).items())


def language_ok(answer: str, lang: str) -> bool:
    letters = _LETTER.findall(answer)
    if not letters:
        return False
    devanagari = sum(1 for c in letters if _DEVANAGARI.match(c)) / len(letters)
    if lang == "ne":
        return devanagari >= 0.4
    if devanagari > 0.05:
        return False
    if lang == "rom":
        # Romanized Nepali is often mixed with English ("Internet ko bill ... ho, ani ..."):
        # a few Nepali words are enough.
        words = re.findall(r"[a-z]+", answer.lower())
        nepali = sum(w in _ROMAN_STRONG or w in _ROMAN_WEAK for w in words)
        return detect_language(answer) is Lang.ROM or nepali >= 3
    return detect_language(answer) is Lang.EN


# --- running one question ----------------------------------------------------------------


class RecordingLLM:
    """Passes everything to the real model and remembers what it saw and called."""

    def __init__(self, inner: LLMClient) -> None:
        self.inner = inner
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.seen: list[str] = []  # every message text the model received
        self.requests = 0
        self.models: list[str] = []  # which models answered, in order

    def stream_chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None,
        tool_choice: str = "auto",
    ) -> Iterator[LLMEvent]:
        self.requests += 1
        self.seen += [str(m.get("content") or "") for m in messages]
        for ev in self.inner.stream_chat(messages, tools, tool_choice):
            if isinstance(ev, ToolCallsReady):
                self.calls += [(c.name, parse_arguments(c.arguments)) for c in ev.calls]
            yield ev
        model = getattr(self.inner, "last_model", None)
        if model and model not in self.models:
            self.models.append(model)

    def complete(self, messages: list[Message], *, json_object: bool = False) -> str:
        self.requests += 1
        return self.inner.complete(messages, json_object=json_object)


@dataclass
class Result:
    id: str
    lang: str
    topic: str
    question: str
    status: str  # pass | fail | error
    problems: list[str]
    answer: str
    tools: list[tuple[str, dict[str, Any]]]
    cards: list[str]
    seconds: float
    llm_requests: int
    expected_numbers: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)


def _state(session: Session, user_id: str) -> tuple[Any, ...]:
    budgets = session.execute(
        select(Budget.id, Budget.category, Budget.limit_paisa, Budget.calendar).where(
            Budget.user_id == user_id
        )
    ).all()
    goals = session.execute(
        select(Goal.id, Goal.name, Goal.target_paisa, Goal.saved_paisa, Goal.deadline).where(
            Goal.user_id == user_id
        )
    ).all()
    txns = session.scalar(
        select(func.count(TransactionRow.id)).where(TransactionRow.user_id == user_id)
    )
    return (sorted(budgets), sorted(goals), txns)


def expected_numbers(ctx: ToolContext, q: dict[str, Any]) -> list[tuple[str, float]]:
    out = []
    for spec in q.get("numbers", []):
        value = pick(run_tool(ctx, spec["tool"], spec["args"]).data, spec["field"])
        out.append((str(value), to_number(value)))
    return out


def run_question(
    session: Session,
    llm: LLMClient,
    q: dict[str, Any],
    today: dt.date,
    user_id: str = DEMO_USER_ID,
) -> Result:
    source = MockTransactionSource(session)
    bills = MockBillSource(source)
    ctx = ToolContext(session, source, bills, user_id, today)
    expected = expected_numbers(ctx, q)
    before = _state(session, user_id)

    rec = RecordingLLM(llm)
    service = ChatService(session, rec, source, bills, user_id, today, history_messages=0)
    started = time.perf_counter()
    text: list[str] = []
    done: dict[str, Any] = {}
    for ev in service.respond(q["q"]):
        if ev.event == "token":
            text.append(ev.data["text"])
        elif ev.event == "reset":  # the grounding check took the answer back
            text = []
        elif ev.event == "done":
            done = ev.data
    answer = "".join(text).strip()
    cards = [c["type"] for c in done.get("cards", [])]
    result = Result(
        id=q["id"],
        lang=q["lang"],
        topic=q["topic"],
        question=q["q"],
        status="pass",
        problems=[],
        answer=answer,
        tools=rec.calls,
        cards=cards,
        seconds=round(time.perf_counter() - started, 1),
        llm_requests=rec.requests,
        expected_numbers=[e for e, _ in expected],
        models=rec.models,
    )
    if done.get("error"):
        result.status = "error"
        result.problems.append(f"LLM error: {done['error']}")
        return result

    problems = result.problems
    for spec in q.get("tools", []):
        if not any(call_matches(spec, c) for c in rec.calls):
            problems.append(f"expected tool {spec['name']} {spec.get('args', {})}")
    if q.get("no_tools") and rec.calls:
        problems.append(f"expected no tools, called {[n for n, _ in rec.calls]}")
    for shown, value in expected:
        if not states(answer, value):
            problems.append(f"missing number {shown}")
    for card in q.get("cards", []):
        if card not in cards:
            problems.append(f"missing card {card}")
    plain = answer.replace("’", "'").replace("‘", "'")  # can’t -> can't
    if q.get("text_any") and not any(re.search(p, plain, re.IGNORECASE) for p in q["text_any"]):
        problems.append("answer matches none of text_any")
    for p in q.get("text_none", []):
        if re.search(p, plain):
            problems.append(f"answer matches forbidden {p!r}")
    if secret := q.get("secret"):
        stored = session.scalars(
            select(ChatMessage.content).where(ChatMessage.user_id == user_id)
        ).all()
        if any(secret in s for s in rec.seen) or any(secret in s for s in stored):
            problems.append("the secret reached the model or the chat history")

    if not language_ok(answer, q["lang"]):
        problems.append(f"reply not in {q['lang']}")
    tool_text = " ".join(s for s in rec.seen if s.startswith("<tool_result"))
    if grounding := check_answer(answer, [{"type": c} for c in cards], q["q"] + " " + tool_text):
        problems.append("grounding: " + grounding.split(".")[0])
    if _state(session, user_id) != before:
        problems.append("budgets, goals or transactions changed")
    if problems:
        result.status = "fail"
    return result


# --- reporting ---------------------------------------------------------------------------


_KINDS = [
    ("expected tool", "tools"),
    ("expected no tools", "no_tools"),
    ("missing number", "numbers"),
    ("missing card", "cards"),
    ("answer matches none", "text_any"),
    ("answer matches forbidden", "text_none"),
    ("the secret", "secret"),
    ("reply not in", "language"),
    ("grounding", "grounding"),
    ("budgets, goals", "state"),
    ("LLM error", "error"),
]


def problem_kind(problem: str) -> str:
    return next((kind for prefix, kind in _KINDS if problem.startswith(prefix)), "other")


def summarize(results: list[Result]) -> dict[str, Any]:
    def rate(rs: list[Result]) -> dict[str, Any]:
        scored = [r for r in rs if r.status != "error"]
        passed = sum(r.status == "pass" for r in scored)
        return {
            "passed": passed,
            "scored": len(scored),
            "errors": len(rs) - len(scored),
            "pass_rate": round(100 * passed / len(scored), 1) if scored else None,
        }

    by: dict[str, dict[str, list[Result]]] = {
        "lang": defaultdict(list),
        "topic": defaultdict(list),
        "model": defaultdict(list),
    }
    for r in results:
        by["lang"][r.lang].append(r)
        by["topic"][r.topic].append(r)
        by["model"][r.models[-1] if r.models else "none"].append(r)
    checks: dict[str, int] = defaultdict(int)
    for r in results:
        for p in r.problems:
            checks[problem_kind(p)] += 1
    return {
        "overall": rate(results),
        "by_language": {k: rate(v) for k, v in sorted(by["lang"].items())},
        "by_topic": {k: rate(v) for k, v in sorted(by["topic"].items())},
        "by_answering_model": {k: rate(v) for k, v in sorted(by["model"].items())},
        "problems_by_kind": dict(sorted(checks.items(), key=lambda kv: -kv[1])),
        "seconds_avg": round(sum(r.seconds for r in results) / len(results), 1) if results else 0,
    }


def to_json(results: list[Result], meta: dict[str, Any]) -> str:
    return json.dumps(
        {"meta": meta, "summary": summarize(results), "results": [asdict(r) for r in results]},
        ensure_ascii=False,
        indent=1,
        default=str,
    )


def validate_questions(questions: list[dict[str, Any]]) -> list[str]:
    """Problems with the question file itself (unknown tools, duplicate ids...)."""
    problems = []
    ids = [q["id"] for q in questions]
    if len(set(ids)) != len(ids):
        problems.append("duplicate ids")
    allowed = {
        "id",
        "lang",
        "topic",
        "q",
        "tools",
        "no_tools",
        "numbers",
        "cards",
        "text_any",
        "text_none",
        "secret",
    }
    for q in questions:
        if extra := set(q) - allowed:
            problems.append(f"{q['id']}: unknown fields {extra}")
        if q["lang"] not in ("en", "ne", "rom"):
            problems.append(f"{q['id']}: bad lang")
        for spec in q.get("tools", []):
            for name in spec["name"].split("|"):
                if name not in TOOLS:
                    problems.append(f"{q['id']}: unknown tool {name}")
        for spec in q.get("numbers", []):
            if spec["tool"] not in TOOLS:
                problems.append(f"{q['id']}: unknown tool {spec['tool']}")
        if q.get("secret") and q["secret"] not in q["q"]:
            problems.append(f"{q['id']}: the secret is not in the question")
    return problems
