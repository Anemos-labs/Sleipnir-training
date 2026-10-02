"""ferrygraph: journey planning on a small timetable network."""
import re
import sys

import config as C
from network import NetworkError, fmt_time, parse_time, read_network
from search import search


class QueryError(Exception):
    pass


def noun(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def describe(net, origin, dest, j):
    out = ["journey %s -> %s: arrive %s, %s, %s, fare %d" % (origin, dest, fmt_time(j.arrive), noun(j.rides, "ride"), "%d walk" % j.walk, j.fare)]
    for leg in j.legs:
        if leg[0] == "ride":
            trip, i, k, board = leg[1], leg[2], leg[3], leg[4]
            out.append("  %s ride %s %s -> %s (arrive %s)" % (fmt_time(board), trip.route, trip.stops[i][0], trip.stops[k][0], fmt_time(trip.stops[k][1])))
        else:
            out.append("  %s walk %s -> %s (%d min)" % (fmt_time(leg[4]), leg[1], leg[2], leg[3]))
    return out


def stop_arg(net, tok):
    if tok not in net.stops:
        raise QueryError("unknown stop '%s'" % tok)
    return tok


def time_arg(tok):
    t = parse_time(tok)
    if t is None:
        raise QueryError("bad time '%s'" % tok)
    return t


def options(net, toks, allow):
    """Parse trailing options: rides N, nowalk, avoid STOP (as enabled)."""
    opt = {"rides": C.MAX_RIDES, "nowalk": False, "avoid": set()}
    i = 0
    while i < len(toks):
        t = toks[i]
        if t == "rides" and "rides" in allow:
            if i + 1 >= len(toks) or not re.match(r"^[0-9]$", toks[i + 1]):
                raise QueryError("bad number '%s'" % (toks[i + 1] if i + 1 < len(toks) else ""))
            opt["rides"] = min(int(toks[i + 1]), C.MAX_RIDES)
            i += 2
        elif t == "nowalk" and "nowalk" in allow and C.HAS_NOWALK:
            opt["nowalk"] = True
            i += 1
        elif t == "avoid" and "avoid" in allow and C.HAS_AVOID:
            if i + 1 >= len(toks):
                raise QueryError("usage: route FROM TO at HH:MM [rides N]" + (" [nowalk]" if C.HAS_NOWALK else "") + (" [avoid STOP]..." if C.HAS_AVOID else ""))
            opt["avoid"].add(stop_arg(net, toks[i + 1]))
            i += 2
        else:
            raise QueryError("bad option '%s'" % t)
    return opt


def q_route(net, toks):
    if len(toks) < 4 or toks[2] != "at":
        raise QueryError("usage: route FROM TO at HH:MM [rides N]" + (" [nowalk]" if C.HAS_NOWALK else "") + (" [avoid STOP]..." if C.HAS_AVOID else ""))
    a, b = stop_arg(net, toks[0]), stop_arg(net, toks[1])
    t0 = time_arg(toks[3])
    opt = options(net, toks[4:], ("rides", "nowalk", "avoid"))
    if a == b:
        raise QueryError("origin and destination are the same")
    best = search(net, a, t0, opt["rides"], opt["nowalk"], opt["avoid"], dest=b)
    if b not in best:
        return ["no journey %s -> %s" % (a, b)]
    return describe(net, a, b, best[b])


def q_departures(net, toks):
    if len(toks) < 3 or toks[1] != "at" or len(toks) > 5 or (len(toks) == 5 and toks[3] != "count") or len(toks) == 4:
        raise QueryError("usage: departures STOP at HH:MM [count N]")
    s = stop_arg(net, toks[0])
    t = time_arg(toks[2])
    count = 5
    if len(toks) == 5:
        if not re.match(r"^[1-9][0-9]?$", toks[4]):
            raise QueryError("bad number '%s'" % toks[4])
        count = int(toks[4])
    rows = []
    for trip, i in net.at.get(s, []):
        if i < len(trip.stops) - 1 and trip.stops[i][1] >= t:
            rows.append((trip.stops[i][1], trip.route, trip.dep, trip.stops[-1][0]))
    rows.sort()
    if not rows:
        return ["no departures from %s" % s]
    return ["%s %s to %s" % (fmt_time(r[0]), r[1], r[3]) for r in rows[:count]]


def q_reach(net, toks):
    if len(toks) < 5 or toks[1] != "at" or toks[3] != "within":
        raise QueryError("usage: reach STOP at HH:MM within MINUTES [rides N]")
    s = stop_arg(net, toks[0])
    t0 = time_arg(toks[2])
    if not re.match(r"^(0|[1-9][0-9]{0,3})$", toks[4]):
        raise QueryError("bad number '%s'" % toks[4])
    within = int(toks[4])
    opt = options(net, toks[5:], ("rides",))
    best = search(net, s, t0, opt["rides"], False, set())
    rows = sorted((j.arrive, name, j) for name, j in best.items() if name != s and j.arrive - t0 <= within)
    if not rows:
        return ["nothing reachable from %s" % s]
    return ["%s arrive %s, %s" % (name, fmt_time(j.arrive), noun(j.rides, "ride")) for _, name, j in rows]


def main():
    try:
        with open("network.txt", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        print("error: cannot read network.txt")
        return 1
    try:
        net = read_network(text)
    except NetworkError as e:
        print("error: " + str(e))
        return 1
    table = {"route": q_route, "departures": q_departures, "reach": q_reach}
    status = 0
    for raw in sys.stdin.read().split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        toks = line.split()
        try:
            fn = table.get(toks[0])
            if fn is None:
                raise QueryError("unknown command '%s'" % toks[0])
            for out in fn(net, toks[1:]):
                print(out)
        except QueryError as e:
            print("error: " + str(e))
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
