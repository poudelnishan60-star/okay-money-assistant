"""Assistant settings: reply language, calendar, alerts, the weekly-summary day and the
low-balance warning line. Stored per user (each public-site visitor has their own)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import SessionDep, UserDep
from app.services.user_settings import UserSettings, load_settings, save_settings

router = APIRouter(prefix="/me", tags=["meta"])


@router.get("/settings", response_model=UserSettings)
def get_settings_(session: SessionDep, user_id: UserDep) -> UserSettings:
    return load_settings(session, user_id)


@router.put("/settings", response_model=UserSettings)
def put_settings(body: UserSettings, session: SessionDep, user_id: UserDep) -> UserSettings:
    return save_settings(session, user_id, body)
