"""Ordering bugs: multi-key sorts, comparators, ties and ranks. Library holds (python), shelf listings (js), file lists (java)."""
from fx import dd, family
from generators.fix._hand_kit import Base, Bug, tasks_from

# ------------------------------------------------------------------------------------------------------------------
# Base A (python): a library's hold queue and a points table.
# ------------------------------------------------------------------------------------------------------------------

A_README = dd('''
    # holds

    Ordering rules of a public library's reservation system.

    ## `holds.ranking.queue_order(holds)`
    `holds` is a list of dicts `{"member": "m12", "tier": "gold" | "silver" | "basic", "at": <minutes>, "title": ...}`.
    The queue is ordered by **tier** (gold, then silver, then basic), then by **earliest `at`**, then by the **number** in
    the member id (`m9` before `m10`). A new list is returned; the input is not modified.

    ## `holds.ranking.rank_table(scores)`
    `scores` maps member to points. Higher points rank first; members with equal points **share a rank** and the next rank
    is skipped (points 90, 80, 80, 70 give ranks 1, 2, 2, 4). Returns `{member: rank}`.

    ## `holds.ranking.top(scores, n)`
    The members whose rank is at most `n` (so everybody tied at the cut-off is included), ordered by rank and then by
    member name.

    ## `holds.ranking.median(values)`
    The median of a list of numbers (the mean of the two middle values for an even count); the input is not modified;
    an empty list is a `ValueError`.
''')

A_RANKING = dd('''
    TIER_RANK = {"gold": 0, "silver": 1, "basic": 2}


    def member_number(member):
        return int(member[1:])


    def queue_order(holds):
        return sorted(holds, key=lambda h: (TIER_RANK[h["tier"]], h["at"], member_number(h["member"])))


    def rank_table(scores):
        ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        ranks = {}
        previous = None
        rank = 0
        for position, (member, points) in enumerate(ordered, start=1):
            if points != previous:
                rank = position
                previous = points
            ranks[member] = rank
        return ranks


    def top(scores, n):
        ranks = rank_table(scores)
        chosen = [m for m, r in ranks.items() if r <= n]
        return sorted(chosen, key=lambda m: (ranks[m], m))


    def median(values):
        if not values:
            raise ValueError("median of nothing")
        ordered = sorted(values)
        mid = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[mid]
        return (ordered[mid - 1] + ordered[mid]) / 2
''')

A_VISIBLE = {
    "tests/test_ranking.py": dd('''
        import unittest

        from holds.ranking import median, queue_order, rank_table, top


        def hold(member, tier, at):
            return {"member": member, "tier": tier, "at": at, "title": "t"}


        class RankingTests(unittest.TestCase):
            def test_tiers_first(self):
                q = queue_order([hold("m1", "basic", 1), hold("m2", "gold", 9), hold("m3", "silver", 5)])
                self.assertEqual([h["member"] for h in q], ["m2", "m3", "m1"])

            def test_rank_table(self):
                self.assertEqual(rank_table({"a": 90, "b": 80, "c": 70}), {"a": 1, "b": 2, "c": 3})

            def test_median_of_sorted_list(self):
                self.assertEqual(median([1, 2, 3]), 2)

            def test_top(self):
                self.assertEqual(top({"a": 3, "b": 2, "c": 1}, 2), ["a", "b"])


        if __name__ == "__main__":
            unittest.main()
    '''),
}

