"""Dispatch-style simulations in domain clothes (python, fix-py-3): lift cars, support-ticket aging, toll routing."""
from fx import Lib, dd

from generators.fix._pylib3 import chain, register_libs3

GITIGNORE = "__pycache__/\n*.pyc\n"

# ======================================================================================================================
# liftsim: a tick-based lift dispatcher (multi-module)
# ======================================================================================================================

LIFTSIM_README = dd('''
    # liftsim

    A tiny deterministic simulator of a bank of lifts. Time is counted in whole **ticks** starting at 0; floors are
    integers (the lobby is floor 0).

    ## `liftsim.car`

    `choose_direction(floor, direction, stops) -> int` is the scan rule. `direction` is `+1`, `-1` or `0` (idle) and
    `stops` is a collection of floors that does not contain `floor`. It returns the direction to move in, `0` to
    stay:

    * no stops: `0`;
    * travelling up (`+1`): keep going up while any stop is above, otherwise turn down if any stop is below;
    * travelling down (`-1`): the mirror image;
    * idle with stops on one side only: go to that side; with stops on both sides go towards the *nearest* stop, and
      when the nearest stops are equally far, go up.

    `Car(id, floor=0, floors=None)` has `id`, `floor`, `direction` (starts at `0`), `stops` (a `set` of floors it has
    to open its doors at) and `riders` (a list of passengers on board). `floors` is `None` (the car serves every
    floor) or a collection of the only floors it serves; `serves(floor)` tells. `move()` sets `direction` to
    `choose_direction(...)`, changes `floor` by it, and returns the new direction.

    ## `liftsim.dispatch`

    * `cost(car, floor) -> int`: `abs(car.floor - floor) + 2 * len(car.stops)`, plus `3` when the car has a direction
      and `floor` lies on the other side of the car than that direction (strictly behind it). A call at the car's own
      floor is never "behind".
    * `assign(cars, origin, dest) -> Car`: among the cars that serve both `origin` and `dest`, the one with the
      lowest `cost(car, origin)`; ties go to the lowest `car.id`. `ValueError` when no car serves both floors.

    ## `liftsim.sim`

    `Passenger(id, origin, dest, t)` (a dataclass; `t` is the arrival tick). `run(passengers, cars, max_ticks=500)`
    returns a list of `Trip(id, car, wait, ride, boarded, delivered)` sorted by passenger id, where `car` is the id of
    the car that carried the passenger, `boarded` and `delivered` are tick numbers, `wait = boarded - t` and
    `ride = delivered - boarded`.

    A passenger with `origin == dest` is a `ValueError` (checked before anything runs, as are duplicate passenger
    ids). For every tick `t = 0, 1, 2, ...`:

    1. Passengers whose arrival tick is `t` are dispatched in id order with `assign`; the origin is added to the
       chosen car's `stops` and the passenger waits at the origin for that car (only).
    2. Then each car, in id order, does one thing: if its `floor` is in its `stops` its doors cycle (the car does not
       move): the floor leaves `stops`, every rider whose destination is this floor is delivered (`delivered = t`),
       then the passengers waiting here for *this* car board (`boarded = t`) in arrival order (arrival tick, then id)
       and each boarding passenger's destination is added to `stops`. Otherwise the car calls `move()`.

    The simulation ends at the tick in which the last passenger is delivered. Only the ticks `0 .. max_ticks - 1` are
    simulated: if somebody is still undelivered after the last of them, `RuntimeError`. With no passengers the result
    is `[]`.

    * `stats(trips) -> dict`: `{"count": n, "max_wait": ..., "total_wait": ..., "avg_wait_tenths": ...}`, where
      `avg_wait_tenths` is the mean wait in tenths of a tick, rounded half up (`0` when there are no trips, and the
      other numbers are `0` too).
''')

LIFTSIM_CAR = dd('''
    """A lift car and the scan rule that steers it."""


    def choose_direction(floor, direction, stops):
        above = [s for s in stops if s > floor]
        below = [s for s in stops if s < floor]
        if not above and not below:
            return 0
        if direction == 0:
            if above and below:
                return 1 if min(above) - floor <= floor - max(below) else -1
            return 1 if above else -1
        ahead = above if direction > 0 else below
        return direction if ahead else -direction


    class Car:
        def __init__(self, car_id, floor=0, floors=None):
            self.id = car_id
            self.floor = floor
            self.floors = None if floors is None else frozenset(floors)
            self.direction = 0
            self.stops = set()
            self.riders = []

        def serves(self, floor):
            return self.floors is None or floor in self.floors

        def move(self):
            self.direction = choose_direction(self.floor, self.direction, self.stops)
            self.floor += self.direction
            return self.direction
''')

LIFTSIM_DISPATCH = dd('''
    """Which car answers a call."""


    def cost(car, floor):
        total = abs(car.floor - floor) + 2 * len(car.stops)
        if car.direction and (floor - car.floor) * car.direction < 0:
            total += 3
        return total


    def assign(cars, origin, dest):
        able = [c for c in cars if c.serves(origin) and c.serves(dest)]
        if not able:
            raise ValueError(f"no car serves floors {origin} and {dest}")
        return min(able, key=lambda c: (cost(c, origin), c.id))
''')

LIFTSIM_SIM = dd('''
    """The tick loop."""
    from dataclasses import dataclass

    from .dispatch import assign


    @dataclass
    class Passenger:
        id: int
        origin: int
        dest: int
        t: int


    @dataclass
    class Trip:
        id: int
        car: int
        wait: int
        ride: int
        boarded: int
        delivered: int


    def run(passengers, cars, max_ticks=500):
        ids = [p.id for p in passengers]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate passenger id")
        for p in passengers:
            if p.origin == p.dest:
                raise ValueError(f"passenger {p.id} has the same origin and destination")
        arrivals = sorted(passengers, key=lambda p: (p.t, p.id))
        nxt = 0
        waiting = []  # (passenger, car id) in arrival order
        log = {}
        delivered = 0
        for t in range(max_ticks):
            while nxt < len(arrivals) and arrivals[nxt].t <= t:
                p = arrivals[nxt]
                nxt += 1
                car = assign(cars, p.origin, p.dest)
                car.stops.add(p.origin)
                waiting.append((p, car.id))
            for car in cars:
                if car.floor in car.stops:
                    car.stops.discard(car.floor)
                    stay = []
                    for rider in car.riders:
                        if rider.dest == car.floor:
                            log[rider.id]["delivered"] = t
                            delivered += 1
                        else:
                            stay.append(rider)
                    car.riders = stay
                    left = []
                    for p, cid in waiting:
                        if cid == car.id and p.origin == car.floor:
                            car.riders.append(p)
                            car.stops.add(p.dest)
                            log[p.id] = {"car": car.id, "boarded": t, "t": p.t}
                        else:
                            left.append((p, cid))
                    waiting = left
                else:
                    car.move()
            if delivered == len(passengers):
                break
        else:
            if passengers:
                raise RuntimeError("not everyone was delivered in time")
        trips = []
        for pid in sorted(log):
            e = log[pid]
            trips.append(Trip(pid, e["car"], e["boarded"] - e["t"], e["delivered"] - e["boarded"], e["boarded"], e["delivered"]))
        return trips


    def stats(trips):
        n = len(trips)
        if n == 0:
            return {"count": 0, "max_wait": 0, "total_wait": 0, "avg_wait_tenths": 0}
        total = sum(t.wait for t in trips)
        return {
            "count": n,
            "max_wait": max(t.wait for t in trips),
            "total_wait": total,
            "avg_wait_tenths": (20 * total + n) // (2 * n),
        }
''')

LIFTSIM_VISIBLE = dd('''
    import unittest

    from liftsim.car import Car, choose_direction
    from liftsim.sim import Passenger, run


    class BasicTests(unittest.TestCase):
        def test_scan_keeps_going(self):
            self.assertEqual(choose_direction(3, 1, {5, 1}), 1)

        def test_one_passenger(self):
            trips = run([Passenger(1, 0, 3, 0)], [Car(0)])
            self.assertEqual((trips[0].boarded, trips[0].delivered), (0, 4))


    if __name__ == "__main__":
        unittest.main()
''')

