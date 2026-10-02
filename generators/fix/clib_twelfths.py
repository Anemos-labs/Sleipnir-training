"""Tide heights by the rule of twelfths (c): integer interpolation between high and low water, passage windows for deep-draught boats, an under-keel check and HH:MM helpers; bugs injected into the library."""
from fx import Lib, dd

from generators.fix import _lang3

README1 = dd(r'''
    # twelfths

    A calculator for a harbour's tide table. Tide tables publish only the times and heights of high and low water; between two
    consecutive extremes the water height is estimated with the **rule of twelfths**. Times are whole **minutes** (any integer
    origin, for example minutes since midnight) and heights are whole **centimetres**. All maths is integer maths.

    ## The rule

    Take two consecutive extremes: `(t_a, h_a)` and `(t_b, h_b)` with `t_a < t_b` (the tide may be rising or falling, so `h_b` can be
    lower than `h_a`). Cut the interval `[t_a, t_b]` into six equal parts. Over the six parts the water covers 1, 2, 3, 3, 2 and 1
    twelfths of the total change `h_b - h_a`, and inside a part it moves linearly. So the fraction of the change that has
    happened at the end of each part is 1/12, 3/12, 6/12, 9/12, 11/12 and 12/12.

    For a time `t` with `x = t - t_a` and `d = t_b - t_a`: part `k = floor(6 * x / d)` (at `x == d` it is the last part, `5`);
    `r = 6 * x - k * d` is the position inside the part (`0 <= r <= d`). With `cum = {0, 1, 3, 6, 9, 11}` and
    `step = {1, 2, 3, 3, 2, 1}`:

        height = h_a + round( (h_b - h_a) * (cum[k] * d + step[k] * r) / (12 * d) )

    where `round` is to the nearest integer with ties **away from zero** (also for a falling tide, where the correction is
    negative). Use 64-bit intermediates.

    ## API (`include/twelfths.h`)

    * `int tw_height(int t_a, int h_a, int t_b, int h_b, int t)` is the height at `t` by the rule above. It returns `TW_ERR`
      (`INT_MIN`) when `t_b <= t_a` or `t` is outside `[t_a, t_b]`.
    * `int tw_phase(int t_a, int t_b, int t)` is the part number `k` (0..5) that `t` falls in, or -1 when `t_b <= t_a` or `t` is outside
      `[t_a, t_b]`.
    * `int tw_window(int t_a, int h_a, int t_b, int h_b, int min_h, int *start, int *end)` finds when a boat that needs at least `min_h`
      centimetres of water can cross: the first and the last whole minute in `[t_a, t_b]` at which `tw_height` is `>= min_h`. The
      water is always at least `min_h` between those two minutes and below it outside them. Returns 0 and sets `*start` and `*end`
      (they may be equal), or -1 (leaving both alone) when no minute qualifies or `t_b <= t_a`.
    * `int tw_safe(int depth_cm, int height_cm, int draft_cm, int margin_pct)`: 1 when the under-keel clearance
      `depth_cm + height_cm - draft_cm` is at least `ceil(draft_cm * margin_pct / 100)`, else 0. A `draft_cm <= 0` or a negative
      `margin_pct` is always 0. The computation is done in 64 bits, so extreme `int` arguments cannot overflow.
    * `int tw_fmt_hhmm(int minutes, char *buf, size_t cap)` writes `HH:MM` (24-hour clock) and a NUL. `minutes` wraps around the day:
      `1440` is `00:00` and `-30` is `23:30`. Returns 5, or -1 (writing nothing) when `cap < 6`.
    * `int tw_parse_hhmm(const char *s, size_t n, int *minutes)` reads exactly `HH:MM` from the first `n` characters of `s` (not
      necessarily NUL-terminated): two digits, a colon, two digits, hours `00..23`, minutes `00..59`. Returns 0 and sets `*minutes` to
      `HH*60 + MM`, or -1 (leaving `*minutes` alone).
''')

F2 = dd(r'''
    #ifndef TWELFTHS_H
    #define TWELFTHS_H

    #include <limits.h>
    #include <stddef.h>

    #define TW_ERR INT_MIN

    int tw_height(int t_a, int h_a, int t_b, int h_b, int t);
    int tw_phase(int t_a, int t_b, int t);
    int tw_window(int t_a, int h_a, int t_b, int h_b, int min_h, int *start, int *end);
    int tw_safe(int depth_cm, int height_cm, int draft_cm, int margin_pct);
    int tw_fmt_hhmm(int minutes, char *buf, size_t cap);
    int tw_parse_hhmm(const char *s, size_t n, int *minutes);

    #endif
''')

