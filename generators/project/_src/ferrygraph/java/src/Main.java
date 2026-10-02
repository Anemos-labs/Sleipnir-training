import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

/** ferrygraph: journey planning on a small timetable network. */
public class Main {
    static final class QueryError extends Exception {
        QueryError(String m) {
            super(m);
        }
    }

    private final Network net;
    private final StringBuilder out = new StringBuilder();
    private int status = 0;

    Main(Network net) {
        this.net = net;
    }

    private static String noun(int n, String word) {
        return n + " " + word + (n == 1 ? "" : "s");
    }

    private String stopArg(String tok) throws QueryError {
        if (!net.stops.containsKey(tok)) throw new QueryError("unknown stop '" + tok + "'");
        return tok;
    }

    private static int timeArg(String tok) throws QueryError {
        int t = Network.parseTime(tok);
        if (t < 0) throw new QueryError("bad time '" + tok + "'");
        return t;
    }

    private static String routeUsage() {
        return "usage: route FROM TO at HH:MM [rides N]" + (Config.HAS_NOWALK ? " [nowalk]" : "") + (Config.HAS_AVOID ? " [avoid STOP]..." : "");
    }

    private static boolean isDigit(String s) {
        return s.matches("[0-9]");
    }

    private int rides;
    private boolean noWalk;
    private final Set<String> avoid = new HashSet<>();

    private void options(List<String> toks, boolean allowRoute) throws QueryError {
        rides = Config.MAX_RIDES;
        noWalk = false;
        avoid.clear();
        int i = 0;
        while (i < toks.size()) {
            String t = toks.get(i);
            if (t.equals("rides")) {
                if (i + 1 >= toks.size() || !isDigit(toks.get(i + 1))) throw new QueryError("bad number '" + (i + 1 < toks.size() ? toks.get(i + 1) : "") + "'");
                rides = Math.min(Integer.parseInt(toks.get(i + 1)), Config.MAX_RIDES);
                i += 2;
            } else if (t.equals("nowalk") && allowRoute && Config.HAS_NOWALK) {
                noWalk = true;
                i++;
            } else if (t.equals("avoid") && allowRoute && Config.HAS_AVOID) {
                if (i + 1 >= toks.size()) throw new QueryError(routeUsage());
                avoid.add(stopArg(toks.get(i + 1)));
                i += 2;
            } else {
                throw new QueryError("bad option '" + t + "'");
            }
        }
    }

    private List<String> qRoute(List<String> toks) throws QueryError {
        if (toks.size() < 4 || !toks.get(2).equals("at")) throw new QueryError(routeUsage());
        String a = stopArg(toks.get(0));
        String b = stopArg(toks.get(1));
        int t0 = timeArg(toks.get(3));
        options(toks.subList(4, toks.size()), true);
        if (a.equals(b)) throw new QueryError("origin and destination are the same");
        Search s = new Search(net, rides, noWalk, new HashSet<>(avoid), b);
        s.run(a, t0);
        Search.Journey j = s.best.get(b);
        List<String> res = new ArrayList<>();
        if (j == null) {
            res.add("no journey " + a + " -> " + b);
            return res;
        }
        res.add("journey " + a + " -> " + b + ": arrive " + Network.fmtTime(j.arrive) + ", " + noun(j.rides, "ride") + ", " + j.walk + " walk, fare " + j.fare);
        for (Search.Leg leg : j.legs) {
            if (leg.ride) {
                res.add("  " + Network.fmtTime(leg.time) + " ride " + leg.trip.route + " " + leg.fromStop + " -> " + leg.toStop + " (arrive " + Network.fmtTime(leg.trip.times.get(leg.to)) + ")");
            } else {
                res.add("  " + Network.fmtTime(leg.time) + " walk " + leg.fromStop + " -> " + leg.toStop + " (" + leg.minutes + " min)");
            }
        }
        return res;
    }

