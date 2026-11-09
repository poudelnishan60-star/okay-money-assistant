"""LLM fallback for unknown merchants: one call per merchant, validated, cached, applied."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.classifier import LLMMerchantClassifier, categorize_unknown_merchants
from app.domain import Category
from app.models import MerchantCategoryCache, TransactionRow
from app.seed import seed_user
from tests.conftest import ANCHOR
from tests.fake_llm import FakeLLM


def test_unknown_merchants_are_classified_once_and_cached(seeded: Session) -> None:
    seed_user(seeded, "v_other_visitor", ANCHOR)  # same merchants, second user
    llm = FakeLLM(
        complete=[
            '{"category": "Food & Dining", "subcategory": null}',
            '{"category": "Groceries", "subcategory": null}',
        ]
    )
    done = categorize_unknown_merchants(seeded, llm)
    assert done == {"Hotel Bhanchha Ghar": "Food & Dining", "Om Shanti Traders": "Groceries"}
    assert len(llm.calls) == 2  # one call per merchant, not per user or transaction
    prompt = llm.calls[0][0][0]["content"]
    assert "<merchant>Hotel Bhanchha Ghar</merchant>" in prompt
    rows = seeded.scalars(
        select(TransactionRow).where(TransactionRow.merchant == "Hotel Bhanchha Ghar")
    ).all()
    assert len(rows) == 2 and {r.category for r in rows} == {"Food & Dining"}
    assert {r.category_source for r in rows} == {"llm", "llm_cache"}
    assert seeded.get(MerchantCategoryCache, "om shanti traders").category == "Groceries"
    assert categorize_unknown_merchants(seeded, FakeLLM()) == {}  # nothing left to ask


def test_bad_llm_answers_are_ignored() -> None:
    for raw in ["not json", '{"category": "Transfers"}', '{"category": "Moon"}', "{}"]:
        result = LLMMerchantClassifier(FakeLLM(complete=[raw])).classify("Om Shanti Traders")
        # invalid JSON / unknown names -> None here; Transfers is refused by the Categorizer
        assert result is None or result[0] is Category.TRANSFERS
