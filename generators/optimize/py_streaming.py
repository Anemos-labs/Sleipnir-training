"""Whole-file loading where streaming would do (python): peak memory is measured with tracemalloc."""
from __future__ import annotations

import json
import random
from string import Template

from fx import Task, family

from ._kit import PY_ALL, PY_CORRECT, PY_PERF, prove_opt

FORMATS = [
    dict(name="csv", sep=",", ki=0, ai=1, cols=3, line='"%s,%d,%s" % (key, amount, rng.choice(["OK", "RETRY", "FAIL"]))', desc="comma separated: `key,amount,status`"),
    dict(name="spaced", sep=" ", ki=1, ai=2, cols=4, line='"%s %s %d %s" % ("2024-03-%02d" % rng.randrange(1, 29), key, amount, rng.choice(["ok", "slow"]))', desc="space separated: `date key amount flag`"),
    dict(name="pipe", sep="|", ki=0, ai=2, cols=4, line='"%s|%s|%d|%s" % (key, rng.choice(["a", "b", "c"]), amount, rng.choice(["x", "y"]))', desc="pipe separated: `key|group|amount|tag`"),
]

SHAPES = {
    "totals": dict(
        d=2, nargs=1, call="$f(src)", fname=["total_bytes_by_host", "spend_per_account", "units_per_sku"],
        naive='''def $f(path):
    """$doc"""
    with open(path) as fh:
        rows = [line.rstrip("\\n").split("$sep") for line in fh.read().splitlines()]
    totals = {}
    for row in rows:
        totals[row[$ki]] = totals.get(row[$ki], 0) + int(row[$ai])
    return totals
''', fast='''def $f(path):
    """$doc"""
    totals = {}
    with open(path) as fh:
        for line in fh:
            row = line.rstrip("\\n").split("$sep")
            totals[row[$ki]] = totals.get(row[$ki], 0) + int(row[$ai])
    return totals
''', oracle='''def oracle(path):
    totals = {}
    with open(path) as fh:
        for line in fh:
            row = line.rstrip("\\n").split("SEP")
            totals[row[KI]] = totals.get(row[KI], 0) + int(row[AI])
    return totals
''', spec="Returns a dict from key to the sum of the amounts of all lines with that key.",
        doc=["Sum the traffic per host over a day's log.", "Total spend per account in a billing export.", "Units shipped per SKU in the warehouse log."]),
    "top": dict(
        d=3, nargs=1, call="$f(src)", fname=["biggest_transfers", "largest_orders", "heaviest_scans"],
        naive='''def $f(path):
    """$doc"""
    with open(path) as fh:
        rows = [line.rstrip("\\n").split("$sep") for line in fh.read().splitlines()]
    numbered = [(int(row[$ai]), number) for number, row in enumerate(rows, 1)]
    numbered.sort(key=lambda pair: (-pair[0], pair[1]))
    return numbered[:5]
''', fast='''import heapq


def $f(path):
    """$doc"""
    def entries():
        with open(path) as fh:
            for number, line in enumerate(fh, 1):
                yield (-int(line.rstrip("\\n").split("$sep")[$ai]), number)

    return [(-negative, number) for negative, number in heapq.nsmallest(5, entries())]
''', oracle='''import heapq


def oracle(path):
    def entries():
        with open(path) as fh:
            for number, line in enumerate(fh, 1):
                yield (-int(line.rstrip("\\n").split("SEP")[AI]), number)

    return [(-a, n) for a, n in heapq.nsmallest(5, entries())]
''', spec="Returns the five largest amounts as `(amount, line number)` pairs (line numbers start at 1), largest first; on equal amounts the earlier line comes first. Fewer pairs if the file has fewer lines.",
        doc=["The five biggest transfers in the log.", "The five largest orders of the export.", "The five heaviest scans of the day."]),
    "convert": dict(
        d=3, nargs=2, call="$f(src, dst)", fname=["rewrite_export", "normalise_feed", "convert_log"],
        naive='''def $f(src, dst):
    """$doc"""
    with open(src) as fh:
        lines = fh.read().splitlines()
    out = []
    for line in lines:
        row = line.split("$sep")
        row[$ki] = row[$ki].upper()
        row[$ai] = str(int(row[$ai]) * 2)
        out.append("$sep".join(row))
    with open(dst, "w") as fh:
        fh.write("\\n".join(out) + ("\\n" if out else ""))
    return len(out)
''', fast='''def $f(src, dst):
    """$doc"""
    count = 0
    with open(src) as fin, open(dst, "w") as fout:
        for line in fin:
            row = line.rstrip("\\n").split("$sep")
            row[$ki] = row[$ki].upper()
            row[$ai] = str(int(row[$ai]) * 2)
            fout.write("$sep".join(row) + "\\n")
            count += 1
    return count
''', oracle='''def oracle(src, dst):
    count = 0
    with open(src) as fin, open(dst, "w") as fout:
        for line in fin:
            row = line.rstrip("\\n").split("SEP")
            row[KI] = row[KI].upper()
            row[AI] = str(int(row[AI]) * 2)
            fout.write("SEP".join(row) + "\\n")
            count += 1
    return count
''', spec="Copies `src` to `dst` line by line, upper-casing the key column and doubling the amount column; returns the number of lines written. Every output line ends with a newline.",
        doc=["Rewrite the nightly export for the new importer.", "Normalise a partner feed: upper-case keys, double the amounts.", "Convert a log to the new units."]),
    "distinct": dict(
        d=2, nargs=1, call="$f(src)", fname=["distinct_hosts", "active_accounts", "listed_skus"],
        naive='''def $f(path):
    """$doc"""
    with open(path) as fh:
        keys = [line.rstrip("\\n").split("$sep")[$ki] for line in fh.read().splitlines()]
    return sorted(set(keys))
''', fast='''def $f(path):
    """$doc"""
    seen = set()
    with open(path) as fh:
        for line in fh:
            seen.add(line.rstrip("\\n").split("$sep")[$ki])
    return sorted(seen)
''', oracle='''def oracle(path):
    seen = set()
    with open(path) as fh:
        for line in fh:
            seen.add(line.rstrip("\\n").split("SEP")[KI])
    return sorted(seen)
''', spec="Returns the sorted list of distinct keys that occur in the file.",
        doc=["Which hosts appear in the log.", "Which accounts were active in the export.", "Which SKUs show up in the feed."]),
    "run": dict(
        d=3, nargs=1, call="$f(src)", fname=["longest_streak", "longest_same_host", "longest_repeat"],
        naive='''def $f(path):
    """$doc"""
    with open(path) as fh:
        keys = [line.rstrip("\\n").split("$sep")[$ki] for line in fh.read().splitlines()]
    best = (None, 0)
    i = 0
    while i < len(keys):
        j = i
        while j < len(keys) and keys[j] == keys[i]:
            j += 1
        if j - i > best[1]:
            best = (keys[i], j - i)
        i = j
    return best
''', fast='''def $f(path):
    """$doc"""
    best = (None, 0)
    current, length = None, 0
    with open(path) as fh:
        for line in fh:
            key = line.rstrip("\\n").split("$sep")[$ki]
            if key == current:
                length += 1
            else:
                current, length = key, 1
            if length > best[1]:
                best = (current, length)
    return best
''', oracle='''def oracle(path):
    best = (None, 0)
    cur, n = None, 0
    with open(path) as fh:
        for line in fh:
            key = line.rstrip("\\n").split("SEP")[KI]
            if key == cur:
                n += 1
            else:
                cur, n = key, 1
            if n > best[1]:
                best = (cur, n)
    return best
''', spec="Returns `(key, length)` for the longest run of consecutive lines with the same key (the first such run if several are equally long), or `(None, 0)` for an empty file.",
        doc=["The longest stretch of requests from a single host.", "The longest streak of the same account in the export.", "The longest run of one SKU in the feed."]),
    "first": dict(
        d=2, nargs=2, call="$f(src, NEEDLE)", fname=["first_error_line", "find_account_line", "locate_sku"],
        naive='''def $f(path, needle):
    """$doc"""
    with open(path) as fh:
        lines = fh.read().splitlines()
    for number, line in enumerate(lines, 1):
        if needle in line:
            return number
    return 0
''', fast='''def $f(path, needle):
    """$doc"""
    with open(path) as fh:
        for number, line in enumerate(fh, 1):
            if needle in line:
                return number
    return 0
''', oracle='''def oracle(path, needle):
    with open(path) as fh:
        for n, line in enumerate(fh, 1):
            if needle in line:
                return n
    return 0
''', spec="Returns the 1-based number of the first line that contains `needle`, or 0 when no line does.",
        doc=["Line number of the first error in a log.", "Line of the first mention of an account.", "Line where a SKU first occurs."]),
}

