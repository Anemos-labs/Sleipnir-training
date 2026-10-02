"""Java: list scans that should be hash lookups, string building by +=, and repeated calls to an expensive collaborator.
Equality/hash/compare calls are counted on a Key class, allocation with ThreadMXBean, calls with counting collaborators; counters carry a budget."""
from __future__ import annotations

import json
from string import Template

from fx import Task, family, merged, run

from ._kit import prove_opt

BUILD = "rm -rf build && mkdir -p build && javac -d build $(find . -name '*.java')"
J_ALL = BUILD + " && java -cp build TestMain"
J_CORRECT = BUILD + " && java -cp build TestMain correct"
J_PERF = BUILD + " && java -cp build TestMain perf"

COUNTING = '''import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.List;

/** Counters with a budget, a Key whose equals/hashCode/compareTo are counted, and an allocation meter. */
public final class Counting {
    public static long ops;
    public static long budget = -1;

    public static class BudgetExceeded extends RuntimeException {
        public BudgetExceeded() {
            super("budget exceeded", null, false, false);
        }
    }

    public static void reset(long b) {
        ops = 0;
        budget = b;
    }

    public static void tick() {
        ops++;
        if (budget >= 0 && ops > budget) {
            throw new BudgetExceeded();
        }
    }

    public static final class Key implements Comparable<Key> {
        public final int v;

        public Key(int v) {
            this.v = v;
        }

        @Override
        public boolean equals(Object o) {
            tick();
            return o instanceof Key && ((Key) o).v == v;
        }

        @Override
        public int hashCode() {
            tick();
            return Integer.hashCode(v);
        }

        @Override
        public int compareTo(Key o) {
            tick();
            return Integer.compare(v, o.v);
        }

        @Override
        public String toString() {
            return "K" + v;
        }
    }

    public static List<Key> keys(int[] values) {
        List<Key> out = new ArrayList<>();
        for (int x : values) {
            out.add(new Key(x));
        }
        return out;
    }

    public static List<Integer> plain(List<Key> keys) {
        List<Integer> out = new ArrayList<>();
        for (Key k : keys) {
            out.add(k.v);
        }
        return out;
    }

    public static long allocatedBytes() {
        com.sun.management.ThreadMXBean bean = (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
        return bean.getThreadAllocatedBytes(Thread.currentThread().getId());
    }
}
'''

TESTMAIN = '''public class TestMain {
    public static void main(String[] args) {
        String mode = args.length > 0 ? args[0] : "all";
        int failures = 0;
        if (!mode.equals("perf")) {
            failures += ExampleTest.run() + BehaviourTest.run();
        }
        if (!mode.equals("correct")) {
            failures += PerfTest.run();
        }
        if (failures > 0) {
            System.out.println(failures + " failing checks");
            System.exit(1);
        }
        System.out.println("all checks passed");
    }
}
'''

