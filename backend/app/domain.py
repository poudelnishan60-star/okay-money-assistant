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

    @property
    def is_debit(self) -> bool:
        return self.direction is Direction.DEBIT

    @property
    def signed_paisa(self) -> int:
        return -self.amount_paisa if self.is_debit else self.amount_paisa

    @property
    def is_spending(self) -> bool:
        return self.is_debit and self.category not in NON_SPENDING
