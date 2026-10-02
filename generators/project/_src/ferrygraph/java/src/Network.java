import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Reader for network.txt and the network model. */
final class Network {
    static final class NetworkError extends Exception {
        NetworkError(String m) {
            super(m);
        }
    }

    static final class Trip {
        final String route;
        final int dep;
        final List<String> stops = new ArrayList<>();
        final List<Integer> times = new ArrayList<>();

        Trip(String route, int dep) {
            this.route = route;
            this.dep = dep;
        }
    }

    static final class At {
        final Trip trip;
        final int index;

        At(Trip trip, int index) {
            this.trip = trip;
            this.index = index;
        }
    }

    final Map<String, Boolean> stops = new LinkedHashMap<>();
    final Map<String, TreeMap<String, Integer>> walks = new HashMap<>();
    final Map<String, Integer> change = new HashMap<>();
    final Map<String, Integer> routes = new HashMap<>();
    final List<Trip> trips = new ArrayList<>();
    final Map<String, List<At>> at = new HashMap<>();

    int changeTime(String stop) {
        return change.getOrDefault(stop, Config.CHANGE_DEFAULT);
    }

    static final Pattern NAME = Pattern.compile("^[A-Za-z][A-Za-z0-9_]*$");
    static final Pattern TIME = Pattern.compile("^([0-9]{2}):([0-5][0-9])$");
    static final Pattern NUM = Pattern.compile("^(0|[1-9][0-9]{0,3})$");

    static int parseTime(String tok) {
        Matcher m = TIME.matcher(tok);
        if (!m.matches() || Integer.parseInt(m.group(1)) > 47) return -1;
        return Integer.parseInt(m.group(1)) * 60 + Integer.parseInt(m.group(2));
    }

    static String fmtTime(int t) {
        return String.format("%02d:%02d", t / 60, t % 60);
    }

    private static NetworkError fail(int n, String msg) {
        return new NetworkError("network.txt:" + n + ": " + msg);
    }

    private static int number(String tok, int n, int lo, int hi) throws NetworkError {
        if (!NUM.matcher(tok).matches() || Integer.parseInt(tok) < lo || Integer.parseInt(tok) > hi) throw fail(n, "bad number '" + tok + "'");
        return Integer.parseInt(tok);
    }

    private String stop(String tok, int n) throws NetworkError {
        if (!stops.containsKey(tok)) throw fail(n, "unknown stop '" + tok + "'");
        return tok;
    }

    static Network read(String text) throws NetworkError {
        Network net = new Network();
        String[] lines = text.split("\n", -1);
        for (int idx = 0; idx < lines.length; idx++) {
            int n = idx + 1;
            String raw = lines[idx];
            int hash = raw.indexOf('#');
            if (hash >= 0) raw = raw.substring(0, hash);
            raw = raw.trim();
            if (raw.isEmpty()) continue;
            String[] w = raw.split("\\s+");
            String d = w[0];
            switch (d) {
                case "stop":
                    if (w.length != 2) throw fail(n, "bad line");
                    if (!NAME.matcher(w[1]).matches()) throw fail(n, "bad name '" + w[1] + "'");
                    if (net.stops.containsKey(w[1])) throw fail(n, "duplicate name '" + w[1] + "'");
                    net.stops.put(w[1], true);
                    net.walks.put(w[1], new TreeMap<>());
                    break;
                case "walk": {
                    if (w.length != 4) throw fail(n, "bad line");
                    String a = net.stop(w[1], n);
                    String b = net.stop(w[2], n);
                    int m = number(w[3], n, 1, 240);
                    net.walks.get(a).put(b, m);
                    net.walks.get(b).put(a, m);
                    break;
                }
                case "change":
                    if (w.length != 3) throw fail(n, "bad line");
                    net.change.put(net.stop(w[1], n), number(w[2], n, 0, 240));
                    break;
                case "route":
                    if (w.length != 4 || !w[2].equals("fare")) throw fail(n, "bad line");
                    if (!NAME.matcher(w[1]).matches()) throw fail(n, "bad name '" + w[1] + "'");
                    if (net.routes.containsKey(w[1])) throw fail(n, "duplicate name '" + w[1] + "'");
                    net.routes.put(w[1], number(w[3], n, 0, 99999));
                    break;
                case "trip": {
                    if (w.length < 7 || w.length % 2 == 0) throw fail(n, "bad line");
                    if (!net.routes.containsKey(w[1])) throw fail(n, "unknown route '" + w[1] + "'");
                    int dep = parseTime(w[2]);
                    if (dep < 0) throw fail(n, "bad time '" + w[2] + "'");
                    Trip trip = new Trip(w[1], dep);
                    int last = -1;
                    for (int i = 3; i < w.length; i += 2) {
                        String s = net.stop(w[i], n);
                        int off = number(w[i + 1], n, 0, 600);
                        if (off <= last && !(i == 3 && off == 0)) throw fail(n, "offsets must increase");
                        if (i == 3 && off != 0) throw fail(n, "offsets must increase");
                        if (trip.stops.contains(s)) throw fail(n, "repeated stop '" + s + "'");
                        trip.stops.add(s);
                        trip.times.add(dep + off);
                        last = off;
                    }
                    net.trips.add(trip);
                    break;
                }
                default:
                    throw fail(n, "unknown directive '" + d + "'");
            }
        }
        for (Trip trip : net.trips) {
            for (int i = 0; i < trip.stops.size(); i++) net.at.computeIfAbsent(trip.stops.get(i), k -> new ArrayList<>()).add(new At(trip, i));
        }
        return net;
    }
}
