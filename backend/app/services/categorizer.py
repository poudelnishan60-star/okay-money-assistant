"""Transaction categorization: rules first, LLM fallback only for unknown merchants.

Order (first match wins):
1. the user's own "apply to all from this merchant" override
2. service type        (electricity bill -> Bills & Utilities / Electricity)
3. transaction type    (transfer -> Transfers, remittance -> Remittance, deposit -> Savings)
4. merchant dictionary (known merchant names)
5. merchant-name keywords ("... Momo House" -> Food & Dining)
6. cached LLM answer for this merchant
7. LLM fallback (result cached per merchant), if a classifier is configured
8. Other

Only the merchant name ever reaches the LLM, and only for merchant payments (scan & pay,
bookings): transfers and remittances are settled by rule 3, so people's names never do.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import SUBCATEGORIES, Category, CategorySource, TxnType
from app.models import MerchantCategoryCache, MerchantOverride
from app.sources.base import TransactionSource
from app.text import normalize_merchant

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CategoryResult:
    category: Category
    subcategory: str | None
    source: CategorySource


class MerchantClassifier(Protocol):
    """Implemented by the LLM layer (step 6). Receives only the merchant's display name."""

    def classify(self, merchant_name: str) -> tuple[Category, str | None] | None: ...


SERVICE_RULES: dict[str, tuple[Category, str | None]] = {
    "electricity": (Category.BILLS, "Electricity"),
    "khanepani": (Category.BILLS, "Khanepani"),
    "internet": (Category.BILLS, "Internet/TV"),
    "tv": (Category.BILLS, "Internet/TV"),
    "mobile_topup": (Category.TOPUP, None),
    "data_pack": (Category.TOPUP, None),
    "flight": (Category.TRAVEL, "Flight"),
    "bus": (Category.TRAVEL, "Bus"),
    "hotel": (Category.TRAVEL, "Hotel"),
    "cable_car": (Category.TRAVEL, "Cable car"),
    "movie": (Category.ENTERTAINMENT, None),
    "smart_deposit": (Category.SAVINGS, None),
    "bank_load": (Category.TRANSFERS, None),
}

TYPE_RULES: dict[TxnType, Category] = {
    TxnType.TRANSFER: Category.TRANSFERS,
    TxnType.REMITTANCE: Category.REMITTANCE,
    TxnType.DEPOSIT: Category.SAVINGS,
    TxnType.TOPUP: Category.TOPUP,
    TxnType.BILL_PAYMENT: Category.BILLS,
}

# Known merchants, keyed by normalize_merchant(name). Covers the demo merchants whose names
# have no telling keyword; the rest are caught by KEYWORD_RULES.
MERCHANT_DICT: dict[str, tuple[Category, str | None]] = {
    "nepal electricity authority": (Category.BILLS, "Electricity"),
    "kukl khanepani": (Category.BILLS, "Khanepani"),
    "gurans fibernet": (Category.BILLS, "Internet/TV"),
    "sajilo dth": (Category.BILLS, "Internet/TV"),
    "digital ghar": (Category.SHOPPING, None),
}

# Ordered: earlier rules win when a name matches several ("Sewa Medical Store" is Health,
# not Shopping). Keywords match whole words of the normalized name.
# Note: "hotel" alone is deliberately absent. In Nepal many small eateries are called
# "Hotel ..." while hotel *stays* arrive as bookings (service="hotel", rule 2), so a bare
# "hotel" in a scan & pay name is ambiguous and is left to the LLM.
KEYWORD_RULES: list[tuple[Category, str | None, tuple[str, ...]]] = [
    (
        Category.HEALTH,
        None,
        (
            "pharmacy",
            "aushadhi",
            "clinic",
            "hospital",
            "dental",
            "medical",
            "polyclinic",
            "औषधि",
            "अस्पताल",
        ),
    ),
    (
        Category.EDUCATION,
        None,
        ("school", "college", "academy", "institute", "tuition", "campus", "vidyalaya", "विद्यालय"),
    ),
    (
        Category.GROCERIES,
        None,
        (
            "mart",
            "kirana",
            "supermarket",
            "grocery",
            "groceries",
            "tarkari",
            "bhandar",
            "मार्ट",
            "किराना",
        ),
    ),
    (
        Category.FOOD,
        None,
        (
            "cafe",
            "coffee",
            "momo",
            "khaja",
            "chiya",
            "restaurant",
            "bhojanalaya",
            "sekuwa",
            "thakali",
            "kitchen",
            "bakery",
            "bakers",
            "sweets",
            "mithai",
            "pizza",
            "burger",
            "bistro",
            "canteen",
            "खाजा",
            "रेस्टुरेन्ट",
            "मिठाई",
        ),
    ),
    (
        Category.ENTERTAINMENT,
        None,
        ("cinema", "cinemas", "movies", "futsal", "gaming", "theatre", "concert"),
    ),
    (
        Category.TRANSPORT,
        None,
        ("ride", "rides", "taxi", "petrol", "fuel", "yatayat", "parking"),
    ),
    (Category.TRAVEL, "Hotel", ("resort", "guest house", "homestay")),
    (Category.TRAVEL, "Cable car", ("cable car",)),
    (Category.TRAVEL, None, ("airlines", "travels", "tours", "trekking")),
    (
        Category.SHOPPING,
        None,
        (
            "fashion",
            "clothing",
            "boutique",
            "electronics",
            "store",
            "mall",
            "footwear",
            "collection",
            "gift",
        ),
    ),
]

