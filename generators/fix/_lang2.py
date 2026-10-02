"""Shared helpers for the JavaScript / TypeScript / Java library families (``jslib_*``, ``tslib_*``, ``javalib_*``).

* ``register_libs(libs, n)``: like ``fx.register_libs`` but cuts the tasks with ``mutation_tasks`` below, a fork of
  ``fx.lib.mutation_tasks`` that (a) supports ``Lib.probes`` for javascript, typescript and java (expressions evaluated
  against the correct and the mutated code, so prompts can say "``f(3)`` gives 4 but should give 5"), and (b) cleans the
  noisy parts of ``node --test`` TAP output out of the CI excerpt.
* ``TSCONFIG`` / ``TS_NODE_SHIM`` / ``TS_VERIFY``: the offline TypeScript setup (no ``@types/node``; ``node:test`` and
  ``node:assert/strict`` are declared by a tiny ambient file).
* ``JAVA_CHECK`` and ``java_test_main``: the plain-Java assertion helper (no JUnit) and a ``TestMain`` that runs the
  test classes.
* ``JS_VERIFY``: ``node --test`` with an explicit file glob (node 22 does not accept a directory argument).
"""
from __future__ import annotations

import json
import random
import re

from fx import Family, Task, merged, mutate, run
from fx.core import register
from fx.lib import (BUILD, LANG_PREFIX, _STYLE_D, _STYLES, _diff_line, _prompt,  # noqa: F401
                    _sanitize_excerpt)

JS_VERIFY = "node --test test/*.test.js"
TS_VERIFY = "rm -rf build && tsc -p . && node --test build/test/*.test.js"

PACKAGE_JSON = '{\n  "name": "%s",\n  "version": "1.0.0",\n  "private": true\n}\n'

TSCONFIG = (
    '{\n  "compilerOptions": {\n    "target": "ES2022",\n    "module": "commonjs",\n    "outDir": "build",\n'
    '    "rootDir": ".",\n    "strict": true,\n    "esModuleInterop": true,\n    "types": [],\n    "lib": ["ES2022"],\n'
    '    "skipLibCheck": true\n  },\n'
    '  "include": ["src/**/*.ts", "test/**/*.ts", "types/**/*.d.ts"]\n}\n'
)

TS_NODE_SHIM = r'''// Minimal ambient declarations for the parts of Node used by the tests (this project has no @types/node).
declare module "node:test" {
  export function test(name: string, fn: () => void | Promise<void>): void;
  export function describe(name: string, fn: () => void): void;
  export function it(name: string, fn: () => void | Promise<void>): void;
}

declare module "node:assert/strict" {
  interface Assert {
    (value: unknown, message?: string): void;
    ok(value: unknown, message?: string): void;
    equal(actual: unknown, expected: unknown, message?: string): void;
    notEqual(actual: unknown, expected: unknown, message?: string): void;
    deepEqual(actual: unknown, expected: unknown, message?: string): void;
    notDeepEqual(actual: unknown, expected: unknown, message?: string): void;
    strictEqual(actual: unknown, expected: unknown, message?: string): void;
    notStrictEqual(actual: unknown, expected: unknown, message?: string): void;
    deepStrictEqual(actual: unknown, expected: unknown, message?: string): void;
    fail(message?: string): never;
    throws(fn: () => unknown, expected?: unknown, message?: string): void;
    doesNotThrow(fn: () => unknown, message?: string): void;
    match(value: string, pattern: RegExp, message?: string): void;
  }
  const assert: Assert;
  export default assert;
}
'''

