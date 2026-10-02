"""Warehouse putaway and pick routes (java): bugs injected into a best-fit slotting planner and a serpentine route builder."""
from fx import Lib, dd
from generators.fix._lang2 import JAVA_CHECK, java_test_main, register_libs

README = dd(r'''
    # binslot

    Putaway planning and pick routes for a small warehouse. Plain Java 17, no dependencies; sources in `src/warehouse/`.

    ## `BinId`

    A shelf location such as `A-03-2`: aisle, bay and level.

    * `BinId.parse(text)`: surrounding whitespace is ignored. The text has three parts separated by `-`: the aisle is one or two
      letters (any case, stored in upper case), the bay is one to three digits and the level one or two digits; bay and level are
      at least 1. Anything else is an `IllegalArgumentException`.
    * `aisle()`, `bay()`, `level()`; `toString()` gives the canonical text: aisle, bay padded with zeros to at least two digits,
      level (`BinId.parse("b-7-1")` prints `B-07-1`).
    * Locations are ordered by aisle first (a shorter aisle name comes first, so `Z` comes before `AA`, otherwise alphabetical),
      then bay, then level, all numerically. `equals` and `hashCode` agree with that order.

    ## `Zone`, `Item`, `Bin`

    * `Zone` is `AMBIENT`, `COLD` or `HAZ`.
    * `new Item(sku, volume, weight, zone)`: the zone is the one the item must be stored in. The sku is trimmed and must not be
      empty, the volume at least 1, the weight at least 0 (`IllegalArgumentException` otherwise).
    * `new Bin(id, zone, volume, weight)`: `id` is parsed like `BinId.parse`; `volume` (capacity) at least 1, `weight` (capacity)
      at least 0. Accessors: `id()` (a `BinId`), `zone()`, `volume()`, `weight()`.

    ## `Putaway.plan(items, bins)`

    Returns a `Plan`. `IllegalArgumentException` when two items have the same sku, or two bins have the same location.

    The items are placed one at a time in this order: largest volume first, then heaviest, then by sku (plain `String` order). An
    item goes into the eligible bin that is left with the least free volume after the item is in; ties go to the lower location. A
    bin is *eligible* for an item when

    * the bin's zone is the item's zone,
    * the free volume and the free weight capacity of the bin both are at least what the item needs,
    * a heavy item (weight over 20) only goes to levels 1 and 2,
    * in a `HAZ` bin, fewer than two items have been placed yet.

    An item without an eligible bin is *unplaced* (and later items are still tried).

    ## `Plan`

    * `assignments()`: map from sku to the canonical text of its location, iterating in placement order (placed items only);
      `binOf(sku)` is the location text or `null`.
    * `unplaced()`: skus that did not fit, in placement order.
    * `volumeUsed(bin)`, `weightUsed(bin)`, `fill(bin)`: for a location text (parsed, so any case or padding works;
      `IllegalArgumentException` for text that is not a bin of this plan). `fill` is the used volume as a whole percentage of the
      capacity, rounded down.
    * `binsUsed()`: the number of bins holding at least one item.
    * `report()`: one line per bin that holds something, lowest location first:
      `A-01-1 AMBIENT vol 8/10 wt 15/50: S1, S2` (zone, used/capacity volume, used/capacity weight, the skus in placement order),
      lines joined by `\n`; `nothing placed` when no item was placed.

    ## `Route`

    Both methods take location texts (parsed like `BinId.parse`, `IllegalArgumentException` for bad ones) and return canonical
    texts. Repeated locations count once.

    * `Route.serpentine(bins)`: the walking order. The aisles present are visited in location order; the first one is walked
      from low bays to high bays, the second from high to low, the third low to high again, and so on (alternation counts the
      aisles in the list, not letters). Within one aisle and bay the lower level comes first.
    * `Route.waves(bins, maxStops)`: the serpentine route cut into waves of at most `maxStops` stops (`maxStops` below 1 is an
      `IllegalArgumentException`). Aisles are not split between waves when they fit: the aisles are taken in route order, and an
      aisle joins the current wave if it still fits, otherwise a new wave starts with it. An aisle with more than `maxStops` stops
      closes the current wave and is cut, in route order, into chunks of `maxStops`; each chunk, the last and shorter one
      included, is a wave of its own. No bins gives no waves.
''')

ZONE = dd(r'''
    package warehouse;

    public enum Zone {
        AMBIENT, COLD, HAZ
    }
''')

BINID = dd(r'''
    package warehouse;

    import java.util.Objects;

    public final class BinId implements Comparable<BinId> {
        private final String aisle;
        private final int bay;
        private final int level;

        private BinId(String aisle, int bay, int level) {
            this.aisle = aisle;
            this.bay = bay;
            this.level = level;
        }

        public static BinId parse(String text) {
            String[] parts = text.trim().split("-", -1);
            if (parts.length != 3) {
                throw new IllegalArgumentException("expected AISLE-BAY-LEVEL: " + text);
            }
            String aisle = parts[0];
            if (aisle.length() < 1 || aisle.length() > 2) {
                throw new IllegalArgumentException("aisle is one or two letters: " + text);
            }
            for (char c : aisle.toCharArray()) {
                if (!(c >= 'a' && c <= 'z') && !(c >= 'A' && c <= 'Z')) {
                    throw new IllegalArgumentException("aisle is letters: " + text);
                }
            }
            int bay = number(parts[1], 3, text);
            int level = number(parts[2], 2, text);
            if (bay < 1 || level < 1) {
                throw new IllegalArgumentException("bay and level start at 1: " + text);
            }
            return new BinId(aisle.toUpperCase(), bay, level);
        }

        private static int number(String s, int maxDigits, String text) {
            if (s.isEmpty() || s.length() > maxDigits) {
                throw new IllegalArgumentException("bad number in " + text);
            }
            int v = 0;
            for (char c : s.toCharArray()) {
                if (c < '0' || c > '9') {
                    throw new IllegalArgumentException("bad number in " + text);
                }
                v = v * 10 + (c - '0');
            }
            return v;
        }

        public String aisle() {
            return aisle;
        }

        public int bay() {
            return bay;
        }

        public int level() {
            return level;
        }

        @Override
        public int compareTo(BinId o) {
            if (aisle.length() != o.aisle.length()) {
                return Integer.compare(aisle.length(), o.aisle.length());
            }
            int c = aisle.compareTo(o.aisle);
            if (c != 0) {
                return c;
            }
            if (bay != o.bay) {
                return Integer.compare(bay, o.bay);
            }
            return Integer.compare(level, o.level);
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof BinId && compareTo((BinId) other) == 0;
        }

        @Override
        public int hashCode() {
            return Objects.hash(aisle, bay, level);
        }

        @Override
        public String toString() {
            return aisle + "-" + String.format("%02d", bay) + "-" + level;
        }
    }
''')

ITEM = dd(r'''
    package warehouse;

    public final class Item {
        private final String sku;
        private final int volume;
        private final int weight;
        private final Zone zone;

        public Item(String sku, int volume, int weight, Zone zone) {
            String s = sku.trim();
            if (s.isEmpty()) {
                throw new IllegalArgumentException("empty sku");
            }
            if (volume < 1) {
                throw new IllegalArgumentException("volume must be at least 1");
            }
            if (weight < 0) {
                throw new IllegalArgumentException("weight must not be negative");
            }
            this.sku = s;
            this.volume = volume;
            this.weight = weight;
            this.zone = zone;
        }

        public String sku() {
            return sku;
        }

        public int volume() {
            return volume;
        }

        public int weight() {
            return weight;
        }

        public Zone zone() {
            return zone;
        }
    }
''')

BIN = dd(r'''
    package warehouse;

    public final class Bin {
        private final BinId id;
        private final Zone zone;
        private final int volume;
        private final int weight;

        public Bin(String id, Zone zone, int volume, int weight) {
            if (volume < 1) {
                throw new IllegalArgumentException("volume must be at least 1");
            }
            if (weight < 0) {
                throw new IllegalArgumentException("weight must not be negative");
            }
            this.id = BinId.parse(id);
            this.zone = zone;
            this.volume = volume;
            this.weight = weight;
        }

        public BinId id() {
            return id;
        }

        public Zone zone() {
            return zone;
        }

        public int volume() {
            return volume;
        }

        public int weight() {
            return weight;
        }
    }
''')

