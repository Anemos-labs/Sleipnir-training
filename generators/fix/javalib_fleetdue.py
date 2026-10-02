"""Fleet maintenance schedule: distance and calendar intervals (java): bugs injected into a due-date library."""
from fx import Lib, dd
from generators.fix._lang2 import JAVA_CHECK, java_test_main, register_libs

README = dd(r'''
    # fleetdue

    Maintenance planning for a small delivery fleet. Plain Java 17, no dependencies; sources in `src/fleet/`.
    Distances are whole kilometres; dates are *month numbers* (months counted from a fixed origin, so `103` is three months
    after `100`).

    ## `Rule(name, everyKm, everyMonths, soonKm, soonMonths)`

    A service interval: the job is due `everyKm` kilometres and/or `everyMonths` months after the last time it was done (`0`
    means "no limit of that kind"; whichever limit comes first counts). `everyKm` and `everyMonths` must not be negative and at
    least one of them must be positive; `soonKm` and `soonMonths` (the warning margins) must not be negative; otherwise
    `IllegalArgumentException`. `Service(km, month)` is the last time a job was done and `Reading(km, month)` the current
    odometer and date; negative numbers are an `IllegalArgumentException`. Fields are public and final.

    ## `Status` and `Maintenance`

    `Status` is `OK`, `SOON`, `DUE`, `OVERDUE` (in that order of severity).

    * `remainingKm(rule, last, now)`: `last.km + everyKm - now.km` (negative when past the limit), or `null` if the rule has no
      distance limit. `remainingMonths(rule, last, now)`: `last.month + everyMonths - now.month`, or `null` without a calendar
      limit.
    * `status(rule, last, now)`: each limit gives a status from its remaining amount `r`: `OVERDUE` if `r < 0`, `DUE` if
      `r == 0`, `SOON` if `r <= soon margin` (`soonKm` for the distance limit, `soonMonths` for the calendar one), else `OK`.
      The status of the rule is the most severe of its limits.
    * `projectedMonths(rule, last, now, kmPerMonth)`: how many months until the job is due, assuming the vehicle drives
      `kmPerMonth` km per month (`kmPerMonth >= 1`, else `IllegalArgumentException`). It is the smaller of the available
      estimates: for a calendar limit the remaining months (at least 0); for a distance limit the remaining kilometres divided by
      `kmPerMonth`, rounded **up** (0 when no kilometres remain).

    ## `Fleet`

    * `addRule(rule)` registers a rule (a second rule with the same name is an `IllegalArgumentException`).
    * `record(vehicle, ruleName, service)` stores when the vehicle last had that job done (unknown rule name: `IllegalArgumentException`).
    * `reading(vehicle, reading)` stores the vehicle's current reading (the latest call wins).
    * `report()` returns a `List<Fleet.Entry>` with one entry for every combination of a vehicle that has at least one
      record and a registered rule: `vehicle`, `rule` (the rule name), `status`, `remainingKm`, `remainingMonths` (both
      `Integer`, possibly `null`). A job that was never recorded for the vehicle is `OVERDUE` with both remaining values `null`.
      A vehicle with records but no reading is an `IllegalStateException`. The entries are sorted by status (most severe first),
      then by vehicle id, then by rule name (plain `String` order).
''')

STATUS = dd(r'''
    package fleet;

    public enum Status {
        OK,
        SOON,
        DUE,
        OVERDUE
    }
''')

RULE = dd(r'''
    package fleet;

    public final class Rule {
        public final String name;
        public final int everyKm;
        public final int everyMonths;
        public final int soonKm;
        public final int soonMonths;

        public Rule(String name, int everyKm, int everyMonths, int soonKm, int soonMonths) {
            if (everyKm < 0 || everyMonths < 0 || (everyKm == 0 && everyMonths == 0)) {
                throw new IllegalArgumentException("a rule needs a distance or a calendar limit");
            }
            if (soonKm < 0 || soonMonths < 0) {
                throw new IllegalArgumentException("warning margins must not be negative");
            }
            this.name = name;
            this.everyKm = everyKm;
            this.everyMonths = everyMonths;
            this.soonKm = soonKm;
            this.soonMonths = soonMonths;
        }
    }
''')