LIFTSIM_HIDDEN_CAR = dd('''
    import unittest

    from liftsim.car import Car, choose_direction


    class ScanRule(unittest.TestCase):
        def test_no_stops(self):
            for d in (-1, 0, 1):
                self.assertEqual(choose_direction(4, d, set()), 0)
                self.assertEqual(choose_direction(4, d, []), 0)

        def test_keeps_direction_while_stops_ahead(self):
            self.assertEqual(choose_direction(4, 1, {6, 1}), 1)
            self.assertEqual(choose_direction(4, -1, {6, 1}), -1)
            self.assertEqual(choose_direction(4, 1, {5}), 1)
            self.assertEqual(choose_direction(4, -1, {3}), -1)

        def test_turns_when_nothing_ahead(self):
            self.assertEqual(choose_direction(4, 1, {1, 2}), -1)
            self.assertEqual(choose_direction(4, -1, {5, 9}), 1)

        def test_idle_one_sided(self):
            self.assertEqual(choose_direction(4, 0, {9}), 1)
            self.assertEqual(choose_direction(4, 0, {0}), -1)
            self.assertEqual(choose_direction(0, 0, {1}), 1)

        def test_idle_nearest_wins(self):
            self.assertEqual(choose_direction(4, 0, {6, 3}), -1)
            self.assertEqual(choose_direction(4, 0, {9, 3}), -1)
            self.assertEqual(choose_direction(4, 0, {5, 0}), 1)
            self.assertEqual(choose_direction(4, 0, {5, 0, 1}), 1)
            self.assertEqual(choose_direction(4, 0, {8, 3}), -1)
            self.assertEqual(choose_direction(4, 0, {7, 1, 3}), -1)
            self.assertEqual(choose_direction(4, 0, {5, 9, 1}), 1)
            self.assertEqual(choose_direction(4, 0, {8, 7, 2, 0}), -1)

        def test_idle_tie_goes_up(self):
            self.assertEqual(choose_direction(4, 0, {6, 2}), 1)
            self.assertEqual(choose_direction(5, 0, {6, 4}), 1)

        def test_uses_nearest_not_farthest(self):
            self.assertEqual(choose_direction(10, 0, {11, 0}), 1)
            self.assertEqual(choose_direction(10, 0, {19, 9}), -1)


    class CarTests(unittest.TestCase):
        def test_defaults(self):
            c = Car(3)
            self.assertEqual((c.id, c.floor, c.direction, c.stops, c.riders), (3, 0, 0, set(), []))
            self.assertTrue(c.serves(0) and c.serves(99))

        def test_serves_subset(self):
            c = Car(1, floors=[0, 5, 6])
            self.assertTrue(c.serves(5))
            self.assertFalse(c.serves(4))
            self.assertTrue(c.serves(0))

        def test_move(self):
            c = Car(0, floor=2)
            c.stops.add(5)
            self.assertEqual(c.move(), 1)
            self.assertEqual((c.floor, c.direction), (3, 1))
            c.stops = {1}
            self.assertEqual(c.move(), -1)
            self.assertEqual((c.floor, c.direction), (2, -1))
            c.stops = set()
            self.assertEqual(c.move(), 0)
            self.assertEqual((c.floor, c.direction), (2, 0))

        def test_move_keeps_direction_with_stops_ahead(self):
            c = Car(0, floor=5)
            c.direction = -1
            c.stops = {9, 4}
            c.move()
            self.assertEqual((c.floor, c.direction), (4, -1))


    if __name__ == "__main__":
        unittest.main()
''')

LIFTSIM_HIDDEN_SIM = dd('''
    import unittest

    from liftsim.car import Car
    from liftsim.dispatch import assign, cost
    from liftsim.sim import Passenger, run, stats

    P = Passenger


    def key(trips):
        return [(t.id, t.car, t.boarded, t.delivered, t.wait, t.ride) for t in trips]


    class Cost(unittest.TestCase):
        def test_distance_and_stops(self):
            c = Car(0, floor=3)
            self.assertEqual(cost(c, 3), 0)
            self.assertEqual(cost(c, 7), 4)
            self.assertEqual(cost(c, 1), 2)
            c.stops = {4, 9}
            self.assertEqual(cost(c, 7), 4 + 4)

        def test_behind_penalty(self):
            c = Car(0, floor=5)
            c.direction = 1
            self.assertEqual(cost(c, 2), 3 + 3)
            self.assertEqual(cost(c, 8), 3)
            self.assertEqual(cost(c, 5), 0)
            c.direction = -1
            self.assertEqual(cost(c, 8), 3 + 3)
            self.assertEqual(cost(c, 2), 3)
            self.assertEqual(cost(c, 5), 0)
            c.direction = 0
            self.assertEqual(cost(c, 8), 3)
            self.assertEqual(cost(c, 2), 3)


    class Assign(unittest.TestCase):
        def test_nearest_car(self):
            cars = [Car(0, floor=0), Car(1, floor=8)]
            self.assertIs(assign(cars, 7, 2), cars[1])
            self.assertIs(assign(cars, 1, 2), cars[0])

        def test_tie_goes_to_lowest_id(self):
            cars = [Car(2, floor=4), Car(1, floor=6)]
            self.assertIs(assign(cars, 5, 0), cars[1])
            cars = [Car(0, floor=4), Car(1, floor=6)]
            self.assertIs(assign(cars, 5, 0), cars[0])

        def test_busy_car_loses(self):
            cars = [Car(0, floor=4), Car(1, floor=5)]
            cars[1].stops = {9, 8}
            self.assertIs(assign(cars, 5, 0), cars[0])

        def test_service_restrictions(self):
            low = Car(0, floor=0, floors=[0, 1, 2, 3])
            high = Car(1, floor=9, floors=[0, 4, 5, 6, 7, 8, 9])
            self.assertIs(assign([low, high], 2, 3), low)
            self.assertIs(assign([low, high], 8, 4), high)
            self.assertIs(assign([low, high], 0, 9), high)
            self.assertIs(assign([low, high], 9, 0), high)
            with self.assertRaises(ValueError):
                assign([low, high], 2, 8)
            with self.assertRaises(ValueError):
                assign([low, high], 8, 2)
            with self.assertRaises(ValueError):
                assign([], 1, 2)


    class Runs(unittest.TestCase):
        def test_single_passenger_up(self):
            trips = run([P(1, 0, 3, 0)], [Car(0)])
            self.assertEqual(key(trips), [(1, 0, 0, 4, 0, 4)])

        def test_car_must_come_to_passenger(self):
            trips = run([P(1, 2, 0, 0)], [Car(0, floor=5)])
            self.assertEqual(key(trips), [(1, 0, 3, 6, 3, 3)])

        def test_late_arrival(self):
            trips = run([P(1, 0, 2, 7)], [Car(0)])
            self.assertEqual(key(trips), [(1, 0, 7, 10, 0, 3)])

        def test_two_riders_same_direction(self):
            trips = run([P(1, 0, 5, 0), P(2, 0, 3, 0)], [Car(0)])
            self.assertEqual(key(trips), [(1, 0, 0, 7, 0, 7), (2, 0, 0, 4, 0, 4)])

        def test_pick_up_on_the_way(self):
            trips = run([P(1, 0, 6, 0), P(2, 3, 5, 1)], [Car(0)])
            # P1 boards at tick 0; P2 arrives at tick 1 and the car reaches floor 3 at tick 3: doors at tick 4 (wait 3)
            self.assertEqual(key(trips)[1][:4], (2, 0, 4, 7))
            self.assertEqual(key(trips)[0][:4], (1, 0, 0, 9))

        def test_turnaround(self):
            trips = run([P(1, 4, 0, 0), P(2, 1, 0, 0)], [Car(0)])
            # stops {4, 1}: the idle car at 0 goes up (tick 0 reaches 1, tick 1 doors), on to 4 (doors at tick 5), then down
            self.assertEqual(key(trips)[1][:4], (2, 0, 1, 10))
            self.assertEqual(key(trips)[0][:4], (1, 0, 5, 10))

        def test_passenger_for_a_different_car_does_not_board(self):
            cars = [Car(0, floor=0), Car(1, floor=6)]
            trips = run([P(1, 5, 2, 0)], cars)
            self.assertEqual(key(trips), [(1, 1, 1, 5, 1, 4)])

        def test_two_cars_share_work(self):
            cars = [Car(0, floor=0), Car(1, floor=9)]
            trips = run([P(1, 1, 4, 0), P(2, 8, 3, 0)], cars)
            self.assertEqual([(t.id, t.car) for t in trips], [(1, 0), (2, 1)])
            self.assertEqual([t.delivered for t in trips], [5, 7])

        def test_ordering_of_boarding_and_ids(self):
            trips = run([P(9, 0, 2, 0), P(3, 0, 4, 0), P(5, 0, 1, 0)], [Car(0)])
            self.assertEqual([t.id for t in trips], [3, 5, 9])
            self.assertTrue(all(t.boarded == 0 for t in trips))
            self.assertEqual({t.id: t.delivered for t in trips}, {5: 2, 9: 4, 3: 7})

        def test_arrival_ties_dispatch_in_id_order(self):
            cars = [Car(0, floor=4), Car(1, floor=6)]
            trips = run([P(2, 5, 0, 0), P(1, 5, 9, 0)], cars)
            # passenger 1 is dispatched first and takes car 0 (tie on cost, lowest id); then car 0 is busier so 2 takes car 1
            self.assertEqual([(t.id, t.car) for t in trips], [(1, 0), (2, 1)])

        def test_restricted_cars(self):
            cars = [Car(0, floors=[0, 1, 2, 3]), Car(1, floors=[0, 4, 5, 6])]
            trips = run([P(1, 0, 6, 0), P(2, 0, 3, 0)], cars)
            self.assertEqual([(t.id, t.car) for t in trips], [(1, 1), (2, 0)])
            self.assertEqual([t.delivered for t in trips], [7, 4])

        def test_no_passengers(self):
            self.assertEqual(run([], [Car(0)]), [])

        def test_validation(self):
            with self.assertRaises(ValueError):
                run([P(1, 2, 2, 0)], [Car(0)])
            with self.assertRaises(ValueError):
                run([P(1, 0, 2, 0), P(1, 0, 3, 0)], [Car(0)])
            with self.assertRaises(ValueError):
                run([P(1, 0, 9, 0)], [Car(0, floors=[0, 1])])

        def test_max_ticks(self):
            with self.assertRaises(RuntimeError):
                run([P(1, 0, 30, 0)], [Car(0)], max_ticks=20)
            trips = run([P(1, 0, 30, 0)], [Car(0)], max_ticks=32)
            self.assertEqual(trips[0].delivered, 31)

        def test_default_max_ticks_is_500(self):
            self.assertEqual(run([P(1, 0, 498, 0)], [Car(0)])[0].delivered, 499)
            with self.assertRaises(RuntimeError):
                run([P(1, 0, 499, 0)], [Car(0)])

        def test_cars_are_left_in_final_state(self):
            car = Car(0)
            run([P(1, 0, 3, 0)], [car])
            self.assertEqual(car.floor, 3)
            self.assertEqual(car.stops, set())
            self.assertEqual(car.riders, [])


    class Stats(unittest.TestCase):
        def test_empty(self):
            self.assertEqual(stats([]), {"count": 0, "max_wait": 0, "total_wait": 0, "avg_wait_tenths": 0})

        def test_values(self):
            trips = run([P(1, 0, 5, 0), P(2, 3, 0, 0), P(3, 0, 2, 20)], [Car(0)])
            s = stats(trips)
            waits = [t.wait for t in trips]
            self.assertEqual(s["count"], 3)
            self.assertEqual(s["total_wait"], sum(waits))
            self.assertEqual(s["max_wait"], max(waits))
            self.assertEqual(s["avg_wait_tenths"], (20 * sum(waits) + 3) // 6)

        def test_rounding_half_up(self):
            from liftsim.sim import Trip
            trips = [Trip(1, 0, 1, 1, 1, 2), Trip(2, 0, 2, 1, 2, 3)]
            self.assertEqual(stats(trips)["avg_wait_tenths"], 15)
            trips = [Trip(1, 0, 0, 1, 0, 1), Trip(2, 0, 0, 1, 0, 1), Trip(3, 0, 1, 1, 1, 2)]
            self.assertEqual(stats(trips)["avg_wait_tenths"], 3)
            trips = [Trip(1, 0, 1, 1, 1, 2), Trip(2, 0, 1, 1, 1, 2), Trip(3, 0, 0, 1, 0, 1)]
            self.assertEqual(stats(trips)["avg_wait_tenths"], 7)
            trips = [Trip(i, 0, w, 1, w, w + 1) for i, w in enumerate([0, 0, 0, 0, 0, 0, 0, 0, 0, 1], 1)]
            self.assertEqual(stats(trips)["avg_wait_tenths"], 1)
            self.assertEqual(stats([Trip(1, 0, 3, 1, 3, 4), Trip(2, 0, 4, 1, 4, 5)])["avg_wait_tenths"], 35)


    if __name__ == "__main__":
        unittest.main()
''')

