from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import Category, CategorySource, TxnType
from app.models import MerchantCategoryCache, MerchantOverride, User
from app.services.categorizer import (
    Categorizer,
    InvalidCategoryError,
    recategorize,
    rule_categorize,
)
from app.sources.mock import MockTransactionSource

S = CategorySource


@pytest.mark.parametrize(
    ("txn_type", "service", "merchant", "expected"),
    [
        (
            TxnType.BILL_PAYMENT,
            "electricity",
            "Nepal Electricity Authority",
            (Category.BILLS, "Electricity", S.SERVICE),
        ),
        (
            TxnType.BILL_PAYMENT,
            "khanepani",
            "KUKL Khanepani",
            (Category.BILLS, "Khanepani", S.SERVICE),
        ),
        (
            TxnType.BILL_PAYMENT,
            "internet",
            "Gurans Fibernet",
            (Category.BILLS, "Internet/TV", S.SERVICE),
        ),
        (TxnType.TOPUP, "data_pack", "Ncell", (Category.TOPUP, None, S.SERVICE)),
        (TxnType.TRANSFER, None, "Bikash Gurung", (Category.TRANSFERS, None, S.TYPE)),
        (TxnType.REMITTANCE, None, "Sagarmatha Remit", (Category.REMITTANCE, None, S.TYPE)),
        (TxnType.DEPOSIT, "smart_deposit", "Smart Deposit", (Category.SAVINGS, None, S.SERVICE)),
        (TxnType.BOOKING, "bus", "Yatra Bus Booking", (Category.TRAVEL, "Bus", S.SERVICE)),
        (TxnType.BOOKING, "movie", "Kalpana Cinemas", (Category.ENTERTAINMENT, None, S.SERVICE)),
        (TxnType.SCAN_PAY, None, "Newa Momo House", (Category.FOOD, None, S.KEYWORD)),
        (TxnType.SCAN_PAY, None, "Café Dhukuti", (Category.FOOD, None, S.KEYWORD)),
        (TxnType.SCAN_PAY, None, "Golden Crust Bakery", (Category.FOOD, None, S.KEYWORD)),
        (TxnType.SCAN_PAY, None, "Ratna Mart", (Category.GROCERIES, None, S.KEYWORD)),
        (TxnType.SCAN_PAY, None, "हाम्रो किराना पसल", (Category.GROCERIES, None, S.KEYWORD)),
        (TxnType.SCAN_PAY, None, "Sewa Medical Store", (Category.HEALTH, None, S.KEYWORD)),
        (
            TxnType.SCAN_PAY,
            None,
            "Sikshya Language Institute",
            (Category.EDUCATION, None, S.KEYWORD),
        ),
        (TxnType.SCAN_PAY, None, "Chalo Taxi", (Category.TRANSPORT, None, S.KEYWORD)),
        (
            TxnType.SCAN_PAY,
            None,
            "Chandragiri Cable Car",
            (Category.TRAVEL, "Cable car", S.KEYWORD),
        ),
        (TxnType.SCAN_PAY, None, "Digital Ghar", (Category.SHOPPING, None, S.MERCHANT)),
    ],
)
def test_rules(txn_type, service, merchant, expected) -> None:
    result = rule_categorize(txn_type, service, merchant)
    assert result is not None
    assert (result.category, result.subcategory, result.source) == expected


@pytest.mark.parametrize(
    "merchant",
    [
        "Hotel Bhanchha Ghar",  # "Hotel" eateries are ambiguous in Nepal: left to the LLM
        "Om Shanti Traders",
        "Smartphone Centre",  # "mart" inside a word must not match Groceries
    ],
)
def test_rules_leave_unknown_merchants_alone(merchant: str) -> None:
    assert rule_categorize(TxnType.SCAN_PAY, None, merchant) is None


class FakeClassifier:
    def __init__(self, answer=(Category.FOOD, None), exc: Exception | None = None) -> None:
        self.answer = answer
        self.exc = exc
        self.calls: list[str] = []

    def classify(self, merchant_name: str):
        self.calls.append(merchant_name)
        if self.exc:
            raise self.exc
        return self.answer


@pytest.fixture
def user(session: Session) -> str:
    session.add(User(id="u1", name="Test", phone="9800000001"))
    session.flush()
    return "u1"


def test_unknown_without_llm_is_other_and_not_cached(session: Session, user: str) -> None:
    r = Categorizer(session).categorize(user, TxnType.SCAN_PAY, None, "Om Shanti Traders")
    assert (r.category, r.source) == (Category.OTHER, S.DEFAULT)
    assert session.scalars(select(MerchantCategoryCache)).all() == []


