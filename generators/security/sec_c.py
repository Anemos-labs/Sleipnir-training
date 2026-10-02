"""Security family: memory safety bugs in C (buffer overflows, format strings, integer overflows, use-after-free). Hidden tests run under
AddressSanitizer and UndefinedBehaviorSanitizer with exact-size heap buffers, so every out-of-bounds access or undefined behaviour aborts the run."""
from fx import dd, family

from . import _sec
from ._sec import patched, readme

VERIFY = ("mkdir -p build && gcc -std=c11 -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=all -Wall -Wextra -Iinclude -Isrc -o build/tests $(find src tests -name '*.c') "
          "&& ASAN_OPTIONS=detect_leaks=0:allocator_may_return_null=1 UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=0 ./build/tests")

CT = dd(r'''
    #include <stdint.h>
    #include <stdio.h>
    #include <stdlib.h>
    #include <string.h>

    static int failures;
    #define CHECK(cond) do { if (!(cond)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); failures++; } } while (0)

    /* exact-size heap copy: any access past the end is reported by AddressSanitizer */
    static char *heap_copy(const char *s) {
        size_t n = strlen(s) + 1;
        char *p = malloc(n);
        memcpy(p, s, n);
        return p;
    }

    static uint8_t *heap_bytes(const uint8_t *s, size_t n) {
        uint8_t *p = malloc(n ? n : 1);
        if (n) memcpy(p, s, n);
        return p;
    }

''')

SC = []


def task(slug, d, product, func, cwe, finding, headers, sources, readme_text, solution, test, tags=None):
    start = {**headers, **sources, "README.md": readme(slug, readme_text)}
    return dict(slug=slug, d=d, lang="c", product=product, func=func, cwe=cwe, finding=finding, start=start, solution=solution,
                hidden={f"tests/test_{slug.replace('-', '_')}.c": CT + dd(test)}, verify=VERIFY, tags=tags or [])


# ---------------------------------------------------------------------------------------------------------------------------------
GREET_H = dd(r'''
    #ifndef GREET_H
    #define GREET_H
    #include <stddef.h>

    /* Writes "Hello, <name>!" into out (capacity cap bytes). Returns the length the complete greeting has, like snprintf. The output is cut to fit and
       always NUL-terminated when cap > 0; with cap == 0 nothing is written (out may be NULL). */
    int greet(char *out, size_t cap, const char *name);

    #endif
''')
GREET_C = dd(r'''
    #include "greet.h"
    #include <string.h>

    int greet(char *out, size_t cap, const char *name) {
        (void)cap;
        strcpy(out, "Hello, ");
        strcat(out, name);
        strcat(out, "!");
        return (int)strlen(out);
    }
''')
SC.append(task("greeting-strcpy", 1, "the kiosk greeter", "greet", "CWE-120",
               "`greet` builds the greeting with `strcpy`/`strcat` and ignores the capacity it was given, so a long name (names come from a badge scanner) overflows the caller's buffer on the heap.",
               {"include/greet.h": GREET_H}, {"src/greet.c": GREET_C},
               "`greet(out, cap, name)` behaves exactly like `snprintf(out, cap, \"Hello, %s!\", name)`: it never writes more than `cap` bytes, truncates, always terminates, and returns the untruncated length (11 for `Ann`). `cap == 0` writes nothing and `out` may be NULL. Build and tests run under AddressSanitizer.",
               {"src/greet.c": patched(GREET_C, ('#include <string.h>\n', '#include <stdio.h>\n'), (
                   '''    (void)cap;
    strcpy(out, "Hello, ");
    strcat(out, name);
    strcat(out, "!");
    return (int)strlen(out);
''', '''    return snprintf(out, cap, "Hello, %s!", name);
'''))},
               r'''
    #include "greet.h"

    int main(void) {
        char *a = malloc(32);
        CHECK(greet(a, 32, "Ann") == 11);
        CHECK(strcmp(a, "Hello, Ann!") == 0);
        free(a);
        a = malloc(12);
        CHECK(greet(a, 12, "Ann") == 11);
        CHECK(strcmp(a, "Hello, Ann!") == 0);
        free(a);
        a = malloc(8);
        CHECK(greet(a, 8, "Alexander") == 17);
        CHECK(strcmp(a, "Hello, ") == 0);
        free(a);
        a = malloc(1);
        CHECK(greet(a, 1, "Bob") == 11);
        CHECK(a[0] == 0);
        free(a);
        CHECK(greet(NULL, 0, "Bob") == 11);
        char *big = malloc(5001);
        memset(big, 'x', 5000);
        big[5000] = 0;
        a = malloc(16);
        CHECK(greet(a, 16, big) == 5008);
        CHECK(strlen(a) == 15);
        CHECK(memcmp(a, "Hello, xxxxxxxx", 15) == 0);
        free(a);
        free(big);
        a = malloc(9);
        CHECK(greet(a, 9, "") == 8);
        CHECK(strcmp(a, "Hello, !") == 0);
        free(a);
        return failures ? 1 : 0;
    }
'''))

LOGLINE_H = dd(r'''
    #ifndef LOGLINE_H
    #define LOGLINE_H
    #include <stddef.h>

    /* Copies the message text verbatim into out (capacity cap) as one log line. The text comes from users: '%' and every other character are ordinary data.
       Returns strlen(out), the number of characters stored; the line is truncated to cap - 1 characters and NUL-terminated. cap == 0 writes nothing and returns 0. */
    size_t log_line(char *out, size_t cap, const char *text);

    #endif
''')
LOGLINE_C = dd(r'''
    #include "logline.h"
    #include <stdio.h>
    #include <string.h>

    size_t log_line(char *out, size_t cap, const char *text) {
        if (cap == 0)
            return 0;
        snprintf(out, cap, text);
        return strlen(out);
    }
''')
SC.append(task("log-format-string", 1, "the support console log", "log_line", "CWE-134",
               "`log_line` passes the user's text to `snprintf` as the *format string*: a message such as `%s%s%s%s` reads garbage from the stack (crash or leak), `%n` writes to memory, and any `%` in a legitimate message is mangled.",
               {"include/logline.h": LOGLINE_H}, {"src/logline.c": LOGLINE_C},
               "`log_line(out, cap, text)` copies the text byte for byte (truncated to `cap - 1` characters, always NUL-terminated) and returns the number of characters stored. Texts such as `100%`, `%s%s%s`, `%n%n` and `%x %x` come out unchanged.",
               {"src/logline.c": patched(LOGLINE_C, ('snprintf(out, cap, text);', 'snprintf(out, cap, "%s", text);'))},
               r'''
    #include "logline.h"

    int main(void) {
        const char *texts[] = {"plain text", "100%", "%s%s%s%s", "%n%n", "%x %x %x %x", "%d", "%", "%%", "a%sb%nc", "%.1000000d", "%99999999999s", ""};
        for (size_t i = 0; i < sizeof texts / sizeof *texts; i++) {
            size_t cap = strlen(texts[i]) + 1;
            char *out = malloc(cap);
            CHECK(log_line(out, cap, texts[i]) == strlen(texts[i]));
            CHECK(strcmp(out, texts[i]) == 0);
            free(out);
        }
        char *out = malloc(6);
        CHECK(log_line(out, 6, "%s%s%s%s%s%s%s") == 5);
        CHECK(memcmp(out, "%s%s%", 6) == 0);
        free(out);
        out = malloc(1);
        CHECK(log_line(out, 1, "abc") == 0);
        CHECK(out[0] == 0);
        free(out);
        CHECK(log_line(NULL, 0, "%s") == 0);
        return failures ? 1 : 0;
    }
'''))

PREFIX_H = dd(r'''
    #ifndef PREFIX_H
    #define PREFIX_H
    #include <stddef.h>

    /* Sum of the first `count` elements of a[0..n-1]; when count > n only the n existing elements are summed. */
    long sum_prefix(const int *a, size_t n, size_t count);

    #endif
''')
PREFIX_C = dd(r'''
    #include "prefix.h"

    long sum_prefix(const int *a, size_t n, size_t count) {
        size_t m = count > n ? n : count;
        long sum = 0;
        for (size_t i = 0; i <= m; i++)
            sum += a[i];
        return sum;
    }
''')
SC.append(task("prefix-fencepost", 1, "the statistics widget", "sum_prefix", "CWE-193",
               "`sum_prefix` loops with `i <= m` instead of `i < m`: it adds one element too many (wrong totals) and when the whole array is requested it reads one `int` past the end of the buffer.",
               {"include/prefix.h": PREFIX_H}, {"src/prefix.c": PREFIX_C},
               "`sum_prefix(a, n, count)` sums exactly `min(count, n)` elements. `count == 0` and `n == 0` give 0 (and `a` may then be NULL).",
               {"src/prefix.c": patched(PREFIX_C, ('i <= m', 'i < m'))},
               r'''
    #include "prefix.h"

    int main(void) {
        int src[5] = {1, 2, 3, 4, 5};
        int *a = malloc(sizeof src);
        memcpy(a, src, sizeof src);
        CHECK(sum_prefix(a, 5, 5) == 15);
        CHECK(sum_prefix(a, 5, 100) == 15);
        CHECK(sum_prefix(a, 5, 3) == 6);
        CHECK(sum_prefix(a, 5, 1) == 1);
        CHECK(sum_prefix(a, 5, 0) == 0);
        free(a);
        CHECK(sum_prefix(NULL, 0, 4) == 0);
        int *one = malloc(sizeof(int));
        one[0] = -7;
        CHECK(sum_prefix(one, 1, 1) == -7);
        CHECK(sum_prefix(one, 1, 0) == 0);
        free(one);
        return failures ? 1 : 0;
    }
'''))

