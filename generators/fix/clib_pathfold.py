"""Path normalisation for a sandboxed file service (c): dot segments, root clamping, jail mode, trailing slashes and containment; bugs injected into the library."""
from fx import Lib, dd

from generators.fix import _lang3

README1 = dd(r'''
    # pathfold

    Lexical path normalisation for a sandboxed file service. Paths are `/`-separated byte strings given as a pointer and a length (not
    necessarily NUL-terminated). Nothing here touches the file system.

    ## `int pf_normalize(const char *path, size_t n, char *out, size_t cap, int flags)`

    Writes the normalised path and a NUL into `out` (`cap` bytes) and returns its length, or a negative error code.

    Rules, applied to the components between slashes:

    * repeated slashes count as one; empty components and `.` components vanish;
    * a `..` component removes the component before it. Components that are only dots in other numbers (`...`, `....`) are ordinary names;
    * **absolute** input (it starts with `/`): the result starts with `/`, and a `..` at the root is ignored (the root has no parent), so
      `/..` is `/` and `/a/../../b` is `/b`;
    * **relative** input: a `..` with nothing to remove is *kept*, so `a/../../b` is `../b`; the kept `..` components can never be removed
      by later ones (`../..` stays `../..`);
    * an empty result is `/` for absolute input and `.` for relative input (`""`, `.`, `a/..`);
    * a component longer than `PF_NAME_MAX` (31) bytes is `PF_E_NAME`; if the normalised path, at any moment while it is built,
      would be longer than `PF_MAX` (255) bytes the result is `PF_E_LONG`. The first error met, scanning from the left, is
      the one reported;
    * flag `PF_JAIL`: a relative input whose result begins with a kept `..` is `PF_E_ESCAPE` (reported when that `..` is met);
    * flag `PF_KEEP_SLASH`: when the input ends with `/` (its last byte), the result keeps one trailing `/`, unless the result
      is just `/` or `.`;
    * `PF_E_SPACE` when the final text plus its NUL does not fit in `cap` bytes (what is in `out` is then unspecified, but nothing
      is written beyond `cap` bytes).

    Error codes are `PF_E_NAME` (-1), `PF_E_LONG` (-2), `PF_E_ESCAPE` (-3), `PF_E_SPACE` (-4), `PF_E_RELATIVE` (-5), `PF_E_OUTSIDE` (-6).

    ## `int pf_relative_to(const char *root, const char *path, char *out, size_t cap)`

    Both arguments are NUL-terminated and must be absolute (`PF_E_RELATIVE` otherwise). Both are normalised (with no flags; their
    errors are returned as they are), and then the part of `path` below `root` is written to `out`: `/srv/data` and `/srv/data/x/../y/z`
    give `y/z`; equal paths give `.`. The check is by whole components: `/srv/database` is not inside `/srv/data` (`PF_E_OUTSIDE`).
    The root `/` contains every absolute path. Returns the length, or a negative error code (`PF_E_SPACE` as above).
''')

F2 = dd(r'''
    #ifndef PATHFOLD_H
    #define PATHFOLD_H

    #include <stddef.h>

    #define PF_NAME_MAX 31
    #define PF_MAX 255

    enum { PF_JAIL = 1, PF_KEEP_SLASH = 2 };
    enum { PF_E_NAME = -1, PF_E_LONG = -2, PF_E_ESCAPE = -3, PF_E_SPACE = -4, PF_E_RELATIVE = -5, PF_E_OUTSIDE = -6 };

    int pf_normalize(const char *path, size_t n, char *out, size_t cap, int flags);
    int pf_relative_to(const char *root, const char *path, char *out, size_t cap);

    #endif
''')

F3 = dd(r'''
    #include "pathfold.h"

    #include <string.h>

    int pf_normalize(const char *p, size_t n, char *out, size_t cap, int flags) {
        char buf[PF_MAX + 2];
        size_t len = 0, fixed = 0, i = 0, total;
        int is_abs = n > 0 && p[0] == '/';
        int keep_slash = (flags & PF_KEEP_SLASH) && n > 0 && p[n - 1] == '/';
        while (i < n) {
            size_t j, clen;
            const char *comp;
            while (i < n && p[i] == '/') i++;
            if (i >= n) break;
            j = i;
            while (j < n && p[j] != '/') j++;
            comp = p + i;
            clen = j - i;
            i = j;
            if (clen == 1 && comp[0] == '.') continue;
            if (clen == 2 && comp[0] == '.' && comp[1] == '.') {
                if (len > fixed) {
                    char *slash = NULL, *q;
                    for (q = buf + fixed; q < buf + len; q++) {
                        if (*q == '/') slash = q;
                    }
                    len = slash ? (size_t)(slash - buf) : fixed;
                    continue;
                }
                if (is_abs) continue;
                if (flags & PF_JAIL) return PF_E_ESCAPE;
                /* keep the leading ".." */
                if (len + (len ? 1 : 0) + 2 > PF_MAX) return PF_E_LONG;
                if (len) buf[len++] = '/';
                buf[len++] = '.';
                buf[len++] = '.';
                fixed = len;
                continue;
            }
            if (clen > PF_NAME_MAX) return PF_E_NAME;
            if (len + (len ? 1 : 0) + clen > PF_MAX) return PF_E_LONG;
            if (len) buf[len++] = '/';
            memcpy(buf + len, comp, clen);
            len += clen;
        }
        total = len + (is_abs ? 1 : 0);
        if (len == 0 && !is_abs) total = 1;
        if (keep_slash && len > 0) total++;
        if (total + 1 > cap) return PF_E_SPACE;
        {
            size_t o = 0;
            if (is_abs) out[o++] = '/';
            if (len == 0 && !is_abs) out[o++] = '.';
            memcpy(out + o, buf, len);
            o += len;
            if (keep_slash && len > 0) out[o++] = '/';
            out[o] = '\0';
            return (int)o;
        }
    }

    int pf_relative_to(const char *root, const char *path, char *out, size_t cap) {
        char r[PF_MAX + 2], q[PF_MAX + 2];
        int rl, ql;
        const char *rest;
        size_t rest_len;
        if (root[0] != '/' || path[0] != '/') return PF_E_RELATIVE;
        rl = pf_normalize(root, strlen(root), r, sizeof r, 0);
        if (rl < 0) return rl;
        ql = pf_normalize(path, strlen(path), q, sizeof q, 0);
        if (ql < 0) return ql;
        if (rl == 1) {
            rest = q + 1;
        } else {
            if (ql < rl || memcmp(q, r, (size_t)rl) != 0) return PF_E_OUTSIDE;
            if (ql > rl && q[rl] != '/') return PF_E_OUTSIDE;
            rest = q + rl + (ql > rl ? 1 : 0);
        }
        rest_len = strlen(rest);
        if (rest_len == 0) {
            rest = ".";
            rest_len = 1;
        }
        if (rest_len + 1 > cap) return PF_E_SPACE;
        memcpy(out, rest, rest_len + 1);
        return (int)rest_len;
    }
''')

V4 = dd(r'''
    #include "harness.h"
    #include "pathfold.h"

    int main(void) {
        char out[64];
        h_init();

        CHECK_INT(pf_normalize("/srv/./data//logs/", 18, out, sizeof out, 0), 14);
        CHECK_STR(out, "/srv/data/logs");
        CHECK_INT(pf_normalize("a/b/../../c", 11, out, sizeof out, 0), 1);
        CHECK_STR(out, "c");
        CHECK_INT(pf_normalize("/../etc", 7, out, sizeof out, 0), 4);
        CHECK_STR(out, "/etc");
        return h_report();
    }
''')