PLAN = dd(r'''
    package warehouse;

    import java.util.ArrayList;
    import java.util.Collections;
    import java.util.LinkedHashMap;
    import java.util.List;
    import java.util.Map;
    import java.util.TreeMap;

    public final class Plan {
        private final Map<BinId, Bin> bins;
        private final Map<BinId, Integer> volumeUsed = new TreeMap<>();
        private final Map<BinId, Integer> weightUsed = new TreeMap<>();
        private final Map<BinId, List<String>> skus = new TreeMap<>();
        private final Map<String, String> assignments = new LinkedHashMap<>();
        private final List<String> unplaced = new ArrayList<>();

        Plan(Map<BinId, Bin> bins) {
            this.bins = bins;
            for (BinId id : bins.keySet()) {
                volumeUsed.put(id, 0);
                weightUsed.put(id, 0);
                skus.put(id, new ArrayList<>());
            }
        }

        void place(Item item, Bin bin) {
            BinId id = bin.id();
            volumeUsed.merge(id, item.volume(), Integer::sum);
            weightUsed.merge(id, item.weight(), Integer::sum);
            skus.get(id).add(item.sku());
            assignments.put(item.sku(), id.toString());
        }

        void reject(Item item) {
            unplaced.add(item.sku());
        }

        int itemsIn(Bin bin) {
            return skus.get(bin.id()).size();
        }

        int freeVolume(Bin bin) {
            return bin.volume() - volumeUsed.get(bin.id());
        }

        int freeWeight(Bin bin) {
            return bin.weight() - weightUsed.get(bin.id());
        }

        public Map<String, String> assignments() {
            return Collections.unmodifiableMap(assignments);
        }

        public String binOf(String sku) {
            return assignments.get(sku);
        }

        public List<String> unplaced() {
            return Collections.unmodifiableList(unplaced);
        }

        private BinId lookup(String text) {
            BinId id = BinId.parse(text);
            if (!bins.containsKey(id)) {
                throw new IllegalArgumentException("not a bin of this plan: " + text);
            }
            return id;
        }

        public int volumeUsed(String bin) {
            return volumeUsed.get(lookup(bin));
        }

        public int weightUsed(String bin) {
            return weightUsed.get(lookup(bin));
        }

        public int fill(String bin) {
            BinId id = lookup(bin);
            return 100 * volumeUsed.get(id) / bins.get(id).volume();
        }

        public int binsUsed() {
            int n = 0;
            for (List<String> list : skus.values()) {
                if (!list.isEmpty()) {
                    n++;
                }
            }
            return n;
        }

        public String report() {
            StringBuilder sb = new StringBuilder();
            for (Map.Entry<BinId, List<String>> e : skus.entrySet()) {
                if (e.getValue().isEmpty()) {
                    continue;
                }
                Bin b = bins.get(e.getKey());
                if (sb.length() > 0) {
                    sb.append('\n');
                }
                sb.append(e.getKey()).append(' ').append(b.zone())
                        .append(" vol ").append(volumeUsed.get(e.getKey())).append('/').append(b.volume())
                        .append(" wt ").append(weightUsed.get(e.getKey())).append('/').append(b.weight())
                        .append(": ").append(String.join(", ", e.getValue()));
            }
            return sb.length() == 0 ? "nothing placed" : sb.toString();
        }
    }
''')

PUTAWAY = dd(r'''
    package warehouse;

    import java.util.ArrayList;
    import java.util.HashSet;
    import java.util.List;
    import java.util.Map;
    import java.util.Set;
    import java.util.TreeMap;

    public final class Putaway {
        private static final int HEAVY = 20;
        private static final int HAZ_ITEMS = 2;

        private Putaway() {}

        public static Plan plan(List<Item> items, List<Bin> bins) {
            Map<BinId, Bin> byId = new TreeMap<>();
            for (Bin b : bins) {
                if (byId.put(b.id(), b) != null) {
                    throw new IllegalArgumentException("duplicate bin " + b.id());
                }
            }
            Set<String> seen = new HashSet<>();
            for (Item it : items) {
                if (!seen.add(it.sku())) {
                    throw new IllegalArgumentException("duplicate sku " + it.sku());
                }
            }
            List<Item> order = new ArrayList<>(items);
            order.sort((a, b) -> {
                if (a.volume() != b.volume()) {
                    return Integer.compare(b.volume(), a.volume());
                }
                if (a.weight() != b.weight()) {
                    return Integer.compare(b.weight(), a.weight());
                }
                return a.sku().compareTo(b.sku());
            });

            Plan plan = new Plan(byId);
            for (Item item : order) {
                Bin best = null;
                int bestLeft = 0;
                for (Bin bin : byId.values()) {
                    if (!eligible(plan, item, bin)) {
                        continue;
                    }
                    int left = plan.freeVolume(bin) - item.volume();
                    if (best == null || left < bestLeft) {
                        best = bin;
                        bestLeft = left;
                    }
                }
                if (best == null) {
                    plan.reject(item);
                } else {
                    plan.place(item, best);
                }
            }
            return plan;
        }

        private static boolean eligible(Plan plan, Item item, Bin bin) {
            if (bin.zone() != item.zone()) {
                return false;
            }
            if (plan.freeVolume(bin) < item.volume() || plan.freeWeight(bin) < item.weight()) {
                return false;
            }
            if (item.weight() > HEAVY && bin.id().level() > 2) {
                return false;
            }
            return bin.zone() != Zone.HAZ || plan.itemsIn(bin) < HAZ_ITEMS;
        }
    }
''')

ROUTE = dd(r'''
    package warehouse;

    import java.util.ArrayList;
    import java.util.List;
    import java.util.TreeSet;

    public final class Route {
        private Route() {}

        private static List<List<BinId>> byAisle(List<String> bins) {
            TreeSet<BinId> sorted = new TreeSet<>();
            for (String text : bins) {
                sorted.add(BinId.parse(text));
            }
            List<List<BinId>> groups = new ArrayList<>();
            for (BinId id : sorted) {
                if (groups.isEmpty() || !groups.get(groups.size() - 1).get(0).aisle().equals(id.aisle())) {
                    groups.add(new ArrayList<>());
                }
                groups.get(groups.size() - 1).add(id);
            }
            return groups;
        }

        public static List<String> serpentine(List<String> bins) {
            List<String> out = new ArrayList<>();
            List<List<BinId>> groups = byAisle(bins);
            for (int i = 0; i < groups.size(); i++) {
                List<BinId> group = groups.get(i);
                if (i % 2 == 0) {
                    for (BinId id : group) {
                        out.add(id.toString());
                    }
                } else {
                    int end = group.size();
                    while (end > 0) {
                        int bay = group.get(end - 1).bay();
                        int start = end;
                        while (start > 0 && group.get(start - 1).bay() == bay) {
                            start--;
                        }
                        for (int k = start; k < end; k++) {
                            out.add(group.get(k).toString());
                        }
                        end = start;
                    }
                }
            }
            return out;
        }

        public static List<List<String>> waves(List<String> bins, int maxStops) {
            if (maxStops < 1) {
                throw new IllegalArgumentException("maxStops must be at least 1");
            }
            List<List<String>> waves = new ArrayList<>();
            List<String> current = new ArrayList<>();
            List<List<BinId>> groups = byAisle(bins);
            List<String> route = serpentine(bins);
            int pos = 0;
            for (List<BinId> group : groups) {
                List<String> stops = route.subList(pos, pos + group.size());
                pos += group.size();
                if (stops.size() > maxStops) {
                    if (!current.isEmpty()) {
                        waves.add(current);
                        current = new ArrayList<>();
                    }
                    for (int from = 0; from < stops.size(); from += maxStops) {
                        waves.add(new ArrayList<>(stops.subList(from, Math.min(stops.size(), from + maxStops))));
                    }
                } else if (current.size() + stops.size() > maxStops) {
                    waves.add(current);
                    current = new ArrayList<>(stops);
                } else {
                    current.addAll(stops);
                }
            }
            if (!current.isEmpty()) {
                waves.add(current);
            }
            return waves;
        }
    }
''')

