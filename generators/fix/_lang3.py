"""Helpers shared by the clib_* / cpplib_* / phplib_* modules (fix-lang-3): test harnesses, verify commands, registration.

The harnesses are ordinary files of the *visible* test tree (C, C++) or are pasted into ``tests/run.php`` (PHP), so every
library reports failures in the same one-line-per-failed-check style and a crash or a hang is reported crisply instead of
silently passing.
"""
from __future__ import annotations

import random
import re

from fx import Family, Task, merged, mutation_tasks, register, run
from fx.lib import LANG_PREFIX, _sanitize_excerpt

# The test binary is built with the address and undefined-behaviour sanitizers: an out-of-bounds access, a signed
# overflow or a bad shift in a mutant becomes a crisp failure instead of silent garbage. Leak checking is off.
_SAN = "-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer"
C_VERIFY = (
    "mkdir -p build && gcc -std=c11 -O1 -g -Wall -Wextra " + _SAN + " -Iinclude -Isrc -o build/tests "
    "$(find src tests -name '*.c') -lm && ASAN_OPTIONS=detect_leaks=0 ./build/tests"
)
CPP_VERIFY = (
    "mkdir -p build && g++ -std=c++17 -O1 -g -Wall -Wextra " + _SAN + " -Iinclude -Isrc -o build/tests "
    "$(find src tests -name '*.cpp') && ASAN_OPTIONS=detect_leaks=0 ./build/tests"
)

C_HARNESS = r'''/* Tiny test harness: every failed CHECK prints one FAIL line; main() ends with `return h_report();`. */
#ifndef HARNESS_H
#define HARNESS_H

#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

static int h_checks = 0, h_fails = 0;

static void h_on_alarm(int sig) {
    static const char msg[] = "FAIL: the test run timed out (probable infinite loop)\n";
    (void)sig;
    if (write(1, msg, sizeof msg - 1) < 0) { /* nothing to do */ }
    _exit(3);
}

static void h_init(void) {
    setvbuf(stdout, NULL, _IONBF, 0);
    signal(SIGALRM, h_on_alarm);
    alarm(20);
}

#define CHECK(cond) do { \
    h_checks++; \
    if (!(cond)) { h_fails++; printf("FAIL %s:%d: check failed: %s\n", __FILE__, __LINE__, #cond); } \
} while (0)

#define CHECK_INT(got, want) do { \
    long long g_ = (long long)(got), w_ = (long long)(want); \
    h_checks++; \
    if (g_ != w_) { h_fails++; printf("FAIL %s:%d: %s: got %lld, want %lld\n", __FILE__, __LINE__, #got, g_, w_); } \
} while (0)

/* like CHECK_INT / CHECK_STR, but `ctx` (a string, e.g. the input of a table row) is part of the message */
#define CHECK_INT_CTX(ctx, got, want) do { \
    long long g_ = (long long)(got), w_ = (long long)(want); \
    h_checks++; \
    if (g_ != w_) { h_fails++; printf("FAIL %s:%d: [%s] %s: got %lld, want %lld\n", __FILE__, __LINE__, (ctx), #got, g_, w_); } \
} while (0)

#define CHECK_STR_CTX(ctx, got, want) do { \
    const char *g_ = (got), *w_ = (want); \
    h_checks++; \
    if (g_ == NULL || strcmp(g_, w_) != 0) { \
        h_fails++; printf("FAIL %s:%d: [%s] %s: got \"%s\", want \"%s\"\n", __FILE__, __LINE__, (ctx), #got, g_ ? g_ : "(null)", w_); } \
} while (0)

#define CHECK_UINT(got, want) do { \
    unsigned long long g_ = (unsigned long long)(got), w_ = (unsigned long long)(want); \
    h_checks++; \
    if (g_ != w_) { h_fails++; printf("FAIL %s:%d: %s: got %llu (0x%llx), want %llu (0x%llx)\n", __FILE__, __LINE__, #got, g_, g_, w_, w_); } \
} while (0)

#define CHECK_STR(got, want) do { \
    const char *g_ = (got), *w_ = (want); \
    h_checks++; \
    if (g_ == NULL || strcmp(g_, w_) != 0) { \
        h_fails++; printf("FAIL %s:%d: %s: got \"%s\", want \"%s\"\n", __FILE__, __LINE__, #got, g_ ? g_ : "(null)", w_); } \
} while (0)

#define CHECK_MEM(got, want, n) do { \
    const unsigned char *g_ = (const unsigned char *)(got), *w_ = (const unsigned char *)(want); \
    size_t n_ = (size_t)(n), i_; \
    h_checks++; \
    if (memcmp(g_, w_, n_) != 0) { \
        h_fails++; printf("FAIL %s:%d: %s: bytes differ\n  got ", __FILE__, __LINE__, #got); \
        for (i_ = 0; i_ < n_; i_++) printf("%02x", g_[i_]); \
        printf("\n  want "); \
        for (i_ = 0; i_ < n_; i_++) printf("%02x", w_[i_]); \
        printf("\n"); } \
} while (0)

static int h_report(void) {
    printf("%d checks, %d failed\n", h_checks, h_fails);
    return h_fails ? 1 : 0;
}

#endif
'''

