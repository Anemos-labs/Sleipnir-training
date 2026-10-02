"""C: quadratic scans, repeated expensive callbacks, strcat in loops. Large inputs under `timeout`, or callbacks counted with a budget."""
from __future__ import annotations

import json
from string import Template

from fx import Task, family, merged, run

from ._kit import prove_opt

BUILD = "mkdir -p build && gcc -std=c11 -O1 -Wall -Wextra -Iinclude -Isrc -o build/tests $(find src tests -name '*.c')"
C_CORRECT = BUILD + " && ./build/tests correct"
C_PERF = BUILD + ' && (timeout 8 ./build/tests perf || { echo "PERF: the large input was not handled within 8 seconds"; exit 1; })'
C_ALL = BUILD + ' && ./build/tests correct && (timeout 8 ./build/tests perf || { echo "PERF: the large input was not handled within 8 seconds"; exit 1; })'

MAIN = '''#include <stdio.h>
#include <string.h>

int run_basic(void);
int run_correct(void);
int run_perf(void);

int main(int argc, char **argv) {
    const char *mode = argc > 1 ? argv[1] : "all";
    int failures = 0;
    if (strcmp(mode, "perf") != 0) {
        failures += run_basic();
        failures += run_correct();
    }
    if (strcmp(mode, "correct") != 0) {
        failures += run_perf();
    }
    if (failures) {
        printf("%d failing checks\\n", failures);
        return 1;
    }
    printf("all checks passed\\n");
    return 0;
}
'''

RNG = '''static unsigned long long rng_state = 88172645463325252ULL;

static unsigned long long rnd64(void) {
    rng_state ^= rng_state << 13;
    rng_state ^= rng_state >> 7;
    rng_state ^= rng_state << 17;
    return rng_state;
}

static int rnd_below(int n) {
    return (int)(rnd64() % (unsigned long long)n);
}
'''

