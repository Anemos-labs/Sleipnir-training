"""Test-style migration inside Python: `unittest.TestCase` suites -> plain functions with `assert`, run by a tiny repo-local runner (`tools/minirun.py`).

Every project is described once as data (modules, test cases written in a small DSL, mutants of the modules). The same DSL renders the original unittest suite and the reference plain suite, so both always
test the same things. A hidden checker proves the migration was done properly: no `unittest.TestCase` left, enough tests, the helpers untouched, the suite passes on the real code and **fails on every mutant**
(which catches dropped or weakened checks), and skips are preserved.
"""
import hashlib
import json
import re

from fx import Task, dd, family

from ._portlib import run_local

# ======================================================================================================================
# the runner and the assertion helpers that every project ships
# ======================================================================================================================

MINIRUN = dd(r'''
"""A very small test runner: plain functions, plain `assert`, fixtures.

usage:  python3 tools/minirun.py [tests_dir]        (default: tests)

* Every `test_*.py` file of the directory is imported (the directory, its parent and this tool's directory are on `sys.path`). Every module-level function whose name starts with `test_` is a test and runs in definition order.
  Classes are ignored.
* A test passes when it returns. An `AssertionError` is a failure, any other exception an error.
* A test may take parameters. Each parameter is the name of a **fixture**: a function marked with `@fixture`, defined in the same test module or in `conftest.py` of the tests directory. A fixture is created again for
  every test (`@fixture(scope="module")`: once per file), may take other fixtures as parameters and may be a generator: the code after its `yield` runs when the test (or, for the module scope, the file) is done.
* `@skip("reason")` skips a test; `@skip_if(condition, "reason")` skips it when the condition is true.
* Output: one line per test, then `N passed, M failed, K skipped`. The exit status is 1 when something failed or when no test was found.
"""
import importlib
import inspect
import os
import sys
import traceback


def fixture(fn=None, *, scope="function"):
    if scope not in ("function", "module"):
        raise ValueError("scope must be 'function' or 'module'")

    def mark(f):
        f.__minirun_fixture__ = scope
        return f

    return mark(fn) if fn is not None else mark


def skip(reason="skipped"):
    def mark(f):
        f.__minirun_skip__ = reason
        return f

    return mark


def skip_if(condition, reason="skipped"):
    return skip(reason) if condition else (lambda f: f)


def _resolve(name, fixtures, module_state, test_state, chain=()):
    for values, _ in (test_state, module_state):
        if name in values:
            return values[name]
    if name not in fixtures:
        raise LookupError("no fixture named %r" % name)
    if name in chain:
        raise LookupError("fixture cycle: " + " -> ".join(chain + (name,)))
    fn = fixtures[name]
    values, finalizers = module_state if fn.__minirun_fixture__ == "module" else test_state
    args = [_resolve(p, fixtures, module_state, test_state, chain + (name,)) for p in inspect.signature(fn).parameters]
    result = fn(*args)
    if inspect.isgenerator(result):
        finalizers.append(result)
        result = next(result)
    values[name] = result
    return result


def _finish(finalizers):
    for gen in reversed(finalizers):
        try:
            next(gen)
        except StopIteration:
            pass


def _fixtures_of(module):
    return {n: f for n, f in vars(module).items() if inspect.isfunction(f) and hasattr(f, "__minirun_fixture__")}


def main(argv):
    tests_dir = os.path.abspath(argv[1] if len(argv) > 1 else "tests")
    here = os.path.dirname(os.path.abspath(__file__))
    sys.dont_write_bytecode = True
    for p in (here, tests_dir, os.path.dirname(tests_dir)):
        sys.path.insert(0, p)
    shared = {}
    if os.path.exists(os.path.join(tests_dir, "conftest.py")):
        shared = _fixtures_of(importlib.import_module("conftest"))
    passed = failed = skipped = 0
    for fname in sorted(n for n in os.listdir(tests_dir) if n.startswith("test_") and n.endswith(".py")):
        module = importlib.import_module(fname[:-3])
        fixtures = dict(shared)
        fixtures.update(_fixtures_of(module))
        tests = [(n, f) for n, f in vars(module).items() if inspect.isfunction(f) and n.startswith("test_") and f.__module__ == module.__name__ and not hasattr(f, "__minirun_fixture__")]
        module_state = ({}, [])
        for name, fn in tests:
            label = "%s::%s" % (fname, name)
            if hasattr(fn, "__minirun_skip__"):
                skipped += 1
                print("skip %s (%s)" % (label, fn.__minirun_skip__))
                continue
            test_state = ({}, [])
            try:
                args = [_resolve(p, fixtures, module_state, test_state) for p in inspect.signature(fn).parameters]
                fn(*args)
                passed += 1
                print("ok   %s" % label)
            except BaseException as exc:  # noqa: BLE001
                failed += 1
                print("FAIL %s: %s: %s" % (label, type(exc).__name__, exc))
                print("".join(traceback.format_exc().splitlines(True)[-4:]), end="")
            finally:
                _finish(test_state[1])
        _finish(module_state[1])
    print("%d passed, %d failed, %d skipped" % (passed, failed, skipped))
    if failed or passed + skipped == 0:
        if passed + skipped == 0:
            print("no tests found")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
''')

ASSERTS = dd(r'''
"""Assertion helpers for plain `assert` tests (the equivalents of the unittest methods that have no one-line `assert`)."""
import contextlib
import re


@contextlib.contextmanager
def raises(exc, match=None):
    """`with raises(ValueError, match="regex"):` passes when the block raises `exc` (and, if given, the message matches the regex)."""
    try:
        yield
    except exc as err:
        if match is not None and not re.search(match, str(err)):
            raise AssertionError("message %r does not match %r" % (str(err), match))
    except BaseException as err:  # noqa: BLE001
        raise AssertionError("expected %s, got %s: %s" % (exc.__name__, type(err).__name__, err))
    else:
        raise AssertionError("did not raise %s" % exc.__name__)


def approx(a, b, places=7):
    """True when `a` and `b` are equal after rounding their difference to `places` decimal places (unittest's assertAlmostEqual)."""
    return a == b or round(abs(a - b), places) == 0


def same_items(a, b):
    """True when both sequences hold the same items the same number of times, in any order (unittest's assertCountEqual)."""
    rest = list(b)
    for item in a:
        try:
            rest.remove(item)
        except ValueError:
            return False
    return not rest
''')

# ======================================================================================================================
# rendering of the DSL
# ======================================================================================================================

U_CALLS = {
    "eq": "assertEqual", "ne": "assertNotEqual", "lt": "assertLess", "le": "assertLessEqual", "gt": "assertGreater", "ge": "assertGreaterEqual",
    "in": "assertIn", "not_in": "assertNotIn", "isinst": "assertIsInstance",
}
P_OPS = {"eq": "==", "ne": "!=", "lt": "<", "le": "<=", "gt": ">", "ge": ">=", "in": "in", "not_in": "not in"}


def _camel(snake):
    return "assert" + "".join(p.capitalize() for p in snake.split("_"))


def _ident_sub(text, names, prefix):
    for n in names:
        text = re.sub(r"(?<![\w.\"'])" + re.escape(n) + r"\b(?!\s*=[^=])", prefix + n, text)
    return text


