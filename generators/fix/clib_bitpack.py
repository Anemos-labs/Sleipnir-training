"""Bit stream writer/reader (c): LSB-first fields of 1..32 bits, signed fields, a 6-bit-length-prefixed integer code, atomic failure; bugs injected into the library."""
from fx import Lib, dd

from generators.fix import _lang3

README1 = dd(r'''
    # bitpack

    A bit-level writer and reader for compact telemetry frames.

    ## Bit order

    Bits are numbered from 0 in the order they are written. Bit `k` of the stream lives in byte `k / 8` at bit position
    `k % 8` (position 0 is the least significant bit of the byte). A field of `width` bits is written
    **least significant bit first**: the lowest bit of the value is stream bit `k`, the next one `k + 1`, and so on. So
    writing the 3-bit value `5` (binary `101`) and then the 5-bit value `31` gives the single byte `0xFD`.
    `width` is always between 1 and 32.

    ## Writer

        typedef struct { uint8_t *buf; size_t cap; size_t bitpos; } bw_t;

    * `void bw_init(bw_t *w, uint8_t *buf, size_t cap)` starts an empty stream over a caller-owned buffer of `cap`
      bytes and **zero-fills the whole buffer**; bits that were never written read as 0.
    * `int bw_put(bw_t *w, uint32_t value, int width)` appends the field. It returns 0, or -1 (and changes nothing) when
      `width` is outside `1..32`, when `value` does not fit in `width` bits (`value >= 2^width`), or when fewer than
      `width` bits are left in the buffer.
    * `int bw_put_signed(bw_t *w, int32_t value, int width)` appends a two's-complement field. The legal range is
      `-2^(width-1) .. 2^(width-1) - 1`; outside it, or in the cases above, it returns -1 and changes nothing.
    * `int bw_put_lp(bw_t *w, uint32_t value)` appends a *length-prefixed* integer: a 6-bit count `n` of significant
      bits of `value` (`n = 0` for the value 0, otherwise the position of the highest set bit plus 1, up to 32) followed by
      exactly those `n` bits. Zero therefore costs 6 bits and `0xFFFFFFFF` costs 38. It returns -1 and changes nothing
      when the whole code does not fit.
    * `int bw_align(bw_t *w)` skips to the next byte boundary (the skipped bits stay 0); it does nothing when the stream is
      already aligned. Returns 0.
    * `size_t bw_size(const bw_t *w)` is the number of bytes the stream occupies so far (a partly used byte counts).

    ## Reader

        typedef struct { const uint8_t *buf; size_t len; size_t bitpos; } br_t;

    * `void br_init(br_t *r, const uint8_t *buf, size_t len)` starts reading `len` bytes.
    * `int br_get(br_t *r, int width, uint32_t *out)` reads a field. It returns -1 (consuming nothing, leaving `*out`
      alone) when `width` is outside `1..32` or fewer than `width` bits remain; otherwise 0.
    * `int br_get_signed(br_t *r, int width, int32_t *out)` reads a field and sign-extends it from `width` bits; same
      failure rules.
    * `int br_get_lp(br_t *r, uint32_t *out)` reads a length-prefixed integer. It returns -1 and consumes nothing when the
      6-bit count is larger than 32 or the stream ends before the count or the payload does.
    * `size_t br_remaining(const br_t *r)` is the number of unread bits.
    * `int br_align(br_t *r)` skips to the next byte boundary; returns -1 (consuming nothing) when that boundary is past
      the end of the data - which cannot happen for byte-aligned lengths, so it is 0 in practice.

    ## Helper

    `int bp_bits_for(uint32_t count)` is the number of bits needed to tell `count` different values apart (the smallest
    `b` with `2^b >= count`): `1 -> 0`, `2 -> 1`, `3 -> 2`, `4 -> 2`, `5 -> 3`, `256 -> 8`, `257 -> 9`. `count == 0` gives 0.
''')

F2 = dd(r'''
    #ifndef BITPACK_H
    #define BITPACK_H

    #include <stddef.h>
    #include <stdint.h>

    typedef struct {
        uint8_t *buf;
        size_t cap;
        size_t bitpos;
    } bw_t;

    typedef struct {
        const uint8_t *buf;
        size_t len;
        size_t bitpos;
    } br_t;

    void bw_init(bw_t *w, uint8_t *buf, size_t cap);
    int bw_put(bw_t *w, uint32_t value, int width);
    int bw_put_signed(bw_t *w, int32_t value, int width);
    int bw_put_lp(bw_t *w, uint32_t value);
    int bw_align(bw_t *w);
    size_t bw_size(const bw_t *w);

    void br_init(br_t *r, const uint8_t *buf, size_t len);
    int br_get(br_t *r, int width, uint32_t *out);
    int br_get_signed(br_t *r, int width, int32_t *out);
    int br_get_lp(br_t *r, uint32_t *out);
    size_t br_remaining(const br_t *r);
    int br_align(br_t *r);

    int bp_bits_for(uint32_t count);

    #endif
''')

