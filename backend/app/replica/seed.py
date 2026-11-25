"""Seed one user with the wallet replica's demo account: Sita Shrestha's year (demo_history.py,
copied from the replica), so O-Kay inside the replica app talks about the same money its
screens show, to the paisa.

The year depends on the Nepal date it is generated for (the replica regenerates it on every
start). The app sends its own clock when it opens a session, so both make the same year.

Mapping (the replica's kinds -> O-Kay's types and categories):
- shop: Scan and Pay, categorised by shop (all ten are the replica's demo shops);
- send / receive: transfers to and from her five friends;
- bill: NEA (electricity), KUKL (water), Chautari Fibernet (internet) and NTC top-up;
- load: money in from her bank; bank: money out to her bank account.

Budgets and goals are O-Kay's own features, which the replica doesn't have: Sita gets one
overall budget and one savings goal, so those screens have something to show.
"""

from __future__ import annotations

import datetime as dt
import hashlib

from sqlalchemy.orm import Session

from app.domain import Category, CategorySource, Direction, KycStatus, TxnStatus, TxnType
from app.models import Budget, Goal, TransactionRow, User
from app.replica.demo_history import NAMES, Event, generate
from app.text import normalize_merchant

NAME = "Sita Shrestha"
PHONE = "9841000001"  # the replica's demoAccountPhone
NPT = dt.timezone(dt.timedelta(hours=5, minutes=45))

SHOP_CATEGORIES = {
    "Himal Momo Corner": Category.FOOD,
    "Patan Kirana Pasal": Category.GROCERIES,
    "Ason Chiya Ghar": Category.FOOD,
    "Sahara Pharmacy": Category.HEALTH,
    "Kalimati Fresh Tarkari": Category.GROCERIES,
    "Bhaktapur Juju Dhau": Category.FOOD,
    "Thamel Book Nook": Category.SHOPPING,
    "Jhamsikhel Bake House": Category.FOOD,
    "Koteshwor Hardware": Category.SHOPPING,
    "Boudha Thakali Kitchen": Category.FOOD,
}
# Biller code -> (type, service, merchant shown, subcategory)
BILLERS = {
    "nea": (TxnType.BILL_PAYMENT, "electricity", "Nepal Electricity Authority", "Electricity"),
    "kukl": (TxnType.BILL_PAYMENT, "khanepani", "KUKL water (Kathmandu valley)", "Khanepani"),
    "isp-chautari": (TxnType.BILL_PAYMENT, "internet", "Chautari Fibernet", "Internet/TV"),
    "ntc": (TxnType.TOPUP, "mobile_topup", "Nepal Telecom", None),
}


def _row_fields(e: Event) -> dict[str, object]:
    """O-Kay's fields for one of the replica's events."""
    if e.kind == "shop":
        return {
            "type": TxnType.SCAN_PAY,
            "direction": Direction.DEBIT,
            "merchant": e.title,
            "service": None,
            "category": SHOP_CATEGORIES.get(e.title, Category.OTHER),
            "subcategory": None,
            "source": CategorySource.MERCHANT,
            "remarks": f"Bill {e.bill_number}" if e.bill_number else None,
            "counterparty": None,
        }
    if e.kind in ("send", "receive"):
        return {
            "type": TxnType.TRANSFER,
            "direction": Direction.DEBIT if e.kind == "send" else Direction.CREDIT,
            "merchant": NAMES.get(e.friend or "", e.title),
            "service": None,
            "category": Category.TRANSFERS,
            "subcategory": None,
            "source": CategorySource.TYPE,
            "remarks": e.remark,
            "counterparty": e.friend,
        }
    if e.kind == "bill":
        txn_type, service, merchant, sub = BILLERS[e.code or ""]
        return {
            "type": txn_type,
            "direction": Direction.DEBIT,
            "merchant": merchant,
            "service": service,
            "category": Category.TOPUP if txn_type is TxnType.TOPUP else Category.BILLS,
            "subcategory": sub,
            "source": CategorySource.SERVICE,
            "remarks": None,
            "counterparty": PHONE if txn_type is TxnType.TOPUP else None,
        }
    # load: in from her bank; bank: out to her bank account
    return {
        "type": TxnType.TRANSFER,
        "direction": Direction.CREDIT if e.kind == "load" else Direction.DEBIT,
        "merchant": e.title,
        "service": "bank_load" if e.kind == "load" else "bank_withdraw",
        "category": Category.TRANSFERS,
        "subcategory": None,
        "source": CategorySource.TYPE,
        "remarks": None,
        "counterparty": None,
    }


def _reference(user_id: str, n: int) -> str:
    digest = hashlib.sha1(f"{user_id}:{n}".encode(), usedforsecurity=False).hexdigest().upper()
    return "R" + digest[:10]


def seed_replica_user(
    session: Session, user_id: str, now: dt.datetime, *, commit: bool = True
) -> dict[str, object]:
    """Give `user_id` Sita's year as the replica makes it for `now` (an aware datetime)."""
    events = generate(now)
    session.add(
        User(
            id=user_id,
            name=NAME,
            phone=PHONE,
            balance_hidden=False,
            kyc_status=KycStatus.VERIFIED.value,
        )
    )
    session.flush()
    prefix = "rtx_" + hashlib.sha1(user_id.encode(), usedforsecurity=False).hexdigest()[:10]
    balance = 0
    for n, e in enumerate(events, start=1):
        f = _row_fields(e)
        balance += e.delta
        merchant = str(f["merchant"])
        session.add(
            TransactionRow(
                id=f"{prefix}_{n:04d}",
                user_id=user_id,
                occurred_at=e.at.astimezone(NPT).replace(tzinfo=None),
                type=f["type"].value,  # type: ignore[attr-defined]
                direction=f["direction"].value,  # type: ignore[attr-defined]
                amount_paisa=e.paisa,
                merchant=merchant,
                merchant_key=normalize_merchant(merchant),
                service=f["service"],
                counterparty_account=f["counterparty"],
                reference=_reference(user_id, n),
                remarks=f["remarks"],
                balance_after_paisa=balance,
                category=f["category"].value,  # type: ignore[attr-defined]
                subcategory=f["subcategory"],
                category_source=f["source"].value,  # type: ignore[attr-defined]
                status=TxnStatus.SUCCESS.value,
            )
        )
    today = now.astimezone(NPT).date()
    session.add_all(
        [
            Budget(user_id=user_id, category=None, limit_paisa=25_000_00, calendar="AD"),
            Budget(user_id=user_id, category="Groceries", limit_paisa=5_000_00, calendar="AD"),
            Goal(
                user_id=user_id,
                name="Emergency fund",
                target_paisa=50_000_00,
                saved_paisa=10_000_00,
                deadline=dt.date(today.year + 1, today.month, 1),
            ),
        ]
    )
    if commit:
        session.commit()
    return {"user": user_id, "transactions": len(events), "balance_paisa": balance}