F3 = dd(r'''
    #include "twelfths.h"

    #include <stdint.h>
    #include <stdio.h>

    static const int CUM[6] = {0, 1, 3, 6, 9, 11};
    static const int STEP[6] = {1, 2, 3, 3, 2, 1};

    /* n / d to the nearest integer, ties away from zero; d > 0. */
    static int64_t round_div(int64_t n, int64_t d) {
        if (n >= 0) return (n + d / 2) / d;
        return -((-n + d / 2) / d);
    }

    int tw_phase(int t_a, int t_b, int t) {
        int64_t dur = (int64_t)t_b - t_a, k;
        if (dur <= 0 || t < t_a || t > t_b) return -1;
        k = 6 * ((int64_t)t - t_a) / dur;
        return k > 5 ? 5 : (int)k;
    }

    int tw_height(int t_a, int h_a, int t_b, int h_b, int t) {
        int64_t dur = (int64_t)t_b - t_a, x = (int64_t)t - t_a, num;
        int k = tw_phase(t_a, t_b, t);
        if (k < 0) return TW_ERR;
        num = CUM[k] * dur + STEP[k] * (6 * x - k * dur);
        return h_a + (int)round_div((int64_t)(h_b - h_a) * num, 12 * dur);
    }

    int tw_window(int t_a, int h_a, int t_b, int h_b, int min_h, int *start, int *end) {
        int lo, hi, mid;
        if (t_b <= t_a) return -1;
        if (h_a < min_h && h_b < min_h) return -1;
        if (h_a >= min_h && h_b >= min_h) {
            *start = t_a;
            *end = t_b;
            return 0;
        }
        lo = t_a;
        hi = t_b;
        if (h_b > h_a) {
            /* rising: height(lo) < min_h <= height(hi) */
            while (hi - lo > 1) {
                mid = lo + (hi - lo) / 2;
                if (tw_height(t_a, h_a, t_b, h_b, mid) >= min_h) hi = mid;
                else lo = mid;
            }
            *start = hi;
            *end = t_b;
        } else {
            /* falling: height(lo) >= min_h > height(hi) */
            while (hi - lo > 1) {
                mid = lo + (hi - lo) / 2;
                if (tw_height(t_a, h_a, t_b, h_b, mid) >= min_h) lo = mid;
                else hi = mid;
            }
            *start = t_a;
            *end = lo;
        }
        return 0;
    }

    int tw_safe(int depth_cm, int height_cm, int draft_cm, int margin_pct) {
        int64_t need, keel;
        if (draft_cm <= 0 || margin_pct < 0) return 0;
        need = ((int64_t)draft_cm * margin_pct + 99) / 100;
        keel = (int64_t)depth_cm + height_cm - draft_cm;
        return keel >= need;
    }

    int tw_fmt_hhmm(int minutes, char *buf, size_t cap) {
        int m = minutes % 1440;
        if (m < 0) m += 1440;
        if (cap < 6) return -1;
        snprintf(buf, cap, "%02d:%02d", m / 60, m % 60);
        return 5;
    }

    int tw_parse_hhmm(const char *s, size_t n, int *minutes) {
        int h, m;
        if (n != 5 || s[2] != ':') return -1;
        if (s[0] < '0' || s[0] > '9' || s[1] < '0' || s[1] > '9' || s[3] < '0' || s[3] > '9' || s[4] < '0' || s[4] > '9') return -1;
        h = (s[0] - '0') * 10 + (s[1] - '0');
        m = (s[3] - '0') * 10 + (s[4] - '0');
        if (h > 23 || m > 59) return -1;
        *minutes = h * 60 + m;
        return 0;
    }
''')

V4 = dd(r'''
    #include "harness.h"
    #include "twelfths.h"

    int main(void) {
        int start = 0, end = 0;
        h_init();

        /* low water at minute 0 (height 100), high water 6 hours later (height 700) */
        CHECK_INT(tw_height(0, 100, 360, 700, 0), 100);
        CHECK_INT(tw_height(0, 100, 360, 700, 60), 150);
        CHECK_INT(tw_height(0, 100, 360, 700, 360), 700);
        CHECK_INT(tw_window(0, 100, 360, 700, 400, &start, &end), 0);
        CHECK_INT(end, 360);
        return h_report();
    }
''')

