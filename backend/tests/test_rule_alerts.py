"""Alerts from Khalti's rules (step 12): the balance above the overnight cap, and 80% of the
day's wallet-to-wallet limit used. Once a day each, words in English or Nepali, a switch each."""

from __future__ import annotations

import datetime as dt
import itertools
import json

from sqlalchemy.orm import Session

from app.domain import Category, Direction, TxnType
from app.models import Notification, TransactionRow
from app.services.notifications import Kind, link_for, render, sync_notifications
from app.services.user_settings import UserSettings, load_settings, save_settings
from app.sources.mock import MockBillSource, MockTransactionSource
from tests.conftest import ANCHOR, USER

NOW = dt.datetime.combine(ANCHOR, dt.time(10))
_ids = itertools.count(1)


def _add(
    session: Session,
    rupees: int,
    *,
    direction: Direction = Direction.DEBIT,
    type: TxnType = TxnType.TRANSFER,
    when: dt.datetime = NOW,
) -> None:
    balance = MockTransactionSource(session).get_balance(USER)
    paisa = rupees * 100
    session.add(
        TransactionRow(
            id=f"a_{next(_ids)}",
            user_id=USER,
            occurred_at=when,
            type=type.value,
            direction=direction.value,
            amount_paisa=paisa,
            merchant="Sita Rai",
            merchant_key="sita rai",
            balance_after_paisa=balance + (paisa if direction is Direction.CREDIT else -paisa),
            category=Category.TRANSFERS.value,
            category_source="rule_type",
        )
    )
    session.commit()


def _sync(session: Session, today: dt.date = ANCHOR) -> dict[str, list[Notification]]:
    src = MockTransactionSource(session)
    out: dict[str, list[Notification]] = {}
    for n in sync_notifications(session, src, MockBillSource(src), USER, today):
        out.setdefault(n.kind, []).append(n)
    return out


def test_the_seed_raises_neither(seeded: Session) -> None:
    new = _sync(seeded)
    assert Kind.OVERNIGHT_CAP not in new and Kind.LIMIT_NEAR not in new


def test_balance_above_the_overnight_cap(seeded: Session) -> None:
    _sync(seeded)  # the usual alerts first
    _add(seeded, 30_000, direction=Direction.CREDIT, type=TxnType.REMITTANCE)  # Rs. 51,944.86
    (cap,) = _sync(seeded)[Kind.OVERNIGHT_CAP]
    assert cap.key == f"overnight_cap:{ANCHOR}"
    assert json.loads(cap.params_json)["over_paisa"] == 1_944_86
    assert render(cap, "en", ANCHOR) == (
        "Balance above Rs. 50,000",
        "Your balance is Rs. 51,944.86, Rs. 1,944.86 over the overnight cap. Move the extra out "
        "of the wallet before the day ends.",
    )
    title, body = render(cap, "ne", ANCHOR)
    assert title == "ब्यालेन्स रु. 50,000 भन्दा बढी" and "रु. 1,944.86 बढी" in body
    assert Kind.OVERNIGHT_CAP not in _sync(seeded)  # once a day
    tomorrow = ANCHOR + dt.timedelta(days=1)
    assert len(_sync(seeded, tomorrow)[Kind.OVERNIGHT_CAP]) == 1  # still over the next day


def test_most_of_the_days_transfer_limit_used(seeded: Session) -> None:
    _sync(seeded)
    _add(seeded, 39_999)
    assert Kind.LIMIT_NEAR not in _sync(seeded)  # just under 80% of Rs. 50,000
    _add(seeded, 1)
    (near,) = _sync(seeded)[Kind.LIMIT_NEAR]
    assert render(near, "en", ANCHOR) == (
        "80% of today's transfer limit used",
        "Rs. 40,000 of Rs. 50,000 sent to other wallets today; Rs. 10,000 left.",
    )
    assert (
        render(near, "ne", ANCHOR)[1]
        == "आज अरू वालेटमा रु. 50,000 मध्ये रु. 40,000 पठाइयो; रु. 10,000 बाँकी।"
    )
    assert link_for(near) == {
        "screen": "transactions",
        "params": {
            "start": ANCHOR.isoformat(),
            "end": ANCHOR.isoformat(),
            "type": "transfer",
            "direction": "debit",
        },
    }
    _add(seeded, 5_000)
    assert Kind.LIMIT_NEAR not in _sync(seeded)  # once a day


def test_each_has_a_switch(seeded: Session) -> None:
    s = load_settings(seeded, USER)
    assert s.alerts.overnight_cap and s.alerts.limit_near  # on by default
    off = UserSettings.model_validate(
        s.model_dump()
        | {"alerts": s.alerts.model_dump() | {"overnight_cap": False, "limit_near": False}}
    )
    save_settings(seeded, USER, off)
    _add(seeded, 40_000)
    _add(seeded, 80_000, direction=Direction.CREDIT, type=TxnType.REMITTANCE)
    new = _sync(seeded)
    assert Kind.OVERNIGHT_CAP not in new and Kind.LIMIT_NEAR not in new


def test_the_settings_api_has_the_switches(make_client) -> None:
    c = make_client()
    alerts = c.get("/me/settings").json()["alerts"]
    assert alerts["overnight_cap"] is True and alerts["limit_near"] is True
