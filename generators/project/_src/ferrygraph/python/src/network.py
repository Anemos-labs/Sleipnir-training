"""Reader for network.txt and the network model."""
import re

import config as C

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
TIME_RE = re.compile(r"^([0-9]{2}):([0-5][0-9])$")
NUM_RE = re.compile(r"^(0|[1-9][0-9]{0,3})$")


class NetworkError(Exception):
    pass


class Trip:
    def __init__(self, route, dep, stops):
        self.route = route
        self.dep = dep  # minutes of the first departure
        self.stops = stops  # [(stop, minutes)]


class Network:
    def __init__(self):
        self.stops = {}  # name -> zone
        self.walks = {}  # name -> {other: minutes}
        self.change = {}  # name -> minutes
        self.routes = {}  # id -> fare
        self.trips = []
        self.at = {}  # stop -> [(trip, index)]

    def change_time(self, stop):
        return self.change.get(stop, C.CHANGE_DEFAULT)


def parse_time(tok):
    m = TIME_RE.match(tok)
    if not m or int(m.group(1)) > 47:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def fmt_time(t):
    return "%02d:%02d" % (t // 60, t % 60)


def read_network(text):
    net = Network()

    def fail(n, msg):
        raise NetworkError("network.txt:%d: %s" % (n, msg))

    def number(tok, n, lo=0, hi=9999):
        if not NUM_RE.match(tok) or not lo <= int(tok) <= hi:
            fail(n, "bad number '%s'" % tok)
        return int(tok)

    def stop(tok, n):
        if tok not in net.stops:
            fail(n, "unknown stop '%s'" % tok)
        return tok

    for n, raw in enumerate(text.split("\n"), 1):
        w = raw.split("#", 1)[0].split()
        if not w:
            continue
        d = w[0]
        if d == "stop":
            if len(w) != 2:
                fail(n, "bad line")
            if not NAME_RE.match(w[1]):
                fail(n, "bad name '%s'" % w[1])
            if w[1] in net.stops:
                fail(n, "duplicate name '%s'" % w[1])
            net.stops[w[1]] = True
            net.walks[w[1]] = {}
        elif d == "walk":
            if len(w) != 4:
                fail(n, "bad line")
            a, b = stop(w[1], n), stop(w[2], n)
            m = number(w[3], n, 1, 240)
            net.walks[a][b] = m
            net.walks[b][a] = m
        elif d == "change":
            if len(w) != 3:
                fail(n, "bad line")
            net.change[stop(w[1], n)] = number(w[2], n, 0, 240)
        elif d == "route":
            if len(w) != 4 or w[2] != "fare":
                fail(n, "bad line")
            if not NAME_RE.match(w[1]):
                fail(n, "bad name '%s'" % w[1])
            if w[1] in net.routes:
                fail(n, "duplicate name '%s'" % w[1])
            net.routes[w[1]] = number(w[3], n, 0, 99999)
        elif d == "trip":
            if len(w) < 7 or len(w) % 2 == 0:
                fail(n, "bad line")
            if w[1] not in net.routes:
                fail(n, "unknown route '%s'" % w[1])
            dep = parse_time(w[2])
            if dep is None:
                fail(n, "bad time '%s'" % w[2])
            stops, last = [], -1
            for i in range(3, len(w), 2):
                s = stop(w[i], n)
                off = number(w[i + 1], n, 0, 600)
                if off <= last and not (i == 3 and off == 0):
                    fail(n, "offsets must increase")
                if i == 3 and off != 0:
                    fail(n, "offsets must increase")
                if s in [x for x, _ in stops]:
                    fail(n, "repeated stop '%s'" % s)
                stops.append((s, dep + off))
                last = off
            net.trips.append(Trip(w[1], dep, stops))
        else:
            fail(n, "unknown directive '%s'" % d)
    for trip in net.trips:
        for i, (s, _) in enumerate(trip.stops):
            net.at.setdefault(s, []).append((trip, i))
    return net
