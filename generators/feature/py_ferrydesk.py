"""ferrydesk (python): an island ferry booking desk extended with manifests, rules, pricing, waitlist, retries, fees, audit."""
import random

from fx import dd
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # ferrydesk

    The booking desk of a small island ferry, as an in-process Python library (standard library only). A *sailing*
    has foot-passenger seats and a stretch of vehicle deck; a *booking* reserves seats (and deck) on one sailing.
    Run the tests with `python3 -m unittest discover -s tests`.

    ## Layout

    * `ferrydesk/model.py`: `Passenger`, `Vehicle`, `Sailing`, `Booking`.
    * `ferrydesk/pricing.py`: fares.
    * `ferrydesk/desk.py`: `FerryDesk` and `SoldOut`.

    ## Basics

    * `Passenger(name, age)`, `Vehicle(kind, length_cm)` with kind `car`, `van`, `bike` or `camper`,
      `Sailing(id, route, day, seats, deck_cm)` (`day` is a `date`).
    * `FerryDesk.add_sailing(sailing)` (`ValueError` for a duplicate id); `FerryDesk.sailing(id)`, `seats_left(id)`,
      `deck_left(id)`; unknown sailing ids raise `KeyError`.
    * `FerryDesk.book(sailing_id, passengers, vehicle=None, **options)` returns a `Booking` with ids `B001`, `B002`, ...
      (one counter for the desk). At least one passenger is required (`ValueError`). If there are not enough seats, or
      the vehicle does not fit on the remaining deck, `SoldOut` is raised and nothing changes. There are no options
      yet; unknown options raise `TypeError`.
    * Fares are in cents: 1800 per passenger aged 12 or over, 900 for ages 3 to 11, free under 3, plus the vehicle
      (car 4200, van 6800, bike 600, camper 9500). An unknown vehicle kind is a `ValueError`. The fare is stored on the
      booking as `fare_cents`.
    * `FerryDesk.booking(id)` returns a booking (`KeyError` if unknown); `FerryDesk.bookings(sailing_id=None)` lists
      bookings ordered by id.
    * `FerryDesk.cancel(booking_id)` removes a booking, frees its seats and deck and returns the refund in cents
      (the full fare). `KeyError` for an unknown booking.
''')

MODEL = '''\
"""Plain data classes of the ferry desk."""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Passenger:
    name: str
    age: int


@dataclass(frozen=True)
class Vehicle:
    kind: str  # car, van, bike, camper
    length_cm: int


@dataclass
class Sailing:
    id: str
    route: str
    day: date
    seats: int
    deck_cm: int


@dataclass
class Booking:
    id: str
    sailing_id: str
    passengers: tuple
    vehicle: object  # Vehicle or None
    fare_cents: int
    @@slot booking_fields
'''

PRICING = '''\
"""Fares in cents."""
@@uniq imports

ADULT = 1800
CHILD = 900
VEHICLES = {"car": 4200, "van": 6800, "bike": 600, "camper": 9500}


def standard_fare(passengers, vehicle):
    total = 0
    for p in passengers:
        if p.age >= 12:
            total += ADULT
        elif p.age >= 3:
            total += CHILD
    if vehicle is not None:
        if vehicle.kind not in VEHICLES:
            raise ValueError(f"unknown vehicle kind: {vehicle.kind}")
        total += VEHICLES[vehicle.kind]
    return total

@@blocks strategies
'''

DESK = '''\
"""The booking desk."""
from .model import Booking
from .pricing import standard_fare
@@uniq imports


class SoldOut(Exception):
    """Not enough seats or deck on the sailing."""

@@blocks classes

