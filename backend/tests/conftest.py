from __future__ import annotations

import datetime as dt
import itertools
from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from app.db import init_db, make_engine, make_session_factory
from app.domain import Category, Direction, Transaction, TxnType
from app.seed import seed_database
from app.sources.mock import MockTransactionSource

ANCHOR = dt.date(2026, 11, 9)  # seeded data runs 2026-08-11 .. 2026-11-08
USER = "demo_user"


@pytest.fixture
def session() -> Iterator[Session]:
    engine = make_engine("sqlite://")
    init_db(engine)
    with make_session_factory(engine)() as s:
        yield s
    engine.dispose()


@pytest.fixture
def seeded(session: Session) -> Session:
    seed_database(session, ANCHOR)
    return session


@pytest.fixture
def source(seeded: Session) -> MockTransactionSource:
    return MockTransactionSource(seeded)


_ids = itertools.count(1)


def make_txn(
    day: dt.date | str,
    rupees: float | int,
    merchant: str = "Test Merchant",
    *,
    type: TxnType = TxnType.SCAN_PAY,
    direction: Direction = Direction.DEBIT,
    service: str | None = None,
    category: Category = Category.OTHER,
    hour: int = 12,
) -> Transaction:
    if isinstance(day, str):
        day = dt.date.fromisoformat(day)
    return Transaction(
        id=f"t{next(_ids)}",
        user_id=USER,
        occurred_at=dt.datetime.combine(day, dt.time(hour)),
        type=type,
        direction=direction,
        amount_paisa=int(round(rupees * 100)),
        merchant=merchant,
        service=service,
        category=category,
    )


@pytest.fixture
def client():
    """API client over a fresh in-memory DB seeded at ANCHOR, with 'today' pinned to ANCHOR."""
    from fastapi.testclient import TestClient

    from app.api.deps import get_today
    from app.config import Settings
    from app.main import create_app

    app = create_app(Settings(_env_file=None, database_url="sqlite://", auto_seed=False))
    app.dependency_overrides[get_today] = lambda: ANCHOR
    with TestClient(app) as c:
        with app.state.session_factory() as s:
            seed_database(s, ANCHOR)
        yield c
