"""Ranked-ballot counting for club elections (java): bugs injected into an instant-runoff tally with ties and thresholds."""
from fx import Lib, dd
from generators.fix._lang2 import JAVA_CHECK, java_test_main, register_libs

README = dd(r'''
    # ballotcount

    Counts ranked ("instant runoff") ballots for club and committee elections. Plain Java 17, no dependencies; sources in
    `src/vote/`.

    ## Ballots

    A `Ballot` is a weight (how many people cast it) and a ranking of candidate names, most preferred first.

    * `new Ballot(weight, ranking)`: `IllegalArgumentException` if the weight is below 1.
    * `Ballot.parse(line)`: the text form `3: Ash > Birch > Cedar`. The part before an optional colon is the weight: digits only
      (spaces around them are fine), at least 1, otherwise `IllegalArgumentException`. Without a colon the weight is 1. The names
      are separated by `>` and trimmed; empty names are skipped, so `parse("2:")` and `parse("")` give ballots with an empty ranking.
      Names are kept as typed: repeated and unknown names are only dealt with when the ballots are counted.

    ## `Election`

    * `new Election(names)`: the candidates in registration order. Names are trimmed. `IllegalArgumentException` for no
      candidates at all, for an empty name, and for two names that are equal when case is ignored.
    * `Election.of("Ash, Birch, Cedar", "3: Ash > Birch", "Cedar")`: shortcut. The first argument is a comma separated list of
      candidates, every further argument is a ballot line (see `parse`).
    * Names on ballots are matched to candidates ignoring case; results always show the registered spelling.
    * `add(Ballot)` and `add(String line)` add a ballot.
    * `withdraw(name)`: the candidate leaves the race (any case; `IllegalArgumentException` for an unknown name). Ballots naming
      them still count, they just skip that name.
    * `setThreshold(percent)`: `0` to `100` (default `0`, otherwise `IllegalArgumentException`), see below.
    * `count()`: returns a `Result`. It can be called again and again; it does not use up the ballots, and ballots added later are
      counted by the next call.

    ## How a count works

    On every ballot, names that are not registered candidates are ignored, and so is a name that already appeared earlier on the
    same ballot. A ballot that names no registered candidate at all is **blank**.

    The candidates *in the race* are the registered ones minus the withdrawn ones minus those eliminated so far. In each round,
    every ballot counts, with its weight, for the first candidate of its ranking that is in the race; a ballot with none left is
    *exhausted* in that round. The round records the tally of every candidate in the race (zero included) and the **active
    weight**, the total weight of the ballots that counted for somebody.

    1. If the active weight is 0 (also when there are no ballots), the count stops without a winner.
    2. A candidate with strictly more than half of the active weight wins. The only candidate left in the race wins too.
    3. Otherwise one candidate is eliminated and the next round starts: the one with the lowest tally in this round. Ties are
       broken by the lower tally in round 1, and if that ties as well, the candidate registered later is eliminated.
    4. **Threshold**, round 1 only: when the threshold is above 0, step 3 of round 1 eliminates *every* candidate whose tally is
       below that percentage of the active weight (`100 * tally < percent * active`) instead of a single one, unless that would be
       all of the candidates in the race, in which case the ordinary rule of step 3 applies.

    A race without any candidate (all withdrawn) has no rounds and no winner.

    ## `Result`

    * `winner()`: the winner's name, `null` for none.
    * `rounds()`: the list of `Round`s.
    * `blank()`: the total weight of the blank ballots.
    * `exhausted()`: the total weight of the non-blank ballots that did not count for anybody in the last round (all of the
      non-blank weight when there were no rounds).
    * `margin()`: the winner's tally in the last round minus the highest tally among the other candidates of that round (0 for
      them if there are none); 0 without a winner.
    * `order()`: the finishing order: the winner, then the other candidates of the last round by tally (highest first, ties in
      registration order), then the eliminated candidates, the latest round first; candidates eliminated together in one round
      go by that round's tally (highest first, ties in registration order). Withdrawn candidates are not listed. Empty without a
      winner.
    * `summary()`: one line per round, joined with `\n`, no trailing newline:
      `Round 2: Ash 5, Birch 4 | active 9 | out Birch` lists the round's tallies highest first (ties in registration order), then
      the active weight, then ` | out ` and the names eliminated (registration order) if any, then ` | win ` and the winner if the
      round decided. Without rounds the summary is `no candidates`.

    ## `Round`

    * `tallies()`: map from name to tally, iterating in registration order.
    * `active()`, `eliminated()` (list, registration order, empty in the deciding round) and `winner()` (the winner in the deciding
      round, otherwise `null`).
    * `share(name)`: the candidate's part of the active weight as a percentage with one decimal, rounded half up, such as
      `44.4%`; `0.0%` when the active weight is 0; `IllegalArgumentException` for a name that is not in this round.
''')

BALLOT = dd(r'''
    package vote;

    import java.util.ArrayList;
    import java.util.List;

    public final class Ballot {
        private final int weight;
        private final List<String> ranking;

        public Ballot(int weight, List<String> ranking) {
            if (weight < 1) {
                throw new IllegalArgumentException("weight must be at least 1");
            }
            this.weight = weight;
            this.ranking = List.copyOf(ranking);
        }

        public int weight() {
            return weight;
        }

        public List<String> ranking() {
            return ranking;
        }

        public static Ballot parse(String line) {
            String body = line;
            int weight = 1;
            int colon = line.indexOf(':');
            if (colon >= 0) {
                String head = line.substring(0, colon).trim();
                if (head.isEmpty() || !head.chars().allMatch(ch -> ch >= '0' && ch <= '9')) {
                    throw new IllegalArgumentException("bad weight: " + head);
                }
                weight = Integer.parseInt(head);
                body = line.substring(colon + 1);
            }
            List<String> names = new ArrayList<>();
            for (String part : body.split(">")) {
                String name = part.trim();
                if (!name.isEmpty()) {
                    names.add(name);
                }
            }
            return new Ballot(weight, names);
        }
    }
''')

ROUND = dd(r'''
    package vote;

    import java.util.ArrayList;
    import java.util.Collections;
    import java.util.List;
    import java.util.Map;

    public final class Round {
        private final Map<String, Integer> tallies;
        private final int active;
        private final List<String> eliminated;
        private final String winner;

        Round(Map<String, Integer> tallies, int active, List<String> eliminated, String winner) {
            this.tallies = tallies;
            this.active = active;
            this.eliminated = eliminated;
            this.winner = winner;
        }

        public Map<String, Integer> tallies() {
            return Collections.unmodifiableMap(tallies);
        }

        public int active() {
            return active;
        }

        public List<String> eliminated() {
            return Collections.unmodifiableList(eliminated);
        }

        public String winner() {
            return winner;
        }

        public String share(String name) {
            Integer t = tallies.get(name);
            if (t == null) {
                throw new IllegalArgumentException("not in this round: " + name);
            }
            if (active == 0) {
                return "0.0%";
            }
            long tenths = (2000L * t + active) / (2L * active);
            return (tenths / 10) + "." + (tenths % 10) + "%";
        }

        String line(int number) {
            List<String> names = new ArrayList<>(tallies.keySet());
            names.sort((a, b) -> tallies.get(b) - tallies.get(a));
            StringBuilder sb = new StringBuilder("Round " + number + ": ");
            for (int i = 0; i < names.size(); i++) {
                if (i > 0) {
                    sb.append(", ");
                }
                sb.append(names.get(i)).append(' ').append(tallies.get(names.get(i)));
            }
            sb.append(" | active ").append(active);
            if (!eliminated.isEmpty()) {
                sb.append(" | out ").append(String.join(", ", eliminated));
            }
            if (winner != null) {
                sb.append(" | win ").append(winner);
            }
            return sb.toString();
        }
    }
''')

