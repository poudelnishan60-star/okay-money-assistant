# COPIED from the wallet replica by scripts/sync_replica_demo.py; do not edit here.
# Source: backend/scripts/demo_history.py
"""The demo account's year of everyday money: the same year as the app's demo data
(app/lib/data/fake/demo_history.dart), step for step. Same generator, same order of draws,
Nepal time on both; app/test/fixtures/demo_year.txt pins both to it (tests/test_demo_history.py).

generate(now) only describes the year; seed_demo.py writes it to the database.

What is real and what is estimated is listed in the Dart file: NEA bills use the real tariff,
shop and friend amounts are estimates of everyday Kathmandu prices.
"""
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone

from app.replica.nea import nea_month_charge
from app.replica.bs_calendar import bs_from_ad
NEPAL = timezone(timedelta(hours=5, minutes=45))

RAM, BIKASH, ANJALI, SUNITA, PRAKASH = '9801000002', '9851000003', '9761000004', '9841000005', '9811000006'
FRIENDS = [RAM, BIKASH, ANJALI, SUNITA, PRAKASH]
NAMES = {RAM: 'Ram Thapa', BIKASH: 'Bikash Gurung', ANJALI: 'Anjali Rai', SUNITA: 'Sunita Tamang',
         PRAKASH: 'Prakash Adhikari'}
SHOPS = {'M-1001': 'Himal Momo Corner', 'M-1002': 'Patan Kirana Pasal', 'M-1003': 'Ason Chiya Ghar',
         'M-1004': 'Sahara Pharmacy', 'M-1005': 'Kalimati Fresh Tarkari', 'M-1006': 'Bhaktapur Juju Dhau',
         'M-1007': 'Thamel Book Nook', 'M-1008': 'Jhamsikhel Bake House', 'M-1009': 'Koteshwor Hardware',
         'M-1010': 'Boudha Thakali Kitchen'}
BANKS = {'Nabil Bank': 'NABIL', 'Global IME Bank': 'GBIME'}
TOPUP = 'Top-up 984 100 0001'

# Units a month on a 5 A meter by BS month (Baishakh..Chaitra), estimates for a small household.
UNITS = [110, 120, 125, 130, 125, 110, 100, 120, 165, 175, 140, 115]
OUTS = [('Lunch', 'bill_sharing', 200, 800), ('Taxi fare', 'bill_sharing', 150, 500), ('Futsal', 'personal', 400, 1000),
        ('Movie tickets', 'personal', 400, 900), ('Birthday gift', 'personal', 1000, 3000),
        ('Chiya', 'bill_sharing', 50, 200), ('Returning the loan', 'lend_borrow', 500, 3000),
        (None, 'personal', 100, 1500)]
INS = [('Lunch share', 'bill_sharing', 200, 800), ('Momo party share', 'bill_sharing', 300, 900),
       ('Taxi share', 'bill_sharing', 100, 400), ('Returned, thanks', 'lend_borrow', 500, 3000),
       ('Movie tickets', 'bill_sharing', 300, 700)]


class Lcg:
    """Park-Miller "minimal standard" generator, the same as the app's."""

    def __init__(self, seed: int):
        self.s = seed

    def _next(self) -> int:
        self.s = self.s * 48271 % 2147483647
        return self.s

    def next_int(self, n: int) -> int:
        return (self._next() - 1) * n // 2147483646

    def next_double(self) -> float:
        return (self._next() - 1) / 2147483646

    def next_bool(self) -> bool:
        return self.next_int(2) == 1


@dataclass
class Event:
    """One of the demo account's transactions. kind: shop, send, receive, bill, load, bank."""
    at: datetime
    kind: str
    paisa: int
    title: str
    remark: str | None = None
    code: str | None = None       # shop code, biller code, bank code
    friend: str | None = None     # the other person's phone
    purpose: str | None = None
    txn_type: str | None = None   # bills: bill_pay or topup
    bill_number: str | None = None
    tell: bool = False            # the hand-written recent ones write inbox messages
    order: int = field(default=0, compare=False)

    @property
    def delta(self) -> int:
        return self.paisa if self.kind in ('receive', 'load') else -self.paisa

    def fixture_line(self) -> str:
        t = {'shop': 'qr_pay', 'send': 'p2p', 'receive': 'p2p', 'load': 'load_bank', 'bank': 'bank_withdraw'}.get(
            self.kind, self.txn_type)
        remark = f'Bill {self.bill_number}' if self.bill_number else (self.remark or '')
        return f"{self.at.astimezone(timezone.utc):%Y-%m-%dT%H:%M}Z|{t}|{self.delta}|{self.title}|{remark}"


