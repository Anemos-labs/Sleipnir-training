"""Python libraries, theme time/money/scheduling (batch transit-a): ferry fares, parking tariff, highway tolls."""
from fx import Lib, dd, register_libs

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# ferryzones: zone fares, transfers within a window, rider discounts, peak surcharge, daily cap
# ======================================================================================================================

FZ_README = dd('''
    # skerryfare

    Fare rules of the Skerry Line ferries. All money is an `int` number of cents. All times are minutes since
    midnight of the service day (`07:30` is `450`).

    ## Zones (`skerryfare/zones.py`)

    Every port belongs to one zone (`PORTS`). `zone_of(port)` returns it; an unknown port is a `ValueError`.
    `span(a, b)` is the number of zones a trip between zones `a` and `b` touches, both ends included, whichever way
    round: `span(2, 2) == 1`, `span(1, 3) == span(3, 1) == 3`.

    `base_fare(zones)` is `240` for 1 zone, `380` for 2 zones, `500` for 3 zones and `610` for 4 or more.
    Fewer than 1 zone is a `ValueError`.

    ## Fares (`skerryfare/fares.py`)

    A **leg** is a `Leg(depart, arrive, origin, dest)`. A leg that arrives before it departs is a `ValueError`.

    `group_journeys(legs)` sorts the legs by departure time (then arrival time) and chains them into journeys. A leg
    continues the current journey when it leaves from the port where the previous leg arrived **and** it departs
    between 0 and 45 minutes (both inclusive) after that arrival. A leg that departs before the previous leg arrived
    never continues a journey. It returns a list of journeys, each a list of legs.

    `discounted(cents, rider)` applies the rider percentage (`adult` 100, `youth` 50, `senior` 60) and rounds **up**
    to the next multiple of 5 cents, for every rider type. An unknown rider is a `ValueError`.

    `journey_fare(journey, rider)`: one fare per journey, for the zones from the lowest to the highest zone of any
    port the journey visits (`base_fare(span(lowest, highest))`). If the journey's *first* leg departs in the morning
    peak (07:00 inclusive to 09:00 exclusive) a surcharge of 60 cents is added before the rider discount.

    `day_total(legs, rider)`: the sum of the journey fares of all legs, but never more than `discounted(1100, rider)`.
    No legs cost `0`.
''')

FZ_ZONES = dd('''
    """Port and zone tables for the Skerry Line ferries."""

    PORTS = {
        "Anvil Quay": 1,
        "Brack": 1,
        "Cormorant Pier": 2,
        "Dunmore": 2,
        "Eel Reach": 3,
        "Fenwick Stairs": 4,
        "Gull Hythe": 4,
        "Hallow Isle": 5,
        "Ironbridge Slip": 6,
    }

    BASE_FARES = {1: 240, 2: 380, 3: 500}
    LONG_FARE = 610


    def zone_of(port):
        try:
            return PORTS[port]
        except KeyError:
            raise ValueError(f"unknown port: {port!r}") from None


    def span(zone_a, zone_b):
        return abs(zone_a - zone_b) + 1


    def base_fare(zones):
        if zones < 1:
            raise ValueError("a trip touches at least one zone")
        return BASE_FARES.get(zones, LONG_FARE)
''')

FZ_FARES = dd('''
    from collections import namedtuple

    from .zones import base_fare, span, zone_of

    Leg = namedtuple("Leg", "depart arrive origin dest")

    TRANSFER_WINDOW = 45
    PEAK_START = 7 * 60
    PEAK_END = 9 * 60
    PEAK_SURCHARGE = 60
    DAY_CAP = 1100
    RIDER_PERCENT = {"adult": 100, "youth": 50, "senior": 60}


    def group_journeys(legs):
        journeys = []
        for leg in sorted(legs, key=lambda l: (l.depart, l.arrive)):
            if leg.arrive < leg.depart:
                raise ValueError("leg arrives before it departs")
            if journeys:
                last = journeys[-1][-1]
                gap = leg.depart - last.arrive
                if leg.origin == last.dest and 0 <= gap <= TRANSFER_WINDOW:
                    journeys[-1].append(leg)
                    continue
            journeys.append([leg])
        return journeys


    def discounted(cents, rider):
        try:
            pct = RIDER_PERCENT[rider]
        except KeyError:
            raise ValueError(f"unknown rider type: {rider!r}") from None
        units = -(-(cents * pct) // 500)  # ceil to a multiple of 5 cents
        return units * 5


    def journey_fare(journey, rider):
        zones = []
        for leg in journey:
            zones.append(zone_of(leg.origin))
            zones.append(zone_of(leg.dest))
        fare = base_fare(span(min(zones), max(zones)))
        if PEAK_START <= journey[0].depart < PEAK_END:
            fare += PEAK_SURCHARGE
        return discounted(fare, rider)


    def day_total(legs, rider):
        total = sum(journey_fare(j, rider) for j in group_journeys(legs))
        return min(total, discounted(DAY_CAP, rider))
''')

FZ_VISIBLE = dd('''
    import unittest

    from skerryfare.fares import Leg, day_total, discounted
    from skerryfare.zones import base_fare, zone_of


    class BasicTests(unittest.TestCase):
        def test_zone_lookup(self):
            self.assertEqual(zone_of("Eel Reach"), 3)

        def test_base_fare_two_zones(self):
            self.assertEqual(base_fare(2), 380)

        def test_single_leg_adult(self):
            self.assertEqual(day_total([Leg(720, 740, "Anvil Quay", "Cormorant Pier")], "adult"), 380)

        def test_youth_half(self):
            self.assertEqual(discounted(240, "youth"), 120)


    if __name__ == "__main__":
        unittest.main()
''')

