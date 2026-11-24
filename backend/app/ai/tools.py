"""The assistant's tools. The LLM never does arithmetic: every number it may quote comes from
here, computed by the same services as the REST API and pre-formatted ("Rs. 9,710").

Each tool returns a ToolResult:
- data:   what the LLM sees (minimal fields, PII masked, untrusted text neutralized)
- cards:  rich cards for the app (built in code)
- topics: used to pick follow-up chips
"""

from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.cards import (
    ApiRequest,
    AppFlowPrefill,
    BillItem,
    BillsListCard,
    BudgetItem,
    BudgetProgressCard,
    CategoryAmount,
    CategoryBreakdownCard,
    ConfirmActionCard,
    Detail,
    FlowItem,
    GoalItem,
    GoalProgressCard,
    MoneyFlow,
    MoneyFlowCard,
    OpenAppFlowCard,
    RequestShare,
    SpendingSummaryCard,
    TransactionItem,
    TransactionsLink,
    TransactionsPreviewCard,
    money_flow,
)
from app.ai.safety import untrusted
from app.domain import (
    NON_SPENDING,
    Category,
    Direction,
    KycStatus,
    Transaction,
    TxnStatus,
    TxnType,
)
from app.models import Budget, FaqArticle, Goal
from app.money import format_npr, to_paisa
from app.periods import (
    CalendarSystem,
    Period,
    custom_period,
    last_n_days,
    month_period,
    month_period_from_key,
    previous_month_period,
    previous_period,
    to_bs_string,
)
from app.rules import (
    ACCOUNT_RULES,
    CARDLESS_ATM_PER_DAY_PAISA,
    CARDLESS_ATM_PER_MONTH_PAISA,
    COMPLAINT_REPLY_HOURS,
    DEPOSIT_COUNT_NOTE,
    DEPOSITS_PER_DAY,
    ESCROW_MIN_PAISA,
    FEES_NOTE,
    FLOW_LIMITS,
    KYC_RULES,
    LAST_CHECKED,
    LIMITS,
    MIN_PAYMENT_PAISA,
    NO_LIMIT_PAYMENTS,
    OVERNIGHT_BALANCE_CAP_PAISA,
    OVERNIGHT_CAP_RULE,
    PENDING_SETTLE_HOURS,
    REFUND_HOURS,
    REFUND_RULES,
    SECURITY_RULES,
    SOURCE,
    Limit,
)
from app.services.bills import list_bills
from app.services.budgets import BudgetLevel, budget_statuses, evaluate_budget, spent_in_period
from app.services.forecast import BalanceForecast, balance_forecast, month_end_forecast
from app.services.goals import goal_progress
from app.services.insights import BASELINE_DAYS, summarize, unusual_spending
from app.services.user_settings import load_settings
from app.services.wallet_limits import TRACKED, LimitUse, check_amount, kyc_status, usage
from app.sources.base import BillSource, TransactionFilter, TransactionSource


@dataclass
class ToolContext:
    session: Session
    source: TransactionSource
    bills: BillSource
    user_id: str
    today: dt.date
    # Amounts O-Kay already showed a send/load/withdraw button for in this message, by
    # limit (rules.FLOW_LIMITS): they count against today's limit like money sent.
    offered: dict[str, int] = field(default_factory=dict)
    # The time now (Nepal), for "is a refund overdue?". None: noon on `today`, so tests and
    # evals with a pinned date always get the same answer.
    now: dt.datetime | None = None
    # Settings, "Let O-Kay read my transactions": off means the money tools return a note.
    can_read_money: bool = True

    def clock(self) -> dt.datetime:
        return self.now or dt.datetime.combine(self.today, dt.time(12))


@dataclass
class ToolResult:
    data: dict[str, Any]
    cards: list[BaseModel] = field(default_factory=list)
    topics: set[str] = field(default_factory=set)


class ToolError(Exception):
    """A problem the model can fix (bad date, unknown goal...). Sent back to it as text."""


# --- shared argument pieces --------------------------------------------------------------

PeriodPreset = Literal[
    "today",
    "yesterday",
    "last_7_days",
    "last_30_days",
    "this_month",
    "last_month",
    "month",
    "custom",
]
CATEGORY_VALUES = [c.value for c in Category]
SPENDING_CATEGORIES = [c.value for c in Category if c not in NON_SPENDING]
SERVICES = ["electricity", "khanepani", "internet", "tv", "data_pack", "mobile_topup"]


class PeriodArgs(BaseModel):
    period: PeriodPreset = "this_month"
    month: str | None = Field(None, pattern=r"^\d{4}-\d{2}$")
    calendar: Literal["AD", "BS"] = "AD"
    start: dt.date | None = None
    end: dt.date | None = None

    def resolve(self, today: dt.date) -> tuple[Period, Period]:
        cal = CalendarSystem(self.calendar)
        try:
            match self.period:
                case "today":
                    p = Period(today, today, "Today")
                    return p, Period(today - dt.timedelta(1), today - dt.timedelta(1), "Yesterday")
                case "yesterday":
                    y = today - dt.timedelta(days=1)
                    return Period(y, y, "Yesterday"), Period(
                        y - dt.timedelta(1), y - dt.timedelta(1), "Day before"
                    )
                case "last_7_days":
                    p = last_n_days(today, 7)
                    return p, previous_period(p, None)
                case "last_30_days":
                    p = last_n_days(today, 30)
                    return p, previous_period(p, None)
                case "this_month":
                    p = month_period(today, cal)
                    return p, previous_period(p, cal)
                case "last_month":
                    p = previous_month_period(today, cal)
                    return p, previous_period(p, cal)
                case "month":
                    if not self.month:
                        raise ToolError("period=month needs month='YYYY-MM'")
                    p = month_period_from_key(self.month, cal)
                    return p, previous_period(p, cal)
                case "custom":
                    if self.start is None or self.end is None:
                        raise ToolError("period=custom needs start and end dates")
                    p = custom_period(self.start, self.end)
                    return p, previous_period(p, None)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        raise ToolError(f"unknown period {self.period}")


def _rs(paisa: int) -> str:
    return format_npr(paisa)


def _rupees_to_paisa(amount: float | None) -> int | None:
    return None if amount is None else to_paisa(Decimal(str(amount)))


def _link(period: Period, today: dt.date, count: int, **filters: Any) -> TransactionsLink:
    clean = {k: v for k, v in filters.items() if v is not None}
    return TransactionsLink(
        count=count,
        filters={
            "start": period.start.isoformat(),
            "end": min(period.end, today).isoformat(),
            **clean,
        },
    )


def _change(pct: float | None) -> str:
    if pct is None:
        return "no comparison (nothing spent in the comparison period)"
    if pct == 0:
        return "same as before"
    return f"{abs(pct):g}% {'more' if pct > 0 else 'less'}"


# --- get_spending_summary -----------------------------------------------------------------


class SpendingSummaryArgs(PeriodArgs):
    group_by: Literal["category", "merchant", "day", "flow"] = "category"
    category: Category | None = None


_IN_LABELS = {Category.TRANSFERS: "Transfers in"}
_MOVED_LABELS = {Category.TRANSFERS: "Transfers out", Category.SAVINGS: "Smart Deposit"}


