"""Money helpers. Amounts are integer paisa everywhere; these convert and format them."""

from decimal import ROUND_HALF_UP, Decimal


def to_paisa(rupees: Decimal | int | str) -> int:
    """Rupees -> paisa, rounding half-up to the nearest paisa. Floats are refused on purpose."""
    if isinstance(rupees, float):
        raise TypeError("pass Decimal, int or str, not float")
    value = Decimal(str(rupees)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(value * 100)


def to_rupees(paisa: int) -> Decimal:
    return (Decimal(paisa) / 100).quantize(Decimal("0.01"))


def _group_lakh(digits: str) -> str:
    """'125000' -> '1,25,000' (last three digits, then groups of two)."""
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups) + "," + tail


def format_npr(paisa: int, *, always_decimals: bool = False) -> str:
    """Format paisa as Nepali rupees with lakh grouping.

    format_npr(12500050) -> 'Rs. 1,25,000.50'
    format_npr(150000)   -> 'Rs. 1,500'       (whole rupees drop the .00)
    """
    sign = "-" if paisa < 0 else ""
    rupees, p = divmod(abs(paisa), 100)
    text = _group_lakh(str(rupees))
    if p or always_decimals:
        text += f".{p:02d}"
    return f"{sign}Rs. {text}"