F3 = dd(r'''
    #include "bitpack.h"

    #include <string.h>

    void bw_init(bw_t *w, uint8_t *buf, size_t cap) {
        w->buf = buf;
        w->cap = cap;
        w->bitpos = 0;
        memset(buf, 0, cap);
    }

    int bw_put(bw_t *w, uint32_t value, int width) {
        int left;
        if (width < 1 || width > 32) return -1;
        if (width < 32 && (value >> width) != 0) return -1;
        if (w->bitpos + (size_t)width > w->cap * 8) return -1;
        left = width;
        while (left > 0) {
            size_t byte = w->bitpos >> 3;
            int off = (int)(w->bitpos & 7);
            int take = 8 - off;
            if (take > left) take = left;
            w->buf[byte] |= (uint8_t)((value & ((1u << take) - 1)) << off);
            value >>= take;
            left -= take;
            w->bitpos += (size_t)take;
        }
        return 0;
    }

    int bw_put_signed(bw_t *w, int32_t value, int width) {
        int64_t lo, hi;
        uint32_t bits;
        if (width < 1 || width > 32) return -1;
        lo = -((int64_t)1 << (width - 1));
        hi = ((int64_t)1 << (width - 1)) - 1;
        if (value < lo || value > hi) return -1;
        bits = (uint32_t)value;
        if (width < 32) bits &= (1u << width) - 1;
        return bw_put(w, bits, width);
    }

    static int bit_length(uint32_t v) {
        int n = 0;
        while (v != 0) {
            n++;
            v >>= 1;
        }
        return n;
    }

    int bw_put_lp(bw_t *w, uint32_t value) {
        int n = bit_length(value);
        if (w->bitpos + 6 + (size_t)n > w->cap * 8) return -1;
        bw_put(w, (uint32_t)n, 6);
        if (n > 0) bw_put(w, value, n);
        return 0;
    }

    int bw_align(bw_t *w) {
        w->bitpos = (w->bitpos + 7) & ~(size_t)7;
        return 0;
    }

    size_t bw_size(const bw_t *w) { return (w->bitpos + 7) / 8; }

    void br_init(br_t *r, const uint8_t *buf, size_t len) {
        r->buf = buf;
        r->len = len;
        r->bitpos = 0;
    }

    int br_get(br_t *r, int width, uint32_t *out) {
        uint32_t v = 0;
        int got = 0;
        size_t pos;
        if (width < 1 || width > 32) return -1;
        if (r->bitpos + (size_t)width > r->len * 8) return -1;
        pos = r->bitpos;
        while (got < width) {
            size_t byte = pos >> 3;
            int off = (int)(pos & 7);
            int take = 8 - off;
            if (take > width - got) take = width - got;
            v |= (uint32_t)((r->buf[byte] >> off) & ((1u << take) - 1)) << got;
            got += take;
            pos += (size_t)take;
        }
        r->bitpos = pos;
        *out = v;
        return 0;
    }

    int br_get_signed(br_t *r, int width, int32_t *out) {
        uint32_t v;
        if (br_get(r, width, &v) != 0) return -1;
        if (width < 32 && ((v >> (width - 1)) & 1u)) v |= ~0u << width;
        *out = (int32_t)v;
        return 0;
    }

    int br_get_lp(br_t *r, uint32_t *out) {
        size_t save = r->bitpos;
        uint32_t n, v = 0;
        if (br_get(r, 6, &n) != 0) return -1;
        if (n > 32) {
            r->bitpos = save;
            return -1;
        }
        if (n > 0 && br_get(r, (int)n, &v) != 0) {
            r->bitpos = save;
            return -1;
        }
        *out = v;
        return 0;
    }

    size_t br_remaining(const br_t *r) { return r->len * 8 - r->bitpos; }

    int br_align(br_t *r) {
        size_t next = (r->bitpos + 7) & ~(size_t)7;
        if (next > r->len * 8) return -1;
        r->bitpos = next;
        return 0;
    }

    int bp_bits_for(uint32_t count) {
        int b = 0;
        while (b < 32 && ((uint64_t)1 << b) < count) b++;
        return b;
    }
''')

