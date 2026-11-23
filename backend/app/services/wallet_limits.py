"""The user's use of Khalti's transaction limits (app/rules.py), worked out in code from the
wallet history: used today and this month, what is left, and whether an amount fits.

Months are AD calendar months. Today's usage also counts amounts O-Kay already offered a
button for in this message (`offered`), so "send 30,000 twice" can't pass the daily limit
as two separate checks.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domain import Direction, KycStatus, Transaction, TxnStatus, TxnType
from app.models import User
from app.rules import (
    BANK_LOAD_SERVICE,
    BANK_WITHDRAW_SERVICE,
    LIMITS,
    NO_LIMIT_SERVICES,
    OVERNIGHT_BALANCE_CAP_PAISA,
    Limit,
)
from app.sources.base import TransactionFilter, TransactionSource

_MERCHANT_TYPES = frozenset(
    {TxnType.SCAN_PAY, TxnType.BILL_PAYMENT, TxnType.TOPUP, TxnType.BOOKING}
)
_BANK_SERVICES = frozenset({BANK_LOAD_SERVICE, BANK_WITHDRAW_SERVICE})


def limit_kind(t: Transaction) -> str | None:
    """Which limit a transaction counts against (None: no limit, or none tracked here).
    A pending one counts (the money is held); a failed or reversed one and money
    returned for it don't."""
    if t.status in (TxnStatus.FAILED, TxnStatus.REVERSED) or t.reversal_of:
        return None
    if t.type is TxnType.TRANSFER:
        if t.direction is Direction.CREDIT:
            return "bank_to_wallet" if t.service == BANK_LOAD_SERVICE else None
        if t.service == BANK_WITHDRAW_SERVICE:
            return "wallet_to_bank"
        return None if t.service in _BANK_SERVICES else "wallet_to_wallet"
    if (
        t.direction is Direction.DEBIT
        and t.type in _MERCHANT_TYPES
        and t.service not in NO_LIMIT_SERVICES
    ):
        return "merchant_payment"
    return None


@dataclass(frozen=True, slots=True)
class LimitUse:
    limit: Limit
    used_today_paisa: int
    used_month_paisa: int

    @property
    def left_month_paisa(self) -> int:
        return max(0, self.limit.per_month_paisa - self.used_month_paisa)

    @property
    def left_today_paisa(self) -> int:
        """What can still go today: the daily limit, or less if the month is nearly used."""
        return min(max(0, self.limit.per_day_paisa - self.used_today_paisa), self.left_month_paisa)

    @property
    def most_now_paisa(self) -> int:
        """The biggest single transaction allowed right now."""
        return min(self.limit.per_txn_paisa, self.left_today_paisa)


@dataclass(frozen=True, slots=True)
class Usage:
    today: dt.date
    limits: dict[str, LimitUse]  # merchant_payment, bank_to_wallet, wallet_to_bank, w2w
    deposits_today: int  # money received into the wallet today (any kind)
    balance_paisa: int

    @property
    def over_overnight_cap_paisa(self) -> int:
        return max(0, self.balance_paisa - OVERNIGHT_BALANCE_CAP_PAISA)


TRACKED = ("wallet_to_wallet", "bank_to_wallet", "wallet_to_bank", "merchant_payment")


def usage(
    source: TransactionSource,
    user_id: str,
    today: dt.date,
    offered: Mapping[str, int] | None = None,
) -> Usage:
    month_start = today.replace(day=1)
    txns = source.list_transactions(user_id, TransactionFilter(start=month_start, end=today))
    day: dict[str, int] = dict.fromkeys(TRACKED, 0)
    month: dict[str, int] = dict.fromkeys(TRACKED, 0)
    deposits = 0
    for t in txns:
        on_day = t.occurred_at.date() == today
        if on_day and t.direction is Direction.CREDIT and not t.reversal_of:
            deposits += 1
        kind = limit_kind(t)
        if kind is None:
            continue
        month[kind] += t.amount_paisa
        if on_day:
            day[kind] += t.amount_paisa
    for kind, paisa in (offered or {}).items():
        if kind in day:
            day[kind] += paisa
            month[kind] += paisa
    return Usage(
        today=today,
        limits={k: LimitUse(LIMITS[k], day[k], month[k]) for k in TRACKED},
        deposits_today=deposits,
        balance_paisa=source.get_balance(user_id),
    )


@dataclass(frozen=True, slots=True)
class LimitProblem:
    rule: str  # "minimum" | "per_transaction" | "per_day" | "per_month"
    allowed_paisa: int  # the most (or, for "minimum", the least) that fits


def check_amount(use: LimitUse, amount_paisa: int) -> LimitProblem | None:
    """None if the amount fits every limit; otherwise the first one it breaks."""
    lim = use.limit
    if amount_paisa < lim.min_paisa:
        return LimitProblem("minimum", lim.min_paisa)
    if amount_paisa > lim.per_txn_paisa:
        return LimitProblem("per_transaction", lim.per_txn_paisa)
    if amount_paisa > use.left_today_paisa:
        rule = "per_month" if use.left_month_paisa < amount_paisa else "per_day"
        return LimitProblem(rule, use.left_today_paisa)
    return None


def kyc_status(session: Session, user_id: str) -> KycStatus | None:
    """The user's KYC status (None: no such user here, e.g. a test without one)."""
    user = session.get(User, user_id)
    return None if user is None else KycStatus(user.kyc_status)
