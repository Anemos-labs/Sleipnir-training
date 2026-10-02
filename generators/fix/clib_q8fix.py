"""Q24.8 fixed-point arithmetic (c): saturating add/mul/div, half-away rounding, decimal parse/format and an integer square root; bugs injected into the library."""
from fx import Lib, dd

from generators.fix import _lang3

README1 = dd(r'''
    # q8fix

    Fixed-point helpers for a thermostat controller that has no floating-point unit. A `q8` is an `int32_t` holding the
    value times 256 (so 1.0 is `256`, 0.5 is `128`, and the resolution is 1/256).

    The legal range is symmetric: `Q8_MAX = 2147483647` and `Q8_MIN = -2147483647` (never `INT32_MIN`), so negating a legal
    value cannot overflow. Every operation that can leave the range **saturates**: the result is clamped to
    `[Q8_MIN, Q8_MAX]`.

    Wherever a result is rounded, rounding is to the nearest representable value with ties going **away from zero**
    (`2.5 -> 3`, `-2.5 -> -3`).

    ## Conversions and simple arithmetic

    * `q8 q8_from_int(int n)`: `n * 256`, saturated.
    * `int q8_to_int(q8 x)`: `x / 256` rounded as above (`q8_to_int(384) == 2`, `q8_to_int(-384) == -2`,
      `q8_to_int(127) == 0`, `q8_to_int(128) == 1`).
    * `q8 q8_add(q8 a, q8 b)`, `q8 q8_sub(q8 a, q8 b)`: saturating.
    * `q8 q8_neg(q8 x)` and `q8 q8_abs(q8 x)`.
    * `q8 q8_clamp(q8 x, q8 lo, q8 hi)`: if `lo > hi` the two bounds are swapped first.

    ## Multiplication, division, square root

    * `q8 q8_mul(q8 a, q8 b)`: the product `a*b/256`, rounded, saturated.
    * `q8 q8_div(q8 a, q8 b)`: the quotient `a*256/b`, rounded, saturated. Division by zero saturates to `Q8_MAX` when
      `a > 0`, `Q8_MIN` when `a < 0` and gives `0` when `a == 0`.
    * `q8 q8_sqrt(q8 x)`: the largest `r` with `r*r <= x*256` (the square root rounded *down*); `0` for `x <= 0`.
    * `q8 q8_lerp(q8 a, q8 b, q8 t)`: `a + (b - a) * t`, where `t` is first clamped to `[0, 256]` (that is 0.0 to 1.0).
      The difference `b - a` is not saturated, only the final result is; the product `(b - a) * t / 256` is rounded as
      above before it is added to `a`.

    ## Text

    * `int q8_parse(const char *s, size_t n, q8 *out)` reads the first `n` characters of `s` (not necessarily
      NUL-terminated) as `[+-]digits[.digits]`: at least one digit overall (`.5`, `5.` and `-0.25` are fine, `.` and
      `+` are not), no spaces, no exponent, nothing after the number. The value is rounded to the nearest 1/256, ties away
      from zero; any number of fraction digits is accepted. Returns 0 and sets `*out`, or -1 (leaving `*out` alone) when
      the text is malformed or the value is outside `[Q8_MIN, Q8_MAX]` after rounding.
    * `int q8_format(q8 x, char *buf, size_t cap, int decimals)` writes `x` in decimal with exactly `decimals` digits after
      the point (`0..6`; with 0 there is no point), rounded from the exact binary value with ties away from zero, followed
      by a NUL. A negative value gets a `-`, except when it rounds to zero (`-0.001` with 2 decimals is `0.00`). Returns the
      text length, or -1 when `decimals` is out of range or the text and its NUL do not fit in `cap` (the contents of
      `buf` are then unspecified, but nothing is ever written beyond `cap` bytes).
''')

