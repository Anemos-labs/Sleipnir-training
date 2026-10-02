"""Kart lap-time board helpers (c): lap time text with minutes or hours, strict parsing with partial fractions, fastest lap and trimmed averages; bugs injected into the library."""
from fx import Lib, dd

from generators.fix import _lang3

README1 = dd(r'''
    # lapclock

    Helpers for a kart track's timing board. Times are `long` **milliseconds**.

    ## `int lc_format(long ms, char *buf, size_t cap)`

    Writes the time as text and a NUL; returns the text length, or -1 (writing nothing) when it and its NUL do not fit in `cap` bytes.

    * below one hour: `M:SS.mmm` (minutes without leading zeros, seconds and milliseconds with them): `83456` is `1:23.456`, `5` is `0:00.005`;
    * from one hour on: `H:MM:SS.mmm` (`3723004` is `1:02:03.004`);
    * a negative time has a `-` in front of the same text for its absolute value (`-1500` is `-0:01.500`). `ms` is within `+-2000000000`.

    ## `int lc_parse(const char *s, size_t n, long *out)`

    Reads the first `n` characters of `s` (not necessarily NUL-terminated). Returns 0 and sets `*out`, or -1 and leaves `*out` alone.

    Accepted: an optional `-`, then `M:SS` or `H:MM:SS`, then optionally a `.` and **one to three** digits of fraction (`.4` is 400 ms, `.45` 450 ms, `.456` 456 ms). Rules: all fields are digits only; `SS` is exactly two digits and below 60; in the
    three-field form `MM` is exactly two digits and below 60 and `H` has one to three digits; in the two-field form `M` has one to four digits. Nothing else is allowed (no spaces, no `+`, no trailing text, no `1:2`, no `1:23.`, no `1:23.4567`).
    `-0:00.000` is accepted and gives 0. The value must fit in `+-2000000000` ms.

    ## `int lc_best(const long *laps, size_t n)`

    The index of the fastest lap. Only laps greater than 0 count (0 or negative entries mark laps without a time, such as the in-lap). Ties go to the earliest lap. Returns -1 when no lap counts. Only the first 256 counted laps are taken into account.

    ## `long lc_average(const long *laps, size_t n, size_t drop_slowest)`

    The mean of the counted laps (greater than 0) after discarding the `drop_slowest` slowest of them (the discarded laps are simply the slowest ones, whatever their order). At least one lap is always kept: when `drop_slowest` is as large as the number of counted laps or larger,
    only the fastest one remains. The mean is rounded to the nearest millisecond, halves up (integer arithmetic). Returns -1 when no lap counts. Only the first 256 counted laps are taken into account.
''')

F2 = dd(r'''
    #ifndef LAPCLOCK_H
    #define LAPCLOCK_H

    #include <stddef.h>

    int lc_format(long ms, char *buf, size_t cap);
    int lc_parse(const char *s, size_t n, long *out);
    int lc_best(const long *laps, size_t n);
    long lc_average(const long *laps, size_t n, size_t drop_slowest);

    #endif
''')

