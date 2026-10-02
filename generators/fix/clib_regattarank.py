"""Regatta handicap results (c): time-on-time corrected times, competition ranking with ties, DNF/DSQ places, discards and countback; bugs injected into the library."""
from fx import Lib, dd

from generators.fix import _lang3

README1 = dd(r'''
    # regattarank

    Scoring for a sailing club's handicap races and its season series.

    ## Race scoring

        typedef struct { int id; int status; long elapsed_s; int rating; } rr_boat;
        typedef struct { int place; long corrected_cs; } rr_result;

    `status` is `RR_FINISHED`, `RR_DNF` (did not finish) or `RR_DSQ` (disqualified). `rating` is the boat's handicap factor in
    thousandths (1000 is neutral, 940 a slower boat that gets a shorter corrected time).

    `int rr_score(const rr_boat *boats, size_t n, long limit_s, rr_result *out, size_t *bad)` fills `out[i]` for `boats[i]`:

    * **Corrected time** of a finisher, in centiseconds: `elapsed_s * rating / 10`, rounded to the nearest integer with halves
      rounding **up** (use integer arithmetic). `corrected_cs` is 0 for boats that did not finish.
    * **Time limit**: when `limit_s > 0`, a boat with `status == RR_FINISHED` and `elapsed_s > limit_s` is scored exactly as
      if it were `RR_DNF` (a boat that finishes exactly at the limit is fine). `limit_s <= 0` means there is no limit.
    * **Places** use competition ranking: a finisher's place is 1 plus the number of finishers with a *strictly smaller*
      corrected time (so two boats tied for first both get 1, and the next boat gets 3). A DNF boat's place is the
      number of finishers plus 1; every DNF boat gets that same place. A DSQ boat's place is `n + 1`, where `n` is the number
      of boats in the call.
    * **Validation** happens first, for the boats whose `status` is `RR_FINISHED` (even those that will be scored as
      DNF because of the limit): `elapsed_s <= 0` is `RR_E_TIME`, a `rating` outside `500..2000` is `RR_E_RATING`; an unknown
      `status` value (for any boat) is `RR_E_STATUS`. The first offending boat, in input order, decides; its index is stored in
      `*bad` (when `bad` is not NULL) and nothing is written to `out`. Per boat the status is checked before the time, and the
      time before the rating. A DNF or DSQ boat's `elapsed_s` and `rating` are ignored.
    * Returns 0 on success.

    `void rr_order(const rr_boat *boats, const rr_result *res, size_t n, size_t *order)` writes the indices `0..n-1` sorted by
    place ascending, then by `id` ascending, then by input index ascending.

    ## Series scoring

    A series is a list of one place per race (a boat's place in each race). Lower totals are better.

    * `size_t rr_discards_for(size_t races)`: how many worst results a series may drop: `races / 4`, but never more than 3.
    * `long rr_series_points(const int *places, size_t races, size_t discards)`: the sum of the places after dropping the
      `discards` largest ones. At least one race always counts: `discards` is capped at `races - 1`. 0 races give 0. More than
      `RR_MAX_RACES` (32) races give -1.
    * `int rr_series_compare(const int *a, const int *b, size_t races, size_t discards)`: -1 when series `a` is better than `b`, 1
      when `b` is better, 0 when they are tied. First compare `rr_series_points`; the lower total wins. A tie is broken by
      *countback*: sort **all** places of each series (discarded ones included) in ascending order and compare them element
      by element; the series with the smaller place at the first difference wins. Series longer than `RR_MAX_RACES` compare as 0.
''')

F2 = dd(r'''
    #ifndef REGATTARANK_H
    #define REGATTARANK_H

    #include <stddef.h>

    #define RR_MAX_RACES 32

    enum { RR_FINISHED = 0, RR_DNF = 1, RR_DSQ = 2 };
    enum { RR_OK = 0, RR_E_TIME = 1, RR_E_RATING = 2, RR_E_STATUS = 3 };

    typedef struct {
        int id;
        int status;
        long elapsed_s;
        int rating;
    } rr_boat;

    typedef struct {
        int place;
        long corrected_cs;
    } rr_result;

    int rr_score(const rr_boat *boats, size_t n, long limit_s, rr_result *out, size_t *bad);
    void rr_order(const rr_boat *boats, const rr_result *res, size_t n, size_t *order);

    size_t rr_discards_for(size_t races);
    long rr_series_points(const int *places, size_t races, size_t discards);
    int rr_series_compare(const int *a, const int *b, size_t races, size_t discards);

    #endif
''')

