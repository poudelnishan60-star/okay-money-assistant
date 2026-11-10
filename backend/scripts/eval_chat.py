"""Evaluate O-Kay on the 50 questions in evals/questions.json against the real LLM (needs
GROQ_API_KEY in backend/.env). Uses a throwaway in-memory copy of the demo data seeded at the
file's anchor date, so the expected numbers never move. Sends mock data only.

    python scripts/eval_chat.py                    # all 50 (about 25 minutes on the free tier)
    python scripts/eval_chat.py --only en01,ne07   # some
    python scripts/eval_chat.py --lang rom         # one language
    python scripts/eval_chat.py --pause 0          # no pause between questions

Prints one line per question and a summary; writes the full report (answers, tool calls,
problems) to evals/results/. See evals/runner.py for what is checked.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai.llm import GroqLLMClient  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import init_db, make_engine, make_session_factory  # noqa: E402
from app.seed import seed_database  # noqa: E402
from evals.runner import (  # noqa: E402
    Result,
    load_questions,
    run_question,
    summarize,
    to_json,
    validate_questions,
)

BUSY_WAIT_SECONDS = 65  # Groq's free-tier limits are per minute


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate O-Kay on evals/questions.json")
    parser.add_argument("--only", help="comma-separated question ids")
    parser.add_argument("--lang", choices=["en", "ne", "rom"])
    parser.add_argument("--topic")
    parser.add_argument(
        "--pause", type=float, default=20.0, help="seconds between questions (default 20)"
    )
    parser.add_argument("--out", type=Path, help="report path (default evals/results/...)")
    args = parser.parse_args()

    settings = get_settings()
    if settings.groq_api_key is None or not settings.groq_api_key.get_secret_value():
        sys.exit("No GROQ_API_KEY in backend/.env")
    anchor, questions = load_questions()
    if problems := validate_questions(questions):
        sys.exit("questions.json: " + "; ".join(problems))
    only = set(args.only.split(",")) if args.only else None
    picked = [
        q
        for q in questions
        if (only is None or q["id"] in only)
        and (args.lang is None or q["lang"] == args.lang)
        and (args.topic is None or q["topic"] == args.topic)
    ]

    engine = make_engine("sqlite://")
    init_db(engine)
    session = make_session_factory(engine)()
    seed_database(session, anchor)
    llm = GroqLLMClient(settings)
    models = [settings.llm_model, *settings.fallback_models]
    print(f"{len(picked)} question(s), data as of {anchor}, models {models}\n")

    results: list[Result] = []
    for i, q in enumerate(picked):
        if i and args.pause:
            time.sleep(args.pause)
        r = run_question(session, llm, q, anchor)
        if r.status == "error":  # rate limit or outage: wait once, then try again
            print(f"  {q['id']}: {r.problems[0]}; waiting {BUSY_WAIT_SECONDS}s", flush=True)
            time.sleep(BUSY_WAIT_SECONDS)
            r = run_question(session, llm, q, anchor)
        results.append(r)
        tools = ",".join(name for name, _ in r.tools) or "-"
        print(
            f"{r.status.upper():5} {r.id:6} {r.seconds:5.1f}s  tools={tools}  "
            f"model={'>'.join(m.split('/')[-1] for m in r.models) or '-'}"
            + (f"\n      problems: {'; '.join(r.problems)}" if r.problems else ""),
            flush=True,
        )
        if r.problems:
            print(f"      answer: {r.answer[:300]!r}", flush=True)

    s = summarize(results)
    o = s["overall"]
    print(f"\nPassed {o['passed']}/{o['scored']} ({o['pass_rate']}%), errors: {o['errors']}")
    for group in ("by_language", "by_topic", "by_answering_model"):
        print(
            f"  {group[3:]}: "
            + ", ".join(f"{k} {v['passed']}/{v['scored']}" for k, v in s[group].items())
        )
    if s["problems_by_kind"]:
        print("  problems: " + ", ".join(f"{k} {n}" for k, n in s["problems_by_kind"].items()))

    out = args.out or ROOT / "evals" / "results" / f"eval-{dt.datetime.now():%Y%m%d-%H%M}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    meta = {"anchor": anchor.isoformat(), "models": models, "run_at": dt.datetime.now()}
    out.write_text(to_json(results, meta), encoding="utf-8")
    print(f"\nReport: {out}")


if __name__ == "__main__":
    main()
