"""Per-user assistant settings: reply language, calendar, alerts, weekly-summary day and the
low-balance warning line. Missing row = defaults. Shared by the API, the chat tools and the
alert generator."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models import AssistantSettings
from app.services.forecast import LOW_BALANCE_THRESHOLD_PAISA

Weekday = Literal["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
WEEKDAYS: tuple[Weekday, ...] = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)  # index = Python's date.weekday()


class AlertSettings(BaseModel):
    budget: bool = Field(True, description="Budget at 80% and 100%")
    bills: bool = Field(True, description="A bill is due in 3 days")
    unusual: bool = Field(True, description="A category at 2x its usual spend")
    weekly_summary: bool = True


class UserSettings(BaseModel):
    language: Literal["auto", "en", "ne"] = Field(
        "auto", description="Reply language; auto follows how the user writes"
    )
    calendar: Literal["AD", "BS"] = "AD"
    alerts: AlertSettings = AlertSettings()
    weekly_summary_day: Weekday = "sunday"  # Nepal's week starts on Sunday
    low_balance_threshold_paisa: int = Field(
        LOW_BALANCE_THRESHOLD_PAISA,
        ge=0,
        le=10_000_000_00,
        description="Warn when the forecast balance drops below this",
    )


def load_settings(session: Session, user_id: str) -> UserSettings:
    row = session.get(AssistantSettings, user_id)
    return UserSettings.model_validate(json.loads(row.settings_json)) if row else UserSettings()


def save_settings(session: Session, user_id: str, settings: UserSettings) -> UserSettings:
    row = session.get(AssistantSettings, user_id)
    data = settings.model_dump_json()
    if row is None:
        session.add(AssistantSettings(user_id=user_id, settings_json=data))
    else:
        row.settings_json = data
    session.commit()
    return settings
