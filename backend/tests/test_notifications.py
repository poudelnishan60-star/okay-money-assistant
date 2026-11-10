"""Alerts: budget 80% / 100%, bill due in 3 days, unusual spending, weekly summary."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Budget, Notification
from app.services.bills import BillStatus, list_bills, set_bill_status
from app.services.notifications import (
    Kind,
    last_summary_day,
    render,
    sync_notifications,
)
from app.services.user_settings import UserSettings, save_settings
from app.sources.mock import MockBillSource, MockTransactionSource
from tests.conftest import ANCHOR, USER


class RecordingPush:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str, dict[str, Any]]] = []

    def send(self, user_id: str, title: str, body: str, link: dict[str, Any]) -> None:
        self.sent.append((user_id, title, body, link))


def _sync(session: Session, today: dt.date = ANCHOR, push: Any = None) -> list[Notification]:
    src = MockTransactionSource(session)
    return sync_notifications(session, src, MockBillSource(src), USER, today, push)


def _clear_inbox(session: Session) -> None:
    for n in session.scalars(select(Notification)):
        session.delete(n)
    session.commit()


def _by_kind(rows: list[Notification]) -> dict[str, list[Notification]]:
    out: dict[str, list[Notification]] = {}
    for r in rows:
        out.setdefault(r.kind, []).append(r)
    return out


def test_demo_user_alerts_and_no_duplicates(seeded: Session) -> None:
    push = RecordingPush()
    new = _by_kind(_sync(seeded, push=push))
    # Shopping (BS month, Rs. 1,400) is past 80%; Ncell is due tomorrow; Sunday's summary.
    assert sorted(new) == ["bill", "budget", "weekly_summary"]
    (budget,) = new["budget"]
    assert json.loads(budget.params_json)["category"] == "Shopping"
    assert budget.key.endswith(":80")
    assert render(budget, "en", ANCHOR)[0] == "Shopping budget at 80%"
    (bill,) = new["bill"]
    assert render(bill, "en", ANCHOR)[0] == "Ncell is due tomorrow"
    assert bill.day == dt.date(2026, 11, 7)  # 3 days before the due date
    (weekly,) = new["weekly_summary"]
    assert weekly.day == dt.date(2026, 11, 8)  # Sunday, the default summary day
    assert len(push.sent) == 3 and {p[0] for p in push.sent} == {USER}

    assert _sync(seeded, push=push) == []  # nothing new: keys are unique per event
    assert len(push.sent) == 3
    # The next day the bill is due today: same event (same due date), so no second alert.
    assert [n.kind for n in _sync(seeded, ANCHOR + dt.timedelta(days=1))] == []


def test_budget_alert_day_and_amounts(seeded: Session) -> None:
    # Food has no budget in the seed. Rs. 500 is crossed early in November.
    seeded.add(Budget(user_id=USER, category="Food & Dining", limit_paisa=500_00, calendar="AD"))
    seeded.commit()
    food = next(
        n
        for n in _sync(seeded)
        if n.kind == "budget" and json.loads(n.params_json)["category"] == "Food & Dining"
    )
    p = json.loads(food.params_json)
    # Both thresholds were passed before the first check: one alert (100%), not two.
    assert p["threshold"] == 100 and food.key.endswith(":100")
    assert dt.date(2026, 11, 1) <= food.day <= dt.date(2026, 11, 8)
    assert p["spent_paisa"] >= 500_00  # the spend on the day it crossed, not today's
    title, body = render(food, "en", ANCHOR)
    assert title == "Food & Dining budget used up"
    assert body.startswith("Rs. ") and "of Rs. 500 in Nov 2026" in body
    assert render(food, "ne", ANCHOR)[0] == "खाना बजेट सकियो"


def test_80_then_100(seeded: Session) -> None:
    budget = seeded.scalars(select(Budget).where(Budget.category == "Groceries")).one()
    budget.limit_paisa = 1_300_00
    seeded.commit()
    first = [n for n in _sync(seeded) if n.kind == "budget"]
    groceries = [n for n in first if json.loads(n.params_json)["category"] == "Groceries"]
    assert [n.key.rsplit(":", 1)[1] for n in groceries] == ["80"]  # Rs. 1,092.80 of 1,300
    budget.limit_paisa = 1_000_00  # now over: the 100% alert comes, the 80% one stays
    seeded.commit()
    later = [n for n in _sync(seeded) if n.kind == "budget"]
    assert [n.key.rsplit(":", 1)[1] for n in later] == ["100"]


def test_bills_window_and_dismissed(seeded: Session) -> None:
    src = MockTransactionSource(seeded)
    bills = MockBillSource(src)
    upcoming = list_bills(seeded, bills, USER, ANCHOR)
    ncell = next(v for v in upcoming if v.bill.merchant == "Ncell")
    nea = next(v for v in upcoming if v.days_until_due > 3)
    alerts = [n for n in _sync(seeded) if n.kind == "bill"]
    assert [json.loads(n.params_json)["bill_id"] for n in alerts] == [ncell.id]
    # Electricity enters the 3-day window later on.
    later_day = nea.bill.due_date - dt.timedelta(days=3)
    assert any(
        json.loads(n.params_json)["bill_id"] == nea.id
        for n in _sync(seeded, later_day)
        if n.kind == "bill"
    )
    # A dismissed bill never alerts.
    _clear_inbox(seeded)
    set_bill_status(seeded, bills, USER, ANCHOR, ncell.id, BillStatus.DISMISSED)
    assert not [n for n in _sync(seeded) if n.kind == "bill"]


def test_bill_words() -> None:
    n = Notification(
        kind="bill",
        params_json=json.dumps(
            {"merchant": "Ncell", "due_date": "2026-11-10", "usual_amount_paisa": 499_00}
        ),
    )
    assert render(n, "en", dt.date(2026, 11, 10))[0] == "Ncell is due today"
    assert render(n, "en", dt.date(2026, 11, 7))[0] == "Ncell is due in 3 days"
    assert render(n, "en", dt.date(2026, 11, 12))[0] == "Ncell was due 2 days ago"
    assert render(n, "ne", dt.date(2026, 11, 10)) == (
        "Ncell को बिल आज तिर्नुपर्छ",
        "सामान्यतया रु. 499। अहिले तिर्नुहोस् वा Autopay राख्नुहोस्।",
    )


def test_unusual_spending_alert(seeded: Session) -> None:
    # Late October: Shopping is far above its usual level (see the dashboard tests).
    oct_end = dt.date(2026, 10, 31)
    unusual = [n for n in _sync(seeded, oct_end) if n.kind == Kind.UNUSUAL]
    shopping = next(n for n in unusual if json.loads(n.params_json)["category"] == "Shopping")
    title, body = render(shopping, "en", oct_end)
    assert title == "Unusual spending on Shopping"
    assert "so far in Oct 2026" in body and "x your usual Rs. " in body
    link = json.loads(shopping.params_json)
    assert (link["start"], link["end"]) == ("2026-10-01", "2026-10-31")


def test_weekly_summary_day_and_switches(seeded: Session) -> None:
    assert last_summary_day(ANCHOR, "sunday") == dt.date(2026, 11, 8)
    assert last_summary_day(ANCHOR, "monday") == ANCHOR  # today counts
    assert last_summary_day(ANCHOR, "tuesday") == dt.date(2026, 11, 3)

    settings = UserSettings(weekly_summary_day="monday")
    settings.alerts.bills = False
    settings.alerts.budget = False
    save_settings(seeded, USER, settings)
    new = _sync(seeded)
    assert [n.kind for n in new] == ["weekly_summary"]
    p = json.loads(new[0].params_json)
    assert (p["start"], p["end"]) == ("2026-11-02", "2026-11-08")
    assert p["spent_paisa"] > 0 and p["top_category"]

    settings.alerts.weekly_summary = False
    save_settings(seeded, USER, settings)
    _clear_inbox(seeded)
    assert _sync(seeded) == []


def test_weekly_words_nepali(seeded: Session) -> None:
    weekly = next(n for n in _sync(seeded) if n.kind == "weekly_summary")
    title, body = render(weekly, "ne", ANCHOR)
    assert title.startswith("तपाईंको हप्ता: रु. ")
    assert "सबैभन्दा धेरै शिक्षा मा" in body


def test_api_inbox_read_and_isolation(client: TestClient) -> None:
    inbox = client.get("/notifications").json()
    assert inbox["unread"] == 3
    kinds = [n["kind"] for n in inbox["items"]]
    assert kinds == ["weekly_summary", "bill", "budget"]  # newest first (by day)
    bill = inbox["items"][1]
    assert bill["title"] == "Ncell is due tomorrow"
    assert bill["link"] == {"screen": "bills", "params": {}}
    assert bill["data"]["usual_amount_paisa"] == 499_00
    assert not bill["read"]

    r = client.post("/notifications/read", json={"ids": [bill["id"]]}).json()
    assert r == {"updated": 1, "unread": 2}
    again = client.get("/notifications").json()
    assert again["unread"] == 2 and len(again["items"]) == 3
    assert next(n for n in again["items"] if n["id"] == bill["id"])["read"]
    assert client.post("/notifications/read", json={}).json() == {"updated": 2, "unread": 0}

    # Language follows the user's settings.
    settings = client.get("/me/settings").json()
    client.put("/me/settings", json={**settings, "language": "ne"})
    titles = [n["title"] for n in client.get("/notifications").json()["items"]]
    assert "Ncell को बिल भोलि तिर्नुपर्छ" in titles

    # Every visitor has their own inbox.
    visitor = client.post("/sessions").json()["session_id"]
    theirs = client.get("/notifications", headers={"X-User-Id": visitor}).json()
    assert theirs["unread"] == 3
    other_ids = {n["id"] for n in theirs["items"]}
    assert not other_ids & {n["id"] for n in again["items"]}
    # ...and cannot mark someone else's read.
    assert client.post(
        "/notifications/read", json={"ids": [bill["id"]]}, headers={"X-User-Id": visitor}
    ).json() == {"updated": 0, "unread": 3}


def test_unusual_link_opens_filtered_transactions(seeded: Session) -> None:
    from app.services.notifications import link_for

    oct_end = dt.date(2026, 10, 31)
    shopping = next(
        n
        for n in _sync(seeded, oct_end)
        if n.kind == "unusual" and json.loads(n.params_json)["category"] == "Shopping"
    )
    assert link_for(shopping) == {
        "screen": "transactions",
        "params": {
            "category": "Shopping",
            "start": "2026-10-01",
            "end": "2026-10-31",
            "spending_only": "true",
        },
    }
    assert seeded.scalars(select(Notification)).all()
