"""Copy the wallet replica's demo year into this backend (app/replica/), so O-Kay can talk
about the same money the replica's screens show.

    python scripts/sync_replica_demo.py                      # replica next to this project
    python scripts/sync_replica_demo.py --replica D:/replica # or somewhere else

It copies three files from the replica's backend and only rewrites their imports:
- scripts/demo_history.py -> app/replica/demo_history.py   (the year, step for step)
- app/bs_calendar.py      -> app/replica/bs_calendar.py    (its Bikram Sambat table)
- app/bills.py (NEA part) -> app/replica/nea.py            (the NEA tariff the year uses)
and the app's pinned year (app/test/fixtures/demo_year.txt) for tests/test_replica_data.py.
Run it again whenever the replica's demo year changes.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
DEFAULT_REPLICA = HERE.parents[1] / "replica"
OUT = HERE / "app" / "replica"
FIXTURE = HERE / "tests" / "fixtures" / "replica_demo_year.txt"

HEADER = (
    "# COPIED from the wallet replica by scripts/sync_replica_demo.py; do not edit here.\n"
    "# Source: {source}\n"
)


def _nea_part(bills: str) -> str:
    """The NEA tariff only: its constants, dart_round, NeaCharge and nea_month_charge."""
    start = bills.index("# Upper bound of each slab")
    keep = bills[start : bills.index("NEA_COUNTERS")]
    funcs = bills[bills.index("def dart_round") : bills.index("def nea_timing_percent")]
    return (
        '"""NEA domestic tariff (5 A meter), as the replica\'s demo year uses it."""\n'
        "import math\n"
        "from dataclasses import dataclass\n\n" + keep + "\n" + funcs.rstrip() + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--replica", type=Path, default=DEFAULT_REPLICA)
    replica: Path = parser.parse_args().replica
    src = {
        "demo_history": replica / "backend" / "scripts" / "demo_history.py",
        "bs_calendar": replica / "backend" / "app" / "bs_calendar.py",
        "bills": replica / "backend" / "app" / "bills.py",
        "fixture": replica / "app" / "test" / "fixtures" / "demo_year.txt",
    }
    for path in src.values():
        if not path.exists():
            raise SystemExit(f"not found: {path}")

    OUT.mkdir(parents=True, exist_ok=True)
    history = src["demo_history"].read_text(encoding="utf-8")
    history = history.replace(
        "from app.bills import nea_month_charge", "from app.replica.nea import nea_month_charge"
    )
    history = history.replace(
        "from app.bs_calendar import bs_from_ad", "from app.replica.bs_calendar import bs_from_ad"
    )
    history = history.replace(
        "from app.clock import NEPAL", "NEPAL = timezone(timedelta(hours=5, minutes=45))"
    )
    if re.search(r"^from app\.(?!replica)", history, re.MULTILINE):
        raise SystemExit("demo_history.py imports something new from the replica's app: update me")
    files = {
        "demo_history.py": (src["demo_history"], history),
        "bs_calendar.py": (src["bs_calendar"], src["bs_calendar"].read_text(encoding="utf-8")),
        "nea.py": (src["bills"], _nea_part(src["bills"].read_text(encoding="utf-8"))),
    }
    for name, (source, text) in files.items():
        rel = source.relative_to(replica).as_posix()
        (OUT / name).write_text(HEADER.format(source=rel) + text, encoding="utf-8", newline="\n")
    init = (
        '"""The wallet replica\'s demo account (Sita Shrestha), so O-Kay can run inside the\n'
        "replica app and talk about the money its screens show. demo_history.py, bs_calendar.py\n"
        "and nea.py are copied from the replica by scripts/sync_replica_demo.py; seed.py is\n"
        'O-Kay\'s own."""\n'
    )
    (OUT / "__init__.py").write_text(init, encoding="utf-8", newline="\n")
    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(src["fixture"].read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    print(f"copied {len(files)} files to {OUT} and the pinned year to {FIXTURE}")  # noqa: T201


if __name__ == "__main__":
    main()
