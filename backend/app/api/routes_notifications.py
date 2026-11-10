"""Alerts inbox: budget at 80% / 100%, a bill due in 3 days, unusual spending, and the weekly
summary. Reading the inbox first runs the alert check (cheap, and the public website has no
scheduler); `scripts/send_alerts.py` runs the same check for every user."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.deps import BillSourceDep, SessionDep, TodayDep, TxSourceDep, UserDep
from app.models import Notification
from app.services.notifications import (
    count_unread,
    inbox,
    link_for,
    mark_read,
    render,
    sync_notifications,
)
from app.services.user_settings import load_settings

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationLink(BaseModel):
    screen: Literal["budgets", "bills", "transactions", "insights"]
    params: dict[str, str] = Field(
        default_factory=dict, description="query parameters for that screen"
    )


class NotificationOut(BaseModel):
    id: int
    kind: Literal["budget", "bill", "unusual", "weekly_summary"]
    title: str
    body: str
    day: dt.date = Field(description="when it happened")
    read: bool
    link: NotificationLink
    data: dict[str, Any] = Field(description="the numbers behind the text (paisa)")

    @classmethod
    def of(cls, n: Notification, language: str, today: dt.date) -> NotificationOut:
        title, body = render(n, language, today)
        return cls(
            id=n.id,
            kind=n.kind,  # type: ignore[arg-type]
            title=title,
            body=body,
            day=n.day,
            read=n.read_at is not None,
            link=NotificationLink.model_validate(link_for(n)),
            data=json.loads(n.params_json),
        )


class InboxOut(BaseModel):
    items: list[NotificationOut]
    unread: int


class MarkReadIn(BaseModel):
    ids: list[int] | None = Field(None, description="omit to mark everything read")


class MarkReadOut(BaseModel):
    updated: int
    unread: int


@router.get("", response_model=InboxOut)
def get_notifications(
    request: Request,
    session: SessionDep,
    user_id: UserDep,
    source: TxSourceDep,
    bills: BillSourceDep,
    today: TodayDep,
) -> InboxOut:
    """Newest first (at most 50). New alerts are found and stored first."""
    sync_notifications(
        session, source, bills, user_id, today, getattr(request.app.state, "push", None)
    )
    language = load_settings(session, user_id).language
    return InboxOut(
        items=[NotificationOut.of(n, language, today) for n in inbox(session, user_id)],
        unread=count_unread(session, user_id),
    )


@router.post("/read", response_model=MarkReadOut)
def post_read(body: MarkReadIn, session: SessionDep, user_id: UserDep) -> MarkReadOut:
    updated = mark_read(session, user_id, body.ids)
    return MarkReadOut(updated=updated, unread=count_unread(session, user_id))