JAVA_CHECK = r'''import java.util.Arrays;
import java.util.Objects;

/** Tiny assertion helper for the plain-Java tests (no JUnit in this project). */
public final class Check {
    public interface Body {
        void run() throws Exception;
    }

    private static int failures = 0;
    private static int total = 0;

    private Check() {}

    public static void test(String name, Body body) {
        total++;
        try {
            body.run();
        } catch (AssertionError e) {
            failures++;
            System.out.println("FAIL " + name + ": " + e.getMessage());
        } catch (Throwable t) {
            failures++;
            System.out.println("FAIL " + name + ": unexpected " + t.getClass().getSimpleName() + (t.getMessage() == null ? "" : ": " + t.getMessage()));
        }
    }

    public static String show(Object o) {
        if (o instanceof Object[]) return Arrays.deepToString((Object[]) o);
        if (o instanceof int[]) return Arrays.toString((int[]) o);
        if (o instanceof long[]) return Arrays.toString((long[]) o);
        if (o instanceof double[]) return Arrays.toString((double[]) o);
        if (o instanceof char[]) return Arrays.toString((char[]) o);
        if (o instanceof boolean[]) return Arrays.toString((boolean[]) o);
        if (o instanceof String) return "\"" + o + "\"";
        return String.valueOf(o);
    }

    public static void eq(Object expected, Object actual) {
        if (!Objects.deepEquals(expected, actual)) {
            throw new AssertionError("expected <" + show(expected) + "> but got <" + show(actual) + ">");
        }
    }

    public static void eq(String what, Object expected, Object actual) {
        if (!Objects.deepEquals(expected, actual)) {
            throw new AssertionError(what + ": expected <" + show(expected) + "> but got <" + show(actual) + ">");
        }
    }

    public static void near(double expected, double actual, double eps) {
        if (Double.isNaN(actual) || Math.abs(expected - actual) > eps) {
            throw new AssertionError("expected <" + expected + "> but got <" + actual + ">");
        }
    }

    public static void yes(boolean condition, String what) {
        if (!condition) throw new AssertionError(what);
    }

    public static void raises(Class<? extends Throwable> type, Body body) {
        try {
            body.run();
        } catch (Throwable t) {
            if (type.isInstance(t)) return;
            throw new AssertionError("expected " + type.getSimpleName() + " but got " + t.getClass().getSimpleName());
        }
        throw new AssertionError("expected " + type.getSimpleName() + " but nothing was thrown");
    }

    public static void done() {
        if (failures > 0) {
            System.out.println(failures + " of " + total + " checks failed");
            System.exit(1);
        }
        System.out.println("all " + total + " checks passed");
    }
}
'''


def java_test_main(*classes: str) -> str:
    calls = "\n".join(f"        {c}.run();" for c in classes)
    return f"public class TestMain {{\n    public static void main(String[] args) {{\n{calls}\n        Check.done();\n    }}\n}}\n"


# ---- probes for javascript / typescript / java --------------------------------------------------------------------------

def _js_probe(lib) -> tuple[dict[str, str], str]:
    script = (
        "'use strict';\nconst util = require('node:util');\n"
        f"{lib.probe_import}\n"
        f"const PROBES = {json.dumps(lib.probes)};\n"
        "for (const e of PROBES) {\n"
        "  let r;\n"
        "  try {\n"
        "    r = util.inspect(eval(e), { depth: 6, breakLength: Infinity, compact: true });\n"
        "  } catch (ex) {\n"
        "    r = 'raises ' + (ex && ex.constructor ? ex.constructor.name : 'Error') + (ex && ex.message ? ': ' + ex.message : '');\n"
        "  }\n"
        "  console.log(JSON.stringify([e, r.slice(0, 160)]));\n"
        "}\n"
    )
    cmd = "node _probe.js" if lib.lang == "javascript" else "rm -rf build && tsc -p . && node _probe.js"
    return {"_probe.js": script}, cmd


