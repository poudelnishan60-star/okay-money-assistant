"""SQLite schema (SQLAlchemy 2.0 ORM). Money columns are integer paisa.

Tables
- users                    demo user(s) and the balance-privacy flag
- transactions             wallet history (owned by MockTransactionSource; Khalti's later)
- merchant_category_cache  LLM categorizations, one row per merchant, shared by all users
- merchant_overrides       a user's "apply to all from this merchant" choice
- budgets                  monthly limit, overall (category NULL) or per category
- goals                    savings goals
- recurring_feedback       user confirmed / dismissed a detected recurring payment
- faq_articles             mock help articles for search_help_articles
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.periods import now_npt


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20))
    balance_hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_npt)


class TransactionRow(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime, index=True)
    type: Mapped[str] = mapped_column(String(20))
    direction: Mapped[str] = mapped_column(String(10))
    amount_paisa: Mapped[int] = mapped_column(Integer)
    merchant: Mapped[str] = mapped_column(String(160))
    merchant_key: Mapped[str] = mapped_column(String(160), index=True)
    service: Mapped[str | None] = mapped_column(String(40))
    counterparty_account: Mapped[str | None] = mapped_column(String(40))
    reference: Mapped[str | None] = mapped_column(String(40))
    remarks: Mapped[str | None] = mapped_column(Text)
    balance_after_paisa: Mapped[int | None] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(40), index=True)
    subcategory: Mapped[str | None] = mapped_column(String(40))
    category_source: Mapped[str] = mapped_column(String(20))


class MerchantCategoryCache(Base):
    __tablename__ = "merchant_category_cache"

    merchant_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    category: Mapped[str] = mapped_column(String(40))
    subcategory: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_npt)


class MerchantOverride(Base):
    __tablename__ = "merchant_overrides"
    __table_args__ = (UniqueConstraint("user_id", "merchant_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    merchant_key: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(40))
    subcategory: Mapped[str | None] = mapped_column(String(40))
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_npt, onupdate=now_npt)


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (
        # One overall budget and at most one budget per category, per user.
        Index(
            "uq_budget_category",
            "user_id",
            "category",
            unique=True,
            sqlite_where=text("category IS NOT NULL"),
            postgresql_where=text("category IS NOT NULL"),
        ),
        Index(
            "uq_budget_overall",
            "user_id",
            unique=True,
            sqlite_where=text("category IS NULL"),
            postgresql_where=text("category IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    category: Mapped[str | None] = mapped_column(String(40))  # NULL = overall budget
    limit_paisa: Mapped[int] = mapped_column(Integer)
    calendar: Mapped[str] = mapped_column(String(2), default="AD")  # "AD" or "BS" month
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_npt)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_npt, onupdate=now_npt)


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    target_paisa: Mapped[int] = mapped_column(Integer)
    saved_paisa: Mapped[int] = mapped_column(Integer, default=0)
    deadline: Mapped[dt.date] = mapped_column(Date)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_npt)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_npt, onupdate=now_npt)


class RecurringFeedback(Base):
    __tablename__ = "recurring_feedback"
    __table_args__ = (UniqueConstraint("user_id", "series_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    series_key: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(12))  # "confirmed" | "dismissed"
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_npt, onupdate=now_npt)


class FaqArticle(Base):
    __tablename__ = "faq_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(String(300))
    answer: Mapped[str] = mapped_column(Text)
    tags: Mapped[str] = mapped_column(String(300), default="")  # space-separated search terms
