"""Port families: one library, written once with shared JSON vectors, becomes several translation tasks.

A ``PortLib`` carries a language-neutral specification, a table of typed functions, hand-written reference
implementations in two or three languages, and a generator of test cases. The expected value of every case is computed
by running the *python* implementation (the oracle); every other implementation is then run against the same vectors at
build time, so two independent implementations of the README must agree before any task is emitted.

From the implementations a family emits ``(source, target, variant)`` tasks:

* ``full``  - the target project is empty (build files and the visible test harness only);
* ``stub``  - the target API exists with every function stubbed out, so the exact names and types are fixed.

Hidden: ``vectors/full.json`` (the harness in the repository prefers it over ``vectors/examples.json``).
"""
from __future__ import annotations

import json
import os
import random
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from fx import Task, dd, merged, run
from fx.core import Family, register
from fx.run import write_tree

from . import _harness as H
from ._types import Fn, fn_name, jsonable_ok, parse_type, signature, tname

LABEL = {
    "python": "Python", "go": "Go", "rust": "Rust", "java": "Java", "javascript": "JavaScript", "typescript": "TypeScript",
    "ruby": "Ruby", "php": "PHP", "c": "C",
}
TEST_CMD = {
    "python": "python3 -m unittest discover -s tests", "go": "go test ./...", "rust": "cargo test --offline",
    "java": "the Java test program (`TestMain`)", "javascript": "node --test test/*.test.js", "typescript": "tsc -p . && node --test build/test/*.test.js",
    "ruby": "the Ruby test script (`test/test_vectors.rb`)", "php": "php tests/run.php", "c": "the C test program (`tests/test_main.c`)",
}
SHORT_CMD = {
    "python": "python3 -m unittest discover -s tests", "go": "go test ./...", "rust": "cargo test --offline",
    "javascript": "node --test test/*.test.js", "typescript": "tsc -p . && node --test build/test/*.test.js",
    "php": "php tests/run.php",
}


@dataclass
class PortLib:
    slug: str  # kebab-case; family is port-<slug>
    title: str  # "tide-table lookups"
    blurb: str  # one or two sentences of domain context
    spec: str  # markdown: the language-neutral behaviour, precise
    fns: list[Fn]
    impls: dict[str, dict[str, str]]  # lang -> implementation files (paths as in harness.impl_paths)
    cases: Callable[[random.Random], list]  # -> [(fn, args)]; the first n_examples are the visible examples
    difficulty: int = 3
    n_examples: int = 8
    pairs: list[tuple[str, str, str]] = field(default_factory=list)  # (src, dst, "full"|"stub")
    tags: list[str] = field(default_factory=list)
    traps: list[str] = field(default_factory=list)  # provenance only (notes)
    diff_adj: dict[str, int] = field(default_factory=dict)  # "src>dst" -> +-1
    notes_by_lang: dict[str, str] = field(default_factory=dict)  # extra README lines for a target language

    def __post_init__(self):
        self.names = H.LibNames(self.slug)
        if "python" not in self.impls:
            raise ValueError(f"{self.slug}: a python implementation (the oracle) is required")
        for lang, files in self.impls.items():
            want = sorted(H.impl_paths(lang, self.names))
            if sorted(files) != want:
                raise ValueError(f"{self.slug}: {lang} implementation files {sorted(files)} != {want}")
        if not self.pairs:
            langs = list(self.impls)
            self.pairs = default_pairs(langs)
        for s, d, v in self.pairs:
            if s not in self.impls or d not in self.impls:
                raise ValueError(f"{self.slug}: pair {s}->{d} has no implementation")
            if d == "c":
                raise ValueError("c cannot be a target")


def default_pairs(langs: list[str]) -> list[tuple[str, str, str]]:
    ls = [x for x in langs]
    out = []
    if len(ls) == 2:
        a, b = ls
        out = [(a, b, "full"), (b, a, "full"), (a, b, "stub")] if b != "c" else [(b, a, "full"), (b, a, "stub")]
    else:
        a, b, c = ls[:3]
        out = [(a, b, "full"), (b, c, "full"), (c, a, "stub"), (a, c, "stub")]
    return [(s, d, v) for s, d, v in out if d != "c"]


