"""Lab sample labels (c): base-32 sequence codec with a look-alike-free alphabet and a mod-31 check symbol; bugs injected into the label library."""
from fx import Lib, dd

from generators.fix import _lang3

README1 = dd(r'''
    # samplelabel

    Label codec for a laboratory's sample-tracking system. Every tube gets a printed label of exactly 16 characters:

        NRW-2614-7M230-F
        site year+week sequence check

    | part | text | meaning |
    |---|---|---|
    | site | 3 letters `A`-`Z` | the collecting site |
    | year, week | 4 digits `YYWW` | two-digit year `00`-`99`, week `01`-`53` |
    | sequence | 5 symbols | the sample sequence number, `0 .. SL_SEQ_MAX` |
    | check | 1 symbol | check symbol over the first three parts |

    The three parts are separated by `-`; the check symbol follows the last `-`. (`SL_TEXT_LEN` is 16.)

    ## Symbols

    Sequence numbers and check symbols are written with a 32-symbol alphabet that leaves out the letters that are easily
    confused with digits (`B`, `I`, `O`, `S`):

        0123456789ACDEFGHJKLMNPQRTUVWXYZ

    Index 0 is `0`, index 10 is `A`, index 31 is `Z`. `SL_SEQ_MAX` is `32^5 - 1 = 33554431`.

    * The sequence is written big-endian with exactly 5 symbols, padded on the left with `0`.
    * When *reading* a sequence or check symbol, letters may be lower case and the look-alikes are accepted:
      `B` reads as `8`, `I` as `1`, `O` as `0`, `S` as `5`. Nothing else outside the alphabet is accepted.

    ## Check symbol

    Take the 12 characters `site + YYWW + sequence` (the sequence in its canonical, padded alphabet form, upper case).
    A digit has the value of the digit; a letter has the value `10 + (letter - 'A')` (so `A` is 10 and `Z` is 35).
    The character at position `i` (0-based) is weighted by `2*i + 1`. The check is the alphabet symbol at index
    `(sum of value*weight) mod 31`. (Index 31, `Z`, therefore never occurs as a check symbol.)

    ## API (`include/samplelabel.h`)

    * `int sl_encode_seq(unsigned long seq, char out[SL_SEQ_LEN + 1])` writes the 5 symbols and a NUL; returns 0, or -1
      (writing nothing) when `seq > SL_SEQ_MAX`.
    * `int sl_decode_seq(const char *s, size_t n, unsigned long *out)` reads exactly 5 symbols from the first `n`
      characters of `s` (which need not be NUL-terminated and must not be read beyond `n`); returns 0, or -1 when
      `n != 5` or a character is not a symbol (look-alikes and lower case are accepted). `*out` is untouched on failure.
    * `char sl_check_char(const char *body, size_t n)` is the check symbol of the `n` upper-case alphanumeric characters
      in `body`, by the rule above (`n` is 12 for a label).
    * `int sl_format(const sl_label *l, char *buf, size_t cap)` writes the label and a NUL and returns its length (16).
      It returns -1 and writes nothing when `cap < 17`, when `site` is not exactly 3 letters `A`-`Z`, when `year` is
      outside `0..99`, `week` outside `1..53` or `seq > SL_SEQ_MAX`.
    * `int sl_parse(const char *s, size_t n, sl_label *out)` reads a label from the first `n` characters of `s` (not
      necessarily NUL-terminated). Upper and lower case are both accepted. It returns, checking in this order:
      `SL_E_SHAPE` unless `n == 16` and the characters at 3, 8 and 14 are `-`; `SL_E_FIELD` when the site is not three
      letters, year/week are not digits, the week is outside `01..53`, the sequence has a character that is not a symbol
      or the check character is not a symbol; `SL_E_CHECK` when the check symbol (after look-alike reading) differs from
      the computed one; otherwise `SL_OK` with `*out` filled in (site in upper case). `*out` is untouched on error.
    * `int sl_succ(sl_label *l)` increments `l->seq` and returns 0; at `SL_SEQ_MAX` it returns -1 and changes nothing.
    * `int sl_compare(const sl_label *a, const sl_label *b)` orders labels by year, then week, then site (as a string),
      then sequence; returns -1, 0 or 1.
''')