F3 = dd(r'''
    #include "lapclock.h"

    #include <stdio.h>
    #include <string.h>

    int lc_format(long ms, char *buf, size_t cap) {
        long a = ms < 0 ? -ms : ms;
        long frac = a % 1000, total_s = a / 1000;
        long h = total_s / 3600, m = (total_s / 60) % 60, s = total_s % 60;
        char tmp[48];
        int len;
        const char *sign = ms < 0 ? "-" : "";
        if (h > 0) len = snprintf(tmp, sizeof tmp, "%s%ld:%02ld:%02ld.%03ld", sign, h, m, s, frac);
        else len = snprintf(tmp, sizeof tmp, "%s%ld:%02ld.%03ld", sign, m, s, frac);
        if (len < 0 || (size_t)len >= cap) return -1;
        memcpy(buf, tmp, (size_t)len + 1);
        return len;
    }

    static int digits(const char *s, size_t n, size_t *pos, long *v) {
        int count = 0;
        *v = 0;
        while (*pos < n && s[*pos] >= '0' && s[*pos] <= '9') {
            *v = *v * 10 + (s[*pos] - '0');
            (*pos)++;
            if (++count > 9) return -1;
        }
        return count;
    }

    int lc_parse(const char *s, size_t n, long *out) {
        size_t pos = 0;
        int neg = 0, na, nb, nc = 0;
        long a, b, c = 0, frac = 0, total;
        if (pos < n && s[pos] == '-') {
            neg = 1;
            pos++;
        }
        na = digits(s, n, &pos, &a);
        if (na < 1 || pos >= n || s[pos] != ':') return -1;
        pos++;
        nb = digits(s, n, &pos, &b);
        if (nb != 2 || b > 59) return -1;
        if (pos < n && s[pos] == ':') {
            pos++;
            nc = digits(s, n, &pos, &c);
            if (nc != 2 || c > 59 || na > 3) return -1;
            total = a * 3600 + b * 60 + c;
        } else {
            if (na > 4) return -1;
            total = a * 60 + b;
        }
        if (pos < n && s[pos] == '.') {
            long scale = 100;
            int nf = 0;
            pos++;
            while (pos < n && s[pos] >= '0' && s[pos] <= '9') {
                frac += (s[pos] - '0') * scale;
                scale /= 10;
                pos++;
                if (++nf > 3) return -1;
            }
            if (nf < 1) return -1;
        }
        if (pos != n) return -1;
        total = total * 1000 + frac;
        if (total > 2000000000L) return -1;
        *out = neg ? -total : total;
        return 0;
    }

    int lc_best(const long *laps, size_t n) {
        int best = -1;
        size_t i;
        for (i = 0; i < n; i++) {
            if (laps[i] > 0 && (best < 0 || laps[i] < laps[best])) best = (int)i;
        }
        return best;
    }

    long lc_average(const long *laps, size_t n, size_t drop_slowest) {
        size_t counted = 0, i, keep;
        long sum = 0;
        long vals[256];
        size_t m = 0, j;
        for (i = 0; i < n && m < 256; i++) {
            if (laps[i] > 0) {
                /* insertion sort ascending; equal times keep their order, so later laps sit further right */
                for (j = m; j > 0 && vals[j - 1] > laps[i]; j--) vals[j] = vals[j - 1];
                vals[j] = laps[i];
                m++;
                counted++;
            }
        }
        if (counted == 0) return -1;
        keep = drop_slowest >= counted ? 1 : counted - drop_slowest;
        for (i = 0; i < keep; i++) sum += vals[i];
        return (2 * sum + (long)keep) / (2 * (long)keep);
    }
''')

V4 = dd(r'''
    #include "harness.h"
    #include "lapclock.h"

    int main(void) {
        char buf[32];
        long ms = 0;
        long laps[3] = {90000, 0, 83456};
        h_init();

        CHECK_INT(lc_format(83456, buf, sizeof buf), 8);
        CHECK_STR(buf, "1:23.456");
        CHECK_INT(lc_parse("1:23.456", 8, &ms), 0);
        CHECK_INT(ms, 83456);
        CHECK_INT(lc_best(laps, 3), 2);
        return h_report();
    }
''')

