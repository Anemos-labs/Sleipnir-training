"""Port library: a single-lift dispatch simulation with collective control (many tie-breaking rules), Python <-> Go."""
from fx import dd

from ._portlib import PortLib, register_port
from ._types import Fn

LF_SPEC = dd('''
    A single lift with **collective control** serves a building with floors `0 .. floors-1` (`2 <= floors <= 100`). Time is counted in ticks from 0. The lift starts at floor 0 and idle (direction 0; direction 1 is up, -1 is down).
    A **request** is a triple `(t, from, to)`: a passenger appears at floor `from` at tick `t` and wants to go to floor `to` (`0 <= t <= 100000`, `0 <= from, to < floors`, `from != to`). `requests` is a flat list
    `[t0, from0, to0, t1, from1, to1, ...]`; requests are numbered by their position in it (0, 1, ...). A `floors` value out of range, a list whose length is not a multiple of 3 or any invalid request is an error.

    Moving one floor takes one tick; boarding and unloading take no time. In **every tick**, with the lift at floor `f`, these steps happen in this order:

    1. **Admit.** Requests with `t` equal to the current tick start waiting at their `from` floor.
    2. **Unload.** Every rider whose `to` is `f` leaves; their *drop time* is the current tick. If that was the last passenger of the whole list, the simulation ends here (the lift does not move in this tick).
    3. **Turn around.** If the direction is not 0 and nothing lies *ahead* (no rider's destination and no waiting passenger's `from` strictly beyond `f` in the direction of travel), the direction becomes 0.
    4. **Board.** Let `sd` be the direction; if it is 0, `sd` is the travel direction (the sign of `to - from`) of the lowest-numbered request waiting at `f`. Every request waiting at `f` whose travel direction equals `sd` boards; its *pickup time* is the current tick.
       If the direction was 0 and somebody boarded, the direction becomes `sd`. Passengers at `f` who want the other way keep waiting.
    5. **Decide.** If the direction is still 0, look at the floors of all riders' destinations and all waiting passengers' `from` floors: if there are some above `f` and some below `f`, go toward the nearest of them (distance in floors; a tie goes up);
       if only above, go up; if only below, go down; if there are none the direction stays 0. A lift that already has a direction keeps it.
    6. **Move.** The lift moves one floor in the new direction (not at all when it is 0) and the tick counter goes up by one.

    The result of a function is read off this simulation (an empty request list gives zeros and empty lists):

    * `schedule` lists, for every request in order, its pickup time and its drop time: `[pickup0, drop0, pickup1, drop1, ...]`.
    * `finish_time` is the tick in which the last passenger was dropped; `travel_floors` is the total number of floors the lift moved; `max_wait` is the largest `pickup - t` over all requests.
    * `stops` lists the floor of every tick in which at least one passenger was unloaded or boarded, in time order (the same floor can repeat in consecutive ticks).
''')

LF_FNS = [
    Fn("schedule", [("floors", "int"), ("requests", "list<int>")], "list<int>", err=True),
    Fn("finish_time", [("floors", "int"), ("requests", "list<int>")], "int", err=True),
    Fn("travel_floors", [("floors", "int"), ("requests", "list<int>")], "int", err=True),
    Fn("max_wait", [("floors", "int"), ("requests", "list<int>")], "int", err=True),
    Fn("stops", [("floors", "int"), ("requests", "list<int>")], "list<int>", err=True),
]

