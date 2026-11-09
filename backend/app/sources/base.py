"""Data-source interfaces. The prototype uses the Mock* implementations (SQLite seed);
Khalti* implementations backed by Khalti's real services slot in later without touching
services, the API or the LLM tools."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.domain import Category, CategorySource, Direction, Transaction, TxnType


@dataclass(frozen=True, slots=True)
class TransactionFilter:
    start: dt.date | None = None  # inclusive
    end: dt.date | None = None  # inclusive
    category: Category | None = None
    merchant: str | None = None  # case-insensitive substring of the merchant name
    type: TxnType | None = None
    direction: Direction | None = None
    min_paisa: int | None = None
    max_paisa: int | None = None


class TransactionSource(Protocol):
    def list_transactions(
        self, user_id: str, flt: TransactionFilter | None = None
    ) -> list[Transaction]:
        """Matching transactions, oldest first."""
        ...

    def get_transaction(self, user_id: str, txn_id: str) -> Transaction | None: ...

    def get_balance(self, user_id: str) -> int:
        """Current wallet balance in paisa."""
        ...

    def set_category(
        self,
        user_id: str,
        txn_ids: Sequence[str],
        category: Category,
        subcategory: str | None,
        source: CategorySource,
    ) -> int:
        """Store the assistant's category for these transactions. Returns rows changed.
        (For Khalti this writes to the assistant's own overlay table, not Khalti's ledger.)"""
        ...

    def merchant_transaction_ids(self, user_id: str, merchant_key: str) -> list[str]: ...


@dataclass(frozen=True, slots=True)
class UpcomingBill:
    series_key: str  # stable id of the recurring series (merchant/service)
    merchant: str
    service: str | None  # e.g. "electricity": used to pre-fill the Pay flow
    type: TxnType
    category: Category
    subcategory: str | None
    cadence: str  # "weekly" | "fortnightly" | "monthly"
    usual_amount_paisa: int
    last_amount_paisa: int
    last_paid: dt.date
    due_date: dt.date  # may be up to a week in the past (overdue)


class BillSource(Protocol):
    def upcoming_bills(self, user_id: str, today: dt.date, within_days: int) -> list[UpcomingBill]:
        """Bills expected within `within_days` of today (plus recently overdue ones),
        soonest first. Knows nothing about the user's confirm/dismiss choices."""
        ...


@dataclass(frozen=True, slots=True)
class SmartDepositPlan:
    id: str
    name: str
    installment_paisa: int
    interval_days: int
    next_date: dt.date | None
    total_deposited_paisa: int


class DepositSource(Protocol):
    def smart_deposits(self, user_id: str, today: dt.date) -> list[SmartDepositPlan]: ...
