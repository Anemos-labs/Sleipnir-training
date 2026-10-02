"""Greenhouse alarm-rule tokenizer and evaluator (c): tenth-unit numbers, comparisons, `in [lo..hi]`, boolean operators, error positions; bugs injected into the library."""
from fx import Lib, dd

from generators.fix import _lang3

README1 = dd(r'''
    # ruletok

    Tokenizer and evaluator for the alarm rules of a greenhouse controller. A rule is a small expression over sensor
    readings, for example

        temp >= 30.5 & !vent_open
        humidity in [40..80] | (soil < 12 & !pump_on)

    Every value is an `int32_t` in **tenths** (a sensor reading of 23.5 degrees is the integer `235`). Readings are supplied by
    the caller as an array of `rt_var { const char *name; int32_t value; }`.

    ## Tokens

    White space (space and tab) between tokens is skipped. The tokens are

    | token | text | notes |
    |---|---|---|
    | `RT_NUM` | `12`, `-3`, `23.5` | digits with an optional `.` and **exactly one** fractional digit; a leading `-` belongs to the number (only directly before a digit). `value` is in tenths (`23.5 -> 235`, `-3 -> -30`). |
    | `RT_IDENT` | `temp`, `_x9` | a letter or `_`, then letters, digits and `_`; at most 31 characters; case matters |
    | `RT_IN` | `in` | the identifier `in` (exactly) is the keyword |
    | `RT_LT` `RT_LE` `RT_GT` `RT_GE` `RT_EQ` `RT_NE` | `<` `<=` `>` `>=` `==` `!=` | |
    | `RT_AND` `RT_OR` `RT_NOT` | `&` `\|` `!` | single characters (`&&` is two `RT_AND` tokens) |
    | `RT_LPAREN` `RT_RPAREN` `RT_LBRACK` `RT_RBRACK` | `(` `)` `[` `]` | |
    | `RT_DOTDOT` | `..` | |

    Number details: the whole part may be at most `100000` and the value at most `1000000` tenths in magnitude, otherwise
    `RT_E_RANGE` (at the start of the number). A `.` directly after the digits belongs to the number only when a digit follows
    it; `..` is never part of a number (so `[1..5]` is `[`, `1`, `..`, `5`, `]`); any other `.` is an `RT_E_TOKEN` error, as is a
    second fractional digit (at that digit's position).

    Errors are reported through `rt_err { int code; size_t pos; }` where `pos` is the offset of the offending character or
    token (the length of the input when the input ends too early):

    * `RT_E_TOKEN`: a character that cannot start a token (this includes a lone `=`, a `-` that is not followed by a digit and
      a lone `.`), a malformed number as described above, or an identifier longer than 31 characters (at its start);
    * `RT_E_RANGE`: a number out of range; `RT_E_TOOMANY`: more tokens than the caller's array can hold (at the first token that does
      not fit).

    ## `int rt_tokenize(const char *src, size_t n, rt_token *out, size_t max, rt_err *err)`

    Tokenizes the first `n` characters of `src` (not NUL-terminated necessarily) into at most `max` tokens
    `rt_token { int kind; size_t pos; size_t len; int32_t value; }` (`value` is only used by `RT_NUM`, and is 0 for the others).
    Returns the token count, or -1 with `*err` set (`err` may be NULL).

    ## Grammar and evaluation

    From the loosest binding to the tightest:

        expr  := and { '|' and }
        and   := not { '&' not }
        not   := '!' not | cmp
        cmp   := term [ relop term | 'in' '[' term '..' term ']' ]
        term  := NUM | IDENT | '(' expr ')'

    * A comparison is not chained: `a < b < c` is a syntax error. Note that `!` binds *looser* than a comparison:
      `!temp > 3` means `!(temp > 3)`.
    * Comparisons, `in`, `!`, `&` and `|` produce 0 or 1; `&`, `|` and `!` treat any non-zero value as true.
      `x in [lo..hi]` is 1 when `lo <= x <= hi`. A bare number or variable evaluates to its own value.
    * There is no short-circuiting: every variable in the rule must exist, and every error is reported, even in a branch that
      could not change the result.
    * Parentheses and `!` may be nested at most `RT_MAX_DEPTH` (8) deep in total on the way down to a term; the ninth level is
      `RT_E_DEPTH` (at that `(` or `!`).

    ## `int rt_eval(const char *src, size_t n, const rt_var *vars, size_t nvars, int32_t *result, rt_err *err)`

    Tokenizes (at most `RT_MAX_TOKENS` = 48 tokens; more is `RT_E_TOOMANY`) and evaluates the rule. Variable names are matched exactly
    and completely; the first entry wins when a name appears twice. Returns 0 and sets `*result`, or -1 and fills `*err` (`err`
    may be NULL; `*result` is left alone on failure):

    * `RT_E_VAR` for an identifier that is not in `vars` (at the identifier);
    * `RT_E_SYNTAX` for a token that does not fit the grammar (at that token), for tokens left over after a complete expression
      (at the first left-over token) and for input that ends too early (at `n`).
    * tokenizer errors as above (they win over syntax and variable errors, because the whole input is tokenized first).
    * `RT_E_DEPTH` as above.
''')

F2 = dd(r'''
    #ifndef RULETOK_H
    #define RULETOK_H

    #include <stddef.h>
    #include <stdint.h>

    #define RT_IDENT_MAX 31
    #define RT_MAX_DEPTH 8
    #define RT_MAX_TOKENS 48

    enum {
        RT_NUM = 1, RT_IDENT, RT_IN, RT_LT, RT_LE, RT_GT, RT_GE, RT_EQ, RT_NE, RT_AND, RT_OR, RT_NOT,
        RT_LPAREN, RT_RPAREN, RT_LBRACK, RT_RBRACK, RT_DOTDOT
    };

    enum { RT_E_TOKEN = 1, RT_E_RANGE, RT_E_TOOMANY, RT_E_SYNTAX, RT_E_VAR, RT_E_DEPTH };

    typedef struct {
        int kind;
        size_t pos;
        size_t len;
        int32_t value;
    } rt_token;

    typedef struct {
        int code;
        size_t pos;
    } rt_err;

    typedef struct {
        const char *name;
        int32_t value;
    } rt_var;

    int rt_tokenize(const char *src, size_t n, rt_token *out, size_t max, rt_err *err);
    int rt_eval(const char *src, size_t n, const rt_var *vars, size_t nvars, int32_t *result, rt_err *err);

    #endif
''')

