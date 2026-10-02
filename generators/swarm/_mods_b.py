"""Bank modules, part B: quorum, lockers, meterbill, holdqueue, sowcal, rentshare."""
from fx import dd

from ._bank import Bug, Mod, add

# ---------------------------------------------------------------------------------------------------------- quorum
add(Mod(
    key="quorum",
    title="quorum: member meeting votes",
    blurb="The tenants' association counts its meeting votes, proxies included, with the `quorum` helpers.",
    names=["tally"],
    spec=dd('''
        # quorum: counting a members' meeting vote

        ## `tally(members, ballots, proxies, quorum_pct=50, chair=None) -> dict`

        * `members`: the names entitled to vote (unique).
        * `ballots`: `{name: "yes" | "no" | "abstain"}` for the people who voted in person. Names that are not members are ignored.
        * `proxies`: a list of `(giver, holder)` pairs in the order they were filed: `giver` lets `holder` cast a second ballot on their behalf.
        * `chair`: the name of the chairperson, or `None`.

        **Proxies.** A pair that names a non-member (as giver or holder) is ignored as if it had never been filed. Of the remaining pairs only the **first**
        one of each giver is considered (later pairs of the same giver are ignored, even if the first turned out void). A considered pair is valid when
        the giver did **not** vote in person, the holder **did** vote in person, and the holder has fewer than **2** valid proxies so far (checked in filing
        order). A valid proxy adds one ballot equal to the holder's own ballot.

        **Counting.** `counted` = in-person ballots (members only) plus valid proxy ballots. `yes`, `no`, `abstain` count all those ballots by value.
        The quorum is met when `counted >= ceil(len(members) * quorum_pct / 100)`.

        **Result** (`"result"`): `"no-quorum"` if the quorum is not met; otherwise `"passed"` if `yes > no`, `"rejected"` if `no > yes` (abstentions count
        for the quorum but not for either side); on a tie, the chairperson's *own in-person ballot* decides if there is one (`"yes"` passes, `"no"` rejects),
        otherwise the result is `"tied"`.

        Returns `{"yes": int, "no": int, "abstain": int, "counted": int, "quorum": bool, "result": str}`.
    '''),
    core=dd('''
        """Meeting vote tally with proxies."""

        __all__ = ["tally"]


        def tally(members, ballots, proxies, quorum_pct=50, chair=None):
            mem = set(members)
            votes = {m: v for m, v in ballots.items() if m in mem}
            counted = list(votes.values())
            carried = {}
            seen_givers = set()
            for giver, holder in proxies:
                if giver not in mem or holder not in mem:
                    continue
                if giver in seen_givers:
                    continue
                seen_givers.add(giver)
                if giver in votes or holder not in votes:
                    continue
                if carried.get(holder, 0) >= 2:
                    continue
                carried[holder] = carried.get(holder, 0) + 1
                counted.append(votes[holder])
            yes, no, abstain = counted.count("yes"), counted.count("no"), counted.count("abstain")
            needed = -(-len(mem) * quorum_pct // 100)
            quorum = len(counted) >= needed
            if not quorum:
                result = "no-quorum"
            elif yes > no:
                result = "passed"
            elif no > yes:
                result = "rejected"
            else:
                c = votes.get(chair) if chair is not None else None
                result = "passed" if c == "yes" else "rejected" if c == "no" else "tied"
            return {"yes": yes, "no": no, "abstain": abstain, "counted": len(counted), "quorum": quorum, "result": result}
    '''),
    visible=dd('''
        from quorum import tally

        MEMBERS = ["ann", "bo", "cy", "di", "ed"]


        class VisibleTests(unittest.TestCase):
            def test_simple_pass(self):
                r = tally(MEMBERS, {"ann": "yes", "bo": "yes", "cy": "no"}, [])
                self.assertEqual((r["yes"], r["no"], r["result"]), (2, 1, "passed"))

            def test_no_quorum(self):
                r = tally(MEMBERS, {"ann": "yes"}, [])
                self.assertEqual(r["result"], "no-quorum")

            def test_proxy_counts(self):
                r = tally(MEMBERS, {"ann": "yes", "bo": "no"}, [("cy", "ann")])
                self.assertEqual((r["yes"], r["no"], r["counted"]), (2, 1, 3))
    '''),
    hidden=dd('''
        import random
        from quorum import tally

        MEMBERS = ["ann", "bo", "cy", "di", "ed", "flo", "gus", "hal"]


        def oracle(members, ballots, proxies, pct, chair):
            mem = set(members)
            votes = {m: v for m, v in ballots.items() if m in mem}
            considered, used = [], set()
            for g, h in proxies:
                if g in mem and h in mem and g not in used:
                    used.add(g)
                    considered.append((g, h))
            load = {}
            extra = []
            for g, h in considered:
                if g not in votes and h in votes and load.get(h, 0) < 2:
                    load[h] = load.get(h, 0) + 1
                    extra.append(votes[h])
            allb = list(votes.values()) + extra
            y, n, a = allb.count("yes"), allb.count("no"), allb.count("abstain")
            need = 0
            while need * 100 < len(mem) * pct:
                need += 1
            q = len(allb) >= need
            if not q:
                res = "no-quorum"
            elif y != n:
                res = "passed" if y > n else "rejected"
            else:
                c = votes.get(chair) if chair is not None else None
                res = {"yes": "passed", "no": "rejected"}.get(c, "tied")
            return {"yes": y, "no": n, "abstain": a, "counted": len(allb), "quorum": q, "result": res}


        class QuorumTests(unittest.TestCase):
            def test_proxy_limit_is_two(self):
                ballots = {"ann": "yes", "bo": "no"}
                proxies = [("cy", "ann"), ("di", "ann"), ("ed", "ann"), ("flo", "bo")]
                r = tally(MEMBERS, ballots, proxies)
                self.assertEqual((r["yes"], r["no"], r["counted"]), (3, 2, 5))

            def test_voting_giver_loses_the_proxy(self):
                r = tally(MEMBERS, {"ann": "yes", "bo": "no"}, [("bo", "ann")])
                self.assertEqual((r["yes"], r["no"], r["counted"]), (1, 1, 2))

            def test_holder_must_be_present(self):
                r = tally(MEMBERS, {"ann": "yes"}, [("bo", "cy")])
                self.assertEqual(r["counted"], 1)

            def test_only_first_proxy_of_a_giver(self):
                r = tally(MEMBERS, {"ann": "yes", "bo": "no"}, [("cy", "ann"), ("cy", "bo")])
                self.assertEqual((r["yes"], r["no"]), (2, 1))
                r = tally(MEMBERS, {"bo": "no"}, [("cy", "ann"), ("cy", "bo")])  # first pair void: holder absent
                self.assertEqual((r["yes"], r["no"], r["counted"]), (0, 1, 1))

            def test_nonmember_pair_is_ignored_entirely(self):
                r = tally(MEMBERS, {"ann": "yes"}, [("cy", "stranger"), ("cy", "ann")])
                self.assertEqual((r["yes"], r["counted"]), (2, 2))
                r = tally(MEMBERS, {"ann": "yes", "stranger": "no"}, [("outsider", "ann")])
                self.assertEqual((r["yes"], r["no"], r["counted"]), (1, 0, 1))

            def test_quorum_threshold_rounds_up(self):
                ballots = {"ann": "yes", "bo": "yes", "cy": "yes"}  # 3 of 8 members
                self.assertFalse(tally(MEMBERS, ballots, [], quorum_pct=40)["quorum"])  # needs 4 (3.2 up)
                self.assertTrue(tally(MEMBERS, ballots, [], quorum_pct=37)["quorum"])  # needs 3 (2.96 up)
                self.assertTrue(tally(MEMBERS, ballots, [], quorum_pct=0)["quorum"])
                four = {"ann": "yes", "bo": "yes", "cy": "yes", "di": "no"}
                self.assertTrue(tally(MEMBERS, four, [], quorum_pct=50)["quorum"])
                self.assertFalse(tally(MEMBERS, four, [], quorum_pct=51)["quorum"])

            def test_abstentions_count_for_quorum_not_for_sides(self):
                ballots = {"ann": "yes", "bo": "abstain", "cy": "abstain", "di": "abstain", "ed": "no"}
                r = tally(MEMBERS, ballots, [])
                self.assertEqual((r["yes"], r["no"], r["abstain"], r["result"]), (1, 1, 3, "tied"))
                r = tally(MEMBERS, {**ballots, "ed": "abstain"}, [])
                self.assertEqual(r["result"], "passed")

            def test_tie_goes_to_the_chair(self):
                ballots = {"ann": "yes", "bo": "no", "cy": "yes", "di": "no"}
                self.assertEqual(tally(MEMBERS, ballots, [], chair="ann")["result"], "passed")
                self.assertEqual(tally(MEMBERS, ballots, [], chair="bo")["result"], "rejected")
                self.assertEqual(tally(MEMBERS, ballots, [], chair="ed")["result"], "tied")
                self.assertEqual(tally(MEMBERS, ballots, [])["result"], "tied")
                abst = {"ann": "abstain", "bo": "yes", "cy": "no", "di": "yes", "ed": "no"}
                self.assertEqual(tally(MEMBERS, abst, [], chair="ann")["result"], "tied")

            def test_no_quorum_beats_everything(self):
                r = tally(MEMBERS, {"ann": "yes"}, [], quorum_pct=50, chair="ann")
                self.assertEqual((r["quorum"], r["result"]), (False, "no-quorum"))

            def test_differential(self):
                rng = random.Random(31)
                for _ in range(600):
                    mem = rng.sample(MEMBERS, rng.randint(2, 8))
                    pool = MEMBERS + ["zed", "yan"]
                    ballots = {n: rng.choice(["yes", "no", "abstain"]) for n in rng.sample(pool, rng.randint(0, 7))}
                    proxies = [(rng.choice(pool), rng.choice(pool)) for _ in range(rng.randint(0, 7))]
                    proxies = [(g, h) for g, h in proxies if g != h]
                    pct = rng.choice([0, 25, 34, 50, 51, 60, 75, 100])
                    chair = rng.choice([None, None] + MEMBERS)
                    self.assertEqual(tally(mem, ballots, proxies, pct, chair), oracle(mem, ballots, proxies, pct, chair), (mem, ballots, proxies, pct, chair))
    '''),
    bugs=[
        Bug("proxy-cap", "if carried.get(holder, 0) >= 2:", "if carried.get(holder, 0) >= 3:",
            ["tally(['a','b','c','d','e'], {'a': 'yes'}, [('b','a'), ('c','a'), ('d','a')])"], "tally", "a holder may carry three proxies"),
        Bug("giver-voted", "if giver in votes or holder not in votes:", "if holder not in votes:",
            ["tally(['a','b'], {'a': 'yes', 'b': 'no'}, [('b','a')])"], "tally", "a member who voted in person also has a proxy counted"),
        Bug("quorum-floor", "needed = -(-len(mem) * quorum_pct // 100)", "needed = len(mem) * quorum_pct // 100",
            ["tally(['a','b','c'], {'a': 'yes'}, [], quorum_pct=50)"], "tally", "the quorum is rounded down"),
        Bug("abstain-as-no", "elif yes > no:", "elif yes > no + abstain:",
            ["tally(['a','b','c'], {'a': 'yes', 'b': 'abstain', 'c': 'abstain'}, [])"], "tally", "abstentions count against the motion"),
        Bug("chair-swapped", '"passed" if c == "yes" else "rejected" if c == "no" else "tied"', '"passed" if c == "no" else "rejected" if c == "yes" else "tied"',
            ["tally(['a','b'], {'a': 'yes', 'b': 'no'}, [], chair='a')"], "tally", "the chairperson's casting vote is inverted"),
        Bug("later-filing", "        seen_givers.add(giver)\n", "        pass\n",
            ["tally(['a','b','c'], {'b': 'no'}, [('c','a'), ('c','b')])"], "tally", "a giver's second proxy is considered after the first turned out void"),
        Bug("nonmember-consumes", "if giver not in mem or holder not in mem:", "if giver not in mem:",
            ["tally(['a','b'], {'a': 'yes'}, [('b','ghost'), ('b','a')])"], "tally", "a pair naming a non-member uses up the giver's one proxy"),
    ],
))

