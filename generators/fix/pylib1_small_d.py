"""Python libraries, theme time/money/scheduling (batch small-d): bike-hire pricing and checked-baggage fees. Tiny
single-module libraries."""
from fx import Lib, dd, register_libs

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# bikehire: city bike-share ride pricing with free minutes, e-bikes, zone penalty, daily cap and lost-bike fee
# ======================================================================================================================

BH_README = dd('''
    # bikehire

    Pricing of the Quayside city bikes. Money is an `int` number of cents; ride lengths are whole minutes.

    * `usage_cost(minutes, member, ebike)`: the first minutes of a ride are free (45 for members, 15 for everybody else).
      Every **started** 15 minutes after that cost 50 cents for members and 80 cents for others; an e-bike adds 20 cents
      to every such block and an unlock fee of 100 cents per ride (charged even for a ride within the free minutes).
      Negative `minutes` is a `ValueError`.
    * `ride_cost(minutes, member=False, ebike=False, outside_zone=False)`: a ride of 1440 minutes or more is a lost bike
      and costs 20000 cents, nothing else. Otherwise `usage_cost` plus a 500 cent penalty when the bike was parked outside
      the zone.
    * `day_total(rides, member=False)`: `rides` is a list of `(minutes, ebike, outside_zone)`. The `usage_cost` of all
      rides of the day (lost bikes excluded) is added up and capped at 600 cents for members and 1200 for others. The
      zone penalties and the 20000 fee of each lost bike (a ride of 1440 minutes or more) are added on top of the capped
      amount.
''')

BH_SRC = dd('''
    FREE_MINUTES = {True: 45, False: 15}
    BLOCK = 15
    RATE = {True: 50, False: 80}
    EBIKE_UNLOCK = 100
    EBIKE_EXTRA = 20
    OUTSIDE_FEE = 500
    DAY_CAP = {True: 600, False: 1200}
    LOST_AFTER = 1440
    LOST_FEE = 20_000


    def usage_cost(minutes, member, ebike):
        if minutes < 0:
            raise ValueError("a ride cannot be shorter than 0 minutes")
        paid = max(0, minutes - FREE_MINUTES[member])
        blocks = -(-paid // BLOCK)
        rate = RATE[member] + (EBIKE_EXTRA if ebike else 0)
        return blocks * rate + (EBIKE_UNLOCK if ebike else 0)


    def ride_cost(minutes, member=False, ebike=False, outside_zone=False):
        if minutes >= LOST_AFTER:
            return LOST_FEE
        return usage_cost(minutes, member, ebike) + (OUTSIDE_FEE if outside_zone else 0)


    def day_total(rides, member=False):
        usage = 0
        extras = 0
        for minutes, ebike, outside_zone in rides:
            if minutes >= LOST_AFTER:
                extras += LOST_FEE
                continue
            usage += usage_cost(minutes, member, ebike)
            if outside_zone:
                extras += OUTSIDE_FEE
        return min(usage, DAY_CAP[member]) + extras
''')

BH_VISIBLE = dd('''
    import unittest

    from bikehire.pricing import ride_cost, usage_cost


    class BasicTests(unittest.TestCase):
        def test_free_ride(self):
            self.assertEqual(usage_cost(10, False, False), 0)

        def test_member_free_period(self):
            self.assertEqual(usage_cost(45, True, False), 0)

        def test_lost_bike(self):
            self.assertEqual(ride_cost(2000), 20_000)


    if __name__ == "__main__":
        unittest.main()
''')