_LS = "from liftsim.car import Car\\nfrom liftsim.sim import Passenger, run\\n"

LIFTSIM = Lib(
    name="liftsim", lang="python", title="the liftsim lift dispatcher",
    blurb="The building-management team uses liftsim to replay a morning's passenger arrivals against a bank of lifts and compare waiting times.",
    files={
        "liftsim/__init__.py": "", "liftsim/car.py": LIFTSIM_CAR, "liftsim/dispatch.py": LIFTSIM_DISPATCH,
        "liftsim/sim.py": LIFTSIM_SIM, "README.md": LIFTSIM_README, ".gitignore": GITIGNORE,
    },
    visible_tests={"tests/test_basic.py": LIFTSIM_VISIBLE},
    hidden_tests={"tests/test_car.py": LIFTSIM_HIDDEN_CAR, "tests/test_sim.py": LIFTSIM_HIDDEN_SIM},
    mutate=["liftsim/car.py", "liftsim/dispatch.py", "liftsim/sim.py"],
    difficulty=4, tags=["simulation", "dispatch", "multi-module"],
    probes=[
        "choose_direction(4, 0, {6, 2})", "choose_direction(4, 0, {9, 3})", "choose_direction(4, 1, {1, 2})",
        "[(t.id, t.boarded, t.delivered) for t in run([Passenger(1, 0, 3, 0)], [Car(0)])]",
        "[(t.id, t.boarded, t.delivered) for t in run([Passenger(1, 2, 0, 0)], [Car(0, floor=5)])]",
        "[(t.id, t.boarded, t.delivered) for t in run([Passenger(1, 0, 5, 0), Passenger(2, 0, 3, 0)], [Car(0)])]",
        "[(t.id, t.car, t.delivered) for t in run([Passenger(1, 4, 0, 0), Passenger(2, 1, 0, 0)], [Car(0)])]",
        "[(t.id, t.car, t.delivered) for t in run([Passenger(1, 5, 2, 0)], [Car(0), Car(1, floor=6)])]",
        "[(t.id, t.car) for t in run([Passenger(1, 0, 6, 0), Passenger(2, 0, 3, 0)], [Car(0, floors=[0, 1, 2, 3]), Car(1, floors=[0, 4, 5, 6])])]",
        "[(t.id, t.car) for t in run([Passenger(2, 5, 0, 0), Passenger(1, 5, 9, 0)], [Car(0, floor=4), Car(1, floor=6)])]",
        "stats(run([Passenger(1, 0, 5, 0), Passenger(2, 3, 0, 0)], [Car(0)]))",
    ],
    probe_import="from liftsim.car import Car, choose_direction\nfrom liftsim.dispatch import assign, cost\nfrom liftsim.sim import Passenger, run, stats\n",
)

# ======================================================================================================================
# triageq: a support-desk queue whose tickets age (multi-module)
# ======================================================================================================================

TRIAGEQ_README = dd('''
    # triageq

    The queue of a support desk. Tickets have a base priority from `1` (most urgent) to `5`, but a ticket that waits
    gets *more* urgent over time, so nothing starves. Times are whole minutes since some fixed origin.

    ## `triageq.ticket`

    `Ticket(id, prio, created, vip=False, pinned=False)` is a frozen dataclass. `prio` must be an integer from 1 to 5
    and `created` must not be negative, otherwise `ValueError`.

    ## `triageq.aging`

    Constants: `STEP = 30` (minutes of waiting that earn one priority level) and `OVERDUE = 240` (minutes of
    waiting after which a ticket is overdue).

    * `waited(ticket, now) -> int`: `now - created`; `ValueError` if `now < created`.
    * `effective_priority(ticket, now, step=STEP) -> int`: `prio` minus one level per *full* `step` minutes waited,
      minus one more level for a VIP ticket, never below `1`.
    * `is_overdue(ticket, now, limit=OVERDUE) -> bool`: waited at least `limit` minutes.
    * `sort_key(ticket, now, step=STEP, limit=OVERDUE)`: the tuple that orders the queue, smallest first:
      pinned tickets before all others; then overdue tickets before those not overdue; then the effective priority;
      then the older `created`; then `id` (compared as strings).

    ## `triageq.queue`

    `TicketQueue(step=STEP, limit=OVERDUE)` (`ValueError` if `step < 1` or `limit < 1`). Every method that takes `now`
    evaluates the queue at that time with the queue's `step` and `limit`.

    * `push(ticket)`: add a ticket (`ValueError` if a ticket with the same id is already queued). `len(q)` and
      `id in q` work.
    * `order(now) -> list[Ticket]`: all tickets, best first (by `sort_key`).
    * `peek(now)`: the best ticket or `None` if the queue is empty. `pop(now)`: the same but it is removed.
    * `remove(ticket_id) -> Ticket`: remove and return a ticket; `KeyError` if it is not queued.
    * `escalated(now) -> list[str]`: sorted ids of the tickets whose effective priority is *strictly better* than
      their base priority.
    * `overdue_ids(now) -> list[str]`: sorted ids of the overdue tickets.
    * `histogram(now) -> dict`: for each level `1..5` the number of queued tickets with that effective priority
      (levels without tickets are present with `0`).
''')

TRIAGEQ_TICKET = dd('''
    """Support tickets."""
    from dataclasses import dataclass


    @dataclass(frozen=True)
    class Ticket:
        id: str
        prio: int
        created: int
        vip: bool = False
        pinned: bool = False

        def __post_init__(self):
            if not isinstance(self.prio, int) or not 1 <= self.prio <= 5:
                raise ValueError("prio must be an integer from 1 to 5")
            if self.created < 0:
                raise ValueError("created must not be negative")
''')

TRIAGEQ_AGING = dd('''
    """How priorities improve while a ticket waits."""

    STEP = 30
    OVERDUE = 240


    def waited(ticket, now):
        if now < ticket.created:
            raise ValueError("now is before the ticket was created")
        return now - ticket.created


    def effective_priority(ticket, now, step=STEP):
        level = ticket.prio - waited(ticket, now) // step
        if ticket.vip:
            level -= 1
        return max(1, level)


    def is_overdue(ticket, now, limit=OVERDUE):
        return waited(ticket, now) >= limit


    def sort_key(ticket, now, step=STEP, limit=OVERDUE):
        return (
            0 if ticket.pinned else 1,
            0 if is_overdue(ticket, now, limit) else 1,
            effective_priority(ticket, now, step),
            ticket.created,
            str(ticket.id),
        )
''')