SERVICE = dd(r'''
    package fleet;

    public final class Service {
        public final int km;
        public final int month;

        public Service(int km, int month) {
            if (km < 0 || month < 0) {
                throw new IllegalArgumentException("km and month must not be negative");
            }
            this.km = km;
            this.month = month;
        }
    }
''')

READING = dd(r'''
    package fleet;

    public final class Reading {
        public final int km;
        public final int month;

        public Reading(int km, int month) {
            if (km < 0 || month < 0) {
                throw new IllegalArgumentException("km and month must not be negative");
            }
            this.km = km;
            this.month = month;
        }
    }
''')

MAINT = dd(r'''
    package fleet;

    public final class Maintenance {
        private Maintenance() {}

        public static Integer remainingKm(Rule rule, Service last, Reading now) {
            return rule.everyKm == 0 ? null : last.km + rule.everyKm - now.km;
        }

        public static Integer remainingMonths(Rule rule, Service last, Reading now) {
            return rule.everyMonths == 0 ? null : last.month + rule.everyMonths - now.month;
        }

        private static Status classify(int remaining, int soon) {
            if (remaining < 0) {
                return Status.OVERDUE;
            }
            if (remaining == 0) {
                return Status.DUE;
            }
            if (remaining <= soon) {
                return Status.SOON;
            }
            return Status.OK;
        }

        public static Status status(Rule rule, Service last, Reading now) {
            Status worst = Status.OK;
            Integer km = remainingKm(rule, last, now);
            if (km != null) {
                Status s = classify(km, rule.soonKm);
                if (s.ordinal() > worst.ordinal()) {
                    worst = s;
                }
            }
            Integer months = remainingMonths(rule, last, now);
            if (months != null) {
                Status s = classify(months, rule.soonMonths);
                if (s.ordinal() > worst.ordinal()) {
                    worst = s;
                }
            }
            return worst;
        }

        public static int projectedMonths(Rule rule, Service last, Reading now, int kmPerMonth) {
            if (kmPerMonth < 1) {
                throw new IllegalArgumentException("kmPerMonth must be at least 1");
            }
            int best = Integer.MAX_VALUE;
            Integer months = remainingMonths(rule, last, now);
            if (months != null) {
                best = Math.max(0, months);
            }
            Integer km = remainingKm(rule, last, now);
            if (km != null) {
                int byDistance = km <= 0 ? 0 : (km + kmPerMonth - 1) / kmPerMonth;
                best = Math.min(best, byDistance);
            }
            return best;
        }
    }
''')

FLEET = dd(r'''
    package fleet;

    import java.util.ArrayList;
    import java.util.HashMap;
    import java.util.LinkedHashMap;
    import java.util.List;
    import java.util.Map;
    import java.util.TreeMap;

    public final class Fleet {
        public static final class Entry {
            public final String vehicle;
            public final String rule;
            public final Status status;
            public final Integer remainingKm;
            public final Integer remainingMonths;

            Entry(String vehicle, String rule, Status status, Integer remainingKm, Integer remainingMonths) {
                this.vehicle = vehicle;
                this.rule = rule;
                this.status = status;
                this.remainingKm = remainingKm;
                this.remainingMonths = remainingMonths;
            }
        }

        private final Map<String, Rule> rules = new LinkedHashMap<>();
        private final Map<String, Map<String, Service>> records = new TreeMap<>();
        private final Map<String, Reading> readings = new HashMap<>();

        public void addRule(Rule rule) {
            if (rules.containsKey(rule.name)) {
                throw new IllegalArgumentException("duplicate rule " + rule.name);
            }
            rules.put(rule.name, rule);
        }

        public void record(String vehicle, String ruleName, Service service) {
            if (!rules.containsKey(ruleName)) {
                throw new IllegalArgumentException("unknown rule " + ruleName);
            }
            records.computeIfAbsent(vehicle, k -> new HashMap<>()).put(ruleName, service);
        }

        public void reading(String vehicle, Reading reading) {
            readings.put(vehicle, reading);
        }

        public List<Entry> report() {
            List<Entry> out = new ArrayList<>();
            for (Map.Entry<String, Map<String, Service>> v : records.entrySet()) {
                Reading now = readings.get(v.getKey());
                if (now == null) {
                    throw new IllegalStateException("no reading for " + v.getKey());
                }
                for (Rule rule : rules.values()) {
                    Service last = v.getValue().get(rule.name);
                    if (last == null) {
                        out.add(new Entry(v.getKey(), rule.name, Status.OVERDUE, null, null));
                    } else {
                        out.add(new Entry(v.getKey(), rule.name, Maintenance.status(rule, last, now),
                            Maintenance.remainingKm(rule, last, now), Maintenance.remainingMonths(rule, last, now)));
                    }
                }
            }
            out.sort((a, b) -> {
                if (a.status != b.status) {
                    return b.status.ordinal() - a.status.ordinal();
                }
                int byVehicle = a.vehicle.compareTo(b.vehicle);
                return byVehicle != 0 ? byVehicle : a.rule.compareTo(b.rule);
            });
            return out;
        }
    }
''')