BH_HIDDEN = dd('''
    import unittest

    from bikehire.pricing import day_total, ride_cost, usage_cost


    class Usage(unittest.TestCase):
        def test_non_members(self):
            table = {0: 0, 15: 0, 16: 80, 30: 80, 31: 160, 45: 160, 46: 240, 300: 1520}
            for minutes, cents in table.items():
                self.assertEqual(usage_cost(minutes, False, False), cents, minutes)

        def test_members(self):
            table = {0: 0, 45: 0, 46: 50, 60: 50, 61: 100, 120: 250}
            for minutes, cents in table.items():
                self.assertEqual(usage_cost(minutes, True, False), cents, minutes)

        def test_ebikes(self):
            table = {0: 100, 10: 100, 15: 100, 16: 200, 30: 200, 31: 300}
            for minutes, cents in table.items():
                self.assertEqual(usage_cost(minutes, False, True), cents, minutes)
            self.assertEqual([usage_cost(m, True, True) for m in (10, 45, 46, 61)], [100, 100, 170, 240])

        def test_negative(self):
            with self.assertRaises(ValueError):
                usage_cost(-1, False, False)
            with self.assertRaises(ValueError):
                usage_cost(-100, True, True)


    class Ride(unittest.TestCase):
        def test_plain(self):
            self.assertEqual(ride_cost(60), 240)
            self.assertEqual(ride_cost(60, member=True), 50)
            self.assertEqual(ride_cost(5, member=True, ebike=True), 100)

        def test_zone_penalty(self):
            self.assertEqual(ride_cost(60, outside_zone=True), 740)
            self.assertEqual(ride_cost(5, True, True, True), 600)
            self.assertEqual(ride_cost(0, outside_zone=True), 500)

        def test_lost_bike(self):
            self.assertEqual(ride_cost(1439), 7600)
            self.assertEqual(ride_cost(1440), 20_000)
            self.assertEqual(ride_cost(1441), 20_000)
            self.assertEqual(ride_cost(1440, outside_zone=True), 20_000)
            self.assertEqual(ride_cost(5000, member=True, ebike=True), 20_000)

        def test_rides_are_not_capped(self):
            self.assertEqual(ride_cost(1439, member=True), 4650)   # 1394 paid minutes: 93 started blocks of 50


    class Day(unittest.TestCase):
        def test_sum(self):
            self.assertEqual(day_total([(60, False, False), (120, False, True)]), 1300)
            self.assertEqual(day_total([]), 0)
            self.assertEqual(day_total([(60, True, True)], True), 670)

        def test_cap(self):
            self.assertEqual(day_total([(300, False, False)]), 1200)
            self.assertEqual(day_total([(300, False, False)], True), 600)
            self.assertEqual(day_total([(100, False, False)] * 3), 1200)
            self.assertEqual(day_total([(100, False, False)] * 3, True), 600)
            self.assertEqual(day_total([(100, False, False)] * 2), 960)
            self.assertEqual(day_total([(100, False, False)] * 2, True), 400)

        def test_penalties_are_added_after_the_cap(self):
            self.assertEqual(day_total([(300, False, True), (300, False, True)]), 2200)
            self.assertEqual(day_total([(300, False, True)], True), 1100)

        def test_lost_bikes_are_outside_the_cap(self):
            self.assertEqual(day_total([(1500, False, False), (60, False, False)]), 20_240)
            self.assertEqual(day_total([(1500, False, False), (1440, True, True)]), 40_000)
            self.assertEqual(day_total([(1500, False, False), (300, False, False)]), 21_200)

        def test_negative_ride(self):
            with self.assertRaises(ValueError):
                day_total([(60, False, False), (-5, False, False)])


    if __name__ == "__main__":
        unittest.main()
''')

