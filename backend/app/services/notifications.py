"""Alerts (spec "Notifications"): a budget at 80% and 100%, a bill due within 3 days, unusual
spending, and a weekly summary on the day the user picks.

How it works
- `sync_notifications` computes every alert that applies today from the same services the
  screens use (budget math, the recurring-bill detector, the unusual-spend check, the spending
  summary), and stores each one ONCE: the key names the event (which budget, which threshold,
  which month), and keys are unique per user. Running it again, on every read or from a
  scheduler, never duplicates.
- Numbers are stored as they were when the alert fired (paisa); the words are written when
  the alert is read, in the user's language. All arithmetic happens here, in code; no LLM.
- Delivery: the in-app inbox (GET /notifications) on the website. Each new alert also goes
  to a `PushSender`; on the website that is a no-op, inside Khalti it would be Khalti's
  push service. `scripts/send_alerts.py` is what a daily scheduler would run.
- The alert switches in the user's settings stop new alerts of that kind.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain import Category
from app.models import Notification
from app.money import format_npr
from app.periods import CalendarSystem, Period, month_period, now_npt
from app.services.bills import list_bills
from app.services.budgets import budget_statuses, spent_in_period
from app.services.insights import BASELINE_DAYS, summarize, unusual_spending
from app.services.user_settings import WEEKDAYS, UserSettings, load_settings
from app.sources.base import BillSource, TransactionFilter, TransactionSource

BILL_DUE_DAYS = 3  # spec: "bill due in 3 days"
INBOX_LIMIT = 50


class Kind(StrEnum):
    BUDGET = "budget"
    BILL = "bill"
    UNUSUAL = "unusual"
    WEEKLY = "weekly_summary"


@dataclass(frozen=True, slots=True)
class Alert:
    key: str  # names the event; unique per user
    kind: Kind
    day: dt.date  # when it happened
    params: dict[str, Any]  # the numbers (paisa) and names the words need


class PushSender(Protocol):
    def send(self, user_id: str, title: str, body: str, link: dict[str, Any]) -> None: ...


class NoPush:
    """The website has only the in-app inbox."""

    def send(self, user_id: str, title: str, body: str, link: dict[str, Any]) -> None:
        return None


# --- finding alerts -----------------------------------------------------------------------


def _crossing_day(
    txns: list[Any], period: Period, category: Category | None, line_paisa: int, today: dt.date
) -> tuple[dt.date, int]:
    """First day the period's spending reached `line_paisa`, and the spend on that day."""
    day = period.start
    last = min(period.end, today)
    while day <= last:
        spent = spent_in_period(txns, Period(period.start, day, ""), category)
        if spent >= line_paisa:
            return day, spent
        day += dt.timedelta(days=1)
    return last, spent_in_period(txns, Period(period.start, last, ""), category)


def budget_alerts(
    session: Session, source: TransactionSource, user_id: str, today: dt.date
) -> list[Alert]:
    """The highest threshold (80 or 100) each budget has reached this month. Reaching both
    before the first check gives one alert (100%), not two."""
    statuses = [s for s in budget_statuses(session, source, user_id, today) if s.alerts_reached]
    if not statuses:
        return []
    start = min(s.period.start for s in statuses)
    txns = source.list_transactions(user_id, TransactionFilter(start=start, end=today))
    alerts = []
    for s in statuses:
        threshold = max(s.alerts_reached)
        day, spent = _crossing_day(
            txns, s.period, s.category, s.limit_paisa * threshold // 100, today
        )
        alerts.append(
            Alert(
                key=f"budget:{s.budget_id}:{s.period.start}:{threshold}",
                kind=Kind.BUDGET,
                day=day,
                params={
                    "budget_id": s.budget_id,
                    "category": s.category.value if s.category else None,
                    "threshold": threshold,
                    "limit_paisa": s.limit_paisa,
                    "spent_paisa": spent,
                    "period_label": s.period.label,
                },
            )
        )
    return alerts


