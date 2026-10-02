"""Unicode normalisation, case folding and code point handling in a handle registry (python) and a notes search kit (js)."""
from fx import dd, family
from generators.fix._hand_kit import Base, Bug, tasks_from

# ------------------------------------------------------------------------------------------------------------------
# Base A (python): a registry of unique user handles compared by their canonical form.
# ------------------------------------------------------------------------------------------------------------------

A_README = dd('''
    # handles

    Unique, human-typed handles for a chat service. A handle is shown the way its owner typed it (surrounding
    whitespace removed) but two handles clash when their **canonical form** is equal.

    ## `handles.canon`
    `canonical(handle)` applies, in this order:
    1. Unicode NFKC normalisation;
    2. removal of every character of Unicode category `Cf` (zero-width and other invisible format characters);
    3. case folding (`str.casefold`);
    4. stripping of surrounding whitespace, then every run of whitespace becomes one `_`.

    `is_valid(canon)` checks a canonical form: 3 to 20 **characters** (not bytes), the first one a letter, and only
    letters, digits, `_` and `.` after that.

    ## `handles.registry.Registry`
    * `register(handle)` returns the canonical form. `Invalid` (a `ValueError`) if it is not valid, `Taken` if the
      canonical form is reserved (`admin`, `root`, `support`) or already registered.
    * `lookup(handle)` returns the registered handle as typed, or `None`.
    * `rename(old, new)` moves a registration to a new handle; it is atomic (on `Invalid`/`Taken` nothing changes),
      `KeyError` if `old` is not registered. Renaming to a handle with the *same* canonical form (a change of
      capitalisation) is allowed. The search index follows the rename.

    ## `handles.search.prefix_search(registry, query, limit=10)`
    Handles whose canonical form starts with the canonical form of `query`, ordered by canonical form, at most
    `limit` of them, shown as typed. A blank query finds nothing.
''')

A_CANON = dd('''
    import re
    import unicodedata

    MIN_LEN, MAX_LEN = 3, 20


    def canonical(handle):
        s = unicodedata.normalize("NFKC", handle)
        s = "".join(ch for ch in s if unicodedata.category(ch) != "Cf")
        s = s.casefold()
        return re.sub(r"\\s+", "_", s.strip())


    def is_valid(canon):
        if not (MIN_LEN <= len(canon) <= MAX_LEN):
            return False
        if not canon[0].isalpha():
            return False
        return all(ch.isalnum() or ch in "_." for ch in canon)
''')

A_SEARCH = dd('''
    import bisect

    from .canon import canonical


    class SearchIndex:
        """Sorted list of canonical handles."""

        def __init__(self):
            self._keys = []

        def add(self, key):
            bisect.insort(self._keys, key)

        def remove(self, key):
            i = bisect.bisect_left(self._keys, key)
            if i < len(self._keys) and self._keys[i] == key:
                del self._keys[i]

        def prefix(self, q, limit):
            i = bisect.bisect_left(self._keys, q)
            out = []
            while i < len(self._keys) and self._keys[i].startswith(q) and len(out) < limit:
                out.append(self._keys[i])
                i += 1
            return out


    def prefix_search(registry, query, limit=10):
        q = canonical(query)
        if not q:
            return []
        return [registry.display(c) for c in registry.index.prefix(q, limit)]
''')

A_REGISTRY = dd('''
    from .canon import canonical, is_valid
    from .search import SearchIndex

    RESERVED = {"admin", "root", "support"}


    class Taken(Exception):
        pass


    class Invalid(ValueError):
        pass


    class Registry:
        def __init__(self):
            self._by_canon = {}
            self.index = SearchIndex()

        def display(self, canon):
            return self._by_canon[canon]

        def register(self, handle):
            c = canonical(handle)
            if not is_valid(c):
                raise Invalid(handle)
            if c in RESERVED or c in self._by_canon:
                raise Taken(handle)
            self._by_canon[c] = handle.strip()
            self.index.add(c)
            return c

        def lookup(self, handle):
            return self._by_canon.get(canonical(handle))

        def rename(self, old, new):
            oc, nc = canonical(old), canonical(new)
            if oc not in self._by_canon:
                raise KeyError(old)
            if not is_valid(nc):
                raise Invalid(new)
            if nc in RESERVED or (nc != oc and nc in self._by_canon):
                raise Taken(new)
            del self._by_canon[oc]
            self.index.remove(oc)
            self._by_canon[nc] = new.strip()
            self.index.add(nc)
            return nc
''')