TRIAGEQ_QUEUE = dd('''
    """The ticket queue."""
    from . import aging


    class TicketQueue:
        def __init__(self, step=aging.STEP, limit=aging.OVERDUE):
            if step < 1 or limit < 1:
                raise ValueError("step and limit must be at least 1")
            self.step = step
            self.limit = limit
            self._tickets = {}

        def __len__(self):
            return len(self._tickets)

        def __contains__(self, ticket_id):
            return ticket_id in self._tickets

        def push(self, ticket):
            if ticket.id in self._tickets:
                raise ValueError(f"ticket {ticket.id!r} is already queued")
            self._tickets[ticket.id] = ticket

        def order(self, now):
            return sorted(self._tickets.values(), key=lambda t: aging.sort_key(t, now, self.step, self.limit))

        def peek(self, now):
            ordered = self.order(now)
            return ordered[0] if ordered else None

        def pop(self, now):
            best = self.peek(now)
            if best is not None:
                del self._tickets[best.id]
            return best

        def remove(self, ticket_id):
            return self._tickets.pop(ticket_id)

        def escalated(self, now):
            return sorted(t.id for t in self._tickets.values() if aging.effective_priority(t, now, self.step) < t.prio)

        def overdue_ids(self, now):
            return sorted(t.id for t in self._tickets.values() if aging.is_overdue(t, now, self.limit))

        def histogram(self, now):
            counts = {level: 0 for level in range(1, 6)}
            for t in self._tickets.values():
                counts[aging.effective_priority(t, now, self.step)] += 1
            return counts
''')

TRIAGEQ_VISIBLE = dd('''
    import unittest

    from triageq.aging import effective_priority
    from triageq.queue import TicketQueue
    from triageq.ticket import Ticket


    class BasicTests(unittest.TestCase):
        def test_aging(self):
            self.assertEqual(effective_priority(Ticket("a", 3, 0), 65), 1)

        def test_pop_order(self):
            q = TicketQueue()
            q.push(Ticket("low", 4, 0))
            q.push(Ticket("high", 1, 0))
            self.assertEqual(q.pop(0).id, "high")


    if __name__ == "__main__":
        unittest.main()
''')

TRIAGEQ_HIDDEN_AGING = dd('''
    import unittest

    from triageq.aging import OVERDUE, STEP, effective_priority, is_overdue, sort_key, waited
    from triageq.ticket import Ticket


    class TicketTests(unittest.TestCase):
        def test_defaults(self):
            t = Ticket("a", 3, 10)
            self.assertEqual((t.vip, t.pinned), (False, False))
            self.assertEqual((STEP, OVERDUE), (30, 240))

        def test_validation(self):
            for prio in (0, 6, -1, 2.5, "3"):
                with self.assertRaises(ValueError):
                    Ticket("a", prio, 0)
            with self.assertRaises(ValueError):
                Ticket("a", 3, -1)
            Ticket("a", 1, 0)
            Ticket("a", 5, 0)

        def test_frozen(self):
            with self.assertRaises(Exception):
                Ticket("a", 3, 0).prio = 1


    class Waited(unittest.TestCase):
        def test_waited(self):
            self.assertEqual(waited(Ticket("a", 3, 10), 10), 0)
            self.assertEqual(waited(Ticket("a", 3, 10), 55), 45)
            with self.assertRaises(ValueError):
                waited(Ticket("a", 3, 10), 9)


    class Effective(unittest.TestCase):
        def test_full_steps_only(self):
            t = Ticket("a", 5, 0)
            got = [effective_priority(t, n) for n in (0, 29, 30, 59, 60, 89, 90, 119, 120, 1000)]
            self.assertEqual(got, [5, 5, 4, 4, 3, 3, 2, 2, 1, 1])

        def test_created_offset(self):
            t = Ticket("a", 4, 100)
            self.assertEqual(effective_priority(t, 100), 4)
            self.assertEqual(effective_priority(t, 129), 4)
            self.assertEqual(effective_priority(t, 130), 3)

        def test_vip_is_one_level_better(self):
            v = Ticket("v", 4, 0, vip=True)
            self.assertEqual(effective_priority(v, 0), 3)
            self.assertEqual(effective_priority(v, 30), 2)
            self.assertEqual(effective_priority(v, 90), 1)
            self.assertEqual(effective_priority(v, 500), 1)
            self.assertEqual(effective_priority(Ticket("v", 1, 0, vip=True), 0), 1)
            self.assertEqual(effective_priority(Ticket("v", 2, 0, vip=True), 0), 1)

        def test_custom_step(self):
            t = Ticket("a", 5, 0)
            self.assertEqual(effective_priority(t, 9, step=10), 5)
            self.assertEqual(effective_priority(t, 10, step=10), 4)
            self.assertEqual(effective_priority(t, 25, step=10), 3)
            self.assertEqual(effective_priority(t, 25, step=100), 5)
            self.assertEqual(effective_priority(t, 100, step=100), 4)

        def test_time_travel(self):
            with self.assertRaises(ValueError):
                effective_priority(Ticket("a", 3, 50), 49)


    class Overdue(unittest.TestCase):
        def test_boundary(self):
            t = Ticket("a", 3, 0)
            self.assertFalse(is_overdue(t, 239))
            self.assertTrue(is_overdue(t, 240))
            self.assertTrue(is_overdue(t, 241))
            self.assertFalse(is_overdue(t, 99, limit=100))
            self.assertTrue(is_overdue(t, 100, limit=100))
            self.assertTrue(is_overdue(Ticket("b", 3, 60), 160, limit=100))

        def test_not_before_creation(self):
            with self.assertRaises(ValueError):
                is_overdue(Ticket("a", 3, 5), 4)


    class SortKey(unittest.TestCase):
        def test_key_shape(self):
            t = Ticket("t7", 4, 20)
            self.assertEqual(sort_key(t, 20), (1, 1, 4, 20, "t7"))
            self.assertEqual(sort_key(t, 80), (1, 1, 2, 20, "t7"))
            self.assertEqual(sort_key(t, 260), (1, 0, 1, 20, "t7"))
            self.assertEqual(sort_key(Ticket("p", 5, 0, pinned=True), 0), (0, 1, 5, 0, "p"))

        def test_custom_parameters(self):
            t = Ticket("t", 5, 0)
            self.assertEqual(sort_key(t, 50, step=10, limit=40), (1, 0, 1, 0, "t"))
            self.assertEqual(sort_key(t, 50, step=10, limit=60), (1, 1, 1, 0, "t"))

        def test_ids_compare_as_strings(self):
            self.assertLess(sort_key(Ticket("10", 3, 0), 0), sort_key(Ticket("9", 3, 0), 0))
            self.assertLess(sort_key(Ticket(10, 3, 0), 0), sort_key(Ticket(9, 3, 0), 0))


    if __name__ == "__main__":
        unittest.main()
''')