    private List<String> qDepartures(List<String> toks) throws QueryError {
        int n = toks.size();
        if (n < 3 || !toks.get(1).equals("at") || n > 5 || (n == 5 && !toks.get(3).equals("count")) || n == 4) throw new QueryError("usage: departures STOP at HH:MM [count N]");
        String s = stopArg(toks.get(0));
        int t = timeArg(toks.get(2));
        int count = 5;
        if (n == 5) {
            if (!toks.get(4).matches("[1-9][0-9]?")) throw new QueryError("bad number '" + toks.get(4) + "'");
            count = Integer.parseInt(toks.get(4));
        }
        List<Object[]> rows = new ArrayList<>();
        List<Network.At> here = net.at.get(s);
        if (here != null) {
            for (Network.At a : here) {
                if (a.index < a.trip.stops.size() - 1 && a.trip.times.get(a.index) >= t) {
                    rows.add(new Object[] {a.trip.times.get(a.index), a.trip.route, a.trip.dep, a.trip.stops.get(a.trip.stops.size() - 1)});
                }
            }
        }
        rows.sort((x, y) -> {
            int c = Integer.compare((Integer) x[0], (Integer) y[0]);
            if (c != 0) return c;
            c = ((String) x[1]).compareTo((String) y[1]);
            if (c != 0) return c;
            c = Integer.compare((Integer) x[2], (Integer) y[2]);
            if (c != 0) return c;
            return ((String) x[3]).compareTo((String) y[3]);
        });
        List<String> res = new ArrayList<>();
        if (rows.isEmpty()) {
            res.add("no departures from " + s);
            return res;
        }
        for (int i = 0; i < Math.min(count, rows.size()); i++) {
            Object[] r = rows.get(i);
            res.add(Network.fmtTime((Integer) r[0]) + " " + r[1] + " to " + r[3]);
        }
        return res;
    }

    private List<String> qReach(List<String> toks) throws QueryError {
        if (toks.size() < 5 || !toks.get(1).equals("at") || !toks.get(3).equals("within")) throw new QueryError("usage: reach STOP at HH:MM within MINUTES [rides N]");
        String s = stopArg(toks.get(0));
        int t0 = timeArg(toks.get(2));
        if (!toks.get(4).matches("0|[1-9][0-9]{0,3}")) throw new QueryError("bad number '" + toks.get(4) + "'");
        int within = Integer.parseInt(toks.get(4));
        options(toks.subList(5, toks.size()), false);
        Search search = new Search(net, rides, false, new HashSet<>(), null);
        search.run(s, t0);
        List<Map.Entry<String, Search.Journey>> rows = new ArrayList<>();
        for (Map.Entry<String, Search.Journey> e : search.best.entrySet()) {
            if (!e.getKey().equals(s) && e.getValue().arrive - t0 <= within) rows.add(e);
        }
        rows.sort((x, y) -> {
            int c = Integer.compare(x.getValue().arrive, y.getValue().arrive);
            return c != 0 ? c : x.getKey().compareTo(y.getKey());
        });
        List<String> res = new ArrayList<>();
        if (rows.isEmpty()) {
            res.add("nothing reachable from " + s);
            return res;
        }
        for (Map.Entry<String, Search.Journey> e : rows) res.add(e.getKey() + " arrive " + Network.fmtTime(e.getValue().arrive) + ", " + noun(e.getValue().rides, "ride"));
        return res;
    }

    void run(String raw) {
        String line = raw.strip();
        if (line.isEmpty() || line.startsWith("#")) return;
        List<String> toks = new ArrayList<>(Arrays.asList(line.split("\\s+")));
        String cmd = toks.get(0);
        List<String> args = toks.subList(1, toks.size());
        try {
            List<String> res;
            switch (cmd) {
                case "route":
                    res = qRoute(args);
                    break;
                case "departures":
                    res = qDepartures(args);
                    break;
                case "reach":
                    res = qReach(args);
                    break;
                default:
                    throw new QueryError("unknown command '" + cmd + "'");
            }
            for (String l : res) out.append(l).append('\n');
        } catch (QueryError e) {
            out.append("error: ").append(e.getMessage()).append('\n');
            status = 1;
        }
    }

    public static void main(String[] argv) throws IOException {
        String text;
        try {
            text = new String(Files.readAllBytes(Path.of("network.txt")), StandardCharsets.UTF_8);
        } catch (IOException e) {
            System.out.print("error: cannot read network.txt\n");
            System.exit(1);
            return;
        }
        Network net;
        try {
            net = Network.read(text);
        } catch (Network.NetworkError e) {
            System.out.print("error: " + e.getMessage() + "\n");
            System.exit(1);
            return;
        }
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        byte[] chunk = new byte[8192];
        int n;
        while ((n = System.in.read(chunk)) > 0) bos.write(chunk, 0, n);
        Main m = new Main(net);
        for (String raw : bos.toString("UTF-8").split("\n", -1)) m.run(raw);
        System.out.print(m.out);
        System.out.flush();
        System.exit(m.status);
    }
}