RESULT = dd(r'''
    package vote;

    import java.util.ArrayList;
    import java.util.Collections;
    import java.util.List;
    import java.util.Map;

    public final class Result {
        private final List<Round> rounds;
        private final String winner;
        private final int blank;
        private final int counted;

        Result(List<Round> rounds, String winner, int blank, int counted) {
            this.rounds = rounds;
            this.winner = winner;
            this.blank = blank;
            this.counted = counted;
        }

        public String winner() {
            return winner;
        }

        public List<Round> rounds() {
            return Collections.unmodifiableList(rounds);
        }

        public int blank() {
            return blank;
        }

        public int exhausted() {
            if (rounds.isEmpty()) {
                return counted;
            }
            return counted - rounds.get(rounds.size() - 1).active();
        }

        public int margin() {
            if (winner == null) {
                return 0;
            }
            Map<String, Integer> last = rounds.get(rounds.size() - 1).tallies();
            int best = 0;
            for (Map.Entry<String, Integer> e : last.entrySet()) {
                if (!e.getKey().equals(winner)) {
                    best = Math.max(best, e.getValue());
                }
            }
            return last.get(winner) - best;
        }

        public List<String> order() {
            List<String> out = new ArrayList<>();
            if (winner == null) {
                return out;
            }
            out.add(winner);
            Map<String, Integer> last = rounds.get(rounds.size() - 1).tallies();
            List<String> rest = new ArrayList<>(last.keySet());
            rest.remove(winner);
            rest.sort((a, b) -> last.get(b) - last.get(a));
            out.addAll(rest);
            for (int i = rounds.size() - 1; i >= 0; i--) {
                Map<String, Integer> tallies = rounds.get(i).tallies();
                List<String> gone = new ArrayList<>(rounds.get(i).eliminated());
                gone.sort((a, b) -> tallies.get(b) - tallies.get(a));
                out.addAll(gone);
            }
            return out;
        }

        public String summary() {
            if (rounds.isEmpty()) {
                return "no candidates";
            }
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < rounds.size(); i++) {
                if (i > 0) {
                    sb.append('\n');
                }
                sb.append(rounds.get(i).line(i + 1));
            }
            return sb.toString();
        }
    }
''')

ELECTION = dd(r'''
    package vote;

    import java.util.ArrayList;
    import java.util.HashSet;
    import java.util.LinkedHashMap;
    import java.util.List;
    import java.util.Map;
    import java.util.Set;

    public final class Election {
        private final List<String> candidates = new ArrayList<>();
        private final Set<String> withdrawn = new HashSet<>();
        private final List<Ballot> ballots = new ArrayList<>();
        private int thresholdPercent = 0;

        public Election(List<String> names) {
            for (String raw : names) {
                String name = raw.trim();
                if (name.isEmpty()) {
                    throw new IllegalArgumentException("empty candidate name");
                }
                if (find(name) != null) {
                    throw new IllegalArgumentException("duplicate candidate: " + name);
                }
                candidates.add(name);
            }
            if (candidates.isEmpty()) {
                throw new IllegalArgumentException("no candidates");
            }
        }

        public static Election of(String candidateList, String... ballotLines) {
            List<String> names = new ArrayList<>();
            for (String part : candidateList.split(",")) {
                names.add(part);
            }
            Election election = new Election(names);
            for (String line : ballotLines) {
                election.add(line);
            }
            return election;
        }

        private String find(String name) {
            for (String c : candidates) {
                if (c.equalsIgnoreCase(name)) {
                    return c;
                }
            }
            return null;
        }

        public void withdraw(String name) {
            String c = find(name.trim());
            if (c == null) {
                throw new IllegalArgumentException("unknown candidate: " + name);
            }
            withdrawn.add(c);
        }

        public void setThreshold(int percent) {
            if (percent < 0 || percent > 100) {
                throw new IllegalArgumentException("percent out of range");
            }
            thresholdPercent = percent;
        }

        public void add(Ballot ballot) {
            ballots.add(ballot);
        }

        public void add(String line) {
            ballots.add(Ballot.parse(line));
        }

        public Result count() {
            int blank = 0;
            int counted = 0;
            List<List<String>> prefs = new ArrayList<>();
            List<Integer> weights = new ArrayList<>();
            for (Ballot b : ballots) {
                List<String> list = new ArrayList<>();
                for (String raw : b.ranking()) {
                    String c = find(raw);
                    if (c != null && !list.contains(c)) {
                        list.add(c);
                    }
                }
                if (list.isEmpty()) {
                    blank += b.weight();
                } else {
                    counted += b.weight();
                    prefs.add(list);
                    weights.add(b.weight());
                }
            }

            List<String> remaining = new ArrayList<>();
            for (String c : candidates) {
                if (!withdrawn.contains(c)) {
                    remaining.add(c);
                }
            }
            List<Round> rounds = new ArrayList<>();
            Map<String, Integer> first = null;
            String winner = null;
            while (!remaining.isEmpty()) {
                Map<String, Integer> tally = new LinkedHashMap<>();
                for (String c : remaining) {
                    tally.put(c, 0);
                }
                int active = 0;
                for (int i = 0; i < prefs.size(); i++) {
                    for (String c : prefs.get(i)) {
                        if (tally.containsKey(c)) {
                            tally.merge(c, weights.get(i), Integer::sum);
                            active += weights.get(i);
                            break;
                        }
                    }
                }
                if (first == null) {
                    first = new LinkedHashMap<>(tally);
                }
                if (active == 0) {
                    rounds.add(new Round(tally, active, new ArrayList<>(), null));
                    break;
                }
                String top = null;
                for (String c : remaining) {
                    if (2 * tally.get(c) > active) {
                        top = c;
                    }
                }
                if (top == null && remaining.size() == 1) {
                    top = remaining.get(0);
                }
                if (top != null) {
                    rounds.add(new Round(tally, active, new ArrayList<>(), top));
                    winner = top;
                    break;
                }
                List<String> drop = new ArrayList<>();
                if (rounds.isEmpty() && thresholdPercent > 0) {
                    for (String c : remaining) {
                        if (100L * tally.get(c) < (long) thresholdPercent * active) {
                            drop.add(c);
                        }
                    }
                    if (drop.size() == remaining.size()) {
                        drop.clear();
                    }
                }
                if (drop.isEmpty()) {
                    drop.add(weakest(remaining, tally, first));
                }
                rounds.add(new Round(tally, active, drop, null));
                remaining.removeAll(drop);
            }
            return new Result(rounds, winner, blank, counted);
        }

        private static String weakest(List<String> remaining, Map<String, Integer> tally, Map<String, Integer> first) {
            String pick = null;
            for (String c : remaining) {
                if (pick == null) {
                    pick = c;
                    continue;
                }
                int a = tally.get(c);
                int b = tally.get(pick);
                if (a < b || (a == b && first.get(c) <= first.get(pick))) {
                    pick = c;
                }
            }
            return pick;
        }
    }
''')

BASIC = dd(r'''
    import java.util.List;
    import vote.Ballot;
    import vote.Election;
    import vote.Result;

    public class BasicTests {
        public static void run() {
            Check.test("parse a ballot line", () -> {
                Ballot b = Ballot.parse("3: Ash > Birch");
                Check.eq(3, b.weight());
                Check.eq(List.of("Ash", "Birch"), b.ranking());
            });
            Check.test("a first-round majority wins", () -> {
                Result r = Election.of("Ash,Birch,Cedar", "Ash > Birch", "Ash", "Birch > Cedar").count();
                Check.eq("Ash", r.winner());
                Check.eq("Round 1: Ash 2, Birch 1, Cedar 0 | active 3 | win Ash", r.summary());
            });
            Check.test("votes move on when a candidate is eliminated", () -> {
                Result r = Election.of("Ash,Birch,Cedar", "3: Ash", "4: Birch", "2: Cedar > Ash").count();
                Check.eq("Ash", r.winner());
            });
        }
    }
''')