def _java_probe(lib) -> tuple[dict[str, str], str]:
    calls = "\n".join(f"        p({json.dumps(e)}, () -> {e});" for e in lib.probes)
    src = (
        f"{lib.probe_import}\n\n"
        "public class Probe {\n"
        "    static String show(Object o) {\n"
        "        if (o instanceof Object[]) return java.util.Arrays.deepToString((Object[]) o);\n"
        "        if (o instanceof int[]) return java.util.Arrays.toString((int[]) o);\n"
        "        if (o instanceof long[]) return java.util.Arrays.toString((long[]) o);\n"
        "        if (o instanceof double[]) return java.util.Arrays.toString((double[]) o);\n"
        "        if (o instanceof boolean[]) return java.util.Arrays.toString((boolean[]) o);\n"
        "        if (o instanceof String) return \"\\\"\" + o + \"\\\"\";\n"
        "        return String.valueOf(o);\n"
        "    }\n\n"
        "    static String quote(String s) {\n"
        "        StringBuilder b = new StringBuilder(\"\\\"\");\n"
        "        for (char c : s.toCharArray()) {\n"
        "            if (c == '\"' || c == '\\\\') b.append('\\\\').append(c);\n"
        "            else if (c == '\\n') b.append(\"\\\\n\");\n"
        "            else if (c < 32 || c > 126) b.append(String.format(\"\\\\u%04x\", (int) c));\n"
        "            else b.append(c);\n"
        "        }\n"
        "        return b.append('\"').toString();\n"
        "    }\n\n"
        "    static void p(String label, java.util.concurrent.Callable<Object> c) {\n"
        "        String r;\n"
        "        try {\n"
        "            r = show(c.call());\n"
        "        } catch (Throwable t) {\n"
        "            r = \"raises \" + t.getClass().getSimpleName() + (t.getMessage() == null ? \"\" : \": \" + t.getMessage());\n"
        "        }\n"
        "        if (r.length() > 160) r = r.substring(0, 160);\n"
        "        System.out.println(\"[\" + quote(label) + \", \" + quote(r) + \"]\");\n"
        "    }\n\n"
        "    public static void main(String[] args) throws Exception {\n"
        f"{calls}\n"
        "    }\n}\n"
    )
    cmd = ("rm -rf build && mkdir -p build && javac -d build $(find . -name '*.java' ! -path './test/*') && java -cp build Probe")
    return {"probe/Probe.java": src}, cmd


def _parse_probe(out: str) -> dict[str, str]:
    d: dict[str, str] = {}
    for ln in out.splitlines():
        if not ln.startswith("["):
            continue
        try:
            e, r = json.loads(ln)
            d[e] = r
        except Exception:  # noqa: BLE001
            pass
    return d


def probe_diffs(lib, good: dict[str, str], bad: dict[str, str]) -> list[tuple[str, str, str]]:
    if not lib.probes:
        return []
    extra, cmd = (_java_probe(lib) if lib.lang == "java" else _js_probe(lib))
    g = run(merged(good, extra), cmd, timeout=60)
    if not g.ok:
        return []
    b = run(merged(bad, extra), cmd, timeout=40)
    if not b.ok and not _parse_probe(b.out):
        return []
    if b.timed_out:
        return []
    gd, bd = _parse_probe(g.out), _parse_probe(b.out)
    return [(e, gd[e], bd[e]) for e in lib.probes if e in gd and e in bd and gd[e] != bd[e]]


def check_probes(lib) -> None:
    """Raise if some probe of the correct library does not run (typo in a probe expression)."""
    if not lib.probes:
        return
    extra, cmd = (_java_probe(lib) if lib.lang == "java" else _js_probe(lib))
    g = run(merged(lib.files, extra), cmd, timeout=60)
    if not g.ok:
        raise RuntimeError(f"lib {lib.name}: probe script fails on the correct code:\n{g.out[-1500:]}")
    got = _parse_probe(g.out)
    missing = [e for e in lib.probes if e not in got]
    if missing:
        raise RuntimeError(f"lib {lib.name}: probes did not run: {missing}")


# ---- excerpt cleaning ----------------------------------------------------------------------------------------------------

def clean_tap(excerpt: str) -> str:
    """Keep, for each failing test of a ``node --test`` TAP run, its name and the assertion message only."""
    out: list[str] = []
    mode = ""  # "" outside a failure block, "meta" before the error text, "err" inside it
    for ln in excerpt.splitlines():
        s = ln.strip()
        if ln.startswith("not ok "):
            out.append(ln)
            mode = "meta"
        elif mode == "meta":
            if s.startswith("error:"):
                out.append("  " + s)
                mode = "err"
        elif mode == "err":
            if re.match(r"^\s{0,2}[a-zA-Z_]+:", ln) and not ln.startswith("    "):
                mode = ""
            else:
                out.append(ln)
        # everything else (# Subtest, ok lines, location, stack frames) is dropped
    return "\n".join(out[:14])