SCORE_H = dd(r'''
    #ifndef SCORE_H
    #define SCORE_H
    #include <stddef.h>

    /* Reads scores[index] into *out and returns 0 when 0 <= index < n. For any other index (negative, n, beyond) returns -1 and leaves *out untouched. */
    int score_at(const int *scores, size_t n, long index, int *out);

    #endif
''')
SCORE_C = dd(r'''
    #include "score.h"

    int score_at(const int *scores, size_t n, long index, int *out) {
        if (index > (long)n)
            return -1;
        *out = scores[index];
        return 0;
    }
''')
SC.append(task("score-index", 1, "the leaderboard", "score_at", "CWE-125",
               "`score_at` only rejects indexes greater than `n` (so `n` itself is accepted) and never looks at negative indexes: `/scores/-1` and `/scores/5` on a five-element table read memory next to the array.",
               {"include/score.h": SCORE_H}, {"src/score.c": SCORE_C},
               "`score_at(scores, n, index, out)` accepts exactly the indexes `0 .. n-1`. Everything else returns -1 without touching `*out`; `n == 0` accepts nothing.",
               {"src/score.c": patched(SCORE_C, ('    if (index > (long)n)\n', '    if (index < 0 || (unsigned long)index >= n)\n'))},
               r'''
    #include <limits.h>
    #include "score.h"

    int main(void) {
        int src[5] = {10, 20, 30, 40, 50};
        int *s = malloc(sizeof src);
        memcpy(s, src, sizeof src);
        int out = -99;
        for (long i = 0; i < 5; i++) {
            CHECK(score_at(s, 5, i, &out) == 0);
            CHECK(out == src[i]);
        }
        out = -99;
        long bad[] = {5, 6, 100, -1, -5, LONG_MAX, LONG_MIN, 1L << 40};
        for (size_t i = 0; i < sizeof bad / sizeof *bad; i++) {
            CHECK(score_at(s, 5, bad[i], &out) == -1);
            CHECK(out == -99);
        }
        free(s);
        CHECK(score_at(NULL, 0, 0, &out) == -1);
        CHECK(out == -99);
        return failures ? 1 : 0;
    }
'''))

# ---------------------------------------------------------------------------------------------------------------------------------
PATH_H = dd(r'''
    #ifndef PATHJOIN_H
    #define PATHJOIN_H
    #include <stddef.h>

    /* Writes "dir/file" into out (capacity cap) and returns 0. A '/' is inserted only when dir is non-empty and does not already end with one:
       ("a", "b") -> "a/b", ("a/", "b") -> "a/b", ("", "b") -> "b", ("/", "b") -> "/b". When the result including its NUL terminator does not fit into cap bytes, returns -1
       and writes nothing but out[0] = 0 (only if cap > 0). */
    int join_path(char *out, size_t cap, const char *dir, const char *file);

    #endif
''')
PATH_C = dd(r'''
    #include "pathjoin.h"
    #include <string.h>

    int join_path(char *out, size_t cap, const char *dir, const char *file) {
        size_t dl = strlen(dir), fl = strlen(file);
        int slash = dl > 0 && dir[dl - 1] != '/';
        if (dl + slash + fl > cap) {
            if (cap > 0)
                out[0] = 0;
            return -1;
        }
        memcpy(out, dir, dl);
        if (slash)
            out[dl] = '/';
        memcpy(out + dl + slash, file, fl);
        out[dl + slash + fl] = 0;
        return 0;
    }
''')
SC.append(task("join-path-boundary", 2, "the file browser", "join_path", "CWE-193",
               "`join_path` compares the length of the result with the capacity but forgets the terminating NUL: when the joined path is exactly `cap` characters long, the NUL is written one byte past the end of the buffer.",
               {"include/pathjoin.h": PATH_H}, {"src/pathjoin.c": PATH_C},
               "`join_path` follows the header comment: success when `len + 1 <= cap`, otherwise -1 with `out[0] = 0` (`cap == 0` writes nothing at all). The result for fitting inputs is unchanged.",
               {"src/pathjoin.c": patched(PATH_C, ('dl + slash + fl > cap', 'dl + slash + fl >= cap'))},
               r'''
    #include "pathjoin.h"

    static void run(const char *dir, const char *file, const char *want) {
        size_t need = strlen(want) + 1;
        char *out = malloc(need);
        CHECK(join_path(out, need, dir, file) == 0);
        CHECK(strcmp(out, want) == 0);
        free(out);
        if (need > 1) {
            out = malloc(need - 1);
            CHECK(join_path(out, need - 1, dir, file) == -1);
            CHECK(out[0] == 0);
            free(out);
        }
        out = malloc(need + 10);
        CHECK(join_path(out, need + 10, dir, file) == 0);
        CHECK(strcmp(out, want) == 0);
        free(out);
    }

    int main(void) {
        run("a", "b", "a/b");
        run("a/", "b", "a/b");
        run("", "b", "b");
        run("/", "b", "/b");
        run("/usr/local", "bin", "/usr/local/bin");
        run("dir/", "", "dir/");
        run("dir", "", "dir/");
        run("", "", "");
        run("/var/log/", "syslog.1", "/var/log/syslog.1");
        char *one = malloc(1);
        CHECK(join_path(one, 1, "", "") == 0);
        CHECK(one[0] == 0);
        CHECK(join_path(one, 1, "a", "") == -1);
        CHECK(one[0] == 0);
        free(one);
        CHECK(join_path(NULL, 0, "a", "b") == -1);
        return failures ? 1 : 0;
    }
'''))

KV_H = dd(r'''
    #ifndef KV_H
    #define KV_H
    #include <stddef.h>

    /* Splits "key=value" at the FIRST '=' and copies the parts into key (capacity keycap) and val (capacity valcap), both NUL-terminated. The value may contain further '='.
       Returns 0 on success. Returns -1 when there is no '=', the key is empty, or key or value (plus its NUL) does not fit its buffer; then key[0] and val[0] are set to 0
       (for capacities > 0) and nothing else is written. */
    int parse_kv(const char *line, char *key, size_t keycap, char *val, size_t valcap);

    #endif
''')
KV_C = dd(r'''
    #include "kv.h"
    #include <string.h>

    int parse_kv(const char *line, char *key, size_t keycap, char *val, size_t valcap) {
        const char *eq = strchr(line, '=');
        (void)keycap;
        (void)valcap;
        if (eq == NULL || eq == line) {
            if (keycap > 0) key[0] = 0;
            if (valcap > 0) val[0] = 0;
            return -1;
        }
        memcpy(key, line, (size_t)(eq - line));
        key[eq - line] = 0;
        strcpy(val, eq + 1);
        return 0;
    }
''')
SC.append(task("config-line-parser", 2, "the config loader", "parse_kv", "CWE-120",
               "`parse_kv` copies the key and the value with `memcpy`/`strcpy` into the caller's buffers without looking at the capacities it receives, so a config line with a long key or value overflows the (fixed-size, often stack) buffers of the caller.",
               {"include/kv.h": KV_H}, {"src/kv.c": KV_C},
               "`parse_kv` honours `keycap` and `valcap` as described in the header: too-long keys or values are an error (-1, both buffers emptied), never a truncation, and nothing is ever written beyond the capacities.",
               {"src/kv.c": patched(KV_C, (
                   '''    (void)keycap;
    (void)valcap;
    if (eq == NULL || eq == line) {
''', '''    size_t kl = eq ? (size_t)(eq - line) : 0;
    size_t vl = eq ? strlen(eq + 1) : 0;
    if (eq == NULL || eq == line || kl + 1 > keycap || vl + 1 > valcap) {
'''), (
                   '''    memcpy(key, line, (size_t)(eq - line));
    key[eq - line] = 0;
    strcpy(val, eq + 1);
''', '''    memcpy(key, line, kl);
    key[kl] = 0;
    memcpy(val, eq + 1, vl + 1);
'''))},
               r'''
    #include "kv.h"

    static int run(const char *line, size_t keycap, size_t valcap, const char *want_key, const char *want_val) {
        char *key = malloc(keycap ? keycap : 1), *val = malloc(valcap ? valcap : 1);
        int rc = parse_kv(line, key, keycap, val, valcap);
        if (want_key) {
            CHECK(rc == 0);
            CHECK(strcmp(key, want_key) == 0);
            CHECK(strcmp(val, want_val) == 0);
        } else {
            CHECK(rc == -1);
            if (keycap) CHECK(key[0] == 0);
            if (valcap) CHECK(val[0] == 0);
        }
        free(key);
        free(val);
        return rc;
    }

    int main(void) {
        run("name=value", 5, 6, "name", "value");
        run("name=value", 100, 100, "name", "value");
        run("a=b=c", 2, 4, "a", "b=c");
        run("empty=", 6, 1, "empty", "");
        run("k= spaced value ", 2, 20, "k", " spaced value ");
        run("name=value", 4, 6, NULL, NULL);
        run("name=value", 5, 5, NULL, NULL);
        run("name=value", 1, 100, NULL, NULL);
        run("=value", 10, 10, NULL, NULL);
        run("novalue", 10, 10, NULL, NULL);
        run("", 10, 10, NULL, NULL);
        run("k=" "0123456789012345678901234567890123456789", 2, 40, NULL, NULL);
        run("k=" "0123456789012345678901234567890123456789", 2, 41, "k", "0123456789012345678901234567890123456789");
        run("longkeylongkeylongkey=v", 8, 8, NULL, NULL);
        char *k = malloc(1), *v = malloc(1);
        CHECK(parse_kv("=", k, 1, v, 1) == -1);
        CHECK(parse_kv("x=", k, 1, v, 1) == -1);
        free(k);
        free(v);
        return failures ? 1 : 0;
    }
'''))