F3 = dd(r'''
    #include "ruletok.h"

    #include <string.h>

    static int is_digit(int c) { return c >= '0' && c <= '9'; }

    static int is_alpha(int c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || c == '_'; }

    static int fail(rt_err *e, int code, size_t pos) {
        if (e) {
            e->code = code;
            e->pos = pos;
        }
        return -1;
    }

    int rt_tokenize(const char *s, size_t n, rt_token *out, size_t max, rt_err *err) {
        size_t i = 0, count = 0;
        while (i < n) {
            char c = s[i];
            rt_token t;
            if (c == ' ' || c == '\t') {
                i++;
                continue;
            }
            t.pos = i;
            t.value = 0;
            if (is_digit(c) || (c == '-' && i + 1 < n && is_digit(s[i + 1]))) {
                size_t j = i;
                int neg = 0;
                long v = 0;
                if (c == '-') {
                    neg = 1;
                    j++;
                }
                for (; j < n && is_digit(s[j]); j++) {
                    v = v * 10 + (s[j] - '0');
                    if (v > 100000) return fail(err, RT_E_RANGE, i);
                }
                v *= 10;
                if (j < n && s[j] == '.' && !(j + 1 < n && s[j + 1] == '.')) {
                    if (j + 1 >= n || !is_digit(s[j + 1])) return fail(err, RT_E_TOKEN, j);
                    v += s[j + 1] - '0';
                    j += 2;
                    if (j < n && is_digit(s[j])) return fail(err, RT_E_TOKEN, j);
                    if (v > 1000000) return fail(err, RT_E_RANGE, i);
                }
                t.kind = RT_NUM;
                t.value = (int32_t)(neg ? -v : v);
                t.len = j - i;
            } else if (is_alpha(c)) {
                size_t j = i;
                while (j < n && (is_alpha(s[j]) || is_digit(s[j]))) j++;
                if (j - i > RT_IDENT_MAX) return fail(err, RT_E_TOKEN, i);
                t.len = j - i;
                t.kind = (t.len == 2 && s[i] == 'i' && s[i + 1] == 'n') ? RT_IN : RT_IDENT;
            } else {
                char d = i + 1 < n ? s[i + 1] : '\0';
                t.len = 1;
                switch (c) {
                case '<': t.kind = d == '=' ? RT_LE : RT_LT; break;
                case '>': t.kind = d == '=' ? RT_GE : RT_GT; break;
                case '=':
                    if (d != '=') return fail(err, RT_E_TOKEN, i);
                    t.kind = RT_EQ;
                    break;
                case '!': t.kind = d == '=' ? RT_NE : RT_NOT; break;
                case '.':
                    if (d != '.') return fail(err, RT_E_TOKEN, i);
                    t.kind = RT_DOTDOT;
                    break;
                case '&': t.kind = RT_AND; break;
                case '|': t.kind = RT_OR; break;
                case '(': t.kind = RT_LPAREN; break;
                case ')': t.kind = RT_RPAREN; break;
                case '[': t.kind = RT_LBRACK; break;
                case ']': t.kind = RT_RBRACK; break;
                default: return fail(err, RT_E_TOKEN, i);
                }
                if (t.kind == RT_LE || t.kind == RT_GE || t.kind == RT_EQ || t.kind == RT_NE || t.kind == RT_DOTDOT) t.len = 2;
            }
            if (count == max) return fail(err, RT_E_TOOMANY, t.pos);
            out[count++] = t;
            i += t.len;
        }
        return (int)count;
    }

    typedef struct {
        const rt_token *t;
        size_t n, i, src_len;
        const char *src;
        const rt_var *vars;
        size_t nvars;
        rt_err *err;
        int depth;
    } parser;

    static int peek(const parser *p) { return p->i < p->n ? p->t[p->i].kind : 0; }

    static size_t here(const parser *p) { return p->i < p->n ? p->t[p->i].pos : p->src_len; }

    static int expect(parser *p, int kind) {
        if (peek(p) != kind) return fail(p->err, RT_E_SYNTAX, here(p));
        p->i++;
        return 0;
    }

    static int parse_or(parser *p, int32_t *out);

    static int descend(parser *p) {
        if (p->depth >= RT_MAX_DEPTH) return fail(p->err, RT_E_DEPTH, here(p));
        p->depth++;
        return 0;
    }

    static int parse_term(parser *p, int32_t *out) {
        const rt_token *t;
        size_t k;
        switch (peek(p)) {
        case RT_NUM:
            *out = p->t[p->i++].value;
            return 0;
        case RT_IDENT:
            t = &p->t[p->i];
            for (k = 0; k < p->nvars; k++) {
                if (strlen(p->vars[k].name) == t->len && memcmp(p->vars[k].name, p->src + t->pos, t->len) == 0) {
                    *out = p->vars[k].value;
                    p->i++;
                    return 0;
                }
            }
            return fail(p->err, RT_E_VAR, t->pos);
        case RT_LPAREN:
            if (descend(p) < 0) return -1;
            p->i++;
            if (parse_or(p, out) < 0) return -1;
            if (expect(p, RT_RPAREN) < 0) return -1;
            p->depth--;
            return 0;
        default:
            return fail(p->err, RT_E_SYNTAX, here(p));
        }
    }

    static int parse_cmp(parser *p, int32_t *out) {
        int32_t a, b, hi;
        int kind;
        if (parse_term(p, &a) < 0) return -1;
        kind = peek(p);
        if (kind >= RT_LT && kind <= RT_NE) {
            p->i++;
            if (parse_term(p, &b) < 0) return -1;
            switch (kind) {
            case RT_LT: *out = a < b; break;
            case RT_LE: *out = a <= b; break;
            case RT_GT: *out = a > b; break;
            case RT_GE: *out = a >= b; break;
            case RT_EQ: *out = a == b; break;
            default: *out = a != b; break;
            }
        } else if (kind == RT_IN) {
            p->i++;
            if (expect(p, RT_LBRACK) < 0 || parse_term(p, &b) < 0 || expect(p, RT_DOTDOT) < 0 || parse_term(p, &hi) < 0 ||
                expect(p, RT_RBRACK) < 0)
                return -1;
            *out = a >= b && a <= hi;
        } else {
            *out = a;
        }
        return 0;
    }

    static int parse_not(parser *p, int32_t *out) {
        if (peek(p) == RT_NOT) {
            int32_t v;
            if (descend(p) < 0) return -1;
            p->i++;
            if (parse_not(p, &v) < 0) return -1;
            p->depth--;
            *out = !v;
            return 0;
        }
        return parse_cmp(p, out);
    }

    static int parse_and(parser *p, int32_t *out) {
        int32_t v, rhs;
        if (parse_not(p, &v) < 0) return -1;
        if (peek(p) != RT_AND) {
            *out = v;
            return 0;
        }
        v = v != 0;
        while (peek(p) == RT_AND) {
            p->i++;
            if (parse_not(p, &rhs) < 0) return -1;
            v = v && rhs;
        }
        *out = v;
        return 0;
    }

    static int parse_or(parser *p, int32_t *out) {
        int32_t v, rhs;
        if (parse_and(p, &v) < 0) return -1;
        if (peek(p) != RT_OR) {
            *out = v;
            return 0;
        }
        v = v != 0;
        while (peek(p) == RT_OR) {
            p->i++;
            if (parse_and(p, &rhs) < 0) return -1;
            v = v || rhs;
        }
        *out = v;
        return 0;
    }

    int rt_eval(const char *src, size_t n, const rt_var *vars, size_t nvars, int32_t *result, rt_err *err) {
        rt_token toks[RT_MAX_TOKENS];
        parser p;
        int32_t v;
        int count = rt_tokenize(src, n, toks, RT_MAX_TOKENS, err);
        if (count < 0) return -1;
        p.t = toks;
        p.n = (size_t)count;
        p.i = 0;
        p.src_len = n;
        p.src = src;
        p.vars = vars;
        p.nvars = nvars;
        p.err = err;
        p.depth = 0;
        if (parse_or(&p, &v) < 0) return -1;
        if (p.i != p.n) return fail(err, RT_E_SYNTAX, here(&p));
        *result = v;
        return 0;
    }
''')

V4 = dd(r'''
    #include "harness.h"
    #include "ruletok.h"

    int main(void) {
        static const char rule[] = "temp >= 30.5 & !vent_open";
        rt_var vars[] = {{"temp", 312}, {"vent_open", 0}};
        int32_t res = -1;
        rt_err err;
        h_init();

        CHECK_INT(rt_eval(rule, sizeof rule - 1, vars, 2, &res, &err), 0);
        CHECK_INT(res, 1);
        CHECK_INT(rt_eval("temp >", 6, vars, 2, &res, &err), -1);
        CHECK_INT(err.code, RT_E_SYNTAX);
        return h_report();
    }
''')