def _money_flow(txns: list[Transaction], start: dt.date, end: dt.date) -> MoneyFlow | None:
    """Every credit by source and every debit by use (spending by category, then transfers
    sent and Smart Deposit), for the money-flow diagram. None when nothing moved."""
    came: dict[str, int] = defaultdict(int)
    spent: dict[str, int] = defaultdict(int)
    moved: dict[str, int] = defaultdict(int)
    for t in txns:
        if not t.counts or not start <= t.occurred_at.date() <= end:
            continue
        if not t.is_debit:
            came[_IN_LABELS.get(t.category, t.category.value)] += t.amount_paisa
        elif t.is_spending:
            spent[t.category.value] += t.amount_paisa
        else:
            moved[_MOVED_LABELS.get(t.category, t.category.value)] += t.amount_paisa
    money_in, money_out = sum(came.values()), sum(spent.values()) + sum(moved.values())
    if not money_in and not money_out:
        return None

    def ranked(d: dict[str, int]) -> list[tuple[str, int]]:
        return sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))

    spending = ranked(spent)
    if len(spending) > 5:  # the four biggest, then the rest together
        spending = [*spending[:4], ("Other spending", sum(v for _, v in spending[4:]))]
    return money_flow(
        [FlowItem(label=k, paisa=v, kind="in") for k, v in ranked(came)],
        [
            *(FlowItem(label=k, paisa=v, kind="out") for k, v in spending),
            *(FlowItem(label=k, paisa=v, kind="moved") for k, v in ranked(moved)),
        ],
        money_in,
        money_out,
    )


def history_start(ctx: ToolContext) -> dt.date | None:
    """The first day with any data for this user (None: no data at all)."""
    first = ctx.source.list_transactions(ctx.user_id, TransactionFilter(end=ctx.today))
    return min((t.occurred_at.date() for t in first), default=None)


def _no_data(ctx: ToolContext, period: Period, topic: str) -> ToolResult | None:
    """A period that ends before the history starts has no data, which is not the same as
    spending Rs. 0 (the eval caught "In 2020 you spent Rs. 0")."""
    start = history_start(ctx)
    if start is not None and period.end >= start:
        return None
    return ToolResult(
        {
            "period": period.label,
            "no_data": True,
            "history_starts": start.isoformat() if start else None,
            "note": "There is no data for this period. Tell the user you don't have that data "
            "(say from when the history starts). Do not say they spent Rs. 0.",
        },
        [],
        {topic},
    )


def _history_note(ctx: ToolContext, period: Period, data: dict[str, Any]) -> None:
    start = history_start(ctx)
    if start is not None and period.start < start:
        data["history_starts"] = start.isoformat()
        data["note_history"] = "Nothing is known before history_starts."


def get_spending_summary(ctx: ToolContext, args: SpendingSummaryArgs) -> ToolResult:
    current, previous = args.resolve(ctx.today)
    if empty := _no_data(ctx, current, "spending"):
        return empty
    start = min(previous.start, current.start - dt.timedelta(days=BASELINE_DAYS))
    txns = ctx.source.list_transactions(
        ctx.user_id,
        TransactionFilter(start=start, end=min(current.end, ctx.today), counted_only=True),
    )
    s = summarize(txns, current, previous, ctx.today)
    compared_with = (
        f"the same days of {previous.label}"
        if s.comparison_basis == "same_days"
        else previous.label
    )
    data: dict[str, Any] = {
        "period": current.label,
        "from": current.start.isoformat(),
        "to": s.covered_end.isoformat(),
        "compared_with": compared_with,
        "note": "Spending excludes transfers to people, Smart Deposit savings and income.",
    }

    if args.category is not None and args.group_by != "flow":
        cat = next((c for c in s.by_category if c.category is args.category), None)
        spent = cat.spent_paisa if cat else 0
        before = cat.previous_spent_paisa if cat else 0
        pct = None if before == 0 else round((spent - before) * 100 / before, 1)
        merchants: dict[str, int] = defaultdict(int)
        for t in txns:
            if (
                t.is_spending
                and t.category is args.category
                and current.start <= t.occurred_at.date() <= s.covered_end
            ):
                merchants[t.merchant] += t.amount_paisa
        top = sorted(merchants.items(), key=lambda kv: -kv[1])[:5]
        data.update(
            {
                "category": args.category.value,
                "spent": _rs(spent),
                "transactions": cat.count if cat else 0,
                "previous_spent": _rs(before),
                "change": _change(pct),
                "share_of_all_spending": f"{cat.share_percent:g}%" if cat else "0%",
                "top_merchants": [{"merchant": untrusted(m), "spent": _rs(v)} for m, v in top],
            }
        )
        card = SpendingSummaryCard(
            period_label=current.label,
            start=current.start,
            end=s.covered_end,
            category=args.category.value,
            total_paisa=spent,
            previous_paisa=before,
            compared_with=compared_with,
            change_percent=pct,
            link=_link(
                current,
                ctx.today,
                cat.count if cat else 0,
                category=args.category.value,
                direction="debit",
            ),
        )
        return ToolResult(data, [card], {"spending"})

    data.update(
        {
            "total_spent": _rs(s.total_spent_paisa),
            "transactions": s.transaction_count,
            "previous_spent": _rs(s.previous_compare_paisa),
            "change": _change(s.change_percent),
            "income_received": _rs(s.income_paisa),
        }
    )
    biggest = next((c for c in s.by_category if c.spent_paisa > 0), None)
    if biggest:  # "where did most go?" (the eval saw the unusual list taken for this)
        data["biggest_category"] = {
            "category": biggest.category.value,
            "spent": _rs(biggest.spent_paisa),
        }
    _history_note(ctx, current, data)
    if args.group_by == "category":
        data["by_category"] = [
            {
                "category": c.category.value,
                "spent": _rs(c.spent_paisa),
                "share": f"{c.share_percent:g}%",
            }
            for c in s.by_category
            if c.spent_paisa > 0
        ][:8]
    elif args.group_by == "merchant":
        data["top_merchants"] = [
            {
                "merchant": untrusted(m.merchant),
                "category": m.category.value,
                "spent": _rs(m.spent_paisa),
                "payments": m.count,
            }
            for m in s.top_merchants
        ]
    elif args.group_by == "day":
        data["by_day"] = [
            {"date": d.date.isoformat(), "spent": _rs(d.spent_paisa)}
            for d in s.daily
            if d.spent_paisa > 0
        ]
    unusual = unusual_spending(txns, current, ctx.today)
    if unusual:
        data["unusual_spending"] = [
            {
                "category": u.category.value,
                "spent": _rs(u.current_paisa),
                "usual": _rs(int(round(u.usual_paisa / 100)) * 100),
                "times_usual": f"{u.ratio:g}x" if u.ratio else "new this period",
            }
            for u in unusual
        ]
        data["unusual_note"] = "Unusual = high compared with usual, not the biggest category."

    flow = _money_flow(txns, current.start, s.covered_end) if args.group_by == "flow" else None
    if flow:
        moved_in, moved_out = flow.money_in_paisa, flow.money_out_paisa
        data["money_in"] = _rs(moved_in)
        data["money_out"] = _rs(moved_out)
        data["money_in_by_source"] = [
            {"source": i.label, "amount": _rs(i.paisa)} for i in flow.sources if i.kind == "in"
        ]
        data["money_out_by_use"] = [
            {"use": i.label, "amount": _rs(i.paisa)} for i in flow.uses if i.kind != "balance"
        ]
        if moved_in > moved_out:
            data["left_over"] = _rs(moved_in - moved_out)
        elif moved_out > moved_in:
            data["taken_from_balance"] = _rs(moved_out - moved_in)
        data["flow_note"] = (
            "Money out here includes transfers sent and Smart Deposit. The app draws these "
            "figures as a money-flow diagram under your answer: give the totals and one or two "
            "points, not every line."
        )

    link = _link(current, ctx.today, s.transaction_count, spending_only=True)
    cards: list[BaseModel] = [
        SpendingSummaryCard(
            period_label=current.label,
            start=current.start,
            end=s.covered_end,
            total_paisa=s.total_spent_paisa,
            previous_paisa=s.previous_compare_paisa,
            compared_with=compared_with,
            change_percent=s.change_percent,
            link=link,
        )
    ]
    if args.group_by == "category" and s.total_spent_paisa > 0:
        cards.append(
            CategoryBreakdownCard(
                period_label=current.label,
                total_paisa=s.total_spent_paisa,
                items=[
                    CategoryAmount(
                        category=c.category.value,
                        spent_paisa=c.spent_paisa,
                        share_percent=c.share_percent,
                    )
                    for c in s.by_category
                    if c.spent_paisa > 0
                ],
                link=link,
            )
        )
    if flow:
        period_txns = sum(1 for t in txns if current.start <= t.occurred_at.date() <= s.covered_end)
        cards.append(
            MoneyFlowCard(
                period_label=current.label,
                flow=flow,
                link=_link(current, ctx.today, period_txns),
            )
        )
    return ToolResult(data, cards, {"spending"})


