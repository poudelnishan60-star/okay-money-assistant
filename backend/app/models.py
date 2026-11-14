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
- chat_messages            chat history per user (masked)
- tool_call_log            audit log of the assistant's tool calls (no raw prompts)
- assistant_settings       language, calendar, alerts, weekly-summary day per user
- notifications            alerts (budget, bill due, unusual spending, weekly summary)
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


class ChatMessage(Base):
    """Chat history. Stored AFTER masking: phone/account/reference numbers and anything that
    looked like an MPIN/OTP/password never reach this table."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(10))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    cards_json: Mapped[str] = mapped_column(Text, default="[]")
    suggestions_json: Mapped[str] = mapped_column(Text, default="[]")
    # Files added to a user message: names and kinds only, never the contents.
    attachments_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    language: Mapped[str | None] = mapped_column(String(10))
    feedback: Mapped[str | None] = mapped_column(String(10))  # "up" | "down"
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_npt, index=True)


class ToolCallLog(Base):
    """Audit log of tool calls (name, masked arguments, outcome). Raw prompts are NOT logged."""

    __tablename__ = "tool_call_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    tool: Mapped[str] = mapped_column(String(60))
    arguments_json: Mapped[str] = mapped_column(Text)
    ok: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(String(300))
    duration_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_npt)


class AssistantSettings(Base):
    """Per-user assistant preferences (language, calendar, alerts). Missing row = defaults."""

    __tablename__ = "assistant_settings"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    settings_json: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_npt, onupdate=now_npt)


class Notification(Base):
    """One alert, stored once per event: `key` is unique per user, so re-running the alert
    check never duplicates. The text is written when it is read (in the user's language),
    from `params_json`, which holds the numbers as they were when the alert fired."""

    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_notification_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(20))  # budget | bill | unusual | weekly_summary
    day: Mapped[dt.date] = mapped_column(Date)  # when it happened
    params_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=now_npt)
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