F3 = dd(r'''
    #include "regattarank.h"

    static int validate(const rr_boat *boats, size_t n, size_t *bad) {
        size_t i;
        for (i = 0; i < n; i++) {
            int code = RR_OK;
            if (boats[i].status < RR_FINISHED || boats[i].status > RR_DSQ) {
                code = RR_E_STATUS;
            } else if (boats[i].status == RR_FINISHED) {
                if (boats[i].elapsed_s <= 0) code = RR_E_TIME;
                else if (boats[i].rating < 500 || boats[i].rating > 2000) code = RR_E_RATING;
            }
            if (code != RR_OK) {
                if (bad) *bad = i;
                return code;
            }
        }
        return RR_OK;
    }

    int rr_score(const rr_boat *boats, size_t n, long limit_s, rr_result *out, size_t *bad) {
        size_t i, j, finishers = 0;
        int code = validate(boats, n, bad);
        if (code != RR_OK) return code;
        /* a finisher always has a positive corrected time (at least 1 * 500 / 10) */
        for (i = 0; i < n; i++) {
            int finished = boats[i].status == RR_FINISHED && !(limit_s > 0 && boats[i].elapsed_s > limit_s);
            out[i].corrected_cs = finished ? (boats[i].elapsed_s * boats[i].rating + 5) / 10 : 0;
            if (finished) finishers++;
        }
        for (i = 0; i < n; i++) {
            if (out[i].corrected_cs > 0) {
                int ahead = 0;
                for (j = 0; j < n; j++) {
                    if (out[j].corrected_cs > 0 && out[j].corrected_cs < out[i].corrected_cs) ahead++;
                }
                out[i].place = 1 + ahead;
            } else {
                out[i].place = boats[i].status == RR_DSQ ? (int)n + 1 : (int)finishers + 1;
            }
        }
        return RR_OK;
    }

    static int before(const rr_boat *boats, const rr_result *res, size_t a, size_t b) {
        if (res[a].place != res[b].place) return res[a].place < res[b].place;
        if (boats[a].id != boats[b].id) return boats[a].id < boats[b].id;
        return a < b;
    }

    void rr_order(const rr_boat *boats, const rr_result *res, size_t n, size_t *order) {
        size_t i, j;
        for (i = 0; i < n; i++) {
            order[i] = i;
            for (j = i; j > 0 && before(boats, res, order[j], order[j - 1]); j--) {
                size_t t = order[j];
                order[j] = order[j - 1];
                order[j - 1] = t;
            }
        }
    }

    size_t rr_discards_for(size_t races) {
        size_t d = races / 4;
        return d > 3 ? 3 : d;
    }

    static void sorted_copy(const int *src, size_t n, int *dst) {
        size_t i, j;
        for (i = 0; i < n; i++) {
            int v = src[i];
            for (j = i; j > 0 && dst[j - 1] > v; j--) dst[j] = dst[j - 1];
            dst[j] = v;
        }
    }

    long rr_series_points(const int *places, size_t races, size_t discards) {
        int s[RR_MAX_RACES];
        long total = 0;
        size_t i;
        if (races == 0) return 0;
        if (races > RR_MAX_RACES) return -1;
        if (discards > races - 1) discards = races - 1;
        sorted_copy(places, races, s);
        for (i = 0; i < races - discards; i++) total += s[i];
        return total;
    }

    int rr_series_compare(const int *a, const int *b, size_t races, size_t discards) {
        int sa[RR_MAX_RACES], sb[RR_MAX_RACES];
        long pa, pb;
        size_t i;
        if (races > RR_MAX_RACES) return 0;
        pa = rr_series_points(a, races, discards);
        pb = rr_series_points(b, races, discards);
        if (pa != pb) return pa < pb ? -1 : 1;
        sorted_copy(a, races, sa);
        sorted_copy(b, races, sb);
        for (i = 0; i < races; i++) {
            if (sa[i] != sb[i]) return sa[i] < sb[i] ? -1 : 1;
        }
        return 0;
    }
''')

