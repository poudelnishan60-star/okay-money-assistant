"""Spending insights, computed in code. The LLM (step 6) only phrases what is computed here.

- summarize():          totals, change vs the previous period, categories, days, merchants
- unusual_spending():   categories running at >= 2x their usual level
- build_highlights():   the insight cards on the dashboard (structured data + English text)
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from app.domain import Category, Transaction
from app.money import format_npr
from app.periods import Period
from app.services.budgets import BudgetLevel, BudgetStatus
from app.services.forecast import BalanceForecast
from app.services.recurring import detect_recurring

TOP_MERCHANTS = 5
UNUSUAL_RATIO = 2.0  # "a category at 2x its usual spend"
UNUSUAL_MIN_DIFF_PAISA = 1_000_00  # ignore tiny categories: must be Rs 1,000+ above usual
BASELINE_DAYS = 90  # "usual" = daily average over up to this many days before the period
MIN_BASELINE_DAYS = 14  # less history than this: no unusual-spending flags at all


@dataclass(frozen=True, slots=True)
class CategorySpend:
    category: Category
    spent_paisa: int
    count: int
    share_percent: float
    previous_spent_paisa: int  # same basis as SpendingSummary.previous_compare_paisa


@dataclass(frozen=True, slots=True)
class MerchantSpend:
    merchant: str
    category: Category
    spent_paisa: int
    count: int


@dataclass(frozen=True, slots=True)
class DaySpend:
    date: dt.date
    spent_paisa: int


@dataclass(frozen=True, slots=True)
class SpendingSummary:
    period: Period
    previous: Period
    in_progress: bool  # today falls inside the period
    covered_end: dt.date  # last day counted (period end, or today if in progress)
    total_spent_paisa: int
    previous_total_spent_paisa: int  # the whole previous period
    previous_compare_paisa: int  # what change_percent compares against
    comparison_basis: str  # "same_days" (period in progress) or "full_period"
    change_percent: float | None  # None when the comparison base is zero
    income_paisa: int  # remittance received
    money_in_paisa: int  # every credit, including bank loads and friends paying back
    transaction_count: int  # spending transactions
    by_category: tuple[CategorySpend, ...]
    daily: tuple[DaySpend, ...]
    top_merchants: tuple[MerchantSpend, ...]


def _in(t: Transaction, start: dt.date, end: dt.date) -> bool:
    return start <= t.occurred_at.date() <= end


def _pct_change(current: int, base: int) -> float | None:
    return None if base == 0 else round((current - base) * 100 / base, 1)


def summarize(
    txns: Sequence[Transaction], period: Period, previous: Period, today: dt.date
) -> SpendingSummary:
    in_progress = period.contains(today)
    covered_end = min(period.end, today)
    current = [t for t in txns if t.is_spending and _in(t, period.start, covered_end)]
    total = sum(t.amount_paisa for t in current)

    prev_all = [t for t in txns if t.is_spending and _in(t, previous.start, previous.end)]
    prev_total = sum(t.amount_paisa for t in prev_all)
    if in_progress:
        # Compare like with like: the first N days of this period vs the first N of the last.
        n = (covered_end - period.start).days
        compare_end = min(previous.start + dt.timedelta(days=n), previous.end)
        prev_compare = [t for t in prev_all if _in(t, previous.start, compare_end)]
        basis = "same_days"
    else:
        prev_compare = prev_all
        basis = "full_period"
    prev_compare_total = sum(t.amount_paisa for t in prev_compare)

    cat_spent: dict[Category, int] = defaultdict(int)
    cat_count: dict[Category, int] = defaultdict(int)
    for t in current:
        cat_spent[t.category] += t.amount_paisa
        cat_count[t.category] += 1
    cat_prev: dict[Category, int] = defaultdict(int)
    for t in prev_compare:
        cat_prev[t.category] += t.amount_paisa
    by_category = tuple(
        sorted(
            (
                CategorySpend(
                    category=c,
                    spent_paisa=cat_spent.get(c, 0),
                    count=cat_count.get(c, 0),
                    share_percent=round(cat_spent.get(c, 0) * 100 / total, 1) if total else 0.0,
                    previous_spent_paisa=cat_prev.get(c, 0),
                )
                for c in set(cat_spent) | set(cat_prev)
            ),
            key=lambda c: (-c.spent_paisa, -c.previous_spent_paisa, c.category.value),
        )
    )

    per_day: dict[dt.date, int] = defaultdict(int)
    for t in current:
        per_day[t.occurred_at.date()] += t.amount_paisa
    daily = []
    day = period.start
    while day <= covered_end:
        daily.append(DaySpend(day, per_day.get(day, 0)))
        day += dt.timedelta(days=1)

    m_spent: dict[str, int] = defaultdict(int)
    m_count: dict[str, int] = defaultdict(int)
    m_cat: dict[str, Category] = {}
    for t in current:
        m_spent[t.merchant] += t.amount_paisa
        m_count[t.merchant] += 1
        m_cat[t.merchant] = t.category
    top = tuple(
        MerchantSpend(m, m_cat[m], m_spent[m], m_count[m])
        for m in sorted(m_spent, key=lambda m: (-m_spent[m], m))[:TOP_MERCHANTS]
    )

    credits = [t for t in txns if not t.is_debit and _in(t, period.start, covered_end)]
    return SpendingSummary(
        period=period,
        previous=previous,
        in_progress=in_progress,
        covered_end=covered_end,
        total_spent_paisa=total,
        previous_total_spent_paisa=prev_total,
        previous_compare_paisa=prev_compare_total,
        comparison_basis=basis,
        change_percent=_pct_change(total, prev_compare_total),
        income_paisa=sum(t.amount_paisa for t in credits if t.category is Category.REMITTANCE),
        money_in_paisa=sum(t.amount_paisa for t in credits),
        transaction_count=len(current),
        by_category=by_category,
        daily=tuple(daily),
        top_merchants=top,
    )


@dataclass(frozen=True, slots=True)
class UnusualSpend:
    category: Category
    current_paisa: int
    usual_paisa: int  # expected for the same number of days, from the baseline
    ratio: float | None  # None = nothing at all in the baseline ("new" spending)


def unusual_spending(
    txns: Sequence[Transaction],
    period: Period,
    today: dt.date,
    *,
    ratio: float = UNUSUAL_RATIO,
    min_diff_paisa: int = UNUSUAL_MIN_DIFF_PAISA,
) -> list[UnusualSpend]:
    """Categories whose spend in `period` (up to today) is >= `ratio` x their usual level.

    Usual = the category's daily average over up to BASELINE_DAYS before the period, scaled
    to the days covered. Recurring payments (bills, class fees, Smart Deposit) are left out:
    a monthly fee paid on the 5th is expected, not unusual."""
    if not txns:
        return []
    covered_end = min(period.end, today)
    covered_days = (covered_end - period.start).days + 1
    if covered_days <= 0:
        return []
    data_start = min(t.occurred_at.date() for t in txns)
    base_end = period.start - dt.timedelta(days=1)
    base_start = max(data_start, period.start - dt.timedelta(days=BASELINE_DAYS))
    base_days = (base_end - base_start).days + 1
    if base_days < MIN_BASELINE_DAYS:
        return []

    recurring_ids = {
        tid for s in detect_recurring(txns, as_of=covered_end) for tid in s.transaction_ids
    }
    spend = [t for t in txns if t.is_spending and t.id not in recurring_ids]
    cur: dict[Category, int] = defaultdict(int)
    base: dict[Category, int] = defaultdict(int)
    for t in spend:
        d = t.occurred_at.date()
        if period.start <= d <= covered_end:
            cur[t.category] += t.amount_paisa
        elif base_start <= d <= base_end:
            base[t.category] += t.amount_paisa

    flagged = []
    for cat, current in cur.items():
        usual = base.get(cat, 0) * covered_days // base_days
        if current - usual < min_diff_paisa:
            continue
        if usual == 0:
            if current >= 2 * min_diff_paisa:
                flagged.append(UnusualSpend(cat, current, 0, None))
        elif current >= ratio * usual:
            flagged.append(UnusualSpend(cat, current, usual, round(current / usual, 1)))
    return sorted(flagged, key=lambda u: -(u.current_paisa - u.usual_paisa))


def _approx(paisa: int) -> str:
    """An estimate shown to whole rupees: 'about Rs. 942', not 'about Rs. 942.15'."""
    return format_npr(int(round(paisa / 100)) * 100)


class Severity(StrEnum):
    INFO = "info"
    POSITIVE = "positive"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class Highlight:
    kind: str  # month_over_month | unusual_category | top_category | top_merchant |
    # budget_alert | low_balance | month_end_balance
    severity: Severity
    message: str  # English default; `data` carries the numbers for localized phrasing
    data: dict[str, object] = field(default_factory=dict)


def build_highlights(
    summary: SpendingSummary,
    unusual: Sequence[UnusualSpend],
    budgets: Sequence[BudgetStatus] = (),
    forecast: BalanceForecast | None = None,
) -> list[Highlight]:
    """Insight cards, most important first. Budgets and forecast only make sense for the
    period that is in progress, so the caller passes them only then."""
    out: list[Highlight] = []
    prev = summary.previous.label
    basis = f"the same days of {prev}" if summary.in_progress else prev

    for u in unusual:
        if u.ratio is None:
            msg = (
                f"New spending on {u.category.value}: {format_npr(u.current_paisa)} "
                f"in {summary.period.label}."
            )
        else:
            msg = (
                f"{u.category.value} is at {u.ratio:g}x its usual level: "
                f"{format_npr(u.current_paisa)} vs about {_approx(u.usual_paisa)}."
            )
        out.append(
            Highlight(
                "unusual_category",
                Severity.WARNING,
                msg,
                {
                    "category": u.category.value,
                    "current_paisa": u.current_paisa,
                    "usual_paisa": u.usual_paisa,
                    "ratio": u.ratio,
                },
            )
        )

    if forecast is not None and forecast.below_threshold:
        out.append(
            Highlight(
                "low_balance",
                Severity.WARNING,
                f"Your balance may drop below {format_npr(forecast.threshold_paisa)} around "
                f"{forecast.first_below_date:%d %b}.",
                {
                    "threshold_paisa": forecast.threshold_paisa,
                    "first_below_date": forecast.first_below_date.isoformat()
                    if forecast.first_below_date
                    else None,
                    "lowest_balance_paisa": forecast.lowest_balance_paisa,
                },
            )
        )

    for b in budgets:
        if b.level is BudgetLevel.OK:
            continue
        name = b.category.value if b.category else "overall"
        verb = "gone over" if b.level is BudgetLevel.OVER else "used"
        out.append(
            Highlight(
                "budget_alert",
                Severity.WARNING,
                f"You've {verb} {b.percent_used:g}% of your {name} budget "
                f"({format_npr(b.spent_paisa)} of {format_npr(b.limit_paisa)}).",
                {
                    "budget_id": b.budget_id,
                    "category": b.category.value if b.category else None,
                    "percent_used": b.percent_used,
                    "level": b.level.value,
                },
            )
        )

    if summary.change_percent is not None:
        pct = summary.change_percent
        if pct > 20:
            sev = Severity.WARNING
        elif pct < -10:
            sev = Severity.POSITIVE
        else:
            sev = Severity.INFO
        direction = "more" if pct > 0 else "less"
        msg = (
            (
                f"You've spent {abs(pct):g}% {direction} than {basis} "
                f"({format_npr(summary.total_spent_paisa)} vs "
                f"{format_npr(summary.previous_compare_paisa)})."
            )
            if pct
            else (f"You've spent the same as {basis}.")
        )
        out.append(
            Highlight(
                "month_over_month",
                sev,
                msg,
                {
                    "change_percent": pct,
                    "current_paisa": summary.total_spent_paisa,
                    "previous_paisa": summary.previous_compare_paisa,
                    "basis": summary.comparison_basis,
                },
            )
        )

    if summary.by_category and summary.by_category[0].spent_paisa > 0:
        top = summary.by_category[0]
        out.append(
            Highlight(
                "top_category",
                Severity.INFO,
                f"{top.category.value} is your biggest category: {format_npr(top.spent_paisa)} "
                f"({top.share_percent:g}% of spending).",
                {
                    "category": top.category.value,
                    "spent_paisa": top.spent_paisa,
                    "share_percent": top.share_percent,
                },
            )
        )

    if summary.top_merchants:
        m = summary.top_merchants[0]
        visits = f"{m.count} payment{'s' if m.count != 1 else ''}"
        out.append(
            Highlight(
                "top_merchant",
                Severity.INFO,
                f"You spent the most at {m.merchant}: {format_npr(m.spent_paisa)} over {visits}.",
                {"merchant": m.merchant, "spent_paisa": m.spent_paisa, "count": m.count},
            )
        )

    if forecast is not None and not forecast.below_threshold:
        out.append(
            Highlight(
                "month_end_balance",
                Severity.POSITIVE,
                f"Projected balance on {forecast.horizon_end:%d %b}: "
                f"{format_npr(forecast.projected_end_balance_paisa)}.",
                {
                    "horizon_end": forecast.horizon_end.isoformat(),
                    "projected_end_balance_paisa": forecast.projected_end_balance_paisa,
                },
            )
        )
    return out
