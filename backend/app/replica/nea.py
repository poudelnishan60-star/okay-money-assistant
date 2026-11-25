# COPIED from the wallet replica by scripts/sync_replica_demo.py; do not edit here.
# Source: backend/app/bills.py
"""NEA domestic tariff (5 A meter), as the replica's demo year uses it."""
import math
from dataclasses import dataclass

# Upper bound of each slab (units a month) and its energy rate in paisa per unit, 5 A meter.
# 5 A: free if the whole month is 20 units or less; otherwise the first 20 cost Rs 3 each.
NEA_SLABS = [(20, 300), (30, 650), (50, 800), (100, 950), (250, 950), (1 << 30, 1100)]
# Monthly minimum (service) charge in paisa, picked by the month's total units.
NEA_MINIMUM_5A = [3000, 5000, 5000, 7500, 10000, 15000]


def dart_round(x: float) -> int:
    """Rounds half away from zero, as Dart's round() does (Python's round() goes to even)."""
    return int(math.copysign(math.floor(abs(x) + 0.5), x))


@dataclass
class NeaCharge:
    service: int
    energy: int
    vat: int

    @property
    def total(self) -> int:
        return self.service + self.energy + self.vat


def nea_month_charge(units: int) -> NeaCharge:
    """One month's charge for a 5 A single-phase meter, with 5% VAT on the energy above 50 units."""
    slab = next(i for i, (up_to, _) in enumerate(NEA_SLABS) if units <= up_to)
    energy = vatable = start = 0
    for up_to, rate in NEA_SLABS:
        if units <= start:
            break
        n = min(units, up_to) - start
        cost = n * rate
        energy += cost
        if up_to > 50:
            vatable += cost if start >= 50 else min(max(units - 50, 0), n) * rate
        start = up_to
    if units <= 20:
        energy = 0
    return NeaCharge(NEA_MINIMUM_5A[slab], energy, dart_round(vatable * 5 / 100))
