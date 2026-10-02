"""Security family: harder C memory-safety tasks (data structures and parsers with several interacting flaws), run under AddressSanitizer and UBSan."""
from fx import dd, family

from . import _sec, sec_c
from ._sec import patched

task = sec_c.task
SC = []

# ---------------------------------------------------------------------------------------------------------------------------------
RING_H = dd(r'''
    #ifndef RING_H
    #define RING_H
    #include <stddef.h>
    #include <stdint.h>

    typedef struct {
        uint8_t *buf;
        size_t cap;     /* capacity in bytes */
        size_t head;    /* index of the oldest unread byte */
        size_t used;    /* number of unread bytes */
    } Ring;

    /* Creates a ring buffer of cap bytes. Returns 0, or -1 for cap == 0 or when the allocation fails. */
    int ring_init(Ring *r, size_t cap);
    /* Appends up to n bytes of data and returns how many were stored: min(n, free space). Unread bytes are never overwritten. */
    size_t ring_write(Ring *r, const uint8_t *data, size_t n);
    /* Removes up to n bytes, oldest first, into out and returns how many were copied: min(n, used). */
    size_t ring_read(Ring *r, uint8_t *out, size_t n);
    /* Copies up to n bytes, starting `offset` bytes after the oldest unread byte, into out without removing them. Returns how many were copied (0 when offset >= used; never more than used - offset). */
    size_t ring_peek(const Ring *r, size_t offset, uint8_t *out, size_t n);
    void ring_free(Ring *r);

    #endif
''')
RING_C = dd(r'''
    #include "ring.h"
    #include <stdlib.h>
    #include <string.h>

    int ring_init(Ring *r, size_t cap) {
        if (cap == 0)
            return -1;
        r->buf = malloc(cap);
        if (r->buf == NULL)
            return -1;
        r->cap = cap;
        r->head = 0;
        r->used = 0;
        return 0;
    }

    size_t ring_write(Ring *r, const uint8_t *data, size_t n) {
        size_t tail = (r->head + r->used) % r->cap;
        size_t first = r->cap - tail;
        if (n > first) {
            memcpy(r->buf + tail, data, first);
            memcpy(r->buf, data + first, n - first);
        } else {
            memcpy(r->buf + tail, data, n);
        }
        r->used += n;
        return n;
    }

    size_t ring_read(Ring *r, uint8_t *out, size_t n) {
        if (n > r->used)
            n = r->used;
        size_t first = r->cap - r->head;
        if (n > first) {
            memcpy(out, r->buf + r->head, first);
            memcpy(out + first, r->buf, n - first);
        } else {
            memcpy(out, r->buf + r->head, n);
        }
        r->head = (r->head + n) % r->cap;
        r->used -= n;
        return n;
    }

    size_t ring_peek(const Ring *r, size_t offset, uint8_t *out, size_t n) {
        size_t start = (r->head + offset) % r->cap;
        size_t first = r->cap - start;
        if (n > first) {
            memcpy(out, r->buf + start, first);
            memcpy(out + first, r->buf, n - first);
        } else {
            memcpy(out, r->buf + start, n);
        }
        return n;
    }

    void ring_free(Ring *r) {
        free(r->buf);
        r->buf = NULL;
        r->cap = r->head = r->used = 0;
    }
''')
SC.append(task("ring-buffer", 4, "the serial-port driver", "ring_write", "CWE-787",
               "`ring_write` never checks the free space: writing more than fits overwrites unread data (and, with a chunk longer than the whole buffer, runs past the heap block), and `ring_peek` happily copies bytes that were never written and computes `head + offset` without looking at how much data there is.",
               {"include/ring.h": RING_H}, {"src/ring.c": RING_C},
               "`ring_write`, `ring_read` and `ring_peek` behave exactly as the header comments say (FIFO order across the wrap-around, partial writes when the buffer is nearly full, peeks that stop at the end of the data). The tests compare the implementation with a simple queue model over thousands of random operations and run under AddressSanitizer.",
               {"src/ring.c": patched(RING_C, (
                   '''    size_t tail = (r->head + r->used) % r->cap;
    size_t first = r->cap - tail;
    if (n > first) {
        memcpy(r->buf + tail, data, first);
        memcpy(r->buf, data + first, n - first);
    } else {
        memcpy(r->buf + tail, data, n);
    }
    r->used += n;
    return n;
''', '''    size_t room = r->cap - r->used;
    if (n > room)
        n = room;
    if (n == 0)
        return 0;
    size_t tail = (r->head + r->used) % r->cap;
    size_t first = r->cap - tail;
    if (n > first) {
        memcpy(r->buf + tail, data, first);
        memcpy(r->buf, data + first, n - first);
    } else {
        memcpy(r->buf + tail, data, n);
    }
    r->used += n;
    return n;
'''), (
                   '''    size_t start = (r->head + offset) % r->cap;
    size_t first = r->cap - start;
''', '''    if (offset >= r->used)
        return 0;
    if (n > r->used - offset)
        n = r->used - offset;
    if (n == 0)
        return 0;
    size_t start = (r->head + offset) % r->cap;
    size_t first = r->cap - start;
'''), (
                   '''size_t ring_read(Ring *r, uint8_t *out, size_t n) {
    if (n > r->used)
        n = r->used;
''', '''size_t ring_read(Ring *r, uint8_t *out, size_t n) {
    if (n > r->used)
        n = r->used;
    if (n == 0)
        return 0;
'''))},
               r'''
    #include "ring.h"

    static uint32_t seed = 12345;
    static uint32_t rnd(void) {
        seed = seed * 1103515245u + 12345u;
        return (seed >> 8) & 0xFFFFFFu;
    }

    static void model_run(size_t cap, int ops) {
        Ring r;
        CHECK(ring_init(&r, cap) == 0);
        uint8_t *model = malloc(cap + 1);
        size_t mlen = 0;
        uint8_t counter = 0;
        for (int op = 0; op < ops; op++) {
            switch (rnd() % 3) {
            case 0: {
                size_t n = rnd() % (cap + 6);
                uint8_t *data = malloc(n ? n : 1);
                for (size_t i = 0; i < n; i++)
                    data[i] = counter++;
                size_t room = cap - mlen;
                size_t want = n < room ? n : room;
                size_t got = ring_write(&r, data, n);
                CHECK(got == want);
                memcpy(model + mlen, data, want);
                mlen += want;
                free(data);
                break;
            }
            case 1: {
                size_t n = rnd() % (cap + 6);
                uint8_t *out = malloc(n ? n : 1);
                size_t want = n < mlen ? n : mlen;
                size_t got = ring_read(&r, out, n);
                CHECK(got == want);
                CHECK(memcmp(out, model, want) == 0);
                memmove(model, model + want, mlen - want);
                mlen -= want;
                free(out);
                break;
            }
            default: {
                size_t offset = rnd() % (cap + 4);
                size_t n = rnd() % (cap + 6);
                uint8_t *out = malloc(n ? n : 1);
                size_t want = offset >= mlen ? 0 : (n < mlen - offset ? n : mlen - offset);
                size_t got = ring_peek(&r, offset, out, n);
                CHECK(got == want);
                if (want)
                    CHECK(memcmp(out, model + offset, want) == 0);
                free(out);
                break;
            }
            }
            CHECK(r.used == mlen);
        }
        free(model);
        ring_free(&r);
    }

    int main(void) {
        Ring r;
        CHECK(ring_init(&r, 0) == -1);
        CHECK(ring_init(&r, 4) == 0);
        uint8_t abcdef[] = "abcdef", out[8];
        CHECK(ring_write(&r, abcdef, 6) == 4);
        CHECK(memcmp(r.buf, "abcd", 4) == 0);
        CHECK(ring_write(&r, abcdef, 1) == 0);
        CHECK(ring_read(&r, out, 3) == 3 && memcmp(out, "abc", 3) == 0);
        CHECK(ring_write(&r, abcdef, 5) == 3);
        CHECK(ring_read(&r, out, SIZE_MAX) == 4 && memcmp(out, "dabc", 4) == 0);
        CHECK(ring_read(&r, out, 1) == 0);
        ring_write(&r, abcdef, 3);
        CHECK(ring_peek(&r, SIZE_MAX, out, 2) == 0);
        CHECK(ring_peek(&r, SIZE_MAX - 1, out, SIZE_MAX) == 0);
        CHECK(ring_peek(&r, 3, out, 5) == 0);
        CHECK(ring_peek(&r, 1, out, SIZE_MAX) == 2 && memcmp(out, "bc", 2) == 0);
        CHECK(ring_peek(&r, 0, out, 0) == 0);
        ring_free(&r);
        size_t caps[] = {1, 2, 7, 8, 64, 100};
        for (size_t i = 0; i < sizeof caps / sizeof *caps; i++)
            model_run(caps[i], 4000);
        return failures ? 1 : 0;
    }
'''))

