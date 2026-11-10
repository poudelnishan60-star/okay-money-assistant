"""Find and store new alerts for every user: what a daily scheduler (cron, a cloud scheduler)
runs in production, where a push sender delivers them. The website does not need it: reading
the inbox (GET /notifications) runs the same check for that user.

    python scripts/send_alerts.py                  # today (Nepal time)
    python scripts/send_alerts.py --today 2026-11-09
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import init_db, make_engine, make_session_factory  # noqa: E402
from app.models import User  # noqa: E402
from app.periods import today_npt  # noqa: E402
from app.services.notifications import sync_notifications  # noqa: E402
from app.sources.mock import MockBillSource, MockTransactionSource  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--today", type=dt.date.fromisoformat, default=None)
    args = parser.parse_args()
    today = args.today or today_npt()

    engine = make_engine(get_settings().database_url)
    init_db(engine)
    with make_session_factory(engine)() as session:
        source = MockTransactionSource(session)
        bills = MockBillSource(source)
        total = 0
        users = list(session.scalars(select(User.id)))
        for user_id in users:
            total += len(sync_notifications(session, source, bills, user_id, today))
    print(f"{total} new alert(s) for {len(users)} user(s) on {today}")


if __name__ == "__main__":
    main()
