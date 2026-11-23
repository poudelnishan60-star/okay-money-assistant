"""Transaction status (step 11): failed, pending and reversed transactions in the seed, kept
out of spending, budgets, forecasts and bills; get_transaction_status; and the new app flows
(load money, withdraw, request or split, support, block the wallet), none of which moves
money."""

from __future__ import annotations

import datetime as dt
import itertools

import pytest
from sqlalchemy.orm import Session

from app.ai.tools import ToolContext, ToolError, run_tool, split_shares
from app.domain import Category, KycStatus, Transaction, TxnStatus
from app.models import User
from app.money import format_npr
from app.periods import month_period
from app.services.budgets import spent_in_period
from app.services.recurring import detect_recurring
from app.sources.base import TransactionFilter
from app.sources.mock import MockBillSource, MockTransactionSource
from tests.conftest import ANCHOR, USER


@pytest.fixture
def ctx(seeded: Session) -> ToolContext:
    source = MockTransactionSource(seeded)
    return ToolContext(seeded, source, MockBillSource(source), USER, ANCHOR)


def _all(ctx: ToolContext) -> list[Transaction]:
    return ctx.source.list_transactions(USER)


def _one(ctx: ToolContext, status: TxnStatus) -> Transaction:
    (t,) = [t for t in _all(ctx) if t.status is status]
    return t


# --- the seed ---------------------------------------------------------------------------------


def test_the_seed_has_a_reversed_a_pending_and_a_failed_transaction(ctx: ToolContext) -> None:
    txns = _all(ctx)
    reversed_ = _one(ctx, TxnStatus.REVERSED)
    (refund,) = [t for t in txns if t.reversal_of]
    assert reversed_.service == "electricity" and reversed_.is_debit
    assert refund.reversal_of == reversed_.id and not refund.is_debit
    assert refund.amount_paisa == reversed_.amount_paisa
    assert refund.occurred_at.date() == reversed_.occurred_at.date() + dt.timedelta(days=1)
    # The user paid again the same day: that one went through.
    retry = [
        t
        for t in txns
        if t.service == "electricity"
        and t.counts
        and t.occurred_at.date() == reversed_.occurred_at.date()
    ]
    assert len(retry) == 1 and retry[0].occurred_at > reversed_.occurred_at

    pending = _one(ctx, TxnStatus.PENDING)
    assert pending.merchant == "Sujan Tamang" and pending.amount_paisa == 1_500_00
    assert pending.occurred_at == dt.datetime(2026, 11, 8, 19, 40)

    failed = _one(ctx, TxnStatus.FAILED)
    assert failed.service == "mobile_topup" and failed.amount_paisa == 500_00
    assert failed.occurred_at == dt.datetime(2026, 11, 5, 14, 20)  # over 24 hours ago
    assert sum(1 for t in txns if not t.counts) == 4


def test_only_completed_transactions_count(ctx: ToolContext) -> None:
    txns = _all(ctx)
    counted = ctx.source.list_transactions(USER, TransactionFilter(counted_only=True))
    assert len(counted) == len(txns) - 4 and all(t.counts for t in counted)

    nov = month_period(ANCHOR)
    spent = sum(
        t.amount_paisa for t in counted if t.is_spending and nov.start <= t.occurred_at.date()
    )
    summary = run_tool(ctx, "get_spending_summary", {"period": "this_month"})
    assert summary.data["total_spent"] == format_npr(spent)
    # The failed Rs. 500 topup is this month but isn't spending or budget use.
    assert not _one(ctx, TxnStatus.FAILED).is_spending
    assert spent_in_period(txns, nov) == spent  # even when given every transaction


def test_bills_still_see_one_nea_payment_a_month(ctx: ToolContext) -> None:
    (nea,) = [s for s in detect_recurring(_all(ctx), as_of=ANCHOR) if s.service == "electricity"]
    assert nea.occurrences == 3 and nea.cadence == "monthly"
    assert _one(ctx, TxnStatus.REVERSED).id not in nea.transaction_ids


# --- get_transaction_status -----------------------------------------------------------------


def test_a_failed_payment_past_its_refund_time_is_overdue(ctx: ToolContext) -> None:
    failed = _one(ctx, TxnStatus.FAILED)
    r = run_tool(ctx, "get_transaction_status", {"transaction_id": failed.id})
    d = r.data
    assert d["status"] == "failed" and d["amount"] == "Rs. 500"
    assert d["refund_expected_by"] == "Fri 06 Nov 2026, 14:20"
    assert d["overdue"] is True and "72 hours" in d["support"]
    assert "24 hours" in d["refund_rule"]
    assert [i.status for i in r.cards[0].items] == ["failed"]
    # Overdue: the support button comes with it, built in code, the transaction attached.
    support = r.cards[1]
    assert (support.flow, support.prefill.transaction_id) == ("support", failed.id)
    assert "app_flow" in r.topics