TRIAGEQ_HIDDEN_QUEUE = dd('''
    import unittest

    from triageq.queue import TicketQueue
    from triageq.ticket import Ticket


    def ids(tickets):
        return [t.id for t in tickets]


    class Basics(unittest.TestCase):
        def test_validation(self):
            for kw in ({"step": 0}, {"limit": 0}, {"step": -5}, {"limit": -1}):
                with self.assertRaises(ValueError):
                    TicketQueue(**kw)
            TicketQueue(step=1, limit=1)

        def test_push_len_contains(self):
            q = TicketQueue()
            self.assertEqual(len(q), 0)
            q.push(Ticket("a", 3, 0))
            self.assertEqual(len(q), 1)
            self.assertIn("a", q)
            self.assertNotIn("b", q)
            with self.assertRaises(ValueError):
                q.push(Ticket("a", 1, 5))
            self.assertEqual(len(q), 1)

        def test_empty_queue(self):
            q = TicketQueue()
            self.assertIsNone(q.peek(0))
            self.assertIsNone(q.pop(0))
            self.assertEqual(q.order(0), [])
            self.assertEqual(q.escalated(0), [])
            self.assertEqual(q.histogram(0), {1: 0, 2: 0, 3: 0, 4: 0, 5: 0})

        def test_remove(self):
            q = TicketQueue()
            t = Ticket("a", 3, 0)
            q.push(t)
            self.assertIs(q.remove("a"), t)
            self.assertEqual(len(q), 0)
            with self.assertRaises(KeyError):
                q.remove("a")


    class Ordering(unittest.TestCase):
        def test_by_priority_then_age_then_id(self):
            q = TicketQueue()
            for t in (Ticket("c", 3, 5), Ticket("b", 3, 5), Ticket("a", 3, 8), Ticket("z", 2, 9), Ticket("y", 4, 0)):
                q.push(t)
            self.assertEqual(ids(q.order(10)), ["z", "b", "c", "a", "y"])
            self.assertEqual(q.peek(10).id, "z")
            self.assertEqual(len(q), 5)

        def test_pop_removes_in_order(self):
            q = TicketQueue()
            for t in (Ticket("a", 2, 0), Ticket("b", 1, 0), Ticket("c", 3, 0)):
                q.push(t)
            self.assertEqual([q.pop(0).id for _ in range(3)], ["b", "a", "c"])
            self.assertIsNone(q.pop(0))

        def test_aging_overtakes(self):
            q = TicketQueue()
            q.push(Ticket("old", 4, 0))
            q.push(Ticket("new", 2, 85))
            self.assertEqual(ids(q.order(85)), ["old", "new"])  # old: 4 - 2 = 2, ties on priority, older first
            q2 = TicketQueue()
            q2.push(Ticket("old", 4, 0))
            q2.push(Ticket("new", 2, 50))
            self.assertEqual(ids(q2.order(50)), ["new", "old"])  # old: 4 - 1 = 3

        def test_vip_boost(self):
            q = TicketQueue()
            q.push(Ticket("plain", 2, 0))
            q.push(Ticket("vip", 3, 0, vip=True))
            self.assertEqual(ids(q.order(0)), ["plain", "vip"])  # equal level 2: older then id ("plain" < "vip")
            q = TicketQueue()
            q.push(Ticket("plain", 2, 0))
            q.push(Ticket("avip", 3, 5, vip=True))
            self.assertEqual(ids(q.order(5)), ["plain", "avip"])
            q = TicketQueue()
            q.push(Ticket("plain", 2, 3))
            q.push(Ticket("avip", 3, 0, vip=True))
            self.assertEqual(ids(q.order(5)), ["avip", "plain"])

        def test_pinned_beats_everything(self):
            q = TicketQueue()
            q.push(Ticket("urgent", 1, 0, vip=True))
            q.push(Ticket("late", 5, 0))
            q.push(Ticket("pin", 5, 100, pinned=True))
            self.assertEqual(q.order(300)[0].id, "pin")
            self.assertEqual(q.order(100)[0].id, "pin")

        def test_overdue_beats_priority(self):
            q = TicketQueue(step=1000)
            q.push(Ticket("urgent", 1, 200))
            q.push(Ticket("ancient", 5, 0))
            self.assertEqual(ids(q.order(239)), ["urgent", "ancient"])
            self.assertEqual(ids(q.order(240)), ["ancient", "urgent"])

        def test_custom_limit_and_step(self):
            q = TicketQueue(step=20, limit=50)
            q.push(Ticket("a", 5, 0))
            q.push(Ticket("b", 1, 45))
            self.assertEqual(ids(q.order(49)), ["b", "a"])
            self.assertEqual(ids(q.order(50)), ["a", "b"])
            self.assertEqual(q.overdue_ids(49), [])
            self.assertEqual(q.overdue_ids(50), ["a"])

        def test_pinned_then_overdue_among_pinned(self):
            q = TicketQueue(step=1000)
            q.push(Ticket("p2", 1, 100, pinned=True))
            q.push(Ticket("p1", 5, 0, pinned=True))
            q.push(Ticket("x", 1, 0))
            self.assertEqual(ids(q.order(300)), ["p1", "p2", "x"])
            self.assertEqual(ids(q.order(200)), ["p2", "p1", "x"])


    class Reports(unittest.TestCase):
        def make(self):
            q = TicketQueue()
            q.push(Ticket("a", 5, 0))
            q.push(Ticket("b", 3, 60))
            q.push(Ticket("c", 1, 0))
            q.push(Ticket("d", 4, 40, vip=True))
            return q

        def test_escalated(self):
            q = self.make()
            self.assertEqual(q.escalated(60), ["a", "d"])  # a: 5-2=3; b: 3-0; c: stays 1; d: 4-0-1=3
            self.assertEqual(q.escalated(100), ["a", "b", "d"])
            self.assertEqual(q.escalated(150), ["a", "b", "d"])
            self.assertEqual(q.escalated(60 + 29)[0], "a")

        def test_overdue_ids(self):
            q = self.make()
            self.assertEqual(q.overdue_ids(239), [])
            self.assertEqual(q.overdue_ids(240), ["a", "c"])
            self.assertEqual(q.overdue_ids(279), ["a", "c"])
            self.assertEqual(q.overdue_ids(280), ["a", "c", "d"])
            self.assertEqual(q.overdue_ids(299), ["a", "c", "d"])
            self.assertEqual(q.overdue_ids(300), ["a", "b", "c", "d"])

        def test_histogram(self):
            q = self.make()
            self.assertEqual(q.histogram(70), {1: 1, 2: 1, 3: 2, 4: 0, 5: 0})
            self.assertEqual(q.histogram(100), {1: 2, 2: 2, 3: 0, 4: 0, 5: 0})
            self.assertEqual(q.histogram(150), {1: 4, 2: 0, 3: 0, 4: 0, 5: 0})

        def test_time_errors(self):
            q = self.make()
            with self.assertRaises(ValueError):
                q.order(50)
            with self.assertRaises(ValueError):
                q.histogram(50)


    if __name__ == "__main__":
        unittest.main()
''')

TRIAGEQ = Lib(
    name="triageq", lang="python", title="the triageq ticket queue",
    blurb="The support desk's dashboard uses triageq to decide which customer ticket an agent should take next.",
    files={
        "triageq/__init__.py": "", "triageq/ticket.py": TRIAGEQ_TICKET, "triageq/aging.py": TRIAGEQ_AGING,
        "triageq/queue.py": TRIAGEQ_QUEUE, "README.md": TRIAGEQ_README, ".gitignore": GITIGNORE,
    },
    visible_tests={"tests/test_basic.py": TRIAGEQ_VISIBLE},
    hidden_tests={"tests/test_aging.py": TRIAGEQ_HIDDEN_AGING, "tests/test_queue.py": TRIAGEQ_HIDDEN_QUEUE},
    mutate=["triageq/ticket.py", "triageq/aging.py", "triageq/queue.py"],
    difficulty=2, tags=["queue", "priority", "multi-module"],
    probes=[
        "[effective_priority(Ticket('a', 5, 0), n) for n in (0, 29, 30, 60, 120, 500)]",
        "effective_priority(Ticket('v', 4, 0, vip=True), 30)",
        "is_overdue(Ticket('a', 3, 0), 240)",
        "sort_key(Ticket('t7', 4, 20), 260)",
        chain("TicketQueue()", ["push(Ticket('a', 2, 0))", "push(Ticket('b', 1, 0))", "push(Ticket('c', 3, 0))", "pop(0).id", "pop(0).id", "pop(0).id"]),
        chain("TicketQueue()", ["push(Ticket('old', 4, 0))", "push(Ticket('new', 2, 50))", "![t.id for t in o.order(50)]"]),
        chain("TicketQueue(step=1000)", ["push(Ticket('urgent', 1, 200))", "push(Ticket('ancient', 5, 0))", "![t.id for t in o.order(240)]"]),
        chain("TicketQueue()", ["push(Ticket('a', 5, 0))", "push(Ticket('b', 3, 60))", "push(Ticket('c', 1, 0))", "escalated(100)", "overdue_ids(240)", "histogram(100)"]),
    ],
    probe_import=(
        "from triageq.aging import effective_priority, is_overdue, sort_key\n"
        "from triageq.queue import TicketQueue\nfrom triageq.ticket import Ticket\n"
    ),
)

# ======================================================================================================================
# tollroute: courier routing over a road map with tolls and vehicle classes (multi-module)
# ======================================================================================================================

TOLLROUTE_README = dd('''
    # tollroute

    A courier firm plans van, truck and bike routes between its depots. Roads cost minutes and may charge a toll
    (integer cents).

    ## `tollroute.graph`

    `Road(a, b, minutes, toll, kind, oneway)` is a frozen dataclass. `RoadMap` stores roads:

    * `add_road(a, b, minutes, toll=0, kind="street", oneway=False)`: `kind` is `"street"`, `"highway"` or
      `"narrow"`. `ValueError` for `minutes < 1`, `toll < 0`, an unknown kind or `a == b`. A road is usable from `a`
      to `b` and, unless `oneway`, from `b` to `a`. Several roads between the same two depots are allowed.
    * `nodes() -> list[str]`: every depot that appears in a road, sorted.
    * `roads_from(node) -> list[(neighbour, Road)]`: the roads that can be driven out of `node`, in the order they
      were added (`KeyError` for an unknown depot).

    `parse_map(text) -> RoadMap` reads one road per line: `A-B minutes [toll [kind]]` for a two-way road or
    `A>B minutes [toll [kind]]` for a one-way road from A to B. Depot names are non-empty and contain no spaces or
    `-`/`>`. Everything after `#` is a comment and blank lines are skipped. A malformed line is a `ValueError`
    starting with `line N:` (N counts physical lines from 1): not 2 to 4 fields, a bad road spec, non-numeric
    minutes or toll, plus everything `add_road` rejects.

    ## `tollroute.tolls`

    * `is_peak(minute) -> bool`: `minute % 1440` falls in `[420, 540)` or `[960, 1140)`.
    * `allowed(road, vehicle) -> bool`: a `"van"` may use every road, a `"bike"` may not use `"highway"` roads, a
      `"truck"` may not use `"narrow"` roads. An unknown vehicle is a `ValueError`.
    * `toll_for(road, vehicle, depart) -> int`: the road's toll multiplied by `0` for a bike, `1` for a van, `2` for
      a truck; if `is_peak(depart)` the result is then multiplied by 1.5 and rounded half up (integer arithmetic).
      Unknown vehicle: `ValueError`.

    ## `tollroute.router`

    `Route(path, minutes, toll, cost)` is a frozen dataclass: `path` is a tuple of depot names.

    * `best_route(roadmap, src, dst, vehicle, depart=0, per_minute=0) -> Route | None`: the cheapest route for the
      vehicle, where a road costs `minutes * per_minute + toll_for(road, vehicle, depart)`. Only roads the vehicle is
      `allowed` on are used, and the peak surcharge is decided once, by the trip's `depart` minute. Among routes of
      equal cost the one with fewer total minutes wins; among those, the lexicographically smaller `path` tuple. A
      trip from a depot to itself is `Route((src,), 0, 0, 0)`. `None` if `dst` cannot be reached. `ValueError` if
      `src` or `dst` is not a depot of the map.
    * `quote(roadmap, path, vehicle, depart=0, per_minute=0) -> Route`: the price of driving the given depot
      sequence. Between each pair of consecutive depots the cheapest *usable* road is taken (cost as above, ties by
      fewer minutes). `ValueError` if there is no usable road for some leg or the path is empty.
    * `isochrone(roadmap, src, vehicle, limit) -> list[(depot, minutes)]`: every other depot the vehicle can reach
      in at most `limit` minutes (tolls are ignored; the quickest way counts), sorted by minutes and then name.
''')