FZ_HIDDEN = dd('''
    import unittest

    from skerryfare.fares import (Leg, day_total, discounted, group_journeys, journey_fare)
    from skerryfare.zones import base_fare, span, zone_of


    class Zones(unittest.TestCase):
        def test_zone_of(self):
            self.assertEqual(zone_of("Anvil Quay"), 1)
            self.assertEqual(zone_of("Dunmore"), 2)
            self.assertEqual(zone_of("Eel Reach"), 3)
            self.assertEqual(zone_of("Fenwick Stairs"), 4)
            self.assertEqual(zone_of("Gull Hythe"), 4)
            self.assertEqual(zone_of("Hallow Isle"), 5)
            self.assertEqual(zone_of("Brack"), 1)
            self.assertEqual(zone_of("Cormorant Pier"), 2)
            self.assertEqual(zone_of("Ironbridge Slip"), 6)

        def test_unknown_port(self):
            with self.assertRaises(ValueError):
                zone_of("Atlantis")

        def test_span(self):
            self.assertEqual(span(2, 2), 1)
            self.assertEqual(span(1, 3), 3)
            self.assertEqual(span(3, 1), 3)
            self.assertEqual(span(6, 1), 6)

        def test_base_fare_table(self):
            self.assertEqual([base_fare(z) for z in (1, 2, 3, 4, 5, 6, 9)], [240, 380, 500, 610, 610, 610, 610])

        def test_base_fare_invalid(self):
            for z in (0, -1):
                with self.assertRaises(ValueError):
                    base_fare(z)


    class Discounts(unittest.TestCase):
        def test_adult(self):
            self.assertEqual(discounted(240, "adult"), 240)
            self.assertEqual(discounted(670, "adult"), 670)

        def test_youth(self):
            self.assertEqual(discounted(240, "youth"), 120)
            self.assertEqual(discounted(380, "youth"), 190)
            self.assertEqual(discounted(610, "youth"), 305)
            self.assertEqual(discounted(670, "youth"), 335)

        def test_senior_rounds_up_to_five(self):
            self.assertEqual(discounted(500, "senior"), 300)
            self.assertEqual(discounted(240, "senior"), 145)
            self.assertEqual(discounted(380, "senior"), 230)
            self.assertEqual(discounted(610, "senior"), 370)
            self.assertEqual(discounted(670, "senior"), 405)

        def test_rounding_applies_to_every_rider(self):
            self.assertEqual(discounted(241, "adult"), 245)
            self.assertEqual(discounted(245, "adult"), 245)
            self.assertEqual(discounted(246, "adult"), 250)
            self.assertEqual(discounted(0, "youth"), 0)

        def test_unknown_rider(self):
            with self.assertRaises(ValueError):
                discounted(100, "toddler")


    def leg(d, a, o, t):
        return Leg(d, a, o, t)


    class Journeys(unittest.TestCase):
        def test_empty(self):
            self.assertEqual(group_journeys([]), [])

        def test_transfer_at_window_edge(self):
            a = leg(600, 630, "Anvil Quay", "Cormorant Pier")
            b = leg(675, 700, "Cormorant Pier", "Eel Reach")  # 45 minutes after arrival
            self.assertEqual(group_journeys([a, b]), [[a, b]])

        def test_transfer_just_too_late(self):
            a = leg(600, 630, "Anvil Quay", "Cormorant Pier")
            b = leg(676, 700, "Cormorant Pier", "Eel Reach")  # 46 minutes after arrival
            self.assertEqual(group_journeys([a, b]), [[a], [b]])

        def test_transfer_immediately(self):
            a = leg(600, 630, "Anvil Quay", "Cormorant Pier")
            b = leg(630, 650, "Cormorant Pier", "Eel Reach")
            self.assertEqual(group_journeys([a, b]), [[a, b]])

        def test_other_port_is_new_journey(self):
            a = leg(600, 630, "Anvil Quay", "Cormorant Pier")
            b = leg(635, 650, "Dunmore", "Eel Reach")
            self.assertEqual(group_journeys([a, b]), [[a], [b]])

        def test_departing_before_arrival_is_new_journey(self):
            a = leg(600, 630, "Anvil Quay", "Cormorant Pier")
            b = leg(625, 650, "Cormorant Pier", "Eel Reach")
            self.assertEqual(group_journeys([a, b]), [[a], [b]])

        def test_unsorted_input(self):
            a = leg(600, 630, "Anvil Quay", "Cormorant Pier")
            b = leg(640, 660, "Cormorant Pier", "Eel Reach")
            c = leg(900, 920, "Eel Reach", "Fenwick Stairs")
            self.assertEqual(group_journeys([c, b, a]), [[a, b], [c]])

        def test_three_legs_chain(self):
            a = leg(600, 620, "Anvil Quay", "Brack")
            b = leg(640, 660, "Brack", "Cormorant Pier")
            c = leg(700, 720, "Cormorant Pier", "Fenwick Stairs")
            self.assertEqual(group_journeys([a, b, c]), [[a, b, c]])

        def test_each_gap_is_measured_from_previous_leg(self):
            a = leg(600, 620, "Anvil Quay", "Brack")
            b = leg(660, 700, "Brack", "Cormorant Pier")
            c = leg(740, 760, "Cormorant Pier", "Dunmore")
            self.assertEqual(group_journeys([a, b, c]), [[a, b, c]])

        def test_comparison_is_with_the_latest_leg_of_the_latest_journey(self):
            a = leg(600, 620, "Anvil Quay", "Brack")
            x = leg(700, 720, "Dunmore", "Eel Reach")
            y = leg(730, 750, "Eel Reach", "Fenwick Stairs")
            z = leg(760, 770, "Brack", "Anvil Quay")
            self.assertEqual(group_journeys([a, x, y]), [[a], [x, y]])
            self.assertEqual(group_journeys([a, x, y, z]), [[a], [x, y], [z]])

        def test_zero_length_leg_is_allowed(self):
            a = leg(600, 600, "Anvil Quay", "Brack")
            self.assertEqual(group_journeys([a]), [[a]])

        def test_arrival_before_departure(self):
            with self.assertRaises(ValueError):
                group_journeys([leg(700, 690, "Anvil Quay", "Brack")])


    class JourneyFare(unittest.TestCase):
        def test_single_zone(self):
            self.assertEqual(journey_fare([leg(720, 730, "Anvil Quay", "Brack")], "adult"), 240)

        def test_zone_spans(self):
            self.assertEqual(journey_fare([leg(720, 740, "Anvil Quay", "Cormorant Pier")], "adult"), 380)
            self.assertEqual(journey_fare([leg(720, 740, "Anvil Quay", "Eel Reach")], "adult"), 500)
            self.assertEqual(journey_fare([leg(720, 740, "Anvil Quay", "Fenwick Stairs")], "adult"), 610)
            self.assertEqual(journey_fare([leg(720, 740, "Anvil Quay", "Ironbridge Slip")], "adult"), 610)

        def test_direction_does_not_matter(self):
            self.assertEqual(journey_fare([leg(720, 740, "Eel Reach", "Anvil Quay")], "adult"), 500)

        def test_transfer_journey_uses_whole_zone_range(self):
            j = [leg(720, 730, "Anvil Quay", "Cormorant Pier"), leg(750, 770, "Cormorant Pier", "Eel Reach")]
            self.assertEqual(journey_fare(j, "adult"), 500)

        def test_round_trip_is_charged_once(self):
            j = [leg(700, 760, "Anvil Quay", "Eel Reach"), leg(800, 860, "Eel Reach", "Anvil Quay")]
            self.assertEqual(journey_fare(j, "adult"), 500)

        def test_range_comes_from_all_ports_not_the_ends(self):
            j = [leg(720, 730, "Cormorant Pier", "Eel Reach"), leg(740, 760, "Eel Reach", "Brack")]
            self.assertEqual(journey_fare(j, "adult"), 500)
            j = [leg(720, 730, "Eel Reach", "Fenwick Stairs"), leg(740, 760, "Fenwick Stairs", "Eel Reach")]
            self.assertEqual(journey_fare(j, "adult"), 380)

        def test_peak_boundaries(self):
            for depart, fare in ((419, 240), (420, 300), (421, 300), (539, 300), (540, 240), (541, 240)):
                got = journey_fare([leg(depart, depart + 5, "Anvil Quay", "Brack")], "adult")
                self.assertEqual(got, fare, depart)

        def test_peak_is_decided_by_first_leg(self):
            j = [leg(530, 545, "Anvil Quay", "Cormorant Pier"), leg(560, 580, "Cormorant Pier", "Dunmore")]
            self.assertEqual(journey_fare(j, "adult"), 440)
            j = [leg(500, 535, "Anvil Quay", "Brack"), leg(536, 545, "Brack", "Eel Reach")]
            self.assertEqual(journey_fare(j, "adult"), 560)
            j = [leg(330, 419, "Anvil Quay", "Brack"), leg(425, 445, "Brack", "Cormorant Pier")]
            self.assertEqual(journey_fare(j, "adult"), 380)

        def test_surcharge_is_discounted_too(self):
            j = [leg(430, 440, "Anvil Quay", "Brack")]
            self.assertEqual(journey_fare(j, "youth"), 150)
            self.assertEqual(journey_fare(j, "senior"), 180)

        def test_rider_discounts(self):
            j = [leg(720, 740, "Anvil Quay", "Fenwick Stairs")]
            self.assertEqual(journey_fare(j, "youth"), 305)
            self.assertEqual(journey_fare(j, "senior"), 370)

        def test_unknown_port(self):
            with self.assertRaises(ValueError):
                journey_fare([leg(720, 740, "Anvil Quay", "Narnia")], "adult")


    class DayTotal(unittest.TestCase):
        def test_no_legs(self):
            self.assertEqual(day_total([], "adult"), 0)

        def test_two_separate_journeys(self):
            legs = [leg(600, 620, "Anvil Quay", "Cormorant Pier"), leg(900, 920, "Eel Reach", "Fenwick Stairs")]
            self.assertEqual(day_total(legs, "adult"), 380 + 380)

        def test_transfers_are_merged(self):
            legs = [leg(600, 630, "Anvil Quay", "Cormorant Pier"), leg(675, 700, "Cormorant Pier", "Eel Reach")]
            self.assertEqual(day_total(legs, "adult"), 500)
            legs = [leg(600, 630, "Anvil Quay", "Cormorant Pier"), leg(676, 700, "Cormorant Pier", "Eel Reach")]
            self.assertEqual(day_total(legs, "adult"), 760)

        def test_cap_adult(self):
            legs = [leg(600 + 120 * i, 610 + 120 * i, "Anvil Quay", "Brack") for i in range(4)]
            self.assertEqual(day_total(legs, "adult"), 960)
            legs.append(leg(600 + 120 * 4, 610 + 120 * 4, "Anvil Quay", "Brack"))
            self.assertEqual(day_total(legs, "adult"), 1100)

        def test_cap_exact(self):
            legs = [leg(600, 610, "Anvil Quay", "Fenwick Stairs"), leg(800, 810, "Anvil Quay", "Fenwick Stairs")]
            self.assertEqual(day_total(legs, "adult"), 1100)
            legs = [leg(600, 610, "Anvil Quay", "Fenwick Stairs"), leg(800, 810, "Anvil Quay", "Eel Reach")]
            self.assertEqual(day_total(legs, "adult"), 1100)

        def test_cap_youth_and_senior(self):
            legs = [leg(600 + 120 * i, 610 + 120 * i, "Anvil Quay", "Brack") for i in range(5)]
            self.assertEqual(day_total(legs, "youth"), 550)
            self.assertEqual(day_total(legs, "senior"), 660)
            self.assertEqual(day_total(legs[:3], "youth"), 360)
            self.assertEqual(day_total(legs[:3], "senior"), 435)

        def test_peak_journey_counts_surcharge(self):
            legs = [leg(450, 470, "Anvil Quay", "Brack"), leg(700, 720, "Anvil Quay", "Brack")]
            self.assertEqual(day_total(legs, "adult"), 300 + 240)


    if __name__ == "__main__":
        unittest.main()
''')

