import datetime as dt
from decimal import Decimal

import pytest

from app.money import format_npr, to_paisa, to_rupees
from app.periods import (
    CalendarSystem,
    last_n_days,
    month_period,
    previous_month_period,
    to_bs_string,
)
from app.text import normalize_merchant

# --- money -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("paisa", "expected"),
    [
        (12_500_050, "Rs. 1,25,000.50"),  # the spec's example
        (0, "Rs. 0"),
        (99, "Rs. 0.99"),
        (100_000, "Rs. 1,000"),
        (99_999_900, "Rs. 9,99,999"),
        (10_00_00_000_00, "Rs. 10,00,00,000"),  # 10 crore
        (-1_500_00, "-Rs. 1,500"),
        (54_940, "Rs. 549.40"),
    ],
)
def test_format_npr_uses_lakh_grouping(paisa: int, expected: str) -> None:
    assert format_npr(paisa) == expected


def test_format_npr_always_decimals() -> None:
    assert format_npr(150_000, always_decimals=True) == "Rs. 1,500.00"


def test_to_paisa_rounds_half_up_and_refuses_floats() -> None:
    assert to_paisa("12.345") == 1235
    assert to_paisa(Decimal("1250.5")) == 125_050
    assert to_paisa(100) == 10_000
    with pytest.raises(TypeError):
        to_paisa(12.5)  # type: ignore[arg-type]
    assert to_rupees(125_050) == Decimal("1250.50")


# --- periods -----------------------------------------------------------------------


def test_ad_month() -> None:
    p = month_period(dt.date(2026, 11, 9))
    assert (p.start, p.end, p.days, p.label) == (
        dt.date(2026, 11, 1),
        dt.date(2026, 11, 30),
        30,
        "Nov 2026",
    )
    assert month_period(dt.date(2028, 2, 10)).days == 29  # leap year


def test_bs_month_kartik_2083() -> None:
    p = month_period(dt.date(2026, 11, 9), CalendarSystem.BS)
    assert p.label == "Kartik 2083"
    assert (p.start, p.end) == (dt.date(2026, 10, 18), dt.date(2026, 11, 16))
    assert to_bs_string(dt.date(2026, 11, 9)) == "2083-07-23"


def test_bs_months_tile_the_year_including_chaitra_to_baisakh() -> None:
    """Consecutive BS months must touch with no gap or overlap, across the BS new year."""
    day = dt.date(2026, 1, 1)
    seen = []
    while day < dt.date(2027, 1, 1):
        p = month_period(day, CalendarSystem.BS)
        nxt = month_period(p.end + dt.timedelta(days=1), CalendarSystem.BS)
        assert nxt.start == p.end + dt.timedelta(days=1)
        assert 29 <= p.days <= 32
        seen.append(p.label)
        day = nxt.start
    assert "Chaitra 2082" in seen and "Baishakh 2083" in seen


def test_previous_month_and_last_n_days() -> None:
    assert previous_month_period(dt.date(2026, 1, 15)).label == "Dec 2025"
    p = last_n_days(dt.date(2026, 11, 9), 7)
    assert (p.start, p.end, p.days) == (dt.date(2026, 11, 3), dt.date(2026, 11, 9), 7)


def test_days_elapsed() -> None:
    p = month_period(dt.date(2026, 11, 9))
    assert p.days_elapsed(dt.date(2026, 11, 9)) == 9
    assert p.days_elapsed(dt.date(2026, 10, 31)) == 0
    assert p.days_elapsed(dt.date(2026, 12, 5)) == 30


# --- text --------------------------------------------------------------------------


def test_normalize_merchant() -> None:
    assert normalize_merchant("Café Dhukuti  (Jhamsikhel)") == "cafe dhukuti jhamsikhel"
    assert normalize_merchant("RATNA-MART") == "ratna mart"


def test_normalize_keeps_devanagari_intact() -> None:
    # virama (्) must survive: stripping it would turn श्रेष्ठ into nonsense
    assert normalize_merchant("श्रेष्ठ किराना") == "श्रेष्ठ किराना"