TOLLROUTE_GRAPH = dd('''
    """The road map and its text format."""
    from dataclasses import dataclass

    KINDS = ("street", "highway", "narrow")


    @dataclass(frozen=True)
    class Road:
        a: str
        b: str
        minutes: int
        toll: int
        kind: str = "street"
        oneway: bool = False


    class RoadMap:
        def __init__(self):
            self._out = {}

        def add_road(self, a, b, minutes, toll=0, kind="street", oneway=False):
            if minutes < 1 or toll < 0:
                raise ValueError("minutes must be at least 1 and toll must not be negative")
            if kind not in KINDS:
                raise ValueError(f"unknown road kind {kind!r}")
            if a == b:
                raise ValueError("a road needs two different depots")
            road = Road(a, b, minutes, toll, kind, oneway)
            self._out.setdefault(a, []).append((b, road))
            self._out.setdefault(b, [])
            if not oneway:
                self._out[b].append((a, road))

        def nodes(self):
            return sorted(self._out)

        def roads_from(self, node):
            return list(self._out[node])


    def parse_map(text):
        roadmap = RoadMap()
        for lineno, raw in enumerate(text.splitlines(), 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            fields = line.split()
            if not 2 <= len(fields) <= 4:
                raise ValueError(f"line {lineno}: expected 2 to 4 fields")
            spec = fields[0]
            oneway = ">" in spec
            sep = ">" if oneway else "-"
            ends = spec.split(sep)
            if len(ends) != 2 or not ends[0] or not ends[1] or "-" in spec.replace(sep, "", 1) or ">" in spec.replace(sep, "", 1):
                raise ValueError(f"line {lineno}: bad road spec {spec!r}")
            if not fields[1].isdigit() or (len(fields) > 2 and not fields[2].isdigit()):
                raise ValueError(f"line {lineno}: minutes and toll must be whole numbers")
            toll = int(fields[2]) if len(fields) > 2 else 0
            kind = fields[3] if len(fields) > 3 else "street"
            try:
                roadmap.add_road(ends[0], ends[1], int(fields[1]), toll, kind, oneway)
            except ValueError as exc:
                raise ValueError(f"line {lineno}: {exc}") from None
        return roadmap
''')

TOLLROUTE_TOLLS = dd('''
    """Who may use which road and what it costs."""

    PEAKS = ((420, 540), (960, 1140))
    FACTOR = {"bike": 0, "van": 1, "truck": 2}


    def is_peak(minute):
        m = minute % 1440
        return any(lo <= m < hi for lo, hi in PEAKS)


    def _check(vehicle):
        if vehicle not in FACTOR:
            raise ValueError(f"unknown vehicle {vehicle!r}")


    def allowed(road, vehicle):
        _check(vehicle)
        if vehicle == "bike":
            return road.kind != "highway"
        if vehicle == "truck":
            return road.kind != "narrow"
        return True


    def toll_for(road, vehicle, depart):
        _check(vehicle)
        toll = road.toll * FACTOR[vehicle]
        if is_peak(depart):
            toll = (toll * 3 + 1) // 2
        return toll
''')

TOLLROUTE_ROUTER = dd('''
    """Cheapest routes."""
    import heapq
    from dataclasses import dataclass

    from .tolls import allowed, toll_for


    @dataclass(frozen=True)
    class Route:
        path: tuple
        minutes: int
        toll: int
        cost: int


    def best_route(roadmap, src, dst, vehicle, depart=0, per_minute=0):
        known = set(roadmap.nodes())
        if src not in known or dst not in known:
            raise ValueError("unknown depot")
        if src == dst:
            return Route((src,), 0, 0, 0)
        heap = [(0, 0, (src,), 0)]
        done = set()
        while heap:
            cost, minutes, path, toll = heapq.heappop(heap)
            node = path[-1]
            if node in done:
                continue
            done.add(node)
            if node == dst:
                return Route(path, minutes, toll, cost)
            for nxt, road in roadmap.roads_from(node):
                if nxt in done or not allowed(road, vehicle):
                    continue
                t = toll_for(road, vehicle, depart)
                step = road.minutes * per_minute + t
                heapq.heappush(heap, (cost + step, minutes + road.minutes, path + (nxt,), toll + t))
        return None


    def quote(roadmap, path, vehicle, depart=0, per_minute=0):
        if not path:
            raise ValueError("empty path")
        minutes = toll = 0
        for a, b in zip(path, path[1:]):
            options = [r for n, r in roadmap.roads_from(a) if n == b and allowed(r, vehicle)]
            if not options:
                raise ValueError(f"no usable road from {a} to {b}")
            best = min(options, key=lambda r: (r.minutes * per_minute + toll_for(r, vehicle, depart), r.minutes))
            minutes += best.minutes
            toll += toll_for(best, vehicle, depart)
        return Route(tuple(path), minutes, toll, minutes * per_minute + toll)


    def isochrone(roadmap, src, vehicle, limit):
        best = {src: 0}
        heap = [(0, src)]
        while heap:
            m, node = heapq.heappop(heap)
            if m > best.get(node, m):
                continue
            for nxt, road in roadmap.roads_from(node):
                if not allowed(road, vehicle):
                    continue
                nm = m + road.minutes
                if nm <= limit and nm < best.get(nxt, limit + 1):
                    best[nxt] = nm
                    heapq.heappush(heap, (nm, nxt))
        return sorted(((n, m) for n, m in best.items() if n != src), key=lambda x: (x[1], x[0]))
''')

TOLLROUTE_VISIBLE = dd('''
    import unittest

    from tollroute.graph import parse_map
    from tollroute.router import best_route


    MAP = """
    A-B 10 100
    B-C 10 100
    A-C 25 0
    """


    class BasicTests(unittest.TestCase):
        def test_cheapest_by_toll(self):
            r = best_route(parse_map(MAP), "A", "C", "van")
            self.assertEqual(r.path, ("A", "C"))

        def test_same_depot(self):
            self.assertEqual(best_route(parse_map(MAP), "B", "B", "van").path, ("B",))


    if __name__ == "__main__":
        unittest.main()
''')