def _render_stmt(stmt, style, fx, ind):
    """Lines (already indented) for one DSL statement; `fx` are the fixture names visible in the test."""
    pad = "    " * ind
    kind = stmt[0]
    sub = (lambda s: _ident_sub(s, fx, "self.")) if style == "unittest" else (lambda s: s)
    if kind == "code":
        return [pad + sub(stmt[1])]
    if kind == "sub":
        _, var, iterable, body = stmt
        lines = [pad + "for %s in %s:" % (var, sub(iterable))]
        if style == "unittest":
            lines.append(pad + "    with self.subTest(%s=%s):" % (var, var))
            for s in body:
                lines += _render_stmt(s, style, fx, ind + 2)
        else:
            for s in body:
                lines += _render_stmt(s, style, fx, ind + 1)
        return lines
    if kind in ("raises", "raises_re"):
        exc = stmt[1]
        regex = stmt[2] if kind == "raises_re" else None
        code = stmt[-1]
        if style == "unittest":
            head = "with self.assertRaises(%s):" % exc if regex is None else "with self.assertRaisesRegex(%s, %s):" % (exc, json.dumps(regex))
        else:
            head = "with raises(%s):" % exc if regex is None else "with raises(%s, match=%s):" % (exc, json.dumps(regex))
        return [pad + head, pad + "    " + sub(code)]
    if kind == "custom":
        name, args = stmt[1], [sub(a) for a in stmt[2]]
        if style == "unittest":
            return [pad + "self.%s(%s)" % (_camel(name), ", ".join(args))]
        return [pad + "assert_%s(%s)" % (name, ", ".join(args))]
    a = [sub(x) if isinstance(x, str) else x for x in stmt[1:]]
    if style == "unittest":
        if kind in U_CALLS:
            return [pad + "self.%s(%s)" % (U_CALLS[kind], ", ".join(str(x) for x in a))]
        return [pad + _u_other(kind, a)]
    if kind in P_OPS:
        return [pad + "assert %s %s %s" % (a[0], P_OPS[kind], a[1])]
    return [pad + _p_other(kind, a)]


def _u_other(kind, a):
    if kind == "true":
        return "self.assertTrue(%s)" % a[0]
    if kind == "false":
        return "self.assertFalse(%s)" % a[0]
    if kind == "none":
        return "self.assertIsNone(%s)" % a[0]
    if kind == "not_none":
        return "self.assertIsNotNone(%s)" % a[0]
    if kind == "almost":
        return "self.assertAlmostEqual(%s, %s, places=%s)" % (a[0], a[1], a[2])
    if kind == "same":
        return "self.assertCountEqual(%s, %s)" % (a[0], a[1])
    raise ValueError(kind)


def _p_other(kind, a):
    if kind == "true":
        return "assert %s" % a[0]
    if kind == "false":
        return "assert not %s" % a[0]
    if kind == "none":
        return "assert %s is None" % a[0]
    if kind == "not_none":
        return "assert %s is not None" % a[0]
    if kind == "isinst":
        return "assert isinstance(%s, %s)" % (a[0], a[1])
    if kind == "almost":
        return "assert approx(%s, %s, %s)" % (a[0], a[1], a[2])
    if kind == "same":
        return "assert same_items(%s, %s)" % (a[0], a[1])
    raise ValueError(kind)


def _stmt_names(stmts, found):
    for s in stmts:
        if s[0] == "sub":
            _stmt_names(s[3], found)
        elif s[0] == "raises" or s[0] == "raises_re":
            found.add("raises")
        elif s[0] == "almost":
            found.add("approx")
        elif s[0] == "same":
            found.add("same_items")
        elif s[0] == "custom":
            found.add("assert_" + s[1])


def _code_strings(stmts):
    out = []
    for st in stmts:
        if st[0] == "sub":
            out.append(st[2])
            out += _code_strings(st[3])
        elif st[0] == "raises":
            out.append(st[2])
        elif st[0] == "raises_re":
            out.append(st[3])
        elif st[0] == "custom":
            out += list(st[2])
        else:
            out += [x for x in st[1:] if isinstance(x, str)]
    return out


def _fixture_names(spec):
    return [f["name"] for f in spec.get("fixtures", [])]


def render_unittest(spec):
    """The original `tests/<file>`: one TestCase class."""
    fx = _fixture_names(spec)
    lines = ["import unittest"]
    if any(t.get("patches") for t in spec["tests"]):
        lines.append("from unittest import mock")
    lines += spec.get("imports", [])
    if spec.get("support"):
        lines.append("from support import BaseCase")
    lines += ["", ""]
    lines.append("class %s(%s):" % (spec["class"], "BaseCase" if spec.get("support") else "unittest.TestCase"))
    func_fx = [f for f in spec.get("fixtures", []) if f.get("scope", "function") == "function"]
    mod_fx = [f for f in spec.get("fixtures", []) if f.get("scope") == "module"]
    if mod_fx:
        lines.append("    @classmethod")
        lines.append("    def setUpClass(cls):")
        for f in mod_fx:
            lines.append("        cls.%s = %s" % (f["name"], _ident_sub(f["expr"], [x["name"] for x in mod_fx], "cls.")))
        lines.append("")
    if func_fx:
        lines.append("    def setUp(self):")
        for f in func_fx:
            lines.append("        self.%s = %s" % (f["name"], _ident_sub(f["expr"], fx, "self.")))
        lines.append("")
        tear = [f for f in func_fx if f.get("teardown")]
        if tear:
            lines.append("    def tearDown(self):")
            for f in reversed(tear):
                for t in f["teardown"]:
                    lines.append("        " + _ident_sub(t, fx, "self."))
            lines.append("")
    for t in spec["tests"]:
        if t.get("skip"):
            lines.append("    @unittest.skip(%s)" % json.dumps(t["skip"]))
        if t.get("skip_if"):
            lines.append("    @unittest.skipIf(%s, %s)" % (t["skip_if"][0], json.dumps(t["skip_if"][1])))
        for target, new in t.get("patches", []):
            lines.append("    @mock.patch(%s, new=%s)" % (json.dumps(target), new))
        lines.append("    def %s(self):" % t["name"])
        for s in t["body"]:
            lines += _render_stmt(s, "unittest", fx, 2)
        lines.append("")
    lines += ["", 'if __name__ == "__main__":', "    unittest.main()", ""]
    return "\n".join(lines).replace("\n\n\n\n", "\n\n\n")


