"""Fixed-capacity open-addressing string map (c): FNV-1a placement, linear probing, tombstones that collapse, deterministic rehash; bugs injected into the library."""
from fx import Lib, dd

from generators.fix import _lang3

README1 = dd(r'''
    # slotmap

    A fixed-capacity hash map from short names to `int32_t` values, used by a gateway's device registry. There is no
    dynamic allocation: the table lives inside the `slotmap` struct.

    ## Layout rules (all of them are part of the contract)

    * The table has `cap` slots (`1..SM_MAX_CAP`, chosen by `sm_init`). A slot is *empty*, *used* or *gone* (a tombstone
      left by a deletion).
    * A key is a non-empty string of at most `SM_KEY_MAX` (15) characters; anything else is `SM_BADKEY`.
    * The home slot of a key is `fnv1a(key) % cap` where `fnv1a` is the 32-bit FNV-1a hash: start with
      `h = 2166136261`; for every byte `b` of the key (as an unsigned byte) do `h ^= b; h *= 16777619` (arithmetic modulo
      2^32).
    * Probing is linear with wrap-around: home slot, home+1, home+2, ... (mod `cap`), at most `cap` slots are looked at.
    * **Lookup** walks the probe sequence; an *empty* slot ends the search (key absent); *used* slots with a different key and
      *gone* slots are skipped.
    * **Insert** (`sm_put`): if the key is already present its value is replaced and the result is `SM_UPDATED`. Otherwise the new
      entry goes into the *first gone slot* met on the probe sequence, or, when there is none, into the empty slot that ended
      the search; the result is `SM_INSERTED`. If every slot is used the result is `SM_FULL` (the map is unchanged).
    * **Delete** (`sm_del`) marks the entry's slot *gone*. Then, **if the slot after it (wrapping around) is empty**, the deleted
      slot becomes *empty* instead, and so does every *gone* slot directly before it (going backwards, wrapping around, until a
      slot that is not gone). Returns 1 when the key existed, else 0.
    * **Rehash** (`sm_rehash`) rebuilds the table: every used entry is re-inserted, scanning the old slots from 0 up, into
      a table with no gone slots, with the insert rule above. Afterwards there are no tombstones.

    ## API (`include/slotmap.h`)

    * `int sm_init(slotmap *m, int cap)`: empty map; -1 when `cap` is outside `1..SM_MAX_CAP` (64), else 0.
    * `int sm_put(slotmap *m, const char *key, int32_t value)`: `SM_INSERTED` (0), `SM_UPDATED` (1), `SM_FULL` (-1) or
      `SM_BADKEY` (-2).
    * `int sm_get(const slotmap *m, const char *key, int32_t *value)`: 1 and `*value` set when present, else 0 (and `*value` is
      left alone; an invalid key is simply absent).
    * `int sm_del(slotmap *m, const char *key)`: see above.
    * `int sm_count(const slotmap *m)`: number of used slots; `int sm_gone(const slotmap *m)`: number of gone slots.
    * `int sm_slot_of(const slotmap *m, const char *key)`: the index of the slot holding `key`, or -1.
    * `int sm_slot_state(const slotmap *m, int i)`: `0` empty, `1` used, `2` gone, `-1` when `i` is outside `0..cap-1`.
    * `int sm_needs_rehash(const slotmap *m)`: 1 when there is at least one gone slot and `(used + gone) * 4 > cap * 3`, else 0.
    * `int sm_next(const slotmap *m, int *cursor, const char **key, int32_t *value)`: iteration in slot order. Start with
      `*cursor = 0`; each call returns the next used slot at or after the cursor (1) and moves the cursor past it, or returns 0
      at the end.
''')

F2 = dd(r'''
    #ifndef SLOTMAP_H
    #define SLOTMAP_H

    #include <stdint.h>

    #define SM_MAX_CAP 64
    #define SM_KEY_MAX 15

    enum { SM_INSERTED = 0, SM_UPDATED = 1, SM_FULL = -1, SM_BADKEY = -2 };

    typedef struct {
        char key[SM_KEY_MAX + 1];
        int32_t value;
        int state; /* 0 empty, 1 used, 2 gone */
    } sm_slot;

    typedef struct {
        sm_slot slots[SM_MAX_CAP];
        int cap;
        int used;
        int gone;
    } slotmap;

    int sm_init(slotmap *m, int cap);
    int sm_put(slotmap *m, const char *key, int32_t value);
    int sm_get(const slotmap *m, const char *key, int32_t *value);
    int sm_del(slotmap *m, const char *key);
    int sm_count(const slotmap *m);
    int sm_gone(const slotmap *m);
    int sm_slot_of(const slotmap *m, const char *key);
    int sm_slot_state(const slotmap *m, int i);
    int sm_needs_rehash(const slotmap *m);
    void sm_rehash(slotmap *m);
    int sm_next(const slotmap *m, int *cursor, const char **key, int32_t *value);

    #endif
''')

F3 = dd(r'''
    #include "slotmap.h"

    #include <string.h>

    enum { EMPTY = 0, USED = 1, GONE = 2 };

    static uint32_t fnv1a(const char *key) {
        uint32_t h = 2166136261u;
        for (; *key; key++) {
            h ^= (uint8_t)*key;
            h *= 16777619u;
        }
        return h;
    }

    static int key_ok(const char *key) {
        size_t n = strlen(key);
        return n >= 1 && n <= SM_KEY_MAX;
    }

    int sm_init(slotmap *m, int cap) {
        if (cap < 1 || cap > SM_MAX_CAP) return -1;
        memset(m, 0, sizeof *m);
        m->cap = cap;
        return 0;
    }

    static int find(const slotmap *m, const char *key) {
        int i, step;
        if (!key_ok(key)) return -1;
        i = (int)(fnv1a(key) % (uint32_t)m->cap);
        for (step = 0; step < m->cap; step++) {
            const sm_slot *s = &m->slots[i];
            if (s->state == EMPTY) return -1;
            if (s->state == USED && strcmp(s->key, key) == 0) return i;
            i = (i + 1) % m->cap;
        }
        return -1;
    }

    int sm_put(slotmap *m, const char *key, int32_t value) {
        int i, step, target = -1;
        sm_slot *s;
        if (!key_ok(key)) return SM_BADKEY;
        i = (int)(fnv1a(key) % (uint32_t)m->cap);
        for (step = 0; step < m->cap; step++) {
            s = &m->slots[i];
            if (s->state == USED && strcmp(s->key, key) == 0) {
                s->value = value;
                return SM_UPDATED;
            }
            if (s->state == GONE && target < 0) target = i;
            if (s->state == EMPTY) {
                if (target < 0) target = i;
                break;
            }
            i = (i + 1) % m->cap;
        }
        if (target < 0) return SM_FULL;
        s = &m->slots[target];
        if (s->state == GONE) m->gone--;
        s->state = USED;
        strcpy(s->key, key);
        s->value = value;
        m->used++;
        return SM_INSERTED;
    }

    int sm_get(const slotmap *m, const char *key, int32_t *value) {
        int i = find(m, key);
        if (i < 0) return 0;
        *value = m->slots[i].value;
        return 1;
    }

    int sm_del(slotmap *m, const char *key) {
        int i = find(m, key), j;
        if (i < 0) return 0;
        m->slots[i].state = GONE;
        m->used--;
        m->gone++;
        if (m->slots[(i + 1) % m->cap].state == EMPTY) {
            for (j = i; m->slots[j].state == GONE; j = (j + m->cap - 1) % m->cap) {
                m->slots[j].state = EMPTY;
                m->gone--;
            }
        }
        return 1;
    }

    int sm_count(const slotmap *m) { return m->used; }

    int sm_gone(const slotmap *m) { return m->gone; }

    int sm_slot_of(const slotmap *m, const char *key) { return find(m, key); }

    int sm_slot_state(const slotmap *m, int i) {
        if (i < 0 || i >= m->cap) return -1;
        return m->slots[i].state;
    }

    int sm_needs_rehash(const slotmap *m) {
        return m->gone > 0 && (m->used + m->gone) * 4 > m->cap * 3;
    }

    void sm_rehash(slotmap *m) {
        sm_slot old[SM_MAX_CAP];
        int i, cap = m->cap;
        memcpy(old, m->slots, sizeof old);
        sm_init(m, cap);
        for (i = 0; i < cap; i++) {
            if (old[i].state == USED) sm_put(m, old[i].key, old[i].value);
        }
    }

    int sm_next(const slotmap *m, int *cursor, const char **key, int32_t *value) {
        while (*cursor < m->cap) {
            const sm_slot *s = &m->slots[(*cursor)++];
            if (s->state == USED) {
                *key = s->key;
                *value = s->value;
                return 1;
            }
        }
        return 0;
    }
''')

V4 = dd(r'''
    #include "harness.h"
    #include "slotmap.h"

    int main(void) {
        slotmap m;
        int32_t v = 0;
        h_init();

        CHECK_INT(sm_init(&m, 8), 0);
        CHECK_INT(sm_put(&m, "gateway", 7), SM_INSERTED);
        CHECK_INT(sm_put(&m, "gateway", 8), SM_UPDATED);
        CHECK_INT(sm_get(&m, "gateway", &v), 1);
        CHECK_INT(v, 8);
        CHECK_INT(sm_del(&m, "gateway"), 1);
        CHECK_INT(sm_get(&m, "gateway", &v), 0);
        return h_report();
    }
''')

