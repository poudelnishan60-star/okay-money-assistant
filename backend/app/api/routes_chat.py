"""Chat endpoints. POST /chat streams server-sent events:

    event: status   data: {"tool": "get_spending_summary"}            (0..n, optional)
    event: token    data: {"text": "Yo mahina khana ma "}             (1..n)
    event: done     data: {"message_id": 7, "cards": [...], "suggestions": [...],
                           "language": "rom", "error": null}           (always last)

`error` is null, "busy" (rate-limited by the AI provider), "unavailable" or "not_configured";
in each case a friendly text was already streamed as tokens.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterator
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.ai.cards import Card, Suggestion
from app.ai.chat import ChatService
from app.api.deps import SessionDep, TodayDep, UserDep
from app.models import ChatMessage
from app.periods import NPT
from app.ratelimit import Limit
from app.sources.mock import MockBillSource, MockTransactionSource

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    language: Literal["auto", "en", "ne", "rom"] = Field(
        "auto", description="Reply language: auto-detect, English, Nepali or Romanized Nepali."
    )


class ChatMessageOut(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    cards: list[Card]
    suggestions: list[Suggestion]
    language: str | None
    feedback: Literal["up", "down"] | None
    created_at: dt.datetime


class FeedbackIn(BaseModel):
    rating: Literal["up", "down"] | None = Field(description="null clears the rating")


def _sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post(
    "",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Server-sent events: status*, token+, done.",
            "content": {"text/event-stream": {}},
        },
        429: {"description": "Too many messages; see Retry-After."},
    },
)
def chat(body: ChatIn, request: Request, user_id: UserDep, today: TodayDep) -> StreamingResponse:
    """Ask O-Kay. Streams the reply, then a final event with cards and follow-up chips."""
    settings = request.app.state.settings
    limiter = request.app.state.rate_limiter
    for key, limits in (
        (
            f"chat:user:{user_id}",
            [Limit(settings.rate_chat_per_minute, 60), Limit(settings.rate_chat_per_day, 86_400)],
        ),
        (
            "chat:global",
            [
                Limit(settings.rate_chat_global_per_minute, 60),
                Limit(settings.rate_chat_global_per_hour, 3600),
            ],
        ),
    ):
        verdict = limiter.check(key, limits)
        if not verdict.allowed:
            raise HTTPException(
                status_code=429,
                detail="You're sending messages quickly. Please wait a moment and try again.",
                headers={"Retry-After": str(verdict.retry_after_seconds)},
            )

    factory = request.app.state.session_factory
    llm = request.app.state.llm

    def stream() -> Iterator[str]:
        # Own DB session: the request's one is closed once streaming starts.
        with factory() as session:
            source = MockTransactionSource(session)
            service = ChatService(
                session,
                llm,
                source,
                MockBillSource(source),
                user_id,
                today,
                history_messages=settings.chat_history_messages,
                max_tool_rounds=settings.chat_max_tool_rounds,
            )
            for ev in service.respond(body.message, body.language):
                yield _sse(ev.event, ev.data)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/history", response_model=list[ChatMessageOut])
def get_history(session: SessionDep, user_id: UserDep, limit: int = 50) -> list[ChatMessageOut]:
    """The latest messages, oldest first (for reopening the chat screen)."""
    rows = list(
        session.scalars(
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id)
            .order_by(ChatMessage.id.desc())
            .limit(max(1, min(limit, 200)))
        )
    )
    return [
        ChatMessageOut(
            id=r.id,
            role=r.role,
            content=r.content,  # type: ignore[arg-type]
            cards=json.loads(r.cards_json),
            suggestions=json.loads(r.suggestions_json),
            language=r.language,
            feedback=r.feedback,  # type: ignore[arg-type]
            created_at=r.created_at.replace(tzinfo=NPT),
        )
        for r in reversed(rows)
    ]


@router.delete("/history", status_code=204)
def clear_history(session: SessionDep, user_id: UserDep) -> Response:
    session.execute(delete(ChatMessage).where(ChatMessage.user_id == user_id))
    session.commit()
    return Response(status_code=204)


@router.put("/messages/{message_id}/feedback", status_code=204)
def set_feedback(
    message_id: int, body: FeedbackIn, session: SessionDep, user_id: UserDep
) -> Response:
    """Thumbs up / down on an answer."""
    row = session.get(ChatMessage, message_id)
    if row is None or row.user_id != user_id or row.role != "assistant":
        raise HTTPException(status_code=404, detail="message not found")
    row.feedback = body.rating
    session.commit()
    return Response(status_code=204)