H5 = dd(r'''
    #include <limits.h>
    #include <stdio.h>
    #include <stdlib.h>
    #include <string.h>

    #include "harness.h"
    #include "twelfths.h"

    typedef struct { int ta, ha, tb, hb, t, height, phase; } height_case;
    typedef struct { int ta, ha, tb, hb, t; } err_case;
    typedef struct { int ta, ha, tb, hb, min_h, rc, start, end; } window_case;
    typedef struct { int minutes; const char *text; } fmt_case;

    static const height_case HEIGHTS[] = {
        {0, 100, 360, 700, 0, 100, 0},
        {0, 100, 360, 700, 1, 101, 0},
        {0, 100, 360, 700, 60, 150, 1},
        {0, 100, 360, 700, 61, 152, 1},
        {0, 100, 360, 700, 94, 207, 1},
        {0, 100, 360, 700, 97, 212, 1},
        {0, 100, 360, 700, 120, 250, 2},
        {0, 100, 360, 700, 121, 253, 2},
        {0, 100, 360, 700, 180, 400, 3},
        {0, 100, 360, 700, 181, 403, 3},
        {0, 100, 360, 700, 231, 528, 3},
        {0, 100, 360, 700, 238, 545, 3},
        {0, 100, 360, 700, 240, 550, 4},
        {0, 100, 360, 700, 241, 552, 4},
        {0, 100, 360, 700, 260, 583, 4},
        {0, 100, 360, 700, 286, 627, 4},
        {0, 100, 360, 700, 300, 650, 5},
        {0, 100, 360, 700, 301, 651, 5},
        {0, 100, 360, 700, 359, 699, 5},
        {0, 100, 360, 700, 360, 700, 5},
        {0, 700, 360, 100, 0, 700, 0},
        {0, 700, 360, 100, 1, 699, 0},
        {0, 700, 360, 100, 48, 660, 0},
        {0, 700, 360, 100, 60, 650, 1},
        {0, 700, 360, 100, 61, 648, 1},
        {0, 700, 360, 100, 95, 592, 1},
        {0, 700, 360, 100, 120, 550, 2},
        {0, 700, 360, 100, 121, 547, 2},
        {0, 700, 360, 100, 155, 462, 2},
        {0, 700, 360, 100, 180, 400, 3},
        {0, 700, 360, 100, 181, 397, 3},
        {0, 700, 360, 100, 228, 280, 3},
        {0, 700, 360, 100, 240, 250, 4},
        {0, 700, 360, 100, 241, 248, 4},
        {0, 700, 360, 100, 243, 245, 4},
        {0, 700, 360, 100, 262, 213, 4},
        {0, 700, 360, 100, 300, 150, 5},
        {0, 700, 360, 100, 301, 149, 5},
        {0, 700, 360, 100, 314, 138, 5},
        {0, 700, 360, 100, 322, 132, 5},
        {0, 700, 360, 100, 359, 101, 5},
        {0, 700, 360, 100, 360, 100, 5},
        {100, 50, 472, 610, 100, 50, 0},
        {100, 50, 472, 610, 101, 51, 0},
        {100, 50, 472, 610, 121, 66, 0},
        {100, 50, 472, 610, 146, 85, 0},
        {100, 50, 472, 610, 162, 97, 1},
        {100, 50, 472, 610, 163, 98, 1},
        {100, 50, 472, 610, 172, 112, 1},
        {100, 50, 472, 610, 224, 190, 2},
        {100, 50, 472, 610, 225, 192, 2},
        {100, 50, 472, 610, 286, 330, 3},
        {100, 50, 472, 610, 287, 332, 3},
        {100, 50, 472, 610, 302, 366, 3},
        {100, 50, 472, 610, 348, 470, 4},
        {100, 50, 472, 610, 349, 472, 4},
        {100, 50, 472, 610, 375, 511, 4},
        {100, 50, 472, 610, 404, 554, 4},
        {100, 50, 472, 610, 410, 563, 5},
        {100, 50, 472, 610, 411, 564, 5},
        {100, 50, 472, 610, 424, 574, 5},
        {100, 50, 472, 610, 455, 597, 5},
        {100, 50, 472, 610, 471, 609, 5},
        {100, 50, 472, 610, 472, 610, 5},
        {1000, 320, 1372, -40, 1000, 320, 0},
        {1000, 320, 1372, -40, 1001, 320, 0},
        {1000, 320, 1372, -40, 1007, 317, 0},
        {1000, 320, 1372, -40, 1062, 290, 1},
        {1000, 320, 1372, -40, 1063, 289, 1},
        {1000, 320, 1372, -40, 1080, 273, 1},
        {1000, 320, 1372, -40, 1124, 230, 2},
        {1000, 320, 1372, -40, 1125, 229, 2},
        {1000, 320, 1372, -40, 1186, 140, 3},
        {1000, 320, 1372, -40, 1187, 139, 3},
        {1000, 320, 1372, -40, 1231, 75, 3},
        {1000, 320, 1372, -40, 1248, 50, 4},
        {1000, 320, 1372, -40, 1249, 49, 4},
        {1000, 320, 1372, -40, 1270, 29, 4},
        {1000, 320, 1372, -40, 1310, -10, 5},
        {1000, 320, 1372, -40, 1311, -10, 5},
        {1000, 320, 1372, -40, 1315, -12, 5},
        {1000, 320, 1372, -40, 1319, -14, 5},
        {1000, 320, 1372, -40, 1332, -21, 5},
        {1000, 320, 1372, -40, 1334, -22, 5},
        {1000, 320, 1372, -40, 1371, -40, 5},
        {1000, 320, 1372, -40, 1372, -40, 5},
        {-200, -80, 170, 520, -200, -80, 0},
        {-200, -80, 170, 520, -199, -79, 0},
        {-200, -80, 170, 520, -185, -68, 0},
        {-200, -80, 170, 520, -182, -65, 0},
        {-200, -80, 170, 520, -170, -56, 0},
        {-200, -80, 170, 520, -168, -54, 0},
        {-200, -80, 170, 520, -139, -31, 0},
        {-200, -80, 170, 520, -138, -29, 1},
        {-200, -80, 170, 520, -103, 27, 1},
        {-200, -80, 170, 520, -77, 69, 1},
        {-200, -80, 170, 520, -76, 72, 2},
        {-200, -80, 170, 520, -15, 220, 3},
        {-200, -80, 170, 520, -14, 222, 3},
        {-200, -80, 170, 520, 37, 346, 3},
        {-200, -80, 170, 520, 46, 368, 3},
        {-200, -80, 170, 520, 47, 371, 4},
        {-200, -80, 170, 520, 107, 468, 4},
        {-200, -80, 170, 520, 108, 469, 4},
        {-200, -80, 170, 520, 109, 471, 5},
        {-200, -80, 170, 520, 169, 519, 5},
        {-200, -80, 170, 520, 170, 520, 5},
        {0, 0, 6, 12, 0, 0, 0},
        {0, 0, 6, 12, 1, 1, 1},
        {0, 0, 6, 12, 2, 3, 2},
        {0, 0, 6, 12, 3, 6, 3},
        {0, 0, 6, 12, 4, 9, 4},
        {0, 0, 6, 12, 5, 11, 5},
        {0, 0, 6, 12, 6, 12, 5},
        {0, 0, 6, 13, 0, 0, 0},
        {0, 0, 6, 13, 1, 1, 1},
        {0, 0, 6, 13, 2, 3, 2},
        {0, 0, 6, 13, 3, 7, 3},
        {0, 0, 6, 13, 4, 10, 4},
        {0, 0, 6, 13, 5, 12, 5},
        {0, 0, 6, 13, 6, 13, 5},
        {0, 0, 12, 5, 0, 0, 0},
        {0, 0, 12, 5, 1, 0, 0},
        {0, 0, 12, 5, 2, 0, 1},
        {0, 0, 12, 5, 3, 1, 1},
        {0, 0, 12, 5, 4, 1, 2},
        {0, 0, 12, 5, 5, 2, 2},
        {0, 0, 12, 5, 6, 3, 3},
        {0, 0, 12, 5, 7, 3, 3},
        {0, 0, 12, 5, 8, 4, 4},
        {0, 0, 12, 5, 9, 4, 4},
        {0, 0, 12, 5, 10, 5, 5},
        {0, 0, 12, 5, 11, 5, 5},
        {0, 0, 12, 5, 12, 5, 5},
        {0, 500, 7, -3, 0, 500, 0},
        {0, 500, 7, -3, 1, 464, 0},
        {0, 500, 7, -3, 2, 398, 1},
        {0, 500, 7, -3, 3, 302, 2},
        {0, 500, 7, -3, 4, 195, 3},
        {0, 500, 7, -3, 5, 99, 4},
        {0, 500, 7, -3, 6, 33, 5},
        {0, 500, 7, -3, 7, -3, 5},
        {30, 200, 31, 260, 30, 200, 0},
        {30, 200, 31, 260, 31, 260, 5},
        {0, 300, 1, 100, 0, 300, 0},
        {0, 300, 1, 100, 1, 100, 5},
        {5, 100, 6, 101, 5, 100, 0},
        {5, 100, 6, 101, 6, 101, 5},
        {0, 100, 360, 100, 0, 100, 0},
        {0, 100, 360, 100, 1, 100, 0},
        {0, 100, 360, 100, 30, 100, 0},
        {0, 100, 360, 100, 60, 100, 1},
        {0, 100, 360, 100, 61, 100, 1},
        {0, 100, 360, 100, 90, 100, 1},
        {0, 100, 360, 100, 96, 100, 1},
        {0, 100, 360, 100, 120, 100, 2},
        {0, 100, 360, 100, 121, 100, 2},
        {0, 100, 360, 100, 180, 100, 3},
        {0, 100, 360, 100, 181, 100, 3},
        {0, 100, 360, 100, 229, 100, 3},
        {0, 100, 360, 100, 238, 100, 3},
        {0, 100, 360, 100, 240, 100, 4},
        {0, 100, 360, 100, 241, 100, 4},
        {0, 100, 360, 100, 249, 100, 4},
        {0, 100, 360, 100, 286, 100, 4},
        {0, 100, 360, 100, 300, 100, 5},
        {0, 100, 360, 100, 301, 100, 5},
        {0, 100, 360, 100, 349, 100, 5},
        {0, 100, 360, 100, 359, 100, 5},
        {0, 100, 360, 100, 360, 100, 5},
        {600, 420, 1000, 420, 600, 420, 0},
        {600, 420, 1000, 420, 601, 420, 0},
        {600, 420, 1000, 420, 666, 420, 0},
        {600, 420, 1000, 420, 667, 420, 1},
        {600, 420, 1000, 420, 697, 420, 1},
        {600, 420, 1000, 420, 733, 420, 1},
        {600, 420, 1000, 420, 734, 420, 2},
        {600, 420, 1000, 420, 796, 420, 2},
        {600, 420, 1000, 420, 800, 420, 3},
        {600, 420, 1000, 420, 801, 420, 3},
        {600, 420, 1000, 420, 814, 420, 3},
        {600, 420, 1000, 420, 860, 420, 3},
        {600, 420, 1000, 420, 866, 420, 3},
        {600, 420, 1000, 420, 867, 420, 4},
        {600, 420, 1000, 420, 929, 420, 4},
        {600, 420, 1000, 420, 933, 420, 4},
        {600, 420, 1000, 420, 934, 420, 5},
        {600, 420, 1000, 420, 974, 420, 5},
        {600, 420, 1000, 420, 993, 420, 5},
        {600, 420, 1000, 420, 999, 420, 5},
        {600, 420, 1000, 420, 1000, 420, 5},
        {0, 0, 1000, 1000, 0, 0, 0},
        {0, 0, 1000, 1000, 1, 1, 0},
        {0, 0, 1000, 1000, 119, 60, 0},
        {0, 0, 1000, 1000, 166, 83, 0},
        {0, 0, 1000, 1000, 167, 84, 1},
        {0, 0, 1000, 1000, 217, 134, 1},
        {0, 0, 1000, 1000, 276, 193, 1},
        {0, 0, 1000, 1000, 333, 250, 1},
        {0, 0, 1000, 1000, 334, 251, 2},
        {0, 0, 1000, 1000, 404, 356, 2},
        {0, 0, 1000, 1000, 430, 395, 2},
        {0, 0, 1000, 1000, 500, 500, 3},
        {0, 0, 1000, 1000, 501, 502, 3},
        {0, 0, 1000, 1000, 666, 749, 3},
        {0, 0, 1000, 1000, 667, 750, 4},
        {0, 0, 1000, 1000, 833, 916, 4},
        {0, 0, 1000, 1000, 834, 917, 5},
        {0, 0, 1000, 1000, 885, 943, 5},
        {0, 0, 1000, 1000, 994, 997, 5},
        {0, 0, 1000, 1000, 999, 1000, 5},
        {0, 0, 1000, 1000, 1000, 1000, 5},
        {0, 10, 7, 3, 0, 10, 0},
        {0, 10, 7, 3, 1, 9, 0},
        {0, 10, 7, 3, 2, 9, 1},
        {0, 10, 7, 3, 3, 7, 2},
        {0, 10, 7, 3, 4, 6, 3},
        {0, 10, 7, 3, 5, 4, 4},
        {0, 10, 7, 3, 6, 3, 5},
        {0, 10, 7, 3, 7, 3, 5},
    };

    static const err_case ERRS[] = {
        {10, 0, 10, 5, 10},
        {10, 0, 5, 5, 7},
        {10, 0, 20, 5, 9},
        {10, 0, 20, 5, 21},
        {0, 0, 100, 5, -1},
    };

    static const window_case WINDOWS[] = {
        {0, 100, 360, 700, 99, 0, 0, 360},
        {0, 100, 360, 700, 100, 0, 0, 360},
        {0, 100, 360, 700, 101, 0, 1, 360},
        {0, 100, 360, 700, 250, 0, 120, 360},
        {0, 100, 360, 700, 400, 0, 180, 360},
        {0, 100, 360, 700, 550, 0, 240, 360},
        {0, 100, 360, 700, 699, 0, 359, 360},
        {0, 100, 360, 700, 700, 0, 360, 360},
        {0, 100, 360, 700, 701, -1, 0, 0},
        {0, 700, 360, 100, 99, 0, 0, 360},
        {0, 700, 360, 100, 100, 0, 0, 360},
        {0, 700, 360, 100, 101, 0, 0, 359},
        {0, 700, 360, 100, 250, 0, 0, 240},
        {0, 700, 360, 100, 400, 0, 0, 180},
        {0, 700, 360, 100, 550, 0, 0, 120},
        {0, 700, 360, 100, 699, 0, 0, 1},
        {0, 700, 360, 100, 700, 0, 0, 0},
        {0, 700, 360, 100, 701, -1, 0, 0},
        {100, 50, 472, 610, 49, 0, 100, 472},
        {100, 50, 472, 610, 50, 0, 100, 472},
        {100, 50, 472, 610, 51, 0, 101, 472},
        {100, 50, 472, 610, 190, 0, 224, 472},
        {100, 50, 472, 610, 330, 0, 286, 472},
        {100, 50, 472, 610, 470, 0, 348, 472},
        {100, 50, 472, 610, 609, 0, 471, 472},
        {100, 50, 472, 610, 610, 0, 472, 472},
        {100, 50, 472, 610, 611, -1, 0, 0},
        {1000, 320, 1372, -40, -41, 0, 1000, 1372},
        {1000, 320, 1372, -40, -40, 0, 1000, 1372},
        {1000, 320, 1372, -40, -39, 0, 1000, 1370},
        {1000, 320, 1372, -40, 50, 0, 1000, 1248},
        {1000, 320, 1372, -40, 140, 0, 1000, 1186},
        {1000, 320, 1372, -40, 230, 0, 1000, 1124},
        {1000, 320, 1372, -40, 319, 0, 1000, 1003},
        {1000, 320, 1372, -40, 320, 0, 1000, 1001},
        {1000, 320, 1372, -40, 321, -1, 0, 0},
        {-200, -80, 170, 520, -81, 0, -200, 170},
        {-200, -80, 170, 520, -80, 0, -200, 170},
        {-200, -80, 170, 520, -79, 0, -199, 170},
        {-200, -80, 170, 520, 70, 0, -76, 170},
        {-200, -80, 170, 520, 220, 0, -15, 170},
        {-200, -80, 170, 520, 370, 0, 47, 170},
        {-200, -80, 170, 520, 519, 0, 169, 170},
        {-200, -80, 170, 520, 520, 0, 170, 170},
        {-200, -80, 170, 520, 521, -1, 0, 0},
        {0, 0, 6, 12, -1, 0, 0, 6},
        {0, 0, 6, 12, 0, 0, 0, 6},
        {0, 0, 6, 12, 1, 0, 1, 6},
        {0, 0, 6, 12, 3, 0, 2, 6},
        {0, 0, 6, 12, 6, 0, 3, 6},
        {0, 0, 6, 12, 9, 0, 4, 6},
        {0, 0, 6, 12, 11, 0, 5, 6},
        {0, 0, 6, 12, 12, 0, 6, 6},
        {0, 0, 6, 12, 13, -1, 0, 0},
        {0, 0, 6, 13, -1, 0, 0, 6},
        {0, 0, 6, 13, 0, 0, 0, 6},
        {0, 0, 6, 13, 1, 0, 1, 6},
        {0, 0, 6, 13, 3, 0, 2, 6},
        {0, 0, 6, 13, 6, 0, 3, 6},
        {0, 0, 6, 13, 9, 0, 4, 6},
        {0, 0, 6, 13, 12, 0, 5, 6},
        {0, 0, 6, 13, 13, 0, 6, 6},
        {0, 0, 6, 13, 14, -1, 0, 0},
        {0, 0, 12, 5, -1, 0, 0, 12},
        {0, 0, 12, 5, 0, 0, 0, 12},
        {0, 0, 12, 5, 1, 0, 3, 12},
        {0, 0, 12, 5, 2, 0, 5, 12},
        {0, 0, 12, 5, 3, 0, 6, 12},
        {0, 0, 12, 5, 4, 0, 8, 12},
        {0, 0, 12, 5, 5, 0, 10, 12},
        {0, 0, 12, 5, 6, -1, 0, 0},
        {0, 500, 7, -3, -4, 0, 0, 7},
        {0, 500, 7, -3, -3, 0, 0, 7},
        {0, 500, 7, -3, -2, 0, 0, 6},
        {0, 500, 7, -3, 122, 0, 0, 4},
        {0, 500, 7, -3, 248, 0, 0, 3},
        {0, 500, 7, -3, 374, 0, 0, 2},
        {0, 500, 7, -3, 499, 0, 0, 0},
        {0, 500, 7, -3, 500, 0, 0, 0},
        {0, 500, 7, -3, 501, -1, 0, 0},
        {30, 200, 31, 260, 199, 0, 30, 31},
        {30, 200, 31, 260, 200, 0, 30, 31},
        {30, 200, 31, 260, 201, 0, 31, 31},
        {30, 200, 31, 260, 215, 0, 31, 31},
        {30, 200, 31, 260, 230, 0, 31, 31},
        {30, 200, 31, 260, 245, 0, 31, 31},
        {30, 200, 31, 260, 259, 0, 31, 31},
        {30, 200, 31, 260, 260, 0, 31, 31},
        {30, 200, 31, 260, 261, -1, 0, 0},
        {0, 300, 1, 100, 99, 0, 0, 1},
        {0, 300, 1, 100, 100, 0, 0, 1},
        {0, 300, 1, 100, 101, 0, 0, 0},
        {0, 300, 1, 100, 150, 0, 0, 0},
        {0, 300, 1, 100, 200, 0, 0, 0},
        {0, 300, 1, 100, 250, 0, 0, 0},
        {0, 300, 1, 100, 299, 0, 0, 0},
        {0, 300, 1, 100, 300, 0, 0, 0},
        {0, 300, 1, 100, 301, -1, 0, 0},
        {5, 100, 6, 101, 99, 0, 5, 6},
        {5, 100, 6, 101, 100, 0, 5, 6},
        {5, 100, 6, 101, 101, 0, 6, 6},
        {5, 100, 6, 101, 102, -1, 0, 0},
        {0, 100, 360, 100, 99, 0, 0, 360},
        {0, 100, 360, 100, 100, 0, 0, 360},
        {0, 100, 360, 100, 101, -1, 0, 0},
        {600, 420, 1000, 420, 419, 0, 600, 1000},
        {600, 420, 1000, 420, 420, 0, 600, 1000},
        {600, 420, 1000, 420, 421, -1, 0, 0},
        {0, 0, 1000, 1000, -1, 0, 0, 1000},
        {0, 0, 1000, 1000, 0, 0, 0, 1000},
        {0, 0, 1000, 1000, 1, 0, 1, 1000},
        {0, 0, 1000, 1000, 250, 0, 333, 1000},
        {0, 0, 1000, 1000, 500, 0, 500, 1000},
        {0, 0, 1000, 1000, 750, 0, 667, 1000},
        {0, 0, 1000, 1000, 999, 0, 997, 1000},
        {0, 0, 1000, 1000, 1000, 0, 999, 1000},
        {0, 0, 1000, 1000, 1001, -1, 0, 0},
        {0, 10, 7, 3, 2, 0, 0, 7},
        {0, 10, 7, 3, 3, 0, 0, 7},
        {0, 10, 7, 3, 4, 0, 0, 5},
        {0, 10, 7, 3, 6, 0, 0, 4},
        {0, 10, 7, 3, 8, 0, 0, 2},
        {0, 10, 7, 3, 9, 0, 0, 2},
        {0, 10, 7, 3, 10, 0, 0, 0},
        {0, 10, 7, 3, 11, -1, 0, 0},
        {0, 0, 360, 600, -1, 0, 0, 360},
        {0, 0, 360, 600, 0, 0, 0, 360},
        {0, 0, 360, 600, 1, 0, 1, 360},
        {0, 0, 360, 600, 150, 0, 120, 360},
        {0, 0, 360, 600, 300, 0, 180, 360},
        {0, 0, 360, 600, 450, 0, 240, 360},
        {0, 0, 360, 600, 599, 0, 359, 360},
        {0, 0, 360, 600, 600, 0, 360, 360},
        {0, 0, 360, 600, 601, -1, 0, 0},
        {0, 600, 360, 0, -1, 0, 0, 360},
        {0, 600, 360, 0, 0, 0, 0, 360},
        {0, 600, 360, 0, 1, 0, 0, 359},
        {0, 600, 360, 0, 150, 0, 0, 240},
        {0, 600, 360, 0, 300, 0, 0, 180},
        {0, 600, 360, 0, 450, 0, 0, 120},
        {0, 600, 360, 0, 599, 0, 0, 1},
        {0, 600, 360, 0, 600, 0, 0, 0},
        {0, 600, 360, 0, 601, -1, 0, 0},
        {100, -50, 400, 400, -51, 0, 100, 400},
        {100, -50, 400, 400, -50, 0, 100, 400},
        {100, -50, 400, 400, -49, 0, 101, 400},
        {100, -50, 400, 400, 62, 0, 200, 400},
        {100, -50, 400, 400, 175, 0, 250, 400},
        {100, -50, 400, 400, 287, 0, 300, 400},
        {100, -50, 400, 400, 399, 0, 398, 400},
        {100, -50, 400, 400, 400, 0, 400, 400},
        {100, -50, 400, 400, 401, -1, 0, 0},
        {50, 100, 50, 900, 0, -1, 0, 0},
        {50, 100, 40, 900, 0, -1, 0, 0},
    };

    static const fmt_case FMTS[] = {
        {0, "00:00"},
        {1, "00:01"},
        {59, "00:59"},
        {60, "01:00"},
        {61, "01:01"},
        {599, "09:59"},
        {600, "10:00"},
        {719, "11:59"},
        {720, "12:00"},
        {1380, "23:00"},
        {1439, "23:59"},
        {1440, "00:00"},
        {1441, "00:01"},
        {2879, "23:59"},
        {2880, "00:00"},
        {-1, "23:59"},
        {-30, "23:30"},
        {-60, "23:00"},
        {-1440, "00:00"},
        {-1441, "23:59"},
        {-1500, "23:00"},
        {100000, "10:40"},
        {-100000, "13:20"},
        {1234, "20:34"},
    };

    static void test_heights(void) {
        size_t i;
        char ctx[80];
        for (i = 0; i < sizeof HEIGHTS / sizeof HEIGHTS[0]; i++) {
            const height_case *c = &HEIGHTS[i];
            snprintf(ctx, sizeof ctx, "(%d,%d)-(%d,%d) at t=%d", c->ta, c->ha, c->tb, c->hb, c->t);
            CHECK_INT_CTX(ctx, tw_height(c->ta, c->ha, c->tb, c->hb, c->t), c->height);
            CHECK_INT_CTX(ctx, tw_phase(c->ta, c->tb, c->t), c->phase);
        }
        for (i = 0; i < sizeof ERRS / sizeof ERRS[0]; i++) {
            const err_case *c = &ERRS[i];
            snprintf(ctx, sizeof ctx, "(%d,%d)-(%d,%d) at t=%d", c->ta, c->ha, c->tb, c->hb, c->t);
            CHECK_INT_CTX(ctx, tw_height(c->ta, c->ha, c->tb, c->hb, c->t), TW_ERR);
            CHECK_INT_CTX(ctx, tw_phase(c->ta, c->tb, c->t), -1);
        }
    }

    static void test_big_values(void) {
        /* 64-bit intermediates: a long interval and a large range */
        CHECK_INT(tw_height(0, 0, 1000000, 1000000, 500000), 500000);
        CHECK_INT(tw_height(0, 0, 1000000, 1000000, 166667), 83334);
        CHECK_INT(tw_height(0, -1000000, 1000000, 1000000, 1000000), 1000000);
        CHECK_INT(tw_height(0, 1000000000, 2000000, -1000000000, 1000000), 0);
        CHECK_INT(tw_height(0, 2000000000, 3000000, 0, 3000000), 0);
        CHECK_INT(tw_height(-2000000000, 0, 2000000000, 100, 0), 50);
        CHECK_INT(tw_height(-2000000000, 0, 2000000000, 100, -2000000000), 0);
        CHECK_INT(tw_height(-2000000000, 0, 2000000000, 100, 2000000000), 100);
        CHECK_INT(tw_phase(-2000000000, 2000000000, 2000000000), 5);
        CHECK_INT(tw_phase(-2000000000, 2000000000, -1999999999), 0);
        CHECK_INT(tw_phase(INT_MIN, INT_MAX, 0), 3);
        CHECK_INT(tw_height(INT_MIN, 0, INT_MAX, 12, INT_MAX), 12);
    }

    static void test_windows(void) {
        size_t i;
        char ctx[96];
        for (i = 0; i < sizeof WINDOWS / sizeof WINDOWS[0]; i++) {
            const window_case *c = &WINDOWS[i];
            int start = -777, end = -888, rc;
            snprintf(ctx, sizeof ctx, "(%d,%d)-(%d,%d) min %d", c->ta, c->ha, c->tb, c->hb, c->min_h);
            rc = tw_window(c->ta, c->ha, c->tb, c->hb, c->min_h, &start, &end);
            CHECK_INT_CTX(ctx, rc, c->rc);
            if (c->rc == 0) {
                CHECK_INT_CTX(ctx, start, c->start);
                CHECK_INT_CTX(ctx, end, c->end);
            } else {
                CHECK_INT_CTX(ctx, start, -777);
                CHECK_INT_CTX(ctx, end, -888);
            }
        }
    }

    static void test_safe(void) {
        /* clearance = depth + height - draft, needed: ceil(draft * pct / 100) */
        CHECK_INT(tw_safe(300, 100, 300, 10), 1);   /* 100 >= 30 */
        CHECK_INT(tw_safe(300, 0, 300, 10), 0);     /* 0 < 30 */
        CHECK_INT(tw_safe(300, 30, 300, 10), 1);    /* 30 >= 30 */
        CHECK_INT(tw_safe(300, 29, 300, 10), 0);
        CHECK_INT(tw_safe(300, 31, 301, 10), 0);    /* clearance 30, need ceil(30.1) = 31 */
        CHECK_INT(tw_safe(300, 32, 301, 10), 1);    /* clearance 31 */
        CHECK_INT(tw_safe(300, 30, 299, 10), 1);    /* clearance 31, need ceil(29.9) = 30 */
        CHECK_INT(tw_safe(200, 5, 200, 0), 1);      /* no margin, clearance 5 */
        CHECK_INT(tw_safe(200, 0, 200, 0), 1);      /* clearance 0 >= 0 */
        CHECK_INT(tw_safe(200, -1, 200, 0), 0);
        CHECK_INT(tw_safe(250, 0, 200, 25), 1);     /* 50 >= 50 */
        CHECK_INT(tw_safe(249, 0, 200, 25), 0);
        CHECK_INT(tw_safe(250, 0, 0, 25), 0);       /* draft must be positive */
        CHECK_INT(tw_safe(250, 0, -10, 0), 0);
        CHECK_INT(tw_safe(1000, 500, 200, -1), 0);  /* negative margin */
        CHECK_INT(tw_safe(1000, 500, 200, 100), 1);
        CHECK_INT(tw_safe(100, -50, 40, 10), 1);    /* clearance 10 >= 4 */
        CHECK_INT(tw_safe(100, -61, 40, 10), 0);    /* clearance -1 */
        CHECK_INT(tw_safe(2000000000, 2000000000, 1000000000, 100), 1);
        CHECK_INT(tw_safe(INT_MIN, INT_MIN, 100, 10), 0);
        CHECK_INT(tw_safe(INT_MAX, INT_MAX, 2000000000, 200), 0);
        CHECK_INT(tw_safe(INT_MAX, INT_MAX, 2000000000, 100), 1);
        CHECK_INT(tw_safe(INT_MAX, INT_MAX, 2000000000, 114), 1);
        CHECK_INT(tw_safe(INT_MAX, INT_MAX, 2000000000, 115), 0);
        CHECK_INT(tw_safe(1, 1, INT_MAX, 10000), 0);
        /* the needed clearance is rounded up even by a hair: 301 * 1 / 100 = 3.01 -> 4 */
        CHECK_INT(tw_safe(300, 4, 301, 1), 0);   /* clearance 3 */
        CHECK_INT(tw_safe(300, 5, 301, 1), 1);   /* clearance 4 */
        CHECK_INT(tw_safe(100, 0, 101, 1), 0);   /* clearance -1 */
        CHECK_INT(tw_safe(102, 0, 101, 1), 0);   /* clearance 1, need ceil(1.01) = 2 */
        CHECK_INT(tw_safe(103, 0, 101, 1), 1);   /* clearance 2 */
        CHECK_INT(tw_safe(250, 0, 200, 50), 0);  /* need 100, clearance 50 */
        CHECK_INT(tw_safe(300, 0, 200, 50), 1);  /* need 100, clearance 100 */
    }

    static void test_fmt(void) {
        size_t i;
        char buf[16], ctx[24];
        for (i = 0; i < sizeof FMTS / sizeof FMTS[0]; i++) {
            snprintf(ctx, sizeof ctx, "minutes=%d", FMTS[i].minutes);
            memset(buf, '?', sizeof buf);
            CHECK_INT_CTX(ctx, tw_fmt_hhmm(FMTS[i].minutes, buf, sizeof buf), 5);
            CHECK_STR_CTX(ctx, buf, FMTS[i].text);
        }
        {
            char *exact = malloc(6);
            CHECK_INT(tw_fmt_hhmm(754, exact, 6), 5);
            CHECK_STR(exact, "12:34");
            free(exact);
            exact = malloc(5);
            memset(exact, '?', 5);
            CHECK_INT(tw_fmt_hhmm(754, exact, 5), -1);
            CHECK_INT(exact[0], '?');
            CHECK_INT(tw_fmt_hhmm(754, exact, 0), -1);
            free(exact);
        }
    }

    static void test_parse(void) {
        static const struct { const char *s; int minutes; } good[] = {
            {"00:00", 0}, {"00:01", 1}, {"00:59", 59}, {"01:00", 60}, {"09:09", 549}, {"10:10", 610}, {"12:34", 754},
            {"19:59", 1199}, {"20:00", 1200}, {"23:00", 1380}, {"23:59", 1439},
        };
        static const char *bad[] = {
            "", "0", "00:0", "0:00", "000:00", "00:000", "24:00", "24:59", "99:00", "00:60", "00:99", "23:60", "1:30 ", " 1:30",
            "12-34", "12.34", "12 34", "1234:", "ab:cd", "1a:00", "00:0a", "-1:00", "00:-1", "12:3x", "x2:30", "12;30", "::::: ",
            "12:34:", "\xc3\xa9\xc3\xa9:00", "/2:30", "1/:30", "12:/5", "12:3/", "12:3:", "/1:00", "0/:00", ":1:00", "1:::0", "12:5:", "12:/0", "00:0/", "00:0:",
        };
        size_t i;
        for (i = 0; i < sizeof good / sizeof good[0]; i++) {
            int v = -5;
            size_t n = strlen(good[i].s);
            char *p = malloc(n);
            memcpy(p, good[i].s, n);
            CHECK_INT_CTX(good[i].s, tw_parse_hhmm(p, n, &v), 0);
            CHECK_INT_CTX(good[i].s, v, good[i].minutes);
            free(p);
        }
        for (i = 0; i < sizeof bad / sizeof bad[0]; i++) {
            int v = -5;
            size_t n = strlen(bad[i]);
            char *p = malloc(n ? n : 1);
            memcpy(p, bad[i], n);
            CHECK_INT_CTX(bad[i], tw_parse_hhmm(p, n, &v), -1);
            CHECK_INT_CTX(bad[i], v, -5);
            free(p);
        }
        {
            int v = -5;
            CHECK_INT(tw_parse_hhmm("12:34 and more", 5, &v), 0);
            CHECK_INT(v, 754);
            CHECK_INT(tw_parse_hhmm("12:34", 4, &v), -1);
            CHECK_INT(tw_parse_hhmm("12:345", 6, &v), -1);
        }
        /* round trip */
        for (i = 0; i < 1440; i += 7) {
            char buf[8];
            int v = -1;
            tw_fmt_hhmm((int)i, buf, sizeof buf);
            CHECK_INT(tw_parse_hhmm(buf, 5, &v), 0);
            CHECK_INT(v, (int)i);
        }
    }

    int main(void) {
        h_init();
        test_heights();
        test_big_values();
        test_windows();
        test_safe();
        test_fmt();
        test_parse();
        return h_report();
    }
''')

LIB = Lib(
    name="twelfths", lang="c", title="the tide table calculator",
    blurb="The harbour office's tide table calculator estimates the water height between published high and low waters with the navigator's rule of twelfths.",
    files={"README.md": README1, "include/twelfths.h": F2, "src/twelfths.c": F3},
    visible_tests={"tests/test_main.c": V4, "tests/harness.h": _lang3.C_HARNESS},
    hidden_tests={"tests/test_main.c": H5},
    mutate=["src/twelfths.c"], difficulty=2, tags=["tides", "interpolation", "time"],
    verify=_lang3.C_VERIFY,
)

_lang3.add(LIB, n=8)