TOLLROUTE_HIDDEN_GRAPH = dd('''
    import unittest

    from tollroute.graph import Road, RoadMap, parse_map
    from tollroute.tolls import allowed, is_peak, toll_for


    class RoadMapTests(unittest.TestCase):
        def test_two_way_and_one_way(self):
            m = RoadMap()
            m.add_road("A", "B", 5, 10)
            m.add_road("B", "C", 7, 0, "highway", oneway=True)
            self.assertEqual(m.nodes(), ["A", "B", "C"])
            self.assertEqual([n for n, _ in m.roads_from("A")], ["B"])
            self.assertEqual([n for n, _ in m.roads_from("B")], ["A", "C"])
            self.assertEqual(m.roads_from("C"), [])
            self.assertEqual(m.roads_from("A")[0][1], Road("A", "B", 5, 10, "street", False))
            self.assertEqual(Road("A", "B", 5, 10), Road("A", "B", 5, 10, "street", False))
            with self.assertRaises(Exception):
                m.roads_from("A")[0][1].minutes = 9

        def test_insertion_order_and_parallel_roads(self):
            m = RoadMap()
            m.add_road("A", "C", 9)
            m.add_road("A", "B", 4)
            m.add_road("A", "B", 6, 50)
            self.assertEqual([(n, r.minutes) for n, r in m.roads_from("A")], [("C", 9), ("B", 4), ("B", 6)])
            self.assertEqual([r.toll for n, r in m.roads_from("A")], [0, 0, 50])
            self.assertEqual([r.kind for n, r in m.roads_from("A")], ["street"] * 3)
            self.assertEqual([(n, r.minutes) for n, r in m.roads_from("B")], [("A", 4), ("A", 6)])

        def test_validation(self):
            m = RoadMap()
            for args in (("A", "B", 0), ("A", "B", -3), ("A", "B", 1, -1), ("A", "A", 5)):
                with self.assertRaises(ValueError):
                    m.add_road(*args)
            with self.assertRaises(ValueError):
                m.add_road("A", "B", 3, 0, "tunnel")
            self.assertEqual(m.nodes(), [])
            m.add_road("A", "B", 1, 0)

        def test_unknown_node(self):
            with self.assertRaises(KeyError):
                RoadMap().roads_from("A")


    class ParseTests(unittest.TestCase):
        def test_all_forms(self):
            m = parse_map("A-B 10\\nB-C 7 120\\nC>D 3 0 narrow\\nD-E 4 55 highway\\n")
            roads = {(r.a, r.b): r for _, r in sum((m.roads_from(n) for n in m.nodes()), [])}
            self.assertEqual(roads[("A", "B")], Road("A", "B", 10, 0, "street", False))
            self.assertEqual(roads[("B", "C")], Road("B", "C", 7, 120, "street", False))
            self.assertEqual(roads[("C", "D")], Road("C", "D", 3, 0, "narrow", True))
            self.assertEqual(roads[("D", "E")], Road("D", "E", 4, 55, "highway", False))
            self.assertEqual([n for n, _ in m.roads_from("D")], ["E"])
            self.assertEqual([n for n, _ in m.roads_from("C")], ["B", "D"])

        def test_comments_blanks_and_spaces(self):
            m = parse_map("# depots\\n\\n  A-B   4   # short hop\\n\\t B>C 5 7\\n")
            self.assertEqual(m.nodes(), ["A", "B", "C"])
            self.assertEqual(m.roads_from("C"), [])

        def test_depot_names(self):
            m = parse_map("North_Gate-Dock4 12")
            self.assertEqual(m.nodes(), ["Dock4", "North_Gate"])

        def test_errors_have_line_numbers(self):
            bad = [
                "A-B", "A-B 1 2 street extra", "A 5", "A--B 5", "-B 5", "A- 5", "A-B-C 5", "A>B>C 5", "A-B x", "A-B 5 y",
                "A-B 0", "A-B 5 5 tunnel", "A-A 5", "A>B- 5", "A-B 1.5", "A-B -2",
            ]
            for text in bad:
                with self.assertRaises(ValueError, msg=text) as cm:
                    parse_map("# first\\n" + text)
                self.assertTrue(str(cm.exception).startswith("line 2:"), (text, str(cm.exception)))

        def test_empty(self):
            self.assertEqual(parse_map("").nodes(), [])
            self.assertEqual(parse_map("# nothing\\n\\n").nodes(), [])


    class TollTests(unittest.TestCase):
        def test_peak_windows(self):
            self.assertFalse(is_peak(419))
            self.assertTrue(is_peak(420))
            self.assertTrue(is_peak(539))
            self.assertFalse(is_peak(540))
            self.assertFalse(is_peak(959))
            self.assertTrue(is_peak(960))
            self.assertTrue(is_peak(1139))
            self.assertFalse(is_peak(1140))
            self.assertFalse(is_peak(0))
            self.assertTrue(is_peak(1440 + 430))
            self.assertTrue(is_peak(3 * 1440 + 1000))
            self.assertFalse(is_peak(1439))
            self.assertTrue(is_peak(1440 + 539))
            self.assertFalse(is_peak(1440 + 540))
            self.assertFalse(is_peak(1440 + 419))
            self.assertTrue(is_peak(1440 + 420))
            self.assertTrue(is_peak(2 * 1440 + 960))
            self.assertFalse(is_peak(2 * 1440 + 1140))

        def test_allowed(self):
            street, hw, nar = (Road("A", "B", 1, 0, k) for k in ("street", "highway", "narrow"))
            self.assertEqual([allowed(r, "van") for r in (street, hw, nar)], [True, True, True])
            self.assertEqual([allowed(r, "bike") for r in (street, hw, nar)], [True, False, True])
            self.assertEqual([allowed(r, "truck") for r in (street, hw, nar)], [True, True, False])
            with self.assertRaises(ValueError):
                allowed(street, "tank")

        def test_toll_factors(self):
            r = Road("A", "B", 1, 100)
            self.assertEqual(toll_for(r, "bike", 0), 0)
            self.assertEqual(toll_for(r, "van", 0), 100)
            self.assertEqual(toll_for(r, "truck", 0), 200)
            with self.assertRaises(ValueError):
                toll_for(r, "tank", 0)

        def test_peak_surcharge_rounds_half_up(self):
            for toll, expect in ((0, 0), (1, 2), (2, 3), (3, 5), (4, 6), (100, 150), (101, 152)):
                self.assertEqual(toll_for(Road("A", "B", 1, toll), "van", 480), expect, toll)
            self.assertEqual(toll_for(Road("A", "B", 1, 3), "truck", 480), 9)  # 6 * 1.5
            self.assertEqual(toll_for(Road("A", "B", 1, 3), "truck", 500 + 1440), 9)
            self.assertEqual(toll_for(Road("A", "B", 1, 3), "van", 600), 3)
            self.assertEqual(toll_for(Road("A", "B", 1, 3), "bike", 480), 0)


    if __name__ == "__main__":
        unittest.main()
''')

