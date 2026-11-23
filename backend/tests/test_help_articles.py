"""Help articles on Khalti's rules (step 12): their numbers come from app/rules.py, search
finds them, and an older database gets the new ones."""

from __future__ import annotations

import re

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.ai.tools import ToolContext, run_tool
from app.models import FaqArticle
from app.money import format_npr
from app.rules import LIMITS, OVERNIGHT_BALANCE_CAP_PAISA
from app.seed import ensure_faq
from app.seed_faq import FAQ_ARTICLES, RULE_ARTICLES
from app.sources.mock import MockBillSource, MockTransactionSource
from tests.conftest import ANCHOR, USER


@pytest.fixture
def ctx(seeded: Session) -> ToolContext:
    source = MockTransactionSource(seeded)
    return ToolContext(seeded, source, MockBillSource(source), USER, ANCHOR)


def test_every_amount_in_the_rule_articles_comes_from_the_rules() -> None:
    known = {format_npr(OVERNIGHT_BALANCE_CAP_PAISA), "Rs. 10", "Rs. 100"}
    for lim in LIMITS.values():
        known |= {
            format_npr(p) for p in (lim.per_txn_paisa, lim.per_day_paisa, lim.per_month_paisa)
        }
    for _, answer, _ in RULE_ARTICLES:
        for amount in re.findall(r"Rs\. [\d,]+", answer):
            assert amount in known, amount
    limits = RULE_ARTICLES[0][1]
    assert "Wallet to wallet: Rs. 50,000 per transaction, Rs. 50,000 a day" in limits
    assert "Rs. 50,000 in your wallet overnight" in RULE_ARTICLES[1][1]
    # The how-to articles still have no amounts (and no article states a fee).
    for _, answer, _ in FAQ_ARTICLES:
        assert not re.search(r"\bfee of Rs", answer)


@pytest.mark.parametrize(
    ("query", "title"),
    [
        ("transaction limits how much can I send", "What are Khalti's transaction limits?"),
        ("how much balance can I keep overnight", "How much money can I keep in my wallet?"),
        ("second wallet kyc", "Can I have more than one Khalti wallet?"),
        ("refund time complaint", "How long do refunds and complaints take?"),
        ("lost phone", "I lost my phone or someone used my account. What do I do?"),
        ("caller asked for otp scam", "How do I spot a scam?"),
        ("card dispute", "How do I dispute a card payment?"),
        ("inactive wallet", "My wallet hasn't been used for a long time. Is it still active?"),
        ("I forgot my MPIN", "I forgot my MPIN. How do I reset it?"),  # still found first
    ],
)
def test_search_finds_them(ctx: ToolContext, query: str, title: str) -> None:
    hits = run_tool(ctx, "search_help_articles", {"query": query}).data["articles"]
    assert hits[0]["question"] == title


def test_an_older_database_gets_the_new_articles(seeded: Session) -> None:
    rule_questions = [q for q, _, _ in RULE_ARTICLES]
    seeded.execute(delete(FaqArticle).where(FaqArticle.question.in_(rule_questions)))
    seeded.commit()
    ensure_faq(seeded)
    seeded.commit()
    assert seeded.scalar(select(func.count()).select_from(FaqArticle)) == len(FAQ_ARTICLES)
    ensure_faq(seeded)  # and again: nothing doubles
    seeded.commit()
    assert seeded.scalar(select(func.count()).select_from(FaqArticle)) == len(FAQ_ARTICLES) == 24