# --- shapes ----------------------------------------------------------------------------------------------------------
LIST_SHAPES = {
    "dedupe": dict(
        d=1, sig="public static <T> List<T> $f(List<T> $a)", imports_naive="java.util.ArrayList\njava.util.List", imports_fast="java.util.ArrayList\njava.util.LinkedHashSet\njava.util.List",
        naive='''public static <T> List<T> $f(List<T> $a) {
        List<T> out = new ArrayList<>();
        for (T item : $a) {
            if (!out.contains(item)) {
                out.add(item);
            }
        }
        return out;
    }''', fast='''public static <T> List<T> $f(List<T> $a) {
        return new ArrayList<>(new LinkedHashSet<>($a));
    }''', nargs=1, limit="30 * n", n=1500,
        call="Ops.$f(L)", oracle_body="List<Integer> out = new ArrayList<>(); java.util.Set<Integer> seen = new java.util.HashSet<>(); for (int x : A) { if (seen.add(x)) out.add(x); } return out;",
        spec="Returns the items of `{a}` in order of first appearance, without repeats (items have `equals`/`hashCode`).",
        vocab=[("uniquePlates", ["plates"], "Licence plates seen at the gate, each once."), ("distinctTags", ["tags"], "Tags used in a photo set, each once."), ("firstSeenHosts", ["hosts"], "Host names in order of first appearance.")]),
    "intersect": dict(
        d=1, sig="public static <T> List<T> $f(List<T> $a, List<T> $b)", imports_naive="java.util.ArrayList\njava.util.List", imports_fast="java.util.ArrayList\njava.util.HashSet\njava.util.List\njava.util.Set",
        naive='''public static <T> List<T> $f(List<T> $a, List<T> $b) {
        List<T> out = new ArrayList<>();
        for (T item : $a) {
            if ($b.contains(item)) {
                out.add(item);
            }
        }
        return out;
    }''', fast='''public static <T> List<T> $f(List<T> $a, List<T> $b) {
        Set<T> lookup = new HashSet<>($b);
        List<T> out = new ArrayList<>();
        for (T item : $a) {
            if (lookup.contains(item)) {
                out.add(item);
            }
        }
        return out;
    }''', nargs=2, limit="30 * n", n=1200, call="Ops.$f(L, M)",
        oracle_body="java.util.Set<Integer> s = new java.util.HashSet<>(); for (int y : B) s.add(y); List<Integer> out = new ArrayList<>(); for (int x : A) { if (s.contains(x)) out.add(x); } return out;",
        spec="Returns, in the order of `{a}` (repeats included), the items of `{a}` that also occur in `{b}`.",
        vocab=[("repliedGuests", ["invited", "replied"], "Invited guests who have replied."), ("sharedFollowers", ["mine", "theirs"], "Accounts that follow both of us."),
               ("stockedItems", ["wanted", "inStock"], "Wanted items that are in stock.")]),
    "difference": dict(
        d=1, sig="public static <T> List<T> $f(List<T> $a, List<T> $b)", imports_naive="java.util.ArrayList\njava.util.List", imports_fast="java.util.ArrayList\njava.util.HashSet\njava.util.List\njava.util.Set",
        naive='''public static <T> List<T> $f(List<T> $a, List<T> $b) {
        List<T> out = new ArrayList<>();
        for (T item : $a) {
            if (!$b.contains(item)) {
                out.add(item);
            }
        }
        return out;
    }''', fast='''public static <T> List<T> $f(List<T> $a, List<T> $b) {
        Set<T> blockedSet = new HashSet<>($b);
        List<T> out = new ArrayList<>();
        for (T item : $a) {
            if (!blockedSet.contains(item)) {
                out.add(item);
            }
        }
        return out;
    }''', nargs=2, limit="30 * n", n=1200, call="Ops.$f(L, M)",
        oracle_body="java.util.Set<Integer> s = new java.util.HashSet<>(); for (int y : B) s.add(y); List<Integer> out = new ArrayList<>(); for (int x : A) { if (!s.contains(x)) out.add(x); } return out;",
        spec="Returns, in the order of `{a}` (repeats included), the items of `{a}` that do not occur in `{b}`.",
        vocab=[("unsentRecipients", ["recipients", "alreadySent"], "Recipients that have not been mailed yet."), ("missingParts", ["required", "onHand"], "Parts required but not on hand."),
               ("unreviewedFiles", ["changed", "reviewed"], "Changed files nobody has reviewed.")]),
    "repeated": dict(
        d=2, sig="public static <T> List<T> $f(List<T> $a)", imports_naive="java.util.ArrayList\njava.util.Collections\njava.util.List", imports_fast="java.util.ArrayList\njava.util.HashMap\njava.util.LinkedHashMap\njava.util.List\njava.util.Map",
        naive='''public static <T> List<T> $f(List<T> $a) {
        List<T> out = new ArrayList<>();
        for (T item : $a) {
            if (Collections.frequency($a, item) > 1 && !out.contains(item)) {
                out.add(item);
            }
        }
        return out;
    }''', fast='''public static <T> List<T> $f(List<T> $a) {
        Map<T, Integer> counts = new LinkedHashMap<>();
        for (T item : $a) {
            counts.merge(item, 1, Integer::sum);
        }
        List<T> out = new ArrayList<>();
        for (Map.Entry<T, Integer> e : counts.entrySet()) {
            if (e.getValue() > 1) {
                out.add(e.getKey());
            }
        }
        return out;
    }''', nargs=1, limit="30 * n", n=900, call="Ops.$f(L)",
        oracle_body="java.util.Map<Integer, Integer> c = new java.util.LinkedHashMap<>(); for (int x : A) c.merge(x, 1, Integer::sum); List<Integer> out = new ArrayList<>(); for (java.util.Map.Entry<Integer, Integer> e : c.entrySet()) if (e.getValue() > 1) out.add(e.getKey()); return out;",
        spec="Returns the items that occur more than once in `{a}`, each once, in order of first occurrence.",
        vocab=[("duplicateScans", ["scans"], "Barcodes scanned more than once."), ("repeatVisitors", ["visits"], "Visitors who came more than once.")]),
    "positions": dict(
        d=2, sig="public static <T> List<Integer> $f(List<T> $a, List<T> $b)", imports_naive="java.util.ArrayList\njava.util.List", imports_fast="java.util.ArrayList\njava.util.HashMap\njava.util.List\njava.util.Map",
        naive='''public static <T> List<Integer> $f(List<T> $a, List<T> $b) {
        List<Integer> out = new ArrayList<>();
        for (T needle : $b) {
            out.add($a.indexOf(needle));
        }
        return out;
    }''', fast='''public static <T> List<Integer> $f(List<T> $a, List<T> $b) {
        Map<T, Integer> first = new HashMap<>();
        for (int i = 0; i < $a.size(); i++) {
            first.putIfAbsent($a.get(i), i);
        }
        List<Integer> out = new ArrayList<>();
        for (T needle : $b) {
            out.add(first.getOrDefault(needle, -1));
        }
        return out;
    }''', nargs=2, limit="30 * n", n=1200, call="Ops.$f(L, M)",
        oracle_body="java.util.Map<Integer, Integer> first = new java.util.HashMap<>(); for (int i = 0; i < A.length; i++) first.putIfAbsent(A[i], i); List<Integer> out = new ArrayList<>(); for (int x : B) out.add(first.getOrDefault(x, -1)); return out;",
        spec="For every item of `{b}` returns the index of its first occurrence in `{a}`, or -1 when absent; one entry per item of `{b}`, in order.",
        vocab=[("slotNumbers", ["shelf", "requests"], "Shelf slot of every requested book (-1 when absent)."), ("columnIndexes", ["header", "wanted"], "Column index of every wanted column.")]),
}