CPP_HARNESS = r'''// Tiny test harness: every failed CHECK prints one FAIL line; main() ends with `return h_report();`.
#ifndef HARNESS_HPP
#define HARNESS_HPP

#include <csignal>
#include <cstdio>
#include <optional>
#include <string>
#include <type_traits>
#include <unistd.h>
#include <utility>
#include <vector>

static int h_checks = 0, h_fails = 0;

static void h_on_alarm(int) {
    static const char msg[] = "FAIL: the test run timed out (probable infinite loop)\n";
    if (write(1, msg, sizeof msg - 1) < 0) { /* nothing to do */ }
    _exit(3);
}

static void h_init() {
    setvbuf(stdout, nullptr, _IONBF, 0);
    std::signal(SIGALRM, h_on_alarm);
    alarm(20);
}

template <class T> std::string h_show(const T &v);

inline std::string h_show(const std::string &s) { return "\"" + s + "\""; }
inline std::string h_show(const char *s) { return std::string("\"") + s + "\""; }
inline std::string h_show(bool b) { return b ? "true" : "false"; }
inline std::string h_show(char c) { return std::string("'") + c + "'"; }

template <class T, class = void> struct h_is_seq : std::false_type {};
template <class T> struct h_is_seq<T, std::void_t<typename T::value_type, decltype(std::declval<T>().begin())>> : std::true_type {};

template <class A, class B> std::string h_show(const std::pair<A, B> &p) { return "(" + h_show(p.first) + ", " + h_show(p.second) + ")"; }
template <class T> std::string h_show(const std::optional<T> &o) { return o ? "some(" + h_show(*o) + ")" : std::string("none"); }

template <class T> std::string h_show(const T &v) {
    if constexpr (std::is_enum_v<T>) {
        return std::to_string(static_cast<long long>(v));
    } else if constexpr (std::is_floating_point_v<T>) {
        char buf[48];
        std::snprintf(buf, sizeof buf, "%.10g", static_cast<double>(v));
        return buf;
    } else if constexpr (std::is_arithmetic_v<T>) {
        return std::to_string(v);
    } else if constexpr (h_is_seq<T>::value) {
        std::string s = "[";
        bool first = true;
        for (const auto &x : v) {
            if (!first) s += ", ";
            first = false;
            s += h_show(x);
        }
        return s + "]";
    } else {
        return "<value>";
    }
}

/* equality that is safe for integers of different signedness */
template <class A, class B> bool h_eq(const A &a, const B &b) {
    if constexpr (std::is_integral_v<A> && std::is_integral_v<B> && !std::is_same_v<A, bool> && !std::is_same_v<B, bool>) {
        if constexpr (std::is_signed_v<A> == std::is_signed_v<B>) {
            return a == b;
        } else if constexpr (std::is_signed_v<A>) {
            return a >= 0 && static_cast<std::make_unsigned_t<A>>(a) == b;
        } else {
            return b >= 0 && a == static_cast<std::make_unsigned_t<B>>(b);
        }
    } else {
        return a == b;
    }
}

#define CHECK(cond) do { \
    h_checks++; \
    if (!(cond)) { h_fails++; std::printf("FAIL %s:%d: check failed: %s\n", __FILE__, __LINE__, #cond); } \
} while (0)

#define CHECK_EQ(got, want) do { \
    auto g_ = (got); \
    auto w_ = (want); \
    h_checks++; \
    if (!h_eq(g_, w_)) { \
        h_fails++; \
        std::printf("FAIL %s:%d: %s: got %s, want %s\n", __FILE__, __LINE__, #got, h_show(g_).c_str(), h_show(w_).c_str()); } \
} while (0)

#define CHECK_EQ_CTX(ctx, got, want) do { \
    auto g_ = (got); \
    auto w_ = (want); \
    h_checks++; \
    if (!h_eq(g_, w_)) { \
        h_fails++; \
        std::printf("FAIL %s:%d: [%s] %s: got %s, want %s\n", __FILE__, __LINE__, std::string(ctx).c_str(), #got, h_show(g_).c_str(), h_show(w_).c_str()); } \
} while (0)

#define CHECK_THROWS(expr, ExType) do { \
    bool threw_ = false; \
    h_checks++; \
    try { (void)(expr); } catch (const ExType &) { threw_ = true; } catch (...) { } \
    if (!threw_) { h_fails++; std::printf("FAIL %s:%d: %s: expected %s to be thrown\n", __FILE__, __LINE__, #expr, #ExType); } \
} while (0)

static int h_report() {
    std::printf("%d checks, %d failed\n", h_checks, h_fails);
    return h_fails ? 1 : 0;
}

#endif
'''