def render_plain(spec):
    """The reference conversion: plain functions, `assert`, fixtures."""
    fx = _fixture_names(spec)
    used = set()
    for t in spec["tests"]:
        _stmt_names(t["body"], used)
    runner = {"fixture"} if fx else set()
    if any(t.get("skip") for t in spec["tests"]):
        runner.add("skip")
    if any(t.get("skip_if") for t in spec["tests"]):
        runner.add("skip_if")
    lines = []
    if any(t.get("patches") for t in spec["tests"]):
        lines.append("from unittest import mock")
    lines += spec.get("imports", [])
    if runner:
        lines.append("from minirun import " + ", ".join(sorted(runner)))
    helpers = sorted(n for n in used if n in ("raises", "approx", "same_items"))
    if helpers:
        lines.append("from asserts import " + ", ".join(helpers))
    custom = sorted(n for n in used if n.startswith("assert_"))
    if custom:
        lines.append("from support import " + ", ".join(custom))
    lines += ["", ""]
    for f in spec.get("fixtures", []):
        scope = f.get("scope", "function")
        lines.append("@fixture" if scope == "function" else '@fixture(scope="module")')
        deps = [d for d in fx if re.search(r"\b%s\b" % d, f["expr"]) and d != f["name"]]
        lines.append("def %s(%s):" % (f["name"], ", ".join(deps)))
        if f.get("teardown"):
            lines.append("    %s = %s" % (f["name"], f["expr"]))
            lines.append("    yield %s" % f["name"])
            for t in f["teardown"]:
                lines.append("    " + t)
        else:
            lines.append("    return %s" % f["expr"])
        lines += ["", ""]
    for t in spec["tests"]:
        if t.get("skip"):
            lines.append("@skip(%s)" % json.dumps(t["skip"]))
        if t.get("skip_if"):
            lines.append("@skip_if(%s, %s)" % (t["skip_if"][0], json.dumps(t["skip_if"][1])))
        names = [d for d in fx if any(re.search(r"(?<![\w.\"'])%s\b" % re.escape(d), code) for code in _code_strings(t["body"]))]
        lines.append("def %s(%s):" % (t["name"], ", ".join(names)))
        depth = 1 + len(t.get("patches", []))
        for k, (target, new) in enumerate(t.get("patches", [])):
            lines.append("    " * (k + 1) + "with mock.patch(%s, new=%s):" % (json.dumps(target), new))
        for st in t["body"]:
            lines += _render_stmt(st, "plain", fx, depth)
        lines += ["", ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def count_checks(stmts):
    n = 0
    for s in stmts:
        n += count_checks(s[3]) if s[0] == "sub" else (0 if s[0] == "code" else 1)
    return n


# ======================================================================================================================
# the projects
# ======================================================================================================================

PARCEL = dd(r'''
"""Shipping fee quotes for the parcel desk."""

BANDS = [(500, 320), (2000, 510), (10000, 980)]  # (heaviest gram count of the band, price in cents)
ZONES = {"A": 100, "B": 125, "C": 160}  # zone surcharge in percent of the base price
MAX_WEIGHT = BANDS[-1][0]


def base_cents(weight_g):
    """Price of the weight band; ValueError for weights that are not positive integers or are above the heaviest band."""
    if isinstance(weight_g, bool) or not isinstance(weight_g, int) or weight_g <= 0:
        raise ValueError("weight must be a positive number of grams")
    for limit, cents in BANDS:
        if weight_g <= limit:
            return cents
    raise ValueError("parcel too heavy")


def quote(weight_g, zone):
    """Price in cents including the zone surcharge, rounded half up; KeyError for an unknown zone."""
    if zone not in ZONES:
        raise KeyError(zone)
    return (base_cents(weight_g) * ZONES[zone] + 50) // 100


def label(weight_g, zone):
    cents = quote(weight_g, zone)
    return "%.1f kg zone %s: EUR %d.%02d" % (weight_g / 1000, zone, cents // 100, cents % 100)


def best_zone(weight_g, budget_cents):
    """The zone with the highest surcharge whose quote still fits the budget, or None."""
    fits = [z for z in sorted(ZONES) if quote(weight_g, z) <= budget_cents]
    return max(fits, key=lambda z: ZONES[z]) if fits else None
''')

PARCEL_TESTS = dict(
    file="tests/test_parcel_fee.py", **{"class": "ParcelFeeTest"}, imports=["import parcel_fee as pf"],
    tests=[
        dict(name="test_base_bands", body=[("eq", "pf.base_cents(1)", "320"), ("eq", "pf.base_cents(500)", "320"), ("eq", "pf.base_cents(501)", "510"), ("eq", "pf.base_cents(2000)", "510"),
                                           ("eq", "pf.base_cents(2001)", "980"), ("eq", "pf.base_cents(10000)", "980")]),
        dict(name="test_base_rejects_bad_weights", body=[("raises", "ValueError", "pf.base_cents(0)"), ("raises", "ValueError", "pf.base_cents(-5)"), ("raises", "ValueError", "pf.base_cents(10001)"),
                                                         ("raises", "ValueError", "pf.base_cents('5')"), ("raises", "ValueError", "pf.base_cents(True)"), ("raises", "ValueError", "pf.base_cents(2.5)")]),
        dict(name="test_quote_zone_a_is_the_base_price", body=[("eq", "pf.quote(700, 'A')", "510"), ("eq", "pf.quote(100, 'A')", "320")]),
        dict(name="test_quote_rounds_half_up", body=[("eq", "pf.quote(700, 'B')", "638"), ("eq", "pf.quote(700, 'C')", "816"), ("eq", "pf.quote(10000, 'B')", "1225"), ("eq", "pf.quote(100, 'C')", "512")]),
        dict(name="test_quote_unknown_zone", body=[("raises", "KeyError", "pf.quote(100, 'Z')")]),
        dict(name="test_label", body=[("eq", "pf.label(1500, 'B')", "'1.5 kg zone B: EUR 6.38'"), ("eq", "pf.label(300, 'A')", "'0.3 kg zone A: EUR 3.20'"), ("eq", "pf.label(10000, 'C')", "'10.0 kg zone C: EUR 15.68'")]),
        dict(name="test_label_is_text", body=[("isinst", "pf.label(700, 'A')", "str")]),
        dict(name="test_best_zone_prefers_the_highest_surcharge", body=[("eq", "pf.best_zone(700, 700)", "'B'"), ("eq", "pf.best_zone(700, 900)", "'C'"), ("eq", "pf.best_zone(700, 510)", "'A'")]),
        dict(name="test_best_zone_none_when_too_expensive", body=[("none", "pf.best_zone(700, 100)"), ("none", "pf.best_zone(700, 509)")]),
        dict(name="test_zone_table", body=[("in", "'A'", "pf.ZONES"), ("not_in", "'D'", "pf.ZONES"), ("eq", "pf.ZONES['A']", "100"), ("true", "all(v >= 100 for v in pf.ZONES.values())")]),
        dict(name="test_surcharge_never_lowers_the_price", body=[("sub", "w", "[1, 500, 501, 2000, 2001, 10000]", [("ge", "pf.quote(w, 'B')", "pf.quote(w, 'A')"), ("ge", "pf.quote(w, 'C')", "pf.quote(w, 'B')")])]),
        dict(name="test_max_weight", body=[("eq", "pf.MAX_WEIGHT", "10000"), ("eq", "pf.base_cents(pf.MAX_WEIGHT)", "980"), ("false", "pf.base_cents(pf.MAX_WEIGHT) == 320")]),
    ],
)

PARCEL_MUTANTS = [
    ("parcel_fee.py", "if weight_g <= limit:", "if weight_g < limit:"),
    ("parcel_fee.py", "* ZONES[zone] + 50) // 100", "* ZONES[zone] + 0) // 100"),
    ("parcel_fee.py", '    raise ValueError("parcel too heavy")', "    return 980"),
    ("parcel_fee.py", "return max(fits, key=lambda z: ZONES[z]) if fits else None", "return min(fits, key=lambda z: ZONES[z]) if fits else None"),
    ("parcel_fee.py", "cents // 100, cents % 100)", "cents // 100, cents // 100)"),
    ("parcel_fee.py", "or weight_g <= 0:", "or weight_g < 0:"),
    ("parcel_fee.py", "if isinstance(weight_g, bool) or not isinstance(weight_g, int)", "if not isinstance(weight_g, int)"),
    ("parcel_fee.py", "(2000, 510)", "(2000, 511)"),
    ("parcel_fee.py", "if quote(weight_g, z) <= budget_cents", "if quote(weight_g, z) < budget_cents"),
]

LANES = dd(r'''
"""Swim meet lane assignment."""

LANE_ORDER = [4, 5, 3, 6, 2, 7, 1, 8]  # the fastest swimmer of a heat gets the first lane of this list, the next one the second, ...


def seed_order(entries):
    """Entries are (name, seed_seconds) pairs; fastest first, ties by name."""
    return sorted(entries, key=lambda e: (e[1], e[0]))


def heats(entries, lanes=8):
    """Split the entries into heats of at most `lanes` swimmers: the fastest swimmers swim in the last heat and the slowest in the first,
    which takes the remainder. Returns a list of {lane: name}."""
    if lanes < 1 or lanes > len(LANE_ORDER):
        raise ValueError("lanes must be between 1 and 8")
    ordered = seed_order(entries)
    chunks = [ordered[i:i + lanes] for i in range(0, len(ordered), lanes)]
    chunks.reverse()
    lane_ids = [lane for lane in LANE_ORDER if lane <= lanes]
    return [{lane_ids[i]: name for i, (name, _) in enumerate(chunk)} for chunk in chunks]


def average_seed(entries):
    if not entries:
        raise ValueError("no entries")
    return sum(seconds for _, seconds in entries) / len(entries)


def spread(entries):
    """Seconds between the slowest and the fastest seed."""
    if not entries:
        raise ValueError("no entries")
    seconds = [s for _, s in entries]
    return max(seconds) - min(seconds)


def lane_of(plan, name):
    """(heat index, lane) of a swimmer, or None."""
    for index, heat in enumerate(plan):
        for lane, swimmer in heat.items():
            if swimmer == name:
                return (index, lane)
    return None


def names_in_lane(plan, lane):
    return [heat[lane] for heat in plan if lane in heat]
''')

LANES_TESTS = dict(
    file="tests/test_lane_plan.py", **{"class": "LanePlanTest"}, imports=["import lane_plan as lp"],
    fixtures=[dict(name="field", expr='[("s%d" % i, 60 + i / 2) for i in range(1, 11)]')],
    tests=[
        dict(name="test_seed_order_sorts_by_time_then_name", body=[("eq", "lp.seed_order([('c', 61.2), ('a', 59.9), ('b', 61.2)])", "[('a', 59.9), ('b', 61.2), ('c', 61.2)]")]),
        dict(name="test_single_heat_uses_the_centre_lanes_first", body=[("code", "plan = lp.heats(field[:3])"), ("eq", "len(plan)", "1"), ("eq", "plan[0]", "{4: 's1', 5: 's2', 3: 's3'}")]),
        dict(name="test_two_heats", body=[("code", "plan = lp.heats(field)"), ("eq", "len(plan)", "2"), ("eq", "len(plan[0])", "2"), ("eq", "len(plan[1])", "8")]),
        dict(name="test_slowest_swim_first", body=[("code", "plan = lp.heats(field)"), ("eq", "sorted(plan[0].values())", "['s10', 's9']"), ("eq", "plan[1][4]", "'s1'"), ("eq", "plan[1][8]", "'s8'")]),
        dict(name="test_full_heat_lane_order", body=[("code", "plan = lp.heats(field)"), ("eq", "plan[1]", "{4: 's1', 5: 's2', 3: 's3', 6: 's4', 2: 's5', 7: 's6', 1: 's7', 8: 's8'}")]),
        dict(name="test_lane_count_validation", body=[("raises", "ValueError", "lp.heats(field, 0)"), ("raises", "ValueError", "lp.heats(field, 9)"), ("raises_re", "ValueError", "between 1 and 8", "lp.heats(field, -2)")]),
        dict(name="test_fewer_lanes_use_the_lowest_numbers", body=[("code", "plan = lp.heats(field[:6], lanes=6)"), ("eq", "sorted(plan[0])", "[1, 2, 3, 4, 5, 6]"), ("eq", "plan[0][4]", "'s1'")]),
        dict(name="test_average_seed", body=[("almost", "lp.average_seed([('a', 60.0), ('b', 61.5), ('c', 59.1)])", "60.2", 6), ("almost", "lp.average_seed(field)", "62.75", 6)]),
        dict(name="test_spread", body=[("almost", "lp.spread(field)", "4.5", 6), ("eq", "lp.spread(field[:1])", "0")]),
        dict(name="test_empty_field", body=[("eq", "lp.heats([])", "[]"), ("raises", "ValueError", "lp.average_seed([])"), ("raises", "ValueError", "lp.spread([])")]),
        dict(name="test_lane_of", body=[("code", "plan = lp.heats(field)"), ("eq", "lp.lane_of(plan, 's1')", "(1, 4)"), ("eq", "lp.lane_of(plan, 's10')", "(0, 5)"), ("none", "lp.lane_of(plan, 'zz')")]),
        dict(name="test_names_in_lane", body=[("code", "plan = lp.heats(field)"), ("same", "lp.names_in_lane(plan, 4)", "['s9', 's1']"), ("eq", "lp.names_in_lane(plan, 8)", "['s8']")]),
        dict(name="test_every_field_size_fills_the_last_heat", body=[("sub", "n", "range(1, 11)", [("code", "plan = lp.heats(field[:n])"), ("eq", "len(plan[-1])", "min(n, 8)"), ("eq", "sum(len(h) for h in plan)", "n")])]),
    ],
)

LANES_MUTANTS = [
    ("lane_plan.py", "LANE_ORDER = [4, 5, 3, 6, 2, 7, 1, 8]", "LANE_ORDER = [4, 5, 3, 6, 2, 1, 7, 8]"),
    ("lane_plan.py", "    chunks.reverse()\n", ""),
    ("lane_plan.py", "ordered[i:i + lanes]", "ordered[i:i + lanes - 1]"),
    ("lane_plan.py", "key=lambda e: (e[1], e[0])", "key=lambda e: e[1]"),
    ("lane_plan.py", "if lane <= lanes]", "if lane < lanes]"),
    ("lane_plan.py", "/ len(entries)", "/ (len(entries) + 1)"),
    ("lane_plan.py", "return max(seconds) - min(seconds)", "return min(seconds) - max(seconds)"),
    ("lane_plan.py", "if lanes < 1 or lanes > len(LANE_ORDER):", "if lanes > len(LANE_ORDER):"),
    ("lane_plan.py", "return (index, lane)", "return (index + 1, lane)"),
    ("lane_plan.py", "return [heat[lane] for heat in plan if lane in heat]", "return [heat[lane] for heat in plan[1:] if lane in heat]"),
]

RECIPE = dd(r'''
"""Scaling recipes and building shopping lists."""
from fractions import Fraction

GRAMS = {"g": Fraction(1), "kg": Fraction(1000), "oz": Fraction(2835, 100), "lb": Fraction(45359237, 100000)}  # grams per unit


def to_grams(qty, unit):
    """Quantity in grams as a float; ValueError('unknown unit: x') for units that are not in GRAMS."""
    if unit not in GRAMS:
        raise ValueError("unknown unit: %s" % unit)
    return float(Fraction(qty) * GRAMS[unit])


def scale(recipe, factor):
    """A new recipe {ingredient: (qty, unit)} with every quantity multiplied by `factor` (a number or a string like '3/2')."""
    factor = Fraction(factor)
    if factor <= 0:
        raise ValueError("factor must be positive")
    return {name: (Fraction(qty) * factor, unit) for name, (qty, unit) in recipe.items()}


def pretty(qty):
    """Mixed-number text: 3 -> '3', Fraction(3, 2) -> '1 1/2', Fraction(3, 4) -> '3/4'."""
    qty = Fraction(qty)
    whole, rest = divmod(qty.numerator, qty.denominator)
    if rest == 0:
        return str(whole)
    if whole == 0:
        return "%d/%d" % (rest, qty.denominator)
    return "%d %d/%d" % (whole, rest, qty.denominator)


def shopping_list(recipes):
    """Total grams per ingredient over several recipes (names compared case-insensitively), sorted by name."""
    totals = {}
    for recipe in recipes:
        for name, (qty, unit) in recipe.items():
            key = name.lower()
            totals[key] = totals.get(key, 0.0) + to_grams(qty, unit)
    return sorted(totals.items())
''')

RECIPE_TESTS = dict(
    file="tests/test_recipe_scale.py", **{"class": "RecipeScaleTest"}, imports=["from fractions import Fraction", "", "import recipe_scale as rs"],
    fixtures=[dict(name="soup", expr='{"Onion": (2, "oz"), "Stock": (1, "kg"), "Salt": (Fraction(1, 2), "g")}')],
    tests=[
        dict(name="test_to_grams_exact_units", body=[("eq", "rs.to_grams(2, 'kg')", "2000.0"), ("eq", "rs.to_grams(5, 'g')", "5.0"), ("eq", "rs.to_grams(0, 'lb')", "0.0")]),
        dict(name="test_to_grams_imperial", body=[("almost", "rs.to_grams(1, 'oz')", "28.35", 6), ("almost", "rs.to_grams(2, 'lb')", "907.18474", 5)]),
        dict(name="test_unknown_unit_names_the_unit", body=[("raises_re", "ValueError", "unknown unit: cup", "rs.to_grams(1, 'cup')"), ("raises", "ValueError", "rs.to_grams(1, 'G')")]),
        dict(name="test_scale_doubles", body=[("code", "big = rs.scale(soup, 2)"), ("eq", "big['Stock']", "(2, 'kg')"), ("eq", "big['Salt']", "(Fraction(1), 'g')")]),
        dict(name="test_scale_accepts_fraction_text", body=[("eq", "rs.scale(soup, '3/2')['Stock']", "(Fraction(3, 2), 'kg')"), ("eq", "rs.scale(soup, '1/4')['Onion']", "(Fraction(1, 2), 'oz')")]),
        dict(name="test_scale_rejects_non_positive_factors", body=[("raises", "ValueError", "rs.scale(soup, 0)"), ("raises", "ValueError", "rs.scale(soup, -1)"), ("raises_re", "ValueError", "positive", "rs.scale(soup, '0/5')")]),
        dict(name="test_scale_does_not_touch_the_original", body=[("code", "rs.scale(soup, 3)"), ("eq", "soup['Stock']", "(1, 'kg')"), ("eq", "len(soup)", "3")]),
        dict(name="test_pretty_whole_and_mixed", body=[("eq", "rs.pretty(3)", "'3'"), ("eq", "rs.pretty(Fraction(3, 2))", "'1 1/2'"), ("eq", "rs.pretty(Fraction(3, 4))", "'3/4'"), ("eq", "rs.pretty(Fraction(7, 3))", "'2 1/3'"), ("eq", "rs.pretty(0)", "'0'")]),
        dict(name="test_shopping_list_merges_case_insensitively", body=[("code", "other = {'onion': (1, 'oz'), 'Pepper': (3, 'g')}"), ("code", "got = dict(rs.shopping_list([soup, other]))"),
                                                                       ("almost", "got['onion']", "85.05", 6), ("eq", "got['pepper']", "3.0"), ("eq", "got['stock']", "1000.0")]),
        dict(name="test_shopping_list_is_sorted", body=[("eq", "[name for name, _ in rs.shopping_list([soup])]", "['onion', 'salt', 'stock']")]),
        dict(name="test_shopping_list_of_nothing", body=[("eq", "rs.shopping_list([])", "[]"), ("eq", "rs.shopping_list([{}])", "[]")]),
    ],
)

RECIPE_MUTANTS = [
    ("recipe_scale.py", "if factor <= 0:", "if factor < 0:"),
    ("recipe_scale.py", "Fraction(2835, 100)", "Fraction(2834, 100)"),
    ("recipe_scale.py", "key = name.lower()", "key = name"),
    ("recipe_scale.py", "return {name: (Fraction(qty) * factor, unit) for name, (qty, unit) in recipe.items()}", "recipe.update({name: (Fraction(qty) * factor, unit) for name, (qty, unit) in recipe.items()})\n    return recipe"),
    ("recipe_scale.py", "if whole == 0:", "if whole == 1:"),
    ("recipe_scale.py", 'raise ValueError("unknown unit: %s" % unit)', 'raise ValueError("bad unit")'),
    ("recipe_scale.py", "return sorted(totals.items())", "return list(totals.items())[::-1]"),
    ("recipe_scale.py", "return \"%d %d/%d\" % (whole, rest, qty.denominator)", "return \"%d %d/%d\" % (whole, rest, qty.denominator + 1)"),
    ("recipe_scale.py", "return float(Fraction(qty) * GRAMS[unit])", "return float(Fraction(qty) * GRAMS[unit]) + 0.01"),
]

BADGES = dd(r'''
"""Badge registry stored in a small text file."""
import os


class Registry:
    def __init__(self, path):
        self.path = path
        self.badges = {}  # code -> holder
        self.revoked = set()
        if os.path.exists(path):
            self._load()

    def _load(self):
        with open(self.path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.rstrip("\n")
                if not line or line.startswith("#"):
                    continue
                status, code, holder = line.split("\t", 2)
                if status == "R":
                    self.revoked.add(code)
                self.badges[code] = holder

    def save(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("# badge registry\n")
            for code in sorted(self.badges):
                fh.write("%s\t%s\t%s\n" % ("R" if code in self.revoked else "A", code, self.badges[code]))

    def issue(self, holder):
        """Issue the next code (B0001, B0002, ...) to `holder` and return it."""
        code = "B%04d" % (len(self.badges) + 1)
        self.badges[code] = holder
        return code

    def revoke(self, code):
        if code not in self.badges:
            raise KeyError(code)
        self.revoked.add(code)

    def active(self):
        return sorted(code for code in self.badges if code not in self.revoked)

    def holder_of(self, code):
        if code in self.revoked:
            raise PermissionError("badge %s is revoked" % code)
        return self.badges[code]
''')

BADGES_TESTS = dict(
    file="tests/test_badge_registry.py", **{"class": "RegistryTest"}, imports=["import os", "import shutil", "import tempfile", "", "from badge_registry import Registry"],
    fixtures=[dict(name="workdir", expr="tempfile.mkdtemp()", teardown=["shutil.rmtree(workdir)"]),
              dict(name="reg", expr='Registry(os.path.join(workdir, "reg.txt"))')],
    tests=[
        dict(name="test_codes_are_sequential", body=[("eq", "reg.issue('ann')", "'B0001'"), ("eq", "reg.issue('bob')", "'B0002'"), ("eq", "reg.issue('cy')", "'B0003'")]),
        dict(name="test_holder_lookup", body=[("code", "code = reg.issue('ann')"), ("eq", "reg.holder_of(code)", "'ann'")]),
        dict(name="test_unknown_code", body=[("raises", "KeyError", "reg.holder_of('B9999')"), ("raises", "KeyError", "reg.revoke('B9999')")]),
        dict(name="test_revoked_badges_cannot_be_looked_up", body=[("code", "code = reg.issue('ann')"), ("code", "reg.revoke(code)"), ("raises_re", "PermissionError", "revoked", "reg.holder_of(code)")]),
        dict(name="test_active_excludes_revoked", body=[("code", "a = reg.issue('ann')"), ("code", "b = reg.issue('bob')"), ("code", "reg.issue('cy')"), ("code", "reg.revoke(b)"), ("eq", "reg.active()", "['B0001', 'B0003']"),
                                                      ("in", "a", "reg.active()"), ("not_in", "b", "reg.active()")]),
        dict(name="test_new_registry_is_empty", body=[("eq", "reg.active()", "[]"), ("false", "os.path.exists(reg.path)")]),
        dict(name="test_save_writes_a_header_and_sorted_rows", body=[("code", "reg.issue('ann')"), ("code", "reg.issue('bob')"), ("code", "reg.revoke('B0001')"), ("code", "reg.save()"),
                                                                    ("code", "text = open(reg.path, encoding='utf-8').read()"), ("eq", "text", "'# badge registry\\nR\\tB0001\\tann\\nA\\tB0002\\tbob\\n'")]),
        dict(name="test_save_and_reload", body=[("code", "reg.issue('ann')"), ("code", "reg.issue('bob')"), ("code", "reg.revoke('B0002')"), ("code", "reg.save()"), ("code", "again = Registry(reg.path)"),
                                               ("eq", "again.active()", "['B0001']"), ("eq", "again.badges", "{'B0001': 'ann', 'B0002': 'bob'}"), ("eq", "again.revoked", "{'B0002'}")]),
        dict(name="test_reload_continues_the_numbering", body=[("code", "reg.issue('ann')"), ("code", "reg.save()"), ("code", "again = Registry(reg.path)"), ("eq", "again.issue('bob')", "'B0002'")]),
        dict(name="test_holder_names_may_contain_tabs_and_spaces", body=[("code", "code = reg.issue('Ann\\tMarie  Lee')"), ("code", "reg.save()"), ("eq", "Registry(reg.path).holder_of(code)", "'Ann\\tMarie  Lee'")]),
        dict(name="test_loading_skips_comments_and_blank_lines", body=[("code", "open(reg.path, 'w', encoding='utf-8').write('# note\\n\\nA\\tB0001\\tann\\n# more\\nR\\tB0002\\tbob\\n')"),
                                                                     ("code", "again = Registry(reg.path)"), ("eq", "again.active()", "['B0001']"), ("eq", "len(again.badges)", "2")]),
        dict(name="test_each_test_gets_its_own_directory", body=[("true", "os.path.isdir(workdir)"), ("true", "workdir.startswith(tempfile.gettempdir())"), ("isinst", "reg", "Registry")]),
    ],
)

BADGES_MUTANTS = [
    ("badge_registry.py", 'code = "B%04d" % (len(self.badges) + 1)', 'code = "B%04d" % len(self.badges)'),
    ("badge_registry.py", 'if not line or line.startswith("#"):', "if not line:"),
    ("badge_registry.py", '"R" if code in self.revoked else "A"', '"A"'),
    ("badge_registry.py", 'line.split("\\t", 2)', 'line.split("\\t")'),
    ("badge_registry.py", "if code not in self.revoked)", "if code in self.revoked)"),
    ("badge_registry.py", "        if code not in self.badges:\n            raise KeyError(code)\n        self.revoked.add(code)", "        self.revoked.add(code)"),
    ("badge_registry.py", 'raise PermissionError("badge %s is revoked" % code)', "return self.badges[code]"),
    ("badge_registry.py", "for code in sorted(self.badges):", "for code in sorted(self.badges, reverse=True):"),
    ("badge_registry.py", 'fh.write("# badge registry\\n")', 'fh.write("# registry\\n")'),
    ("badge_registry.py", 'if status == "R":', 'if status == "A":'),
]

METERS = dd(r'''
"""Parsing and summarising utility meter readings."""
import calendar
import time

KINDS = ("gas", "power", "water")
ROLLOVER = 10000.0


class ParseError(ValueError):
    pass


def parse_line(line):
    """`2024-03-09 14:05 gas 1234.5` -> ('2024-03-09 14:05', 'gas', 1234.5)."""
    parts = line.split()
    if len(parts) != 4:
        raise ParseError("expected 4 fields: %r" % line)
    day, clock, kind, raw = parts
    if kind not in KINDS:
        raise ParseError("unknown meter: %s" % kind)
    try:
        value = float(raw)
    except ValueError:
        raise ParseError("bad value: %s" % raw)
    if value < 0:
        raise ParseError("negative reading")
    return ("%s %s" % (day, clock), kind, value)


def parse(text):
    """All readings of a text; blank lines and `#` comments are skipped, errors name the line number."""
    out = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        try:
            out.append(parse_line(line))
        except ParseError as exc:
            raise ParseError("line %d: %s" % (number, exc))
    return out


def consumption(readings, kind):
    """Total consumption of one meter between its first and last reading; a reading that is lower than the one before means the dial rolled over at ROLLOVER."""
    values = [v for _, k, v in sorted(readings) if k == kind]
    if len(values) < 2:
        raise ValueError("need at least two readings of %s" % kind)
    total = 0.0
    for before, after in zip(values, values[1:]):
        total += after - before if after >= before else after + ROLLOVER - before
    return total


def age_of(stamp, now=None):
    """Seconds between the UTC time stamp `YYYY-MM-DD HH:MM` and now."""
    then = calendar.timegm(time.strptime(stamp, "%Y-%m-%d %H:%M"))
    return (time.time() if now is None else now) - then
''')

METERS_SAMPLE = "# march data\\n2024-03-01 08:00 gas 100.0\\n2024-03-02 08:00 gas 112.5\\n\\n2024-03-01 08:00 power 9990.0\\n2024-03-02 08:00 power 15.0\\n2024-03-03 08:00 power 40.0\\n2024-03-01 09:30 water 3.25\\n"

METERS_TESTS = dict(
    file="tests/test_meter_log.py", **{"class": "MeterLogTest"}, imports=["import sys", "", "import meter_log as ml"],
    fixtures=[dict(name="readings", expr="ml.parse(%s)" % json.dumps(METERS_SAMPLE.replace("\\n", "\n")), scope="module")],
    tests=[
        dict(name="test_parse_line", body=[("eq", "ml.parse_line('2024-03-09 14:05 gas 1234.5')", "('2024-03-09 14:05', 'gas', 1234.5)"), ("eq", "ml.parse_line('  2024-03-09   14:05\\tpower  7  ')", "('2024-03-09 14:05', 'power', 7.0)")]),
        dict(name="test_parse_line_rejects_bad_lines", body=[("sub", "bad", "['', 'gas 12', '2024-03-09 14:05 gas', '2024-03-09 14:05 gas 1 2', '2024-03-09 14:05 steam 3', '2024-03-09 14:05 gas abc', '2024-03-09 14:05 gas -1']",
                                                           [("raises", "ml.ParseError", "ml.parse_line(bad)")])]),
        dict(name="test_parse_error_is_a_value_error", body=[("true", "issubclass(ml.ParseError, ValueError)"), ("raises", "ValueError", "ml.parse_line('nonsense')")]),
        dict(name="test_parse_skips_comments_and_blank_lines", body=[("eq", "len(readings)", "6"), ("eq", "readings[0]", "('2024-03-01 08:00', 'gas', 100.0)")]),
        dict(name="test_parse_error_names_the_line", body=[("raises_re", "ml.ParseError", "line 3: unknown meter: steam", "ml.parse('2024-03-01 08:00 gas 1\\n\\n2024-03-09 14:05 steam 3\\n')")]),
        dict(name="test_consumption_simple", body=[("eq", "ml.consumption(readings, 'gas')", "12.5"), ("true", "ml.consumption(readings, 'power') > 0")]),
        dict(name="test_consumption_handles_rollover", body=[("eq", "ml.consumption(readings, 'power')", "50.0")]),
        dict(name="test_consumption_is_zero_when_the_dial_did_not_move", body=[("eq", "ml.consumption([('2024-03-01 08:00', 'gas', 5.0), ('2024-03-02 08:00', 'gas', 5.0)], 'gas')", "0.0")]),
        dict(name="test_consumption_needs_two_readings", body=[("raises_re", "ValueError", "at least two readings of water", "ml.consumption(readings, 'water')"), ("raises", "ValueError", "ml.consumption([], 'gas')")]),
        dict(name="test_consumption_ignores_the_input_order", body=[("code", "shuffled = list(reversed(readings))"), ("eq", "ml.consumption(shuffled, 'power')", "50.0")]),
        dict(name="test_age_with_explicit_now", body=[("eq", "ml.age_of('1970-01-01 00:01', now=100)", "40"), ("eq", "ml.age_of('1970-01-01 00:00', now=0)", "0")]),
        dict(name="test_age_defaults_to_the_clock", patches=[("meter_log.time.time", "lambda: 1710000000.0")],
             body=[("eq", "ml.age_of('2024-03-09 12:00')", "14400.0"), ("eq", "ml.age_of('2024-03-09 16:00')", "0.0")]),
        dict(name="test_age_is_negative_for_the_future", body=[("true", "ml.age_of('2030-01-01 00:00', now=0) < 0")]),
        dict(name="test_decimal_comma_is_accepted", skip="decimal commas are not supported yet", body=[("eq", "ml.parse_line('2024-03-09 14:05 gas 12,5')[2]", "12.5")]),
        dict(name="test_kinds", skip_if=("sys.version_info < (3, 8)", "needs python 3.8"), body=[("eq", "ml.KINDS", "('gas', 'power', 'water')"), ("eq", "ml.ROLLOVER", "10000.0")]),
    ],
)

METERS_MUTANTS = [
    ("meter_log.py", "if len(parts) != 4:", "if len(parts) < 4:"),
    ("meter_log.py", "if value < 0:", "if value < -1:"),
    ("meter_log.py", "for _, k, v in sorted(readings)", "for _, k, v in readings"),
    ("meter_log.py", "after + ROLLOVER - before", "after + 1000.0 - before"),
    ("meter_log.py", "return (time.time() if now is None else now) - then", "return then - (time.time() if now is None else now)"),
    ("meter_log.py", 'raise ParseError("line %d: %s" % (number, exc))', "raise ParseError(str(exc))"),
    ("meter_log.py", "if not line.strip() or line.lstrip().startswith(\"#\"):", "if not line.strip():"),
    ("meter_log.py", "if len(values) < 2:", "if len(values) < 1:"),
    ("meter_log.py", "class ParseError(ValueError):", "class ParseError(Exception):"),
    ("meter_log.py", "if kind not in KINDS:", "if kind not in KINDS + ('steam',):"),
    ("meter_log.py", "total += after - before if after >= before else", "total += after - before if after > before else"),
]

SUPPORT = dd(r'''
"""Shared helpers for the test suites."""
import unittest


class BaseCase(unittest.TestCase):
    def assertSorted(self, seq):
        self.assertEqual(list(seq), sorted(seq), "not sorted: %r" % (seq,))

    def assertWithin(self, actual, expected, tolerance):
        self.assertLessEqual(abs(actual - expected), tolerance, "%r is not within %r of %r" % (actual, tolerance, expected))
''')

SUPPORT_PLAIN = dd(r'''
"""Shared helpers for the test suites."""


def assert_sorted(seq):
    assert list(seq) == sorted(seq), "not sorted: %r" % (seq,)


def assert_within(actual, expected, tolerance):
    assert abs(actual - expected) <= tolerance, "%r is not within %r of %r" % (actual, tolerance, expected)
''')


def _with_support(spec, extra):
    """The composite project reuses the stand-alone suites on a shared base class and adds checks that use its custom assertions."""
    out = dict(spec)
    out["support"] = True
    out["tests"] = [dict(t) for t in spec["tests"]]
    for name, stmt in extra:
        for t in out["tests"]:
            if t["name"] == name:
                t["body"] = list(t["body"]) + [stmt]
    return out


COMPOSITE_PARCEL = _with_support(PARCEL_TESTS, [
    ("test_surcharge_never_lowers_the_price", ("custom", "within", ["pf.quote(100, 'B') / 100", "pf.quote(100, 'A') / 100 * 1.25", "0.01"])),
    ("test_base_bands", ("custom", "sorted", ["[pf.base_cents(w) for w in (1, 500, 501, 2000, 2001, 10000)]"])),
])
COMPOSITE_LANES = _with_support(LANES_TESTS, [
    ("test_seed_order_sorts_by_time_then_name", ("custom", "sorted", ["[t for _, t in lp.seed_order([('c', 61.2), ('a', 59.9), ('b', 61.2)])]"])),
    ("test_average_seed", ("custom", "within", ["lp.average_seed(field)", "62.75", "0.001"])),
])
COMPOSITE_RECIPE = _with_support(RECIPE_TESTS, [
    ("test_to_grams_imperial", ("custom", "within", ["rs.to_grams(1, 'oz')", "28.35", "0.0001"])),
    ("test_shopping_list_is_sorted", ("custom", "sorted", ["[name for name, _ in rs.shopping_list([soup])]"])),
])

PROJECTS = [
    dict(key="parcel-desk", d=2, title="parcel desk", modules={"parcel_fee.py": PARCEL}, suites=[PARCEL_TESTS], mutants=PARCEL_MUTANTS, support=False),
    dict(key="swim-meet", d=3, title="swim meet planner", modules={"lane_plan.py": LANES}, suites=[LANES_TESTS], mutants=LANES_MUTANTS, support=False),
    dict(key="recipe-box", d=3, title="recipe box", modules={"recipe_scale.py": RECIPE}, suites=[RECIPE_TESTS], mutants=RECIPE_MUTANTS, support=False),
    dict(key="badge-office", d=4, title="badge office", modules={"badge_registry.py": BADGES}, suites=[BADGES_TESTS], mutants=BADGES_MUTANTS, support=False),
    dict(key="meter-room", d=4, title="meter room", modules={"meter_log.py": METERS}, suites=[METERS_TESTS], mutants=METERS_MUTANTS, support=False),
    dict(key="town-hall", d=5, title="town hall services", modules={"parcel_fee.py": PARCEL, "lane_plan.py": LANES, "recipe_scale.py": RECIPE},
         suites=[COMPOSITE_PARCEL, COMPOSITE_LANES, COMPOSITE_RECIPE], mutants=PARCEL_MUTANTS + LANES_MUTANTS + RECIPE_MUTANTS, support=True),
]

CHECKER = dd(r'''
import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
SPEC = json.load(open(os.path.join(HERE, "spec.json"), encoding="utf-8"))


def fail(message):
    print("FAIL: " + message)
    sys.exit(1)


def run_suite(root):
    p = subprocess.run([sys.executable, "tools/minirun.py", "tests"], cwd=root, capture_output=True, text=True, timeout=60)
    return p.returncode, p.stdout + p.stderr


for path, digest in SPEC["hashes"].items():
    full = os.path.join(ROOT, path)
    if not os.path.exists(full) or hashlib.sha256(open(full, "rb").read()).hexdigest() != digest:
        fail("%s was changed; the runner and the assertion helpers must stay as they are" % path)

tests_dir = os.path.join(ROOT, "tests")
n_tests = n_checks = 0
for dirpath, _, names in os.walk(tests_dir):
    if "__pycache__" in dirpath:
        continue
    for name in sorted(names):
        if not name.endswith(".py"):
            continue
        path = os.path.join(dirpath, name)
        tree = ast.parse(open(path, encoding="utf-8").read(), path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "unittest":
                        fail("%s still imports unittest" % name)
            elif isinstance(node, ast.ImportFrom):
                if node.module == "unittest" and any(a.name != "mock" for a in node.names):
                    fail("%s still imports from unittest" % name)
            elif isinstance(node, ast.ClassDef):
                for base in node.bases:
                    if "TestCase" in ast.dump(base) or "BaseCase" in ast.dump(base):
                        fail("%s still has a TestCase class (%s)" % (name, node.name))
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "self" and (node.func.attr.startswith("assert") or node.func.attr == "subTest"):
                    fail("%s still calls self.%s" % (name, node.func.attr))
        if name.startswith("test_"):
            for node in tree.body:
                if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                    n_tests += 1
                    checks = 0
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Assert):
                            checks += 1
                        elif isinstance(sub, ast.With):
                            checks += 1
                        elif isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id.startswith("assert"):
                            checks += 1
                    if checks == 0:
                        fail("%s::%s checks nothing" % (name, node.name))
                    n_checks += checks

if n_tests < SPEC["min_tests"]:
    fail("only %d test functions found, the suite had %d tests" % (n_tests, SPEC["tests"]))
if n_checks < SPEC["min_checks"]:
    fail("only %d checks left, the suite had about %d" % (n_checks, SPEC["checks"]))

code, out = run_suite(ROOT)
m = re.search(r"(\d+) passed, (\d+) failed, (\d+) skipped", out)
if code != 0 or not m:
    fail("the converted suite does not pass:\n" + out[-800:])
passed, failed, skipped = (int(x) for x in m.groups())
if skipped != SPEC["skips"]:
    fail("%d tests are skipped, expected %d (skips must be kept, and nothing else may be skipped)" % (skipped, SPEC["skips"]))
if passed < SPEC["min_passed"]:
    fail("only %d tests pass, expected at least %d" % (passed, SPEC["min_passed"]))

for index, (path, old, new) in enumerate(SPEC["mutants"]):
    tmp = tempfile.mkdtemp(prefix="mut-")
    try:
        work = os.path.join(tmp, "repo")
        shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns("__pycache__", "_verify", ".git"))
        target = os.path.join(work, path)
        text = open(target, encoding="utf-8").read()
        if old not in text:
            fail("checker error: mutant %d does not apply" % index)
        open(target, "w", encoding="utf-8").write(text.replace(old, new, 1))
        code, out = run_suite(work)
        if code == 0:
            fail("the suite does not notice a change in %s: %r became %r" % (path, old[:60], new[:60]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

print("ok: %d tests, %d checks, %d mutants caught" % (n_tests, n_checks, len(SPEC["mutants"])))
''')


def _readme(project, suites):
    files = ", ".join("`%s`" % s["file"] for s in suites)
    return (f"# {project['title']}\n\nSmall Python modules with their tests ({files}). The tests are written with `unittest.TestCase` classes; the team is moving all test suites to plain functions with `assert`, run by "
            f"`tools/minirun.py` (read its docstring: how tests are found, fixtures, skipping).\n\n"
            "## How to convert\n\n"
            "* `self.assertEqual(a, b)` and the other one-line assertions become plain `assert` statements; `assertRaises`/`assertRaisesRegex` become `with raises(...)`, `assertAlmostEqual` becomes `approx(...)` and `assertCountEqual` becomes "
            "`same_items(...)` (all in `tests/asserts.py`, which, like the runner, must not be edited).\n"
            "* `setUp`/`tearDown`/`setUpClass` become fixtures, `subTest` loops become plain loops, `unittest.skip`/`skipIf` become `skip`/`skip_if`, `mock.patch` decorators become `with mock.patch(...)` blocks "
            "(`unittest.mock` itself stays available).\n"
            "* Test files keep their names. Every test keeps its checks: the suite will be run against deliberately broken versions of the modules to see that it still notices. The modules themselves are not to be changed.\n")


def _validate(project, files_old, files_new, mutants):
    """Original suite: passes, and fails on every mutant. Reference suite: passes (the mutants are proven at admission)."""
    code, out = run_local(files_old, ["python3", "-m", "unittest", "discover", "-s", "tests"], timeout=120)
    if code != 0:
        raise RuntimeError(f"{project['key']}: the original unittest suite fails:\n{out[-1500:]}")
    for path, old, new in mutants:
        mutated = dict(files_old)
        if old not in mutated[path]:
            raise RuntimeError(f"{project['key']}: mutant does not apply: {old!r}")
        mutated[path] = mutated[path].replace(old, new, 1)
        code, out = run_local(mutated, ["python3", "-m", "unittest", "discover", "-s", "tests"], timeout=120)
        if code == 0:
            raise RuntimeError(f"{project['key']}: the original suite does not catch the mutant {old!r} -> {new!r}")
    code, out = run_local(files_new, ["python3", "tools/minirun.py", "tests"], timeout=120)
    if code != 0:
        raise RuntimeError(f"{project['key']}: the converted suite fails:\n{out[-1500:]}")
    return out


@family("port-unittest-to-asserts", category="port", lang="python", kind="refactor", n=6,
        summary="migrate unittest.TestCase suites to plain assert functions run by a tiny runner; a hidden checker mutates the code to prove no check was lost")
def gen_unittest(rng, n):
    voices = [
        "We're dropping `unittest`. Convert the test suite in this repository to plain functions with `assert`, run by `python3 tools/minirun.py` (README.md and the runner's docstring explain the conventions). Keep every check: "
        "the converted suite is later run against broken copies of the modules and has to notice. Don't edit the modules.",
        "The tests here are `unittest.TestCase` classes and we want plain `assert` tests that `tools/minirun.py` can run (fixtures instead of setUp/tearDown, `raises`/`approx`/`same_items` helpers from tests/asserts.py). "
        "Please migrate all of them without losing any assertion; the application code stays untouched.",
        "port the tests from unittest style to the repo's mini runner (plain test functions, assert statements, fixtures, skip markers). no check may get weaker or disappear - they'll mutate the code to see - and don't change the runner or the helpers.",
        "Ticket: test style migration. All `unittest` suites become plain-function suites for `tools/minirun.py`, one file per old file, same coverage, skips preserved. See README.md for the mapping of unittest features to the new ones.",
    ]
    for i, project in enumerate(PROJECTS[:n]):
        files_old = {"tools/minirun.py": MINIRUN, "tests/asserts.py": ASSERTS}
        files_new = dict(files_old)
        files_old.update(project["modules"])
        files_new.update(project["modules"])
        test_old, test_new = {}, {}
        n_tests = n_checks = n_skips = 0
        for spec in project["suites"]:
            test_old[spec["file"]] = render_unittest(spec)
            test_new[spec["file"]] = render_plain(spec)
            n_tests += len(spec["tests"])
            n_checks += sum(count_checks(t["body"]) for t in spec["tests"])
            n_skips += sum(1 for t in spec["tests"] if t.get("skip"))
        if project["support"]:
            test_old["tests/support.py"] = SUPPORT
            test_new["tests/support.py"] = SUPPORT_PLAIN
        files_old.update(test_old)
        files_new.update(test_new)
        _validate(project, files_old, files_new, project["mutants"])
        spec_json = {
            "hashes": {p: hashlib.sha256(t.encode("utf-8")).hexdigest() for p, t in (("tools/minirun.py", MINIRUN), ("tests/asserts.py", ASSERTS))},
            "tests": n_tests, "min_tests": max(1, int(n_tests * 0.9)), "checks": n_checks, "min_checks": max(1, int(n_checks * 0.6)),
            "skips": n_skips, "min_passed": max(1, int((n_tests - n_skips) * 0.9)), "mutants": [list(m) for m in project["mutants"]],
        }
        start = {"tools/minirun.py": MINIRUN, "tests/asserts.py": ASSERTS, "README.md": _readme(project, project["suites"]), **project["modules"], **test_old}
        solution = dict(test_new)
        yield Task(
            slug=f"{i + 1:02d}-{project['key']}",
            prompt=voices[i % len(voices)],
            difficulty=project["d"],
            lang="python",
            kind="refactor",
            start=start,
            hidden={"_verify/check_migration.py": CHECKER, "_verify/spec.json": json.dumps(spec_json, indent=1) + "\n"},
            solution=solution,
            verify="python3 tools/minirun.py tests && python3 _verify/check_migration.py",
            protect_tests=False,
            protected=["tools/minirun.py", "tests/asserts.py", *[m for m in project["modules"]]],
            timeout_s=240,
            tags=["api-migration", "testing", "unittest-to-assert", "python"],
            notes={"tests": n_tests, "checks": n_checks, "mutants": len(project["mutants"]), "skips": n_skips},
        )