def _java_call(call, fsubs):
    return Template(call).substitute(fsubs)


def _list_tests(sp, pkg, f, seed):
    """BehaviourTest, PerfTest and ExampleTest for a list shape (items are Key objects counted by Counting)."""
    two = sp["nargs"] == 2
    oracle_sig = "int[] A, int[] B" if two else "int[] A"
    call_keys = sp["call"].replace("$f", f)
    arrs = "A, B" if two else "A"
    gen_small = ("int[] A = rand(r, 25, 12);\n            int[] B = rand(r, 25, 12);\n" if two else "int[] A = rand(r, 25, 12);\n")
    gen_big = ("int[] A = rand(r, N, N);\n        int[] B = rand(r, N, N);\n" if two else "int[] A = rand(r, N, N / 2);\n")
    wrap_lists = ("List<Counting.Key> L = Counting.keys(A);\n            List<Counting.Key> M = Counting.keys(B);\n" if two else "List<Counting.Key> L = Counting.keys(A);\n")
    wrap_lists_big = wrap_lists.replace("            ", "        ")
    result_plain = "Counting.plain(" + call_keys + ")" if sp.get("keys_result", True) else call_keys
    # positions returns List<Integer> (no Key inside)
    if f and sp["sig"].startswith("public static <T> List<Integer>"):
        result_plain = call_keys
    oracle = f"static List<Integer> oracle({oracle_sig}) {{ {sp['oracle_body']} }}"
    common = ("import java.util.ArrayList;\nimport java.util.List;\nimport java.util.Random;\n"
              f"import {pkg}.Ops;\n\n")
    behaviour = (common + "public class BehaviourTest {\n    " + oracle + "\n\n"
                 "    static int[] rand(Random r, int len, int range) {\n        int[] out = new int[r.nextInt(len + 1)];\n        for (int i = 0; i < out.length; i++) {\n            out[i] = r.nextInt(range);\n        }\n        return out;\n    }\n\n"
                 "    static int run() {\n        int failures = 0;\n        Random r = new Random(" + str(seed) + ");\n        for (int t = 0; t < 200; t++) {\n            " + gen_small
                 + "            " + wrap_lists + "            Counting.reset(-1);\n            List<Integer> got = " + result_plain + ";\n            List<Integer> want = oracle(" + arrs + ");\n"
                 "            if (!got.equals(want)) {\n                System.out.println(\"input \" + java.util.Arrays.toString(A) + \": got \" + got + \", want \" + want);\n                failures++;\n            }\n        }\n"
                 "        return failures;\n    }\n}\n")
    perf = (common + "public class PerfTest {\n    " + oracle + "\n\n"
            "    static int[] rand(Random r, int len, int range) {\n        int[] out = new int[len];\n        for (int i = 0; i < out.length; i++) {\n            out[i] = r.nextInt(range);\n        }\n        return out;\n    }\n\n"
            "    static int run() {\n        int N = " + str(sp["n"]) + ";\n        Random r = new Random(" + str(seed) + ");\n        " + gen_big + "        " + wrap_lists_big
            + "        long limit = " + sp["limit"].replace("n", "N") + ";\n        Counting.reset(limit * 20);\n        List<Integer> got;\n        try {\n            got = " + result_plain
            + ";\n        } catch (Counting.BudgetExceeded e) {\n            System.out.println(\"PERF: gave up after \" + Counting.budget + \" equals/hashCode/compareTo calls for \" + N + \" items (limit \" + limit + \"): the code scans lists instead of using hash lookups\");\n            return 1;\n        } finally {\n            Counting.budget = -1;\n        }\n"
            "        long ops = Counting.ops;\n        int failures = 0;\n        if (!got.equals(oracle(" + arrs + "))) {\n            System.out.println(\"result differs from the reference\");\n            failures++;\n        }\n"
            "        if (ops > limit) {\n            System.out.println(\"PERF: \" + ops + \" equals/hashCode/compareTo calls for \" + N + \" items (limit \" + limit + \"): the code scans lists instead of using hash lookups\");\n            failures++;\n        }\n        return failures;\n    }\n}\n")
    return behaviour, perf


