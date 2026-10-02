"""Overflow-checked size arithmetic and a memory layout planner (c); bugs injected into the library."""
from fx import Lib, dd

from generators.fix import _lang3

README1 = dd(r'''
    # slabplan

    Overflow-checked size arithmetic and a small planner that lays several arrays out in one memory slab. All sizes are
    `size_t`. "Overflow" always means "does not fit in a `size_t`". No function writes its `*out` result when it fails.

    ## Checked arithmetic

    * `int sp_add(size_t a, size_t b, size_t *out)`: `a + b`; returns 0, or -1 on overflow.
    * `int sp_mul(size_t a, size_t b, size_t *out)`: `a * b`; returns 0, or -1 on overflow (a zero factor never overflows).
    * `int sp_is_pow2(size_t v)`: 1 for 1, 2, 4, 8, ... and 0 otherwise (0 is not a power of two).
    * `int sp_align_up(size_t v, size_t align, size_t *out)`: the smallest multiple of `align` that is `>= v`. `align` must be a
      power of two, otherwise -1; -1 also when the result would overflow.
    * `size_t sp_ceil_div(size_t a, size_t b)`: `a / b` rounded up; `0` when `b == 0`.
    * `int sp_scale_pct(size_t value, unsigned pct, size_t *out)`: `floor(value * pct / 100)` computed exactly, without the
      intermediate product ever overflowing. `pct` may be up to 10000 (100 times the value), and above that the result is -1
      (so is a result that does not fit).
    * `size_t sp_split(size_t total, size_t parts, size_t index)`: the size of share number `index` when `total` is divided into
      `parts` shares as evenly as possible; the first `total % parts` shares are one larger. `0` when `parts == 0` or
      `index >= parts`.

    ## Layout planner

    A `sp_layout` hands out offsets for arrays inside one slab of at most `limit` bytes.

    * `void sp_begin(sp_layout *l, size_t limit)`: an empty layout.
    * `int sp_reserve(sp_layout *l, size_t count, size_t elem_size, size_t align, size_t *offset)` reserves `count * elem_size`
      bytes at the next offset that is a multiple of `align` (a power of two, at least the alignment of the array's element
      type) and stores that offset in `*offset`. It returns 0, or -1 when: `align` is not a power of two, a size computation
      overflows, or the slab would not fit within `limit` bytes. "Would fit" counts the padding that
      closes the slab: the slab's total size is the end of the last array rounded up to the **largest alignment requested so far**,
      and that rounded total must not exceed `limit` either.
      A reservation of **zero bytes** (`count == 0` or `elem_size == 0`) consumes no space and does not count as a request for its
      alignment; it still returns the aligned offset (and fails when that offset lies beyond `limit`).
    * A failed reservation makes the layout *failed*: it changes nothing else, but every later `sp_reserve` also returns -1.
    * `size_t sp_total(const sp_layout *l)`: the slab size so far: the end of the last array rounded up to the largest
      alignment requested; 0 for an empty layout and 0 for a failed one.
''')

F2 = dd(r'''
    #ifndef SLABPLAN_H
    #define SLABPLAN_H

    #include <stddef.h>
    #include <stdint.h>

    typedef struct {
        size_t used;
        size_t max_align;
        size_t limit;
        int failed;
    } sp_layout;

    int sp_add(size_t a, size_t b, size_t *out);
    int sp_mul(size_t a, size_t b, size_t *out);
    int sp_is_pow2(size_t v);
    int sp_align_up(size_t v, size_t align, size_t *out);
    size_t sp_ceil_div(size_t a, size_t b);
    int sp_scale_pct(size_t value, unsigned pct, size_t *out);
    size_t sp_split(size_t total, size_t parts, size_t index);

    void sp_begin(sp_layout *l, size_t limit);
    int sp_reserve(sp_layout *l, size_t count, size_t elem_size, size_t align, size_t *offset);
    size_t sp_total(const sp_layout *l);

    #endif
''')

