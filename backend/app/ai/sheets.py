"""A spreadsheet (Excel or CSV) turned into a short report, worked out in code.

The model gets this report instead of the whole sheet: a statement of 99 rows is too much
for the free tier's 7,000 input tokens a minute, and the model must never add numbers up
itself. Everything here is computed with Decimal from every row:

- the header row (rows above it, like a statement's title block with the owner's name and
  phone, are left out);
- the date range, from a date column;
- money out and money in (columns like "Amount(-)", "Debit", "Amount(+)", "Credit"); a
  single "Amount" column is only totalled (whether + means spent or received varies);
- a running balance is never added up: its value after the oldest and the newest entry;
- totals by a type-like column (e.g. Scan and Pay, Transfer, Fee), the biggest payments by
  description, and totals per week (or per month for a long sheet);
- then as many of the first rows as fit.

The same figures also make a chart card for the app (sheet_report): a pie by type, week by
week bars, the biggest payments and the balance line. The model never sees the card.

Cell text is masked (phone, account and reference numbers; anything like an MPIN or OTP)
and cannot contain the tags the chat wraps files in.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.ai.cards import (
    BalancePoint,
    FilePeriod,
    FileReportCard,
    FileSlice,
    FlowItem,
    MoneyFlow,
    money_flow,
)
from app.ai.safety import mask_pii, redact_secrets
from app.money import _group_lakh

MAX_GROUPS = 10  # values listed per type column
MAX_BIGGEST = 6  # descriptions listed for money out
MAX_PERIODS = 10  # weeks or months listed
MAX_SLICES = 5  # pie slices before "Other" (the app's chart palette has five colours)
MAX_BALANCE_POINTS = 60  # points on the balance line

_NUMBER = re.compile(r"^\(?-?(?:Rs\.?|NPR|रु\.?)?\s*-?[\d,०-९]+(?:\.\d+)?\)?$", re.IGNORECASE)
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

_MONEY_OUT = re.compile(
    r"\(-\)|debit|\bdr\b|withdraw|money out|paid out|\bspent\b|expense|outflow", re.IGNORECASE
)
_MONEY_IN = re.compile(
    r"\(\+\)|credit|\bcr\b|deposit|received|money in|income|inflow", re.IGNORECASE
)
_BALANCE = re.compile(r"balance|मौज्दात", re.IGNORECASE)
_MONEY = re.compile(
    r"amount|\brs\b|npr|रु|रकम|price|total|paid|fee|charge|cost|debit|credit|balance|\(-\)|\(\+\)",
    re.IGNORECASE,
)
_ID_LIKE = re.compile(
    r"^\s*(?:s\.?\s?n\.?|sn|#|no\.?|sr\.?\s?no\.?|serial)\s*$|\bid\b|\bref|reference|txn|code"
    r"|number|\bno\b",
    re.IGNORECASE,
)
_DATE_HEADER = re.compile(r"date|time|\bday\b|मिति", re.IGNORECASE)
_TYPE_HEADER = re.compile(
    r"type|service|category|channel|mode|method|status|product|प्रकार", re.IGNORECASE
)
_TEXT_HEADER = re.compile(
    r"description|remark|particular|merchant|detail|narration|purpose|payee|name|\bto\b"
    r"|\bfrom\b|note|विवरण",
    re.IGNORECASE,
)
_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%m/%d/%Y",
    "%d %b %Y",
    "%d-%b-%Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%b %d %Y",
)


# --- cells --------------------------------------------------------------------------------


def number(value: object) -> Decimal | None:
    """A cell as a number: 1200, '1,200.50', 'Rs. 150', '(500)' (negative), '-350'."""
    if isinstance(value, bool) or value is None or isinstance(value, dt.date):
        return None
    if isinstance(value, int | float):
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    text = str(value).strip()
    if not text or not _NUMBER.match(text):
        return None
    negative = text.startswith("(") and text.endswith(")") or "-" in text
    bare = re.sub(r"(?i)rs\.?|npr|रु\.?", "", text)
    digits = re.sub(r"[^\d.]", "", bare.translate(_DEVANAGARI_DIGITS))
    if not digits or digits.count(".") > 1:
        return None
    try:
        n = Decimal(digits)
    except InvalidOperation:
        return None
    return -n if negative else n


def date(value: object) -> dt.date | None:
    """A cell as a date: Excel dates, ISO dates (with or without a time), 13/11/2026,
    13 Nov 2026, Nov 13, 2026. Day-first when ambiguous (as in Nepal)."""
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if value is None or isinstance(value, bool | int | float):
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    if not 6 <= len(text) <= 40:
        return None
    iso = re.match(r"(\d{4}-\d{2}-\d{2})(?:[T ]|$)", text)
    if iso:
        try:
            return dt.date.fromisoformat(iso.group(1))
        except ValueError:
            return None
    # "13/11/2026 14:05", "Nov 13, 2026 2:05 PM": try the text, then without the time.
    candidates = [text, re.sub(r"[ T]\d{1,2}:\d{2}(?::\d{2})?(?:\s?[AP]M)?$", "", text, flags=re.I)]
    for candidate in candidates:
        for fmt in _DATE_FORMATS:
            try:
                return dt.datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def cell(value: object) -> str:
    """Cell text as the model may see it: masked, one line, no tags."""
    if isinstance(value, dt.datetime):
        text = value.strftime("%Y-%m-%d %H:%M").removesuffix(" 00:00")
    elif isinstance(value, dt.date):
        text = value.isoformat()
    else:
        text = re.sub(r"\s+", " ", str(value)).strip()
    text, _ = redact_secrets(text)
    return mask_pii(text).replace("<", "‹").replace(">", "›")


def rupees(n: Decimal, *, prefix: bool = True) -> str:
    """Decimal -> 'Rs. 1,25,000.50' (Nepali grouping; whole rupees drop the .00)."""
    q = n.quantize(Decimal("0.01"))
    whole, _, paisa = f"{abs(q):.2f}".partition(".")
    text = _group_lakh(whole) + ("" if paisa == "00" else "." + paisa)
    sign = "-" if q < 0 else ""
    return f"{sign}Rs. {text}" if prefix else sign + text


def paisa(n: Decimal) -> int:
    return int((n * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _share(part: Decimal, whole: Decimal) -> float:
    return float((part * 100 / whole).quantize(Decimal("0.1"), ROUND_HALF_UP)) if whole else 0.0


def _day(d: dt.date) -> str:
    return f"{d.day} {d:%b %Y}"


def _short(text: str, n: int = 45) -> str:
    return text if len(text) <= n else text[: n - 1] + "…"


# --- the report ---------------------------------------------------------------------------


def _rows(n: int) -> str:
    return f"{n} row{'s' if n != 1 else ''}"


@dataclass
class _Flow:
    """A money column: 'out', 'in', or 'signed' (one amount column, whose sign may mean
    either direction, so it is only totalled)."""

    index: int
    name: str
    kind: str


@dataclass
class _Totals:
    rows: int = 0
    out: Decimal = field(default_factory=lambda: Decimal(0))
    into: Decimal = field(default_factory=lambda: Decimal(0))
    total: Decimal = field(default_factory=lambda: Decimal(0))  # signed columns

    def add(self, money: tuple[Decimal, Decimal, Decimal]) -> None:
        self.rows += 1
        self.out += money[0]
        self.into += money[1]
        self.total += money[2]

    def text(self, split: bool) -> str:
        parts = [_rows(self.rows)]
        if not split:
            parts.append(f"total {rupees(self.total)}")
        if split and self.out:
            parts.append(f"out {rupees(self.out)}")
        if split and self.into:
            parts.append(f"in {rupees(self.into)}")
        return ", ".join(parts)

    def rank(self, split: bool) -> tuple[Decimal, Decimal]:
        return (-self.out, -self.into) if split else (-abs(self.total), Decimal(0))


def _balance_mismatches(
    balance: dict[int, Decimal],
    chrono: list[int],
    money: Callable[[int], tuple[Decimal, Decimal, Decimal]],
) -> tuple[list[int], int] | None:
    """Does the running balance follow money in and out, row by row? Worked out here so the
    model never checks rows itself (seen live: it called a correct statement wrong).
    Returns the rows that don't, and how many were checked.

    Only neighbouring rows are compared, oldest first. A signed amount column may mean spent
    or received, so both readings are tried. None unless it is clear: if most rows don't
    follow, the rows are likely not in date order, and nothing is said.
    """
    steps = [(a, b) for a, b in zip(chrono, chrono[1:], strict=False) if abs(a - b) == 1]
    if not steps:
        return None

    def off(sign: int) -> list[int]:
        bad = []
        for prev, k in steps:
            out, into, signed = money(k)
            if abs(balance[prev] + into - out + sign * signed - balance[k]) > Decimal("0.01"):
                bad.append(k)
        return bad

    wrong = min(off(1), off(-1), key=len)
    if len(wrong) * 2 > len(steps):
        return None
    return wrong, len(steps)


def _balance_check(name: str, wrong: list[int], checked: int, where: Callable[[int], str]) -> str:
    head = f"Balance check (done in code, row by row): {name}"
    if not wrong:
        return f"{head} follows money in and out on every row ({_rows(checked)} checked)."
    shown = "; ".join(where(k) for k in wrong[:3])
    return (
        f"{head} does not follow money in and out on {len(wrong)} of {checked} rows "
        f"checked, for example: {shown}."
    )


def _slices(
    groups: dict[str, _Totals], value: Callable[[_Totals], Decimal], keep: int, *, fold: bool
) -> list[FileSlice]:
    """The biggest groups by `value`, largest first; with `fold`, the rest as "Other" so
    the slices add up to the whole (a pie)."""
    ranked = sorted(
        ((n, t) for n, t in groups.items() if value(t) > 0), key=lambda g: (-value(g[1]), g[0])
    )
    whole = sum((value(t) for _, t in ranked), Decimal(0))
    top, rest = ranked[:keep], ranked[keep:]
    out = [
        FileSlice(
            label=n, paisa=paisa(value(t)), share_percent=_share(value(t), whole), rows=t.rows
        )
        for n, t in top
    ]
    if fold and rest:
        other = sum((value(t) for _, t in rest), Decimal(0))
        out.append(
            FileSlice(
                label="Other",
                paisa=paisa(other),
                share_percent=_share(other, whole),
                rows=sum(t.rows for _, t in rest),
                is_other=True,
            )
        )
    return out


def _sample(items: list[int], n: int) -> list[int]:
    """At most n of them, evenly spread, always with the first and the last."""
    if len(items) <= n:
        return items
    picks = sorted({round(j * (len(items) - 1) / (n - 1)) for j in range(n)})
    return [items[j] for j in picks]


def _header_index(rows: Sequence[Sequence[object]]) -> int:
    """The first row that looks like column names: wide enough, and only text."""
    width = max((sum(c not in (None, "") for c in r) for r in rows[:50]), default=0)
    for i, row in enumerate(rows[:20]):
        filled = [c for c in row if c not in (None, "")]
        if len(filled) >= max(2, int(width * 0.6)) and all(
            number(c) is None and date(c) is None for c in filled
        ):
            return i
    return 0


def sheet_text(title: str, raw_rows: Sequence[Sequence[object]], budget: int) -> str | None:
    """The report for one sheet, at most about `budget` characters. None if it's empty."""
    report = sheet_report(title, raw_rows, budget)
    return report[0] if report else None


