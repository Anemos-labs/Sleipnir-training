import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/** The venue: zones, doors, badges, the clock, and the decision for one swipe. */
final class Venue {
    static final String OUTSIDE = "outside";
    static final int WEEK = 10080;

    static final class Zone {
        final String name;
        final int level;
        final int cap; // 0: unlimited
        final List<Hours.Window> windows;
        boolean locked = false;

        Zone(String name, int level, int cap, List<Hours.Window> windows) {
            this.name = name;
            this.level = level;
            this.cap = cap;
            this.windows = windows;
        }
    }

    static final class Door {
        final String id;
        final String outer;
        final String inner;

        Door(String id, String outer, String inner) {
            this.id = id;
            this.outer = outer;
            this.inner = inner;
        }
    }

    static final class Badge {
        final String id;
        final int level;
        final Integer expires; // absolute minute, or null
        String loc = OUTSIDE;
        Integer since = null; // minute of the last grant or timeout

        Badge(String id, int level, Integer expires) {
            this.id = id;
            this.level = level;
            this.expires = expires;
        }
    }

    final Map<String, Zone> zones = new LinkedHashMap<>();
    final Map<String, Door> doors = new LinkedHashMap<>();
    final Map<String, Badge> badges = new TreeMap<>(); // sorted by id
    int now = 0;
    int grants = 0;
    int denies = 0;
    int timeouts = 0;
    final Map<String, Integer> reasons = new LinkedHashMap<>();

    static String stamp(int t) {
        return String.format("%s %02d:%02d", Hours.DAYS[(t / 1440) % 7], t % 1440 / 60, t % 60);
    }

    List<String> occupants(String zone) {
        List<String> ids = new ArrayList<>();
        for (Badge b : badges.values()) {
            if (b.loc.equals(zone)) {
                ids.add(b.id);
            }
        }
        return ids;
    }

    String countText(String zone) {
        Zone z = zones.get(zone);
        return occupants(zone).size() + "/" + (z.cap > 0 ? String.valueOf(z.cap) : "-");
    }

    /** Moves the clock to `t` and times out the badges that have been inside for too long. */
    void setClock(int t, List<String> out) {
        int before = now;
        now = t;
        if (Config.EVICT > 0 && t > before) {
            for (Badge b : badges.values()) {
                if (!b.loc.equals(OUTSIDE) && t - b.since >= Config.EVICT) {
                    out.add("[" + stamp(t) + "] TIMEOUT " + b.id + " left " + b.loc);
                    b.loc = OUTSIDE;
                    b.since = t;
                    timeouts++;
                }
            }
        }
    }

    /** The first minute at or after now that is weekday `day` at `tod`. */
    int nextAt(int day, int tod) {
        int t = now / WEEK * WEEK + day * 1440 + tod;
        return t >= now ? t : t + WEEK;
    }

    private boolean passback(Badge m, Door door, boolean inward) {
        if (Config.APB.equals("off")) {
            return false;
        }
        String here = inward ? door.outer : door.inner;
        String there = inward ? door.inner : door.outer;
        if (Config.APB.equals("soft")) {
            return m.loc.equals(there);
        }
        return !m.loc.equals(here);
    }

    private boolean fails(String reason, List<Badge> members, Door door, boolean inward) {
        Zone zone = zones.get(door.inner);
        switch (reason) {
            case "expired":
                if (!inward && !Config.EXP_OUT) {
                    return false;
                }
                for (Badge m : members) {
                    if (m.expires != null && now >= m.expires) {
                        return true;
                    }
                }
                return false;
            case "lockdown":
                return (inward || Config.SEAL) && zone.locked;
            case "passback":
                for (Badge m : members) {
                    if (passback(m, door, inward)) {
                        return true;
                    }
                }
                return false;
            case "level":
                int best = 0;
                for (Badge m : members) {
                    best = Math.max(best, m.level);
                }
                return inward && best < zone.level;
            case "hours":
                return inward && !Hours.isOpen(zone.windows, now);
            case "full":
                if (!inward || zone.cap == 0) {
                    return false;
                }
                int movers = 0;
                for (Badge m : members) {
                    if (!m.loc.equals(zone.name)) {
                        movers++;
                    }
                }
                return occupants(zone.name).size() + movers > zone.cap;
            default:
                throw new IllegalStateException(reason);
        }
    }

    /** One swipe; returns the line to print. */
    String swipe(Badge badge, Door door, String direction, Badge escort) {
        List<Badge> members = new ArrayList<>();
        members.add(badge);
        if (escort != null) {
            members.add(escort);
        }
        boolean inward = direction.equals("in");
        String target = inward ? door.inner : door.outer;
        StringBuilder who = new StringBuilder();
        for (Badge m : members) {
            who.append(who.length() > 0 ? "+" : "").append(m.id);
        }
        for (String reason : Config.ORDER) {
            if (fails(reason, members, door, inward)) {
                denies++;
                reasons.merge(reason, 1, Integer::sum);
                return "[" + stamp(now) + "] DENY " + who + " " + door.id + " " + direction + ": " + reason;
            }
        }
        for (Badge m : members) {
            m.loc = target;
            m.since = now;
        }
        grants++;
        String where = target.equals(OUTSIDE) ? "outside" : target + " (" + countText(target) + ")";
        return "[" + stamp(now) + "] GRANT " + who + " " + door.id + " " + direction + " -> " + where;
    }
}