EXAMPLES = {
    "dedupe": ("Ops.{f}(Arrays.asList(3, 1, 3, 2, 1))", "Arrays.asList(3, 1, 2)", "Ops.{f}(new ArrayList<Integer>())", "new ArrayList<Integer>()"),
    "intersect": ("Ops.{f}(Arrays.asList(1, 2, 2, 3), Arrays.asList(2, 3, 9))", "Arrays.asList(2, 2, 3)", "Ops.{f}(Arrays.asList(1), new ArrayList<Integer>())", "new ArrayList<Integer>()"),
    "difference": ("Ops.{f}(Arrays.asList(1, 2, 2, 3), Arrays.asList(2))", "Arrays.asList(1, 3)", "Ops.{f}(new ArrayList<Integer>(), Arrays.asList(1))", "new ArrayList<Integer>()"),
    "repeated": ("Ops.{f}(Arrays.asList(5, 1, 5, 2, 1, 5))", "Arrays.asList(5, 1)", "Ops.{f}(Arrays.asList(1, 2, 3))", "new ArrayList<Integer>()"),
    "positions": ("Ops.{f}(Arrays.asList(4, 5, 6, 5), Arrays.asList(5, 9, 4))", "Arrays.asList(1, -1, 0)", "Ops.{f}(new ArrayList<Integer>(), Arrays.asList(1))", "Arrays.asList(-1)"),
}


def _example_test(pkg, shape, f):
    e1, w1, e2, w2 = (x.replace("{f}", f) for x in EXAMPLES[shape])
    return (f"import java.util.ArrayList;\nimport java.util.Arrays;\nimport java.util.List;\nimport {pkg}.Ops;\n\npublic class ExampleTest {{\n    static int run() {{\n        int failures = 0;\n"
            f"        List<Integer> a = {e1};\n        if (!a.equals({w1})) {{\n            System.out.println(\"example 1: got \" + a);\n            failures++;\n        }}\n"
            f"        List<Integer> b = {e2};\n        if (!b.equals({w2})) {{\n            System.out.println(\"example 2: got \" + b);\n            failures++;\n        }}\n        return failures;\n    }}\n}}\n")


