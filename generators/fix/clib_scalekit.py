"""Pounds-and-ounces conversions for a postal scale (c): exact integer rounding to tenths of an ounce, text output and kitchen-scale rounding; bugs injected into the library."""
from fx import Lib, dd

from generators.fix import _lang3

README1 = dd(r'''
    # scalekit

    Weight conversions for a postal scale, integer arithmetic only. One pound is 16 ounces; one ounce is exactly `28.349523125` grams. Ounces are handled in **tenths of an ounce** (`oz_tenths`): `35` means 3.5 oz, and a pound is `160` tenths.
    "Rounded" always means to the nearest unit with halves rounding **up**.

    ## `long wt_to_grams(long lb, long oz_tenths)`
    The weight `lb` pounds and `oz_tenths` tenths of an ounce in grams, rounded. Invalid (returns -1): `lb < 0`, `lb > 1000000`, `oz_tenths < 0` or `oz_tenths >= 160`.

    ## `int wt_from_grams(long grams, long *lb, long *oz_tenths)`
    Converts grams to whole pounds and tenths of an ounce: the number of tenths of an ounce in total is `grams / 2.8349523125` rounded, then `*lb` is that total divided by 160 (rounded down) and `*oz_tenths` the remainder (so `*oz_tenths` is `0..159`; a weight
    just below a pound can round up to the full pound). Returns 0, or -1 (leaving both outputs alone) when `grams < 0` or `grams > 400000000`.

    ## `int wt_format(long grams, char *buf, size_t cap)`
    The weight as text and a NUL, using the conversion above: `"5 lb 3.5 oz"`. The pounds part is left out when it is 0 (`"3.5 oz"`), the ounces part is left out when it is 0 and there are pounds (`"5 lb"`); a weight of zero ounces and pounds is `"0 oz"`.
    Ounces are written without a fraction when the tenths are 0 (`"3 oz"`) and as `W.T` otherwise (`"3.5 oz"`, `"0.5 oz"`). Returns the text length, or -1 (writing nothing) when the text and its NUL do not fit in `cap` or when `grams` is out of the range of `wt_from_grams`.

    ## `long wt_kitchen(long grams)`
    Rounding for a kitchen scale display: up to and including 100 g the weight is unchanged, above 100 g up to and including 1000 g it is rounded to a multiple of 5, above 1000 g to a multiple of 10. Returns -1 for negative weights.
''')

F2 = dd(r'''
    #ifndef SCALEKIT_H
    #define SCALEKIT_H

    #include <stddef.h>

    long wt_to_grams(long lb, long oz_tenths);
    int wt_from_grams(long grams, long *lb, long *oz_tenths);
    int wt_format(long grams, char *buf, size_t cap);
    long wt_kitchen(long grams);

    #endif
''')

F3 = dd(r'''
    #include "scalekit.h"

    #include <stdio.h>
    #include <string.h>

    #define OZ_NUM 28349523125LL /* grams per ounce, times 10^9 */

    long wt_to_grams(long lb, long oz_tenths) {
        long long tenths;
        if (lb < 0 || lb > 1000000 || oz_tenths < 0 || oz_tenths >= 160) return -1;
        tenths = (long long)lb * 160 + oz_tenths;
        /* grams = tenths * 28.349523125 / 10 = tenths * OZ_NUM / 10^10 */
        return (long)((tenths * OZ_NUM + 5000000000LL) / 10000000000LL);
    }

    int wt_from_grams(long grams, long *lb, long *oz_tenths) {
        long long total;
        if (grams < 0 || grams > 400000000L) return -1;
        /* tenths = grams * 10 / 28.349523125 = grams * 10^10 / OZ_NUM */
        total = ((long long)grams * 10000000000LL * 2 + OZ_NUM) / (2 * OZ_NUM);
        *lb = (long)(total / 160);
        *oz_tenths = (long)(total % 160);
        return 0;
    }

    int wt_format(long grams, char *buf, size_t cap) {
        long lb, t;
        char tmp[128], oz[48];
        int len;
        if (wt_from_grams(grams, &lb, &t) != 0) return -1;
        if (t % 10 == 0) snprintf(oz, sizeof oz, "%ld oz", t / 10);
        else snprintf(oz, sizeof oz, "%ld.%ld oz", t / 10, t % 10);
        if (lb == 0) len = snprintf(tmp, sizeof tmp, "%s", oz);
        else if (t == 0) len = snprintf(tmp, sizeof tmp, "%ld lb", lb);
        else len = snprintf(tmp, sizeof tmp, "%ld lb %s", lb, oz);
        if (len < 0 || (size_t)len >= cap) return -1;
        memcpy(buf, tmp, (size_t)len + 1);
        return len;
    }

    long wt_kitchen(long grams) {
        long step;
        if (grams < 0) return -1;
        if (grams <= 100) return grams;
        step = grams <= 1000 ? 5 : 10;
        return (grams + step / 2) / step * step;
    }
''')