def bill_alerts(session: Session, bills: BillSource, user_id: str, today: dt.date) -> list[Alert]:
    """Bills (not dismissed) due today or in the next 3 days."""
    alerts = []
    for v in list_bills(session, bills, user_id, today, BILL_DUE_DAYS):
        if not 0 <= v.days_until_due <= BILL_DUE_DAYS:
            continue
        b = v.bill
        alerts.append(
            Alert(
                key=f"bill:{v.id}:{b.due_date}",
                kind=Kind.BILL,
                day=b.due_date - dt.timedelta(days=BILL_DUE_DAYS),
                params={
                    "bill_id": v.id,
                    "merchant": b.merchant,
                    "service": b.service,
                    "category": b.category.value,
                    "due_date": b.due_date.isoformat(),
                    "usual_amount_paisa": b.usual_amount_paisa,
                },
            )
        )
    return alerts


def unusual_alerts(
    source: TransactionSource, user_id: str, today: dt.date, calendar: CalendarSystem
) -> list[Alert]:
    """Categories at 2x (or more) their usual spend this month; once per category a month."""
    period = month_period(today, calendar)
    txns = source.list_transactions(
        user_id,
        TransactionFilter(start=period.start - dt.timedelta(days=BASELINE_DAYS), end=today),
    )
    return [
        Alert(
            key=f"unusual:{u.category.value}:{period.start}",
            kind=Kind.UNUSUAL,
            day=today,
            params={
                "category": u.category.value,
                "current_paisa": u.current_paisa,
                "usual_paisa": int(round(u.usual_paisa / 100)) * 100,
                "ratio": u.ratio,
                "period_label": period.label,
                "start": period.start.isoformat(),
                "end": min(period.end, today).isoformat(),
            },
        )
        for u in unusual_spending(txns, period, today)
    ]


def last_summary_day(today: dt.date, weekday: str) -> dt.date:
    """The most recent `weekday` on or before today."""
    return today - dt.timedelta(days=(today.weekday() - WEEKDAYS.index(weekday)) % 7)  # type: ignore[arg-type]


def weekly_alert(source: TransactionSource, user_id: str, today: dt.date, weekday: str) -> Alert:
    """The latest weekly summary: the 7 days before the user's summary day."""
    day = last_summary_day(today, weekday)
    week = Period(day - dt.timedelta(days=7), day - dt.timedelta(days=1), "week")
    before = Period(week.start - dt.timedelta(days=7), week.start - dt.timedelta(days=1), "")
    txns = source.list_transactions(user_id, TransactionFilter(start=before.start, end=week.end))
    s = summarize(txns, week, before, today)
    top = next((c for c in s.by_category if c.spent_paisa > 0), None)
    return Alert(
        key=f"weekly:{day}",
        kind=Kind.WEEKLY,
        day=day,
        params={
            "start": week.start.isoformat(),
            "end": week.end.isoformat(),
            "spent_paisa": s.total_spent_paisa,
            "previous_paisa": s.previous_compare_paisa,
            "change_percent": s.change_percent,
            "payments": s.transaction_count,
            "top_category": top.category.value if top else None,
            "top_category_paisa": top.spent_paisa if top else 0,
        },
    )


def find_alerts(
    session: Session,
    source: TransactionSource,
    bills: BillSource,
    user_id: str,
    today: dt.date,
    settings: UserSettings,
) -> list[Alert]:
    on = settings.alerts
    alerts: list[Alert] = []
    if on.budget:
        alerts += budget_alerts(session, source, user_id, today)
    if on.bills:
        alerts += bill_alerts(session, bills, user_id, today)
    if on.unusual:
        alerts += unusual_alerts(source, user_id, today, CalendarSystem(settings.calendar))
    if on.weekly_summary:
        alerts.append(weekly_alert(source, user_id, today, settings.weekly_summary_day))
    return alerts