def _ops_file(pkg, imports, body, extra=""):
    imps = "".join(f"import {i};\n" for i in sorted(set(x for x in imports.split("\n") if x)))
    return f"package {pkg};\n\n{imps}\n/** Small helpers used by the nightly jobs. */\npublic final class Ops {{\n    private Ops() {{}}\n\n    {body}\n{extra}}}\n"


PROMPTS = [
    "`Ops.{f}` in `src/{pkg}/Ops.java` is quadratic: every element is checked against a whole list. {doc} With the real data (tens of thousands of entries) the nightly job runs for hours. "
    "Fix it without changing what it returns. The README has the contract.",
    "perf: `Ops.{f}` ({pkg}) scans lists inside a loop. {doc} Make it linear in expectation, same results and same order. CI counts equals/hashCode/compareTo calls on the elements.",
    "Our import job slowed down badly since the data grew. Profiling points to `{f}` in `src/{pkg}/Ops.java`: {hint}. {doc} Please fix it; behaviour and signature stay the same.",
]


@family("optimize-java-collections", category="optimize", lang="java", kind="feature", n=10,
        summary="java list scans (contains/indexOf/frequency in loops): equals/hashCode/compareTo calls on tracked keys must grow linearly")
def gen(rng, n):
    order = list(LIST_SHAPES) * 3
    rng.shuffle(order)
    used = set()
    for i in range(n):
        shape = order[i]
        sp = LIST_SHAPES[shape]
        vocab = [v for v in sp["vocab"] if (shape, v[0]) not in used] or sp["vocab"]
        f, argn, doc = rng.choice(vocab)
        used.add((shape, f))
        pkg = rng.choice(["ledgerkit", "roster", "gatehouse", "feedtools", "inventory", "tracking"])
        subs = {"f": f, "a": argn[0], "b": argn[1] if len(argn) > 1 else ""}
        naive = Template(sp["naive"]).substitute(subs)
        fast = Template(sp["fast"]).substitute(subs)
        start_ops = _ops_file(pkg, sp["imports_naive"], naive)
        sol_ops = _ops_file(pkg, sp["imports_fast"], fast)
        spec = sp["spec"].format(a=argn[0], b=argn[1] if len(argn) > 1 else "")
        readme = f"# {pkg}\n\n## `Ops.{f}({', '.join(argn)})`\n\n{doc}\n\n{spec}\n\nThe lists can hold hundreds of thousands of items, so the cost of a call has to grow about linearly with their size.\n"
        seed = 77 + i
        behaviour, perf = _list_tests(sp, pkg, f, seed)
        files = {f"src/{pkg}/Ops.java": start_ops, "README.md": readme, "tests/ExampleTest.java": _example_test(pkg, shape, f)}
        hidden = {"tests/Counting.java": COUNTING, "tests/BehaviourTest.java": behaviour, "tests/PerfTest.java": perf, "tests/TestMain.java": TESTMAIN}
        solution = {f"src/{pkg}/Ops.java": sol_ops}
        prove_opt(f"{shape}/{f}", files, hidden, solution, J_CORRECT, J_PERF, J_ALL, timeout=240)
        hint = {"dedupe": "`contains` on a list for every item", "intersect": "`contains` on a list for every item", "difference": "`contains` on a list for every item",
                "repeated": "`Collections.frequency` for every item", "positions": "`indexOf` on a list for every needle"}[shape]
        prompt = rng.choice(PROMPTS).format(f=f, pkg=pkg, doc=doc, hint=hint)
        yield Task(slug=f"{i + 1:02d}-{shape}-{f.lower()}", prompt=prompt, difficulty=sp["d"], start=files, hidden=hidden, solution=solution, verify=J_ALL, timeout_s=240,
                   tags=["complexity", "hash-lookup", "operation-counter", "java"], notes={"shape": shape, "n": sp["n"]})