COPY_H = dd(r'''
    #ifndef FIELD_H
    #define FIELD_H
    #include <stddef.h>

    /* Copies src into dst (capacity cap), cutting it to cap - 1 characters when it is longer. dst is always NUL-terminated when cap > 0; cap == 0 does nothing. */
    void copy_field(char *dst, size_t cap, const char *src);

    #endif
''')
COPY_C = dd(r'''
    #include "field.h"
    #include <string.h>

    void copy_field(char *dst, size_t cap, const char *src) {
        strncpy(dst, src, cap);
    }
''')
SC.append(task("strncpy-terminator", 2, "the address book", "copy_field", "CWE-170",
               "`copy_field` uses `strncpy(dst, src, cap)`, which does not terminate the destination when the source is `cap` characters or longer: every later `strlen`, `printf(\"%s\")` or `strcpy` on the field runs off the end of the buffer.",
               {"include/field.h": COPY_H}, {"src/field.c": COPY_C},
               "`copy_field(dst, cap, src)` copies at most `cap - 1` characters and always writes the terminating NUL (for `cap > 0`). Sources that fit are copied unchanged; `cap == 0` writes nothing.",
               {"src/field.c": patched(COPY_C, (
                   '    strncpy(dst, src, cap);\n', '''    if (cap == 0)
        return;
    strncpy(dst, src, cap - 1);
    dst[cap - 1] = 0;
'''))},
               r'''
    #include "field.h"

    int main(void) {
        const char *src = "0123456789";
        for (size_t cap = 1; cap <= 14; cap++) {
            char *dst = malloc(cap);
            memset(dst, 'Z', cap);
            copy_field(dst, cap, src);
            size_t want = strlen(src) < cap - 1 ? strlen(src) : cap - 1;
            CHECK(strlen(dst) == want);
            CHECK(memcmp(dst, src, want) == 0);
            free(dst);
        }
        char *d = malloc(1);
        d[0] = 'x';
        copy_field(d, 1, "abc");
        CHECK(d[0] == 0);
        free(d);
        char *keep = malloc(3);
        memcpy(keep, "KK", 3);
        copy_field(keep, 0, "abc");
        CHECK(strcmp(keep, "KK") == 0);
        free(keep);
        char *e = malloc(4);
        copy_field(e, 4, "");
        CHECK(e[0] == 0);
        free(e);
        return failures ? 1 : 0;
    }
'''))

SPLIT_H = dd(r'''
    #ifndef SPLIT_H
    #define SPLIT_H
    #include <stddef.h>

    /* Splits `text` in place into words separated by one or more spaces (leading and trailing spaces are ignored). The separators are overwritten with NUL bytes, words[i] points to the i-th word.
       At most max_words pointers are stored in words[]; further words are ignored. Returns the number of words stored. */
    size_t split_words(char *text, char **words, size_t max_words);

    #endif
''')
SPLIT_C = dd(r'''
    #include "split.h"

    size_t split_words(char *text, char **words, size_t max_words) {
        size_t count = 0;
        char *p = text;
        (void)max_words;
        while (*p) {
            while (*p == ' ')
                *p++ = 0;
            if (!*p)
                break;
            words[count++] = p;
            while (*p && *p != ' ')
                p++;
        }
        return count;
    }
''')
SC.append(task("word-splitter", 2, "the command-line parser", "split_words", "CWE-787",
               "`split_words` stores a pointer for every word of the input and never checks `max_words`: a command line with more words than the caller's array has slots writes pointers past the end of that array.",
               {"include/split.h": SPLIT_H}, {"src/split.c": SPLIT_C},
               "`split_words` stores at most `max_words` pointers (extra words are ignored, `max_words == 0` stores nothing and returns 0); every stored word is still NUL-terminated in place. Words and separators behave as in the header comment.",
               {"src/split.c": patched(SPLIT_C, (
                   '''    (void)max_words;
    while (*p) {
        while (*p == ' ')
            *p++ = 0;
        if (!*p)
            break;
        words[count++] = p;
''', '''    while (*p) {
        while (*p == ' ')
            *p++ = 0;
        if (!*p)
            break;
        if (count < max_words)
            words[count++] = p;
'''))},
               r'''
    #include "split.h"

    static size_t run(const char *text, size_t max, const char **want, size_t nwant) {
        char *buf = heap_copy(text);
        char **words = malloc((max ? max : 1) * sizeof(char *));
        size_t n = split_words(buf, words, max);
        CHECK(n == nwant);
        for (size_t i = 0; i < n && i < nwant; i++)
            CHECK(strcmp(words[i], want[i]) == 0);
        free(words);
        free(buf);
        return n;
    }

    int main(void) {
        const char *w3[] = {"alpha", "beta", "gamma"};
        run("alpha beta gamma", 8, w3, 3);
        run("  alpha   beta  gamma  ", 3, w3, 3);
        run("alpha beta gamma delta epsilon", 3, w3, 3);
        run("alpha beta gamma", 3, w3, 3);
        const char *w2[] = {"alpha", "beta"};
        run("alpha beta gamma", 2, w2, 2);
        run("alpha", 0, w2, 0);
        const char *w1[] = {"alpha"};
        run("alpha beta", 1, w1, 1);
        run("", 4, w1, 0);
        run("     ", 4, w1, 0);
        char *many = malloc(2001);
        for (int i = 0; i < 1000; i++) {
            many[2 * i] = 'w';
            many[2 * i + 1] = ' ';
        }
        many[2000] = 0;
        char **words = malloc(5 * sizeof(char *));
        CHECK(split_words(many, words, 5) == 5);
        CHECK(strcmp(words[4], "w") == 0);
        free(words);
        free(many);
        return failures ? 1 : 0;
    }
'''))

# ---------------------------------------------------------------------------------------------------------------------------------
REPEAT_H = dd(r'''
    #ifndef REPEAT_H
    #define REPEAT_H
    #include <stddef.h>

    /* Returns a newly malloc'ed string made of `count` copies of `s` (the caller frees it); count == 0 or an empty s give "". Returns NULL when the result cannot be represented
       (its length plus the NUL would exceed SIZE_MAX) or the allocation fails. */
    char *repeat_string(const char *s, size_t count);

    #endif
''')
REPEAT_C = dd(r'''
    #include "repeat.h"
    #include <stdlib.h>
    #include <string.h>

    char *repeat_string(const char *s, size_t count) {
        size_t len = strlen(s);
        char *result = malloc(len * count + 1);
        for (size_t i = 0; i < count && len > 0; i++)
            memcpy(result + i * len, s, len);
        result[len * count] = 0;
        return result;
    }
''')
SC.append(task("repeat-allocation", 3, "the banner generator", "repeat_string", "CWE-190",
               "`repeat_string` computes the allocation size as `len * count + 1` without an overflow check: for `count = SIZE_MAX / 2 + 1` and a two-character string the product wraps to 0, `malloc(1)` succeeds, and the copy loop writes far beyond the one-byte block. Failed allocations are not checked either.",
               {"include/repeat.h": REPEAT_H}, {"src/repeat.c": REPEAT_C},
               "`repeat_string` returns NULL (writing nothing) whenever `len * count + 1` would overflow `size_t` or `malloc` fails, and otherwise the repeated string exactly as before. Strings of length 0 and counts of 0 give an allocated empty string.",
               {"src/repeat.c": patched(REPEAT_C, (
                   '''    char *result = malloc(len * count + 1);
    for (size_t i = 0; i < count && len > 0; i++)
''', '''    if (len > 0 && count > (SIZE_MAX - 1) / len)
        return NULL;
    char *result = malloc(len * count + 1);
    if (result == NULL)
        return NULL;
    for (size_t i = 0; i < count && len > 0; i++)
'''), ('#include <stdlib.h>\n', '#include <stdint.h>\n#include <stdlib.h>\n'))},
               r'''
    #include "repeat.h"

    int main(void) {
        char *r = repeat_string("ab", 3);
        CHECK(r && strcmp(r, "ababab") == 0);
        free(r);
        r = repeat_string("x", 0);
        CHECK(r && r[0] == 0);
        free(r);
        r = repeat_string("", 5);
        CHECK(r && r[0] == 0);
        free(r);
        r = repeat_string("-=", 1000);
        CHECK(r && strlen(r) == 2000 && r[1998] == '-' && r[1999] == '=');
        free(r);
        CHECK(repeat_string("ab", SIZE_MAX / 2 + 1) == NULL);
        CHECK(repeat_string("abc", SIZE_MAX / 3 + 2) == NULL);
        CHECK(repeat_string("abcd", SIZE_MAX / 4 + 1) == NULL);
        CHECK(repeat_string("x", SIZE_MAX) == NULL);
        CHECK(repeat_string("ab", SIZE_MAX / 4) == NULL);
        CHECK(repeat_string("xyz", (SIZE_MAX - 1) / 3 + 1) == NULL);
        return failures ? 1 : 0;
    }
'''))