class FerryDesk:
    def __init__(self):
        self._sailings = {}
        self._bookings = {}
        self._next = 1
        @@slot init

    def add_sailing(self, sailing):
        if sailing.id in self._sailings:
            raise ValueError(f"duplicate sailing: {sailing.id}")
        self._sailings[sailing.id] = sailing

    def sailing(self, sailing_id):
        try:
            return self._sailings[sailing_id]
        except KeyError:
            raise KeyError(f"no such sailing: {sailing_id}") from None

    def seats_left(self, sailing_id):
        s = self.sailing(sailing_id)
        return s.seats - sum(len(b.passengers) for b in self._bookings.values() if b.sailing_id == sailing_id)

    def deck_left(self, sailing_id):
        s = self.sailing(sailing_id)
        return s.deck_cm - sum(b.vehicle.length_cm for b in self._bookings.values() if b.sailing_id == sailing_id and b.vehicle)

    def booking(self, booking_id):
        b = self._bookings.get(booking_id)
        @@slot booking_lookup
        if b is None:
            raise KeyError(f"no such booking: {booking_id}")
        return b

    def bookings(self, sailing_id=None):
        return [b for _, b in sorted(self._bookings.items()) if sailing_id is None or b.sailing_id == sailing_id]

    def book(self, sailing_id, passengers, vehicle=None, **opts):
        @@slot book_pre
        self.sailing(sailing_id)
        if not passengers:
            raise ValueError("at least one passenger is required")
        @@slot book_checks
        need_seats = len(passengers)
        need_deck = vehicle.length_cm if vehicle is not None else 0
        @@default capacity_check
        if need_seats > self.seats_left(sailing_id) or need_deck > self.deck_left(sailing_id):
            raise SoldOut(sailing_id)
        @@end
        @@default fare_call
        fare = standard_fare(passengers, vehicle)
        @@end
        booking = Booking(f"B{self._next:03d}", sailing_id, tuple(passengers), vehicle, fare)
        self._next += 1
        self._bookings[booking.id] = booking
        @@slot on_book
        @@slot book_record
        if opts:
            raise TypeError("unknown option(s): " + ", ".join(sorted(opts)))
        return booking

    @@default cancel_sig
    def cancel(self, booking_id):
    @@end
        @@slot cancel_pre
        b = self._bookings.pop(booking_id, None)
        if b is None:
            raise KeyError(f"no such booking: {booking_id}")
        @@default cancel_refund
        refund = b.fare_cents
        @@end
        @@slot cancel_record
        @@slot on_cancel
        return refund

    @@blocks methods
'''

INIT = '''\
"""A booking desk for a small island ferry."""
from .desk import FerryDesk, SoldOut
from .model import Booking, Passenger, Sailing, Vehicle

__all__ = ["FerryDesk", "SoldOut", "Booking", "Passenger", "Sailing", "Vehicle"]
'''

HELPERS = '''\
import unittest
from datetime import date
@@uniq imports

from ferrydesk import FerryDesk, Passenger, Sailing, SoldOut, Vehicle

CAR = Vehicle("car", 450)
VAN = Vehicle("van", 600)
BIKE = Vehicle("bike", 180)


def adult(name="Ana", age=30):
    return Passenger(name, age)


def make_desk():
    d = FerryDesk()
    d.add_sailing(Sailing("S1", "Harbour-Skerry", date(2025, 6, 14), 6, 1200))
    d.add_sailing(Sailing("S2", "Skerry-Harbour", date(2025, 6, 15), 3, 0))
    d.add_sailing(Sailing("S3", "Harbour-Skerry", date(2025, 6, 16), 6, 400))
    d.add_sailing(Sailing("BIG", "Harbour-Skerry", date(2025, 7, 1), 40, 6000))
    return d

'''

VISIBLE = HELPERS + '''
class BasicTests(unittest.TestCase):
    def test_book_and_fare(self):
        d = make_desk()
        b = d.book("S1", [adult("Ana"), adult("Bo", 10), adult("Cy", 2)], CAR)
        self.assertEqual(b.id, "B001")
        self.assertEqual(b.fare_cents, 1800 + 900 + 4200)
        self.assertEqual(d.seats_left("S1"), 3)
        self.assertEqual(d.deck_left("S1"), 750)
        self.assertEqual(d.booking("B001"), b)

    def test_sold_out(self):
        d = make_desk()
        with self.assertRaises(SoldOut):
            d.book("S2", [adult(f"P{i}") for i in range(4)])
        with self.assertRaises(SoldOut):
            d.book("S2", [adult()], BIKE)
        self.assertEqual(d.bookings(), [])

    def test_cancel(self):
        d = make_desk()
        d.book("S1", [adult()], VAN)
        self.assertEqual(d.cancel("B001"), 1800 + 6800)
        self.assertEqual(d.deck_left("S1"), 1200)
        with self.assertRaises(KeyError):
            d.cancel("B001")
    @@blocks tests
