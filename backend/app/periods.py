"""Calendar periods in Nepal time, for both AD (Gregorian) and BS (Bikram Sambat) months."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum

import nepali_datetime as nd

# Nepal is UTC+05:45 all year (no DST). A fixed offset avoids needing tzdata on Windows.
NPT = dt.timezone(dt.timedelta(hours=5, minutes=45), name="NPT")


class CalendarSystem(StrEnum):
    AD = "AD"
    BS = "BS"


@dataclass(frozen=True, slots=True)
class Period:
    """Inclusive date range [start, end]."""

    start: dt.date
    end: dt.date
    label: str

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def contains(self, day: dt.date) -> bool:
        return self.start <= day <= self.end

    def days_elapsed(self, today: dt.date) -> int:
        """Days of the period up to and including today (0 if not started, capped at days)."""
        if today < self.start:
            return 0
        return min((today - self.start).days + 1, self.days)


def now_npt() -> dt.datetime:
    """Current Nepal time as a naive datetime (the storage convention)."""
    return dt.datetime.now(NPT).replace(tzinfo=None)


def today_npt() -> dt.date:
    return now_npt().date()


def month_period(day: dt.date, calendar: CalendarSystem = CalendarSystem.AD) -> Period:
    """The AD or BS month containing `day`, as AD dates."""
    if calendar is CalendarSystem.AD:
        start = day.replace(day=1)
        next_start = (start + dt.timedelta(days=32)).replace(day=1)
        return Period(start, next_start - dt.timedelta(days=1), start.strftime("%b %Y"))

    bs = nd.date.from_datetime_date(day)
    start_bs = nd.date(bs.year, bs.month, 1)
    next_bs = nd.date(bs.year + 1, 1, 1) if bs.month == 12 else nd.date(bs.year, bs.month + 1, 1)
    start = start_bs.to_datetime_date()
    end = next_bs.to_datetime_date() - dt.timedelta(days=1)
    return Period(start, end, start_bs.strftime("%B %Y"))


def previous_month_period(day: dt.date, calendar: CalendarSystem = CalendarSystem.AD) -> Period:
    current = month_period(day, calendar)
    return month_period(current.start - dt.timedelta(days=1), calendar)


def last_n_days(today: dt.date, n: int) -> Period:
    """The n days ending today, inclusive."""
    return Period(today - dt.timedelta(days=n - 1), today, f"Last {n} days")


def to_bs_string(day: dt.date) -> str:
    """'2083-07-23' style BS date string."""
    return str(nd.date.from_datetime_date(day))