F2 = dd(r'''
    #ifndef SAMPLELABEL_H
    #define SAMPLELABEL_H

    #include <stddef.h>

    #define SL_SEQ_LEN 5
    #define SL_SEQ_MAX 33554431UL
    #define SL_TEXT_LEN 16

    enum { SL_OK = 0, SL_E_SHAPE = 1, SL_E_FIELD = 2, SL_E_CHECK = 3 };

    typedef struct {
        char site[4];       /* three letters A-Z and a NUL */
        int year;           /* 0..99 */
        int week;           /* 1..53 */
        unsigned long seq;  /* 0..SL_SEQ_MAX */
    } sl_label;

    int sl_encode_seq(unsigned long seq, char out[SL_SEQ_LEN + 1]);
    int sl_decode_seq(const char *s, size_t n, unsigned long *out);
    char sl_check_char(const char *body, size_t n);
    int sl_format(const sl_label *l, char *buf, size_t cap);
    int sl_parse(const char *s, size_t n, sl_label *out);
    int sl_succ(sl_label *l);
    int sl_compare(const sl_label *a, const sl_label *b);

    #endif
''')

F3 = dd(r'''
    #include "samplelabel.h"

    #include <ctype.h>
    #include <stdio.h>
    #include <string.h>

    static const char ALPHABET[] = "0123456789ACDEFGHJKLMNPQRTUVWXYZ";

    /* Index of a symbol in the alphabet (after reading look-alikes and lower case), or -1. */
    static int symbol_index(int c) {
        const char *p;
        c = toupper(c);
        switch (c) {
        case 'B': c = '8'; break;
        case 'I': c = '1'; break;
        case 'O': c = '0'; break;
        case 'S': c = '5'; break;
        default: break;
        }
        p = (c != 0) ? strchr(ALPHABET, c) : NULL;
        return p ? (int)(p - ALPHABET) : -1;
    }

    int sl_encode_seq(unsigned long seq, char out[SL_SEQ_LEN + 1]) {
        int i;
        if (seq > SL_SEQ_MAX) return -1;
        for (i = SL_SEQ_LEN - 1; i >= 0; i--) {
            out[i] = ALPHABET[seq & 31];
            seq >>= 5;
        }
        out[SL_SEQ_LEN] = '\0';
        return 0;
    }

    int sl_decode_seq(const char *s, size_t n, unsigned long *out) {
        unsigned long v = 0;
        size_t i;
        if (n != SL_SEQ_LEN) return -1;
        for (i = 0; i < n; i++) {
            int d = symbol_index((unsigned char)s[i]);
            if (d < 0) return -1;
            v = (v << 5) | (unsigned long)d;
        }
        *out = v;
        return 0;
    }

    static int check_index(const char *body, size_t n) {
        unsigned long sum = 0;
        size_t i;
        for (i = 0; i < n; i++) {
            int v = isdigit((unsigned char)body[i]) ? body[i] - '0' : 10 + (body[i] - 'A');
            sum += (unsigned long)v * (2 * i + 1);
        }
        return (int)(sum % 31);
    }

    char sl_check_char(const char *body, size_t n) {
        return ALPHABET[check_index(body, n)];
    }

    int sl_format(const sl_label *l, char *buf, size_t cap) {
        char seq[SL_SEQ_LEN + 1], body[13];
        int i;
        if (cap < SL_TEXT_LEN + 1) return -1;
        if (l->year < 0 || l->year > 99 || l->week < 1 || l->week > 53) return -1;
        for (i = 0; i < 3; i++) {
            if (l->site[i] < 'A' || l->site[i] > 'Z') return -1;
        }
        if (l->site[3] != '\0') return -1;
        if (sl_encode_seq(l->seq, seq) != 0) return -1;
        snprintf(body, sizeof body, "%s%02d%02d%s", l->site, l->year, l->week, seq);
        snprintf(buf, cap, "%s-%02d%02d-%s-%c", l->site, l->year, l->week, seq, sl_check_char(body, 12));
        return SL_TEXT_LEN;
    }

    int sl_parse(const char *s, size_t n, sl_label *out) {
        char canon[SL_TEXT_LEN], seq[SL_SEQ_LEN + 1], body[13];
        sl_label l;
        unsigned long v;
        size_t i;
        int want, got;
        if (n != SL_TEXT_LEN) return SL_E_SHAPE;
        if (s[3] != '-' || s[8] != '-' || s[14] != '-') return SL_E_SHAPE;
        for (i = 0; i < n; i++) canon[i] = (char)toupper((unsigned char)s[i]);
        for (i = 0; i < 3; i++) {
            if (canon[i] < 'A' || canon[i] > 'Z') return SL_E_FIELD;
            l.site[i] = canon[i];
        }
        l.site[3] = '\0';
        for (i = 4; i < 8; i++) {
            if (canon[i] < '0' || canon[i] > '9') return SL_E_FIELD;
        }
        l.year = (canon[4] - '0') * 10 + (canon[5] - '0');
        l.week = (canon[6] - '0') * 10 + (canon[7] - '0');
        if (l.week < 1 || l.week > 53) return SL_E_FIELD;
        if (sl_decode_seq(canon + 9, SL_SEQ_LEN, &v) != 0) return SL_E_FIELD;
        got = symbol_index((unsigned char)canon[15]);
        if (got < 0) return SL_E_FIELD;
        l.seq = v;
        sl_encode_seq(v, seq);
        snprintf(body, sizeof body, "%s%02d%02d%s", l.site, l.year, l.week, seq);
        want = check_index(body, 12);
        if (want != got) return SL_E_CHECK;
        *out = l;
        return SL_OK;
    }

    int sl_succ(sl_label *l) {
        if (l->seq >= SL_SEQ_MAX) return -1;
        l->seq++;
        return 0;
    }

    int sl_compare(const sl_label *a, const sl_label *b) {
        int c;
        if (a->year != b->year) return a->year < b->year ? -1 : 1;
        if (a->week != b->week) return a->week < b->week ? -1 : 1;
        c = strcmp(a->site, b->site);
        if (c != 0) return c < 0 ? -1 : 1;
        if (a->seq != b->seq) return a->seq < b->seq ? -1 : 1;
        return 0;
    }
''')