LF_PY = dd(r'''
def _sign(x):
    return (x > 0) - (x < 0)


def _simulate(floors, requests):
    if not (2 <= floors <= 100) or len(requests) % 3 != 0:
        raise ValueError("bad input")
    reqs = []
    for k in range(0, len(requests), 3):
        t, a, b = requests[k:k + 3]
        if not (0 <= t <= 100000 and 0 <= a < floors and 0 <= b < floors and a != b):
            raise ValueError("bad request")
        reqs.append((t, a, b))
    n = len(reqs)
    status = [0] * n  # 0 future, 1 waiting, 2 riding, 3 done
    pickup = [0] * n
    drop = [0] * n
    floor, d, now, moved, done = 0, 0, 0, 0, 0
    stops = []
    while done < n:
        for i in range(n):
            if status[i] == 0 and reqs[i][0] == now:
                status[i] = 1
        acted = False
        for i in range(n):
            if status[i] == 2 and reqs[i][2] == floor:
                status[i] = 3
                drop[i] = now
                done += 1
                acted = True
        if done == n:
            stops.append(floor)
            break
        if d != 0:
            ahead = any((status[i] == 2 and _sign(reqs[i][2] - floor) == d) or (status[i] == 1 and _sign(reqs[i][1] - floor) == d) for i in range(n))
            if not ahead:
                d = 0
        here = [i for i in range(n) if status[i] == 1 and reqs[i][1] == floor]
        if here:
            sd = d if d != 0 else _sign(reqs[here[0]][2] - floor)
            boarded = False
            for i in here:
                if _sign(reqs[i][2] - floor) == sd:
                    status[i] = 2
                    pickup[i] = now
                    boarded = True
            if boarded:
                acted = True
                if d == 0:
                    d = sd
        if acted:
            stops.append(floor)
        above = [reqs[i][2] if status[i] == 2 else reqs[i][1] for i in range(n) if status[i] in (1, 2)]
        up_targets = [x - floor for x in above if x > floor]
        down_targets = [floor - x for x in above if x < floor]
        if d == 0:
            if up_targets and down_targets:
                d = 1 if min(up_targets) <= min(down_targets) else -1
            elif up_targets:
                d = 1
            elif down_targets:
                d = -1
        floor += d
        moved += abs(d)
        now += 1
    return reqs, pickup, drop, now if n else 0, moved, stops


def schedule(floors, requests):
    _, pickup, drop, _, _, _ = _simulate(floors, requests)
    out = []
    for p, q in zip(pickup, drop):
        out += [p, q]
    return out


def finish_time(floors, requests):
    return _simulate(floors, requests)[3]


def travel_floors(floors, requests):
    return _simulate(floors, requests)[4]


def max_wait(floors, requests):
    reqs, pickup, _, _, _, _ = _simulate(floors, requests)
    return max([p - r[0] for p, r in zip(pickup, reqs)], default=0)


def stops(floors, requests):
    return _simulate(floors, requests)[5]
''')