def clean_excerpt(lang: str, excerpt: str) -> str:
    if not excerpt:
        return ""
    if lang in ("javascript", "typescript") and "not ok " in excerpt:
        excerpt = clean_tap(excerpt)
    if lang == "java":
        fails = [x for x in excerpt.splitlines() if x.startswith("FAIL ")]
        tail = [x for x in excerpt.splitlines() if x.endswith("checks failed")]
        if len(fails) > 6:
            fails = fails[:6] + ["..."]
        excerpt = "\n".join(fails + tail)
    return excerpt if len([x for x in excerpt.splitlines() if x.strip()]) >= 2 else ""


def headline(lang: str, excerpt: str) -> str:
    """One informative line of a failing run: the first failing check's name and its message."""
    lines = [x for x in excerpt.splitlines() if x.strip()]
    if lang == "java":
        for ln in lines:
            if ln.startswith("FAIL "):
                return ln[5:].strip()[:170]
        return ""
    for i, ln in enumerate(lines):
        if ln.startswith("not ok "):
            name = re.sub(r"^not ok \d+ - ", "", ln)
            msg = []
            for x in lines[i + 1:]:
                if x.startswith("not ok "):
                    break
                msg.append(x.strip())
            msg = [x for x in msg if not x.startswith(("error:", "Expected values", "+ actual", "Expected \"actual\""))]
            if len(msg) == 1:
                return f"{name}: {msg[0]}"[:170]
            if msg and any("!==" in x for x in msg):
                return f"{name}: {[x for x in msg if '!==' in x][0]}"[:170]
            return name[:170]
    return ""


def _prompt2(style, lib, m, excerpt, diffs, visible_fail, rng) -> str:
    if style == "review" and excerpt:
        line = headline(lib.lang, excerpt)
        if not line:
            return ""
        end = rng.choice(["Please repair it.", "Please fix it.", "Can you take a look?", "Please sort it out."])
        tail = rng.choice(["Don't change the tests.", "Keep the public API as it is.", "", "Leave unrelated code alone."])
        what = f"One failure says: `{line}`." if re.search(r": .*(\S)", line) and ("!==" in line or "Error" in line or "expected" in line or "but" in line) else f"One of the failing checks is called `{line}`."
        return (f"A teammate's last commit touched `{m.path}` and the suite for {lib.title} has been red since. "
                f"{what} {end} {tail}").strip()
    return _prompt(style, lib, m, excerpt, diffs, visible_fail, rng)


def skip_mutant(m) -> bool:
    """Mutants that only remove an export or are otherwise uninteresting."""
    return m.op == "delete" and m.before.startswith(("module.exports", "exports.", "export ", "package ", "import "))


# ---- the fork of fx.lib.mutation_tasks ------------------------------------------------------------------------------------

def _test_failed(lang: str, out: str) -> bool:
    """True when ``out`` shows failing checks (rather than a compile error or a crash)."""
    if lang == "java":
        return "FAIL " in out or "checks failed" in out
    if lang == "typescript":
        return "error TS" not in out and "not ok " in out
    return True