def test_a_pending_transfer_is_not_overdue_yet(ctx: ToolContext) -> None:
    pending = _one(ctx, TxnStatus.PENDING)
    d = run_tool(ctx, "get_transaction_status", {"transaction_id": pending.id}).data
    assert d["status"] == "pending" and d["expected_by"] == "Mon 09 Nov 2026, 19:40"
    assert d["overdue"] is False and "support" not in d
    late = ToolContext(
        ctx.session, ctx.source, ctx.bills, USER, ANCHOR, now=dt.datetime(2026, 11, 9, 20)
    )
    assert run_tool(late, "get_transaction_status", {"transaction_id": pending.id}).data["overdue"]


def test_a_reversed_payment_shows_the_money_returned(ctx: ToolContext) -> None:
    rev = _one(ctx, TxnStatus.REVERSED)
    r = run_tool(ctx, "get_transaction_status", {"transaction_id": rev.id})
    back = r.data["money_returned"]
    assert back["amount"] == format_npr(rev.amount_paisa) and "10:05" in back["when"]
    assert "overdue" not in r.data
    items = r.cards[0].items
    assert [(i.status, i.refund) for i in items] == [("reversed", False), ("success", True)]

    (refund,) = [t for t in _all(ctx) if t.reversal_of]
    d = run_tool(ctx, "get_transaction_status", {"transaction_id": refund.id}).data
    assert d["refund_of"] == rev.id and d["meaning"].startswith("Money returned")
    with pytest.raises(ToolError, match="get_transactions"):
        run_tool(ctx, "get_transaction_status", {"transaction_id": "txn_9999"})


def test_failed_finds_reversed_and_earlier_ones(ctx: ToolContext) -> None:
    # Seen live: status=failed for the last 7 days of bill payments found nothing, and the
    # model said no money was taken, while the failed NEA payment a month earlier was refunded.
    args = {"period": "last_7_days", "status": "failed", "type": "bill_payment"}
    d = run_tool(ctx, "get_transactions", args).data
    assert d["count"] == 0
    (earlier,) = d["none_in_this_period_but_earlier"]
    assert earlier["status"] == "reversed" and earlier["id"] == _one(ctx, TxnStatus.REVERSED).id
    # Over the whole period asked, "failed" finds both the failed and the reversed one.
    nov_oct = {"period": "custom", "start": "2026-10-01", "end": "2026-11-09", "status": "failed"}
    statuses = {
        line["status"] for line in run_tool(ctx, "get_transactions", nov_oct).data["latest"]
    }
    assert statuses == {"failed", "reversed"}


def test_get_transactions_finds_problem_payments_by_status(ctx: ToolContext) -> None:
    r = run_tool(ctx, "get_transactions", {"period": "last_30_days", "status": "failed"})
    (line,) = r.data["latest"]
    assert line["status"] == "failed" and line["id"] == _one(ctx, TxnStatus.FAILED).id
    assert r.data["total_paid_out"] == "Rs. 0"  # totals are completed payments only
    everything = run_tool(ctx, "get_transactions", {"period": "last_30_days"}).data
    start = ANCHOR - dt.timedelta(days=29)
    n = sum(1 for t in _all(ctx) if not t.counts and t.occurred_at.date() >= start)
    assert n >= 2  # at least the pending transfer and the failed topup
    assert everything["not_in_totals"].startswith(f"{n} failed, pending, reversed or refunded")


# --- the new app flows ------------------------------------------------------------------------


def test_load_and_withdraw_open_buttons_within_the_limits(ctx: ToolContext) -> None:
    load = run_tool(ctx, "open_app_flow", {"flow": "load_money", "amount": 5000})
    card = load.cards[0]
    assert card.flow == "load_money" and card.prefill.amount_paisa == 5_000_00
    assert "NOTHING has been paid" in load.data["status"] and "cap_note" not in load.data

    big = run_tool(ctx, "open_app_flow", {"flow": "load_money", "amount": 40000})
    assert big.cards and "Rs. 61,944.86" in big.data["cap_note"]  # over the overnight cap

    over = run_tool(ctx, "open_app_flow", {"flow": "load_money", "amount": 250000})
    assert over.cards == [] and over.data["limit"] == "Bank to wallet: Rs. 2,00,000 per transaction"

    out = run_tool(ctx, "open_app_flow", {"flow": "withdraw_to_bank", "amount": 1000})
    assert out.cards[0].flow == "withdraw_to_bank" and out.cards[0].title == "Withdraw to bank"