FULL = dd(r'''
    import java.util.ArrayList;
    import java.util.Arrays;
    import java.util.List;
    import vote.Ballot;
    import vote.Election;
    import vote.Result;
    import vote.Round;

    public class FullTests {
        static void scenario(String names, String withdrawn, int threshold, String ballots, String summary, String order, int blank, int exhausted, int margin) {
            Election e = Election.of(names);
            if (!withdrawn.isEmpty()) {
                for (String w : withdrawn.split(",")) {
                    e.withdraw(w);
                }
            }
            e.setThreshold(threshold);
            if (!ballots.isEmpty()) {
                for (String line : ballots.split("\\|", -1)) {
                    e.add(line);
                }
            }
            Result r = e.count();
            String label = names + " / " + ballots;
            Check.eq(label + " (summary)", summary, r.summary());
            Check.eq(label + " (order)", order, String.join(",", r.order()));
            Check.eq(label + " (winner)", order.isEmpty() ? null : order.split(",")[0], r.winner());
            Check.eq(label + " (blank)", blank, r.blank());
            Check.eq(label + " (exhausted)", exhausted, r.exhausted());
            Check.eq(label + " (margin)", margin, r.margin());
        }

        static List<String> names(String... n) {
            return Arrays.asList(n);
        }

        public static void run() {
            Check.test("Ballot.parse weights", () -> {
                Ballot a = Ballot.parse("Ash > Birch > Cedar");
                Check.eq(1, a.weight());
                Check.eq(names("Ash", "Birch", "Cedar"), a.ranking());
                Ballot b = Ballot.parse("3: Ash > Birch");
                Check.eq(3, b.weight());
                Check.eq(names("Ash", "Birch"), b.ranking());
                Ballot c = Ballot.parse("  12 :  x>y  ");
                Check.eq(12, c.weight());
                Check.eq(names("x", "y"), c.ranking());
                Check.eq(7, Ballot.parse("007: Ash").weight());
                Check.eq(100, Ballot.parse("100:Ash").weight());
                Check.eq(1, Ballot.parse("1: Ash").weight());
            });

            Check.test("Ballot.parse names", () -> {
                Check.eq(names("Ash", "Birch"), Ballot.parse("Ash > > Birch >").ranking());
                Check.eq(names("Ash"), Ballot.parse(" > Ash").ranking());
                Check.eq(names("Ash Tree", "Birch"), Ballot.parse("  Ash Tree  >Birch ").ranking());
                Check.eq(names(), Ballot.parse("2:").ranking());
                Check.eq(2, Ballot.parse("2:").weight());
                Check.eq(names(), Ballot.parse("").ranking());
                Check.eq(1, Ballot.parse("").weight());
                Check.eq(names(), Ballot.parse(" > > ").ranking());
                Check.eq(names("Ash", "Ash"), Ballot.parse("Ash > Ash").ranking());
            });

            Check.test("Ballot weights are checked", () -> {
                Check.raises(IllegalArgumentException.class, () -> Ballot.parse("0: Ash"));
                Check.raises(IllegalArgumentException.class, () -> Ballot.parse("00: Ash"));
                Check.raises(IllegalArgumentException.class, () -> Ballot.parse("-1: Ash"));
                Check.raises(IllegalArgumentException.class, () -> Ballot.parse("+1: Ash"));
                Check.raises(IllegalArgumentException.class, () -> Ballot.parse("1.5: Ash"));
                Check.raises(IllegalArgumentException.class, () -> Ballot.parse(": Ash"));
                Check.raises(IllegalArgumentException.class, () -> Ballot.parse("  : Ash"));
                Check.raises(IllegalArgumentException.class, () -> Ballot.parse("x: Ash"));
                Check.raises(IllegalArgumentException.class, () -> Ballot.parse("2 3: Ash"));
                Check.raises(IllegalArgumentException.class, () -> new Ballot(0, names("Ash")));
                Check.raises(IllegalArgumentException.class, () -> new Ballot(-4, names("Ash")));
                Check.eq(1, new Ballot(1, names("Ash")).weight());
                Check.eq(names("Ash", "Birch"), new Ballot(5, names("Ash", "Birch")).ranking());
            });

            Check.test("election set-up is validated", () -> {
                Check.raises(IllegalArgumentException.class, () -> new Election(names()));
                Check.raises(IllegalArgumentException.class, () -> new Election(names("Ash", "")));
                Check.raises(IllegalArgumentException.class, () -> new Election(names("Ash", "  ")));
                Check.raises(IllegalArgumentException.class, () -> new Election(names("Ash", "ASH")));
                Check.raises(IllegalArgumentException.class, () -> new Election(names("Ash", "Birch", " birch ")));
                Check.raises(IllegalArgumentException.class, () -> Election.of("Ash,,Birch"));
                Check.raises(IllegalArgumentException.class, () -> Election.of(""));
                Election e = Election.of("Ash, Birch");
                Check.raises(IllegalArgumentException.class, () -> e.withdraw("Cedar"));
                Check.raises(IllegalArgumentException.class, () -> e.setThreshold(-1));
                Check.raises(IllegalArgumentException.class, () -> e.setThreshold(101));
                e.setThreshold(0);
                e.setThreshold(100);
                e.withdraw("ash");
                e.withdraw("birch");
                Check.raises(IllegalArgumentException.class, () -> e.add("x: Ash"));
            });

            Check.test("candidate names are trimmed and keep their spelling", () -> {
                Result r = Election.of(" Ash ,bIRCH,  Cedar Tree", "ASH > birch", "cedar tree > ASH", "3: CEDAR TREE").count();
                Check.eq("Round 1: Cedar Tree 4, Ash 1, bIRCH 0 | active 5 | win Cedar Tree", r.summary());
                Check.eq("Cedar Tree", r.winner());
                Check.eq(names("Cedar Tree", "Ash", "bIRCH"), r.order());
            });

            Check.test("Election.of and add", () -> {
                Result r = Election.of("Ash,Birch,Cedar", "3: Ash > Birch", "2: Birch > Cedar", "Cedar").count();
                Check.eq("Round 1: Ash 3, Birch 2, Cedar 1 | active 6 | out Cedar\nRound 2: Ash 3, Birch 2 | active 5 | win Ash", r.summary());
                Election e = new Election(names("Ash", "Birch"));
                e.add(new Ballot(4, names("birch")));
                e.add("Ash");
                Check.eq("Round 1: Birch 4, Ash 1 | active 5 | win Birch", e.count().summary());
            });

            Check.test("a majority in round 1 wins at once", () -> {
                scenario("Ash,Birch,Cedar", "", 0, "Ash > Birch|Ash|Birch > Cedar",
                        "Round 1: Ash 2, Birch 1, Cedar 0 | active 3 | win Ash",
                        "Ash,Birch,Cedar", 0, 0, 1);
                scenario("Ash,Birch,Cedar", "", 0, "3: Cedar > Ash|Ash > Cedar|Birch",
                        "Round 1: Cedar 3, Ash 1, Birch 1 | active 5 | win Cedar",
                        "Cedar,Ash,Birch", 0, 0, 2);
                scenario("Ash", "", 0, "",
                        "Round 1: Ash 0 | active 0",
                        "", 0, 0, 0);
                scenario("Ash", "", 0, "Ash|2: Ash",
                        "Round 1: Ash 3 | active 3 | win Ash",
                        "Ash", 0, 0, 3);
                scenario("Ash", "", 0, "Zed|Zed > Yew",
                        "Round 1: Ash 0 | active 0",
                        "", 2, 0, 0);
            });

            Check.test("more than half is needed, exactly half is not enough", () -> {
                scenario("Ash,Birch", "", 0, "Ash|Ash|Birch|Birch",
                        "Round 1: Ash 2, Birch 2 | active 4 | out Birch\nRound 2: Ash 2 | active 2 | win Ash",
                        "Ash,Birch", 0, 2, 2);
                scenario("Ash,Birch", "", 0, "Birch|Birch|Ash|Ash",
                        "Round 1: Ash 2, Birch 2 | active 4 | out Birch\nRound 2: Ash 2 | active 2 | win Ash",
                        "Ash,Birch", 0, 2, 2);
                scenario("Ash,Birch,Cedar", "", 0, "Ash|Ash|Birch|Birch|Cedar > Birch|Cedar > Ash",
                        "Round 1: Ash 2, Birch 2, Cedar 2 | active 6 | out Cedar\nRound 2: Ash 3, Birch 3 | active 6 | out Birch\nRound 3: Ash 3 | active 3 | win Ash",
                        "Ash,Birch,Cedar", 0, 3, 3);
                scenario("Ash,Birch,Cedar", "", 0, "2: Ash|Birch|Cedar",
                        "Round 1: Ash 2, Birch 1, Cedar 1 | active 4 | out Cedar\nRound 2: Ash 2, Birch 1 | active 3 | win Ash",
                        "Ash,Birch,Cedar", 0, 1, 1);
            });

            Check.test("votes move to the next choice still in the race", () -> {
                scenario("Ash,Birch,Cedar,Dogwood", "", 0, "4: Ash > Birch|3: Birch > Ash|2: Cedar > Birch > Ash|2: Dogwood > Cedar > Birch",
                        "Round 1: Ash 4, Birch 3, Cedar 2, Dogwood 2 | active 11 | out Dogwood\nRound 2: Ash 4, Cedar 4, Birch 3 | active 11 | out Birch\nRound 3: Ash 7, Cedar 4 | active 11 | win Ash",
                        "Ash,Cedar,Birch,Dogwood", 0, 0, 3);
                scenario("Ash,Birch,Cedar", "", 0, "3: Ash > Cedar|3: Birch > Cedar|2: Cedar > Birch|1: Cedar > Ash",
                        "Round 1: Ash 3, Birch 3, Cedar 3 | active 9 | out Cedar\nRound 2: Birch 5, Ash 4 | active 9 | win Birch",
                        "Birch,Ash,Cedar", 0, 0, 1);
                scenario("Ash,Birch,Cedar,Dogwood", "", 0, "Ash > Birch > Cedar > Dogwood|Birch > Cedar > Dogwood > Ash|Cedar > Dogwood > Ash > Birch|Dogwood > Ash > Birch > Cedar|Dogwood > Ash|Cedar",
                        "Round 1: Cedar 2, Dogwood 2, Ash 1, Birch 1 | active 6 | out Birch\nRound 2: Cedar 3, Dogwood 2, Ash 1 | active 6 | out Ash\nRound 3: Cedar 4, Dogwood 2 | active 6 | win Cedar",
                        "Cedar,Dogwood,Ash,Birch", 0, 0, 2);
            });

            Check.test("elimination ties: lower round-1 tally first, then the later registered", () -> {
                scenario("A,B,C,D", "", 0, "B > C|D > A|2: D > B|A|C > D > A|2: A|C",
                        "Round 1: A 3, D 3, C 2, B 1 | active 9 | out B\nRound 2: A 3, C 3, D 3 | active 9 | out C\nRound 3: D 4, A 3 | active 7 | win D",
                        "D,A,C,B", 0, 2, 1);
                scenario("A,B,C,D", "", 0, "B > C|A > B|B|C > A|D > A",
                        "Round 1: B 2, A 1, C 1, D 1 | active 5 | out D\nRound 2: A 2, B 2, C 1 | active 5 | out C\nRound 3: A 3, B 2 | active 5 | win A",
                        "A,B,C,D", 0, 0, 1);
                scenario("A,B,C", "", 0, "A|B|C",
                        "Round 1: A 1, B 1, C 1 | active 3 | out C\nRound 2: A 1, B 1 | active 2 | out B\nRound 3: A 1 | active 1 | win A",
                        "A,B,C", 0, 2, 1);
                scenario("A,B,C,D", "", 0, "A > D|B > D|C > D|D",
                        "Round 1: A 1, B 1, C 1, D 1 | active 4 | out D\nRound 2: A 1, B 1, C 1 | active 3 | out C\nRound 3: A 1, B 1 | active 2 | out B\nRound 4: A 1 | active 1 | win A",
                        "A,B,C,D", 0, 3, 1);
                scenario("A,B,C,D", "", 0, "2: A > B|2: B > C|2: C > D|3: D",
                        "Round 1: D 3, A 2, B 2, C 2 | active 9 | out C\nRound 2: D 5, A 2, B 2 | active 9 | win D",
                        "D,A,B,C", 0, 0, 3);
            });

            Check.test("ballot weights", () -> {
                scenario("Ash,Birch,Cedar", "", 0, "5: Ash|1: Birch|1: Birch|1: Birch|1: Cedar|1: Cedar|1: Cedar",
                        "Round 1: Ash 5, Birch 3, Cedar 3 | active 11 | out Cedar\nRound 2: Ash 5, Birch 3 | active 8 | win Ash",
                        "Ash,Birch,Cedar", 0, 3, 2);
                scenario("Ash,Birch,Cedar", "", 0, "4: Birch > Cedar|2: Ash > Cedar|3: Ash|1: Cedar > Ash",
                        "Round 1: Ash 5, Birch 4, Cedar 1 | active 10 | out Cedar\nRound 2: Ash 6, Birch 4 | active 10 | win Ash",
                        "Ash,Birch,Cedar", 0, 0, 2);
                scenario("Ash,Birch", "", 0, "07: Ash|  3 :Birch|4: Birch",
                        "Round 1: Ash 7, Birch 7 | active 14 | out Birch\nRound 2: Ash 7 | active 7 | win Ash",
                        "Ash,Birch", 0, 7, 7);
            });

            Check.test("names match ignoring case; repeated and unknown names are skipped", () -> {
                scenario("Ash,Birch,Cedar", "", 0, "ash|ASH > cedar|bIrCh > ASH|zed > Birch|Yew > cedar > Zed",
                        "Round 1: Ash 2, Birch 2, Cedar 1 | active 5 | out Cedar\nRound 2: Ash 2, Birch 2 | active 4 | out Birch\nRound 3: Ash 3 | active 3 | win Ash",
                        "Ash,Birch,Cedar", 0, 2, 3);
                scenario("Ash,Birch,Cedar", "", 0, "Birch > Birch > Cedar|Birch > Ash > Birch|Cedar > cedar > Ash|Ash > ASH",
                        "Round 1: Birch 2, Ash 1, Cedar 1 | active 4 | out Cedar\nRound 2: Ash 2, Birch 2 | active 4 | out Ash\nRound 3: Birch 2 | active 2 | win Birch",
                        "Birch,Ash,Cedar", 0, 2, 2);
                scenario("Ash,Birch,Cedar", "", 0, "Zed > Birch > Ash|Zed > Zed > Cedar|Birch > zed|Cedar",
                        "Round 1: Birch 2, Cedar 2, Ash 0 | active 4 | out Ash\nRound 2: Birch 2, Cedar 2 | active 4 | out Cedar\nRound 3: Birch 2 | active 2 | win Birch",
                        "Birch,Cedar,Ash", 0, 2, 2);
            });

            Check.test("withdrawn candidates", () -> {
                scenario("Ash,Birch,Cedar", "Ash", 0, "Ash > Birch|Ash > Cedar|Birch|Cedar|Cedar > Birch",
                        "Round 1: Cedar 3, Birch 2 | active 5 | win Cedar",
                        "Cedar,Birch", 0, 0, 1);
                scenario("Ash,Birch,Cedar,Dogwood", "birch,DOGWOOD", 0, "Ash > Birch|2: Birch > Cedar|Cedar > Dogwood|Dogwood > Ash",
                        "Round 1: Cedar 3, Ash 2 | active 5 | win Cedar",
                        "Cedar,Ash", 0, 0, 1);
                scenario("Ash,Birch,Cedar", "Ash,Birch", 0, "Ash|Birch > Ash|2: Cedar > Ash",
                        "Round 1: Cedar 2 | active 2 | win Cedar",
                        "Cedar", 0, 2, 2);
                scenario("Ash,Birch", "Ash,Birch", 0, "Ash|Birch",
                        "no candidates",
                        "", 0, 2, 0);
                scenario("Ash,Birch,Cedar", "Ash,Birch,Cedar", 0, "Ash|2: Ash > Birch|Cedar",
                        "no candidates",
                        "", 0, 4, 0);
                scenario("Ash,Birch,Cedar", "Ash,Birch", 0, "Ash > Birch|2: Ash|Cedar",
                        "Round 1: Cedar 1 | active 1 | win Cedar",
                        "Cedar", 0, 3, 1);
            });

            Check.test("threshold", () -> {
                scenario("Ash,Birch,Cedar,Dogwood", "", 20, "5: Ash|3: Birch > Ash|2: Cedar > Birch|Dogwood > Cedar > Ash",
                        "Round 1: Ash 5, Birch 3, Cedar 2, Dogwood 1 | active 11 | out Cedar, Dogwood\nRound 2: Ash 6, Birch 5 | active 11 | win Ash",
                        "Ash,Birch,Cedar,Dogwood", 0, 0, 1);
                scenario("Ash,Birch,Cedar,Dogwood", "", 20, "5: Ash|3: Birch > Ash|2: Cedar > Birch",
                        "Round 1: Ash 5, Birch 3, Cedar 2, Dogwood 0 | active 10 | out Dogwood\nRound 2: Ash 5, Birch 3, Cedar 2 | active 10 | out Cedar\nRound 3: Ash 5, Birch 5 | active 10 | out Birch\nRound 4: Ash 8 | active 8 | win Ash",
                        "Ash,Birch,Cedar,Dogwood", 0, 2, 8);
                scenario("Ash,Birch,Cedar,Dogwood", "", 21, "5: Ash|3: Birch > Ash|2: Cedar > Birch",
                        "Round 1: Ash 5, Birch 3, Cedar 2, Dogwood 0 | active 10 | out Cedar, Dogwood\nRound 2: Ash 5, Birch 5 | active 10 | out Birch\nRound 3: Ash 8 | active 8 | win Ash",
                        "Ash,Birch,Cedar,Dogwood", 0, 2, 8);
                scenario("Ash,Birch,Cedar,Dogwood", "", 0, "5: Ash|3: Birch > Ash|2: Cedar > Birch",
                        "Round 1: Ash 5, Birch 3, Cedar 2, Dogwood 0 | active 10 | out Dogwood\nRound 2: Ash 5, Birch 3, Cedar 2 | active 10 | out Cedar\nRound 3: Ash 5, Birch 5 | active 10 | out Birch\nRound 4: Ash 8 | active 8 | win Ash",
                        "Ash,Birch,Cedar,Dogwood", 0, 2, 8);
                scenario("Ash,Birch,Cedar", "", 40, "4: Ash|3: Birch|3: Cedar",
                        "Round 1: Ash 4, Birch 3, Cedar 3 | active 10 | out Birch, Cedar\nRound 2: Ash 4 | active 4 | win Ash",
                        "Ash,Birch,Cedar", 0, 6, 4);
                scenario("Ash,Birch,Cedar", "", 100, "4: Ash|3: Birch|3: Cedar",
                        "Round 1: Ash 4, Birch 3, Cedar 3 | active 10 | out Cedar\nRound 2: Ash 4, Birch 3 | active 7 | win Ash",
                        "Ash,Birch,Cedar", 0, 3, 1);
                scenario("Ash,Birch,Cedar", "", 35, "4: Ash|3: Birch > Cedar|3: Cedar > Birch",
                        "Round 1: Ash 4, Birch 3, Cedar 3 | active 10 | out Birch, Cedar\nRound 2: Ash 4 | active 4 | win Ash",
                        "Ash,Birch,Cedar", 0, 6, 4);
                scenario("Ash,Birch,Cedar,Dogwood", "", 25, "6: Ash|5: Birch > Ash|2: Cedar > Birch|1: Dogwood > Cedar",
                        "Round 1: Ash 6, Birch 5, Cedar 2, Dogwood 1 | active 14 | out Cedar, Dogwood\nRound 2: Birch 7, Ash 6 | active 13 | win Birch",
                        "Birch,Ash,Cedar,Dogwood", 0, 1, 1);
                scenario("Ash,Birch,Cedar,Dogwood", "", 10, "3: Ash|3: Birch|2: Cedar > Birch|1: Dogwood > Cedar|2: Cedar > Ash > Birch",
                        "Round 1: Cedar 4, Ash 3, Birch 3, Dogwood 1 | active 11 | out Dogwood\nRound 2: Cedar 5, Ash 3, Birch 3 | active 11 | out Birch\nRound 3: Cedar 5, Ash 3 | active 8 | win Cedar",
                        "Cedar,Ash,Birch,Dogwood", 0, 3, 2);
                scenario("Ash,Birch,Cedar", "", 100, "Ash|Birch",
                        "Round 1: Ash 1, Birch 1, Cedar 0 | active 2 | out Cedar\nRound 2: Ash 1, Birch 1 | active 2 | out Birch\nRound 3: Ash 1 | active 1 | win Ash",
                        "Ash,Birch,Cedar", 0, 1, 1);
                scenario("Ash,Birch,Cedar", "", 30, "6: Ash|2: Birch|2: Cedar",
                        "Round 1: Ash 6, Birch 2, Cedar 2 | active 10 | win Ash",
                        "Ash,Birch,Cedar", 0, 0, 4);
            });

            Check.test("count can be repeated and sees later ballots", () -> {
                Election e = Election.of("Ash,Birch,Cedar", "Ash > Birch", "Birch", "Cedar > Birch");
                String once = e.count().summary();
                Check.eq("Round 1: Ash 1, Birch 1, Cedar 1 | active 3 | out Cedar\nRound 2: Birch 2, Ash 1 | active 3 | win Birch", once);
                Check.eq(once, e.count().summary());
                e.add("3: Ash");
                Check.eq("Round 1: Ash 4, Birch 1, Cedar 1 | active 6 | win Ash", e.count().summary());
                e.withdraw("Ash");
                Check.eq("Round 1: Birch 2, Cedar 1 | active 3 | win Birch", e.count().summary());
            });

            Check.test("round details", () -> {
                Result r = Election.of("Ash,Birch,Cedar,Dogwood", "4: Ash > Birch", "3: Birch > Ash", "2: Cedar > Birch > Ash", "2: Dogwood > Cedar > Birch").count();
                Check.eq(3, r.rounds().size());
                Round r1 = r.rounds().get(0);
                Check.eq(11, r1.active());
                Check.eq(4, r1.tallies().get("Ash"));
                Check.eq(3, r1.tallies().get("Birch"));
                Check.eq(2, r1.tallies().get("Cedar"));
                Check.eq(2, r1.tallies().get("Dogwood"));
                Check.eq(names("Ash", "Birch", "Cedar", "Dogwood"), new ArrayList<>(r1.tallies().keySet()));
                Check.eq(names("Dogwood"), r1.eliminated());
                Check.eq(null, r1.winner());
                Round r2 = r.rounds().get(1);
                Check.eq(11, r2.active());
                Check.eq(4, r2.tallies().get("Ash"));
                Check.eq(3, r2.tallies().get("Birch"));
                Check.eq(4, r2.tallies().get("Cedar"));
                Check.eq(names("Ash", "Birch", "Cedar"), new ArrayList<>(r2.tallies().keySet()));
                Check.eq(names("Birch"), r2.eliminated());
                Check.eq(null, r2.winner());
                Round r3 = r.rounds().get(2);
                Check.eq(11, r3.active());
                Check.eq(7, r3.tallies().get("Ash"));
                Check.eq(4, r3.tallies().get("Cedar"));
                Check.eq(names("Ash", "Cedar"), new ArrayList<>(r3.tallies().keySet()));
                Check.eq(names(), r3.eliminated());
                Check.eq("Ash", r3.winner());
                Check.eq("Ash", r.winner());
            });

            Check.test("round details with a threshold", () -> {
                Result r = Election.of("Ash,Birch,Cedar,Dogwood,Elm", "3: Ash > Elm", "3: Birch", "2: Cedar > Birch", "2: Dogwood > Cedar", "Elm").count();
                Check.eq(4, r.rounds().size());
                Round r1 = r.rounds().get(0);
                Check.eq(11, r1.active());
                Check.eq(3, r1.tallies().get("Ash"));
                Check.eq(3, r1.tallies().get("Birch"));
                Check.eq(2, r1.tallies().get("Cedar"));
                Check.eq(2, r1.tallies().get("Dogwood"));
                Check.eq(1, r1.tallies().get("Elm"));
                Check.eq(names("Ash", "Birch", "Cedar", "Dogwood", "Elm"), new ArrayList<>(r1.tallies().keySet()));
                Check.eq(names("Elm"), r1.eliminated());
                Check.eq(null, r1.winner());
                Round r2 = r.rounds().get(1);
                Check.eq(10, r2.active());
                Check.eq(3, r2.tallies().get("Ash"));
                Check.eq(3, r2.tallies().get("Birch"));
                Check.eq(2, r2.tallies().get("Cedar"));
                Check.eq(2, r2.tallies().get("Dogwood"));
                Check.eq(names("Ash", "Birch", "Cedar", "Dogwood"), new ArrayList<>(r2.tallies().keySet()));
                Check.eq(names("Dogwood"), r2.eliminated());
                Check.eq(null, r2.winner());
                Round r3 = r.rounds().get(2);
                Check.eq(10, r3.active());
                Check.eq(3, r3.tallies().get("Ash"));
                Check.eq(3, r3.tallies().get("Birch"));
                Check.eq(4, r3.tallies().get("Cedar"));
                Check.eq(names("Ash", "Birch", "Cedar"), new ArrayList<>(r3.tallies().keySet()));
                Check.eq(names("Birch"), r3.eliminated());
                Check.eq(null, r3.winner());
                Round r4 = r.rounds().get(3);
                Check.eq(7, r4.active());
                Check.eq(3, r4.tallies().get("Ash"));
                Check.eq(4, r4.tallies().get("Cedar"));
                Check.eq(names("Ash", "Cedar"), new ArrayList<>(r4.tallies().keySet()));
                Check.eq(names(), r4.eliminated());
                Check.eq("Cedar", r4.winner());
                Check.eq("Cedar", r.winner());
            });

            Check.test("blank and exhausted ballots", () -> {
                scenario("Ash,Birch", "", 0, "Ash|Zed| |2: |3:|Birch > Zed",
                        "Round 1: Ash 1, Birch 1 | active 2 | out Birch\nRound 2: Ash 1 | active 1 | win Ash",
                        "Ash,Birch", 7, 1, 1);
                scenario("Ash,Birch,Cedar", "Cedar", 0, "Ash|Birch|Cedar|2: Cedar|Zed > Yew|3: Zed",
                        "Round 1: Ash 1, Birch 1 | active 2 | out Birch\nRound 2: Ash 1 | active 1 | win Ash",
                        "Ash,Birch", 4, 4, 1);
                scenario("Ash,Birch,Cedar", "Cedar", 0, "4: Cedar|Ash|Birch|Zed",
                        "Round 1: Ash 1, Birch 1 | active 2 | out Birch\nRound 2: Ash 1 | active 1 | win Ash",
                        "Ash,Birch", 1, 5, 1);
                scenario("Ash,Birch,Cedar", "Cedar", 0, "2: Ash > Birch|Birch > Cedar|Cedar|Cedar",
                        "Round 1: Ash 2, Birch 1 | active 3 | win Ash",
                        "Ash,Birch", 0, 2, 1);
                scenario("Ash,Birch,Cedar,Dogwood", "", 0, "3: Ash|2: Birch|2: Cedar|Dogwood|4: Cedar > Dogwood|Ash > Birch",
                        "Round 1: Cedar 6, Ash 4, Birch 2, Dogwood 1 | active 13 | out Dogwood\nRound 2: Cedar 6, Ash 4, Birch 2 | active 12 | out Birch\nRound 3: Cedar 6, Ash 4 | active 10 | win Cedar",
                        "Cedar,Ash,Birch,Dogwood", 0, 3, 2);
            });

            Check.test("no winner", () -> {
                scenario("Ash,Birch,Cedar", "", 0, "",
                        "Round 1: Ash 0, Birch 0, Cedar 0 | active 0",
                        "", 0, 0, 0);
                scenario("Ash,Birch,Cedar", "", 0, "Zed|3: Yew > Zed",
                        "Round 1: Ash 0, Birch 0, Cedar 0 | active 0",
                        "", 4, 0, 0);
                scenario("Ash,Birch,Cedar", "Ash", 0, "Ash|3: Ash > Cedar",
                        "Round 1: Cedar 3, Birch 0 | active 3 | win Cedar",
                        "Cedar,Birch", 0, 1, 3);
                scenario("Ash,Birch,Cedar", "Ash", 0, "2: Ash|Zed",
                        "Round 1: Birch 0, Cedar 0 | active 0",
                        "", 1, 2, 0);
            });

            Check.test("order and margin", () -> {
                scenario("Ash,Birch,Cedar,Dogwood,Elm", "", 0, "5: Ash > Elm|4: Birch > Ash|3: Cedar > Birch|2: Dogwood > Cedar|1: Elm > Dogwood|2: Zed",
                        "Round 1: Ash 5, Birch 4, Cedar 3, Dogwood 2, Elm 1 | active 15 | out Elm\nRound 2: Ash 5, Birch 4, Cedar 3, Dogwood 3 | active 15 | out Dogwood\nRound 3: Ash 5, Cedar 5, Birch 4 | active 14 | out Birch\nRound 4: Ash 9, Cedar 5 | active 14 | win Ash",
                        "Ash,Cedar,Birch,Dogwood,Elm", 2, 1, 4);
                scenario("Ash,Birch,Cedar,Dogwood,Elm,Fir", "", 15, "6: Ash > Fir|5: Birch > Ash|4: Cedar|3: Dogwood > Elm|3: Elm > Dogwood|1: Fir",
                        "Round 1: Ash 6, Birch 5, Cedar 4, Dogwood 3, Elm 3, Fir 1 | active 22 | out Dogwood, Elm, Fir\nRound 2: Ash 6, Birch 5, Cedar 4 | active 15 | out Cedar\nRound 3: Ash 6, Birch 5 | active 11 | win Ash",
                        "Ash,Birch,Cedar,Dogwood,Elm,Fir", 0, 11, 1);
                scenario("Ash,Birch,Cedar,Dogwood,Elm,Fir", "Cedar", 0, "6: Ash > Fir|5: Birch > Ash|4: Cedar|3: Dogwood > Elm|3: Elm > Dogwood|1: Fir",
                        "Round 1: Ash 6, Birch 5, Dogwood 3, Elm 3, Fir 1 | active 18 | out Fir\nRound 2: Ash 6, Birch 5, Dogwood 3, Elm 3 | active 17 | out Elm\nRound 3: Ash 6, Dogwood 6, Birch 5 | active 17 | out Birch\nRound 4: Ash 11, Dogwood 6 | active 17 | win Ash",
                        "Ash,Dogwood,Birch,Elm,Fir", 0, 5, 5);
                scenario("Ash,Birch,Cedar", "", 0, "3: Ash|3: Birch|3: Cedar",
                        "Round 1: Ash 3, Birch 3, Cedar 3 | active 9 | out Cedar\nRound 2: Ash 3, Birch 3 | active 6 | out Birch\nRound 3: Ash 3 | active 3 | win Ash",
                        "Ash,Birch,Cedar", 0, 6, 3);
            });

            Check.test("Round.share", () -> {
                Round r;
                r = Election.of("Ash,Birch,Cedar", "4: Ash", "3: Birch", "2: Cedar").count().rounds().get(0);
                Check.eq("44.4%", r.share("Ash"));
                Check.eq("33.3%", r.share("Birch"));
                Check.eq("22.2%", r.share("Cedar"));
                r = Election.of("Ash,Birch", "Ash", "15: Birch").count().rounds().get(0);
                Check.eq("6.3%", r.share("Ash"));
                Check.eq("93.8%", r.share("Birch"));
                r = Election.of("Ash,Birch,Cedar", "Ash", "7: Birch", "Cedar > Birch").count().rounds().get(0);
                Check.eq("11.1%", r.share("Ash"));
                Check.eq("77.8%", r.share("Birch"));
                Check.eq("11.1%", r.share("Cedar"));
                r = Election.of("Ash,Birch,Cedar", "1: Ash", "199: Birch").count().rounds().get(0);
                Check.eq("0.5%", r.share("Ash"));
                Check.eq("99.5%", r.share("Birch"));
                Check.eq("0.0%", r.share("Cedar"));
                r = Election.of("Ash,Birch", "3: Ash", "5: Birch").count().rounds().get(0);
                Check.eq("37.5%", r.share("Ash"));
                Check.eq("62.5%", r.share("Birch"));
                r = Election.of("Ash,Birch", "Ash", "7: Birch").count().rounds().get(0);
                Check.eq("12.5%", r.share("Ash"));
                Check.eq("87.5%", r.share("Birch"));
                r = Election.of("Ash,Birch,Cedar", "Ash", "Birch", "Birch").count().rounds().get(0);
                Check.eq("33.3%", r.share("Ash"));
                Check.eq("66.7%", r.share("Birch"));
                Check.eq("0.0%", r.share("Cedar"));
                r = Election.of("Ash,Birch", "Zed").count().rounds().get(0);
                Check.eq("0.0%", r.share("Ash"));
                Check.eq("0.0%", r.share("Birch"));
                Round last = Election.of("Ash,Birch,Cedar", "4: Ash", "3: Birch", "2: Cedar").count().rounds().get(0);
                Check.raises(IllegalArgumentException.class, () -> last.share("Dogwood"));
                Check.raises(IllegalArgumentException.class, () -> last.share(""));
            });

            Check.test("mixed elections 1", () -> {
                scenario("Ash,Birch,Cedar", "", 15, "1: Birch > Cedar > Ash|2: birch|2: Cedar > Birch > Ash|3: ash|3: Cedar|2: Ash > Cedar|3: Ash > Birch > Cedar|3: Ash|2: Birch > Ash > Cedar|3: Cedar > Ash|4: Cedar > Birch",
                        "Round 1: Cedar 12, Ash 11, Birch 5 | active 28 | out Birch\nRound 2: Ash 13, Cedar 13 | active 26 | out Ash\nRound 3: Cedar 20 | active 20 | win Cedar",
                        "Cedar,Ash,Birch", 0, 8, 20);
                scenario("Ash,Birch,Cedar,Dogwood,Elm", "", 10, " |2: Dogwood > Ash > cedar > dogwood|2: |2: Elm > Dogwood|4: |3: ash > Dogwood > ash|4: cedar > Cedar|2: Birch > Ash",
                        "Round 1: Cedar 4, Ash 3, Birch 2, Dogwood 2, Elm 2 | active 13 | out Elm\nRound 2: Cedar 4, Dogwood 4, Ash 3, Birch 2 | active 13 | out Birch\nRound 3: Ash 5, Cedar 4, Dogwood 4 | active 13 | out Dogwood\nRound 4: Ash 7, Cedar 4 | active 11 | win Ash",
                        "Ash,Cedar,Dogwood,Birch,Elm", 7, 2, 3);
                scenario("Ash,Birch,Cedar,Dogwood,Elm", "", 30, "2: Ash|Cedar > Elm > Birch > ash > Dogwood|1: Ash > Elm > Birch|2: Elm > Birch > Ash > Dogwood|4: Zed > cedar|2: Ash > Elm > Birch|1: Elm|3: Cedar",
                        "Round 1: Cedar 8, Ash 5, Elm 3, Birch 0, Dogwood 0 | active 16 | out Birch, Dogwood, Elm\nRound 2: Cedar 8, Ash 7 | active 15 | win Cedar",
                        "Cedar,Ash,Elm,Birch,Dogwood", 0, 1, 1);
                scenario("Ash,Birch,Cedar,Dogwood,Elm", "", 0, "3: Dogwood > Elm > ash|3: |1: |4: Elm|4: cedar|2: |1: Birch > Elm > Cedar > Ash > Dogwood|2: Ash > Cedar > Birch|2: ",
                        "Round 1: Cedar 4, Elm 4, Dogwood 3, Ash 2, Birch 1 | active 14 | out Birch\nRound 2: Elm 5, Cedar 4, Dogwood 3, Ash 2 | active 14 | out Ash\nRound 3: Cedar 6, Elm 5, Dogwood 3 | active 14 | out Dogwood\nRound 4: Elm 8, Cedar 6 | active 14 | win Elm",
                        "Elm,Cedar,Dogwood,Ash,Birch", 8, 0, 2);
                scenario("Ash,Birch,Cedar,Dogwood,Elm", "Elm", 20, "2: Dogwood > elm|Birch > Dogwood > Elm|Birch > Ash > Dogwood > Cedar|4: Dogwood > birch > Cedar > Elm > Ash|2: Elm > Ash|2: Dogwood > Cedar > Birch > Elm|3: Birch|1: Cedar > Elm|birch > Ash > Dogwood > Cedar|Dogwood > Birch|4: Ash > Ash > birch|dogwood > Birch > Ash > Cedar|1: ",
                        "Round 1: Dogwood 10, Ash 6, Birch 6, Cedar 1 | active 23 | out Cedar\nRound 2: Dogwood 10, Ash 6, Birch 6 | active 22 | out Birch\nRound 3: Dogwood 11, Ash 8 | active 19 | win Dogwood",
                        "Dogwood,Ash,Birch,Cedar", 1, 4, 3);
            });

            Check.test("mixed elections 2", () -> {
                scenario("Ash,Birch,Cedar,Dogwood,Elm", "", 10, "4: Birch > Elm|Ash|1: Cedar| |4: Dogwood > Birch > elm > Ash|3: Birch > Ash > Dogwood|Ash > Birch > Dogwood > Elm|3: Cedar > Dogwood|Birch > Elm > Ash",
                        "Round 1: Birch 8, Cedar 4, Dogwood 4, Ash 2, Elm 0 | active 18 | out Elm\nRound 2: Birch 8, Cedar 4, Dogwood 4, Ash 2 | active 18 | out Ash\nRound 3: Birch 9, Cedar 4, Dogwood 4 | active 17 | win Birch",
                        "Birch,Cedar,Dogwood,Ash,Elm", 1, 1, 5);
                scenario("Ash,Birch,Cedar,Dogwood,Elm,Fir", "", 0, "4: Dogwood > Elm > Cedar|fir > Cedar > Dogwood > Ash > Elm|2: |3: |2: cedar > Birch|2: Ash > fir|4: Elm > Fir > Birch > Cedar|3: Fir > Elm > Dogwood|Birch > Ash > Elm > dogwood > cedar > Fir|3: ",
                        "Round 1: Dogwood 4, Elm 4, Fir 4, Ash 2, Cedar 2, Birch 1 | active 17 | out Birch\nRound 2: Dogwood 4, Elm 4, Fir 4, Ash 3, Cedar 2 | active 17 | out Cedar\nRound 3: Dogwood 4, Elm 4, Fir 4, Ash 3 | active 15 | out Ash\nRound 4: Fir 6, Elm 5, Dogwood 4 | active 15 | out Dogwood\nRound 5: Elm 9, Fir 6 | active 15 | win Elm",
                        "Elm,Fir,Dogwood,Ash,Cedar,Birch", 8, 2, 3);
                scenario("Ash,Birch,Cedar,Dogwood,Elm", "", 0, "2: Elm > Birch > Dogwood|Dogwood > Birch| |Cedar > Elm > Birch > Ash|2: Dogwood > Cedar| |2: Ash > Ash > Ash > Birch|3: |1: Birch|2: Ash > Elm > Birch > Cedar|1: Birch",
                        "Round 1: Ash 4, Dogwood 3, Birch 2, Elm 2, Cedar 1 | active 12 | out Cedar\nRound 2: Ash 4, Dogwood 3, Elm 3, Birch 2 | active 12 | out Birch\nRound 3: Ash 4, Dogwood 3, Elm 3 | active 10 | out Elm\nRound 4: Ash 5, Dogwood 5 | active 10 | out Dogwood\nRound 5: Ash 5 | active 5 | win Ash",
                        "Ash,Dogwood,Elm,Birch,Cedar", 5, 7, 5);
                scenario("Ash,Birch,Cedar,Dogwood,Elm", "Ash", 0, "4: Dogwood > Cedar > Cedar > dogwood > Dogwood|Ash > Birch > Dogwood > elm > cedar|Birch > Elm|Elm > Cedar > Ash > Ash > cedar|2: Elm > birch|1: Birch > Dogwood > Cedar|4: Elm > Cedar > Ash > Dogwood > Birch|3: Birch > Elm > Cedar|Birch > Birch > Elm",
                        "Round 1: Birch 7, Elm 7, Dogwood 4, Cedar 0 | active 18 | out Cedar\nRound 2: Birch 7, Elm 7, Dogwood 4 | active 18 | out Dogwood\nRound 3: Birch 7, Elm 7 | active 14 | out Elm\nRound 4: Birch 13 | active 13 | win Birch",
                        "Birch,Elm,Dogwood,Cedar", 0, 5, 13);
                scenario("Ash,Birch,Cedar,Dogwood,Elm", "", 10, "1: |4: Ash > Elm > birch|4: elm > Cedar|Ash > Elm|3: Cedar > Elm > Ash > Birch > dogwood|2: Cedar > Ash > Dogwood > Elm > Birch|3: Elm|4: Dogwood > Cedar > Ash|3: Elm|4: Dogwood",
                        "Round 1: Elm 10, Dogwood 8, Ash 5, Cedar 5, Birch 0 | active 28 | out Birch\nRound 2: Elm 10, Dogwood 8, Ash 5, Cedar 5 | active 28 | out Cedar\nRound 3: Elm 13, Dogwood 8, Ash 7 | active 28 | out Ash\nRound 4: Elm 18, Dogwood 10 | active 28 | win Elm",
                        "Elm,Dogwood,Ash,Cedar,Birch", 1, 0, 8);
            });

            Check.test("mixed elections 3", () -> {
                scenario("Ash,Birch,Cedar,Dogwood", "", 30, "2: Dogwood > Birch > Ash|4: Cedar > Zed|Ash > Cedar > Dogwood|Zed|2: cedar > Birch| |4: |3: Birch > Cedar|2: Dogwood > Ash > Cedar|4: Birch|4: Ash|Ash > Cedar > Birch",
                        "Round 1: Birch 7, Ash 6, Cedar 6, Dogwood 4 | active 23 | out Ash, Cedar, Dogwood\nRound 2: Birch 12 | active 12 | win Birch",
                        "Birch,Ash,Cedar,Dogwood", 6, 11, 12);
                scenario("Ash,Birch,Cedar,Dogwood", "", 0, "3: Cedar|Cedar > Birch > Dogwood > Ash|1: |4: |3: Dogwood > Zed > Cedar > Ash > Dogwood|2: |Ash",
                        "Round 1: Cedar 4, Dogwood 3, Ash 1, Birch 0 | active 8 | out Birch\nRound 2: Cedar 4, Dogwood 3, Ash 1 | active 8 | out Ash\nRound 3: Cedar 4, Dogwood 3 | active 7 | win Cedar",
                        "Cedar,Dogwood,Ash,Birch", 7, 1, 1);
                scenario("Ash,Birch,Cedar,Dogwood,Elm,Fir", "Birch", 0, "Dogwood > Ash > Fir > elm|elm > Cedar > Fir > Dogwood > Ash|3: Cedar > Birch > Dogwood > Cedar > Elm|Birch > dogwood > Ash > Cedar > Elm|4: | |Birch > Fir > Ash > dogwood > cedar > Elm|2: Cedar > Fir|1: Cedar > Elm > Fir > Ash > Dogwood > ash",
                        "Round 1: Cedar 6, Dogwood 2, Elm 1, Fir 1, Ash 0 | active 10 | win Cedar",
                        "Cedar,Dogwood,Elm,Fir,Ash", 5, 0, 4);
                scenario("Ash,Birch,Cedar,Dogwood,Elm,Fir", "", 15, "3: Birch > Elm > Fir| |3: |Birch > dogwood|Dogwood > Birch > Birch > Birch > Dogwood|Birch > Fir > Elm > ash|1: Elm > Birch > Fir > Ash|Ash > Birch > Zed|Cedar > fir > Birch > Ash > Elm",
                        "Round 1: Birch 5, Ash 1, Cedar 1, Dogwood 1, Elm 1, Fir 0 | active 9 | win Birch",
                        "Birch,Ash,Cedar,Dogwood,Elm,Fir", 4, 0, 4);
                scenario("Ash,Birch,Cedar,Dogwood,Elm", "", 15, "4: Birch > Ash|Cedar > Dogwood > Birch > Elm|Elm|Dogwood > Cedar > Dogwood > Dogwood| |2: |Elm > Dogwood|2: Elm > ash|2: Ash > Elm > Birch|3: |Cedar > Ash > Birch > Elm > Ash",
                        "Round 1: Birch 4, Elm 4, Ash 2, Cedar 2, Dogwood 1 | active 13 | out Dogwood\nRound 2: Birch 4, Elm 4, Cedar 3, Ash 2 | active 13 | out Ash\nRound 3: Elm 6, Birch 4, Cedar 3 | active 13 | out Cedar\nRound 4: Birch 6, Elm 6 | active 12 | out Elm\nRound 5: Birch 8 | active 8 | win Birch",
                        "Birch,Elm,Cedar,Ash,Dogwood", 6, 5, 8);
            });
        }
    }
''')