# --- get_transactions ---------------------------------------------------------------------


class TransactionsArgs(PeriodArgs):
    category: Category | None = None
    merchant: str | None = Field(None, max_length=60)
    type: TxnType | None = None
    direction: Literal["debit", "credit"] | None = None
    min_amount: float | None = Field(None, ge=0)
    max_amount: float | None = Field(None, ge=0)
    status: TxnStatus | None = None


def _txn_title(t: Transaction) -> str:
    return t.subcategory or t.category.value


def _txn_line(t: Transaction) -> dict[str, Any]:
    line: dict[str, Any] = {
        "id": t.id,
        "date": t.occurred_at.date().isoformat(),
        "merchant": untrusted(t.merchant),
        "what": _txn_title(t),
        "amount": _rs(t.amount_paisa),
        "direction": "out" if t.is_debit else "in",
        "note": untrusted(t.remarks, 60),
    }
    if t.status is not TxnStatus.SUCCESS:
        line["status"] = t.status.value
    if t.reversal_of:
        line["refund_of"] = t.reversal_of
    return line


def get_transactions(ctx: ToolContext, args: TransactionsArgs) -> ToolResult:
    current, _ = args.resolve(ctx.today)
    if empty := _no_data(ctx, current, "transactions"):
        return empty
    flt = TransactionFilter(
        start=current.start,
        end=min(current.end, ctx.today),
        category=args.category,
        merchant=args.merchant,
        type=args.type,
        direction=Direction(args.direction) if args.direction else None,
        min_paisa=_rupees_to_paisa(args.min_amount),
        max_paisa=_rupees_to_paisa(args.max_amount),
    )
    # A reversed payment failed too (then came back): "failed" finds both. Seen live: asked
    # about a failed NEA payment, status=failed missed the reversed one.
    wanted = {args.status} if args.status else None
    if args.status is TxnStatus.FAILED:
        wanted = {TxnStatus.FAILED, TxnStatus.REVERSED}
    txns = [
        t
        for t in reversed(ctx.source.list_transactions(ctx.user_id, flt))  # newest first
        if wanted is None or t.status in wanted
    ]
    # Totals count completed transactions only; the list shows every one with its status.
    debit = sum(t.amount_paisa for t in txns if t.is_debit and t.counts)
    credit = sum(t.amount_paisa for t in txns if not t.is_debit and t.counts)
    data: dict[str, Any] = {
        "period": current.label,
        "count": len(txns),
        "total_paid_out": _rs(debit),
        "total_received": _rs(credit),
        "latest": [_txn_line(t) for t in txns[:10]],
    }
    if not_done := sum(1 for t in txns if not t.counts):
        data["not_in_totals"] = (
            f"{not_done} failed, pending, reversed or refunded (status on each; "
            "get_transaction_status for details)"
        )
    if len(txns) > 10:
        data["more_not_listed"] = len(txns) - 10
    if wanted and not txns:
        # Seen live: nothing failed in the last 7 days, and the model said no money was
        # taken, while a failed payment a month earlier had been refunded. Show earlier ones.
        before = replace(flt, start=None, end=current.start - dt.timedelta(days=1))
        earlier = [
            t
            for t in reversed(ctx.source.list_transactions(ctx.user_id, before))
            if t.status in wanted
        ]
        if earlier:
            data["none_in_this_period_but_earlier"] = [_txn_line(t) for t in earlier[:3]]
    card = TransactionsPreviewCard(
        count=len(txns),
        total_debit_paisa=debit,
        total_credit_paisa=credit,
        items=[_txn_item(t) for t in txns[:5]],
        link=_link(
            current,
            ctx.today,
            len(txns),
            category=args.category.value if args.category else None,
            merchant=args.merchant,
            type=args.type.value if args.type else None,
            direction=args.direction,
            min_paisa=flt.min_paisa,
            max_paisa=flt.max_paisa,
        ),
    )
    return ToolResult(data, [card], {"transactions"})


# --- get_transaction_status -------------------------------------------------------------------


class TxnStatusArgs(BaseModel):
    transaction_id: str = Field(min_length=1, max_length=60)


def _when(t: dt.datetime) -> str:
    return f"{t:%a %d %b %Y, %H:%M}"


def _txn_item(t: Transaction) -> TransactionItem:
    return TransactionItem(
        id=t.id,
        date=t.occurred_at.date(),
        merchant=t.merchant,
        amount_paisa=t.amount_paisa,
        direction=t.direction.value,
        category=t.category.value,
        status=t.status.value,
        refund=t.reversal_of is not None,
    )


def get_transaction_status(ctx: ToolContext, args: TxnStatusArgs) -> ToolResult:
    """Where one transaction stands, and whether the time Khalti gives for it has passed.
    Times come from app/rules.py; "now" from the context."""
    t = ctx.source.get_transaction(ctx.user_id, args.transaction_id.strip())
    if t is None:
        raise ToolError("no transaction with that id: find it with get_transactions")
    data: dict[str, Any] = {
        "transaction_id": t.id,
        "status": t.status.value,
        "what": _txn_title(t),
        "merchant": untrusted(t.merchant),
        "amount": _rs(t.amount_paisa),
        "direction": "out" if t.is_debit else "in",
        "when": _when(t.occurred_at),
    }
    shown = [t]
    due: dt.datetime | None = None
    if t.reversal_of:
        data["meaning"] = "Money returned for a failed payment."
        data["refund_of"] = t.reversal_of
    elif t.status is TxnStatus.SUCCESS:
        data["meaning"] = "Completed."
    elif t.status is TxnStatus.PENDING:
        due = t.occurred_at + dt.timedelta(hours=PENDING_SETTLE_HOURS)
        data["meaning"] = "Not completed yet; the money is held until it goes through or fails."
        data["expected_by"] = _when(due)
    elif t.status is TxnStatus.FAILED:
        due = t.occurred_at + dt.timedelta(hours=REFUND_HOURS)
        data["meaning"] = "Failed: the money left the wallet and hasn't come back yet."
        data["refund_expected_by"] = _when(due)
        data["refund_rule"] = REFUND_RULES[0]
    else:  # reversed
        data["meaning"] = "Failed, and the money came back."
        after = ctx.source.list_transactions(
            ctx.user_id, TransactionFilter(start=t.occurred_at.date())
        )
        back = next((r for r in after if r.reversal_of == t.id), None)
        if back is not None:
            data["money_returned"] = {
                "amount": _rs(back.amount_paisa),
                "when": _when(back.occurred_at),
            }
            shown.append(back)
    cards: list[BaseModel] = []
    if due is not None:
        data["overdue"] = ctx.clock() > due
        if data["overdue"]:
            # Seen live: told to "offer open_app_flow flow=support", the model wrote that as
            # text instead of calling it. The support button comes from here instead.
            cards.append(_support_card(t, None))
            data["support"] = (
                "The expected time has passed. A 'Contact Khalti support' button with this "
                "transaction attached is shown under your answer: tell the user to tap it. "
                f"Khalti answers complaints within {COMPLAINT_REPLY_HOURS} hours."
            )
    debit = sum(x.amount_paisa for x in shown if x.is_debit)
    card = TransactionsPreviewCard(
        count=len(shown),
        total_debit_paisa=debit,
        total_credit_paisa=sum(x.amount_paisa for x in shown) - debit,
        items=[_txn_item(x) for x in shown],
        link=TransactionsLink(
            count=len(shown),
            filters={
                "start": t.occurred_at.date().isoformat(),
                "end": shown[-1].occurred_at.date().isoformat(),
                "merchant": t.merchant,
            },
        ),
    )
    topics = {"transactions", "app_flow"} if cards else {"transactions"}
    return ToolResult(data, [card, *cards], topics)


