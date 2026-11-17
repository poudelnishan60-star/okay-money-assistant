"""Rich cards shown inside the chat. Built in code from tool results (never by the LLM), sent
in the final SSE event and stored with the message. Amounts are integer paisa, as in the
rest of the API."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class TransactionsLink(BaseModel):
    """ "View 12 transactions ->": open the transactions screen with these GET /transactions
    query parameters."""

    count: int
    filters: dict[str, Any]


class CategoryAmount(BaseModel):
    category: str
    spent_paisa: int
    share_percent: float


class SpendingSummaryCard(BaseModel):
    type: Literal["spending_summary"] = "spending_summary"
    period_label: str
    start: dt.date
    end: dt.date
    category: str | None = None
    total_paisa: int
    previous_paisa: int
    compared_with: str
    change_percent: float | None
    link: TransactionsLink


class CategoryBreakdownCard(BaseModel):
    type: Literal["category_breakdown"] = "category_breakdown"
    period_label: str
    total_paisa: int
    items: list[CategoryAmount]
    link: TransactionsLink


class BudgetItem(BaseModel):
    budget_id: int | None
    category: str | None  # None = overall
    period_label: str
    limit_paisa: int
    spent_paisa: int
    percent_used: float
    level: str


class BudgetProgressCard(BaseModel):
    type: Literal["budget_progress"] = "budget_progress"
    items: list[BudgetItem]


class BillItem(BaseModel):
    bill_id: str
    merchant: str
    service: str | None
    usual_amount_paisa: int
    due_date: dt.date
    days_until_due: int
    overdue: bool


class BillsListCard(BaseModel):
    type: Literal["bills_list"] = "bills_list"
    items: list[BillItem]


class GoalItem(BaseModel):
    goal_id: int
    name: str
    target_paisa: int
    saved_paisa: int
    percent: float
    deadline: dt.date
    required_monthly_paisa: int
    state: str


class GoalProgressCard(BaseModel):
    type: Literal["goal_progress"] = "goal_progress"
    items: list[GoalItem]


class TransactionItem(BaseModel):
    id: str
    date: dt.date
    merchant: str
    amount_paisa: int
    direction: str
    category: str


class TransactionsPreviewCard(BaseModel):
    type: Literal["transactions_preview"] = "transactions_preview"
    count: int
    total_debit_paisa: int
    total_credit_paisa: int
    items: list[TransactionItem]
    link: TransactionsLink


class Detail(BaseModel):
    label: str
    value: str


class ApiRequest(BaseModel):
    """What the app calls when the user taps Confirm. Nothing is saved before that."""

    method: Literal["POST", "PATCH"]
    path: str
    body: dict[str, Any]


class ConfirmActionCard(BaseModel):
    type: Literal["confirm_action"] = "confirm_action"
    action: Literal["upsert_budget", "upsert_goal"]
    title: str
    details: list[Detail]
    request: ApiRequest
    confirm_label: str = "Confirm"


class AppFlowPrefill(BaseModel):
    amount_paisa: int | None = None
    biller_name: str | None = None
    recipient_name: str | None = None
    goal_name: str | None = None
    monthly_amount_paisa: int | None = None


class OpenAppFlowCard(BaseModel):
    """Opens an existing Khalti flow through the HostAppBridge. The assistant never moves
    money; the user finishes in the app with MPIN / biometric."""

    type: Literal["open_app_flow"] = "open_app_flow"
    flow: Literal["bill_payment", "send_money", "autopay", "smart_deposit"]
    service: str | None = None
    title: str
    prefill: AppFlowPrefill
    note: str = "You'll confirm in Khalti with your MPIN."


class FileSlice(BaseModel):
    """One part of a file's total: a type (Scan and Pay, Transfer, ...) or a payee."""

    label: str
    paisa: int
    share_percent: float  # of the whole file's total for this measure, worked out in code
    rows: int
    is_other: bool = False  # the smaller parts folded together


class FilePeriod(BaseModel):
    start: dt.date  # Monday of the week, or the 1st of the month
    label: str  # "26 Oct-1 Nov" or "Nov 2026"
    paisa: int  # the card's measure
    in_paisa: int = 0  # money in, when the measure is money out


class BalancePoint(BaseModel):
    date: dt.date | None
    paisa: int


FileSection = Literal["types", "periods", "biggest", "balance"]


class FileReportCard(BaseModel):
    """Charts for a spreadsheet the user added, worked out in code from every row (see
    sheets.py), like the report the model gets. Sent with the answer but never stored with
    it: what was read from a file stays in the server's memory only."""

    type: Literal["file_report"] = "file_report"
    file_name: str
    rows: int
    start: dt.date | None = None
    end: dt.date | None = None
    # What the charts add up: money out (the sheet has money in and out columns), money in
    # (only an in column), or "amount" (one amount column whose values all have one sign).
    # None: one amount column with both signs, which is only totalled, so not charted.
    measure: Literal["out", "in", "amount"] | None = None
    money_in_paisa: int | None = None
    money_out_paisa: int | None = None
    total_paisa: int | None = None  # one amount column
    type_column: str | None = None
    by_type: list[FileSlice] = Field(default_factory=list)
    in_by_type: list[FileSlice] = Field(default_factory=list)
    period: Literal["week", "month"] | None = None
    periods: list[FilePeriod] = Field(default_factory=list)
    biggest_column: str | None = None
    biggest: list[FileSlice] = Field(default_factory=list)
    balance_column: str | None = None
    balance: list[BalancePoint] = Field(default_factory=list)  # oldest first, sampled
    balance_check: Literal["ok", "off"] | None = None  # follows money in and out row by row
    balance_rows_checked: int = 0
    balance_rows_off: int = 0
    sections: list[FileSection] = Field(default_factory=list)  # which charts to show


Card = Annotated[
    SpendingSummaryCard
    | CategoryBreakdownCard
    | BudgetProgressCard
    | BillsListCard
    | GoalProgressCard
    | TransactionsPreviewCard
    | ConfirmActionCard
    | OpenAppFlowCard
    | FileReportCard,
    Field(discriminator="type"),
]


class Suggestion(BaseModel):
    """A chip under an answer: a follow-up question, or a feature chip like Smart Deposit."""

    text: str
    type: Literal["prompt", "feature"] = "prompt"
    feature: Literal["smart_deposit", "autopay"] | None = None