SHAPES = {
    "dedupe": dict(
        d=3, proto="size_t $f(const int *in, size_t n, int *out)", inc="#include <stddef.h>\n",
        naive='''size_t $f(const int *in, size_t n, int *out) {
    size_t count = 0;
    for (size_t i = 0; i < n; i++) {
        int seen = 0;
        for (size_t j = 0; j < count; j++) {
            if (out[j] == in[i]) {
                seen = 1;
                break;
            }
        }
        if (!seen) {
            out[count++] = in[i];
        }
    }
    return count;
}
''', fast='''#include <stdlib.h>

size_t $f(const int *in, size_t n, int *out) {
    size_t cap = 16;
    while (cap < 2 * n) {
        cap <<= 1;
    }
    unsigned char *used = calloc(cap, 1);
    int *slots = malloc(cap * sizeof(int));
    size_t count = 0;
    for (size_t i = 0; i < n; i++) {
        size_t h = ((unsigned)in[i] * 2654435761u) & (cap - 1);
        while (used[h] && slots[h] != in[i]) {
            h = (h + 1) & (cap - 1);
        }
        if (!used[h]) {
            used[h] = 1;
            slots[h] = in[i];
            out[count++] = in[i];
        }
    }
    free(used);
    free(slots);
    return count;
}
''', spec="Copies every distinct value of `in[0..n)` to `out`, in order of first appearance, and returns how many were copied (`out` has room for `n` values).",
        test_small='''int n = rnd_below(30);
        int in[30], out[30], want[30];
        for (int i = 0; i < n; i++) in[i] = rnd_below(12) - 4;
        size_t k = 0;
        for (int i = 0; i < n; i++) {
            int seen = 0;
            for (size_t j = 0; j < k; j++) if (want[j] == in[i]) seen = 1;
            if (!seen) want[k++] = in[i];
        }
        size_t got = FN(in, (size_t)n, out);
        if (got != k || memcmp(out, want, k * sizeof(int)) != 0) { printf("dedupe mismatch for n=%d\\n", n); failures++; }''',
        test_big='''size_t n = 760000;
    int *in = malloc(n * sizeof(int));
    int *out = malloc(n * sizeof(int));
    for (size_t i = 0; i < n; i++) in[i] = rnd_below((int)(n / 2));
    size_t got = FN(in, n, out);
    /* distinct values: count with a bitmap */
    unsigned char *seen = calloc(n / 2 + 1, 1);
    size_t want = 0;
    for (size_t i = 0; i < n; i++) if (!seen[in[i]]) { seen[in[i]] = 1; want++; }
    if (got != want) { printf("wrong count %zu, want %zu\\n", got, want); failures++; }''',
        example='''int in[] = {3, 1, 3, 2, 1};
    int out[5];
    size_t k = FN(in, 5, out);
    if (k != 3 || out[0] != 3 || out[1] != 1 || out[2] != 2) { printf("example failed\\n"); failures++; }''',
        vocab=[("unique_ids", "Distinct ids of a sensor batch"), ("first_seen_codes", "Distinct product codes in scan order"), ("distinct_zones", "Distinct delivery zones in route order")]),
    "common": dict(
        d=2, proto="size_t $f(const int *a, size_t na, const int *b, size_t nb)", inc="#include <stddef.h>\n",
        naive='''size_t $f(const int *a, size_t na, const int *b, size_t nb) {
    size_t count = 0;
    for (size_t i = 0; i < na; i++) {
        for (size_t j = 0; j < nb; j++) {
            if (a[i] == b[j]) {
                count++;
                break;
            }
        }
    }
    return count;
}
''', fast='''#include <stdlib.h>

static int cmp_int(const void *x, const void *y) {
    int a = *(const int *)x, b = *(const int *)y;
    return (a > b) - (a < b);
}

size_t $f(const int *a, size_t na, const int *b, size_t nb) {
    int *sorted = malloc((nb ? nb : 1) * sizeof(int));
    for (size_t i = 0; i < nb; i++) {
        sorted[i] = b[i];
    }
    qsort(sorted, nb, sizeof(int), cmp_int);
    size_t count = 0;
    for (size_t i = 0; i < na; i++) {
        if (nb && bsearch(&a[i], sorted, nb, sizeof(int), cmp_int)) {
            count++;
        }
    }
    free(sorted);
    return count;
}
''', spec="Returns how many elements of `a[0..na)` (repeats counted) also occur somewhere in `b[0..nb)`.",
        test_small='''int na = rnd_below(25), nb = rnd_below(25);
        int a[25], b[25];
        for (int i = 0; i < na; i++) a[i] = rnd_below(15);
        for (int i = 0; i < nb; i++) b[i] = rnd_below(15);
        size_t want = 0;
        for (int i = 0; i < na; i++) { int f = 0; for (int j = 0; j < nb; j++) if (a[i] == b[j]) f = 1; want += f; }
        size_t got = FN(a, (size_t)na, b, (size_t)nb);
        if (got != want) { printf("common: got %zu, want %zu\\n", got, want); failures++; }''',
        test_big='''size_t n = 450000;
    int *a = malloc(n * sizeof(int));
    int *b = malloc(n * sizeof(int));
    unsigned char *inb = calloc(3 * n, 1);
    for (size_t i = 0; i < n; i++) { a[i] = rnd_below((int)(3 * n)); b[i] = rnd_below((int)(3 * n)); inb[b[i]] = 1; }
    size_t want = 0;
    for (size_t i = 0; i < n; i++) want += inb[a[i]];
    size_t got = FN(a, n, b, n);
    if (got != want) { printf("wrong count %zu, want %zu\\n", got, want); failures++; }''',
        example='''int a[] = {1, 2, 2, 7};
    int b[] = {2, 7, 9};
    if (FN(a, 4, b, 3) != 3 || FN(a, 0, b, 3) != 0 || FN(a, 4, b, 0) != 0) { printf("example failed\\n"); failures++; }''',
        vocab=[("count_replied", "How many invitees have replied"), ("count_in_stock", "How many wanted items are in stock"), ("count_known_plates", "How many scanned plates are on the permit list")]),
    "lookup": dict(
        d=3, proto="void $f(const int *keys, size_t nk, const int *table, size_t nt, int *out)", inc="#include <stddef.h>\n",
        naive='''void $f(const int *keys, size_t nk, const int *table, size_t nt, int *out) {
    for (size_t i = 0; i < nk; i++) {
        out[i] = -1;
        for (size_t j = 0; j < nt; j++) {
            if (table[j] == keys[i]) {
                out[i] = (int)j;
                break;
            }
        }
    }
}
''', fast='''void $f(const int *keys, size_t nk, const int *table, size_t nt, int *out) {
    for (size_t i = 0; i < nk; i++) {
        size_t lo = 0, hi = nt;
        out[i] = -1;
        while (lo < hi) {
            size_t mid = lo + (hi - lo) / 2;
            if (table[mid] < keys[i]) {
                lo = mid + 1;
            } else if (table[mid] > keys[i]) {
                hi = mid;
            } else {
                out[i] = (int)mid;
                break;
            }
        }
    }
}
''', spec="`table[0..nt)` is sorted ascending without repeats. Sets `out[i]` to the index of `keys[i]` in `table`, or -1 when it is absent.",
        test_small='''int nt = rnd_below(20), nk = rnd_below(20);
        int table[20], keys[20], out[20];
        int v = rnd_below(5);
        for (int i = 0; i < nt; i++) { table[i] = v; v += 1 + rnd_below(3); }
        for (int i = 0; i < nk; i++) keys[i] = rnd_below(v + 3);
        FN(keys, (size_t)nk, table, (size_t)nt, out);
        for (int i = 0; i < nk; i++) {
            int want = -1;
            for (int j = 0; j < nt; j++) if (table[j] == keys[i]) want = j;
            if (out[i] != want) { printf("lookup: key %d got %d want %d\\n", keys[i], out[i], want); failures++; }
        }''',
        test_big='''size_t n = 380000;
    int *table = malloc(n * sizeof(int));
    int *keys = malloc(n * sizeof(int));
    int *out = malloc(n * sizeof(int));
    for (size_t i = 0; i < n; i++) table[i] = (int)(2 * i);
    for (size_t i = 0; i < n; i++) keys[i] = rnd_below((int)(2 * n));
    FN(keys, n, table, n, out);
    for (size_t i = 0; i < n; i++) {
        int want = (keys[i] % 2 == 0) ? keys[i] / 2 : -1;
        if (out[i] != want) { printf("wrong index for key %d\\n", keys[i]); failures++; break; }
    }''',
        example='''int table[] = {2, 4, 8, 16};
    int keys[] = {8, 3, 2, 16};
    int out[4];
    FN(keys, 4, table, 4, out);
    if (out[0] != 2 || out[1] != -1 || out[2] != 0 || out[3] != 3) { printf("example failed\\n"); failures++; }''',
        vocab=[("slot_of_each", "Slot of every requested part number"), ("rank_positions", "Position of every wanted bib number in the start list"), ("column_of_each", "Column index of every wanted column id")]),
    "join": dict(
        d=2, proto="char *$f(const char **parts, size_t n)", inc="#include <stddef.h>\n",
        naive='''#include <stdlib.h>
#include <string.h>

char *$f(const char **parts, size_t n) {
    char *out = malloc(1);
    out[0] = '\\0';
    for (size_t i = 0; i < n; i++) {
        out = realloc(out, strlen(out) + strlen(parts[i]) + 2);
        if (i > 0) {
            strcat(out, ",");
        }
        strcat(out, parts[i]);
    }
    return out;
}
''', fast='''#include <stdlib.h>
#include <string.h>

char *$f(const char **parts, size_t n) {
    size_t total = 1;
    for (size_t i = 0; i < n; i++) {
        total += strlen(parts[i]) + 1;
    }
    char *out = malloc(total);
    char *end = out;
    for (size_t i = 0; i < n; i++) {
        if (i > 0) {
            *end++ = ',';
        }
        size_t len = strlen(parts[i]);
        memcpy(end, parts[i], len);
        end += len;
    }
    *end = '\\0';
    return out;
}
''', spec="Returns a newly allocated, NUL-terminated string with the `n` parts joined by commas (`\"\"` for no parts). The caller frees it.",
        test_small='''int n = rnd_below(8);
        const char *pool[] = {"a", "bb", "", "kiln", "x9"};
        const char *parts[8];
        char want[128];
        want[0] = 0;
        for (int i = 0; i < n; i++) { parts[i] = pool[rnd_below(5)]; if (i) strcat(want, ","); strcat(want, parts[i]); }
        char *got = FN(parts, (size_t)n);
        if (strcmp(got, want) != 0) { printf("join: got '%s', want '%s'\\n", got, want); failures++; }
        free(got);''',
        test_big='''size_t n = 200000;
    const char **parts = malloc(n * sizeof(char *));
    char (*store)[10] = malloc(n * 10);
    size_t want_len = 0;
    for (size_t i = 0; i < n; i++) { snprintf(store[i], 10, "p%d", rnd_below(100000)); parts[i] = store[i]; want_len += strlen(store[i]) + 1; }
    char *got = FN(parts, n);
    if (strlen(got) != want_len - 1) { printf("wrong length %zu, want %zu\\n", strlen(got), want_len - 1); failures++; }
    free(got);''',
        example='''const char *parts[] = {"north", "south", "dock"};
    char *got = FN(parts, 3);
    if (strcmp(got, "north,south,dock") != 0) { printf("example failed: %s\\n", got); failures++; }
    free(got);
    char *none = FN(parts, 0);
    if (strcmp(none, "") != 0) { printf("example (empty) failed\\n"); failures++; }
    free(none);''',
        vocab=[("join_tags", "Join the tags of a photo"), ("route_line", "Join the stops of a route"), ("csv_row", "Join the cells of a CSV row")], extra_inc="#include <stdlib.h>\n#include <string.h>\n"),
}

