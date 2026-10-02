import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

/** Exhaustive search for the best journeys; the best one is defined by the ordered criteria of Config.CRITERIA. */
final class Search {
    static final class Leg {
        final boolean ride;
        final Network.Trip trip;
        final int from;
        final int to;
        final int time; // boarding time of a ride, leaving time of a walk
        final String fromStop;
        final String toStop;
        final int minutes;

        Leg(Network.Trip trip, int i, int j, int board) {
            this.ride = true;
            this.trip = trip;
            this.from = i;
            this.to = j;
            this.time = board;
            this.fromStop = trip.stops.get(i);
            this.toStop = trip.stops.get(j);
            this.minutes = 0;
        }

        Leg(String a, String b, int minutes, int leave) {
            this.ride = false;
            this.trip = null;
            this.from = 0;
            this.to = 0;
            this.time = leave;
            this.fromStop = a;
            this.toStop = b;
            this.minutes = minutes;
        }

        int compareKey(Leg o) {
            int ka = ride ? 0 : 1;
            int kb = o.ride ? 0 : 1;
            if (ka != kb) return Integer.compare(ka, kb);
            int c;
            if (ride) {
                if ((c = trip.route.compareTo(o.trip.route)) != 0) return c;
                if ((c = Integer.compare(trip.dep, o.trip.dep)) != 0) return c;
            }
            if ((c = fromStop.compareTo(o.fromStop)) != 0) return c;
            return toStop.compareTo(o.toStop);
        }
    }

    static final class Journey {
        final List<Leg> legs;
        final int arrive;
        final int rides;
        final int fare;
        final int walk;

        Journey(List<Leg> legs, int arrive, int rides, int fare, int walk) {
            this.legs = new ArrayList<>(legs);
            this.arrive = arrive;
            this.rides = rides;
            this.fare = fare;
            this.walk = walk;
        }

        int value(String c) {
            switch (c) {
                case "arrive":
                    return arrive;
                case "rides":
                    return rides;
                case "fare":
                    return fare;
                default:
                    return walk;
            }
        }

        int compareTo(Journey o) {
            for (String c : Config.CRITERIA) {
                int r = Integer.compare(value(c), o.value(c));
                if (r != 0) return r;
            }
            for (int i = 0; i < Math.min(legs.size(), o.legs.size()); i++) {
                int r = legs.get(i).compareKey(o.legs.get(i));
                if (r != 0) return r;
            }
            return Integer.compare(legs.size(), o.legs.size());
        }
    }

    private final Network net;
    private final int maxRides;
    private final boolean noWalk;
    private final Set<String> avoid;
    private final String dest;
    final Map<String, Journey> best = new TreeMap<>();

    Search(Network net, int maxRides, boolean noWalk, Set<String> avoid, String dest) {
        this.net = net;
        this.maxRides = maxRides;
        this.noWalk = noWalk;
        this.avoid = avoid;
        this.dest = dest;
    }

    private void record(String stop, List<Leg> legs, int arrive, int rides, int fare, int walk) {
        Journey j = new Journey(legs, arrive, rides, fare, walk);
        Journey cur = best.get(stop);
        if (cur == null || j.compareTo(cur) < 0) best.put(stop, j);
    }

    private int fareOf(List<Integer> fares) {
        int sum = 0;
        for (int f : fares) sum += f;
        return Math.min(sum, Config.FARE_CAP);
    }

    void run(String origin, int t0) {
        Set<String> visited = new HashSet<>();
        visited.add(origin);
        go(origin, t0, t0, "start", visited, new ArrayList<>(), 0, new ArrayList<>(), -1_000_000_000, 0);
    }

    private void go(String stop, int ready, int leave, String lastKind, Set<String> visited, List<Leg> legs, int rides, List<Integer> fares, int lastAlight, int walk) {
        if (rides < maxRides) {
            List<Network.At> here = net.at.get(stop);
            if (here != null) {
                for (Network.At a : here) {
                    Network.Trip trip = a.trip;
                    int i = a.index;
                    int board = trip.times.get(i);
                    if (board < ready || i == trip.stops.size() - 1) continue;
                    for (int j = i + 1; j < trip.stops.size(); j++) {
                        String s2 = trip.stops.get(j);
                        int alight = trip.times.get(j);
                        if (visited.contains(s2) || avoid.contains(s2)) continue;
                        int f = net.routes.get(trip.route);
                        if (rides > 0 && board - lastAlight <= Config.TRANSFER_WINDOW) f = Math.max(0, f - Config.TRANSFER_DISCOUNT);
                        List<Integer> nf = new ArrayList<>(fares);
                        nf.add(f);
                        List<Leg> nl = new ArrayList<>(legs);
                        nl.add(new Leg(trip, i, j, board));
                        if (dest == null || s2.equals(dest)) record(s2, nl, alight, rides + 1, fareOf(nf), walk);
                        if (dest == null || !s2.equals(dest)) {
                            Set<String> nv = new HashSet<>(visited);
                            nv.add(s2);
                            go(s2, alight + net.changeTime(s2), alight, "ride", nv, nl, rides + 1, nf, alight, walk);
                        }
                    }
                }
            }
        }
        if (!noWalk && !lastKind.equals("walk")) {
            for (Map.Entry<String, Integer> e : net.walks.get(stop).entrySet()) {
                String s2 = e.getKey();
                if (visited.contains(s2) || avoid.contains(s2)) continue;
                int m = e.getValue();
                int arrive = leave + m;
                List<Leg> nl = new ArrayList<>(legs);
                nl.add(new Leg(stop, s2, m, leave));
                if (dest == null || s2.equals(dest)) record(s2, nl, arrive, rides, fareOf(fares), walk + m);
                if (dest == null || !s2.equals(dest)) {
                    Set<String> nv = new HashSet<>(visited);
                    nv.add(s2);
                    go(s2, arrive, arrive, "walk", nv, nl, rides, fares, lastAlight, walk + m);
                }
            }
        }
    }
}