F2 = dd(r'''
    #ifndef Q8FIX_H
    #define Q8FIX_H

    #include <stddef.h>
    #include <stdint.h>

    typedef int32_t q8;

    #define Q8_MAX 2147483647
    #define Q8_MIN (-2147483647)

    q8 q8_from_int(int n);
    int q8_to_int(q8 x);
    q8 q8_add(q8 a, q8 b);
    q8 q8_sub(q8 a, q8 b);
    q8 q8_neg(q8 x);
    q8 q8_abs(q8 x);
    q8 q8_clamp(q8 x, q8 lo, q8 hi);
    q8 q8_mul(q8 a, q8 b);
    q8 q8_div(q8 a, q8 b);
    q8 q8_sqrt(q8 x);
    q8 q8_lerp(q8 a, q8 b, q8 t);
    int q8_parse(const char *s, size_t n, q8 *out);
    int q8_format(q8 x, char *buf, size_t cap, int decimals);

    #endif
''')

F3 = dd(r'''
    #include "q8fix.h"

    #include <stdio.h>

    static q8 sat(int64_t v) {
        if (v > Q8_MAX) return Q8_MAX;
        if (v < Q8_MIN) return Q8_MIN;
        return (q8)v;
    }

    /* n / d rounded to nearest, ties away from zero; d > 0. */
    static int64_t div_round(int64_t n, int64_t d) {
        if (n >= 0) return (n + d / 2) / d;
        return -((-n + d / 2) / d);
    }

    q8 q8_from_int(int n) { return sat((int64_t)n * 256); }

    int q8_to_int(q8 x) { return (int)div_round(x, 256); }

    q8 q8_add(q8 a, q8 b) { return sat((int64_t)a + b); }

    q8 q8_sub(q8 a, q8 b) { return sat((int64_t)a - b); }

    q8 q8_neg(q8 x) { return sat(-(int64_t)x); }

    q8 q8_abs(q8 x) { return x < 0 ? q8_neg(x) : x; }

    q8 q8_clamp(q8 x, q8 lo, q8 hi) {
        if (lo > hi) {
            q8 t = lo;
            lo = hi;
            hi = t;
        }
        if (x < lo) return lo;
        if (x > hi) return hi;
        return x;
    }

    q8 q8_mul(q8 a, q8 b) { return sat(div_round((int64_t)a * b, 256)); }

    q8 q8_div(q8 a, q8 b) {
        int64_t num = (int64_t)a * 256, den = b;
        if (b == 0) return a > 0 ? Q8_MAX : (a < 0 ? Q8_MIN : 0);
        if (den < 0) {
            num = -num;
            den = -den;
        }
        return sat(div_round(num, den));
    }

    static uint64_t isqrt64(uint64_t n) {
        uint64_t r = 0, bit = (uint64_t)1 << 62;
        while (bit > n) bit >>= 2;
        while (bit != 0) {
            if (n >= r + bit) {
                n -= r + bit;
                r = (r >> 1) + bit;
            } else {
                r >>= 1;
            }
            bit >>= 2;
        }
        return r;
    }

    q8 q8_sqrt(q8 x) {
        if (x <= 0) return 0;
        return (q8)isqrt64((uint64_t)x << 8);
    }

    q8 q8_lerp(q8 a, q8 b, q8 t) {
        int64_t diff = (int64_t)b - a;
        if (t < 0) t = 0;
        if (t > 256) t = 256;
        return sat((int64_t)a + div_round(diff * t, 256));
    }

    int q8_parse(const char *s, size_t n, q8 *out) {
        size_t i = 0;
        int neg = 0, digits = 0, fdigits = 0;
        int64_t whole = 0, frac = 0, mag;
        if (i < n && (s[i] == '+' || s[i] == '-')) {
            neg = s[i] == '-';
            i++;
        }
        for (; i < n && s[i] >= '0' && s[i] <= '9'; i++) {
            whole = whole * 10 + (s[i] - '0');
            if (whole > 8388608) return -1;
            digits++;
        }
        if (i < n && s[i] == '.') {
            i++;
            for (; i < n && s[i] >= '0' && s[i] <= '9'; i++) {
                if (fdigits < 9) {
                    frac = frac * 10 + (s[i] - '0');
                    fdigits++;
                }
                digits++;
            }
        }
        if (digits == 0 || i != n) return -1;
        while (fdigits < 9) {
            frac *= 10;
            fdigits++;
        }
        mag = whole * 256 + div_round(frac * 256, 1000000000);
        if (mag > Q8_MAX) return -1;
        *out = (q8)(neg ? -mag : mag);
        return 0;
    }

    int q8_format(q8 x, char *buf, size_t cap, int decimals) {
        static const int64_t POW10[] = {1, 10, 100, 1000, 10000, 100000, 1000000};
        int64_t mag, scaled, whole, frac;
        int len;
        const char *sign;
        if (decimals < 0 || decimals > 6) return -1;
        mag = x < 0 ? -(int64_t)x : (int64_t)x;
        scaled = div_round(mag * POW10[decimals], 256);
        whole = scaled / POW10[decimals];
        frac = scaled % POW10[decimals];
        sign = (x < 0 && scaled != 0) ? "-" : "";
        if (decimals == 0) {
            len = snprintf(buf, cap, "%s%lld", sign, (long long)whole);
        } else {
            len = snprintf(buf, cap, "%s%lld.%0*lld", sign, (long long)whole, decimals, (long long)frac);
        }
        if (len < 0 || (size_t)len >= cap) return -1;
        return len;
    }
''')

