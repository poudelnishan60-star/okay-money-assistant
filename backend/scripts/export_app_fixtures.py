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

from app.ai.attachments import Upload, read  # noqa: E402
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
    "notifications": "/notifications",  # after the others: reading it stores the alerts
}


# A made-up wallet statement (newest first, like a Khalti export) for the file chart card.
_PAYMENTS = [
    ("Chiya Chautari", "Scan and Pay", 285),
    ("Ratna Mart", "Scan and Pay", 1240.50),
    ("NEA Electricity", "Service payment", 1180),
    ("Sajilo Supermarket", "Scan and Pay", 2310),
    ("Fund transfer to 9841234567", "Transfer", 1500),
    ("Chiya Chautari", "Scan and Pay", 340),
    ("Worldlink Internet", "Service payment", 1695),
    ("Withdraw to bank A/C 0123456789012", "Withdraw", 3000),
    ("Ratna Mart", "Scan and Pay", 865.25),
    ("Ncell Topup", "Service payment", 500),
    ("Chiya Chautari", "Scan and Pay", 410),
    ("Khalti hub load", "Load", -8000),
    ("Bakery Cafe", "Scan and Pay", 620),
    ("Fund transfer to 9812345678", "Transfer", 2200),
    ("Ratna Mart", "Scan and Pay", 1530),
    ("Cashback on Scan and Pay", "Cashback", -45),
    ("Khanepani", "Service payment", 450),
    ("Chiya Chautari", "Scan and Pay", 295),
    ("Khalti hub load", "Load", -10000),
    ("Sajilo Supermarket", "Scan and Pay", 1875.75),
    ("Bus ticket Kathmandu-Pokhara", "Service payment", 1800),
    ("Chiya Chautari", "Scan and Pay", 365),
    ("Fund transfer to 9841234567", "Transfer", 1000),
    ("Ratna Mart", "Scan and Pay", 990),
]


def sample_statement() -> bytes:
    rows = ["Date,Description,Type,Amount(-) Rs,Amount(+) Rs,Balance"]
    balance = 4_825.50  # after the newest entry
    day = dt.datetime(2026, 11, 8, 18, 0)
    for i, (text, kind, amount) in enumerate(_PAYMENTS):
        out, into = (f"{amount:.2f}", "") if amount > 0 else ("", f"{-amount:.2f}")
        rows.append(f"{day:%Y-%m-%d %H:%M},{text},{kind},{out},{into},{balance:.2f}")
        balance += amount  # the balance before this entry, for the next (older) row
        day -= dt.timedelta(days=1 if i % 3 else 2, hours=3)
    return ("\n".join(rows) + "\n").encode()


def main() -> None:
    app = create_app(
        Settings(_env_file=None, database_url="sqlite://", auto_seed=False, groq_api_key=None)
    )
    app.dependency_overrides[get_today] = lambda: ANCHOR
    (OUT / "api").mkdir(parents=True, exist_ok=True)
    with TestClient(app) as client:
        with app.state.session_factory() as s:
            seed_database(s, ANCHOR)
        for name, url in ENDPOINTS.items():
            r = client.get(url)
            r.raise_for_status()
            (OUT / "api" / f"{name}.json").write_text(
                json.dumps(r.json(), ensure_ascii=False, indent=1), encoding="utf-8"
            )
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
            # The money-flow card (its spending summary is already above).
            flow = run_tool(
                ctx, "get_spending_summary", {"period": "last_30_days", "group_by": "flow"}
            )
            cards += [c.model_dump(mode="json") for c in flow.cards if c.type == "money_flow"]  # type: ignore[attr-defined]
    # The chart card for a statement, as the chat sends it with the answer.
    cards += [
        c.model_dump(mode="json")
        for c in read(Upload("statement.csv", sample_statement()), None).charts
    ]  # type: ignore[arg-type]  # noqa: E501
    (OUT / "chat_cards.json").write_text(
        json.dumps(cards, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"wrote {len(ENDPOINTS)} API fixtures and {len(cards)} chat cards")  # noqa: T201


if __name__ == "__main__":
    main()