PROMPTS = [
    "`{f}` in `src/{mod}.c` is hopelessly slow on real inputs: it behaves quadratically, and the nightly batch with a few hundred thousand entries takes many minutes. {doc} "
    "Fix the algorithm; the function must return exactly the same results. The header comment says what it promises.",
    "perf: `{f}` (src/{mod}.c) is O(n^2) (or worse) in practice. {doc} Make it O(n log n) or better. Same results, same signature. CI runs a large input under a timeout.",
    "We replaced the sample data with the real export (250k entries) and `{f}` in `src/{mod}.c` no longer finishes in any reasonable time. {doc} Please fix it without changing its interface or results.",
]


@family("optimize-c-algorithms", category="optimize", lang="c", kind="feature", n=10,
        summary="quadratic C (nested scans, linear lookups, strcat in loops): a large input must finish under a timeout that only a better algorithm meets")
def gen(rng, n):
    order = list(SHAPES) * 3
    rng.shuffle(order)
    used = set()
    for i in range(n):
        shape = order[i]
        sp = SHAPES[shape]
        vocab = [v for v in sp["vocab"] if (shape, v[0]) not in used] or sp["vocab"]
        f, doc = rng.choice(vocab)
        used.add((shape, f))
        mod = rng.choice(["batch", "scan", "tables", "feeds", "report"])
        proto = Template(sp["proto"]).substitute(f=f)
        header = f"#ifndef {mod.upper()}_H\n#define {mod.upper()}_H\n\n{sp['inc']}\n/* {sp['spec']} */\n{proto};\n\n#endif\n"
        start_c = f'#include "{mod}.h"\n' + sp.get("extra_inc", "") + "\n" + Template(sp["naive"]).substitute(f=f)
        sol_c = f'#include "{mod}.h"\n' + sp.get("extra_inc", "") + "\n" + Template(sp["fast"]).substitute(f=f)
        # when the naive source brings its own includes they sit after the header include: fine for C
        seed = 17 + i
        prelude = f'#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include "{mod}.h"\n\n{RNG}\n'
        basic = prelude + f"int run_basic(void) {{\n    int failures = 0;\n    {sp['example'].replace('FN', f)}\n    return failures;\n}}\n"
        hidden_c = (prelude + f"int run_correct(void) {{\n    int failures = 0;\n    rng_state = {seed}ULL * 2654435761ULL + 1;\n    for (int t = 0; t < 300; t++) {{\n        {sp['test_small'].replace('FN', f)}\n    }}\n    return failures;\n}}\n\n"
                    f"int run_perf(void) {{\n    int failures = 0;\n    rng_state = {seed}ULL * 40503ULL + 7;\n    {sp['test_big'].replace('FN', f)}\n    return failures;\n}}\n")
        files = {f"include/{mod}.h": header, f"src/{mod}.c": start_c, "tests/test_basic.c": basic,
                 "README.md": f"# {mod}\n\n## `{f}`\n\n{doc}. {sp['spec']}\n\nInputs reach hundreds of thousands of entries.\n"}
        hidden = {"tests/test_main.c": MAIN, "tests/test_hidden.c": hidden_c}
        solution = {f"src/{mod}.c": sol_c}
        prove_opt(f"{shape}/{f}", files, hidden, solution, C_CORRECT, C_PERF, C_ALL, timeout=120)
        prompt = rng.choice(PROMPTS).format(f=f, mod=mod, doc=doc + ".")
        yield Task(slug=f"{i + 1:02d}-{shape}-{f}", prompt=prompt, difficulty=sp["d"], start=files, hidden=hidden, solution=solution, verify=C_ALL, timeout_s=120,
                   tags=["complexity", "quadratic", "timeout-bar", "c"], notes={"shape": shape})