H5 = dd(r'''
    #include <stdio.h>
    #include <string.h>

    #include "harness.h"
    #include "slotmap.h"

    /* the layout as text: '.' empty, '#' gone, otherwise the key; slots joined with '|' */
    static const char *layout(const slotmap *m) {
        static char out[SM_MAX_CAP * 17 + 1];
        int i;
        size_t n = 0;
        out[0] = '\0';
        for (i = 0; i < m->cap; i++) {
            int st = sm_slot_state(m, i);
            const char *txt = st == 0 ? "." : st == 2 ? "#" : m->slots[i].key;
            n += (size_t)sprintf(out + n, "%s%s", i ? "|" : "", txt);
        }
        return out;
    }

    typedef struct {
        char op;            /* p put, g get, d delete, r rehash */
        const char *key;
        int val;            /* put: value; get: expected value */
        int ret;            /* expected return value (for 'r' unused) */
        int used, gone;     /* expected counts after the step */
        int need;           /* expected sm_needs_rehash after the step */
        int slot;           /* expected sm_slot_of(key) after the step */
        const char *layout; /* expected layout after the step */
    } step_t;

    static const step_t stepsE[] = {
        {'p', "a1", 1, 0, 1, 0, 0, 7, ".|.|.|.|.|.|.|a1"},
        {'p', "b0", 2, 0, 2, 0, 0, 0, "b0|.|.|.|.|.|.|a1"},
        {'p', "g3", 3, 0, 3, 0, 0, 1, "b0|g3|.|.|.|.|.|a1"},
        {'p', "h2", 4, 0, 4, 0, 0, 2, "b0|g3|h2|.|.|.|.|a1"},
        {'d', "b0", 0, 1, 3, 1, 0, -1, "#|g3|h2|.|.|.|.|a1"},
        {'p', "c2", 33, 0, 4, 0, 0, 0, "c2|g3|h2|.|.|.|.|a1"},
        {'g', "c2", 33, 1, 4, 0, 0, 0, "c2|g3|h2|.|.|.|.|a1"},
        {'g', "g3", 3, 1, 4, 0, 0, 1, "c2|g3|h2|.|.|.|.|a1"},
        {'g', "h2", 4, 1, 4, 0, 0, 2, "c2|g3|h2|.|.|.|.|a1"},
        {'d', "a1", 0, 1, 3, 1, 0, -1, "c2|g3|h2|.|.|.|.|#"},
        {'p', "f1", 44, 0, 4, 1, 0, 3, "c2|g3|h2|f1|.|.|.|#"},
        {'g', "f1", 44, 1, 4, 1, 0, 3, "c2|g3|h2|f1|.|.|.|#"},
        {'d', "c2", 0, 1, 3, 2, 0, -1, "#|g3|h2|f1|.|.|.|#"},
        {'p', "d3", 55, 0, 4, 1, 0, 0, "d3|g3|h2|f1|.|.|.|#"},
        {'d', "g3", 0, 1, 3, 2, 0, -1, "d3|#|h2|f1|.|.|.|#"},
        {'d', "h2", 0, 1, 2, 3, 0, -1, "d3|#|#|f1|.|.|.|#"},
        {'d', "f1", 0, 1, 1, 1, 0, -1, "d3|.|.|.|.|.|.|#"},
        {'d', "d3", 0, 1, 0, 0, 0, -1, ".|.|.|.|.|.|.|."},
    };

    static const step_t stepsF[] = {
        {'p', "dev0", 0, 0, 1, 0, 0, 36, ".|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|dev0|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|."},
        {'p', "dev1", 1, 0, 2, 0, 0, 55, ".|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|dev0|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|dev1|.|.|.|.|.|.|.|."},
        {'p', "dev2", 2, 0, 3, 0, 0, 10, ".|.|.|.|.|.|.|.|.|.|dev2|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|dev0|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|dev1|.|.|.|.|.|.|.|."},
        {'p', "dev3", 3, 0, 4, 0, 0, 29, ".|.|.|.|.|.|.|.|.|.|dev2|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|dev3|.|.|.|.|.|.|dev0|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|dev1|.|.|.|.|.|.|.|."},
        {'p', "dev4", 4, 0, 5, 0, 0, 24, ".|.|.|.|.|.|.|.|.|.|dev2|.|.|.|.|.|.|.|.|.|.|.|.|.|dev4|.|.|.|.|dev3|.|.|.|.|.|.|dev0|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|dev1|.|.|.|.|.|.|.|."},
        {'p', "dev5", 5, 0, 6, 0, 0, 43, ".|.|.|.|.|.|.|.|.|.|dev2|.|.|.|.|.|.|.|.|.|.|.|.|.|dev4|.|.|.|.|dev3|.|.|.|.|.|.|dev0|.|.|.|.|.|.|dev5|.|.|.|.|.|.|.|.|.|.|.|dev1|.|.|.|.|.|.|.|."},
        {'p', "dev6", 6, 0, 7, 0, 0, 62, ".|.|.|.|.|.|.|.|.|.|dev2|.|.|.|.|.|.|.|.|.|.|.|.|.|dev4|.|.|.|.|dev3|.|.|.|.|.|.|dev0|.|.|.|.|.|.|dev5|.|.|.|.|.|.|.|.|.|.|.|dev1|.|.|.|.|.|.|dev6|."},
        {'p', "dev7", 7, 0, 8, 0, 0, 17, ".|.|.|.|.|.|.|.|.|.|dev2|.|.|.|.|.|.|dev7|.|.|.|.|.|.|dev4|.|.|.|.|dev3|.|.|.|.|.|.|dev0|.|.|.|.|.|.|dev5|.|.|.|.|.|.|.|.|.|.|.|dev1|.|.|.|.|.|.|dev6|."},
        {'p', "dev8", 8, 0, 9, 0, 0, 12, ".|.|.|.|.|.|.|.|.|.|dev2|.|dev8|.|.|.|.|dev7|.|.|.|.|.|.|dev4|.|.|.|.|dev3|.|.|.|.|.|.|dev0|.|.|.|.|.|.|dev5|.|.|.|.|.|.|.|.|.|.|.|dev1|.|.|.|.|.|.|dev6|."},
        {'p', "dev9", 9, 0, 10, 0, 0, 31, ".|.|.|.|.|.|.|.|.|.|dev2|.|dev8|.|.|.|.|dev7|.|.|.|.|.|.|dev4|.|.|.|.|dev3|.|dev9|.|.|.|.|dev0|.|.|.|.|.|.|dev5|.|.|.|.|.|.|.|.|.|.|.|dev1|.|.|.|.|.|.|dev6|."},
        {'p', "dev10", 10, 0, 11, 0, 0, 5, ".|.|.|.|.|dev10|.|.|.|.|dev2|.|dev8|.|.|.|.|dev7|.|.|.|.|.|.|dev4|.|.|.|.|dev3|.|dev9|.|.|.|.|dev0|.|.|.|.|.|.|dev5|.|.|.|.|.|.|.|.|.|.|.|dev1|.|.|.|.|.|.|dev6|."},
        {'p', "dev11", 11, 0, 12, 0, 0, 50, ".|.|.|.|.|dev10|.|.|.|.|dev2|.|dev8|.|.|.|.|dev7|.|.|.|.|.|.|dev4|.|.|.|.|dev3|.|dev9|.|.|.|.|dev0|.|.|.|.|.|.|dev5|.|.|.|.|.|.|dev11|.|.|.|.|dev1|.|.|.|.|.|.|dev6|."},
        {'p', "dev12", 12, 0, 13, 0, 0, 32, ".|.|.|.|.|dev10|.|.|.|.|dev2|.|dev8|.|.|.|.|dev7|.|.|.|.|.|.|dev4|.|.|.|.|dev3|.|dev9|dev12|.|.|.|dev0|.|.|.|.|.|.|dev5|.|.|.|.|.|.|dev11|.|.|.|.|dev1|.|.|.|.|.|.|dev6|."},
        {'p', "dev13", 13, 0, 14, 0, 0, 13, ".|.|.|.|.|dev10|.|.|.|.|dev2|.|dev8|dev13|.|.|.|dev7|.|.|.|.|.|.|dev4|.|.|.|.|dev3|.|dev9|dev12|.|.|.|dev0|.|.|.|.|.|.|dev5|.|.|.|.|.|.|dev11|.|.|.|.|dev1|.|.|.|.|.|.|dev6|."},
        {'p', "dev14", 14, 0, 15, 0, 0, 57, ".|.|.|.|.|dev10|.|.|.|.|dev2|.|dev8|dev13|.|.|.|dev7|.|.|.|.|.|.|dev4|.|.|.|.|dev3|.|dev9|dev12|.|.|.|dev0|.|.|.|.|.|.|dev5|.|.|.|.|.|.|dev11|.|.|.|.|dev1|.|dev14|.|.|.|.|dev6|."},
        {'p', "dev15", 15, 0, 16, 0, 0, 38, ".|.|.|.|.|dev10|.|.|.|.|dev2|.|dev8|dev13|.|.|.|dev7|.|.|.|.|.|.|dev4|.|.|.|.|dev3|.|dev9|dev12|.|.|.|dev0|.|dev15|.|.|.|.|dev5|.|.|.|.|.|.|dev11|.|.|.|.|dev1|.|dev14|.|.|.|.|dev6|."},
        {'p', "dev16", 16, 0, 17, 0, 0, 19, ".|.|.|.|.|dev10|.|.|.|.|dev2|.|dev8|dev13|.|.|.|dev7|.|dev16|.|.|.|.|dev4|.|.|.|.|dev3|.|dev9|dev12|.|.|.|dev0|.|dev15|.|.|.|.|dev5|.|.|.|.|.|.|dev11|.|.|.|.|dev1|.|dev14|.|.|.|.|dev6|."},
        {'p', "dev17", 17, 0, 18, 0, 0, 0, "dev17|.|.|.|.|dev10|.|.|.|.|dev2|.|dev8|dev13|.|.|.|dev7|.|dev16|.|.|.|.|dev4|.|.|.|.|dev3|.|dev9|dev12|.|.|.|dev0|.|dev15|.|.|.|.|dev5|.|.|.|.|.|.|dev11|.|.|.|.|dev1|.|dev14|.|.|.|.|dev6|."},
        {'p', "dev18", 18, 0, 19, 0, 0, 30, "dev17|.|.|.|.|dev10|.|.|.|.|dev2|.|dev8|dev13|.|.|.|dev7|.|dev16|.|.|.|.|dev4|.|.|.|.|dev3|dev18|dev9|dev12|.|.|.|dev0|.|dev15|.|.|.|.|dev5|.|.|.|.|.|.|dev11|.|.|.|.|dev1|.|dev14|.|.|.|.|dev6|."},
        {'p', "dev19", 19, 0, 20, 0, 0, 11, "dev17|.|.|.|.|dev10|.|.|.|.|dev2|dev19|dev8|dev13|.|.|.|dev7|.|dev16|.|.|.|.|dev4|.|.|.|.|dev3|dev18|dev9|dev12|.|.|.|dev0|.|dev15|.|.|.|.|dev5|.|.|.|.|.|.|dev11|.|.|.|.|dev1|.|dev14|.|.|.|.|dev6|."},
        {'p', "dev20", 20, 0, 21, 0, 0, 14, "dev17|.|.|.|.|dev10|.|.|.|.|dev2|dev19|dev8|dev13|dev20|.|.|dev7|.|dev16|.|.|.|.|dev4|.|.|.|.|dev3|dev18|dev9|dev12|.|.|.|dev0|.|dev15|.|.|.|.|dev5|.|.|.|.|.|.|dev11|.|.|.|.|dev1|.|dev14|.|.|.|.|dev6|."},
        {'p', "dev21", 21, 0, 22, 0, 0, 33, "dev17|.|.|.|.|dev10|.|.|.|.|dev2|dev19|dev8|dev13|dev20|.|.|dev7|.|dev16|.|.|.|.|dev4|.|.|.|.|dev3|dev18|dev9|dev12|dev21|.|.|dev0|.|dev15|.|.|.|.|dev5|.|.|.|.|.|.|dev11|.|.|.|.|dev1|.|dev14|.|.|.|.|dev6|."},
        {'p', "dev22", 22, 0, 23, 0, 0, 40, "dev17|.|.|.|.|dev10|.|.|.|.|dev2|dev19|dev8|dev13|dev20|.|.|dev7|.|dev16|.|.|.|.|dev4|.|.|.|.|dev3|dev18|dev9|dev12|dev21|.|.|dev0|.|dev15|.|dev22|.|.|dev5|.|.|.|.|.|.|dev11|.|.|.|.|dev1|.|dev14|.|.|.|.|dev6|."},
        {'p', "dev23", 23, 0, 24, 0, 0, 59, "dev17|.|.|.|.|dev10|.|.|.|.|dev2|dev19|dev8|dev13|dev20|.|.|dev7|.|dev16|.|.|.|.|dev4|.|.|.|.|dev3|dev18|dev9|dev12|dev21|.|.|dev0|.|dev15|.|dev22|.|.|dev5|.|.|.|.|.|.|dev11|.|.|.|.|dev1|.|dev14|.|dev23|.|.|dev6|."},
        {'p', "dev24", 24, 0, 25, 0, 0, 26, "dev17|.|.|.|.|dev10|.|.|.|.|dev2|dev19|dev8|dev13|dev20|.|.|dev7|.|dev16|.|.|.|.|dev4|.|dev24|.|.|dev3|dev18|dev9|dev12|dev21|.|.|dev0|.|dev15|.|dev22|.|.|dev5|.|.|.|.|.|.|dev11|.|.|.|.|dev1|.|dev14|.|dev23|.|.|dev6|."},
        {'p', "dev25", 25, 0, 26, 0, 0, 45, "dev17|.|.|.|.|dev10|.|.|.|.|dev2|dev19|dev8|dev13|dev20|.|.|dev7|.|dev16|.|.|.|.|dev4|.|dev24|.|.|dev3|dev18|dev9|dev12|dev21|.|.|dev0|.|dev15|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|.|.|.|.|dev1|.|dev14|.|dev23|.|.|dev6|."},
        {'p', "dev26", 26, 0, 27, 0, 0, 52, "dev17|.|.|.|.|dev10|.|.|.|.|dev2|dev19|dev8|dev13|dev20|.|.|dev7|.|dev16|.|.|.|.|dev4|.|dev24|.|.|dev3|dev18|dev9|dev12|dev21|.|.|dev0|.|dev15|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|.|dev26|.|.|dev1|.|dev14|.|dev23|.|.|dev6|."},
        {'p', "dev27", 27, 0, 28, 0, 0, 7, "dev17|.|.|.|.|dev10|.|dev27|.|.|dev2|dev19|dev8|dev13|dev20|.|.|dev7|.|dev16|.|.|.|.|dev4|.|dev24|.|.|dev3|dev18|dev9|dev12|dev21|.|.|dev0|.|dev15|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|.|dev26|.|.|dev1|.|dev14|.|dev23|.|.|dev6|."},
        {'p', "dev28", 28, 0, 29, 0, 0, 54, "dev17|.|.|.|.|dev10|.|dev27|.|.|dev2|dev19|dev8|dev13|dev20|.|.|dev7|.|dev16|.|.|.|.|dev4|.|dev24|.|.|dev3|dev18|dev9|dev12|dev21|.|.|dev0|.|dev15|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|.|dev26|.|dev28|dev1|.|dev14|.|dev23|.|.|dev6|."},
        {'p', "dev29", 29, 0, 30, 0, 0, 9, "dev17|.|.|.|.|dev10|.|dev27|.|dev29|dev2|dev19|dev8|dev13|dev20|.|.|dev7|.|dev16|.|.|.|.|dev4|.|dev24|.|.|dev3|dev18|dev9|dev12|dev21|.|.|dev0|.|dev15|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|.|dev26|.|dev28|dev1|.|dev14|.|dev23|.|.|dev6|."},
        {'d', "dev0", 0, 1, 29, 0, 0, -1, "dev17|.|.|.|.|dev10|.|dev27|.|dev29|dev2|dev19|dev8|dev13|dev20|.|.|dev7|.|dev16|.|.|.|.|dev4|.|dev24|.|.|dev3|dev18|dev9|dev12|dev21|.|.|.|.|dev15|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|.|dev26|.|dev28|dev1|.|dev14|.|dev23|.|.|dev6|."},
        {'d', "dev3", 0, 1, 28, 1, 0, -1, "dev17|.|.|.|.|dev10|.|dev27|.|dev29|dev2|dev19|dev8|dev13|dev20|.|.|dev7|.|dev16|.|.|.|.|dev4|.|dev24|.|.|#|dev18|dev9|dev12|dev21|.|.|.|.|dev15|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|.|dev26|.|dev28|dev1|.|dev14|.|dev23|.|.|dev6|."},
        {'d', "dev6", 0, 1, 27, 1, 0, -1, "dev17|.|.|.|.|dev10|.|dev27|.|dev29|dev2|dev19|dev8|dev13|dev20|.|.|dev7|.|dev16|.|.|.|.|dev4|.|dev24|.|.|#|dev18|dev9|dev12|dev21|.|.|.|.|dev15|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|.|dev26|.|dev28|dev1|.|dev14|.|dev23|.|.|.|."},
        {'d', "dev9", 0, 1, 26, 2, 0, -1, "dev17|.|.|.|.|dev10|.|dev27|.|dev29|dev2|dev19|dev8|dev13|dev20|.|.|dev7|.|dev16|.|.|.|.|dev4|.|dev24|.|.|#|dev18|#|dev12|dev21|.|.|.|.|dev15|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|.|dev26|.|dev28|dev1|.|dev14|.|dev23|.|.|.|."},
        {'d', "dev12", 0, 1, 25, 3, 0, -1, "dev17|.|.|.|.|dev10|.|dev27|.|dev29|dev2|dev19|dev8|dev13|dev20|.|.|dev7|.|dev16|.|.|.|.|dev4|.|dev24|.|.|#|dev18|#|#|dev21|.|.|.|.|dev15|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|.|dev26|.|dev28|dev1|.|dev14|.|dev23|.|.|.|."},
        {'d', "dev15", 0, 1, 24, 3, 0, -1, "dev17|.|.|.|.|dev10|.|dev27|.|dev29|dev2|dev19|dev8|dev13|dev20|.|.|dev7|.|dev16|.|.|.|.|dev4|.|dev24|.|.|#|dev18|#|#|dev21|.|.|.|.|.|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|.|dev26|.|dev28|dev1|.|dev14|.|dev23|.|.|.|."},
        {'d', "dev18", 0, 1, 23, 4, 0, -1, "dev17|.|.|.|.|dev10|.|dev27|.|dev29|dev2|dev19|dev8|dev13|dev20|.|.|dev7|.|dev16|.|.|.|.|dev4|.|dev24|.|.|#|#|#|#|dev21|.|.|.|.|.|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|.|dev26|.|dev28|dev1|.|dev14|.|dev23|.|.|.|."},
        {'d', "dev21", 0, 1, 22, 0, 0, -1, "dev17|.|.|.|.|dev10|.|dev27|.|dev29|dev2|dev19|dev8|dev13|dev20|.|.|dev7|.|dev16|.|.|.|.|dev4|.|dev24|.|.|.|.|.|.|.|.|.|.|.|.|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|.|dev26|.|dev28|dev1|.|dev14|.|dev23|.|.|.|."},
        {'d', "dev24", 0, 1, 21, 0, 0, -1, "dev17|.|.|.|.|dev10|.|dev27|.|dev29|dev2|dev19|dev8|dev13|dev20|.|.|dev7|.|dev16|.|.|.|.|dev4|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|.|dev26|.|dev28|dev1|.|dev14|.|dev23|.|.|.|."},
        {'d', "dev27", 0, 1, 20, 0, 0, -1, "dev17|.|.|.|.|dev10|.|.|.|dev29|dev2|dev19|dev8|dev13|dev20|.|.|dev7|.|dev16|.|.|.|.|dev4|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|.|dev26|.|dev28|dev1|.|dev14|.|dev23|.|.|.|."},
        {'r', "x", 0, 0, 20, 0, 0, -1, "dev17|.|.|.|.|dev10|.|.|.|dev29|dev2|dev19|dev8|dev13|dev20|.|.|dev7|.|dev16|.|.|.|.|dev4|.|.|.|.|.|.|.|.|.|.|.|.|.|.|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|.|dev26|.|dev28|dev1|.|dev14|.|dev23|.|.|.|."},
        {'p', "zz0", 100, 0, 21, 0, 0, 31, "dev17|.|.|.|.|dev10|.|.|.|dev29|dev2|dev19|dev8|dev13|dev20|.|.|dev7|.|dev16|.|.|.|.|dev4|.|.|.|.|.|.|zz0|.|.|.|.|.|.|.|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|.|dev26|.|dev28|dev1|.|dev14|.|dev23|.|.|.|."},
        {'p', "zz1", 101, 0, 22, 0, 0, 15, "dev17|.|.|.|.|dev10|.|.|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|.|dev7|.|dev16|.|.|.|.|dev4|.|.|.|.|.|.|zz0|.|.|.|.|.|.|.|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|.|dev26|.|dev28|dev1|.|dev14|.|dev23|.|.|.|."},
        {'p', "zz2", 102, 0, 23, 0, 0, 6, "dev17|.|.|.|.|dev10|zz2|.|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|.|dev7|.|dev16|.|.|.|.|dev4|.|.|.|.|.|.|zz0|.|.|.|.|.|.|.|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|.|dev26|.|dev28|dev1|.|dev14|.|dev23|.|.|.|."},
        {'p', "zz3", 103, 0, 24, 0, 0, 51, "dev17|.|.|.|.|dev10|zz2|.|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|.|dev7|.|dev16|.|.|.|.|dev4|.|.|.|.|.|.|zz0|.|.|.|.|.|.|.|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|zz3|dev26|.|dev28|dev1|.|dev14|.|dev23|.|.|.|."},
        {'p', "zz4", 104, 0, 25, 0, 0, 20, "dev17|.|.|.|.|dev10|zz2|.|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|.|dev7|.|dev16|zz4|.|.|.|dev4|.|.|.|.|.|.|zz0|.|.|.|.|.|.|.|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|zz3|dev26|.|dev28|dev1|.|dev14|.|dev23|.|.|.|."},
        {'p', "zz5", 105, 0, 26, 0, 0, 1, "dev17|zz5|.|.|.|dev10|zz2|.|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|.|dev7|.|dev16|zz4|.|.|.|dev4|.|.|.|.|.|.|zz0|.|.|.|.|.|.|.|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|zz3|dev26|.|dev28|dev1|.|dev14|.|dev23|.|.|.|."},
        {'p', "zz6", 106, 0, 27, 0, 0, 58, "dev17|zz5|.|.|.|dev10|zz2|.|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|.|dev7|.|dev16|zz4|.|.|.|dev4|.|.|.|.|.|.|zz0|.|.|.|.|.|.|.|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|zz3|dev26|.|dev28|dev1|.|dev14|zz6|dev23|.|.|.|."},
        {'p', "zz7", 107, 0, 28, 0, 0, 38, "dev17|zz5|.|.|.|dev10|zz2|.|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|.|dev7|.|dev16|zz4|.|.|.|dev4|.|.|.|.|.|.|zz0|.|.|.|.|.|.|zz7|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|zz3|dev26|.|dev28|dev1|.|dev14|zz6|dev23|.|.|.|."},
        {'p', "zz8", 108, 0, 29, 0, 0, 56, "dev17|zz5|.|.|.|dev10|zz2|.|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|.|dev7|.|dev16|zz4|.|.|.|dev4|.|.|.|.|.|.|zz0|.|.|.|.|.|.|zz7|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|zz3|dev26|.|dev28|dev1|zz8|dev14|zz6|dev23|.|.|.|."},
        {'p', "zz9", 109, 0, 30, 0, 0, 36, "dev17|zz5|.|.|.|dev10|zz2|.|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|.|dev7|.|dev16|zz4|.|.|.|dev4|.|.|.|.|.|.|zz0|.|.|.|.|zz9|.|zz7|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|zz3|dev26|.|dev28|dev1|zz8|dev14|zz6|dev23|.|.|.|."},
        {'p', "zz10", 110, 0, 31, 0, 0, 53, "dev17|zz5|.|.|.|dev10|zz2|.|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|.|dev7|.|dev16|zz4|.|.|.|dev4|.|.|.|.|.|.|zz0|.|.|.|.|zz9|.|zz7|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|zz3|dev26|zz10|dev28|dev1|zz8|dev14|zz6|dev23|.|.|.|."},
        {'p', "zz11", 111, 0, 32, 0, 0, 7, "dev17|zz5|.|.|.|dev10|zz2|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|.|dev7|.|dev16|zz4|.|.|.|dev4|.|.|.|.|.|.|zz0|.|.|.|.|zz9|.|zz7|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|zz3|dev26|zz10|dev28|dev1|zz8|dev14|zz6|dev23|.|.|.|."},
        {'p', "zz12", 112, 0, 33, 0, 0, 26, "dev17|zz5|.|.|.|dev10|zz2|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|.|dev7|.|dev16|zz4|.|.|.|dev4|.|zz12|.|.|.|.|zz0|.|.|.|.|zz9|.|zz7|.|dev22|.|.|dev5|.|dev25|.|.|.|.|dev11|zz3|dev26|zz10|dev28|dev1|zz8|dev14|zz6|dev23|.|.|.|."},
        {'p', "zz13", 113, 0, 34, 0, 0, 46, "dev17|zz5|.|.|.|dev10|zz2|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|.|dev7|.|dev16|zz4|.|.|.|dev4|.|zz12|.|.|.|.|zz0|.|.|.|.|zz9|.|zz7|.|dev22|.|.|dev5|.|dev25|zz13|.|.|.|dev11|zz3|dev26|zz10|dev28|dev1|zz8|dev14|zz6|dev23|.|.|.|."},
        {'p', "zz14", 114, 0, 35, 0, 0, 41, "dev17|zz5|.|.|.|dev10|zz2|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|.|dev7|.|dev16|zz4|.|.|.|dev4|.|zz12|.|.|.|.|zz0|.|.|.|.|zz9|.|zz7|.|dev22|zz14|.|dev5|.|dev25|zz13|.|.|.|dev11|zz3|dev26|zz10|dev28|dev1|zz8|dev14|zz6|dev23|.|.|.|."},
        {'p', "zz15", 115, 0, 36, 0, 0, 60, "dev17|zz5|.|.|.|dev10|zz2|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|.|dev7|.|dev16|zz4|.|.|.|dev4|.|zz12|.|.|.|.|zz0|.|.|.|.|zz9|.|zz7|.|dev22|zz14|.|dev5|.|dev25|zz13|.|.|.|dev11|zz3|dev26|zz10|dev28|dev1|zz8|dev14|zz6|dev23|zz15|.|.|."},
        {'p', "zz16", 116, 0, 37, 0, 0, 16, "dev17|zz5|.|.|.|dev10|zz2|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|zz16|dev7|.|dev16|zz4|.|.|.|dev4|.|zz12|.|.|.|.|zz0|.|.|.|.|zz9|.|zz7|.|dev22|zz14|.|dev5|.|dev25|zz13|.|.|.|dev11|zz3|dev26|zz10|dev28|dev1|zz8|dev14|zz6|dev23|zz15|.|.|."},
        {'p', "zz17", 117, 0, 38, 0, 0, 33, "dev17|zz5|.|.|.|dev10|zz2|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|zz16|dev7|.|dev16|zz4|.|.|.|dev4|.|zz12|.|.|.|.|zz0|.|zz17|.|.|zz9|.|zz7|.|dev22|zz14|.|dev5|.|dev25|zz13|.|.|.|dev11|zz3|dev26|zz10|dev28|dev1|zz8|dev14|zz6|dev23|zz15|.|.|."},
        {'p', "zz18", 118, 0, 39, 0, 0, 28, "dev17|zz5|.|.|.|dev10|zz2|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|zz16|dev7|.|dev16|zz4|.|.|.|dev4|.|zz12|.|zz18|.|.|zz0|.|zz17|.|.|zz9|.|zz7|.|dev22|zz14|.|dev5|.|dev25|zz13|.|.|.|dev11|zz3|dev26|zz10|dev28|dev1|zz8|dev14|zz6|dev23|zz15|.|.|."},
        {'p', "zz19", 119, 0, 40, 0, 0, 47, "dev17|zz5|.|.|.|dev10|zz2|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|zz16|dev7|.|dev16|zz4|.|.|.|dev4|.|zz12|.|zz18|.|.|zz0|.|zz17|.|.|zz9|.|zz7|.|dev22|zz14|.|dev5|.|dev25|zz13|zz19|.|.|dev11|zz3|dev26|zz10|dev28|dev1|zz8|dev14|zz6|dev23|zz15|.|.|."},
        {'d', "zz0", 0, 1, 39, 0, 0, -1, "dev17|zz5|.|.|.|dev10|zz2|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|zz16|dev7|.|dev16|zz4|.|.|.|dev4|.|zz12|.|zz18|.|.|.|.|zz17|.|.|zz9|.|zz7|.|dev22|zz14|.|dev5|.|dev25|zz13|zz19|.|.|dev11|zz3|dev26|zz10|dev28|dev1|zz8|dev14|zz6|dev23|zz15|.|.|."},
        {'d', "zz2", 0, 1, 38, 1, 0, -1, "dev17|zz5|.|.|.|dev10|#|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|zz16|dev7|.|dev16|zz4|.|.|.|dev4|.|zz12|.|zz18|.|.|.|.|zz17|.|.|zz9|.|zz7|.|dev22|zz14|.|dev5|.|dev25|zz13|zz19|.|.|dev11|zz3|dev26|zz10|dev28|dev1|zz8|dev14|zz6|dev23|zz15|.|.|."},
        {'d', "zz4", 0, 1, 37, 1, 0, -1, "dev17|zz5|.|.|.|dev10|#|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|zz16|dev7|.|dev16|.|.|.|.|dev4|.|zz12|.|zz18|.|.|.|.|zz17|.|.|zz9|.|zz7|.|dev22|zz14|.|dev5|.|dev25|zz13|zz19|.|.|dev11|zz3|dev26|zz10|dev28|dev1|zz8|dev14|zz6|dev23|zz15|.|.|."},
        {'d', "zz6", 0, 1, 36, 2, 0, -1, "dev17|zz5|.|.|.|dev10|#|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|zz16|dev7|.|dev16|.|.|.|.|dev4|.|zz12|.|zz18|.|.|.|.|zz17|.|.|zz9|.|zz7|.|dev22|zz14|.|dev5|.|dev25|zz13|zz19|.|.|dev11|zz3|dev26|zz10|dev28|dev1|zz8|dev14|#|dev23|zz15|.|.|."},
        {'d', "zz8", 0, 1, 35, 3, 0, -1, "dev17|zz5|.|.|.|dev10|#|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|zz16|dev7|.|dev16|.|.|.|.|dev4|.|zz12|.|zz18|.|.|.|.|zz17|.|.|zz9|.|zz7|.|dev22|zz14|.|dev5|.|dev25|zz13|zz19|.|.|dev11|zz3|dev26|zz10|dev28|dev1|#|dev14|#|dev23|zz15|.|.|."},
        {'d', "zz10", 0, 1, 34, 4, 0, -1, "dev17|zz5|.|.|.|dev10|#|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|zz16|dev7|.|dev16|.|.|.|.|dev4|.|zz12|.|zz18|.|.|.|.|zz17|.|.|zz9|.|zz7|.|dev22|zz14|.|dev5|.|dev25|zz13|zz19|.|.|dev11|zz3|dev26|#|dev28|dev1|#|dev14|#|dev23|zz15|.|.|."},
        {'d', "zz12", 0, 1, 33, 4, 0, -1, "dev17|zz5|.|.|.|dev10|#|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|zz16|dev7|.|dev16|.|.|.|.|dev4|.|.|.|zz18|.|.|.|.|zz17|.|.|zz9|.|zz7|.|dev22|zz14|.|dev5|.|dev25|zz13|zz19|.|.|dev11|zz3|dev26|#|dev28|dev1|#|dev14|#|dev23|zz15|.|.|."},
        {'d', "zz14", 0, 1, 32, 4, 0, -1, "dev17|zz5|.|.|.|dev10|#|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|zz16|dev7|.|dev16|.|.|.|.|dev4|.|.|.|zz18|.|.|.|.|zz17|.|.|zz9|.|zz7|.|dev22|.|.|dev5|.|dev25|zz13|zz19|.|.|dev11|zz3|dev26|#|dev28|dev1|#|dev14|#|dev23|zz15|.|.|."},
        {'d', "zz16", 0, 1, 31, 5, 0, -1, "dev17|zz5|.|.|.|dev10|#|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|#|dev7|.|dev16|.|.|.|.|dev4|.|.|.|zz18|.|.|.|.|zz17|.|.|zz9|.|zz7|.|dev22|.|.|dev5|.|dev25|zz13|zz19|.|.|dev11|zz3|dev26|#|dev28|dev1|#|dev14|#|dev23|zz15|.|.|."},
        {'d', "zz18", 0, 1, 30, 5, 0, -1, "dev17|zz5|.|.|.|dev10|#|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|#|dev7|.|dev16|.|.|.|.|dev4|.|.|.|.|.|.|.|.|zz17|.|.|zz9|.|zz7|.|dev22|.|.|dev5|.|dev25|zz13|zz19|.|.|dev11|zz3|dev26|#|dev28|dev1|#|dev14|#|dev23|zz15|.|.|."},
        {'r', "x", 0, 0, 30, 0, 0, -1, "dev17|zz5|.|.|.|dev10|.|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|.|dev7|.|dev16|.|.|.|.|dev4|.|.|.|.|.|.|.|.|zz17|.|.|zz9|.|zz7|.|dev22|.|.|dev5|.|dev25|zz13|zz19|.|.|dev11|zz3|dev26|.|dev28|dev1|.|dev14|.|dev23|zz15|.|.|."},
        {'g', "dev1", 1, 1, 30, 0, 0, 55, "dev17|zz5|.|.|.|dev10|.|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|.|dev7|.|dev16|.|.|.|.|dev4|.|.|.|.|.|.|.|.|zz17|.|.|zz9|.|zz7|.|dev22|.|.|dev5|.|dev25|zz13|zz19|.|.|dev11|zz3|dev26|.|dev28|dev1|.|dev14|.|dev23|zz15|.|.|."},
        {'g', "dev2", 2, 1, 30, 0, 0, 10, "dev17|zz5|.|.|.|dev10|.|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|.|dev7|.|dev16|.|.|.|.|dev4|.|.|.|.|.|.|.|.|zz17|.|.|zz9|.|zz7|.|dev22|.|.|dev5|.|dev25|zz13|zz19|.|.|dev11|zz3|dev26|.|dev28|dev1|.|dev14|.|dev23|zz15|.|.|."},
        {'g', "zz1", 101, 1, 30, 0, 0, 15, "dev17|zz5|.|.|.|dev10|.|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|.|dev7|.|dev16|.|.|.|.|dev4|.|.|.|.|.|.|.|.|zz17|.|.|zz9|.|zz7|.|dev22|.|.|dev5|.|dev25|zz13|zz19|.|.|dev11|zz3|dev26|.|dev28|dev1|.|dev14|.|dev23|zz15|.|.|."},
        {'g', "zz4", 0, 0, 30, 0, 0, -1, "dev17|zz5|.|.|.|dev10|.|zz11|.|dev29|dev2|dev19|dev8|dev13|dev20|zz1|.|dev7|.|dev16|.|.|.|.|dev4|.|.|.|.|.|.|.|.|zz17|.|.|zz9|.|zz7|.|dev22|.|.|dev5|.|dev25|zz13|zz19|.|.|dev11|zz3|dev26|.|dev28|dev1|.|dev14|.|dev23|zz15|.|.|."},
    };

    static const step_t stepsA[] = {
        {'p', "c3", 1, 0, 1, 0, 0, 3, ".|.|.|c3|.|.|.|."},
        {'p', "d2", 2, 0, 2, 0, 0, 4, ".|.|.|c3|d2|.|.|."},
        {'p', "e1", 3, 0, 3, 0, 0, 5, ".|.|.|c3|d2|e1|.|."},
        {'p', "f0", 4, 0, 4, 0, 0, 6, ".|.|.|c3|d2|e1|f0|."},
        {'g', "e1", 3, 1, 4, 0, 0, 5, ".|.|.|c3|d2|e1|f0|."},
        {'d', "d2", 0, 1, 3, 1, 0, -1, ".|.|.|c3|#|e1|f0|."},
        {'g', "e1", 3, 1, 3, 1, 0, 5, ".|.|.|c3|#|e1|f0|."},
        {'g', "d2", 0, 0, 3, 1, 0, -1, ".|.|.|c3|#|e1|f0|."},
        {'p', "f0", 99, 1, 3, 1, 0, 6, ".|.|.|c3|#|e1|f0|."},
        {'p', "b0", 7, 0, 4, 1, 0, 7, ".|.|.|c3|#|e1|f0|b0"},
        {'d', "c3", 0, 1, 3, 2, 0, -1, ".|.|.|#|#|e1|f0|b0"},
        {'g', "e1", 3, 1, 3, 2, 0, 5, ".|.|.|#|#|e1|f0|b0"},
        {'p', "a0", 5, 0, 4, 1, 0, 4, ".|.|.|#|a0|e1|f0|b0"},
        {'p', "d2", 6, 0, 5, 0, 0, 3, ".|.|.|d2|a0|e1|f0|b0"},
        {'d', "e1", 0, 1, 4, 1, 0, -1, ".|.|.|d2|a0|#|f0|b0"},
        {'d', "f0", 0, 1, 3, 2, 0, -1, ".|.|.|d2|a0|#|#|b0"},
        {'d', "d2", 0, 1, 2, 3, 0, -1, ".|.|.|#|a0|#|#|b0"},
        {'d', "b0", 0, 1, 1, 1, 0, -1, ".|.|.|#|a0|.|.|."},
        {'d', "a0", 0, 1, 0, 0, 0, -1, ".|.|.|.|.|.|.|."},
    };

    static const step_t stepsB[] = {
        {'p', "a1", 10, 0, 1, 0, 0, 7, ".|.|.|.|.|.|.|a1"},
        {'p', "b0", 11, 0, 2, 0, 0, 0, "b0|.|.|.|.|.|.|a1"},
        {'p', "g3", 12, 0, 3, 0, 0, 1, "b0|g3|.|.|.|.|.|a1"},
        {'p', "h2", 13, 0, 4, 0, 0, 2, "b0|g3|h2|.|.|.|.|a1"},
        {'p', "b2", 77, 0, 5, 0, 0, 5, "b0|g3|h2|.|.|b2|.|a1"},
        {'d', "b0", 0, 1, 4, 1, 0, -1, "#|g3|h2|.|.|b2|.|a1"},
        {'g', "g3", 12, 1, 4, 1, 0, 1, "#|g3|h2|.|.|b2|.|a1"},
        {'g', "h2", 13, 1, 4, 1, 0, 2, "#|g3|h2|.|.|b2|.|a1"},
        {'d', "g3", 0, 1, 3, 2, 0, -1, "#|#|h2|.|.|b2|.|a1"},
        {'d', "h2", 0, 1, 2, 0, 0, -1, ".|.|.|.|.|b2|.|a1"},
        {'d', "a1", 0, 1, 1, 0, 0, -1, ".|.|.|.|.|b2|.|."},
        {'p', "h2", 1, 0, 2, 0, 0, 7, ".|.|.|.|.|b2|.|h2"},
        {'p', "a1", 2, 0, 3, 0, 0, 0, "a1|.|.|.|.|b2|.|h2"},
    };

    static const step_t stepsC[] = {
        {'p', "a", 1, 0, 1, 0, 0, 0, "a|.|.|."},
        {'p', "b", 2, 0, 2, 0, 0, 1, "a|b|.|."},
        {'p', "c", 3, 0, 3, 0, 0, 2, "a|b|c|."},
        {'p', "d", 4, 0, 4, 0, 0, 3, "a|b|c|d"},
        {'p', "e", 5, -1, 4, 0, 0, -1, "a|b|c|d"},
        {'g', "e", 0, 0, 4, 0, 0, -1, "a|b|c|d"},
        {'p', "b", 20, 1, 4, 0, 0, 1, "a|b|c|d"},
        {'d', "c", 0, 1, 3, 1, 1, -1, "a|b|#|d"},
        {'g', "d", 4, 1, 3, 1, 1, 3, "a|b|#|d"},
        {'p', "e", 50, 0, 4, 0, 0, 2, "a|b|e|d"},
        {'p', "f", 6, -1, 4, 0, 0, -1, "a|b|e|d"},
        {'d', "b", 0, 1, 3, 1, 1, -1, "a|#|e|d"},
        {'d', "a", 0, 1, 2, 2, 1, -1, "#|#|e|d"},
        {'d', "d", 0, 1, 1, 3, 1, -1, "#|#|e|#"},
        {'d', "e", 0, 1, 0, 4, 1, -1, "#|#|#|#"},
        {'p', "z", 1, 0, 1, 3, 1, 1, "#|z|#|#"},
    };

    static const step_t stepsD[] = {
        {'p', "c3", 0, 0, 1, 0, 0, 3, ".|.|.|c3|.|.|.|."},
        {'p', "d2", 1, 0, 2, 0, 0, 4, ".|.|.|c3|d2|.|.|."},
        {'p', "e1", 2, 0, 3, 0, 0, 5, ".|.|.|c3|d2|e1|.|."},
        {'p', "f0", 3, 0, 4, 0, 0, 6, ".|.|.|c3|d2|e1|f0|."},
        {'p', "c2", 4, 0, 5, 0, 0, 0, "c2|.|.|c3|d2|e1|f0|."},
        {'p', "d3", 5, 0, 6, 0, 0, 1, "c2|d3|.|c3|d2|e1|f0|."},
        {'d', "c3", 0, 1, 5, 1, 0, -1, "c2|d3|.|#|d2|e1|f0|."},
        {'d', "e1", 0, 1, 4, 2, 0, -1, "c2|d3|.|#|d2|#|f0|."},
        {'r', "x", 0, 0, 4, 0, 0, -1, "c2|d3|.|d2|f0|.|.|."},
        {'d', "d2", 0, 1, 3, 1, 0, -1, "c2|d3|.|#|f0|.|.|."},
        {'r', "x", 0, 0, 3, 0, 0, -1, "c2|d3|.|f0|.|.|.|."},
        {'p', "c1", 3, 0, 4, 0, 0, 2, "c2|d3|c1|f0|.|.|.|."},
        {'p', "d0", 4, 0, 5, 0, 0, 4, "c2|d3|c1|f0|d0|.|.|."},
        {'p', "c3", 3, 0, 6, 0, 0, 5, "c2|d3|c1|f0|d0|c3|.|."},
        {'d', "c2", 0, 1, 5, 1, 0, -1, "#|d3|c1|f0|d0|c3|.|."},
        {'d', "d3", 0, 1, 4, 2, 0, -1, "#|#|c1|f0|d0|c3|.|."},
        {'d', "f0", 0, 1, 3, 3, 0, -1, "#|#|c1|#|d0|c3|.|."},
    };

    static const step_t steps8[] = {
        {'d', "k2", 0, 0, 0, 0, 0, -1, ".|.|.|.|.|.|.|."},
        {'d', "k12", 0, 0, 0, 0, 0, -1, ".|.|.|.|.|.|.|."},
        {'p', "k4", 410, 0, 1, 0, 0, 2, ".|.|k4|.|.|.|.|."},
        {'d', "k7", 0, 0, 1, 0, 0, -1, ".|.|k4|.|.|.|.|."},
        {'p', "k12", 449, 0, 2, 0, 0, 1, ".|k12|k4|.|.|.|.|."},
        {'g', "k0", 0, 0, 2, 0, 0, -1, ".|k12|k4|.|.|.|.|."},
        {'p', "k6", -48, 0, 3, 0, 0, 4, ".|k12|k4|.|k6|.|.|."},
        {'p', "k11", 184, 0, 4, 0, 0, 0, "k11|k12|k4|.|k6|.|.|."},
        {'g', "k9", 0, 0, 4, 0, 0, -1, "k11|k12|k4|.|k6|.|.|."},
        {'p', "k5", -24, 0, 5, 0, 0, 5, "k11|k12|k4|.|k6|k5|.|."},
        {'d', "k10", 0, 0, 5, 0, 0, -1, "k11|k12|k4|.|k6|k5|.|."},
        {'d', "k6", 0, 1, 4, 1, 0, -1, "k11|k12|k4|.|#|k5|.|."},
        {'d', "k6", 0, 0, 4, 1, 0, -1, "k11|k12|k4|.|#|k5|.|."},
        {'p', "k8", 398, 0, 5, 1, 0, 6, "k11|k12|k4|.|#|k5|k8|."},
        {'d', "k7", 0, 0, 5, 1, 0, -1, "k11|k12|k4|.|#|k5|k8|."},
        {'p', "k5", 174, 1, 5, 1, 0, 5, "k11|k12|k4|.|#|k5|k8|."},
        {'p', "k12", 246, 1, 5, 1, 0, 1, "k11|k12|k4|.|#|k5|k8|."},
        {'p', "k0", 52, 0, 6, 1, 1, 7, "k11|k12|k4|.|#|k5|k8|k0"},
        {'d', "k2", 0, 0, 6, 1, 1, -1, "k11|k12|k4|.|#|k5|k8|k0"},
        {'g', "k11", 184, 1, 6, 1, 1, 0, "k11|k12|k4|.|#|k5|k8|k0"},
        {'d', "k1", 0, 0, 6, 1, 1, -1, "k11|k12|k4|.|#|k5|k8|k0"},
        {'g', "k11", 184, 1, 6, 1, 1, 0, "k11|k12|k4|.|#|k5|k8|k0"},
        {'g', "k8", 398, 1, 6, 1, 1, 6, "k11|k12|k4|.|#|k5|k8|k0"},
        {'d', "k6", 0, 0, 6, 1, 1, -1, "k11|k12|k4|.|#|k5|k8|k0"},
        {'p', "k10", 240, 0, 7, 1, 1, 3, "k11|k12|k4|k10|#|k5|k8|k0"},
        {'g', "k9", 0, 0, 7, 1, 1, -1, "k11|k12|k4|k10|#|k5|k8|k0"},
        {'g', "k7", 0, 0, 7, 1, 1, -1, "k11|k12|k4|k10|#|k5|k8|k0"},
        {'p', "k8", -15, 1, 7, 1, 1, 6, "k11|k12|k4|k10|#|k5|k8|k0"},
        {'p', "k7", 363, 0, 8, 0, 0, 4, "k11|k12|k4|k10|k7|k5|k8|k0"},
        {'d', "k6", 0, 0, 8, 0, 0, -1, "k11|k12|k4|k10|k7|k5|k8|k0"},
        {'d', "k5", 0, 1, 7, 1, 1, -1, "k11|k12|k4|k10|k7|#|k8|k0"},
        {'d', "k11", 0, 1, 6, 2, 1, -1, "#|k12|k4|k10|k7|#|k8|k0"},
        {'p', "k11", 399, 0, 7, 1, 1, 0, "k11|k12|k4|k10|k7|#|k8|k0"},
        {'d', "k10", 0, 1, 6, 2, 1, -1, "k11|k12|k4|#|k7|#|k8|k0"},
        {'p', "k12", 352, 1, 6, 2, 1, 1, "k11|k12|k4|#|k7|#|k8|k0"},
        {'p', "k5", -20, 0, 7, 1, 1, 5, "k11|k12|k4|#|k7|k5|k8|k0"},
        {'p', "k7", 353, 1, 7, 1, 1, 4, "k11|k12|k4|#|k7|k5|k8|k0"},
        {'p', "k10", 464, 0, 8, 0, 0, 3, "k11|k12|k4|k10|k7|k5|k8|k0"},
        {'g', "k3", 0, 0, 8, 0, 0, -1, "k11|k12|k4|k10|k7|k5|k8|k0"},
        {'p', "k12", 187, 1, 8, 0, 0, 1, "k11|k12|k4|k10|k7|k5|k8|k0"},
        {'d', "k6", 0, 0, 8, 0, 0, -1, "k11|k12|k4|k10|k7|k5|k8|k0"},
        {'p', "k9", 225, -1, 8, 0, 0, -1, "k11|k12|k4|k10|k7|k5|k8|k0"},
        {'d', "k10", 0, 1, 7, 1, 1, -1, "k11|k12|k4|#|k7|k5|k8|k0"},
        {'p', "k11", 474, 1, 7, 1, 1, 0, "k11|k12|k4|#|k7|k5|k8|k0"},
        {'p', "k12", 160, 1, 7, 1, 1, 1, "k11|k12|k4|#|k7|k5|k8|k0"},
        {'g', "k6", 0, 0, 7, 1, 1, -1, "k11|k12|k4|#|k7|k5|k8|k0"},
        {'g', "k7", 353, 1, 7, 1, 1, 4, "k11|k12|k4|#|k7|k5|k8|k0"},
        {'d', "k9", 0, 0, 7, 1, 1, -1, "k11|k12|k4|#|k7|k5|k8|k0"},
        {'p', "k8", 315, 1, 7, 1, 1, 6, "k11|k12|k4|#|k7|k5|k8|k0"},
        {'p', "k6", 289, 0, 8, 0, 0, 3, "k11|k12|k4|k6|k7|k5|k8|k0"},
        {'d', "k7", 0, 1, 7, 1, 1, -1, "k11|k12|k4|k6|#|k5|k8|k0"},
        {'p', "k12", 131, 1, 7, 1, 1, 1, "k11|k12|k4|k6|#|k5|k8|k0"},
        {'d', "k8", 0, 1, 6, 2, 1, -1, "k11|k12|k4|k6|#|k5|#|k0"},
        {'d', "k1", 0, 0, 6, 2, 1, -1, "k11|k12|k4|k6|#|k5|#|k0"},
        {'g', "k12", 131, 1, 6, 2, 1, 1, "k11|k12|k4|k6|#|k5|#|k0"},
        {'p', "k4", 22, 1, 6, 2, 1, 2, "k11|k12|k4|k6|#|k5|#|k0"},
        {'g', "k1", 0, 0, 6, 2, 1, -1, "k11|k12|k4|k6|#|k5|#|k0"},
        {'p', "k7", 237, 0, 7, 1, 1, 4, "k11|k12|k4|k6|k7|k5|#|k0"},
        {'p', "k3", 139, 0, 8, 0, 0, 6, "k11|k12|k4|k6|k7|k5|k3|k0"},
        {'p', "k5", 121, 1, 8, 0, 0, 5, "k11|k12|k4|k6|k7|k5|k3|k0"},
        {'p', "k2", 122, -1, 8, 0, 0, -1, "k11|k12|k4|k6|k7|k5|k3|k0"},
        {'p', "k10", 251, -1, 8, 0, 0, -1, "k11|k12|k4|k6|k7|k5|k3|k0"},
        {'d', "k7", 0, 1, 7, 1, 1, -1, "k11|k12|k4|k6|#|k5|k3|k0"},
        {'p', "k7", -26, 0, 8, 0, 0, 4, "k11|k12|k4|k6|k7|k5|k3|k0"},
        {'p', "k4", 381, 1, 8, 0, 0, 2, "k11|k12|k4|k6|k7|k5|k3|k0"},
        {'p', "k12", 61, 1, 8, 0, 0, 1, "k11|k12|k4|k6|k7|k5|k3|k0"},
        {'g', "k4", 381, 1, 8, 0, 0, 2, "k11|k12|k4|k6|k7|k5|k3|k0"},
        {'g', "k8", 0, 0, 8, 0, 0, -1, "k11|k12|k4|k6|k7|k5|k3|k0"},
        {'p', "k9", -29, -1, 8, 0, 0, -1, "k11|k12|k4|k6|k7|k5|k3|k0"},
        {'p', "k3", 99, 1, 8, 0, 0, 6, "k11|k12|k4|k6|k7|k5|k3|k0"},
    };

    static const step_t steps5[] = {
        {'p', "ab", 319, 0, 1, 0, 0, 1, ".|ab|.|.|."},
        {'d', "abd", 0, 0, 1, 0, 0, -1, ".|ab|.|.|."},
        {'p', "bb", 167, 0, 2, 0, 0, 0, "bb|ab|.|.|."},
        {'d', "ab", 0, 1, 1, 0, 0, -1, "bb|.|.|.|."},
        {'g', "abd", 0, 0, 1, 0, 0, -1, "bb|.|.|.|."},
        {'g', "cd", 0, 0, 1, 0, 0, -1, "bb|.|.|.|."},
        {'d', "c", 0, 0, 1, 0, 0, -1, "bb|.|.|.|."},
        {'d', "dd", 0, 0, 1, 0, 0, -1, "bb|.|.|.|."},
        {'g', "ab", 0, 0, 1, 0, 0, -1, "bb|.|.|.|."},
        {'p', "c", 276, 0, 2, 0, 0, 3, "bb|.|.|c|."},
        {'p', "cd", 488, 0, 3, 0, 0, 2, "bb|.|cd|c|."},
        {'d', "abd", 0, 0, 3, 0, 0, -1, "bb|.|cd|c|."},
        {'p', "b", 130, 0, 4, 0, 0, 4, "bb|.|cd|c|b"},
        {'p', "c", 472, 1, 4, 0, 0, 3, "bb|.|cd|c|b"},
        {'g', "c", 472, 1, 4, 0, 0, 3, "bb|.|cd|c|b"},
        {'g', "abd", 0, 0, 4, 0, 0, -1, "bb|.|cd|c|b"},
        {'r', "dd", 0, 0, 4, 0, 0, -1, "bb|.|cd|c|b"},
        {'d', "c", 0, 1, 3, 1, 1, -1, "bb|.|cd|#|b"},
        {'p', "c", 406, 0, 4, 0, 0, 3, "bb|.|cd|c|b"},
        {'g', "abd", 0, 0, 4, 0, 0, -1, "bb|.|cd|c|b"},
        {'d', "cd", 0, 1, 3, 1, 1, -1, "bb|.|#|c|b"},
        {'d', "dd", 0, 0, 3, 1, 1, -1, "bb|.|#|c|b"},
        {'p', "b", 460, 1, 3, 1, 1, 4, "bb|.|#|c|b"},
        {'d', "c", 0, 1, 2, 2, 1, -1, "bb|.|#|#|b"},
        {'g', "dd", 0, 0, 2, 2, 1, -1, "bb|.|#|#|b"},
        {'p', "dd", 417, 0, 3, 1, 1, 2, "bb|.|dd|#|b"},
        {'d', "dd", 0, 1, 2, 2, 1, -1, "bb|.|#|#|b"},
        {'g', "c", 0, 0, 2, 2, 1, -1, "bb|.|#|#|b"},
        {'g', "abd", 0, 0, 2, 2, 1, -1, "bb|.|#|#|b"},
        {'d', "bb", 0, 1, 1, 2, 0, -1, ".|.|#|#|b"},
        {'p', "dd", 466, 0, 2, 1, 0, 2, ".|.|dd|#|b"},
        {'p', "cd", 162, 0, 3, 0, 0, 3, ".|.|dd|cd|b"},
        {'d', "dd", 0, 1, 2, 1, 0, -1, ".|.|#|cd|b"},
        {'r', "abc", 0, 0, 2, 0, 0, -1, ".|.|cd|b|."},
        {'d', "c", 0, 0, 2, 0, 0, -1, ".|.|cd|b|."},
        {'g', "b", 460, 1, 2, 0, 0, 3, ".|.|cd|b|."},
        {'p', "abc", 0, 0, 3, 0, 0, 1, ".|abc|cd|b|."},
        {'d', "bb", 0, 0, 3, 0, 0, -1, ".|abc|cd|b|."},
        {'d', "abc", 0, 1, 2, 1, 0, -1, ".|#|cd|b|."},
        {'g', "abd", 0, 0, 2, 1, 0, -1, ".|#|cd|b|."},
        {'g', "b", 460, 1, 2, 1, 0, 3, ".|#|cd|b|."},
        {'p', "ab", -18, 0, 3, 0, 0, 1, ".|ab|cd|b|."},
        {'p', "ab", 126, 1, 3, 0, 0, 1, ".|ab|cd|b|."},
        {'d', "b", 0, 1, 2, 0, 0, -1, ".|ab|cd|.|."},
        {'p', "abc", 19, 0, 3, 0, 0, 3, ".|ab|cd|abc|."},
        {'p', "ab", -29, 1, 3, 0, 0, 1, ".|ab|cd|abc|."},
        {'p', "c", 110, 0, 4, 0, 0, 4, ".|ab|cd|abc|c"},
        {'d', "abd", 0, 0, 4, 0, 0, -1, ".|ab|cd|abc|c"},
        {'p', "ab", -6, 1, 4, 0, 0, 1, ".|ab|cd|abc|c"},
        {'p', "b", -13, 0, 5, 0, 0, 0, "b|ab|cd|abc|c"},
        {'r', "ab", 0, 0, 5, 0, 0, -1, "c|ab|b|cd|abc"},
        {'p', "abc", 450, 1, 5, 0, 0, 4, "c|ab|b|cd|abc"},
        {'p', "ab", -4, 1, 5, 0, 0, 1, "c|ab|b|cd|abc"},
        {'d', "bb", 0, 0, 5, 0, 0, -1, "c|ab|b|cd|abc"},
        {'p', "abd", 180, -1, 5, 0, 0, -1, "c|ab|b|cd|abc"},
        {'d', "abc", 0, 1, 4, 1, 1, -1, "c|ab|b|cd|#"},
        {'g', "c", 110, 1, 4, 1, 1, 0, "c|ab|b|cd|#"},
        {'p', "ab", 80, 1, 4, 1, 1, 1, "c|ab|b|cd|#"},
        {'p', "cd", 285, 1, 4, 1, 1, 3, "c|ab|b|cd|#"},
        {'g', "abd", 0, 0, 4, 1, 1, -1, "c|ab|b|cd|#"},
        {'p', "c", 379, 1, 4, 1, 1, 0, "c|ab|b|cd|#"},
        {'d', "ab", 0, 1, 3, 2, 1, -1, "c|#|b|cd|#"},
        {'d', "abd", 0, 0, 3, 2, 1, -1, "c|#|b|cd|#"},
        {'p', "bb", 115, 0, 4, 1, 1, 1, "c|bb|b|cd|#"},
        {'p', "abd", 187, 0, 5, 0, 0, 4, "c|bb|b|cd|abd"},
        {'g', "ab", 0, 0, 5, 0, 0, -1, "c|bb|b|cd|abd"},
        {'d', "b", 0, 1, 4, 1, 1, -1, "c|bb|#|cd|abd"},
        {'r', "abc", 0, 0, 4, 0, 0, -1, "bb|abd|cd|c|."},
        {'d', "b", 0, 0, 4, 0, 0, -1, "bb|abd|cd|c|."},
        {'p', "c", 383, 1, 4, 0, 0, 3, "bb|abd|cd|c|."},
    };

    static const step_t steps3[] = {
        {'d', "y", 0, 0, 0, 0, 0, -1, ".|.|."},
        {'p', "y", 435, 0, 1, 0, 0, 1, ".|y|."},
        {'p', "v", -37, 0, 2, 0, 0, 2, ".|y|v"},
        {'p', "w", 189, 0, 3, 0, 0, 0, "w|y|v"},
        {'g', "y", 435, 1, 3, 0, 0, 1, "w|y|v"},
        {'d', "w", 0, 1, 2, 1, 1, -1, "#|y|v"},
        {'p', "v", 104, 1, 2, 1, 1, 2, "#|y|v"},
        {'d', "y", 0, 1, 1, 2, 1, -1, "#|#|v"},
        {'p', "v", -35, 1, 1, 2, 1, 2, "#|#|v"},
        {'p', "x", -7, 0, 2, 1, 1, 0, "x|#|v"},
        {'d', "z", 0, 0, 2, 1, 1, -1, "x|#|v"},
        {'p', "z", 346, 0, 3, 0, 0, 1, "x|z|v"},
        {'p', "w", 405, -1, 3, 0, 0, -1, "x|z|v"},
        {'g', "y", 0, 0, 3, 0, 0, -1, "x|z|v"},
        {'p', "x", 456, 1, 3, 0, 0, 0, "x|z|v"},
        {'p', "y", 396, -1, 3, 0, 0, -1, "x|z|v"},
        {'p', "z", 345, 1, 3, 0, 0, 1, "x|z|v"},
        {'p', "v", 367, 1, 3, 0, 0, 2, "x|z|v"},
        {'p', "v", 294, 1, 3, 0, 0, 2, "x|z|v"},
        {'g', "x", 456, 1, 3, 0, 0, 0, "x|z|v"},
        {'d', "v", 0, 1, 2, 1, 1, -1, "x|z|#"},
        {'d', "y", 0, 0, 2, 1, 1, -1, "x|z|#"},
        {'g', "z", 345, 1, 2, 1, 1, 1, "x|z|#"},
        {'d', "v", 0, 0, 2, 1, 1, -1, "x|z|#"},
        {'d', "y", 0, 0, 2, 1, 1, -1, "x|z|#"},
        {'p', "v", 77, 0, 3, 0, 0, 2, "x|z|v"},
        {'p', "x", 445, 1, 3, 0, 0, 0, "x|z|v"},
        {'p', "x", 18, 1, 3, 0, 0, 0, "x|z|v"},
        {'g', "w", 0, 0, 3, 0, 0, -1, "x|z|v"},
        {'p', "x", 375, 1, 3, 0, 0, 0, "x|z|v"},
        {'p', "x", -4, 1, 3, 0, 0, 0, "x|z|v"},
        {'d', "w", 0, 0, 3, 0, 0, -1, "x|z|v"},
        {'d', "z", 0, 1, 2, 1, 1, -1, "x|#|v"},
        {'d', "z", 0, 0, 2, 1, 1, -1, "x|#|v"},
        {'p', "x", 28, 1, 2, 1, 1, 0, "x|#|v"},
        {'d', "x", 0, 1, 1, 2, 1, -1, "#|#|v"},
        {'g', "x", 0, 0, 1, 2, 1, -1, "#|#|v"},
        {'p', "w", 219, 0, 2, 1, 1, 0, "w|#|v"},
        {'d', "y", 0, 0, 2, 1, 1, -1, "w|#|v"},
        {'p', "z", 91, 0, 3, 0, 0, 1, "w|z|v"},
        {'p', "w", 482, 1, 3, 0, 0, 0, "w|z|v"},
        {'d', "w", 0, 1, 2, 1, 1, -1, "#|z|v"},
        {'d', "v", 0, 1, 1, 2, 1, -1, "#|z|#"},
        {'d', "x", 0, 0, 1, 2, 1, -1, "#|z|#"},
        {'p', "v", 193, 0, 2, 1, 1, 2, "#|z|v"},
        {'p', "z", 214, 1, 2, 1, 1, 1, "#|z|v"},
        {'p', "v", 297, 1, 2, 1, 1, 2, "#|z|v"},
        {'d', "x", 0, 0, 2, 1, 1, -1, "#|z|v"},
        {'p', "v", 335, 1, 2, 1, 1, 2, "#|z|v"},
        {'d', "v", 0, 1, 1, 2, 1, -1, "#|z|#"},
    };

    static const step_t steps16[] = {
        {'p', "dev7", 355, 0, 1, 0, 0, 1, ".|dev7|.|.|.|.|.|.|.|.|.|.|.|.|.|."},
        {'p', "dev15", 18, 0, 2, 0, 0, 6, ".|dev7|.|.|.|.|dev15|.|.|.|.|.|.|.|.|."},
        {'p', "dev0", 246, 0, 3, 0, 0, 4, ".|dev7|.|.|dev0|.|dev15|.|.|.|.|.|.|.|.|."},
        {'p', "dev1", 499, 0, 4, 0, 0, 7, ".|dev7|.|.|dev0|.|dev15|dev1|.|.|.|.|.|.|.|."},
        {'p', "dev11", 126, 0, 5, 0, 0, 2, ".|dev7|dev11|.|dev0|.|dev15|dev1|.|.|.|.|.|.|.|."},
        {'p', "dev3", -24, 0, 6, 0, 0, 13, ".|dev7|dev11|.|dev0|.|dev15|dev1|.|.|.|.|.|dev3|.|."},
        {'g', "dev8", 0, 0, 6, 0, 0, -1, ".|dev7|dev11|.|dev0|.|dev15|dev1|.|.|.|.|.|dev3|.|."},
        {'p', "dev6", 246, 0, 7, 0, 0, 14, ".|dev7|dev11|.|dev0|.|dev15|dev1|.|.|.|.|.|dev3|dev6|."},
        {'p', "dev11", 295, 1, 7, 0, 0, 2, ".|dev7|dev11|.|dev0|.|dev15|dev1|.|.|.|.|.|dev3|dev6|."},
        {'d', "dev12", 0, 0, 7, 0, 0, -1, ".|dev7|dev11|.|dev0|.|dev15|dev1|.|.|.|.|.|dev3|dev6|."},
        {'p', "dev5", 236, 0, 8, 0, 0, 11, ".|dev7|dev11|.|dev0|.|dev15|dev1|.|.|.|dev5|.|dev3|dev6|."},
        {'g', "dev2", 0, 0, 8, 0, 0, -1, ".|dev7|dev11|.|dev0|.|dev15|dev1|.|.|.|dev5|.|dev3|dev6|."},
        {'g', "dev17", 0, 0, 8, 0, 0, -1, ".|dev7|dev11|.|dev0|.|dev15|dev1|.|.|.|dev5|.|dev3|dev6|."},
        {'g', "dev0", 246, 1, 8, 0, 0, 4, ".|dev7|dev11|.|dev0|.|dev15|dev1|.|.|.|dev5|.|dev3|dev6|."},
        {'d', "dev18", 0, 0, 8, 0, 0, -1, ".|dev7|dev11|.|dev0|.|dev15|dev1|.|.|.|dev5|.|dev3|dev6|."},
        {'g', "dev9", 0, 0, 8, 0, 0, -1, ".|dev7|dev11|.|dev0|.|dev15|dev1|.|.|.|dev5|.|dev3|dev6|."},
        {'p', "dev16", 383, 0, 9, 0, 0, 3, ".|dev7|dev11|dev16|dev0|.|dev15|dev1|.|.|.|dev5|.|dev3|dev6|."},
        {'p', "dev19", 412, 0, 10, 0, 0, 10, ".|dev7|dev11|dev16|dev0|.|dev15|dev1|.|.|dev19|dev5|.|dev3|dev6|."},
        {'p', "dev5", 215, 1, 10, 0, 0, 11, ".|dev7|dev11|dev16|dev0|.|dev15|dev1|.|.|dev19|dev5|.|dev3|dev6|."},
        {'p', "dev1", 423, 1, 10, 0, 0, 7, ".|dev7|dev11|dev16|dev0|.|dev15|dev1|.|.|dev19|dev5|.|dev3|dev6|."},
        {'d', "dev8", 0, 0, 10, 0, 0, -1, ".|dev7|dev11|dev16|dev0|.|dev15|dev1|.|.|dev19|dev5|.|dev3|dev6|."},
        {'d', "dev15", 0, 1, 9, 1, 0, -1, ".|dev7|dev11|dev16|dev0|.|#|dev1|.|.|dev19|dev5|.|dev3|dev6|."},
        {'g', "dev4", 0, 0, 9, 1, 0, -1, ".|dev7|dev11|dev16|dev0|.|#|dev1|.|.|dev19|dev5|.|dev3|dev6|."},
        {'p', "dev6", 157, 1, 9, 1, 0, 14, ".|dev7|dev11|dev16|dev0|.|#|dev1|.|.|dev19|dev5|.|dev3|dev6|."},
        {'p', "dev14", 314, 0, 10, 1, 0, 9, ".|dev7|dev11|dev16|dev0|.|#|dev1|.|dev14|dev19|dev5|.|dev3|dev6|."},
        {'d', "dev13", 0, 0, 10, 1, 0, -1, ".|dev7|dev11|dev16|dev0|.|#|dev1|.|dev14|dev19|dev5|.|dev3|dev6|."},
        {'d', "dev10", 0, 0, 10, 1, 0, -1, ".|dev7|dev11|dev16|dev0|.|#|dev1|.|dev14|dev19|dev5|.|dev3|dev6|."},
        {'g', "dev6", 157, 1, 10, 1, 0, 14, ".|dev7|dev11|dev16|dev0|.|#|dev1|.|dev14|dev19|dev5|.|dev3|dev6|."},
        {'r', "dev3", 0, 0, 10, 0, 0, -1, ".|dev7|dev11|dev16|dev0|.|.|dev1|.|dev14|dev19|dev5|.|dev3|dev6|."},
        {'p', "dev7", 193, 1, 10, 0, 0, 1, ".|dev7|dev11|dev16|dev0|.|.|dev1|.|dev14|dev19|dev5|.|dev3|dev6|."},
        {'p', "dev3", 131, 1, 10, 0, 0, 13, ".|dev7|dev11|dev16|dev0|.|.|dev1|.|dev14|dev19|dev5|.|dev3|dev6|."},
        {'p', "dev9", -7, 0, 11, 0, 0, 15, ".|dev7|dev11|dev16|dev0|.|.|dev1|.|dev14|dev19|dev5|.|dev3|dev6|dev9"},
        {'d', "dev11", 0, 1, 10, 1, 0, -1, ".|dev7|#|dev16|dev0|.|.|dev1|.|dev14|dev19|dev5|.|dev3|dev6|dev9"},
        {'d', "dev9", 0, 1, 9, 1, 0, -1, ".|dev7|#|dev16|dev0|.|.|dev1|.|dev14|dev19|dev5|.|dev3|dev6|."},
        {'p', "dev10", 245, 0, 10, 1, 0, 5, ".|dev7|#|dev16|dev0|dev10|.|dev1|.|dev14|dev19|dev5|.|dev3|dev6|."},
        {'g', "dev10", 245, 1, 10, 1, 0, 5, ".|dev7|#|dev16|dev0|dev10|.|dev1|.|dev14|dev19|dev5|.|dev3|dev6|."},
        {'g', "dev13", 0, 0, 10, 1, 0, -1, ".|dev7|#|dev16|dev0|dev10|.|dev1|.|dev14|dev19|dev5|.|dev3|dev6|."},
        {'d', "dev19", 0, 1, 9, 2, 0, -1, ".|dev7|#|dev16|dev0|dev10|.|dev1|.|dev14|#|dev5|.|dev3|dev6|."},
        {'p', "dev2", 146, 0, 10, 1, 0, 10, ".|dev7|#|dev16|dev0|dev10|.|dev1|.|dev14|dev2|dev5|.|dev3|dev6|."},
        {'p', "dev14", 206, 1, 10, 1, 0, 9, ".|dev7|#|dev16|dev0|dev10|.|dev1|.|dev14|dev2|dev5|.|dev3|dev6|."},
        {'d', "dev12", 0, 0, 10, 1, 0, -1, ".|dev7|#|dev16|dev0|dev10|.|dev1|.|dev14|dev2|dev5|.|dev3|dev6|."},
        {'p', "dev5", -41, 1, 10, 1, 0, 11, ".|dev7|#|dev16|dev0|dev10|.|dev1|.|dev14|dev2|dev5|.|dev3|dev6|."},
        {'p', "dev11", 123, 0, 11, 0, 0, 2, ".|dev7|dev11|dev16|dev0|dev10|.|dev1|.|dev14|dev2|dev5|.|dev3|dev6|."},
        {'d', "dev11", 0, 1, 10, 1, 0, -1, ".|dev7|#|dev16|dev0|dev10|.|dev1|.|dev14|dev2|dev5|.|dev3|dev6|."},
        {'g', "dev11", 0, 0, 10, 1, 0, -1, ".|dev7|#|dev16|dev0|dev10|.|dev1|.|dev14|dev2|dev5|.|dev3|dev6|."},
        {'p', "dev18", 162, 0, 11, 1, 0, 15, ".|dev7|#|dev16|dev0|dev10|.|dev1|.|dev14|dev2|dev5|.|dev3|dev6|dev18"},
        {'g', "dev13", 0, 0, 11, 1, 0, -1, ".|dev7|#|dev16|dev0|dev10|.|dev1|.|dev14|dev2|dev5|.|dev3|dev6|dev18"},
        {'p', "dev3", 6, 1, 11, 1, 0, 13, ".|dev7|#|dev16|dev0|dev10|.|dev1|.|dev14|dev2|dev5|.|dev3|dev6|dev18"},
        {'d', "dev5", 0, 1, 10, 1, 0, -1, ".|dev7|#|dev16|dev0|dev10|.|dev1|.|dev14|dev2|.|.|dev3|dev6|dev18"},
        {'d', "dev4", 0, 0, 10, 1, 0, -1, ".|dev7|#|dev16|dev0|dev10|.|dev1|.|dev14|dev2|.|.|dev3|dev6|dev18"},
        {'p', "dev17", 205, 0, 11, 1, 0, 0, "dev17|dev7|#|dev16|dev0|dev10|.|dev1|.|dev14|dev2|.|.|dev3|dev6|dev18"},
        {'g', "dev10", 245, 1, 11, 1, 0, 5, "dev17|dev7|#|dev16|dev0|dev10|.|dev1|.|dev14|dev2|.|.|dev3|dev6|dev18"},
        {'g', "dev3", 6, 1, 11, 1, 0, 13, "dev17|dev7|#|dev16|dev0|dev10|.|dev1|.|dev14|dev2|.|.|dev3|dev6|dev18"},
        {'d', "dev9", 0, 0, 11, 1, 0, -1, "dev17|dev7|#|dev16|dev0|dev10|.|dev1|.|dev14|dev2|.|.|dev3|dev6|dev18"},
        {'d', "dev13", 0, 0, 11, 1, 0, -1, "dev17|dev7|#|dev16|dev0|dev10|.|dev1|.|dev14|dev2|.|.|dev3|dev6|dev18"},
        {'p', "dev6", 197, 1, 11, 1, 0, 14, "dev17|dev7|#|dev16|dev0|dev10|.|dev1|.|dev14|dev2|.|.|dev3|dev6|dev18"},
        {'p', "dev14", -13, 1, 11, 1, 0, 9, "dev17|dev7|#|dev16|dev0|dev10|.|dev1|.|dev14|dev2|.|.|dev3|dev6|dev18"},
        {'r', "dev7", 0, 0, 11, 0, 0, -1, "dev17|dev7|.|dev16|dev0|dev10|.|dev1|.|dev14|dev2|.|.|dev3|dev6|dev18"},
        {'d', "dev7", 0, 1, 10, 0, 0, -1, "dev17|.|.|dev16|dev0|dev10|.|dev1|.|dev14|dev2|.|.|dev3|dev6|dev18"},
        {'g', "dev13", 0, 0, 10, 0, 0, -1, "dev17|.|.|dev16|dev0|dev10|.|dev1|.|dev14|dev2|.|.|dev3|dev6|dev18"},
        {'p', "dev15", -13, 0, 11, 0, 0, 6, "dev17|.|.|dev16|dev0|dev10|dev15|dev1|.|dev14|dev2|.|.|dev3|dev6|dev18"},
        {'p', "dev8", 488, 0, 12, 0, 0, 12, "dev17|.|.|dev16|dev0|dev10|dev15|dev1|.|dev14|dev2|.|dev8|dev3|dev6|dev18"},
        {'d', "dev6", 0, 1, 11, 1, 0, -1, "dev17|.|.|dev16|dev0|dev10|dev15|dev1|.|dev14|dev2|.|dev8|dev3|#|dev18"},
        {'g', "dev13", 0, 0, 11, 1, 0, -1, "dev17|.|.|dev16|dev0|dev10|dev15|dev1|.|dev14|dev2|.|dev8|dev3|#|dev18"},
        {'p', "dev4", 272, 0, 12, 1, 1, 8, "dev17|.|.|dev16|dev0|dev10|dev15|dev1|dev4|dev14|dev2|.|dev8|dev3|#|dev18"},
        {'p', "dev18", 362, 1, 12, 1, 1, 15, "dev17|.|.|dev16|dev0|dev10|dev15|dev1|dev4|dev14|dev2|.|dev8|dev3|#|dev18"},
        {'p', "dev1", 45, 1, 12, 1, 1, 7, "dev17|.|.|dev16|dev0|dev10|dev15|dev1|dev4|dev14|dev2|.|dev8|dev3|#|dev18"},
        {'p', "dev13", 119, 0, 13, 0, 0, 14, "dev17|.|.|dev16|dev0|dev10|dev15|dev1|dev4|dev14|dev2|.|dev8|dev3|dev13|dev18"},
        {'p', "dev10", 432, 1, 13, 0, 0, 5, "dev17|.|.|dev16|dev0|dev10|dev15|dev1|dev4|dev14|dev2|.|dev8|dev3|dev13|dev18"},
        {'g', "dev10", 432, 1, 13, 0, 0, 5, "dev17|.|.|dev16|dev0|dev10|dev15|dev1|dev4|dev14|dev2|.|dev8|dev3|dev13|dev18"},
        {'p', "dev16", 224, 1, 13, 0, 0, 3, "dev17|.|.|dev16|dev0|dev10|dev15|dev1|dev4|dev14|dev2|.|dev8|dev3|dev13|dev18"},
        {'g', "dev10", 432, 1, 13, 0, 0, 5, "dev17|.|.|dev16|dev0|dev10|dev15|dev1|dev4|dev14|dev2|.|dev8|dev3|dev13|dev18"},
        {'p', "dev15", 236, 1, 13, 0, 0, 6, "dev17|.|.|dev16|dev0|dev10|dev15|dev1|dev4|dev14|dev2|.|dev8|dev3|dev13|dev18"},
        {'p', "dev6", 80, 0, 14, 0, 0, 1, "dev17|dev6|.|dev16|dev0|dev10|dev15|dev1|dev4|dev14|dev2|.|dev8|dev3|dev13|dev18"},
        {'d', "dev8", 0, 1, 13, 1, 1, -1, "dev17|dev6|.|dev16|dev0|dev10|dev15|dev1|dev4|dev14|dev2|.|#|dev3|dev13|dev18"},
        {'g', "dev1", 45, 1, 13, 1, 1, 7, "dev17|dev6|.|dev16|dev0|dev10|dev15|dev1|dev4|dev14|dev2|.|#|dev3|dev13|dev18"},
        {'d', "dev14", 0, 1, 12, 2, 1, -1, "dev17|dev6|.|dev16|dev0|dev10|dev15|dev1|dev4|#|dev2|.|#|dev3|dev13|dev18"},
        {'g', "dev12", 0, 0, 12, 2, 1, -1, "dev17|dev6|.|dev16|dev0|dev10|dev15|dev1|dev4|#|dev2|.|#|dev3|dev13|dev18"},
        {'d', "dev6", 0, 1, 11, 2, 1, -1, "dev17|.|.|dev16|dev0|dev10|dev15|dev1|dev4|#|dev2|.|#|dev3|dev13|dev18"},
        {'g', "dev6", 0, 0, 11, 2, 1, -1, "dev17|.|.|dev16|dev0|dev10|dev15|dev1|dev4|#|dev2|.|#|dev3|dev13|dev18"},
        {'d', "dev0", 0, 1, 10, 3, 1, -1, "dev17|.|.|dev16|#|dev10|dev15|dev1|dev4|#|dev2|.|#|dev3|dev13|dev18"},
        {'p', "dev8", 340, 0, 11, 2, 1, 12, "dev17|.|.|dev16|#|dev10|dev15|dev1|dev4|#|dev2|.|dev8|dev3|dev13|dev18"},
        {'d', "dev7", 0, 0, 11, 2, 1, -1, "dev17|.|.|dev16|#|dev10|dev15|dev1|dev4|#|dev2|.|dev8|dev3|dev13|dev18"},
        {'p', "dev6", 288, 0, 12, 2, 1, 1, "dev17|dev6|.|dev16|#|dev10|dev15|dev1|dev4|#|dev2|.|dev8|dev3|dev13|dev18"},
        {'d', "dev17", 0, 1, 11, 3, 1, -1, "#|dev6|.|dev16|#|dev10|dev15|dev1|dev4|#|dev2|.|dev8|dev3|dev13|dev18"},
        {'g', "dev15", 236, 1, 11, 3, 1, 6, "#|dev6|.|dev16|#|dev10|dev15|dev1|dev4|#|dev2|.|dev8|dev3|dev13|dev18"},
        {'r', "dev14", 0, 0, 11, 0, 0, -1, "dev18|.|.|dev16|.|dev10|dev15|dev1|dev4|.|dev2|.|dev8|dev3|dev6|dev13"},
        {'d', "dev1", 0, 1, 10, 1, 0, -1, "dev18|.|.|dev16|.|dev10|dev15|#|dev4|.|dev2|.|dev8|dev3|dev6|dev13"},
        {'p', "dev3", 213, 1, 10, 1, 0, 13, "dev18|.|.|dev16|.|dev10|dev15|#|dev4|.|dev2|.|dev8|dev3|dev6|dev13"},
        {'d', "dev19", 0, 0, 10, 1, 0, -1, "dev18|.|.|dev16|.|dev10|dev15|#|dev4|.|dev2|.|dev8|dev3|dev6|dev13"},
    };

    static const step_t steps1[] = {
        {'d', "q", 0, 0, 0, 0, 0, -1, "."},
        {'g', "p", 0, 0, 0, 0, 0, -1, "."},
        {'d', "p", 0, 0, 0, 0, 0, -1, "."},
        {'p', "p", 430, 0, 1, 0, 0, 0, "p"},
        {'p', "p", 54, 1, 1, 0, 0, 0, "p"},
        {'p', "p", 171, 1, 1, 0, 0, 0, "p"},
        {'p', "q", 348, -1, 1, 0, 0, -1, "p"},
        {'d', "p", 0, 1, 0, 1, 1, -1, "#"},
        {'p', "p", 405, 0, 1, 0, 0, 0, "p"},
        {'p', "p", -45, 1, 1, 0, 0, 0, "p"},
        {'d', "p", 0, 1, 0, 1, 1, -1, "#"},
        {'g', "p", 0, 0, 0, 1, 1, -1, "#"},
        {'p', "q", 153, 0, 1, 0, 0, 0, "q"},
        {'p', "p", 151, -1, 1, 0, 0, -1, "q"},
        {'p', "q", 319, 1, 1, 0, 0, 0, "q"},
        {'p', "q", 99, 1, 1, 0, 0, 0, "q"},
        {'p', "q", 258, 1, 1, 0, 0, 0, "q"},
        {'d', "p", 0, 0, 1, 0, 0, -1, "q"},
        {'p', "q", 313, 1, 1, 0, 0, 0, "q"},
        {'p', "q", 273, 1, 1, 0, 0, 0, "q"},
    };

    static void run_steps(const char *name, int cap, const step_t *st, size_t n) {
        slotmap m;
        size_t i;
        char ctx[80];
        int32_t v;
        CHECK_INT(sm_init(&m, cap), 0);
        for (i = 0; i < n; i++) {
            snprintf(ctx, sizeof ctx, "%s step %d: %c %s", name, (int)i, st[i].op, st[i].key);
            switch (st[i].op) {
            case 'p':
                CHECK_INT_CTX(ctx, sm_put(&m, st[i].key, st[i].val), st[i].ret);
                break;
            case 'd':
                CHECK_INT_CTX(ctx, sm_del(&m, st[i].key), st[i].ret);
                break;
            case 'g':
                v = -12345;
                CHECK_INT_CTX(ctx, sm_get(&m, st[i].key, &v), st[i].ret);
                CHECK_INT_CTX(ctx, v, st[i].ret ? st[i].val : -12345);
                break;
            default:
                sm_rehash(&m);
                break;
            }
            CHECK_INT_CTX(ctx, sm_count(&m), st[i].used);
            CHECK_INT_CTX(ctx, sm_gone(&m), st[i].gone);
            CHECK_INT_CTX(ctx, sm_needs_rehash(&m), st[i].need);
            if (st[i].op != 'r') CHECK_INT_CTX(ctx, sm_slot_of(&m, st[i].key), st[i].slot);
            CHECK_STR_CTX(ctx, layout(&m), st[i].layout);
        }
    }

    #define RUN(name, cap) run_steps(#name, cap, name, sizeof name / sizeof name[0])

    static void test_init(void) {
        slotmap m;
        CHECK_INT(sm_init(&m, 0), -1);
        CHECK_INT(sm_init(&m, -3), -1);
        CHECK_INT(sm_init(&m, 65), -1);
        CHECK_INT(sm_init(&m, 1), 0);
        CHECK_INT(sm_init(&m, 64), 0);
        CHECK_INT(sm_count(&m), 0);
        CHECK_INT(sm_gone(&m), 0);
        CHECK_INT(sm_slot_state(&m, 0), 0);
        CHECK_INT(sm_slot_state(&m, 63), 0);
        CHECK_INT(sm_slot_state(&m, 64), -1);
        CHECK_INT(sm_slot_state(&m, -1), -1);
        CHECK_INT(sm_init(&m, 8), 0);
        CHECK_INT(sm_slot_state(&m, 7), 0);
        CHECK_INT(sm_slot_state(&m, 8), -1);
        CHECK_INT(sm_needs_rehash(&m), 0);
        /* a used map is wiped by init */
        sm_put(&m, "a", 1);
        sm_init(&m, 8);
        CHECK_INT(sm_count(&m), 0);
        CHECK_INT(sm_slot_of(&m, "a"), -1);
    }

    static void test_keys(void) {
        slotmap m;
        int32_t v = 0;
        sm_init(&m, 8);
        CHECK_INT(sm_put(&m, "", 1), SM_BADKEY);
        CHECK_INT(sm_put(&m, "0123456789abcdef", 1), SM_BADKEY);
        CHECK_INT(sm_put(&m, "0123456789abcde", 1), SM_INSERTED);
        CHECK_INT(sm_count(&m), 1);
        CHECK_INT(sm_get(&m, "0123456789abcde", &v), 1);
        CHECK_INT(v, 1);
        CHECK_INT(sm_get(&m, "", &v), 0);
        CHECK_INT(sm_get(&m, "0123456789abcdef", &v), 0);
        CHECK_INT(sm_del(&m, ""), 0);
        CHECK_INT(sm_del(&m, "0123456789abcdef"), 0);
        CHECK_INT(sm_slot_of(&m, ""), -1);
        CHECK_INT(sm_count(&m), 1);
        /* keys that are prefixes of each other are different keys; case matters */
        CHECK_INT(sm_put(&m, "ab", 2), SM_INSERTED);
        CHECK_INT(sm_put(&m, "abc", 3), SM_INSERTED);
        CHECK_INT(sm_put(&m, "AB", 4), SM_INSERTED);
        CHECK_INT(sm_get(&m, "ab", &v), 1);
        CHECK_INT(v, 2);
        CHECK_INT(sm_get(&m, "abc", &v), 1);
        CHECK_INT(v, 3);
        CHECK_INT(sm_get(&m, "AB", &v), 1);
        CHECK_INT(v, 4);
        CHECK_INT(sm_get(&m, "a", &v), 0);
        CHECK_INT(sm_get(&m, "abcd", &v), 0);
        CHECK_INT(sm_del(&m, "abc"), 1);
        CHECK_INT(sm_get(&m, "ab", &v), 1);
        CHECK_INT(sm_get(&m, "abc", &v), 0);
        CHECK_INT(sm_count(&m), 3);
        /* non-ASCII bytes hash as unsigned bytes */
        sm_init(&m, 5);
        CHECK_INT(sm_put(&m, "caf\xc3\xa9", 5), SM_INSERTED);
        CHECK_INT(sm_slot_of(&m, "caf\xc3\xa9"), 4);
        sm_init(&m, 5);
        CHECK_INT(sm_put(&m, "gr\xc3\xb6\xc3\x9f" "e", 6), SM_INSERTED);
        CHECK_INT(sm_slot_of(&m, "gr\xc3\xb6\xc3\x9f" "e"), 4);
        sm_init(&m, 8);
        /* negative values are values */
        CHECK_INT(sm_put(&m, "neg", -2147483647 - 1), SM_INSERTED);
        CHECK_INT(sm_get(&m, "neg", &v), 1);
        CHECK_INT(v, -2147483647 - 1);
    }

    static void test_full_table_update(void) {
        slotmap m;
        int32_t v = 0;
        sm_init(&m, 3);
        CHECK_INT(sm_put(&m, "x", 1), SM_INSERTED);
        CHECK_INT(sm_put(&m, "y", 2), SM_INSERTED);
        CHECK_INT(sm_put(&m, "z", 3), SM_INSERTED);
        CHECK_INT(sm_put(&m, "w", 4), SM_FULL);
        CHECK_INT(sm_put(&m, "y", 20), SM_UPDATED);
        CHECK_INT(sm_put(&m, "x", 10), SM_UPDATED);
        CHECK_INT(sm_put(&m, "z", 30), SM_UPDATED);
        CHECK_INT(sm_count(&m), 3);
        CHECK_INT(sm_get(&m, "w", &v), 0);
        CHECK_INT(sm_get(&m, "q", &v), 0);
        CHECK_INT(sm_get(&m, "z", &v), 1);
        CHECK_INT(v, 30);
        CHECK_INT(sm_del(&m, "w"), 0);
        CHECK_INT(sm_count(&m), 3);
    }

    static void test_needs_rehash(void) {
        slotmap m;
        int i;
        char key[16];
        sm_init(&m, 8);
        for (i = 0; i < 7; i++) {
            snprintf(key, sizeof key, "n%d", i);
            sm_put(&m, key, i);
        }
        CHECK_INT(sm_count(&m), 7);
        CHECK_INT(sm_gone(&m), 0);
        CHECK_INT(sm_needs_rehash(&m), 0); /* no tombstones: nothing to gain */
        sm_init(&m, 4);
        sm_put(&m, "n0", 0);
        sm_put(&m, "n1", 1);
        sm_put(&m, "n2", 2);
        CHECK_INT(sm_needs_rehash(&m), 0);
    }

    static void test_next(void) {
        slotmap m;
        const char *k = NULL;
        int32_t v = 0;
        int cur = 0;
        sm_init(&m, 8);
        CHECK_INT(sm_next(&m, &cur, &k, &v), 0);
        CHECK_INT(cur, 8);
        sm_put(&m, "c3", 1);
        sm_put(&m, "d2", 2);
        sm_put(&m, "e1", 3);
        sm_put(&m, "a1", 4);
        sm_put(&m, "b0", 5);
        sm_del(&m, "d2");
        /* layout: slots 3 c3, 4 gone, 5 e1, 6 ..: a1, b0 home 7 -> slots 7 and 0 */
        cur = 0;
        CHECK_INT(sm_next(&m, &cur, &k, &v), 1);
        CHECK_STR(k, "b0");
        CHECK_INT(v, 5);
        CHECK_INT(cur, 1);
        CHECK_INT(sm_next(&m, &cur, &k, &v), 1);
        CHECK_STR(k, "c3");
        CHECK_INT(v, 1);
        CHECK_INT(cur, 4);
        CHECK_INT(sm_next(&m, &cur, &k, &v), 1);
        CHECK_STR(k, "e1");
        CHECK_INT(cur, 6);
        CHECK_INT(sm_next(&m, &cur, &k, &v), 1);
        CHECK_STR(k, "a1");
        CHECK_INT(v, 4);
        CHECK_INT(cur, 8);
        CHECK_INT(sm_next(&m, &cur, &k, &v), 0);
        CHECK_INT(cur, 8);
        /* a cursor in the middle */
        cur = 4;
        CHECK_INT(sm_next(&m, &cur, &k, &v), 1);
        CHECK_STR(k, "e1");
        cur = 7;
        CHECK_INT(sm_next(&m, &cur, &k, &v), 1);
        CHECK_STR(k, "a1");
        cur = 8;
        CHECK_INT(sm_next(&m, &cur, &k, &v), 0);
    }

    int main(void) {
        h_init();
        test_init();
        test_keys();
        test_full_table_update();
        test_needs_rehash();
        test_next();
        RUN(stepsE, 8);
        RUN(stepsF, 64);
        RUN(stepsA, 8);
        RUN(stepsB, 8);
        RUN(stepsC, 4);
        RUN(stepsD, 8);
        RUN(steps8, 8);
        RUN(steps5, 5);
        RUN(steps3, 3);
        RUN(steps16, 16);
        RUN(steps1, 1);
        return h_report();
    }
''')

LIB = Lib(
    name="slotmap", lang="c", title="the slotmap hash table",
    blurb="The device registry on the gateway keeps its tiny name-to-id table in this fixed-size hash map, so slot placement must be exactly what the README says.",
    files={"README.md": README1, "include/slotmap.h": F2, "src/slotmap.c": F3},
    visible_tests={"tests/test_main.c": V4, "tests/harness.h": _lang3.C_HARNESS},
    hidden_tests={"tests/test_main.c": H5},
    mutate=["src/slotmap.c"], difficulty=4, tags=["hash-table", "open-addressing", "data-structure"],
    verify=_lang3.C_VERIFY,
)

_lang3.add(LIB, n=8)