def test_a_bill_is_split_in_code_with_whole_paisa() -> None:
    assert split_shares(1_500_00, 3) == (500_00, 500_00)
    assert split_shares(1_000_00, 3) == (333_33, 333_34)  # the leftover paisa is the requester's
    for total, people in itertools.product([1_00, 999_99, 1_000_01, 12_345_67], range(2, 21)):
        each, mine = split_shares(total, people)
        assert each * (people - 1) + mine == total and 0 <= mine - each < people


def test_request_money_splits_the_total(ctx: ToolContext) -> None:
    r = run_tool(
        ctx,
        "open_app_flow",
        {"flow": "request_money", "amount": 1000, "split_between": 3, "recipient_names": ["Sita"]},
    )
    p = r.cards[0].prefill
    assert (p.total_paisa, p.split_between, p.amount_paisa, p.your_share_paisa) == (
        1_000_00,
        3,
        333_33,
        333_34,
    )
    assert [(s.name, s.amount_paisa) for s in p.shares] == [("Sita", 333_33), ("Person 2", 333_33)]
    assert r.data["each_other_person_pays"] == "Rs. 333.33"
    assert r.data["your_share"] == "Rs. 333.34" and "NOTHING" not in r.data["status"]

    one = run_tool(
        ctx, "open_app_flow", {"flow": "request_money", "amount": 800, "recipient_name": "Ram"}
    )
    assert one.cards[0].title == "Request money from Ram"
    assert one.cards[0].prefill.amount_paisa == 800_00 and one.cards[0].prefill.shares is None

    tiny = run_tool(
        ctx, "open_app_flow", {"flow": "request_money", "amount": 25, "split_between": 3}
    )
    assert tiny.cards == [] and tiny.data["limit"] == "The minimum is Rs. 10."
    with pytest.raises(ToolError, match="needs amount"):
        run_tool(ctx, "open_app_flow", {"flow": "request_money", "split_between": 3})
    with pytest.raises(ToolError, match="only 1 others"):
        run_tool(
            ctx,
            "open_app_flow",
            {
                "flow": "request_money",
                "amount": 900,
                "split_between": 2,
                "recipient_names": ["A", "B"],
            },
        )


def test_support_attaches_the_transaction(ctx: ToolContext) -> None:
    failed = _one(ctx, TxnStatus.FAILED)
    r = run_tool(
        ctx,
        "open_app_flow",
        {"flow": "support", "transaction_id": failed.id, "issue": "topup failed, money deducted"},
    )
    card = r.cards[0]
    assert card.flow == "support" and card.prefill.transaction_id == failed.id
    assert card.prefill.transaction_label == "Nepal Telecom · Rs. 500 · 05 Nov 2026 · failed"
    assert card.prefill.issue == "topup failed, money deducted"
    assert r.data["complaint_time"] == "Khalti answers complaints within 72 hours."
    assert (
        run_tool(ctx, "open_app_flow", {"flow": "support"}).cards[0].prefill.transaction_id is None
    )
    with pytest.raises(ToolError):
        run_tool(ctx, "open_app_flow", {"flow": "support", "transaction_id": "txn_9999"})


def test_support_and_blocking_work_without_kyc_but_money_flows_dont(ctx: ToolContext) -> None:
    ctx.session.get(User, USER).kyc_status = KycStatus.NOT_STARTED.value
    ctx.session.commit()
    block = run_tool(ctx, "open_app_flow", {"flow": "block_wallet"})
    assert block.cards[0].flow == "block_wallet" and block.cards[0].title == "Block my wallet"
    assert "search_help_articles" in block.data["next_step"]
    assert "24 hours" in block.data["report_rule"]
    assert block.data["wallet"].startswith("NOT blocked yet")  # never "your wallet is blocked"
    assert run_tool(ctx, "open_app_flow", {"flow": "support"}).cards
    for flow in ("load_money", "withdraw_to_bank", "request_money"):
        assert run_tool(ctx, "open_app_flow", {"flow": flow, "amount": 500}).cards == [], flow


def test_the_api_shows_the_status(make_client) -> None:
    c = make_client()
    items = c.get("/transactions", params={"period": "30d", "limit": 200}).json()["items"]
    by_status = {i["status"] for i in items}
    assert {"success", "pending", "failed"} <= by_status
    refunds = [
        i
        for i in c.get("/transactions", params={"limit": 200, "type": "bill_payment"}).json()[
            "items"
        ]
        if i["reversal_of"]
    ]
    assert len(refunds) == 1 and refunds[0]["direction"] == "credit"
    assert Category.BILLS.value == refunds[0]["category"]