H5 = dd(r'''
    #include <stdio.h>
    #include <stdlib.h>
    #include <string.h>

    #include "harness.h"
    #include "lapclock.h"

    typedef struct { long ms; const char *text; } fmt_case;
    typedef struct { const char *text; int ok; long ms; } parse_case;
    typedef struct { int n; int best; int unused; long laps[12]; } best_case;
    typedef struct { int n; int drop; long want; long laps[12]; } avg_case;

    static const fmt_case FMTS[] = {
        {0L, "0:00.000"},
        {1L, "0:00.001"},
        {5L, "0:00.005"},
        {999L, "0:00.999"},
        {1000L, "0:01.000"},
        {1001L, "0:01.001"},
        {59999L, "0:59.999"},
        {60000L, "1:00.000"},
        {60001L, "1:00.001"},
        {83456L, "1:23.456"},
        {599999L, "9:59.999"},
        {600000L, "10:00.000"},
        {3599999L, "59:59.999"},
        {3600000L, "1:00:00.000"},
        {3600001L, "1:00:00.001"},
        {3723004L, "1:02:03.004"},
        {36000000L, "10:00:00.000"},
        {359999999L, "99:59:59.999"},
        {360000000L, "100:00:00.000"},
        {1999999999L, "555:33:19.999"},
        {2000000000L, "555:33:20.000"},
        {-1L, "-0:00.001"},
        {-5L, "-0:00.005"},
        {-1000L, "-0:01.000"},
        {-1500L, "-0:01.500"},
        {-83456L, "-1:23.456"},
        {-3600000L, "-1:00:00.000"},
        {-3723004L, "-1:02:03.004"},
        {-2000000000L, "-555:33:20.000"},
        {59000L, "0:59.000"},
        {61000L, "1:01.000"},
        {3661001L, "1:01:01.001"},
        {7200000L, "2:00:00.000"},
        {86400000L, "24:00:00.000"},
        {12345678L, "3:25:45.678"},
    };

    static const parse_case PARSES[] = {
        {"0:00", 1, 0},
        {"0:00.000", 1, 0},
        {"0:00.0", 1, 0},
        {"0:01", 1, 1000},
        {"1:23", 1, 83000},
        {"1:23.4", 1, 83400},
        {"1:23.45", 1, 83450},
        {"1:23.456", 1, 83456},
        {"1:23.", 0, 0},
        {"1:23.4567", 0, 0},
        {"1:2", 0, 0},
        {"1:234", 0, 0},
        {"12:34", 1, 754000},
        {"123:45", 1, 7425000},
        {"1234:56", 1, 74096000},
        {"12345:00", 0, 0},
        {"99:59.999", 1, 5999999},
        {"0:59.999", 1, 59999},
        {"0:60", 0, 0},
        {"0:60.000", 0, 0},
        {"1:60", 0, 0},
        {"1:00:00", 1, 3600000},
        {"1:00:00.000", 1, 3600000},
        {"0:00:00", 1, 0},
        {"00:00", 1, 0},
        {"00:00:00", 1, 0},
        {"1:02:03", 1, 3723000},
        {"1:02:03.004", 1, 3723004},
        {"1:02:03.04", 1, 3723040},
        {"1:02:03.4", 1, 3723400},
        {"123:59:59.999", 1, 446399999},
        {"1234:00:00", 0, 0},
        {"1:2:03", 0, 0},
        {"1:02:3", 0, 0},
        {"1:60:00", 0, 0},
        {"1:00:60", 0, 0},
        {"1:02:03.", 0, 0},
        {"1:02:03.0004", 0, 0},
        {"-0:00.000", 1, 0},
        {"-0:01.500", 1, -1500},
        {"-1:23.456", 1, -83456},
        {"-1:02:03.004", 1, -3723004},
        {"--1:00", 0, 0},
        {"+1:00", 0, 0},
        {"1:00 ", 0, 0},
        {" 1:00", 0, 0},
        {"1:00x", 0, 0},
        {"x1:00", 0, 0},
        {"1.00", 0, 0},
        {"1:00:", 0, 0},
        {"1::00", 0, 0},
        {":00", 0, 0},
        {"1:", 0, 0},
        {"", 0, 0},
        {"-", 0, 0},
        {"0:00,5", 0, 0},
        {"0:00.5.5", 0, 0},
        {"1:00.5:00", 0, 0},
        {"5:00:00.5", 1, 18000500},
        {"33333:00", 0, 0},
        {"33333:20", 0, 0},
        {"33333:19.999", 0, 0},
        {"33334:00", 0, 0},
        {"555:00:00", 1, 1998000000},
        {"1:00:00:00", 0, 0},
        {"0:00.5", 1, 500},
        {"0:00.50", 1, 500},
        {"0:00.500", 1, 500},
        {"0:00.050", 1, 50},
        {"0:00.005", 1, 5},
        {"0:00.05", 1, 50},
        {"0:00.5x", 0, 0},
        {"a:bc", 0, 0},
        {"1:ab", 0, 0},
        {"1:0a", 0, 0},
        {"9:59", 1, 599000},
        {"10:00", 1, 600000},
        {"999:59:59", 0, 0},
        {"999:59:59.999", 0, 0},
        {"2000000:00", 0, 0},
    };

    static const best_case BESTS[] = {
        {0, -1, 0, {0L}},
        {1, -1, 0, {0L}},
        {1, -1, 0, {-5L}},
        {1, 0, 0, {83456L}},
        {3, 1, 0, {90000L, 80000L, 85000L}},
        {3, 0, 0, {80000L, 80000L, 90000L}},
        {4, 2, 0, {0L, 0L, 70000L, 0L}},
        {3, 2, 0, {-1L, 0L, 5L}},
        {4, 1, 0, {70000L, 60000L, 60000L, 70000L}},
        {5, 0, 0, {100L, 200L, 300L, 400L, 500L}},
        {2, 0, 0, {1L, 2L}},
        {4, 1, 0, {5L, 3L, 9L, 3L}},
        {9, 1, 0, {83481L, 30415L, 0L, 70558L, -1L, 0L, -1L, -1L, 0L}},
        {2, -1, 0, {-1L, 0L}},
        {3, -1, 0, {-1L, -1L, -1L}},
        {6, 2, 0, {89162L, -1L, 84578L, 0L, 94288L, 96576L}},
        {7, 0, 0, {193749L, -1L, 0L, 885922L, 575738L, 0L, -1L}},
        {9, 4, 0, {-1L, 110582L, 263082L, 64162L, 38411L, 61951L, 117224L, 69424L, 62068L}},
        {4, 1, 0, {0L, 69512L, 0L, 629827L}},
        {0, -1, 0, {0L}},
        {3, 0, 0, {95066L, 682588L, 0L}},
        {7, 5, 0, {-1L, -1L, -1L, -1L, 885768L, 148062L, 547561L}},
        {7, 6, 0, {91641L, 492916L, 118029L, 188111L, 0L, 114469L, 58271L}},
        {9, 4, 0, {54498L, 97635L, 113659L, -1L, 51517L, 92717L, 110678L, 95597L, -1L}},
        {7, 5, 0, {-1L, -1L, 982916L, 0L, 180174L, 89671L, -1L}},
        {9, 8, 0, {-1L, -1L, -1L, -1L, -1L, 0L, 104459L, 0L, 76786L}},
        {0, -1, 0, {0L}},
        {5, 3, 0, {103133L, 0L, 99005L, 62428L, -1L}},
        {6, 5, 0, {103640L, -1L, 591250L, 0L, 0L, 100050L}},
        {9, 6, 0, {341249L, -1L, 305655L, -1L, 84055L, 263265L, 52578L, 114455L, 0L}},
        {1, 0, 0, {108126L}},
        {0, -1, 0, {0L}},
        {2, 0, 0, {13845L, 119804L}},
        {3, 2, 0, {0L, 82199L, 70285L}},
        {4, 3, 0, {637574L, 0L, -1L, 89412L}},
        {9, 1, 0, {0L, 110861L, 0L, 580102L, -1L, 450543L, 900405L, -1L, 0L}},
        {4, 1, 0, {728364L, 679891L, -1L, 729005L}},
        {5, 4, 0, {0L, -1L, 0L, 0L, 757700L}},
        {1, 0, 0, {735312L}},
        {0, -1, 0, {0L}},
        {1, -1, 0, {0L}},
        {2, 0, 0, {740058L, -1L}},
    };

    static const avg_case AVGS[] = {
        {0, 0, -1L, {0L}},
        {0, 1, -1L, {0L}},
        {0, 2, -1L, {0L}},
        {0, 3, -1L, {0L}},
        {0, 10, -1L, {0L}},
        {1, 0, -1L, {0L}},
        {1, 1, -1L, {0L}},
        {1, 2, -1L, {0L}},
        {1, 3, -1L, {0L}},
        {1, 10, -1L, {0L}},
        {1, 0, -1L, {-5L}},
        {1, 1, -1L, {-5L}},
        {1, 2, -1L, {-5L}},
        {1, 3, -1L, {-5L}},
        {1, 10, -1L, {-5L}},
        {1, 0, 83456L, {83456L}},
        {1, 1, 83456L, {83456L}},
        {1, 2, 83456L, {83456L}},
        {1, 3, 83456L, {83456L}},
        {1, 10, 83456L, {83456L}},
        {3, 0, 85000L, {90000L, 80000L, 85000L}},
        {3, 1, 82500L, {90000L, 80000L, 85000L}},
        {3, 2, 80000L, {90000L, 80000L, 85000L}},
        {3, 3, 80000L, {90000L, 80000L, 85000L}},
        {3, 10, 80000L, {90000L, 80000L, 85000L}},
        {3, 0, 83333L, {80000L, 80000L, 90000L}},
        {3, 1, 80000L, {80000L, 80000L, 90000L}},
        {3, 2, 80000L, {80000L, 80000L, 90000L}},
        {3, 3, 80000L, {80000L, 80000L, 90000L}},
        {3, 10, 80000L, {80000L, 80000L, 90000L}},
        {4, 0, 70000L, {0L, 0L, 70000L, 0L}},
        {4, 1, 70000L, {0L, 0L, 70000L, 0L}},
        {4, 2, 70000L, {0L, 0L, 70000L, 0L}},
        {4, 3, 70000L, {0L, 0L, 70000L, 0L}},
        {4, 10, 70000L, {0L, 0L, 70000L, 0L}},
        {3, 0, 5L, {-1L, 0L, 5L}},
        {3, 1, 5L, {-1L, 0L, 5L}},
        {3, 2, 5L, {-1L, 0L, 5L}},
        {3, 3, 5L, {-1L, 0L, 5L}},
        {3, 10, 5L, {-1L, 0L, 5L}},
        {4, 0, 65000L, {70000L, 60000L, 60000L, 70000L}},
        {4, 1, 63333L, {70000L, 60000L, 60000L, 70000L}},
        {4, 2, 60000L, {70000L, 60000L, 60000L, 70000L}},
        {4, 3, 60000L, {70000L, 60000L, 60000L, 70000L}},
        {4, 10, 60000L, {70000L, 60000L, 60000L, 70000L}},
        {5, 0, 300L, {100L, 200L, 300L, 400L, 500L}},
        {5, 1, 250L, {100L, 200L, 300L, 400L, 500L}},
        {5, 2, 200L, {100L, 200L, 300L, 400L, 500L}},
        {5, 3, 150L, {100L, 200L, 300L, 400L, 500L}},
        {5, 10, 100L, {100L, 200L, 300L, 400L, 500L}},
        {2, 0, 2L, {1L, 2L}},
        {2, 1, 1L, {1L, 2L}},
        {2, 2, 1L, {1L, 2L}},
        {2, 3, 1L, {1L, 2L}},
        {2, 10, 1L, {1L, 2L}},
        {4, 0, 5L, {5L, 3L, 9L, 3L}},
        {4, 1, 4L, {5L, 3L, 9L, 3L}},
        {4, 2, 3L, {5L, 3L, 9L, 3L}},
        {4, 3, 3L, {5L, 3L, 9L, 3L}},
        {4, 10, 3L, {5L, 3L, 9L, 3L}},
        {9, 0, 61485L, {83481L, 30415L, 0L, 70558L, -1L, 0L, -1L, -1L, 0L}},
        {9, 1, 50487L, {83481L, 30415L, 0L, 70558L, -1L, 0L, -1L, -1L, 0L}},
        {9, 2, 30415L, {83481L, 30415L, 0L, 70558L, -1L, 0L, -1L, -1L, 0L}},
        {9, 3, 30415L, {83481L, 30415L, 0L, 70558L, -1L, 0L, -1L, -1L, 0L}},
        {9, 10, 30415L, {83481L, 30415L, 0L, 70558L, -1L, 0L, -1L, -1L, 0L}},
        {2, 0, -1L, {-1L, 0L}},
        {2, 1, -1L, {-1L, 0L}},
        {2, 2, -1L, {-1L, 0L}},
        {2, 3, -1L, {-1L, 0L}},
        {2, 10, -1L, {-1L, 0L}},
        {3, 0, -1L, {-1L, -1L, -1L}},
        {3, 1, -1L, {-1L, -1L, -1L}},
        {3, 2, -1L, {-1L, -1L, -1L}},
        {3, 3, -1L, {-1L, -1L, -1L}},
        {3, 10, -1L, {-1L, -1L, -1L}},
        {6, 0, 91151L, {89162L, -1L, 84578L, 0L, 94288L, 96576L}},
        {6, 1, 89343L, {89162L, -1L, 84578L, 0L, 94288L, 96576L}},
        {6, 2, 86870L, {89162L, -1L, 84578L, 0L, 94288L, 96576L}},
        {6, 3, 84578L, {89162L, -1L, 84578L, 0L, 94288L, 96576L}},
        {6, 10, 84578L, {89162L, -1L, 84578L, 0L, 94288L, 96576L}},
        {7, 0, 551803L, {193749L, -1L, 0L, 885922L, 575738L, 0L, -1L}},
        {7, 1, 384744L, {193749L, -1L, 0L, 885922L, 575738L, 0L, -1L}},
        {7, 2, 193749L, {193749L, -1L, 0L, 885922L, 575738L, 0L, -1L}},
        {7, 3, 193749L, {193749L, -1L, 0L, 885922L, 575738L, 0L, -1L}},
        {7, 10, 193749L, {193749L, -1L, 0L, 885922L, 575738L, 0L, -1L}},
        {9, 0, 98363L, {-1L, 110582L, 263082L, 64162L, 38411L, 61951L, 117224L, 69424L, 62068L}},
        {9, 1, 74832L, {-1L, 110582L, 263082L, 64162L, 38411L, 61951L, 117224L, 69424L, 62068L}},
        {9, 2, 67766L, {-1L, 110582L, 263082L, 64162L, 38411L, 61951L, 117224L, 69424L, 62068L}},
        {9, 3, 59203L, {-1L, 110582L, 263082L, 64162L, 38411L, 61951L, 117224L, 69424L, 62068L}},
        {9, 10, 38411L, {-1L, 110582L, 263082L, 64162L, 38411L, 61951L, 117224L, 69424L, 62068L}},
        {4, 0, 349670L, {0L, 69512L, 0L, 629827L}},
        {4, 1, 69512L, {0L, 69512L, 0L, 629827L}},
        {4, 2, 69512L, {0L, 69512L, 0L, 629827L}},
        {4, 3, 69512L, {0L, 69512L, 0L, 629827L}},
        {4, 10, 69512L, {0L, 69512L, 0L, 629827L}},
        {0, 0, -1L, {0L}},
        {0, 1, -1L, {0L}},
        {0, 2, -1L, {0L}},
        {0, 3, -1L, {0L}},
        {0, 10, -1L, {0L}},
        {3, 0, 388827L, {95066L, 682588L, 0L}},
        {3, 1, 95066L, {95066L, 682588L, 0L}},
        {3, 2, 95066L, {95066L, 682588L, 0L}},
        {3, 3, 95066L, {95066L, 682588L, 0L}},
        {3, 10, 95066L, {95066L, 682588L, 0L}},
        {7, 0, 527130L, {-1L, -1L, -1L, -1L, 885768L, 148062L, 547561L}},
        {7, 1, 347812L, {-1L, -1L, -1L, -1L, 885768L, 148062L, 547561L}},
        {7, 2, 148062L, {-1L, -1L, -1L, -1L, 885768L, 148062L, 547561L}},
        {7, 3, 148062L, {-1L, -1L, -1L, -1L, 885768L, 148062L, 547561L}},
        {7, 10, 148062L, {-1L, -1L, -1L, -1L, 885768L, 148062L, 547561L}},
        {7, 0, 177240L, {91641L, 492916L, 118029L, 188111L, 0L, 114469L, 58271L}},
        {7, 1, 114104L, {91641L, 492916L, 118029L, 188111L, 0L, 114469L, 58271L}},
        {7, 2, 95603L, {91641L, 492916L, 118029L, 188111L, 0L, 114469L, 58271L}},
        {7, 3, 88127L, {91641L, 492916L, 118029L, 188111L, 0L, 114469L, 58271L}},
        {7, 10, 58271L, {91641L, 492916L, 118029L, 188111L, 0L, 114469L, 58271L}},
        {9, 0, 88043L, {54498L, 97635L, 113659L, -1L, 51517L, 92717L, 110678L, 95597L, -1L}},
        {9, 1, 83774L, {54498L, 97635L, 113659L, -1L, 51517L, 92717L, 110678L, 95597L, -1L}},
        {9, 2, 78393L, {54498L, 97635L, 113659L, -1L, 51517L, 92717L, 110678L, 95597L, -1L}},
        {9, 3, 73582L, {54498L, 97635L, 113659L, -1L, 51517L, 92717L, 110678L, 95597L, -1L}},
        {9, 10, 51517L, {54498L, 97635L, 113659L, -1L, 51517L, 92717L, 110678L, 95597L, -1L}},
        {7, 0, 417587L, {-1L, -1L, 982916L, 0L, 180174L, 89671L, -1L}},
        {7, 1, 134923L, {-1L, -1L, 982916L, 0L, 180174L, 89671L, -1L}},
        {7, 2, 89671L, {-1L, -1L, 982916L, 0L, 180174L, 89671L, -1L}},
        {7, 3, 89671L, {-1L, -1L, 982916L, 0L, 180174L, 89671L, -1L}},
        {7, 10, 89671L, {-1L, -1L, 982916L, 0L, 180174L, 89671L, -1L}},
        {9, 0, 90623L, {-1L, -1L, -1L, -1L, -1L, 0L, 104459L, 0L, 76786L}},
        {9, 1, 76786L, {-1L, -1L, -1L, -1L, -1L, 0L, 104459L, 0L, 76786L}},
        {9, 2, 76786L, {-1L, -1L, -1L, -1L, -1L, 0L, 104459L, 0L, 76786L}},
        {9, 3, 76786L, {-1L, -1L, -1L, -1L, -1L, 0L, 104459L, 0L, 76786L}},
        {9, 10, 76786L, {-1L, -1L, -1L, -1L, -1L, 0L, 104459L, 0L, 76786L}},
        {0, 0, -1L, {0L}},
        {0, 1, -1L, {0L}},
        {0, 2, -1L, {0L}},
        {0, 3, -1L, {0L}},
        {0, 10, -1L, {0L}},
        {5, 0, 88189L, {103133L, 0L, 99005L, 62428L, -1L}},
        {5, 1, 80717L, {103133L, 0L, 99005L, 62428L, -1L}},
        {5, 2, 62428L, {103133L, 0L, 99005L, 62428L, -1L}},
        {5, 3, 62428L, {103133L, 0L, 99005L, 62428L, -1L}},
        {5, 10, 62428L, {103133L, 0L, 99005L, 62428L, -1L}},
        {6, 0, 264980L, {103640L, -1L, 591250L, 0L, 0L, 100050L}},
        {6, 1, 101845L, {103640L, -1L, 591250L, 0L, 0L, 100050L}},
        {6, 2, 100050L, {103640L, -1L, 591250L, 0L, 0L, 100050L}},
        {6, 3, 100050L, {103640L, -1L, 591250L, 0L, 0L, 100050L}},
        {6, 10, 100050L, {103640L, -1L, 591250L, 0L, 0L, 100050L}},
        {9, 0, 193543L, {341249L, -1L, 305655L, -1L, 84055L, 263265L, 52578L, 114455L, 0L}},
        {9, 1, 164002L, {341249L, -1L, 305655L, -1L, 84055L, 263265L, 52578L, 114455L, 0L}},
        {9, 2, 128588L, {341249L, -1L, 305655L, -1L, 84055L, 263265L, 52578L, 114455L, 0L}},
        {9, 3, 83696L, {341249L, -1L, 305655L, -1L, 84055L, 263265L, 52578L, 114455L, 0L}},
        {9, 10, 52578L, {341249L, -1L, 305655L, -1L, 84055L, 263265L, 52578L, 114455L, 0L}},
        {1, 0, 108126L, {108126L}},
        {1, 1, 108126L, {108126L}},
        {1, 2, 108126L, {108126L}},
        {1, 3, 108126L, {108126L}},
        {1, 10, 108126L, {108126L}},
        {0, 0, -1L, {0L}},
        {0, 1, -1L, {0L}},
        {0, 2, -1L, {0L}},
        {0, 3, -1L, {0L}},
        {0, 10, -1L, {0L}},
        {2, 0, 66825L, {13845L, 119804L}},
        {2, 1, 13845L, {13845L, 119804L}},
        {2, 2, 13845L, {13845L, 119804L}},
        {2, 3, 13845L, {13845L, 119804L}},
        {2, 10, 13845L, {13845L, 119804L}},
        {3, 0, 76242L, {0L, 82199L, 70285L}},
        {3, 1, 70285L, {0L, 82199L, 70285L}},
        {3, 2, 70285L, {0L, 82199L, 70285L}},
        {3, 3, 70285L, {0L, 82199L, 70285L}},
        {3, 10, 70285L, {0L, 82199L, 70285L}},
        {4, 0, 363493L, {637574L, 0L, -1L, 89412L}},
        {4, 1, 89412L, {637574L, 0L, -1L, 89412L}},
        {4, 2, 89412L, {637574L, 0L, -1L, 89412L}},
        {4, 3, 89412L, {637574L, 0L, -1L, 89412L}},
        {4, 10, 89412L, {637574L, 0L, -1L, 89412L}},
        {9, 0, 510478L, {0L, 110861L, 0L, 580102L, -1L, 450543L, 900405L, -1L, 0L}},
        {9, 1, 380502L, {0L, 110861L, 0L, 580102L, -1L, 450543L, 900405L, -1L, 0L}},
        {9, 2, 280702L, {0L, 110861L, 0L, 580102L, -1L, 450543L, 900405L, -1L, 0L}},
        {9, 3, 110861L, {0L, 110861L, 0L, 580102L, -1L, 450543L, 900405L, -1L, 0L}},
        {9, 10, 110861L, {0L, 110861L, 0L, 580102L, -1L, 450543L, 900405L, -1L, 0L}},
        {4, 0, 712420L, {728364L, 679891L, -1L, 729005L}},
        {4, 1, 704128L, {728364L, 679891L, -1L, 729005L}},
        {4, 2, 679891L, {728364L, 679891L, -1L, 729005L}},
        {4, 3, 679891L, {728364L, 679891L, -1L, 729005L}},
        {4, 10, 679891L, {728364L, 679891L, -1L, 729005L}},
        {5, 0, 757700L, {0L, -1L, 0L, 0L, 757700L}},
        {5, 1, 757700L, {0L, -1L, 0L, 0L, 757700L}},
        {5, 2, 757700L, {0L, -1L, 0L, 0L, 757700L}},
        {5, 3, 757700L, {0L, -1L, 0L, 0L, 757700L}},
        {5, 10, 757700L, {0L, -1L, 0L, 0L, 757700L}},
        {1, 0, 735312L, {735312L}},
        {1, 1, 735312L, {735312L}},
        {1, 2, 735312L, {735312L}},
        {1, 3, 735312L, {735312L}},
        {1, 10, 735312L, {735312L}},
        {0, 0, -1L, {0L}},
        {0, 1, -1L, {0L}},
        {0, 2, -1L, {0L}},
        {0, 3, -1L, {0L}},
        {0, 10, -1L, {0L}},
        {1, 0, -1L, {0L}},
        {1, 1, -1L, {0L}},
        {1, 2, -1L, {0L}},
        {1, 3, -1L, {0L}},
        {1, 10, -1L, {0L}},
        {2, 0, 740058L, {740058L, -1L}},
        {2, 1, 740058L, {740058L, -1L}},
        {2, 2, 740058L, {740058L, -1L}},
        {2, 3, 740058L, {740058L, -1L}},
        {2, 10, 740058L, {740058L, -1L}},
    };

    static void test_format(void) {
        size_t i;
        char ctx[40];
        for (i = 0; i < sizeof FMTS / sizeof FMTS[0]; i++) {
            size_t len = strlen(FMTS[i].text);
            char *buf = malloc(len + 1);
            snprintf(ctx, sizeof ctx, "format(%ld)", FMTS[i].ms);
            CHECK_INT_CTX(ctx, lc_format(FMTS[i].ms, buf, len + 1), (long long)len);
            CHECK_STR_CTX(ctx, buf, FMTS[i].text);
            free(buf);
            buf = malloc(len);
            CHECK_INT_CTX(ctx, lc_format(FMTS[i].ms, buf, len), -1);
            free(buf);
            buf = malloc(64);
            CHECK_INT_CTX(ctx, lc_format(FMTS[i].ms, buf, 64), (long long)len);
            CHECK_STR_CTX(ctx, buf, FMTS[i].text);
            free(buf);
        }
        {
            char one[1] = {'?'};
            CHECK_INT(lc_format(5, one, 1), -1);
            CHECK_INT(lc_format(5, one, 0), -1);
            CHECK_INT(one[0], '?');
        }
    }

    static void test_parse(void) {
        size_t i;
        for (i = 0; i < sizeof PARSES / sizeof PARSES[0]; i++) {
            size_t n = strlen(PARSES[i].text);
            char *p = malloc(n ? n : 1);
            long v = 12345;
            memcpy(p, PARSES[i].text, n);
            CHECK_INT_CTX(PARSES[i].text, lc_parse(p, n, &v), PARSES[i].ok ? 0 : -1);
            CHECK_INT_CTX(PARSES[i].text, v, PARSES[i].ok ? PARSES[i].ms : 12345);
            free(p);
        }
        {
            long v = 1;
            CHECK_INT(lc_parse("1:23.456xyz", 8, &v), 0);
            CHECK_INT(v, 83456);
            CHECK_INT(lc_parse("1:23.456", 7, &v), 0);
            CHECK_INT(v, 83450);
            v = 1;
            CHECK_INT(lc_parse("1:23.456", 5, &v), -1);   /* "1:23." */
            CHECK_INT(v, 1);
            CHECK_INT(lc_parse("1:23.456", 4, &v), 0);    /* "1:23" */
            CHECK_INT(v, 83000);
        }
    }

    static void test_best(void) {
        size_t i, k;
        char ctx[48];
        for (i = 0; i < sizeof BESTS / sizeof BESTS[0]; i++) {
            long laps[12];
            for (k = 0; k < (size_t)BESTS[i].n; k++) laps[k] = BESTS[i].laps[k];
            snprintf(ctx, sizeof ctx, "best case %d", (int)i);
            CHECK_INT_CTX(ctx, lc_best(laps, (size_t)BESTS[i].n), BESTS[i].best);
        }
    }

    static void test_average(void) {
        size_t i, k;
        char ctx[48];
        for (i = 0; i < sizeof AVGS / sizeof AVGS[0]; i++) {
            long laps[12];
            for (k = 0; k < (size_t)AVGS[i].n; k++) laps[k] = AVGS[i].laps[k];
            snprintf(ctx, sizeof ctx, "average case %d (drop %d)", (int)i, AVGS[i].drop);
            CHECK_INT_CTX(ctx, lc_average(laps, (size_t)AVGS[i].n, (size_t)AVGS[i].drop), AVGS[i].want);
            /* the input is not changed */
            for (k = 0; k < (size_t)AVGS[i].n; k++) CHECK_INT_CTX(ctx, laps[k], AVGS[i].laps[k]);
        }
        {
            long laps[300];
            int j;
            for (j = 0; j < 300; j++) laps[j] = 1000 + j;
            CHECK_INT(lc_average(laps, 300, 0) > 0, 1);
        }
    }

    int main(void) {
        h_init();
        test_format();
        test_parse();
        test_best();
        test_average();
        return h_report();
    }
''')

LIB = Lib(
    name="lapclock", lang="c", title="the lapclock timing helpers",
    blurb="The karting track's timing board prints lap times such as `1:23.456` and ranks drivers by their fastest lap and their trimmed average with lapclock.",
    files={"README.md": README1, "include/lapclock.h": F2, "src/lapclock.c": F3},
    visible_tests={"tests/test_main.c": V4, "tests/harness.h": _lang3.C_HARNESS},
    hidden_tests={"tests/test_main.c": H5},
    mutate=["src/lapclock.c"], difficulty=1, tags=["time", "formatting", "statistics"],
    verify=_lang3.C_VERIFY,
)

_lang3.add(LIB, n=8)
