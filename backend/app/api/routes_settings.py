"""Assistant settings: reply language, calendar, alerts and the weekly-summary day.
Stored per user (each public-site visitor has their own)."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import SessionDep, UserDep
from app.models import AssistantSettings

router = APIRouter(prefix="/me", tags=["meta"])

Weekday = Literal["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]


class AlertSettings(BaseModel):
    budget: bool = Field(True, description="Budget at 80% and 100%")
    bills: bool = Field(True, description="A bill is due in 3 days")
    unusual: bool = Field(True, description="A category at 2x its usual spend")
    weekly_summary: bool = True


class SettingsOut(BaseModel):
    language: Literal["auto", "en", "ne"] = Field(
        "auto", description="Reply language; auto follows how the user writes"
    )
    calendar: Literal["AD", "BS"] = "AD"
    alerts: AlertSettings = AlertSettings()
    weekly_summary_day: Weekday = "sunday"  # Nepal's week starts on Sunday
    low_balance_threshold_paisa: int = Field(1_000_00, ge=0, le=10_000_000_00)


SettingsIn = SettingsOut


def load_settings(session: SessionDep, user_id: str) -> SettingsOut:
    row = session.get(AssistantSettings, user_id)
    return SettingsOut.model_validate(json.loads(row.settings_json)) if row else SettingsOut()


@router.get("/settings", response_model=SettingsOut)
def get_settings_(session: SessionDep, user_id: UserDep) -> SettingsOut:
    return load_settings(session, user_id)


@router.put("/settings", response_model=SettingsOut)
def put_settings(body: SettingsIn, session: SessionDep, user_id: UserDep) -> SettingsOut:
    row = session.get(AssistantSettings, user_id)
    data = body.model_dump_json()
    if row is None:
        session.add(AssistantSettings(user_id=user_id, settings_json=data))
    else:
        row.settings_json = data
    session.commit()
    return body