# --------------------------------------------------------------------------------------------------------- lockers
add(Mod(
    key="lockers",
    title="lockers: parcel locker bank",
    blurb="The parcel locker terminal at the station allocates compartments with the `lockers` helpers.",
    names=["Bank"],
    spec=dd('''
        # lockers: a parcel locker bank

        Sizes are `"S"` < `"M"` < `"L"`. A bank is created from a list of sizes; locker ids are the list positions (0, 1, 2, ...). Times are whole day numbers.

        ## `Bank(sizes)`

        * `assign(size, parcel, now) -> int`: store `parcel` (any hashable) in the **lowest-numbered free locker of the smallest size that is at least `size`**:
          first the requested size, and only if none is free the next larger one, and so on. `ValueError` for an unknown size; `LookupError` when nothing
          fits. The locker remembers the parcel and the day `now`.
        * `release(locker_id) -> parcel`: empty the locker and return its parcel. `KeyError` if the locker is empty or does not exist.
        * `expire(now, ttl_days) -> list[tuple[int, parcel]]`: empty every locker whose parcel was stored **more than** `ttl_days` days ago (`now - stored > ttl_days`)
          and return `(locker_id, parcel)` pairs sorted by locker id.
        * `free_counts() -> dict`: the number of free lockers per size; always has the three keys `"S"`, `"M"`, `"L"`, also when some are 0.
    '''),
    core=dd('''
        """A parcel locker bank."""

        __all__ = ["Bank"]

        ORDER = ["S", "M", "L"]


        class Bank:
            def __init__(self, sizes):
                self.sizes = list(sizes)
                self.parcels = {}

            def assign(self, size, parcel, now):
                if size not in ORDER:
                    raise ValueError("unknown size")
                for s in ORDER[ORDER.index(size):]:
                    for lid, sz in enumerate(self.sizes):
                        if sz == s and lid not in self.parcels:
                            self.parcels[lid] = (parcel, now)
                            return lid
                raise LookupError("no free locker")

            def release(self, locker_id):
                if locker_id not in self.parcels:
                    raise KeyError(locker_id)
                return self.parcels.pop(locker_id)[0]

            def expire(self, now, ttl_days):
                out = [(lid, p) for lid, (p, day) in sorted(self.parcels.items()) if now - day > ttl_days]
                for lid, _ in out:
                    del self.parcels[lid]
                return out

            def free_counts(self):
                counts = {s: 0 for s in ORDER}
                for lid, sz in enumerate(self.sizes):
                    if lid not in self.parcels:
                        counts[sz] += 1
                return counts
    '''),
    visible=dd('''
        from lockers import Bank


        class VisibleTests(unittest.TestCase):
            def test_assign_lowest_matching(self):
                b = Bank(["S", "M", "M", "L"])
                self.assertEqual(b.assign("M", "p1", 0), 1)
                self.assertEqual(b.assign("M", "p2", 0), 2)

            def test_release(self):
                b = Bank(["S"])
                b.assign("S", "x", 3)
                self.assertEqual(b.release(0), "x")

            def test_counts(self):
                self.assertEqual(Bank(["S", "L"]).free_counts(), {"S": 1, "M": 0, "L": 1})
    '''),
    hidden=dd('''
        import random
        from lockers import Bank


        class Model:
            """A slow, obviously-correct model of the specification."""

            def __init__(self, sizes):
                self.sizes = list(sizes)
                self.slot = [None] * len(sizes)

            def assign(self, size, parcel, now):
                rank = {"S": 0, "M": 1, "L": 2}
                if size not in rank:
                    raise ValueError
                for want in range(rank[size], 3):
                    for i, s in enumerate(self.sizes):
                        if rank[s] == want and self.slot[i] is None:
                            self.slot[i] = (parcel, now)
                            return i
                raise LookupError

            def release(self, i):
                if not (0 <= i < len(self.sizes)) or self.slot[i] is None:
                    raise KeyError(i)
                p = self.slot[i][0]
                self.slot[i] = None
                return p

            def expire(self, now, ttl):
                out = []
                for i, cell in enumerate(self.slot):
                    if cell is not None and now - cell[1] > ttl:
                        out.append((i, cell[0]))
                        self.slot[i] = None
                return out

            def counts(self):
                return {k: sum(1 for i, s in enumerate(self.sizes) if s == k and self.slot[i] is None) for k in "SML"}


        class LockerTests(unittest.TestCase):
            def test_prefers_smallest_fitting_size(self):
                b = Bank(["L", "M", "S", "M"])
                self.assertEqual(b.assign("S", "a", 0), 2)
                self.assertEqual(b.assign("S", "b", 0), 1)
                self.assertEqual(b.assign("S", "c", 0), 3)
                self.assertEqual(b.assign("S", "d", 0), 0)
                with self.assertRaises(LookupError):
                    b.assign("S", "e", 0)

            def test_does_not_use_smaller_lockers(self):
                b = Bank(["S", "S", "M"])
                self.assertEqual(b.assign("M", "x", 0), 2)
                with self.assertRaises(LookupError):
                    b.assign("M", "y", 0)
                with self.assertRaises(LookupError):
                    b.assign("L", "z", 0)

            def test_unknown_size(self):
                with self.assertRaises(ValueError):
                    Bank(["S"]).assign("XL", "p", 0)

            def test_release_errors(self):
                b = Bank(["S", "M"])
                with self.assertRaises(KeyError):
                    b.release(0)
                with self.assertRaises(KeyError):
                    b.release(7)
                b.assign("S", "p", 1)
                self.assertEqual(b.release(0), "p")
                with self.assertRaises(KeyError):
                    b.release(0)
                self.assertEqual(b.assign("S", "q", 2), 0)

            def test_expire_is_strict_and_sorted(self):
                b = Bank(["S", "S", "S", "S"])
                for i, day in enumerate([5, 1, 3, 2]):
                    b.assign("S", f"p{i}", day)
                self.assertEqual(b.expire(8, 5), [(1, "p1"), (3, "p3")])  # 7 and 6 days old; p2 is exactly 5 days old and stays
                self.assertEqual(b.expire(8, 4), [(2, "p2")])
                self.assertEqual(b.expire(8, 2), [(0, "p0")])
                self.assertEqual(b.free_counts()["S"], 4)

            def test_free_counts_always_three_keys(self):
                b = Bank(["S", "S"])
                self.assertEqual(b.free_counts(), {"S": 2, "M": 0, "L": 0})
                b.assign("S", "x", 0)
                b.assign("S", "y", 0)
                self.assertEqual(b.free_counts(), {"S": 0, "M": 0, "L": 0})
                self.assertEqual(Bank([]).free_counts(), {"S": 0, "M": 0, "L": 0})

            def test_differential(self):
                rng = random.Random(14)
                for _ in range(120):
                    sizes = [rng.choice("SML") for _ in range(rng.randint(1, 9))]
                    real, model = Bank(sizes), Model(sizes)
                    day = 0
                    for step in range(40):
                        op = rng.choice(["assign", "assign", "release", "expire", "counts"])
                        day += rng.choice([0, 1, 1, 2])
                        if op == "assign":
                            size = rng.choice(["S", "M", "L", "S"])
                            args = (size, f"p{step}", day)
                            try:
                                want = model.assign(*args)
                            except (LookupError, ValueError) as e:
                                with self.assertRaises(type(e)):
                                    real.assign(*args)
                            else:
                                self.assertEqual(real.assign(*args), want)
                        elif op == "release":
                            i = rng.randint(-1, len(sizes))
                            try:
                                want = model.release(i)
                            except KeyError:
                                with self.assertRaises(KeyError):
                                    real.release(i)
                            else:
                                self.assertEqual(real.release(i), want)
                        elif op == "expire":
                            ttl = rng.randint(0, 4)
                            self.assertEqual(real.expire(day, ttl), model.expire(day, ttl))
                        else:
                            self.assertEqual(real.free_counts(), model.counts())
    '''),
    bugs=[
        Bug("largest-first", "for s in ORDER[ORDER.index(size):]:", "for s in reversed(ORDER[ORDER.index(size):]):",
            ["(lambda b: b.assign('S', 'x', 0))(Bank(['S', 'L']))"], "assign", "the largest free locker is used first"),
        Bug("highest-id", "for lid, sz in enumerate(self.sizes):\n                if sz == s and lid not in self.parcels:",
            "for lid, sz in reversed(list(enumerate(self.sizes))):\n                if sz == s and lid not in self.parcels:",
            ["(lambda b: b.assign('S', 'x', 0))(Bank(['S', 'S', 'S']))"], "assign", "the highest-numbered locker is used first"),
        Bug("no-fallback", "for s in ORDER[ORDER.index(size):]:", "for s in ORDER[ORDER.index(size):ORDER.index(size) + 1]:",
            ["(lambda b: b.assign('S', 'x', 0))(Bank(['M']))"], "assign", "a parcel is refused when only larger lockers are free"),
        Bug("expire-inclusive", "if now - day > ttl_days]", "if now - day >= ttl_days]",
            ["(lambda b: (b.assign('S', 'x', 1), b.expire(4, 3)))(Bank(['S']))"], "expire", "a parcel exactly ttl days old is expired too early"),
        Bug("release-silent", "if locker_id not in self.parcels:\n            raise KeyError(locker_id)\n        return self.parcels.pop(locker_id)[0]",
            "return self.parcels.pop(locker_id, (None,))[0]", ["Bank(['S']).release(0)"], "release", "releasing an empty locker returns None instead of raising"),
        Bug("counts-skip-zero", "counts = {s: 0 for s in ORDER}", "counts = {}", ["Bank(['S']).free_counts()"], "free_counts",
            "sizes with no free lockers are missing from the counts"),
        Bug("expire-unsorted", "for lid, (p, day) in sorted(self.parcels.items()) if", "for lid, (p, day) in reversed(sorted(self.parcels.items())) if",
            ["(lambda b: (b.assign('S', 'x', 0), b.assign('S', 'y', 0), b.expire(9, 1)))(Bank(['S', 'S']))"], "expire", "expired parcels come back in descending locker order"),
    ],
))