V4 = dd(r'''
    #include "harness.h"
    #include "regattarank.h"

    int main(void) {
        rr_boat boats[3] = {{1, RR_FINISHED, 3600, 1000}, {2, RR_FINISHED, 3700, 960}, {3, RR_DNF, 0, 0}};
        rr_result res[3];
        int a[4] = {1, 2, 3, 4};
        h_init();

        CHECK_INT(rr_score(boats, 3, 0, res, NULL), RR_OK);
        CHECK_INT(res[0].corrected_cs, 360000);
        CHECK_INT(res[0].place, 2);
        CHECK_INT(res[1].place, 1);
        CHECK_INT(res[2].place, 3);
        CHECK_INT(rr_series_points(a, 4, 1), 6);
        return h_report();
    }
''')

H5 = dd(r'''
    #include <stdio.h>
    #include <string.h>

    #include "harness.h"
    #include "regattarank.h"

    typedef struct {
        size_t n;
        long limit;
        rr_boat boats[10];
        int code;
        int bad;
        int is_err;
        int place[10];
        long cs[10];
        size_t order[10];
    } race_case;

    typedef struct {
        int a[32], b[32];
        size_t races, discards;
        long pa, pb;
        int cmp;
    } series_case;

    static const race_case RACES[] = {
        {3, 0, {{1, 0, 3600, 1000}, {2, 0, 3700, 960}, {3, 1, 0, 0}}, 0, 0, 0, {2, 1, 3}, {360000, 355200, 0}, {1, 0, 2}},
        {4, 0, {{10, 0, 3600, 1000}, {11, 0, 3600, 1000}, {12, 0, 3600, 1000}, {13, 0, 3601, 1000}}, 0, 0, 0, {1, 1, 1, 4}, {360000, 360000, 360000, 360100}, {0, 1, 2, 3}},
        {5, 0, {{5, 0, 3000, 1000}, {4, 0, 3000, 1000}, {3, 0, 3500, 1000}, {2, 0, 3500, 1000}, {1, 0, 3500, 1000}}, 0, 0, 0, {1, 1, 3, 3, 3}, {300000, 300000, 350000, 350000, 350000}, {1, 0, 4, 3, 2}},
        {4, 0, {{1, 0, 100, 505}, {2, 0, 100, 500}, {3, 0, 1, 1}, {4, 0, 7, 999}}, 2, 2, 1, {0}, {0}, {0}},
        {4, 0, {{1, 0, 100, 505}, {2, 0, 100, 500}, {3, 0, 99, 2000}, {4, 0, 7, 999}}, 0, 0, 0, {3, 2, 4, 1}, {5050, 5000, 19800, 699}, {3, 1, 0, 2}},
        {1, 0, {{1, 0, 0, 1000}}, 1, 0, 1, {0}, {0}, {0}},
        {1, 0, {{1, 0, -5, 1000}}, 1, 0, 1, {0}, {0}, {0}},
        {1, 0, {{1, 0, 5, 499}}, 2, 0, 1, {0}, {0}, {0}},
        {1, 0, {{1, 0, 5, 2001}}, 2, 0, 1, {0}, {0}, {0}},
        {1, 0, {{1, 0, 5, 2000}}, 0, 0, 0, {1}, {1000}, {0}},
        {1, 0, {{1, 0, 5, 500}}, 0, 0, 0, {1}, {250}, {0}},
        {2, 0, {{1, 0, 5, 500}, {2, 0, 0, 3000}}, 1, 1, 1, {0}, {0}, {0}},
        {2, 0, {{1, 0, 5, 3000}, {2, 0, 0, 1000}}, 2, 0, 1, {0}, {0}, {0}},
        {1, 0, {{1, 7, 5, 1000}}, 3, 0, 1, {0}, {0}, {0}},
        {1, 0, {{1, -1, 5, 1000}}, 3, 0, 1, {0}, {0}, {0}},
        {1, 0, {{1, 3, 5, 1000}}, 3, 0, 1, {0}, {0}, {0}},
        {3, 0, {{1, 1, 0, 0}, {2, 2, -5, 9999}, {3, 0, 10, 1000}}, 0, 0, 0, {2, 4, 1}, {0, 0, 1000}, {2, 0, 1}},
        {6, 0, {{1, 0, 3600, 1000}, {2, 0, 3601, 1000}, {3, 0, 3599, 1000}, {4, 2, 0, 0}, {5, 1, 0, 0}, {6, 2, 0, 0}}, 0, 0, 0, {2, 3, 1, 7, 4, 7}, {360000, 360100, 359900, 0, 0, 0}, {2, 0, 1, 4, 3, 5}},
        {6, 3600, {{1, 0, 3600, 1000}, {2, 0, 3601, 1000}, {3, 0, 3599, 1000}, {4, 2, 0, 0}, {5, 1, 0, 0}, {6, 2, 0, 0}}, 0, 0, 0, {2, 3, 1, 7, 3, 7}, {360000, 0, 359900, 0, 0, 0}, {2, 0, 1, 4, 3, 5}},
        {3, 3599, {{1, 0, 3600, 1000}, {2, 0, 3601, 1000}, {3, 0, 3599, 1000}}, 0, 0, 0, {2, 2, 1}, {0, 0, 359900}, {2, 0, 1}},
        {3, 3598, {{1, 0, 3600, 1000}, {2, 0, 3601, 1000}, {3, 0, 3599, 1000}}, 0, 0, 0, {1, 1, 1}, {0, 0, 0}, {0, 1, 2}},
        {3, -1, {{1, 0, 3600, 1000}, {2, 0, 3601, 1000}, {3, 0, 3599, 1000}}, 0, 0, 0, {2, 3, 1}, {360000, 360100, 359900}, {2, 0, 1}},
        {3, 1, {{1, 0, 3600, 1000}, {2, 0, 3601, 1000}, {3, 0, 3599, 1000}}, 0, 0, 0, {1, 1, 1}, {0, 0, 0}, {0, 1, 2}},
        {3, 4, {{1, 0, 5, 1000}, {2, 0, 6, 1000}, {3, 0, 0, 1000}}, 1, 2, 1, {0}, {0}, {0}},
        {3, 4, {{1, 0, 5, 1000}, {2, 0, 6, 1000}, {3, 0, 7, 100}}, 2, 2, 1, {0}, {0}, {0}},
        {1, 0, {{1, 0, 1, 1000}}, 0, 0, 0, {1}, {100}, {0}},
        {4, 0, {{1, 0, 1, 995}, {2, 0, 1, 994}, {3, 0, 3, 1000}, {4, 0, 1, 1005}}, 0, 0, 0, {2, 1, 4, 3}, {100, 99, 300, 101}, {1, 0, 3, 2}},
        {3, 0, {{7, 1, 0, 0}, {3, 1, 0, 0}, {9, 2, 0, 0}}, 0, 0, 0, {1, 1, 4}, {0, 0, 0}, {1, 0, 2}},
        {4, 0, {{7, 0, 10, 1000}, {3, 1, 0, 0}, {9, 2, 0, 0}, {2, 0, 10, 1000}}, 0, 0, 0, {1, 3, 5, 1}, {1000, 0, 0, 1000}, {3, 0, 1, 2}},
        {1, 0, {{1, 0, 2147, 2000}}, 0, 0, 0, {1}, {429400}, {0}},
        {2, 0, {{1, 0, 1000000, 2000}, {2, 0, 999999, 2000}}, 0, 0, 0, {2, 1}, {200000000, 199999800}, {1, 0}},
        {5, 0, {{4, 0, 50, 1000}, {3, 0, 50, 1000}, {2, 0, 50, 1000}, {1, 0, 50, 1000}, {0, 0, 50, 1000}}, 0, 0, 0, {1, 1, 1, 1, 1}, {5000, 5000, 5000, 5000, 5000}, {4, 3, 2, 1, 0}},
        {5, 0, {{6, 1, 0, 0}, {2, 0, 3001, 1040}, {4, 0, 3600, 960}, {5, 0, 3002, 950}, {2, 0, 3002, 1000}}, 0, 0, 0, {5, 3, 4, 1, 2}, {0, 312104, 345600, 285190, 300200}, {3, 4, 1, 2, 0}},
        {3, 3800, {{2, 1, 0, 0}, {1, 2, 0, 0}, {3, 0, 3002, 1000}}, 0, 0, 0, {2, 4, 1}, {0, 0, 300200}, {2, 0, 1}},
        {1, 3800, {{3, 0, 4000, 940}}, 0, 0, 0, {1}, {0}, {0}},
        {8, 0, {{1, 1, 0, 0}, {5, 0, 4000, 1000}, {4, 1, 0, 0}, {4, 0, 3600, 960}, {5, 0, 3650, 1000}, {1, 1, 0, 0}, {3, 0, 4000, 1050}, {3, 2, 0, 0}}, 0, 0, 0, {5, 3, 5, 1, 2, 5, 4, 9}, {0, 400000, 0, 345600, 365000, 0, 420000, 0}, {3, 4, 1, 6, 0, 5, 2, 7}},
        {2, 3600, {{6, 0, 3650, 950}, {6, 0, 4001, 960}}, 0, 0, 0, {1, 1}, {0, 0}, {0, 1}},
        {6, 4000, {{6, 1, 0, 0}, {6, 0, 4000, 950}, {4, 0, 4001, 950}, {4, 0, 4001, 950}, {4, 2, 0, 0}, {4, 1, 0, 0}}, 0, 0, 0, {2, 1, 2, 2, 7, 2}, {0, 380000, 0, 0, 0, 0}, {1, 2, 3, 5, 0, 4}},
        {3, 3800, {{3, 0, 3002, 1171}, {1, 0, 3650, 1050}, {5, 1, 0, 0}}, 0, 0, 0, {1, 2, 3}, {351534, 383250, 0}, {0, 1, 2}},
        {8, 0, {{5, 0, 3650, 950}, {4, 1, 0, 0}, {6, 0, 4000, 940}, {3, 0, 4000, 938}, {2, 2, 0, 0}, {2, 1, 0, 0}, {6, 0, 4001, 940}, {5, 2, 0, 0}}, 0, 0, 0, {1, 5, 3, 2, 9, 5, 4, 9}, {346750, 0, 376000, 375200, 0, 0, 376094, 0}, {0, 3, 2, 6, 5, 1, 4, 7}},
        {4, 3800, {{2, 1, 0, 0}, {4, 0, 3001, 950}, {4, 0, 4001, 1050}, {1, 0, 3600, 1050}}, 0, 0, 0, {3, 1, 3, 2}, {0, 285095, 0, 378000}, {1, 3, 0, 2}},
        {7, 4000, {{1, 2, 0, 0}, {5, 0, 3001, 1050}, {5, 0, 3002, 1010}, {5, 0, 3513, 950}, {3, 0, 3600, 1000}, {3, 1, 0, 0}, {4, 0, 3002, 1010}}, 0, 0, 0, {8, 3, 1, 4, 5, 6, 1}, {0, 315105, 303202, 333735, 360000, 0, 303202}, {6, 2, 1, 3, 4, 5, 0}},
        {4, 0, {{5, 0, 4001, 950}, {1, 0, 3232, 1010}, {4, 0, 3259, 950}, {1, 0, 4703, 940}}, 0, 0, 0, {3, 2, 1, 4}, {380095, 326432, 309605, 442082}, {2, 1, 0, 3}},
        {7, 0, {{1, 0, 3650, 974}, {4, 0, 3002, 940}, {3, 0, 3001, 950}, {6, 0, 4000, 940}, {1, 0, 4000, 950}, {1, 0, 4266, 960}, {4, 0, 3751, 1047}}, 0, 0, 0, {3, 1, 2, 4, 5, 7, 6}, {355510, 282188, 285095, 376000, 380000, 409536, 392730}, {1, 2, 0, 3, 4, 6, 5}},
        {5, 4000, {{5, 0, 3650, 1010}, {4, 0, 3650, 950}, {4, 1, 0, 0}, {1, 0, 3001, 940}, {1, 1, 0, 0}}, 0, 0, 0, {3, 2, 4, 1, 4}, {368650, 346750, 0, 282094, 0}, {3, 1, 0, 4, 2}},
        {8, 0, {{6, 0, 3600, 1000}, {5, 2, 0, 0}, {1, 0, 3001, 960}, {1, 0, 4001, 940}, {1, 0, 4001, 950}, {6, 0, 3288, 1050}, {5, 0, 3002, 950}, {3, 0, 3650, 960}}, 0, 0, 0, {5, 9, 2, 6, 7, 3, 1, 4}, {360000, 0, 288096, 376094, 380095, 345240, 285190, 350400}, {6, 2, 5, 7, 0, 3, 4, 1}},
        {9, 3600, {{4, 0, 3002, 1050}, {1, 1, 0, 0}, {2, 0, 3001, 913}, {5, 0, 3894, 1000}, {4, 0, 4001, 950}, {2, 1, 0, 0}, {3, 0, 4001, 960}, {2, 0, 4000, 1010}, {3, 1, 0, 0}}, 0, 0, 0, {2, 3, 1, 3, 3, 3, 3, 3, 3}, {315210, 0, 273991, 0, 0, 0, 0, 0, 0}, {2, 0, 1, 5, 7, 6, 8, 4, 3}},
        {1, 0, {{1, 0, 3600, 1010}}, 0, 0, 0, {1}, {363600}, {0}},
        {1, 3800, {{4, 0, 3600, 870}}, 0, 0, 0, {1}, {313200}, {0}},
        {1, 0, {{4, 0, 4001, 1015}}, 0, 0, 0, {1}, {406102}, {0}},
        {4, 0, {{4, 0, 3001, 1010}, {3, 0, 3001, 950}, {3, 1, 0, 0}, {4, 0, 3000, 1194}}, 0, 0, 0, {2, 1, 4, 3}, {303101, 285095, 0, 358200}, {1, 0, 3, 2}},
        {2, 0, {{6, 1, 0, 0}, {6, 2, 0, 0}}, 0, 0, 0, {1, 3}, {0, 0}, {0, 1}},
    };

    static const series_case SERIES[] = {
        {{1, 2, 3, 4}, {2, 2, 2, 2}, 4, 1, 6, 6, -1},
        {{1, 5, 5, 5}, {2, 2, 2, 2}, 4, 0, 16, 8, 1},
        {{1, 5, 5, 5}, {2, 2, 2, 2}, 4, 1, 11, 6, 1},
        {{3, 1, 2}, {1, 1, 4}, 3, 0, 6, 6, 1},
        {{1, 1, 4}, {3, 1, 2}, 3, 0, 6, 6, -1},
        {{1, 1, 4}, {1, 1, 4}, 3, 0, 6, 6, 0},
        {{2, 2}, {2, 2}, 2, 1, 2, 2, 0},
        {{5}, {3}, 1, 0, 5, 3, 1},
        {{5}, {3}, 1, 9, 5, 3, 1},
        {{4, 1, 3, 2}, {1, 2, 3, 4}, 4, 2, 3, 3, 0},
        {{1, 2, 3, 4}, {4, 3, 2, 1}, 4, 3, 1, 1, 0},
        {{1, 4, 4, 1}, {2, 2, 3, 3}, 4, 0, 10, 10, -1},
        {{1, 4, 4, 1}, {2, 2, 3, 3}, 4, 1, 6, 7, -1},
        {{1, 4, 4, 1}, {2, 2, 3, 3}, 4, 2, 2, 4, -1},
        {{1, 4, 4, 1}, {2, 2, 3, 3}, 4, 3, 1, 2, -1},
        {{1, 4, 4, 1}, {2, 2, 3, 3}, 4, 4, 1, 2, -1},
        {{7, 7, 7}, {7, 7, 7}, 3, 1, 14, 14, 0},
        {{1, 10, 3, 3, 3}, {2, 2, 2, 10, 10}, 5, 1, 10, 16, -1},
        {{1, 10, 3, 3, 3}, {2, 2, 2, 10, 10}, 5, 2, 7, 6, 1},
        {{4, 6, 3, 6, 3, 2, 4, 3, 3, 1}, {6, 6, 4, 2, 2, 2, 6, 2, 1, 6}, 10, 2, 23, 25, -1},
        {{4}, {4}, 1, 1, 4, 4, 0},
        {{1}, {5}, 1, 4, 1, 5, -1},
        {{3, 1, 6, 1, 2, 4, 1, 4, 1, 6}, {1, 3, 4, 6, 1, 1, 4, 2, 1, 6}, 10, 4, 9, 9, 0},
        {{5, 1, 6}, {5, 1, 6}, 3, 4, 1, 1, 0},
        {{2, 6, 1, 3, 6, 4, 2, 5, 1, 2, 3}, {4, 1, 3, 4, 3, 2, 2, 5, 1, 4, 2}, 11, 3, 18, 18, 1},
        {{6, 2, 3, 1, 4, 6, 2, 1, 6, 2}, {3, 3, 1, 1, 4, 3, 4, 5, 1, 3}, 10, 1, 27, 23, 1},
        {{1, 4, 2, 6, 6, 1, 6, 1, 6, 4}, {1, 6, 2, 1, 4, 6, 6, 1, 6, 4}, 10, 4, 13, 13, 0},
        {{2}, {2}, 1, 2, 2, 2, 0},
        {{1, 2, 5, 5, 2, 6}, {1, 3, 5, 5, 2, 6}, 6, 3, 5, 6, -1},
        {{4, 1, 3, 3, 4, 2, 4}, {5, 4, 2, 4, 1, 6, 2}, 7, 3, 9, 9, 1},
        {{1, 1, 2, 4, 6, 1, 2, 1, 1, 5}, {1, 4, 5, 1, 2, 1, 2, 6, 1, 1}, 10, 2, 13, 13, 0},
        {{2, 2, 4}, {2, 2, 4}, 3, 1, 4, 4, 0},
        {{4, 6, 4, 5, 5, 1}, {2, 4, 6, 1, 1, 5}, 6, 4, 5, 2, 1},
        {{4, 1, 3}, {4, 1, 3}, 3, 3, 1, 1, 0},
        {{5, 6, 5, 6, 1, 5, 2, 4}, {5, 4, 5, 6, 5, 1, 6, 2}, 8, 1, 28, 28, 0},
        {{1, 1}, {6, 3}, 2, 4, 1, 3, -1},
        {{5, 2, 4, 5, 1, 1, 2, 3, 5, 4}, {4, 1, 6, 4, 4, 2, 6, 5, 2, 6}, 10, 3, 17, 22, -1},
        {{1, 6, 5, 6, 6, 3}, {2, 1, 2, 3, 3, 3}, 6, 0, 27, 14, 1},
        {{1, 6, 4}, {1, 6, 4}, 3, 3, 1, 1, 0},
        {{2, 4, 4, 5, 5, 2, 3}, {2, 5, 5, 4, 2, 4, 3}, 7, 2, 15, 15, 0},
        {{1, 1, 4, 2, 5, 1, 3, 2, 4, 6, 4, 2}, {1, 2, 2, 4, 2, 1, 4, 1, 5, 6, 4, 3}, 12, 0, 35, 35, 0},
        {{2, 3, 3, 2}, {3, 3, 2, 2}, 4, 2, 4, 4, 0},
        {{6, 1, 4}, {4, 1, 6}, 3, 0, 11, 11, 0},
        {{3, 6, 2, 3, 4, 2, 3, 4}, {6, 6, 1, 5, 1, 3, 4, 3}, 8, 0, 27, 29, -1},
        {{1, 8, 6, 4, 2, 9, 7, 5, 3, 1, 8, 6, 4, 2, 9, 7, 5, 3, 1, 8, 6, 4, 2, 9, 7, 5, 3, 1, 8, 6, 4, 2}, {1, 6, 2, 7, 3, 8, 4, 9, 5, 1, 6, 2, 7, 3, 8, 4, 9, 5, 1, 6, 2, 7, 3, 8, 4, 9, 5, 1, 6, 2, 7, 3}, 32, 3, 129, 127, 1},
    };

    static void test_races(void) {
        size_t i, k;
        for (i = 0; i < sizeof RACES / sizeof RACES[0]; i++) {
            const race_case *c = &RACES[i];
            rr_result res[10];
            size_t bad = 999, order[10];
            char ctx[48];
            int rc;
            snprintf(ctx, sizeof ctx, "race %d (n=%d, limit=%ld)", (int)i, (int)c->n, c->limit);
            for (k = 0; k < 10; k++) {
                res[k].place = -99;
                res[k].corrected_cs = -99;
            }
            rc = rr_score(c->boats, c->n, c->limit, res, &bad);
            CHECK_INT_CTX(ctx, rc, c->code);
            if (c->is_err) {
                CHECK_INT_CTX(ctx, bad, c->bad);
                CHECK_INT_CTX(ctx, res[0].place, -99);
                CHECK_INT_CTX(ctx, res[0].corrected_cs, -99);
                /* bad == NULL is allowed */
                CHECK_INT_CTX(ctx, rr_score(c->boats, c->n, c->limit, res, NULL), c->code);
                continue;
            }
            for (k = 0; k < c->n; k++) {
                char kctx[80];
                snprintf(kctx, sizeof kctx, "%s boat %d", ctx, (int)k);
                CHECK_INT_CTX(kctx, res[k].place, c->place[k]);
                CHECK_INT_CTX(kctx, res[k].corrected_cs, c->cs[k]);
            }
            rr_order(c->boats, res, c->n, order);
            for (k = 0; k < c->n; k++) {
                char kctx[80];
                snprintf(kctx, sizeof kctx, "%s order %d", ctx, (int)k);
                CHECK_INT_CTX(kctx, order[k], c->order[k]);
            }
        }
    }

    static void test_discards(void) {
        static const size_t want[] = {0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3, 3, 3, 3};
        size_t i;
        for (i = 0; i < sizeof want / sizeof want[0]; i++) {
            char ctx[32];
            snprintf(ctx, sizeof ctx, "races=%d", (int)i);
            CHECK_INT_CTX(ctx, rr_discards_for(i), want[i]);
        }
        CHECK_INT(rr_discards_for(100), 3);
    }

    static void test_series(void) {
        size_t i;
        int big[33], other[33];
        for (i = 0; i < sizeof SERIES / sizeof SERIES[0]; i++) {
            const series_case *c = &SERIES[i];
            char ctx[64];
            snprintf(ctx, sizeof ctx, "series %d (races=%d, discards=%d)", (int)i, (int)c->races, (int)c->discards);
            CHECK_INT_CTX(ctx, rr_series_points(c->a, c->races, c->discards), c->pa);
            CHECK_INT_CTX(ctx, rr_series_points(c->b, c->races, c->discards), c->pb);
            CHECK_INT_CTX(ctx, rr_series_compare(c->a, c->b, c->races, c->discards), c->cmp);
            CHECK_INT_CTX(ctx, rr_series_compare(c->b, c->a, c->races, c->discards), -c->cmp);
        }
        for (i = 0; i < 33; i++) {
            big[i] = 1;
            other[i] = 2;
        }
        CHECK_INT(rr_series_points(big, 32, 0), 32);
        CHECK_INT(rr_series_points(big, 33, 0), -1);
        CHECK_INT(rr_series_points(big, 33, 3), -1);
        CHECK_INT(rr_series_compare(big, other, 32, 0), -1);
        CHECK_INT(rr_series_compare(big, other, 33, 0), 0);
        CHECK_INT(rr_series_points(big, 0, 0), 0);
        CHECK_INT(rr_series_points(NULL, 0, 5), 0);
        CHECK_INT(rr_series_compare(big, other, 0, 0), 0);
    }

    static void test_input_untouched(void) {
        int a[5] = {5, 1, 4, 2, 3};
        int b[5] = {3, 3, 3, 3, 3};
        rr_series_points(a, 5, 1);
        rr_series_compare(a, b, 5, 1);
        CHECK_INT(a[0], 5);
        CHECK_INT(a[1], 1);
        CHECK_INT(a[2], 4);
        CHECK_INT(a[3], 2);
        CHECK_INT(a[4], 3);
        CHECK_INT(rr_series_points(a, 5, 1), 10);
        CHECK_INT(rr_series_points(a, 5, 2), 6);
        CHECK_INT(rr_series_points(a, 5, 4), 1);
        CHECK_INT(rr_series_points(a, 5, 5), 1);
        CHECK_INT(rr_series_points(a, 5, 99), 1);
    }

    int main(void) {
        h_init();
        test_races();
        test_discards();
        test_series();
        test_input_untouched();
        return h_report();
    }
''')

LIB = Lib(
    name="regattarank", lang="c", title="the regatta scoring library",
    blurb="The sailing club's race-office software scores handicap races and season series with this library.",
    files={"README.md": README1, "include/regattarank.h": F2, "src/regattarank.c": F3},
    visible_tests={"tests/test_main.c": V4, "tests/harness.h": _lang3.C_HARNESS},
    hidden_tests={"tests/test_main.c": H5},
    mutate=["src/regattarank.c"], difficulty=2, tags=["ranking", "scoring", "ties"],
    verify=_lang3.C_VERIFY,
)

_lang3.add(LIB, n=8)