TLV_H = dd(r'''
    #ifndef TLV_H
    #define TLV_H
    #include <stddef.h>
    #include <stdint.h>

    /* TLV records: 1 byte type, 2 bytes length (big endian), then `length` bytes of value. A record of type TLV_CONTAINER holds a sequence of TLV records as its value. */
    #define TLV_CONTAINER 0xFF
    #define TLV_MAX_DEPTH 16

    typedef struct {
        uint8_t type;
        const uint8_t *value;   /* points into the buffer */
        uint16_t length;
    } Tlv;

    /* Reads the record at *pos of buf (buflen bytes) into *out and advances *pos past it. Returns 1 for a record, 0 when *pos == buflen (clean end) and -1 for malformed data:
       *pos > buflen, fewer than 3 bytes left for the header, or a length larger than the bytes that remain. Nothing outside buf is ever read. */
    int tlv_next(const uint8_t *buf, size_t buflen, size_t *pos, Tlv *out);

    /* Number of records in buf, counting the records inside containers (recursively) as well as the containers themselves. Returns -1 when anything is malformed
       (also inside containers) or when containers are nested deeper than TLV_MAX_DEPTH levels (a container inside 16 containers is the first one that is refused). */
    long tlv_count(const uint8_t *buf, size_t buflen);

    #endif
''')
TLV_C = dd(r'''
    #include "tlv.h"

    int tlv_next(const uint8_t *buf, size_t buflen, size_t *pos, Tlv *out) {
        size_t p = *pos;
        if (p == buflen)
            return 0;
        unsigned length = (unsigned)((buf[p + 1] << 8) | buf[p + 2]);
        if (p + 3 + length > buflen)
            return -1;
        out->type = buf[p];
        out->length = (uint16_t)length;
        out->value = buf + p + 3;
        *pos = p + 3 + length;
        return 1;
    }

    static long count_records(const uint8_t *buf, size_t n) {
        size_t pos = 0;
        long total = 0;
        Tlv t;
        while (tlv_next(buf, n, &pos, &t) == 1) {
            total++;
            if (t.type == TLV_CONTAINER)
                total += count_records(t.value, t.length);
        }
        return total;
    }

    long tlv_count(const uint8_t *buf, size_t buflen) {
        return count_records(buf, buflen);
    }
''')
SC.append(task("tlv-nesting", 4, "the device configuration parser", "tlv_next", "CWE-125",
               "`tlv_next` reads the two length bytes before checking that they exist, compares `pos + 3 + length` instead of what is left, and `tlv_count` recurses into containers without a depth limit and ignores errors in the inner records, so a short or crafted buffer reads out of bounds and a hostile one can nest deeper than the stack allows.",
               {"include/tlv.h": TLV_H}, {"src/tlv.c": TLV_C},
               "`tlv_next` and `tlv_count` follow the header comments: header and length are validated against the remaining bytes before anything is read, malformed data anywhere (also in nested containers) gives -1, and nesting beyond `TLV_MAX_DEPTH` containers gives -1 without recursing further. Valid input counts as before.",
               {"src/tlv.c": dd(r'''
                   #include "tlv.h"

                   int tlv_next(const uint8_t *buf, size_t buflen, size_t *pos, Tlv *out) {
                       size_t p = *pos;
                       if (p > buflen)
                           return -1;
                       if (p == buflen)
                           return 0;
                       if (buflen - p < 3)
                           return -1;
                       size_t length = ((size_t)buf[p + 1] << 8) | buf[p + 2];
                       if (length > buflen - p - 3)
                           return -1;
                       out->type = buf[p];
                       out->length = (uint16_t)length;
                       out->value = buf + p + 3;
                       *pos = p + 3 + length;
                       return 1;
                   }

                   static long count_records(const uint8_t *buf, size_t n, int depth) {
                       size_t pos = 0;
                       long total = 0;
                       Tlv t;
                       int rc;
                       while ((rc = tlv_next(buf, n, &pos, &t)) == 1) {
                           total++;
                           if (t.type == TLV_CONTAINER) {
                               if (depth >= TLV_MAX_DEPTH)
                                   return -1;
                               long inner = count_records(t.value, t.length, depth + 1);
                               if (inner < 0)
                                   return -1;
                               total += inner;
                           }
                       }
                       return rc < 0 ? -1 : total;
                   }

                   long tlv_count(const uint8_t *buf, size_t buflen) {
                       return count_records(buf, buflen, 0);
                   }
               ''')},
               r'''
    #include "tlv.h"

    /* appends a record to buf at *n */
    static void put(uint8_t *buf, size_t *n, uint8_t type, const uint8_t *value, size_t len) {
        buf[(*n)++] = type;
        buf[(*n)++] = (uint8_t)(len >> 8);
        buf[(*n)++] = (uint8_t)len;
        if (len) memcpy(buf + *n, value, len);
        *n += len;
    }

    static long count_heap(const uint8_t *msg, size_t n) {
        uint8_t *b = heap_bytes(msg, n);
        long c = tlv_count(b, n);
        free(b);
        return c;
    }

    /* `levels` containers inside each other, the innermost one empty */
    static size_t nested(uint8_t *out, int levels) {
        size_t n = 0;
        if (levels == 0)
            return 0;
        uint8_t inner[256];
        size_t in = nested(inner, levels - 1);
        put(out, &n, TLV_CONTAINER, inner, in);
        return n;
    }

    int main(void) {
        uint8_t msg[128];
        size_t n = 0;
        put(msg, &n, 1, (const uint8_t *)"ab", 2);
        uint8_t inner[64];
        size_t in = 0;
        put(inner, &in, 2, NULL, 0);
        put(inner, &in, 3, (const uint8_t *)"x", 1);
        put(msg, &n, TLV_CONTAINER, inner, in);
        put(msg, &n, 4, NULL, 0);
        CHECK(count_heap(msg, n) == 5);
        CHECK(count_heap(msg, 0) == 0);
        uint8_t *buf = heap_bytes(msg, n);
        size_t pos = 0;
        Tlv t;
        CHECK(tlv_next(buf, n, &pos, &t) == 1 && t.type == 1 && t.length == 2 && memcmp(t.value, "ab", 2) == 0 && pos == 5);
        CHECK(tlv_next(buf, n, &pos, &t) == 1 && t.type == TLV_CONTAINER && t.length == in);
        CHECK(tlv_next(buf, n, &pos, &t) == 1 && t.type == 4 && t.length == 0 && pos == n);
        CHECK(tlv_next(buf, n, &pos, &t) == 0);
        pos = n + 1;
        CHECK(tlv_next(buf, n, &pos, &t) == -1);
        free(buf);
        /* every truncation of a valid buffer: records read so far are fine, nothing is read out of bounds */
        for (size_t cut = 0; cut < n; cut++) {
            long c = count_heap(msg, cut);
            CHECK(c == -1 || cut == 0 || cut == 5 || cut == 5 + 3 + in);
        }
        /* length fields that point past the end, also inside a container */
        const uint8_t too_long[] = {1, 0x00, 0x05, 'a', 'b'};
        CHECK(count_heap(too_long, sizeof too_long) == -1);
        const uint8_t huge[] = {1, 0xFF, 0xFF, 'a'};
        CHECK(count_heap(huge, sizeof huge) == -1);
        const uint8_t bad_inner[] = {TLV_CONTAINER, 0x00, 0x05, 1, 0x00, 0x09, 'a', 'b'};
        CHECK(count_heap(bad_inner, sizeof bad_inner) == -1);
        const uint8_t header_only[] = {7};
        CHECK(count_heap(header_only, 1) == -1);
        CHECK(count_heap(header_only, 0) == 0);
        const uint8_t two_bytes[] = {7, 0};
        CHECK(count_heap(two_bytes, 2) == -1);
        /* nesting depth */
        for (int levels = 1; levels <= 20; levels++) {
            uint8_t deep[256];
            size_t dn = nested(deep, levels);
            long c = count_heap(deep, dn);
            if (levels <= TLV_MAX_DEPTH)
                CHECK(c == levels);
            else
                CHECK(c == -1);
        }
        /* a wide record count and a deep chain built from a long run of tiny containers */
        uint8_t wide[3 * 500];
        size_t wn = 0;
        for (int i = 0; i < 500; i++)
            put(wide, &wn, (uint8_t)(i % 200), NULL, 0);
        CHECK(count_heap(wide, wn) == 500);
        return failures ? 1 : 0;
    }
'''))

