import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Opening hours: windows such as `mon-fri@08:00-18:00,sat@10:00-14:00` and the test whether a minute of the week lies in them. */
final class Hours {
    static final String[] DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"};

    private Hours() {}

    static final class Window {
        final Set<Integer> days;
        final int start;
        final int end;
        final boolean crossing;

        Window(Set<Integer> days, int start, int end) {
            this.days = days;
            this.start = start;
            this.end = end;
            this.crossing = end < start;
        }
    }

    static int dayIndex(String text) {
        for (int i = 0; i < DAYS.length; i++) {
            if (DAYS[i].equals(text)) {
                return i;
            }
        }
        return -1;
    }

    /** Minutes since midnight of `HH:MM`, or -1; `24:00` is accepted only for the end of a window. */
    static int clock(String text, boolean allow24) {
        if (allow24 && text.equals("24:00")) {
            return 1440;
        }
        if (text.length() != 5 || text.charAt(2) != ':') {
            return -1;
        }
        for (int i : new int[] {0, 1, 3, 4}) {
            if (text.charAt(i) < '0' || text.charAt(i) > '9') {
                return -1;
            }
        }
        int h = Integer.parseInt(text.substring(0, 2));
        int m = Integer.parseInt(text.substring(3));
        return h > 23 || m > 59 ? -1 : h * 60 + m;
    }

    /** The weekday numbers (0 = mon) of `*`, `DAY` or `DAY-DAY` (a range may wrap around the end of the week), or null. */
    static Set<Integer> parseDays(String text) {
        Set<Integer> out = new HashSet<>();
        if (text.equals("*")) {
            for (int i = 0; i < 7; i++) {
                out.add(i);
            }
            return out;
        }
        String[] parts = text.split("-", -1);
        if (parts.length == 1 && dayIndex(parts[0]) >= 0) {
            out.add(dayIndex(parts[0]));
            return out;
        }
        if (parts.length == 2 && dayIndex(parts[0]) >= 0 && dayIndex(parts[1]) >= 0) {
            int a = dayIndex(parts[0]);
            int b = dayIndex(parts[1]);
            out.add(a);
            while (a != b) {
                a = (a + 1) % 7;
                out.add(a);
            }
            return out;
        }
        return null;
    }

    /** The windows of a specification, or null when it is bad. */
    static List<Window> parse(String spec) {
        List<Window> windows = new ArrayList<>();
        for (String part : spec.split(",", -1)) {
            String[] halves = part.split("@", -1);
            if (halves.length != 2) {
                return null;
            }
            Set<Integer> days = parseDays(halves[0]);
            String[] span = halves[1].split("-", -1);
            if (days == null || span.length != 2) {
                return null;
            }
            int start = clock(span[0], false);
            int end = clock(span[1], true);
            if (start < 0 || end < 0 || start == end || (end < start && !Config.CROSS)) {
                return null;
            }
            windows.add(new Window(days, start, end));
        }
        return windows;
    }

    /** Whether minute `t` (since Monday 00:00 of week 0) is inside one of the windows; no windows at all (null) means always open. */
    static boolean isOpen(List<Window> windows, int t) {
        if (windows == null) {
            return true;
        }
        int day = (t / 1440) % 7;
        int tod = t % 1440;
        for (Window w : windows) {
            if (!w.crossing) {
                if (w.days.contains(day) && w.start <= tod && tod < w.end) {
                    return true;
                }
            } else if ((w.days.contains(day) && tod >= w.start) || (w.days.contains((day + 6) % 7) && tod < w.end)) {
                return true;
            }
        }
        return false;
    }
}
