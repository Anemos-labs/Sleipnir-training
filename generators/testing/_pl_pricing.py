"""Python libraries about pricing rules (parametrised: every call to a factory draws a different rule book)."""
from __future__ import annotations

from fx import dd

from ._engine import TLib
from ._pygold import gold_tests

WHERE_PY = ("Put your tests in `tests/` (plain `unittest`; there is no pytest here). They are run from the repository root with "
            "`python3 -m unittest discover -s tests -t .`.")
STUB_INIT = "\n"

ROUTE_NAMES = ["ARD-BRA", "ARD-COL", "BRA-COL", "COL-TIR", "TIR-ARD", "BRA-ISL", "ISL-COL", "KYL-ARD", "SKY-BRA", "OBA-ISL"]
NUMW = {2: "two", 3: "three", 4: "four", 5: "five"}


def ferry(rng) -> TLib:
    """Skerry Sound ferry fares: age bands, return and peak multipliers, bikes, family cap."""
    P = dict(
        infant=rng.choice([2, 4]), child=rng.choice([11, 15]), senior=rng.choice([60, 65]),
        child_pct=rng.choice([50, 40]), senior_pct=rng.choice([70, 75]), ret=rng.choice([175, 180, 190]),
        peak=rng.choice([10, 15, 20]), step=rng.choice([5, 10]), bike=rng.choice([200, 250]), max_bikes=rng.choice([3, 4]),
        group=rng.choice([4, 5]), cap=rng.choice([300, 350]),
    )
    routes = rng.sample(ROUTE_NAMES, 4)
    fares = {r: rng.choice(range(305, 1500, 10)) for r in routes}
    rt = "".join(f'    "{r}": {v},\n' for r, v in fares.items()).rstrip("\n")
    src = dd(f'''
        """Fare rules for the Skerry Sound ferries. All money is an int number of pence."""

        ROUTES = {{
        @@ROUTES@@
        }}

        INFANT_MAX = {P["infant"]}
        CHILD_MAX = {P["child"]}
        SENIOR_MIN = {P["senior"]}
        CHILD_PCT = {P["child_pct"]}
        SENIOR_PCT = {P["senior_pct"]}
        RETURN_PCT = {P["ret"]}
        PEAK_PCT = {P["peak"]}
        STEP = {P["step"]}
        BIKE_PENCE = {P["bike"]}
        MAX_BIKES = {P["max_bikes"]}
        GROUP_MIN = {P["group"]}
        CAP_PCT = {P["cap"]}


        class UnknownRoute(KeyError):
            """The route code is not in the timetable."""


        def base_fare(route):
            try:
                return ROUTES[route]
            except KeyError:
                raise UnknownRoute(route) from None


        def _round_up(num, den):
            """The smallest multiple of STEP pence that is >= num/den."""
            steps = -(-num // (den * STEP))
            return steps * STEP


        def _price(base, pct, return_trip, peak):
            num, den = base * pct, 100
            if return_trip:
                num *= RETURN_PCT
                den *= 100
            if peak:
                num *= 100 + PEAK_PCT
                den *= 100
            return _round_up(num, den)


        def passenger_fare(route, age, return_trip=False, peak=False):
            base = base_fare(route)
            if age < 0 or age > 120:
                raise ValueError(f"age out of range: {{age}}")
            if age <= INFANT_MAX:
                return 0
            if age <= CHILD_MAX:
                pct = CHILD_PCT
            elif age >= SENIOR_MIN:
                pct = SENIOR_PCT
            else:
                pct = 100
            return _price(base, pct, return_trip, peak)


        def bike_charge(bikes, return_trip=False):
            if bikes < 0 or bikes > MAX_BIKES:
                raise ValueError(f"bikes out of range: {{bikes}}")
            paid = bikes - 1 if (return_trip and bikes > 0) else bikes
            return paid * BIKE_PENCE


        def quote(route, ages, return_trip=False, peak=False, bikes=0):
            if not ages:
                raise ValueError("a booking needs at least one passenger")
            fares = [passenger_fare(route, a, return_trip, peak) for a in ages]
            subtotal = sum(fares)
            capped = False
            if len(ages) >= GROUP_MIN and any(a > CHILD_MAX for a in ages):
                cap = _price(base_fare(route), CAP_PCT, return_trip, peak)
                if subtotal > cap:
                    subtotal = cap
                    capped = True
            extra = bike_charge(bikes, return_trip)
            return {{"passengers": fares, "subtotal": subtotal, "bikes": extra, "total": subtotal + extra, "capped": capped}}
    ''').replace("@@ROUTES@@", rt)
    names = list(fares)
    readme = dd(f'''
        # ferryfare

        Fare rules for the Skerry Sound ferries, used by the ticket office and the website. Money is always an `int`
        number of **pence**. Routes are the codes in `ferryfare.fares.ROUTES` ({", ".join("`" + r + "`" for r in names)});
        the table value is the adult single fare.

        ## `base_fare(route) -> int`
        The adult single fare of the route. An unknown route raises `UnknownRoute` (a `KeyError` subclass).

        ## `passenger_fare(route, age, return_trip=False, peak=False) -> int`
        The fare for one passenger.

        * The route is checked first (`UnknownRoute`), then the age: ages below 0 or above 120 raise `ValueError`.
        * Age bands: ages `0..{P["infant"]}` travel free (fare `0`); `{P["infant"] + 1}..{P["child"]}` pay {P["child_pct"]}% of the adult fare;
          `{P["senior"]}` and over pay {P["senior_pct"]}%; everybody else pays 100%.
        * A return trip costs {P["ret"]}% of the single fare, a peak sailing adds {P["peak"]}% on top. The percentages are applied to the
          exact amount in sequence (age band, then return, then peak) with no intermediate rounding.
        * Only the final amount is rounded, **up** to the next multiple of {P["step"]}p (an amount that is already a multiple is left as it is).

        ## `bike_charge(bikes, return_trip=False) -> int`
        {P["bike"]}p per bicycle. On a return trip the first bicycle travels free. `bikes` below 0 or above {P["max_bikes"]} is a `ValueError`.

        ## `quote(route, ages, return_trip=False, peak=False, bikes=0) -> dict`
        Prices a whole booking. `ages` is a list of passenger ages and must not be empty (`ValueError`). Returns a dict with

        * `passengers`: the list of individual fares, in the order of `ages`;
        * `subtotal`: their sum, except that a *party* (`{P["group"]}` or more passengers, at least one of them older than {P["child"]}) never pays more than
          the *cap*: the fare of a passenger who pays {P["cap"]}% of the adult fare on the same terms (return/peak, same rounding).
          `passengers` still lists the uncapped individual fares;
        * `bikes`: the bicycle charge; `total`: `subtotal + bikes`;
        * `capped`: `True` only when the cap actually lowered the subtotal.
    ''')
    files = {"README.md": readme, "ferryfare/__init__.py": '"""Ferry fares."""\n', "ferryfare/fares.py": src, "tests/__init__.py": ""}
    stub = {
        "tests/test_smoke.py": dd('''
            import unittest

            from ferryfare import fares


            class SmokeTest(unittest.TestCase):
                def test_api_is_there(self):
                    self.assertTrue(callable(fares.quote))
                    self.assertTrue(callable(fares.passenger_fare))
        '''),
    }
    r0, r1, r2, r3 = names
    ad = (P["child"] + P["senior"]) // 2 + 1  # an adult age
    adult = min(max(ad, P["child"] + 1), P["senior"] - 1)
    g = P["group"]
    ns: dict = {}
    exec(src, ns)
    exact = None
    for rt_flag in (False, True):
        for pk_flag in (False, True):
            for route in names:
                cap = ns["_price"](fares[route], P["cap"], rt_flag, pk_flag)
                for n_ad in range(1, 6):
                    for n_ch in range(0, 4):
                        for n_inf in range(0, 3):
                            ages = [adult] * n_ad + [P["child"]] * n_ch + [0] * n_inf
                            if len(ages) < P["group"]:
                                continue
                            q = ns["quote"](route, ages, rt_flag, pk_flag)
                            if q["subtotal"] == cap and sum(q["passengers"]) == cap and exact is None:
                                exact = (route, ages, rt_flag, pk_flag)
    steps = [
        ("base_fares", [("eq", f"base_fare('{r}')") for r in names] + [("raises", "UnknownRoute", "base_fare('XXX-YYY')"),
                                                                       ("raises", "UnknownRoute", "passenger_fare('nope', 30)")]),
        ("age_band_edges", [("eq", f"passenger_fare('{r0}', {a})") for a in
                            [0, P["infant"], P["infant"] + 1, P["child"], P["child"] + 1, adult, P["senior"] - 1, P["senior"], 120]]),
        ("age_out_of_range", [("raises", "ValueError", f"passenger_fare('{r0}', -1)"), ("raises", "ValueError", f"passenger_fare('{r0}', 121)"),
                              ("raises", "UnknownRoute", "passenger_fare('nope', -5)")]),
        ("rounding_per_route", [("eq", f"passenger_fare('{r}', {a})") for r in names for a in (P["child"], P["senior"])]),
        ("return_and_peak", [("eq", f"passenger_fare('{r}', {a}, {rt_}, {pk})") for r in (r1, r2) for a in (adult, P["child"], P["senior"])
                             for rt_ in (False, True) for pk in (False, True)]),
        ("return_peak_infant", [("eq", f"passenger_fare('{r3}', {P['infant']}, True, True)")]),
        ("bikes", [("eq", f"bike_charge({b})") for b in range(P["max_bikes"] + 1)]
                  + [("eq", f"bike_charge({b}, True)") for b in range(P["max_bikes"] + 1)]
                  + [("raises", "ValueError", f"bike_charge({P['max_bikes'] + 1})"), ("raises", "ValueError", "bike_charge(-1)"),
                     ("raises", "ValueError", f"bike_charge({P['max_bikes'] + 1}, True)")]),
        ("quote_single_passenger", [("eq", f"quote('{r1}', [{adult}])"), ("eq", f"quote('{r1}', [{P['child']}], True, True, bikes=2)"),
                                    ("eq", f"quote('{r2}', [{P['senior']}], peak=True, bikes=1)")]),
        ("quote_order_of_ages", [("eq", f"quote('{r0}', [{P['senior']}, {adult}, {P['child']}, 0])"),
                                 ("eq", f"quote('{r0}', [0, {adult}])['passengers']")]),
        ("quote_errors", [("raises", "ValueError", f"quote('{r0}', [])"), ("raises", "UnknownRoute", "quote('nope', [30])"),
                          ("raises", "ValueError", f"quote('{r0}', [30], bikes={P['max_bikes'] + 1})"),
                          ("raises", "ValueError", f"quote('{r0}', [30, -2])")]),
        ("party_just_below_size", [("eq", f"quote('{r2}', [{adult}] * {g - 1})"), ("eq", f"quote('{r2}', [{adult}] * {g - 1}, True, True)")]),
        ("party_capped", [("eq", f"quote('{r2}', [{adult}] * {g})"), ("eq", f"quote('{r2}', [{adult}] * {g + 2}, True)"),
                          ("eq", f"quote('{r3}', [{adult}] * {g}, True, True, bikes=1)"),
                          ("eq", f"quote('{r1}', [{P['senior']}] * {g})")]),
        ("party_needs_an_adult", [("eq", f"quote('{r2}', [{P['child']}] * {g + 1})"), ("eq", f"quote('{r2}', [{P['child']}] * {g}, True)"),
                                  ("eq", f"quote('{r2}', [{P['child'] + 1}] * {g - 1} + [{P['child']}])"),
                                  ("eq", f"quote('{r2}', [{P['child']}] * {g - 1} + [{P['child'] + 1}])")]),
        ("party_exactly_at_cap", [("eq", f"quote({exact[0]!r}, {exact[1]!r}, {exact[2]}, {exact[3]})")] if exact else []),
        ("party_under_cap_not_flagged", [("eq", f"quote('{r0}', [{adult}] + [0] * {g - 1})"), ("eq", f"quote('{r0}', [{adult}, {P['child']}] + [0] * {g})")]),
    ]
    gold = gold_tests(files, "from ferryfare.fares import *\nfrom ferryfare import fares", steps)
    probes = [f"passenger_fare('{r0}', {P['child']})", f"passenger_fare('{r0}', {P['child'] + 1})", f"passenger_fare('{r1}', {P['senior']}, True)",
              f"quote('{r2}', [{adult}] * {g})['total']", f"quote('{r2}', [{adult}] * {g - 1})['subtotal']", f"bike_charge(1, True)",
              f"passenger_fare('{r3}', {adult}, False, True)", f"quote('{r1}', [{P['child']}] * {g})['capped']"]
    return TLib(
        name="py-ferryfare", lang="python", title="the Skerry Sound ferry fare calculator", blurb="The ticket office and the website both price bookings with `ferryfare`.",
        files=files, stub=stub, gold=gold, mutate=["ferryfare/fares.py"], cmd="python3 -m unittest discover -s tests -t .",
        where=WHERE_PY, difficulty=3, probes=probes, probe_import="from ferryfare.fares import *", renames={"_price": "_compose_fare", "_round_up": "_ceil_to_step"},
    )