UTF8_H = dd(r'''
    #ifndef UTF8_H
    #define UTF8_H
    #include <stddef.h>
    #include <stdint.h>

    /* Strict UTF-8 decoder (RFC 3629). Decodes s[0..n-1] into the code points out[0..cap-1] and returns how many there are.
       Returns -1 when the input is invalid - a stray continuation byte, a truncated sequence, an overlong encoding (C0, C1, E0 80..9F, F0 80..8F), a surrogate (U+D800..U+DFFF),
       a value above U+10FFFF (F4 90.., F5..FF) - or when the result does not fit into cap code points. Never reads outside s[0..n-1] and never writes outside out[0..cap-1]. */
    long utf8_decode(const uint8_t *s, size_t n, uint32_t *out, size_t cap);

    #endif
''')
UTF8_C = dd(r'''
    #include "utf8.h"

    long utf8_decode(const uint8_t *s, size_t n, uint32_t *out, size_t cap) {
        size_t i = 0, count = 0;
        (void)cap;
        while (i < n) {
            uint8_t b = s[i];
            if (b < 0x80) {
                out[count++] = b;
                i += 1;
            } else if ((b & 0xE0) == 0xC0) {
                out[count++] = ((b & 0x1F) << 6) | (s[i + 1] & 0x3F);
                i += 2;
            } else if ((b & 0xF0) == 0xE0) {
                out[count++] = ((b & 0x0F) << 12) | ((s[i + 1] & 0x3F) << 6) | (s[i + 2] & 0x3F);
                i += 3;
            } else if ((b & 0xF8) == 0xF0) {
                out[count++] = ((b & 0x07) << 18) | ((s[i + 1] & 0x3F) << 12) | ((s[i + 2] & 0x3F) << 6) | (s[i + 3] & 0x3F);
                i += 4;
            } else {
                return -1;
            }
        }
        return (long)count;
    }
''')
SC.append(task("utf8-decoder", 4, "the text import filter", "utf8_decode", "CWE-176",
               "`utf8_decode` trusts the lead byte: it reads continuation bytes past the end of a truncated sequence, never checks that they are continuation bytes, accepts overlong encodings (`C0 80` for NUL, a classic filter bypass), surrogates and values above U+10FFFF, ignores `cap` and writes every code point it finds.",
               {"include/utf8.h": UTF8_H}, {"src/utf8.c": UTF8_C},
               "`utf8_decode` is a strict RFC 3629 decoder as the header says: invalid or truncated input and results that do not fit into `cap` give -1 without any out-of-bounds read or write; valid input (including the boundary code points U+007F, U+0080, U+07FF, U+0800, U+FFFF, U+10000, U+10FFFF) decodes exactly.",
               {"src/utf8.c": dd(r'''
                   #include "utf8.h"

                   long utf8_decode(const uint8_t *s, size_t n, uint32_t *out, size_t cap) {
                       size_t i = 0, count = 0;
                       while (i < n) {
                           uint8_t b = s[i];
                           uint32_t cp;
                           size_t len;
                           if (b < 0x80) {
                               cp = b;
                               len = 1;
                           } else if (b >= 0xC2 && b <= 0xDF) {
                               cp = b & 0x1Fu;
                               len = 2;
                           } else if (b >= 0xE0 && b <= 0xEF) {
                               cp = b & 0x0Fu;
                               len = 3;
                           } else if (b >= 0xF0 && b <= 0xF4) {
                               cp = b & 0x07u;
                               len = 4;
                           } else {
                               return -1;
                           }
                           if (n - i < len)
                               return -1;
                           for (size_t k = 1; k < len; k++) {
                               if ((s[i + k] & 0xC0) != 0x80)
                                   return -1;
                               cp = (cp << 6) | (s[i + k] & 0x3Fu);
                           }
                           if ((len == 3 && cp < 0x800) || (len == 4 && (cp < 0x10000 || cp > 0x10FFFF)) || (cp >= 0xD800 && cp <= 0xDFFF))
                               return -1;
                           if (count >= cap)
                               return -1;
                           out[count++] = cp;
                           i += len;
                       }
                       return (long)count;
                   }
               ''')},
               r'''
    #include "utf8.h"

    static long decode(const uint8_t *msg, size_t n, size_t cap, uint32_t *want, size_t nwant) {
        uint8_t *s = heap_bytes(msg, n);
        uint32_t *out = malloc((cap ? cap : 1) * sizeof(uint32_t));
        long rc = utf8_decode(s, n, out, cap);
        if (want) {
            CHECK(rc == (long)nwant);
            for (size_t i = 0; i < nwant && rc == (long)nwant; i++)
                CHECK(out[i] == want[i]);
        } else {
            CHECK(rc == -1);
        }
        free(s);
        free(out);
        return rc;
    }

    int main(void) {
        const uint8_t ok[] = {'A', 0x7F, 0xC2, 0x80, 0xDF, 0xBF, 0xE0, 0xA0, 0x80, 0xED, 0x9F, 0xBF, 0xEE, 0x80, 0x80, 0xEF, 0xBF, 0xBF, 0xF0, 0x90, 0x80, 0x80, 0xF4, 0x8F, 0xBF, 0xBF};
        uint32_t want[] = {0x41, 0x7F, 0x80, 0x7FF, 0x800, 0xD7FF, 0xE000, 0xFFFF, 0x10000, 0x10FFFF};
        CHECK(decode(ok, sizeof ok, 10, want, 10) == 10);
        CHECK(decode(ok, sizeof ok, 11, want, 10) == 10);
        CHECK(decode(ok, sizeof ok, 9, NULL, 0) == -1);
        CHECK(decode(ok, sizeof ok, 0, NULL, 0) == -1);
        CHECK(decode(ok, 0, 0, want, 0) == 0);
        const uint8_t euro[] = {0xE2, 0x82, 0xAC, 0x20, 0xC3, 0xA9};
        uint32_t euro_want[] = {0x20AC, 0x20, 0xE9};
        CHECK(decode(euro, sizeof euro, 3, euro_want, 3) == 3);
        const char *bad[] = {"\x80", "\xBF", "\xC0\x80", "\xC1\xBF", "\xC2", "\xC2\x20", "\xE0\x80\x80", "\xE0\x9F\xBF", "\xE0\xA0", "\xE1\x80", "\xE1\x80\x20", "\xED\xA0\x80", "\xED\xBF\xBF",
                             "\xF0\x80\x80\x80", "\xF0\x8F\xBF\xBF", "\xF0\x90\x80", "\xF4\x90\x80\x80", "\xF5\x80\x80\x80", "\xF8\x88\x80\x80\x80", "\xFC\x84\x80\x80\x80\x80", "\xFE", "\xFF", "a\xC3", "a\xE2\x82",
                             "\xF0\x9F\x98", "\xE2\x28\xA1", "\xC3\x28", "\xF0\x28\x8C\xBC", "\x80\x80\x80", "ab\x80" "cd"};
        for (size_t i = 0; i < sizeof bad / sizeof *bad; i++)
            decode((const uint8_t *)bad[i], strlen(bad[i]), 16, NULL, 0);
        uint32_t two[] = {0xE9, 0xE9};
        const uint8_t twice[] = {0xC3, 0xA9, 0xC3, 0xA9};
        CHECK(decode(twice, sizeof twice, 2, two, 2) == 2);
        CHECK(decode(twice, sizeof twice, 1, NULL, 0) == -1);
        uint8_t *big = malloc(30000);
        for (int i = 0; i < 10000; i++) {
            big[3 * i] = 0xE2; big[3 * i + 1] = 0x82; big[3 * i + 2] = 0xAC;
        }
        uint32_t *bout = malloc(10000 * sizeof(uint32_t));
        CHECK(utf8_decode(big, 30000, bout, 10000) == 10000 && bout[9999] == 0x20AC);
        CHECK(utf8_decode(big, 30000, bout, 9999) == -1);
        free(big);
        free(bout);
        return failures ? 1 : 0;
    }
'''))