PHP_HARNESS = r'''// ---- tiny test harness -------------------------------------------------------------------------------------
error_reporting(E_ALL);
ini_set('memory_limit', '256M');
set_time_limit(20);
set_error_handler(function ($no, $str, $file, $line) {
    throw new ErrorException($str, 0, $no, $file, $line);
});
$T = ['checks' => 0, 'fails' => 0, 'test' => ''];

function t_clean(string $s): string {
    return preg_replace('~\S*\.php(?::\d+| on line \d+|\(\d+\))?~', '<file>', $s);
}
function t_show($v): string {
    $j = json_encode($v, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_PRESERVE_ZERO_FRACTION | JSON_PARTIAL_OUTPUT_ON_ERROR);
    return $j === false ? gettype($v) : $j;
}
function t_fail(string $msg): void {
    global $T;
    $T['fails']++;
    echo "FAIL {$T['test']}: $msg\n";
}
function eq($got, $want, string $label = ''): void {
    global $T;
    $T['checks']++;
    if ($got !== $want) {
        t_fail(($label !== '' ? "$label: " : '') . 'got ' . t_show($got) . ', want ' . t_show($want));
    }
}
function ok($cond, string $label = ''): void {
    global $T;
    $T['checks']++;
    if (!$cond) {
        t_fail('check failed' . ($label !== '' ? ": $label" : ''));
    }
}
function raises(callable $f, string $class, string $label = ''): void {
    global $T;
    $T['checks']++;
    try {
        $f();
    } catch (Throwable $e) {
        if ($e instanceof $class) {
            return;
        }
        t_fail(($label !== '' ? "$label: " : '') . "expected $class, got " . get_class($e));
        return;
    }
    t_fail(($label !== '' ? "$label: " : '') . "expected $class to be thrown");
}
function test(string $name, callable $f): void {
    global $T;
    $T['test'] = $name;
    try {
        $f();
    } catch (Throwable $e) {
        t_fail('uncaught ' . get_class($e) . ': ' . t_clean($e->getMessage()));
    }
}
function t_done(): void {
    global $T;
    echo "{$T['checks']} checks, {$T['fails']} failed\n";
    exit($T['fails'] ? 1 : 0);
}
// ---- end of harness ---------------------------------------------------------------------------------------
'''

_PID = re.compile(r"^==\d+==.*$\n?", re.M)


_NICE_VERIFY = {
    "c": "The test program (`src/*.c` and `tests/*.c` compiled with `gcc -fsanitize=address,undefined`, then run as `./build/tests`)",
    "cpp": "The test program (`src/*.cpp` and `tests/*.cpp` compiled with `g++ -std=c++17 -fsanitize=address,undefined`, then run as `./build/tests`)",
    "php": "The PHP test script (run with `php` from the repository root)",
}


def _scrub(task: Task, hidden: list[str], verify: str = "", lang: str = "") -> Task:
    """Make a prompt independent of process ids and free of the hidden test paths; shorten the long verify command."""
    p = _PID.sub("", task.prompt)
    p = p.replace(" (0xADDR)", "")
    if verify and lang in _NICE_VERIFY and f"`{verify}`" in p:
        p = p.replace(f"`{verify}`", _NICE_VERIFY[lang])
    for h in hidden:
        if h in p:
            base = h.rsplit("/", 1)[-1]
            p = "\n".join(ln for ln in p.split("\n") if h not in ln and base not in ln)
    return task.with_(prompt=p) if p != task.prompt else task


