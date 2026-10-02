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
        if opts:
            raise TypeError("unknown option(s): " + ", ".join(sorted(opts)))
        booking = Booking(f"B{self._next:03d}", sailing_id, tuple(passengers), vehicle, fare)
        self._next += 1
        self._bookings[booking.id] = booking
        @@slot on_book
        @@slot book_record
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
        ("de", "%d.%m.%Y", ".", ",", "{} \u20ac", "DD.MM.YYYY", "1.234,50 \u20ac", "14.06.2025", "1.260,00 \u20ac", "10,13 \u20ac"),
        ("fr", "%d/%m/%Y", " ", ",", "{} \u20ac", "DD/MM/YYYY", "1 234,50 \u20ac", "14/06/2025", "1 260,00 \u20ac", "10,13 \u20ac"),
        ("nl", "%d-%m-%Y", ".", ",", "\u20ac {}", "DD-MM-YYYY", "\u20ac 1.234,50", "14-06-2025", "\u20ac 1.260,00", "\u20ac 10,13"),
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
                self.assertEqual(d.book("BIG", [adult("A", 5), adult("B", 20)], BIKE).fare_cents, 900 + 1800 + 600)
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
    S.append(Slice(
        id="waitlist", title="Waiting list", d=4,
        pitch=("Popular sailings sell out and the desk keeps names on paper; people ring up daily to ask if a seat has opened.",
               "When a sailing is full we turn people away although cancellations are common."),
        reqs=("`book(..., waitlist=True)`: if the booking does not fit (seats or deck) it is not rejected but placed on the waiting list. It gets a booking id from the same counter and a fare like any booking, its `status` is `\"waiting\"`, and it uses up no seats or deck. A booking that fits is simply confirmed (`status` `\"confirmed\"`, the new default status of every booking) even when `waitlist=True`. Without the option a booking that does not fit still raises `SoldOut`.",
              "`FerryDesk.waiting(sailing_id=None)` lists the waiting bookings in the order they were made, optionally only those of one sailing. `bookings()` lists confirmed bookings only; `booking(id)` finds confirmed and waiting ones.",
              "When a confirmed booking is cancelled, the waiting bookings of **that sailing** are considered in order: each one that fits into what is free now is confirmed (status `\"confirmed\"`) and uses it up, and the next is considered with what is left. A booking that does not fit stays waiting and does not block later, smaller ones.",
              "Cancelling a waiting booking just removes it from the list and returns 0. A cancelled booking object (waiting or confirmed) has its `status` set to `\"cancelled\"`."),
        code={
            "ferrydesk/model.py::booking_fields": 'status: str = "confirmed"',
            "ferrydesk/desk.py::init": "self._waiting = []",
            "ferrydesk/desk.py::booking_lookup": '''
                if b is None:
                    b = next((w for w in self._waiting if w.id == booking_id), None)
            ''',
            "ferrydesk/desk.py::capacity_check": '''
                waiting = False
                if need_seats > self.seats_left(sailing_id) or need_deck > self.deck_left(sailing_id):
                    if not opts.get("waitlist", False):
                        raise SoldOut(sailing_id)
                    waiting = True
                opts.pop("waitlist", None)
            ''',
            "ferrydesk/desk.py::on_book": '''
                if waiting:
                    del self._bookings[booking.id]
                    booking.status = "waiting"
                    self._waiting.append(booking)
            ''',
            "ferrydesk/desk.py::cancel_pre": '''
                for w in self._waiting:
                    if w.id == booking_id:
                        self._waiting.remove(w)
                        w.status = "cancelled"
                        @@slot cancel_waiting_record
                        return 0
            ''',
            "ferrydesk/desk.py::on_cancel": '''
                b.status = "cancelled"
                for w in list(self._waiting):
                    if w.sailing_id == b.sailing_id and self._fits(w):
                        self._waiting.remove(w)
                        w.status = "confirmed"
                        self._bookings[w.id] = w
                        @@slot on_promote
            ''',
            "ferrydesk/desk.py::methods": '''
                def waiting(self, sailing_id=None):
                    return [w for w in self._waiting if sailing_id is None or w.sailing_id == sailing_id]

                def _fits(self, w):
                    deck = w.vehicle.length_cm if w.vehicle is not None else 0
                    return len(w.passengers) <= self.seats_left(w.sailing_id) and deck <= self.deck_left(w.sailing_id)
            ''',
        },
        readme=dd('''
            ## Waiting list

            `book(..., waitlist=True)` puts a booking that does not fit on the waiting list (`status` `"waiting"`, no seats
            used); everything else has status `"confirmed"`. `waiting(sailing_id=None)` lists them in booking order. When a
            confirmed booking is cancelled, that sailing's waiting bookings are tried in order and every one that fits is
            confirmed; cancelling a waiting booking returns 0. Cancelled bookings get status `"cancelled"`.
        '''),
        vtests='''
            def test_waitlist_status(self):
                d = make_desk()
                self.assertEqual(d.book("S1", [adult()]).status, "confirmed")
        ''',
        tests='''
            def test_waitlist_basic(self):
                d = make_desk()
                a = d.book("S2", [adult("A"), adult("B")])
                w = d.book("S2", [adult("C"), adult("D")], waitlist=True)
                self.assertEqual((a.status, w.status, w.id, w.fare_cents), ("confirmed", "waiting", "B002", 3600))
                self.assertEqual(d.seats_left("S2"), 1)
                self.assertEqual([b.id for b in d.waiting()], ["B002"])
                self.assertEqual([b.id for b in d.bookings()], ["B001"])
                self.assertIs(d.booking("B002"), w)
                ok = d.book("S2", [adult("E")], waitlist=True)
                self.assertEqual(ok.status, "confirmed")
                with self.assertRaises(SoldOut):
                    d.book("S2", [adult("F")])
                with self.assertRaises(SoldOut):
                    d.book("S2", [adult("F")], waitlist=False)
                self.assertEqual(d.seats_left("S2"), 0)

            def test_waitlist_promotion_skips_what_does_not_fit(self):
                d = make_desk()
                c1 = d.book("S2", [adult("A")])
                c2 = d.book("S2", [adult("B"), adult("C")])
                wa = d.book("S2", [adult("D"), adult("E")], waitlist=True)
                wb = d.book("S2", [adult("F")], waitlist=True)
                self.assertEqual(d.cancel(c1.id), 1800)
                self.assertEqual((wa.status, wb.status), ("waiting", "confirmed"))
                self.assertEqual([b.id for b in d.waiting()], [wa.id])
                self.assertEqual(d.seats_left("S2"), 0)
                d.cancel(c2.id)
                self.assertEqual((wa.status, c1.status, c2.status), ("confirmed", "cancelled", "cancelled"))
                self.assertEqual(d.waiting(), [])
                self.assertEqual([b.id for b in d.bookings("S2")], [wa.id, wb.id])

            def test_waitlist_is_per_sailing_and_fifo(self):
                d = make_desk()
                d.add_sailing(Sailing("S5", "x", date(2025, 8, 1), 2, 0))
                full1 = d.book("S5", [adult("A"), adult("B")])
                w5 = d.book("S5", [adult("C")], waitlist=True)
                full2 = d.book("S2", [adult("D"), adult("E"), adult("F")])
                w2a = d.book("S2", [adult("G")], waitlist=True)
                w2b = d.book("S2", [adult("H")], waitlist=True)
                self.assertEqual([b.id for b in d.waiting("S2")], [w2a.id, w2b.id])
                d.cancel(full2.id)
                self.assertEqual((w5.status, w2a.status, w2b.status), ("waiting", "confirmed", "confirmed"))
                one = d.book("S2", [adult("I")])
                d.cancel(one.id)
                self.assertEqual(w5.status, "waiting")
                d.cancel(full1.id)
                self.assertEqual(w5.status, "confirmed")

            def test_waitlist_deck(self):
                d = make_desk()
                v1 = d.book("S1", [adult("A")], VAN)
                d.book("S1", [adult("B")], VAN)
                car = d.book("S1", [adult("C")], CAR, waitlist=True)
                self.assertEqual(car.status, "waiting")
                self.assertEqual(d.deck_left("S1"), 0)
                d.cancel(v1.id)
                self.assertEqual(car.status, "confirmed")
                self.assertEqual(d.deck_left("S1"), 1200 - 600 - 450)

            def test_cancel_waiting(self):
                d = make_desk()
                d.book("S2", [adult("A"), adult("B"), adult("C")])
                w = d.book("S2", [adult("D")], waitlist=True)
                self.assertEqual(d.cancel(w.id), 0)
                self.assertEqual(w.status, "cancelled")
                self.assertEqual(d.waiting(), [])
                with self.assertRaises(KeyError):
                    d.booking(w.id)
                with self.assertRaises(KeyError):
                    d.cancel(w.id)
        ''',
        cross={
            "vehicle-rules": {"tests": '''
                def test_waitlist_does_not_bypass_vehicle_rules(self):
                    d = make_desk()
                    with self.assertRaises(ValueError):
                        d.book("S3", [adult("B", 20)], Vehicle("car", 9999), waitlist=True)
                    self.assertEqual(d.waiting(), [])
            '''},
            "pricing": {
                "reqs": ("A waiting booking's fare is fixed when the booking is made (with the tariff in force then), also after it is confirmed later.",),
                "tests": '''
                    def test_waiting_fare_is_fixed_at_booking_time(self):
                        d = make_desk()
                        full = d.book("S2", [adult("A"), adult("B"), adult("C")])
                        d.set_pricing("peak")
                        w = d.book("S2", [adult("D", 5)], waitlist=True)
                        d.set_pricing("standard")
                        self.assertEqual(w.fare_cents, 1013)
                        d.cancel(full.id)
                        self.assertEqual((w.status, w.fare_cents), ("confirmed", 1013))
                '''},
        },
    ))

    S.append(Slice(
        id="idempotent", title="Safe booking retries", d=3,
        pitch=("The kiosk retries a booking when the network drops and some people end up booked twice.",
               "A retried booking request must not take a second set of seats."),
        reqs=("`book(..., request_id=KEY)`: the first call with a key behaves like a normal booking and remembers the key. Any later call with the same key returns the very same `Booking` object and changes nothing, whatever its other arguments are (even if that booking has been cancelled since).",
              "A call that fails (`SoldOut`, `ValueError`, ...) does not remember its key, so it can be retried. A key must be a non-empty string; an empty string is a `ValueError`; without the option nothing changes."),
        code={
            "ferrydesk/desk.py::init": "self._requests = {}",
            "ferrydesk/desk.py::book_pre": '''
                request_id = opts.pop("request_id", None)
                if request_id is not None:
                    if not isinstance(request_id, str) or not request_id:
                        raise ValueError("request_id must be a non-empty string")
                    if request_id in self._requests:
                        return self._requests[request_id]
            ''',
            "ferrydesk/desk.py::on_book": '''
                if request_id is not None:
                    self._requests[request_id] = booking
            ''',
        },
        readme=dd('''
            ## Safe retries

            `book(..., request_id=KEY)` returns the original `Booking` object for a repeated key without booking again; failed
            calls are not remembered; the key must be a non-empty string.
        '''),
        vtests='''
            def test_request_id_basic(self):
                d = make_desk()
                a = d.book("S1", [adult()], request_id="k")
                self.assertIs(d.book("S1", [adult()], request_id="k"), a)
        ''',
        tests='''
            def test_request_id_replay(self):
                d = make_desk()
                a = d.book("S1", [adult("A"), adult("B")], request_id="k1")
                again = d.book("S2", [adult("Z")], VAN, request_id="k1")
                self.assertIs(again, a)
                self.assertEqual(len(d.bookings()), 1)
                self.assertEqual(d.seats_left("S1"), 4)
                b = d.book("S1", [adult("C")], request_id="k2")
                self.assertEqual(b.id, "B002")
                d.cancel(a.id)
                self.assertIs(d.book("S1", [adult("A")], request_id="k1"), a)
                self.assertEqual([x.id for x in d.bookings()], ["B002"])
                self.assertEqual(d.book("S1", [adult("D")]).id, "B003")

            def test_request_id_failures_not_remembered(self):
                d = make_desk()
                with self.assertRaises(SoldOut):
                    d.book("S2", [adult(f"P{i}") for i in range(4)], request_id="k")
                b = d.book("S2", [adult("A")], request_id="k")
                self.assertEqual(b.id, "B001")
                with self.assertRaises(ValueError):
                    d.book("S1", [adult()], request_id="")
                with self.assertRaises(ValueError):
                    d.book("S1", [], request_id="other")
                self.assertEqual(d.book("S1", [adult()], request_id="other").id, "B002")
        ''',
        cross={
            "waitlist": {"tests": '''
                def test_request_id_replays_waiting_booking(self):
                    d = make_desk()
                    full = d.book("S2", [adult("A"), adult("B"), adult("C")])
                    w = d.book("S2", [adult("D")], waitlist=True, request_id="w")
                    self.assertIs(d.book("S2", [adult("D")], waitlist=True, request_id="w"), w)
                    self.assertEqual(len(d.waiting()), 1)
                    d.cancel(full.id)
                    self.assertIs(d.book("S2", [adult("D")], request_id="w"), w)
                    self.assertEqual(w.status, "confirmed")
            '''},
        },
    ))

    S.append(Slice(
        id="cancel-fees", title="Cancellation fees", d=3,
        pitch=("Right now every cancellation is refunded in full, even minutes before departure.",
               "The office wants refunds to shrink the closer to departure someone cancels."),
        reqs=("`FerryDesk.set_cancel_policy(tiers)` takes a non-empty list of `(min_hours, refund_pct)` pairs: `min_hours` an integer of at least 0, `refund_pct` an integer from 0 to 100; anything else is a `ValueError` and keeps the old policy.",
              "`cancel(booking_id, hours_before=None)`: when `hours_before` is given and a policy is set, the refund is `fare_cents * refund_pct // 100` for the tier with the largest `min_hours` that is `<= hours_before`; if no tier applies the refund is 0. With no `hours_before`, or with no policy, the refund is the full fare as before. A negative `hours_before` is a `ValueError` and cancels nothing.",
              "The tiers may be given in any order."),
        code={
            "ferrydesk/desk.py::init": "self._tiers = None",
            "ferrydesk/desk.py::cancel_sig": "def cancel(self, booking_id, hours_before=None):",
            "ferrydesk/desk.py::cancel_pre": '''
                if hours_before is not None and hours_before < 0:
                    raise ValueError("hours_before must not be negative")
            ''',
            "ferrydesk/desk.py::cancel_refund": '''
                refund = b.fare_cents
                if hours_before is not None and self._tiers is not None:
                    pct = 0
                    for min_hours, tier_pct in self._tiers:
                        if hours_before >= min_hours:
                            pct = tier_pct
                            break
                    refund = b.fare_cents * pct // 100
            ''',
            "ferrydesk/desk.py::methods": '''
                def set_cancel_policy(self, tiers):
                    tiers = list(tiers)
                    if not tiers:
                        raise ValueError("at least one tier is required")
                    for hours, pct in tiers:
                        ok = isinstance(hours, int) and isinstance(pct, int) and hours >= 0 and 0 <= pct <= 100
                        if not ok:
                            raise ValueError(f"bad tier: {(hours, pct)}")
                    self._tiers = sorted(tiers, reverse=True)
            ''',
        },
        readme=dd('''
            ## Cancellation fees

            `set_cancel_policy([(min_hours, refund_pct), ...])` and `cancel(booking_id, hours_before=None)`: the tier with the
            largest `min_hours <= hours_before` decides the refund percentage (floor of `fare * pct / 100`; 0 if no tier
            applies). Without a policy or without `hours_before` the refund is the full fare.
        '''),
        vtests='''
            def test_cancel_policy_exists(self):
                d = make_desk()
                d.set_cancel_policy([(0, 100)])
        ''',
        tests=fmt('''
            def test_cancel_tiers(self):
                d = make_desk()
                desc = sorted(__TIERS__, reverse=True)
                d.set_cancel_policy(list(reversed(desc)))
                fare = 1800 + 900 + 600
                probes = [(h, p) for h, p in desc] + [(1000, desc[0][1])]
                probes += [(desc[i + 1][0] + 1, desc[i + 1][1]) for i in range(len(desc) - 1)]
                for hours, pct in probes:
                    b = d.book("BIG", [adult("A"), adult("B", 7)], BIKE)
                    self.assertEqual(d.cancel(b.id, hours_before=hours), fare * pct // 100, (hours, pct))

            def test_cancel_default_is_full_refund(self):
                d = make_desk()
                b1 = d.book("S1", [adult()])
                b2 = d.book("S1", [adult()])
                self.assertEqual(d.cancel(b1.id, hours_before=0), 1800)
                d.set_cancel_policy([(24, 50), (0, 10)])
                self.assertEqual(d.cancel(b2.id), 1800)

            def test_cancel_policy_validation(self):
                d = make_desk()
                for bad in ([], [(1, 101)], [(-1, 50)], [(1.5, 50)], [(2, -5)]):
                    with self.assertRaises(ValueError):
                        d.set_cancel_policy(bad)
                d.set_cancel_policy([(0, 25)])
                with self.assertRaises(ValueError):
                    d.set_cancel_policy([])
                b = d.book("S1", [adult()])
                self.assertEqual(d.cancel(b.id, hours_before=3), 450)
                b = d.book("S1", [adult()])
                with self.assertRaises(ValueError):
                    d.cancel(b.id, hours_before=-1)
                self.assertEqual([x.id for x in d.bookings()], [b.id])
                d.set_cancel_policy([(24, 100)])
                self.assertEqual(d.cancel(b.id, hours_before=23), 0)
        ''', TIERS=repr(tiers)),
    ))

    S.append(Slice(
        id="audit", title="Booking trail", d=3,
        pitch=("When a passenger disputes a charge the desk cannot show what happened to the booking.",
               "Management wants a trail of what the desk did, kept in memory for the shift report."),
        reqs=("`FerryDesk.trail(booking_id=None)` returns copies of the desk's log entries, oldest first (only a booking's entries when an id is given). An entry is a dict with `n` (1 for the first entry, then +1 each), `event`, `booking` (the booking id) and `sailing` (the sailing id).",
              "`book` logs `booked` after success; `cancel` logs `cancelled`. Calls that raise log nothing."),
        code={
            "ferrydesk/desk.py::init": "self._trail = []",
            "ferrydesk/desk.py::book_record": '''
                @@default book_event
                self._log("booked", booking.id, sailing_id)
                @@end
            ''',
            "ferrydesk/desk.py::cancel_record": '''
                @@default cancel_event
                self._log("cancelled", booking_id, b.sailing_id)
                @@end
            ''',
            "ferrydesk/desk.py::methods": '''
                def _log(self, event, booking_id, sailing_id, **extra):
                    self._trail.append({"n": len(self._trail) + 1, "event": event, "booking": booking_id, "sailing": sailing_id, **extra})

                def trail(self, booking_id=None):
                    return [dict(e) for e in self._trail if booking_id is None or e["booking"] == booking_id]
            ''',
        },
        readme=dd('''
            ## Booking trail

            `FerryDesk.trail(booking_id=None)` returns copies of the log entries `{"n", "event", "booking", "sailing"}`:
            `booked` after a successful `book`, `cancelled` after a successful `cancel`.
        '''),
        vtests='''
            def test_trail_basic(self):
                d = make_desk()
                d.book("S1", [adult()])
                self.assertEqual(len(d.trail()), 1)
        ''',
        tests='''
            def core(self, entries):
                return [{k: e[k] for k in ("n", "event", "booking", "sailing")} for e in entries]

            def test_trail(self):
                d = make_desk()
                d.book("S1", [adult()])
                d.book("S2", [adult("A")])
                with self.assertRaises(SoldOut):
                    d.book("S2", [adult("B"), adult("C"), adult("D")])
                with self.assertRaises(ValueError):
                    d.book("S1", [])
                d.cancel("B001")
                with self.assertRaises(KeyError):
                    d.cancel("B001")
                self.assertEqual(self.core(d.trail()), [
                    {"n": 1, "event": "booked", "booking": "B001", "sailing": "S1"},
                    {"n": 2, "event": "booked", "booking": "B002", "sailing": "S2"},
                    {"n": 3, "event": "cancelled", "booking": "B001", "sailing": "S1"},
                ])
                self.assertEqual([e["n"] for e in d.trail("B001")], [1, 3])
                self.assertEqual(d.trail("B404"), [])
                d.trail()[0]["event"] = "tampered"
                self.assertEqual(d.trail()[0]["event"], "booked")
        ''',
        cross={
            "waitlist": {
                "reqs": ("With the waiting list: a booking that is put on the waiting list logs `waitlisted` instead of `booked`; a waiting booking that gets confirmed by a cancellation logs `promoted` (after the `cancelled` entry of the booking that made room, in promotion order); cancelling a waiting booking logs `cancelled`.",),
                "code": {
                    "ferrydesk/desk.py::book_event": 'self._log("waitlisted" if booking.status == "waiting" else "booked", booking.id, sailing_id)',
                    "ferrydesk/desk.py::on_promote": 'self._log("promoted", w.id, w.sailing_id)',
                    "ferrydesk/desk.py::cancel_waiting_record": 'self._log("cancelled", booking_id, w.sailing_id)',
                },
                "tests": '''
                    def test_trail_with_waitlist(self):
                        d = make_desk()
                        full = d.book("S2", [adult("A"), adult("B"), adult("C")])
                        w1 = d.book("S2", [adult("D")], waitlist=True)
                        w2 = d.book("S2", [adult("E")], waitlist=True)
                        d.cancel(w2.id)
                        d.cancel(full.id)
                        self.assertEqual([(e["event"], e["booking"]) for e in d.trail()], [
                            ("booked", "B001"), ("waitlisted", "B002"), ("waitlisted", "B003"),
                            ("cancelled", "B003"), ("cancelled", "B001"), ("promoted", "B002"),
                        ])
                        self.assertEqual(w1.status, "confirmed")
                '''},
            "idempotent": {"tests": '''
                def test_replay_is_not_logged(self):
                    d = make_desk()
                    d.book("S1", [adult()], request_id="k")
                    d.book("S1", [adult()], request_id="k")
                    self.assertEqual(len(d.trail()), 1)
            '''},
            "cancel-fees": {
                "reqs": ("The `cancelled` entry of a cancellation also carries `refund`: the refund in cents that `cancel` returned.",),
                "code": {"ferrydesk/desk.py::cancel_event": 'self._log("cancelled", booking_id, b.sailing_id, refund=refund)'},
                "tests": '''
                    def test_trail_records_refund(self):
                        d = make_desk()
                        d.set_cancel_policy([(24, 50), (0, 0)])
                        b = d.book("S1", [adult()])
                        d.cancel(b.id, hours_before=30)
                        self.assertEqual(d.trail()[-1], {"n": 2, "event": "cancelled", "booking": b.id, "sailing": "S1", "refund": 900})
                '''},
        },
    ))


    S.append(Slice(
        id="receipt", title="Localised receipts", d=2,
        pitch=("Our German and Dutch customers cannot read American-style amounts on their receipts.",
               "Receipts have to be printed in the customer's own number and date conventions."),
        reqs=("`FerryDesk.receipt(booking_id, locale=\"en\")` returns one line `ID | ROUTE | DATE | AMOUNT`: the booking id, the sailing's route, the sailing's day and the booking's fare, separated by ` | `. Unknown booking: `KeyError`; unknown locale: `ValueError`.",
              "The amount always has two decimals (the fare is in cents) and thousands are grouped. `en`: date `MM/DD/YYYY`, amount like `\u20ac1,260.00`.",
              *(f"`{l[0]}`: date `{l[5]}`, amount like `{l[6]}` (a fare of 126000 cents for the sailing of 14 June 2025 gives `{l[7]}` and `{l[8]}`)." for l in locs)),
        code={
            "ferrydesk/desk.py::classes": "LOCALES = {\n    \"en\": (\"%m/%d/%Y\", \",\", \".\", \"\\u20ac{}\"),\n" + "".join(f"    {l[0]!r}: ({l[1]!r}, {l[2]!r}, {l[3]!r}, {l[4]!r}),\n" for l in locs) + "}",
            "ferrydesk/desk.py::methods": '''
                def receipt(self, booking_id, locale="en"):
                    b = self.booking(booking_id)
                    if locale not in LOCALES:
                        raise ValueError(f"unknown locale: {locale}")
                    datefmt, thousands, decimal, pattern = LOCALES[locale]
                    whole, cents = divmod(b.fare_cents, 100)
                    amount = f"{whole:,}".replace(",", thousands) + decimal + f"{cents:02d}"
                    s = self.sailing(b.sailing_id)
                    return f"{b.id} | {s.route} | {s.day.strftime(datefmt)} | {pattern.format(amount)}"
            ''',
        },
        readme="## Receipts\n\n`FerryDesk.receipt(booking_id, locale=\"en\")` returns `ID | ROUTE | DATE | AMOUNT` with the date and the amount (two decimals, grouped thousands) formatted for the locale: `en`, " + ", ".join(f"`{l[0]}`" for l in locs) + ".\n",
        vtests='''
            def test_receipt_basic(self):
                d = make_desk()
                d.book("S1", [adult()])
                self.assertTrue(d.receipt("B001").startswith("B001 | Harbour-Skerry | "))
        ''',
        tests=fmt('''
            def test_receipt_formats(self):
                d = make_desk()
                d.add_sailing(Sailing("HUGE", "Harbour-Skerry", date(2025, 6, 14), 200, 0))
                d.book("HUGE", [adult(f"P{i}") for i in range(70)])
                d.book("S1", [adult("Q")])
                self.assertEqual(d.receipt("B001"), "B001 | Harbour-Skerry | 06/14/2025 | \\u20ac1,260.00")
                self.assertEqual(d.receipt("B001", locale="en"), d.receipt("B001"))
                for code, expect in __EXPECT__:
                    self.assertEqual(d.receipt("B001", locale=code), expect)
                self.assertEqual(d.receipt("B002"), "B002 | Harbour-Skerry | 06/14/2025 | \\u20ac18.00")

            def test_receipt_errors(self):
                d = make_desk()
                d.book("S1", [adult()])
                with self.assertRaises(KeyError):
                    d.receipt("B404")
                with self.assertRaises(ValueError):
                    d.receipt("B001", locale="xx")
        ''', EXPECT=repr([(l[0], "B001 | Harbour-Skerry | " + l[7] + " | " + l[8]) for l in locs])),
        cross={
            "pricing": {"tests": fmt('''
                def test_receipt_shows_peak_cents(self):
                    d = make_desk()
                    d.set_pricing("peak")
                    d.book("S1", [adult("A", 5)])
                    self.assertEqual(d.receipt("B001"), "B001 | Harbour-Skerry | 06/14/2025 | \\u20ac10.13")
                    self.assertEqual(d.receipt("B001", "__LOC__"), "B001 | Harbour-Skerry | __DATE__ | __MONEY__")
            ''', LOC=locs[0][0], DATE=locs[0][7], MONEY=locs[0][9])},
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

register_app("feature-py-ferrydesk", APP, make_slices, n=16, summary="ferry booking desk: manifest, rules, tariffs, waiting list, retries, fees, trail, receipts")