MAP_H = dd(r'''
    #ifndef STRMAP_H
    #define STRMAP_H
    #include <stddef.h>

    typedef struct {
        char *key;      /* NULL for an empty slot */
        int value;
    } Slot;

    typedef struct {
        Slot *slots;
        size_t cap;     /* number of slots, starts at 8 and doubles */
        size_t count;   /* number of keys stored */
    } StrMap;

    /* Empty map with 8 slots. Returns 0 or -1 (allocation failure). */
    int map_init(StrMap *m);
    /* Stores value under key, replacing the value of an existing key (the number of keys does not change then). The map keeps its OWN COPY of the key: the caller may free or reuse its buffer
       at once. The table grows (doubling) before it would become more than 3/4 full. Returns 0, or -1 on allocation failure or size overflow, leaving the map unchanged. */
    int map_put(StrMap *m, const char *key, int value);
    /* Looks key up: 0 and *value set when found, -1 otherwise. */
    int map_get(const StrMap *m, const char *key, int *value);
    void map_free(StrMap *m);

    #endif
''')
MAP_C = dd(r'''
    #include "strmap.h"
    #include <stdlib.h>
    #include <string.h>

    static size_t hash(const char *s) {
        size_t h = 5381;
        while (*s)
            h = h * 33 + (unsigned char)*s++;
        return h;
    }

    static void insert_raw(StrMap *m, char *key, int value) {
        size_t i = hash(key) % m->cap;
        while (m->slots[i].key)
            i = (i + 1) % m->cap;
        m->slots[i].key = key;
        m->slots[i].value = value;
        m->count++;
    }

    int map_init(StrMap *m) {
        m->cap = 8;
        m->count = 0;
        m->slots = calloc(m->cap, sizeof(Slot));
        return m->slots ? 0 : -1;
    }

    int map_put(StrMap *m, const char *key, int value) {
        if ((m->count + 1) * 4 > m->cap * 3) {
            Slot *old = m->slots;
            size_t old_cap = m->cap;
            m->cap *= 2;
            m->slots = calloc(m->cap, sizeof(Slot));
            m->count = 0;
            free(old);
            for (size_t i = 0; i < old_cap; i++)
                if (old[i].key)
                    insert_raw(m, old[i].key, old[i].value);
        }
        insert_raw(m, (char *)key, value);
        return 0;
    }

    int map_get(const StrMap *m, const char *key, int *value) {
        size_t i = hash(key) % m->cap;
        while (m->slots[i].key) {
            if (strcmp(m->slots[i].key, key) == 0) {
                *value = m->slots[i].value;
                return 0;
            }
            i = (i + 1) % m->cap;
        }
        return -1;
    }

    void map_free(StrMap *m) {
        free(m->slots);
        m->slots = NULL;
        m->cap = m->count = 0;
    }
''')
SC.append(task("string-map-growth", 4, "the symbol table", "map_put", "CWE-416",
               "`map_put` frees the old slot array and then re-inserts the entries it reads from it (use after free); it stores the caller's key pointer instead of a copy, so keys that the caller frees or reuses dangle, and it never looks for an existing key, so updating a key adds a duplicate that `map_get` never sees.",
               {"include/strmap.h": MAP_H}, {"src/strmap.c": MAP_C},
               "`StrMap` follows the header comments: keys are copied (and released by `map_free`), updates replace the value, the table doubles before exceeding 3/4 load and every entry survives the move, failures leave the map unchanged. The tests free every key buffer right after `map_put` and verify thousands of entries under AddressSanitizer.",
               {"src/strmap.c": dd(r'''
                   #include "strmap.h"
                   #include <stdint.h>
                   #include <stdlib.h>
                   #include <string.h>

                   static size_t hash(const char *s) {
                       size_t h = 5381;
                       while (*s)
                           h = h * 33 + (unsigned char)*s++;
                       return h;
                   }

                   static Slot *find(Slot *slots, size_t cap, const char *key) {
                       size_t i = hash(key) % cap;
                       while (slots[i].key && strcmp(slots[i].key, key) != 0)
                           i = (i + 1) % cap;
                       return &slots[i];
                   }

                   static int grow(StrMap *m) {
                       if (m->cap > SIZE_MAX / 2 / sizeof(Slot))
                           return -1;
                       size_t new_cap = m->cap * 2;
                       Slot *fresh = calloc(new_cap, sizeof(Slot));
                       if (fresh == NULL)
                           return -1;
                       for (size_t i = 0; i < m->cap; i++)
                           if (m->slots[i].key)
                               *find(fresh, new_cap, m->slots[i].key) = m->slots[i];
                       free(m->slots);
                       m->slots = fresh;
                       m->cap = new_cap;
                       return 0;
                   }

                   int map_init(StrMap *m) {
                       m->cap = 8;
                       m->count = 0;
                       m->slots = calloc(m->cap, sizeof(Slot));
                       return m->slots ? 0 : -1;
                   }

                   int map_put(StrMap *m, const char *key, int value) {
                       Slot *s = find(m->slots, m->cap, key);
                       if (s->key) {
                           s->value = value;
                           return 0;
                       }
                       if ((m->count + 1) * 4 > m->cap * 3) {
                           if (grow(m) != 0)
                               return -1;
                           s = find(m->slots, m->cap, key);
                       }
                       size_t n = strlen(key) + 1;
                       char *copy = malloc(n);
                       if (copy == NULL)
                           return -1;
                       memcpy(copy, key, n);
                       s->key = copy;
                       s->value = value;
                       m->count++;
                       return 0;
                   }

                   int map_get(const StrMap *m, const char *key, int *value) {
                       Slot *s = find(m->slots, m->cap, key);
                       if (!s->key)
                           return -1;
                       *value = s->value;
                       return 0;
                   }

                   void map_free(StrMap *m) {
                       for (size_t i = 0; i < m->cap; i++)
                           free(m->slots[i].key);
                       free(m->slots);
                       m->slots = NULL;
                       m->cap = m->count = 0;
                   }
               ''')},
               r'''
    #include "strmap.h"

    static void put(StrMap *m, const char *key, int value) {
        char *tmp = heap_copy(key);
        CHECK(map_put(m, tmp, value) == 0);
        memset(tmp, 'X', strlen(tmp));
        free(tmp);
    }

    int main(void) {
        StrMap m;
        CHECK(map_init(&m) == 0);
        CHECK(m.cap == 8 && m.count == 0);
        int v = -1;
        CHECK(map_get(&m, "missing", &v) == -1);
        put(&m, "alpha", 1);
        put(&m, "beta", 2);
        CHECK(map_get(&m, "alpha", &v) == 0 && v == 1);
        CHECK(map_get(&m, "beta", &v) == 0 && v == 2);
        put(&m, "alpha", 10);
        put(&m, "alpha", 11);
        CHECK(m.count == 2);
        CHECK(map_get(&m, "alpha", &v) == 0 && v == 11);
        put(&m, "", 7);
        CHECK(map_get(&m, "", &v) == 0 && v == 7 && m.count == 3);
        char key[32];
        for (int i = 0; i < 2000; i++) {
            snprintf(key, sizeof key, "key-%d", i);
            put(&m, key, i * 3);
        }
        CHECK(m.count == 2003);
        CHECK(m.cap >= 2003 * 4 / 3 && (m.count * 4 <= m.cap * 3));
        for (int i = 0; i < 2000; i++) {
            snprintf(key, sizeof key, "key-%d", i);
            CHECK(map_get(&m, key, &v) == 0 && v == i * 3);
        }
        for (int i = 0; i < 2000; i += 7) {
            snprintf(key, sizeof key, "key-%d", i);
            put(&m, key, -i);
        }
        CHECK(m.count == 2003);
        for (int i = 0; i < 2000; i++) {
            snprintf(key, sizeof key, "key-%d", i);
            CHECK(map_get(&m, key, &v) == 0 && v == (i % 7 == 0 ? -i : i * 3));
        }
        CHECK(map_get(&m, "key-2000", &v) == -1);
        CHECK(map_get(&m, "KEY-1", &v) == -1);
        CHECK(map_get(&m, "alpha", &v) == 0 && v == 11);
        map_free(&m);
        CHECK(map_init(&m) == 0);
        put(&m, "again", 5);
        CHECK(map_get(&m, "again", &v) == 0 && v == 5);
        map_free(&m);
        return failures ? 1 : 0;
    }
'''))