V4 = dd(r'''
    #include "harness.h"
    #include "q8fix.h"

    int main(void) {
        q8 v = 0;
        h_init();

        CHECK_INT(q8_from_int(3), 768);
        CHECK_INT(q8_mul(640, 384), 960);
        CHECK_INT(q8_parse("1.5", 3, &v), 0);
        CHECK_INT(v, 384);
        return h_report();
    }
''')

H5 = dd(r'''
    #include <limits.h>
    #include <stdio.h>
    #include <stdlib.h>
    #include <string.h>

    #include "harness.h"
    #include "q8fix.h"

    static char *exact(const char *s, size_t n) {
        char *p = malloc(n ? n : 1);
        memcpy(p, s, n);
        return p;
    }

    /* parse a whole string (held in an exact-size block); returns 0 and sets *out, or -1 */
    static int parse(const char *text, q8 *out) {
        size_t n = strlen(text);
        char *p = exact(text, n);
        int rc = q8_parse(p, n, out);
        free(p);
        return rc;
    }

    /* format into a block of exactly cap bytes */
    static int format_cap(q8 x, size_t cap, int decimals, char *copy /* at least cap+1 */) {
        char *p = malloc(cap ? cap : 1);
        int rc = q8_format(x, p, cap, decimals);
        if (rc >= 0) {
            memcpy(copy, p, (size_t)rc + 1);
        }
        free(p);
        return rc;
    }

    static void test_conversions(void) {
        static const struct { int in; q8 out; } from[] = {
            {0, 0}, {1, 256}, {-1, -256}, {100, 25600}, {8388607, 2147483392}, {8388608, Q8_MAX}, {-8388607, -2147483392},
            {-8388608, Q8_MIN}, {INT_MAX, Q8_MAX}, {INT_MIN, Q8_MIN},
        };
        static const struct { q8 in; int out; } to[] = {
            {0, 0}, {127, 0}, {128, 1}, {129, 1}, {255, 1}, {256, 1}, {383, 1}, {384, 2}, {-127, 0}, {-128, -1}, {-129, -1},
            {-384, -2}, {-383, -1}, {Q8_MAX, 8388608}, {Q8_MIN, -8388608}, {640, 3}, {-640, -3},
        };
        size_t i;
        char ctx[40];
        for (i = 0; i < sizeof from / sizeof from[0]; i++) {
            snprintf(ctx, sizeof ctx, "from_int(%d)", from[i].in);
            CHECK_INT_CTX(ctx, q8_from_int(from[i].in), from[i].out);
        }
        for (i = 0; i < sizeof to / sizeof to[0]; i++) {
            snprintf(ctx, sizeof ctx, "to_int(%d)", (int)to[i].in);
            CHECK_INT_CTX(ctx, q8_to_int(to[i].in), to[i].out);
        }
    }

    static void test_add_sub_neg_abs_clamp(void) {
        CHECK_INT(q8_add(100, 200), 300);
        CHECK_INT(q8_add(100, -300), -200);
        CHECK_INT(q8_add(Q8_MAX, 1), Q8_MAX);
        CHECK_INT(q8_add(Q8_MAX, Q8_MAX), Q8_MAX);
        CHECK_INT(q8_add(Q8_MAX - 5, 5), Q8_MAX);
        CHECK_INT(q8_add(Q8_MAX - 5, 4), Q8_MAX - 1);
        CHECK_INT(q8_add(Q8_MIN, -1), Q8_MIN);
        CHECK_INT(q8_add(Q8_MIN + 5, -5), Q8_MIN);
        CHECK_INT(q8_add(Q8_MIN + 5, -4), Q8_MIN + 1);
        CHECK_INT(q8_add(Q8_MAX, Q8_MIN), 0);
        CHECK_INT(q8_sub(5, 7), -2);
        CHECK_INT(q8_sub(-5, -7), 2);
        CHECK_INT(q8_sub(Q8_MIN, 1), Q8_MIN);
        CHECK_INT(q8_sub(Q8_MAX, -1), Q8_MAX);
        CHECK_INT(q8_sub(Q8_MAX, Q8_MIN), Q8_MAX);
        CHECK_INT(q8_sub(Q8_MIN, Q8_MAX), Q8_MIN);
        CHECK_INT(q8_sub(Q8_MIN, Q8_MIN), 0);
        CHECK_INT(q8_neg(5), -5);
        CHECK_INT(q8_neg(-5), 5);
        CHECK_INT(q8_neg(0), 0);
        CHECK_INT(q8_neg(Q8_MAX), Q8_MIN);
        CHECK_INT(q8_neg(Q8_MIN), Q8_MAX);
        CHECK_INT(q8_abs(7), 7);
        CHECK_INT(q8_abs(-7), 7);
        CHECK_INT(q8_abs(0), 0);
        CHECK_INT(q8_abs(Q8_MIN), Q8_MAX);
        CHECK_INT(q8_abs(Q8_MAX), Q8_MAX);
        CHECK_INT(q8_clamp(5, 0, 10), 5);
        CHECK_INT(q8_clamp(-5, 0, 10), 0);
        CHECK_INT(q8_clamp(15, 0, 10), 10);
        CHECK_INT(q8_clamp(0, 0, 10), 0);
        CHECK_INT(q8_clamp(10, 0, 10), 10);
        CHECK_INT(q8_clamp(5, 10, 0), 5);
        CHECK_INT(q8_clamp(15, 10, 0), 10);
        CHECK_INT(q8_clamp(-5, 10, 0), 0);
        CHECK_INT(q8_clamp(-5, -2, -9), -5);
        CHECK_INT(q8_clamp(-50, -2, -9), -9);
        CHECK_INT(q8_clamp(3, 4, 4), 4);
    }

    static void test_mul(void) {
        static const struct { q8 a, b, out; } c[] = {
            {640, 384, 960}, {-640, 384, -960}, {640, -384, -960}, {-640, -384, 960}, {3, 128, 2}, {1, 128, 1}, {-1, 128, -1},
            {-3, 128, -2}, {1, 127, 0}, {-1, 127, 0}, {255, 255, 254}, {-255, 255, -254}, {100000, 100000, 39062500},
            {Q8_MAX, 512, Q8_MAX}, {Q8_MAX, -512, Q8_MIN}, {Q8_MIN, Q8_MIN, Q8_MAX}, {741456, 741456, Q8_MAX},
            {741455, 741455, 2147482488}, {0, Q8_MAX, 0}, {256, 12345, 12345}, {Q8_MAX, 256, Q8_MAX},
        };
        size_t i;
        char ctx[48];
        for (i = 0; i < sizeof c / sizeof c[0]; i++) {
            snprintf(ctx, sizeof ctx, "mul(%d, %d)", (int)c[i].a, (int)c[i].b);
            CHECK_INT_CTX(ctx, q8_mul(c[i].a, c[i].b), c[i].out);
        }
    }

    static void test_div(void) {
        static const struct { q8 a, b, out; } c[] = {
            {256, 768, 85}, {512, 768, 171}, {-256, 768, -85}, {256, -768, -85}, {-256, -768, 85}, {1, 2, 128}, {1, -2, -128},
            {3, 2, 384}, {5, 0, Q8_MAX}, {-5, 0, Q8_MIN}, {0, 0, 0}, {0, 7, 0}, {Q8_MAX, 1, Q8_MAX}, {Q8_MIN, 1, Q8_MIN},
            {Q8_MAX, -1, Q8_MIN}, {1000, 3, 85333}, {1, 512, 1}, {-1, 512, -1}, {256, 1000, 66}, {Q8_MAX, Q8_MAX, 256},
            {Q8_MIN, Q8_MAX, -256}, {Q8_MAX, 128, Q8_MAX}, {-7, -2, 896}, {1, 513, 0}, {1, 3, 85},
        };
        size_t i;
        char ctx[48];
        for (i = 0; i < sizeof c / sizeof c[0]; i++) {
            snprintf(ctx, sizeof ctx, "div(%d, %d)", (int)c[i].a, (int)c[i].b);
            CHECK_INT_CTX(ctx, q8_div(c[i].a, c[i].b), c[i].out);
        }
    }

    static void test_sqrt(void) {
        static const struct { q8 in, out; } c[] = {
            {0, 0}, {1, 16}, {255, 255}, {256, 256}, {257, 256}, {512, 362}, {1024, 512}, {1000, 505}, {65536, 4096},
            {262144, 8192}, {Q8_MAX, 741455}, {-5, 0}, {Q8_MIN, 0}, {2, 22}, {3, 27}, {64, 128}, {63, 126}, {16384, 2048},
        };
        size_t i;
        char ctx[40];
        for (i = 0; i < sizeof c / sizeof c[0]; i++) {
            snprintf(ctx, sizeof ctx, "sqrt(%d)", (int)c[i].in);
            CHECK_INT_CTX(ctx, q8_sqrt(c[i].in), c[i].out);
        }
        /* the defining property */
        for (i = 1; i < 3000; i += 7) {
            long long r = q8_sqrt((q8)(i * 331));
            long long x = (long long)(i * 331) * 256;
            CHECK(r * r <= x);
            CHECK((r + 1) * (r + 1) > x);
        }
    }

    static void test_lerp(void) {
        static const struct { q8 a, b, t, out; } c[] = {
            {0, 2560, 128, 1280}, {2560, 0, 64, 1920}, {0, 256, 1, 1}, {0, 256, 129, 129}, {0, -256, 129, -129},
            {-300, 300, 300, 300}, {Q8_MIN, Q8_MAX, 256, Q8_MAX}, {Q8_MIN, Q8_MAX, 128, 0}, {Q8_MIN, Q8_MAX, -9, Q8_MIN},
            {5, 10, 0, 5}, {5, 10, 256, 10}, {1000, 2000, 85, 1332}, {1000, 2000, 171, 1668}, {100, 50, 128, 75},
            {5, 10, 257, 10}, {5, 10, 100000, 10}, {5, 10, -1, 5}, {Q8_MAX, Q8_MIN, 256, Q8_MIN}, {Q8_MAX, Q8_MIN, 0, Q8_MAX},
            {0, 3, 128, 2}, {0, -3, 128, -2},
        };
        size_t i;
        char ctx[56];
        for (i = 0; i < sizeof c / sizeof c[0]; i++) {
            snprintf(ctx, sizeof ctx, "lerp(%d, %d, %d)", (int)c[i].a, (int)c[i].b, (int)c[i].t);
            CHECK_INT_CTX(ctx, q8_lerp(c[i].a, c[i].b, c[i].t), c[i].out);
        }
    }

    static void test_parse_ok(void) {
        static const struct { const char *text; q8 out; } c[] = {
            {"0", 0}, {"1", 256}, {"1.5", 384}, {"-1.5", -384}, {"+2", 512}, {".5", 128}, {"5.", 1280}, {"-0.25", -64},
            {"0.001953125", 1}, {"-0.001953125", -1}, {"0.0019531249999", 0}, {"0.001953125000000001", 1},
            {"0.00195312499999999", 0}, {"0.0009765625", 0}, {"0.0029296875", 1}, {"0.00292968749", 1}, {"0.005859375", 2}, {"0.005859374", 1}, {"0.0029296875001", 1}, {"8388607.998", 2147483647}, {"8388607.998046874", 2147483647}, {"-8388607.998046874", -2147483647},
            {"8388607.99609375", Q8_MAX}, {"-8388607.99609375", Q8_MIN}, {"8388607", 2147483392},
            {"000000000000000000000001.5", 384}, {"0.5000000000000000000000001", 128}, {"-0", 0}, {"+0.0", 0},
            {"12.375", 3168}, {"100.1", 25626}, {"-100.1", -25626}, {"0.1", 26}, {"0.3", 77}, {"0.7", 179}, {"3.14159", 804},
            {"1.99999", 512}, {"-1.99999", -512}, {"0.00390625", 1}, {"0.004", 1}, {"0.0019", 0}, {"7.0000000001", 1792},
        };
        size_t i;
        for (i = 0; i < sizeof c / sizeof c[0]; i++) {
            q8 v = 12345;
            CHECK_INT_CTX(c[i].text, parse(c[i].text, &v), 0);
            CHECK_INT_CTX(c[i].text, v, c[i].out);
        }
    }

    static void test_parse_bad(void) {
        static const char *bad[] = {
            "", "+", "-", ".", "-.", "+.", "1e3", " 1", "1 ", "1.2.3", "--1", "+-1", "0x10", "abc", "1,5", "1.5f", "1_000",
            "8388608", "-8388608", "8388607.998046875", "8388607.99805", "-8388607.998046875", "-8388607.99805", "99999999999999999999", "9999999999",
            "-9999999999.5", "08388608", "8388608.0", "1.5\n", "\t1.5", ".e", "1..5", "1.-5", "-1.5-",
        };
        size_t i;
        for (i = 0; i < sizeof bad / sizeof bad[0]; i++) {
            q8 v = 777;
            CHECK_INT_CTX(bad[i], parse(bad[i], &v), -1);
            CHECK_INT_CTX(bad[i], v, 777);
        }
    }

    static void test_parse_length(void) {
        q8 v = 5;
        char *p = exact("1.5abc", 6);
        CHECK_INT(q8_parse(p, 3, &v), 0);
        CHECK_INT(v, 384);
        CHECK_INT(q8_parse(p, 4, &v), -1);
        CHECK_INT(q8_parse(p, 2, &v), 0);
        CHECK_INT(v, 256 + 0);  /* "1." */
        CHECK_INT(q8_parse(p, 1, &v), 0);
        CHECK_INT(v, 256);
        CHECK_INT(q8_parse(p, 0, &v), -1);
        free(p);
        p = exact("-", 1);
        CHECK_INT(q8_parse(p, 1, &v), -1);
        free(p);
        p = exact("7", 1);
        CHECK_INT(q8_parse(p, 1, &v), 0);
        CHECK_INT(v, 1792);
        free(p);
    }

    static void test_format(void) {
        static const struct { q8 x; int dec; const char *text; } c[] = {
            {384, 0, "2"}, {-384, 0, "-2"}, {128, 0, "1"}, {127, 0, "0"}, {-128, 0, "-1"}, {-127, 0, "0"}, {1, 2, "0.00"},
            {-1, 2, "0.00"}, {2, 2, "0.01"}, {-2, 2, "-0.01"}, {3, 2, "0.01"}, {384, 2, "1.50"}, {448, 3, "1.750"},
            {1, 6, "0.003906"}, {Q8_MAX, 0, "8388608"}, {Q8_MIN, 3, "-8388607.996"}, {Q8_MAX, 6, "8388607.996094"},
            {0, 4, "0.0000"}, {-1, 6, "-0.003906"}, {255, 1, "1.0"}, {26, 1, "0.1"}, {-26, 1, "-0.1"}, {13, 1, "0.1"},
            {12, 1, "0.0"}, {-12, 1, "0.0"}, {0, 0, "0"}, {256, 0, "1"}, {25626, 1, "100.1"}, {-25626, 2, "-100.10"},
            {2560, 5, "10.00000"}, {1, 3, "0.004"}, {5, 3, "0.020"}, {-5, 3, "-0.020"}, {99, 1, "0.4"}, {100, 1, "0.4"},
            {115, 2, "0.45"}, {-115, 2, "-0.45"}, {Q8_MAX, 1, "8388608.0"}, {3, 4, "0.0117"}, {2559, 0, "10"},
        };
        size_t i;
        char copy[32], ctx[40];
        for (i = 0; i < sizeof c / sizeof c[0]; i++) {
            size_t len = strlen(c[i].text);
            snprintf(ctx, sizeof ctx, "format(%d, %d)", (int)c[i].x, c[i].dec);
            memset(copy, '?', sizeof copy);
            CHECK_INT_CTX(ctx, format_cap(c[i].x, len + 1, c[i].dec, copy), (long long)len);
            CHECK_STR_CTX(ctx, copy, c[i].text);
            /* one byte less is not enough */
            CHECK_INT_CTX(ctx, format_cap(c[i].x, len, c[i].dec, copy), -1);
            /* a roomy buffer gives the same text */
            CHECK_INT_CTX(ctx, format_cap(c[i].x, 30, c[i].dec, copy), (long long)len);
            CHECK_STR_CTX(ctx, copy, c[i].text);
        }
    }

    static void test_format_args(void) {
        char buf[32];
        CHECK_INT(q8_format(256, buf, sizeof buf, -1), -1);
        CHECK_INT(q8_format(256, buf, sizeof buf, 7), -1);
        CHECK_INT(q8_format(256, buf, sizeof buf, 0), 1);
        CHECK_INT(q8_format(256, buf, sizeof buf, 6), 8);
        CHECK_INT(q8_format(256, buf, 0, 2), -1);
        CHECK_INT(q8_format(256, buf, 1, 0), -1);
        CHECK_INT(q8_format(256, buf, 2, 0), 1);
    }

    static void test_roundtrip(void) {
        q8 vals[] = {0, 1, -1, 255, 256, -257, 12345, -98765, 2560000, Q8_MAX, Q8_MIN, 1 << 20, -(1 << 24)};
        size_t i;
        for (i = 0; i < sizeof vals / sizeof vals[0]; i++) {
            char txt[40];
            q8 back = 1;
            int n = q8_format(vals[i], txt, sizeof txt, 6);
            CHECK(n > 0);
            /* six decimals are enough to identify every q8 value (1/256 = 0.00390625) */
            CHECK_INT_CTX(txt, parse(txt, &back), 0);
            CHECK_INT_CTX(txt, back, vals[i]);
        }
    }

    int main(void) {
        h_init();
        test_conversions();
        test_add_sub_neg_abs_clamp();
        test_mul();
        test_div();
        test_sqrt();
        test_lerp();
        test_parse_ok();
        test_parse_bad();
        test_parse_length();
        test_format();
        test_format_args();
        test_roundtrip();
        return h_report();
    }
''')

LIB = Lib(
    name="q8fix", lang="c", title="the q8 fixed-point library",
    blurb="The thermostat firmware does all its temperature maths in q8 fixed point (no floating point on the target).",
    files={"README.md": README1, "include/q8fix.h": F2, "src/q8fix.c": F3},
    visible_tests={"tests/test_main.c": V4, "tests/harness.h": _lang3.C_HARNESS},
    hidden_tests={"tests/test_main.c": H5},
    mutate=["src/q8fix.c"], difficulty=2, tags=["fixed-point", "saturation", "rounding"],
    verify=_lang3.C_VERIFY,
)

_lang3.add(LIB, n=8)