A_VISIBLE = {
    "tests/test_basic.py": dd('''
        import unittest

        from handles.canon import canonical, is_valid
        from handles.registry import Registry, Taken
        from handles.search import prefix_search


        class BasicTests(unittest.TestCase):
            def test_canonical_simple(self):
                self.assertEqual(canonical("  Ann  Lee "), "ann_lee")

            def test_register_and_clash(self):
                r = Registry()
                self.assertEqual(r.register("Anna"), "anna")
                with self.assertRaises(Taken):
                    r.register("ANNA")
                self.assertEqual(r.lookup("anna"), "Anna")

            def test_search(self):
                r = Registry()
                for h in ("Bea", "Bernd", "Cleo"):
                    r.register(h)
                self.assertEqual(prefix_search(r, "be"), ["Bea", "Bernd"])

            def test_is_valid(self):
                self.assertTrue(is_valid("abc"))
                self.assertFalse(is_valid("9abc"))


        if __name__ == "__main__":
            unittest.main()
    '''),
}

A_HIDDEN = {
    "tests/test_hidden_handles.py": dd('''
        import unittest

        from handles.canon import canonical, is_valid
        from handles.registry import Invalid, Registry, Taken
        from handles.search import prefix_search


        class Canonical(unittest.TestCase):
            def test_case_folding_is_full(self):
                self.assertEqual(canonical("Stra\\u00dfe"), "strasse")
                self.assertEqual(canonical("STRASSE"), "strasse")
                self.assertEqual(canonical("\\u039f\\u0394\\u039f\\u03a3"), canonical("\\u03bf\\u03b4\\u03bf\\u03c2"))

            def test_compatibility_forms_fold_together(self):
                self.assertEqual(canonical("\\uff21\\uff24\\uff2d\\uff29\\uff2e"), "admin")
                self.assertEqual(canonical("\\ufb01sh"), "fish")
                self.assertEqual(canonical("x\\u00b2"), "x2")

            def test_invisible_format_characters_are_dropped(self):
                self.assertEqual(canonical("ad\\u200bmin"), "admin")
                self.assertEqual(canonical("ro\\u00adot"), "root")
                self.assertEqual(canonical("a\\u2060b\\ufeffc"), "abc")

            def test_composed_and_decomposed_accents_agree(self):
                self.assertEqual(canonical("\\u00c9ric"), "\\u00e9ric")
                self.assertEqual(canonical("E\\u0301ric"), "\\u00e9ric")

            def test_whitespace(self):
                self.assertEqual(canonical("  a \\t b\\u00a0\\u00a0c  "), "a_b_c")

            def test_validity_counts_characters(self):
                self.assertTrue(is_valid("abc"))
                self.assertFalse(is_valid("ab"))
                self.assertTrue(is_valid("a" * 20))
                self.assertFalse(is_valid("a" * 21))
                self.assertFalse(is_valid("1abc"))
                self.assertFalse(is_valid("ab!c"))
                self.assertTrue(is_valid("ab_c.d"))
                self.assertTrue(is_valid("\\u0438\\u0432\\u0430\\u043d"))
                self.assertTrue(is_valid("\\u0436" * 12))
                self.assertFalse(is_valid("\\u044f\\u043d"))
                self.assertFalse(is_valid("\\u0436" * 21))


        class RegistryRules(unittest.TestCase):
            def test_clashes(self):
                r = Registry()
                self.assertEqual(r.register("Anna"), "anna")
                for dup in ("ANNA", " anna ", "ANNa"):
                    with self.assertRaises(Taken):
                        r.register(dup)
                r.register("Stra\\u00dfe")
                with self.assertRaises(Taken):
                    r.register("STRASSE")

            def test_reserved_names_in_disguise(self):
                r = Registry()
                for sneaky in ("Admin", "\\uff41\\uff44\\uff4d\\uff49\\uff4e", "ad\\u200bmin", "ROOT", "Sup\\u00adport"):
                    with self.assertRaises(Taken, msg=sneaky):
                        r.register(sneaky)

            def test_invalid_handles(self):
                r = Registry()
                for bad in ("ab", "9lives", "bad name!", "", "\\u044f\\u043d"):
                    with self.assertRaises(Invalid, msg=bad):
                        r.register(bad)

            def test_long_non_latin_handle_is_fine(self):
                r = Registry()
                self.assertEqual(r.register("\\u0410\\u043b\\u0435\\u043a\\u0441\\u0430\\u043d\\u0434\\u0440\\u0438\\u044f"), "\\u0430\\u043b\\u0435\\u043a\\u0441\\u0430\\u043d\\u0434\\u0440\\u0438\\u044f")

            def test_lookup_returns_the_handle_as_typed(self):
                r = Registry()
                r.register("  Anna Maria ")
                self.assertEqual(r.lookup("ANNA MARIA"), "Anna Maria")
                self.assertIsNone(r.lookup("nobody"))


        class Rename(unittest.TestCase):
            def test_rename_changes_display_and_frees_the_old_name(self):
                r = Registry()
                r.register("Anna")
                self.assertEqual(r.rename("Anna", "Bea"), "bea")
                self.assertIsNone(r.lookup("anna"))
                self.assertEqual(r.lookup("BEA"), "Bea")
                self.assertEqual(r.register("Anna"), "anna")

            def test_capitalisation_change_is_allowed(self):
                r = Registry()
                r.register("Anna")
                self.assertEqual(r.rename("Anna", "ANNA"), "anna")
                self.assertEqual(r.lookup("anna"), "ANNA")

            def test_failed_renames_change_nothing(self):
                r = Registry()
                r.register("Anna")
                r.register("Bea")
                with self.assertRaises(Taken):
                    r.rename("Anna", "bea")
                with self.assertRaises(Taken):
                    r.rename("Anna", "Admin")
                with self.assertRaises(Invalid):
                    r.rename("Anna", "x")
                with self.assertRaises(KeyError):
                    r.rename("Ghost", "Gertrude")
                self.assertEqual(r.lookup("anna"), "Anna")
                self.assertEqual(prefix_search(r, "a"), ["Anna"])


        class Search(unittest.TestCase):
            def setUp(self):
                self.r = Registry()
                for h in ("Zoe", "zo\\u00eb", "Jos\\u00e9", "Joshua", "jo_ann", "ZED", "Zora"):
                    self.r.register(h)

            def test_ordered_by_canonical_form(self):
                self.assertEqual(prefix_search(self.r, "zo"), ["Zoe", "Zora", "zo\\u00eb"])
                self.assertEqual(prefix_search(self.r, "Z"), ["ZED", "Zoe", "Zora", "zo\\u00eb"])

            def test_limit(self):
                self.assertEqual(prefix_search(self.r, "z", limit=2), ["ZED", "Zoe"])

            def test_query_is_canonicalised(self):
                self.assertEqual(prefix_search(self.r, "JOS"), ["Joshua", "Jos\\u00e9"])
                self.assertEqual(prefix_search(self.r, "Jose\\u0301"), ["Jos\\u00e9"])
                self.assertEqual(prefix_search(self.r, "  jo  "), ["jo_ann", "Joshua", "Jos\\u00e9"])
                self.assertEqual(prefix_search(self.r, "jo_a"), ["jo_ann"])

            def test_blank_query(self):
                self.assertEqual(prefix_search(self.r, ""), [])
                self.assertEqual(prefix_search(self.r, "   "), [])

            def test_stored_decomposed_handle_is_found_by_composed_query(self):
                r = Registry()
                r.register("Jose\\u0301")
                self.assertEqual(prefix_search(r, "jos\\u00e9"), ["Jose\\u0301"])

            def test_rename_moves_search_results(self):
                r = Registry()
                r.register("Anna")
                r.register("Anselm")
                r.rename("Anna", "Bea")
                self.assertEqual(prefix_search(r, "an"), ["Anselm"])
                self.assertEqual(prefix_search(r, "b"), ["Bea"])


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _a_prompts():
    p = {}
    p["lower"] = (
        "Two people on the service now have \"Straße\" and \"STRASSE\" as handles, and the second one was supposed to be "
        "rejected as a clash. The README says canonical forms are case *folded*. Please fix the canonicalisation."
    )
    p["nfc"] = (
        "Security report from support: someone registered the handle \"ａｄｍｉｎ\" (full-width letters) and now shows up in chat "
        "looking like a staff member. `admin` is reserved, but the check apparently does not see through compatibility "
        "characters. Find out why and fix it so that all such look-alikes are treated like the plain name."
    )
    p["bytes"] = (
        "Our Russian-speaking users cannot register handles longer than about ten letters (\"Александрия\" is rejected as "
        "too long), while two-letter ones like \"ян\" go through even though the minimum is three. Looks like a "
        "units mix-up somewhere in the validity check."
    )
    p["cf"] = (
        "Abuse report: a user got the name \"admin\" back after we reserved it, by typing it with a zero-width space (U+200B) in the "
        "middle. The registry thinks it is a different handle. The README says invisible format characters are "
        "ignored in the canonical form. Make that true."
    )
    p["search-nfd"] = (
        "Searching for \"José\" in the user directory finds nothing when I type it on my Mac, although José is clearly "
        "registered (his own client sends the composed form). Searching for \"jos\" works. It looks like a difference "
        "between how queries and stored handles are treated. Please find it."
    )
    p["rename-stale"] = lambda c: (
        "After a user renames themselves, directory search blows up. This is the traceback from our test harness:\n\n```\n"
        + "\n".join(c.bad_run("from handles.registry import Registry\nfrom handles.search import prefix_search\n"
                            "r = Registry()\nr.register('Anna')\nr.rename('Anna', 'Bea')\nprint(prefix_search(r, 'a'))\n").splitlines())
        + "\n```\n\nThe rename itself looks fine (lookup works). Please fix the root cause."
    )
    p["rename-case"] = (
        "A user wants to change \"anna\" to \"Anna\" in their profile and is told the handle is taken (by themselves). "
        "Changing the capitalisation of your own handle is supposed to work. Rename to a really different name is fine."
    )
    p["two"] = (
        "Two directory problems that arrived together. (1) The fancy full-width \"ＡＤＭＩＮ\" can still be registered although "
        "`admin` is reserved. (2) After renaming a user, searching crashes. I do not know if they are related; the visible "
        "tests pass. Please fix everything that is wrong."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "handles/__init__.py": '"""Handle registry."""\n', "handles/canon.py": A_CANON,
            "handles/search.py": A_SEARCH, "handles/registry.py": A_REGISTRY}
    c, r, s = "handles/canon.py", "handles/registry.py", "handles/search.py"
    nfc = ('    s = unicodedata.normalize("NFKC", handle)', '    s = unicodedata.normalize("NFC", handle)')
    stale = ("        del self._by_canon[oc]\n        self.index.remove(oc)\n        self._by_canon[nc] = new.strip()\n        self.index.add(nc)\n",
             "        del self._by_canon[oc]\n        self._by_canon[nc] = new.strip()\n")
    bugs = [
        Bug("lower-instead-of-casefold", 2, {c: [("    s = s.casefold()", "    s = s.lower()")]}, P["lower"]),
        Bug("nfc-misses-compat-forms", 3, {c: [nfc]}, P["nfc"]),
        Bug("length-in-bytes", 2, {c: [("    if not (MIN_LEN <= len(canon) <= MAX_LEN):", '    if not (MIN_LEN <= len(canon.encode("utf-8")) <= MAX_LEN):')]}, P["bytes"]),
        Bug("format-chars-kept", 3, {c: [('    s = "".join(ch for ch in s if unicodedata.category(ch) != "Cf")\n', "")]}, P["cf"]),
        Bug("search-query-not-normalised", 3, {s: [("    q = canonical(query)", "    q = query.strip().casefold()")]}, P["search-nfd"]),
        Bug("rename-index-stale", 4, {r: [stale]}, P["rename-stale"]),
        Bug("rename-self-collision", 3, {r: [("        if nc in RESERVED or (nc != oc and nc in self._by_canon):", "        if nc in RESERVED or nc in self._by_canon:")]}, P["rename-case"]),
        Bug("compat-and-stale-index", 5, {c: [nfc], r: [stale]}, P["two"]),
    ]
    return Base("handles", "python", good, A_VISIBLE, A_HIDDEN, bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base B (javascript): text helpers of a notes app: accent-insensitive fold, slugs, truncation, highlighting.
# ------------------------------------------------------------------------------------------------------------------

B_README = dd('''
    # notekit

    Text helpers behind the search box and the URLs of a notes app (CommonJS, no dependencies).

    * `fold(s)`: accent- and case-insensitive form: decompose (NFD), drop **every** combining mark (`\\p{M}`), lower
      case. `fold('Crème Brûlée') === 'creme brulee'`.
    * `slugify(title, max = 40)`: fold the title, turn every run of characters other than `a-z` and `0-9` into one
      `-`, strip leading and trailing `-`, cut to `max` characters (and strip a trailing `-` again). If nothing is
      left the slug is `untitled`.
    * `uniqueSlug(title, taken, max = 40)`: the slug if it is not in the Set `taken`, otherwise the slug followed by
      `-2`, `-3`, ... (the first free one). The result never exceeds `max` characters: the base is cut to make room
      for the suffix, and a `-` left at the end of the cut base is stripped before the suffix is added.
    * `truncate(text, max)`: `text` unchanged when it has at most `max` **code points**; otherwise its first
      `max - 1` code points followed by `…` (so the result has `max` code points). Never splits a character.
    * `compareTitles(a, b)`: ordering for note lists: by `fold`, ties broken by plain code unit order.
    * `highlight(text, query)`: wraps every non-overlapping, left-to-right occurrence of `fold(query)` in the
      folded text with `[[` and `]]`, but returns the *original* characters; a match includes the combining marks
      that follow its last letter. An empty query returns `text` unchanged.
''')

B_FOLD = dd('''
    'use strict';

    function fold(s) {
      return s.normalize('NFD').replace(/\\p{M}/gu, '').toLowerCase();
    }

    module.exports = { fold };
''')

B_SLUG = dd('''
    'use strict';
    const { fold } = require('./fold');

    const MAX_SLUG = 40;

    function slugify(title, max = MAX_SLUG) {
      let s = fold(title).replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
      if (s.length > max) s = s.slice(0, max).replace(/-+$/g, '');
      return s || 'untitled';
    }

    function uniqueSlug(title, taken, max = MAX_SLUG) {
      const base = slugify(title, max);
      let candidate = base;
      for (let n = 2; taken.has(candidate); n++) {
        const suffix = `-${n}`;
        candidate = base.slice(0, max - suffix.length).replace(/-+$/g, '') + suffix;
      }
      return candidate;
    }

    module.exports = { slugify, uniqueSlug, MAX_SLUG };
''')

B_TEXT = dd('''
    'use strict';
    const { fold } = require('./fold');

    function truncate(text, max) {
      const cps = Array.from(text);
      if (cps.length <= max) return text;
      return cps.slice(0, max - 1).join('') + '\\u2026';
    }

    function compareTitles(a, b) {
      const fa = fold(a);
      const fb = fold(b);
      if (fa !== fb) return fa < fb ? -1 : 1;
      return a < b ? -1 : a > b ? 1 : 0;
    }

    module.exports = { truncate, compareTitles };
''')

B_HIGHLIGHT = dd('''
    'use strict';
    const { fold } = require('./fold');

    function highlight(text, query) {
      const q = fold(query);
      if (q === '') return text;
      const cps = Array.from(text);
      // the folded text, remembering which code point of `text` every folded unit came from
      let folded = '';
      const origin = [];
      cps.forEach((cp, i) => {
        const f = fold(cp);
        for (let k = 0; k < f.length; k++) origin.push(i);
        folded += f;
      });
      let out = '';
      let copied = 0;
      let from = 0;
      for (;;) {
        const at = folded.indexOf(q, from);
        if (at === -1) break;
        const first = origin[at];
        let last = origin[at + q.length - 1];
        while (last + 1 < cps.length && /\\p{M}/u.test(cps[last + 1])) last++;
        out += cps.slice(copied, first).join('') + '[[' + cps.slice(first, last + 1).join('') + ']]';
        copied = last + 1;
        from = at + q.length;
      }
      return out + cps.slice(copied).join('');
    }

    module.exports = { highlight };
''')

B_HIGHLIGHT_BAD = dd('''
    'use strict';
    const { fold } = require('./fold');

    function highlight(text, query) {
      const q = fold(query);
      if (q === '') return text;
      const folded = fold(text);
      let out = '';
      let copied = 0;
      let from = 0;
      for (;;) {
        const at = folded.indexOf(q, from);
        if (at === -1) break;
        out += text.slice(copied, at) + '[[' + text.slice(at, at + q.length) + ']]';
        copied = at + q.length;
        from = at + q.length;
      }
      return out + text.slice(copied);
    }

    module.exports = { highlight };
''')

B_VISIBLE = {
    "test/notekit.test.js": dd('''
        const test = require('node:test');
        const assert = require('node:assert');
        const { fold } = require('../src/fold');
        const { slugify } = require('../src/slug');
        const { truncate } = require('../src/text');
        const { highlight } = require('../src/highlight');

        test('fold', () => {
          assert.strictEqual(fold('Cr\\u00e8me Br\\u00fbl\\u00e9e'), 'creme brulee');
        });

        test('slugify', () => {
          assert.strictEqual(slugify('Hello, World!'), 'hello-world');
        });

        test('truncate and highlight on plain text', () => {
          assert.strictEqual(truncate('hello world', 5), 'hell\\u2026');
          assert.strictEqual(highlight('Hello hello', 'hel'), '[[Hel]]lo [[hel]]lo');
        });
    '''),
}

B_HIDDEN = {
    "test/hidden_notekit.test.js": dd('''
        const test = require('node:test');
        const assert = require('node:assert');
        const { fold } = require('../src/fold');
        const { slugify, uniqueSlug } = require('../src/slug');
        const { truncate, compareTitles } = require('../src/text');
        const { highlight } = require('../src/highlight');

        test('fold removes all combining marks, whatever the script', () => {
          assert.strictEqual(fold('Cr\\u00e8me Br\\u00fbl\\u00e9e'), 'creme brulee');
          assert.strictEqual(fold('e\\u0301'), 'e');
          assert.strictEqual(fold('\\u0130stanbul'), 'istanbul');
          assert.strictEqual(fold('\\u0645\\u064f\\u062d\\u064e\\u0645\\u0651\\u064e\\u062f'), '\\u0645\\u062d\\u0645\\u062f');
          assert.strictEqual(fold('\\u05e9\\u05b8\\u05c1\\u05dc\\u05d5\\u05b9\\u05dd'), '\\u05e9\\u05dc\\u05d5\\u05dd');
          assert.strictEqual(fold('ABC'), 'abc');
        });

        test('slugify', () => {
          assert.strictEqual(slugify('Hello, World!'), 'hello-world');
          assert.strictEqual(slugify('  Cr\\u00e8me   Br\\u00fbl\\u00e9e -- 2024 '), 'creme-brulee-2024');
          assert.strictEqual(slugify('a'.repeat(50)), 'a'.repeat(40));
          assert.strictEqual(slugify('a'.repeat(39) + ' bbb'), 'a'.repeat(39));
          assert.strictEqual(slugify('one two three', 7), 'one-two');
        });

        test('slugify never returns an empty slug', () => {
          assert.strictEqual(slugify('\\u041f\\u0440\\u0438\\u0432\\u0435\\u0442'), 'untitled');
          assert.strictEqual(slugify('  --  '), 'untitled');
          assert.strictEqual(slugify(''), 'untitled');
          assert.strictEqual(slugify('\\ud83d\\ude00'), 'untitled');
        });

        test('uniqueSlug', () => {
          assert.strictEqual(uniqueSlug('Hello World', new Set()), 'hello-world');
          assert.strictEqual(uniqueSlug('Hello World', new Set(['hello-world'])), 'hello-world-2');
          assert.strictEqual(uniqueSlug('Hello World', new Set(['hello-world', 'hello-world-2', 'hello-world-3'])), 'hello-world-4');
        });

        test('uniqueSlug keeps within the maximum length', () => {
          const long = 'a'.repeat(40);
          const got = uniqueSlug('a'.repeat(60), new Set([long]));
          assert.strictEqual(got, 'a'.repeat(38) + '-2');
          assert.strictEqual(got.length, 40);
          const taken = new Set([long, 'a'.repeat(38) + '-2']);
          assert.strictEqual(uniqueSlug('a'.repeat(60), taken), 'a'.repeat(38) + '-3');
          assert.strictEqual(uniqueSlug('abcdefg hijk', new Set(['abcdefg-hi']), 10), 'abcdefg-2');
          assert.strictEqual(uniqueSlug('abcdefgh ijkl', new Set(['abcdefgh']), 9), 'abcdefg-2');
        });

        test('truncate counts code points', () => {
          assert.strictEqual(truncate('hello', 5), 'hello');
          assert.strictEqual(truncate('hello world', 5), 'hell\\u2026');
          assert.strictEqual(truncate('abc', 1), '\\u2026');
          const face = '\\ud83d\\ude00';
          assert.strictEqual(truncate(face.repeat(5), 5), face.repeat(5));
          assert.strictEqual(truncate(face.repeat(6), 5), face.repeat(4) + '\\u2026');
          assert.strictEqual(truncate('ab' + face + 'cd', 4), 'ab' + face + '\\u2026');
          assert.strictEqual(truncate('', 3), '');
        });

        test('compareTitles orders by folded text, then by code units', () => {
          const titles = ['banana', 'Apple', '\\u00c9cole', 'cherry', 'apple', 'Banana', 'dune'];
          assert.deepStrictEqual([...titles].sort(compareTitles), ['Apple', 'apple', 'Banana', 'banana', 'cherry', 'dune', '\\u00c9cole']);
          assert.strictEqual(compareTitles('same', 'same'), 0);
          assert.ok(compareTitles('\\u00e9a', 'eb') < 0);
        });

        test('highlight on composed text', () => {
          assert.strictEqual(highlight('Cr\\u00e8me br\\u00fbl\\u00e9e', 'brule'), 'Cr\\u00e8me [[br\\u00fbl\\u00e9]]e');
          assert.strictEqual(highlight('aXa \\u00e0', 'a'), '[[a]]X[[a]] [[\\u00e0]]');
          assert.strictEqual(highlight('\\u00c9COLE \\u00e9cole', 'ecole'), '[[\\u00c9COLE]] [[\\u00e9cole]]');
          assert.strictEqual(highlight('nothing here', 'zzz'), 'nothing here');
          assert.strictEqual(highlight('keep', ''), 'keep');
        });

        test('highlight on decomposed text keeps the marks and the right positions', () => {
          const text = 'Cre\\u0300me bru\\u0302le\\u0301e';
          assert.strictEqual(highlight(text, 'brule'), 'Cre\\u0300me [[bru\\u0302le\\u0301]]e');
          assert.strictEqual(highlight('e\\u0301e\\u0301e', 'ee'), '[[e\\u0301e\\u0301]]e');
          assert.strictEqual(highlight('\\ud83d\\ude00 caf\\u00e9', 'cafe'), '\\ud83d\\ude00 [[caf\\u00e9]]');
        });
    '''),
}


def _b_prompts():
    p = {}
    p["truncate-units"] = (
        "Note previews are cut in the middle of emoji (we see a replacement character at the end of some previews) and "
        "short emoji-only notes get an ellipsis even though they are within the limit. The limit is in characters. "
        "`truncate` in `src/text.js` is what the preview code uses."
    )
    p["marks-range"] = (
        "Accent-insensitive search works for French and Turkish notes but not for Arabic and Hebrew ones: searching "
        "محمد does not find notes that contain the vowelled spelling مُحَمَّد. The README says all combining marks are "
        "dropped by `fold`."
    )
    p["slug-empty"] = (
        "Notes whose titles contain no Latin letters or digits (\"Привет\", \"😀\") get an empty slug and their URL ends up as "
        "`/notes/`, which 404s. Please make slug generation robust as documented."
    )
    p["title-order"] = (
        "The note list sorts \"École\" after \"zebra\". Lists should ignore accents and case when ordering, as in the README; "
        "ties are broken by the plain order of the text."
    )
    p["highlight"] = (
        "Search hit highlighting is shifted or garbled for notes that were pasted from a Mac (accents stored as base "
        "letter + combining mark). For \"Crème brûlée\" and the query \"brule\" the [[ ]] markers surround the wrong "
        "part. Precomposed text is fine. Fix `highlight`."
    )
    p["suffix-length"] = (
        "Our database column for slugs is 40 characters and the importer now fails with \"value too long\" for some "
        "notes with long titles that collide with an existing slug. The suffix (-2, -3) seems to push the slug over the limit."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "src/fold.js": B_FOLD, "src/slug.js": B_SLUG, "src/text.js": B_TEXT, "src/highlight.js": B_HIGHLIGHT,
            "package.json": '{\n  "name": "notekit",\n  "version": "1.0.0",\n  "private": true\n}\n'}
    bugs = [
        Bug("slug-empty-allowed", 1, {"src/slug.js": [("  return s || 'untitled';", "  return s;")]}, P["slug-empty"]),
        Bug("truncate-code-units", 2, {"src/text.js": [("  const cps = Array.from(text);\n  if (cps.length <= max) return text;\n  return cps.slice(0, max - 1).join('') + '\\u2026';",
                                                         "  if (text.length <= max) return text;\n  return text.slice(0, max - 1) + '\\u2026';")]}, P["truncate-units"]),
        Bug("title-order-raw", 2, {"src/text.js": [("  const fa = fold(a);\n  const fb = fold(b);\n  if (fa !== fb) return fa < fb ? -1 : 1;\n  return a < b ? -1 : a > b ? 1 : 0;",
                                                     "  return a < b ? -1 : a > b ? 1 : 0;")]}, P["title-order"]),
        Bug("marks-limited-range", 3, {"src/fold.js": [("replace(/\\p{M}/gu, '')", "replace(/[\\u0300-\\u036f]/g, '')")]}, P["marks-range"]),
        Bug("unique-suffix-overflows", 3, {"src/slug.js": [("    candidate = base.slice(0, max - suffix.length).replace(/-+$/g, '') + suffix;", "    candidate = base + suffix;")]}, P["suffix-length"]),
        Bug("highlight-folded-indexes", 4, {"src/highlight.js": B_HIGHLIGHT_BAD}, P["highlight"]),
    ]
    return Base("notekit", "javascript", good, B_VISIBLE, B_HIDDEN, bugs)


@family("fix-hand-unicode-fold", category="fix", lang="python", kind="fix", n=14,
        summary="unicode normalisation, case folding and code point handling: a handle registry (python), text helpers (js)")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b()])