V4 = dd(r'''
    #include "harness.h"
    #include "samplelabel.h"

    int main(void) {
        char buf[32];
        unsigned long v = 0;
        sl_label l = {"NRW", 26, 14, 7997536UL};
        h_init();

        CHECK_INT(sl_format(&l, buf, sizeof buf), 16);
        CHECK_STR(buf, "NRW-2614-7M230-F");

        CHECK_INT(sl_decode_seq("7M230", 5, &v), 0);
        CHECK_UINT(v, 7997536UL);
        return h_report();
    }
''')

H5 = dd(r'''
    #include <stdio.h>
    #include <stdlib.h>
    #include <string.h>

    #include "harness.h"
    #include "samplelabel.h"

    /* A copy of the first n bytes in a heap block of exactly n bytes: reading past n is an error. */
    static char *exact(const char *s, size_t n) {
        char *p = malloc(n ? n : 1);
        memcpy(p, s, n);
        return p;
    }

    static int parse_text(const char *text, sl_label *out) {
        size_t n = strlen(text);
        char *p = exact(text, n);
        int rc = sl_parse(p, n, out);
        free(p);
        return rc;
    }

    static void test_encode_seq(void) {
        static const struct { unsigned long seq; const char *text; } cases[] = {
            {0, "00000"}, {1, "00001"}, {9, "00009"}, {10, "0000A"}, {31, "0000Z"}, {32, "00010"}, {1023, "000ZZ"},
            {1024, "00100"}, {262143, "07ZZZ"}, {7997536UL, "7M230"}, {16777216UL, "H0000"}, {33554430UL, "ZZZZY"},
            {33554431UL, "ZZZZZ"},
        };
        size_t i;
        char out[SL_SEQ_LEN + 1], ctx[40];
        for (i = 0; i < sizeof cases / sizeof cases[0]; i++) {
            memset(out, '?', sizeof out);
            snprintf(ctx, sizeof ctx, "seq=%lu", cases[i].seq);
            CHECK_INT_CTX(ctx, sl_encode_seq(cases[i].seq, out), 0);
            CHECK_STR_CTX(ctx, out, cases[i].text);
        }
        memset(out, '?', sizeof out);
        CHECK_INT(sl_encode_seq(SL_SEQ_MAX + 1, out), -1);
        CHECK_INT(out[0], '?');
        CHECK_INT(sl_encode_seq(~0UL, out), -1);
        CHECK_INT(out[5], '?');
    }

    static void test_decode_seq(void) {
        unsigned long v = 777;
        char *p;
        CHECK_INT(sl_decode_seq("00000", 5, &v), 0);
        CHECK_UINT(v, 0);
        CHECK_INT(sl_decode_seq("ZZZZZ", 5, &v), 0);
        CHECK_UINT(v, 33554431UL);
        CHECK_INT(sl_decode_seq("H0000", 5, &v), 0);
        CHECK_UINT(v, 16777216UL);
        CHECK_INT(sl_decode_seq("0000A", 5, &v), 0);
        CHECK_UINT(v, 10);
        /* lower case and look-alikes */
        CHECK_INT(sl_decode_seq("7m23o", 5, &v), 0);
        CHECK_UINT(v, 7997536UL);
        CHECK_INT(sl_decode_seq("0000B", 5, &v), 0);
        CHECK_UINT(v, 8);
        CHECK_INT(sl_decode_seq("0000i", 5, &v), 0);
        CHECK_UINT(v, 1);
        CHECK_INT(sl_decode_seq("0000S", 5, &v), 0);
        CHECK_UINT(v, 5);
        CHECK_INT(sl_decode_seq("0000o", 5, &v), 0);
        CHECK_UINT(v, 0);
        /* failures leave *out alone */
        v = 4242;
        CHECK_INT(sl_decode_seq("0000!", 5, &v), -1);
        CHECK_INT(sl_decode_seq("0 000", 5, &v), -1);
        CHECK_INT(sl_decode_seq("0000-", 5, &v), -1);
        CHECK_INT(sl_decode_seq("000", 3, &v), -1);
        CHECK_INT(sl_decode_seq("000000", 6, &v), -1);
        CHECK_INT(sl_decode_seq("", 0, &v), -1);
        CHECK_UINT(v, 4242);
        /* an embedded NUL is not a symbol */
        CHECK_INT(sl_decode_seq("00\0" "00", 5, &v), -1);
        /* never reads beyond n */
        p = exact("7M230", 5);
        CHECK_INT(sl_decode_seq(p, 5, &v), 0);
        CHECK_UINT(v, 7997536UL);
        free(p);
        p = exact("7M23", 4);
        CHECK_INT(sl_decode_seq(p, 4, &v), -1);
        free(p);
    }

    static void test_check_char(void) {
        CHECK_INT(sl_check_char("NRW26147M230", 12), 'F');
        CHECK_INT(sl_check_char("NRW26147", 8), '4');
        CHECK_INT(sl_check_char("", 0), '0');
        CHECK_INT(sl_check_char("A", 1), 'A');
        CHECK_INT(sl_check_char("ZZ", 2), 'H');
        CHECK_INT(sl_check_char("10", 2), '1');
        CHECK_INT(sl_check_char("1A", 2), '0');
        CHECK_INT(sl_check_char("ZZZZ", 3), sl_check_char("ZZZ", 3));
        CHECK_INT(sl_check_char("01", 2), '3');
        CHECK_INT(sl_check_char("9", 1), '9');
        CHECK_INT(sl_check_char("ABC000100000", 12), 'Q');
    }

    static void test_format(void) {
        static const struct { const char *site; int year, week; unsigned long seq; const char *text; } cases[] = {
            {"NRW", 26, 14, 7997536UL, "NRW-2614-7M230-F"},
            {"ABC", 0, 1, 0, "ABC-0001-00000-Q"},
            {"ZZZ", 99, 53, 33554431UL, "ZZZ-9953-ZZZZZ-3"},
            {"LAB", 25, 9, 1234567UL, "LAB-2509-15NM7-H"},
            {"QRS", 3, 52, 31, "QRS-0352-0000Z-E"},
            {"TUV", 12, 30, 32, "TUV-1230-00010-D"},
            {"HOB", 8, 5, 99999UL, "HOB-0805-031MZ-6"},
            {"XYZ", 7, 7, 1, "XYZ-0707-00001-P"},
            {"AAA", 1, 1, 1023, "AAA-0101-000ZZ-9"},
            {"AAB", 1, 1, 1024, "AAB-0101-00100-D"},
            {"BIS", 10, 10, 33554430UL, "BIS-1010-ZZZZY-P"},
            {"SOS", 50, 20, 5555555UL, "SOS-5020-59JC3-X"},
            {"MMM", 45, 45, 16777216UL, "MMM-4545-H0000-G"},
            {"KEL", 19, 3, 262143UL, "KEL-1903-07ZZZ-F"},
        };
        size_t i;
        char buf[17], ctx[64];
        for (i = 0; i < sizeof cases / sizeof cases[0]; i++) {
            sl_label l;
            memset(&l, 0, sizeof l);
            strcpy(l.site, cases[i].site);
            l.year = cases[i].year;
            l.week = cases[i].week;
            l.seq = cases[i].seq;
            memset(buf, '?', sizeof buf);
            snprintf(ctx, sizeof ctx, "%s year=%d week=%d seq=%lu", cases[i].site, l.year, l.week, l.seq);
            CHECK_INT_CTX(ctx, sl_format(&l, buf, sizeof buf), 16);
            CHECK_STR_CTX(ctx, buf, cases[i].text);
        }
    }

    static void test_format_rejects(void) {
        sl_label ok = {"NRW", 26, 14, 7997536UL}, l;
        char buf[40];
        char small[16];
        memset(buf, '?', sizeof buf);
        /* capacity: 16 characters plus the NUL */
        memset(small, '?', sizeof small);
        CHECK_INT(sl_format(&ok, small, 16), -1);
        CHECK_INT(small[0], '?');
        CHECK_INT(sl_format(&ok, buf, 0), -1);
        CHECK_INT(sl_format(&ok, buf, 17), 16);
        CHECK_STR(buf, "NRW-2614-7M230-F");
        l = ok; l.year = -1;
        CHECK_INT(sl_format(&l, buf, sizeof buf), -1);
        l = ok; l.year = 100;
        CHECK_INT(sl_format(&l, buf, sizeof buf), -1);
        l = ok; l.year = 0;
        CHECK_INT(sl_format(&l, buf, sizeof buf), 16);
        l = ok; l.year = 99;
        CHECK_INT(sl_format(&l, buf, sizeof buf), 16);
        l = ok; l.week = 0;
        CHECK_INT(sl_format(&l, buf, sizeof buf), -1);
        l = ok; l.week = 54;
        CHECK_INT(sl_format(&l, buf, sizeof buf), -1);
        l = ok; l.week = 1;
        CHECK_INT(sl_format(&l, buf, sizeof buf), 16);
        l = ok; l.week = 53;
        CHECK_INT(sl_format(&l, buf, sizeof buf), 16);
        l = ok; l.seq = SL_SEQ_MAX + 1;
        CHECK_INT(sl_format(&l, buf, sizeof buf), -1);
        l = ok; l.site[0] = 'a';
        CHECK_INT(sl_format(&l, buf, sizeof buf), -1);
        l = ok; l.site[1] = '1';
        CHECK_INT(sl_format(&l, buf, sizeof buf), -1);
        l = ok; l.site[2] = '@';
        CHECK_INT(sl_format(&l, buf, sizeof buf), -1);
        l = ok; l.site[2] = '[';
        CHECK_INT(sl_format(&l, buf, sizeof buf), -1);
        l = ok; l.site[2] = '\0';
        CHECK_INT(sl_format(&l, buf, sizeof buf), -1);
        l = ok; l.site[3] = 'X';
        CHECK_INT(sl_format(&l, buf, sizeof buf), -1);
        /* a rejected label leaves the buffer alone */
        memset(buf, '?', sizeof buf);
        l = ok; l.week = 60;
        CHECK_INT(sl_format(&l, buf, sizeof buf), -1);
        CHECK_INT(buf[0], '?');
    }

    static void test_parse_ok(void) {
        sl_label l;
        memset(&l, 0, sizeof l);
        CHECK_INT(parse_text("NRW-2614-7M230-F", &l), SL_OK);
        CHECK_STR(l.site, "NRW");
        CHECK_INT(l.year, 26);
        CHECK_INT(l.week, 14);
        CHECK_UINT(l.seq, 7997536UL);
        CHECK_INT(parse_text("abc-0001-00000-q", &l), SL_OK);
        CHECK_STR(l.site, "ABC");
        CHECK_INT(l.year, 0);
        CHECK_INT(l.week, 1);
        CHECK_UINT(l.seq, 0);
        CHECK_INT(parse_text("ZZZ-9953-ZZZZZ-3", &l), SL_OK);
        CHECK_INT(l.year, 99);
        CHECK_INT(l.week, 53);
        CHECK_UINT(l.seq, 33554431UL);
        CHECK_INT(parse_text("SOS-5020-59JC3-X", &l), SL_OK);
        CHECK_STR(l.site, "SOS");
        CHECK_UINT(l.seq, 5555555UL);
        /* look-alikes in the sequence are read as their digits; the check is over the canonical form */
        CHECK_INT(parse_text("NRW-2614-7m23O-F", &l), SL_OK);
        CHECK_UINT(l.seq, 7997536UL);
        CHECK_INT(parse_text("LAB-2509-0000b-1", &l), SL_OK);
        CHECK_UINT(l.seq, 8);
        /* look-alikes in the check symbol */
        CHECK_INT(parse_text("LAB-2509-00008-I", &l), SL_OK);
        CHECK_INT(parse_text("LAB-2509-0000C-O", &l), SL_OK);
        CHECK_INT(parse_text("LAB-2509-0000N-S", &l), SL_OK);
        CHECK_INT(parse_text("LAB-2509-00012-B", &l), SL_OK);
        CHECK_UINT(l.seq, 34);
    }

    static void test_parse_errors(void) {
        sl_label l;
        static const char *shape[] = {
            "", "NRW", "NRW-2614-7M230-", "NRW-2614-7M230-FF", "NRW-2614-7M230-F ", " NRW-2614-7M230-F",
            "NRW_2614-7M230-F", "NRW-2614_7M230-F", "NRW-2614-7M230_F", "NRW2614-7M230-F-", "NR-W2614-7M230-F",
            "NRW-261-47M230-F", "NRW-2614-7M23-0F",
        };
        static const char *field[] = {
            "N1W-2614-7M230-F", "NR!-2614-7M230-F", "NRW-26A4-7M230-F", "NRW-2614-7M2#0-F", "NRW-2614-7M230-!",
            "NRW-2600-7M230-F", "NRW-2654-7M230-F", "NRW-2699-7M230-F", "NRW-2614-7M2 0-F", "NRW-2614-7M23--F",
            "NRW-2614-7M23\xc3-F", "NRW--614-7M230-F", "NRW-26 4-7M230-F", "NRW-2614-7M230-@", "NRW-2614-7M230-[",
        };
        size_t i;
        memset(&l, 0, sizeof l);
        l.year = 55;
        strcpy(l.site, "ZZZ");
        for (i = 0; i < sizeof shape / sizeof shape[0]; i++) {
            CHECK_INT_CTX(shape[i], parse_text(shape[i], &l), SL_E_SHAPE);
        }
        for (i = 0; i < sizeof field / sizeof field[0]; i++) {
            CHECK_INT_CTX(field[i], parse_text(field[i], &l), SL_E_FIELD);
        }
        /* checksum mismatches */
        CHECK_INT(parse_text("NRW-2614-7M230-G", &l), SL_E_CHECK);
        CHECK_INT(parse_text("NRW-2614-7M230-E", &l), SL_E_CHECK);
        CHECK_INT(parse_text("NRW-2614-7M231-F", &l), SL_E_CHECK);
        CHECK_INT(parse_text("NRW-2615-7M230-F", &l), SL_E_CHECK);
        CHECK_INT(parse_text("NRV-2614-7M230-F", &l), SL_E_CHECK);
        CHECK_INT(parse_text("ZZZ-9953-ZZZZZ-4", &l), SL_E_CHECK);
        CHECK_INT(parse_text("ZZZ-9953-ZZZZZ-Z", &l), SL_E_CHECK);
        CHECK_INT(parse_text("ABC-0001-00000-0", &l), SL_E_CHECK);
        /* a swap of two sequence symbols is caught by the position weights */
        CHECK_INT(parse_text("NRW-2614-7M320-F", &l), SL_E_CHECK);
        /* errors do not touch the output */
        CHECK_INT(l.year, 55);
        CHECK_STR(l.site, "ZZZ");
    }

    static void test_parse_bounds(void) {
        sl_label l;
        char *p = exact("NRW-2614-7M230-F", 16);
        CHECK_INT(sl_parse(p, 16, &l), SL_OK);
        free(p);
        /* shorter and longer lengths are judged before the text is looked at */
        p = exact("NRW-2614-7M230-F", 15);
        CHECK_INT(sl_parse(p, 15, &l), SL_E_SHAPE);
        free(p);
        p = exact("NRW-2614-7M230-FX", 17);
        CHECK_INT(sl_parse(p, 17, &l), SL_E_SHAPE);
        free(p);
        p = exact("NRW", 3);
        CHECK_INT(sl_parse(p, 3, &l), SL_E_SHAPE);
        free(p);
        CHECK_INT(sl_parse("NRW-2614-7M230-F", 0, &l), SL_E_SHAPE);
    }

    static void test_roundtrip(void) {
        unsigned long seqs[] = {0, 1, 31, 32, 1000, 65535, 65536, 1048575, 12345678UL, 33554430UL, 33554431UL};
        size_t i;
        int wk;
        for (i = 0; i < sizeof seqs / sizeof seqs[0]; i++) {
            for (wk = 1; wk <= 53; wk += 13) {
                sl_label a = {"QPD", 31, 0, 0}, b;
                char buf[17];
                a.week = wk;
                a.seq = seqs[i];
                memset(&b, 0, sizeof b);
                CHECK_INT(sl_format(&a, buf, sizeof buf), 16);
                CHECK_INT(parse_text(buf, &b), SL_OK);
                CHECK_STR(b.site, "QPD");
                CHECK_INT(b.year, 31);
                CHECK_INT(b.week, wk);
                CHECK_UINT(b.seq, seqs[i]);
            }
        }
    }

    static void test_succ_compare(void) {
        sl_label a = {"AAA", 5, 5, 41};
        sl_label b = {"AAA", 5, 5, 42};
        sl_label top = {"AAA", 5, 5, SL_SEQ_MAX};
        sl_label almost = {"AAA", 5, 5, SL_SEQ_MAX - 1};
        CHECK_INT(sl_succ(&a), 0);
        CHECK_UINT(a.seq, 42);
        CHECK_INT(sl_compare(&a, &b), 0);
        CHECK_INT(sl_succ(&almost), 0);
        CHECK_UINT(almost.seq, SL_SEQ_MAX);
        CHECK_INT(sl_succ(&top), -1);
        CHECK_UINT(top.seq, SL_SEQ_MAX);
        CHECK_INT(sl_succ(&almost), -1);
        CHECK_UINT(almost.seq, SL_SEQ_MAX);
        {
            sl_label x = {"MMM", 20, 30, 9}, y;
            y = x; y.year = 21;
            CHECK_INT(sl_compare(&x, &y), -1);
            CHECK_INT(sl_compare(&y, &x), 1);
            y = x; y.year = 19; y.week = 52; y.seq = 99;
            CHECK_INT(sl_compare(&x, &y), 1);
            y = x; y.week = 31; strcpy(y.site, "AAA");
            CHECK_INT(sl_compare(&x, &y), -1);
            y = x; strcpy(y.site, "MMN"); y.seq = 0;
            CHECK_INT(sl_compare(&x, &y), -1);
            CHECK_INT(sl_compare(&y, &x), 1);
            y = x; strcpy(y.site, "MML"); y.seq = 99;
            CHECK_INT(sl_compare(&x, &y), 1);
            y = x; y.seq = 10;
            CHECK_INT(sl_compare(&x, &y), -1);
            CHECK_INT(sl_compare(&y, &x), 1);
            CHECK_INT(sl_compare(&x, &x), 0);
            y = x; y.seq = 0xFFFFFFFFUL + 1;  /* only meaningful on LP64; still ordered after x */
            CHECK_INT(sl_compare(&x, &y), -1);
        }
    }

    int main(void) {
        h_init();
        test_encode_seq();
        test_decode_seq();
        test_check_char();
        test_format();
        test_format_rejects();
        test_parse_ok();
        test_parse_errors();
        test_parse_bounds();
        test_roundtrip();
        test_succ_compare();
        return h_report();
    }
''')

LIB = Lib(
    name="samplelabel", lang="c", title="the sample-label codec",
    blurb="The lab's sample-tracking system prints and scans labels such as `NRW-2614-7M230-F` with this library.",
    files={"README.md": README1, "include/samplelabel.h": F2, "src/samplelabel.c": F3},
    visible_tests={"tests/test_main.c": V4, "tests/harness.h": _lang3.C_HARNESS},
    hidden_tests={"tests/test_main.c": H5},
    mutate=["src/samplelabel.c"], difficulty=2, tags=["codec", "labels", "checksum"],
    verify=_lang3.C_VERIFY,
)

_lang3.add(LIB, n=8)