F3 = dd(r'''
    #include "slabplan.h"

    int sp_add(size_t a, size_t b, size_t *out) {
        if (a > SIZE_MAX - b) return -1;
        *out = a + b;
        return 0;
    }

    int sp_mul(size_t a, size_t b, size_t *out) {
        if (a != 0 && b > SIZE_MAX / a) return -1;
        *out = a * b;
        return 0;
    }

    int sp_is_pow2(size_t v) { return v != 0 && (v & (v - 1)) == 0; }

    int sp_align_up(size_t v, size_t align, size_t *out) {
        size_t mask, sum;
        if (!sp_is_pow2(align)) return -1;
        mask = align - 1;
        if (sp_add(v, mask, &sum) != 0) return -1;
        *out = sum & ~mask;
        return 0;
    }

    size_t sp_ceil_div(size_t a, size_t b) {
        if (b == 0) return 0;
        return a / b + (a % b != 0 ? 1 : 0);
    }

    int sp_scale_pct(size_t value, unsigned pct, size_t *out) {
        size_t q = value / 100, r = value % 100, hi, lo;
        if (pct > 10000) return -1;
        if (sp_mul(q, pct, &hi) != 0) return -1;
        lo = (r * pct) / 100;
        return sp_add(hi, lo, out);
    }

    size_t sp_split(size_t total, size_t parts, size_t index) {
        if (parts == 0 || index >= parts) return 0;
        return total / parts + (index < total % parts ? 1 : 0);
    }

    void sp_begin(sp_layout *l, size_t limit) {
        l->used = 0;
        l->max_align = 1;
        l->limit = limit;
        l->failed = 0;
    }

    int sp_reserve(sp_layout *l, size_t count, size_t elem_size, size_t align, size_t *offset) {
        size_t off, bytes, end, new_max, total;
        if (l->failed) return -1;
        if (sp_align_up(l->used, align, &off) != 0) goto fail;
        if (sp_mul(count, elem_size, &bytes) != 0) goto fail;
        if (off > l->limit) goto fail;
        if (bytes == 0) {
            *offset = off;
            return 0;
        }
        if (sp_add(off, bytes, &end) != 0) goto fail;
        new_max = align > l->max_align ? align : l->max_align;
        if (sp_align_up(end, new_max, &total) != 0 || total > l->limit) goto fail;
        l->used = end;
        l->max_align = new_max;
        *offset = off;
        return 0;
    fail:
        l->failed = 1;
        return -1;
    }

    size_t sp_total(const sp_layout *l) {
        size_t t;
        if (l->failed) return 0;
        if (sp_align_up(l->used, l->max_align, &t) != 0) return 0;
        return t;
    }
''')

V4 = dd(r'''
    #include "harness.h"
    #include "slabplan.h"

    int main(void) {
        size_t v = 0;
        sp_layout l;
        h_init();

        CHECK_INT(sp_mul(6, 7, &v), 0);
        CHECK_INT(v, 42);
        CHECK_INT(sp_align_up(13, 8, &v), 0);
        CHECK_INT(v, 16);

        sp_begin(&l, 1024);
        CHECK_INT(sp_reserve(&l, 3, 4, 4, &v), 0);
        CHECK_INT(v, 0);
        return h_report();
    }
''')