_PLACEHOLDER = re.compile(r"\{[a-z_]+\}")


def _voice(lib, task: Task, hidden: list[str], rng: random.Random) -> Task:
    """Rewrite a prompt that quotes a failing run ('ci' / 'review' style) in one of several other voices."""
    r = run(merged(task.start, task.hidden), task.verify, timeout=max(lib.timeout_s, 60))
    ex = _sanitize_excerpt(r.out, hidden)
    if not ex:
        return task
    lines = [ln.replace("`", "'") for ln in ex.splitlines() if ln.strip()]
    sal = next((ln for ln in lines if re.search(r"got |want|expected|FAIL", ln)), lines[0]).strip()
    sal = sal[:170]
    body = "\n".join(lines[:10])
    path = sorted(task.solution)[0]
    t, blurb = lib.title, lib.blurb
    T = t[:1].upper() + t[1:]
    voices = [
        ("ticket", f"**Bug: wrong results from {t}**\n\n{blurb}\n\nThe nightly regression run now fails with this output (trimmed):\n\n```\n{body}\n```\n\n"
                   f"`README.md` is the specification and it has not changed. Please find the cause in the code and fix it."),
        ("chat", f"{T} broke somewhere between yesterday and today: `{sal}`. The README is still the spec. Can you find what changed in the code and fix it? The tests are off limits."),
        ("pr", f"While reviewing a refactor I noticed that {t} no longer behaves as `README.md` says. The change is somewhere in `{path}`. The suite reports:\n\n    {sal}\n\n"
               f"Please fix the implementation (not the tests) so that it matches the specification again."),
        ("brief", f"Context: {blurb}\n\nProblem: since the last release some checks of {t} fail; the first one reads\n\n    {sal}\n\n"
                  f"Scope: only the source files may change, the documented behaviour in `README.md` stays as it is, and the public API must not change. Keep the fix small and targeted."),
        ("terse", f"{T}: `{sal}` - this used to pass and the README has not changed. Please fix the code, not the tests."),
        ("handover", f"I'm handing over a half-finished investigation. {blurb} One of the checks fails with `{sal}`; I suspect `{path}` but did not get further. "
                     f"The specification is `README.md`. Please finish the job and fix the defect."),
    ]
    name, text = voices[rng.randrange(len(voices))]
    if _PLACEHOLDER.search(text):
        name = "spec"
        text = (f"{blurb} After a recent edit, {t} no longer behaves as `README.md` says in at least one case. The change touched `{path}`. "
                f"Compare the code with the specification, find the discrepancy and fix it.")
    tags = [name if x == task.notes.get("style") else x for x in task.tags]
    return task.with_(prompt=text, tags=tags, notes={**task.notes, "style": name})


def add(lib, n: int = 8, max_candidates: int | None = None) -> None:
    """Register ``fix-<c|cpp|php>-<name>`` for ``lib`` (like fx.register_libs, with a bigger candidate budget)."""
    budget = max_candidates or (70 if lib.lang == "php" else 90)
    fam = Family(name=f"fix-{LANG_PREFIX.get(lib.lang, lib.lang)}-{lib.name}", category="fix", lang=lib.lang, kind="fix", n=n,
                 summary=f"injected bugs in {lib.title} ({lib.lang})")

    def gen(rng, count, _lib=lib):
        hidden = sorted(_lib.hidden_tests)
        out = []
        for t in mutation_tasks(_lib, rng, count, max_candidates=budget):
            if t.notes.get("style") in ("ci", "review"):
                t = _voice(_lib, t, hidden, random.Random(f"{_lib.name}/{t.slug}"))
            out.append(_scrub(t, hidden, _lib.verify, _lib.lang))
        return out

    gen.__module__ = lib.__class__.__module__
    register(fam, gen)
    LIBS[lib.name] = lib


LIBS: dict = {}


def c_tests(visible: str) -> dict[str, str]:
    return {"tests/test_main.c": visible, "tests/harness.h": C_HARNESS}


def cpp_tests(visible: str) -> dict[str, str]:
    return {"tests/test_main.cpp": visible, "tests/harness.hpp": CPP_HARNESS}


def php_test(body: str) -> str:
    """A tests/run.php from the part between the harness and the end (the body must call t_done() itself)."""
    return "<?php\n" + PHP_HARNESS + "\n" + body