RPN_H = dd(r'''
    #ifndef RPN_H
    #define RPN_H

    /* Evaluates a postfix expression: numbers and the operators + - * / separated by single or repeated spaces ("3 4 + 2 *" is 14).
       A number is an optional '-' followed by digits and optionally '.' and more digits ("-5", "0.25", "12"), at most 31 characters long.
       Returns 0 and stores the result in *out, or -1 (leaving *out alone) for every error: an unknown token (letters, "1.2.3", "12abc", "+5", ".5", "5.", tabs...), a number token longer than 31 characters,
       an operator with fewer than two operands, more than 16 values on the stack at the same time, division by zero, an empty expression, and an expression that leaves anything other than exactly one value. */
    int rpn_eval(const char *expr, double *out);

    #endif
''')
RPN_C = dd(r'''
    #include "rpn.h"
    #include <stdlib.h>
    #include <string.h>

    int rpn_eval(const char *expr, double *out) {
        double stack[16];
        int sp = 0;
        char tok[32];
        const char *p = expr;
        while (*p) {
            while (*p == ' ')
                p++;
            if (!*p)
                break;
            const char *start = p;
            while (*p && *p != ' ')
                p++;
            size_t len = (size_t)(p - start);
            if (len == 1 && strchr("+-*/", start[0])) {
                double b = stack[--sp];
                double a = stack[--sp];
                double r = 0;
                switch (start[0]) {
                case '+': r = a + b; break;
                case '-': r = a - b; break;
                case '*': r = a * b; break;
                default: r = a / b; break;
                }
                stack[sp++] = r;
            } else {
                memcpy(tok, start, len);
                tok[len] = 0;
                stack[sp++] = atof(tok);
            }
        }
        *out = stack[sp - 1];
        return 0;
    }
''')
SC.append(task("rpn-evaluator", 4, "the spreadsheet formula engine", "rpn_eval", "CWE-121",
               "`rpn_eval` copies each token into a 32-byte stack buffer without a length check, pops operands without checking that there are two (reading below the stack array), pushes without checking the 16-slot limit, accepts any garbage through `atof`, divides by zero and ignores values left on the stack: user formulas corrupt the stack of the server process.",
               {"include/rpn.h": RPN_H}, {"src/rpn.c": RPN_C},
               "`rpn_eval` validates everything the header comment lists and never touches memory outside its stack arrays: every error returns -1 and leaves `*out` unchanged; valid expressions evaluate as before (left operand first for `-` and `/`).",
               {"src/rpn.c": dd(r'''
                   #include "rpn.h"
                   #include <stdlib.h>
                   #include <string.h>

                   static int valid_number(const char *s, size_t len) {
                       size_t i = 0;
                       if (i < len && s[i] == '-')
                           i++;
                       size_t digits = 0;
                       while (i < len && s[i] >= '0' && s[i] <= '9') {
                           i++;
                           digits++;
                       }
                       if (digits == 0)
                           return 0;
                       if (i == len)
                           return 1;
                       if (s[i] != '.')
                           return 0;
                       i++;
                       size_t fraction = 0;
                       while (i < len && s[i] >= '0' && s[i] <= '9') {
                           i++;
                           fraction++;
                       }
                       return fraction > 0 && i == len;
                   }

                   int rpn_eval(const char *expr, double *out) {
                       double stack[16];
                       int sp = 0;
                       const char *p = expr;
                       int tokens = 0;
                       while (*p) {
                           while (*p == ' ')
                               p++;
                           if (!*p)
                               break;
                           const char *start = p;
                           while (*p && *p != ' ')
                               p++;
                           size_t len = (size_t)(p - start);
                           tokens++;
                           if (len == 1 && strchr("+-*/", start[0])) {
                               if (sp < 2)
                                   return -1;
                               double b = stack[--sp];
                               double a = stack[--sp];
                               double r;
                               switch (start[0]) {
                               case '+': r = a + b; break;
                               case '-': r = a - b; break;
                               case '*': r = a * b; break;
                               default:
                                   if (b == 0.0)
                                       return -1;
                                   r = a / b;
                                   break;
                               }
                               stack[sp++] = r;
                           } else {
                               char tok[32];
                               if (len > 31 || !valid_number(start, len) || sp >= 16)
                                   return -1;
                               memcpy(tok, start, len);
                               tok[len] = 0;
                               stack[sp++] = strtod(tok, NULL);
                           }
                       }
                       if (tokens == 0 || sp != 1)
                           return -1;
                       *out = stack[0];
                       return 0;
                   }
               ''')},
               r'''
    #include "rpn.h"

    static void ok(const char *expr, double want) {
        char *e = heap_copy(expr);
        double out = -999;
        CHECK(rpn_eval(e, &out) == 0);
        CHECK(out == want);
        free(e);
    }

    static void bad(const char *expr) {
        char *e = heap_copy(expr);
        double out = -999;
        CHECK(rpn_eval(e, &out) == -1);
        CHECK(out == -999);
        free(e);
    }

    int main(void) {
        ok("3 4 + 2 *", 14);
        ok("5", 5);
        ok("  1   2  +  ", 3);
        ok("10 4 -", 6);
        ok("-5 3 -", -8);
        ok("1 4 /", 0.25);
        ok("0.5 0.25 +", 0.75);
        ok("2 3 4 * +", 14);
        ok("-0.5 2 *", -1);
        ok("1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 + + + + + + + + + + + + + + +", 136);
        bad("");
        bad("   ");
        bad("+");
        bad("1 +");
        bad("1 2");
        bad("1 2 3 +");
        bad("abc");
        bad("1 a +");
        bad("1.2.3");
        bad("12abc");
        bad("+5");
        bad(".5");
        bad("5.");
        bad("1\t2 +");
        bad("1 0 /");
        bad("0 0 /");
        bad("1 2 ++");
        bad("- -");
        bad("1e3");
        bad("0x10");
        bad("nan");
        bad("inf");
        bad("1 2 + +");
        bad("1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 + + + + + + + + + + + + + + + +");
        bad("1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17");
        bad("1234567890123456789012345678901234567890");
        bad("12345678901234567890123456789012");
        ok("1234567890123456789012345678901", 1234567890123456789012345678901.0);
        bad("1 2 + + + + + + + +");
        char *many = malloc(4001);
        for (int i = 0; i < 2000; i++) {
            many[2 * i] = '1';
            many[2 * i + 1] = ' ';
        }
        many[4000] = 0;
        double out = -999;
        CHECK(rpn_eval(many, &out) == -1 && out == -999);
        free(many);
        char *longtok = malloc(5001);
        memset(longtok, '9', 5000);
        longtok[5000] = 0;
        CHECK(rpn_eval(longtok, &out) == -1 && out == -999);
        free(longtok);
        return failures ? 1 : 0;
    }
'''))