def sheet_report(
    title: str, raw_rows: Sequence[Sequence[object]], budget: int
) -> tuple[str, FileReportCard | None] | None:
    """The report for one sheet (see sheet_text) and, if it has something to chart, a chart
    card made from the same figures. None if the sheet is empty."""
    rows = [list(r) for r in raw_rows if any(c not in (None, "") for c in r)]
    if not rows:
        return None
    # Rows above the header (a statement's title block: name, phone, period) are left out:
    # they are mostly personal details, and the date range comes from the rows themselves.
    start = _header_index(rows)
    header = [
        cell(c) if c not in (None, "") else f"Column {i + 1}" for i, c in enumerate(rows[start])
    ]
    body = rows[start + 1 :]
    width = len(header)

    def column(i: int) -> list[object]:
        return [r[i] if i < len(r) else None for r in body]

    filled = {
        i: [(k, v) for k, v in enumerate(column(i)) if v not in (None, "")] for i in range(width)
    }
    numbers = {
        i: {k: n for k, v in filled[i] if (n := number(v)) is not None} for i in range(width)
    }
    dates = {i: {k: d for k, v in filled[i] if (d := date(v)) is not None} for i in range(width)}

    def mostly(found: dict[int, object], i: int) -> bool:
        return bool(filled[i]) and len(found) >= max(1, 0.6 * len(filled[i]))

    date_cols = [i for i in range(width) if mostly(dates[i], i)]
    date_col = next((i for i in date_cols if _DATE_HEADER.search(header[i])), None)
    if date_col is None and date_cols:
        date_col = date_cols[0]
    numeric = [i for i in range(width) if i not in date_cols and mostly(numbers[i], i)]

    def serial(i: int) -> bool:  # 1, 2, 3, ... (a row number)
        values = list(numbers[i].values())
        return len(values) > 2 and all(v == j + values[0] for j, v in enumerate(values))

    ids = [
        i
        for i in numeric
        if (_ID_LIKE.search(header[i]) and not _MONEY.search(header[i])) or serial(i)
    ]
    balances = [i for i in numeric if i not in ids and _BALANCE.search(header[i])]
    flows: list[_Flow] = []
    for i in numeric:
        if i in ids or i in balances:
            continue
        if _MONEY_OUT.search(header[i]):
            flows.append(_Flow(i, header[i], "out"))
        elif _MONEY_IN.search(header[i]):
            flows.append(_Flow(i, header[i], "in"))
    has_split = any(f.kind in ("out", "in") for f in flows)
    used = {f.index for f in flows}
    others = [i for i in numeric if i not in ids and i not in balances and i not in used]
    if not has_split:
        flows += [_Flow(i, header[i], "signed") for i in others if _MONEY.search(header[i])]
        others = [i for i in others if i not in {f.index for f in flows}]

    def money(k: int) -> tuple[Decimal, Decimal, Decimal]:
        """(out, in, signed total) of body row k; out and in are positive."""
        out = into = total = Decimal(0)
        for f in flows:
            n = numbers[f.index].get(k)
            if n is None:
                continue
            if f.kind == "out":
                out += abs(n)
            elif f.kind == "in":
                into += abs(n)
            else:
                total += n
        return out, into, total

    text_cols = [i for i in range(width) if i not in date_cols and i not in numeric and filled[i]]

    def distinct(i: int) -> int:  # on the raw text: masking makes every ID look alike
        return len({re.sub(r"\s+", " ", str(v)).strip().lower() for _, v in filled[i]})

    def type_like(i: int) -> bool:
        """A column of a few repeated values (Scan and Pay, Transfer, ...)."""
        d = distinct(i)
        if not 2 <= d <= 12 or _ID_LIKE.search(header[i]):
            return False
        if _TYPE_HEADER.search(header[i]):  # named like one: some repeats are enough
            return d < len(filled[i])
        return d <= max(2, len(filled[i]) // 3)

    types = [i for i in text_cols if type_like(i)]
    types.sort(key=lambda i: (not _TYPE_HEADER.search(header[i]), i))
    types = types[:2]
    described = [
        i
        for i in text_cols
        if i not in types and distinct(i) > 1 and not _ID_LIKE.search(header[i])
    ]
    described.sort(key=lambda i: (not _TEXT_HEADER.search(header[i]), -distinct(i)))
    desc_col = described[0] if described else None

    # -- lines -------------------------------------------------------------------------
    head = f"Sheet {title!r}: " if title else ""
    head += f"{len(body)} rows"
    chart = FileReportCard(file_name=title, rows=len(body))
    if date_col is not None and dates[date_col]:
        first, last = min(dates[date_col].values()), max(dates[date_col].values())
        head += f", dated {_day(first)} to {_day(last)}"
        chart.start, chart.end = first, last
    lines = [head + ". Columns: " + ", ".join(header) + "."]
    worked: list[str] = []

    for f in flows:
        values = list(numbers[f.index].values())
        if not values:
            continue
        if f.kind == "signed":
            plus = [v for v in values if v > 0]
            minus = [v for v in values if v < 0]
            signs = []
            if plus and minus:
                signs = [
                    f"positive amounts {rupees(sum(plus, Decimal(0)))} in {_rows(len(plus))}",
                    f"negative amounts {rupees(sum(minus, Decimal(0)))} in {_rows(len(minus))}",
                ]
            worked.append(
                f"{f.name}: total {rupees(sum(values, Decimal(0)))} over {_rows(len(values))} "
                f"({'; '.join([*signs, ''])}smallest {rupees(min(values))}, "
                f"largest {rupees(max(values))})."
            )
        else:
            total = sum((abs(v) for v in values), Decimal(0))
            label = "money out" if f.kind == "out" else "money in"
            nonzero = [v for v in values if v]
            worked.append(
                f"{f.name} ({label}): {rupees(total)} over {_rows(len(nonzero))}"
                + (f", largest {rupees(max(abs(v) for v in nonzero))}." if nonzero else ".")
            )
    if any(f.kind == "out" for f in flows) and any(f.kind == "in" for f in flows):
        all_out = sum((money(k)[0] for k in range(len(body))), Decimal(0))
        all_in = sum((money(k)[1] for k in range(len(body))), Decimal(0))
        worked.append(f"Money in minus money out: {rupees(all_in - all_out)}.")

    # The chart's measure. One amount column whose values have both signs is only totalled
    # (+ may mean spent or received), so it isn't broken down.
    signed = [f.index for f in flows if f.kind == "signed"]
    signed_values = [money(k)[2] for k in range(len(body)) if any(k in numbers[i] for i in signed)]
    if any(f.kind == "out" for f in flows):
        chart.measure = "out"
    elif any(f.kind == "in" for f in flows):
        chart.measure = "in"
    elif signed_values and (
        all(v >= 0 for v in signed_values) or all(v <= 0 for v in signed_values)
    ):
        chart.measure = "amount"
    every_row = range(len(body))
    if any(f.kind == "out" for f in flows):
        chart.money_out_paisa = paisa(sum((money(k)[0] for k in every_row), Decimal(0)))
    if any(f.kind == "in" for f in flows):
        chart.money_in_paisa = paisa(sum((money(k)[1] for k in every_row), Decimal(0)))
    if not has_split and signed_values:
        chart.total_paisa = paisa(sum(signed_values, Decimal(0)))

    def measured(t: _Totals) -> Decimal:
        if chart.measure == "out":
            return t.out
        return t.into if chart.measure == "in" else abs(t.total)

    def where(k: int) -> str:
        """A row, so the user can find it: its date and description."""
        d = dates[date_col].get(k) if date_col is not None else None
        bits = [_day(d)] if d else []
        row = body[k]
        if desc_col is not None and desc_col < len(row) and row[desc_col] not in (None, ""):
            bits.append(cell(row[desc_col]))
        return ", ".join(bits) or f"row {k + 1}"

    for i in balances:
        known = numbers[i]
        if not known:
            continue
        order = sorted(known)  # body row numbers, file order
        newest_first = False
        if date_col is not None:
            dated = [k for k in order if k in dates[date_col]]
            if len(dated) >= 2:
                newest_first = dates[date_col][dated[0]] > dates[date_col][dated[-1]]
        oldest, newest = (order[-1], order[0]) if newest_first else (order[0], order[-1])

        def when(k: int) -> str:
            d = dates[date_col].get(k) if date_col is not None else None
            return f" ({_day(d)})" if d else ""

        change = known[newest] - known[oldest]
        worked.append(
            f"{header[i]}: {rupees(known[oldest])} after the oldest entry{when(oldest)}, "
            f"{rupees(known[newest])} after the newest entry{when(newest)}, "
            f"{'down' if change < 0 else 'up'} {rupees(abs(change))} between them. It is a "
            "running balance, so it is not added up."
        )
        chrono = list(reversed(order)) if newest_first else order
        checked = _balance_mismatches(known, chrono, money) if flows else None
        if checked:
            worked.append(_balance_check(header[i], *checked, where))
        if chart.balance_column is None and len(chrono) >= 2:
            chart.balance_column = header[i]
            chart.balance = [
                BalancePoint(
                    date=dates[date_col].get(k) if date_col is not None else None,
                    paisa=paisa(known[k]),
                )
                for k in _sample(chrono, MAX_BALANCE_POINTS)
            ]
            if checked:
                chart.balance_check = "off" if checked[0] else "ok"
                chart.balance_rows_checked = checked[1]
                chart.balance_rows_off = len(checked[0])

    for i in others:
        values = list(numbers[i].values())
        worked.append(
            f"{header[i]}: total {rupees(sum(values, Decimal(0)), prefix=False)} over "
            f"{_rows(len(values))} (smallest {rupees(min(values), prefix=False)}, "
            f"largest {rupees(max(values), prefix=False)})."
        )

    if flows:
        for i in types:
            groups: dict[str, _Totals] = defaultdict(_Totals)
            for k, v in filled[i]:
                groups[_short(cell(v), 40)].add(money(k))
            ranked = sorted(groups.items(), key=lambda g: (g[1].rank(has_split), g[0]))
            shown = "; ".join(f"{n}: {t.text(has_split)}" for n, t in ranked[:MAX_GROUPS])
            more = f"; and {len(ranked) - MAX_GROUPS} more" if len(ranked) > MAX_GROUPS else ""
            worked.append(f"By {header[i]}: {shown}{more}.")
            if chart.measure and chart.type_column is None:
                chart.type_column = header[i]
                chart.by_type = _slices(groups, measured, MAX_SLICES, fold=True)
                if chart.measure == "out":
                    chart.in_by_type = _slices(groups, lambda t: t.into, MAX_SLICES, fold=True)

        if desc_col is not None:
            payees: dict[str, _Totals] = defaultdict(_Totals)
            for k, v in filled[desc_col]:
                name = re.sub(r"\d{4,}", "…", cell(v))
                payees[_short(name)].add(money(k))
            if has_split:
                biggest = sorted(
                    ((n, t) for n, t in payees.items() if t.out), key=lambda g: (-g[1].out, g[0])
                )[:MAX_BIGGEST]
                listed = [f"{n}: {rupees(t.out)} ({_rows(t.rows)})" for n, t in biggest]
                title = f"Biggest money out by {header[desc_col]}"
            else:
                biggest = sorted(
                    ((n, t) for n, t in payees.items() if t.total),
                    key=lambda g: (-abs(g[1].total), g[0]),
                )[:MAX_BIGGEST]
                listed = [f"{n}: {rupees(t.total)} ({_rows(t.rows)})" for n, t in biggest]
                title = f"Largest amounts by {header[desc_col]}"
            if listed:
                worked.append(f"{title}: " + "; ".join(listed) + ".")
            if chart.measure:
                chart.biggest_column = header[desc_col]
                chart.biggest = _slices(payees, measured, MAX_BIGGEST, fold=False)

        if date_col is not None and dates[date_col]:
            first, last = min(dates[date_col].values()), max(dates[date_col].values())
            weekly = (last - first).days <= 70
            periods: dict[dt.date, _Totals] = defaultdict(_Totals)
            for k, d in dates[date_col].items():
                start_day = d - dt.timedelta(days=d.weekday()) if weekly else d.replace(day=1)
                periods[start_day].add(money(k))
            ordered = sorted(periods.items())[-MAX_PERIODS:]

            def label(d: dt.date) -> str:
                if not weekly:
                    return f"{d:%b %Y}"
                end = d + dt.timedelta(days=6)
                return f"{d.day} {d:%b}-{end.day} {end:%b}"

            worked.append(
                ("By week (Monday to Sunday): " if weekly else "By month: ")
                + "; ".join(f"{label(d)}: {t.text(has_split)}" for d, t in ordered)
                + "."
            )
            if chart.measure:
                chart.period = "week" if weekly else "month"
                chart.periods = [
                    FilePeriod(
                        start=d,
                        label=label(d),
                        paisa=paisa(measured(t)),
                        in_paisa=paisa(t.into) if chart.measure == "out" else 0,
                    )
                    for d, t in ordered
                ]

    if worked:
        # Seen live: with only some rows listed below, a model said it "can only see 44 of
        # 99 rows" and gave no totals. So say plainly that these lines cover every row.
        lines.append(
            f"Worked out in code from all {_rows(len(body))} (complete; use these for totals):"
        )
        lines += [f"- {w}" for w in worked]

    # As many of the first rows as fit in what is left (and room for the label).
    room = budget - sum(len(x) + 1 for x in lines) - 100
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(header)
    shown = 0
    for r in body:
        line = io.StringIO()
        csv.writer(line, lineterminator="\n").writerow(
            ["" if c is None else cell(c) for c in r[:width]]
        )
        if len(out.getvalue()) + len(line.getvalue()) > room:
            break
        out.write(line.getvalue())
        shown += 1
    if shown:
        if shown == len(body):
            label = f"All {_rows(shown)}:"
        elif worked:
            label = (
                f"First {shown} of {len(body)} rows, only a sample (the worked-out lines "
                f"above cover all {len(body)} rows):"
            )
        else:
            label = f"First {shown} of {len(body)} rows (the rest didn't fit):"
        lines.append(label)
        lines.append(out.getvalue().rstrip("\n"))

    chart.flow = _flow(chart)
    chart.sections = [
        name
        for name, ok in (
            ("flow", chart.flow is not None),
            ("types", len(chart.by_type) >= 2),
            ("periods", len(chart.periods) >= 2),
            ("biggest", len(chart.biggest) >= 2),
            ("balance", len(chart.balance) >= 2),
        )
        if ok
    ]
    totals = (chart.money_in_paisa, chart.money_out_paisa, chart.total_paisa)
    charted = chart.sections or any(t is not None for t in totals)
    return "\n".join(lines), chart if charted else None


def _flow(chart: FileReportCard) -> MoneyFlow | None:
    """Money in by type -> money out by type, for the money-flow diagram. Only when every
    row's money has a type, so both sides add up to the file's own totals."""
    ins, outs = chart.money_in_paisa, chart.money_out_paisa
    if chart.measure != "out" or not ins or not outs or not chart.in_by_type:
        return None
    if sum(s.paisa for s in chart.in_by_type) != ins or sum(s.paisa for s in chart.by_type) != outs:
        return None
    return money_flow(
        [FlowItem(label=s.label, paisa=s.paisa, kind="in") for s in chart.in_by_type],
        [FlowItem(label=s.label, paisa=s.paisa, kind="out") for s in chart.by_type],
        ins,
        outs,
    )


def report_parts(text: str) -> set[str]:
    """Which parts the worked-out lines of sheet reports (sheet_text) have, so follow-up chips
    offer only questions the file can answer: "in_out", "balance", "periods", "types" and
    "biggest". Only the "Worked out in code" lines are looked at, never the rows."""
    parts: set[str] = set()
    in_block = False
    for line in text.split("\n"):
        if line.startswith("Worked out in code"):
            in_block = True
            continue
        if not (in_block and line.startswith("- ")):
            in_block = False
            continue
        body = line[2:]
        if body.startswith("Money in minus money out:"):
            parts.add("in_out")
        elif "after the oldest entry" in body:
            parts.add("balance")
        elif body.startswith(("By week (", "By month: ")):
            parts.add("periods")
        elif body.startswith("By "):
            parts.add("types")
        elif body.startswith(("Biggest money out by ", "Largest amounts by ")):
            parts.add("biggest")
    return parts
