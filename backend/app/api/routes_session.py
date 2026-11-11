"""Visitor sessions for the public website: each visitor gets a private copy of the demo data.

The session id is an unguessable random token and doubles as the user id (sent back in the
X-User-Id header). It is a demo convenience, not real authentication.
"""

from __future__ import annotations

import datetime as dt
import secrets

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.deps import SessionDep, TodayDep
from app.models import User
from app.periods import now_npt
from app.ratelimit import Limit
from app.seed import DEMO_USER_ID, ensure_faq, seed_user

router = APIRouter(tags=["session"])


class SessionOut(BaseModel):
    session_id: str
    name: str
    expires_at: dt.datetime


def cleanup_expired_sessions(session: Session, ttl_days: int) -> int:
    """Delete visitor copies older than the TTL (the shared demo user is kept)."""
    cutoff = now_npt() - dt.timedelta(days=ttl_days)
    result = session.execute(delete(User).where(User.id != DEMO_USER_ID, User.created_at < cutoff))
    return result.rowcount or 0  # type: ignore[attr-defined]


def evict_oldest_sessions(session: Session, keep: int) -> int:
    """Keep at most `keep` visitor copies, dropping the oldest. A public demo should never
    turn new visitors away; a dropped visitor just gets a fresh copy (the app renews its
    session when the server no longer knows it)."""
    visitors = select(User.id).where(User.id != DEMO_USER_ID)
    extra = (session.scalar(select(func.count()).select_from(visitors.subquery())) or 0) - keep
    if extra <= 0:
        return 0
    oldest = list(session.scalars(visitors.order_by(User.created_at, User.id).limit(extra)))
    session.execute(delete(User).where(User.id.in_(oldest)))
    return len(oldest)


@router.post("/sessions", response_model=SessionOut, status_code=201)
def create_session(request: Request, session: SessionDep, today: TodayDep) -> SessionOut:
    """Start a visitor session with a fresh copy of the demo data. Send the returned
    session_id as the X-User-Id header on every other request."""
    settings = request.app.state.settings
    ip = request.client.host if request.client else "unknown"
    verdict = request.app.state.rate_limiter.check(
        f"sessions:{ip}", [Limit(settings.rate_sessions_per_ip_per_hour, 3600)]
    )
    if not verdict.allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many new sessions from this network. Try again later.",
            headers={"Retry-After": str(verdict.retry_after_seconds)},
        )

    cleanup_expired_sessions(session, settings.session_ttl_days)
    evict_oldest_sessions(session, settings.max_sessions - 1)

    user_id = "v_" + secrets.token_urlsafe(18)
    ensure_faq(session)
    seed_user(session, user_id, anchor=today, commit=False)
    session.commit()
    user = session.get(User, user_id)
    assert user is not None  # noqa: S101
    return SessionOut(
        session_id=user_id,
        name=user.name,
        expires_at=(user.created_at + dt.timedelta(days=settings.session_ttl_days)).replace(
            tzinfo=dt.timezone(dt.timedelta(hours=5, minutes=45))
        ),
    )