BASIC = dd(r'''
    import java.util.List;
    import warehouse.Bin;
    import warehouse.BinId;
    import warehouse.Item;
    import warehouse.Plan;
    import warehouse.Putaway;
    import warehouse.Route;
    import warehouse.Zone;

    public class BasicTests {
        public static void run() {
            Check.test("location text", () -> {
                Check.eq("B-07-1", BinId.parse("b-7-1").toString());
            });
            Check.test("a single item goes to the only fitting bin", () -> {
                Plan p = Putaway.plan(List.of(new Item("S1", 4, 3, Zone.AMBIENT)),
                        List.of(new Bin("A-01-1", Zone.AMBIENT, 3, 50), new Bin("A-02-1", Zone.AMBIENT, 10, 50)));
                Check.eq("A-02-1", p.binOf("S1"));
            });
            Check.test("serpentine", () -> {
                Check.eq(List.of("A-01-1", "A-02-1", "B-02-1", "B-01-1"), Route.serpentine(List.of("B-1-1", "A-2-1", "B-2-1", "A-1-1")));
            });
        }
    }
''')

FULL = dd(r'''
    import java.util.ArrayList;
    import java.util.Arrays;
    import java.util.List;
    import java.util.Map;
    import warehouse.Bin;
    import warehouse.BinId;
    import warehouse.Item;
    import warehouse.Plan;
    import warehouse.Putaway;
    import warehouse.Route;
    import warehouse.Zone;

    public class FullTests {
        static Plan plan(String bins, String items) {
            List<Bin> bl = new ArrayList<>();
            if (!bins.isEmpty()) {
                for (String t : bins.split(" ")) {
                    String[] p = t.split(":");
                    bl.add(new Bin(p[0], Zone.valueOf(p[1]), Integer.parseInt(p[2]), Integer.parseInt(p[3])));
                }
            }
            List<Item> il = new ArrayList<>();
            if (!items.isEmpty()) {
                for (String t : items.split(" ")) {
                    String[] p = t.split(":");
                    il.add(new Item(p[0], Integer.parseInt(p[1]), Integer.parseInt(p[2]), Zone.valueOf(p[3])));
                }
            }
            return Putaway.plan(il, bl);
        }

        static void check(String bins, String items, String assigned, String unplaced, int used, String stats, String report) {
            Plan p = plan(bins, items);
            String label = bins + " / " + items;
            StringBuilder a = new StringBuilder();
            for (Map.Entry<String, String> e : p.assignments().entrySet()) {
                if (a.length() > 0) {
                    a.append(',');
                }
                a.append(e.getKey()).append('=').append(e.getValue());
            }
            Check.eq(label + " (assignments)", assigned, a.toString());
            Check.eq(label + " (unplaced)", unplaced, String.join(",", p.unplaced()));
            Check.eq(label + " (binsUsed)", used, p.binsUsed());
            StringBuilder s = new StringBuilder();
            if (!bins.isEmpty()) {
                for (String t : bins.split(" ")) {
                    String id = t.split(":")[0];
                    if (s.length() > 0) {
                        s.append(' ');
                    }
                    s.append(id).append(':').append(p.volumeUsed(id)).append(':').append(p.weightUsed(id)).append(':').append(p.fill(id));
                }
            }
            Check.eq(label + " (volume, weight, fill)", stats, s.toString());
            Check.eq(label + " (report)", report, p.report());
            for (Map.Entry<String, String> e : p.assignments().entrySet()) {
                Check.eq(e.getValue(), p.binOf(e.getKey()));
            }
        }

        static String join(List<List<String>> waves) {
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < waves.size(); i++) {
                if (i > 0) {
                    sb.append('|');
                }
                sb.append(String.join(",", waves.get(i)));
            }
            return sb.toString();
        }

        static void route(String bins, String serpentine, Object... maxAndWaves) {
            List<String> list = bins.isEmpty() ? new ArrayList<>() : Arrays.asList(bins.split(","));
            Check.eq(bins + " (serpentine)", serpentine, String.join(",", Route.serpentine(list)));
            for (int i = 0; i < maxAndWaves.length; i += 2) {
                int max = (Integer) maxAndWaves[i];
                Check.eq(bins + " (waves of " + max + ")", maxAndWaves[i + 1], join(Route.waves(list, max)));
            }
        }

        public static void run() {
            Check.test("BinId.parse and toString", () -> {
                BinId a = BinId.parse("A-03-2");
                Check.eq("A", a.aisle());
                Check.eq(3, a.bay());
                Check.eq(2, a.level());
                Check.eq("A-03-2", a.toString());
                Check.eq("B-07-1", BinId.parse(" b-7-1 ").toString());
                Check.eq("AB-123-12", BinId.parse("ab-123-12").toString());
                Check.eq("C-01-1", BinId.parse("c-1-1").toString());
                Check.eq("D-100-10", BinId.parse("D-100-10").toString());
                Check.eq("E-10-3", BinId.parse("E-010-03").toString());
                Check.eq("AB", BinId.parse("aB-5-5").aisle());
                Check.eq(123, BinId.parse("A-123-1").bay());
                Check.eq(12, BinId.parse("A-1-12").level());
                Check.eq(5, BinId.parse("\tA-5-5\n").bay());
            });

            Check.test("BinId.parse rejects bad text", () -> {
                String[] bad = {
                    "", "A", "A-1", "A-1-1-1", "ABC-1-1", "1-1-1", "A-0-1", "A-1-0", "A-1000-1", "A-1-100", "A--1", "A-x-1", "A-1-x", "-1-1",
                    "A-1- 1", "A- 1-1", "A-+1-1", "A_1_1", "A-1-1x", "A-1.5-1", "A-0001-1", "A-000-1", "A-1-00", "AA1-1-1", "A -1-1", "-A-1-1", "A-1-1-",
                };
                for (String text : bad) {
                    Check.raises(IllegalArgumentException.class, () -> BinId.parse(text));
                }
            });

            Check.test("BinId order and equality", () -> {
                Check.yes(BinId.parse("Z-01-1").compareTo(BinId.parse("AA-01-1")) < 0, "Z before AA");
                Check.yes(BinId.parse("AA-01-1").compareTo(BinId.parse("Z-01-1")) > 0, "AA after Z");
                Check.yes(BinId.parse("A-02-1").compareTo(BinId.parse("A-10-1")) < 0, "bay 2 before bay 10");
                Check.yes(BinId.parse("A-01-2").compareTo(BinId.parse("A-01-10")) < 0, "level 2 before level 10");
                Check.yes(BinId.parse("A-09-9").compareTo(BinId.parse("B-01-1")) < 0, "aisle first");
                Check.yes(BinId.parse("A-02-9").compareTo(BinId.parse("A-03-1")) < 0, "bay before level");
                Check.yes(BinId.parse("AB-01-1").compareTo(BinId.parse("AC-01-1")) < 0, "AB before AC");
                Check.yes(BinId.parse("AZ-01-1").compareTo(BinId.parse("B-01-1")) > 0, "two letters after one");
                Check.eq(0, BinId.parse("A-1-1").compareTo(BinId.parse("a-01-1")));
                Check.yes(BinId.parse("A-1-1").equals(BinId.parse("a-01-1")), "equal");
                Check.yes(!BinId.parse("A-1-1").equals(BinId.parse("A-1-2")), "levels differ");
                Check.yes(!BinId.parse("A-1-1").equals(BinId.parse("A-2-1")), "bays differ");
                Check.yes(!BinId.parse("A-1-1").equals(BinId.parse("B-1-1")), "aisles differ");
                Check.eq(BinId.parse("A-1-1").hashCode(), BinId.parse("a-01-1").hashCode());
            });

            Check.test("Item and Bin are validated", () -> {
                Check.raises(IllegalArgumentException.class, () -> new Item("", 1, 1, Zone.AMBIENT));
                Check.raises(IllegalArgumentException.class, () -> new Item("  ", 1, 1, Zone.AMBIENT));
                Check.raises(IllegalArgumentException.class, () -> new Item("S", 0, 1, Zone.AMBIENT));
                Check.raises(IllegalArgumentException.class, () -> new Item("S", 1, -1, Zone.AMBIENT));
                Check.eq("S1", new Item(" S1 ", 1, 0, Zone.COLD).sku());
                Check.eq(4, new Item("S", 4, 5, Zone.HAZ).volume());
                Check.eq(5, new Item("S", 4, 5, Zone.HAZ).weight());
                Check.eq(Zone.HAZ, new Item("S", 4, 5, Zone.HAZ).zone());
                Check.raises(IllegalArgumentException.class, () -> new Bin("A-1-1", Zone.AMBIENT, 0, 1));
                Check.raises(IllegalArgumentException.class, () -> new Bin("A-1-1", Zone.AMBIENT, 1, -1));
                Check.raises(IllegalArgumentException.class, () -> new Bin("A-0-1", Zone.AMBIENT, 1, 1));
                Bin b = new Bin("b-2-1", Zone.COLD, 7, 0);
                Check.eq(BinId.parse("B-02-1"), b.id());
                Check.eq(Zone.COLD, b.zone());
                Check.eq(7, b.volume());
                Check.eq(0, b.weight());
            });

            Check.test("duplicates are rejected", () -> {
                Check.raises(IllegalArgumentException.class, () -> plan("A-01-1:AMBIENT:5:5", "S1:1:1:AMBIENT S1:2:2:AMBIENT"));
                Check.raises(IllegalArgumentException.class, () -> plan("A-01-1:AMBIENT:5:5 a-1-1:COLD:5:5", "S1:1:1:AMBIENT"));
                Check.raises(IllegalArgumentException.class, () -> Putaway.plan(
                        List.of(new Item("S1", 1, 1, Zone.AMBIENT), new Item(" S1", 1, 1, Zone.AMBIENT)), List.of(new Bin("A-1-1", Zone.AMBIENT, 5, 5))));
                plan("A-01-1:AMBIENT:5:5 A-01-2:AMBIENT:5:5", "S1:1:1:AMBIENT s1:1:1:AMBIENT");
            });

            Check.test("best fit: the bin left with the least free volume", () -> {
                check("A-01-1:AMBIENT:10:100 A-02-1:AMBIENT:6:100 A-03-1:AMBIENT:8:100",
                        "S1:5:1:AMBIENT",
                        "S1=A-02-1", "", 1,
                        "A-01-1:0:0:0 A-02-1:5:1:83 A-03-1:0:0:0",
                        "A-02-1 AMBIENT vol 5/6 wt 1/100: S1");
                check("A-01-1:AMBIENT:10:100 A-02-1:AMBIENT:6:100 A-03-1:AMBIENT:8:100",
                        "S1:5:1:AMBIENT S2:5:1:AMBIENT S3:5:1:AMBIENT",
                        "S1=A-02-1,S2=A-03-1,S3=A-01-1", "", 3,
                        "A-01-1:5:1:50 A-02-1:5:1:83 A-03-1:5:1:62",
                        "A-01-1 AMBIENT vol 5/10 wt 1/100: S3\nA-02-1 AMBIENT vol 5/6 wt 1/100: S1\nA-03-1 AMBIENT vol 5/8 wt 1/100: S2");
                check("A-01-1:AMBIENT:10:100 A-02-1:AMBIENT:10:100",
                        "S1:4:1:AMBIENT S2:3:1:AMBIENT S3:3:1:AMBIENT",
                        "S1=A-01-1,S2=A-01-1,S3=A-01-1", "", 1,
                        "A-01-1:10:3:100 A-02-1:0:0:0",
                        "A-01-1 AMBIENT vol 10/10 wt 3/100: S1, S2, S3");
                check("A-01-1:AMBIENT:5:100 A-01-2:AMBIENT:5:100",
                        "S1:5:1:AMBIENT S2:5:1:AMBIENT S3:1:1:AMBIENT",
                        "S1=A-01-1,S2=A-01-2", "S3", 2,
                        "A-01-1:5:1:100 A-01-2:5:1:100",
                        "A-01-1 AMBIENT vol 5/5 wt 1/100: S1\nA-01-2 AMBIENT vol 5/5 wt 1/100: S2");
            });

            Check.test("ties go to the lower location, in natural order", () -> {
                check("A-10-1:AMBIENT:9:99 A-02-1:AMBIENT:9:99",
                        "S1:4:1:AMBIENT",
                        "S1=A-02-1", "", 1,
                        "A-10-1:0:0:0 A-02-1:4:1:44",
                        "A-02-1 AMBIENT vol 4/9 wt 1/99: S1");
                check("A-01-10:AMBIENT:9:99 A-01-2:AMBIENT:9:99",
                        "S1:4:1:AMBIENT",
                        "S1=A-01-2", "", 1,
                        "A-01-10:0:0:0 A-01-2:4:1:44",
                        "A-01-2 AMBIENT vol 4/9 wt 1/99: S1");
                check("AA-01-1:AMBIENT:9:99 Z-01-1:AMBIENT:9:99 B-01-1:AMBIENT:9:99",
                        "S1:4:1:AMBIENT S2:9:1:AMBIENT",
                        "S2=B-01-1,S1=Z-01-1", "", 2,
                        "AA-01-1:0:0:0 Z-01-1:4:1:44 B-01-1:9:1:100",
                        "B-01-1 AMBIENT vol 9/9 wt 1/99: S2\nZ-01-1 AMBIENT vol 4/9 wt 1/99: S1");
                check("b-03-1:AMBIENT:9:99 B-04-1:AMBIENT:9:99",
                        "S1:4:1:AMBIENT",
                        "S1=B-03-1", "", 1,
                        "b-03-1:4:1:44 B-04-1:0:0:0",
                        "B-03-1 AMBIENT vol 4/9 wt 1/99: S1");
            });

            Check.test("items go in order: volume, weight, sku", () -> {
                check("A-01-1:AMBIENT:10:100",
                        "S1:3:5:AMBIENT S2:4:1:AMBIENT S3:3:9:AMBIENT S4:3:9:AMBIENT",
                        "S2=A-01-1,S3=A-01-1,S4=A-01-1", "S1", 1,
                        "A-01-1:10:19:100",
                        "A-01-1 AMBIENT vol 10/10 wt 19/100: S2, S3, S4");
                check("A-01-1:AMBIENT:6:100",
                        "S9:3:2:AMBIENT S10:3:2:AMBIENT S2:3:2:AMBIENT",
                        "S10=A-01-1,S2=A-01-1", "S9", 1,
                        "A-01-1:6:4:100",
                        "A-01-1 AMBIENT vol 6/6 wt 4/100: S10, S2");
                check("A-01-1:AMBIENT:6:100",
                        "b:3:2:AMBIENT B:3:2:AMBIENT a:3:2:AMBIENT",
                        "B=A-01-1,a=A-01-1", "b", 1,
                        "A-01-1:6:4:100",
                        "A-01-1 AMBIENT vol 6/6 wt 4/100: B, a");
                check("A-01-1:AMBIENT:7:100 A-02-1:AMBIENT:3:100",
                        "X:3:1:AMBIENT Y:7:1:AMBIENT Z:3:2:AMBIENT",
                        "Y=A-01-1,Z=A-02-1", "X", 2,
                        "A-01-1:7:1:100 A-02-1:3:2:100",
                        "A-01-1 AMBIENT vol 7/7 wt 1/100: Y\nA-02-1 AMBIENT vol 3/3 wt 2/100: Z");
            });

            Check.test("zones must match", () -> {
                check("A-01-1:AMBIENT:9:99 B-01-1:COLD:9:99 C-01-1:HAZ:9:99",
                        "a:2:1:AMBIENT c:2:1:COLD h:2:1:HAZ",
                        "a=A-01-1,c=B-01-1,h=C-01-1", "", 3,
                        "A-01-1:2:1:22 B-01-1:2:1:22 C-01-1:2:1:22",
                        "A-01-1 AMBIENT vol 2/9 wt 1/99: a\nB-01-1 COLD vol 2/9 wt 1/99: c\nC-01-1 HAZ vol 2/9 wt 1/99: h");
                check("A-01-1:AMBIENT:9:99 B-01-1:COLD:3:99",
                        "c1:2:1:COLD c2:2:1:COLD a1:2:1:AMBIENT",
                        "a1=A-01-1,c1=B-01-1", "c2", 2,
                        "A-01-1:2:1:22 B-01-1:2:1:66",
                        "A-01-1 AMBIENT vol 2/9 wt 1/99: a1\nB-01-1 COLD vol 2/3 wt 1/99: c1");
                check("A-01-1:COLD:9:99",
                        "a:2:1:AMBIENT h:2:1:HAZ",
                        "", "a,h", 0,
                        "A-01-1:0:0:0",
                        "nothing placed");
            });

            Check.test("exact fits and capacity limits", () -> {
                check("A-01-1:AMBIENT:10:10",
                        "S1:10:10:AMBIENT",
                        "S1=A-01-1", "", 1,
                        "A-01-1:10:10:100",
                        "A-01-1 AMBIENT vol 10/10 wt 10/10: S1");
                check("A-01-1:AMBIENT:10:10",
                        "S1:11:1:AMBIENT S2:1:11:AMBIENT S3:5:5:AMBIENT S4:5:5:AMBIENT S5:1:0:AMBIENT",
                        "S3=A-01-1,S4=A-01-1", "S1,S2,S5", 1,
                        "A-01-1:10:10:100",
                        "A-01-1 AMBIENT vol 10/10 wt 10/10: S3, S4");
                check("A-01-1:AMBIENT:10:30 A-02-1:AMBIENT:10:15",
                        "S1:4:8:AMBIENT S2:4:8:AMBIENT S3:4:8:AMBIENT",
                        "S1=A-01-1,S2=A-01-1,S3=A-02-1", "", 2,
                        "A-01-1:8:16:80 A-02-1:4:8:40",
                        "A-01-1 AMBIENT vol 8/10 wt 16/30: S1, S2\nA-02-1 AMBIENT vol 4/10 wt 8/15: S3");
                check("A-01-1:AMBIENT:4:0",
                        "S1:2:0:AMBIENT S2:2:0:AMBIENT S3:1:0:AMBIENT",
                        "S1=A-01-1,S2=A-01-1", "S3", 1,
                        "A-01-1:4:0:100",
                        "A-01-1 AMBIENT vol 4/4 wt 0/0: S1, S2");
            });

            Check.test("heavy items stay on the lower levels", () -> {
                check("A-01-3:AMBIENT:5:99 A-02-2:AMBIENT:9:99",
                        "S1:3:21:AMBIENT",
                        "S1=A-02-2", "", 1,
                        "A-01-3:0:0:0 A-02-2:3:21:33",
                        "A-02-2 AMBIENT vol 3/9 wt 21/99: S1");
                check("A-01-3:AMBIENT:5:99 A-02-2:AMBIENT:9:99",
                        "S1:3:20:AMBIENT",
                        "S1=A-01-3", "", 1,
                        "A-01-3:3:20:60 A-02-2:0:0:0",
                        "A-01-3 AMBIENT vol 3/5 wt 20/99: S1");
                check("A-01-3:AMBIENT:5:99 A-02-1:AMBIENT:9:99",
                        "S1:3:21:AMBIENT S2:3:22:AMBIENT",
                        "S2=A-02-1,S1=A-02-1", "", 1,
                        "A-01-3:0:0:0 A-02-1:6:43:66",
                        "A-02-1 AMBIENT vol 6/9 wt 43/99: S2, S1");
                check("A-01-3:AMBIENT:5:99 A-01-4:AMBIENT:5:99",
                        "S1:3:21:AMBIENT S2:3:1:AMBIENT",
                        "S2=A-01-3", "S1", 1,
                        "A-01-3:3:1:60 A-01-4:0:0:0",
                        "A-01-3 AMBIENT vol 3/5 wt 1/99: S2");
                check("A-01-2:AMBIENT:5:99 A-01-1:AMBIENT:5:99",
                        "S1:3:50:AMBIENT S2:2:50:AMBIENT",
                        "S1=A-01-1,S2=A-01-2", "", 2,
                        "A-01-2:2:50:40 A-01-1:3:50:60",
                        "A-01-1 AMBIENT vol 3/5 wt 50/99: S1\nA-01-2 AMBIENT vol 2/5 wt 50/99: S2");
            });

            Check.test("hazardous bins hold two items", () -> {
                check("H-01-1:HAZ:20:99",
                        "h1:2:1:HAZ h2:2:1:HAZ h3:2:1:HAZ",
                        "h1=H-01-1,h2=H-01-1", "h3", 1,
                        "H-01-1:4:2:20",
                        "H-01-1 HAZ vol 4/20 wt 2/99: h1, h2");
                check("H-01-1:HAZ:20:99 H-02-1:HAZ:20:99",
                        "h1:2:1:HAZ h2:2:1:HAZ h3:2:1:HAZ h4:2:1:HAZ h5:2:1:HAZ",
                        "h1=H-01-1,h2=H-01-1,h3=H-02-1,h4=H-02-1", "h5", 2,
                        "H-01-1:4:2:20 H-02-1:4:2:20",
                        "H-01-1 HAZ vol 4/20 wt 2/99: h1, h2\nH-02-1 HAZ vol 4/20 wt 2/99: h3, h4");
                check("A-01-1:AMBIENT:20:99",
                        "a1:1:1:AMBIENT a2:1:1:AMBIENT a3:1:1:AMBIENT a4:1:1:AMBIENT",
                        "a1=A-01-1,a2=A-01-1,a3=A-01-1,a4=A-01-1", "", 1,
                        "A-01-1:4:4:20",
                        "A-01-1 AMBIENT vol 4/20 wt 4/99: a1, a2, a3, a4");
                check("H-01-1:HAZ:5:99 H-01-2:HAZ:20:99",
                        "h1:5:1:HAZ h2:4:1:HAZ h3:3:1:HAZ",
                        "h1=H-01-1,h2=H-01-2,h3=H-01-2", "", 2,
                        "H-01-1:5:1:100 H-01-2:7:2:35",
                        "H-01-1 HAZ vol 5/5 wt 1/99: h1\nH-01-2 HAZ vol 7/20 wt 2/99: h2, h3");
            });

            Check.test("items that do not fit stay unplaced", () -> {
                check("A-01-1:AMBIENT:5:99",
                        "S1:9:1:AMBIENT S2:4:1:AMBIENT S3:3:1:AMBIENT S4:1:1:AMBIENT",
                        "S2=A-01-1,S4=A-01-1", "S1,S3", 1,
                        "A-01-1:5:2:100",
                        "A-01-1 AMBIENT vol 5/5 wt 2/99: S2, S4");
                check("",
                        "S1:1:1:AMBIENT",
                        "", "S1", 0,
                        "",
                        "nothing placed");
                check("A-01-1:AMBIENT:5:99",
                        "",
                        "", "", 0,
                        "A-01-1:0:0:0",
                        "nothing placed");
                check("",
                        "",
                        "", "", 0,
                        "",
                        "nothing placed");
                check("A-01-1:COLD:5:99",
                        "S1:1:1:AMBIENT",
                        "", "S1", 0,
                        "A-01-1:0:0:0",
                        "nothing placed");
            });

            Check.test("used volume, weight and fill", () -> {
                check("A-01-1:AMBIENT:3:99 A-02-1:AMBIENT:7:99 A-03-1:AMBIENT:200:99 A-04-1:AMBIENT:8:99",
                        "S1:2:1:AMBIENT S2:1:1:AMBIENT S3:5:1:AMBIENT S4:1:1:AMBIENT S5:7:1:AMBIENT",
                        "S5=A-02-1,S3=A-04-1,S1=A-01-1,S2=A-01-1,S4=A-04-1", "", 3,
                        "A-01-1:3:2:100 A-02-1:7:1:100 A-03-1:0:0:0 A-04-1:6:2:75",
                        "A-01-1 AMBIENT vol 3/3 wt 2/99: S1, S2\nA-02-1 AMBIENT vol 7/7 wt 1/99: S5\nA-04-1 AMBIENT vol 6/8 wt 2/99: S3, S4");
                check("a-1-1:AMBIENT:3:99 B-02-2:COLD:9:99",
                        "S1:2:1:AMBIENT S2:5:1:COLD",
                        "S2=B-02-2,S1=A-01-1", "", 2,
                        "a-1-1:2:1:66 B-02-2:5:1:55",
                        "A-01-1 AMBIENT vol 2/3 wt 1/99: S1\nB-02-2 COLD vol 5/9 wt 1/99: S2");
            });

            Check.test("plan lookups take any spelling of a location", () -> {
                Plan p = plan("A-01-1:AMBIENT:10:50 B-02-2:COLD:8:20", "S1:3:4:AMBIENT S2:2:5:COLD");
                Check.eq(3, p.volumeUsed("a-1-1"));
                Check.eq(4, p.weightUsed(" A-001-1 "));
                Check.eq(30, p.fill("A-1-1"));
                Check.eq(25, p.fill("b-02-02"));
                Check.eq("A-01-1", p.binOf("S1"));
                Check.eq("B-02-2", p.binOf("S2"));
                Check.eq(null, p.binOf("S3"));
                Check.raises(IllegalArgumentException.class, () -> p.volumeUsed("C-1-1"));
                Check.raises(IllegalArgumentException.class, () -> p.weightUsed("C-1-1"));
                Check.raises(IllegalArgumentException.class, () -> p.fill("C-1-1"));
                Check.raises(IllegalArgumentException.class, () -> p.fill("nonsense"));
                Check.eq(2, p.binsUsed());
            });

            Check.test("assignments keep placement order", () -> {
                Plan p = plan("A-01-1:AMBIENT:22:99", "S1:1:1:AMBIENT S2:9:1:AMBIENT S3:5:1:AMBIENT S4:7:1:AMBIENT");
                Check.eq(List.of("S2", "S4", "S3", "S1"), new ArrayList<>(p.assignments().keySet()));
                Check.eq(4, p.assignments().size());
                Check.eq(List.of(), p.unplaced());
            });

            Check.test("report format", () -> {
                Plan p = plan("A-01-1:AMBIENT:10:50 B-01-1:COLD:5:5 C-01-1:HAZ:5:5", "X:4:10:AMBIENT Y:3:5:AMBIENT");
                Check.eq("A-01-1 AMBIENT vol 7/10 wt 15/50: X, Y", p.report());
                Check.eq(1, p.binsUsed());
                Check.eq("nothing placed", plan("A-01-1:AMBIENT:10:50", "").report());
                Check.eq("nothing placed", plan("", "").report());
                Check.eq(0, plan("A-01-1:AMBIENT:10:50", "").binsUsed());
            });

            Check.test("mixed warehouses 1", () -> {
                check("C-03-2:AMBIENT:10:20 C-10-3:COLD:10:50 A-01-2:HAZ:10:30 B-10-2:AMBIENT:6:50 B-10-1:AMBIENT:12:20",
                        "S1:3:10:AMBIENT S5:8:5:AMBIENT S16:7:10:AMBIENT S4:4:5:HAZ S8:4:21:AMBIENT S12:9:21:AMBIENT S9:6:15:AMBIENT S20:6:15:HAZ",
                        "S5=C-03-2,S16=B-10-1,S20=A-01-2,S9=B-10-2,S4=A-01-2,S1=B-10-1", "S12,S8", 4,
                        "C-03-2:8:5:80 C-10-3:0:0:0 A-01-2:10:20:100 B-10-2:6:15:100 B-10-1:10:20:83",
                        "A-01-2 HAZ vol 10/10 wt 20/30: S20, S4\nB-10-1 AMBIENT vol 10/12 wt 20/20: S16, S1\nB-10-2 AMBIENT vol 6/6 wt 15/50: S9\nC-03-2 AMBIENT vol 8/10 wt 5/20: S5");
                check("C-03-3:COLD:15:30 B-03-2:HAZ:12:50 B-10-1:HAZ:15:20 C-01-3:COLD:6:50 A-02-2:AMBIENT:10:20 C-10-2:AMBIENT:20:30",
                        "S19:6:1:AMBIENT S9:1:20:HAZ S18:6:20:AMBIENT S14:4:10:COLD S7:4:25:AMBIENT S8:2:25:COLD S3:2:30:AMBIENT S16:3:15:COLD S10:7:21:AMBIENT S12:6:1:HAZ S11:5:30:AMBIENT S2:7:10:AMBIENT",
                        "S10=C-10-2,S2=A-02-2,S12=B-03-2,S19=C-10-2,S14=C-01-3,S16=C-03-3,S9=B-03-2", "S18,S11,S7,S3,S8", 5,
                        "C-03-3:3:15:20 B-03-2:7:21:58 B-10-1:0:0:0 C-01-3:4:10:66 A-02-2:7:10:70 C-10-2:13:22:65",
                        "A-02-2 AMBIENT vol 7/10 wt 10/20: S2\nB-03-2 HAZ vol 7/12 wt 21/50: S12, S9\nC-01-3 COLD vol 4/6 wt 10/50: S14\nC-03-3 COLD vol 3/15 wt 15/30: S16\nC-10-2 AMBIENT vol 13/20 wt 22/30: S10, S19");
                check("C-02-3:AMBIENT:12:20 C-10-1:AMBIENT:15:50 A-10-2:HAZ:20:20 A-10-1:HAZ:6:20",
                        "S1:8:10:HAZ S17:2:25:AMBIENT S6:8:15:AMBIENT S13:7:5:AMBIENT S4:8:25:HAZ S19:3:5:HAZ S15:7:30:COLD S10:2:10:COLD",
                        "S6=C-02-3,S1=A-10-2,S13=C-10-1,S19=A-10-1,S17=C-10-1", "S4,S15,S10", 4,
                        "C-02-3:8:15:66 C-10-1:9:30:60 A-10-2:8:10:40 A-10-1:3:5:50",
                        "A-10-1 HAZ vol 3/6 wt 5/20: S19\nA-10-2 HAZ vol 8/20 wt 10/20: S1\nC-02-3 AMBIENT vol 8/12 wt 15/20: S6\nC-10-1 AMBIENT vol 9/15 wt 30/50: S13, S17");
                check("B-03-1:AMBIENT:12:50 B-10-2:AMBIENT:6:20 A-02-3:HAZ:6:30 B-10-3:AMBIENT:15:80 A-10-2:HAZ:15:30 A-10-1:AMBIENT:12:50 C-10-3:COLD:6:20",
                        "S8:6:20:COLD S13:3:25:HAZ S4:7:30:COLD S5:3:1:AMBIENT S1:6:10:AMBIENT S2:9:20:AMBIENT S17:8:10:AMBIENT",
                        "S2=A-10-1,S17=B-03-1,S8=C-10-3,S1=B-10-2,S13=A-10-2,S5=A-10-1", "S4", 5,
                        "B-03-1:8:10:66 B-10-2:6:10:100 A-02-3:0:0:0 B-10-3:0:0:0 A-10-2:3:25:20 A-10-1:12:21:100 C-10-3:6:20:100",
                        "A-10-1 AMBIENT vol 12/12 wt 21/50: S2, S5\nA-10-2 HAZ vol 3/15 wt 25/30: S13\nB-03-1 AMBIENT vol 8/12 wt 10/50: S17\nB-10-2 AMBIENT vol 6/6 wt 10/20: S1\nC-10-3 COLD vol 6/6 wt 20/20: S8");
            });

            Check.test("mixed warehouses 2", () -> {
                check("C-10-2:HAZ:15:20 C-02-2:COLD:12:80 B-01-1:AMBIENT:10:30 C-01-3:AMBIENT:15:50 B-02-2:COLD:20:50",
                        "S20:2:10:AMBIENT S15:9:5:HAZ S3:7:20:AMBIENT S6:3:21:HAZ S17:2:20:AMBIENT S7:7:30:AMBIENT S12:7:10:AMBIENT S13:3:21:AMBIENT S4:1:30:AMBIENT S2:9:1:AMBIENT",
                        "S15=C-10-2,S2=B-01-1,S3=C-01-3,S12=C-01-3", "S7,S13,S6,S17,S20,S4", 3,
                        "C-10-2:9:5:60 C-02-2:0:0:0 B-01-1:9:1:90 C-01-3:14:30:93 B-02-2:0:0:0",
                        "B-01-1 AMBIENT vol 9/10 wt 1/30: S2\nC-01-3 AMBIENT vol 14/15 wt 30/50: S3, S12\nC-10-2 HAZ vol 9/15 wt 5/20: S15");
                check("B-02-1:COLD:12:80 C-02-1:HAZ:20:80 B-01-1:AMBIENT:6:20 C-10-3:AMBIENT:20:20 B-02-3:HAZ:12:30 B-10-1:AMBIENT:15:30 A-02-2:HAZ:10:30 A-03-1:AMBIENT:6:80",
                        "S14:3:21:AMBIENT S13:1:10:AMBIENT S17:6:15:AMBIENT S12:5:1:HAZ S19:1:25:AMBIENT S4:6:15:AMBIENT S6:1:5:COLD S7:7:15:HAZ S10:2:25:AMBIENT",
                        "S7=A-02-2,S17=A-03-1,S4=B-01-1,S12=B-02-3,S14=B-10-1,S13=C-10-3,S6=B-02-1", "S10,S19", 7,
                        "B-02-1:1:5:8 C-02-1:0:0:0 B-01-1:6:15:100 C-10-3:1:10:5 B-02-3:5:1:41 B-10-1:3:21:20 A-02-2:7:15:70 A-03-1:6:15:100",
                        "A-02-2 HAZ vol 7/10 wt 15/30: S7\nA-03-1 AMBIENT vol 6/6 wt 15/80: S17\nB-01-1 AMBIENT vol 6/6 wt 15/20: S4\nB-02-1 COLD vol 1/12 wt 5/80: S6\nB-02-3 HAZ vol 5/12 wt 1/30: S12\nB-10-1 AMBIENT vol 3/15 wt 21/30: S14\nC-10-3 AMBIENT vol 1/20 wt 10/20: S13");
                check("A-01-3:AMBIENT:20:30 C-10-1:AMBIENT:8:30 C-02-3:COLD:20:80 B-01-1:AMBIENT:15:80 A-01-1:COLD:10:80 C-01-2:HAZ:8:50",
                        "S18:6:5:HAZ S5:9:10:AMBIENT S8:7:5:AMBIENT S3:4:15:AMBIENT S1:7:21:COLD S6:9:20:COLD S7:3:21:COLD S11:5:30:AMBIENT",
                        "S6=A-01-1,S5=B-01-1,S8=C-10-1,S18=C-01-2,S11=B-01-1,S3=A-01-3", "S1,S7", 5,
                        "A-01-3:4:15:20 C-10-1:7:5:87 C-02-3:0:0:0 B-01-1:14:40:93 A-01-1:9:20:90 C-01-2:6:5:75",
                        "A-01-1 COLD vol 9/10 wt 20/80: S6\nA-01-3 AMBIENT vol 4/20 wt 15/30: S3\nB-01-1 AMBIENT vol 14/15 wt 40/80: S5, S11\nC-01-2 HAZ vol 6/8 wt 5/50: S18\nC-10-1 AMBIENT vol 7/8 wt 5/30: S8");
                check("B-01-2:HAZ:10:30 B-02-1:COLD:15:80 A-03-2:AMBIENT:8:50 A-02-1:COLD:12:30 C-02-3:HAZ:15:30 C-03-1:AMBIENT:12:50 B-10-2:AMBIENT:6:80 A-01-2:COLD:6:30",
                        "S1:2:10:AMBIENT S3:7:25:AMBIENT S11:5:30:AMBIENT S7:6:15:HAZ S15:2:5:COLD S8:7:10:AMBIENT S13:9:10:AMBIENT S19:5:20:AMBIENT S5:1:20:HAZ S9:6:10:HAZ S12:8:1:AMBIENT",
                        "S13=C-03-1,S12=A-03-2,S7=B-01-2,S9=C-02-3,S11=B-10-2,S1=C-03-1,S15=A-01-2,S5=C-02-3", "S3,S8,S19", 6,
                        "B-01-2:6:15:60 B-02-1:0:0:0 A-03-2:8:1:100 A-02-1:0:0:0 C-02-3:7:30:46 C-03-1:11:20:91 B-10-2:5:30:83 A-01-2:2:5:33",
                        "A-01-2 COLD vol 2/6 wt 5/30: S15\nA-03-2 AMBIENT vol 8/8 wt 1/50: S12\nB-01-2 HAZ vol 6/10 wt 15/30: S7\nB-10-2 AMBIENT vol 5/6 wt 30/80: S11\nC-02-3 HAZ vol 7/15 wt 30/30: S9, S5\nC-03-1 AMBIENT vol 11/12 wt 20/50: S13, S1");
            });

            Check.test("mixed warehouses 3", () -> {
                check("C-02-3:AMBIENT:10:30 C-01-1:HAZ:8:80 B-02-3:AMBIENT:8:80 C-10-2:HAZ:12:50 A-02-2:HAZ:6:20 B-01-1:AMBIENT:12:80 B-10-3:COLD:8:20 B-03-3:AMBIENT:10:50",
                        "S9:3:20:COLD S10:9:15:AMBIENT S11:2:21:AMBIENT S1:9:1:HAZ S5:5:15:AMBIENT S16:9:21:AMBIENT S20:1:5:AMBIENT",
                        "S16=B-01-1,S10=B-03-3,S1=C-10-2,S5=B-02-3,S9=B-10-3,S11=B-01-1,S20=B-01-1", "", 5,
                        "C-02-3:0:0:0 C-01-1:0:0:0 B-02-3:5:15:62 C-10-2:9:1:75 A-02-2:0:0:0 B-01-1:12:47:100 B-10-3:3:20:37 B-03-3:9:15:90",
                        "B-01-1 AMBIENT vol 12/12 wt 47/80: S16, S11, S20\nB-02-3 AMBIENT vol 5/8 wt 15/80: S5\nB-03-3 AMBIENT vol 9/10 wt 15/50: S10\nB-10-3 COLD vol 3/8 wt 20/20: S9\nC-10-2 HAZ vol 9/12 wt 1/50: S1");
            });

            Check.test("serpentine routes and waves", () -> {
                route("A-1-1,A-2-1,B-1-1,B-3-2,B-3-1,C-4-1,c-1-1", "A-01-1,A-02-1,B-03-1,B-03-2,B-01-1,C-01-1,C-04-1",
                        3, "A-01-1,A-02-1|B-03-1,B-03-2,B-01-1|C-01-1,C-04-1", 2, "A-01-1,A-02-1|B-03-1,B-03-2|B-01-1|C-01-1,C-04-1", 10, "A-01-1,A-02-1,B-03-1,B-03-2,B-01-1,C-01-1,C-04-1");
                route("B-5-1,B-1-1,D-2-1,D-9-3,D-9-1,F-1-1,F-2-1,F-3-1", "B-01-1,B-05-1,D-09-1,D-09-3,D-02-1,F-01-1,F-02-1,F-03-1",
                        4, "B-01-1,B-05-1|D-09-1,D-09-3,D-02-1|F-01-1,F-02-1,F-03-1", 3, "B-01-1,B-05-1|D-09-1,D-09-3,D-02-1|F-01-1,F-02-1,F-03-1", 1, "B-01-1|B-05-1|D-09-1|D-09-3|D-02-1|F-01-1|F-02-1|F-03-1");
                route("A-1-1", "A-01-1",
                        1, "A-01-1", 5, "A-01-1");
                route("Z-05-1,AA-03-1,AA-01-1,Z-01-2,Z-01-1,AB-02-1", "Z-01-1,Z-01-2,Z-05-1,AA-03-1,AA-01-1,AB-02-1",
                        2, "Z-01-1,Z-01-2|Z-05-1|AA-03-1,AA-01-1|AB-02-1", 3, "Z-01-1,Z-01-2,Z-05-1|AA-03-1,AA-01-1,AB-02-1", 100, "Z-01-1,Z-01-2,Z-05-1,AA-03-1,AA-01-1,AB-02-1");
                route("A-1-1,A-1-1,a-01-1,A-2-1", "A-01-1,A-02-1",
                        5, "A-01-1,A-02-1", 1, "A-01-1|A-02-1");
            });

            Check.test("more routes and waves", () -> {
                route("C-1-1,A-3-1,B-2-1", "A-03-1,B-02-1,C-01-1",
                        1, "A-03-1|B-02-1|C-01-1", 2, "A-03-1,B-02-1|C-01-1");
                route("A-1-1,A-2-1,A-3-1,B-1-1,C-1-1,C-2-1,C-3-1,C-4-1,C-5-1,D-1-1,E-1-1,E-2-1", "A-01-1,A-02-1,A-03-1,B-01-1,C-01-1,C-02-1,C-03-1,C-04-1,C-05-1,D-01-1,E-01-1,E-02-1",
                        2, "A-01-1,A-02-1|A-03-1|B-01-1|C-01-1,C-02-1|C-03-1,C-04-1|C-05-1|D-01-1|E-01-1,E-02-1", 3, "A-01-1,A-02-1,A-03-1|B-01-1|C-01-1,C-02-1,C-03-1|C-04-1,C-05-1|D-01-1,E-01-1,E-02-1", 4, "A-01-1,A-02-1,A-03-1,B-01-1|C-01-1,C-02-1,C-03-1,C-04-1|C-05-1|D-01-1,E-01-1,E-02-1", 5, "A-01-1,A-02-1,A-03-1,B-01-1|C-01-1,C-02-1,C-03-1,C-04-1,C-05-1|D-01-1,E-01-1,E-02-1");
                route("A-01-3,A-01-1,A-01-2,B-01-3,B-01-1,B-01-2,C-02-1,C-01-1", "A-01-1,A-01-2,A-01-3,B-01-1,B-01-2,B-01-3,C-01-1,C-02-1",
                        3, "A-01-1,A-01-2,A-01-3|B-01-1,B-01-2,B-01-3|C-01-1,C-02-1", 4, "A-01-1,A-01-2,A-01-3|B-01-1,B-01-2,B-01-3|C-01-1,C-02-1", 5, "A-01-1,A-01-2,A-01-3|B-01-1,B-01-2,B-01-3,C-01-1,C-02-1");
                route("", "",
                        3, "");
            });

            Check.test("route validation", () -> {
                Check.raises(IllegalArgumentException.class, () -> Route.serpentine(List.of("A-1-1", "nonsense")));
                Check.raises(IllegalArgumentException.class, () -> Route.waves(List.of("A-1-1"), 0));
                Check.raises(IllegalArgumentException.class, () -> Route.waves(List.of("A-1-1"), -2));
                Check.raises(IllegalArgumentException.class, () -> Route.waves(List.of("A-1-1", "A-0-1"), 3));
                Check.eq(List.of(), Route.serpentine(List.of()));
                Check.eq(List.of(), Route.waves(List.of(), 4));
            });
        }
    }
''')

