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
from dataclasses import dataclass, field
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
    GoalItem,
    GoalProgressCard,
    OpenAppFlowCard,
    SpendingSummaryCard,
    TransactionItem,
    TransactionsLink,
    TransactionsPreviewCard,
)
from app.ai.safety import untrusted
from app.domain import NON_SPENDING, Category, Direction, Transaction, TxnType
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
from app.services.bills import list_bills
from app.services.budgets import BudgetLevel, budget_statuses, evaluate_budget, spent_in_period
from app.services.forecast import balance_forecast, month_end_forecast
from app.services.goals import goal_progress
from app.services.insights import BASELINE_DAYS, summarize, unusual_spending
from app.sources.base import BillSource, TransactionFilter, TransactionSource


@dataclass
class ToolContext:
    session: Session
    source: TransactionSource
    bills: BillSource
    user_id: str
    today: dt.date


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
    group_by: Literal["category", "merchant", "day"] = "category"
    category: Category | None = None


def get_spending_summary(ctx: ToolContext, args: SpendingSummaryArgs) -> ToolResult:
    current, previous = args.resolve(ctx.today)
    start = min(previous.start, current.start - dt.timedelta(days=BASELINE_DAYS))
    txns = ctx.source.list_transactions(
        ctx.user_id, TransactionFilter(start=start, end=min(current.end, ctx.today))
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

    if args.category is not None:
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
    else:
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
    return ToolResult(data, cards, {"spending"})


# --- get_transactions ---------------------------------------------------------------------


class TransactionsArgs(PeriodArgs):
    category: Category | None = None
    merchant: str | None = Field(None, max_length=60)
    type: TxnType | None = None
    direction: Literal["debit", "credit"] | None = None
    min_amount: float | None = Field(None, ge=0)
    max_amount: float | None = Field(None, ge=0)


def _txn_title(t: Transaction) -> str:
    return t.subcategory or t.category.value


def get_transactions(ctx: ToolContext, args: TransactionsArgs) -> ToolResult:
    current, _ = args.resolve(ctx.today)
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
    txns = list(reversed(ctx.source.list_transactions(ctx.user_id, flt)))  # newest first
    debit = sum(t.amount_paisa for t in txns if t.is_debit)
    credit = sum(t.amount_paisa for t in txns if not t.is_debit)
    data = {
        "period": current.label,
        "count": len(txns),
        "total_paid_out": _rs(debit),
        "total_received": _rs(credit),
        "latest": [
            {
                "date": t.occurred_at.date().isoformat(),
                "merchant": untrusted(t.merchant),
                "what": _txn_title(t),
                "amount": _rs(t.amount_paisa),
                "direction": "out" if t.is_debit else "in",
                "note": untrusted(t.remarks, 60),
            }
            for t in txns[:10]
        ],
    }
    if len(txns) > 10:
        data["more_not_listed"] = len(txns) - 10
    card = TransactionsPreviewCard(
        count=len(txns),
        total_debit_paisa=debit,
        total_credit_paisa=credit,
        items=[
            TransactionItem(
                id=t.id,
                date=t.occurred_at.date(),
                merchant=t.merchant,
                amount_paisa=t.amount_paisa,
                direction=t.direction.value,
                category=t.category.value,
            )
            for t in txns[:5]
        ],
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
    category: Category | None = Field(None, description="null = overall budget")
    limit_amount: float = Field(gt=0, le=1_00_00_000)
    calendar: Literal["AD", "BS"] = "AD"

    @field_validator("category")
    @classmethod
    def _spending_only(cls, v: Category | None) -> Category | None:
        if v in NON_SPENDING:
            raise ValueError("budgets are for spending categories only")
        return v


def upsert_budget(ctx: ToolContext, args: UpsertBudgetArgs) -> ToolResult:
    limit = _rupees_to_paisa(args.limit_amount)
    assert limit is not None  # noqa: S101
    cal = CalendarSystem(args.calendar)
    period = month_period(ctx.today, cal)
    name = args.category.value if args.category else "Overall"
    q = select(Budget).where(Budget.user_id == ctx.user_id)
    q = (
        q.where(Budget.category.is_(None))
        if args.category is None
        else q.where(Budget.category == args.category.value)
    )
    existing = ctx.session.scalar(q)
    txns = ctx.source.list_transactions(
        ctx.user_id, TransactionFilter(start=period.start, end=ctx.today)
    )
    spent = spent_in_period(txns, period, args.category)
    status = evaluate_budget(
        limit_paisa=limit,
        spent_paisa=spent,
        period=period,
        today=ctx.today,
        category=args.category,
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
                "category": args.category.value if args.category else None,
                "limit_paisa": limit,
                "calendar": args.calendar,
            },
        ),
    )
    data = {
        "status": "NOT SAVED YET: waiting for the user to tap Confirm on the card",
        "budget": name,
        "new_limit": _rs(limit),
        "current_limit": _rs(existing.limit_paisa) if existing else None,
        "spent_this_month": _rs(spent),
        "would_be_used": f"{status.percent_used:g}%",
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


def get_balance_forecast(ctx: ToolContext, args: ForecastArgs) -> ToolResult:
    f = (
        balance_forecast(ctx.source, ctx.user_id, ctx.today, args.days)
        if args.days
        else month_end_forecast(ctx.source, ctx.user_id, ctx.today)
    )
    data = {
        "today": ctx.today.isoformat(),
        "until": f.horizon_end.isoformat(),
        "balance_now": _rs(f.current_balance_paisa),
        "projected_balance_at_end": _rs(f.projected_end_balance_paisa),
        "lowest_projected_balance": _rs(f.lowest_balance_paisa),
        "lowest_on": f.lowest_date.isoformat(),
        "low_balance_warning": f.below_threshold,
        "warning_line": _rs(f.threshold_paisa),
        "first_day_below_warning_line": f.first_below_date.isoformat()
        if f.first_below_date
        else None,
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


# --- open_app_flow -------------------------------------------------------------------------


class AppFlowArgs(BaseModel):
    flow: Literal["bill_payment", "send_money", "autopay", "smart_deposit"]
    service: (
        Literal["electricity", "khanepani", "internet", "tv", "data_pack", "mobile_topup"] | None
    ) = None
    amount: float | None = Field(None, gt=0)
    recipient_name: str | None = Field(None, max_length=80)
    goal_id: int | None = None


_FLOW_TITLES = {
    "electricity": "Pay electricity bill",
    "khanepani": "Pay Khanepani bill",
    "internet": "Pay internet bill",
    "tv": "Pay TV bill",
    "data_pack": "Buy data pack",
    "mobile_topup": "Mobile topup",
}


def open_app_flow(ctx: ToolContext, args: AppFlowArgs) -> ToolResult:
    prefill = AppFlowPrefill(amount_paisa=_rupees_to_paisa(args.amount))
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
    data = {
        "status": "A button was shown. NOTHING has been paid or sent: the user finishes in "
        "the Khalti app with their MPIN.",
        "button": title,
        "prefilled_amount": _rs(prefill.amount_paisa) if prefill.amount_paisa else None,
    }
    return ToolResult(data, [card], {"app_flow"})


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
        "period": {
            "type": "string",
            "enum": list(PeriodPreset.__args__),
            "description": "Pick a preset. 'month' needs month; 'custom' needs start/end.",
        },
        "month": {"type": "string", "description": "YYYY-MM, in the chosen calendar"},
        "calendar": {
            "type": "string",
            "enum": ["AD", "BS"],
            "description": "BS for Nepali months like Kartik 2083",
        },
        "start": {"type": "string", "description": "YYYY-MM-DD (custom period)"},
        "end": {"type": "string", "description": "YYYY-MM-DD (custom period)"},
    }


def _obj(props: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": props,
        "required": required or [],
        "additionalProperties": False,
    }


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool(
            "get_spending_summary",
            "Total spending for a period with the comparison to the previous period, broken down "
            "by category, merchant or day, plus unusual spending. Pass category to focus on one "
            "category (e.g. food).",
            SpendingSummaryArgs,
            get_spending_summary,
            _obj(
                {
                    **_period_props(),
                    "group_by": {"type": "string", "enum": ["category", "merchant", "day"]},
                    "category": {"type": "string", "enum": SPENDING_CATEGORIES},
                }
            ),
        ),
        Tool(
            "get_transactions",
            "List the user's transactions for a period, optionally filtered. Returns the count, "
            "totals and the latest ten.",
            TransactionsArgs,
            get_transactions,
            _obj(
                {
                    **_period_props(),
                    "category": {"type": "string", "enum": CATEGORY_VALUES},
                    "merchant": {
                        "type": "string",
                        "description": "part of the merchant/person name",
                    },
                    "type": {"type": "string", "enum": [t.value for t in TxnType]},
                    "direction": {"type": "string", "enum": ["debit", "credit"]},
                    "min_amount": {"type": "number", "description": "rupees"},
                    "max_amount": {"type": "number", "description": "rupees"},
                }
            ),
        ),
        Tool(
            "get_budgets",
            "The user's monthly budgets with how much is spent and left.",
            NoArgs,
            get_budgets,
            _obj({}),
        ),
        Tool(
            "upsert_budget",
            "PROPOSE creating or changing a monthly budget. Shows a Confirm card; nothing is saved "
            "until the user taps Confirm.",
            UpsertBudgetArgs,
            upsert_budget,
            _obj(
                {
                    "category": {
                        "type": ["string", "null"],
                        "enum": [*SPENDING_CATEGORIES, None],
                        "description": "null for an overall budget",
                    },
                    "limit_amount": {"type": "number", "description": "monthly limit in rupees"},
                    "calendar": {"type": "string", "enum": ["AD", "BS"]},
                },
                ["limit_amount"],
            ),
        ),
        Tool(
            "get_goals",
            "The user's savings goals with progress and the monthly saving needed.",
            NoArgs,
            get_goals,
            _obj({}),
        ),
        Tool(
            "upsert_goal",
            "PROPOSE creating or updating a savings goal. Shows a Confirm card; nothing is saved "
            "until the user taps Confirm.",
            UpsertGoalArgs,
            upsert_goal,
            _obj(
                {
                    "name": {"type": "string"},
                    "target_amount": {"type": "number", "description": "rupees"},
                    "deadline": {"type": "string", "description": "YYYY-MM-DD"},
                    "saved_amount": {"type": "number", "description": "rupees already saved"},
                    "goal_id": {"type": "integer", "description": "to update an existing goal"},
                },
                ["name", "target_amount", "deadline"],
            ),
        ),
        Tool(
            "get_recurring_payments",
            "Detected recurring bills and subscriptions with usual amount and next due date.",
            RecurringArgs,
            get_recurring_payments,
            _obj({"within_days": {"type": "integer", "description": "default 45"}}),
        ),
        Tool(
            "get_balance_forecast",
            "Projected wallet balance: until the end of this month by default, or for N days. "
            "Warns if it may drop below Rs. 1,000.",
            ForecastArgs,
            get_balance_forecast,
            _obj({"days": {"type": "integer", "description": "1-90; omit for month end"}}),
        ),
        Tool(
            "search_help_articles",
            "Search Khalti help articles (how to load money, pay bills, reset MPIN, KYC...).",
            HelpArgs,
            search_help_articles,
            _obj({"query": {"type": "string"}}, ["query"]),
        ),
        Tool(
            "open_app_flow",
            "Show a button that opens Khalti's own screen, pre-filled: pay a bill, send money, "
            "set up Autopay or Smart Deposit. The assistant never moves money itself.",
            AppFlowArgs,
            open_app_flow,
            _obj(
                {
                    "flow": {
                        "type": "string",
                        "enum": ["bill_payment", "send_money", "autopay", "smart_deposit"],
                    },
                    "service": {"type": "string", "enum": SERVICES},
                    "amount": {"type": "number", "description": "rupees"},
                    "recipient_name": {"type": "string"},
                    "goal_id": {"type": "integer"},
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
    return tool.run(ctx, args)


def today_line(today: dt.date) -> str:
    return f"{today:%A %d %B %Y} ({to_bs_string(today)} BS)"