# --- budgets ------------------------------------------------------------------------------


class NoArgs(BaseModel):
    pass


def _level_words(level: BudgetLevel) -> str:
    return {
        BudgetLevel.OK: "on track",
        BudgetLevel.WARNING: "near the limit",
        BudgetLevel.OVER: "over the limit",
    }[level]


def get_budgets(ctx: ToolContext, _: NoArgs) -> ToolResult:
    statuses = budget_statuses(ctx.session, ctx.source, ctx.user_id, ctx.today)
    if not statuses:
        return ToolResult({"budgets": [], "note": "The user has no budgets yet."}, [], {"budgets"})
    data = {
        "budgets": [
            {
                "budget": s.category.value if s.category else "Overall (all spending)",
                "month": s.period.label,
                "limit": _rs(s.limit_paisa),
                "spent": _rs(s.spent_paisa),
                "left": _rs(max(s.remaining_paisa, 0)),
                "over_by": _rs(-s.remaining_paisa) if s.remaining_paisa < 0 else None,
                "used": f"{s.percent_used:g}%",
                "status": _level_words(s.level),
                "days_left": s.days_left,
                "can_spend_per_day": _rs(s.daily_allowance_paisa),
            }
            for s in statuses
        ]
    }
    card = BudgetProgressCard(
        items=[
            BudgetItem(
                budget_id=s.budget_id,
                category=s.category.value if s.category else None,
                period_label=s.period.label,
                limit_paisa=s.limit_paisa,
                spent_paisa=s.spent_paisa,
                percent_used=s.percent_used,
                level=s.level.value,
            )
            for s in statuses
        ]
    )
    return ToolResult(data, [card], {"budgets"})


class UpsertBudgetArgs(BaseModel):
    # Required on purpose: a missing category must never silently become the overall budget
    # (the model once dropped it for "set a food budget"). "Overall" is said explicitly.
    category: Category | Literal["Overall"]
    limit_amount: float = Field(gt=0, le=1_00_00_000)
    calendar: Literal["AD", "BS"] = "AD"

    @field_validator("category")
    @classmethod
    def _spending_only(cls, v: Category | str) -> Category | str:
        if v in NON_SPENDING:
            raise ValueError("budgets are for spending categories only")
        return v

    @property
    def budget_category(self) -> Category | None:
        """None = the overall budget."""
        return None if self.category == "Overall" else Category(self.category)


def upsert_budget(ctx: ToolContext, args: UpsertBudgetArgs) -> ToolResult:
    category = args.budget_category
    limit = _rupees_to_paisa(args.limit_amount)
    assert limit is not None  # noqa: S101
    cal = CalendarSystem(args.calendar)
    period = month_period(ctx.today, cal)
    name = category.value if category else "Overall"
    q = select(Budget).where(Budget.user_id == ctx.user_id)
    q = (
        q.where(Budget.category.is_(None))
        if category is None
        else q.where(Budget.category == category.value)
    )
    existing = ctx.session.scalar(q)
    txns = ctx.source.list_transactions(
        ctx.user_id, TransactionFilter(start=period.start, end=ctx.today, counted_only=True)
    )
    spent = spent_in_period(txns, period, category)
    status = evaluate_budget(
        limit_paisa=limit,
        spent_paisa=spent,
        period=period,
        today=ctx.today,
        category=category,
        calendar=cal,
    )
    details = [
        Detail(label="Monthly limit", value=_rs(limit)),
        Detail(label=f"Spent so far ({period.label})", value=_rs(spent)),
        Detail(
            label="Month", value="Nepali (BS) month" if cal is CalendarSystem.BS else "AD month"
        ),
    ]
    if existing is not None:
        details.insert(1, Detail(label="Current limit", value=_rs(existing.limit_paisa)))
    card = ConfirmActionCard(
        action="upsert_budget",
        title=f"{'Change' if existing else 'Set'} {name} budget",
        details=details,
        request=ApiRequest(
            method="POST",
            path="/budgets",
            body={
                "category": category.value if category else None,
                "limit_paisa": limit,
                "calendar": args.calendar,
            },
        ),
    )
    data = {
        "status": "NOT SAVED YET: waiting for the user to tap Confirm on the card",
        "budget": f"{name} (one category)" if category else "Overall (all spending)",
        "new_limit": _rs(limit),
        "current_limit": _rs(existing.limit_paisa) if existing else None,
        "spent_this_month": _rs(spent),
        "already_used_of_new_limit": f"{status.percent_used:g}%",
    }
    return ToolResult(data, [card], {"budget_proposal"})


# --- goals --------------------------------------------------------------------------------


def get_goals(ctx: ToolContext, _: NoArgs) -> ToolResult:
    goals = list(
        ctx.session.scalars(select(Goal).where(Goal.user_id == ctx.user_id).order_by(Goal.deadline))
    )
    if not goals:
        return ToolResult(
            {"goals": [], "note": "The user has no savings goals yet."}, [], {"goals"}
        )
    items, data_goals = [], []
    for g in goals:
        p = goal_progress(
            target_paisa=g.target_paisa,
            saved_paisa=g.saved_paisa,
            deadline=g.deadline,
            today=ctx.today,
        )
        items.append(
            GoalItem(
                goal_id=g.id,
                name=g.name,
                target_paisa=g.target_paisa,
                saved_paisa=g.saved_paisa,
                percent=p.percent,
                deadline=g.deadline,
                required_monthly_paisa=p.required_monthly_paisa,
                state=p.state.value,
            )
        )
        data_goals.append(
            {
                "goal_id": g.id,
                "name": untrusted(g.name),
                "target": _rs(g.target_paisa),
                "saved": _rs(g.saved_paisa),
                "progress": f"{p.percent:g}%",
                "left_to_save": _rs(p.remaining_paisa),
                "deadline": g.deadline.isoformat(),
                "months_left": p.months_left,
                "needs_per_month": _rs(p.required_monthly_paisa),
                "state": p.state.value,
            }
        )
    return ToolResult(
        {"goals": data_goals, "tip": "Smart Deposit can save the monthly amount automatically."},
        [GoalProgressCard(items=items)],
        {"goals"},
    )