JOIN_H = dd(r'''
    #ifndef JOIN_H
    #define JOIN_H
    #include <stddef.h>

    /* Joins the n strings of items with ", " and writes the result into out (capacity cap), cut to cap - 1 characters and NUL-terminated (cap == 0: nothing is written, out may be NULL).
       Returns the length of the COMPLETE joined text, whether or not it fitted (like snprintf). n == 0 gives "" and 0. */
    size_t join_items(char *out, size_t cap, const char *const *items, size_t n);

    #endif
''')
JOIN_C = dd(r'''
    #include "join.h"
    #include <stdio.h>

    size_t join_items(char *out, size_t cap, const char *const *items, size_t n) {
        size_t used = 0;
        if (cap > 0)
            out[0] = 0;
        for (size_t i = 0; i < n; i++)
            used += (size_t)snprintf(out + used, cap - used, "%s%s", i ? ", " : "", items[i]);
        return used;
    }
''')
SC.append(task("snprintf-accumulator", 3, "the report generator", "join_items", "CWE-787",
               "`join_items` adds the return value of `snprintf` (the length the output *would* have had) to its write position: as soon as one item does not fit, `used` exceeds `cap`, `cap - used` wraps to a huge number and the next `snprintf` writes to `out + used`, far outside the buffer.",
               {"include/join.h": JOIN_H}, {"src/join.c": JOIN_C},
               "`join_items` returns the full length but never writes more than `cap` bytes, wherever the truncation happens (inside an item, inside a separator, or between items). The text produced for fitting buffers is unchanged.",
               {"src/join.c": patched(JOIN_C, (
                   '''    size_t used = 0;
    if (cap > 0)
        out[0] = 0;
    for (size_t i = 0; i < n; i++)
        used += (size_t)snprintf(out + used, cap - used, "%s%s", i ? ", " : "", items[i]);
    return used;
''', '''    size_t used = 0;
    if (cap > 0)
        out[0] = 0;
    for (size_t i = 0; i < n; i++) {
        size_t room = used < cap ? cap - used : 0;
        char *dst = room ? out + used : NULL;
        int w = snprintf(dst, room, "%s%s", i ? ", " : "", items[i]);
        used += (size_t)w;
    }
    return used;
'''))},
               r'''
    #include "join.h"

    int main(void) {
        const char *items[] = {"alpha", "beta", "gamma"};
        const char *full = "alpha, beta, gamma";
        size_t flen = strlen(full);
        CHECK(flen == 18);
        for (size_t cap = 1; cap <= 24; cap++) {
            char *out = malloc(cap);
            memset(out, 'Z', cap);
            CHECK(join_items(out, cap, items, 3) == flen);
            size_t shown = flen < cap - 1 ? flen : cap - 1;
            CHECK(strlen(out) == shown);
            CHECK(memcmp(out, full, shown) == 0);
            free(out);
        }
        CHECK(join_items(NULL, 0, items, 3) == flen);
        char *out = malloc(1);
        out[0] = 'Z';
        CHECK(join_items(out, 1, items, 0) == 0);
        CHECK(out[0] == 0);
        free(out);
        const char *one[] = {"solo"};
        out = malloc(5);
        CHECK(join_items(out, 5, one, 1) == 4);
        CHECK(strcmp(out, "solo") == 0);
        free(out);
        const char *longitems[] = {"a-rather-long-first-item", "second", "third-item-here", "x", "y", "z"};
        out = malloc(10);
        size_t want = strlen("a-rather-long-first-item") + 2 + 6 + 2 + 15 + 2 + 1 + 2 + 1 + 2 + 1;
        CHECK(join_items(out, 10, longitems, 6) == want);
        CHECK(strcmp(out, "a-rather-") == 0);
        free(out);
        return failures ? 1 : 0;
    }
'''))

SB_H = dd(r'''
    #ifndef STRBUF_H
    #define STRBUF_H
    #include <stddef.h>

    typedef struct {
        char *data;
        size_t len;   /* characters stored, without the NUL */
        size_t cap;   /* bytes allocated */
    } StrBuf;

    void sb_init(StrBuf *sb);
    /* Appends the n bytes at s. Returns 0 on success; -1 (and leaves the buffer unchanged) when the new size cannot be represented or the allocation fails. The contents stay NUL-terminated. */
    int sb_append(StrBuf *sb, const char *s, size_t n);
    const char *sb_str(const StrBuf *sb);
    void sb_free(StrBuf *sb);

    #endif
''')
SB_C = dd(r'''
    #include "strbuf.h"
    #include <stdlib.h>
    #include <string.h>

    void sb_init(StrBuf *sb) {
        sb->data = NULL;
        sb->len = 0;
        sb->cap = 0;
    }

    int sb_append(StrBuf *sb, const char *s, size_t n) {
        if (sb->len + n + 1 > sb->cap) {
            size_t cap = sb->cap ? sb->cap * 2 : 16;
            char *grown = realloc(sb->data, cap);
            if (grown == NULL)
                return -1;
            sb->data = grown;
            sb->cap = cap;
        }
        memcpy(sb->data + sb->len, s, n);
        sb->len += n;
        sb->data[sb->len] = 0;
        return 0;
    }

    const char *sb_str(const StrBuf *sb) {
        return sb->data ? sb->data : "";
    }

    void sb_free(StrBuf *sb) {
        free(sb->data);
        sb_init(sb);
    }
''')
SC.append(task("string-builder-growth", 3, "the template renderer", "sb_append", "CWE-122",
               "`sb_append` doubles the capacity once when the new text does not fit, but a single append can be much larger than the doubled capacity (a 10 KB chunk into a 16-byte buffer): `memcpy` then writes far past the end of the block. `len + n + 1` is not checked for overflow either.",
               {"include/strbuf.h": SB_H}, {"src/strbuf.c": SB_C},
               "`sb_append` grows the buffer until `len + n + 1` bytes fit (doubling, starting at 16), checks every size computation for overflow and every allocation for failure, and then behaves as before. On failure the builder is unchanged and still usable.",
               {"src/strbuf.c": patched(SB_C, ('#include <stdlib.h>\n', '#include <stdint.h>\n#include <stdlib.h>\n'), (
                   '''    if (sb->len + n + 1 > sb->cap) {
        size_t cap = sb->cap ? sb->cap * 2 : 16;
        char *grown''', '''    if (n > SIZE_MAX - sb->len - 1)
        return -1;
    if (sb->len + n + 1 > sb->cap) {
        size_t cap = sb->cap ? sb->cap : 16;
        while (cap < sb->len + n + 1) {
            if (cap > SIZE_MAX / 2)
                return -1;
            cap *= 2;
        }
        char *grown'''))},
               r'''
    #include "strbuf.h"

    int main(void) {
        StrBuf sb;
        sb_init(&sb);
        CHECK(strcmp(sb_str(&sb), "") == 0);
        CHECK(sb_append(&sb, "hello", 5) == 0);
        CHECK(sb_append(&sb, ", ", 2) == 0);
        CHECK(sb_append(&sb, "world", 5) == 0);
        CHECK(strcmp(sb_str(&sb), "hello, world") == 0);
        CHECK(sb.len == 12);
        char *chunk = malloc(10000);
        memset(chunk, 'x', 10000);
        CHECK(sb_append(&sb, chunk, 10000) == 0);
        CHECK(sb.len == 10012 && sb.cap >= 10013);
        CHECK(strlen(sb_str(&sb)) == 10012);
        CHECK(sb_str(&sb)[10011] == 'x');
        for (int i = 0; i < 200; i++)
            CHECK(sb_append(&sb, "abc", 3) == 0);
        CHECK(sb.len == 10612 && strlen(sb_str(&sb)) == 10612);
        CHECK(sb_append(&sb, "", 0) == 0);
        sb_free(&sb);
        sb_init(&sb);
        CHECK(sb_append(&sb, chunk, 10000) == 0);
        CHECK(sb.len == 10000);
        size_t before = sb.len;
        CHECK(sb_append(&sb, "tail", SIZE_MAX - 5) == -1);
        CHECK(sb_append(&sb, "tail", SIZE_MAX) == -1);
        CHECK(sb_append(&sb, "tail", SIZE_MAX / 2) == -1);
        CHECK(sb.len == before && strlen(sb_str(&sb)) == before);
        CHECK(sb_append(&sb, "ok", 2) == 0);
        CHECK(sb.len == before + 2);
        sb_free(&sb);
        free(chunk);
        StrBuf tiny;
        sb_init(&tiny);
        CHECK(sb_append(&tiny, "0123456789abcdef0123456789abcdef0123456789", 42) == 0);
        CHECK(strlen(sb_str(&tiny)) == 42);
        sb_free(&tiny);
        return failures ? 1 : 0;
    }
'''))