# The LLM may only pick a spending category for a merchant: never income or money-movement.
LLM_ALLOWED: frozenset[Category] = frozenset(Category) - {
    Category.TRANSFERS,
    Category.REMITTANCE,
    Category.SAVINGS,
}


def valid_subcategory(category: Category, subcategory: str | None) -> bool:
    return subcategory is None or subcategory in SUBCATEGORIES.get(category, ())


def _match_keywords(key: str) -> tuple[Category, str | None] | None:
    padded = f" {key} "
    for category, sub, keywords in KEYWORD_RULES:
        if any(f" {kw} " in padded for kw in keywords):
            return category, sub
    return None


def rule_categorize(txn_type: TxnType, service: str | None, merchant: str) -> CategoryResult | None:
    """Rules 2-5. Pure function: no database, no LLM."""
    if service and service in SERVICE_RULES:
        cat, sub = SERVICE_RULES[service]
        return CategoryResult(cat, sub, CategorySource.SERVICE)
    if txn_type in TYPE_RULES:
        return CategoryResult(TYPE_RULES[txn_type], None, CategorySource.TYPE)
    key = normalize_merchant(merchant)
    if key in MERCHANT_DICT:
        cat, sub = MERCHANT_DICT[key]
        return CategoryResult(cat, sub, CategorySource.MERCHANT)
    hit = _match_keywords(key)
    if hit:
        return CategoryResult(hit[0], hit[1], CategorySource.KEYWORD)
    return None


class Categorizer:
    def __init__(self, session: Session, classifier: MerchantClassifier | None = None) -> None:
        self.session = session
        self.classifier = classifier

    def categorize(
        self, user_id: str, txn_type: TxnType, service: str | None, merchant: str
    ) -> CategoryResult:
        key = normalize_merchant(merchant)

        override = self.session.scalar(
            select(MerchantOverride).where(
                MerchantOverride.user_id == user_id, MerchantOverride.merchant_key == key
            )
        )
        if override is not None:
            return CategoryResult(
                Category(override.category), override.subcategory, CategorySource.USER
            )

        ruled = rule_categorize(txn_type, service, merchant)
        if ruled is not None:
            return ruled

        cached = self.session.get(MerchantCategoryCache, key)
        if cached is not None:
            return CategoryResult(
                Category(cached.category), cached.subcategory, CategorySource.CACHE
            )

        llm = self._ask_llm(merchant)
        if llm is not None:
            self.session.add(
                MerchantCategoryCache(merchant_key=key, category=llm[0].value, subcategory=llm[1])
            )
            self.session.flush()
            return CategoryResult(llm[0], llm[1], CategorySource.LLM)

        return CategoryResult(Category.OTHER, None, CategorySource.DEFAULT)

    def _ask_llm(self, merchant: str) -> tuple[Category, str | None] | None:
        if self.classifier is None:
            return None
        try:
            answer = self.classifier.classify(merchant)
        except Exception:  # LLM down / rate-limited: fall back to Other, try again next time
            log.warning("merchant classifier failed", exc_info=True)
            return None
        if answer is None:
            return None
        category, sub = answer
        if category not in LLM_ALLOWED or not valid_subcategory(category, sub):
            log.warning("classifier returned an invalid category: %r / %r", category, sub)
            return None
        return category, sub


@dataclass(frozen=True, slots=True)
class RecategorizeResult:
    updated_ids: list[str]
    merchant_key: str
    applied_to_merchant: bool


class InvalidCategoryError(ValueError):
    pass


def recategorize(
    session: Session,
    source: TransactionSource,
    user_id: str,
    txn_id: str,
    category: Category,
    subcategory: str | None = None,
    *,
    apply_to_merchant: bool = False,
) -> RecategorizeResult:
    """User changes a transaction's category; optionally for every transaction from that
    merchant, past and future (stored as a per-user merchant override)."""
    if not valid_subcategory(category, subcategory):
        raise InvalidCategoryError(f"{subcategory!r} is not a subcategory of {category.value}")
    txn = source.get_transaction(user_id, txn_id)
    if txn is None:
        raise LookupError(txn_id)
    key = normalize_merchant(txn.merchant)

    ids: Sequence[str] = [txn_id]
    if apply_to_merchant:
        override = session.scalar(
            select(MerchantOverride).where(
                MerchantOverride.user_id == user_id, MerchantOverride.merchant_key == key
            )
        )
        if override is None:
            session.add(
                MerchantOverride(
                    user_id=user_id,
                    merchant_key=key,
                    category=category.value,
                    subcategory=subcategory,
                )
            )
        else:
            override.category = category.value
            override.subcategory = subcategory
        ids = source.merchant_transaction_ids(user_id, key)

    source.set_category(user_id, ids, category, subcategory, CategorySource.USER)
    return RecategorizeResult(list(ids), key, apply_to_merchant)