def test_llm_fallback_is_cached_per_merchant(session: Session, user: str) -> None:
    llm = FakeClassifier((Category.FOOD, None))
    cat = Categorizer(session, llm)
    first = cat.categorize(user, TxnType.SCAN_PAY, None, "Hotel Bhanchha Ghar")
    second = cat.categorize(user, TxnType.SCAN_PAY, None, "HOTEL  Bhanchha-Ghar")
    assert (first.category, first.source) == (Category.FOOD, S.LLM)
    assert (second.category, second.source) == (Category.FOOD, S.CACHE)
    assert llm.calls == ["Hotel Bhanchha Ghar"]  # asked once, merchant name only


@pytest.mark.parametrize(
    "answer",
    [
        (Category.TRANSFERS, None),  # LLM may not turn a shop into a transfer
        (Category.REMITTANCE, None),  # ... or into income
        (Category.FOOD, "Electricity"),  # subcategory that does not belong to the category
        None,
    ],
)
def test_bad_llm_answers_fall_back_to_other(session: Session, user: str, answer) -> None:
    r = Categorizer(session, FakeClassifier(answer)).categorize(
        user, TxnType.SCAN_PAY, None, "Om Shanti Traders"
    )
    assert (r.category, r.source) == (Category.OTHER, S.DEFAULT)
    assert session.scalars(select(MerchantCategoryCache)).all() == []


def test_llm_errors_do_not_break_categorization(session: Session, user: str) -> None:
    llm = FakeClassifier(exc=RuntimeError("429"))
    r = Categorizer(session, llm).categorize(user, TxnType.SCAN_PAY, None, "Om Shanti Traders")
    assert r.category is Category.OTHER


def test_people_names_never_reach_the_llm(session: Session, user: str) -> None:
    llm = FakeClassifier()
    cat = Categorizer(session, llm)
    cat.categorize(user, TxnType.TRANSFER, None, "Some Unknown Person")
    cat.categorize(user, TxnType.REMITTANCE, None, "Unknown Remit Co")
    assert llm.calls == []


def test_user_override_beats_rules(session: Session, user: str) -> None:
    session.add(
        MerchantOverride(user_id=user, merchant_key="ratna mart", category=Category.SHOPPING.value)
    )
    session.flush()
    r = Categorizer(session).categorize(user, TxnType.SCAN_PAY, None, "Ratna Mart")
    assert (r.category, r.source) == (Category.SHOPPING, S.USER)
    # another user is unaffected
    session.add(User(id="u2", name="Other", phone="9800000002"))
    assert (
        Categorizer(session).categorize("u2", TxnType.SCAN_PAY, None, "Ratna Mart").category
        is Category.GROCERIES
    )


# --- recategorize on the seeded data -------------------------------------------------


def _txns_for(source: MockTransactionSource, merchant: str):
    return [t for t in source.list_transactions("demo_user") if t.merchant == merchant]


def test_recategorize_single_transaction(seeded: Session, source: MockTransactionSource) -> None:
    mart = _txns_for(source, "Ratna Mart")
    assert len(mart) >= 2
    res = recategorize(seeded, source, "demo_user", mart[0].id, Category.SHOPPING)
    assert res.updated_ids == [mart[0].id]
    after = _txns_for(source, "Ratna Mart")
    assert after[0].category is Category.SHOPPING and after[0].category_source is S.USER
    assert all(t.category is Category.GROCERIES for t in after[1:])


def test_recategorize_apply_to_all_from_merchant(
    seeded: Session, source: MockTransactionSource
) -> None:
    trader = _txns_for(source, "Om Shanti Traders")
    res = recategorize(
        seeded, source, "demo_user", trader[0].id, Category.GROCERIES, apply_to_merchant=True
    )
    assert res.applied_to_merchant and set(res.updated_ids) == {t.id for t in trader}
    assert all(t.category is Category.GROCERIES for t in _txns_for(source, "Om Shanti Traders"))
    # and future transactions from this merchant follow the user's choice
    future = Categorizer(seeded).categorize(
        "demo_user", TxnType.SCAN_PAY, None, "Om Shanti Traders"
    )
    assert (future.category, future.source) == (Category.GROCERIES, S.USER)


def test_recategorize_validates(seeded: Session, source: MockTransactionSource) -> None:
    txn = source.list_transactions("demo_user")[0]
    with pytest.raises(InvalidCategoryError):
        recategorize(seeded, source, "demo_user", txn.id, Category.FOOD, "Electricity")
    with pytest.raises(LookupError):
        recategorize(seeded, source, "demo_user", "txn_9999", Category.FOOD)
    with pytest.raises(LookupError):
        recategorize(seeded, source, "someone_else", txn.id, Category.FOOD)