BASIC = dd(r'''
    import fleet.Maintenance;
    import fleet.Reading;
    import fleet.Rule;
    import fleet.Service;
    import fleet.Status;

    public class BasicTests {
        public static void run() {
            Check.test("an oil change that is not yet due", () -> {
                Rule oil = new Rule("oil", 10000, 6, 500, 1);
                Check.eq(Status.OK, Maintenance.status(oil, new Service(50000, 100), new Reading(55000, 103)));
            });
            Check.test("remaining km", () -> {
                Rule oil = new Rule("oil", 10000, 6, 500, 1);
                Check.eq(5000, Maintenance.remainingKm(oil, new Service(50000, 100), new Reading(55000, 103)));
            });
        }
    }
''')

FULL = dd(r'''
    import fleet.Fleet;
    import fleet.Maintenance;
    import fleet.Reading;
    import fleet.Rule;
    import fleet.Service;
    import fleet.Status;
    import java.util.List;

    public class FullTests {
        static Rule rule(String name, int km, int months, int soonKm, int soonMonths) {
            return new Rule(name, km, months, soonKm, soonMonths);
        }

        static void check(Rule r, int lastKm, int lastMonth, int nowKm, int nowMonth, String status, Integer remKm, Integer remMonths) {
            Service last = new Service(lastKm, lastMonth);
            Reading now = new Reading(nowKm, nowMonth);
            Check.eq(status, Maintenance.status(r, last, now).name());
            Check.eq(remKm, Maintenance.remainingKm(r, last, now));
            Check.eq(remMonths, Maintenance.remainingMonths(r, last, now));
        }

        static void entry(Fleet.Entry e, String vehicle, String rule, String status, Integer remKm, Integer remMonths) {
            Check.eq(vehicle, e.vehicle);
            Check.eq(rule, e.rule);
            Check.eq(status, e.status.name());
            Check.eq(remKm, e.remainingKm);
            Check.eq(remMonths, e.remainingMonths);
        }

        public static void run() {
            Check.test("rule validation", () -> {
                Check.raises(IllegalArgumentException.class, () -> rule("x", 0, 0, 0, 0));
                Check.raises(IllegalArgumentException.class, () -> rule("x", -1, 6, 0, 0));
                Check.raises(IllegalArgumentException.class, () -> rule("x", 100, -1, 0, 0));
                Check.raises(IllegalArgumentException.class, () -> rule("x", 100, 6, -1, 0));
                Check.raises(IllegalArgumentException.class, () -> rule("x", 100, 6, 0, -1));
                rule("km only", 100, 0, 0, 0);
                rule("months only", 0, 1, 0, 0);
            });

            Check.test("service and reading validation", () -> {
                Check.raises(IllegalArgumentException.class, () -> new Service(-1, 0));
                Check.raises(IllegalArgumentException.class, () -> new Service(0, -1));
                Check.raises(IllegalArgumentException.class, () -> new Reading(-1, 0));
                Check.raises(IllegalArgumentException.class, () -> new Reading(0, -1));
                new Service(0, 0);
                new Reading(0, 0);
            });

            Check.test("statuses at the boundaries", () -> {
                Check.yes(Status.OK.ordinal() < Status.SOON.ordinal(), "order");
                Check.yes(Status.SOON.ordinal() < Status.DUE.ordinal(), "order");
                Check.yes(Status.DUE.ordinal() < Status.OVERDUE.ordinal(), "order");
            });

            Check.test("status and remaining values", () -> {
                check(rule("oil", 10000, 6, 500, 1), 50000, 100, 55000, 103, "OK", 5000, 3);
                check(rule("oil", 10000, 6, 500, 1), 50000, 100, 59500, 103, "SOON", 500, 3);
                check(rule("oil", 10000, 6, 500, 1), 50000, 100, 59499, 103, "OK", 501, 3);
                check(rule("oil", 10000, 6, 500, 1), 50000, 100, 60000, 103, "DUE", 0, 3);
                check(rule("oil", 10000, 6, 500, 1), 50000, 100, 60001, 103, "OVERDUE", -1, 3);
                check(rule("oil", 10000, 6, 500, 1), 50000, 100, 52000, 105, "SOON", 8000, 1);
                check(rule("oil", 10000, 6, 500, 1), 50000, 100, 52000, 106, "DUE", 8000, 0);
                check(rule("oil", 10000, 6, 500, 1), 50000, 100, 52000, 107, "OVERDUE", 8000, -1);
                check(rule("oil", 10000, 6, 500, 1), 50000, 100, 52000, 104, "OK", 8000, 2);
                check(rule("oil", 10000, 6, 500, 1), 50000, 100, 61000, 100, "OVERDUE", -1000, 6);
                check(rule("tires", 12000, 0, 1000, 0), 30000, 100, 41000, 150, "SOON", 1000, null);
                check(rule("tires", 12000, 0, 1000, 0), 30000, 100, 41001, 150, "SOON", 999, null);
                check(rule("tires", 12000, 0, 1000, 0), 30000, 100, 42000, 150, "DUE", 0, null);
                check(rule("tires", 12000, 0, 1000, 0), 30000, 100, 42001, 150, "OVERDUE", -1, null);
                check(rule("tires", 12000, 0, 1000, 0), 30000, 100, 30000, 100, "OK", 12000, null);
                check(rule("inspection", 0, 12, 0, 1), 0, 100, 999999, 110, "OK", null, 2);
                check(rule("inspection", 0, 12, 0, 1), 0, 100, 999999, 111, "SOON", null, 1);
                check(rule("inspection", 0, 12, 0, 1), 0, 100, 999999, 112, "DUE", null, 0);
                check(rule("inspection", 0, 12, 0, 1), 0, 100, 999999, 113, "OVERDUE", null, -1);
                check(rule("inspection", 0, 12, 0, 1), 0, 100, 0, 99, "OK", null, 13);
                check(rule("brakes", 20000, 12, 1000, 2), 10000, 100, 29000, 105, "SOON", 1000, 7);
                check(rule("brakes", 20000, 12, 1000, 2), 10000, 100, 15000, 110, "SOON", 15000, 2);
                check(rule("brakes", 20000, 12, 1000, 2), 10000, 100, 15000, 112, "DUE", 15000, 0);
                check(rule("brakes", 20000, 12, 1000, 2), 10000, 100, 15000, 113, "OVERDUE", 15000, -1);
                check(rule("brakes", 20000, 12, 1000, 2), 10000, 100, 29999, 100, "SOON", 1, 12);
                check(rule("brakes", 20000, 12, 1000, 2), 10000, 100, 29500, 100, "SOON", 500, 12);
                check(rule("brakes", 20000, 12, 1000, 2), 10000, 100, 28999, 100, "OK", 1001, 12);
            });

            Check.test("projected months until due", () -> {
                Check.eq(5, Maintenance.projectedMonths(rule("oil", 10000, 6, 500, 1), new Service(50000, 100), new Reading(55000, 101), 1000));
                Check.eq(3, Maintenance.projectedMonths(rule("oil", 10000, 6, 500, 1), new Service(50000, 100), new Reading(55000, 101), 2000));
                Check.eq(4, Maintenance.projectedMonths(rule("oil", 10000, 6, 500, 1), new Service(50000, 100), new Reading(55000, 101), 1500));
                Check.eq(0, Maintenance.projectedMonths(rule("oil", 10000, 6, 500, 1), new Service(50000, 100), new Reading(60000, 103), 1000));
                Check.eq(0, Maintenance.projectedMonths(rule("oil", 10000, 6, 500, 1), new Service(50000, 100), new Reading(61000, 103), 1000));
                Check.eq(3, Maintenance.projectedMonths(rule("tires", 12000, 0, 1000, 0), new Service(30000, 100), new Reading(40000, 110), 700));
                Check.eq(7, Maintenance.projectedMonths(rule("inspection", 0, 12, 0, 1), new Service(0, 100), new Reading(0, 105), 500));
                Check.eq(0, Maintenance.projectedMonths(rule("oil", 10000, 6, 500, 1), new Service(50000, 100), new Reading(52000, 110), 1000));
                Check.eq(2, Maintenance.projectedMonths(rule("brakes", 20000, 12, 1000, 2), new Service(10000, 100), new Reading(15000, 110), 3000));
                Check.eq(2, Maintenance.projectedMonths(rule("brakes", 20000, 12, 1000, 2), new Service(10000, 100), new Reading(15000, 110), 7500));
                Check.eq(2, Maintenance.projectedMonths(rule("brakes", 20000, 12, 1000, 2), new Service(10000, 100), new Reading(15000, 110), 7501));
                Check.eq(1, Maintenance.projectedMonths(rule("tires", 12000, 0, 1000, 0), new Service(30000, 100), new Reading(30000, 100), 12000));
                Check.eq(2, Maintenance.projectedMonths(rule("tires", 12000, 0, 1000, 0), new Service(30000, 100), new Reading(30000, 100), 11999));
            });

            Check.test("fleet report", () -> {
                Fleet fleet = new Fleet();
                fleet.addRule(rule("oil", 10000, 6, 500, 1));
                fleet.addRule(rule("tires", 12000, 0, 1000, 0));
                fleet.addRule(rule("inspection", 0, 12, 0, 1));
                fleet.addRule(rule("brakes", 20000, 12, 1000, 2));
                fleet.record("van-2", "oil", new Service(50000, 100));
                fleet.record("van-2", "tires", new Service(30000, 100));
                fleet.record("van-2", "inspection", new Service(0, 100));
                fleet.record("van-2", "brakes", new Service(10000, 100));
                fleet.record("van-10", "oil", new Service(8000, 101));
                fleet.record("van-10", "tires", new Service(0, 90));
                fleet.record("van-10", "inspection", new Service(0, 102));
                fleet.record("bus-1", "oil", new Service(120000, 98));
                fleet.record("bus-1", "tires", new Service(110000, 99));
                fleet.record("bus-1", "inspection", new Service(0, 95));
                fleet.record("bus-1", "brakes", new Service(100000, 99));
                fleet.reading("van-2", new Reading(59500, 103));
                fleet.reading("van-10", new Reading(9000, 106));
                fleet.reading("bus-1", new Reading(126000, 108));
                List<Fleet.Entry> got = fleet.report();
                Check.eq(12, got.size());
                entry(got.get(0), "bus-1", "brakes", "OVERDUE", -6000, 3);
                entry(got.get(1), "bus-1", "inspection", "OVERDUE", null, -1);
                entry(got.get(2), "bus-1", "oil", "OVERDUE", 4000, -4);
                entry(got.get(3), "bus-1", "tires", "OVERDUE", -4000, null);
                entry(got.get(4), "van-10", "brakes", "OVERDUE", null, null);
                entry(got.get(5), "van-2", "brakes", "OVERDUE", -29500, 9);
                entry(got.get(6), "van-2", "tires", "OVERDUE", -17500, null);
                entry(got.get(7), "van-10", "oil", "SOON", 9000, 1);
                entry(got.get(8), "van-2", "oil", "SOON", 500, 3);
                entry(got.get(9), "van-10", "inspection", "OK", null, 8);
                entry(got.get(10), "van-10", "tires", "OK", 3000, null);
                entry(got.get(11), "van-2", "inspection", "OK", null, 9);
            });

            Check.test("projection needs a positive rate", () -> {
                Rule oil = rule("oil", 10000, 6, 500, 1);
                Check.raises(IllegalArgumentException.class, () -> Maintenance.projectedMonths(oil, new Service(0, 0), new Reading(0, 0), 0));
                Check.raises(IllegalArgumentException.class, () -> Maintenance.projectedMonths(oil, new Service(0, 0), new Reading(0, 0), -5));
            });

            Check.test("fleet registration errors", () -> {
                Fleet fleet = new Fleet();
                fleet.addRule(rule("oil", 10000, 6, 500, 1));
                Check.raises(IllegalArgumentException.class, () -> fleet.addRule(rule("oil", 5000, 3, 0, 0)));
                Check.raises(IllegalArgumentException.class, () -> fleet.record("v1", "tires", new Service(0, 0)));
                fleet.record("v1", "oil", new Service(0, 0));
                Check.raises(IllegalStateException.class, fleet::report);
                fleet.reading("v1", new Reading(100, 1));
                Check.eq(1, fleet.report().size());
                Check.eq(0, new Fleet().report().size());
            });

            Check.test("the latest reading wins and an older rule list is kept in order", () -> {
                Fleet fleet = new Fleet();
                fleet.addRule(rule("zeta", 1000, 0, 100, 0));
                fleet.addRule(rule("alpha", 1000, 0, 100, 0));
                fleet.record("v", "zeta", new Service(0, 0));
                fleet.record("v", "alpha", new Service(0, 0));
                fleet.reading("v", new Reading(500, 1));
                fleet.reading("v", new Reading(950, 2));
                List<Fleet.Entry> got = fleet.report();
                Check.eq("alpha", got.get(0).rule);
                Check.eq("zeta", got.get(1).rule);
                Check.eq("SOON", got.get(0).status.name());
                Check.eq(50, got.get(0).remainingKm);
            });
        }
    }
''')