TOLLROUTE_HIDDEN_ROUTER = dd('''
    import unittest

    from tollroute.graph import parse_map
    from tollroute.router import Route, best_route, isochrone, quote

    MAP = parse_map("""
    A-B 10 100
    B-D 10 100
    A-C 5 300 highway
    C-D 5 0 highway
    D-E 4 0 narrow
    A>E 30 250
    F>A 2 0
    """)


    class BestRoute(unittest.TestCase):
        def test_toll_only(self):
            r = best_route(MAP, "A", "D", "van")
            self.assertEqual(r, Route(("A", "B", "D"), 20, 200, 200))

        def test_time_matters(self):
            r = best_route(MAP, "A", "D", "van", per_minute=20)
            self.assertEqual(r, Route(("A", "C", "D"), 10, 300, 500))

        def test_peak_surcharge(self):
            r = best_route(MAP, "A", "D", "van", depart=480)
            self.assertEqual(r, Route(("A", "B", "D"), 20, 300, 300))
            r = best_route(MAP, "A", "D", "van", depart=480, per_minute=20)
            self.assertEqual(r, Route(("A", "C", "D"), 10, 450, 650))
            r = best_route(MAP, "A", "D", "van", depart=480 + 1440, per_minute=20)
            self.assertEqual(r.path, ("A", "C", "D"))
            r = best_route(MAP, "A", "D", "van", depart=540, per_minute=20)
            self.assertEqual(r.cost, 500)

        def test_bike_avoids_highways_and_pays_nothing(self):
            r = best_route(MAP, "A", "D", "bike", per_minute=3)
            self.assertEqual(r, Route(("A", "B", "D"), 20, 0, 60))
            self.assertEqual(best_route(MAP, "A", "D", "bike").cost, 0)

        def test_truck_avoids_narrow_roads_and_pays_double(self):
            r = best_route(MAP, "A", "E", "truck")
            self.assertEqual(r, Route(("A", "E"), 30, 500, 500))
            r = best_route(MAP, "A", "D", "truck")
            self.assertEqual(r, Route(("A", "B", "D"), 20, 400, 400))
            r = best_route(MAP, "A", "D", "truck", depart=1000)
            self.assertEqual(r, Route(("A", "B", "D"), 20, 600, 600))

        def test_van_may_use_narrow_roads(self):
            self.assertEqual(best_route(MAP, "A", "E", "van"), Route(("A", "B", "D", "E"), 24, 200, 200))
            # equal cost at 10 per minute (440 both ways): the quicker route wins
            self.assertEqual(best_route(MAP, "A", "E", "van", per_minute=10), Route(("A", "C", "D", "E"), 14, 300, 440))
            self.assertEqual(best_route(MAP, "A", "E", "van", per_minute=30), Route(("A", "C", "D", "E"), 14, 300, 720))
            self.assertEqual(best_route(MAP, "A", "E", "van", depart=480), Route(("A", "B", "D", "E"), 24, 300, 300))

        def test_one_way_road_can_win(self):
            m = parse_map("A>E 30 10\\nA-B 10 100\\nB-E 10 100")
            self.assertEqual(best_route(m, "A", "E", "van"), Route(("A", "E"), 30, 10, 10))
            self.assertEqual(best_route(m, "E", "A", "van"), Route(("E", "B", "A"), 20, 200, 200))

        def test_one_way(self):
            self.assertEqual(best_route(MAP, "E", "A", "van").path, ("E", "D", "B", "A"))
            self.assertIsNone(best_route(MAP, "A", "F", "van"))
            self.assertEqual(best_route(MAP, "F", "E", "van").path, ("F", "A", "B", "D", "E"))

        def test_unreachable_for_vehicle(self):
            m = parse_map("A-B 5 0 highway\\nB-C 5 0")
            self.assertIsNone(best_route(m, "A", "C", "bike"))
            self.assertIsNotNone(best_route(m, "A", "C", "van"))
            m = parse_map("A-B 5 0 narrow")
            self.assertIsNone(best_route(m, "A", "B", "truck"))

        def test_route_is_frozen(self):
            r = best_route(MAP, "A", "D", "van")
            with self.assertRaises(Exception):
                r.cost = 1

        def test_same_depot_and_unknown(self):
            self.assertEqual(best_route(MAP, "B", "B", "van"), Route(("B",), 0, 0, 0))
            self.assertEqual(best_route(MAP, "E", "E", "truck"), Route(("E",), 0, 0, 0))
            with self.assertRaises(ValueError):
                best_route(MAP, "A", "Z", "van")
            with self.assertRaises(ValueError):
                best_route(MAP, "Z", "A", "van")
            with self.assertRaises(ValueError):
                best_route(MAP, "Z", "Z", "van")

        def test_ties_fewer_minutes_then_lexicographic(self):
            m = parse_map("P-Q 5\\nP-R 5\\nQ-S 5\\nR-S 5")
            self.assertEqual(best_route(m, "P", "S", "van").path, ("P", "Q", "S"))
            m = parse_map("P-R 5\\nP-Q 5\\nR-S 5\\nQ-S 5")
            self.assertEqual(best_route(m, "P", "S", "van").path, ("P", "Q", "S"))
            m = parse_map("P-S 20\\nP-Q 5\\nQ-S 5")
            self.assertEqual(best_route(m, "P", "S", "van"), Route(("P", "Q", "S"), 10, 0, 0))

        def test_fewer_minutes_beats_path_order(self):
            m = parse_map("P-A 9 100\\nA-S 9\\nP-Z 3 100\\nZ-S 3")
            r = best_route(m, "P", "S", "van")
            self.assertEqual(r, Route(("P", "Z", "S"), 6, 100, 100))

        def test_parallel_roads(self):
            m = parse_map("A-B 10 100\\nA-B 30 0\\nA-B 20 50")
            self.assertEqual(best_route(m, "A", "B", "van"), Route(("A", "B"), 30, 0, 0))
            self.assertEqual(best_route(m, "A", "B", "van", per_minute=5), Route(("A", "B"), 10, 100, 150))
            self.assertEqual(best_route(m, "A", "B", "van", per_minute=2), Route(("A", "B"), 30, 0, 60))

        def test_longer_cheaper_detour(self):
            m = parse_map("A-B 1 1000\\nA-C 8 0\\nC-D 8 0\\nD-B 8 0")
            self.assertEqual(best_route(m, "A", "B", "van"), Route(("A", "C", "D", "B"), 24, 0, 0))
            self.assertEqual(best_route(m, "A", "B", "van", per_minute=100).path, ("A", "B"))


    class Quote(unittest.TestCase):
        def test_quote_matches_best_route(self):
            r = best_route(MAP, "A", "D", "van", depart=480, per_minute=20)
            self.assertEqual(quote(MAP, r.path, "van", 480, 20), r)

        def test_quote_explicit_path(self):
            self.assertEqual(quote(MAP, ["A", "B", "D", "E"], "van"), Route(("A", "B", "D", "E"), 24, 200, 200))
            self.assertEqual(quote(MAP, ("A", "B", "D", "E"), "van", 0, 10), Route(("A", "B", "D", "E"), 24, 200, 440))
            self.assertEqual(quote(MAP, ["A"], "van"), Route(("A",), 0, 0, 0))

        def test_quote_picks_cheapest_parallel_road(self):
            m = parse_map("A-B 10 100\\nA-B 30 0\\nA-B 20 50")
            self.assertEqual(quote(m, ["A", "B"], "van").minutes, 30)
            self.assertEqual(quote(m, ["A", "B"], "van", per_minute=5), Route(("A", "B"), 10, 100, 150))
            self.assertEqual(quote(m, ["A", "B"], "van", per_minute=2), Route(("A", "B"), 30, 0, 60))
            m = parse_map("A-B 10 20\\nA-B 5 20")
            self.assertEqual(quote(m, ["A", "B"], "van").minutes, 5)
            m = parse_map("A-B 5 20\\nA-B 10 20")
            self.assertEqual(quote(m, ["A", "B"], "van").minutes, 5)

        def test_quote_errors(self):
            with self.assertRaises(ValueError):
                quote(MAP, [], "van")
            with self.assertRaises(ValueError):
                quote(MAP, ["A", "D"], "van")
            with self.assertRaises(ValueError):
                quote(MAP, ["A", "C"], "bike")
            with self.assertRaises(ValueError):
                quote(MAP, ["A", "F"], "van")


    class Isochrone(unittest.TestCase):
        def test_van(self):
            self.assertEqual(isochrone(MAP, "A", "van", 15), [("C", 5), ("B", 10), ("D", 10), ("E", 14)])
            self.assertEqual(isochrone(MAP, "A", "van", 14), [("C", 5), ("B", 10), ("D", 10), ("E", 14)])
            self.assertEqual(isochrone(MAP, "A", "van", 13), [("C", 5), ("B", 10), ("D", 10)])
            self.assertEqual(isochrone(MAP, "A", "van", 9), [("C", 5)])
            self.assertEqual(isochrone(MAP, "A", "van", 4), [])
            self.assertEqual(isochrone(MAP, "A", "van", 30), [("C", 5), ("B", 10), ("D", 10), ("E", 14)])

        def test_limit_is_inclusive(self):
            self.assertEqual(isochrone(MAP, "A", "van", 10), [("C", 5), ("B", 10), ("D", 10)])
            self.assertEqual(isochrone(MAP, "A", "van", 5), [("C", 5)])

        def test_bike_and_truck(self):
            self.assertEqual(isochrone(MAP, "A", "bike", 30), [("B", 10), ("D", 20), ("E", 24)])
            self.assertEqual(isochrone(MAP, "A", "truck", 40), [("C", 5), ("B", 10), ("D", 10), ("E", 30)])

        def test_ties_sorted_by_name_and_source_excluded(self):
            m = parse_map("S-Z 3\\nS-M 3\\nS-A 3\\nA-Q 1")
            self.assertEqual(isochrone(m, "S", "van", 4), [("A", 3), ("M", 3), ("Z", 3), ("Q", 4)])
            self.assertEqual(isochrone(m, "S", "van", 2), [])

        def test_quickest_way_counts(self):
            m = parse_map("S-A 10\\nS-B 2\\nB-A 3")
            self.assertEqual(isochrone(m, "S", "van", 10), [("B", 2), ("A", 5)])

        def test_zero_limit(self):
            self.assertEqual(isochrone(MAP, "A", "van", 0), [])


    if __name__ == "__main__":
        unittest.main()
''')

_TM = "'A-B 10 100\\nB-D 10 100\\nA-C 5 300 highway\\nC-D 5 0 highway\\nD-E 4 0 narrow\\nA>E 30 250'"

TOLLROUTE = Lib(
    name="tollroute", lang="python", title="the tollroute route planner",
    blurb="The courier firm's planner uses tollroute to price van, truck and bike routes between its depots.",
    files={
        "tollroute/__init__.py": "", "tollroute/graph.py": TOLLROUTE_GRAPH, "tollroute/tolls.py": TOLLROUTE_TOLLS,
        "tollroute/router.py": TOLLROUTE_ROUTER, "README.md": TOLLROUTE_README, ".gitignore": GITIGNORE,
    },
    visible_tests={"tests/test_basic.py": TOLLROUTE_VISIBLE},
    hidden_tests={"tests/test_graph.py": TOLLROUTE_HIDDEN_GRAPH, "tests/test_router.py": TOLLROUTE_HIDDEN_ROUTER},
    mutate=["tollroute/graph.py", "tollroute/tolls.py", "tollroute/router.py"],
    difficulty=4, tags=["routing", "tolls", "multi-module"],
    probes=[
        f"best_route(parse_map({_TM}), 'A', 'D', 'van', per_minute=20)",
        f"best_route(parse_map({_TM}), 'A', 'D', 'van', depart=480)",
        f"best_route(parse_map({_TM}), 'A', 'D', 'bike', per_minute=3)",
        f"best_route(parse_map({_TM}), 'A', 'D', 'truck', depart=1000)",
        f"best_route(parse_map({_TM}), 'A', 'E', 'van', per_minute=30)",
        f"best_route(parse_map({_TM}), 'A', 'E', 'truck')",
        f"quote(parse_map({_TM}), ['A', 'B', 'D', 'E'], 'van', 0, 10)",
        f"isochrone(parse_map({_TM}), 'A', 'van', 14)",
        "best_route(parse_map('P-Q 5\\nP-R 5\\nQ-S 5\\nR-S 5'), 'P', 'S', 'van').path",
        "parse_map('A-B 5 7\\nB>C 4').nodes()",
        "toll_for(Road('A', 'B', 1, 3), 'van', 480)", "is_peak(540)", "is_peak(420)",
    ],
    probe_import=(
        "from tollroute.graph import Road, parse_map\nfrom tollroute.tolls import is_peak, toll_for\n"
        "from tollroute.router import best_route, quote, isochrone\n"
    ),
)

LIBS = [LIFTSIM, TRIAGEQ, TOLLROUTE]
register_libs3(LIBS, n=10)