def mutation_tasks(lib, rng: random.Random, n: int, max_candidates: int = 34) -> list[Task]:
    check_probes(lib)
    base_tree = merged(lib.files, lib.visible_tests, lib.hidden_tests)
    vis_tree = merged(lib.files, lib.visible_tests)
    base = run(base_tree, lib.verify, timeout=lib.timeout_s)
    if not base.ok:
        raise RuntimeError(f"lib {lib.name}: hidden+visible suite fails on the correct implementation:\n{base.out[-1500:]}")
    vbase = run(vis_tree, lib.verify, timeout=lib.timeout_s)
    leash = int(max(8, min(lib.timeout_s, 8 * (base.ms / 1000.0) + 6)))
    if not vbase.ok:
        raise RuntimeError(f"lib {lib.name}: visible suite fails on the correct implementation:\n{vbase.out[-1500:]}")

    cands: list[mutate.Mutant] = []
    for path in lib.mutate:
        cands += mutate.mutants(lib.lang, path, lib.files[path], rng)
    rng.shuffle(cands)
    # java / typescript: no separate build step (it would cost a second compile); a failing run without test-failure
    # output is a mutant that does not compile (or crashes before any check ran) and is skipped.
    buildcmd = BUILD.get(lib.lang, "") if lib.lang == "javascript" else ""
    hidden_paths = sorted(lib.hidden_tests)

    good: list[tuple[mutate.Mutant, str, bool]] = []
    per_op: dict[str, int] = {}
    per_line: dict[tuple, int] = {}
    tried = 0
    for m in cands:
        if len(good) >= n * 2 or tried >= max_candidates:
            break
        if per_op.get(m.op, 0) >= max(2, n // 2 + 1) or per_line.get((m.path, m.line), 0) >= 1 or skip_mutant(m):
            continue
        tried += 1
        files = merged(lib.files, {m.path: m.text})
        if buildcmd:
            b = run(merged(files, lib.visible_tests), buildcmd, timeout=max(leash, 60))
            if not b.ok:
                continue
        r = run(merged(files, lib.visible_tests, lib.hidden_tests), lib.verify, timeout=leash)
        if r.ok or r.timed_out or len(r.out.strip()) < 10 or not _test_failed(lib.lang, r.out):
            continue
        v = run(merged(files, lib.visible_tests), lib.verify, timeout=leash)
        if v.timed_out:
            continue
        good.append((m, r.out, not v.ok))
        per_op[m.op] = per_op.get(m.op, 0) + 1
        per_line[(m.path, m.line)] = 1

    by_op: dict[str, list] = {}
    for g in good:
        by_op.setdefault(g[0].op, []).append(g)
    chosen: list = []
    ops = sorted(by_op)
    rng.shuffle(ops)
    while len(chosen) < n and any(by_op.values()):
        for op in ops:
            if by_op[op] and len(chosen) < n:
                chosen.append(by_op[op].pop(0))
    tasks: list[Task] = []
    for k, (m, out, visible_fail) in enumerate(chosen):
        files = merged(lib.files, {m.path: m.text})
        excerpt = clean_excerpt(lib.lang, _sanitize_excerpt(out, hidden_paths, limit=60))
        diffs = probe_diffs(lib, lib.files, files)
        styles = [s for s in _STYLES if _prompt2(s, lib, m, excerpt, diffs, visible_fail, random.Random(0))]
        style = rng.choice(styles) if styles else "spec"
        prompt = _prompt2(style, lib, m, excerpt, diffs, visible_fail, rng) or _prompt("spec", lib, m, excerpt, diffs, visible_fail, rng)
        d = max(1, min(5, lib.difficulty + _STYLE_D[style]))
        tasks.append(Task(
            slug=f"{k + 1:02d}-{m.op}",
            prompt=prompt,
            difficulty=d,
            start=merged(files, lib.visible_tests),
            hidden=dict(lib.hidden_tests),
            solution={m.path: lib.files[m.path]},
            verify=lib.verify,
            timeout_s=lib.timeout_s,
            tags=["mutation", "bugfix", style, *lib.tags],
            notes={"library": lib.name, "mutation": m.desc, "style": style, "visible_fails": visible_fail},
        ))
    return tasks


def register_libs(libs, n: int = 8, category: str = "fix") -> None:
    """One family per library: ``fix-<js|ts|java>-<name>``."""
    for lib in libs:
        fam = Family(name=f"fix-{LANG_PREFIX.get(lib.lang, lib.lang)}-{lib.name}", category=category, lang=lib.lang, kind="fix", n=n,
                     summary=f"injected bugs in {lib.title} ({lib.lang})")

        def gen(rng, count, _lib=lib):
            return mutation_tasks(_lib, rng, count)

        register(fam, gen)
