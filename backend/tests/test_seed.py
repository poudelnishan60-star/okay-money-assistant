from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import Category, Direction, TxnType
from app.models import Budget, FaqArticle, Goal, TransactionRow
from app.seed import (
    INJECTION_REMARK,
    MIN_WALLET_BUFFER_PAISA,
    STARTING_BALANCE_PAISA,
    generate,
    seed_database,
)
from app.sources.mock import MockTransactionSource
from tests.conftest import ANCHOR, USER


def _snapshot(anchor: dt.date, seed: int = 2083):
    _, rows = generate(anchor, seed)
    return [(i, ref, d.occurred_at, d.merchant, d.amount_paisa, bal) for i, ref, d, bal in rows]


def test_seed_is_reproducible() -> None:
    assert _snapshot(ANCHOR) == _snapshot(ANCHOR)
    assert _snapshot(ANCHOR) != _snapshot(ANCHOR, seed=1)


def test_about_150_transactions_over_90_days(source: MockTransactionSource) -> None:
    txns = source.list_transactions(USER)
    assert 130 <= len(txns) <= 170
    days = {t.occurred_at.date() for t in txns}
    assert min(days) >= ANCHOR - dt.timedelta(days=90)
    assert max(days) <= ANCHOR - dt.timedelta(days=1)  # nothing in the future


def test_running_balance_is_consistent_and_never_too_low(source: MockTransactionSource) -> None:
    balance = STARTING_BALANCE_PAISA
    for t in source.list_transactions(USER):
        balance += t.signed_paisa
        assert t.balance_after_paisa == balance
        assert balance >= MIN_WALLET_BUFFER_PAISA
    assert source.get_balance(USER) == balance


def test_starting_balance_is_about_15000(source: MockTransactionSource) -> None:
    first = source.list_transactions(USER)[0]
    assert first.balance_after_paisa - first.signed_paisa == 15_000_00


def test_covers_every_kind_the_spec_asks_for(source: MockTransactionSource) -> None:
    txns = source.list_transactions(USER)
    services = {t.service for t in txns}
    assert {
        "electricity",
        "khanepani",
        "internet",
        "tv",
        "data_pack",
        "mobile_topup",
        "bus",
        "smart_deposit",
    } <= services
    types = {t.type for t in txns}
    assert set(TxnType) <= types
    friends_out = [t for t in txns if t.type is TxnType.TRANSFER and t.is_debit]
    assert len(friends_out) >= 3
    assert any(t.type is TxnType.REMITTANCE and t.direction is Direction.CREDIT for t in txns)
    merchants = {t.merchant for t in txns}
    assert any("Café" in m for m in merchants)
    assert any("Mart" in m for m in merchants)
    assert any("Bakery" in m for m in merchants)


def test_only_the_deliberately_unknown_merchants_are_other(source: MockTransactionSource) -> None:
    others = {t.merchant for t in source.list_transactions(USER) if t.category is Category.OTHER}
    assert others == {"Hotel Bhanchha Ghar", "Om Shanti Traders"}


def test_ids_and_references_are_unique(source: MockTransactionSource) -> None:
    txns = source.list_transactions(USER)
    assert len({t.id for t in txns}) == len(txns)
    refs = [t.reference for t in txns]
    assert len(set(refs)) == len(refs) and all(r and len(r) == 11 for r in refs)


def test_injection_remark_is_stored_as_plain_data(source: MockTransactionSource) -> None:
    hits = [t for t in source.list_transactions(USER) if t.remarks == INJECTION_REMARK]
    assert len(hits) == 1 and hits[0].category is Category.TRANSFERS


def test_budgets_goals_and_faq(seeded: Session) -> None:
    budgets = seeded.scalars(select(Budget)).all()
    assert {b.category for b in budgets} == {None, "Groceries", "Entertainment", "Shopping"}
    assert "Food & Dining" not in {b.category for b in budgets}  # left for "Set a food budget"
    assert {b.calendar for b in budgets} == {"AD", "BS"}
    goals = seeded.scalars(select(Goal)).all()
    assert len(goals) == 2 and all(g.deadline > ANCHOR for g in goals)
    assert seeded.scalar(select(func.count()).select_from(FaqArticle)) >= 15


def test_reseeding_replaces_instead_of_duplicating(seeded: Session) -> None:
    before = seeded.scalar(select(func.count()).select_from(TransactionRow))
    seed_database(seeded, ANCHOR)
    assert seeded.scalar(select(func.count()).select_from(TransactionRow)) == before
    assert seeded.scalar(select(func.count()).select_from(Budget)) == 4
