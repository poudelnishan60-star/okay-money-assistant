"""Domain types shared by sources, services and (later) the API and LLM tools.

Money is always integer paisa (Rs. 1 = 100 paisa) so no float rounding ever touches a balance.
Times are naive Nepal time (NPT, UTC+05:45; Nepal has no DST).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum


class TxnType(StrEnum):
    SCAN_PAY = "scan_pay"
    BILL_PAYMENT = "bill_payment"
    TOPUP = "topup"
    TRANSFER = "transfer"
    REMITTANCE = "remittance"
    BOOKING = "booking"
    DEPOSIT = "deposit"


class Direction(StrEnum):
    DEBIT = "debit"
    CREDIT = "credit"


class Category(StrEnum):
    FOOD = "Food & Dining"
    GROCERIES = "Groceries"
    TRANSPORT = "Transport"
    BILLS = "Bills & Utilities"
    TOPUP = "Topup & Data"
    TRAVEL = "Travel"
    SHOPPING = "Shopping"
    EDUCATION = "Education"
    HEALTH = "Health"
    ENTERTAINMENT = "Entertainment"
    TRANSFERS = "Transfers"
    REMITTANCE = "Remittance"
    SAVINGS = "Savings"
    OTHER = "Other"


# Subcategories the spec names explicitly.
SUBCATEGORIES: dict[Category, tuple[str, ...]] = {
    Category.BILLS: ("Electricity", "Khanepani", "Internet/TV"),
    Category.TRAVEL: ("Flight", "Bus", "Hotel", "Cable car"),
}

# Categories that are money moved, not money spent. They still affect the wallet balance
# (so the cash-flow forecast counts them) but are left out of "spending" and budgets.
NON_SPENDING: frozenset[Category] = frozenset(
    {Category.TRANSFERS, Category.SAVINGS, Category.REMITTANCE}
)


class TxnStatus(StrEnum):
    SUCCESS = "success"
    PENDING = "pending"  # not settled yet; the money is held
    FAILED = "failed"  # money left the wallet, nothing reached the other side
    REVERSED = "reversed"  # failed, and the money came back (see reversal_of)


class KycStatus(StrEnum):
    VERIFIED = "verified"
    PENDING = "pending"  # sent, being checked
    NOT_STARTED = "not_started"


class CategorySource(StrEnum):
    USER = "user"  # user recategorized (possibly "apply to all from this merchant")
    SERVICE = "rule_service"  # service type, e.g. electricity bill
    TYPE = "rule_type"  # transaction type, e.g. transfer
    MERCHANT = "merchant_dict"  # known-merchant dictionary
    KEYWORD = "keyword"  # merchant-name keyword, e.g. "... Momo House"
    CACHE = "llm_cache"  # earlier LLM answer for this merchant
    LLM = "llm"  # fresh LLM answer (then cached)
    DEFAULT = "default"  # nothing matched


@dataclass(frozen=True, slots=True)
class Transaction:
    id: str
    user_id: str
    occurred_at: dt.datetime
    type: TxnType
    direction: Direction
    amount_paisa: int  # always positive; direction says which way
    merchant: str  # merchant / biller / counterparty display name (untrusted text)
    service: str | None = None  # e.g. "electricity", "data_pack", "bus", "smart_deposit"
    counterparty_account: str | None = None  # phone / account number (masked before LLM)
    reference: str | None = None  # Khalti reference id (masked before LLM)
    remarks: str | None = None  # free text typed by a person (untrusted)
    balance_after_paisa: int | None = None
    category: Category = Category.OTHER
    subcategory: str | None = None
    category_source: CategorySource = CategorySource.DEFAULT
    status: TxnStatus = TxnStatus.SUCCESS
    reversal_of: str | None = None  # on the money returned: the failed transaction

    @property
    def is_debit(self) -> bool:
        return self.direction is Direction.DEBIT

    @property
    def signed_paisa(self) -> int:
        return -self.amount_paisa if self.is_debit else self.amount_paisa

    @property
    def counts(self) -> bool:
        """Counted in spending, budgets, forecasts and insights: only a completed
        transaction. A failed or pending one isn't, and a reversed payment and the money
        returned for it cancel out, so neither is."""
        return self.status is TxnStatus.SUCCESS and self.reversal_of is None

    @property
    def is_spending(self) -> bool:
        return self.is_debit and self.category not in NON_SPENDING and self.counts