FERRYZONES = Lib(
    name="ferryzones", lang="python", title="the Skerry Line ferry fare calculator (`skerryfare/`)",
    blurb="The ticketing back-end of the Skerry Line ferries prices a rider's day of crossings with these helpers.",
    files={"skerryfare/__init__.py": "", "skerryfare/zones.py": FZ_ZONES, "skerryfare/fares.py": FZ_FARES,
           "README.md": FZ_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": FZ_VISIBLE},
    hidden_tests={"tests/test_full.py": FZ_HIDDEN},
    mutate=["skerryfare/zones.py", "skerryfare/fares.py"], difficulty=3, tags=["transit", "fares", "money"],
    probes=[
        "base_fare(3)", "base_fare(7)", "span(5, 2)", "discounted(240, 'senior')", "discounted(670, 'youth')",
        "journey_fare([Leg(419, 430, 'Anvil Quay', 'Brack')], 'adult')",
        "journey_fare([Leg(540, 550, 'Anvil Quay', 'Brack')], 'adult')",
        "len(group_journeys([Leg(600, 630, 'Anvil Quay', 'Cormorant Pier'), Leg(675, 700, 'Cormorant Pier', 'Eel Reach')]))",
        "len(group_journeys([Leg(600, 630, 'Anvil Quay', 'Cormorant Pier'), Leg(625, 700, 'Cormorant Pier', 'Eel Reach')]))",
        "day_total([Leg(600 + 120 * i, 610 + 120 * i, 'Anvil Quay', 'Brack') for i in range(5)], 'adult')",
        "day_total([Leg(600, 610, 'Anvil Quay', 'Fenwick Stairs'), Leg(800, 810, 'Anvil Quay', 'Eel Reach')], 'adult')",
    ],
    probe_import="from skerryfare.zones import *\nfrom skerryfare.fares import *",
)

# ======================================================================================================================
# parktariff: tiered parking fee with grace, validation stamps, day cap, night flat, lost ticket
# ======================================================================================================================

PK_README = dd('''
    # kerbside

    Fee calculation for the Quay Street car park. Money is an `int` number of cents; times are whole minutes since
    an arbitrary midnight `0` (so minute `1500` is 01:00 on the next day).

    ## `stay_cost(minutes) -> int`

    The uncapped tariff for one stay of `minutes`:

    * 15 minutes or less are free (the grace period is *not* deducted from longer stays).
    * Otherwise the first 120 minutes cost 120 cents per **started** 30 minutes, and every minute after the first
      120 costs 90 cents per **started** 30 minutes (blocks are counted separately for the two parts).

    ## `fee(entry, exit, stamps=0, lost_ticket=False) -> int`

    * A lost ticket costs a flat `2500` and nothing else is looked at.
    * `exit < entry` or negative `stamps` is a `ValueError`.
    * Each validation stamp (from a shop) removes 60 minutes from the stay (never below zero) *before* anything is
      charged.
    * The chargeable minutes are split into full 24-hour days and a remainder. Every full day costs the day cap
      `1500`; the remainder costs `min(stay_cost(remainder), 1500)`.
    * **Night flat:** a stay that starts at 18:00 or later and ends on the *following* calendar day at 08:00 or
      earlier costs at most `600`. (It is decided by the real `entry` and `exit`, not by the stamps.)

    ## Formatting

    `format_cents(c)` gives `"15.00"` for `1500` and `"0.05"` for `5`.
    `format_duration(minutes)` gives `"2h 05m"` (125), `"59m"` (59), `"1d 01h 00m"` (1500); the day part is shown only
    from one full day on, the hour part only from one full hour on (but is always present with a day), minutes are
    two digits whenever an hour or day is shown.

    `receipt(entry, exit, stamps=0, lost_ticket=False)` returns `"<duration> -> <fee>"` such as `"2h 05m -> 5.70"`,
    or `"lost ticket -> 25.00"`. The duration shown is the real `exit - entry`.
''')

PK_SRC = dd('''
    GRACE = 15
    FIRST_TIER = 120
    FIRST_RATE = 120
    LATER_RATE = 90
    BLOCK = 30
    DAY = 1440
    DAY_CAP = 1500
    STAMP_MINUTES = 60
    LOST_TICKET = 2500
    NIGHT_FLAT = 600
    NIGHT_FROM = 18 * 60
    NIGHT_UNTIL = 8 * 60


    def _blocks(minutes):
        return -(-minutes // BLOCK)


    def stay_cost(minutes):
        if minutes <= GRACE:
            return 0
        first = min(minutes, FIRST_TIER)
        rest = minutes - first
        return _blocks(first) * FIRST_RATE + _blocks(rest) * LATER_RATE


    def _is_night_stay(entry, exit):
        if entry % DAY < NIGHT_FROM:
            return False
        if exit // DAY != entry // DAY + 1:
            return False
        return exit % DAY <= NIGHT_UNTIL


    def fee(entry, exit, stamps=0, lost_ticket=False):
        if lost_ticket:
            return LOST_TICKET
        if exit < entry:
            raise ValueError("exit before entry")
        if stamps < 0:
            raise ValueError("negative stamps")
        chargeable = max(0, exit - entry - stamps * STAMP_MINUTES)
        days, rest = divmod(chargeable, DAY)
        cost = days * DAY_CAP + min(stay_cost(rest), DAY_CAP)
        if _is_night_stay(entry, exit):
            cost = min(cost, NIGHT_FLAT)
        return cost


    def format_cents(cents):
        return f"{cents // 100}.{cents % 100:02d}"


    def format_duration(minutes):
        days, rest = divmod(minutes, DAY)
        hours, mins = divmod(rest, 60)
        if days:
            return f"{days:d}d {hours:02d}h {mins:02d}m"
        if hours:
            return f"{hours:d}h {mins:02d}m"
        return f"{mins:d}m"


    def receipt(entry, exit, stamps=0, lost_ticket=False):
        if lost_ticket:
            return f"lost ticket -> {format_cents(LOST_TICKET)}"
        total = fee(entry, exit, stamps)
        return f"{format_duration(exit - entry)} -> {format_cents(total)}"
''')

PK_VISIBLE = dd('''
    import unittest

    from kerbside.tariff import fee, format_cents, stay_cost


    class BasicTests(unittest.TestCase):
        def test_grace(self):
            self.assertEqual(stay_cost(10), 0)

        def test_one_block(self):
            self.assertEqual(stay_cost(30), 120)

        def test_fee_two_hours(self):
            self.assertEqual(fee(600, 720), 480)

        def test_cents(self):
            self.assertEqual(format_cents(1500), "15.00")


    if __name__ == "__main__":
        unittest.main()
''')

PK_HIDDEN = dd('''
    import unittest

    from kerbside.tariff import fee, format_cents, format_duration, receipt, stay_cost


    class StayCost(unittest.TestCase):
        def test_table(self):
            table = {0: 0, 1: 0, 15: 0, 16: 120, 30: 120, 31: 240, 60: 240, 61: 360, 90: 360, 119: 480, 120: 480,
                     121: 570, 150: 570, 151: 660, 180: 660, 181: 750, 240: 840, 480: 1560}
            for minutes, cents in table.items():
                self.assertEqual(stay_cost(minutes), cents, minutes)

        def test_grace_is_not_deducted(self):
            self.assertEqual(stay_cost(16), 120)
            self.assertEqual(stay_cost(45), 240)


    class Fee(unittest.TestCase):
        def test_simple(self):
            self.assertEqual(fee(0, 0), 0)
            self.assertEqual(fee(600, 610), 0)
            self.assertEqual(fee(600, 700), 480)
            self.assertEqual(fee(600, 720), 480)

        def test_entry_offset_does_not_matter(self):
            self.assertEqual(fee(5000, 5000 + 125), stay_cost(125))

        def test_cap_for_a_partial_day(self):
            self.assertEqual(fee(600, 600 + 450), 1470)
            self.assertEqual(fee(600, 600 + 451), 1500)
            self.assertEqual(fee(600, 600 + 900), 1500)

        def test_full_days(self):
            self.assertEqual(fee(600, 600 + 1440), 1500)
            self.assertEqual(fee(600, 600 + 1441), 1500)
            self.assertEqual(fee(600, 600 + 1440 + 15), 1500)
            self.assertEqual(fee(600, 600 + 1440 + 16), 1620)
            self.assertEqual(fee(600, 600 + 2 * 1440 + 30), 3120)
            self.assertEqual(fee(600, 600 + 1440 + 500), 3000)
            self.assertEqual(fee(600, 600 + 3 * 1440), 4500)

        def test_stamps(self):
            self.assertEqual(fee(600, 690, stamps=1), 120)
            self.assertEqual(fee(600, 691, stamps=1), 240)
            self.assertEqual(fee(600, 690, stamps=2), 0)
            self.assertEqual(fee(600, 690, stamps=3), 0)
            self.assertEqual(fee(600, 675, stamps=1), 0)
            self.assertEqual(fee(600, 677, stamps=1), 120)
            self.assertEqual(fee(600, 600 + 1500, stamps=1), 1500)
            self.assertEqual(fee(600, 600 + 1500, stamps=0), 1740)

        def test_stamps_cut_a_day(self):
            self.assertEqual(fee(600, 600 + 1500, stamps=2), 1500)
            self.assertEqual(fee(600, 600 + 1440 + 60, stamps=1), 1500)
            self.assertEqual(fee(600, 600 + 1440 + 30, stamps=0), 1620)
            self.assertEqual(fee(600, 600 + 1440 + 30, stamps=1), 1500)
            self.assertEqual(fee(600, 600 + 2 * 1440 + 120, stamps=2), 3000)

        def test_lost_ticket(self):
            self.assertEqual(fee(100, 200, lost_ticket=True), 2500)
            self.assertEqual(fee(300, 100, stamps=-4, lost_ticket=True), 2500)
            self.assertEqual(fee(100, 100 + 3000, stamps=2, lost_ticket=True), 2500)

        def test_errors(self):
            with self.assertRaises(ValueError):
                fee(200, 199)
            with self.assertRaises(ValueError):
                fee(200, 300, stamps=-1)

        def test_night_flat(self):
            day1 = 1440
            self.assertEqual(fee(1080, day1 + 480), 600)
            self.assertEqual(fee(1080, day1 + 481), 1500)
            self.assertEqual(fee(1079, day1 + 480), 1500)
            self.assertEqual(fee(1380, day1 + 30), 360)
            self.assertEqual(fee(day1 + 1100, 2 * day1 + 300), 600)
            self.assertEqual(fee(1080, day1 + 0), 600)

        def test_night_flat_needs_next_day(self):
            self.assertEqual(fee(1080, 1140), 240)
            self.assertEqual(fee(1100, 1100 + 821), 1500)
            self.assertEqual(fee(1100, 1100 + 820), 600)
            self.assertEqual(fee(1080, 2 * 1440 + 360), 3000)
            self.assertEqual(fee(0, 460), 1500)

        def test_night_flat_ignores_stamps(self):
            self.assertEqual(fee(1080, 1440 + 480, stamps=1), 600)
            self.assertEqual(fee(1080, 1440 + 480, stamps=14), 0)
            self.assertEqual(fee(1380, 1440 + 100, stamps=1), 480)
            self.assertEqual(fee(1380, 1440 + 100, stamps=2), 240)


    class Formatting(unittest.TestCase):
        def test_cents(self):
            self.assertEqual([format_cents(c) for c in (0, 5, 70, 100, 1500, 2505, 12345)],
                             ["0.00", "0.05", "0.70", "1.00", "15.00", "25.05", "123.45"])

        def test_duration(self):
            table = {0: "0m", 1: "1m", 59: "59m", 60: "1h 00m", 61: "1h 01m", 125: "2h 05m", 1439: "23h 59m",
                     1440: "1d 00h 00m", 1500: "1d 01h 00m", 2 * 1440 + 61: "2d 01h 01m"}
            for minutes, text in table.items():
                self.assertEqual(format_duration(minutes), text, minutes)

        def test_receipt(self):
            self.assertEqual(receipt(0, 125), "2h 05m -> 5.70")
            self.assertEqual(receipt(100, 110), "10m -> 0.00")
            self.assertEqual(receipt(1000, 1000 + 1500), "1d 01h 00m -> 17.40")
            self.assertEqual(receipt(0, 0, lost_ticket=True), "lost ticket -> 25.00")

        def test_receipt_shows_real_duration_with_stamps(self):
            self.assertEqual(receipt(600, 690, stamps=1), "1h 30m -> 1.20")


    if __name__ == "__main__":
        unittest.main()
''')

PARKTARIFF = Lib(
    name="parktariff", lang="python", title="the Quay Street car park tariff (`kerbside/tariff.py`)",
    blurb="The car-park kiosk computes what a driver owes at the barrier with these helpers.",
    files={"kerbside/__init__.py": "", "kerbside/tariff.py": PK_SRC, "README.md": PK_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": PK_VISIBLE},
    hidden_tests={"tests/test_full.py": PK_HIDDEN},
    mutate=["kerbside/tariff.py"], difficulty=2, tags=["parking", "tariff", "money"],
    probes=[
        "stay_cost(15)", "stay_cost(16)", "stay_cost(121)", "fee(600, 1051)", "fee(600, 2040 + 16)",
        "fee(600, 690, stamps=1)", "fee(1080, 1920)", "fee(1080, 1921)", "fee(1079, 1920)", "fee(1380, 1470)",
        "format_duration(1500)", "format_duration(60)", "format_cents(5)", "receipt(0, 125)",
    ],
    probe_import="from kerbside.tariff import *",
)

# ======================================================================================================================
# tollgate: distance toll by class, peak multiplier with half-up rounding, tag discount, repeat-trip rule, daily cap
# ======================================================================================================================

TG_README = dd('''
    # tollgate

    Toll pricing for the Estuary Expressway. Money is an `int` number of cents. Positions on the road are whole
    hectometres (1 km = 10 hm) from the harbour; times are minutes since midnight.

    ## `trip_toll(entry_hm, exit_hm, klass, minute, tag=False) -> int`

    * `klass` is `"A"` (cars, 8 cents per km), `"B"` (vans, 14) or `"C"` (trucks, 25); anything else is a `ValueError`.
    * The distance is `abs(exit_hm - entry_hm)`. A trip of length 0 costs `0` (no minimum, no tag logic).
    * The distance charge is `rate * hm / 10`, rounded half up to a whole cent. In the **peak** (`minute` from 07:00
      inclusive to 09:30 exclusive, or from 16:30 inclusive to 19:00 exclusive) the charge is multiplied by 3/2
      *before* the single rounding step.
    * The charge is never below the class minimum (`A` 50, `B` 90, `C` 150).
    * With `tag=True`, 10% of the charge (rounded down) is taken off. The tag discount comes after the minimum, so
      a tagged trip can cost less than the class minimum.

    ## `day_total(trips, klass, tag=False) -> int`

    `trips` is a list of `(entry_hm, exit_hm, minute)`, in any order. Trips are priced with `trip_toll` and processed
    in order of `minute` (ties keep the given order). Trips that cost nothing do not count. The 5th and every later
    paid trip of the day costs half its toll (rounded down). The total is then capped per class (`A` 900, `B` 1500,
    `C` 2800).

    ## Names

    `GANTRIES` maps gantry names to positions. `quote(from_name, to_name, klass, minute, tag=False)` is `trip_toll`
    between two named gantries; an unknown name is a `ValueError`.

    `cheapest_departure(entry_hm, exit_hm, klass, earliest, latest, step=15, tag=False)` tries the departure minutes
    `earliest, earliest + step, ...` up to and including `latest` and returns `(minute, toll)` for the lowest toll;
    on equal tolls the earliest minute wins. `earliest > latest` or `step < 1` is a `ValueError`.
''')

TG_SRC = dd('''
    RATES = {"A": 8, "B": 14, "C": 25}
    MINIMUM = {"A": 50, "B": 90, "C": 150}
    DAILY_CAP = {"A": 900, "B": 1500, "C": 2800}
    PEAKS = ((7 * 60, 9 * 60 + 30), (16 * 60 + 30, 19 * 60))
    PEAK_NUM = 3
    PEAK_DEN = 2
    TAG_PERCENT = 10
    HALF_PRICE_FROM = 5

    GANTRIES = {
        "Harbour Junction": 0,
        "Millrace": 85,
        "Carter's Cross": 190,
        "Eastfold": 342,
        "Salt Hill": 510,
    }


    def in_peak(minute):
        return any(start <= minute < end for start, end in PEAKS)


    def trip_toll(entry_hm, exit_hm, klass, minute, tag=False):
        if klass not in RATES:
            raise ValueError(f"unknown vehicle class {klass!r}")
        hm = abs(exit_hm - entry_hm)
        if hm == 0:
            return 0
        num = RATES[klass] * hm
        den = 10
        if in_peak(minute):
            num *= PEAK_NUM
            den *= PEAK_DEN
        charge = (2 * num + den) // (2 * den)
        charge = max(charge, MINIMUM[klass])
        if tag:
            charge -= charge * TAG_PERCENT // 100
        return charge


    def day_total(trips, klass, tag=False):
        total = 0
        paid = 0
        for entry_hm, exit_hm, minute in sorted(trips, key=lambda t: t[2]):
            toll = trip_toll(entry_hm, exit_hm, klass, minute, tag)
            if toll == 0:
                continue
            paid += 1
            if paid >= HALF_PRICE_FROM:
                toll //= 2
            total += toll
        return min(total, DAILY_CAP[klass])


    def _gantry(name):
        try:
            return GANTRIES[name]
        except KeyError:
            raise ValueError(f"unknown gantry {name!r}") from None


    def quote(from_name, to_name, klass, minute, tag=False):
        return trip_toll(_gantry(from_name), _gantry(to_name), klass, minute, tag)


    def cheapest_departure(entry_hm, exit_hm, klass, earliest, latest, step=15, tag=False):
        if earliest > latest:
            raise ValueError("earliest is after latest")
        if step < 1:
            raise ValueError("step must be positive")
        best = None
        minute = earliest
        while minute <= latest:
            toll = trip_toll(entry_hm, exit_hm, klass, minute, tag)
            if best is None or toll < best[1]:
                best = (minute, toll)
            minute += step
        return best
''')

TG_VISIBLE = dd('''
    import unittest

    from tollgate.pricing import quote, trip_toll


    class BasicTests(unittest.TestCase):
        def test_car_ten_km(self):
            self.assertEqual(trip_toll(0, 100, "A", 720), 80)

        def test_minimum(self):
            self.assertEqual(trip_toll(0, 20, "A", 720), 50)

        def test_named_gantries(self):
            self.assertEqual(quote("Harbour Junction", "Millrace", "A", 720), 68)


    if __name__ == "__main__":
        unittest.main()
''')

TG_HIDDEN = dd('''
    import unittest

    from tollgate.pricing import cheapest_departure, day_total, quote, trip_toll


    class TripToll(unittest.TestCase):
        def test_distance_charge(self):
            self.assertEqual(trip_toll(0, 100, "A", 720), 80)
            self.assertEqual(trip_toll(0, 100, "B", 720), 140)
            self.assertEqual(trip_toll(0, 100, "C", 720), 250)

        def test_direction_and_offset(self):
            self.assertEqual(trip_toll(100, 0, "A", 720), 80)
            self.assertEqual(trip_toll(300, 400, "A", 720), 80)
            self.assertEqual(trip_toll(400, 300, "C", 720), 250)

        def test_zero_length(self):
            self.assertEqual(trip_toll(250, 250, "C", 720), 0)
            self.assertEqual(trip_toll(250, 250, "A", 450, tag=True), 0)

        def test_minimum(self):
            self.assertEqual(trip_toll(0, 50, "A", 720), 50)
            self.assertEqual(trip_toll(0, 63, "A", 720), 50)
            self.assertEqual(trip_toll(0, 65, "A", 720), 52)
            self.assertEqual(trip_toll(0, 1, "B", 720), 90)
            self.assertEqual(trip_toll(0, 1, "C", 720), 150)
            self.assertEqual(trip_toll(0, 60, "C", 720), 150)
            self.assertEqual(trip_toll(0, 61, "C", 720), 153)

        def test_half_up_rounding(self):
            self.assertEqual(trip_toll(0, 67, "C", 720), 168)
            self.assertEqual(trip_toll(0, 66, "C", 720), 165)
            self.assertEqual(trip_toll(0, 63, "C", 720), 158)
            self.assertEqual(trip_toll(0, 73, "B", 720), 102)
            self.assertEqual(trip_toll(0, 75, "B", 720), 105)
            self.assertEqual(trip_toll(0, 77, "B", 720), 108)

        def test_peak_single_rounding(self):
            self.assertEqual(trip_toll(0, 100, "C", 430), 375)
            self.assertEqual(trip_toll(0, 82, "C", 430), 308)
            self.assertEqual(trip_toll(0, 82, "C", 720), 205)
            self.assertEqual(trip_toll(0, 63, "C", 430), 236)
            self.assertEqual(trip_toll(0, 67, "C", 430), 251)
            self.assertEqual(trip_toll(0, 125, "A", 430), 150)
            self.assertEqual(trip_toll(0, 71, "B", 430), 149)
            self.assertEqual(trip_toll(0, 73, "B", 430), 153)

        def test_peak_windows(self):
            expect = {419: 250, 420: 375, 421: 375, 569: 375, 570: 250, 989: 250, 990: 375, 1139: 375, 1140: 250}
            for minute, toll in expect.items():
                self.assertEqual(trip_toll(0, 100, "C", minute), toll, minute)

        def test_minimum_applies_after_peak(self):
            self.assertEqual(trip_toll(0, 40, "A", 430), 50)
            self.assertEqual(trip_toll(0, 100, "A", 430), 120)

        def test_tag_discount(self):
            self.assertEqual(trip_toll(0, 100, "A", 720, tag=True), 72)
            self.assertEqual(trip_toll(0, 124, "A", 720, tag=True), 90)
            self.assertEqual(trip_toll(0, 57, "C", 720, tag=True), 150 - 15)
            self.assertEqual(trip_toll(0, 62, "C", 720, tag=True), 155 - 15)
            self.assertEqual(trip_toll(0, 100, "C", 430, tag=True), 375 - 37)

        def test_tag_after_minimum(self):
            self.assertEqual(trip_toll(0, 50, "A", 720, tag=True), 45)
            self.assertEqual(trip_toll(0, 10, "B", 720, tag=True), 81)

        def test_unknown_class(self):
            with self.assertRaises(ValueError):
                trip_toll(0, 100, "D", 720)
            with self.assertRaises(ValueError):
                trip_toll(0, 0, "", 720)


    class DayTotal(unittest.TestCase):
        def test_empty(self):
            self.assertEqual(day_total([], "A"), 0)

        def test_plain_sum_and_order(self):
            trips = [(0, 100, 800), (0, 100, 600), (100, 0, 700)]
            self.assertEqual(day_total(trips, "A"), 240)

        def test_fifth_trip_half_price(self):
            four = [(0, 100, 600 + 50 * i) for i in range(4)]
            self.assertEqual(day_total(four, "A"), 320)
            self.assertEqual(day_total(four + [(0, 100, 800)], "A"), 360)
            self.assertEqual(day_total(four + [(0, 100, 800), (0, 100, 850)], "A"), 400)

        def test_half_price_follows_time_order(self):
            base = [(0, 100, 600 + 50 * i) for i in range(4)]
            self.assertEqual(day_total(base + [(0, 300, 800)], "A"), 320 + 120)
            self.assertEqual(day_total([(0, 300, 580)] + base, "A"), 240 + 240 + 40)
            self.assertEqual(day_total(list(reversed(base)) + [(0, 300, 800)], "A"), 320 + 120)

        def test_half_price_rounds_down(self):
            trips = [(0, 63, 600 + 50 * i) for i in range(5)]
            self.assertEqual(day_total(trips, "C"), 4 * 158 + 79)
            trips = [(0, 67, 600 + 50 * i) for i in range(5)]
            self.assertEqual(day_total(trips, "C"), 4 * 168 + 84)
            trips = [(0, 1, 600 + 50 * i) for i in range(5)]
            self.assertEqual(day_total(trips, "B", tag=True), 4 * 81 + 40)

        def test_free_trips_do_not_count(self):
            trips = [(0, 100, 600), (5, 5, 625), (0, 100, 650), (7, 7, 675), (0, 100, 700), (0, 100, 750), (0, 100, 800)]
            self.assertEqual(day_total(trips, "A"), 4 * 80 + 40)

        def test_cap(self):
            self.assertEqual(day_total([(0, 300, 100 * (i + 1)) for i in range(3)], "A"), 720)
            self.assertEqual(day_total([(0, 300, 100 * (i + 1)) for i in range(4)], "A"), 900)
            self.assertEqual(day_total([(0, 400, 100), (0, 400, 200), (0, 400, 300)], "C"), 2800)
            self.assertEqual(day_total([(0, 400, 100), (0, 400, 200)], "C"), 2000)
            self.assertEqual(day_total([(0, 1000, 100)], "B"), 1400)
            self.assertEqual(day_total([(0, 1100, 100)], "B"), 1500)
            self.assertEqual(day_total([(0, 1200, 100)], "B"), 1500)

        def test_class_is_validated(self):
            with self.assertRaises(ValueError):
                day_total([(0, 100, 100)], "Z")


    class Names(unittest.TestCase):
        def test_quote(self):
            self.assertEqual(quote("Harbour Junction", "Eastfold", "A", 720), 274)
            self.assertEqual(quote("Eastfold", "Harbour Junction", "A", 720), 274)
            self.assertEqual(quote("Millrace", "Carter's Cross", "B", 720), 147)
            self.assertEqual(quote("Salt Hill", "Salt Hill", "C", 720), 0)
            self.assertEqual(quote("Eastfold", "Salt Hill", "C", 720), 420)
            self.assertEqual(quote("Harbour Junction", "Salt Hill", "A", 450, tag=True), 551)

        def test_unknown_gantry(self):
            with self.assertRaises(ValueError):
                quote("Harbour Junction", "Nowhere", "A", 720)
            with self.assertRaises(ValueError):
                quote("Nowhere", "Millrace", "A", 720)


    class Cheapest(unittest.TestCase):
        def test_off_peak_first(self):
            self.assertEqual(cheapest_departure(0, 100, "C", 400, 600), (400, 250))

        def test_wait_for_off_peak(self):
            self.assertEqual(cheapest_departure(0, 100, "C", 430, 600), (580, 250))

        def test_latest_is_inclusive(self):
            self.assertEqual(cheapest_departure(0, 100, "C", 430, 580), (580, 250))
            self.assertEqual(cheapest_departure(0, 100, "C", 430, 579), (430, 375))
            self.assertEqual(cheapest_departure(0, 100, "C", 400, 400), (400, 250))

        def test_tie_goes_to_earliest(self):
            self.assertEqual(cheapest_departure(0, 100, "C", 600, 700), (600, 250))
            self.assertEqual(cheapest_departure(0, 100, "C", 430, 569, step=10), (430, 375))

        def test_step(self):
            self.assertEqual(cheapest_departure(0, 100, "C", 430, 620, step=60), (610, 250))
            self.assertEqual(cheapest_departure(0, 100, "C", 430, 600, step=60), (430, 375))
            self.assertEqual(cheapest_departure(0, 100, "C", 430, 600, step=1), (570, 250))

        def test_tag(self):
            self.assertEqual(cheapest_departure(0, 100, "C", 430, 600, tag=True), (580, 225))

        def test_errors(self):
            with self.assertRaises(ValueError):
                cheapest_departure(0, 100, "C", 600, 500)
            with self.assertRaises(ValueError):
                cheapest_departure(0, 100, "C", 400, 500, step=0)


    if __name__ == "__main__":
        unittest.main()
''')

TOLLGATE = Lib(
    name="tollgate", lang="python", title="the Estuary Expressway toll pricing (`tollgate/pricing.py`)",
    blurb="The Estuary Expressway's tolling system prices trips and whole days with these helpers.",
    files={"tollgate/__init__.py": "", "tollgate/pricing.py": TG_SRC, "README.md": TG_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": TG_VISIBLE},
    hidden_tests={"tests/test_full.py": TG_HIDDEN},
    mutate=["tollgate/pricing.py"], difficulty=3, tags=["tolls", "rounding", "money"],
    probes=[
        "trip_toll(0, 67, 'C', 720)", "trip_toll(0, 82, 'C', 430)", "trip_toll(0, 100, 'C', 570)", "trip_toll(0, 100, 'C', 419)",
        "trip_toll(0, 50, 'A', 720, tag=True)", "trip_toll(0, 100, 'A', 720, tag=True)",
        "day_total([(0, 100, 100 * (i + 1)) for i in range(5)], 'A')",
        "day_total([(0, 300, 50)] + [(0, 100, 100 * (i + 1)) for i in range(4)], 'A')",
        "day_total([(0, 400, 100), (0, 400, 200), (0, 400, 300)], 'C')",
        "cheapest_departure(0, 100, 'C', 430, 580)", "cheapest_departure(0, 100, 'C', 600, 700)",
        "quote('Harbour Junction', 'Eastfold', 'A', 720)",
    ],
    probe_import="from tollgate.pricing import *",
)

register_libs([FERRYZONES, PARKTARIFF, TOLLGATE], n=10)