# ------------------------------------------------------------------------------------------------------------------
# vectors
# ------------------------------------------------------------------------------------------------------------------

_ORACLE = '''import json, sys
sys.path.insert(0, ".")
import {mod} as M

cases = json.load(open("cases.json", encoding="utf-8"))
out = []
for fn, args in cases:
    try:
        out.append({{"fn": fn, "args": args, "want": getattr(M, fn)(*args)}})
    except Exception as e:  # noqa: BLE001
        out.append({{"fn": fn, "args": args, "error": True, "why": type(e).__name__ + ": " + str(e)[:80]}})
print(json.dumps(out, ensure_ascii=True))
'''


def run_local(files: dict[str, str], cmd: list[str], timeout: int = 120) -> tuple[int, str]:
    """Run ``cmd`` in a temp dir holding ``files`` and return (exit code, stdout): no output cap, no cache."""
    with tempfile.TemporaryDirectory(prefix="fxport-") as tmp:
        write_tree(Path(tmp), files)
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1", "LC_ALL": "C.UTF-8", "HOME": tmp}
        p = subprocess.run(cmd, cwd=tmp, env=env, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        return p.returncode, p.stdout + (("\n" + p.stderr[-1500:]) if p.returncode else "")


def build_vectors(lib: PortLib, rng: random.Random) -> list[dict]:
    raw = lib.cases(rng)
    seen, cases = set(), []
    byname = {f.name: f for f in lib.fns}
    for fn, args in raw:
        f = byname[fn]
        key = json.dumps([fn, args], ensure_ascii=True)
        if key in seen:
            continue
        seen.add(key)
        if len(args) != len(f.args):
            raise RuntimeError(f"{lib.slug}: {fn} called with {len(args)} args")
        for (an, at), v in zip(f.args, args):
            if not jsonable_ok(v, parse_type(at)):
                raise RuntimeError(f"{lib.slug}: argument {an} of {fn} has a value {v!r} that is not a {at}")
        cases.append([fn, args])
    files = merged(lib.impls["python"], {"cases.json": json.dumps(cases, ensure_ascii=True),
                                         "oracle.py": _ORACLE.format(mod=lib.names.snake)})
    code, out_text = run_local(files, ["python3", "oracle.py"], timeout=120)
    if code != 0:
        raise RuntimeError(f"{lib.slug}: oracle failed:\n{out_text[-1500:]}")
    got = json.loads(out_text.strip().splitlines()[-1])
    out = []
    for c in got:
        f = byname[c["fn"]]
        if c.get("error"):
            if not f.err:
                raise RuntimeError(f"{lib.slug}: {c['fn']}{tuple(c['args'])!r} raised ({c.get('why')}) but is declared infallible")
            out.append({"fn": c["fn"], "args": c["args"], "error": True})
        else:
            if not jsonable_ok(c["want"], f.rtype):
                raise RuntimeError(f"{lib.slug}: {c['fn']}{tuple(c['args'])!r} returned {c['want']!r}, not a {f.ret}")
            out.append({"fn": c["fn"], "args": c["args"], "want": c["want"]})
    for f in lib.fns:
        n_calls = sum(1 for c in out if c["fn"] == f.name)
        if n_calls < 3:
            raise RuntimeError(f"{lib.slug}: only {n_calls} vectors for {f.name}")
        if f.err and not any(c.get("error") for c in out if c["fn"] == f.name):
            raise RuntimeError(f"{lib.slug}: {f.name} is fallible but no vector exercises an error")
    return out


def vector_text(slug: str, cases: list[dict]) -> str:
    lines = ",\n".join(json.dumps(c, ensure_ascii=True, separators=(",", ":")) for c in cases)
    return f'{{"lib":"{slug}","cases":[\n{lines}\n]}}\n'


def check_impls(lib: PortLib, cases: list[dict]) -> None:
    """Every implementation must pass the full vectors (this is what makes the reference solutions trustworthy)."""
    full = vector_text(lib.slug, cases)
    for lang, files in sorted(lib.impls.items()):
        tree = merged(files, H.skeleton(lang, lib.names), {"vectors/full.json": full, "vectors/examples.json": full})
        if lang == "c":
            tree.update(H.c_harness(lib.names, lib.fns, cases))
        else:
            tree.update(H.HARNESS[lang](lib.names, lib.fns))
        r = run(tree, H.VERIFY[lang], timeout=240)
        if not r.ok:
            raise RuntimeError(f"{lib.slug}: the {lang} implementation fails its own vectors:\n{r.out[-2500:]}")


# ------------------------------------------------------------------------------------------------------------------
# README
# ------------------------------------------------------------------------------------------------------------------

def _conventions(lang: str, lib: PortLib) -> str:
    n = lib.names
    extra = lib.notes_by_lang.get(lang, "")
    base = {
        "python": f"Module `{n.snake}` (file `{n.snake}.py` at the repository root). Plain `int`/`str`/`list` values. Failure is signalled by raising an exception (any subclass of `Exception`).",
        "go": f"Package `{n.flat}` in the repository root (module `example.com/{n.flat}`, standard library only). Use the integer widths shown in the signatures. Failure is a non-nil `error` returned to the caller; never `panic` on bad input. A `(T, bool)` result reports whether a value is present.",
        "rust": f"Crate `{n.snake}`: everything is reachable from `src/lib.rs` (extra modules are fine; re-export them). Failure is an `Err(_)` (the error type is yours); never panic on bad input. No dependencies.",
        "java": f"Class `{n.pascal}` in the default package (file `{n.pascal}.java` in the repository root) with `public static` methods. `u32` values are `long`s in the range 0..4294967295 and `u8` values are `int`s in 0..255. Failure is signalled by throwing an exception.",
        "javascript": f"CommonJS module `src/{n.snake}.js` whose `module.exports` has one property per function (camelCase names). Numbers are JavaScript numbers; `u32` values are non-negative integers below 2^32; every `i32`/`u32` result must be exactly the value the specification gives. Failure is signalled by throwing an exception. An absent `opt` value is `null`.",
        "typescript": f"Module `src/{n.snake}.ts` with one `export function` per function. The test run includes `tsc -p .` with `strict` enabled, so the code must type-check. Numbers are `number`; `u32` values are non-negative integers below 2^32. Failure is signalled by throwing an exception. An absent `opt` value is `null`.",
        "ruby": f"Module `{n.pascal}` in `lib/{n.snake}.rb` with module-level methods (`def self.name`). Failure is signalled by raising a `StandardError`. An absent `opt` value is `nil`.",
        "php": f"Class `{n.pascal}` in `src/{n.pascal}.php` with `public static` methods. Strings are UTF-8 byte strings in PHP; the `mbstring` extension is available. Failure is signalled by throwing an exception. An absent `opt` value is `null`.",
        "c": "",
    }[lang]
    return base + ((" " + extra) if extra else "")


def _api_block(lang: str, lib: PortLib) -> str:
    lines = [signature(lang, f, lib.names.pascal if lang in ("ruby",) else lib.names.snake) for f in lib.fns]
    fence = {"javascript": "js", "typescript": "ts", "ruby": "ruby", "php": "php", "c": "c", "java": "java", "go": "go", "rust": "rust", "python": "python"}[lang]
    return f"```{fence}\n" + "\n".join(lines) + "\n```"


def _fn_docs(lib: PortLib) -> str:
    out = []
    for f in lib.fns:
        args = ", ".join(f"`{a}`: {t}" for a, t in f.args)
        fail = " Fails on invalid input." if f.err else ""
        out.append(f"* `{f.name}({', '.join(a for a, _ in f.args)})` -> `{f.ret}`.{fail} ({args})" + (f" {f.doc}" if f.doc else ""))
    return "\n".join(out)


def _kinds(t) -> set:
    out = {t.kind}
    if t.inner is not None:
        out |= _kinds(t.inner)
    return out


def _types_line(lib: PortLib) -> str:
    used = set()
    for f in lib.fns:
        for t in [*f.atypes, f.rtype]:
            used |= _kinds(t)
    parts = []
    fixed = [k for k in ("i32", "u32", "u8") if k in used]
    if fixed:
        parts.append(", ".join(f"`{k}`" for k in fixed) + (" is a fixed-width integer" if len(fixed) == 1 else " are fixed-width integers")
                     + " (what happens on overflow is stated in the behaviour section)")
    if "int" in used:
        parts.append("`int` is a signed 64-bit integer and every value in the test vectors is within +-2^53")
    if "str" in used:
        parts.append("`str` is Unicode text")
    if "opt" in used:
        parts.append("`opt<T>` is either a value of `T` or *absent*")
    if "list" in used:
        parts.append("`list<T>` is an ordered sequence")
    if "bool" in used:
        parts.append("`bool` is true or false")
    return "Types: " + "; ".join(parts) + "."


def readme(lib: PortLib, src: str, dst: str, variant: str) -> str:
    n = lib.names
    S, D = LABEL[src], LABEL[dst]
    src_files = ", ".join(f"`{p}`" for p in H.impl_paths(src, n))
    dst_files = ", ".join(f"`{p}`" for p in H.impl_paths(dst, n))
    state = (f"The {D} API already exists as stubs (every function fails at run time); replace the bodies."
             if variant == "stub" else f"Create {dst_files} (and any extra files you need).")
    cmd = SHORT_CMD.get(dst) or TEST_CMD[dst]
    test_files = {"python": "tests/test_vectors.py", "go": "vectors_test.go", "rust": "tests/vectors.rs", "java": "TestMain.java",
                  "javascript": "test/vectors.test.js", "typescript": "test/vectors.test.ts", "ruby": "test/test_vectors.rb",
                  "php": "tests/run.php"}[dst]
    return (
        f"# {lib.title}\n\n{lib.blurb}\n\n"
        f"This repository holds the {S} implementation ({src_files}). It is being ported to {D}; the port must behave "
        f"exactly like the specification below, including for malformed input.\n\n"
        f"## Behaviour\n\n{lib.spec.strip()}\n\n"
        f"## Functions\n\n{_fn_docs(lib)}\n\n"
        f"{_types_line(lib)}\n\n"
        f"## {S} (source)\n\n{_api_block(src, lib)}\n\n"
        f"## {D} (target)\n\n{state}\n\n{_conventions(dst, lib)}\n\n{_api_block(dst, lib)}\n\n"
        f"## Checking\n\n"
        f"`{test_files}` reads the vector file `vectors/examples.json` (a small sample) and calls the {D} API; run `{cmd}`. "
        f"The same harness is used with a much larger vector file when the port is graded, so passing the examples only is not enough. "
        f"The harness files and `vectors/examples.json` must not be edited.\n"
    )


# ------------------------------------------------------------------------------------------------------------------
# prompts
# ------------------------------------------------------------------------------------------------------------------

def _prompt(rng: random.Random, lib: PortLib, src: str, dst: str, variant: str) -> str:
    S, D = LABEL[src], LABEL[dst]
    cmd = SHORT_CMD.get(dst) or ("the checked-in test harness" if dst != "java" else "the Java `TestMain` harness")
    title, blurb = lib.title, lib.blurb
    stub_t = [
        f"The {D} skeleton for {title} is already in the repo with every function stubbed (it compiles, then fails when called). "
        f"Fill it in so it behaves exactly like the {S} implementation. {blurb} README.md is the spec; `{cmd}` runs the sample vectors and the grader uses many more.",
        f"Implement the stubbed {D} functions for {title}. The {S} version next to them is the reference and README.md settles every place where {S} and {D} would naturally differ. Don't touch the harness.",
        f"{blurb} The {D} half is stubbed out; please implement it so it matches the {S} code on all inputs, including the error cases. See README.md.",
        f"finish the {D} port of {title}: signatures are fixed by the stubs, bodies are `not implemented`. match the {S} behaviour exactly. there are more test vectors than the visible ones",
    ]
    full_t = [
        f"{blurb} We're moving this code from {S} to {D}. Port {title}: README.md gives the exact behaviour and the {D} API the tests call, and the checked-in harness runs with `{cmd}`. "
        f"Hidden vectors are much broader than the sample ones, so reproduce the specification, not just the examples.",
        f"port the {S} {title} lib to {D}. README.md has the spec and the {D} signatures. `{cmd}` should pass on the sample vectors and also on a bigger set you can't see, so read the spec carefully.",
        f"Ticket: replace the {S} implementation of {title} with a {D} one. {blurb} Acceptance: every documented behaviour (including failures on bad input) is identical to the {S} version, standard library only, and `{cmd}` passes.",
        f"The {D} side of {title} doesn't exist yet. Please write it from the {S} code and the README: the spec there pins down the details where {S} and {D} differ (integer widths, text handling, error reporting). Keep the harness as it is.",
        f"Can you translate this {S} module to {D}? {blurb} I put the details in README.md and a few example vectors in the repo; the real check uses many more.",
        f"Behaviour has to survive the {S} -> {D} rewrite of {title} bit for bit. The spec is in README.md; the {S} source and tests are there for reference. Write the {D} implementation with the API listed in the README and make `{cmd}` pass.",
        f"We're retiring the {S} version of {title}. Create the {D} equivalent following README.md. Don't change `vectors/examples.json` or the test harness; graders run the same harness against a larger vector file.",
    ]
    return rng.choice(stub_t if variant == "stub" else full_t)


# ------------------------------------------------------------------------------------------------------------------
# family registration
# ------------------------------------------------------------------------------------------------------------------

def register_port(lib: PortLib, module: str = "") -> None:
    fam = Family(name=f"port-{lib.slug}", category="port", lang="mixed", kind="feature", n=len(lib.pairs),
                 summary=f"port {lib.title} between languages ({', '.join(sorted(lib.impls))})")

    def gen(rng, count, _lib=lib):
        return list(_tasks(_lib, rng, count))

    gen.__module__ = module or "generators.port"
    register(fam, gen)


def _tasks(lib: PortLib, rng: random.Random, count: int):
    cases = build_vectors(lib, rng)
    check_impls(lib, cases)
    full_text = vector_text(lib.slug, cases)
    examples_text = vector_text(lib.slug, cases[: lib.n_examples])
    n = lib.names
    for i, (src, dst, variant) in enumerate(lib.pairs[:count]):
        start = {"README.md": readme(lib, src, dst, variant)}
        start.update(lib.impls[src])
        start.update(H.skeleton(src, n))
        if src == "c":
            start.update(H.c_harness(n, lib.fns, cases[: lib.n_examples]))
        else:
            start.update(H.HARNESS[src](n, lib.fns))
        start["vectors/examples.json"] = examples_text
        start.update(H.skeleton(dst, n))
        start.update(H.HARNESS[dst](n, lib.fns))
        if variant == "stub":
            start.update(H.stub(dst, n, lib.fns))
        d = lib.difficulty - (1 if variant == "stub" else 0) + lib.diff_adj.get(f"{src}>{dst}", 0)
        d = max(1, min(5, d))
        yield Task(
            slug=f"{i + 1:02d}-{src}-to-{dst}" + ("-stub" if variant == "stub" else ""),
            prompt=_prompt(rng, lib, src, dst, variant),
            difficulty=d,
            lang=dst,
            kind="feature" if variant == "stub" else "greenfield",
            start=start,
            hidden={"vectors/full.json": full_text},
            solution=dict(lib.impls[dst]),
            verify=H.VERIFY[dst],
            protected=["vectors/examples.json", *H.PROTECT.get(dst, []), *H.PROTECT.get(src, [])],
            timeout_s=240,
            tags=["port", f"from-{src}", variant, *lib.tags],
            notes={"library": lib.slug, "source": src, "target": dst, "variant": variant, "vectors": len(cases), "traps": lib.traps},
        )