class UpsertGoalArgs(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_amount: float = Field(gt=0, le=1_00_00_00_000)
    deadline: dt.date
    saved_amount: float | None = Field(None, ge=0)
    goal_id: int | None = Field(None, description="set to change an existing goal")


def upsert_goal(ctx: ToolContext, args: UpsertGoalArgs) -> ToolResult:
    if args.deadline <= ctx.today:
        raise ToolError("the deadline must be after today")
    existing = None
    if args.goal_id is not None:
        existing = ctx.session.get(Goal, args.goal_id)
        if existing is None or existing.user_id != ctx.user_id:
            raise ToolError(f"no goal with goal_id {args.goal_id}")
    target = _rupees_to_paisa(args.target_amount)
    assert target is not None  # noqa: S101
    saved = _rupees_to_paisa(args.saved_amount)
    if saved is None:
        saved = existing.saved_paisa if existing else 0
    p = goal_progress(
        target_paisa=target, saved_paisa=saved, deadline=args.deadline, today=ctx.today
    )
    body = {
        "name": args.name.strip(),
        "target_paisa": target,
        "saved_paisa": saved,
        "deadline": args.deadline.isoformat(),
    }
    request = (
        ApiRequest(method="PATCH", path=f"/goals/{existing.id}", body=body)
        if existing
        else ApiRequest(method="POST", path="/goals", body=body)
    )
    card = ConfirmActionCard(
        action="upsert_goal",
        title=f"{'Update' if existing else 'Create'} goal: {args.name.strip()}",
        details=[
            Detail(label="Target", value=_rs(target)),
            Detail(label="Saved so far", value=_rs(saved)),
            Detail(label="Deadline", value=args.deadline.strftime("%d %b %Y")),
            Detail(label="Needs per month", value=_rs(p.required_monthly_paisa)),
        ],
        request=request,
    )
    data = {
        "status": "NOT SAVED YET: waiting for the user to tap Confirm on the card",
        "goal": untrusted(args.name),
        "target": _rs(target),
        "saved": _rs(saved),
        "deadline": args.deadline.isoformat(),
        "months_left": p.months_left,
        "needs_per_month": _rs(p.required_monthly_paisa),
    }
    return ToolResult(data, [card], {"goal_proposal"})


# --- bills and forecast ---------------------------------------------------------------------


class RecurringArgs(BaseModel):
    within_days: int = Field(45, ge=1, le=120)


def get_recurring_payments(ctx: ToolContext, args: RecurringArgs) -> ToolResult:
    views = list_bills(ctx.session, ctx.bills, ctx.user_id, ctx.today, args.within_days)
    data = {
        "as_of": ctx.today.isoformat(),
        "bills": [
            {
                "merchant": untrusted(v.bill.merchant),
                "what": v.bill.subcategory or v.bill.category.value,
                "usual_amount": _rs(v.bill.usual_amount_paisa),
                "how_often": v.bill.cadence,
                "next_due": v.bill.due_date.isoformat(),
                "due": ("overdue by " if v.overdue else "in ") + f"{abs(v.days_until_due)} days",
                "last_paid": v.bill.last_paid.isoformat(),
            }
            for v in views
        ],
    }
    if not views:
        data["note"] = "No recurring payments detected in this window."
    card = BillsListCard(
        items=[
            BillItem(
                bill_id=v.id,
                merchant=v.bill.merchant,
                service=v.bill.service,
                usual_amount_paisa=v.bill.usual_amount_paisa,
                due_date=v.bill.due_date,
                days_until_due=v.days_until_due,
                overdue=v.overdue,
            )
            for v in views
        ]
    )
    return ToolResult(data, [card] if views else [], {"bills"})


class ForecastArgs(BaseModel):
    days: int | None = Field(None, ge=1, le=90, description="omit for: until the month ends")


def _projection(f: BalanceForecast) -> dict[str, Any]:
    return {
        "until": f.horizon_end.isoformat(),
        "projected_balance": _rs(f.projected_end_balance_paisa),
        "lowest_projected_balance": _rs(f.lowest_balance_paisa),
        "lowest_on": f.lowest_date.isoformat(),
        "low_balance_warning": f.below_threshold,
        "first_day_below_warning_line": f.first_below_date.isoformat()
        if f.first_below_date
        else None,
    }


def get_balance_forecast(ctx: ToolContext, args: ForecastArgs) -> ToolResult:
    """Always gives the month-end projection ("by_month_end"); with days=N, also that
    horizon ("asked_period"). Live runs showed models asked "by month end" passing days=30
    and reading the 30-day figure as the month end when it was the only one."""
    line = load_settings(ctx.session, ctx.user_id).low_balance_threshold_paisa
    month = month_end_forecast(ctx.source, ctx.user_id, ctx.today, threshold_paisa=line)
    asked = (
        balance_forecast(ctx.source, ctx.user_id, ctx.today, args.days, threshold_paisa=line)
        if args.days
        else None
    )
    f = asked or month
    data: dict[str, Any] = {
        "today": ctx.today.isoformat(),
        "balance_now": _rs(f.current_balance_paisa),
        "warning_line": _rs(f.threshold_paisa),
        "by_month_end": _projection(month),
    }
    if asked is not None:
        data["asked_period"] = {"days": args.days, **_projection(asked)}
    data |= {
        "average_everyday_spending_per_day": _rs(f.avg_daily_spend_paisa),
        "expected_bills_and_income": [
            {
                "date": i.date.isoformat(),
                "merchant": untrusted(i.merchant),
                "amount": ("+" if i.amount_paisa > 0 else "-") + _rs(abs(i.amount_paisa)),
            }
            for i in f.scheduled[:8]
        ],
        "method": "balance now + expected bills/income - average everyday spending per day",
    }
    return ToolResult(data, [], {"forecast"})


# --- help articles ----------------------------------------------------------------------------


class HelpArgs(BaseModel):
    query: str = Field(min_length=1, max_length=200)


_WORD = re.compile(r"[a-z0-9ऀ-ॿ]+")


def search_help_articles(ctx: ToolContext, args: HelpArgs) -> ToolResult:
    words = set(_WORD.findall(args.query.lower())) - {
        "how",
        "do",
        "i",
        "my",
        "the",
        "a",
        "to",
        "is",
        "can",
        "what",
        "in",
        "of",
        "ma",
    }
    scored = []
    for a in ctx.session.scalars(select(FaqArticle)):
        hay = set(_WORD.findall(f"{a.question} {a.tags}".lower()))
        score = len(words & hay)
        if score:
            scored.append((score, a))
    scored.sort(key=lambda sa: -sa[0])
    hits = [{"question": a.question, "answer": a.answer} for _, a in scored[:3]]
    data: dict[str, Any] = {"articles": hits}
    if not hits:
        data["note"] = "No matching help article."
    return ToolResult(data, [], {"help"})


# --- get_wallet_rules ------------------------------------------------------------------------

RuleTopic = Literal["limits", "balance_cap", "kyc", "security", "refunds", "fees", "all"]
_RULE_TOPICS = ("limits", "balance_cap", "kyc", "security", "refunds", "fees")


class WalletRulesArgs(BaseModel):
    topic: RuleTopic = "limits"


def _limit_rule(lim: Limit) -> str:
    return (
        f"{_rs(lim.per_txn_paisa)} per transaction, {_rs(lim.per_day_paisa)} a day, "
        f"{_rs(lim.per_month_paisa)} a month"
    )


def _use(u: LimitUse) -> dict[str, str]:
    return {
        "used_today": _rs(u.used_today_paisa),
        "left_today": _rs(u.left_today_paisa),
        "used_this_month": _rs(u.used_month_paisa),
        "left_this_month": _rs(u.left_month_paisa),
    }


def get_wallet_rules(ctx: ToolContext, args: WalletRulesArgs) -> ToolResult:
    """Khalti's rules from app/rules.py (amounts formatted here, never from the prompt), with
    the user's own usage worked out from the wallet history."""
    topics = _RULE_TOPICS if args.topic == "all" else (args.topic,)
    data: dict[str, Any] = {
        "source": SOURCE,
        "last_checked": f"{LAST_CHECKED:%d %b %Y}",
        "for": "KYC-verified users",
    }
    # The rules are help; the user's own usage and balance are their money (Settings switch).
    use = usage(ctx.source, ctx.user_id, ctx.today, ctx.offered) if ctx.can_read_money else None
    if use is None and {"limits", "balance_cap"} & set(topics):
        data["your_usage"] = NO_MONEY_ACCESS["note"]
    if "limits" in topics:
        data["limits"] = {lim.label: _limit_rule(lim) for lim in LIMITS.values()}
        data["minimum"] = (
            f"{_rs(MIN_PAYMENT_PAISA)} for any transfer or payment "
            f"({LIMITS['escrow'].label}: {_rs(ESCROW_MIN_PAISA)})"
        )
        data["no_limit"] = "No limit for " + "; ".join(NO_LIMIT_PAYMENTS)
        data["cardless_atm"] = (
            "Cash from Nabil Bank ATMs without a card, with an OTP: up to "
            f"{_rs(CARDLESS_ATM_PER_DAY_PAISA)} a day and "
            f"{_rs(CARDLESS_ATM_PER_MONTH_PAISA)} a month"
        )
        if use is not None:
            data["your_usage"] = {LIMITS[k].label: _use(use.limits[k]) for k in TRACKED} | {
                "month": f"{ctx.today:%B %Y} (AD)"
            }
            data["deposits_today"] = f"{use.deposits_today} of {DEPOSITS_PER_DAY} a day"
        data["deposits_per_day"] = f"{DEPOSITS_PER_DAY} deposits into a personal wallet a day"
        data["deposits_note"] = DEPOSIT_COUNT_NOTE
    if "balance_cap" in topics:
        data["overnight_balance_cap"] = _rs(OVERNIGHT_BALANCE_CAP_PAISA)
        data["cap_rule"] = OVERNIGHT_CAP_RULE
        if use is not None:
            over = use.over_overnight_cap_paisa
            data["balance_now"] = _rs(use.balance_paisa)
            data["over_overnight_cap"] = over > 0
            if over:
                data["over_by"] = _rs(over)
    if "kyc" in topics:
        status = kyc_status(ctx.session, ctx.user_id)
        data["kyc_rules"] = list(KYC_RULES)
        data["account_rules"] = list(ACCOUNT_RULES)
        data["your_kyc"] = status.value if status else "unknown"
    if "security" in topics:
        data["security"] = list(SECURITY_RULES)
    if "refunds" in topics:
        data["refunds_and_complaints"] = list(REFUND_RULES)
    if "fees" in topics:
        data["fees"] = FEES_NOTE
    return ToolResult(data, [], {"help"})


# --- open_app_flow -------------------------------------------------------------------------

Flow = Literal[
    "bill_payment",
    "send_money",
    "autopay",
    "smart_deposit",
    "load_money",
    "withdraw_to_bank",
    "request_money",
    "support",
    "block_wallet",
]
# Every flow that pays, sends, requests or loads money needs verified KYC first. Support and
# blocking the wallet never do: a user with a lost phone must always reach them.
_MONEY_FLOWS = frozenset(
    {
        "bill_payment",
        "send_money",
        "autopay",
        "smart_deposit",
        "load_money",
        "withdraw_to_bank",
        "request_money",
    }
)


def split_shares(total_paisa: int, people: int) -> tuple[int, int]:
    """A bill split between `people` (the requester included), in whole paisa: what each
    of the others pays, and the requester's own share, which takes any leftover paisa."""
    each = total_paisa // people
    return each, total_paisa - each * (people - 1)


def _kyc_refusal(ctx: ToolContext) -> ToolResult | None:
    status = kyc_status(ctx.session, ctx.user_id)
    if status is None or status is KycStatus.VERIFIED:
        return None
    state = "sent and being checked" if status is KycStatus.PENDING else "not started"
    return ToolResult(
        {
            "status": "NOT opened, no button is shown: the user's KYC is not verified "
            f"({state}). They can't pay, send or load money until it is. Tell them so and "
            "give the KYC steps from search_help_articles.",
            "kyc": status.value,
        },
        [],
        {"help"},
    )


def _limit_refusal(ctx: ToolContext, kind: str, amount_paisa: int) -> ToolResult | None:
    use = usage(ctx.source, ctx.user_id, ctx.today, ctx.offered).limits[kind]
    problem = check_amount(use, amount_paisa)
    if problem is None:
        return None
    lim = use.limit
    data: dict[str, Any] = {
        "status": "NOT opened, no button is shown: the amount breaks a Khalti limit. Tell the "
        "user which limit and how much is left. Never suggest splitting it, another wallet or "
        "someone else's account to get around it.",
        "amount": _rs(amount_paisa),
    }
    if problem.rule == "minimum":
        data["limit"] = f"The minimum is {_rs(lim.min_paisa)}."
        return ToolResult(data, [], {"help"})
    data["limit"] = {
        "per_transaction": f"{lim.label}: {_rs(lim.per_txn_paisa)} per transaction",
        "per_day": f"{lim.label}: {_rs(lim.per_day_paisa)} a day",
        "per_month": f"{lim.label}: {_rs(lim.per_month_paisa)} a month",
    }[problem.rule]
    # Seen live: the model worked out "Rs. 10,000 over the limit" itself, which the
    # grounding check rightly refused. The difference comes from here instead.
    data["over_by"] = _rs(amount_paisa - problem.allowed_paisa)
    data |= _use(use)
    data["most_in_one_transaction_now"] = _rs(use.most_now_paisa)
    if ctx.offered.get(kind):
        data["used_today_includes"] = (
            f"{_rs(ctx.offered[kind])} for buttons already shown in this message"
        )
    return ToolResult(data, [], {"help"})


class AppFlowArgs(BaseModel):
    flow: Flow
    service: (
        Literal["electricity", "khanepani", "internet", "tv", "data_pack", "mobile_topup"] | None
    ) = None
    amount: float | None = Field(None, gt=0)
    recipient_name: str | None = Field(None, max_length=80)
    goal_id: int | None = None
    # request_money: amount is the total; split_between counts the requester too.
    split_between: int | None = Field(None, ge=2, le=20)
    recipient_names: list[str] | None = Field(None, max_length=19)
    # support
    transaction_id: str | None = Field(None, max_length=60)
    issue: str | None = Field(None, max_length=200)

    @field_validator("recipient_names")
    @classmethod
    def _short_names(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        names = [n.strip() for n in v if n.strip()]
        if any(len(n) > 80 for n in names):
            raise ValueError("names are at most 80 characters")
        return names or None


_FLOW_TITLES = {
    "electricity": "Pay electricity bill",
    "khanepani": "Pay Khanepani bill",
    "internet": "Pay internet bill",
    "tv": "Pay TV bill",
    "data_pack": "Buy data pack",
    "mobile_topup": "Mobile topup",
}


def open_app_flow(ctx: ToolContext, args: AppFlowArgs) -> ToolResult:
    # Checked in code before any button: the model can't skip these.
    if args.flow in _MONEY_FLOWS and (refused := _kyc_refusal(ctx)):
        return refused
    amount = _rupees_to_paisa(args.amount)
    limit = FLOW_LIMITS.get(args.flow)
    if limit and amount is not None and (refused := _limit_refusal(ctx, limit, amount)):
        return refused
    prefill = AppFlowPrefill(amount_paisa=amount)
    if args.flow in ("bill_payment", "autopay"):
        if args.flow == "bill_payment" and args.service is None:
            raise ToolError("bill_payment needs a service")
        if args.service:
            bill = next(
                (
                    v.bill
                    for v in list_bills(
                        ctx.session, ctx.bills, ctx.user_id, ctx.today, 120, include_dismissed=True
                    )
                    if v.bill.service == args.service
                ),
                None,
            )
            if bill is not None:
                prefill.biller_name = bill.merchant
                if prefill.amount_paisa is None and args.flow == "bill_payment":
                    prefill.amount_paisa = bill.usual_amount_paisa
        title = (
            _FLOW_TITLES.get(args.service or "", "Pay a bill")
            if args.flow == "bill_payment"
            else "Set up Autopay"
        )
    elif args.flow == "send_money":
        prefill.recipient_name = args.recipient_name
        title = f"Send money{' to ' + args.recipient_name if args.recipient_name else ''}"
    elif args.flow == "request_money":
        return _request_money(ctx, args, amount)
    elif args.flow == "support":
        return _support(ctx, args)
    elif args.flow == "block_wallet":
        return _flow_result(
            OpenAppFlowCard(
                flow="block_wallet",
                title="Block my wallet",
                prefill=prefill,
                note="Opens Khalti's security screen; you confirm there.",
            ),
            {
                # Seen live: "Your wallet is blocked" before the user had tapped anything.
                "wallet": "NOT blocked yet: the user blocks it in Khalti's screen after "
                "tapping the button. Never say it is blocked.",
                "next_step": "Then give the reporting steps from search_help_articles.",
                "report_rule": SECURITY_RULES[1],
            },
            money=False,
        )
    elif args.flow in ("load_money", "withdraw_to_bank"):
        title = "Load money from bank" if args.flow == "load_money" else "Withdraw to bank"
        extra: dict[str, Any] = {}
        balance = ctx.source.get_balance(ctx.user_id)
        if args.flow == "load_money" and amount and balance + amount > OVERNIGHT_BALANCE_CAP_PAISA:
            extra["cap_note"] = (
                f"After loading, the balance would be {_rs(balance + amount)}, above the "
                f"{_rs(OVERNIGHT_BALANCE_CAP_PAISA)} overnight cap: "
                + OVERNIGHT_CAP_RULE[0].lower()
                + OVERNIGHT_CAP_RULE[1:]
            )
        card = OpenAppFlowCard(flow=args.flow, title=title, prefill=prefill)
        if limit and amount is not None:
            ctx.offered[limit] = ctx.offered.get(limit, 0) + amount
        return _flow_result(card, extra)
    else:
        title = "Automate with Smart Deposit"
        if args.goal_id is not None:
            g = ctx.session.get(Goal, args.goal_id)
            if g is not None and g.user_id == ctx.user_id:
                p = goal_progress(
                    target_paisa=g.target_paisa,
                    saved_paisa=g.saved_paisa,
                    deadline=g.deadline,
                    today=ctx.today,
                )
                prefill.goal_name = g.name
                prefill.monthly_amount_paisa = p.required_monthly_paisa
    card = OpenAppFlowCard(flow=args.flow, service=args.service, title=title, prefill=prefill)
    if limit and amount is not None:
        ctx.offered[limit] = ctx.offered.get(limit, 0) + amount
    return _flow_result(card, {})


def _flow_result(card: OpenAppFlowCard, extra: dict[str, Any], *, money: bool = True) -> ToolResult:
    status = "A button is shown under your answer; nothing has opened yet. Tell the user to tap it."
    if money:
        status += " NOTHING has been paid or sent: they finish in Khalti with their MPIN."
    data: dict[str, Any] = {"status": status, "button": card.title}
    if card.prefill.amount_paisa:
        data["prefilled_amount"] = _rs(card.prefill.amount_paisa)
    return ToolResult(data | extra, [card], {"app_flow"})


def _request_money(ctx: ToolContext, args: AppFlowArgs, total: int | None) -> ToolResult:
    """Request money, or split a bill: the shares are worked out here, never by the model."""
    names = args.recipient_names or ([args.recipient_name] if args.recipient_name else [])
    people = args.split_between
    if people is None:  # no split: the amount from each person named
        prefill = AppFlowPrefill(amount_paisa=total, recipient_name=names[0] if names else None)
        if len(names) > 1 and total is not None:
            prefill.recipient_name = None
            prefill.shares = [RequestShare(name=n, amount_paisa=total) for n in names]
        title = f"Request money{' from ' + names[0] if len(names) == 1 else ''}"
        return _flow_result(
            OpenAppFlowCard(flow="request_money", title=title, prefill=prefill, note=_ASK_NOTE),
            {"requests_to": [untrusted(n) for n in names]} if names else {},
            money=False,
        )
    if total is None:
        raise ToolError("request_money with split_between needs amount (the total)")
    if len(names) > people - 1:
        raise ToolError(f"{len(names)} names but only {people - 1} others to split with")
    each, mine = split_shares(total, people)
    if each < MIN_PAYMENT_PAISA:
        return ToolResult(
            {
                "status": "NOT opened, no button is shown: each share would be under the minimum.",
                "each_share": _rs(each),
                "limit": f"The minimum is {_rs(MIN_PAYMENT_PAISA)}.",
            },
            [],
            {"help"},
        )
    others = [names[i] if i < len(names) else f"Person {i + 1}" for i in range(people - 1)]
    shares = [RequestShare(name=n, amount_paisa=each) for n in others]
    prefill = AppFlowPrefill(
        amount_paisa=each,
        total_paisa=total,
        split_between=people,
        shares=shares,
        your_share_paisa=mine,
    )
    card = OpenAppFlowCard(
        flow="request_money", title="Split the bill", prefill=prefill, note=_ASK_NOTE
    )
    return _flow_result(
        card,
        {
            "total": _rs(total),
            "split_between": f"{people} people, you included",
            "each_other_person_pays": _rs(each),
            "your_share": _rs(mine),
            "requests_to": [untrusted(n) for n in others],
            # Seen live: "tap Split the bill" with no figure. The share is the key figure.
            "say": "Give the share each person pays, then tell the user to tap the button.",
        },
        money=False,
    )


_ASK_NOTE = "You'll check and send the request in Khalti."


def _support_card(t: Transaction | None, issue: str | None) -> OpenAppFlowCard:
    prefill = AppFlowPrefill(issue=issue.strip() if issue else None)
    note = "Opens Khalti support."
    if t is not None:
        prefill.transaction_id = t.id
        prefill.transaction_label = (
            f"{t.merchant} · {_rs(t.amount_paisa)} · {t.occurred_at:%d %b %Y} · {t.status.value}"
        )
        note = "Opens Khalti support with this transaction attached."
    return OpenAppFlowCard(
        flow="support", title="Contact Khalti support", prefill=prefill, note=note
    )


def _support(ctx: ToolContext, args: AppFlowArgs) -> ToolResult:
    t = None
    if args.transaction_id and ctx.can_read_money:  # attaching one reads the history
        t = ctx.source.get_transaction(ctx.user_id, args.transaction_id.strip())
        if t is None:
            raise ToolError("no transaction with that id: find it with get_transactions")
    card = _support_card(t, args.issue)
    prefill = card.prefill
    return _flow_result(
        card,
        {
            "complaint_time": f"Khalti answers complaints within {COMPLAINT_REPLY_HOURS} hours.",
            "transaction_attached": prefill.transaction_id,
        },
        money=False,
    )


# --- registry and JSON schemas for the model ------------------------------------------------


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    run: Callable[[ToolContext, Any], ToolResult]
    parameters: dict[str, Any]


def _period_props() -> dict[str, Any]:
    return {
        "period": {"type": "string", "enum": list(PeriodPreset.__args__)},
        "month": {"type": "string", "description": "YYYY-MM (period=month)"},
        "calendar": {"type": "string", "enum": ["AD", "BS"]},
        "start": {"type": "string", "description": "YYYY-MM-DD (period=custom)"},
        "end": {"type": "string", "description": "YYYY-MM-DD (period=custom)"},
    }


def _obj(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    spec: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        spec["required"] = required
    return spec


# Descriptions are kept short on purpose: every request carries them, and the Groq free tier
# allows 8,000 tokens per minute per model.
TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool(
            "get_spending_summary",
            "Spending total vs previous period, by category/merchant/day, unusual spending. "
            "category= focuses on one category. group_by=flow (no category): money in by "
            "source and out by use, for money flow / where money came from and went.",
            SpendingSummaryArgs,
            get_spending_summary,
            _obj(
                {
                    **_period_props(),
                    "group_by": {
                        "type": "string",
                        "enum": ["category", "merchant", "day", "flow"],
                    },
                    "category": {"type": "string", "enum": SPENDING_CATEGORIES},
                }
            ),
        ),
        Tool(
            "get_transactions",
            "Transactions for a period: count, totals, latest ten with ids. type remittance "
            "= money from abroad; transfer = to/from people. status finds failed/pending/reversed.",
            TransactionsArgs,
            get_transactions,
            _obj(
                {
                    **_period_props(),
                    "category": {"type": "string", "enum": CATEGORY_VALUES},
                    "merchant": {"type": "string"},
                    "type": {"type": "string", "enum": [t.value for t in TxnType]},
                    "direction": {"type": "string", "enum": ["debit", "credit"]},
                    "min_amount": {"type": "number"},
                    "max_amount": {"type": "number"},
                    "status": {"type": "string", "enum": [s.value for s in TxnStatus]},
                }
            ),
        ),
        Tool(
            "get_transaction_status",
            "One transaction's status (failed, pending, reversed), refund and expected "
            "time, and whether it is overdue.",
            TxnStatusArgs,
            get_transaction_status,
            _obj({"transaction_id": {"type": "string"}}, ["transaction_id"]),
        ),
        Tool("get_budgets", "Monthly budgets: limit, spent, left.", NoArgs, get_budgets, _obj({})),
        Tool(
            "upsert_budget",
            "PROPOSE a monthly budget for one category, or category Overall for all "
            "spending. Saved only when the user taps Confirm.",
            UpsertBudgetArgs,
            upsert_budget,
            _obj(
                {
                    "category": {"type": "string", "enum": [*SPENDING_CATEGORIES, "Overall"]},
                    "limit_amount": {"type": "number"},
                    "calendar": {"type": "string", "enum": ["AD", "BS"]},
                },
                ["category", "limit_amount"],
            ),
        ),
        Tool(
            "get_goals",
            "Savings goals: progress, monthly saving needed.",
            NoArgs,
            get_goals,
            _obj({}),
        ),
        Tool(
            "upsert_goal",
            "PROPOSE a savings goal (goal_id to change one). Saved only when the user taps "
            "Confirm.",
            UpsertGoalArgs,
            upsert_goal,
            _obj(
                {
                    "name": {"type": "string"},
                    "target_amount": {"type": "number"},
                    "deadline": {"type": "string", "description": "YYYY-MM-DD"},
                    "saved_amount": {"type": "number"},
                    "goal_id": {"type": "integer"},
                },
                ["name", "target_amount", "deadline"],
            ),
        ),
        Tool(
            "get_recurring_payments",
            "Recurring bills/subscriptions: usual amount, next due.",
            RecurringArgs,
            get_recurring_payments,
            _obj({"within_days": {"type": "integer"}}),
        ),
        Tool(
            "get_balance_forecast",
            "Projected balance: always to this month's end; days=N adds N days ahead.",
            ForecastArgs,
            get_balance_forecast,
            _obj({"days": {"type": "integer"}}),
        ),
        Tool(
            "search_help_articles",
            "Khalti help articles: how-to, and facts about Khalti (services, the company, "
            "contacts, Super Wallet, IME Pay).",
            HelpArgs,
            search_help_articles,
            _obj(
                {"query": {"type": "string", "description": "English keywords, e.g. load money"}},
                ["query"],
            ),
        ),
        Tool(
            "get_wallet_rules",
            "Khalti's rules: transaction limits with the user's use today/this month and "
            "what's left, overnight balance cap, KYC, security, refund and complaint times, "
            "fees.",
            WalletRulesArgs,
            get_wallet_rules,
            _obj({"topic": {"type": "string", "enum": list(RuleTopic.__args__)}}),
        ),
        Tool(
            "open_app_flow",
            "Button that opens Khalti's own screen pre-filled: pay bill, send/request/load "
            "money, withdraw to bank, Autopay, Smart Deposit, support (to reach a person), "
            "block wallet. Never moves money. Refuses amounts over Khalti's limits.",
            AppFlowArgs,
            open_app_flow,
            _obj(
                {
                    "flow": {"type": "string", "enum": list(Flow.__args__)},
                    "service": {"type": "string", "enum": SERVICES},
                    "amount": {"type": "number"},
                    "recipient_name": {"type": "string"},
                    "goal_id": {"type": "integer"},
                    "split_between": {"type": "integer", "description": "people, you too"},
                    "recipient_names": {"type": "array", "items": {"type": "string"}},
                    "transaction_id": {"type": "string"},
                    "issue": {"type": "string"},
                },
                ["flow"],
            ),
        ),
    ]
}


def openai_tool_specs() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
        }
        for t in TOOLS.values()
    ]