'''

HIDDEN = HELPERS + '''
class FeatureTests(unittest.TestCase):
    def test_base_rules(self):
        d = make_desk()
        with self.assertRaises(ValueError):
            d.book("S1", [])
        with self.assertRaises(KeyError):
            d.book("S9", [adult()])
        with self.assertRaises(ValueError):
            d.book("S1", [adult()], Vehicle("tractor", 300))
        with self.assertRaises(TypeError):
            d.book("S1", [adult()], colour="red")
        with self.assertRaises(ValueError):
            d.add_sailing(Sailing("S1", "x", date(2025, 1, 1), 1, 1))
        self.assertEqual(d.bookings(), [])
        a = d.book("S1", [adult("A", 40), adult("B", 3), adult("C", 2)], BIKE)
        b = d.book("S2", [adult("D")])
        self.assertEqual((a.id, a.fare_cents, b.id, b.fare_cents), ("B001", 1800 + 900 + 600, "B002", 1800))
        self.assertEqual([x.id for x in d.bookings()], ["B001", "B002"])
        self.assertEqual([x.id for x in d.bookings("S2")], ["B002"])
        with self.assertRaises(SoldOut):
            d.book("S3", [adult()], VAN)
        self.assertEqual(d.book("S1", [adult()]).id, "B003")
    @@blocks tests