A_HIDDEN = {
    "tests/test_hidden_ranking.py": dd('''
        import copy
        import unittest

        from holds.ranking import median, queue_order, rank_table, top


        def hold(member, tier, at):
            return {"member": member, "tier": tier, "at": at, "title": f"book for {member}"}


        def members(q):
            return [h["member"] for h in q]


        class QueueOrder(unittest.TestCase):
            def test_tier_then_time_then_member_number(self):
                holds = [hold("m10", "gold", 100), hold("m9", "gold", 100), hold("m3", "gold", 50), hold("m4", "silver", 10),
                         hold("m5", "basic", 1), hold("m6", "silver", 20), hold("m7", "basic", 0), hold("m2", "gold", 200)]
                self.assertEqual(members(queue_order(holds)), ["m3", "m9", "m10", "m2", "m4", "m6", "m7", "m5"])

            def test_earlier_requests_come_first_within_a_tier(self):
                holds = [hold("m1", "silver", 30), hold("m2", "silver", 10), hold("m3", "silver", 20)]
                self.assertEqual(members(queue_order(holds)), ["m2", "m3", "m1"])

            def test_input_is_untouched_and_a_new_list_is_returned(self):
                holds = [hold("m2", "basic", 5), hold("m1", "gold", 9)]
                before = copy.deepcopy(holds)
                out = queue_order(holds)
                self.assertEqual(holds, before)
                self.assertIsNot(out, holds)

            def test_empty_and_single(self):
                self.assertEqual(queue_order([]), [])
                self.assertEqual(members(queue_order([hold("m1", "basic", 1)])), ["m1"])

            def test_big_member_numbers(self):
                holds = [hold("m100", "basic", 1), hold("m20", "basic", 1), hold("m3", "basic", 1)]
                self.assertEqual(members(queue_order(holds)), ["m3", "m20", "m100"])


        class Ranks(unittest.TestCase):
            def test_competition_ranking(self):
                scores = {"ann": 90, "bob": 80, "cy": 80, "dee": 70}
                self.assertEqual(rank_table(scores), {"ann": 1, "bob": 2, "cy": 2, "dee": 4})

            def test_everyone_tied(self):
                self.assertEqual(rank_table({"a": 5, "b": 5, "c": 5}), {"a": 1, "b": 1, "c": 1})

            def test_two_groups_of_ties(self):
                scores = {"a": 10, "b": 10, "c": 10, "d": 7, "e": 7, "f": 1}
                self.assertEqual(rank_table(scores), {"a": 1, "b": 1, "c": 1, "d": 4, "e": 4, "f": 6})

            def test_empty(self):
                self.assertEqual(rank_table({}), {})

            def test_top_includes_everyone_tied_at_the_cut(self):
                scores = {"ann": 90, "bob": 80, "cy": 80, "dee": 70, "eve": 60}
                self.assertEqual(top(scores, 2), ["ann", "bob", "cy"])
                self.assertEqual(top(scores, 1), ["ann"])
                self.assertEqual(top(scores, 3), ["ann", "bob", "cy"])
                self.assertEqual(top(scores, 4), ["ann", "bob", "cy", "dee"])
                self.assertEqual(top(scores, 99), ["ann", "bob", "cy", "dee", "eve"])
                self.assertEqual(top(scores, 0), [])

            def test_top_orders_by_rank_then_name(self):
                scores = {"zed": 5, "amy": 5, "kim": 9}
                self.assertEqual(top(scores, 2), ["kim", "amy", "zed"])


        class Median(unittest.TestCase):
            def test_unsorted_input(self):
                self.assertEqual(median([9, 1, 5]), 5)
                self.assertEqual(median([4, 1, 3, 2]), 2.5)
                self.assertEqual(median([10, 9]), 9.5)
                self.assertEqual(median([7]), 7)

            def test_input_is_not_modified(self):
                values = [3, 1, 2]
                median(values)
                self.assertEqual(values, [3, 1, 2])

            def test_empty(self):
                with self.assertRaises(ValueError):
                    median([])


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _a_prompts():
    p = {}
    p["reverse"] = lambda c: (
        "The hold queue shows the newest requests first inside each tier: the gold member who asked last week is behind the one "
        "who asked this morning, though the tiers themselves are in the right order. Here is a reproduction from the shell:\n\n```\n"
        + c.probe("from holds.ranking import queue_order\nq = queue_order([{'member': 'm1', 'tier': 'gold', 'at': 5, 'title': 'x'}, "
                  "{'member': 'm2', 'tier': 'gold', 'at': 9, 'title': 'y'}])\nprint([h['member'] for h in q])\n")[1]
        + "\n```\n(m1 asked at 5, m2 at 9, so m1 should be first.)"
    )
    p["text-order"] = (
        "When two gold members asked in the same minute, member m10 is served before m9. The tie-break is supposed to be the "
        "member number. It is the kind of thing that only shows up once the member ids reach two digits."
    )
    p["chained"] = (
        "The queue ignores tiers whenever the timestamps differ: a basic member who asked at 1 is ahead of a gold member who "
        "asked at 5. The code sorts several times, once per criterion, and I do not trust that."
    )
    p["dense"] = lambda c: (
        "The points table ranks 90, 80, 80, 70 as "
        + c.probe("from holds.ranking import rank_table\nprint(sorted(rank_table({'ann': 90, 'bob': 80, 'cy': 80, 'dee': 70}).values()))\n")[1]
        + " but our league rules (printed on the leaflet) skip a rank after a tie: 1, 2, 2, 4. Please fix `rank_table`."
    )
    p["top-ties"] = (
        "\"Top 3 readers\" shows only three names even when the third place is shared, so somebody who is exactly as good as "
        "the third reader is left out of the newsletter. The ranking rules say everyone tied at the cut-off is included."
    )
    p["median"] = (
        "The median waiting time on the dashboard changes when I reload, because it depends on the order in which the waits "
        "were collected. For the waits 9, 1 and 5 minutes it says 1, not 5."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "holds/__init__.py": '"""Hold queue ordering."""\n', "holds/ranking.py": A_RANKING}
    r = "holds/ranking.py"
    bugs = [
        Bug("median-of-unsorted", 1, {r: [("    ordered = sorted(values)\n    mid = len(ordered) // 2\n", "    ordered = list(values)\n    mid = len(ordered) // 2\n")]}, P["median"]),
        Bug("member-compared-as-text", 2, {r: [("    return sorted(holds, key=lambda h: (TIER_RANK[h[\"tier\"]], h[\"at\"], member_number(h[\"member\"])))\n",
                                                "    return sorted(holds, key=lambda h: (TIER_RANK[h[\"tier\"]], h[\"at\"], h[\"member\"]))\n")]}, P["text-order"]),
        Bug("reverse-flips-time", 2, {r: [("    return sorted(holds, key=lambda h: (TIER_RANK[h[\"tier\"]], h[\"at\"], member_number(h[\"member\"])))\n",
                                           "    return sorted(holds, key=lambda h: (-TIER_RANK[h[\"tier\"]], h[\"at\"], member_number(h[\"member\"])), reverse=True)\n")]}, P["reverse"]),
        Bug("one-sort-per-criterion", 3, {r: [("    return sorted(holds, key=lambda h: (TIER_RANK[h[\"tier\"]], h[\"at\"], member_number(h[\"member\"])))\n",
                                               "    out = sorted(holds, key=lambda h: TIER_RANK[h[\"tier\"]])\n    out = sorted(out, key=lambda h: h[\"at\"])\n    return sorted(out, key=lambda h: member_number(h[\"member\"]))\n")]}, P["chained"]),
        Bug("dense-ranks", 2, {r: [("            rank = position\n", "            rank += 1\n")]}, P["dense"]),
        Bug("top-cuts-ties", 4, {r: [("    ranks = rank_table(scores)\n    chosen = [m for m, r in ranks.items() if r <= n]\n    return sorted(chosen, key=lambda m: (ranks[m], m))\n",
                                      "    ranks = rank_table(scores)\n    ordered = sorted(ranks, key=lambda m: (ranks[m], m))\n    return ordered[:n]\n")]}, P["top-ties"]),
    ]
    return Base("holds", "python", good, A_VISIBLE, A_HIDDEN, bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base B (javascript): sorting helpers of a shop's listing page.
# ------------------------------------------------------------------------------------------------------------------

B_README = dd('''
    # shelfsort

    Sorting helpers for a shop's product listing (CommonJS). Products are `{ name, price }`; `price` may be missing
    (`undefined` or `null`).

    * `nameCompare(a, b)`: case-insensitive comparison of two names; names that differ only in case are ordered by plain
      code unit order (so `Apple` comes before `apple`).
    * `sortBy(items, keys)`: a **new** array (the input is never reordered), sorted by `keys`, an array such as
      `['-price', 'name']`: the first key is the most significant, a leading `-` means descending. Strings are compared with
      `nameCompare`, numbers numerically. Items with a missing value for a key go **last** for that key, whatever the
      direction. Items that are equal on every key keep their input order.
    * `median(numbers)`: numeric median (mean of the two middle values for an even count); the input is not reordered; `NaN`
      for an empty array.
''')

B_SORT = dd('''
    'use strict';

    function nameCompare(a, b) {
      const la = a.toLowerCase();
      const lb = b.toLowerCase();
      if (la !== lb) return la < lb ? -1 : 1;
      return a < b ? -1 : a > b ? 1 : 0;
    }

    function missing(v) {
      return v === undefined || v === null;
    }

    function compareValues(a, b) {
      if (typeof a === 'string' && typeof b === 'string') return nameCompare(a, b);
      return a < b ? -1 : a > b ? 1 : 0;
    }

    function sortBy(items, keys) {
      const specs = keys.map((k) => (k.startsWith('-') ? { key: k.slice(1), dir: -1 } : { key: k, dir: 1 }));
      return [...items].sort((x, y) => {
        for (const { key, dir } of specs) {
          const a = x[key];
          const b = y[key];
          if (missing(a) && missing(b)) continue;
          if (missing(a)) return 1;
          if (missing(b)) return -1;
          const c = compareValues(a, b);
          if (c !== 0) return c * dir;
        }
        return 0;
      });
    }

    function median(numbers) {
      if (numbers.length === 0) return NaN;
      const sorted = [...numbers].sort((a, b) => a - b);
      const mid = Math.floor(sorted.length / 2);
      return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
    }

    module.exports = { nameCompare, sortBy, median };
''')

B_VISIBLE = {
    "test/sort.test.js": dd('''
        const test = require('node:test');
        const assert = require('node:assert');
        const { sortBy, median, nameCompare } = require('../src/sort');

        test('sort by price then name', () => {
          const items = [{ name: 'b', price: 2 }, { name: 'a', price: 2 }, { name: 'c', price: 1 }];
          assert.deepStrictEqual(sortBy(items, ['price', 'name']).map((i) => i.name), ['c', 'a', 'b']);
        });

        test('median', () => {
          assert.strictEqual(median([1, 2, 3]), 2);
          assert.ok(Number.isNaN(median([])));
        });

        test('name compare', () => {
          assert.ok(nameCompare('a', 'b') < 0);
        });
    '''),
}

B_HIDDEN = {
    "test/hidden_sort.test.js": dd('''
        const test = require('node:test');
        const assert = require('node:assert');
        const { sortBy, median, nameCompare } = require('../src/sort');

        const names = (items) => items.map((i) => i.name);

        test('median needs a numeric sort', () => {
          assert.strictEqual(median([10, 9, 100]), 10);
          assert.strictEqual(median([5, 25, 100, 1]), 15);
          assert.strictEqual(median([3]), 3);
          assert.strictEqual(median([-5, -20, 0]), -5);
        });

        test('median leaves its input alone', () => {
          const input = [3, 1, 2];
          median(input);
          assert.deepStrictEqual(input, [3, 1, 2]);
        });

        test('sortBy returns a new array and does not reorder the input', () => {
          const items = [{ name: 'b', price: 2 }, { name: 'a', price: 1 }];
          const out = sortBy(items, ['price']);
          assert.deepStrictEqual(names(items), ['b', 'a']);
          assert.notStrictEqual(out, items);
          assert.deepStrictEqual(names(out), ['a', 'b']);
        });

        test('missing prices go last in both directions', () => {
          const items = [{ name: 'x' }, { name: 'a', price: 5 }, { name: 'y', price: null }, { name: 'b', price: 1 }, { name: 'c', price: 9 }];
          assert.deepStrictEqual(names(sortBy(items, ['price'])), ['b', 'a', 'c', 'x', 'y']);
          assert.deepStrictEqual(names(sortBy(items, ['-price'])), ['c', 'a', 'b', 'x', 'y']);
        });

        test('each key has its own direction', () => {
          const items = [
            { name: 'pear', price: 3 }, { name: 'fig', price: 3 }, { name: 'apple', price: 7 },
            { name: 'Banana', price: 7 }, { name: 'kiwi', price: 1 },
          ];
          assert.deepStrictEqual(names(sortBy(items, ['-price', 'name'])), ['apple', 'Banana', 'fig', 'pear', 'kiwi']);
          assert.deepStrictEqual(names(sortBy(items, ['price', '-name'])), ['kiwi', 'pear', 'fig', 'Banana', 'apple']);
        });

        test('the first key is the most significant', () => {
          const items = [{ name: 'a', price: 9 }, { name: 'b', price: 1 }, { name: 'c', price: 5 }, { name: 'd', price: 1 }];
          assert.deepStrictEqual(names(sortBy(items, ['price', 'name'])), ['b', 'd', 'c', 'a']);
          assert.deepStrictEqual(names(sortBy(items, ['name'])), ['a', 'b', 'c', 'd']);
        });

        test('ties on every key keep the input order', () => {
          const items = [{ name: 'same', price: 1, id: 1 }, { name: 'same', price: 1, id: 2 }, { name: 'same', price: 1, id: 3 }];
          assert.deepStrictEqual(sortBy(items, ['price', 'name']).map((i) => i.id), [1, 2, 3]);
          assert.deepStrictEqual(sortBy(items, []).map((i) => i.id), [1, 2, 3]);
        });

        test('names ignore case, ties go by code unit order', () => {
          assert.ok(nameCompare('apple', 'Banana') < 0);
          assert.ok(nameCompare('Apple', 'apple') < 0);
          assert.ok(nameCompare('apple', 'Apple') > 0);
          assert.strictEqual(nameCompare('x', 'x'), 0);
          const items = [{ name: 'banana' }, { name: 'Apple' }, { name: 'cherry' }, { name: 'apple' }, { name: 'Banana' }];
          assert.deepStrictEqual(names(sortBy(items, ['name'])), ['Apple', 'apple', 'Banana', 'banana', 'cherry']);
        });
    '''),
}


def _b_prompts():
    p = {}
    p["median-lex"] = (
        "The listing's \"typical price\" is nonsense when prices have different numbers of digits: for the prices 5, 25, 100 and 1 it "
        "reports 62.5 instead of 15, and for 10, 9 and 100 it reports 100 instead of 10. It looks like the numbers are "
        "sorted as text."
    )
    p["mutates"] = (
        "After the listing page sorts the products, the same array that the cart module holds is reordered too, and the "
        "\"recently added\" strip shows products in price order. Our sort helper must not touch its input."
    )
    p["missing-first"] = (
        "Products without a price (not yet priced) jump around: sometimes first, sometimes in the middle of the price-sorted "
        "list. They should always be at the end, both for ascending and for descending price order."
    )
    p["dir-all"] = (
        "Sorting by `['-price', 'name']` should give the most expensive first, and *within the same price* names A to Z. We get "
        "the names Z to A inside each price. The README says every key has its own direction."
    )
    p["two-pass"] = (
        "The category page sorted by `['price', 'name']` looks sorted by name only, price seems to be ignored unless names "
        "are equal. Ties on price are fine, but it is as if the last key were the most significant."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "src/sort.js": B_SORT, "package.json": '{\n  "name": "shelfsort",\n  "version": "1.0.0",\n  "private": true\n}\n'}
    s = "src/sort.js"
    bugs = [
        Bug("median-sorted-as-text", 1, {s: [("  const sorted = [...numbers].sort((a, b) => a - b);\n", "  const sorted = [...numbers].sort();\n")]}, P["median-lex"]),
        Bug("sort-mutates-input", 1, {s: [("  return [...items].sort((x, y) => {\n", "  return items.sort((x, y) => {\n")]}, P["mutates"]),
        Bug("missing-values-compare-as-nan", 3, {s: [("      if (missing(a) && missing(b)) continue;\n      if (missing(a)) return 1;\n      if (missing(b)) return -1;\n",
                                                      "      if (missing(a) && missing(b)) continue;\n")]}, P["missing-first"]),
        Bug("first-direction-for-all-keys", 3, {s: [("  const specs = keys.map((k) => (k.startsWith('-') ? { key: k.slice(1), dir: -1 } : { key: k, dir: 1 }));\n",
                                                     "  const dir0 = keys.length && keys[0].startsWith('-') ? -1 : 1;\n  const specs = keys.map((k) => ({ key: k.replace(/^-/, ''), dir: dir0 }));\n")]}, P["dir-all"]),
        Bug("one-pass-per-key", 4, {s: [(
            "  return [...items].sort((x, y) => {\n    for (const { key, dir } of specs) {\n      const a = x[key];\n      const b = y[key];\n      if (missing(a) && missing(b)) continue;\n      if (missing(a)) return 1;\n      if (missing(b)) return -1;\n      const c = compareValues(a, b);\n      if (c !== 0) return c * dir;\n    }\n    return 0;\n  });\n",
            "  let out = [...items];\n  for (const { key, dir } of specs) {\n    out = out.sort((x, y) => {\n      const a = x[key];\n      const b = y[key];\n      if (missing(a) && missing(b)) return 0;\n      if (missing(a)) return 1;\n      if (missing(b)) return -1;\n      return compareValues(a, b) * dir;\n    });\n  }\n  return out;\n")]}, P["two-pass"]),
    ]
    return Base("shelfsort", "javascript", good, B_VISIBLE, B_HIDDEN, bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base C (java): ordering of a directory listing.
# ------------------------------------------------------------------------------------------------------------------

C_README = dd('''
    # filelist

    Ordering of a directory listing in a file manager (plain Java). `Listing.Entry` is a record `(String name, long size)`.

    * `Listing.compareNames(a, b)`: case-insensitive, names that differ only in case are ordered by plain `compareTo`
      (`"Readme"` before `"readme"`).
    * `Listing.bySize(entries)`: a new list ordered by size ascending, ties by `compareNames` on the name. Sizes can be any
      `long` (files over 4 GB are normal).
    * `Listing.distinct(entries)`: the entries ordered like `bySize`, with exact duplicates (same name **and** same size)
      removed; two different files of the same size are both kept.
''')

C_LISTING = dd('''
    package filelist;

    import java.util.ArrayList;
    import java.util.Collection;
    import java.util.Comparator;
    import java.util.List;
    import java.util.TreeSet;

    public final class Listing {
        private Listing() {}

        public record Entry(String name, long size) {}

        public static int compareNames(String a, String b) {
            int c = a.compareToIgnoreCase(b);
            return c != 0 ? c : a.compareTo(b);
        }

        private static final Comparator<Entry> ORDER = (a, b) -> {
            int c = Long.compare(a.size(), b.size());
            return c != 0 ? c : compareNames(a.name(), b.name());
        };

        public static List<Entry> bySize(List<Entry> entries) {
            List<Entry> out = new ArrayList<>(entries);
            out.sort(ORDER);
            return out;
        }

        public static List<Entry> distinct(Collection<Entry> entries) {
            TreeSet<Entry> set = new TreeSet<>(ORDER);
            set.addAll(entries);
            return new ArrayList<>(set);
        }
    }
''')

C_VISIBLE = {
    "tests/TestMain.java": dd('''
        import filelist.Listing;
        import filelist.Listing.Entry;
        import java.util.List;

        public class TestMain {
            public static void main(String[] args) {
                List<Entry> sorted = Listing.bySize(List.of(new Entry("b", 20), new Entry("a", 10)));
                if (!sorted.get(0).name().equals("a")) {
                    System.out.println("FAIL: smallest first");
                    System.exit(1);
                }
                if (Listing.compareNames("a", "b") >= 0) {
                    System.out.println("FAIL: a < b");
                    System.exit(1);
                }
                System.out.println("all checks passed");
            }
        }
    '''),
}

C_HIDDEN = {
    "tests/TestMain.java": dd('''
        import filelist.Listing;
        import filelist.Listing.Entry;
        import java.util.ArrayList;
        import java.util.List;
        import java.util.Objects;

        public class TestMain {
            static int failures = 0;

            static void check(String what, Object got, Object want) {
                if (!Objects.equals(got, want)) {
                    failures++;
                    System.out.println("FAIL " + what + ": got " + got + ", want " + want);
                }
            }

            static List<String> names(List<Entry> es) {
                List<String> out = new ArrayList<>();
                for (Entry e : es) {
                    out.add(e.name());
                }
                return out;
            }

            public static void main(String[] args) {
                List<Entry> huge = List.of(new Entry("movie.mkv", 6_000_000_000L), new Entry("note.txt", 12), new Entry("iso.img", 3_000_000_000L),
                        new Entry("empty", 0), new Entry("mid", 4_294_967_296L));
                check("sizes beyond int", names(Listing.bySize(huge)), List.of("empty", "note.txt", "iso.img", "mid", "movie.mkv"));

                List<Entry> wrap = List.of(new Entry("big", 3_000_000_000L), new Entry("small", 1));
                check("difference overflows int", names(Listing.bySize(wrap)), List.of("small", "big"));
                List<Entry> wrap2 = List.of(new Entry("small", 1), new Entry("big", 5_000_000_000L));
                check("difference overflows int 2", names(Listing.bySize(wrap2)), List.of("small", "big"));

                List<Entry> ties = List.of(new Entry("b.txt", 5), new Entry("a.txt", 5), new Entry("A.txt", 5), new Entry("c.txt", 1));
                check("ties by name", names(Listing.bySize(ties)), List.of("c.txt", "A.txt", "a.txt", "b.txt"));

                check("input unchanged", names(ties), List.of("b.txt", "a.txt", "A.txt", "c.txt"));
                check("empty", Listing.bySize(List.of()), List.of());

                check("compareNames ignores case", Listing.compareNames("apple", "Banana") < 0, true);
                check("compareNames case tie", Listing.compareNames("Readme", "readme") < 0, true);
                check("compareNames equal", Listing.compareNames("x", "x"), 0);
                check("compareNames upper first only on a tie", Listing.compareNames("Zed", "apple") > 0, true);

                List<Entry> dups = List.of(new Entry("a", 5), new Entry("b", 5), new Entry("a", 5), new Entry("c", 7), new Entry("b", 6), new Entry("B", 5));
                List<Entry> d = Listing.distinct(dups);
                check("distinct keeps different files of equal size", names(d), List.of("a", "B", "b", "b", "c"));
                check("distinct sizes", d.stream().map(Entry::size).toList(), List.of(5L, 5L, 5L, 6L, 7L));
                check("distinct of nothing", Listing.distinct(List.of()), List.of());

                if (failures > 0) {
                    System.out.println(failures + " check(s) failed");
                    System.exit(1);
                }
                System.out.println("all checks passed");
            }
        }
    '''),
}


def _c_prompts():
    p = {}
    p["overflow"] = (
        "A directory with a 3 GB image and a tiny file lists the image *first* in the size-sorted view, and with a 5 GB file the order flips "
        "again, so the list looks random once files get big. Small files sort correctly. I'd look at how sizes are compared."
    )
    p["treeset"] = (
        "The \"remove duplicates\" action deleted files it should not: two different files that happen to have the same size "
        "(`a` and `b`, 5 bytes each) came out as one entry. Only exact duplicates (same name and same size) should be merged."
    )
    p["case"] = (
        "In the listing, `Zed` sorts before `apple` when the sizes are equal. Names are supposed to sort ignoring case, and only "
        "names that differ just in case are ordered upper case first."
    )
    return p


def _base_c() -> Base:
    P = _c_prompts()
    good = {"README.md": C_README, "src/filelist/Listing.java": C_LISTING}
    ls = "src/filelist/Listing.java"
    bugs = [
        Bug("size-difference-cast-to-int", 2, {ls: [("        int c = Long.compare(a.size(), b.size());\n", "        int c = (int) (a.size() - b.size());\n")]}, P["overflow"]),
        Bug("distinct-by-size-only", 3, {ls: [("        TreeSet<Entry> set = new TreeSet<>(ORDER);\n", "        TreeSet<Entry> set = new TreeSet<>(Comparator.comparingLong(Entry::size));\n"),
                                              ("        return new ArrayList<>(set);\n", "        List<Entry> out = new ArrayList<>(set);\n        out.sort(ORDER);\n        return out;\n")]}, P["treeset"]),
        Bug("names-compared-case-sensitively", 3, {ls: [("        int c = a.compareToIgnoreCase(b);\n        return c != 0 ? c : a.compareTo(b);\n", "        return a.compareTo(b);\n")]}, P["case"]),
    ]
    return Base("filelist", "java", good, C_VISIBLE, C_HIDDEN, bugs)


@family("fix-hand-sort-order", category="fix", lang="python", kind="fix", n=14,
        summary="ordering: multi-key sorts, comparators, ties and ranks (python hold queue, js listing helpers, java file lists)")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b(), _base_c()])
