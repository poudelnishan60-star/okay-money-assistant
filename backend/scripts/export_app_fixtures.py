"""Export real API responses (seeded demo data, 'today' = 2026-11-09) as JSON fixtures for the
Flutter tests, so the app is always tested against what the backend actually returns.

    python scripts/export_app_fixtures.py

Writes app/test/ai_assistant/fixtures/api/*.json and app/test/ai_assistant/fixtures/chat_cards.json.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.ai.tools import ToolContext, run_tool  # noqa: E402
from app.api.deps import get_today  # noqa: E402
from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.seed import seed_database  # noqa: E402
from app.sources.mock import MockBillSource, MockTransactionSource  # noqa: E402

ANCHOR = dt.date(2026, 11, 9)
REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "app/test/ai_assistant/fixtures"

ENDPOINTS = {
    "me": "/me",
    "categories": "/categories",
    "settings": "/me/settings",
    "transactions_all": "/transactions?limit=200",
    "transactions_7d": "/transactions?period=7d&limit=50",
    "transactions_food_month": "/transactions?period=this_month&category=Food+%26+Dining&limit=50",
    "dashboard_current": "/insights/dashboard",
    "dashboard_oct": "/insights/dashboard?month=2026-10",
    "dashboard_kartik_bs": "/insights/dashboard?month=2083-07&calendar=BS",
    "budgets": "/budgets",
    "goals": "/goals",
    "smart_deposits": "/smart-deposits",
    "bills": "/bills",
}


def main() -> None:
    app = create_app(Settings(_env_file=None, database_url="sqlite://", auto_seed=False,
                              groq_api_key=None))
    app.dependency_overrides[get_today] = lambda: ANCHOR
    (OUT / "api").mkdir(parents=True, exist_ok=True)
    with TestClient(app) as client:
        with app.state.session_factory() as s:
            seed_database(s, ANCHOR)
        for name, url in ENDPOINTS.items():
            r = client.get(url)
            r.raise_for_status()
            (OUT / "api" / f"{name}.json").write_text(
                json.dumps(r.json(), ensure_ascii=False, indent=1), encoding="utf-8")
        with app.state.session_factory() as s:
            src = MockTransactionSource(s)
            ctx = ToolContext(s, src, MockBillSource(src), "demo_user", ANCHOR)
            cards: list[dict[str, object]] = []
            for tool, args in [
                ("get_spending_summary", {"period": "month", "month": "2026-10"}),
                ("get_budgets", {}),
                ("get_recurring_payments", {}),
                ("get_goals", {}),
                ("get_transactions", {"period": "last_7_days"}),
                ("upsert_budget", {"category": "Food & Dining", "limit_amount": 6000}),
                ("open_app_flow", {"flow": "bill_payment", "service": "electricity"}),
            ]:
                cards += [c.model_dump(mode="json") for c in run_tool(ctx, tool, args).cards]
    (OUT / "chat_cards.json").write_text(json.dumps(cards, ensure_ascii=False, indent=1),
                                         encoding="utf-8")
    print(f"wrote {len(ENDPOINTS)} API fixtures and {len(cards)} chat cards")  # noqa: T201


if __name__ == "__main__":
    main()
