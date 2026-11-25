"""O-Kay inside the wallet replica: the replica's demo account (Sita Shrestha), made the same way
the replica makes it, so the chat's figures match the wallet's screens to the paisa."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai.tools import ToolContext, run_tool
from app.api.routes_session import MAX_CLOCK_SKEW, _replica_now
from app.replica.demo_history import fixture_lines, generate
from app.replica.seed import NAME, seed_replica_user
from app.services.recurring import detect_recurring
from app.sources.mock import MockBillSource, MockTransactionSource

# The replica pins its year to noon in Nepal on 23 Nov 2026 (app/test/fixtures/demo_year.txt);
# its build log: 419 transactions and a balance of Rs 17,021.76 at that moment.
PINNED = dt.datetime(2026, 11, 23, 6, 15, tzinfo=dt.UTC)
FIXTURE = Path(__file__).parent / "fixtures" / "replica_demo_year.txt"


def test_the_copy_makes_the_replicas_year() -> None:
    ours = fixture_lines(generate(PINNED))
    theirs = FIXTURE.read_text(encoding="utf-8").splitlines()
    assert len(ours) == len(theirs) == 419
    assert ours == theirs


def test_sita_gets_the_year_and_the_replicas_balance(session: Session) -> None:
    summary = seed_replica_user(session, "v_sita", PINNED)
    assert summary["transactions"] == 419
    source = MockTransactionSource(session)
    assert source.get_balance("v_sita") == 17_021_76  # what the replica's screens show
    txns = source.list_transactions("v_sita")
    assert len(txns) == 419 and all(t.counts for t in txns)
    assert txns[-1].occurred_at.date() == dt.date(2026, 11, 22)  # up to yesterday, Nepal time
    nea = [t for t in txns if t.service == "electricity"]
    assert nea and all(t.merchant == "Nepal Electricity Authority" for t in nea)
    momo = [t for t in txns if t.merchant == "Himal Momo Corner"]
    assert momo and all(t.category.value == "Food & Dining" for t in momo)
    rent = [t for t in txns if t.remarks == "Room rent share"]
    assert rent and all(t.merchant == "Anjali Rai" and t.is_debit for t in rent)


def test_o_kay_reads_her_bills_and_spending(session: Session) -> None:
    seed_replica_user(session, "v_sita", PINNED)
    source = MockTransactionSource(session)
    today = dt.date(2026, 11, 23)
    series = {s.service for s in detect_recurring(source.list_transactions("v_sita"), today)}
    assert {"electricity", "khanepani", "internet"} <= series
    ctx = ToolContext(session, source, MockBillSource(source), "v_sita", today)
    spent = run_tool(ctx, "get_spending_summary", {"period": "last_30_days"}).data
    assert spent["total_spent"].startswith("Rs. ")
    assert run_tool(ctx, "get_budgets", {}).data["budgets"]  # her demo budgets


def test_the_apps_clock_is_used_only_when_close(session: Session) -> None:
    now = dt.datetime.now(dt.UTC)
    near = now - dt.timedelta(hours=3)
    assert _replica_now(near) == near
    assert abs(_replica_now(now - MAX_CLOCK_SKEW * 3) - now) < dt.timedelta(minutes=1)
    assert abs(_replica_now(None) - now) < dt.timedelta(minutes=1)


def test_a_replica_session(make_client) -> None:
    c = make_client()
    sid = c.post("/sessions", json={"dataset": "replica"}).json()["session_id"]
    me = c.get("/me", headers={"X-User-Id": sid}).json()
    assert me["name"] == NAME and me["kyc_status"] == "verified"
    page = c.get("/transactions", params={"limit": 5}, headers={"X-User-Id": sid}).json()
    assert page["total"] > 400
    # No body: O-Kay's own demo person, as before.
    plain = c.post("/sessions").json()
    assert plain["name"] == "Anjali Thapa"
    assert c.post("/sessions", json={"dataset": "other"}).status_code == 422
