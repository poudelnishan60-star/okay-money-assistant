"""FastAPI entry point. The generated OpenAPI spec (/openapi.json) is the API contract.

uvicorn app.main:app --reload
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from sqlalchemy import select

from app.api import (
    routes_bills,
    routes_budgets_goals,
    routes_insights,
    routes_meta,
    routes_transactions,
)
from app.config import Settings, get_settings
from app.db import init_db, make_engine, make_session_factory
from app.models import User


def _operation_id(route: APIRoute) -> str:
    """operationId = the route function's name, so generated clients read naturally."""
    return route.name


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(routes_meta.router)
    app.include_router(routes_transactions.router)
    app.include_router(routes_insights.router)
    app.include_router(routes_budgets_goals.budgets)
    app.include_router(routes_budgets_goals.goals)
    app.include_router(routes_budgets_goals.smart_deposits)
    app.include_router(routes_bills.router)
    return app


app = create_app()
