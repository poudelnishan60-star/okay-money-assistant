"""Mock sources backed by the SQLite seed."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.domain import Category, CategorySource, Direction, Transaction, TxnType
from app.models import RecurringFeedback, TransactionRow
from app.sources.base import SmartDepositPlan, TransactionFilter, UpcomingBill


def row_to_domain(row: TransactionRow) -> Transaction:
    return Transaction(
        id=row.id,
        user_id=row.user_id,
        occurred_at=row.occurred_at,
        type=TxnType(row.type),
        direction=Direction(row.direction),
        amount_paisa=row.amount_paisa,
        merchant=row.merchant,
        service=row.service,
        counterparty_account=row.counterparty_account,
        reference=row.reference,
        remarks=row.remarks,
        balance_after_paisa=row.balance_after_paisa,
        category=Category(row.category),
        subcategory=row.subcategory,
        category_source=CategorySource(row.category_source),
    )


class MockTransactionSource:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_transactions(
        self, user_id: str, flt: TransactionFilter | None = None
    ) -> list[Transaction]:
        f = flt or TransactionFilter()
        q = select(TransactionRow).where(TransactionRow.user_id == user_id)
        if f.start is not None:
            q = q.where(TransactionRow.occurred_at >= dt.datetime.combine(f.start, dt.time.min))
        if f.end is not None:
            next_day = f.end + dt.timedelta(days=1)
            q = q.where(TransactionRow.occurred_at < dt.datetime.combine(next_day, dt.time.min))
        if f.category is not None:
            q = q.where(TransactionRow.category == f.category.value)
        if f.merchant:
            q = q.where(func.lower(TransactionRow.merchant).contains(f.merchant.lower()))
        if f.type is not None:
            q = q.where(TransactionRow.type == f.type.value)
        if f.direction is not None:
            q = q.where(TransactionRow.direction == f.direction.value)
        if f.min_paisa is not None:
            q = q.where(TransactionRow.amount_paisa >= f.min_paisa)
        if f.max_paisa is not None:
            q = q.where(TransactionRow.amount_paisa <= f.max_paisa)
        q = q.order_by(TransactionRow.occurred_at, TransactionRow.id)
        return [row_to_domain(r) for r in self.session.scalars(q)]

    def get_transaction(self, user_id: str, txn_id: str) -> Transaction | None:
        row = self.session.get(TransactionRow, txn_id)
        if row is None or row.user_id != user_id:
            return None
        return row_to_domain(row)

    def get_balance(self, user_id: str) -> int:
        q = (
            select(TransactionRow.balance_after_paisa)
            .where(TransactionRow.user_id == user_id)
            .order_by(TransactionRow.occurred_at.desc(), TransactionRow.id.desc())
            .limit(1)
        )
        return self.session.scalar(q) or 0

    def set_category(
        self,
        user_id: str,
        txn_ids: Sequence[str],
        category: Category,
        subcategory: str | None,
        source: CategorySource,
    ) -> int:
        if not txn_ids:
            return 0
        stmt = (
            update(TransactionRow)
            .where(TransactionRow.user_id == user_id, TransactionRow.id.in_(list(txn_ids)))
            .values(category=category.value, subcategory=subcategory, category_source=source.value)
        )
        result = self.session.execute(stmt)
        self.session.flush()
        return result.rowcount  # type: ignore[attr-defined, no-any-return]

    def merchant_transaction_ids(self, user_id: str, merchant_key: str) -> list[str]:
        q = select(TransactionRow.id).where(
            TransactionRow.user_id == user_id, TransactionRow.merchant_key == merchant_key
        )
        return list(self.session.scalars(q))


def _dismissed_keys(session: Session, user_id: str) -> set[str]:
    q = select(RecurringFeedback.series_key).where(
        RecurringFeedback.user_id == user_id, RecurringFeedback.status == "dismissed"
    )
    return set(session.scalars(q))


class MockBillSource:
    """Upcoming bills and subscriptions come from recurring-payment detection over the mock
    history. Khalti's version would ask the billers (NEA, KUKL, ISPs) for real due amounts.

    Smart Deposit installments are recurring too, but they are savings, not bills."""

    NOT_BILLS = frozenset({Category.SAVINGS})
    OVERDUE_GRACE_DAYS = 7  # still list a bill that was expected up to a week ago

    def __init__(self, session: Session, transactions: MockTransactionSource) -> None:
        self.session = session
        self.transactions = transactions

    def upcoming_bills(self, user_id: str, today: dt.date, within_days: int) -> list[UpcomingBill]:
        from app.services.recurring import detect_recurring

        dismissed = _dismissed_keys(self.session, user_id)
        series = detect_recurring(
            self.transactions.list_transactions(user_id, TransactionFilter(end=today)),
            as_of=today,
        )
        earliest = today - dt.timedelta(days=self.OVERDUE_GRACE_DAYS)
        horizon = today + dt.timedelta(days=within_days)
        bills = [
            UpcomingBill(
                series_key=s.key,
                merchant=s.merchant,
                service=s.service,
                category=s.category,
                subcategory=s.subcategory,
                usual_amount_paisa=s.usual_amount_paisa,
                due_date=s.next_due,
            )
            for s in series
            if s.direction is Direction.DEBIT
            and s.category not in self.NOT_BILLS
            and s.key not in dismissed
            and earliest <= s.next_due <= horizon
        ]
        return sorted(bills, key=lambda b: (b.due_date, b.merchant))


class MockDepositSource:
    """Smart Deposit plans inferred from the deposit installments in the mock history.
    The assistant only reads these and deep-links to Smart Deposit; it never rebuilds it."""

    def __init__(self, transactions: MockTransactionSource) -> None:
        self.transactions = transactions

    def smart_deposits(self, user_id: str, today: dt.date) -> list[SmartDepositPlan]:
        from app.services.recurring import detect_recurring

        deposits = self.transactions.list_transactions(
            user_id, TransactionFilter(type=TxnType.DEPOSIT, end=today)
        )
        if not deposits:
            return []
        total = sum(t.amount_paisa for t in deposits)
        series = detect_recurring(deposits, as_of=today)
        if series:
            s = series[0]
            return [
                SmartDepositPlan(
                    id="sd_1",
                    name=s.merchant,
                    installment_paisa=s.usual_amount_paisa,
                    interval_days=s.interval_days,
                    next_date=s.next_due,
                    total_deposited_paisa=total,
                )
            ]
        last = deposits[-1]
        return [
            SmartDepositPlan(
                id="sd_1",
                name=last.merchant,
                installment_paisa=last.amount_paisa,
                interval_days=0,
                next_date=None,
                total_deposited_paisa=total,
            )
        ]