'''


def make_slices(rng: random.Random):
    limits = rng.choice([(520, 700, 250, 900), (500, 650, 220, 850), (550, 720, 260, 950)])
    car, van, bike, camper = limits
    locs = rng.sample([
        ("de", "%d.%m.%Y", ".", ",", "{} €", "14.06.2025", "1.234,50 €"),
        ("fr", "%d/%m/%Y", " ", ",", "{} €", "14/06/2025", "1 234,50 €"),
        ("nl", "%d-%m-%Y", ".", ",", "€ {}", "14-06-2025", "€ 1.234,50"),
    ], 2)
    tiers = rng.choice([[(48, 100), (24, 50), (0, 0)], [(72, 100), (24, 60), (0, 20)], [(36, 90), (12, 40), (0, 0)]])
    S = []

    S.append(Slice(
        id="manifest", title="Passenger manifest", d=2,
        pitch=("The deckhands need a sorted list of who is aboard before departure.",
               "At the quay the crew wants a printable list of the passengers on a sailing."),
        reqs=("`FerryDesk.manifest(sailing_id, fmt=\"text\")` lists every passenger of the sailing's bookings ordered by name (case-insensitive), ties by booking id. Unknown sailing: `KeyError`; unknown `fmt`: `ValueError`.",
              "`fmt=\"text\"`: one line per passenger, `NAME (AGE) [BOOKING]`, each line ending with a newline; an empty manifest is the empty string.",
              "`fmt=\"csv\"`: a header line `booking,name,age` and then one line per passenger in the same order, fields separated by commas, lines ending with a newline (names never contain commas or quotes here, so no quoting is needed)."),
        code={
            "ferrydesk/desk.py::methods": '''
                def manifest(self, sailing_id, fmt="text"):
                    self.sailing(sailing_id)
                    if fmt not in ("text", "csv"):
                        raise ValueError(f"unknown manifest format: {fmt}")
                    rows = [(p, b.id) for b in self.bookings(sailing_id) for p in b.passengers]
                    rows.sort(key=lambda r: (r[0].name.lower(), r[1]))
                    if fmt == "csv":
                        return "booking,name,age\\n" + "".join(f"{bid},{p.name},{p.age}\\n" for p, bid in rows)
                    return "".join(f"{p.name} ({p.age}) [{bid}]\\n" for p, bid in rows)
            ''',
        },
        readme=dd('''
            ## Manifest

            `FerryDesk.manifest(sailing_id, fmt="text")` lists the sailing's passengers ordered by name (ignoring case), then
            booking id. `text` gives `NAME (AGE) [BOOKING]` lines, `csv` a `booking,name,age` header plus rows.
        '''),
        vtests='''
            def test_manifest_basic(self):
                d = make_desk()
                d.book("S1", [adult("Zed")])
                self.assertEqual(d.manifest("S1"), "Zed (30) [B001]\\n")
        ''',
        tests='''
            def test_manifest(self):
                d = make_desk()
                self.assertEqual(d.manifest("S1"), "")
                self.assertEqual(d.manifest("S1", fmt="csv"), "booking,name,age\\n")
                d.book("S1", [adult("bea", 41), adult("Zoe", 9)])
                d.book("S1", [adult("Adam", 33), adult("Bea", 12)])
                d.book("S2", [adult("Other")])
                self.assertEqual(d.manifest("S1"), "Adam (33) [B002]\\nbea (41) [B001]\\nBea (12) [B002]\\nZoe (9) [B001]\\n")
                self.assertEqual(d.manifest("S1", "csv"), "booking,name,age\\nB002,Adam,33\\nB001,bea,41\\nB002,Bea,12\\nB001,Zoe,9\\n")
                self.assertEqual(d.manifest("S2"), "Other (30) [B003]\\n")

            def test_manifest_errors(self):
                d = make_desk()
                with self.assertRaises(KeyError):
                    d.manifest("S9")
                with self.assertRaises(ValueError):
                    d.manifest("S1", fmt="xml")
                d.book("S1", [adult("Ana")])
                d.cancel("B001")
                self.assertEqual(d.manifest("S1"), "")
        ''',
    ))

    S.append(Slice(
        id="vehicle-rules", title="Vehicle rules", d=2,
        pitch=("Last summer a camper that was far too long got a ticket and blocked the deck.",
               "The harbour master wants bookings with oversized vehicles rejected up front."),
        reqs=(f"`book` rejects with `ValueError` a vehicle longer than its kind allows: car {car} cm, van {van} cm, bike {bike} cm, camper {camper} cm (the limit itself is fine). A vehicle with a length of 0 or less is a `ValueError` too.",
              "A booking with a vehicle needs at least one passenger aged 18 or over (`ValueError` otherwise).",
              "Rejected bookings change nothing: no booking is stored and the booking counter does not advance."),
        code={
            "ferrydesk/desk.py::book_checks": '''
                if vehicle is not None:
                    if vehicle.length_cm <= 0:
                        raise ValueError("vehicle length must be positive")
                    if vehicle.length_cm > MAX_LENGTH_CM.get(vehicle.kind, 0):
                        raise ValueError(f"{vehicle.kind} is too long: {vehicle.length_cm} cm")
                    if not any(p.age >= 18 for p in passengers):
                        raise ValueError("a vehicle needs an adult passenger")
            ''',
            "ferrydesk/desk.py::classes": f"MAX_LENGTH_CM = {{\"car\": {car}, \"van\": {van}, \"bike\": {bike}, \"camper\": {camper}}}",
        },
        readme=fmt(dd('''
            ## Vehicle rules

            Length limits (cm): car __CAR__, van __VAN__, bike __BIKE__, camper __CAMPER__; longer (or non-positive) vehicles are a
            `ValueError`, as is a vehicle booking without a passenger aged 18+. Rejected bookings change nothing.
        '''), CAR=car, VAN=van, BIKE=bike, CAMPER=camper),
        vtests='''
            def test_vehicle_adult_rule(self):
                d = make_desk()
                with self.assertRaises(ValueError):
                    d.book("S1", [adult("Kid", 15)], CAR)
        ''',
        tests=fmt('''
            def test_vehicle_limits(self):
                d = make_desk()
                for kind, limit in (("car", __CAR__), ("van", __VAN__), ("bike", __BIKE__)):
                    with self.assertRaises(ValueError):
                        d.book("S1", [adult()], Vehicle(kind, limit + 1))
                with self.assertRaises(ValueError):
                    d.book("S1", [adult()], Vehicle("camper", __CAMPER__ + 1))
                for kind, limit in (("car", __CAR__), ("van", __VAN__), ("bike", __BIKE__), ("camper", __CAMPER__)):
                    d.book("BIG", [adult()], Vehicle(kind, limit))
                for bad in (0, -50):
                    with self.assertRaises(ValueError):
                        d.book("BIG", [adult()], Vehicle("car", bad))

            def test_vehicle_needs_adult(self):
                d = make_desk()
                with self.assertRaises(ValueError):
                    d.book("S1", [adult("Teen", 17), adult("Kid", 9)], CAR)
                b = d.book("S1", [adult("Teen", 17), adult("Dad", 18)], CAR)
                self.assertEqual(b.fare_cents, 1800 * 2 + 4200)
                self.assertEqual(d.book("S1", [adult("Teen", 15)]).fare_cents, 1800)

            def test_rejections_change_nothing(self):
                d = make_desk()
                with self.assertRaises(ValueError):
                    d.book("S1", [adult("Kid", 10)], CAR)
                self.assertEqual(d.bookings(), [])
                self.assertEqual(d.book("S1", [adult()]).id, "B001")
        ''', CAR=car, VAN=van, BIKE=bike, CAMPER=camper),
    ))

    S.append(Slice(
        id="pricing", title="Pricing strategies", d=3,
        pitch=("Summer weekends need a surcharge and the family offer has to run next to the standard tariff.",
               "Fares are hard-wired; the office wants to switch between tariffs without a code change."),
        reqs=("`FerryDesk.set_pricing(name)` selects the tariff for **later** bookings (existing bookings keep their stored fare): `standard` (the default, today's fares), `peak` and `family`. An unknown name is a `ValueError` and keeps the current tariff. `FerryDesk.pricing_name` is the name in use.",
              "`peak`: the standard fare of the whole booking (people and vehicle) plus 12.5 percent, rounded half up to the cent: `(fare * 9 + 4) // 8`.",
              "`family`: children aged 3 to 11 travel free when the booking has at least two passengers aged 12 or over; otherwise (and for everyone else, and the vehicle) the standard fares apply."),
        code={
            "ferrydesk/pricing.py::strategies": '''
                def peak_fare(passengers, vehicle):
                    return (standard_fare(passengers, vehicle) * 9 + 4) // 8


                def family_fare(passengers, vehicle):
                    adults = sum(1 for p in passengers if p.age >= 12)
                    if adults >= 2:
                        passengers = [p for p in passengers if p.age >= 12 or p.age < 3]
                    return standard_fare(passengers, vehicle)


                TARIFFS = {"standard": standard_fare, "peak": peak_fare, "family": family_fare}
            ''',
            "ferrydesk/desk.py::imports": "from .pricing import TARIFFS",
            "ferrydesk/desk.py::init": 'self.pricing_name = "standard"',
            "ferrydesk/desk.py::fare_call": "fare = TARIFFS[self.pricing_name](passengers, vehicle)",
            "ferrydesk/desk.py::methods": '''
                def set_pricing(self, name):
                    if name not in TARIFFS:
                        raise ValueError(f"unknown tariff: {name}")
                    self.pricing_name = name
            ''',
        },
        readme=dd('''
            ## Pricing strategies

            `FerryDesk.set_pricing(name)` picks the tariff for later bookings: `standard`, `peak` (+12.5%, rounded half up) or
            `family` (children 3-11 free with two or more passengers aged 12+). `FerryDesk.pricing_name` shows the current one.
        '''),
        vtests='''
            def test_pricing_default(self):
                self.assertEqual(make_desk().pricing_name, "standard")
        ''',
        tests='''
            def test_pricing_tariffs(self):
                d = make_desk()
                kids = [adult("A"), adult("B", 40), adult("C", 8), adult("D", 5), adult("E", 1)]
                self.assertEqual(d.book("BIG", kids).fare_cents, 1800 * 2 + 900 * 2)
                d.set_pricing("family")
                self.assertEqual(d.pricing_name, "family")
                self.assertEqual(d.book("BIG", kids[:4]).fare_cents, 1800 * 2)
                self.assertEqual(d.book("BIG", [adult("F"), adult("G", 6)]).fare_cents, 1800 + 900)
                d.set_pricing("peak")
                b = d.book("BIG", [adult("H")], CAR)
                self.assertEqual(b.fare_cents, 6750)
                self.assertEqual(d.booking("B001").fare_cents, 1800 * 2 + 900 * 2)

            def test_pricing_rounding_and_errors(self):
                d = make_desk()
                d.set_pricing("peak")
                self.assertEqual(d.book("BIG", [adult("A", 5)]).fare_cents, 1013)
                self.assertEqual(d.book("BIG", [adult("A", 20)], BIKE).fare_cents, 2700)
                with self.assertRaises(ValueError):
                    d.set_pricing("holiday")
                self.assertEqual(d.pricing_name, "peak")
                d.set_pricing("family")
                self.assertEqual(d.book("BIG", [adult("A", 5), adult("B", 12)], BIKE).fare_cents, 900 + 1800 + 600)
        ''',
        cross={
            "vehicle-rules": {"tests": '''
                def test_family_tariff_still_needs_adult_for_vehicle(self):
                    d = make_desk()
                    d.set_pricing("family")
                    with self.assertRaises(ValueError):
                        d.book("S1", [adult("A", 17), adult("B", 16)], CAR)
            '''},
        },
    ))
    return S


APP = App(
    name="ferrydesk", lang="python", title="the ferry booking library", role="a clerk at the ferry office", key="FERRY",
    base={
        "README.md": README + "\n@@blocks features\n",
        "ferrydesk/__init__.py": INIT,
        "ferrydesk/model.py": MODEL,
        "ferrydesk/pricing.py": PRICING,
        "ferrydesk/desk.py": DESK,
        ".gitignore": "__pycache__/\n*.pyc\n",
    },
    visible={"tests/test_basic.py": VISIBLE},
    hidden={"tests/test_features.py": HIDDEN},
)
