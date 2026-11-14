"""FastAPI entry point. The generated OpenAPI spec (/openapi.json) is the API contract.

uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy import select

from app.ai.llm import LLMClient, build_llm_client
from app.api import (
    routes_bills,
    routes_budgets_goals,
    routes_chat,
    routes_insights,
    routes_meta,
    routes_notifications,
    routes_session,
    routes_settings,
    routes_transactions,
)
from app.config import Settings, get_settings
from app.db import init_db, make_engine, make_session_factory
from app.models import User
from app.ratelimit import RateLimiter
from app.services.notifications import NoPush, PushSender


def _operation_id(route: APIRoute) -> str:
    """operationId = the route function's name, so generated clients read naturally."""
    return route.name


def _configure_logging() -> None:
    """Our warnings and the tool-call audit line go to the console (uvicorn only sets up its
    own loggers). Prompts are never logged."""
    app_log = logging.getLogger("app")
    if not app_log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        for name, level in (("app", logging.WARNING), ("okay.audit", logging.INFO)):
            logger = logging.getLogger(name)
            logger.addHandler(handler)
            logger.setLevel(level)
            logger.propagate = False


def create_app(
    settings: Settings | None = None,
    llm: LLMClient | None = None,
    push: PushSender | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    _configure_logging()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        init_db(engine)
        if settings.auto_seed:
            from app.seed import seed_database

            with session_factory() as session:
                if session.scalar(select(User.id).limit(1)) is None:
                    seed_database(session)
        yield
        engine.dispose()

    app = FastAPI(
        title="Khalti O-Kay AI Assistant API",
        version="0.1.0",
        description=(
            "Prototype backend for the O-Kay financial assistant. Mock data only.\n\n"
            "Money is integer paisa (`*_paisa`, Rs. 1 = 100). Dates are AD `YYYY-MM-DD`; "
            "timestamps carry the Nepal offset (+05:45). Periods are inclusive."
        ),
        lifespan=lifespan,
        generate_unique_id_function=_operation_id,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.llm = llm or build_llm_client(settings)
    app.state.rate_limiter = RateLimiter()
    app.state.push = push or NoPush()  # Khalti's push service when merged into the app

    # Files come base64 in the JSON (+37%): refuse oversized bodies before reading them.
    max_body = int(settings.max_attachments * settings.max_attachment_mb * 1.4 + 1) * 1024 * 1024

    @app.middleware("http")
    async def _limit_body(request: Request, call_next):  # type: ignore[no-untyped-def]
        size = request.headers.get("content-length")
        if size and size.isdigit() and int(size) > max_body:
            return JSONResponse({"detail": "The files are too large."}, status_code=413)
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=settings.cors_origin_regex or None,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(routes_meta.router)
    app.include_router(routes_session.router)
    app.include_router(routes_settings.router)
    app.include_router(routes_chat.router)
    app.include_router(routes_transactions.router)
    app.include_router(routes_insights.router)
    app.include_router(routes_budgets_goals.budgets)
    app.include_router(routes_budgets_goals.goals)
    app.include_router(routes_budgets_goals.smart_deposits)
    app.include_router(routes_bills.router)
    app.include_router(routes_notifications.router)
    return app


app = create_app()
