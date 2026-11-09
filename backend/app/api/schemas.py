"""API request/response models: the public contract (see /openapi.json).

Conventions
- Money: integer paisa in fields ending `_paisa` (Rs. 1 = 100). The app formats for display.
- Dates: ISO `YYYY-MM-DD` (AD). Timestamps: ISO with the Nepal offset, e.g. `...T14:05:00+05:45`.
- Periods: `{start, end, label, days}`, both ends inclusive.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain import Category, CategorySource, Direction, Transaction, TxnType
from app.periods import NPT, CalendarSystem, Period
from app.services.bills import BillStatus, BillView
from app.services.budgets import BudgetLevel, BudgetStatus
from app.services.forecast import BalanceForecast
from app.services.goals import GoalProgress, GoalState
from app.services.insights import Highlight, Severity, SpendingSummary, UnusualSpend
from app.sources.base import SmartDepositPlan

MAX_PAISA = 1_000_000_000_00  # Rs. 100 crore: a sanity cap for user-entered amounts


class PeriodOut(BaseModel):
    start: dt.date
    end: dt.date
    label: str
    days: int

    @classmethod
    def of(cls, p: Period) -> PeriodOut:
        return cls(start=p.start, end=p.end, label=p.label, days=p.days)


# --- user / meta ---------------------------------------------------------------------------


class MeOut(BaseModel):
    id: str
    name: str
    balance_paisa: int
    balance_hidden: bool = Field(description="If true, mask amounts until the user taps them.")


class CategoryInfo(BaseModel):
    name: Category
    subcategories: list[str]
    counts_as_spending: bool


# --- transactions --------------------------------------------------------------------------


class TransactionOut(BaseModel):
    id: str
    occurred_at: dt.datetime
    type: TxnType
    direction: Direction
    amount_paisa: int
    merchant: str
    service: str | None
    reference: str | None
    counterparty_account: str | None
    remarks: str | None
    balance_after_paisa: int | None
    category: Category
    subcategory: str | None
    category_source: CategorySource

    @classmethod
    def of(cls, t: Transaction) -> TransactionOut:
        return cls(
            id=t.id,
            occurred_at=t.occurred_at.replace(tzinfo=NPT),
            type=t.type,
            direction=t.direction,
            amount_paisa=t.amount_paisa,
            merchant=t.merchant,
            service=t.service,
            reference=t.reference,
            counterparty_account=t.counterparty_account,
            remarks=t.remarks,
            balance_after_paisa=t.balance_after_paisa,
            category=t.category,
            subcategory=t.subcategory,
            category_source=t.category_source,
        )


class TransactionPage(BaseModel):
    items: list[TransactionOut] = Field(description="Newest first.")
    total: int = Field(description="Matching transactions before paging.")
    total_debit_paisa: int
    total_credit_paisa: int
    limit: int
    offset: int
    start: dt.date | None
    end: dt.date | None


class RecategorizeIn(BaseModel):
    category: Category
    subcategory: str | None = None
    apply_to_merchant: bool = Field(
        False, description="Also change every past and future transaction from this merchant."
    )


class RecategorizeOut(BaseModel):
    transaction: TransactionOut
    updated_ids: list[str]
    applied_to_merchant: bool


# --- insights ------------------------------------------------------------------------------


class CategorySpendOut(BaseModel):
    category: Category
    spent_paisa: int
    count: int
    share_percent: float
    previous_spent_paisa: int


class MerchantSpendOut(BaseModel):
    merchant: str
    category: Category
    spent_paisa: int
    count: int


class DaySpendOut(BaseModel):
    date: dt.date
    spent_paisa: int


class SpendingSummaryOut(BaseModel):
    period: PeriodOut
    previous_period: PeriodOut
    in_progress: bool
    covered_end: dt.date
    total_spent_paisa: int
    previous_total_spent_paisa: int
    previous_compare_paisa: int
    comparison_basis: Literal["same_days", "full_period"]
    change_percent: float | None
    income_paisa: int
    money_in_paisa: int
    transaction_count: int
    by_category: list[CategorySpendOut]
    daily: list[DaySpendOut]
    top_merchants: list[MerchantSpendOut]

    @classmethod
    def of(cls, s: SpendingSummary) -> SpendingSummaryOut:
        return cls(
            period=PeriodOut.of(s.period),
            previous_period=PeriodOut.of(s.previous),
            in_progress=s.in_progress,
            covered_end=s.covered_end,
            total_spent_paisa=s.total_spent_paisa,
            previous_total_spent_paisa=s.previous_total_spent_paisa,
            previous_compare_paisa=s.previous_compare_paisa,
            comparison_basis=s.comparison_basis,  # type: ignore[arg-type]
            change_percent=s.change_percent,
            income_paisa=s.income_paisa,
            money_in_paisa=s.money_in_paisa,
            transaction_count=s.transaction_count,
            by_category=[CategorySpendOut(**_asdict(c)) for c in s.by_category],
            daily=[DaySpendOut(**_asdict(d)) for d in s.daily],
            top_merchants=[MerchantSpendOut(**_asdict(m)) for m in s.top_merchants],
        )


class UnusualSpendOut(BaseModel):
    category: Category
    current_paisa: int
    usual_paisa: int
    ratio: float | None

    @classmethod
    def of(cls, u: UnusualSpend) -> UnusualSpendOut:
        return cls(**_asdict(u))


class HighlightOut(BaseModel):
    kind: str
    severity: Severity
    message: str = Field(description="English default text; `data` holds the numbers.")
    data: dict[str, Any]

    @classmethod
    def of(cls, h: Highlight) -> HighlightOut:
        return cls(kind=h.kind, severity=h.severity, message=h.message, data=h.data)


class ScheduledItemOut(BaseModel):
    date: dt.date
    merchant: str
    category: Category
    amount_paisa: int = Field(description="Signed: negative = money out.")


class ForecastPointOut(BaseModel):
    date: dt.date
    balance_paisa: int


class ForecastOut(BaseModel):
    as_of: dt.date
    horizon_end: dt.date
    current_balance_paisa: int
    avg_daily_spend_paisa: int
    lookback_days: int
    projected_end_balance_paisa: int
    lowest_balance_paisa: int
    lowest_date: dt.date
    threshold_paisa: int
    below_threshold: bool
    first_below_date: dt.date | None
    scheduled: list[ScheduledItemOut]
    points: list[ForecastPointOut]

    @classmethod
    def of(cls, f: BalanceForecast) -> ForecastOut:
        return cls(
            as_of=f.as_of,
            horizon_end=f.horizon_end,
            current_balance_paisa=f.current_balance_paisa,
            avg_daily_spend_paisa=f.avg_daily_spend_paisa,
            lookback_days=f.lookback_days,
            projected_end_balance_paisa=f.projected_end_balance_paisa,
            lowest_balance_paisa=f.lowest_balance_paisa,
            lowest_date=f.lowest_date,
            threshold_paisa=f.threshold_paisa,
            below_threshold=f.below_threshold,
            first_below_date=f.first_below_date,
            scheduled=[
                ScheduledItemOut(
                    date=i.date,
                    merchant=i.merchant,
                    category=i.category,
                    amount_paisa=i.amount_paisa,
                )
                for i in f.scheduled
            ],
            points=[ForecastPointOut(date=p.date, balance_paisa=p.balance_paisa) for p in f.points],
        )


class DashboardOut(BaseModel):
    summary: SpendingSummaryOut
    unusual: list[UnusualSpendOut]
    highlights: list[HighlightOut]
    forecast: ForecastOut | None = Field(description="Only for the period in progress.")


# --- budgets -------------------------------------------------------------------------------


class BudgetIn(BaseModel):
    category: Category | None = Field(None, description="null = overall budget")
    limit_paisa: int = Field(gt=0, le=MAX_PAISA)
    calendar: CalendarSystem = CalendarSystem.AD


class BudgetPatch(BaseModel):
    limit_paisa: int | None = Field(None, gt=0, le=MAX_PAISA)
    calendar: CalendarSystem | None = None


class BudgetOut(BaseModel):
    id: int
    category: Category | None
    calendar: CalendarSystem
    period: PeriodOut
    limit_paisa: int
    spent_paisa: int
    remaining_paisa: int
    percent_used: float
    level: BudgetLevel = Field(
        description="ok < 80% (green), warning 80-100% (amber), over > 100% (red)"
    )
    alerts_reached: list[int]
    days_left: int
    daily_allowance_paisa: int
    projected_spend_paisa: int

    @classmethod
    def of(cls, b: BudgetStatus) -> BudgetOut:
        if b.budget_id is None:
            raise ValueError("budget status without an id")
        return cls(
            id=b.budget_id,
            category=b.category,
            calendar=b.calendar,
            period=PeriodOut.of(b.period),
            limit_paisa=b.limit_paisa,
            spent_paisa=b.spent_paisa,
            remaining_paisa=b.remaining_paisa,
            percent_used=b.percent_used,
            level=b.level,
            alerts_reached=list(b.alerts_reached),
            days_left=b.days_left,
            daily_allowance_paisa=b.daily_allowance_paisa,
            projected_spend_paisa=b.projected_spend_paisa,
        )


# --- goals ---------------------------------------------------------------------------------


class GoalIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_paisa: int = Field(gt=0, le=MAX_PAISA)
    saved_paisa: int = Field(0, ge=0, le=MAX_PAISA)
    deadline: dt.date


class GoalPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    target_paisa: int | None = Field(None, gt=0, le=MAX_PAISA)
    saved_paisa: int | None = Field(None, ge=0, le=MAX_PAISA)
    deadline: dt.date | None = None


class GoalOut(BaseModel):
    id: int
    name: str
    target_paisa: int
    saved_paisa: int
    deadline: dt.date
    remaining_paisa: int
    percent: float
    days_left: int
    months_left: int
    required_monthly_paisa: int = Field(
        description="Monthly saving needed to reach the target by the deadline (whole rupees, "
        "rounded up). Pre-fill for 'Automate with Smart Deposit'."
    )
    state: GoalState

    @classmethod
    def of(cls, goal_id: int, name: str, deadline: dt.date, g: GoalProgress) -> GoalOut:
        return cls(
            id=goal_id,
            name=name,
            target_paisa=g.target_paisa,
            saved_paisa=g.saved_paisa,
            deadline=deadline,
            remaining_paisa=g.remaining_paisa,
            percent=g.percent,
            days_left=g.days_left,
            months_left=g.months_left,
            required_monthly_paisa=g.required_monthly_paisa,
            state=g.state,
        )


class SmartDepositOut(BaseModel):
    id: str
    name: str
    installment_paisa: int
    interval_days: int
    next_date: dt.date | None
    total_deposited_paisa: int

    @classmethod
    def of(cls, p: SmartDepositPlan) -> SmartDepositOut:
        return cls(**_asdict(p))


# --- bills ---------------------------------------------------------------------------------


class BillOut(BaseModel):
    id: str
    merchant: str
    service: str | None = Field(description="Pre-fill for the Pay / Autopay flows.")
    type: TxnType
    category: Category
    subcategory: str | None
    cadence: str
    usual_amount_paisa: int
    last_amount_paisa: int
    last_paid: dt.date
    due_date: dt.date
    days_until_due: int = Field(description="Negative when overdue.")
    overdue: bool
    status: BillStatus

    @classmethod
    def of(cls, v: BillView) -> BillOut:
        b = v.bill
        return cls(
            id=v.id,
            merchant=b.merchant,
            service=b.service,
            type=b.type,
            category=b.category,
            subcategory=b.subcategory,
            cadence=b.cadence,
            usual_amount_paisa=b.usual_amount_paisa,
            last_amount_paisa=b.last_amount_paisa,
            last_paid=b.last_paid,
            due_date=b.due_date,
            days_until_due=v.days_until_due,
            overdue=v.overdue,
            status=v.status,
        )


class BillStatusIn(BaseModel):
    status: BillStatus = Field(description="'detected' undoes an earlier confirm/dismiss.")


def _asdict(obj: object) -> dict[str, object]:
    return {name: getattr(obj, name) for name in obj.__slots__}  # type: ignore[attr-defined]