PROMPTS = [
    "`{f}` in `{path}` reads the whole file into memory before doing anything, and the log files have grown to gigabytes: the job now gets OOM-killed. {doc} "
    "Rework it to process the file as a stream. It must return exactly what it returns today.",
    "memory: `{f}` ({path}) loads everything with `read()` / a list of all rows. {doc} Make it constant-memory (a few hundred KB regardless of file size), same results.",
    "Our container has a 256 MB limit and `{f}` ({path}) dies on the big files. It slurps the file and builds a list of every line. {doc} Please make it stream. "
    "The CI harness measures peak allocations with tracemalloc on a file of a few hundred thousand lines.",
    "Could you make `{f}` in `{path}` use constant memory? Currently peak memory grows with the file. {doc} Keep the interface and the results.",
]


def _writer(fmt, shape):
    runs = shape == "run"
    body = (
        "def write_data(path, n, rng):\n    keys = ['node' + str(k) for k in range(40)]\n    with open(path, 'w') as fh:\n        i = 0\n        while i < n:\n"
        "            key = rng.choice(keys)\n            for _ in range(rng.randrange(1, 30) if RUNS else 1):\n                if i >= n:\n                    break\n"
        "                amount = rng.randrange(1, 100000)\n                fh.write(LINE + '\\n')\n                i += 1\n")
    return body.replace("RUNS", str(runs)).replace("LINE", fmt["line"])