# ------------------------------------------------------------------------------------------------------- meterbill
add(Mod(
    key="meterbill",
    title="meterbill: water meter billing",
    blurb="The village water works bills households from odometer-style meters with the `meterbill` helpers.",
    names=["usage", "bill", "daily_estimate"],
    spec=dd('''
        # meterbill: odometer meters and tiered bills

        A meter shows `digits` decimal digits (default 5), so readings are integers from 0 to `10**digits - 1` and wrap around to 0 after the maximum.

        ## `usage(prev, cur, digits=5) -> int`
        Units consumed between two readings. A reading outside `0 .. 10**digits - 1` is a `ValueError`. If `cur >= prev` the answer is `cur - prev`.
        If `cur < prev` the meter may have wrapped: that is accepted only when `prev` was in the top tenth of the range (`prev * 10 >= 9 * 10**digits`), and the
        answer is then `cur + 10**digits - prev`; otherwise the reading went backwards and it is a `ValueError`.

        ## `bill(units, tiers, fixed_cents) -> int`
        `tiers` is a list of `(upto, rate_millicents)`: `upto` is the **cumulative** number of units at which the tier ends (the last tier has `upto=None`, no limit),
        `rate_millicents` the price of one unit in thousandths of a cent. Tier 1 prices the first `tiers[0].upto` units, tier 2 the units after that up to
        `tiers[1].upto`, and so on. Add up the exact amounts in millicents, convert to cents by rounding **half up once**, then add `fixed_cents` (always, even for 0 units).
        Negative `units` are a `ValueError`.

        ## `daily_estimate(readings, digits=5) -> int`
        `readings` is a list of `(day, reading)` in ascending day order (days are integers, strictly increasing). Only the **last three** readings (or all, if fewer)
        are used; at least two are needed (`ValueError` otherwise). Units consumed between consecutive used readings follow the rules of `usage` (a `ValueError`
        from it propagates). The result is the total units divided by the number of days between the first and the last used reading, rounded half up to an integer.
    '''),
    core=dd('''
        """Odometer meters and tiered billing."""

        __all__ = ["usage", "bill", "daily_estimate"]


        def usage(prev, cur, digits=5):
            top = 10 ** digits
            if not (0 <= prev < top and 0 <= cur < top):
                raise ValueError("reading outside the meter range")
            if cur >= prev:
                return cur - prev
            if prev * 10 >= 9 * top:
                return cur + top - prev
            raise ValueError("reading went backwards")


        def bill(units, tiers, fixed_cents):
            if units < 0:
                raise ValueError("negative units")
            milli, done = 0, 0
            for upto, rate in tiers:
                limit = units if upto is None else min(units, upto)
                if limit > done:
                    milli += (limit - done) * rate
                    done = limit
            return (2 * milli + 1000) // 2000 + fixed_cents


        def daily_estimate(readings, digits=5):
            used = readings[-3:]
            if len(used) < 2:
                raise ValueError("need at least two readings")
            total = sum(usage(a[1], b[1], digits) for a, b in zip(used, used[1:]))
            days = used[-1][0] - used[0][0]
            return (2 * total + days) // (2 * days)
    '''),
    visible=dd('''
        from meterbill import bill, daily_estimate, usage

        TIERS = [(100, 1500), (400, 2200), (None, 3100)]


        class VisibleTests(unittest.TestCase):
            def test_usage_plain(self):
                self.assertEqual(usage(120, 180), 60)

            def test_usage_wraps(self):
                self.assertEqual(usage(99990, 15), 25)

            def test_backwards(self):
                with self.assertRaises(ValueError):
                    usage(500, 100)

            def test_bill_first_tier(self):
                self.assertEqual(bill(40, TIERS, 250), 310)

            def test_estimate(self):
                self.assertEqual(daily_estimate([(0, 100), (10, 150)]), 5)
    '''),
    hidden=dd('''
        import random
        from fractions import Fraction
        from meterbill import bill, daily_estimate, usage

        TIERS = [(100, 1500), (400, 2200), (None, 3100)]


        def oracle_bill(units, tiers, fixed):
            milli, prev = Fraction(0), 0
            for upto, rate in tiers:
                hi = units if upto is None else min(units, upto)
                if hi > prev:
                    milli += (hi - prev) * rate
                    prev = hi
            cents = milli / 1000
            whole = int(cents)
            if cents - whole >= Fraction(1, 2):
                whole += 1
            return whole + fixed


        class UsageTests(unittest.TestCase):
            def test_plain_and_equal(self):
                self.assertEqual(usage(0, 0), 0)
                self.assertEqual(usage(10, 10), 0)
                self.assertEqual(usage(99999, 99999), 0)
                self.assertEqual(usage(0, 99999), 99999)

            def test_wrap_rule(self):
                self.assertEqual(usage(99999, 0), 1)
                self.assertEqual(usage(90000, 5), 10005)
                self.assertEqual(usage(95000, 100), 5100)
                with self.assertRaises(ValueError):
                    usage(89999, 5)
                with self.assertRaises(ValueError):
                    usage(50000, 49999)

            def test_other_digit_counts(self):
                self.assertEqual(usage(998, 4, digits=3), 6)
                self.assertEqual(usage(900, 0, digits=3), 100)
                with self.assertRaises(ValueError):
                    usage(899, 0, digits=3)
                self.assertEqual(usage(9, 3, digits=1), 4)

            def test_range_errors(self):
                for a, b in ((-1, 5), (5, -1), (100000, 5), (5, 100000)):
                    with self.assertRaises(ValueError):
                        usage(a, b)
                with self.assertRaises(ValueError):
                    usage(10, 1000, digits=3)


        class BillTests(unittest.TestCase):
            def test_tier_boundaries(self):
                self.assertEqual(bill(0, TIERS, 250), 250)
                self.assertEqual(bill(100, TIERS, 0), 150)
                self.assertEqual(bill(101, TIERS, 0), 150 + 2)
                self.assertEqual(bill(400, TIERS, 0), 150 + 660)
                self.assertEqual(bill(401, TIERS, 0), 150 + 660 + 3)
                self.assertEqual(bill(1000, TIERS, 100), 150 + 660 + 1860 + 100)

            def test_tiers_are_cumulative(self):
                tiers = [(10, 10000), (20, 20000), (None, 30000)]
                self.assertEqual(bill(25, tiers, 0), 100 + 200 + 150)

            def test_rounds_half_up_once(self):
                tiers = [(None, 500)]  # 0.5 cent per unit
                self.assertEqual(bill(1, tiers, 0), 1)
                self.assertEqual(bill(2, tiers, 0), 1)
                self.assertEqual(bill(3, tiers, 0), 2)
                self.assertEqual(bill(3, [(1, 400), (None, 700)], 0), 2)  # 400 + 1400 = 1800 millicents

            def test_negative_units(self):
                with self.assertRaises(ValueError):
                    bill(-1, TIERS, 0)

            def test_differential(self):
                rng = random.Random(5)
                for _ in range(300):
                    n = rng.randint(1, 4)
                    cuts = sorted(rng.sample(range(1, 500), n - 1)) if n > 1 else []
                    tiers = [(c, rng.randint(1, 5000)) for c in cuts] + [(None, rng.randint(1, 5000))]
                    units = rng.choice([0, 1, rng.randint(0, 700), (cuts[0] if cuts else 5)])
                    fixed = rng.choice([0, 99, 250])
                    self.assertEqual(bill(units, tiers, fixed), oracle_bill(units, tiers, fixed), (units, tiers, fixed))


        class EstimateTests(unittest.TestCase):
            def test_two_readings(self):
                self.assertEqual(daily_estimate([(0, 100), (10, 157)]), 6)  # 5.7
                self.assertEqual(daily_estimate([(0, 100), (10, 155)]), 6)  # 5.5 rounds up
                self.assertEqual(daily_estimate([(0, 100), (10, 154)]), 5)

            def test_only_last_three_count(self):
                r = [(0, 0), (10, 5000), (20, 5100), (30, 5300)]
                self.assertEqual(daily_estimate(r), 15)  # readings at days 10, 20, 30: 300 units in 20 days
                r2 = [(0, 10), (5, 20), (10, 40), (20, 100)]
                self.assertEqual(daily_estimate(r2), 5)  # 80 units in 15 days = 5.33; the last two alone would give 6

            def test_wrap_inside_window(self):
                self.assertEqual(daily_estimate([(0, 99950), (5, 50), (10, 130)]), 18)

            def test_errors(self):
                with self.assertRaises(ValueError):
                    daily_estimate([(0, 5)])
                with self.assertRaises(ValueError):
                    daily_estimate([])
                with self.assertRaises(ValueError):
                    daily_estimate([(0, 500), (5, 100)])
    '''),
    bugs=[
        Bug("wrap-threshold", "if prev * 10 >= 9 * top:", "if prev * 10 > 9 * top:", ["usage(90000, 5)"], "usage", "a meter at exactly 90% is not allowed to wrap"),
        Bug("range-edge", "if not (0 <= prev < top and 0 <= cur < top):", "if not (0 <= prev < top and 0 <= cur <= top):", ["usage(5, 100000)"], "usage",
            "a reading of 10**digits is accepted"),
        Bug("wrap-math", "return cur + top - prev", "return cur + top - prev - 1", ["usage(99999, 0)"], "usage", "wrapped usage is one unit short"),
        Bug("tier-slices", "limit = units if upto is None else min(units, upto)", "limit = units if upto is None else min(units, done + upto)",
            ["bill(250, [(100, 1500), (200, 2200), (None, 3100)], 0)"], "bill", "tier limits are treated as slice sizes instead of cumulative"),
        Bug("round-floor", "return (2 * milli + 1000) // 2000 + fixed_cents", "return milli // 1000 + fixed_cents", ["bill(3, [(None, 500)], 0)"], "bill",
            "millicents are truncated instead of rounded half up"),
        Bug("fixed-skip", "return (2 * milli + 1000) // 2000 + fixed_cents", "return ((2 * milli + 1000) // 2000 + fixed_cents) if units else 0", ["bill(0, [(None, 500)], 250)"], "bill",
            "the fixed charge is dropped when nothing was consumed"),
        Bug("estimate-window", "used = readings[-3:]", "used = readings[-2:]", ["daily_estimate([(0, 10), (5, 20), (10, 40), (20, 100)])"], "daily_estimate",
            "only the last two readings are used"),
        Bug("estimate-floor", "return (2 * total + days) // (2 * days)", "return total // days", ["daily_estimate([(0, 100), (10, 155)])"], "daily_estimate",
            "the daily average is truncated"),
    ],
))