ARENA_H = dd(r'''
    #ifndef ARENA_H
    #define ARENA_H
    #include <stddef.h>
    #include <stdint.h>

    typedef struct {
        uint8_t *base;
        size_t cap;
        size_t used;
    } Arena;

    /* The arena hands out pieces of the caller's buffer (cap bytes at buffer, whose address may have any alignment). */
    void arena_init(Arena *a, void *buffer, size_t cap);
    /* A piece of `size` bytes whose ADDRESS is a multiple of `align` (a power of two; anything else, and size == 0, give NULL). NULL as well when padding plus size do not fit into the
       remaining space. Pieces never overlap and never leave [base, base + cap). */
    void *arena_alloc(Arena *a, size_t size, size_t align);
    /* count * elem zeroed bytes with the given alignment; NULL when the product overflows size_t, is 0, or does not fit. */
    void *arena_array(Arena *a, size_t count, size_t elem, size_t align);
    /* A copy of the string including its NUL, 1-byte aligned; NULL when it does not fit. */
    char *arena_strdup(Arena *a, const char *s);
    /* Forgets everything handed out so far (the buffer is reused from its start). */
    void arena_reset(Arena *a);
    /* Bytes still unused at the end of the buffer (padding for alignment is not counted until it is used). */
    size_t arena_remaining(const Arena *a);

    #endif
''')
ARENA_C = dd(r'''
    #include "arena.h"
    #include <string.h>

    void arena_init(Arena *a, void *buffer, size_t cap) {
        a->base = buffer;
        a->cap = cap;
        a->used = 0;
    }

    void *arena_alloc(Arena *a, size_t size, size_t align) {
        if (size == 0 || align == 0)
            return NULL;
        size_t start = (a->used + align - 1) & ~(align - 1);
        if (start + size > a->cap)
            return NULL;
        a->used = start + size;
        return a->base + start;
    }

    void *arena_array(Arena *a, size_t count, size_t elem, size_t align) {
        size_t size = count * elem;
        void *p = arena_alloc(a, size, align);
        if (p)
            memset(p, 0, count * elem);
        return p;
    }

    char *arena_strdup(Arena *a, const char *s) {
        size_t n = strlen(s) + 1;
        char *p = arena_alloc(a, n, 1);
        if (p)
            memcpy(p, s, n);
        return p;
    }

    void arena_reset(Arena *a) {
        a->used = 0;
    }

    size_t arena_remaining(const Arena *a) {
        return a->cap - a->used;
    }
''')
SC.append(task("arena-allocator", 5, "the request-scoped memory arena", "arena_alloc", "CWE-190",
               "`arena_alloc` aligns the *offset* instead of the address (a misaligned buffer gives misaligned pointers), computes `start + size` without overflow protection (a request of `SIZE_MAX - 8` bytes wraps around and succeeds), accepts alignments that are not powers of two, and `arena_array` multiplies `count * elem` unchecked and then zeroes more memory than it allocated.",
               {"include/arena.h": ARENA_H}, {"src/arena.c": ARENA_C},
               "The arena follows the header comments exactly: addresses are aligned (whatever the buffer's own alignment), nothing is handed out beyond `base + cap`, every size computation is overflow-safe, invalid alignments and zero sizes give NULL, `arena_array` returns zeroed memory or NULL, and a failed request does not change the arena.",
               {"src/arena.c": dd(r'''
                   #include "arena.h"
                   #include <string.h>

                   void arena_init(Arena *a, void *buffer, size_t cap) {
                       a->base = buffer;
                       a->cap = cap;
                       a->used = 0;
                   }

                   void *arena_alloc(Arena *a, size_t size, size_t align) {
                       if (size == 0 || align == 0 || (align & (align - 1)) != 0)
                           return NULL;
                       size_t pad = (size_t)((align - ((uintptr_t)a->base + a->used) % align) % align);
                       if (pad > a->cap - a->used)
                           return NULL;
                       size_t start = a->used + pad;
                       if (size > a->cap - start)
                           return NULL;
                       a->used = start + size;
                       return a->base + start;
                   }

                   void *arena_array(Arena *a, size_t count, size_t elem, size_t align) {
                       if (count == 0 || elem == 0 || count > SIZE_MAX / elem)
                           return NULL;
                       size_t size = count * elem;
                       void *p = arena_alloc(a, size, align);
                       if (p)
                           memset(p, 0, size);
                       return p;
                   }

                   char *arena_strdup(Arena *a, const char *s) {
                       size_t n = strlen(s) + 1;
                       char *p = arena_alloc(a, n, 1);
                       if (p)
                           memcpy(p, s, n);
                       return p;
                   }

                   void arena_reset(Arena *a) {
                       a->used = 0;
                   }

                   size_t arena_remaining(const Arena *a) {
                       return a->cap - a->used;
                   }
               ''')},
               r'''
    #include "arena.h"

    static uint8_t *raw;

    static uint8_t *make_buffer(size_t cap, size_t skew) {
        raw = malloc(cap + skew);
        memset(raw, 0xAA, cap + skew);
        return raw + skew;
    }

    int main(void) {
        size_t cap = 512;
        for (size_t skew = 0; skew < 8; skew += 3) {
            uint8_t *base = make_buffer(cap, skew);
            Arena a;
            arena_init(&a, base, cap);
            size_t aligns[] = {1, 2, 4, 8, 16, 64};
            uint8_t *last_end = base;
            for (size_t i = 0; i < sizeof aligns / sizeof *aligns; i++) {
                uint8_t *p = arena_alloc(&a, 5 + i, aligns[i]);
                CHECK(p != NULL);
                if (p) {
                    CHECK((uintptr_t)p % aligns[i] == 0);
                    CHECK(p >= last_end && p + 5 + i <= base + cap);
                    memset(p, 0x11 * (int)(i + 1), 5 + i);
                    last_end = p + 5 + i;
                }
            }
            CHECK(arena_remaining(&a) == cap - (size_t)(last_end - base));
            char *s = arena_strdup(&a, "hello arena");
            CHECK(s && strcmp(s, "hello arena") == 0);
            uint32_t *arr = arena_array(&a, 10, sizeof(uint32_t), 4);
            CHECK(arr != NULL && (uintptr_t)arr % 4 == 0);
            if (arr)
                for (int i = 0; i < 10; i++)
                    CHECK(arr[i] == 0);
            arena_reset(&a);
            CHECK(arena_remaining(&a) == cap);
            free(raw);
        }
        uint8_t *base = make_buffer(64, 3);
        Arena a;
        arena_init(&a, base, 64);
        size_t before = arena_remaining(&a);
        CHECK(arena_alloc(&a, 0, 8) == NULL);
        CHECK(arena_alloc(&a, 8, 0) == NULL);
        CHECK(arena_alloc(&a, 8, 3) == NULL);
        CHECK(arena_alloc(&a, 8, 12) == NULL);
        CHECK(arena_alloc(&a, 65, 1) == NULL);
        CHECK(arena_alloc(&a, SIZE_MAX, 1) == NULL);
        CHECK(arena_alloc(&a, SIZE_MAX - 8, 8) == NULL);
        CHECK(arena_alloc(&a, SIZE_MAX - 70, 16) == NULL);
        CHECK(arena_alloc(&a, 1, (size_t)1 << 63) == NULL);
        CHECK(arena_alloc(&a, 8, (size_t)1 << 40) == NULL);
        CHECK(arena_array(&a, SIZE_MAX / 2 + 1, 2, 1) == NULL);
        CHECK(arena_array(&a, SIZE_MAX, SIZE_MAX, 1) == NULL);
        CHECK(arena_array(&a, 0, 4, 4) == NULL);
        CHECK(arena_array(&a, 4, 0, 4) == NULL);
        CHECK(arena_array(&a, 1000, 1000, 8) == NULL);
        CHECK(arena_remaining(&a) == before);
        CHECK(arena_alloc(&a, 64, 1) == base);
        CHECK(arena_alloc(&a, 1, 1) == NULL);
        CHECK(arena_strdup(&a, "x") == NULL);
        arena_reset(&a);
        char *tight = arena_strdup(&a, "0123456789012345678901234567890123456789012345678901234567890123");
        CHECK(tight == NULL);
        char *fits = arena_strdup(&a, "012345678901234567890123456789012345678901234567890123456789012");
        CHECK(fits != NULL && strlen(fits) == 63);
        free(raw);
        return failures ? 1 : 0;
    }
'''))

ORDER = ["ring-buffer", "tlv-nesting", "utf8-decoder", "string-map-growth", "rpn-evaluator", "arena-allocator"]
SC.sort(key=lambda s: (s["d"], ORDER.index(s["slug"])))


@family("security-c-structures", category="security", lang="c", kind="fix", n=6,
        summary="C data structures and parsers under AddressSanitizer/UBSan: ring buffer, nested TLV, strict UTF-8, hash map growth, RPN evaluator, arena allocator")
def gen_c2(rng, n):
    return list(_sec.emit(rng, SC[:n], tags=["c", "asan", "memory-safety"]))