def sync_notifications(
    session: Session,
    source: TransactionSource,
    bills: BillSource,
    user_id: str,
    today: dt.date,
    push: PushSender | None = None,
) -> list[Notification]:
    """Store the alerts that are new since the last check, push them, return them."""
    settings = load_settings(session, user_id)
    alerts = find_alerts(session, source, bills, user_id, today, settings)
    if not alerts:
        return []
    known = set(session.scalars(select(Notification.key).where(Notification.user_id == user_id)))
    new = [
        Notification(
            user_id=user_id,
            key=a.key,
            kind=a.kind.value,
            day=a.day,
            params_json=json.dumps(a.params, ensure_ascii=False),
        )
        for a in alerts
        if a.key not in known
    ]
    if not new:
        return []
    session.add_all(new)
    try:
        session.commit()
    except IntegrityError:  # a parallel request stored them first
        session.rollback()
        return []
    lang = settings.language
    for n in new:
        title, body = render(n, lang, today)
        (push or NoPush()).send(user_id, title, body, link_for(n))
    return new


def inbox(session: Session, user_id: str) -> list[Notification]:
    return list(
        session.scalars(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.day.desc(), Notification.id.desc())
            .limit(INBOX_LIMIT)
        )
    )


def count_unread(session: Session, user_id: str) -> int:
    return (
        session.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id, Notification.read_at.is_(None)
            )
        )
        or 0
    )


def mark_read(session: Session, user_id: str, ids: list[int] | None) -> int:
    """Mark these (or, with None, all) unread notifications read. Returns how many changed."""
    q = select(Notification).where(Notification.user_id == user_id, Notification.read_at.is_(None))
    if ids is not None:
        q = q.where(Notification.id.in_(ids))
    rows = list(session.scalars(q))
    now = now_npt()
    for r in rows:
        r.read_at = now
    session.commit()
    return len(rows)


# --- words --------------------------------------------------------------------------------

CATEGORY_NE = {
    "Food & Dining": "खाना",
    "Groceries": "किराना",
    "Transport": "यातायात",
    "Bills & Utilities": "बिल",
    "Topup & Data": "टपअप र डाटा",
    "Travel": "यात्रा",
    "Shopping": "किनमेल",
    "Education": "शिक्षा",
    "Health": "स्वास्थ्य",
    "Entertainment": "मनोरञ्जन",
    "Transfers": "ट्रान्सफर",
    "Remittance": "रेमिट्यान्स",
    "Savings": "बचत",
    "Other": "अन्य",
}


def _rs(paisa: int, ne: bool) -> str:
    text = format_npr(paisa)
    return text.replace("Rs.", "रु.") if ne else text


def _cat(name: str | None, ne: bool) -> str:
    if name is None:
        return "समग्र" if ne else "Overall"
    return CATEGORY_NE.get(name, name) if ne else name


def render(n: Notification, language: str, today: dt.date) -> tuple[str, str]:
    """(title, body) in the user's language: Nepali for "ne", English otherwise."""
    p = json.loads(n.params_json)
    ne = language == "ne"
    match n.kind:
        case Kind.BUDGET:
            return _budget_words(p, ne)
        case Kind.BILL:
            return _bill_words(p, ne, today)
        case Kind.UNUSUAL:
            return _unusual_words(p, ne)
        case Kind.WEEKLY:
            return _weekly_words(p, ne)
    return n.kind, ""


def _budget_words(p: dict[str, Any], ne: bool) -> tuple[str, str]:
    name, period = _cat(p["category"], ne), p["period_label"]
    spent, limit = _rs(p["spent_paisa"], ne), _rs(p["limit_paisa"], ne)
    over = p["spent_paisa"] - p["limit_paisa"]
    if p["threshold"] >= 100:
        if ne:
            extra = f", {_rs(over, ne)} बढी" if over > 0 else ""
            return f"{name} बजेट सकियो", f"{period}: {limit} को बजेटमा {spent} खर्च भयो{extra}।"
        extra = f": {_rs(over, ne)} over" if over > 0 else ""
        return f"{name} budget used up", f"{spent} spent of {limit} in {period}{extra}."
    if ne:
        return (
            f"{name} बजेटको {p['threshold']}% पुग्यो",
            f"{period}: {limit} मध्ये {spent} खर्च भइसक्यो।",
        )
    return (
        f"{name} budget at {p['threshold']}%",
        f"{spent} of {limit} spent in {period}.",
    )