def _same_nepal_month(a: datetime, b: datetime) -> bool:
    x, y = a.astimezone(NEPAL), b.astimezone(NEPAL)
    return (x.year, x.month) == (y.year, y.month)


def generate(now: datetime, year: bool = True) -> list[Event]:
    """The year, in the order it happened (with the loads and bank transfers it needs).
    year=False: only the hand-written last weeks (quick test databases); not the app's year."""
    rng = Lcg(2083)
    today = now.astimezone(NEPAL).date()

    def ago(days: int, h: int, m: int) -> datetime:
        return datetime.combine(today - timedelta(days=days), time(h, m), tzinfo=NEPAL).astimezone(timezone.utc)

    def pick(xs):
        return xs[rng.next_int(len(xs))]

    def rs(lo: int, hi: int, step: int = 10) -> int:
        return (lo + rng.next_int((hi - lo) // step + 1) * step) * 100

    nabil_since, gime_since = ago(364, 12, 0), ago(200, 16, 30)
    events: list[Event] = []

    def add(e: Event) -> None:
        e.order = len(events)
        events.append(e)

    def shop(code, paisa, at, bill=None):
        add(Event(at, 'shop', paisa, SHOPS[code], code=code, bill_number=bill))

    def send(friend, paisa, purpose, remark, at, tell=False):
        add(Event(at, 'send', paisa, f'To {NAMES[friend]}', remark, friend=friend, purpose=purpose, tell=tell))

    def receive(friend, paisa, purpose, remark, at, tell=False):
        add(Event(at, 'receive', paisa, f'From {NAMES[friend]}', remark, friend=friend, purpose=purpose, tell=tell))

    def bill(txn_type, paisa, title, code, at):
        add(Event(at, 'bill', paisa, title, code=code, txn_type=txn_type))

    def load(bank, paisa, at):
        add(Event(at, 'load', paisa, f'Load from {bank}', code=BANKS[bank]))

    # ---- the hand-written last weeks, unchanged
    load('Global IME Bank', 500000, ago(52, 11, 5))
    send(RAM, 300000, 'family', 'Dashain kharcha', ago(45, 18, 40), tell=True)
    bill('topup', 20000, TOPUP, 'ntc', ago(38, 8, 12))
    receive(SUNITA, 120000, 'bill_sharing', 'Picnic share', ago(27, 20, 3), tell=True)
    bill('bill_pay', 38600, 'KUKL water (Kathmandu valley)', 'kukl', ago(20, 9, 30))
    shop('M-1004', 43550, ago(12, 18, 5), 'INV-2083-1098')
    send(BIKASH, 75000, 'personal', 'Futsal', ago(14, 19, 15), tell=True)
    load('Nabil Bank', 1000000, ago(9, 10, 20))
    send(ANJALI, 150000, 'rent', 'Room rent share', ago(5, 21, 0), tell=True)
    shop('M-1001', 36000, ago(4, 13, 20))
    bill('topup', 20000, TOPUP, 'ntc', ago(3, 9, 2))
    bill('bill_pay', 121400, 'Nepal Electricity Authority', 'nea', ago(2, 10, 42))
    receive(RAM, 250000, 'bill_sharing', 'Momo party share', ago(1, 19, 15), tell=True)

    # ---- a year before and around them
    rent_day = bs_from_ad(today - timedelta(days=5))[2]
    invoice, next_topup = 1001, 360
    if year:
        load('Nabil Bank', 1000000, ago(364, 18, 30))

    for d in range(363 if year else 1, 1, -1):
        by, bm, bd = bs_from_ad(today - timedelta(days=d))

        def at(from_hour, to_hour):
            h = from_hour + rng.next_int(to_hour - from_hour)
            return ago(d, h, rng.next_int(60))

        if bd == 2 and d > 52:
            bank = 'Global IME Bank' if (d < 200 and rng.next_int(10) < 3) else 'Nabil Bank'
            amount = pick([10000, 15000, 15000, 20000]) * 100
            load(bank, amount, at(18, 21))
        if bd == 3:
            bill('bill_pay', 135000, 'Chautari Fibernet', 'isp-chautari', at(9, 21))
        if bd == 12 and d > 35:
            u = UNITS[bm - 1] + rng.next_int(31) - 15
            bill('bill_pay', nea_month_charge(u).total, 'Nepal Electricity Authority', 'nea', at(9, 17))
        if bd == 20 and d > 25:
            amount = rs(300, 700, 1)
            bill('bill_pay', amount, 'KUKL water (Kathmandu valley)', 'kukl', at(9, 17))
        if bd == rent_day and d > 10:
            send(ANJALI, 150000, 'rent', 'Room rent share', ago(d, 21, 0))
        if d <= next_topup and d > 40:
            amount = pick([100, 200, 200, 300, 500]) * 100
            bill('topup', amount, TOPUP, 'ntc', at(7, 22))
            next_topup = d - 10 - rng.next_int(5)
        if bm == 9 and bd == 14:  # Poush is picnic season
            friend = pick(FRIENDS)
            amount = rs(800, 2000, 100)
            send(friend, amount, 'bill_sharing', 'Picnic share', at(18, 21))

        if rng.next_double() < 0.25:
            amount = rs(30, 150, 5)
            shop('M-1003', amount, at(7, 10) if rng.next_bool() else at(15, 18))
        if rng.next_double() < 0.08:
            amount = (1 + rng.next_int(3)) * pick([160, 180, 200, 220]) * 100
            shop('M-1001', amount, at(12, 20))
        if rng.next_double() < 0.03:
            amount = (1 + rng.next_int(2)) * pick([550, 600, 650, 700]) * 100
            shop('M-1010', amount, at(12, 21))
        if rng.next_double() < 0.08:
            amount = rs(250, 3500, 5)
            shop('M-1002', amount, at(8, 20))
        if rng.next_double() < 0.10:
            amount = rs(80, 700, 5)
            shop('M-1005', amount, at(7, 11))
        if rng.next_double() < 0.04:
            amount = rs(120, 1800, 5)
            when = at(9, 20)
            number = None
            if rng.next_bool():
                number = f'INV-{by}-{invoice}'
                invoice += 1
            shop('M-1004', amount, when, number)
        if rng.next_double() < 0.05:
            amount = rs(90, 650, 5)
            shop('M-1008', amount, at(7, 19))
        if rng.next_double() < 0.03:
            amount = pick([150, 180, 200, 250, 300, 360, 400]) * 100
            shop('M-1006', amount, at(10, 19))
        if rng.next_double() < 0.01:
            amount = rs(300, 1600)
            shop('M-1007', amount, at(11, 19))
        if rng.next_double() < 0.008:
            amount = rs(250, 2500)
            shop('M-1009', amount, at(9, 18))

        if rng.next_double() < 0.12:
            remark, purpose, lo, hi = OUTS[rng.next_int(len(OUTS))]
            friend = pick(FRIENDS)
            amount = rs(lo, hi)
            send(friend, amount, purpose, remark, at(11, 22))
        if rng.next_double() < 0.08:
            remark, purpose, lo, hi = INS[rng.next_int(len(INS))]
            friend = pick(FRIENDS)
            amount = rs(lo, hi)
            receive(friend, amount, purpose, remark, at(11, 22))

    # Play it in time order: load before anything the balance cannot cover; move a large
    # balance to the bank at most once a month, never this month.
    events.sort(key=lambda e: (e.at, e.order))
    out: list[Event] = []
    balance = 0
    last_to_bank = None
    for e in events:
        floor = 600000 if (now - e.at).days <= 10 else 100000
        if e.delta < 0 and balance + e.delta < floor:
            short = (floor - balance - e.delta + 99) // 100
            rupees = max(5000, (short + 999) // 1000 * 1000 + pick([2000, 3000, 5000]))
            when = e.at - timedelta(minutes=20 + rng.next_int(60))
            bank = 'Global IME Bank' if (when > gime_since and rng.next_bool()) else 'Nabil Bank'
            out.append(Event(when, 'load', rupees * 100, f'Load from {bank}', code=BANKS[bank]))
            balance += rupees * 100
        out.append(e)
        balance += e.delta
        if (balance > 2500000 and e.at > nabil_since and not _same_nepal_month(e.at, now)
                and (last_to_bank is None or (e.at - last_to_bank).days > 25)):
            amount = (balance - 1200000) // 500000 * 500000
            last_to_bank = e.at + timedelta(hours=2)
            out.append(Event(last_to_bank, 'bank', amount, 'To Nabil Bank **** 4821', code='NABIL'))
            balance -= amount
    return out


def fixture_lines(events: list[Event]) -> list[str]:
    return sorted(e.fixture_line() for e in events)


if __name__ == '__main__':
    import sys
    stamp = datetime.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else datetime.now(timezone.utc)
    print('\n'.join(fixture_lines(generate(stamp))))