LIST_H = dd(r'''
    #ifndef LIST_H
    #define LIST_H
    #include <stddef.h>

    typedef struct Node {
        int value;
        struct Node *next;
    } Node;

    /* A new node in front of head; returns the new head (NULL when the allocation fails, the old list is then still valid). */
    Node *list_push(Node *head, int value);
    /* Removes and frees every node whose value equals `value`; returns the new head. */
    Node *list_remove(Node *head, int value);
    size_t list_len(const Node *head);
    void list_free(Node *head);

    #endif
''')
LIST_C = dd(r'''
    #include "list.h"
    #include <stdlib.h>

    Node *list_push(Node *head, int value) {
        Node *node = malloc(sizeof *node);
        if (node == NULL)
            return NULL;
        node->value = value;
        node->next = head;
        return node;
    }

    Node *list_remove(Node *head, int value) {
        Node **link = &head;
        while (*link) {
            if ((*link)->value == value) {
                free(*link);
                *link = (*link)->next;
            } else {
                link = &(*link)->next;
            }
        }
        return head;
    }

    size_t list_len(const Node *head) {
        size_t n = 0;
        for (; head; head = head->next)
            n++;
        return n;
    }

    void list_free(Node *head) {
        while (head) {
            Node *next = head->next;
            free(head);
            head = next;
        }
    }
''')
SC.append(task("list-remove-uaf", 3, "the task queue", "list_remove", "CWE-416",
               "`list_remove` frees a node and then reads `(*link)->next` from the memory it just released (use after free): the list is silently corrupted when the allocator reuses the block, and AddressSanitizer reports it on the first removal.",
               {"include/list.h": LIST_H}, {"src/list.c": LIST_C},
               "`list_remove` keeps its contract (removes all nodes with that value, returns the new head) without ever touching a freed node. Head, middle, tail, repeated and missing values all work.",
               {"src/list.c": patched(LIST_C, (
                   '''            free(*link);
            *link = (*link)->next;
''', '''            Node *dead = *link;
            *link = dead->next;
            free(dead);
'''))},
               r'''
    #include "list.h"

    static Node *build(const int *v, size_t n) {
        Node *head = NULL;
        for (size_t i = n; i > 0; i--)
            head = list_push(head, v[i - 1]);
        return head;
    }

    static int same(const Node *head, const int *want, size_t n) {
        for (size_t i = 0; i < n; i++, head = head ? head->next : NULL)
            if (head == NULL || head->value != want[i])
                return 0;
        return head == NULL;
    }

    int main(void) {
        int v[] = {1, 2, 3, 2, 4, 2};
        Node *l = build(v, 6);
        CHECK(list_len(l) == 6);
        l = list_remove(l, 2);
        int a[] = {1, 3, 4};
        CHECK(same(l, a, 3));
        l = list_remove(l, 1);
        int b[] = {3, 4};
        CHECK(same(l, b, 2));
        l = list_remove(l, 4);
        int c[] = {3};
        CHECK(same(l, c, 1));
        l = list_remove(l, 99);
        CHECK(same(l, c, 1));
        l = list_remove(l, 3);
        CHECK(l == NULL);
        l = list_remove(l, 3);
        CHECK(l == NULL);
        int same_values[] = {7, 7, 7, 7};
        l = build(same_values, 4);
        l = list_remove(l, 7);
        CHECK(l == NULL && list_len(l) == 0);
        int w[] = {5, 6, 5};
        l = build(w, 3);
        l = list_remove(l, 5);
        int d[] = {6};
        CHECK(same(l, d, 1));
        list_free(l);
        return failures ? 1 : 0;
    }
'''))

CACHE_H = dd(r'''
    #ifndef CACHE_H
    #define CACHE_H
    #include <stddef.h>

    #define CACHE_SLOTS 8

    typedef struct {
        char *slots[CACHE_SLOTS];
    } Cache;

    void cache_init(Cache *c);
    /* Stores a private copy of text in the slot and releases what the slot held before. text may point into the slot's current content (for example the result of cache_get).
       Returns 0, or -1 for slot >= CACHE_SLOTS or when the allocation fails (the slot is then unchanged). */
    int cache_set(Cache *c, size_t slot, const char *text);
    /* The text of a slot, or NULL when it is empty or the slot does not exist. */
    const char *cache_get(const Cache *c, size_t slot);
    /* Empties the slot (also when it is already empty). */
    void cache_clear(Cache *c, size_t slot);
    /* Releases everything; the cache is empty and usable afterwards. */
    void cache_free(Cache *c);

    #endif
''')
CACHE_C = dd(r'''
    #include "cache.h"
    #include <stdlib.h>
    #include <string.h>

    void cache_init(Cache *c) {
        memset(c, 0, sizeof *c);
    }

    int cache_set(Cache *c, size_t slot, const char *text) {
        if (slot >= CACHE_SLOTS)
            return -1;
        free(c->slots[slot]);
        size_t n = strlen(text) + 1;
        char *copy = malloc(n);
        if (copy == NULL) {
            c->slots[slot] = NULL;
            return -1;
        }
        memcpy(copy, text, n);
        c->slots[slot] = copy;
        return 0;
    }

    const char *cache_get(const Cache *c, size_t slot) {
        return slot < CACHE_SLOTS ? c->slots[slot] : NULL;
    }

    void cache_clear(Cache *c, size_t slot) {
        if (slot < CACHE_SLOTS)
            free(c->slots[slot]);
    }

    void cache_free(Cache *c) {
        for (size_t i = 0; i < CACHE_SLOTS; i++)
            free(c->slots[i]);
    }
''')
SC.append(task("cache-double-free", 3, "the session cache", "cache_set", "CWE-415",
               "`cache_set` frees the old text before copying the new one, so `cache_set(c, 0, cache_get(c, 0))` (refreshing a value from itself) reads freed memory; `cache_clear` frees without clearing the pointer, so clearing twice or freeing the cache afterwards frees the same block again.",
               {"include/cache.h": CACHE_H}, {"src/cache.c": CACHE_C},
               "The cache API follows the header comments: `cache_set` copies first and releases the old text afterwards (also on allocation failure the old text stays), `cache_clear` and `cache_free` leave NULL behind so any sequence of clears and frees releases each block once.",
               {"src/cache.c": patched(CACHE_C, (
                   '''    free(c->slots[slot]);
    size_t n = strlen(text) + 1;
    char *copy = malloc(n);
    if (copy == NULL) {
        c->slots[slot] = NULL;
        return -1;
    }
    memcpy(copy, text, n);
    c->slots[slot] = copy;
    return 0;
''', '''    size_t n = strlen(text) + 1;
    char *copy = malloc(n);
    if (copy == NULL)
        return -1;
    memcpy(copy, text, n);
    free(c->slots[slot]);
    c->slots[slot] = copy;
    return 0;
'''), (
                   '''    if (slot < CACHE_SLOTS)
        free(c->slots[slot]);
''', '''    if (slot < CACHE_SLOTS) {
        free(c->slots[slot]);
        c->slots[slot] = NULL;
    }
'''), (
                   '''    for (size_t i = 0; i < CACHE_SLOTS; i++)
        free(c->slots[i]);
''', '''    for (size_t i = 0; i < CACHE_SLOTS; i++) {
        free(c->slots[i]);
        c->slots[i] = NULL;
    }
'''))},
               r'''
    #include "cache.h"

    int main(void) {
        Cache c;
        cache_init(&c);
        CHECK(cache_get(&c, 0) == NULL);
        CHECK(cache_set(&c, 0, "alpha") == 0);
        CHECK(cache_set(&c, 7, "omega") == 0);
        CHECK(strcmp(cache_get(&c, 0), "alpha") == 0);
        CHECK(strcmp(cache_get(&c, 7), "omega") == 0);
        CHECK(cache_set(&c, 8, "nope") == -1);
        CHECK(cache_get(&c, 8) == NULL);
        CHECK(cache_get(&c, 100) == NULL);
        CHECK(cache_set(&c, 0, cache_get(&c, 0)) == 0);
        CHECK(strcmp(cache_get(&c, 0), "alpha") == 0);
        CHECK(cache_set(&c, 0, cache_get(&c, 0) + 2) == 0);
        CHECK(strcmp(cache_get(&c, 0), "pha") == 0);
        CHECK(cache_set(&c, 7, cache_get(&c, 0)) == 0);
        CHECK(strcmp(cache_get(&c, 7), "pha") == 0);
        CHECK(cache_set(&c, 0, "") == 0);
        CHECK(strcmp(cache_get(&c, 0), "") == 0);
        cache_clear(&c, 0);
        cache_clear(&c, 0);
        cache_clear(&c, 3);
        cache_clear(&c, 99);
        CHECK(cache_get(&c, 0) == NULL);
        cache_free(&c);
        cache_free(&c);
        CHECK(cache_get(&c, 7) == NULL);
        CHECK(cache_set(&c, 1, "again") == 0);
        CHECK(strcmp(cache_get(&c, 1), "again") == 0);
        cache_clear(&c, 1);
        cache_free(&c);
        return failures ? 1 : 0;
    }
'''))