BIKEHIRE = Lib(
    name="bikehire", lang="python", title="the city bike-share pricing (`bikehire/pricing.py`)",
    blurb="The Quayside bike-share app prices rides and days of riding with the bikehire module.",
    files={"bikehire/__init__.py": "", "bikehire/pricing.py": BH_SRC, "README.md": BH_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": BH_VISIBLE},
    hidden_tests={"tests/test_full.py": BH_HIDDEN},
    mutate=["bikehire/pricing.py"], difficulty=1, tags=["bikes", "pricing", "caps"],
    probes=[
        "usage_cost(15, False, False)", "usage_cost(16, False, False)", "usage_cost(46, True, False)", "usage_cost(10, False, True)",
        "usage_cost(31, False, True)", "usage_cost(61, True, True)", "ride_cost(1439)", "ride_cost(1440)", "ride_cost(60, outside_zone=True)",
        "day_total([(60, False, False), (120, False, True)])", "day_total([(300, False, False)], True)",
        "day_total([(1500, False, False), (60, False, False)])", "day_total([(300, False, True), (300, False, True)])",
    ],
    probe_import="from bikehire.pricing import *",
)

# ======================================================================================================================
# bagfees: checked-baggage fees by fare, bag position, weight and size
# ======================================================================================================================

BG_README = dd('''
    # bagfees

    Checked-baggage fees of a small airline. Money is an `int` number of cents; weights are whole kilograms; the size of
    a bag is its linear dimension (length + width + height) in whole centimetres.

    * `surcharge(weight_kg, linear_cm)`: 4000 cents for a bag of 24 kg or more, plus 6000 cents for one longer than
      158 cm (both can apply). A bag over 32 kg cannot travel, and a weight or size of 0 or less is not a bag: both
      are a `ValueError`.
    * `extra_bag_fee(position)`: the fee of the 1st, 2nd and 3rd-or-later **paid** bag: 3500, 5000, 7500 cents.
    * `checked_fees(fare, bags, prepaid=False)`: `bags` is a list of `(weight_kg, linear_cm)` in check-in order. The
      fare decides how many bags are free: `basic` 0, `standard` 1, `flex` 2 (an unknown fare is a `ValueError`). The
      free bags are the first ones; the bag after them is the 1st paid bag, and so on. Every bag pays its `surcharge`,
      free or not; each paid bag also pays `extra_bag_fee` of its paid position, reduced by 20% for `prepaid` (the
      surcharges are never discounted). No bags cost `0`.
''')

BG_SRC = dd('''
    FREE_BAGS = {"basic": 0, "standard": 1, "flex": 2}
    EXTRA_BAG_FEES = [3500, 5000, 7500]
    MAX_KG = 32
    HEAVY_FROM_KG = 24
    HEAVY_FEE = 4000
    OVERSIZE_CM = 158
    OVERSIZE_FEE = 6000
    PREPAID_PERCENT_OFF = 20


    def surcharge(weight_kg, linear_cm):
        if weight_kg > MAX_KG:
            raise ValueError("bag too heavy to travel")
        if weight_kg <= 0 or linear_cm <= 0:
            raise ValueError("a bag needs a weight and a size")
        fee = 0
        if weight_kg >= HEAVY_FROM_KG:
            fee += HEAVY_FEE
        if linear_cm > OVERSIZE_CM:
            fee += OVERSIZE_FEE
        return fee


    def extra_bag_fee(position):
        return EXTRA_BAG_FEES[min(position, len(EXTRA_BAG_FEES)) - 1]


    def checked_fees(fare, bags, prepaid=False):
        if fare not in FREE_BAGS:
            raise ValueError(f"unknown fare {fare!r}")
        free = FREE_BAGS[fare]
        total = 0
        for index, (weight_kg, linear_cm) in enumerate(bags):
            total += surcharge(weight_kg, linear_cm)
            paid_position = index + 1 - free
            if paid_position >= 1:
                fee = extra_bag_fee(paid_position)
                if prepaid:
                    fee = fee * (100 - PREPAID_PERCENT_OFF) // 100
                total += fee
        return total
''')

BG_VISIBLE = dd('''
    import unittest

    from bagfees.fees import checked_fees, extra_bag_fee


    class BasicTests(unittest.TestCase):
        def test_extra_bag(self):
            self.assertEqual(extra_bag_fee(1), 3500)

        def test_standard_fare_one_free_bag(self):
            self.assertEqual(checked_fees("standard", [(10, 100)]), 0)


    if __name__ == "__main__":
        unittest.main()
''')

BG_HIDDEN = dd('''
    import unittest

    from bagfees.fees import checked_fees, extra_bag_fee, surcharge


    class Surcharge(unittest.TestCase):
        def test_weight_and_size(self):
            table = {(10, 100): 0, (23, 158): 0, (24, 158): 4000, (24, 159): 10_000, (32, 159): 10_000, (32, 158): 4000, (1, 1): 0,
                     (23, 159): 6000}
            for (kg, cm), cents in table.items():
                self.assertEqual(surcharge(kg, cm), cents, (kg, cm))

        def test_errors(self):
            for kg, cm in ((33, 100), (100, 100), (0, 100), (-1, 100), (10, 0), (10, -5)):
                with self.assertRaises(ValueError, msg=(kg, cm)):
                    surcharge(kg, cm)


    class Position(unittest.TestCase):
        def test_fees(self):
            self.assertEqual([extra_bag_fee(p) for p in (1, 2, 3, 4, 10)], [3500, 5000, 7500, 7500, 7500])


    class Checked(unittest.TestCase):
        BAG = (10, 100)

        def test_free_allowances(self):
            self.assertEqual(checked_fees("basic", [self.BAG]), 3500)
            self.assertEqual(checked_fees("standard", [self.BAG]), 0)
            self.assertEqual(checked_fees("flex", [self.BAG, self.BAG]), 0)
            self.assertEqual(checked_fees("standard", [self.BAG, self.BAG]), 3500)
            self.assertEqual(checked_fees("flex", [self.BAG, self.BAG, self.BAG]), 3500)

        def test_positions_after_the_free_bags(self):
            self.assertEqual(checked_fees("basic", [self.BAG] * 4), 3500 + 5000 + 7500 + 7500)
            self.assertEqual(checked_fees("standard", [self.BAG] * 4), 3500 + 5000 + 7500)
            self.assertEqual(checked_fees("flex", [self.BAG] * 5), 3500 + 5000 + 7500)
            self.assertEqual(checked_fees("flex", [self.BAG, (20, 100), (23, 100), (23, 100), (23, 100)]), 16_000)

        def test_surcharges_apply_to_free_bags_too(self):
            self.assertEqual(checked_fees("flex", [(30, 170)]), 10_000)
            self.assertEqual(checked_fees("standard", [(24, 100)]), 4000)
            self.assertEqual(checked_fees("basic", [(25, 170), self.BAG]), 10_000 + 3500 + 5000)

        def test_prepaid_discounts_only_the_bag_fees(self):
            self.assertEqual(checked_fees("basic", [self.BAG], True), 2800)
            self.assertEqual(checked_fees("standard", [self.BAG] * 3, True), 2800 + 4000)
            self.assertEqual(checked_fees("basic", [(30, 100)], True), 4000 + 2800)
            self.assertEqual(checked_fees("flex", [(30, 170)], True), 10_000)
            self.assertEqual(checked_fees("basic", [self.BAG] * 3, True), 2800 + 4000 + 6000)

        def test_no_bags(self):
            self.assertEqual(checked_fees("basic", []), 0)
            self.assertEqual(checked_fees("flex", [], True), 0)

        def test_errors(self):
            for fare, bags in (("gold", [self.BAG]), ("", []), ("basic", [(33, 100)]), ("basic", [(0, 100)]), ("flex", [self.BAG, (10, 0)])):
                with self.assertRaises(ValueError, msg=(fare, bags)):
                    checked_fees(fare, bags)


    if __name__ == "__main__":
        unittest.main()
''')

BAGFEES = Lib(
    name="bagfees", lang="python", title="the checked-baggage fee rules (`bagfees/fees.py`)",
    blurb="The airline's booking engine prices checked baggage with the bagfees module.",
    files={"bagfees/__init__.py": "", "bagfees/fees.py": BG_SRC, "README.md": BG_README, ".gitignore": GITIGNORE},
    visible_tests={"tests/test_basic.py": BG_VISIBLE},
    hidden_tests={"tests/test_full.py": BG_HIDDEN},
    mutate=["bagfees/fees.py"], difficulty=1, tags=["airline", "baggage", "fees"],
    probes=[
        "surcharge(23, 158)", "surcharge(24, 158)", "surcharge(24, 159)", "surcharge(33, 100)", "extra_bag_fee(3)", "extra_bag_fee(4)",
        "checked_fees('standard', [(10, 100), (10, 100)])", "checked_fees('flex', [(10, 100)] * 5)", "checked_fees('basic', [(25, 170), (10, 100)])",
        "checked_fees('basic', [(10, 100)], True)", "checked_fees('basic', [(30, 100)], True)", "checked_fees('flex', [(30, 170)], True)",
    ],
    probe_import="from bagfees.fees import *",
)

register_libs([BIKEHIRE, BAGFEES], n=10)