LIB = Lib(
    name="ballotcount", lang="java", title="the ballotcount library",
    blurb="The members' club picks its committee chair by ranked ballots; the counting is done with ballotcount.",
    files={
        "src/vote/Ballot.java": BALLOT, "src/vote/Round.java": ROUND, "src/vote/Result.java": RESULT, "src/vote/Election.java": ELECTION,
        "README.md": README, ".gitignore": "build/\n",
    },
    visible_tests={"test/Check.java": JAVA_CHECK, "test/BasicTests.java": BASIC, "test/TestMain.java": java_test_main("BasicTests")},
    hidden_tests={"test/FullTests.java": FULL, "test/TestMain.java": java_test_main("BasicTests", "FullTests")},
    mutate=["src/vote/Election.java", "src/vote/Round.java", "src/vote/Result.java", "src/vote/Ballot.java"], difficulty=4,
    tags=["voting", "ranked-choice", "tie-breaking"],
    probe_import="import vote.*;",
    probes=[
        "Ballot.parse(\"3: Ash > Birch\").weight()",
        "Ballot.parse(\"  12 :  x>y  \").ranking()",
        "Ballot.parse(\"Ash > > Birch >\").ranking()",
        "Ballot.parse(\"2:\").ranking()",
        "Ballot.parse(\"0: Ash\").weight()",
        "Ballot.parse(\"1.5: Ash\").weight()",
        "Election.of(\"Ash,Birch,Cedar\", \"3: Ash\", \"4: Birch\", \"2: Cedar > Ash\").count().summary()",
        "Election.of(\"Ash,Birch\", \"Ash\", \"Ash\", \"Birch\", \"Birch\").count().summary()",
        "Election.of(\"Ash,Birch,Cedar\", \"ash > ASH > cedar\", \"Zed\", \"3:\").count().blank()",
        "Election.of(\"A,B,C\", \"3: A\", \"3: B\", \"3: C\").count().order()",
        "Election.of(\"A,B,C\", \"3: A\", \"3: B\", \"3: C\").count().rounds().get(0).share(\"A\")",
    ],
)

register_libs([LIB], n=8)
