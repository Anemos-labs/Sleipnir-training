"""Helpers shared by the clib_* / cpplib_* / phplib_* modules (fix-lang-3): test harnesses, verify commands, registration.

The harnesses are ordinary files of the *visible* test tree (C, C++) or are pasted into ``tests/run.php`` (PHP), so every
library reports failures in the same one-line-per-failed-check style and a crash or a hang is reported crisply instead of
silently passing.
"""
from __future__ import annotations

import re

from fx import Family, Task, mutation_tasks, register
from fx.lib import LANG_PREFIX

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
#include <iostream>
#include <map>
#include <optional>
#include <sstream>
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
    std::ios::sync_with_stdio(true);
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
    } else if constexpr (std::is_arithmetic_v<T>) {
        std::ostringstream os;
        os << v;
        return os.str();
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
        std::ostringstream os;
        os << v;
        return os.str();
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
    if (!(g_ == w_)) { \
        h_fails++; \
        std::printf("FAIL %s:%d: %s: got %s, want %s\n", __FILE__, __LINE__, #got, h_show(g_).c_str(), h_show(w_).c_str()); } \
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
}


def _scrub(task: Task, hidden: list[str], verify: str = "", lang: str = "") -> Task:
    """Make a prompt independent of process ids and free of the hidden test paths; shorten the long verify command."""
    p = _PID.sub("", task.prompt)
    if verify and lang in _NICE_VERIFY and f"`{verify}`" in p:
        p = p.replace(f"`{verify}`", _NICE_VERIFY[lang])
    for h in hidden:
        if h in p:
            base = h.rsplit("/", 1)[-1]
            p = "\n".join(ln for ln in p.split("\n") if h not in ln and base not in ln)
    return task.with_(prompt=p) if p != task.prompt else task


def add(lib, n: int = 8, max_candidates: int | None = None) -> None:
    """Register ``fix-<c|cpp|php>-<name>`` for ``lib`` (like fx.register_libs, with a bigger candidate budget)."""
    budget = max_candidates or (70 if lib.lang == "php" else 90)
    fam = Family(name=f"fix-{LANG_PREFIX.get(lib.lang, lib.lang)}-{lib.name}", category="fix", lang=lib.lang, kind="fix", n=n,
                 summary=f"injected bugs in {lib.title} ({lib.lang})")

    def gen(rng, count, _lib=lib):
        hidden = sorted(_lib.hidden_tests)
        return [_scrub(t, hidden, _lib.verify, _lib.lang) for t in mutation_tasks(_lib, rng, count, max_candidates=budget)]

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