HASH_H = dd(r'''
    #ifndef BUCKET_H
    #define BUCKET_H
    #include <stddef.h>

    /* Hash table bucket of a key: h starts at 5381 and for every byte c of the key (as an unsigned value 0..255) h = h * 33 + c, computed in 32-bit unsigned arithmetic that wraps around;
       the bucket is h % nbuckets. nbuckets must be > 0. */
    size_t bucket_of(const char *key, size_t nbuckets);

    #endif
''')
HASH_C = dd(r'''
    #include "bucket.h"

    size_t bucket_of(const char *key, size_t nbuckets) {
        int h = 5381;
        for (const char *p = key; *p; p++)
            h = h * 33 + *p;
        return h % nbuckets;
    }
''')
SC.append(task("hash-bucket-overflow", 3, "the lookup table", "bucket_of", "CWE-190",
               "`bucket_of` hashes with a signed `int` and plain `char`: long keys overflow the signed accumulator (undefined behaviour), bytes above 127 are added as negative numbers, and a negative hash is converted to a huge `size_t` before the modulo, so the bucket index differs from the documented hash and can differ between compilers.",
               {"include/bucket.h": HASH_H}, {"src/bucket.c": HASH_C},
               "`bucket_of` implements the documented 32-bit unsigned hash exactly (test vectors are computed with the reference algorithm), including keys with bytes of 128 and above and keys of any length, and never exceeds `nbuckets - 1`.",
               {"src/bucket.c": patched(HASH_C, ('#include "bucket.h"\n', '#include "bucket.h"\n#include <stdint.h>\n'), (
                   '''    int h = 5381;
    for (const char *p = key; *p; p++)
        h = h * 33 + *p;
    return h % nbuckets;
''', '''    uint32_t h = 5381u;
    for (const unsigned char *p = (const unsigned char *)key; *p; p++)
        h = h * 33u + *p;
    return (size_t)(h % nbuckets);
'''))},
               r'''
    #include "bucket.h"

    static size_t reference(const char *key, size_t nbuckets) {
        uint32_t h = 5381u;
        for (const unsigned char *p = (const unsigned char *)key; *p; p++)
            h = h * 33u + *p;
        return (size_t)(h % nbuckets);
    }

    int main(void) {
        const char *keys[] = {"", "a", "hello", "The quick brown fox jumps over the lazy dog", "caf\xc3\xa9", "\xff\xfe\xfd\xfc", "\x80", "key-0000000001", "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"};
        size_t sizes[] = {1, 2, 7, 16, 97, 1000, 65536, 1000003};
        for (size_t k = 0; k < sizeof keys / sizeof *keys; k++) {
            for (size_t s = 0; s < sizeof sizes / sizeof *sizes; s++) {
                size_t got = bucket_of(keys[k], sizes[s]);
                CHECK(got == reference(keys[k], sizes[s]));
                CHECK(got < sizes[s]);
            }
        }
        CHECK(bucket_of("a", 1000) == (5381u * 33u + 97u) % 1000u);
        char *long_key = malloc(100001);
        for (int i = 0; i < 100000; i++)
            long_key[i] = (char)(33 + i % 90);
        long_key[100000] = 0;
        CHECK(bucket_of(long_key, 1021) == reference(long_key, 1021));
        for (int i = 0; i < 100000; i++)
            long_key[i] = (char)(128 + i % 128);
        CHECK(bucket_of(long_key, 4093) == reference(long_key, 4093));
        free(long_key);
        return failures ? 1 : 0;
    }
'''))

IMAGE_H = dd(r'''
    #ifndef IMAGE_H
    #define IMAGE_H
    #include <stdint.h>

    #define IMAGE_MAX_BYTES (4u * 1024u * 1024u)

    typedef struct {
        uint32_t width, height;
        uint8_t *pixels;      /* RGBA, 4 bytes per pixel, row after row */
    } Image;

    /* Creates a zero-filled width x height image. Returns 0, or -1 when width or height is 0, when the pixel data (width * height * 4 bytes) would be larger than IMAGE_MAX_BYTES,
       or when the allocation fails; img is then left untouched. */
    int image_create(Image *img, uint32_t width, uint32_t height);
    void image_fill(Image *img, uint8_t r, uint8_t g, uint8_t b, uint8_t a);
    void image_free(Image *img);

    #endif
''')
IMAGE_C = dd(r'''
    #include "image.h"
    #include <stdlib.h>

    int image_create(Image *img, uint32_t width, uint32_t height) {
        uint32_t size = width * height * 4;
        if (width == 0 || height == 0)
            return -1;
        img->pixels = calloc(size, 1);
        if (img->pixels == NULL)
            return -1;
        img->width = width;
        img->height = height;
        return 0;
    }

    void image_fill(Image *img, uint8_t r, uint8_t g, uint8_t b, uint8_t a) {
        for (uint32_t i = 0; i < img->width * img->height; i++) {
            img->pixels[4 * i] = r;
            img->pixels[4 * i + 1] = g;
            img->pixels[4 * i + 2] = b;
            img->pixels[4 * i + 3] = a;
        }
    }

    void image_free(Image *img) {
        free(img->pixels);
        img->pixels = NULL;
        img->width = img->height = 0;
    }
''')
SC.append(task("image-size-overflow", 3, "the thumbnail service", "image_create", "CWE-190",
               "`image_create` computes the buffer size in 32-bit arithmetic: a 65536 x 16384 image gives `size == 0`, `calloc(0)` succeeds with a tiny block, and `image_fill` then writes four bytes for each of a billion pixels into it. The documented 4 MiB limit is not enforced at all.",
               {"include/image.h": IMAGE_H}, {"src/image.c": IMAGE_C},
               "`image_create` computes the size in 64 bits and enforces `IMAGE_MAX_BYTES` (1024 x 1024 is accepted, 1025 x 1024 is not), leaves `img` untouched on failure, and keeps everything else as it is. Dimensions are attacker-controlled (they come from the file header).",
               {"src/image.c": patched(IMAGE_C, (
                   '''    uint32_t size = width * height * 4;
    if (width == 0 || height == 0)
        return -1;
    img->pixels = calloc(size, 1);
    if (img->pixels == NULL)
        return -1;
''', '''    if (width == 0 || height == 0)
        return -1;
    uint64_t size = (uint64_t)width * height * 4u;
    if (size > IMAGE_MAX_BYTES)
        return -1;
    uint8_t *pixels = calloc((size_t)size, 1);
    if (pixels == NULL)
        return -1;
    img->pixels = pixels;
'''), (
                   'for (uint32_t i = 0; i < img->width * img->height; i++) {', 'for (uint64_t i = 0; i < (uint64_t)img->width * img->height; i++) {'))},
               r'''
    #include "image.h"

    int main(void) {
        Image img;
        CHECK(image_create(&img, 3, 2) == 0);
        CHECK(img.width == 3 && img.height == 2);
        image_fill(&img, 1, 2, 3, 4);
        for (int i = 0; i < 6; i++)
            CHECK(img.pixels[4 * i] == 1 && img.pixels[4 * i + 1] == 2 && img.pixels[4 * i + 2] == 3 && img.pixels[4 * i + 3] == 4);
        image_free(&img);
        CHECK(img.pixels == NULL);
        CHECK(image_create(&img, 1024, 1024) == 0);
        image_fill(&img, 9, 9, 9, 9);
        CHECK(img.pixels[IMAGE_MAX_BYTES - 1] == 9);
        image_free(&img);
        Image sentinel = {7, 8, (uint8_t *)&sentinel};
        uint32_t dims[][2] = {{1025, 1024}, {1024, 1025}, {65536, 16384}, {16384, 65536}, {65536, 65536}, {0xFFFFFFFFu, 0xFFFFFFFFu}, {0x40000001u, 1}, {0x80000000u, 2}, {2000, 2000}, {0, 5}, {5, 0}};
        for (size_t i = 0; i < sizeof dims / sizeof *dims; i++) {
            Image probe = sentinel;
            CHECK(image_create(&probe, dims[i][0], dims[i][1]) == -1);
            CHECK(probe.width == 7 && probe.height == 8 && probe.pixels == (uint8_t *)&sentinel);
        }
        return failures ? 1 : 0;
    }
'''))