H5 = dd(r'''
    #include <stdio.h>
    #include <stdlib.h>
    #include <string.h>

    #include "harness.h"
    #include "ruletok.h"

    static const char *KIND[] = {"?", "NUM", "IDENT", "IN", "LT", "LE", "GT", "GE", "EQ", "NE", "AND", "OR", "NOT",
                                 "LPAREN", "RPAREN", "LBRACK", "RBRACK", "DOTDOT"};

    static const rt_var VARS[] = {
        {"temp", 235}, {"humidity", 550}, {"vent_open", 0}, {"pump_on", 1}, {"soil", 100}, {"zero", 0}, {"neg", -50},
        {"big", 1000000}, {"_x9", 7}, {"a123456789012345678901234567890", 3}, {"temperature", 999},
        {"A", 11}, {"Z", 12}, {"a", 13}, {"z", 14}, {"_", 15}, {"zZ_aA9", 16}, {"Aa", 17}, {"m0", 18}, {"m9", 19},
    };
    #define NVARS (sizeof VARS / sizeof VARS[0])

    typedef struct {
        const char *src;
        int ok;
        int32_t value;
        int code;
        size_t pos;
    } eval_case;

    typedef struct {
        const char *src;
        const char *dump; /* NULL for a tokenizer error */
        int code;
        size_t pos;
    } tok_case;

    static const eval_case EVAL_CASES[] = {
        {"temp >= 30.5 & !vent_open", 1, 0, 0, 0},
        {"humidity in [40..80] | (soil < 12 & !pump_on)", 1, 1, 0, 0},
        {"!temp > 3", 1, 0, 0, 0},
        {"temp", 1, 235, 0, 0},
        {"12", 1, 120, 0, 0},
        {"-3", 1, -30, 0, 0},
        {"23.5", 1, 235, 0, 0},
        {"0", 1, 0, 0, 0},
        {"  temp  ", 1, 235, 0, 0},
        {"\ttemp\t>\t1", 1, 1, 0, 0},
        {"", 0, 0, 4, 0},
        {"temp > 1 > 0", 0, 0, 4, 9},
        {"temp < < 3", 0, 0, 4, 7},
        {"1..5", 0, 0, 4, 1},
        {"x", 0, 0, 5, 0},
        {"a b", 0, 0, 4, 2},
        {"1 2", 0, 0, 4, 2},
        {"(1", 0, 0, 4, 2},
        {"1)", 0, 0, 4, 1},
        {"()", 0, 0, 4, 1},
        {"!", 0, 0, 4, 1},
        {"1 &", 0, 0, 4, 3},
        {"& 1", 0, 0, 4, 0},
        {"1 |", 0, 0, 4, 3},
        {"| 1", 0, 0, 4, 0},
        {"=", 0, 0, 1, 0},
        {"temp = 3", 0, 0, 1, 5},
        {"temp =< 3", 0, 0, 1, 5},
        {"3 !", 0, 0, 4, 2},
        {"3 ! 4", 0, 0, 4, 2},
        {"- 3", 0, 0, 1, 0},
        {"-", 0, 0, 1, 0},
        {"-x", 0, 0, 1, 0},
        {"-.5", 0, 0, 1, 0},
        {".5", 0, 0, 1, 0},
        {"1.", 0, 0, 1, 1},
        {"1.5.", 0, 0, 1, 3},
        {"1.5.5", 0, 0, 1, 3},
        {"1.55", 0, 0, 1, 3},
        {"1.5 5", 0, 0, 4, 4},
        {"2..3", 0, 0, 4, 1},
        {"1.5..2.5", 0, 0, 4, 3},
        {"12.5..13", 0, 0, 4, 4},
        {"humidity in [1..2", 0, 0, 4, 17},
        {"humidity in 1..2]", 0, 0, 4, 12},
        {"humidity in [1 2]", 0, 0, 4, 15},
        {"humidity in [1..2]]", 0, 0, 4, 18},
        {"humidity in [..2]", 0, 0, 4, 13},
        {"humidity in [1..]", 0, 0, 4, 16},
        {"humidity in[400..700]", 1, 0, 0, 0},
        {"humidity in [(1)..(99)]", 1, 1, 0, 0},
        {"temp in [-30..30]", 1, 1, 0, 0},
        {"soil in [10..10]", 1, 1, 0, 0},
        {"soil in [10.0..10.0]", 1, 1, 0, 0},
        {"soil in [10.1..10.2]", 1, 0, 0, 0},
        {"in", 0, 0, 4, 0},
        {"in [1..2]", 0, 0, 4, 0},
        {"temp in", 0, 0, 4, 7},
        {"temp in [", 0, 0, 4, 9},
        {"int", 0, 0, 5, 0},
        {"inn", 0, 0, 5, 0},
        {"In", 0, 0, 5, 0},
        {"_in", 0, 0, 5, 0},
        {"in2", 0, 0, 5, 0},
        {"temp&&1", 0, 0, 4, 5},
        {"temp||1", 0, 0, 4, 5},
        {"temp&1|0", 1, 1, 0, 0},
        {"1|0&0", 1, 1, 0, 0},
        {"(1|0)&0", 1, 0, 0, 0},
        {"!1&0", 1, 0, 0, 0},
        {"!(1&0)", 1, 1, 0, 0},
        {"!!1", 1, 1, 0, 0},
        {"!!!5", 1, 0, 0, 0},
        {"!0|0", 1, 1, 0, 0},
        {"!1|1", 1, 1, 0, 0},
        {"1&2", 1, 1, 0, 0},
        {"2&3", 1, 1, 0, 0},
        {"5|0", 1, 1, 0, 0},
        {"0|0", 1, 0, 0, 0},
        {"0&5", 1, 0, 0, 0},
        {"3&0|4", 1, 1, 0, 0},
        {"100000", 1, 1000000, 0, 0},
        {"100000.0", 1, 1000000, 0, 0},
        {"100000.1", 0, 0, 2, 0},
        {"100001", 0, 0, 2, 0},
        {"-100000", 1, -1000000, 0, 0},
        {"-100000.0", 1, -1000000, 0, 0},
        {"-100000.1", 0, 0, 2, 0},
        {"99999.9 > 0", 1, 1, 0, 0},
        {"99999999999", 0, 0, 2, 0},
        {"0000012", 1, 120, 0, 0},
        {"00.5", 1, 5, 0, 0},
        {"-0", 1, 0, 0, 0},
        {"-0.0", 1, 0, 0, 0},
        {"5 == 5.0", 1, 1, 0, 0},
        {"5 != 5.0", 1, 0, 0, 0},
        {"big > 99999", 1, 1, 0, 0},
        {"big == 100000", 1, 1, 0, 0},
        {"big >= 100000.0", 1, 1, 0, 0},
        {"neg < 0", 1, 1, 0, 0},
        {"neg == -5", 1, 1, 0, 0},
        {"neg == -5.0", 1, 1, 0, 0},
        {"neg <= -5.1", 1, 0, 0, 0},
        {"neg >= -5.0 & neg < -4.9", 1, 1, 0, 0},
        {"a123456789012345678901234567890", 1, 3, 0, 0},
        {"a123456789012345678901234567890 == 3", 1, 0, 0, 0},
        {"a1234567890123456789012345678901", 0, 0, 1, 0},
        {"a1234567890123456789012345678901 == 3", 0, 0, 1, 0},
        {"_x9 == 0.7", 1, 1, 0, 0},
        {"_x9", 1, 7, 0, 0},
        {"temperature", 1, 999, 0, 0},
        {"temperature > temp", 1, 1, 0, 0},
        {"temp > temperature", 1, 0, 0, 0},
        {"temper", 0, 0, 5, 0},
        {"emp", 0, 0, 5, 0},
        {"Temp", 0, 0, 5, 0},
        {"TEMP", 0, 0, 5, 0},
        {"temp1", 0, 0, 5, 0},
        {"humidity >= 55 & humidity <= 55.0", 1, 1, 0, 0},
        {"temp #", 0, 0, 1, 5},
        {"temp @ 3", 0, 0, 1, 5},
        {"temp ; 3", 0, 0, 1, 5},
        {"temp , 3", 0, 0, 1, 5},
        {"temp 'a'", 0, 0, 1, 5},
        {"temp\n", 0, 0, 1, 4},
        {"\ttemp", 1, 235, 0, 0},
        {"temp\r", 0, 0, 1, 4},
        {"é", 0, 0, 1, 0},
        {"temp > é", 0, 0, 1, 7},
        {"(((((((((1)))))))))", 0, 0, 6, 8},
        {"((((((((1))))))))", 1, 10, 0, 0},
        {"!!!!!!!!1", 1, 1, 0, 0},
        {"!!!!!!!!!1", 0, 0, 6, 8},
        {"((((!!!!1))))", 1, 1, 0, 0},
        {"(((((!!!!1)))))", 0, 0, 6, 8},
        {"((((!!!!!1))))", 0, 0, 6, 8},
        {"(!(!(!(!(!(!(!(!(1))))))))", 0, 0, 6, 8},
        {"(!(!(!(!(!(!(!(!(!(1)))))))))", 0, 0, 6, 8},
        {"1 & (((((((1)))))))", 1, 1, 0, 0},
        {"1 & ((((((((1))))))))", 1, 1, 0, 0},
        {"(1)(2)", 0, 0, 4, 3},
        {"(1) 2", 0, 0, 4, 4},
        {"((1)", 0, 0, 4, 4},
        {"(1))", 0, 0, 4, 3},
        {"1 & (2 | 3) & !(4 & 0)", 1, 1, 0, 0},
        {"unknown", 0, 0, 5, 0},
        {"unknown > 3", 0, 0, 5, 0},
        {"3 > unknown", 0, 0, 5, 4},
        {"(unknown)", 0, 0, 5, 1},
        {"zero & unknown", 0, 0, 5, 7},
        {"1 | unknown", 0, 0, 5, 4},
        {"unknown &", 0, 0, 5, 0},
        {"3 >", 0, 0, 4, 3},
        {"3 > >", 0, 0, 4, 4},
        {"temp > 3 &", 0, 0, 4, 10},
        {"x >", 0, 0, 5, 0},
        {"y in [1..2]", 0, 0, 5, 0},
        {"3 in [x..2]", 0, 0, 5, 6},
        {"3 in [1..y]", 0, 0, 5, 9},
        {"1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1", 1, 1, 0, 0},
        {"!1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1", 1, 1, 0, 0},
        {"!!1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1", 0, 0, 3, 48},
        {"1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1", 0, 0, 3, 48},
        {"!1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1", 0, 0, 3, 48},
        {"1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1|1", 0, 0, 3, 48},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 0, 0, 1, 0},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 0, 0, 5, 0},
        {"9999999", 0, 0, 2, 0},
        {"1..", 0, 0, 4, 1},
        {"1.5..", 0, 0, 4, 3},
        {"[1..", 0, 0, 4, 0},
        {"A", 1, 11, 0, 0},
        {"Z", 1, 12, 0, 0},
        {"a", 1, 13, 0, 0},
        {"z", 1, 14, 0, 0},
        {"_", 1, 15, 0, 0},
        {"zZ_aA9", 1, 16, 0, 0},
        {"Aa", 1, 17, 0, 0},
        {"A > Z", 1, 0, 0, 0},
        {"m0 < m9", 1, 1, 0, 0},
        {"m9 - 1", 0, 0, 1, 3},
        {"9", 1, 90, 0, 0},
        {"@", 0, 0, 1, 0},
        {"`", 0, 0, 1, 0},
        {"{", 0, 0, 1, 0},
        {"/", 0, 0, 1, 0},
        {":", 0, 0, 1, 0},
        {"a@", 0, 0, 1, 1},
        {"a`", 0, 0, 1, 1},
        {"a{", 0, 0, 1, 1},
        {"a/", 0, 0, 1, 1},
        {"a:", 0, 0, 1, 1},
        {"a[", 0, 0, 4, 1},
        {"1/", 0, 0, 1, 1},
        {"1:", 0, 0, 1, 1},
        {"1`", 0, 0, 1, 1},
        {"A[", 0, 0, 4, 1},
        {"Z{", 0, 0, 1, 1},
        {"A@", 0, 0, 1, 1},
        {"m09", 0, 0, 5, 0},
        {"A in [a..z]", 1, 0, 0, 0},
        {"z in [A..Z]", 1, 0, 0, 0},
        {"_ in [0..9]", 1, 1, 0, 0},
        {"9 in [0..9]", 1, 1, 0, 0},
        {"0 in [0..9]", 1, 1, 0, 0},
        {"!_x9", 1, 0, 0, 0},
        {"#!_x", 0, 0, 1, 0},
        {"!!40 & 12 & (temperature) >=m9", 1, 1, 0, 0},
        {"m9 != a123456789012345678901234567890 | 12 >vent_open | (_x9) in [humidity..Z]", 1, 1, 0, 0},
        {"m9 != a12345678901234567890", 0, 0, 5, 6},
        {"12 <=40", 1, 1, 0, 0},
        {"1<=40", 1, 1, 0, 0},
        {"(zZ_aA9 !=1) >=(zZ_aA9 & a123456789012345678901234567890) & zero", 1, 0, 0, 0},
        {"(12) in [m9..80] | 55.0 < (Aa) & humidity", 1, 1, 0, 0},
        {"a<z", 1, 1, 0, 0},
        {"Aa != 12", 1, 1, 0, 0},
        {"Aa != 2", 1, 1, 0, 0},
        {"100", 1, 1000, 0, 0},
        {"23.5 <=(0)", 1, 0, 0, 0},
        {"23.5 <=( 0)", 1, 0, 0, 0},
        {"zero | !(big) ==-0.5", 1, 1, 0, 0},
        {"55.0 <m0 & soil in [A..80]", 1, 0, 0, 0},
        {"!Aa", 1, 0, 0, 0},
        {"(a", 0, 0, 4, 2},
        {"(-0.5 > _x9) >(Aa < m0)", 1, 0, 0, 0},
        {"(-0.5 > _x9 >(Aa < m0)", 0, 0, 4, 12},
        {"(Aa) <= 12 | big & pump_on | 7.5 <= 7.5 | 7.5 | Aa & 12", 1, 1, 0, 0},
        {"(Aa) <= 12 | big & pum[p_on | 7.5 <= 7.5 | 7.5 | Aa & 12", 0, 0, 5, 19},
        {"30.5 | a", 1, 1, 0, 0},
        {"30.5  a", 0, 0, 4, 6},
        {"!-0.5", 1, 0, 0, 0},
        {"!!12", 1, 1, 0, 0},
        {"!!)2", 0, 0, 4, 2},
        {"!-0.5 != (m9) & !neg & _ & 30.5 in [big..99.9]", 1, 0, 0, 0},
        {"!-0.5 != (m9) & !neg & _ & 30.5 in [big..99. ]", 0, 0, 1, 43},
        {"!55.0 | 100 | 55.0 | -0.5 & _x9", 1, 1, 0, 0},
        {"vent_open<= 100", 1, 1, 0, 0},
        {"v|ent_open<= 100", 0, 0, 5, 0},
        {"99.9 >=(a >=100)", 1, 1, 0, 0},
        {"Z | 12 | 100 & -3 >(A) & !neg & _ & (m9) in [zero..40]", 1, 1, 0, 0},
        {"Z | !2 | 100 & -3 >(A) & !neg & _ & (m9) in [zero..40]", 1, 1, 0, 0},
        {"Z | 12 | 100 & -3 >(A) & !neg & _ & .m9) in [zero..40]$", 0, 0, 1, 36},
        {"1<(!soil | 40 & -3)", 1, 0, 0, 0},
        {"30.5", 1, 305, 0, 0},
        {"12<=80", 1, 1, 0, 0},
        {"z in [(23.5>=7.5)..-3]", 1, 0, 0, 0},
        {"z in [(23.$>=7.5)..-3]", 0, 0, 1, 9},
        {"!-3 | a123456789012345678901234567890 > 23.5 & 40 | 0 in [_..vent_open]", 1, 0, 0, 0},
        {"!-3 | a123456789012345678901234567890 # 23.5 & 40 | 0 in [_..vent_open]", 0, 0, 1, 38},
        {"a == _x9 | zero", 1, 0, 0, 0},
        {"a == _x9 | zero)", 0, 0, 4, 15},
        {"a == _x#  zero", 0, 0, 1, 7},
        {"!!neg & _x9 in [(40)..80] | !_ | 7.5", 1, 1, 0, 0},
        {"12 in [1..temperature]", 1, 1, 0, 0},
        {"!0<Z", 1, 0, 0, 0},
        {"(z<= 80) < a123456789012345678901234567890", 1, 1, 0, 0},
        {"(z<= 80) < a12345678901234", 0, 0, 5, 11},
        {"-0.5", 1, -5, 0, 0},
        {"-0.!5", 0, 0, 1, 2},
        {"neg", 1, -50, 0, 0},
        {"zZ_aA9>-0.5 & 100 > 99.9", 1, 1, 0, 0},
        {"zZ_aA9>-0.5 & 100 > 99<9", 0, 0, 4, 22},
        {"!(m0) in [1..(1)] | m9 & 100 & !Aa | a123456789012345678901234567890", 1, 1, 0, 0},
        {"!(m0) in [1.(1)] | m9 & 100 & !Aa | a123456789012345678901234567890", 0, 0, 1, 11},
        {"!-3 | (m0) <=big", 1, 1, 0, 0},
        {"!-3 | (m0) <=b(ig", 0, 0, 5, 13},
        {"((-3) in [z.._]) in [40..0] | 40 >(_x9)", 1, 1, 0, 0},
        {"m0<zero", 1, 0, 0, 0},
        {"12>=z", 1, 1, 0, 0},
        {"!!Aa >=7.5", 1, 0, 0, 0},
        {"big | !23.5!=(-3) | big", 1, 1, 0, 0},
        {"big | !23.5!=(-3) | big>", 0, 0, 4, 24},
        {"!0 & 30.5 | -0.5 & _x9", 1, 1, 0, 0},
        {"ng", 0, 0, 5, 0},
        {"Aa<= 0", 1, 0, 0, 0},
        {"=a= 0", 0, 0, 1, 0},
        {"3.5", 1, 35, 0, 0},
        {"55.0 in [pump_on..80]", 1, 1, 0, 0},
        {"55.0 in [pump_o", 0, 0, 5, 9},
        {"(temperature <-0.5 & 55.0 < 100)>=100", 1, 0, 0, 0},
        {"[", 0, 0, 4, 0},
        {"!a>((7.5) in [(big).._x9])", 1, 0, 0, 0},
        {"!a>((7.5) ]n [(big).._x9])", 0, 0, 4, 10},
        {"!a>(=(7.5) in [(big)..", 0, 0, 1, 4},
        {"305", 1, 3050, 0, 0},
        {"m9 <= 55.0", 1, 1, 0, 0},
        {"m9 <|= 55.0", 0, 0, 1, 5},
        {"1", 1, 10, 0, 0},
        {"big in [((-3) <12)..-0.5]", 1, 0, 0, 0},
        {"big in [((-3)", 0, 0, 4, 13},
        {"big in [((-3>) <12)", 0, 0, 4, 13},
        {"12!= 30.5", 1, 1, 0, 0},
        {"30.5 <= 99.9", 1, 1, 0, 0},
        {"30", 1, 300, 0, 0},
        {"55.0", 1, 550, 0, 0},
        {"!12<_x9 | (0) > 100", 1, 1, 0, 0},
        {"30.5 & !1 in [vent_open..(z)]", 1, 0, 0, 0},
        {"30.5 & !1 in ", 0, 0, 4, 13},
        {"!1", 1, 0, 0, 0},
        {"!(1", 0, 0, 4, 3},
        {"!7.5!= -3 | !soil | !A<=(1)", 1, 1, 0, 0},
        {"!7.5!= -3  !soil | !A<=(1 ", 0, 0, 4, 11},
        {"!!zero | 30.5 & !big & 30.5", 1, 0, 0, 0},
        {"-0.5 <= 23.5", 1, 1, 0, 0},
        {"30.5< (temperature | 12) | (_x9)== big", 1, 0, 0, 0},
        {"30.5< (temperature | 12) | (_#x9)== big", 0, 0, 1, 29},
        {"30.5< (temperature | 12) | (_x9)=", 0, 0, 1, 32},
        {"!(m0) !=(zZ_aA9) & 7.5 !=A", 1, 0, 0, 0},
        {"(99.9 in [_..80])< (7.5)", 1, 1, 0, 0},
        {"(0 & 100>= 7.5) in [1..-0.5]", 1, 0, 0, 0},
        {"(0 & 100>= 7.5) in [1.-0.5]", 0, 0, 1, 21},
        {"80> 40", 1, 1, 0, 0},
        {"zero== (A ==A)", 1, 0, 0, 0},
        {"big !=1", 1, 1, 0, 0},
        {"_ <=(temperature | a123456789012345678901234567890 & zero & neg)", 1, 0, 0, 0},
        {"_ <=(temperature#| a123456789012345678901234567x890 & zero & neg)", 0, 0, 1, 16},
        {"&1", 0, 0, 4, 0},
        {"7.5", 1, 75, 0, 0},
        {"!!a123456789012345678901234567890", 1, 1, 0, 0},
        {"40 | !40 & m0 & 23.5 in [-3..(100)]", 1, 1, 0, 0},
        {"40 | !40  m0 & 23.5 in [-3..(100)]", 0, 0, 4, 10},
        {"A | 1 | (40) <=temperature & -3 in [(zZ_aA9)..(-3)] & !!1 & 7.5", 1, 1, 0, 0},
        {"A | 1 | (40) <=temperatu]re & -3 in [(zZ_aA9)..(-3)] & !!1 & 7.5", 0, 0, 5, 15},
        {"!100", 1, 0, 0, 0},
        {"zZ_aA9 & 7.5 | (m9 | -3) in [-0.5..a123456789012345678901234567890]", 1, 1, 0, 0},
        {"zZ_aA9 & 7.5 | (m9 | -3) in [-0.5..a12345678901234567)8901234567890]", 0, 0, 2, 54},
        {"!_ & !m9 & pump_on>=(-0.5) & humidity | -0.5", 1, 1, 0, 0},
        {"!_ & !m9 & pump_on>=(-0.5) & humidty | -0.5", 0, 0, 5, 29},
        {"40 <=-3", 1, 0, 0, 0},
        {"99.9 in [(!Z in [(7.5).._])..-0.5]", 1, 0, 0, 0},
        {"99.9 in [(!Z in! [(7.5).._])..-0.5]", 0, 0, 4, 15},
        {"99.9 i [(!Z i", 0, 0, 4, 5},
    };

    static const tok_case TOK_CASES[] = {
        {"temp >= 30.5 & !vent_open", "IDENT@0+4 GE@5+2 NUM@8+4=305 AND@13+1 NOT@15+1 IDENT@16+9", 0, 0},
        {"humidity in [40..80] | (soil < 12 & !pump_on)", "IDENT@0+8 IN@9+2 LBRACK@12+1 NUM@13+2=400 DOTDOT@15+2 NUM@17+2=800 RBRACK@19+1 OR@21+1 LPAREN@23+1 IDENT@24+4 LT@29+1 NUM@31+2=120 AND@34+1 NOT@36+1 IDENT@37+7 RPAREN@44+1", 0, 0},
        {"!temp > 3", "NOT@0+1 IDENT@1+4 GT@6+1 NUM@8+1=30", 0, 0},
        {"temp", "IDENT@0+4", 0, 0},
        {"12", "NUM@0+2=120", 0, 0},
        {"-3", "NUM@0+2=-30", 0, 0},
        {"23.5", "NUM@0+4=235", 0, 0},
        {"0", "NUM@0+1=0", 0, 0},
        {"  temp  ", "IDENT@2+4", 0, 0},
        {"\ttemp\t>\t1", "IDENT@1+4 GT@6+1 NUM@8+1=10", 0, 0},
        {"", "", 0, 0},
        {"temp > 1 > 0", "IDENT@0+4 GT@5+1 NUM@7+1=10 GT@9+1 NUM@11+1=0", 0, 0},
        {"temp < < 3", "IDENT@0+4 LT@5+1 LT@7+1 NUM@9+1=30", 0, 0},
        {"1..5", "NUM@0+1=10 DOTDOT@1+2 NUM@3+1=50", 0, 0},
        {"x", "IDENT@0+1", 0, 0},
        {"a b", "IDENT@0+1 IDENT@2+1", 0, 0},
        {"1 2", "NUM@0+1=10 NUM@2+1=20", 0, 0},
        {"(1", "LPAREN@0+1 NUM@1+1=10", 0, 0},
        {"1)", "NUM@0+1=10 RPAREN@1+1", 0, 0},
        {"()", "LPAREN@0+1 RPAREN@1+1", 0, 0},
        {"!", "NOT@0+1", 0, 0},
        {"1 &", "NUM@0+1=10 AND@2+1", 0, 0},
        {"& 1", "AND@0+1 NUM@2+1=10", 0, 0},
        {"1 |", "NUM@0+1=10 OR@2+1", 0, 0},
        {"| 1", "OR@0+1 NUM@2+1=10", 0, 0},
        {"=", NULL, 1, 0},
        {"temp = 3", NULL, 1, 5},
        {"temp =< 3", NULL, 1, 5},
        {"3 !", "NUM@0+1=30 NOT@2+1", 0, 0},
        {"3 ! 4", "NUM@0+1=30 NOT@2+1 NUM@4+1=40", 0, 0},
        {"- 3", NULL, 1, 0},
        {"-", NULL, 1, 0},
        {"-x", NULL, 1, 0},
        {"-.5", NULL, 1, 0},
        {".5", NULL, 1, 0},
        {"1.", NULL, 1, 1},
        {"1.5.", NULL, 1, 3},
        {"1.5.5", NULL, 1, 3},
        {"1.55", NULL, 1, 3},
        {"1.5 5", "NUM@0+3=15 NUM@4+1=50", 0, 0},
        {"2..3", "NUM@0+1=20 DOTDOT@1+2 NUM@3+1=30", 0, 0},
        {"1.5..2.5", "NUM@0+3=15 DOTDOT@3+2 NUM@5+3=25", 0, 0},
        {"12.5..13", "NUM@0+4=125 DOTDOT@4+2 NUM@6+2=130", 0, 0},
        {"humidity in [1..2", "IDENT@0+8 IN@9+2 LBRACK@12+1 NUM@13+1=10 DOTDOT@14+2 NUM@16+1=20", 0, 0},
        {"humidity in 1..2]", "IDENT@0+8 IN@9+2 NUM@12+1=10 DOTDOT@13+2 NUM@15+1=20 RBRACK@16+1", 0, 0},
        {"humidity in [1 2]", "IDENT@0+8 IN@9+2 LBRACK@12+1 NUM@13+1=10 NUM@15+1=20 RBRACK@16+1", 0, 0},
        {"humidity in [1..2]]", "IDENT@0+8 IN@9+2 LBRACK@12+1 NUM@13+1=10 DOTDOT@14+2 NUM@16+1=20 RBRACK@17+1 RBRACK@18+1", 0, 0},
        {"humidity in [..2]", "IDENT@0+8 IN@9+2 LBRACK@12+1 DOTDOT@13+2 NUM@15+1=20 RBRACK@16+1", 0, 0},
        {"humidity in [1..]", "IDENT@0+8 IN@9+2 LBRACK@12+1 NUM@13+1=10 DOTDOT@14+2 RBRACK@16+1", 0, 0},
        {"humidity in[400..700]", "IDENT@0+8 IN@9+2 LBRACK@11+1 NUM@12+3=4000 DOTDOT@15+2 NUM@17+3=7000 RBRACK@20+1", 0, 0},
        {"humidity in [(1)..(99)]", "IDENT@0+8 IN@9+2 LBRACK@12+1 LPAREN@13+1 NUM@14+1=10 RPAREN@15+1 DOTDOT@16+2 LPAREN@18+1 NUM@19+2=990 RPAREN@21+1 RBRACK@22+1", 0, 0},
        {"temp in [-30..30]", "IDENT@0+4 IN@5+2 LBRACK@8+1 NUM@9+3=-300 DOTDOT@12+2 NUM@14+2=300 RBRACK@16+1", 0, 0},
        {"soil in [10..10]", "IDENT@0+4 IN@5+2 LBRACK@8+1 NUM@9+2=100 DOTDOT@11+2 NUM@13+2=100 RBRACK@15+1", 0, 0},
        {"soil in [10.0..10.0]", "IDENT@0+4 IN@5+2 LBRACK@8+1 NUM@9+4=100 DOTDOT@13+2 NUM@15+4=100 RBRACK@19+1", 0, 0},
        {"soil in [10.1..10.2]", "IDENT@0+4 IN@5+2 LBRACK@8+1 NUM@9+4=101 DOTDOT@13+2 NUM@15+4=102 RBRACK@19+1", 0, 0},
        {"in", "IN@0+2", 0, 0},
        {"in [1..2]", "IN@0+2 LBRACK@3+1 NUM@4+1=10 DOTDOT@5+2 NUM@7+1=20 RBRACK@8+1", 0, 0},
        {"temp in", "IDENT@0+4 IN@5+2", 0, 0},
        {"temp in [", "IDENT@0+4 IN@5+2 LBRACK@8+1", 0, 0},
        {"int", "IDENT@0+3", 0, 0},
        {"inn", "IDENT@0+3", 0, 0},
        {"In", "IDENT@0+2", 0, 0},
        {"_in", "IDENT@0+3", 0, 0},
        {"in2", "IDENT@0+3", 0, 0},
        {"temp&&1", "IDENT@0+4 AND@4+1 AND@5+1 NUM@6+1=10", 0, 0},
        {"temp||1", "IDENT@0+4 OR@4+1 OR@5+1 NUM@6+1=10", 0, 0},
        {"temp&1|0", "IDENT@0+4 AND@4+1 NUM@5+1=10 OR@6+1 NUM@7+1=0", 0, 0},
        {"1|0&0", "NUM@0+1=10 OR@1+1 NUM@2+1=0 AND@3+1 NUM@4+1=0", 0, 0},
        {"(1|0)&0", "LPAREN@0+1 NUM@1+1=10 OR@2+1 NUM@3+1=0 RPAREN@4+1 AND@5+1 NUM@6+1=0", 0, 0},
        {"!1&0", "NOT@0+1 NUM@1+1=10 AND@2+1 NUM@3+1=0", 0, 0},
        {"!(1&0)", "NOT@0+1 LPAREN@1+1 NUM@2+1=10 AND@3+1 NUM@4+1=0 RPAREN@5+1", 0, 0},
        {"!!1", "NOT@0+1 NOT@1+1 NUM@2+1=10", 0, 0},
        {"!!!5", "NOT@0+1 NOT@1+1 NOT@2+1 NUM@3+1=50", 0, 0},
        {"!0|0", "NOT@0+1 NUM@1+1=0 OR@2+1 NUM@3+1=0", 0, 0},
        {"!1|1", "NOT@0+1 NUM@1+1=10 OR@2+1 NUM@3+1=10", 0, 0},
        {"1&2", "NUM@0+1=10 AND@1+1 NUM@2+1=20", 0, 0},
        {"2&3", "NUM@0+1=20 AND@1+1 NUM@2+1=30", 0, 0},
        {"5|0", "NUM@0+1=50 OR@1+1 NUM@2+1=0", 0, 0},
        {"0|0", "NUM@0+1=0 OR@1+1 NUM@2+1=0", 0, 0},
        {"0&5", "NUM@0+1=0 AND@1+1 NUM@2+1=50", 0, 0},
        {"3&0|4", "NUM@0+1=30 AND@1+1 NUM@2+1=0 OR@3+1 NUM@4+1=40", 0, 0},
        {"100000", "NUM@0+6=1000000", 0, 0},
        {"100000.0", "NUM@0+8=1000000", 0, 0},
        {"100000.1", NULL, 2, 0},
        {"100001", NULL, 2, 0},
        {"-100000", "NUM@0+7=-1000000", 0, 0},
        {"-100000.0", "NUM@0+9=-1000000", 0, 0},
        {"-100000.1", NULL, 2, 0},
        {"99999.9 > 0", "NUM@0+7=999999 GT@8+1 NUM@10+1=0", 0, 0},
        {"99999999999", NULL, 2, 0},
        {"0000012", "NUM@0+7=120", 0, 0},
        {"00.5", "NUM@0+4=5", 0, 0},
        {"-0", "NUM@0+2=0", 0, 0},
        {"-0.0", "NUM@0+4=0", 0, 0},
        {"5 == 5.0", "NUM@0+1=50 EQ@2+2 NUM@5+3=50", 0, 0},
        {"5 != 5.0", "NUM@0+1=50 NE@2+2 NUM@5+3=50", 0, 0},
        {"big > 99999", "IDENT@0+3 GT@4+1 NUM@6+5=999990", 0, 0},
        {"big == 100000", "IDENT@0+3 EQ@4+2 NUM@7+6=1000000", 0, 0},
        {"big >= 100000.0", "IDENT@0+3 GE@4+2 NUM@7+8=1000000", 0, 0},
        {"neg < 0", "IDENT@0+3 LT@4+1 NUM@6+1=0", 0, 0},
        {"neg == -5", "IDENT@0+3 EQ@4+2 NUM@7+2=-50", 0, 0},
        {"neg == -5.0", "IDENT@0+3 EQ@4+2 NUM@7+4=-50", 0, 0},
        {"neg <= -5.1", "IDENT@0+3 LE@4+2 NUM@7+4=-51", 0, 0},
        {"neg >= -5.0 & neg < -4.9", "IDENT@0+3 GE@4+2 NUM@7+4=-50 AND@12+1 IDENT@14+3 LT@18+1 NUM@20+4=-49", 0, 0},
        {"a123456789012345678901234567890", "IDENT@0+31", 0, 0},
        {"a123456789012345678901234567890 == 3", "IDENT@0+31 EQ@32+2 NUM@35+1=30", 0, 0},
        {"a1234567890123456789012345678901", NULL, 1, 0},
        {"a1234567890123456789012345678901 == 3", NULL, 1, 0},
        {"_x9 == 0.7", "IDENT@0+3 EQ@4+2 NUM@7+3=7", 0, 0},
        {"_x9", "IDENT@0+3", 0, 0},
        {"temperature", "IDENT@0+11", 0, 0},
        {"temperature > temp", "IDENT@0+11 GT@12+1 IDENT@14+4", 0, 0},
        {"temp > temperature", "IDENT@0+4 GT@5+1 IDENT@7+11", 0, 0},
        {"temper", "IDENT@0+6", 0, 0},
        {"emp", "IDENT@0+3", 0, 0},
        {"Temp", "IDENT@0+4", 0, 0},
        {"TEMP", "IDENT@0+4", 0, 0},
        {"temp1", "IDENT@0+5", 0, 0},
        {"humidity >= 55 & humidity <= 55.0", "IDENT@0+8 GE@9+2 NUM@12+2=550 AND@15+1 IDENT@17+8 LE@26+2 NUM@29+4=550", 0, 0},
        {"temp #", NULL, 1, 5},
        {"temp @ 3", NULL, 1, 5},
        {"temp ; 3", NULL, 1, 5},
        {"temp , 3", NULL, 1, 5},
        {"temp 'a'", NULL, 1, 5},
        {"temp\n", NULL, 1, 4},
        {"\ttemp", "IDENT@1+4", 0, 0},
        {"temp\r", NULL, 1, 4},
        {"é", NULL, 1, 0},
        {"temp > é", NULL, 1, 7},
        {"(((((((((1)))))))))", "LPAREN@0+1 LPAREN@1+1 LPAREN@2+1 LPAREN@3+1 LPAREN@4+1 LPAREN@5+1 LPAREN@6+1 LPAREN@7+1 LPAREN@8+1 NUM@9+1=10 RPAREN@10+1 RPAREN@11+1 RPAREN@12+1 RPAREN@13+1 RPAREN@14+1 RPAREN@15+1 RPAREN@16+1 RPAREN@17+1 RPAREN@18+1", 0, 0},
        {"((((((((1))))))))", "LPAREN@0+1 LPAREN@1+1 LPAREN@2+1 LPAREN@3+1 LPAREN@4+1 LPAREN@5+1 LPAREN@6+1 LPAREN@7+1 NUM@8+1=10 RPAREN@9+1 RPAREN@10+1 RPAREN@11+1 RPAREN@12+1 RPAREN@13+1 RPAREN@14+1 RPAREN@15+1 RPAREN@16+1", 0, 0},
        {"!!!!!!!!1", "NOT@0+1 NOT@1+1 NOT@2+1 NOT@3+1 NOT@4+1 NOT@5+1 NOT@6+1 NOT@7+1 NUM@8+1=10", 0, 0},
        {"!!!!!!!!!1", "NOT@0+1 NOT@1+1 NOT@2+1 NOT@3+1 NOT@4+1 NOT@5+1 NOT@6+1 NOT@7+1 NOT@8+1 NUM@9+1=10", 0, 0},
        {"((((!!!!1))))", "LPAREN@0+1 LPAREN@1+1 LPAREN@2+1 LPAREN@3+1 NOT@4+1 NOT@5+1 NOT@6+1 NOT@7+1 NUM@8+1=10 RPAREN@9+1 RPAREN@10+1 RPAREN@11+1 RPAREN@12+1", 0, 0},
        {"(((((!!!!1)))))", "LPAREN@0+1 LPAREN@1+1 LPAREN@2+1 LPAREN@3+1 LPAREN@4+1 NOT@5+1 NOT@6+1 NOT@7+1 NOT@8+1 NUM@9+1=10 RPAREN@10+1 RPAREN@11+1 RPAREN@12+1 RPAREN@13+1 RPAREN@14+1", 0, 0},
        {"((((!!!!!1))))", "LPAREN@0+1 LPAREN@1+1 LPAREN@2+1 LPAREN@3+1 NOT@4+1 NOT@5+1 NOT@6+1 NOT@7+1 NOT@8+1 NUM@9+1=10 RPAREN@10+1 RPAREN@11+1 RPAREN@12+1 RPAREN@13+1", 0, 0},
        {"(!(!(!(!(!(!(!(!(1))))))))", "LPAREN@0+1 NOT@1+1 LPAREN@2+1 NOT@3+1 LPAREN@4+1 NOT@5+1 LPAREN@6+1 NOT@7+1 LPAREN@8+1 NOT@9+1 LPAREN@10+1 NOT@11+1 LPAREN@12+1 NOT@13+1 LPAREN@14+1 NOT@15+1 LPAREN@16+1 NUM@17+1=10 RPAREN@18+1 RPAREN@19+1 RPAREN@20+1 RPAREN@21+1 RPAREN@22+1 RPAREN@23+1 RPAREN@24+1 RPAREN@25+1", 0, 0},
        {"(!(!(!(!(!(!(!(!(!(1)))))))))", "LPAREN@0+1 NOT@1+1 LPAREN@2+1 NOT@3+1 LPAREN@4+1 NOT@5+1 LPAREN@6+1 NOT@7+1 LPAREN@8+1 NOT@9+1 LPAREN@10+1 NOT@11+1 LPAREN@12+1 NOT@13+1 LPAREN@14+1 NOT@15+1 LPAREN@16+1 NOT@17+1 LPAREN@18+1 NUM@19+1=10 RPAREN@20+1 RPAREN@21+1 RPAREN@22+1 RPAREN@23+1 RPAREN@24+1 RPAREN@25+1 RPAREN@26+1 RPAREN@27+1 RPAREN@28+1", 0, 0},
        {"1 & (((((((1)))))))", "NUM@0+1=10 AND@2+1 LPAREN@4+1 LPAREN@5+1 LPAREN@6+1 LPAREN@7+1 LPAREN@8+1 LPAREN@9+1 LPAREN@10+1 NUM@11+1=10 RPAREN@12+1 RPAREN@13+1 RPAREN@14+1 RPAREN@15+1 RPAREN@16+1 RPAREN@17+1 RPAREN@18+1", 0, 0},
        {"1 & ((((((((1))))))))", "NUM@0+1=10 AND@2+1 LPAREN@4+1 LPAREN@5+1 LPAREN@6+1 LPAREN@7+1 LPAREN@8+1 LPAREN@9+1 LPAREN@10+1 LPAREN@11+1 NUM@12+1=10 RPAREN@13+1 RPAREN@14+1 RPAREN@15+1 RPAREN@16+1 RPAREN@17+1 RPAREN@18+1 RPAREN@19+1 RPAREN@20+1", 0, 0},
    };

    /* a block of exactly n bytes: reading past it is an error */
    static char *exact(const char *s, size_t n) {
        char *p = malloc(n ? n : 1);
        memcpy(p, s, n);
        return p;
    }

    static const char *dump(const rt_token *t, int n) {
        static char out[2048];
        size_t len = 0;
        int i;
        out[0] = '\0';
        for (i = 0; i < n; i++) {
            len += (size_t)sprintf(out + len, "%s%s@%d+%d", i ? " " : "", KIND[t[i].kind], (int)t[i].pos, (int)t[i].len);
            if (t[i].kind == RT_NUM) len += (size_t)sprintf(out + len, "=%d", (int)t[i].value);
            else CHECK_INT(t[i].value, 0);
        }
        return out;
    }

    static void test_eval_table(void) {
        size_t i;
        for (i = 0; i < sizeof EVAL_CASES / sizeof EVAL_CASES[0]; i++) {
            const eval_case *c = &EVAL_CASES[i];
            size_t n = strlen(c->src);
            char *p = exact(c->src, n);
            int32_t res = 0x5A5A5A5;
            rt_err err = {-1, 99999};
            int rc = rt_eval(p, n, VARS, NVARS, &res, &err);
            if (c->ok) {
                CHECK_INT_CTX(c->src, rc, 0);
                CHECK_INT_CTX(c->src, res, c->value);
            } else {
                CHECK_INT_CTX(c->src, rc, -1);
                CHECK_INT_CTX(c->src, err.code, c->code);
                CHECK_INT_CTX(c->src, err.pos, c->pos);
                CHECK_INT_CTX(c->src, res, 0x5A5A5A5);
            }
            free(p);
        }
    }

    static void test_tokenize_table(void) {
        size_t i;
        for (i = 0; i < sizeof TOK_CASES / sizeof TOK_CASES[0]; i++) {
            const tok_case *c = &TOK_CASES[i];
            size_t n = strlen(c->src);
            char *p = exact(c->src, n);
            rt_token toks[64];
            rt_err err = {-1, 99999};
            int rc = rt_tokenize(p, n, toks, 64, &err);
            if (c->dump) {
                CHECK_INT_CTX(c->src, rc >= 0, 1);
                if (rc >= 0) CHECK_STR_CTX(c->src, dump(toks, rc), c->dump);
            } else {
                CHECK_INT_CTX(c->src, rc, -1);
                CHECK_INT_CTX(c->src, err.code, c->code);
                CHECK_INT_CTX(c->src, err.pos, c->pos);
            }
            free(p);
        }
    }

    static void test_token_limits(void) {
        rt_token toks[8];
        rt_err err = {0, 0};
        CHECK_INT(rt_tokenize("a b c", 5, toks, 3, &err), 3);
        CHECK_STR(dump(toks, 3), "IDENT@0+1 IDENT@2+1 IDENT@4+1");
        CHECK_INT(rt_tokenize("a b c", 5, toks, 2, &err), -1);
        CHECK_INT(err.code, RT_E_TOOMANY);
        CHECK_INT(err.pos, 4);
        CHECK_INT(rt_tokenize("a b c", 5, toks, 0, &err), -1);
        CHECK_INT(err.pos, 0);
        CHECK_INT(rt_tokenize("", 0, toks, 0, &err), 0);
        CHECK_INT(rt_tokenize("   ", 3, toks, 0, &err), 0);
        CHECK_INT(rt_tokenize("<=", 2, toks, 1, &err), 1);
        CHECK_INT(rt_tokenize("<= <", 4, toks, 1, &err), -1);
        CHECK_INT(err.pos, 3);
        /* err may be NULL */
        CHECK_INT(rt_tokenize("a b c", 5, toks, 2, NULL), -1);
        CHECK_INT(rt_tokenize("a #", 3, toks, 8, NULL), -1);
        CHECK_INT(rt_tokenize("a b", 3, toks, 8, NULL), 2);
        /* only the first n characters count */
        CHECK_INT(rt_tokenize("abc def", 3, toks, 8, NULL), 1);
        CHECK_STR(dump(toks, 1), "IDENT@0+3");
        CHECK_INT(rt_tokenize("12.5", 2, toks, 8, NULL), 1);
        CHECK_STR(dump(toks, 1), "NUM@0+2=120");
        CHECK_INT(rt_tokenize("12.5", 3, toks, 8, &err), -1);
        CHECK_INT(err.code, RT_E_TOKEN);
        CHECK_INT(err.pos, 2);
        CHECK_INT(rt_tokenize("a <= b", 3, toks, 8, NULL), 2);
        CHECK_STR(dump(toks, 2), "IDENT@0+1 LT@2+1");
        CHECK_INT(rt_tokenize("a <= b", 4, toks, 8, NULL), 2);
        CHECK_STR(dump(toks, 2), "IDENT@0+1 LE@2+2");
        CHECK_INT(rt_tokenize("a <= b", 5, toks, 8, NULL), 2);
        CHECK_INT(rt_tokenize("a <= b", 6, toks, 8, NULL), 3);
    }

    static void test_eval_misc(void) {
        int32_t res = -7;
        rt_err err = {0, 0};
        static const rt_var dup[] = {{"d", 1}, {"d", 2}, {"dd", 3}};
        static const rt_var pre[] = {{"temp", 1}, {"temperature", 2}, {"t", 3}};
        CHECK_INT(rt_eval("d", 1, dup, 3, &res, &err), 0);
        CHECK_INT(res, 1);
        CHECK_INT(rt_eval("dd", 2, dup, 3, &res, &err), 0);
        CHECK_INT(res, 3);
        CHECK_INT(rt_eval("temp", 4, pre, 3, &res, &err), 0);
        CHECK_INT(res, 1);
        CHECK_INT(rt_eval("temperature", 11, pre, 3, &res, &err), 0);
        CHECK_INT(res, 2);
        CHECK_INT(rt_eval("t", 1, pre, 3, &res, &err), 0);
        CHECK_INT(res, 3);
        CHECK_INT(rt_eval("tem", 3, pre, 3, &res, &err), -1);
        CHECK_INT(err.code, RT_E_VAR);
        CHECK_INT(err.pos, 0);
        CHECK_INT(rt_eval("1 < 2", 5, NULL, 0, &res, &err), 0);
        CHECK_INT(res, 1);
        CHECK_INT(rt_eval("x", 1, NULL, 0, &res, &err), -1);
        CHECK_INT(err.code, RT_E_VAR);
        /* only the first n characters are the rule */
        CHECK_INT(rt_eval("1 < 2 junk #", 5, NULL, 0, &res, &err), 0);
        CHECK_INT(res, 1);
        CHECK_INT(rt_eval("1 < 2 junk", 7, NULL, 0, &res, &err), -1);
        CHECK_INT(err.code, RT_E_SYNTAX);
        CHECK_INT(err.pos, 6);
        CHECK_INT(rt_eval("1 <", 3, NULL, 0, &res, &err), -1);
        CHECK_INT(err.pos, 3);
        CHECK_INT(rt_eval("1 < 22", 3, NULL, 0, &res, &err), -1);
        CHECK_INT(err.pos, 3);
        /* err may be NULL */
        CHECK_INT(rt_eval("1 <", 3, NULL, 0, &res, NULL), -1);
        CHECK_INT(rt_eval("1 < 2", 5, NULL, 0, &res, NULL), 0);
        CHECK_INT(rt_eval("#", 1, NULL, 0, &res, NULL), -1);
        CHECK_INT(rt_eval("a", 1, NULL, 0, &res, NULL), -1);
    }

    int main(void) {
        h_init();
        test_eval_table();
        test_tokenize_table();
        test_token_limits();
        test_eval_misc();
        return h_report();
    }
''')

LIB = Lib(
    name="ruletok", lang="c", title="the greenhouse rule evaluator",
    blurb="The greenhouse controller lets growers write alarm rules such as `temp >= 30.5 & !vent_open` and evaluates them against the latest sensor readings with this library.",
    files={"README.md": README1, "include/ruletok.h": F2, "src/ruletok.c": F3},
    visible_tests={"tests/test_main.c": V4, "tests/harness.h": _lang3.C_HARNESS},
    hidden_tests={"tests/test_main.c": H5},
    mutate=["src/ruletok.c"], difficulty=4, tags=["tokenizer", "parser", "expression"],
    verify=_lang3.C_VERIFY,
)

_lang3.add(LIB, n=8)