# ------------------------------------------------------------------------------------------------------- holdqueue
add(Mod(
    key="holdqueue",
    title="holdqueue: call-centre hold queue",
    blurb="The council's call centre answers waiting callers with the aging priority queue in `holdqueue`.",
    names=["HoldQueue"],
    spec=dd('''
        # holdqueue: a hold queue where waiting raises priority

        ## `HoldQueue(aging_s=60, max_boost=3)`

        Every call has an integer priority from 1 (lowest) to 5 (highest) and an arrival time in whole seconds. While it waits its *effective priority* grows:

        `effective(t) = priority + min(max_boost, (t - arrived) // aging_s)`

        (one step for every full `aging_s` seconds waited, at most `max_boost` steps; the effective priority may exceed 5). Times given to the queue never go backwards.

        * `push(call_id, priority, t)`: add a call. `ValueError` if the priority is outside 1..5 or the id is already waiting.
        * `pop(t) -> call_id`: remove and return the call with the highest effective priority at `t`. Ties go to the call that arrived **earlier**; if still tied, to the
          smaller `call_id` (plain string comparison). `IndexError` when the queue is empty.
        * `peek(t) -> call_id`: like `pop` without removing it.
        * `waiting(t) -> list[tuple[str, int]]`: every waiting call as `(call_id, effective priority)` in the order in which `pop` would return them.
        * `cancel(call_id) -> bool`: remove a waiting call; `True` if it was waiting, `False` otherwise.
        * `len(queue)` is the number of waiting calls.
    '''),
    core=dd('''
        """A hold queue with aging priorities."""

        __all__ = ["HoldQueue"]


        class HoldQueue:
            def __init__(self, aging_s=60, max_boost=3):
                self.aging_s = aging_s
                self.max_boost = max_boost
                self._calls = {}

            def __len__(self):
                return len(self._calls)

            def push(self, call_id, priority, t):
                if not 1 <= priority <= 5:
                    raise ValueError("priority must be 1..5")
                if call_id in self._calls:
                    raise ValueError("call already waiting")
                self._calls[call_id] = (priority, t)

            def _effective(self, call_id, t):
                priority, arrived = self._calls[call_id]
                return priority + min(self.max_boost, (t - arrived) // self.aging_s)

            def _order(self, t):
                return sorted(self._calls, key=lambda c: (-self._effective(c, t), self._calls[c][1], c))

            def peek(self, t):
                order = self._order(t)
                if not order:
                    raise IndexError("queue is empty")
                return order[0]

            def pop(self, t):
                call_id = self.peek(t)
                del self._calls[call_id]
                return call_id

            def waiting(self, t):
                return [(c, self._effective(c, t)) for c in self._order(t)]

            def cancel(self, call_id):
                return self._calls.pop(call_id, None) is not None
    '''),
    visible=dd('''
        from holdqueue import HoldQueue


        class VisibleTests(unittest.TestCase):
            def test_priority_order(self):
                q = HoldQueue()
                q.push("a", 2, 0)
                q.push("b", 4, 0)
                self.assertEqual(q.pop(0), "b")
                self.assertEqual(q.pop(0), "a")

            def test_empty(self):
                with self.assertRaises(IndexError):
                    HoldQueue().pop(0)

            def test_cancel(self):
                q = HoldQueue()
                q.push("a", 1, 0)
                self.assertTrue(q.cancel("a"))
                self.assertFalse(q.cancel("a"))
    '''),
    hidden=dd('''
        import random
        from holdqueue import HoldQueue


        class Model:
            def __init__(self, aging, boost):
                self.aging, self.boost, self.calls = aging, boost, []

            def eff(self, c, t):
                steps = 0
                while steps < self.boost and t - c[2] >= (steps + 1) * self.aging:
                    steps += 1
                return c[1] + steps

            def order(self, t):
                best = list(self.calls)
                out = []
                while best:
                    pick = best[0]
                    for c in best[1:]:
                        a, b = (self.eff(c, t), -c[2], c[0]), (self.eff(pick, t), -pick[2], pick[0])
                        if (a[0], a[1]) > (b[0], b[1]) or ((a[0], a[1]) == (b[0], b[1]) and c[0] < pick[0]):
                            pick = c
                    out.append(pick)
                    best.remove(pick)
                return out


        class HoldQueueTests(unittest.TestCase):
            def test_aging_raises_priority(self):
                q = HoldQueue(aging_s=60, max_boost=3)
                q.push("old", 1, 0)
                q.push("new", 3, 180)
                self.assertEqual(q.waiting(180), [("old", 4), ("new", 3)])
                self.assertEqual(q.pop(180), "old")

            def test_a_step_needs_a_full_interval(self):
                q = HoldQueue(aging_s=60)
                q.push("a", 1, 0)
                self.assertEqual(q.waiting(59), [("a", 1)])
                self.assertEqual(q.waiting(60), [("a", 2)])
                self.assertEqual(q.waiting(119), [("a", 2)])
                self.assertEqual(q.waiting(120), [("a", 3)])

            def test_boost_is_capped(self):
                q = HoldQueue(aging_s=10, max_boost=2)
                q.push("a", 4, 0)
                self.assertEqual(q.waiting(1000), [("a", 6)])
                q2 = HoldQueue(aging_s=10, max_boost=0)
                q2.push("a", 4, 0)
                self.assertEqual(q2.waiting(1000), [("a", 4)])

            def test_ties_arrival_then_id(self):
                q = HoldQueue()
                q.push("zed", 3, 5)
                q.push("amy", 3, 7)
                q.push("bob", 3, 5)
                self.assertEqual([c for c, _ in q.waiting(7)], ["bob", "zed", "amy"])
                self.assertEqual(q.pop(7), "bob")
                self.assertEqual(q.pop(7), "zed")
                self.assertEqual(q.pop(7), "amy")

            def test_aging_can_overtake_higher_priority(self):
                q = HoldQueue(aging_s=60, max_boost=3)
                q.push("low", 2, 0)
                q.push("high", 4, 170)
                self.assertEqual(q.peek(170), "low")  # 2 + 2 against 4: a tie, and low arrived first
                self.assertEqual(q.peek(180), "low")  # 2 + 3 against 4
                q2 = HoldQueue()
                q2.push("low", 2, 100)
                q2.push("high", 4, 100)
                self.assertEqual(q2.peek(100), "high")

            def test_peek_does_not_remove(self):
                q = HoldQueue()
                q.push("a", 1, 0)
                self.assertEqual(q.peek(0), "a")
                self.assertEqual(len(q), 1)
                q.pop(0)
                self.assertEqual(len(q), 0)
                with self.assertRaises(IndexError):
                    q.peek(0)

            def test_errors_and_cancel(self):
                q = HoldQueue()
                for bad in (0, 6, -1):
                    with self.assertRaises(ValueError):
                        q.push("x", bad, 0)
                q.push("x", 1, 0)
                with self.assertRaises(ValueError):
                    q.push("x", 2, 1)
                self.assertTrue(q.cancel("x"))
                self.assertFalse(q.cancel("x"))
                q.push("x", 5, 2)  # an id can come back after it left
                self.assertEqual(len(q), 1)

            def test_differential(self):
                rng = random.Random(77)
                for _ in range(150):
                    aging, boost = rng.choice([(30, 2), (60, 3), (10, 5), (45, 1)])
                    q, m = HoldQueue(aging, boost), Model(aging, boost)
                    t = 0
                    for step in range(40):
                        t += rng.choice([0, 5, 20, 31, 60, 100])
                        op = rng.choice(["push", "push", "pop", "cancel", "peek"])
                        if op == "push":
                            cid = rng.choice(["c%02d" % rng.randint(0, 14), "A", "b"])
                            if any(c[0] == cid for c in m.calls):
                                with self.assertRaises(ValueError):
                                    q.push(cid, 3, t)
                            else:
                                pr = rng.randint(1, 5)
                                q.push(cid, pr, t)
                                m.calls.append((cid, pr, t))
                        elif op == "pop":
                            if not m.calls:
                                with self.assertRaises(IndexError):
                                    q.pop(t)
                            else:
                                want = m.order(t)[0]
                                self.assertEqual(q.pop(t), want[0])
                                m.calls.remove(want)
                        elif op == "peek":
                            if m.calls:
                                self.assertEqual(q.peek(t), m.order(t)[0][0])
                        else:
                            cid = rng.choice(["c%02d" % rng.randint(0, 14), "A", "b"])
                            had = any(c[0] == cid for c in m.calls)
                            self.assertEqual(q.cancel(cid), had)
                            m.calls = [c for c in m.calls if c[0] != cid]
                        self.assertEqual(q.waiting(t), [(c[0], m.eff(c, t)) for c in m.order(t)])
    '''),
    bugs=[
        Bug("tie-late-first", "key=lambda c: (-self._effective(c, t), self._calls[c][1], c))", "key=lambda c: (-self._effective(c, t), -self._calls[c][1], c))",
            ["(lambda q: (q.push('a', 3, 1), q.push('b', 3, 5), q.pop(6)))(HoldQueue())"], "_order", "ties go to the later arrival"),
        Bug("tie-id-descending", "self._calls[c][1], c))", "self._calls[c][1], [-ord(ch) for ch in c]))",
            ["(lambda q: (q.push('a', 3, 1), q.push('b', 3, 1), q.pop(6)))(HoldQueue())"], "_order", "equal arrivals are served in reverse id order"),
        Bug("boost-uncapped", "priority + min(self.max_boost, (t - arrived) // self.aging_s)", "priority + (t - arrived) // self.aging_s",
            ["(lambda q: (q.push('a', 1, 0), q.waiting(10000)))(HoldQueue())"], "_effective", "waiting raises the priority without limit"),
        Bug("boost-ceiling", "(t - arrived) // self.aging_s)", "-(-(t - arrived) // self.aging_s))",
            ["(lambda q: (q.push('a', 1, 0), q.waiting(59)))(HoldQueue())"], "_effective", "a started interval already counts as a step"),
        Bug("cancel-always-true", "return self._calls.pop(call_id, None) is not None", "self._calls.pop(call_id, None)\n        return True",
            ["HoldQueue().cancel('ghost')"], "cancel", "cancelling an unknown call reports success"),
        Bug("pop-keeps", "call_id = self.peek(t)\n        del self._calls[call_id]\n        return call_id", "return self.peek(t)",
            ["(lambda q: (q.push('a', 3, 0), q.pop(1), len(q)))(HoldQueue())"], "pop", "pop does not remove the call"),
        Bug("duplicate-allowed", "if call_id in self._calls:\n            raise ValueError(\"call already waiting\")\n        ", "",
            ["(lambda q: (q.push('a', 3, 0), q.push('a', 4, 1)))(HoldQueue())"], "push", "a call id can be pushed twice"),
    ],
))