H5 = dd(r'''
    #include <stdio.h>
    #include <stdlib.h>
    #include <string.h>

    #include "harness.h"
    #include "pathfold.h"

    typedef struct { const char *in; int flags; size_t cap; int rc; const char *out; } norm_case;
    typedef struct { const char *root, *path; size_t cap; int rc; const char *out; } rel_case;

    static const norm_case NORMS[] = {
        {"", 0, 300, 1, "."},
        {"", 1, 300, 1, "."},
        {"", 2, 300, 1, "."},
        {"", 3, 300, 1, "."},
        {"/", 0, 300, 1, "/"},
        {"/", 1, 300, 1, "/"},
        {"/", 2, 300, 1, "/"},
        {"/", 3, 300, 1, "/"},
        {".", 0, 300, 1, "."},
        {".", 1, 300, 1, "."},
        {".", 2, 300, 1, "."},
        {".", 3, 300, 1, "."},
        {"./", 0, 300, 1, "."},
        {"./", 1, 300, 1, "."},
        {"./", 2, 300, 1, "."},
        {"./", 3, 300, 1, "."},
        {"..", 0, 300, 2, ".."},
        {"..", 1, 300, -3, ""},
        {"..", 2, 300, 2, ".."},
        {"..", 3, 300, -3, ""},
        {"../", 0, 300, 2, ".."},
        {"../", 1, 300, -3, ""},
        {"../", 2, 300, 3, "../"},
        {"../", 3, 300, -3, ""},
        {"/..", 0, 300, 1, "/"},
        {"/..", 1, 300, 1, "/"},
        {"/..", 2, 300, 1, "/"},
        {"/..", 3, 300, 1, "/"},
        {"/../", 0, 300, 1, "/"},
        {"/../", 1, 300, 1, "/"},
        {"/../", 2, 300, 1, "/"},
        {"/../", 3, 300, 1, "/"},
        {"a", 0, 300, 1, "a"},
        {"a", 1, 300, 1, "a"},
        {"a", 2, 300, 1, "a"},
        {"a", 3, 300, 1, "a"},
        {"/a", 0, 300, 2, "/a"},
        {"/a", 1, 300, 2, "/a"},
        {"/a", 2, 300, 2, "/a"},
        {"/a", 3, 300, 2, "/a"},
        {"a/", 0, 300, 1, "a"},
        {"a/", 1, 300, 1, "a"},
        {"a/", 2, 300, 2, "a/"},
        {"a/", 3, 300, 2, "a/"},
        {"/a/", 0, 300, 2, "/a"},
        {"/a/", 1, 300, 2, "/a"},
        {"/a/", 2, 300, 3, "/a/"},
        {"/a/", 3, 300, 3, "/a/"},
        {"a//b", 0, 300, 3, "a/b"},
        {"a//b", 1, 300, 3, "a/b"},
        {"a//b", 2, 300, 3, "a/b"},
        {"a//b", 3, 300, 3, "a/b"},
        {"//a///b//", 0, 300, 4, "/a/b"},
        {"//a///b//", 1, 300, 4, "/a/b"},
        {"//a///b//", 2, 300, 5, "/a/b/"},
        {"//a///b//", 3, 300, 5, "/a/b/"},
        {"a/./b", 0, 300, 3, "a/b"},
        {"a/./b", 1, 300, 3, "a/b"},
        {"a/./b", 2, 300, 3, "a/b"},
        {"a/./b", 3, 300, 3, "a/b"},
        {"./a/./b/.", 0, 300, 3, "a/b"},
        {"./a/./b/.", 1, 300, 3, "a/b"},
        {"./a/./b/.", 2, 300, 3, "a/b"},
        {"./a/./b/.", 3, 300, 3, "a/b"},
        {"a/../b", 0, 300, 1, "b"},
        {"a/../b", 1, 300, 1, "b"},
        {"a/../b", 2, 300, 1, "b"},
        {"a/../b", 3, 300, 1, "b"},
        {"a/b/..", 0, 300, 1, "a"},
        {"a/b/..", 1, 300, 1, "a"},
        {"a/b/..", 2, 300, 1, "a"},
        {"a/b/..", 3, 300, 1, "a"},
        {"a/b/../..", 0, 300, 1, "."},
        {"a/b/../..", 1, 300, 1, "."},
        {"a/b/../..", 2, 300, 1, "."},
        {"a/b/../..", 3, 300, 1, "."},
        {"a/b/../../..", 0, 300, 2, ".."},
        {"a/b/../../..", 1, 300, -3, ""},
        {"a/b/../../..", 2, 300, 2, ".."},
        {"a/b/../../..", 3, 300, -3, ""},
        {"/a/b/../../..", 0, 300, 1, "/"},
        {"/a/b/../../..", 1, 300, 1, "/"},
        {"/a/b/../../..", 2, 300, 1, "/"},
        {"/a/b/../../..", 3, 300, 1, "/"},
        {"/a/../../b", 0, 300, 2, "/b"},
        {"/a/../../b", 1, 300, 2, "/b"},
        {"/a/../../b", 2, 300, 2, "/b"},
        {"/a/../../b", 3, 300, 2, "/b"},
        {"a/../../b", 0, 300, 4, "../b"},
        {"a/../../b", 1, 300, -3, ""},
        {"a/../../b", 2, 300, 4, "../b"},
        {"a/../../b", 3, 300, -3, ""},
        {"../..", 0, 300, 5, "../.."},
        {"../..", 1, 300, -3, ""},
        {"../..", 2, 300, 5, "../.."},
        {"../..", 3, 300, -3, ""},
        {"../../a", 0, 300, 7, "../../a"},
        {"../../a", 1, 300, -3, ""},
        {"../../a", 2, 300, 7, "../../a"},
        {"../../a", 3, 300, -3, ""},
        {"../a/..", 0, 300, 2, ".."},
        {"../a/..", 1, 300, -3, ""},
        {"../a/..", 2, 300, 2, ".."},
        {"../a/..", 3, 300, -3, ""},
        {"../a/../..", 0, 300, 5, "../.."},
        {"../a/../..", 1, 300, -3, ""},
        {"../a/../..", 2, 300, 5, "../.."},
        {"../a/../..", 3, 300, -3, ""},
        {"a/../..", 0, 300, 2, ".."},
        {"a/../..", 1, 300, -3, ""},
        {"a/../..", 2, 300, 2, ".."},
        {"a/../..", 3, 300, -3, ""},
        {"a/../../..", 0, 300, 5, "../.."},
        {"a/../../..", 1, 300, -3, ""},
        {"a/../../..", 2, 300, 5, "../.."},
        {"a/../../..", 3, 300, -3, ""},
        {"./../a", 0, 300, 4, "../a"},
        {"./../a", 1, 300, -3, ""},
        {"./../a", 2, 300, 4, "../a"},
        {"./../a", 3, 300, -3, ""},
        {".../a", 0, 300, 5, ".../a"},
        {".../a", 1, 300, 5, ".../a"},
        {".../a", 2, 300, 5, ".../a"},
        {".../a", 3, 300, 5, ".../a"},
        {"a/...", 0, 300, 5, "a/..."},
        {"a/...", 1, 300, 5, "a/..."},
        {"a/...", 2, 300, 5, "a/..."},
        {"a/...", 3, 300, 5, "a/..."},
        {"a/..../b", 0, 300, 8, "a/..../b"},
        {"a/..../b", 1, 300, 8, "a/..../b"},
        {"a/..../b", 2, 300, 8, "a/..../b"},
        {"a/..../b", 3, 300, 8, "a/..../b"},
        {"a/.../..", 0, 300, 1, "a"},
        {"a/.../..", 1, 300, 1, "a"},
        {"a/.../..", 2, 300, 1, "a"},
        {"a/.../..", 3, 300, 1, "a"},
        {"..a", 0, 300, 3, "..a"},
        {"..a", 1, 300, 3, "..a"},
        {"..a", 2, 300, 3, "..a"},
        {"..a", 3, 300, 3, "..a"},
        {"a..", 0, 300, 3, "a.."},
        {"a..", 1, 300, 3, "a.."},
        {"a..", 2, 300, 3, "a.."},
        {"a..", 3, 300, 3, "a.."},
        {"a/..b/..c", 0, 300, 9, "a/..b/..c"},
        {"a/..b/..c", 1, 300, 9, "a/..b/..c"},
        {"a/..b/..c", 2, 300, 9, "a/..b/..c"},
        {"a/..b/..c", 3, 300, 9, "a/..b/..c"},
        {"a/.b", 0, 300, 4, "a/.b"},
        {"a/.b", 1, 300, 4, "a/.b"},
        {"a/.b", 2, 300, 4, "a/.b"},
        {"a/.b", 3, 300, 4, "a/.b"},
        {"/.hidden/../x", 0, 300, 2, "/x"},
        {"/.hidden/../x", 1, 300, 2, "/x"},
        {"/.hidden/../x", 2, 300, 2, "/x"},
        {"/.hidden/../x", 3, 300, 2, "/x"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 0, 300, 31, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 1, 300, 31, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 2, 300, 31, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 3, 300, 31, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 0, 300, -1, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 1, 300, -1, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 2, 300, -1, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 3, 300, -1, ""},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 0, 300, 32, "/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 1, 300, 32, "/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 2, 300, 32, "/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 3, 300, 32, "/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"a/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 0, 300, -1, ""},
        {"a/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 1, 300, -1, ""},
        {"a/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 2, 300, -1, ""},
        {"a/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 3, 300, -1, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/..", 0, 300, -1, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/..", 1, 300, -1, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/..", 2, 300, -1, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/..", 3, 300, -1, ""},
        {"a/../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 0, 300, -1, ""},
        {"a/../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 1, 300, -1, ""},
        {"a/../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 2, 300, -1, ""},
        {"a/../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 3, 300, -1, ""},
        {"../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 0, 300, -1, ""},
        {"../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 1, 300, -3, ""},
        {"../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 2, 300, -1, ""},
        {"../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 3, 300, -3, ""},
        {"abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij", 0, 300, -2, ""},
        {"abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij", 1, 300, -2, ""},
        {"abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij", 2, 300, -2, ""},
        {"abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij", 3, 300, -2, ""},
        {"abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghija", 0, 300, -2, ""},
        {"abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghija", 1, 300, -2, ""},
        {"abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghija", 2, 300, -2, ""},
        {"abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghija", 3, 300, -2, ""},
        {"abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij", 0, 300, 252, "abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij"},
        {"abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij", 1, 300, 252, "abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij"},
        {"abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij", 2, 300, 252, "abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij"},
        {"abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij", 3, 300, 252, "abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij"},
        {"/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghijklmnopqrs", 0, 300, -2, ""},
        {"/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghijklmnopqrs", 1, 300, -2, ""},
        {"/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghijklmnopqrs", 2, 300, -2, ""},
        {"/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghijklmnopqrs", 3, 300, -2, ""},
        {"/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghijklmnopqrst", 0, 300, -2, ""},
        {"/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghijklmnopqrst", 1, 300, -2, ""},
        {"/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghijklmnopqrst", 2, 300, -2, ""},
        {"/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghijklmnopqrst", 3, 300, -2, ""},
        {"abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/../../../../../../../../../../../../../../../../../../../../../../../../../../../../../x", 0, 300, -2, ""},
        {"abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/../../../../../../../../../../../../../../../../../../../../../../../../../../../../../x", 1, 300, -2, ""},
        {"abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/../../../../../../../../../../../../../../../../../../../../../../../../../../../../../x", 2, 300, -2, ""},
        {"abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/../../../../../../../../../../../../../../../../../../../../../../../../../../../../../x", 3, 300, -2, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../z", 0, 300, 121, "../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../z"},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../z", 1, 300, -3, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../z", 2, 300, 121, "../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../z"},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../z", 3, 300, -3, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../z", 0, 300, -2, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../z", 1, 300, -3, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../z", 2, 300, -2, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../z", 3, 300, -3, ""},
        {"a b/c d", 0, 300, 7, "a b/c d"},
        {"a b/c d", 1, 300, 7, "a b/c d"},
        {"a b/c d", 2, 300, 7, "a b/c d"},
        {"a b/c d", 3, 300, 7, "a b/c d"},
        {"a/b/c/d/e/../../..", 0, 300, 3, "a/b"},
        {"a/b/c/d/e/../../..", 1, 300, 3, "a/b"},
        {"a/b/c/d/e/../../..", 2, 300, 3, "a/b"},
        {"a/b/c/d/e/../../..", 3, 300, 3, "a/b"},
        {"/a/b/c/./../d/", 0, 300, 6, "/a/b/d"},
        {"/a/b/c/./../d/", 1, 300, 6, "/a/b/d"},
        {"/a/b/c/./../d/", 2, 300, 7, "/a/b/d/"},
        {"/a/b/c/./../d/", 3, 300, 7, "/a/b/d/"},
        {"a/b/", 0, 300, 3, "a/b"},
        {"a/b/", 1, 300, 3, "a/b"},
        {"a/b/", 2, 300, 4, "a/b/"},
        {"a/b/", 3, 300, 4, "a/b/"},
        {"a/b//", 0, 300, 3, "a/b"},
        {"a/b//", 1, 300, 3, "a/b"},
        {"a/b//", 2, 300, 4, "a/b/"},
        {"a/b//", 3, 300, 4, "a/b/"},
        {"./", 0, 300, 1, "."},
        {"./", 1, 300, 1, "."},
        {"./", 2, 300, 1, "."},
        {"./", 3, 300, 1, "."},
        {"././", 0, 300, 1, "."},
        {"././", 1, 300, 1, "."},
        {"././", 2, 300, 1, "."},
        {"././", 3, 300, 1, "."},
        {"a/.", 0, 300, 1, "a"},
        {"a/.", 1, 300, 1, "a"},
        {"a/.", 2, 300, 1, "a"},
        {"a/.", 3, 300, 1, "a"},
        {"a/..", 0, 300, 1, "."},
        {"a/..", 1, 300, 1, "."},
        {"a/..", 2, 300, 1, "."},
        {"a/..", 3, 300, 1, "."},
        {"/a/..", 0, 300, 1, "/"},
        {"/a/..", 1, 300, 1, "/"},
        {"/a/..", 2, 300, 1, "/"},
        {"/a/..", 3, 300, 1, "/"},
        {"a/../", 0, 300, 1, "."},
        {"a/../", 1, 300, 1, "."},
        {"a/../", 2, 300, 1, "."},
        {"a/../", 3, 300, 1, "."},
        {"a/b/../", 0, 300, 1, "a"},
        {"a/b/../", 1, 300, 1, "a"},
        {"a/b/../", 2, 300, 2, "a/"},
        {"a/b/../", 3, 300, 2, "a/"},
        {"..//..//", 0, 300, 5, "../.."},
        {"..//..//", 1, 300, -3, ""},
        {"..//..//", 2, 300, 6, "../../"},
        {"..//..//", 3, 300, -3, ""},
        {"a\\b/..", 0, 300, 1, "."},
        {"a\\b/..", 1, 300, 1, "."},
        {"a\\b/..", 2, 300, 1, "."},
        {"a\\b/..", 3, 300, 1, "."},
        {"-/+/*", 0, 300, 5, "-/+/*"},
        {"-/+/*", 1, 300, 5, "-/+/*"},
        {"-/+/*", 2, 300, 5, "-/+/*"},
        {"-/+/*", 3, 300, 5, "-/+/*"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 0, 300, 253, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 1, 300, 253, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 2, 300, 253, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 3, 300, 253, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 0, 300, 254, "/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 1, 300, 254, "/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 2, 300, 254, "/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 3, 300, 254, "/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 0, 300, 253, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 1, 300, 253, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 2, 300, 254, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx/"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 3, 300, 254, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxx/"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 0, 300, 254, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 1, 300, 254, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 2, 300, 254, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 3, 300, 254, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 0, 300, 255, "/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 1, 300, 255, "/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 2, 300, 255, "/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 3, 300, 255, "/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 0, 300, 254, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 1, 300, 254, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 2, 300, 255, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 3, 300, 255, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 0, 300, 255, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 1, 300, 255, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 2, 300, 255, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 3, 300, 255, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 0, 300, 256, "/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 1, 300, 256, "/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 2, 300, 256, "/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 3, 300, 256, "/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 0, 300, 255, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 1, 300, 255, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 2, 300, 256, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 3, 300, 256, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x", 0, 300, -2, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x", 1, 300, -2, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x", 2, 300, -2, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x", 3, 300, -2, ""},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x", 0, 300, -2, ""},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x", 1, 300, -2, ""},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x", 2, 300, -2, ""},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x", 3, 300, -2, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x/", 0, 300, -2, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x/", 1, 300, -2, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x/", 2, 300, -2, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x/", 3, 300, -2, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x", 0, 300, -2, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x", 1, 300, -2, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x", 2, 300, -2, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x", 3, 300, -2, ""},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x", 0, 300, -2, ""},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x", 1, 300, -2, ""},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x", 2, 300, -2, ""},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x", 3, 300, -2, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x/", 0, 300, -2, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x/", 1, 300, -2, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x/", 2, 300, -2, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/x/", 3, 300, -2, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xx", 0, 300, -2, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xx", 1, 300, -2, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xx", 2, 300, -2, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xx", 3, 300, -2, ""},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xx", 0, 300, -2, ""},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xx", 1, 300, -2, ""},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xx", 2, 300, -2, ""},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xx", 3, 300, -2, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xx/", 0, 300, -2, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xx/", 1, 300, -2, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xx/", 2, 300, -2, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xx/", 3, 300, -2, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../..", 0, 300, 251, "../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../.."},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../..", 1, 300, -3, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../..", 2, 300, 251, "../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../.."},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../..", 3, 300, -3, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../a", 0, 300, 253, "../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../a"},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../a", 1, 300, -3, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../a", 2, 300, 253, "../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../a"},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../a", 3, 300, -3, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../..", 0, 300, 254, "../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../.."},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../..", 1, 300, -3, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../..", 2, 300, 254, "../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../.."},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../..", 3, 300, -3, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../a", 0, 300, -2, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../a", 1, 300, -3, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../a", 2, 300, -2, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../a", 3, 300, -3, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../..", 0, 300, -2, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../..", 1, 300, -3, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../..", 2, 300, -2, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../..", 3, 300, -3, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../a", 0, 300, -2, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../a", 1, 300, -3, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../a", 2, 300, -2, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../a", 3, 300, -3, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../..", 0, 300, -2, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../..", 1, 300, -3, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../..", 2, 300, -2, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../..", 3, 300, -3, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../a", 0, 300, -2, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../a", 1, 300, -3, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../a", 2, 300, -2, ""},
        {"../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../../a", 3, 300, -3, ""},
        {"a./b", 0, 300, 4, "a./b"},
        {"a./b", 1, 300, 4, "a./b"},
        {"a./b", 2, 300, 4, "a./b"},
        {"a./b", 3, 300, 4, "a./b"},
        {"../a.", 0, 300, 5, "../a."},
        {"../a.", 1, 300, -3, ""},
        {"../a.", 2, 300, 5, "../a."},
        {"../a.", 3, 300, -3, ""},
        {"x./..", 0, 300, 1, "."},
        {"x./..", 1, 300, 1, "."},
        {"x./..", 2, 300, 1, "."},
        {"x./..", 3, 300, 1, "."},
        {"a./../b", 0, 300, 1, "b"},
        {"a./../b", 1, 300, 1, "b"},
        {"a./../b", 2, 300, 1, "b"},
        {"a./../b", 3, 300, 1, "b"},
        {"a.", 0, 300, 2, "a."},
        {"a.", 1, 300, 2, "a."},
        {"a.", 2, 300, 2, "a."},
        {"a.", 3, 300, 2, "a."},
        {"..x", 0, 300, 3, "..x"},
        {"..x", 1, 300, 3, "..x"},
        {"..x", 2, 300, 3, "..x"},
        {"..x", 3, 300, 3, "..x"},
        {"x..", 0, 300, 3, "x.."},
        {"x..", 1, 300, 3, "x.."},
        {"x..", 2, 300, 3, "x.."},
        {"x..", 3, 300, 3, "x.."},
        {"./a.", 0, 300, 2, "a."},
        {"./a.", 1, 300, 2, "a."},
        {"./a.", 2, 300, 2, "a."},
        {"./a.", 3, 300, 2, "a."},
        {".a/..", 0, 300, 1, "."},
        {".a/..", 1, 300, 1, "."},
        {".a/..", 2, 300, 1, "."},
        {".a/..", 3, 300, 1, "."},
        {"a../..", 0, 300, 1, "."},
        {"a../..", 1, 300, 1, "."},
        {"a../..", 2, 300, 1, "."},
        {"a../..", 3, 300, 1, "."},
        {"../.", 0, 300, 2, ".."},
        {"../.", 1, 300, -3, ""},
        {"../.", 2, 300, 2, ".."},
        {"../.", 3, 300, -3, ""},
        {"b./a../..", 0, 300, 2, "b."},
        {"b./a../..", 1, 300, 2, "b."},
        {"b./a../..", 2, 300, 2, "b."},
        {"b./a../..", 3, 300, 2, "b."},
        {".", 0, 0, -4, ""},
        {".", 1, 0, -4, ""},
        {".", 2, 0, -4, ""},
        {".", 3, 0, -4, ""},
        {".", 0, 1, -4, ""},
        {".", 1, 1, -4, ""},
        {".", 2, 1, -4, ""},
        {".", 3, 1, -4, ""},
        {".", 0, 2, 1, "."},
        {".", 1, 2, 1, "."},
        {".", 2, 2, 1, "."},
        {".", 3, 2, 1, "."},
        {".", 0, 3, 1, "."},
        {".", 1, 3, 1, "."},
        {".", 2, 3, 1, "."},
        {".", 3, 3, 1, "."},
        {"", 0, 0, -4, ""},
        {"", 1, 0, -4, ""},
        {"", 2, 0, -4, ""},
        {"", 3, 0, -4, ""},
        {"", 0, 1, -4, ""},
        {"", 1, 1, -4, ""},
        {"", 2, 1, -4, ""},
        {"", 3, 1, -4, ""},
        {"", 0, 2, 1, "."},
        {"", 1, 2, 1, "."},
        {"", 2, 2, 1, "."},
        {"", 3, 2, 1, "."},
        {"", 0, 3, 1, "."},
        {"", 1, 3, 1, "."},
        {"", 2, 3, 1, "."},
        {"", 3, 3, 1, "."},
        {"a/..", 0, 0, -4, ""},
        {"a/..", 1, 0, -4, ""},
        {"a/..", 2, 0, -4, ""},
        {"a/..", 3, 0, -4, ""},
        {"a/..", 0, 1, -4, ""},
        {"a/..", 1, 1, -4, ""},
        {"a/..", 2, 1, -4, ""},
        {"a/..", 3, 1, -4, ""},
        {"a/..", 0, 2, 1, "."},
        {"a/..", 1, 2, 1, "."},
        {"a/..", 2, 2, 1, "."},
        {"a/..", 3, 2, 1, "."},
        {"a/..", 0, 3, 1, "."},
        {"a/..", 1, 3, 1, "."},
        {"a/..", 2, 3, 1, "."},
        {"a/..", 3, 3, 1, "."},
        {"./", 0, 0, -4, ""},
        {"./", 1, 0, -4, ""},
        {"./", 2, 0, -4, ""},
        {"./", 3, 0, -4, ""},
        {"./", 0, 1, -4, ""},
        {"./", 1, 1, -4, ""},
        {"./", 2, 1, -4, ""},
        {"./", 3, 1, -4, ""},
        {"./", 0, 2, 1, "."},
        {"./", 1, 2, 1, "."},
        {"./", 2, 2, 1, "."},
        {"./", 3, 2, 1, "."},
        {"./", 0, 3, 1, "."},
        {"./", 1, 3, 1, "."},
        {"./", 2, 3, 1, "."},
        {"./", 3, 3, 1, "."},
        {"a/../", 0, 0, -4, ""},
        {"a/../", 1, 0, -4, ""},
        {"a/../", 2, 0, -4, ""},
        {"a/../", 3, 0, -4, ""},
        {"a/../", 0, 1, -4, ""},
        {"a/../", 1, 1, -4, ""},
        {"a/../", 2, 1, -4, ""},
        {"a/../", 3, 1, -4, ""},
        {"a/../", 0, 2, 1, "."},
        {"a/../", 1, 2, 1, "."},
        {"a/../", 2, 2, 1, "."},
        {"a/../", 3, 2, 1, "."},
        {"a/../", 0, 3, 1, "."},
        {"a/../", 1, 3, 1, "."},
        {"a/../", 2, 3, 1, "."},
        {"a/../", 3, 3, 1, "."},
        {"/", 0, 0, -4, ""},
        {"/", 1, 0, -4, ""},
        {"/", 2, 0, -4, ""},
        {"/", 3, 0, -4, ""},
        {"/", 0, 1, -4, ""},
        {"/", 1, 1, -4, ""},
        {"/", 2, 1, -4, ""},
        {"/", 3, 1, -4, ""},
        {"/", 0, 2, 1, "/"},
        {"/", 1, 2, 1, "/"},
        {"/", 2, 2, 1, "/"},
        {"/", 3, 2, 1, "/"},
        {"/", 0, 3, 1, "/"},
        {"/", 1, 3, 1, "/"},
        {"/", 2, 3, 1, "/"},
        {"/", 3, 3, 1, "/"},
        {"//", 0, 0, -4, ""},
        {"//", 1, 0, -4, ""},
        {"//", 2, 0, -4, ""},
        {"//", 3, 0, -4, ""},
        {"//", 0, 1, -4, ""},
        {"//", 1, 1, -4, ""},
        {"//", 2, 1, -4, ""},
        {"//", 3, 1, -4, ""},
        {"//", 0, 2, 1, "/"},
        {"//", 1, 2, 1, "/"},
        {"//", 2, 2, 1, "/"},
        {"//", 3, 2, 1, "/"},
        {"//", 0, 3, 1, "/"},
        {"//", 1, 3, 1, "/"},
        {"//", 2, 3, 1, "/"},
        {"//", 3, 3, 1, "/"},
        {"/.", 0, 0, -4, ""},
        {"/.", 1, 0, -4, ""},
        {"/.", 2, 0, -4, ""},
        {"/.", 3, 0, -4, ""},
        {"/.", 0, 1, -4, ""},
        {"/.", 1, 1, -4, ""},
        {"/.", 2, 1, -4, ""},
        {"/.", 3, 1, -4, ""},
        {"/.", 0, 2, 1, "/"},
        {"/.", 1, 2, 1, "/"},
        {"/.", 2, 2, 1, "/"},
        {"/.", 3, 2, 1, "/"},
        {"/.", 0, 3, 1, "/"},
        {"/.", 1, 3, 1, "/"},
        {"/.", 2, 3, 1, "/"},
        {"/.", 3, 3, 1, "/"},
        {"a/", 2, 1, -4, ""},
        {"a/", 0, 1, -4, ""},
        {"a/", 2, 2, -4, ""},
        {"a/", 0, 2, 1, "a"},
        {"a/", 2, 3, 2, "a/"},
        {"a/", 0, 3, 1, "a"},
        {"a/", 2, 4, 2, "a/"},
        {"a/", 0, 4, 1, "a"},
        {"a/", 2, 5, 2, "a/"},
        {"a/", 0, 5, 1, "a"},
        {"a/", 2, 6, 2, "a/"},
        {"a/", 0, 6, 1, "a"},
        {"a/", 2, 7, 2, "a/"},
        {"a/", 0, 7, 1, "a"},
        {"/a/", 2, 1, -4, ""},
        {"/a/", 0, 1, -4, ""},
        {"/a/", 2, 2, -4, ""},
        {"/a/", 0, 2, -4, ""},
        {"/a/", 2, 3, -4, ""},
        {"/a/", 0, 3, 2, "/a"},
        {"/a/", 2, 4, 3, "/a/"},
        {"/a/", 0, 4, 2, "/a"},
        {"/a/", 2, 5, 3, "/a/"},
        {"/a/", 0, 5, 2, "/a"},
        {"/a/", 2, 6, 3, "/a/"},
        {"/a/", 0, 6, 2, "/a"},
        {"/a/", 2, 7, 3, "/a/"},
        {"/a/", 0, 7, 2, "/a"},
        {"x/y/", 2, 1, -4, ""},
        {"x/y/", 0, 1, -4, ""},
        {"x/y/", 2, 2, -4, ""},
        {"x/y/", 0, 2, -4, ""},
        {"x/y/", 2, 3, -4, ""},
        {"x/y/", 0, 3, -4, ""},
        {"x/y/", 2, 4, -4, ""},
        {"x/y/", 0, 4, 3, "x/y"},
        {"x/y/", 2, 5, 4, "x/y/"},
        {"x/y/", 0, 5, 3, "x/y"},
        {"x/y/", 2, 6, 4, "x/y/"},
        {"x/y/", 0, 6, 3, "x/y"},
        {"x/y/", 2, 7, 4, "x/y/"},
        {"x/y/", 0, 7, 3, "x/y"},
        {"ab/", 2, 1, -4, ""},
        {"ab/", 0, 1, -4, ""},
        {"ab/", 2, 2, -4, ""},
        {"ab/", 0, 2, -4, ""},
        {"ab/", 2, 3, -4, ""},
        {"ab/", 0, 3, 2, "ab"},
        {"ab/", 2, 4, 3, "ab/"},
        {"ab/", 0, 4, 2, "ab"},
        {"ab/", 2, 5, 3, "ab/"},
        {"ab/", 0, 5, 2, "ab"},
        {"ab/", 2, 6, 3, "ab/"},
        {"ab/", 0, 6, 2, "ab"},
        {"ab/", 2, 7, 3, "ab/"},
        {"ab/", 0, 7, 2, "ab"},
        {"a/b/", 2, 1, -4, ""},
        {"a/b/", 0, 1, -4, ""},
        {"a/b/", 2, 2, -4, ""},
        {"a/b/", 0, 2, -4, ""},
        {"a/b/", 2, 3, -4, ""},
        {"a/b/", 0, 3, -4, ""},
        {"a/b/", 2, 4, -4, ""},
        {"a/b/", 0, 4, 3, "a/b"},
        {"a/b/", 2, 5, 4, "a/b/"},
        {"a/b/", 0, 5, 3, "a/b"},
        {"a/b/", 2, 6, 4, "a/b/"},
        {"a/b/", 0, 6, 3, "a/b"},
        {"a/b/", 2, 7, 4, "a/b/"},
        {"a/b/", 0, 7, 3, "a/b"},
        {"a/b", 2, 0, -4, ""},
        {"a/b", 2, 1, -4, ""},
        {"a/b", 2, 2, -4, ""},
        {"a/b", 2, 3, -4, ""},
        {"a/b", 2, 4, 3, "a/b"},
        {"a/b", 2, 5, 3, "a/b"},
        {"a/b", 2, 6, 3, "a/b"},
        {"a/b", 2, 7, 3, "a/b"},
        {"a/b", 2, 8, 3, "a/b"},
        {"/a/b/", 2, 0, -4, ""},
        {"/a/b/", 2, 1, -4, ""},
        {"/a/b/", 2, 2, -4, ""},
        {"/a/b/", 2, 3, -4, ""},
        {"/a/b/", 2, 4, -4, ""},
        {"/a/b/", 2, 5, -4, ""},
        {"/a/b/", 2, 6, 5, "/a/b/"},
        {"/a/b/", 2, 7, 5, "/a/b/"},
        {"/a/b/", 2, 8, 5, "/a/b/"},
        {"../x", 2, 0, -4, ""},
        {"../x", 2, 1, -4, ""},
        {"../x", 2, 2, -4, ""},
        {"../x", 2, 3, -4, ""},
        {"../x", 2, 4, -4, ""},
        {"../x", 2, 5, 4, "../x"},
        {"../x", 2, 6, 4, "../x"},
        {"../x", 2, 7, 4, "../x"},
        {"../x", 2, 8, 4, "../x"},
        {"/", 2, 0, -4, ""},
        {"/", 2, 1, -4, ""},
        {"/", 2, 2, 1, "/"},
        {"/", 2, 3, 1, "/"},
        {"/", 2, 4, 1, "/"},
        {"/", 2, 5, 1, "/"},
        {"/", 2, 6, 1, "/"},
        {"/", 2, 7, 1, "/"},
        {"/", 2, 8, 1, "/"},
        {"a/../..", 2, 0, -4, ""},
        {"a/../..", 2, 1, -4, ""},
        {"a/../..", 2, 2, -4, ""},
        {"a/../..", 2, 3, 2, ".."},
        {"a/../..", 2, 4, 2, ".."},
        {"a/../..", 2, 5, 2, ".."},
        {"a/../..", 2, 6, 2, ".."},
        {"a/../..", 2, 7, 2, ".."},
        {"a/../..", 2, 8, 2, ".."},
        {"//../c/", 1, 300, 2, "/c"},
        {"../../dir/a/.../.../.../../", 3, 300, -3, ""},
        {"../../a/file.txt/./xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/..", 0, 40, 16, "../../a/file.txt"},
        {"b/d/b/..", 0, 300, 3, "b/d"},
        {"file.txt/b/...", 1, 12, -4, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/b/", 1, 300, -1, ""},
        {"/.../file.txt/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/..././xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx//d/..", 0, 12, -1, ""},
        {"file.txt//dir/d/.../", 1, 300, 18, "file.txt/dir/d/..."},
        {"./xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/dir/b/../d/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/file.txt", 0, 300, 78, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/dir/d/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/file.txt"},
        {"/.././a/../.", 3, 300, 1, "/"},
        {"b/c/dir/d/a/../", 0, 300, 9, "b/c/dir/d"},
        {"//d/c/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/../..", 3, 6, -1, ""},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 0, 300, -1, ""},
        {"..", 3, 40, -3, ""},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/b", 2, 6, -1, ""},
        {"b/file.txt/.////a/dir/d/", 0, 12, -4, ""},
        {"c/", 0, 300, 1, "c"},
        {"../.../../.../../c/../b/b", 1, 40, -3, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/file.txt/b/file.txt/.../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/..", 0, 300, -1, ""},
        {"/", 0, 40, 1, "/"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/a/dir//d/../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/b/file.txt", 1, 12, -1, ""},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/..", 0, 300, 1, "/"},
        {"./b/file.txt//../../dir/./b", 2, 40, 5, "dir/b"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/./dir/d//", 0, 300, 37, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/dir/d"},
        {"//../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/d/./../.", 2, 40, -1, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx//dir/../../.../d/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 0, 6, -1, ""},
        {"../../b/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 2, 300, -1, ""},
        {"././dir/../..//../..", 1, 300, -3, ""},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/d/..//.../../b/../b", 3, 300, 34, "/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/b"},
        {"/a/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 0, 6, -1, ""},
        {"/d/dir/./xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/b/c/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 0, 300, -1, ""},
        {"/", 1, 40, 1, "/"},
        {"/d/b/d/../file.txt", 1, 300, 13, "/d/b/file.txt"},
        {"/b/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/b/file.txt", 1, 300, 45, "/b/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/b/file.txt"},
        {"c/../file.txt/../b/b/", 1, 300, 3, "b/b"},
        {"b/a/a", 1, 12, 5, "b/a/a"},
        {"/./../file.txt/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/...", 0, 300, 45, "/file.txt/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/..."},
        {"/..//", 1, 6, 1, "/"},
        {"", 2, 6, 1, "."},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/dir/file.txt//file.txt/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 2, 40, -1, ""},
        {"c/././dir/.../d/c/d", 2, 300, 15, "c/dir/.../d/c/d"},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/../../c/d/.../dir/.../b/", 2, 12, -4, ""},
        {"/../file.txt/a/", 0, 300, 11, "/file.txt/a"},
        {".../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 3, 12, -1, ""},
        {"/b//xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/a/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/file.txt/dir//", 0, 6, -1, ""},
        {"dir/..", 2, 6, 1, "."},
        {"/file.txt/dir/dir/a/file.txt", 2, 300, 28, "/file.txt/dir/dir/a/file.txt"},
        {"", 3, 300, 1, "."},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/c/./c/dir/./..", 2, 12, -4, ""},
        {".../d/./.", 0, 6, 5, ".../d"},
        {"/c/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/file.txt/b//file.txt", 3, 12, -1, ""},
        {"../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/file.txt/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/c", 0, 300, -1, ""},
        {"/../dir/.././../c/dir/..", 1, 300, 2, "/c"},
        {"/", 1, 300, 1, "/"},
        {"/a/a/file.txt/a/file.txt", 2, 300, 24, "/a/a/file.txt/a/file.txt"},
        {"", 0, 6, 1, "."},
        {"d/a/d/", 1, 6, 5, "d/a/d"},
        {"b/../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/c/b/c", 2, 12, -4, ""},
        {"/dir/a/./../file.txt/dir/", 0, 6, -4, ""},
        {"file.txt/c/../a/..", 2, 12, 8, "file.txt"},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/a/../..", 1, 300, -1, ""},
        {"..", 3, 300, -3, ""},
        {"../dir/b/../", 3, 6, -3, ""},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/c/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/c/.../b/../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 1, 12, -1, ""},
        {"../../file.txt", 2, 40, 14, "../../file.txt"},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/..", 1, 40, -1, ""},
        {"file.txt/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/..", 3, 300, -1, ""},
        {"b/b/../dir", 3, 6, 5, "b/dir"},
        {"/a/...//xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/file.txt/d/../a/..", 2, 300, 47, "/a/.../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/file.txt"},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/b/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/c/b/a/...", 1, 300, -1, ""},
        {"/a", 2, 6, 2, "/a"},
        {"c/.../file.txt/.././dir/a/.../d", 0, 12, -4, ""},
        {"dir/../.../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/.../../dir/c", 1, 300, 41, ".../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/dir/c"},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 2, 300, -1, ""},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/a/dir/../", 1, 12, -4, ""},
        {"..././file.txt/../.../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/b", 2, 300, 41, ".../.../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/b"},
        {"../b/", 3, 300, -3, ""},
        {"/../file.txt/../.../../../../a/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 3, 12, -4, ""},
        {"", 2, 300, 1, "."},
        {"b/b/../d/...", 1, 300, 7, "b/d/..."},
        {"c/../...//dir", 0, 6, -4, ""},
        {"dir/dir/../d/c/../b/", 1, 300, 7, "dir/d/b"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/d/dir/d/c/../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/a/d", 2, 300, 75, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/d/dir/d/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/a/d"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 2, 300, 32, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/"},
        {"/../a/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 0, 300, -1, ""},
        {".../.", 0, 6, 3, "..."},
        {"b/../.../...", 1, 300, 7, ".../..."},
        {"", 0, 300, 1, "."},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx//dir/file.txt/../a/file.txt/.", 0, 40, -1, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/b", 0, 12, -1, ""},
        {"/", 2, 300, 1, "/"},
        {"d//d", 2, 300, 3, "d/d"},
        {"d/d/dir", 2, 300, 7, "d/d/dir"},
        {"/a/../a/b/../..", 1, 300, 1, "/"},
        {"//xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/../../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 2, 300, 32, "/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"", 0, 12, 1, "."},
        {"", 2, 12, 1, "."},
        {"./xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 0, 40, 31, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"/../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/c//./.../file.txt/dir", 2, 40, -1, ""},
        {"/...", 1, 12, 4, "/..."},
        {"//d/b/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/./xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/../dir/", 0, 300, -1, ""},
        {"/", 3, 40, 1, "/"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/../d/a/file.txt/a/c/../dir", 2, 12, -4, ""},
        {"../../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 3, 300, -3, ""},
        {"file.txt/../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/d/..", 0, 6, -1, ""},
        {"//../d/.../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/dir", 1, 300, -1, ""},
        {"c/../..//.././xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx//", 2, 300, 38, "../../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/"},
        {"/../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/./d/.../", 1, 300, 38, "/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/d/..."},
        {"/d/file.txt/", 0, 40, 11, "/d/file.txt"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/b/c/", 1, 40, -1, ""},
        {"b//d/b/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/file.txt/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 0, 40, -1, ""},
        {"/dir/d/c/dir/file.txt/a/dir/b/", 1, 40, 29, "/dir/d/c/dir/file.txt/a/dir/b"},
        {"a/dir/dir/file.txt/c/../../a/a", 2, 6, -4, ""},
        {"dir/a/", 2, 12, 6, "dir/a/"},
        {"/c/./../b/b/..", 3, 300, 2, "/b"},
        {"/./.././d//./../", 0, 40, 1, "/"},
        {"../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/b", 3, 12, -3, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/c/c/.../.../d/file.txt/dir/b", 2, 300, -1, ""},
        {"/b/.//xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/d/./.../", 0, 300, 40, "/b/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/d/..."},
        {"./a/d/b/../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/.", 0, 300, 35, "a/d/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"/d/../dir/file.txt/d", 3, 40, 15, "/dir/file.txt/d"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/b/d/..//..//", 3, 300, 32, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/"},
        {"b/./b", 0, 300, 3, "b/b"},
        {"/", 1, 12, 1, "/"},
        {"/..././../b/./xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/d", 3, 300, 36, "/b/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/d"},
        {"/./c/../..", 0, 300, 1, "/"},
        {"/file.txt/../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 1, 12, -4, ""},
        {"c", 1, 12, 1, "c"},
        {"dir/../.", 3, 40, 1, "."},
        {"//", 3, 300, 1, "/"},
        {"/file.txt", 0, 300, 9, "/file.txt"},
        {".", 1, 6, 1, "."},
        {"/a/..//a/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 3, 40, 34, "/a/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"file.txt/dir/", 3, 300, 13, "file.txt/dir/"},
        {"/d//xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/./", 3, 300, -1, ""},
        {"/b/./", 2, 12, 3, "/b/"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 1, 40, -1, ""},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/d/../", 2, 12, -4, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/file.txt/..", 1, 6, -1, ""},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 0, 300, -1, ""},
        {"./xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 0, 6, -4, ""},
        {".../dir", 2, 12, 7, ".../dir"},
        {"../../a/..", 2, 300, 5, "../.."},
        {"..//..././b/.../", 3, 12, -3, ""},
        {"//..", 1, 300, 1, "/"},
        {"/file.txt/dir/../c", 3, 300, 11, "/file.txt/c"},
        {"/d/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/file.txt/a//a/c/.../", 3, 40, -1, ""},
        {"../file.txt", 2, 300, 11, "../file.txt"},
        {"", 0, 300, 1, "."},
        {".../...//xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/c/file.txt/../c/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 3, 6, -1, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/file.txt/dir", 2, 300, 44, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/file.txt/dir"},
        {"b/dir", 0, 40, 5, "b/dir"},
        {"/file.txt/b/../a/dir/c/", 0, 12, -4, ""},
        {"a/file.txt/d/file.txt/d", 1, 300, 23, "a/file.txt/d/file.txt/d"},
        {"/../a/dir/b/.../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/c/../.", 2, 300, -1, ""},
        {"d", 2, 6, 1, "d"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/c/a/b/../d", 1, 6, -4, ""},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/c/file.txt/a/c/c/d/", 2, 300, 52, "/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/c/file.txt/a/c/c/d/"},
        {"d/c/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/.../..//a/dir", 1, 300, 41, "d/c/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/a/dir"},
        {"/dir/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/d/.//../file.txt/c/../", 2, 300, 46, "/dir/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/file.txt/"},
        {"../a/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/../b/..", 1, 300, -3, ""},
        {"../c/../../b/b/dir/dir/.", 3, 40, -3, ""},
        {"../c/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/d/d//c/a/", 3, 6, -3, ""},
        {"b/file.txt/d/file.txt/./file.txt/", 1, 12, -4, ""},
        {"/file.txt/d/a/./c/..", 0, 12, -4, ""},
        {"", 3, 300, 1, "."},
        {"/dir//../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/file.txt/../...", 0, 40, 36, "/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/..."},
        {"/./../", 1, 40, 1, "/"},
        {"/d/dir/./.././file.txt/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/file.txt/b", 1, 300, 54, "/d/file.txt/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/file.txt/b"},
        {"/../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/./file.txt/b/", 3, 6, -1, ""},
        {"/", 0, 12, 1, "/"},
        {"b/../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 1, 300, 31, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"/", 0, 300, 1, "/"},
        {"/./xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/dir/.//c/a/", 2, 300, 41, "/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/dir/c/a/"},
        {"file.txt/d/b/file.txt/..", 1, 40, 12, "file.txt/d/b"},
        {"", 3, 300, 1, "."},
        {"/file.txt/../c", 0, 40, 2, "/c"},
        {"", 3, 300, 1, "."},
        {"/file.txt/b/d/..", 3, 12, 11, "/file.txt/b"},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/./.../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/dir/", 0, 300, -1, ""},
        {".././xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/c/../b/./..", 3, 6, -3, ""},
        {"c/b/b/../c/file.txt", 1, 300, 14, "c/b/c/file.txt"},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/..././a/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/./d/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/..", 2, 300, -1, ""},
        {"../..//dir/./../dir/b/", 1, 40, -3, ""},
        {"/c", 0, 40, 2, "/c"},
        {"../d/", 3, 6, -3, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 2, 12, -4, ""},
        {"", 0, 12, 1, "."},
        {"/../b/././../../c/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 3, 300, 34, "/c/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"d/./file.txt/file.txt/../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/../b/.../", 1, 6, -4, ""},
        {"a", 3, 300, 1, "a"},
        {"../a/d/../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/dir/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 0, 300, -1, ""},
        {"/..//../d/d/../file.txt/file.txt", 1, 300, 20, "/d/file.txt/file.txt"},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/.../b/", 2, 300, -1, ""},
        {"../c/c/../a/b/", 0, 300, 8, "../c/a/b"},
        {"dir/a/b/../file.txt/..././file.txt/c", 0, 300, 29, "dir/a/file.txt/.../file.txt/c"},
        {"//../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 2, 300, 32, "/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
        {"/", 0, 300, 1, "/"},
        {"/../../../a/b/a/../file.txt/..", 0, 6, 4, "/a/b"},
        {"c/../../dir/a", 2, 40, 8, "../dir/a"},
        {"./b/c", 3, 300, 3, "b/c"},
        {"/", 2, 300, 1, "/"},
        {"/c//../../", 3, 12, 1, "/"},
        {".../dir//b/b/file.txt/", 2, 300, 21, ".../dir/b/b/file.txt/"},
        {"file.txt", 3, 300, 8, "file.txt"},
        {"/.././file.txt/.../../c/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 2, 6, -4, ""},
        {"/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/../file.txt/", 2, 300, -1, ""},
        {"/d/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 3, 6, -4, ""},
        {"d/c/b", 0, 300, 5, "d/c/b"},
        {"/b/dir/./", 2, 12, 7, "/b/dir/"},
        {"./.../file.txt", 2, 12, -4, ""},
        {"b/b/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 3, 40, -1, ""},
        {"./../dir/../b/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/", 0, 300, -1, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/././xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/../b", 2, 6, -4, ""},
        {"/../xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 1, 300, -1, ""},
        {"dir/b/a/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/a/a//file.txt/..", 1, 300, -1, ""},
        {"b/./xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx//dir/dir/...", 0, 300, -1, ""},
        {"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/dir/", 1, 300, 35, "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/dir"},
        {"/dir/../d/./dir/b/c/file.txt", 1, 40, 19, "/d/dir/b/c/file.txt"},
        {"./xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx/file.txt/c/a//", 0, 12, -4, ""},
    };

    static const rel_case RELS[] = {
        {"/srv/data", "/srv/data", 300, 1, "."},
        {"/srv/data", "/srv/data/", 300, 1, "."},
        {"/srv/data", "/srv/data/x/../y/z", 300, 3, "y/z"},
        {"/srv/data", "/srv/database", 300, -6, ""},
        {"/srv/data", "/srv/data2/x", 300, -6, ""},
        {"/srv/data/", "/srv/data/a", 300, 1, "a"},
        {"/srv/data", "/srv", 300, -6, ""},
        {"/srv/data", "/", 300, -6, ""},
        {"/", "/", 300, 1, "."},
        {"/", "/a/b", 300, 3, "a/b"},
        {"/", "/a/../b/", 300, 1, "b"},
        {"/", "/..", 300, 1, "."},
        {"//srv//data/./", "/srv/data/../data/q", 300, 1, "q"},
        {"/srv/data", "/srv/data/../other", 300, -6, ""},
        {"/srv/data/..", "/srv/x", 300, 1, "x"},
        {"/a", "/a/b/c/d", 300, 5, "b/c/d"},
        {"/a/b", "/a", 300, -6, ""},
        {"/a/b", "/a/c", 300, -6, ""},
        {"/a", "/ab", 300, -6, ""},
        {"/a", "/a/..", 300, -6, ""},
        {"srv", "/srv", 300, -5, ""},
        {"/srv", "srv", 300, -5, ""},
        {"", "/a", 300, -5, ""},
        {"/a", "", 300, -5, ""},
        {"/a/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "/a", 300, -1, ""},
        {"/a", "/b/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 300, -1, ""},
        {"/a", "/a/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", 300, -1, ""},
        {"/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij", "/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghij/abcdefghijklmnopqrs", 300, -2, ""},
        {"/a/..", "/", 300, 1, "."},
        {"/a/../b", "/b/c", 300, 1, "c"},
        {"/a/b", "/a/b/cc", 0, -4, ""},
        {"/a", "/a", 0, -4, ""},
        {"/", "/xyz", 0, -4, ""},
        {"/a/b", "/a/b/cc", 1, -4, ""},
        {"/a", "/a", 1, -4, ""},
        {"/", "/xyz", 1, -4, ""},
        {"/a/b", "/a/b/cc", 2, -4, ""},
        {"/a", "/a", 2, 1, "."},
        {"/", "/xyz", 2, -4, ""},
        {"/a/b", "/a/b/cc", 3, 2, "cc"},
        {"/a", "/a", 3, 1, "."},
        {"/", "/xyz", 3, -4, ""},
        {"/a/b", "/a/b/cc", 4, 2, "cc"},
        {"/a", "/a", 4, 1, "."},
        {"/", "/xyz", 4, 3, "xyz"},
        {"/a/b", "/a/b/cc", 5, 2, "cc"},
        {"/a", "/a", 5, 1, "."},
        {"/", "/xyz", 5, 3, "xyz"},
    };

    static void test_normalize(void) {
        size_t i;
        char ctx[400];
        for (i = 0; i < sizeof NORMS / sizeof NORMS[0]; i++) {
            const norm_case *c = &NORMS[i];
            size_t n = strlen(c->in);
            char *in = malloc(n ? n : 1);
            char *out = malloc(c->cap ? c->cap : 1);
            int rc;
            memcpy(in, c->in, n);
            snprintf(ctx, sizeof ctx, "normalize(\"%.200s\", flags=%d, cap=%d)", c->in, c->flags, (int)c->cap);
            rc = pf_normalize(in, n, out, c->cap, c->flags);
            CHECK_INT_CTX(ctx, rc, c->rc);
            if (c->rc >= 0 && rc == c->rc) {
                CHECK_INT_CTX(ctx, out[rc], 0);
                CHECK_MEM(out, c->out, (size_t)rc);
            }
            free(in);
            free(out);
        }
    }

    static void test_relative(void) {
        size_t i;
        char ctx[400];
        for (i = 0; i < sizeof RELS / sizeof RELS[0]; i++) {
            const rel_case *c = &RELS[i];
            char *out = malloc(c->cap ? c->cap : 1);
            int rc;
            snprintf(ctx, sizeof ctx, "relative_to(\"%.150s\", \"%.150s\", cap=%d)", c->root, c->path, (int)c->cap);
            rc = pf_relative_to(c->root, c->path, out, c->cap);
            CHECK_INT_CTX(ctx, rc, c->rc);
            if (c->rc >= 0 && rc == c->rc) {
                CHECK_INT_CTX(ctx, out[rc], 0);
                CHECK_MEM(out, c->out, (size_t)rc);
            }
            free(out);
        }
    }

    static void test_length_only(void) {
        /* only the first n bytes of the input are the path */
        char out[16];
        CHECK_INT(pf_normalize("/a/b/../c", 4, out, sizeof out, 0), 4);
        CHECK_STR(out, "/a/b");
        CHECK_INT(pf_normalize("/a/b/../c", 5, out, sizeof out, PF_KEEP_SLASH), 5);
        CHECK_STR(out, "/a/b/");
        CHECK_INT(pf_normalize("/a/b/../c", 7, out, sizeof out, 0), 2);
        CHECK_STR(out, "/a");
        CHECK_INT(pf_normalize("xyz", 0, out, sizeof out, 0), 1);
        CHECK_STR(out, ".");
        CHECK_INT(pf_normalize("/xyz", 1, out, sizeof out, 0), 1);
        CHECK_STR(out, "/");
    }

    int main(void) {
        h_init();
        test_normalize();
        test_relative();
        test_length_only();
        return h_report();
    }
''')

LIB = Lib(
    name="pathfold", lang="c", title="the pathfold path normaliser",
    blurb="The sandboxed file service normalises every client-supplied path with pathfold before it touches the disk.",
    files={"README.md": README1, "include/pathfold.h": F2, "src/pathfold.c": F3},
    visible_tests={"tests/test_main.c": V4, "tests/harness.h": _lang3.C_HARNESS},
    hidden_tests={"tests/test_main.c": H5},
    mutate=["src/pathfold.c"], difficulty=1, tags=["paths", "strings", "security"],
    verify=_lang3.C_VERIFY,
)

_lang3.add(LIB, n=8)
