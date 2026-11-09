"""Savings-goal math: progress and the monthly saving needed to hit the deadline.
Automating the saving is Smart Deposit's job (deep link); nothing here moves money."""

from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass
from enum import StrEnum

AVG_DAYS_PER_MONTH = 365.25 / 12  # 30.4375


def _ceil_to_rupee(paisa: int) -> int:
    """Round paisa UP to a whole rupee, in integers (no float touches money)."""
    return -(-paisa // 100) * 100


class GoalState(StrEnum):
    ACTIVE = "active"
    DONE = "done"  # saved >= target
    OVERDUE = "overdue"  # deadline passed, target not reached


@dataclass(frozen=True, slots=True)
class GoalProgress:
    target_paisa: int
    saved_paisa: int
    remaining_paisa: int
    percent: float  # 0-100, one decimal
    days_left: int  # 0 when the deadline is today or past
    months_left: int  # whole months, a part month counts as one
    required_monthly_paisa: int  # rounded UP to a whole rupee; 0 when done
    state: GoalState


def goal_progress(
    *, target_paisa: int, saved_paisa: int, deadline: dt.date, today: dt.date
) -> GoalProgress:
    if target_paisa <= 0:
        raise ValueError("goal target must be positive")
    saved = max(saved_paisa, 0)
    remaining = max(target_paisa - saved, 0)
    percent = round(min(saved * 100 / target_paisa, 100.0), 1)
    days_left = max((deadline - today).days, 0)
    months_left = math.ceil(days_left / AVG_DAYS_PER_MONTH) if days_left else 0

    if remaining == 0:
        return GoalProgress(
            target_paisa, saved, 0, percent, days_left, months_left, 0, GoalState.DONE
        )
    if months_left == 0:
        # Deadline is today or past: the whole remainder is "needed now".
        need = _ceil_to_rupee(remaining)
        return GoalProgress(target_paisa, saved, remaining, percent, 0, 0, need, GoalState.OVERDUE)

    per_month = _ceil_to_rupee(-(-remaining // months_left))
    return GoalProgress(
        target_paisa, saved, remaining, percent, days_left, months_left, per_month, GoalState.ACTIVE
    )