# ---------------------------------------------------------------------------------------------------------- sowcal
add(Mod(
    key="sowcal",
    title="sowcal: sowing calendar",
    blurb="The allotment society's planting calendar is computed from the last frost date with the `sowcal` helpers.",
    names=["window", "open_on", "days_left", "next_opening"],
    probe_pre="from datetime import date",
    spec=dd('''
        # sowcal: when to sow, relative to the last frost

        Dates are `datetime.date`. A *crop* is a tuple `(name, start_offset, end_offset)`: it can be sown from `last_frost + start_offset days` to
        `last_frost + end_offset days`, **both days included**. Offsets are integers and may be negative; `start_offset <= end_offset` is guaranteed.

        ## `window(last_frost, start_offset, end_offset) -> tuple[date, date]`
        The first and last day of the sowing window.

        ## `open_on(last_frost, crops, day) -> list[str]`
        The names of the crops that can be sown on `day`, ordered by the day their window closes (earliest first), ties by name.

        ## `days_left(last_frost, crop, day) -> int | None`
        How many days remain after `day` until the window's last day (0 on the last day itself); `None` when the crop cannot be sown on `day`.

        ## `next_opening(last_frost, crops, day) -> tuple[str, date] | None`
        The crop whose window opens soonest **after** `day` (strictly later than `day`) as `(name, first_day)`; if several open on the same day the
        alphabetically first name wins. `None` if no window opens after `day`. A crop that is already open on `day` is not considered.
    '''),
    core=dd('''
        """Sowing windows relative to the last frost."""
        from datetime import timedelta

        __all__ = ["window", "open_on", "days_left", "next_opening"]


        def window(last_frost, start_offset, end_offset):
            return (last_frost + timedelta(days=start_offset), last_frost + timedelta(days=end_offset))


        def open_on(last_frost, crops, day):
            hits = []
            for name, a, b in crops:
                first, last = window(last_frost, a, b)
                if first <= day <= last:
                    hits.append((last, name))
            return [name for _, name in sorted(hits)]


        def days_left(last_frost, crop, day):
            first, last = window(last_frost, crop[1], crop[2])
            if first <= day <= last:
                return (last - day).days
            return None


        def next_opening(last_frost, crops, day):
            best = None
            for name, a, b in crops:
                first, _ = window(last_frost, a, b)
                if first > day and (best is None or (first, name) < (best[1], best[0])):
                    best = (name, first)
            return best
    '''),
    visible=dd('''
        from datetime import date

        from sowcal import days_left, next_opening, open_on, window

        FROST = date(2024, 4, 20)
        CROPS = [("peas", -30, -5), ("beans", 7, 40), ("kale", -10, 20)]


        class VisibleTests(unittest.TestCase):
            def test_window(self):
                self.assertEqual(window(FROST, -30, -5), (date(2024, 3, 21), date(2024, 4, 15)))

            def test_open_on(self):
                self.assertEqual(open_on(FROST, CROPS, date(2024, 4, 12)), ["peas", "kale"])

            def test_days_left(self):
                self.assertEqual(days_left(FROST, CROPS[0], date(2024, 4, 10)), 5)

            def test_next_opening(self):
                self.assertEqual(next_opening(FROST, CROPS, date(2024, 4, 12)), ("beans", date(2024, 4, 27)))
    '''),
    hidden=dd('''
        import random
        from datetime import date, timedelta

        from sowcal import days_left, next_opening, open_on, window

        FROST = date(2024, 4, 20)


        class SowTests(unittest.TestCase):
            def test_window_crosses_the_year(self):
                self.assertEqual(window(date(2023, 12, 20), 5, 25), (date(2023, 12, 25), date(2024, 1, 14)))
                self.assertEqual(window(date(2024, 1, 3), -10, 0), (date(2023, 12, 24), date(2024, 1, 3)))
                self.assertEqual(window(date(2024, 2, 20), 8, 12), (date(2024, 2, 28), date(2024, 3, 3)))  # 2024 is a leap year

            def test_both_ends_included(self):
                crops = [("a", 0, 10)]
                self.assertEqual(open_on(FROST, crops, date(2024, 4, 20)), ["a"])
                self.assertEqual(open_on(FROST, crops, date(2024, 4, 30)), ["a"])
                self.assertEqual(open_on(FROST, crops, date(2024, 4, 19)), [])
                self.assertEqual(open_on(FROST, crops, date(2024, 5, 1)), [])

            def test_open_on_orders_by_closing_day_then_name(self):
                crops = [("kale", -10, 20), ("peas", -30, 20), ("beet", -5, 30), ("corn", 0, 20)]
                self.assertEqual(open_on(FROST, crops, date(2024, 4, 22)), ["corn", "kale", "peas", "beet"])
                self.assertEqual(open_on(FROST, crops, date(2024, 6, 30)), [])

            def test_days_left(self):
                crop = ("x", -3, 12)
                self.assertEqual(days_left(FROST, crop, date(2024, 4, 17)), 15)
                self.assertEqual(days_left(FROST, crop, date(2024, 5, 2)), 0)
                self.assertIsNone(days_left(FROST, crop, date(2024, 5, 3)))
                self.assertIsNone(days_left(FROST, crop, date(2024, 4, 16)))

            def test_days_left_across_leap_day(self):
                self.assertEqual(days_left(date(2024, 2, 25), ("x", 0, 10), date(2024, 2, 27)), 8)

            def test_next_opening_is_strictly_after(self):
                crops = [("late", 20, 30), ("soon", 5, 9), ("open", -5, 5), ("soon2", 5, 12), ("sooner", 3, 4)]
                self.assertEqual(next_opening(FROST, crops, date(2024, 4, 20)), ("sooner", date(2024, 4, 23)))
                self.assertEqual(next_opening(FROST, crops, date(2024, 4, 23)), ("soon", date(2024, 4, 25)))
                self.assertEqual(next_opening(FROST, crops, date(2024, 4, 25)), ("late", date(2024, 5, 10)))
                self.assertIsNone(next_opening(FROST, crops, date(2024, 5, 10)))
                self.assertIsNone(next_opening(FROST, [], date(2024, 4, 1)))

            def test_differential(self):
                rng = random.Random(21)
                for _ in range(300):
                    frost = date(2023, 12, 1) + timedelta(days=rng.randint(0, 120))
                    crops = []
                    for i in range(rng.randint(0, 6)):
                        a = rng.randint(-40, 40)
                        crops.append((rng.choice(["amaranth", "borage", "chard", "dill", "endive"]) + str(i % 2), a, a + rng.randint(0, 30)))
                    day = frost + timedelta(days=rng.randint(-60, 80))
                    want_open = sorted(
                        ((frost + timedelta(days=b), n) for n, a, b in crops if frost + timedelta(days=a) <= day <= frost + timedelta(days=b)))
                    self.assertEqual(open_on(frost, crops, day), [n for _, n in want_open])
                    later = sorted((frost + timedelta(days=a), n) for n, a, b in crops if frost + timedelta(days=a) > day)
                    self.assertEqual(next_opening(frost, crops, day), (later[0][1], later[0][0]) if later else None)
                    for c in crops:
                        lo, hi = frost + timedelta(days=c[1]), frost + timedelta(days=c[2])
                        self.assertEqual(days_left(frost, c, day), (hi - day).days if lo <= day <= hi else None)
    '''),
    bugs=[
        Bug("end-exclusive", "if first <= day <= last:\n            hits.append", "if first <= day < last:\n            hits.append",
            ["open_on(date(2024, 4, 20), [('a', 0, 10)], date(2024, 4, 30))"], "open_on", "the last sowing day is missing"),
        Bug("start-exclusive", "if first <= day <= last:\n            hits.append", "if first < day <= last:\n            hits.append",
            ["open_on(date(2024, 4, 20), [('a', 0, 10)], date(2024, 4, 20))"], "open_on", "the first sowing day is missing"),
        Bug("sort-by-name", "return [name for _, name in sorted(hits)]", "return [name for _, name in sorted(hits, key=lambda h: h[1])]",
            ["open_on(date(2024, 4, 20), [('kale', -10, 20), ('peas', -30, 5)], date(2024, 4, 22))"], "open_on", "open crops are listed alphabetically"),
        Bug("days-left-off", "return (last - day).days\n    return None", "return (last - day).days + 1\n    return None",
            ["days_left(date(2024, 4, 20), ('x', -3, 12), date(2024, 5, 2))"], "days_left", "one day too many remains"),
        Bug("next-inclusive", "if first > day and (best is None", "if first >= day and (best is None",
            ["next_opening(date(2024, 4, 20), [('a', 3, 9)], date(2024, 4, 23))"], "next_opening", "a window opening today counts as upcoming"),
        Bug("next-name-tie", "(first, name) < (best[1], best[0])", "(first, name) <= (best[1], best[0]) and name > best[0] or best is None or first < best[1]",
            ["next_opening(date(2024, 4, 20), [('b', 5, 9), ('a', 5, 12)], date(2024, 4, 21))"], "next_opening", "equal opening days are decided by the last crop listed, not by name"),
        Bug("window-end-offset", "last_frost + timedelta(days=end_offset))", "last_frost + timedelta(days=end_offset - 1))",
            ["window(date(2024, 4, 20), 0, 10)"], "window", "the window ends a day early"),
    ],
))