LF_GO = dd(r'''
package liftdispatch

import "errors"

type sim struct {
	pickup, drop []int64
	reqT         []int64
	finish       int64
	moved        int64
	stops        []int64
}

func sign(x int64) int64 {
	if x > 0 {
		return 1
	}
	if x < 0 {
		return -1
	}
	return 0
}

func abs(x int64) int64 {
	if x < 0 {
		return -x
	}
	return x
}

func simulate(floors int64, requests []int64) (*sim, error) {
	if floors < 2 || floors > 100 || len(requests)%3 != 0 {
		return nil, errors.New("bad input")
	}
	n := len(requests) / 3
	t := make([]int64, n)
	from := make([]int64, n)
	to := make([]int64, n)
	for i := 0; i < n; i++ {
		t[i], from[i], to[i] = requests[3*i], requests[3*i+1], requests[3*i+2]
		if t[i] < 0 || t[i] > 100000 || from[i] < 0 || from[i] >= floors || to[i] < 0 || to[i] >= floors || from[i] == to[i] {
			return nil, errors.New("bad request")
		}
	}
	s := &sim{pickup: make([]int64, n), drop: make([]int64, n), reqT: t, stops: []int64{}}
	status := make([]int, n) // 0 future, 1 waiting, 2 riding, 3 done
	var floor, d, now, done int64
	for done < int64(n) {
		for i := 0; i < n; i++ {
			if status[i] == 0 && t[i] == now {
				status[i] = 1
			}
		}
		acted := false
		for i := 0; i < n; i++ {
			if status[i] == 2 && to[i] == floor {
				status[i] = 3
				s.drop[i] = now
				done++
				acted = true
			}
		}
		if done == int64(n) {
			s.stops = append(s.stops, floor)
			break
		}
		if d != 0 {
			ahead := false
			for i := 0; i < n; i++ {
				if (status[i] == 2 && sign(to[i]-floor) == d) || (status[i] == 1 && sign(from[i]-floor) == d) {
					ahead = true
					break
				}
			}
			if !ahead {
				d = 0
			}
		}
		first := -1
		for i := 0; i < n; i++ {
			if status[i] == 1 && from[i] == floor {
				first = i
				break
			}
		}
		if first >= 0 {
			sd := d
			if sd == 0 {
				sd = sign(to[first] - floor)
			}
			boarded := false
			for i := 0; i < n; i++ {
				if status[i] == 1 && from[i] == floor && sign(to[i]-floor) == sd {
					status[i] = 2
					s.pickup[i] = now
					boarded = true
				}
			}
			if boarded {
				acted = true
				if d == 0 {
					d = sd
				}
			}
		}
		if acted {
			s.stops = append(s.stops, floor)
		}
		var nearUp, nearDown int64 = -1, -1
		for i := 0; i < n; i++ {
			var target int64
			switch status[i] {
			case 1:
				target = from[i]
			case 2:
				target = to[i]
			default:
				continue
			}
			if target > floor && (nearUp < 0 || target-floor < nearUp) {
				nearUp = target - floor
			}
			if target < floor && (nearDown < 0 || floor-target < nearDown) {
				nearDown = floor - target
			}
		}
		up, down := nearUp >= 0, nearDown >= 0
		if d == 0 {
			switch {
			case up && down:
				if nearUp <= nearDown {
					d = 1
				} else {
					d = -1
				}
			case up:
				d = 1
			case down:
				d = -1
			}
		}
		floor += d
		s.moved += abs(d)
		now++
	}
	if n > 0 {
		s.finish = now
	}
	return s, nil
}

func Schedule(floors int64, requests []int64) ([]int64, error) {
	s, err := simulate(floors, requests)
	if err != nil {
		return nil, err
	}
	out := []int64{}
	for i := range s.pickup {
		out = append(out, s.pickup[i], s.drop[i])
	}
	return out, nil
}

func FinishTime(floors int64, requests []int64) (int64, error) {
	s, err := simulate(floors, requests)
	if err != nil {
		return 0, err
	}
	return s.finish, nil
}

func TravelFloors(floors int64, requests []int64) (int64, error) {
	s, err := simulate(floors, requests)
	if err != nil {
		return 0, err
	}
	return s.moved, nil
}

func MaxWait(floors int64, requests []int64) (int64, error) {
	s, err := simulate(floors, requests)
	if err != nil {
		return 0, err
	}
	var best int64
	for i := range s.pickup {
		if w := s.pickup[i] - s.reqT[i]; w > best {
			best = w
		}
	}
	return best, nil
}

func Stops(floors int64, requests []int64) ([]int64, error) {
	s, err := simulate(floors, requests)
	if err != nil {
		return nil, err
	}
	return s.stops, nil
}
''')