@family("optimize-py-streaming", category="optimize", lang="python", kind="feature", n=12,
        summary="functions that slurp a whole file instead of streaming: peak memory measured with tracemalloc on a large generated file")
def gen(rng, n):
    order = list(SHAPES) * 3
    rng.shuffle(order)
    for i in range(n):
        shape = order[i]
        sp = SHAPES[shape]
        fmt = FORMATS[i % len(FORMATS)]
        k = rng.randrange(3)
        f = sp["fname"][k]
        doc = sp["doc"][k]
        pkg = rng.choice(["logtools", "exportkit", "feedpipe", "opsreports", "batchio"])
        mod = rng.choice(["reader", "summary", "files", "scan"])
        subs = {"f": f, "doc": doc, "sep": fmt["sep"], "ki": fmt["ki"], "ai": fmt["ai"]}
        naive = Template(sp["naive"]).substitute(subs)
        fast = Template(sp["fast"]).substitute(subs)
        head = f'"""{pkg}: reports over large text files."""\n\n\n'
        start_src = head + naive
        sol_src = head + fast
        readme = (f"# {pkg}\n\nFiles are text, one record per line, {fmt['desc']}. They can be many gigabytes: the jobs run in small containers, so a function "
                  f"must not keep the whole file (or a list of all its lines) in memory.\n\n## `{mod}.{f}({'path' if sp['nargs'] == 1 and shape != 'first' else ('src, dst' if shape == 'convert' else 'path, needle')})`\n\n{doc}\n\n{sp['spec']}\n")
        files = {f"{pkg}/{mod}.py": start_src, f"{pkg}/__init__.py": "", "README.md": readme}
        oracle = sp["oracle"].replace("SEP", fmt["sep"]).replace("KI", str(fmt["ki"])).replace("AI", str(fmt["ai"]))
        writer = _writer(fmt, shape)
        needle_expr = "'node7'"
        call_small = {"totals": f"{f}(src)", "top": f"{f}(src)", "distinct": f"{f}(src)", "run": f"{f}(src)", "first": f"{f}(src, NEEDLE)", "convert": f"{f}(src, dst)"}[shape]
        oracle_call = call_small.replace(f, "oracle")
        base = (f"import os\nimport random\nimport tempfile\nimport tracemalloc\nimport unittest\n\nfrom {pkg}.{mod} import {f}\n\nNEEDLE = {needle_expr}\n\n\n{oracle}\n\n\n{writer}\n")
        seed = 700 + i
        conv_check = ""
        if shape == "convert":
            conv_check = ("\n\ndef read_all(path):\n    with open(path) as fh:\n        return fh.read()\n")
        def check_lines(indent, got_expr):
            pad = " " * indent
            if shape == "convert":
                return (f"{pad}self.assertEqual({got_expr}, {oracle_call.replace('dst', 'dst2')})\n"
                        f"{pad}self.assertEqual(read_all(dst), read_all(dst2))\n")
            return f"{pad}self.assertEqual({got_expr}, {oracle_call})\n"

        small_body = (
            "        rng = random.Random(%d)\n        for trial in range(30):\n            with tempfile.TemporaryDirectory() as d:\n                src = os.path.join(d, 'in.txt')\n"
            "                dst = os.path.join(d, 'out.txt')\n                dst2 = os.path.join(d, 'ref.txt')\n                write_data(src, rng.randrange(0, 60), rng)\n" % seed)
        small_body += check_lines(16, call_small)
        empty_body = ("\n    def test_empty_file(self):\n        with tempfile.TemporaryDirectory() as d:\n            src = os.path.join(d, 'in.txt')\n"
                      "            dst = os.path.join(d, 'out.txt')\n            dst2 = os.path.join(d, 'ref.txt')\n            open(src, 'w').close()\n")
        empty_body += check_lines(12, call_small)
        corr = base + conv_check + "\n\nclass CorrectnessTests(unittest.TestCase):\n    def test_random_files(self):\n" + small_body + empty_body
        limit = 1_000_000
        perf_body = (
            f"        rng = random.Random({seed})\n        with tempfile.TemporaryDirectory() as d:\n            src = os.path.join(d, 'big.txt')\n            dst = os.path.join(d, 'out.txt')\n"
            "            dst2 = os.path.join(d, 'ref.txt')\n            write_data(src, 150000, rng)\n            tracemalloc.start()\n            try:\n"
            f"                got = {call_small}\n                current, peak = tracemalloc.get_traced_memory()\n            finally:\n                tracemalloc.stop()\n")
        perf_body += check_lines(12, "got")
        perf_body += f"            self.assertLessEqual(peak, {limit}, \"PERF: peak memory %d bytes while processing a 150000-line file (limit {limit}): the file is held in memory instead of streamed\" % peak)\n"
        perf = base + conv_check + "\n\nclass PerformanceTests(unittest.TestCase):\n    def test_memory_does_not_grow_with_the_file(self):\n" + perf_body
        # make the 'first' perf case find its needle early: plant it on line 5
        if shape == "first":
            perf = perf.replace("write_data(src, 150000, rng)", "write_data(src, 150000, rng)\n            lines = open(src).read().split('\\n')\n            lines[4] = lines[4] + ' node7x'\n            open(src, 'w').write('\\n'.join(lines))")
        # visible tests: a handful of tiny fixed files
        vr = random.Random(900 + i)
        tiny = []
        ns = {}
        exec(oracle, ns)
        wns = {}
        exec("import random\n" + writer, wns)
        import os
        import tempfile
        case_texts = []
        for t in range(2):
            with tempfile.TemporaryDirectory() as d:
                p = os.path.join(d, "x.txt")
                wns["write_data"](p, 6 + t * 3, vr)
                text = open(p).read()
                if shape == "convert":
                    want = None
                    ns["oracle"](p, os.path.join(d, "y.txt"))
                    want = (6 + t * 3, open(os.path.join(d, "y.txt")).read())
                elif shape == "first":
                    want = ns["oracle"](p, "node7")
                else:
                    want = ns["oracle"](p)
            case_texts.append((text, want))
        vis = f"import os\nimport tempfile\nimport unittest\n\nfrom {pkg}.{mod} import {f}\n\n\nclass BasicTests(unittest.TestCase):\n"
        for t, (text, want) in enumerate(case_texts):
            vis += f"    def test_small_file_{t + 1}(self):\n        text = {text!r}\n        with tempfile.TemporaryDirectory() as d:\n            src = os.path.join(d, 'in.txt')\n            dst = os.path.join(d, 'out.txt')\n            with open(src, 'w') as fh:\n                fh.write(text)\n"
            if shape == "convert":
                vis += f"            self.assertEqual({f}(src, dst), {want[0]!r})\n            with open(dst) as fh:\n                self.assertEqual(fh.read(), {want[1]!r})\n"
            elif shape == "first":
                vis += f"            self.assertEqual({f}(src, 'node7'), {want!r})\n"
            else:
                vis += f"            self.assertEqual({f}(src), {want!r})\n"
        vis += "\n\nif __name__ == '__main__':\n    unittest.main()\n"
        start = {**files, "tests/test_basic.py": vis}
        hidden = {"tests/test_correct_stream.py": corr, "tests/test_perf_stream.py": perf}
        solution = {f"{pkg}/{mod}.py": sol_src}
        prove_opt(f"{shape}/{fmt['name']}", start, hidden, solution, PY_CORRECT, PY_PERF, PY_ALL)
        prompt = rng.choice(PROMPTS).format(f=f, path=f"{pkg}/{mod}.py", doc=doc)
        yield Task(slug=f"{i + 1:02d}-{shape}-{fmt['name']}", prompt=prompt, difficulty=sp["d"], start=start, hidden=hidden, solution=solution, verify=PY_ALL,
                   tags=["streaming", "memory", "tracemalloc"], notes={"shape": shape, "format": fmt["name"], "limit_bytes": limit})