# ------------------------------------------------------------------------------------------------------- rentshare
add(Mod(
    key="rentshare",
    title="rentshare: shared house rent",
    blurb="The flatshare's rent split is computed with the `rentshare` helpers.",
    names=["weights", "split"],
    spec=dd('''
        # rentshare: splitting the rent of a shared flat

        A room is a dict `{"name": str, "sqm": int, "ensuite": bool, "balcony": bool}`; names are unique.

        ## `weights(rooms) -> dict[str, int]`
        Each room's weight in points: `sqm * 10`, plus 30 if it has an en-suite bathroom, plus 15 if it has a balcony. `ValueError` for no rooms, a duplicate
        name, or `sqm <= 0`.

        ## `split(total_cents, rooms) -> dict[str, int]`
        Splits the rent in proportion to the weights so that the shares add up to exactly `total_cents`:

        1. every room first gets `floor(total * weight / sum of weights)` cents;
        2. the cents still missing (fewer than the number of rooms) are handed out **one each** to the rooms with the **largest fractional remainder**
           (the part of the exact share that the floor dropped), in that order; rooms with equal remainders are served in alphabetical order of their names
           (plain string comparison).

        `ValueError` for a negative total or invalid rooms (as in `weights`).
    '''),
    core=dd('''
        """Splitting rent by room weights."""
        from fractions import Fraction

        __all__ = ["weights", "split"]


        def weights(rooms):
            if not rooms:
                raise ValueError("no rooms")
            out = {}
            for r in rooms:
                if r["name"] in out:
                    raise ValueError("duplicate room name")
                if r["sqm"] <= 0:
                    raise ValueError("sqm must be positive")
                out[r["name"]] = r["sqm"] * 10 + (30 if r["ensuite"] else 0) + (15 if r["balcony"] else 0)
            return out


        def split(total_cents, rooms):
            if total_cents < 0:
                raise ValueError("negative total")
            w = weights(rooms)
            whole = sum(w.values())
            exact = {n: Fraction(total_cents * x, whole) for n, x in w.items()}
            shares = {n: int(v) for n, v in exact.items()}
            missing = total_cents - sum(shares.values())
            order = sorted(w, key=lambda n: (-(exact[n] - shares[n]), n))
            for n in order[:missing]:
                shares[n] += 1
            return shares
    '''),
    visible=dd('''
        from rentshare import split, weights

        ROOMS = [
            {"name": "attic", "sqm": 12, "ensuite": True, "balcony": False},
            {"name": "back", "sqm": 10, "ensuite": False, "balcony": False},
            {"name": "front", "sqm": 14, "ensuite": False, "balcony": True},
        ]


        class VisibleTests(unittest.TestCase):
            def test_weights(self):
                self.assertEqual(weights(ROOMS), {"attic": 150, "back": 100, "front": 155})

            def test_split_adds_up(self):
                s = split(100_000, ROOMS)
                self.assertEqual(sum(s.values()), 100_000)

            def test_errors(self):
                with self.assertRaises(ValueError):
                    split(-1, ROOMS)
    '''),
    hidden=dd('''
        import random
        from fractions import Fraction
        from rentshare import split, weights


        def room(name, sqm, e=False, b=False):
            return {"name": name, "sqm": sqm, "ensuite": e, "balcony": b}


        class RentTests(unittest.TestCase):
            def test_weights(self):
                rooms = [room("a", 9), room("b", 9, e=True), room("c", 9, b=True), room("d", 9, e=True, b=True)]
                self.assertEqual(weights(rooms), {"a": 90, "b": 120, "c": 105, "d": 135})

            def test_weight_errors(self):
                for bad in ([], [room("a", 5), room("a", 6)], [room("a", 0)], [room("a", -4)]):
                    with self.assertRaises(ValueError):
                        weights(bad)
                    with self.assertRaises(ValueError):
                        split(1000, bad)

            def test_even_split_leftover_goes_alphabetically(self):
                rooms = [room("c", 10), room("a", 10), room("b", 10)]
                self.assertEqual(split(100, rooms), {"a": 34, "b": 33, "c": 33})
                self.assertEqual(split(101, rooms), {"a": 34, "b": 34, "c": 33})
                self.assertEqual(split(2, rooms), {"a": 1, "b": 1, "c": 0})
                self.assertEqual(split(0, rooms), {"a": 0, "b": 0, "c": 0})

            def test_largest_remainder_wins(self):
                rooms = [room("a", 10), room("b", 15), room("c", 25)]  # weights 100, 150, 250
                self.assertEqual(split(1001, rooms), {"a": 200, "b": 300, "c": 501})
                self.assertEqual(split(7, [room("a", 10), room("b", 10, e=True)]), {"a": 3, "b": 4})

            def test_remainders_not_first_room(self):
                rooms = [room("a", 10), room("b", 10), room("c", 30)]  # 1/5, 1/5, 3/5 of 11 = 2.2, 2.2, 6.6
                self.assertEqual(split(11, rooms), {"a": 2, "b": 2, "c": 7})

            def test_single_room_and_negative(self):
                self.assertEqual(split(123456, [room("only", 8)]), {"only": 123456})
                with self.assertRaises(ValueError):
                    split(-5, [room("a", 5)])

            def test_differential(self):
                rng = random.Random(8)
                for _ in range(300):
                    n = rng.randint(1, 7)
                    names = rng.sample(["Zoe", "amy", "Bo", "cy", "Di", "ed", "Fay", "gus"], n)
                    rooms = [room(nm, rng.randint(5, 30), rng.random() < 0.4, rng.random() < 0.4) for nm in names]
                    total = rng.choice([0, 1, 99, 100_000, rng.randint(0, 300_000)])
                    w = weights(rooms)
                    whole = sum(w.values())
                    exact = {k: Fraction(total * v, whole) for k, v in w.items()}
                    want = {k: int(v) for k, v in exact.items()}
                    left = total - sum(want.values())
                    for k in sorted(w, key=lambda k: (-(exact[k] - int(exact[k])), k))[:left]:
                        want[k] += 1
                    self.assertEqual(split(total, rooms), want)
                    self.assertEqual(sum(split(total, rooms).values()), total)
    '''),
    bugs=[
        Bug("leftover-first", "for n in order[:missing]:", "for n in list(w)[:missing]:",
            ["split(11, [{'name': 'a', 'sqm': 10, 'ensuite': False, 'balcony': False}, {'name': 'b', 'sqm': 10, 'ensuite': False, 'balcony': False}, {'name': 'c', 'sqm': 30, 'ensuite': False, 'balcony': False}])"],
            "split", "the missing cents go to the first rooms listed"),
        Bug("tie-reverse", "key=lambda n: (-(exact[n] - shares[n]), n))", "key=lambda n: (-(exact[n] - shares[n]), [-ord(c) for c in n]))",
            ["split(100, [{'name': 'a', 'sqm': 10, 'ensuite': False, 'balcony': False}, {'name': 'b', 'sqm': 10, 'ensuite': False, 'balcony': False}, {'name': 'c', 'sqm': 10, 'ensuite': False, 'balcony': False}])"],
            "split", "equal remainders are served in reverse alphabetical order"),
        Bug("smallest-remainder", "key=lambda n: (-(exact[n] - shares[n]), n))", "key=lambda n: ((exact[n] - shares[n]), n))",
            ["split(1001, [{'name': 'a', 'sqm': 10, 'ensuite': False, 'balcony': False}, {'name': 'b', 'sqm': 15, 'ensuite': False, 'balcony': False}, {'name': 'c', 'sqm': 25, 'ensuite': False, 'balcony': False}])"],
            "split", "the smallest remainders get the extra cents"),
        Bug("balcony-bonus", "(15 if r[\"balcony\"] else 0)", "(30 if r[\"balcony\"] else 0)",
            ["weights([{'name': 'a', 'sqm': 9, 'ensuite': False, 'balcony': True}])"], "weights", "a balcony is worth 30 points"),
        Bug("ensuite-missing", "(30 if r[\"ensuite\"] else 0)", "0",
            ["weights([{'name': 'a', 'sqm': 9, 'ensuite': True, 'balcony': False}])"], "weights", "en-suite rooms get no bonus"),
        Bug("rounding-split", "shares = {n: int(v) for n, v in exact.items()}", "shares = {n: int(v + Fraction(1, 2)) for n, v in exact.items()}",
            ["split(5, [{'name': 'a', 'sqm': 10, 'ensuite': False, 'balcony': False}, {'name': 'b', 'sqm': 10, 'ensuite': False, 'balcony': False}, {'name': 'c', 'sqm': 10, 'ensuite': False, 'balcony': False}])"],
            "split", "shares are rounded to nearest first, so the leftover step can be negative"),
        Bug("duplicate-ok", "if r[\"name\"] in out:\n            raise ValueError(\"duplicate room name\")\n        ", "",
            ["weights([{'name': 'a', 'sqm': 9, 'ensuite': False, 'balcony': False}, {'name': 'a', 'sqm': 5, 'ensuite': False, 'balcony': False}])"],
            "weights", "duplicate room names overwrite each other silently"),
    ],
))