def lf_cases(rng):
    out = [("schedule", [10, [0, 0, 5]]), ("finish_time", [10, [0, 0, 5, 1, 3, 1]]), ("travel_floors", [5, [0, 4, 0]]), ("max_wait", [8, [0, 2, 6, 0, 5, 1]]), ("stops", [6, [0, 1, 4, 0, 3, 0]]), ("schedule", [5, []]),
           ("finish_time", [5, []]), ("stops", [5, []])]
    hand = [
        (10, [0, 0, 5]), (10, [0, 5, 0]), (10, [3, 5, 0]), (10, [0, 0, 5, 0, 0, 3, 0, 2, 8]), (6, [0, 3, 1, 0, 3, 5]), (6, [0, 3, 5, 0, 3, 1]), (6, [0, 3, 1, 0, 3, 5, 0, 3, 4]), (8, [0, 4, 2, 1, 2, 6, 2, 7, 0]),
        (5, [0, 0, 4, 0, 4, 0]), (5, [0, 4, 0, 0, 0, 4]), (5, [0, 2, 4, 0, 2, 0, 0, 2, 3]), (9, [0, 2, 8, 1, 6, 1, 1, 4, 7, 3, 3, 0]), (4, [0, 3, 2, 0, 1, 0, 0, 2, 3, 5, 0, 3]), (7, [0, 3, 6, 0, 3, 1]),
        (7, [0, 6, 3, 0, 1, 3]), (7, [0, 1, 5, 0, 5, 1]), (12, [0, 5, 10, 0, 8, 2, 0, 3, 11, 1, 6, 0]), (3, [0, 1, 2, 0, 2, 1, 0, 1, 0, 0, 0, 1, 4, 2, 0]), (6, [10, 0, 5, 12, 5, 0]), (6, [0, 1, 2, 50, 4, 3]),
        (20, [0, 10, 0, 0, 10, 19]), (20, [0, 15, 5, 0, 5, 15]), (20, [0, 5, 15, 0, 15, 5]), (6, [0, 2, 4, 0, 4, 2]), (6, [0, 3, 0, 0, 3, 5]), (2, [0, 0, 1, 0, 1, 0]), (2, [3, 1, 0, 3, 0, 1]),
    ]
    for floors, reqs in hand:
        for fn in ["schedule", "finish_time", "travel_floors", "max_wait", "stops"]:
            out.append((fn, [floors, reqs]))
    for floors, reqs in [(10, [0, 0, 4, 5, 2, 0, 5, 6, 9]), (10, [0, 0, 4, 5, 6, 9, 5, 2, 0]), (12, [0, 0, 6, 7, 3, 0, 7, 9, 11]), (9, [0, 0, 4, 6, 3, 8, 6, 5, 0]), (8, [0, 7, 0, 3, 6, 7]), (10, [0, 5, 0, 4, 8, 9, 5, 3, 1])]:
        for fn in ["schedule", "finish_time", "travel_floors", "max_wait", "stops"]:
            out.append((fn, [floors, reqs]))
    for _ in range(130):
        floors = rng.randint(2, 12)
        n = rng.randint(0, 9)
        reqs = []
        span = rng.choice([0, 3, 8, 15, 30])
        for _ in range(n):
            a = rng.randrange(floors)
            b = rng.randrange(floors)
            while b == a:
                b = rng.randrange(floors)
            reqs += [rng.randint(0, span), a, b]
        for fn in ["schedule", "finish_time", "travel_floors", "max_wait", "stops"]:
            out.append((fn, [floors, reqs]))
    for floors, reqs in [(1, [0, 0, 1]), (0, []), (101, []), (-3, []), (5, [0, 1]), (5, [0, 1, 2, 3]), (5, [0, 1, 1]), (5, [-1, 0, 1]), (5, [0, -1, 2]), (5, [0, 1, 5]), (5, [0, 5, 1]), (5, [100001, 0, 1]), (5, [0, 0, 5]), (5, [0, 2, -2])]:
        for fn in ["schedule", "finish_time", "travel_floors", "max_wait", "stops"]:
            out.append((fn, [floors, reqs]))
    return out


LF = PortLib(
    slug="lift-dispatch",
    title="lift dispatch simulation",
    blurb="A building-management package simulates a single lift with collective control (turn-around, boarding direction and idle-choice rules) and the rewrite has to reproduce every tick exactly.",
    spec=LF_SPEC,
    fns=LF_FNS,
    impls={"python": {"lift_dispatch.py": LF_PY}, "go": {"liftdispatch.go": LF_GO}},
    cases=lf_cases,
    difficulty=5,
    n_examples=10,
    pairs=[("python", "go", "full"), ("go", "python", "full"), ("python", "go", "stub"), ("go", "python", "stub")],
    traps=["ordered steps within a tick", "tie-breaking (lowest index, nearest floor, up wins ties)", "direction release before boarding", "boundary behaviour at the last drop"],
    tags=["simulation", "state-machine"],
)
register_port(LF, __name__)
