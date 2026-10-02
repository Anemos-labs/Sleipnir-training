import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** turnstile: a scripted door-access controller. */
public class Main {
    static final class Bad extends Exception {
        Bad(String message) {
            super(message);
        }
    }

    private final Venue v = new Venue();
    private final List<String> out = new ArrayList<>();
    private int errors = 0;

    private static boolean isName(String s) {
        if (s.isEmpty() || s.length() > 12 || s.charAt(0) < 'a' || s.charAt(0) > 'z') {
            return false;
        }
        for (char c : s.toCharArray()) {
            if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-')) {
                return false;
            }
        }
        return true;
    }

    /** `0` or digits without a leading zero, at most five of them. */
    private static boolean isNumber(String s) {
        if (s.isEmpty() || s.length() > 5 || (s.length() > 1 && s.charAt(0) == '0')) {
            return false;
        }
        for (char c : s.toCharArray()) {
            if (c < '0' || c > '9') {
                return false;
            }
        }
        return true;
    }

    private static int number(String text, int lo, int hi, String what) throws Bad {
        if (!isNumber(text) || Integer.parseInt(text) < lo || Integer.parseInt(text) > hi) {
            throw new Bad("bad " + what + " '" + text + "'");
        }
        return Integer.parseInt(text);
    }

    private static String name(String text) throws Bad {
        if (!isName(text)) {
            throw new Bad("bad name '" + text + "'");
        }
        return text;
    }

    private void zone(String[] a) throws Bad {
        Bad usage = new Bad("usage: zone NAME [level N] [cap N] [hours SPEC]");
        if (a.length == 0 || a.length % 2 == 0) {
            throw usage;
        }
        Map<String, String> opts = new HashMap<>();
        for (int i = 1; i < a.length; i += 2) {
            if (!(a[i].equals("level") || a[i].equals("cap") || a[i].equals("hours")) || opts.containsKey(a[i])) {
                throw usage;
            }
            opts.put(a[i], a[i + 1]);
        }
        String id = name(a[0]);
        if (id.equals(Venue.OUTSIDE)) {
            throw new Bad("'outside' is reserved");
        }
        if (v.zones.containsKey(id)) {
            throw new Bad("zone '" + id + "' exists");
        }
        int level = 0;
        int cap = 0;
        List<Hours.Window> windows = null;
        for (int i = 1; i < a.length; i += 2) {
            String val = opts.get(a[i]);
            if (a[i].equals("level")) {
                level = number(val, 0, 9, "level");
            } else if (a[i].equals("cap")) {
                cap = number(val, 1, 99, "cap");
            } else {
                windows = Hours.parse(val);
                if (windows == null) {
                    throw new Bad("bad hours '" + val + "'");
                }
            }
        }
        v.zones.put(id, new Venue.Zone(id, level, cap, windows));
    }

    private void door(String[] a) throws Bad {
        if (a.length != 3) {
            throw new Bad("usage: door ID A B");
        }
        String id = name(a[0]);
        if (v.doors.containsKey(id)) {
            throw new Bad("door '" + id + "' exists");
        }
        for (int i = 1; i < 3; i++) {
            if (!a[i].equals(Venue.OUTSIDE) && !v.zones.containsKey(a[i])) {
                throw new Bad("unknown zone '" + a[i] + "'");
            }
        }
        if (a[2].equals(Venue.OUTSIDE)) {
            throw new Bad("'outside' can only be the outer side");
        }
        if (a[1].equals(a[2])) {
            throw new Bad("door '" + id + "' joins a zone to itself");
        }
        v.doors.put(id, new Venue.Door(id, a[1], a[2]));
    }

    private void badge(String[] a) throws Bad {
        Bad usage = new Bad("usage: badge ID level N [expires in MINUTES]");
        if ((a.length != 3 && a.length != 6) || !a[1].equals("level") || (a.length == 6 && !(a[3].equals("expires") && a[4].equals("in")))) {
            throw usage;
        }
        String id = name(a[0]);
        if (v.badges.containsKey(id)) {
            throw new Bad("badge '" + id + "' exists");
        }
        int level = number(a[2], 0, 9, "level");
        Integer expires = null;
        if (a.length == 6) {
            expires = v.now + number(a[5], 1, 99999, "expiry");
        }
        v.badges.put(id, new Venue.Badge(id, level, expires));
    }

    private void at(String[] a) throws Bad {
        int t;
        if (a.length == 1 && a[0].startsWith("+")) {
            String n = a[0].substring(1);
            if (!isNumber(n) || Integer.parseInt(n) < 1 || Integer.parseInt(n) > 10080) {
                throw new Bad("bad time '" + a[0] + "'");
            }
            t = v.now + Integer.parseInt(n);
        } else if (a.length == 2) {
            int day = Hours.dayIndex(a[0]);
            if (day < 0) {
                throw new Bad("bad day '" + a[0] + "'");
            }
            int tod = Hours.clock(a[1], false);
            if (tod < 0) {
                throw new Bad("bad time '" + a[1] + "'");
            }
            t = v.nextAt(day, tod);
        } else {
            throw new Bad("usage: at DAY HH:MM | at +MINUTES");
        }
        v.setClock(t, out);
    }

    private void lockdown(String[] a) throws Bad {
        if (a.length != 2 || !(a[1].equals("on") || a[1].equals("off"))) {
            throw new Bad("usage: lockdown ZONE on|off");
        }
        if (!v.zones.containsKey(a[0])) {
            throw new Bad("unknown zone '" + a[0] + "'");
        }
        v.zones.get(a[0]).locked = a[1].equals("on");
        out.add("[" + Venue.stamp(v.now) + "] lockdown " + a[0] + " " + a[1]);
    }

    private void swipe(String[] a) throws Bad {
        String form = "usage: swipe BADGE DOOR in|out" + (Config.ESCORT ? " [with BADGE]" : "");
        if ((a.length != 3 && a.length != 5) || !(a[2].equals("in") || a[2].equals("out"))) {
            throw new Bad(form);
        }
        if (a.length == 5 && !(Config.ESCORT && a[2].equals("in") && a[3].equals("with"))) {
            throw new Bad(form);
        }
        if (!v.badges.containsKey(a[0])) {
            throw new Bad("unknown badge '" + a[0] + "'");
        }
        if (!v.doors.containsKey(a[1])) {
            throw new Bad("unknown door '" + a[1] + "'");
        }
        Venue.Badge escort = null;
        if (a.length == 5) {
            if (!v.badges.containsKey(a[4])) {
                throw new Bad("unknown badge '" + a[4] + "'");
            }
            if (a[4].equals(a[0])) {
                throw new Bad("an escort must be another badge");
            }
            escort = v.badges.get(a[4]);
        }
        out.add(v.swipe(v.badges.get(a[0]), v.doors.get(a[1]), a[2], escort));
    }

    private void where(String[] a) throws Bad {
        if (a.length != 1) {
            throw new Bad("usage: where BADGE");
        }
        if (!v.badges.containsKey(a[0])) {
            throw new Bad("unknown badge '" + a[0] + "'");
        }
        Venue.Badge b = v.badges.get(a[0]);
        out.add(b.id + ": " + b.loc + (b.since == null ? "" : " since " + Venue.stamp(b.since)));
    }

    private void who(String[] a) throws Bad {
        if (a.length != 1) {
            throw new Bad("usage: who ZONE");
        }
        String z = a[0];
        if (!z.equals(Venue.OUTSIDE) && !v.zones.containsKey(z)) {
            throw new Bad("unknown zone '" + z + "'");
        }
        List<String> ids = v.occupants(z);
        String count = z.equals(Venue.OUTSIDE) ? ids.size() + "/-" : v.countText(z);
        out.add(z + " (" + count + "): " + (ids.isEmpty() ? "-" : String.join(" ", ids)));
    }

    private void report(String[] a) throws Bad {
        if (a.length != 0) {
            throw new Bad("usage: report");
        }
        for (Venue.Zone z : v.zones.values()) {
            out.add(z.name + ": " + v.countText(z.name) + " level " + z.level + " " + (Hours.isOpen(z.windows, v.now) ? "open" : "closed") + (z.locked ? " lockdown" : ""));
        }
    }

    private void stats(String[] a) throws Bad {
        if (a.length != 0) {
            throw new Bad("usage: stats");
        }
        out.add("grants=" + v.grants + " denies=" + v.denies + " timeouts=" + v.timeouts);
        for (String reason : Config.ORDER) {
            if (v.reasons.getOrDefault(reason, 0) > 0) {
                out.add("deny " + reason + " " + v.reasons.get(reason));
            }
        }
    }

    private void run(String line) {
        String trimmed = line.trim();
        if (trimmed.isEmpty() || trimmed.startsWith("#")) {
            return;
        }
        String[] words = trimmed.split("\\s+");
        String[] args = new String[words.length - 1];
        System.arraycopy(words, 1, args, 0, args.length);
        try {
            switch (words[0]) {
                case "zone": zone(args); break;
                case "door": door(args); break;
                case "badge": badge(args); break;
                case "at": at(args); break;
                case "swipe": swipe(args); break;
                case "lockdown": lockdown(args); break;
                case "where": where(args); break;
                case "who": who(args); break;
                case "report": report(args); break;
                case "stats": stats(args); break;
                default: throw new Bad("unknown command '" + words[0] + "'");
            }
        } catch (Bad e) {
            out.add("error: " + e.getMessage());
            errors++;
        }
    }

    private static String readAll(InputStream in) throws IOException {
        ByteArrayOutputStream buf = new ByteArrayOutputStream();
        byte[] chunk = new byte[8192];
        int n;
        while ((n = in.read(chunk)) > 0) {
            buf.write(chunk, 0, n);
        }
        return new String(buf.toByteArray(), StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws IOException {
        Main script = new Main();
        for (String line : readAll(System.in).split("\n", -1)) {
            script.run(line);
        }
        StringBuilder sb = new StringBuilder();
        for (String l : script.out) {
            sb.append(l).append('\n');
        }
        System.out.print(sb);
        System.out.flush();
        System.exit(script.errors > 0 ? 1 : 0);
    }
}