LIB = Lib(
    name="binslot", lang="java", title="the binslot library",
    blurb="The warehouse puts new stock away and builds its pick routes with binslot.",
    files={
        "src/warehouse/Zone.java": ZONE, "src/warehouse/BinId.java": BINID, "src/warehouse/Item.java": ITEM, "src/warehouse/Bin.java": BIN,
        "src/warehouse/Plan.java": PLAN, "src/warehouse/Putaway.java": PUTAWAY, "src/warehouse/Route.java": ROUTE,
        "README.md": README, ".gitignore": "build/\n",
    },
    visible_tests={"test/Check.java": JAVA_CHECK, "test/BasicTests.java": BASIC, "test/TestMain.java": java_test_main("BasicTests")},
    hidden_tests={"test/FullTests.java": FULL, "test/TestMain.java": java_test_main("BasicTests", "FullTests")},
    mutate=["src/warehouse/Putaway.java", "src/warehouse/Plan.java", "src/warehouse/Route.java", "src/warehouse/BinId.java"], difficulty=4,
    tags=["warehouse", "bin-packing", "routing"],
    probe_import="import warehouse.*;",
    probes=[
        "BinId.parse(\" b-7-1 \").toString()",
        "BinId.parse(\"ab-123-12\").toString()",
        "BinId.parse(\"A-1000-1\").toString()",
        "BinId.parse(\"A-1-0\").toString()",
        "BinId.parse(\"Z-01-1\").compareTo(BinId.parse(\"AA-01-1\")) < 0",
        "BinId.parse(\"A-02-1\").compareTo(BinId.parse(\"A-10-1\")) < 0",
        "Route.serpentine(java.util.List.of(\"A-1-1\", \"A-2-1\", \"B-1-1\", \"B-3-2\", \"B-3-1\", \"C-4-1\", \"c-1-1\"))",
        "Route.serpentine(java.util.List.of(\"D-2-1\", \"B-5-1\", \"D-9-3\", \"B-1-1\"))",
        "Route.waves(java.util.List.of(\"A-1-1\", \"A-2-1\", \"B-1-1\", \"B-3-1\", \"C-4-1\"), 3)",
        "Route.waves(java.util.List.of(\"A-1-1\", \"A-2-1\", \"A-3-1\", \"A-4-1\", \"A-5-1\", \"B-1-1\"), 2)",
        "Route.waves(java.util.List.of(\"A-1-1\"), 0)",
        "Putaway.plan(java.util.List.of(new Item(\"S1\", 5, 1, Zone.AMBIENT)), java.util.List.of(new Bin(\"A-01-1\", Zone.AMBIENT, 10, 9), new Bin(\"A-02-1\", Zone.AMBIENT, 6, 9), new Bin(\"A-03-1\", Zone.AMBIENT, 8, 9))).assignments()",
        "Putaway.plan(java.util.List.of(new Item(\"S1\", 3, 21, Zone.AMBIENT)), java.util.List.of(new Bin(\"A-01-3\", Zone.AMBIENT, 5, 99), new Bin(\"A-02-2\", Zone.AMBIENT, 9, 99))).assignments()",
        "Putaway.plan(java.util.List.of(new Item(\"h1\", 2, 1, Zone.HAZ), new Item(\"h2\", 2, 1, Zone.HAZ), new Item(\"h3\", 2, 1, Zone.HAZ)), java.util.List.of(new Bin(\"H-01-1\", Zone.HAZ, 20, 99))).unplaced()",
        "Putaway.plan(java.util.List.of(new Item(\"X\", 4, 10, Zone.AMBIENT), new Item(\"Y\", 3, 5, Zone.AMBIENT)), java.util.List.of(new Bin(\"A-01-1\", Zone.AMBIENT, 10, 50))).report()",
        "Putaway.plan(java.util.List.of(new Item(\"S1\", 2, 1, Zone.AMBIENT)), java.util.List.of(new Bin(\"A-01-1\", Zone.AMBIENT, 3, 50))).fill(\"a-1-1\")",
    ],
)

register_libs([LIB], n=8)