V4 = dd(r'''
    #include "bitpack.h"
    #include "harness.h"

    int main(void) {
        uint8_t buf[8];
        bw_t w;
        br_t r;
        uint32_t v = 0;
        h_init();

        bw_init(&w, buf, sizeof buf);
        CHECK_INT(bw_put(&w, 5, 3), 0);
        CHECK_INT(bw_put(&w, 31, 5), 0);
        CHECK_INT(bw_size(&w), 1);
        CHECK_INT(buf[0], 0xFD);

        br_init(&r, buf, 1);
        CHECK_INT(br_get(&r, 3, &v), 0);
        CHECK_UINT(v, 5);
        return h_report();
    }
''')

H5 = dd(r'''
    #include <limits.h>
    #include <stdio.h>
    #include <stdlib.h>
    #include <string.h>

    #include "bitpack.h"
    #include "harness.h"

    static const char *hex(const uint8_t *b, size_t n) {
        static char out[160];
        size_t i;
        for (i = 0; i < n && i < 70; i++) sprintf(out + 2 * i, "%02x", b[i]);
        out[2 * i] = '\0';
        return out;
    }

    #define CHECK_HEX(w, want) CHECK_STR(hex((w).buf, bw_size(&(w))), want)

    static void test_put_layout(void) {
        uint8_t b[16];
        bw_t w;
        bw_init(&w, b, sizeof b);
        CHECK_INT(bw_put(&w, 5, 3), 0);
        CHECK_INT(bw_put(&w, 31, 5), 0);
        CHECK_HEX(w, "fd");
        CHECK_INT(w.bitpos, 8);

        bw_init(&w, b, sizeof b);
        bw_put(&w, 1, 1);
        bw_put(&w, 0x3FF, 10);
        bw_put(&w, 0, 2);
        bw_put(&w, 0xABCDE, 20);
        CHECK_HEX(w, "ffc79b5701");
        CHECK_INT(w.bitpos, 33);
        CHECK_INT(bw_size(&w), 5);

        bw_init(&w, b, sizeof b);
        CHECK_INT(bw_put(&w, 0xDEADBEEFu, 32), 0);
        CHECK_HEX(w, "efbeadde");

        bw_init(&w, b, sizeof b);
        bw_put(&w, 1, 1);
        bw_put(&w, 0xDEADBEEFu, 32);
        CHECK_HEX(w, "df7d5bbd01");
        CHECK_INT(w.bitpos, 33);

        bw_init(&w, b, sizeof b);
        bw_put(&w, 0x12345, 17);
        bw_put(&w, 0x7, 3);
        bw_put(&w, 0x55, 7);
        bw_put(&w, 1, 1);
        bw_put(&w, 0xFFFFFFFFu, 32);
        bw_put(&w, 0x2a, 6);
        CHECK_HEX(w, "45235ffdffffffaf02");
        CHECK_INT(w.bitpos, 66);
    }

    static void test_init_zero_fills(void) {
        uint8_t b[6];
        bw_t w;
        memset(b, 0xAA, sizeof b);
        bw_init(&w, b, sizeof b);
        CHECK_INT(w.bitpos, 0);
        CHECK_INT(bw_size(&w), 0);
        CHECK_STR(hex(b, 6), "000000000000");
        bw_put(&w, 1, 1);
        CHECK_STR(hex(b, 6), "010000000000");
    }

    static void test_put_rejects(void) {
        uint8_t b[2];
        bw_t w;
        bw_init(&w, b, sizeof b);
        CHECK_INT(bw_put(&w, 1, 0), -1);
        CHECK_INT(bw_put(&w, 1, -3), -1);
        CHECK_INT(bw_put(&w, 1, 33), -1);
        CHECK_INT(bw_put(&w, 0, 33), -1);
        CHECK_INT(bw_put(&w, 8, 3), -1);
        CHECK_INT(bw_put(&w, 2, 1), -1);
        CHECK_INT(bw_put(&w, 0x10000, 16), -1);
        CHECK_INT(w.bitpos, 0);
        CHECK_INT(bw_put(&w, 7, 3), 0);
        CHECK_INT(bw_put(&w, 1, 1), 0);
        CHECK_INT(bw_put(&w, 0, 1), 0);
        CHECK_INT(w.bitpos, 5);
        /* 11 bits are left */
        CHECK_INT(bw_put(&w, 0x7FF, 12), -1);
        CHECK_INT(w.bitpos, 5);
        CHECK_STR(hex(b, 2), "0f00");
        CHECK_INT(bw_put(&w, 0x7FF, 11), 0);
        CHECK_INT(w.bitpos, 16);
        CHECK_STR(hex(b, 2), "efff");
        CHECK_INT(bw_put(&w, 0, 1), -1);
        CHECK_INT(bw_size(&w), 2);
        /* a 32-bit field needs 32 free bits */
        {
            uint8_t big[4];
            bw_init(&w, big, sizeof big);
            CHECK_INT(bw_put(&w, 0xFFFFFFFFu, 32), 0);
            CHECK_STR(hex(big, 4), "ffffffff");
            bw_init(&w, big, 3);
            CHECK_INT(bw_put(&w, 0xFFFFFFFFu, 32), -1);
            CHECK_INT(bw_put(&w, 0xFFFFFFu, 24), 0);
        }
        /* widths above 32 are refused even when there is room */
        {
            uint8_t roomy[16];
            bw_init(&w, roomy, sizeof roomy);
            CHECK_INT(bw_put(&w, 1, 33), -1);
            CHECK_INT(bw_put(&w, 0, 40), -1);
            CHECK_INT(bw_put(&w, 0, 64), -1);
            CHECK_INT(w.bitpos, 0);
            CHECK_INT(bw_put(&w, 0xFFFFFFFFu, 32), 0);
        }
        /* an empty buffer takes nothing */
        bw_init(&w, b, 0);
        CHECK_INT(bw_put(&w, 0, 1), -1);
        CHECK_INT(bw_size(&w), 0);
    }

    static void test_signed_put(void) {
        uint8_t b[16];
        bw_t w;
        bw_init(&w, b, sizeof b);
        bw_put_signed(&w, -3, 4);
        bw_put_signed(&w, 7, 4);
        bw_put_signed(&w, -1, 12);
        bw_put_signed(&w, -32768, 16);
        bw_put_signed(&w, 5, 3);
        CHECK_HEX(w, "7dff0f0008");
        CHECK_INT(w.bitpos, 36);

        bw_init(&w, b, sizeof b);
        CHECK_INT(bw_put_signed(&w, -8, 4), 0);
        CHECK_INT(bw_put_signed(&w, 7, 4), 0);
        CHECK_INT(bw_put_signed(&w, -9, 4), -1);
        CHECK_INT(bw_put_signed(&w, 8, 4), -1);
        CHECK_INT(w.bitpos, 8);
        CHECK_HEX(w, "78");
        CHECK_INT(bw_put_signed(&w, -1, 1), 0);
        CHECK_INT(bw_put_signed(&w, 0, 1), 0);
        CHECK_INT(bw_put_signed(&w, 1, 1), -1);
        CHECK_INT(bw_put_signed(&w, -2, 1), -1);
        CHECK_INT(w.bitpos, 10);
        CHECK_INT(bw_put_signed(&w, INT_MIN, 32), 0);
        CHECK_INT(bw_put_signed(&w, INT_MAX, 32), 0);
        CHECK_INT(w.bitpos, 74);
        CHECK_INT(bw_put_signed(&w, 1, 0), -1);
        CHECK_INT(bw_put_signed(&w, 1, 33), -1);
        CHECK_INT(bw_put_signed(&w, 1, -1), -1);
        CHECK_INT(w.bitpos, 74);
        /* no room: nothing written */
        {
            uint8_t two[2];
            bw_init(&w, two, sizeof two);
            CHECK_INT(bw_put_signed(&w, -1, 17), -1);
            CHECK_INT(bw_put_signed(&w, -1, 16), 0);
            CHECK_STR(hex(two, 2), "ffff");
            CHECK_INT(bw_put_signed(&w, 0, 1), -1);
        }
    }

    static void test_lp_put(void) {
        uint8_t b[16];
        bw_t w;
        bw_init(&w, b, sizeof b);
        CHECK_INT(bw_put_lp(&w, 0), 0);
        CHECK_INT(w.bitpos, 6);
        CHECK_INT(bw_put_lp(&w, 1), 0);
        CHECK_INT(w.bitpos, 13);
        CHECK_INT(bw_put_lp(&w, 0xFFFFFFFFu), 0);
        CHECK_INT(w.bitpos, 51);
        CHECK_INT(bw_put_lp(&w, 300), 0);
        CHECK_INT(w.bitpos, 66);
        CHECK_HEX(w, "4010fcffffff4f5802");

        /* costs: n=1 -> 7 bits, n=2 -> 8, 255 -> 14, 256 -> 15, 2^31 -> 38 */
        bw_init(&w, b, sizeof b);
        bw_put_lp(&w, 2);
        CHECK_INT(w.bitpos, 8);
        bw_init(&w, b, sizeof b);
        bw_put_lp(&w, 255);
        CHECK_INT(w.bitpos, 14);
        bw_init(&w, b, sizeof b);
        bw_put_lp(&w, 256);
        CHECK_INT(w.bitpos, 15);
        bw_init(&w, b, sizeof b);
        bw_put_lp(&w, 0x80000000u);
        CHECK_INT(w.bitpos, 38);
        bw_init(&w, b, sizeof b);
        bw_put_lp(&w, 0x7FFFFFFFu);
        CHECK_INT(w.bitpos, 37);
    }

    static void test_lp_capacity(void) {
        uint8_t b[5];
        bw_t w;
        bw_init(&w, b, sizeof b); /* 40 bits */
        CHECK_INT(bw_put_lp(&w, 0xFFFFFFFFu), 0); /* 38 */
        CHECK_INT(bw_put_lp(&w, 1), -1);          /* needs 7, 2 left */
        CHECK_INT(w.bitpos, 38);
        CHECK_INT(bw_put_lp(&w, 0), -1);          /* needs 6 */
        CHECK_INT(w.bitpos, 38);
        CHECK_STR(hex(b, 5), "e0ffffff3f");
        CHECK_INT(bw_put(&w, 3, 2), 0);
        CHECK_INT(bw_put_lp(&w, 0), -1);

        bw_init(&w, b, sizeof b);
        bw_put(&w, 0, 32);
        bw_put(&w, 0, 2);
        CHECK_INT(bw_put_lp(&w, 0), 0); /* exactly 6 left */
        CHECK_INT(w.bitpos, 40);
        bw_init(&w, b, sizeof b);
        bw_put(&w, 0, 32);
        bw_put(&w, 0, 3);
        CHECK_INT(bw_put_lp(&w, 0), -1);
        CHECK_INT(w.bitpos, 35);
        CHECK_INT(bw_put_lp(&w, 1), -1);
        /* payload does not fit although the prefix does */
        bw_init(&w, b, sizeof b);
        bw_put(&w, 0, 30);
        CHECK_INT(bw_put_lp(&w, 0x7F), -1);
        CHECK_INT(w.bitpos, 30);
        CHECK_STR(hex(b, 5), "0000000000");
        CHECK_INT(bw_put_lp(&w, 0xF), 0);
        CHECK_INT(w.bitpos, 40);
    }

    static void test_align_size(void) {
        uint8_t b[16];
        bw_t w;
        bw_init(&w, b, sizeof b);
        CHECK_INT(bw_size(&w), 0);
        CHECK_INT(bw_align(&w), 0);
        CHECK_INT(w.bitpos, 0);
        bw_put(&w, 7, 3);
        CHECK_INT(bw_size(&w), 1);
        CHECK_INT(bw_align(&w), 0);
        CHECK_INT(w.bitpos, 8);
        bw_put(&w, 1, 1);
        CHECK_INT(bw_size(&w), 2);
        bw_align(&w);
        bw_align(&w);
        CHECK_INT(w.bitpos, 16);
        CHECK_HEX(w, "0701");
        bw_put(&w, 0x3, 8);
        CHECK_INT(bw_size(&w), 3);
        bw_put(&w, 1, 7);
        CHECK_INT(w.bitpos, 31);
        bw_align(&w);
        CHECK_INT(w.bitpos, 32);
    }

    static void test_reader_basic(void) {
        static const uint8_t data[] = {0x45, 0x23, 0x5f, 0xfd, 0xff, 0xff, 0xff, 0xaf, 0x02};
        br_t r;
        uint32_t v = 99;
        br_init(&r, data, sizeof data);
        CHECK_INT(br_remaining(&r), 72);
        CHECK_INT(br_get(&r, 17, &v), 0);
        CHECK_UINT(v, 0x12345);
        CHECK_INT(br_get(&r, 3, &v), 0);
        CHECK_UINT(v, 7);
        CHECK_INT(br_get(&r, 7, &v), 0);
        CHECK_UINT(v, 0x55);
        CHECK_INT(br_get(&r, 1, &v), 0);
        CHECK_UINT(v, 1);
        CHECK_INT(br_get(&r, 32, &v), 0);
        CHECK_UINT(v, 0xFFFFFFFFu);
        CHECK_INT(br_get(&r, 6, &v), 0);
        CHECK_UINT(v, 0x2a);
        CHECK_INT(br_remaining(&r), 6);
        CHECK_INT(r.bitpos, 66);
        CHECK_INT(br_get(&r, 7, &v), -1);
        CHECK_UINT(v, 0x2a);
        CHECK_INT(br_remaining(&r), 6);
        CHECK_INT(br_get(&r, 6, &v), 0);
        CHECK_UINT(v, 0);
        CHECK_INT(br_remaining(&r), 0);
        CHECK_INT(br_get(&r, 1, &v), -1);
    }

    static void test_reader_rejects(void) {
        static const uint8_t data[] = {0xff, 0xff, 0xff, 0xff, 0xff};
        br_t r;
        uint32_t v = 7;
        br_init(&r, data, sizeof data);
        CHECK_INT(br_get(&r, 0, &v), -1);
        CHECK_INT(br_get(&r, -1, &v), -1);
        CHECK_INT(br_get(&r, 33, &v), -1);
        CHECK_INT(r.bitpos, 0);
        CHECK_UINT(v, 7);
        CHECK_INT(br_get(&r, 32, &v), 0);
        CHECK_UINT(v, 0xFFFFFFFFu);
        CHECK_INT(br_get(&r, 9, &v), -1);
        CHECK_INT(br_get(&r, 8, &v), 0);
        CHECK_UINT(v, 255);
        CHECK_INT(br_get(&r, 1, &v), -1);
        br_init(&r, data, 0);
        CHECK_INT(br_get(&r, 1, &v), -1);
        CHECK_INT(br_remaining(&r), 0);
    }

    static void test_reader_exact_buffer(void) {
        /* the last byte of an exact-size block is readable, the byte after it is never touched */
        uint8_t *p = malloc(3);
        br_t r;
        uint32_t v = 0;
        p[0] = 0x01;
        p[1] = 0x80;
        p[2] = 0x81;
        br_init(&r, p, 3);
        CHECK_INT(br_get(&r, 7, &v), 0);
        CHECK_UINT(v, 1);
        CHECK_INT(br_get(&r, 17, &v), 0);
        CHECK_UINT(v, 0x10300);
        CHECK_INT(br_get(&r, 1, &v), -1);
        br_init(&r, p, 3);
        CHECK_INT(br_get(&r, 24, &v), 0);
        CHECK_UINT(v, 0x818001);
        CHECK_INT(br_get(&r, 1, &v), -1);
        br_init(&r, p, 3);
        br_get(&r, 5, &v);
        CHECK_INT(br_get(&r, 20, &v), -1);
        CHECK_INT(br_get(&r, 19, &v), 0);
        CHECK_UINT(v, 265216);
        CHECK_INT(br_get(&r, 1, &v), -1);
        free(p);
    }

    static void test_signed_get(void) {
        static const uint8_t data[] = {0x7d, 0xff, 0x0f, 0x00, 0x08};
        br_t r;
        int32_t s = 0;
        br_init(&r, data, sizeof data);
        CHECK_INT(br_get_signed(&r, 4, &s), 0);
        CHECK_INT(s, -3);
        CHECK_INT(br_get_signed(&r, 4, &s), 0);
        CHECK_INT(s, 7);
        CHECK_INT(br_get_signed(&r, 12, &s), 0);
        CHECK_INT(s, -1);
        CHECK_INT(br_get_signed(&r, 16, &s), 0);
        CHECK_INT(s, -32768);
        CHECK_INT(br_get_signed(&r, 5, &s), -1);
        CHECK_INT(s, -32768);
        CHECK_INT(br_get_signed(&r, 4, &s), 0);
        CHECK_INT(s, 0);
        CHECK_INT(br_get_signed(&r, 1, &s), -1);
        CHECK_INT(br_get_signed(&r, 0, &s), -1);
        CHECK_INT(br_get_signed(&r, 33, &s), -1);
        {
            static const uint8_t one[] = {0x01};
            static const uint8_t half[] = {0x80, 0x7f};
            static const uint8_t full[] = {0x00, 0x00, 0x00, 0x80, 0xff, 0xff, 0xff, 0x7f};
            br_init(&r, one, 1);
            CHECK_INT(br_get_signed(&r, 1, &s), 0);
            CHECK_INT(s, -1);
            CHECK_INT(br_get_signed(&r, 1, &s), 0);
            CHECK_INT(s, 0);
            br_init(&r, half, 2);
            CHECK_INT(br_get_signed(&r, 8, &s), 0);
            CHECK_INT(s, -128);
            CHECK_INT(br_get_signed(&r, 8, &s), 0);
            CHECK_INT(s, 127);
            br_init(&r, full, 8);
            CHECK_INT(br_get_signed(&r, 32, &s), 0);
            CHECK_INT(s, INT_MIN);
            CHECK_INT(br_get_signed(&r, 32, &s), 0);
            CHECK_INT(s, INT_MAX);
            br_init(&r, full + 4, 4);
            CHECK_INT(br_get_signed(&r, 31, &s), 0);
            CHECK_INT(s, -1);
        }
    }

    static void test_lp_get(void) {
        uint8_t b[16];
        bw_t w;
        br_t r;
        uint32_t v = 123;
        uint32_t vals[] = {0, 1, 2, 255, 256, 65535, 0x7FFFFFFFu, 0x80000000u, 0xFFFFFFFFu, 300, 0};
        size_t i;
        bw_init(&w, b, sizeof b);
        for (i = 0; i < 5; i++) bw_put_lp(&w, vals[i]);
        br_init(&r, b, bw_size(&w));
        for (i = 0; i < 5; i++) {
            CHECK_INT(br_get_lp(&r, &v), 0);
            CHECK_UINT(v, vals[i]);
        }
        for (i = 5; i < sizeof vals / sizeof vals[0]; i++) {
            bw_init(&w, b, sizeof b);
            bw_put_lp(&w, vals[i]);
            br_init(&r, b, bw_size(&w));
            CHECK_INT(br_get_lp(&r, &v), 0);
            CHECK_UINT(v, vals[i]);
            CHECK(br_remaining(&r) < 8);
        }
        /* count 33 and 63 are invalid, 32 is fine */
        {
            uint8_t bad[8];
            bw_init(&w, bad, sizeof bad);
            bw_put(&w, 33, 6);
            bw_put(&w, 0, 33);
            br_init(&r, bad, sizeof bad);
            v = 5;
            CHECK_INT(br_get_lp(&r, &v), -1);
            CHECK_INT(r.bitpos, 0);
            CHECK_UINT(v, 5);
            bw_init(&w, bad, sizeof bad);
            bw_put(&w, 63, 6);
            br_init(&r, bad, sizeof bad);
            CHECK_INT(br_get_lp(&r, &v), -1);
            CHECK_INT(r.bitpos, 0);
            bw_init(&w, bad, sizeof bad);
            bw_put(&w, 32, 6);
            bw_put(&w, 0x80000001u, 32);
            br_init(&r, bad, sizeof bad);
            CHECK_INT(br_get_lp(&r, &v), 0);
            CHECK_UINT(v, 0x80000001u);
        }
        /* truncated streams consume nothing */
        {
            uint8_t t[2];
            bw_init(&w, t, sizeof t);
            bw_put(&w, 3, 3);   /* leading field */
            bw_put(&w, 9, 6);   /* count 9, but only 7 bits follow */
            br_init(&r, t, 2);
            br_get(&r, 3, &v);
            CHECK_INT(br_get_lp(&r, &v), -1);
            CHECK_INT(r.bitpos, 3);
            CHECK_INT(br_remaining(&r), 13);
            br_init(&r, t, 1);
            CHECK_INT(br_get_lp(&r, &v), -1);
            CHECK_INT(r.bitpos, 0);
            br_init(&r, t, 0);
            CHECK_INT(br_get_lp(&r, &v), -1);
            CHECK_INT(r.bitpos, 0);
        }
        /* zero needs only its 6-bit prefix */
        {
            uint8_t z[1] = {0};
            br_init(&r, z, 1);
            v = 9;
            CHECK_INT(br_get_lp(&r, &v), 0);
            CHECK_UINT(v, 0);
            CHECK_INT(r.bitpos, 6);
        }
    }

    static void test_reader_align(void) {
        static const uint8_t d[] = {1, 2, 3};
        br_t r;
        uint32_t v;
        br_init(&r, d, 3);
        CHECK_INT(br_align(&r), 0);
        CHECK_INT(r.bitpos, 0);
        br_get(&r, 1, &v);
        CHECK_INT(br_align(&r), 0);
        CHECK_INT(r.bitpos, 8);
        br_init(&r, d, 3);
        br_get(&r, 3, &v);
        CHECK_INT(br_align(&r), 0);
        CHECK_INT(r.bitpos, 8);
        CHECK_INT(br_get(&r, 8, &v), 0);
        CHECK_UINT(v, 2);
        br_get(&r, 7, &v);
        CHECK_INT(br_align(&r), 0);
        CHECK_INT(r.bitpos, 24);
        CHECK_INT(br_remaining(&r), 0);
        CHECK_INT(br_align(&r), 0);
    }

    static unsigned lcg(unsigned *s) {
        *s = *s * 1103515245u + 12345u;
        return (*s >> 8) & 0xFFFFFFu;
    }

    static void test_roundtrip(void) {
        unsigned seed = 7;
        int round;
        for (round = 0; round < 40; round++) {
            uint8_t b[256];
            bw_t w;
            br_t r;
            int widths[40], kinds[40], i, n = 5 + round % 30;
            uint32_t vals[40];
            bw_init(&w, b, sizeof b);
            for (i = 0; i < n; i++) {
                int width = 1 + (int)(lcg(&seed) % 32);
                uint32_t value = lcg(&seed) * 257u + lcg(&seed);
                kinds[i] = (int)(lcg(&seed) % 3);
                if (width < 32) value &= (1u << width) - 1;
                if (kinds[i] == 1 && width < 32) {
                    /* signed: value is a width-bit pattern */
                }
                widths[i] = width;
                vals[i] = value;
                if (kinds[i] == 0) {
                    CHECK_INT(bw_put(&w, value, width), 0);
                } else if (kinds[i] == 1) {
                    int32_t sv = (int32_t)value;
                    if (width < 32 && (value >> (width - 1)) & 1u) sv = (int32_t)(value | (~0u << width));
                    CHECK_INT(bw_put_signed(&w, sv, width), 0);
                } else {
                    CHECK_INT(bw_put_lp(&w, value), 0);
                }
            }
            br_init(&r, b, bw_size(&w));
            for (i = 0; i < n; i++) {
                uint32_t got = 0;
                int32_t sgot = 0;
                if (kinds[i] == 0) {
                    CHECK_INT(br_get(&r, widths[i], &got), 0);
                    CHECK_UINT(got, vals[i]);
                } else if (kinds[i] == 1) {
                    CHECK_INT(br_get_signed(&r, widths[i], &sgot), 0);
                    CHECK_UINT((uint32_t)sgot, widths[i] < 32 && ((vals[i] >> (widths[i] - 1)) & 1u) ? (vals[i] | (~0u << widths[i])) : vals[i]);
                } else {
                    CHECK_INT(br_get_lp(&r, &got), 0);
                    CHECK_UINT(got, vals[i]);
                }
            }
            CHECK(br_remaining(&r) < 8);
        }
    }

    static void test_bits_for(void) {
        static const struct { uint32_t n; int bits; } c[] = {
            {0, 0}, {1, 0}, {2, 1}, {3, 2}, {4, 2}, {5, 3}, {8, 3}, {9, 4}, {16, 4}, {17, 5}, {255, 8}, {256, 8}, {257, 9},
            {65536, 16}, {65537, 17}, {0x7FFFFFFFu, 31}, {0x80000000u, 31}, {0x80000001u, 32}, {0xFFFFFFFFu, 32},
        };
        size_t i;
        char ctx[24];
        for (i = 0; i < sizeof c / sizeof c[0]; i++) {
            snprintf(ctx, sizeof ctx, "count=%lu", (unsigned long)c[i].n);
            CHECK_INT_CTX(ctx, bp_bits_for(c[i].n), c[i].bits);
        }
    }

    int main(void) {
        h_init();
        test_put_layout();
        test_init_zero_fills();
        test_put_rejects();
        test_signed_put();
        test_lp_put();
        test_lp_capacity();
        test_align_size();
        test_reader_basic();
        test_reader_rejects();
        test_reader_exact_buffer();
        test_signed_get();
        test_lp_get();
        test_reader_align();
        test_roundtrip();
        test_bits_for();
        return h_report();
    }
''')

LIB = Lib(
    name="bitpack", lang="c", title="the bitpack library",
    blurb="The telemetry uplink packs sensor readings into frames bit by bit with this library, because every bit of the radio budget counts.",
    files={"README.md": README1, "include/bitpack.h": F2, "src/bitpack.c": F3},
    visible_tests={"tests/test_main.c": V4, "tests/harness.h": _lang3.C_HARNESS},
    hidden_tests={"tests/test_main.c": H5},
    mutate=["src/bitpack.c"], difficulty=3, tags=["bits", "serialization", "telemetry"],
    verify=_lang3.C_VERIFY,
)

_lang3.add(LIB, n=8)