# ---------------------------------------------------------------------------------------------------------------------------------
REC_H = dd(r'''
    #ifndef RECORD_H
    #define RECORD_H
    #include <stddef.h>
    #include <stdint.h>

    /* Record format: a 4-byte big-endian length L followed by L payload bytes.
       decode_record copies the payload of the record at the start of buf (buflen bytes available) into out (capacity outcap) and returns L.
       Returns -1, writing nothing, when buflen < 4, when the record is truncated (L > buflen - 4) or when the payload does not fit (L > outcap). The input is untrusted. */
    long decode_record(const uint8_t *buf, size_t buflen, uint8_t *out, size_t outcap);

    #endif
''')
REC_C = dd(r'''
    #include "record.h"
    #include <string.h>

    long decode_record(const uint8_t *buf, size_t buflen, uint8_t *out, size_t outcap) {
        int len = (buf[0] << 24) | (buf[1] << 16) | (buf[2] << 8) | buf[3];
        if (len > (int)outcap || len > (int)(buflen - 4))
            return -1;
        memcpy(out, buf + 4, len);
        return len;
    }
''')
SC.append(task("record-length-checks", 4, "the wire protocol decoder", "decode_record", "CWE-190",
               "`decode_record` reads the 32-bit length into a signed `int` (the shift of a byte above 127 into bit 31 is already undefined behaviour), so lengths like `0x80000000` or `0xFFFFFFF0` become negative, pass both `len > ...` checks and reach `memcpy` as a gigantic size; it also reads four bytes without checking that there are four, and `buflen - 4` underflows for short buffers.",
               {"include/record.h": REC_H}, {"src/record.c": REC_C},
               "`decode_record` validates in `size_t`/`uint32_t` arithmetic exactly as the header comment says (buflen < 4, truncation, capacity), reads the length without undefined behaviour, and writes nothing on error. Valid records, including empty ones and ones that exactly fill `out`, decode as before.",
               {"src/record.c": patched(REC_C, (
                   '''    int len = (buf[0] << 24) | (buf[1] << 16) | (buf[2] << 8) | buf[3];
    if (len > (int)outcap || len > (int)(buflen - 4))
        return -1;
    memcpy(out, buf + 4, len);
    return len;
''', '''    if (buflen < 4)
        return -1;
    uint32_t len = ((uint32_t)buf[0] << 24) | ((uint32_t)buf[1] << 16) | ((uint32_t)buf[2] << 8) | (uint32_t)buf[3];
    if ((size_t)len > buflen - 4 || (size_t)len > outcap)
        return -1;
    memcpy(out, buf + 4, len);
    return (long)len;
'''))},
               r'''
    #include "record.h"

    static long run(const uint8_t *msg, size_t n, size_t outcap, const uint8_t *want, size_t wantn) {
        uint8_t *buf = heap_bytes(msg, n);
        uint8_t *out = malloc(outcap ? outcap : 1);
        memset(out, 0xEE, outcap ? outcap : 1);
        long rc = decode_record(buf, n, out, outcap);
        if (wantn == (size_t)-1) {
            CHECK(rc == -1);
            for (size_t i = 0; i < outcap; i++)
                CHECK(out[i] == 0xEE);
        } else {
            CHECK(rc == (long)wantn);
            if (wantn)
                CHECK(memcmp(out, want, wantn) == 0);
        }
        free(buf);
        free(out);
        return rc;
    }

    int main(void) {
        const uint8_t rec3[] = {0, 0, 0, 3, 'a', 'b', 'c'};
        run(rec3, sizeof rec3, 3, (const uint8_t *)"abc", 3);
        run(rec3, sizeof rec3, 100, (const uint8_t *)"abc", 3);
        const uint8_t rec0[] = {0, 0, 0, 0};
        run(rec0, sizeof rec0, 0, NULL, 0);
        const uint8_t rec_trailing[] = {0, 0, 0, 2, 'h', 'i', 'X', 'Y'};
        run(rec_trailing, sizeof rec_trailing, 2, (const uint8_t *)"hi", 2);
        run(rec3, sizeof rec3, 2, NULL, (size_t)-1);
        run(rec3, sizeof rec3, 0, NULL, (size_t)-1);
        const uint8_t shorts[4][4] = {{0}, {0, 0}, {0, 0, 0}, {0, 0, 0}};
        for (size_t n = 0; n < 4; n++)
            run(shorts[n], n, 8, NULL, (size_t)-1);
        const uint8_t trunc[] = {0, 0, 0, 5, 'a', 'b', 'c'};
        run(trunc, sizeof trunc, 100, NULL, (size_t)-1);
        const uint8_t one_more[] = {0, 0, 0, 4, 'a', 'b', 'c'};
        run(one_more, sizeof one_more, 100, NULL, (size_t)-1);
        const uint8_t huge[][8] = {{0xFF, 0xFF, 0xFF, 0xFF, 1, 2, 3, 4}, {0x80, 0, 0, 0, 1, 2, 3, 4}, {0xFF, 0xFF, 0xFF, 0xF0, 1, 2, 3, 4}, {0x7F, 0xFF, 0xFF, 0xFF, 1, 2, 3, 4},
                                   {0x80, 0, 0, 1, 1, 2, 3, 4}, {0, 0, 1, 0, 1, 2, 3, 4}, {0x01, 0, 0, 0, 1, 2, 3, 4}};
        for (size_t i = 0; i < sizeof huge / sizeof *huge; i++) {
            run(huge[i], 8, 4, NULL, (size_t)-1);
            run(huge[i], 8, 1000, NULL, (size_t)-1);
        }
        uint8_t big[4 + 70000];
        big[0] = 0; big[1] = 1; big[2] = 0x11; big[3] = 0x70;
        memset(big + 4, 'z', 70000);
        uint8_t *bb = heap_bytes(big, sizeof big);
        uint8_t *out = malloc(70000);
        CHECK(decode_record(bb, sizeof big, out, 70000) == 70000);
        CHECK(out[0] == 'z' && out[69999] == 'z');
        free(out);
        free(bb);
        return failures ? 1 : 0;
    }
'''))

B64_H = dd(r'''
    #ifndef B64_H
    #define B64_H
    #include <stddef.h>
    #include <stdint.h>

    /* Decodes standard base64 (RFC 4648: A-Z a-z 0-9 + /, padding with '=' is required, no whitespace) into out (capacity cap).
       Returns the number of decoded bytes. Returns -1 for invalid input (character outside the alphabet, length not a multiple of 4, '=' anywhere but the last one or two
       positions, "Q===" style padding) and when the decoded data does not fit into cap bytes. Never writes more than cap bytes. The empty string decodes to 0 bytes. */
    long b64_decode(const char *in, uint8_t *out, size_t cap);

    #endif
''')
B64_C = dd(r'''
    #include "b64.h"
    #include <string.h>

    static int value(char c) {
        if (c >= 'A' && c <= 'Z') return c - 'A';
        if (c >= 'a' && c <= 'z') return c - 'a' + 26;
        if (c >= '0' && c <= '9') return c - '0' + 52;
        if (c == '+') return 62;
        if (c == '/') return 63;
        return -1;
    }

    long b64_decode(const char *in, uint8_t *out, size_t cap) {
        size_t n = strlen(in), o = 0;
        (void)cap;
        if (n % 4 != 0)
            return -1;
        for (size_t i = 0; i < n; i += 4) {
            int pad = 0;
            int v[4];
            for (int k = 0; k < 4; k++) {
                char c = in[i + k];
                if (c == '=') {
                    pad++;
                    v[k] = 0;
                } else {
                    if (pad)
                        return -1;
                    v[k] = value(c);
                    if (v[k] < 0)
                        return -1;
                }
            }
            if (pad > 2 || (pad && i + 4 != n))
                return -1;
            out[o++] = (uint8_t)((v[0] << 2) | (v[1] >> 4));
            if (pad < 2)
                out[o++] = (uint8_t)((v[1] << 4) | (v[2] >> 2));
            if (pad < 1)
                out[o++] = (uint8_t)((v[2] << 6) | v[3]);
        }
        return (long)o;
    }
''')
SC.append(task("base64-output-bound", 4, "the attachment decoder", "b64_decode", "CWE-787",
               "`b64_decode` ignores its `cap` argument and writes every decoded byte: callers size the output from what they expect (a 32-byte token), and an input that decodes to more bytes - or one that fails halfway after having written a lot - overflows the heap buffer.",
               {"include/b64.h": B64_H}, {"src/b64.c": B64_C},
               "`b64_decode` must never write more than `cap` bytes: it checks the capacity before every store and returns -1 when the data does not fit. Decoding results, the accepted padding forms and all other rejections stay as in the header comment.",
               {"src/b64.c": patched(B64_C, (
                   '''    (void)cap;
    if (n % 4 != 0)
''', '''    if (n % 4 != 0)
'''), (
                   '''            out[o++] = (uint8_t)((v[0] << 2) | (v[1] >> 4));
            if (pad < 2)
                out[o++] = (uint8_t)((v[1] << 4) | (v[2] >> 2));
            if (pad < 1)
                out[o++] = (uint8_t)((v[2] << 6) | v[3]);
''', '''            size_t produced = (size_t)(3 - pad);
            if (produced > cap - o)
                return -1;
            out[o++] = (uint8_t)((v[0] << 2) | (v[1] >> 4));
            if (pad < 2)
                out[o++] = (uint8_t)((v[1] << 4) | (v[2] >> 2));
            if (pad < 1)
                out[o++] = (uint8_t)((v[2] << 6) | v[3]);
'''))},
               r'''
    #include "b64.h"

    static void ok(const char *in, const char *want) {
        size_t n = strlen(want);
        uint8_t *out = malloc(n ? n : 1);
        CHECK(b64_decode(in, out, n) == (long)n);
        CHECK(memcmp(out, want, n) == 0);
        free(out);
        if (n > 0) {
            out = malloc(n - 1 ? n - 1 : 1);
            CHECK(b64_decode(in, out, n - 1) == -1);
            free(out);
        }
        out = malloc(n + 5);
        CHECK(b64_decode(in, out, n + 5) == (long)n);
        free(out);
    }

    static void bad(const char *in, size_t cap) {
        uint8_t *out = malloc(cap ? cap : 1);
        CHECK(b64_decode(in, out, cap) == -1);
        free(out);
    }

    int main(void) {
        ok("", "");
        ok("Zg==", "f");
        ok("Zm8=", "fo");
        ok("Zm9v", "foo");
        ok("Zm9vYg==", "foob");
        ok("Zm9vYmE=", "fooba");
        ok("Zm9vYmFy", "foobar");
        ok("SGVsbG8sIHdvcmxkIQ==", "Hello, world!");
        ok("YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXo=", "abcdefghijklmnopqrstuvwxyz");
        uint8_t bin[3] = {0xFF, 0xFE, 0xFD};
        uint8_t *out = malloc(3);
        CHECK(b64_decode("//79", out, 3) == 3);
        CHECK(memcmp(out, bin, 3) == 0);
        free(out);
        const char *invalid[] = {"Zm9", "Zm9vY", "Zm9v!A==", "Z===", "====", "Zg=a", "Zg==Zg==", "Zm9v Zg==", "Zm9v\n", "Zm=v", "Z\xc3\xa9v", "Zg=", "=Zg=", "Zm9vYg==Zm9v"};
        for (size_t i = 0; i < sizeof invalid / sizeof *invalid; i++) {
            bad(invalid[i], 64);
            bad(invalid[i], 1);
            bad(invalid[i], 0);
        }
        bad("Zm9vYmFy", 5);
        bad("Zm9vYmFy", 0);
        bad("Zm9vYmFyZm9vYmFy", 11);
        uint8_t *small = malloc(1);
        CHECK(b64_decode("Zm9vYmFy", small, 1) == -1);
        free(small);
        char *long_in = malloc(4 * 5000 + 1);
        for (int i = 0; i < 5000; i++)
            memcpy(long_in + 4 * i, "QUJD", 4);
        long_in[4 * 5000] = 0;
        uint8_t *big = malloc(15000);
        CHECK(b64_decode(long_in, big, 15000) == 15000);
        CHECK(memcmp(big + 14997, "ABC", 3) == 0);
        uint8_t *toosmall = malloc(14999);
        CHECK(b64_decode(long_in, toosmall, 14999) == -1);
        free(toosmall);
        free(big);
        free(long_in);
        return failures ? 1 : 0;
    }
'''))