V4 = dd(r'''
    #include "harness.h"
    #include "scalekit.h"

    int main(void) {
        char buf[32];
        long lb = 0, t = 0;
        h_init();

        CHECK_INT(wt_to_grams(1, 0), 454);
        CHECK_INT(wt_from_grams(454, &lb, &t), 0);
        CHECK_INT(lb, 1);
        CHECK_INT(wt_format(2268, buf, sizeof buf), 4);
        CHECK_STR(buf, "5 lb");
        CHECK_INT(wt_kitchen(103), 105);
        return h_report();
    }
''')

H5 = dd(r'''
    #include <stdio.h>
    #include <stdlib.h>
    #include <string.h>

    #include "harness.h"
    #include "scalekit.h"

    typedef struct { long lb, tenths, grams; } to_case;
    typedef struct { long grams; int invalid; long lb, tenths; } from_case;
    typedef struct { long grams; const char *text; } fmt_case;
    typedef struct { long grams, want; } kit_case;

    static const to_case TOS[] = {
        {0, 0, 0L},
        {0, 1, 3L},
        {0, 5, 14L},
        {0, 10, 28L},
        {0, 159, 451L},
        {1, 0, 454L},
        {1, 1, 456L},
        {5, 35, 2367L},
        {10, 0, 4536L},
        {25, 80, 11567L},
        {100, 159, 45810L},
        {1000000, 0, 453592370L},
        {1000000, 159, 453592821L},
        {1000001, 0, -1L},
        {1000000, 160, -1L},
        {0, 160, -1L},
        {-1, 0, -1L},
        {0, -1, -1L},
        {2, 100, 1191L},
        {3, 17, 1409L},
        {7, 99, 3456L},
        {15, 155, 7243L},
        {50, 60, 22850L},
        {123, 45, 55919L},
    };
    static const from_case FROMS[] = {
        {0L, 0, 0, 0},
        {1L, 0, 0, 0},
        {2L, 0, 0, 1},
        {3L, 0, 0, 1},
        {14L, 0, 0, 5},
        {15L, 0, 0, 5},
        {16L, 0, 0, 6},
        {17L, 0, 0, 6},
        {28L, 0, 0, 10},
        {29L, 0, 0, 10},
        {30L, 0, 0, 11},
        {42L, 0, 0, 15},
        {43L, 0, 0, 15},
        {44L, 0, 0, 16},
        {45L, 0, 0, 16},
        {100L, 0, 0, 35},
        {283L, 0, 0, 100},
        {284L, 0, 0, 100},
        {453L, 0, 1, 0},
        {454L, 0, 1, 0},
        {455L, 0, 1, 0},
        {456L, 0, 1, 1},
        {500L, 0, 1, 16},
        {1000L, 0, 2, 33},
        {2267L, 0, 5, 0},
        {2268L, 0, 5, 0},
        {4535L, 0, 10, 0},
        {4536L, 0, 10, 0},
        {4537L, 0, 10, 0},
        {10000L, 0, 22, 7},
        {45359L, 0, 100, 0},
        {45360L, 0, 100, 0},
        {453592L, 0, 1000, 0},
        {453593L, 0, 1000, 0},
        {1000000L, 0, 2204, 100},
        {45359237L, 0, 100000, 0},
        {45359238L, 0, 100000, 0},
        {100000000L, 0, 220462, 42},
        {399999999L, 0, 881849, 7},
        {400000000L, 0, 881849, 8},
        {400000001L, 1, 0, 0},
        {500000000L, 1, 0, 0},
        {-1L, 1, 0, 0},
        {-100L, 1, 0, 0},
        {483L, 0, 1, 10},
        {621L, 0, 1, 59},
        {211L, 0, 0, 74},
        {1477L, 0, 3, 41},
        {811L, 0, 1, 126},
        {980L, 0, 2, 26},
        {317L, 0, 0, 112},
        {184L, 0, 0, 65},
        {136L, 0, 0, 48},
        {40L, 0, 0, 14},
        {822L, 0, 1, 130},
        {1125L, 0, 2, 77},
        {1879L, 0, 4, 23},
        {592L, 0, 1, 49},
        {1639L, 0, 3, 98},
        {1567L, 0, 3, 73},
        {120L, 0, 0, 42},
        {454L, 0, 1, 0},
        {1065L, 0, 2, 56},
        {1099L, 0, 2, 68},
        {737L, 0, 1, 100},
        {566L, 0, 1, 40},
        {1596L, 0, 3, 83},
        {353L, 0, 0, 125},
        {1693L, 0, 3, 117},
        {217L, 0, 0, 77},
        {536L, 0, 1, 29},
        {439L, 0, 0, 155},
        {1931L, 0, 4, 41},
        {1899L, 0, 4, 30},
        {52L, 0, 0, 18},
        {1697L, 0, 3, 119},
        {1312L, 0, 2, 143},
        {1652L, 0, 3, 103},
        {533L, 0, 1, 28},
        {1639L, 0, 3, 98},
        {556L, 0, 1, 36},
        {396L, 0, 0, 140},
        {337L, 0, 0, 119},
        {634L, 0, 1, 64},
        {4861364L, 0, 10717, 76},
        {6249719L, 0, 13778, 44},
        {1456890L, 0, 3211, 143},
        {5662674L, 0, 12484, 9},
        {6510416L, 0, 14353, 2},
        {8490495L, 0, 18718, 54},
        {4177405L, 0, 9209, 96},
        {2984824L, 0, 6580, 66},
        {4151378L, 0, 9152, 35},
        {7947486L, 0, 17521, 33},
        {4699580L, 0, 10360, 128},
        {1500980L, 0, 3309, 15},
        {9189855L, 0, 20260, 26},
        {5039287L, 0, 11109, 116},
        {122986L, 0, 271, 22},
        {4899968L, 0, 10802, 93},
        {9604721L, 0, 21174, 126},
        {5232501L, 0, 11535, 110},
        {8531073L, 0, 18807, 127},
        {3275657L, 0, 7221, 94},
        {6946862L, 0, 15315, 33},
        {7111027L, 0, 15677, 21},
        {4837253L, 0, 10664, 51},
        {7233701L, 0, 15947, 93},
        {7574772L, 0, 16699, 82},
        {2708510L, 0, 5971, 39},
        {3914869L, 0, 8630, 129},
        {5120923L, 0, 11289, 112},
        {4358290L, 0, 9608, 62},
        {727421L, 0, 1603, 110},
    };
    static const fmt_case FMTS[] = {
        {0L, "0 oz"},
        {1L, "0 oz"},
        {2L, "0.1 oz"},
        {3L, "0.1 oz"},
        {14L, "0.5 oz"},
        {15L, "0.5 oz"},
        {16L, "0.6 oz"},
        {17L, "0.6 oz"},
        {28L, "1 oz"},
        {29L, "1 oz"},
        {30L, "1.1 oz"},
        {42L, "1.5 oz"},
        {43L, "1.5 oz"},
        {44L, "1.6 oz"},
        {45L, "1.6 oz"},
        {100L, "3.5 oz"},
        {283L, "10 oz"},
        {284L, "10 oz"},
        {453L, "1 lb"},
        {454L, "1 lb"},
        {455L, "1 lb"},
        {456L, "1 lb 0.1 oz"},
        {500L, "1 lb 1.6 oz"},
        {1000L, "2 lb 3.3 oz"},
        {2267L, "5 lb"},
        {2268L, "5 lb"},
        {4535L, "10 lb"},
        {4536L, "10 lb"},
        {4537L, "10 lb"},
        {10000L, "22 lb 0.7 oz"},
        {45359L, "100 lb"},
        {45360L, "100 lb"},
        {453592L, "1000 lb"},
        {453593L, "1000 lb"},
        {1000000L, "2204 lb 10 oz"},
        {45359237L, "100000 lb"},
        {45359238L, "100000 lb"},
        {100000000L, "220462 lb 4.2 oz"},
        {399999999L, "881849 lb 0.7 oz"},
        {400000000L, "881849 lb 0.8 oz"},
        {400000001L, NULL},
        {500000000L, NULL},
        {-1L, NULL},
        {-100L, NULL},
        {483L, "1 lb 1 oz"},
        {621L, "1 lb 5.9 oz"},
        {211L, "7.4 oz"},
        {1477L, "3 lb 4.1 oz"},
        {811L, "1 lb 12.6 oz"},
        {980L, "2 lb 2.6 oz"},
        {317L, "11.2 oz"},
        {184L, "6.5 oz"},
        {136L, "4.8 oz"},
        {40L, "1.4 oz"},
        {822L, "1 lb 13 oz"},
        {1125L, "2 lb 7.7 oz"},
        {1879L, "4 lb 2.3 oz"},
        {592L, "1 lb 4.9 oz"},
        {1639L, "3 lb 9.8 oz"},
        {1567L, "3 lb 7.3 oz"},
        {120L, "4.2 oz"},
        {454L, "1 lb"},
        {1065L, "2 lb 5.6 oz"},
        {1099L, "2 lb 6.8 oz"},
        {737L, "1 lb 10 oz"},
        {566L, "1 lb 4 oz"},
        {1596L, "3 lb 8.3 oz"},
        {353L, "12.5 oz"},
        {1693L, "3 lb 11.7 oz"},
        {217L, "7.7 oz"},
        {536L, "1 lb 2.9 oz"},
        {439L, "15.5 oz"},
        {1931L, "4 lb 4.1 oz"},
        {1899L, "4 lb 3 oz"},
        {52L, "1.8 oz"},
        {1697L, "3 lb 11.9 oz"},
        {1312L, "2 lb 14.3 oz"},
        {1652L, "3 lb 10.3 oz"},
        {533L, "1 lb 2.8 oz"},
        {1639L, "3 lb 9.8 oz"},
        {556L, "1 lb 3.6 oz"},
        {396L, "14 oz"},
        {337L, "11.9 oz"},
        {634L, "1 lb 6.4 oz"},
        {4861364L, "10717 lb 7.6 oz"},
        {6249719L, "13778 lb 4.4 oz"},
        {1456890L, "3211 lb 14.3 oz"},
        {5662674L, "12484 lb 0.9 oz"},
        {6510416L, "14353 lb 0.2 oz"},
        {8490495L, "18718 lb 5.4 oz"},
        {4177405L, "9209 lb 9.6 oz"},
        {2984824L, "6580 lb 6.6 oz"},
        {4151378L, "9152 lb 3.5 oz"},
        {7947486L, "17521 lb 3.3 oz"},
        {4699580L, "10360 lb 12.8 oz"},
        {1500980L, "3309 lb 1.5 oz"},
        {9189855L, "20260 lb 2.6 oz"},
        {5039287L, "11109 lb 11.6 oz"},
        {122986L, "271 lb 2.2 oz"},
        {4899968L, "10802 lb 9.3 oz"},
        {9604721L, "21174 lb 12.6 oz"},
        {5232501L, "11535 lb 11 oz"},
        {8531073L, "18807 lb 12.7 oz"},
        {3275657L, "7221 lb 9.4 oz"},
        {6946862L, "15315 lb 3.3 oz"},
        {7111027L, "15677 lb 2.1 oz"},
        {4837253L, "10664 lb 5.1 oz"},
        {7233701L, "15947 lb 9.3 oz"},
        {7574772L, "16699 lb 8.2 oz"},
        {2708510L, "5971 lb 3.9 oz"},
        {3914869L, "8630 lb 12.9 oz"},
        {5120923L, "11289 lb 11.2 oz"},
        {4358290L, "9608 lb 6.2 oz"},
        {727421L, "1603 lb 11 oz"},
    };
    static const kit_case KITS[] = {
        {0L, 0L},
        {1L, 1L},
        {99L, 99L},
        {100L, 100L},
        {101L, 100L},
        {102L, 100L},
        {103L, 105L},
        {104L, 105L},
        {105L, 105L},
        {106L, 105L},
        {107L, 105L},
        {108L, 110L},
        {109L, 110L},
        {110L, 110L},
        {997L, 995L},
        {998L, 1000L},
        {999L, 1000L},
        {1000L, 1000L},
        {1001L, 1000L},
        {1002L, 1000L},
        {1004L, 1000L},
        {1005L, 1010L},
        {1006L, 1010L},
        {1009L, 1010L},
        {1010L, 1010L},
        {1014L, 1010L},
        {1015L, 1020L},
        {12345L, 12350L},
        {99995L, 100000L},
        {-1L, -1L},
        {-5L, -1L},
        {2000000000L, 2000000000L},
    };

    static void test_to_grams(void) {
        size_t i;
        char ctx[40];
        for (i = 0; i < sizeof TOS / sizeof TOS[0]; i++) {
            snprintf(ctx, sizeof ctx, "to_grams(%ld, %ld)", TOS[i].lb, TOS[i].tenths);
            CHECK_INT_CTX(ctx, wt_to_grams(TOS[i].lb, TOS[i].tenths), TOS[i].grams);
        }
    }

    static void test_from_grams(void) {
        size_t i;
        char ctx[40];
        for (i = 0; i < sizeof FROMS / sizeof FROMS[0]; i++) {
            long lb = -77, t = -88;
            int rc;
            snprintf(ctx, sizeof ctx, "from_grams(%ld)", FROMS[i].grams);
            rc = wt_from_grams(FROMS[i].grams, &lb, &t);
            CHECK_INT_CTX(ctx, rc, FROMS[i].invalid ? -1 : 0);
            CHECK_INT_CTX(ctx, lb, FROMS[i].invalid ? -77 : FROMS[i].lb);
            CHECK_INT_CTX(ctx, t, FROMS[i].invalid ? -88 : FROMS[i].tenths);
        }
    }

    static void test_format(void) {
        size_t i;
        char ctx[40];
        for (i = 0; i < sizeof FMTS / sizeof FMTS[0]; i++) {
            snprintf(ctx, sizeof ctx, "format(%ld)", FMTS[i].grams);
            if (FMTS[i].text == NULL) {
                char buf[64];
                memset(buf, '?', sizeof buf);
                CHECK_INT_CTX(ctx, wt_format(FMTS[i].grams, buf, sizeof buf), -1);
                CHECK_INT_CTX(ctx, buf[0], '?');
            } else {
                size_t len = strlen(FMTS[i].text);
                char *buf = malloc(len + 1);
                CHECK_INT_CTX(ctx, wt_format(FMTS[i].grams, buf, len + 1), (long long)len);
                CHECK_STR_CTX(ctx, buf, FMTS[i].text);
                free(buf);
                buf = malloc(len);
                memset(buf, '?', len);
                CHECK_INT_CTX(ctx, wt_format(FMTS[i].grams, buf, len), -1);
                CHECK_INT_CTX(ctx, buf[0], '?');
                free(buf);
                buf = malloc(64);
                CHECK_INT_CTX(ctx, wt_format(FMTS[i].grams, buf, 64), (long long)len);
                CHECK_STR_CTX(ctx, buf, FMTS[i].text);
                free(buf);
            }
        }
    }

    static void test_kitchen(void) {
        size_t i;
        char ctx[40];
        for (i = 0; i < sizeof KITS / sizeof KITS[0]; i++) {
            snprintf(ctx, sizeof ctx, "kitchen(%ld)", KITS[i].grams);
            CHECK_INT_CTX(ctx, wt_kitchen(KITS[i].grams), KITS[i].want);
        }
    }

    int main(void) {
        h_init();
        test_to_grams();
        test_from_grams();
        test_format();
        test_kitchen();
        return h_report();
    }
''')

LIB = Lib(
    name="scalekit", lang="c", title="the scalekit weight helpers",
    blurb="The parcel counter's scale shows weights in grams and, for overseas customers, in pounds and ounces; scalekit does the conversions with integer arithmetic only.",
    files={"README.md": README1, "include/scalekit.h": F2, "src/scalekit.c": F3},
    visible_tests={"tests/test_main.c": V4, "tests/harness.h": _lang3.C_HARNESS},
    hidden_tests={"tests/test_main.c": H5},
    mutate=["src/scalekit.c"], difficulty=1, tags=["units", "rounding", "formatting"],
    verify=_lang3.C_VERIFY,
)

_lang3.add(LIB, n=8)