def _bill_words(p: dict[str, Any], ne: bool, today: dt.date) -> tuple[str, str]:
    m, usual = p["merchant"], _rs(p["usual_amount_paisa"], ne)
    days = (dt.date.fromisoformat(p["due_date"]) - today).days
    if ne:
        when = {0: "आज", 1: "भोलि"}.get(days, f"{days} दिनमा" if days > 0 else "")
        title = f"{m} को बिल {when} तिर्नुपर्छ" if days >= 0 else f"{m} को बिल तिर्ने दिन गयो"
        return title, f"सामान्यतया {usual}। अहिले तिर्नुहोस् वा Autopay राख्नुहोस्।"
    if days < 0:
        title = f"{m} was due {-days} day{'s' if days < -1 else ''} ago"
    else:
        title = f"{m} is due " + {0: "today", 1: "tomorrow"}.get(days, f"in {days} days")
    return title, f"Usually {usual}. Pay now or set up Autopay so you don't miss it."


def _unusual_words(p: dict[str, Any], ne: bool) -> tuple[str, str]:
    name, period = _cat(p["category"], ne), p["period_label"]
    current, usual = _rs(p["current_paisa"], ne), _rs(p["usual_paisa"], ne)
    ratio = p["ratio"]
    if ne:
        title = f"{name} मा असामान्य खर्च"
        if ratio is None:
            return title, f"{period} मा अहिलेसम्म {current}; सामान्यतया यसमा खर्च हुँदैनथ्यो।"
        return title, f"{period} मा अहिलेसम्म {current}, सामान्य ({usual}) भन्दा {ratio:g} गुणा।"
    title = f"Unusual spending on {name}"
    if ratio is None:
        return title, f"{current} so far in {period}, where you usually spend nothing."
    return (
        title,
        f"{current} so far in {period}: {ratio:g}x your usual {usual} for this many days.",
    )


def _weekly_words(p: dict[str, Any], ne: bool) -> tuple[str, str]:
    spent = _rs(p["spent_paisa"], ne)
    pct = p["change_percent"]
    top, top_amount = p["top_category"], _rs(p["top_category_paisa"], ne)
    if ne:
        title = f"तपाईंको हप्ता: {spent} खर्च"
        parts = []
        if pct is not None and pct != 0:
            parts.append(f"अघिल्लो हप्ताभन्दा {abs(pct):g}% {'कम' if pct < 0 else 'बढी'}।")
        if top:
            parts.append(f"सबैभन्दा धेरै {_cat(top, ne)} मा ({top_amount})।")
        return title, " ".join(parts) or "गएको हप्ता कुनै खर्च भएन।"
    title = f"Your week: {spent} spent"
    parts = []
    if pct is not None and pct != 0:
        parts.append(f"{abs(pct):g}% {'less' if pct < 0 else 'more'} than the week before.")
    if top:
        parts.append(f"Most went to {top} ({top_amount}).")
    return title, " ".join(parts) or "No spending last week."


def link_for(n: Notification) -> dict[str, Any]:
    """Where tapping the alert goes in the app: a screen plus its filters."""
    p = json.loads(n.params_json)
    match n.kind:
        case Kind.BUDGET:
            return {"screen": "budgets", "params": {}}
        case Kind.BILL:
            return {"screen": "bills", "params": {}}
        case Kind.UNUSUAL:
            return {
                "screen": "transactions",
                "params": {
                    "category": p["category"],
                    "start": p["start"],
                    "end": p["end"],
                    "spending_only": "true",
                },
            }
    return {"screen": "insights", "params": {}}