H5 = dd(r'''
    #include <stdio.h>
    #include <string.h>

    #include "harness.h"
    #include "slabplan.h"

    #define MAXV SIZE_MAX

    static void test_add_mul(void) {
        size_t v = 123;
        CHECK_INT(sp_add(1, 2, &v), 0);
        CHECK_UINT(v, 3);
        CHECK_INT(sp_add(0, 0, &v), 0);
        CHECK_UINT(v, 0);
        CHECK_INT(sp_add(MAXV, 0, &v), 0);
        CHECK_UINT(v, MAXV);
        CHECK_INT(sp_add(0, MAXV, &v), 0);
        CHECK_UINT(v, MAXV);
        CHECK_INT(sp_add(MAXV - 5, 5, &v), 0);
        CHECK_UINT(v, MAXV);
        v = 77;
        CHECK_INT(sp_add(MAXV - 5, 6, &v), -1);
        CHECK_INT(sp_add(MAXV, 1, &v), -1);
        CHECK_INT(sp_add(1, MAXV, &v), -1);
        CHECK_INT(sp_add(MAXV, MAXV, &v), -1);
        CHECK_UINT(v, 77);

        CHECK_INT(sp_mul(6, 7, &v), 0);
        CHECK_UINT(v, 42);
        CHECK_INT(sp_mul(0, MAXV, &v), 0);
        CHECK_UINT(v, 0);
        CHECK_INT(sp_mul(MAXV, 0, &v), 0);
        CHECK_UINT(v, 0);
        CHECK_INT(sp_mul(1, MAXV, &v), 0);
        CHECK_UINT(v, MAXV);
        CHECK_INT(sp_mul(MAXV, 1, &v), 0);
        CHECK_UINT(v, MAXV);
        CHECK_INT(sp_mul(MAXV / 3, 3, &v), 0);
        CHECK_UINT(v, (MAXV / 3) * 3);
        v = 77;
        CHECK_INT(sp_mul(MAXV / 3 + 1, 3, &v), -1);
        CHECK_INT(sp_mul(3, MAXV / 3 + 1, &v), -1);
        CHECK_INT(sp_mul(2, MAXV, &v), -1);
        CHECK_INT(sp_mul(MAXV, MAXV, &v), -1);
        CHECK_INT(sp_mul((size_t)1 << (sizeof(size_t) * 8 - 1), 2, &v), -1);
        CHECK_UINT(v, 77);
        CHECK_INT(sp_mul((size_t)1 << (sizeof(size_t) * 8 - 2), 2, &v), 0);
        CHECK_UINT(v, (size_t)1 << (sizeof(size_t) * 8 - 1));
        CHECK_INT(sp_mul((size_t)1 << (sizeof(size_t) * 8 - 2), 4, &v), -1);
    }

    static void test_pow2(void) {
        size_t i;
        CHECK_INT(sp_is_pow2(0), 0);
        CHECK_INT(sp_is_pow2(1), 1);
        CHECK_INT(sp_is_pow2(2), 1);
        CHECK_INT(sp_is_pow2(3), 0);
        CHECK_INT(sp_is_pow2(4), 1);
        CHECK_INT(sp_is_pow2(6), 0);
        CHECK_INT(sp_is_pow2(12), 0);
        CHECK_INT(sp_is_pow2(255), 0);
        CHECK_INT(sp_is_pow2(256), 1);
        CHECK_INT(sp_is_pow2(257), 0);
        CHECK_INT(sp_is_pow2(MAXV), 0);
        CHECK_INT(sp_is_pow2((size_t)1 << (sizeof(size_t) * 8 - 1)), 1);
        for (i = 0; i < sizeof(size_t) * 8; i++) {
            CHECK_INT(sp_is_pow2((size_t)1 << i), 1);
            if (i > 1) CHECK_INT(sp_is_pow2(((size_t)1 << i) + ((size_t)1 << (i - 1))), 0);
        }
    }

    static void test_align_up(void) {
        static const struct { size_t v, align, out; } c[] = {
            {0, 1, 0}, {5, 1, 5}, {0, 8, 0}, {1, 8, 8}, {7, 8, 8}, {8, 8, 8}, {9, 8, 16}, {16, 8, 16}, {17, 16, 32},
            {100, 64, 128}, {128, 64, 128}, {129, 64, 192}, {4095, 4096, 4096}, {4096, 4096, 4096}, {4097, 4096, 8192},
            {3, 2, 4}, {4, 2, 4},
        };
        size_t i, v = 99;
        char ctx[40];
        for (i = 0; i < sizeof c / sizeof c[0]; i++) {
            snprintf(ctx, sizeof ctx, "align_up(%zu, %zu)", c[i].v, c[i].align);
            CHECK_INT_CTX(ctx, sp_align_up(c[i].v, c[i].align, &v), 0);
            CHECK_UINT(v, c[i].out);
        }
        v = 99;
        CHECK_INT(sp_align_up(5, 0, &v), -1);
        CHECK_INT(sp_align_up(5, 3, &v), -1);
        CHECK_INT(sp_align_up(5, 6, &v), -1);
        CHECK_INT(sp_align_up(0, 12, &v), -1);
        CHECK_INT(sp_align_up(5, MAXV, &v), -1);
        CHECK_UINT(v, 99);
        /* overflow only when rounding up actually crosses the top */
        CHECK_INT(sp_align_up(MAXV, 1, &v), 0);
        CHECK_UINT(v, MAXV);
        CHECK_INT(sp_align_up(MAXV - 7, 8, &v), 0);
        CHECK_UINT(v, MAXV - 7);
        CHECK_INT(sp_align_up(MAXV - 6, 8, &v), -1);
        CHECK_INT(sp_align_up(MAXV, 2, &v), -1);
        CHECK_INT(sp_align_up(MAXV, 4096, &v), -1);
        CHECK_INT(sp_align_up(0, (size_t)1 << (sizeof(size_t) * 8 - 1), &v), 0);
        CHECK_UINT(v, 0);
        CHECK_INT(sp_align_up(1, (size_t)1 << (sizeof(size_t) * 8 - 1), &v), 0);
        CHECK_UINT(v, (size_t)1 << (sizeof(size_t) * 8 - 1));
        CHECK_INT(sp_align_up(((size_t)1 << (sizeof(size_t) * 8 - 1)) + 1, (size_t)1 << (sizeof(size_t) * 8 - 1), &v), -1);
    }

    static void test_ceil_div(void) {
        CHECK_UINT(sp_ceil_div(0, 5), 0);
        CHECK_UINT(sp_ceil_div(1, 5), 1);
        CHECK_UINT(sp_ceil_div(5, 5), 1);
        CHECK_UINT(sp_ceil_div(6, 5), 2);
        CHECK_UINT(sp_ceil_div(10, 5), 2);
        CHECK_UINT(sp_ceil_div(11, 5), 3);
        CHECK_UINT(sp_ceil_div(7, 1), 7);
        CHECK_UINT(sp_ceil_div(7, 0), 0);
        CHECK_UINT(sp_ceil_div(0, 0), 0);
        CHECK_UINT(sp_ceil_div(MAXV, 1), MAXV);
        CHECK_UINT(sp_ceil_div(MAXV, 2), MAXV / 2 + 1);
        CHECK_UINT(sp_ceil_div(MAXV, MAXV), 1);
        CHECK_UINT(sp_ceil_div(MAXV - 1, MAXV), 1);
        CHECK_UINT(sp_ceil_div(3, 1000), 1);
    }

    static void test_scale_pct(void) {
        static const struct { size_t value; unsigned pct; size_t out; } c[] = {
            {0, 50, 0}, {100, 0, 0}, {100, 100, 100}, {100, 50, 50}, {1, 50, 0}, {1, 100, 1}, {3, 50, 1}, {99, 1, 0},
            {101, 1, 1}, {250, 33, 82}, {999, 99, 989}, {12345, 10000, 1234500}, {7, 10000, 700}, {199, 50, 99}, {1000, 7, 70},
            {1050, 15, 157}, {99, 100, 99}, {99, 101, 99},
        };
        size_t i, v = 55;
        char ctx[40];
        for (i = 0; i < sizeof c / sizeof c[0]; i++) {
            snprintf(ctx, sizeof ctx, "scale_pct(%zu, %u)", c[i].value, c[i].pct);
            CHECK_INT_CTX(ctx, sp_scale_pct(c[i].value, c[i].pct, &v), 0);
            CHECK_UINT(v, c[i].out);
        }
        CHECK_INT(sp_scale_pct(MAXV, 100, &v), 0);
        CHECK_UINT(v, MAXV);
        CHECK_INT(sp_scale_pct(MAXV, 50, &v), 0);
        CHECK_UINT(v, MAXV / 2);
        CHECK_INT(sp_scale_pct(MAXV, 99, &v), 0);
        CHECK_UINT(v, MAXV / 100 * 99 + (MAXV % 100) * 99 / 100);
        CHECK_INT(sp_scale_pct(MAXV, 0, &v), 0);
        CHECK_UINT(v, 0);
        v = 55;
        CHECK_INT(sp_scale_pct(MAXV, 101, &v), -1);
        CHECK_INT(sp_scale_pct(MAXV, 10000, &v), -1);
        CHECK_INT(sp_scale_pct(10, 10001, &v), -1);
        CHECK_INT(sp_scale_pct(10, 100000, &v), -1);
        CHECK_INT(sp_scale_pct(10, 4000000000u, &v), -1);
        CHECK_UINT(v, 55);
        CHECK_INT(sp_scale_pct(10, 10000, &v), 0);
        CHECK_UINT(v, 1000);
        /* the top of the range */
        CHECK_INT(sp_scale_pct(MAXV / 100 + 1, 10000, &v), -1);
        CHECK_INT(sp_scale_pct(MAXV / 10000, 10000, &v), 0);
        CHECK_UINT(v, MAXV / 10000 * 100);
    }

    static void test_split(void) {
        size_t i, sum = 0;
        CHECK_UINT(sp_split(10, 3, 0), 4);
        CHECK_UINT(sp_split(10, 3, 1), 3);
        CHECK_UINT(sp_split(10, 3, 2), 3);
        CHECK_UINT(sp_split(10, 3, 3), 0);
        CHECK_UINT(sp_split(11, 3, 0), 4);
        CHECK_UINT(sp_split(11, 3, 1), 4);
        CHECK_UINT(sp_split(11, 3, 2), 3);
        CHECK_UINT(sp_split(12, 3, 2), 4);
        CHECK_UINT(sp_split(2, 5, 0), 1);
        CHECK_UINT(sp_split(2, 5, 1), 1);
        CHECK_UINT(sp_split(2, 5, 2), 0);
        CHECK_UINT(sp_split(0, 5, 0), 0);
        CHECK_UINT(sp_split(7, 1, 0), 7);
        CHECK_UINT(sp_split(7, 1, 1), 0);
        CHECK_UINT(sp_split(7, 0, 0), 0);
        CHECK_UINT(sp_split(MAXV, 2, 0), MAXV / 2 + 1);
        CHECK_UINT(sp_split(MAXV, 2, 1), MAXV / 2);
        for (i = 0; i < 7; i++) sum += sp_split(1000, 7, i);
        CHECK_UINT(sum, 1000);
        CHECK_UINT(sp_split(1000, 7, 0), 143);
        CHECK_UINT(sp_split(1000, 7, 5), 143);
        CHECK_UINT(sp_split(1000, 7, 6), 142);
    }

    static void test_layout_basic(void) {
        sp_layout l;
        size_t off = 999;
        sp_begin(&l, 1000);
        CHECK_UINT(sp_total(&l), 0);
        CHECK_INT(sp_reserve(&l, 3, 1, 1, &off), 0);
        CHECK_UINT(off, 0);
        CHECK_UINT(sp_total(&l), 3);
        CHECK_INT(sp_reserve(&l, 2, 4, 4, &off), 0);
        CHECK_UINT(off, 4);
        CHECK_UINT(sp_total(&l), 12);
        CHECK_INT(sp_reserve(&l, 1, 8, 8, &off), 0);
        CHECK_UINT(off, 16);
        CHECK_UINT(sp_total(&l), 24);
        CHECK_INT(sp_reserve(&l, 5, 1, 1, &off), 0);
        CHECK_UINT(off, 24);
        CHECK_UINT(sp_total(&l), 32);   /* 29 rounded up to the largest alignment so far (8) */
        CHECK_INT(sp_reserve(&l, 1, 2, 2, &off), 0);
        CHECK_UINT(off, 30);
        CHECK_UINT(sp_total(&l), 32);
        CHECK_INT(sp_reserve(&l, 1, 64, 64, &off), 0);
        CHECK_UINT(off, 64);
        CHECK_UINT(sp_total(&l), 128);
    }

    static void test_layout_zero_size(void) {
        sp_layout l;
        size_t off = 0;
        sp_begin(&l, 100);
        CHECK_INT(sp_reserve(&l, 3, 1, 1, &off), 0);
        /* an empty array: aligned offset, no space, no alignment request */
        CHECK_INT(sp_reserve(&l, 0, 4, 64, &off), 0);
        CHECK_UINT(off, 64);
        CHECK_UINT(sp_total(&l), 3);
        CHECK_INT(sp_reserve(&l, 4, 0, 32, &off), 0);
        CHECK_UINT(off, 32);
        CHECK_UINT(sp_total(&l), 3);
        CHECK_INT(sp_reserve(&l, 1, 1, 1, &off), 0);
        CHECK_UINT(off, 3);
        CHECK_UINT(sp_total(&l), 4);
        /* a zero-size reservation past the limit fails */
        CHECK_INT(sp_reserve(&l, 0, 4, 128, &off), -1);
        CHECK_INT(sp_reserve(&l, 1, 1, 1, &off), -1);
        CHECK_UINT(sp_total(&l), 0);
        /* offset exactly at the limit is fine for an empty array */
        sp_begin(&l, 64);
        CHECK_INT(sp_reserve(&l, 0, 4, 64, &off), 0);
        CHECK_UINT(off, 0);
        sp_begin(&l, 64);
        CHECK_INT(sp_reserve(&l, 64, 1, 1, &off), 0);
        CHECK_INT(sp_reserve(&l, 0, 1, 64, &off), 0);
        CHECK_UINT(off, 64);
        CHECK_INT(sp_reserve(&l, 0, 1, 128, &off), -1);
    }

    static void test_layout_limits(void) {
        sp_layout l;
        size_t off = 7;
        /* exactly the limit */
        sp_begin(&l, 16);
        CHECK_INT(sp_reserve(&l, 16, 1, 1, &off), 0);
        CHECK_UINT(sp_total(&l), 16);
        CHECK_INT(sp_reserve(&l, 1, 1, 1, &off), -1);
        CHECK_UINT(sp_total(&l), 0);
        /* one over */
        sp_begin(&l, 16);
        off = 7;
        CHECK_INT(sp_reserve(&l, 17, 1, 1, &off), -1);
        CHECK_UINT(off, 7);
        /* the closing padding counts: 17 bytes aligned to 8 is 24 */
        sp_begin(&l, 23);
        CHECK_INT(sp_reserve(&l, 17, 1, 8, &off), -1);
        sp_begin(&l, 24);
        CHECK_INT(sp_reserve(&l, 17, 1, 8, &off), 0);
        CHECK_UINT(sp_total(&l), 24);
        /* padding forced by a later, larger alignment */
        sp_begin(&l, 40);
        CHECK_INT(sp_reserve(&l, 33, 1, 1, &off), 0);
        CHECK_INT(sp_reserve(&l, 1, 1, 16, &off), -1); /* the next 16-aligned offset is 48 */
        sp_begin(&l, 48);
        CHECK_INT(sp_reserve(&l, 33, 1, 1, &off), 0);
        CHECK_UINT(sp_total(&l), 33);
        CHECK_INT(sp_reserve(&l, 1, 1, 16, &off), -1);
        sp_begin(&l, 64);
        CHECK_INT(sp_reserve(&l, 33, 1, 1, &off), 0);
        CHECK_INT(sp_reserve(&l, 1, 1, 16, &off), 0);
        CHECK_UINT(off, 48);
        CHECK_UINT(sp_total(&l), 64);
        /* a limit of 0 */
        sp_begin(&l, 0);
        CHECK_INT(sp_reserve(&l, 1, 1, 1, &off), -1);
        sp_begin(&l, 0);
        CHECK_INT(sp_reserve(&l, 0, 1, 1, &off), 0);
        CHECK_UINT(off, 0);
    }

    static void test_layout_failures(void) {
        sp_layout l;
        size_t off = 5;
        sp_begin(&l, 1000);
        CHECK_INT(sp_reserve(&l, 1, 1, 0, &off), -1);
        CHECK_UINT(off, 5);
        CHECK_INT(sp_reserve(&l, 1, 1, 1, &off), -1); /* failed layouts stay failed */
        CHECK_UINT(sp_total(&l), 0);
        sp_begin(&l, 1000);
        CHECK_INT(sp_reserve(&l, 1, 1, 3, &off), -1);
        sp_begin(&l, 1000);
        CHECK_INT(sp_reserve(&l, MAXV, 2, 1, &off), -1);
        CHECK_INT(sp_reserve(&l, 1, 1, 1, &off), -1);
        sp_begin(&l, MAXV);
        CHECK_INT(sp_reserve(&l, MAXV / 2, 2, 1, &off), 0);
        CHECK_UINT(off, 0);
        CHECK_UINT(sp_total(&l), MAXV - 1);
        CHECK_INT(sp_reserve(&l, 1, 1, 1, &off), 0);
        CHECK_UINT(off, MAXV - 1);
        CHECK_UINT(sp_total(&l), MAXV);
        CHECK_INT(sp_reserve(&l, 1, 1, 1, &off), -1);
        /* rounding the total up overflows */
        sp_begin(&l, MAXV);
        CHECK_INT(sp_reserve(&l, MAXV - 2, 1, 1, &off), 0);
        CHECK_INT(sp_reserve(&l, 1, 1, 8, &off), -1);
        /* an offset computation that overflows */
        sp_begin(&l, MAXV);
        CHECK_INT(sp_reserve(&l, MAXV - 1, 1, 1, &off), 0);
        CHECK_INT(sp_reserve(&l, 1, 1, 4, &off), -1);
        /* a failed layout can be restarted */
        sp_begin(&l, 100);
        CHECK_INT(sp_reserve(&l, 1, 1, 1, &off), 0);
        CHECK_UINT(off, 0);
        CHECK_UINT(sp_total(&l), 1);
    }

    int main(void) {
        h_init();
        test_add_mul();
        test_pow2();
        test_align_up();
        test_ceil_div();
        test_scale_pct();
        test_split();
        test_layout_basic();
        test_layout_zero_size();
        test_layout_limits();
        test_layout_failures();
        return h_report();
    }
''')

LIB = Lib(
    name="slabplan", lang="c", title="the slabplan size calculator",
    blurb="The embedded runtime sizes its static memory slabs at start-up with these helpers, so a size that overflows must be refused rather than wrap around.",
    files={"README.md": README1, "include/slabplan.h": F2, "src/slabplan.c": F3},
    visible_tests={"tests/test_main.c": V4, "tests/harness.h": _lang3.C_HARNESS},
    hidden_tests={"tests/test_main.c": H5},
    mutate=["src/slabplan.c"], difficulty=1, tags=["safe-arithmetic", "alignment", "allocation"],
    verify=_lang3.C_VERIFY,
)

_lang3.add(LIB, n=8)