def run_tool(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> ToolResult:
    """Validate and run. Raises ToolError for anything the model should correct."""
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolError(f"unknown tool {name}")
    try:
        args = tool.args_model.model_validate(arguments)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}" for e in exc.errors()
        )
        raise ToolError(f"invalid arguments: {problems}") from exc
    if not ctx.can_read_money and _reads_money(name, args):
        return ToolResult(dict(NO_MONEY_ACCESS), [], {"help"})
    return tool.run(ctx, args)


# Tools that read the user's money. With "Let O-Kay read my transactions" off in Settings they
# return NO_MONEY_ACCESS instead, and O-Kay answers help questions only. get_wallet_rules
# still gives the rules (without the user's usage); support and blocking the wallet still
# work, so a user with a lost phone always reaches them.
MONEY_TOOLS = frozenset(
    {
        "get_spending_summary",
        "get_transactions",
        "get_transaction_status",
        "get_budgets",
        "upsert_budget",
        "get_goals",
        "upsert_goal",
        "get_recurring_payments",
        "get_balance_forecast",
    }
)
NO_MONEY_ACCESS = {
    "note": "The user turned off 'Let O-Kay read my transactions' in Settings, so O-Kay "
    "can't see their money now. Say so, and that they can turn it back on in Settings. "
    "Answer only help questions."
}


def _reads_money(name: str, args: BaseModel) -> bool:
    if name == "open_app_flow":
        return getattr(args, "flow", None) not in ("support", "block_wallet")
    return name in MONEY_TOOLS


def today_line(today: dt.date) -> str:
    return f"{today:%A %d %B %Y} ({to_bs_string(today)} BS)"