ARC_H = dd(r'''
    #ifndef ARCHIVE_H
    #define ARCHIVE_H
    #include <stddef.h>
    #include <stdint.h>

    /* Archive format: a sequence of entries. Entry = 1 byte name length N (1..255), N name bytes, a 4-byte big-endian data length D, D data bytes. */
    typedef struct {
        char name[256];          /* NUL-terminated entry name */
        const uint8_t *data;     /* points into the archive buffer */
        uint32_t size;
    } Entry;

    /* Reads the entry at offset *pos of buf (buflen bytes) into *e and advances *pos past it. Returns 1 for an entry, 0 when *pos == buflen (clean end of archive) and -1 for malformed or
       truncated data: *pos > buflen, N == 0, the name, the length field or the data extend beyond buflen. *pos and *e are not meaningful after -1, but nothing outside the buffer is read.
       The archive is untrusted: all lengths are attacker-controlled. */
    int archive_next(const uint8_t *buf, size_t buflen, size_t *pos, Entry *e);

    #endif
''')
ARC_C = dd(r'''
    #include "archive.h"
    #include <string.h>

    int archive_next(const uint8_t *buf, size_t buflen, size_t *pos, Entry *e) {
        if (*pos == buflen)
            return 0;
        unsigned p = (unsigned)*pos;
        unsigned name_len = buf[p];
        unsigned size = (unsigned)((buf[p + 1 + name_len] << 24) | (buf[p + 2 + name_len] << 16) | (buf[p + 3 + name_len] << 8) | buf[p + 4 + name_len]);
        unsigned end = p + 1 + name_len + 4 + size;
        if (end > buflen)
            return -1;
        memcpy(e->name, buf + p + 1, name_len);
        e->data = buf + p + 1 + name_len + 4;
        e->size = size;
        *pos = end;
        return 1;
    }
''')
SC.append(task("archive-reader", 5, "the archive extractor", "archive_next", "CWE-190",
               "`archive_next` trusts every length field: it reads the name length and the four size bytes before checking that they exist, adds them up in 32-bit `unsigned` arithmetic (a data length such as `0xFFFFFFF0` wraps the end offset around to a small value that passes the bounds check), accepts empty names, and copies the name without terminating it.",
               {"include/archive.h": ARC_H}, {"src/archive.c": ARC_C},
               "`archive_next` validates the offset, the name, the length field and the data against `buflen` in `size_t` arithmetic *before* reading them, rejects names of length 0 and truncations at every possible byte with -1, terminates names, and returns 0 only for an exact end of the buffer. Well-formed archives parse exactly as before.",
               {"src/archive.c": dd(r'''
                   #include "archive.h"
                   #include <string.h>

                   int archive_next(const uint8_t *buf, size_t buflen, size_t *pos, Entry *e) {
                       size_t p = *pos;
                       if (p > buflen)
                           return -1;
                       if (p == buflen)
                           return 0;
                       size_t name_len = buf[p];
                       if (name_len == 0 || name_len > buflen - p - 1)
                           return -1;
                       size_t len_at = p + 1 + name_len;
                       if (buflen - len_at < 4)
                           return -1;
                       uint32_t size = ((uint32_t)buf[len_at] << 24) | ((uint32_t)buf[len_at + 1] << 16) | ((uint32_t)buf[len_at + 2] << 8) | (uint32_t)buf[len_at + 3];
                       size_t data_at = len_at + 4;
                       if ((size_t)size > buflen - data_at)
                           return -1;
                       memcpy(e->name, buf + p + 1, name_len);
                       e->name[name_len] = 0;
                       e->data = buf + data_at;
                       e->size = size;
                       *pos = data_at + size;
                       return 1;
                   }
               ''')},
               r'''
    #include "archive.h"

    /* two entries: "a.txt" with "hello" and "dir/b" with "" */
    static const uint8_t GOOD[] = {5, 'a', '.', 't', 'x', 't', 0, 0, 0, 5, 'h', 'e', 'l', 'l', 'o', 5, 'd', 'i', 'r', '/', 'b', 0, 0, 0, 0};

    static int walk(const uint8_t *msg, size_t n, int *entries, int *end_state) {
        uint8_t *buf = heap_bytes(msg, n);
        size_t pos = 0;
        *entries = 0;
        for (;;) {
            Entry e;
            memset(&e, 0xAA, sizeof e);
            int rc = archive_next(buf, n, &pos, &e);
            if (rc == 1) {
                CHECK(strlen(e.name) < 256);
                CHECK(e.data >= buf && (size_t)(e.data - buf) + e.size <= n);
                CHECK(pos <= n);
                (*entries)++;
                if (*entries > 4)
                    break;
            } else {
                *end_state = rc;
                break;
            }
        }
        free(buf);
        return *entries;
    }

    int main(void) {
        int entries, end;
        CHECK(walk(GOOD, sizeof GOOD, &entries, &end) == 2 && end == 0);
        uint8_t *buf = heap_bytes(GOOD, sizeof GOOD);
        size_t pos = 0;
        Entry e;
        memset(&e, 0xAA, sizeof e);
        CHECK(archive_next(buf, sizeof GOOD, &pos, &e) == 1);
        CHECK(strcmp(e.name, "a.txt") == 0 && e.size == 5 && memcmp(e.data, "hello", 5) == 0 && pos == 15);
        CHECK(archive_next(buf, sizeof GOOD, &pos, &e) == 1);
        CHECK(strcmp(e.name, "dir/b") == 0 && e.size == 0 && pos == sizeof GOOD);
        CHECK(archive_next(buf, sizeof GOOD, &pos, &e) == 0);
        pos = sizeof GOOD + 1;
        CHECK(archive_next(buf, sizeof GOOD, &pos, &e) == -1);
        free(buf);
        /* every truncation of a valid archive: complete entries are read, then -1 (or 0 at an entry boundary), nothing is read out of bounds */
        for (size_t cut = 0; cut < sizeof GOOD; cut++) {
            int want_entries = cut >= 15 ? 1 : 0;
            int want_end = (cut == 0 || cut == 15) ? 0 : -1;
            CHECK(walk(GOOD, cut, &entries, &end) == want_entries);
            CHECK(end == want_end);
        }
        /* malformed headers */
        const uint8_t empty_name[] = {0, 0, 0, 0, 0};
        CHECK(walk(empty_name, sizeof empty_name, &entries, &end) == 0 && end == -1);
        const uint8_t huge_size[] = {1, 'x', 0xFF, 0xFF, 0xFF, 0xFF, 'a', 'b'};
        CHECK(walk(huge_size, sizeof huge_size, &entries, &end) == 0 && end == -1);
        uint8_t wrap[64];
        memset(wrap, 'p', sizeof wrap);
        wrap[0] = 40;                                    /* name of 40 bytes, then a length that wraps 32-bit arithmetic */
        wrap[41] = 0xFF; wrap[42] = 0xFF; wrap[43] = 0xFF; wrap[44] = 0xF0;
        CHECK(walk(wrap, sizeof wrap, &entries, &end) == 0 && end == -1);
        wrap[41] = 0x80; wrap[42] = 0; wrap[43] = 0; wrap[44] = 0;
        CHECK(walk(wrap, sizeof wrap, &entries, &end) == 0 && end == -1);
        const uint8_t name_overrun[] = {200, 'a', 'b'};
        CHECK(walk(name_overrun, sizeof name_overrun, &entries, &end) == 0 && end == -1);
        const uint8_t no_length[] = {2, 'a', 'b', 0, 0};
        CHECK(walk(no_length, sizeof no_length, &entries, &end) == 0 && end == -1);
        /* longest name */
        uint8_t longest[1 + 255 + 4 + 2];
        longest[0] = 255;
        memset(longest + 1, 'n', 255);
        longest[256] = 0; longest[257] = 0; longest[258] = 0; longest[259] = 2;
        longest[260] = 'o'; longest[261] = 'k';
        uint8_t *lb = heap_bytes(longest, sizeof longest);
        pos = 0;
        memset(&e, 0xAA, sizeof e);
        CHECK(archive_next(lb, sizeof longest, &pos, &e) == 1);
        CHECK(strlen(e.name) == 255 && e.size == 2 && memcmp(e.data, "ok", 2) == 0);
        CHECK(archive_next(lb, sizeof longest, &pos, &e) == 0);
        free(lb);
        return failures ? 1 : 0;
    }
'''))

ORDER = ["greeting-strcpy", "log-format-string", "prefix-fencepost", "score-index", "join-path-boundary", "config-line-parser", "strncpy-terminator", "word-splitter",
         "repeat-allocation", "snprintf-accumulator", "string-builder-growth", "list-remove-uaf", "cache-double-free", "hash-bucket-overflow", "image-size-overflow",
         "record-length-checks", "base64-output-bound", "archive-reader"]
SC.sort(key=lambda s: (s["d"], ORDER.index(s["slug"])))


@family("security-c-memory", category="security", lang="c", kind="fix", n=18,
        summary="C memory safety under AddressSanitizer/UBSan: buffer overflows, format strings, integer overflows, use-after-free, untrusted lengths")
def gen_c(rng, n):
    return list(_sec.emit(rng, SC[:n], tags=["c", "asan", "memory-safety"]))
