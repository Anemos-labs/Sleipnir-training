"""Exhaustive search for the best journeys: the best one is defined by the ordered criteria of config.CRITERIA."""
import config as C


class Journey:
    def __init__(self, legs, arrive, rides, fare, walk):
        self.legs = legs  # ("ride", trip, i, j, board_time) / ("walk", from, to, minutes, leave_time)
        self.arrive = arrive
        self.rides = rides
        self.fare = fare
        self.walk = walk

    def leg_keys(self):
        out = []
        for leg in self.legs:
            if leg[0] == "ride":
                out.append((0, leg[1].route, leg[1].dep, leg[1].stops[leg[2]][0], leg[1].stops[leg[3]][0]))
            else:
                out.append((1, leg[1], leg[2]))
        return out

    def key(self):
        vals = {"arrive": self.arrive, "rides": self.rides, "fare": self.fare, "walk": self.walk}
        return tuple(vals[c] for c in C.CRITERIA) + (self.leg_keys(),)


def search(net, origin, t0, max_rides, no_walk, avoid, targets=None, dest=None):
    """Best journey per destination: a dict stop -> Journey (only `dest` if given)."""
    best = {}

    def record(stop, legs, arrive, rides, fare, walk):
        j = Journey(list(legs), arrive, rides, fare, walk)
        cur = best.get(stop)
        if cur is None or j.key() < cur.key():
            best[stop] = j

    def fare_of(rides_fares):
        return min(sum(rides_fares), C.FARE_CAP)

    def go(stop, ready, leave, last_kind, visited, legs, rides, fares, last_alight, walk):
        # ride from here
        if rides < max_rides:
            for trip, i in net.at.get(stop, []):
                board = trip.stops[i][1]
                if board < ready or i == len(trip.stops) - 1:
                    continue
                for j in range(i + 1, len(trip.stops)):
                    s2, alight = trip.stops[j]
                    if s2 in visited or s2 in avoid:
                        continue
                    f = net.routes[trip.route]
                    if rides > 0 and board - last_alight <= C.TRANSFER_WINDOW:
                        f = max(0, f - C.TRANSFER_DISCOUNT)
                    nf = fares + [f]
                    nl = legs + [("ride", trip, i, j, board)]
                    if dest is None or s2 == dest:
                        record(s2, nl, alight, rides + 1, fare_of(nf), walk)
                    if dest is None or s2 != dest:
                        go(s2, alight + net.change_time(s2), alight, "ride", visited | {s2}, nl, rides + 1, nf, alight, walk)
        # walk from here
        if not no_walk and last_kind != "walk":
            for s2 in sorted(net.walks[stop]):
                if s2 in visited or s2 in avoid:
                    continue
                m = net.walks[stop][s2]
                arrive = leave + m
                nl = legs + [("walk", stop, s2, m, leave)]
                if dest is None or s2 == dest:
                    record(s2, nl, arrive, rides, fare_of(fares), walk + m)
                if dest is None or s2 != dest:
                    go(s2, arrive, arrive, "walk", visited | {s2}, nl, rides, fares, last_alight, walk + m)

    go(origin, t0, t0, "start", {origin}, [], 0, [], -10 ** 9, 0)
    return best