LIB = Lib(
    name="fleetdue", lang="java", title="the fleetdue library",
    blurb="The depot's maintenance planner uses fleetdue to tell which service jobs of which vehicle are due soon, due or overdue.",
    files={"src/fleet/Status.java": STATUS, "src/fleet/Rule.java": RULE, "src/fleet/Service.java": SERVICE, "src/fleet/Reading.java": READING,
           "src/fleet/Maintenance.java": MAINT, "src/fleet/Fleet.java": FLEET, "README.md": README, ".gitignore": "build/\n"},
    visible_tests={"test/Check.java": JAVA_CHECK, "test/BasicTests.java": BASIC, "test/TestMain.java": java_test_main("BasicTests")},
    hidden_tests={"test/FullTests.java": FULL, "test/TestMain.java": java_test_main("BasicTests", "FullTests")},
    mutate=["src/fleet/Maintenance.java", "src/fleet/Fleet.java", "src/fleet/Rule.java"], difficulty=2, tags=["maintenance", "schedules", "fleet"],
    probe_import="import java.util.*;\nimport fleet.*;",
    probes=[
        "Maintenance.status(new Rule(\"oil\", 10000, 6, 500, 1), new Service(50000, 100), new Reading(59500, 103))",
        "Maintenance.status(new Rule(\"oil\", 10000, 6, 500, 1), new Service(50000, 100), new Reading(60000, 103))",
        "Maintenance.status(new Rule(\"oil\", 10000, 6, 500, 1), new Service(50000, 100), new Reading(52000, 106))",
        "Maintenance.status(new Rule(\"oil\", 10000, 6, 500, 1), new Service(50000, 100), new Reading(52000, 107))",
        "Maintenance.status(new Rule(\"tires\", 12000, 0, 1000, 0), new Service(30000, 100), new Reading(41001, 150))",
        "Maintenance.status(new Rule(\"inspection\", 0, 12, 0, 1), new Service(0, 100), new Reading(999999, 111))",
        "Maintenance.remainingKm(new Rule(\"inspection\", 0, 12, 0, 1), new Service(0, 100), new Reading(5, 111))",
        "Maintenance.remainingMonths(new Rule(\"tires\", 12000, 0, 1000, 0), new Service(30000, 100), new Reading(5, 111))",
        "Maintenance.remainingMonths(new Rule(\"oil\", 10000, 6, 500, 1), new Service(50000, 100), new Reading(52000, 107))",
        "Maintenance.projectedMonths(new Rule(\"oil\", 10000, 6, 500, 1), new Service(50000, 100), new Reading(55000, 101), 1500)",
        "Maintenance.projectedMonths(new Rule(\"tires\", 12000, 0, 1000, 0), new Service(30000, 100), new Reading(40000, 110), 700)",
        "Maintenance.projectedMonths(new Rule(\"oil\", 10000, 6, 500, 1), new Service(50000, 100), new Reading(61000, 103), 1000)",
        "Maintenance.projectedMonths(new Rule(\"oil\", 10000, 6, 500, 1), new Service(50000, 100), new Reading(52000, 110), 1000)",
        "new Rule(\"x\", 0, 0, 0, 0)",
    ],
)

register_libs([LIB], n=8)
