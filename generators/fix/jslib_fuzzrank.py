"""Fuzzy scoring and ranking for a command palette (javascript): bugs injected into a matcher library."""
from fx import Lib, dd
from generators.fix._lang2 import JS_VERIFY, PACKAGE_JSON, register_libs

README = dd(r'''
    # fuzzrank

    Scores and ranks entries of a command palette against what the user has typed. CommonJS:
    `const { score, positions, highlight, rank } = require('./src/match')`, `const { isBoundary } = require('./src/boundary')`.

    ## Matching

    The query is compared without its whitespace (`'o f'` is `'of'`). Matching ignores letter case and is a *subsequence*
    match: every query character must occur in the text, in order. The positions are chosen greedily from the left: the
    first query character takes its first occurrence, each next one the first occurrence after the previous one.

    * `positions(query, text)` returns the array of matched text indexes, `[]` for an empty query, or `null` if the text
      does not match.
    * `isBoundary(text, i)` (in `src/boundary.js`) says whether index `i` (`i >= 1`) starts a word: the previous character
      is whitespace, `-`, `_`, `/` or `.`, or the previous character is a lower-case letter `a-z` and the character at `i` is
      an upper-case letter `A-Z`.

    ## `score(query, text)`

    `null` when `text` does not match; `0` for an empty query. Otherwise the sum of

    * per matched character: `+10`; `+1` more when the text character has exactly the case of the query character;
    * `+15` when it is at index 0, else `+10` when `isBoundary` holds there;
    * for the first matched character: `-min(index, 10)` (characters skipped at the start); for every later one, `+8` when it
      directly follows the previous matched character, else `-min(gap, 5)` where `gap` is the number of skipped characters
      in between;

    plus `+25` when the lower-cased text starts with the lower-cased query, minus `floor(text.length / 8)`.

    ## `rank(query, items, opts = {})`

    Returns the items that match, best first. `opts.key` says where the text comes from: a function, or a property name;
    by default the item itself is the text. The text is `String(...)` of that value. An empty query (nothing but
    whitespace) keeps every item, in the original order. Otherwise items are sorted by score, highest first; ties are broken
    by shorter text, then by the lower-cased text in plain `<` order, then by original position. `opts.limit`, a positive
    integer, keeps only the first items of the result.

    ## `highlight(query, text, open = '[', close = ']')`

    Returns `text` with every run of consecutive matched characters wrapped in `open` and `close`, or `null` when it does not
    match. An empty query returns the text unchanged.
''')

BOUNDARY = dd(r'''
    'use strict';

    function isBoundary(text, i) {
      const prev = text[i - 1];
      if (/[\s\-_/.]/.test(prev)) return true;
      return /[a-z]/.test(prev) && /[A-Z]/.test(text[i]);
    }

    module.exports = { isBoundary };
''')

MATCH = dd(r'''
    'use strict';

    const { isBoundary } = require('./boundary');

    function strip(query) {
      return query.replace(/\s+/g, '');
    }

    function positions(query, text) {
      const q = strip(query).toLowerCase();
      const t = text.toLowerCase();
      const out = [];
      let from = 0;
      for (const ch of q) {
        const at = t.indexOf(ch, from);
        if (at < 0) return null;
        out.push(at);
        from = at + 1;
      }
      return out;
    }

    function score(query, text) {
      const pos = positions(query, text);
      if (pos === null) return null;
      const q = strip(query);
      if (q === '') return 0;
      let total = 0;
      pos.forEach((at, k) => {
        total += 10;
        if (text[at] === q[k]) total += 1;
        if (at === 0) total += 15;
        else if (isBoundary(text, at)) total += 10;
        if (k === 0) {
          total -= Math.min(at, 10);
        } else {
          const gap = at - pos[k - 1] - 1;
          total += gap === 0 ? 8 : -Math.min(gap, 5);
        }
      });
      if (text.toLowerCase().startsWith(q.toLowerCase())) total += 25;
      return total - Math.floor(text.length / 8);
    }

    function highlight(query, text, open = '[', close = ']') {
      const pos = positions(query, text);
      if (pos === null) return null;
      const hit = new Set(pos);
      let out = '';
      let inside = false;
      for (let i = 0; i < text.length; i++) {
        if (hit.has(i) && !inside) {
          out += open;
          inside = true;
        } else if (!hit.has(i) && inside) {
          out += close;
          inside = false;
        }
        out += text[i];
      }
      return inside ? out + close : out;
    }

    function rank(query, items, opts = {}) {
      const key = opts.key;
      const textOf = typeof key === 'function' ? key : key ? (x) => x[key] : (x) => x;
      let result;
      if (strip(query) === '') {
        result = items.slice();
      } else {
        const scored = [];
        items.forEach((item, index) => {
          const text = String(textOf(item));
          const s = score(query, text);
          if (s !== null) scored.push({ item, index, text, lower: text.toLowerCase(), s });
        });
        scored.sort((a, b) => b.s - a.s || a.text.length - b.text.length || (a.lower < b.lower ? -1 : a.lower > b.lower ? 1 : 0) || a.index - b.index);
        result = scored.map((x) => x.item);
      }
      return opts.limit > 0 ? result.slice(0, opts.limit) : result;
    }

    module.exports = { positions, score, highlight, rank };
''')

VISIBLE = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { score, rank } = require('../src/match');

    test('no match is null', () => {
      assert.equal(score('xyz', 'abc'), null);
      assert.equal(score('ab', 'ba'), null);
    });

    test('rank puts the better match first', () => {
      assert.deepEqual(rank('fil', ['Find in Files', 'File: New']), ['File: New', 'Find in Files']);
    });
''')

HIDDEN = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { positions, score, highlight, rank } = require('../src/match');
    const { isBoundary } = require('../src/boundary');

    const ITEMS = ['Open File', 'Open Folder', 'Close File', 'Save File As...', 'Save All', 'Find in Files', 'Toggle Fullscreen',
      'Format Document', 'Go to File...', 'File: New', 'Reopen Closed Editor', 'Fold All'];

    test('isBoundary', () => {
      assert.equal(isBoundary('a b', 2), true);
      assert.equal(isBoundary('a-b', 2), true);
      assert.equal(isBoundary('a_b', 2), true);
      assert.equal(isBoundary('a/b', 2), true);
      assert.equal(isBoundary('a.b', 2), true);
      assert.equal(isBoundary('a\tb', 2), true);
      assert.equal(isBoundary('aB', 1), true);
      assert.equal(isBoundary('ab', 1), false);
      assert.equal(isBoundary('AB', 1), false);
      assert.equal(isBoundary('Ab', 1), false);
      assert.equal(isBoundary('1B', 1), false);
      assert.equal(isBoundary('a1', 1), false);
      assert.equal(isBoundary('zA', 1), true);
      assert.equal(isBoundary('aZ', 1), true);
      assert.equal(isBoundary('a+b', 2), false);
    });

    test('positions are greedy from the left', () => {
      assert.deepEqual(positions('abc', 'aXbXc'), [0, 2, 4]);
      assert.deepEqual(positions('ab', 'xabab'), [1, 2]);
      assert.deepEqual(positions('aa', 'banana'), [1, 3]);
      assert.deepEqual(positions('OF', 'open file'), [0, 5]);
      assert.deepEqual(positions('o f', 'Open File'), [0, 5]);
      assert.deepEqual(positions('', 'abc'), []);
      assert.deepEqual(positions('  ', 'abc'), []);
      assert.equal(positions('abc', 'ab'), null);
      assert.equal(positions('ba', 'ab'), null);
      assert.equal(positions('aaa', 'aa'), null);
    });

    test('score: documented values', () => {
      const cases = [
        ['of', 'Open File', 40], ['OF', 'Open File', 42], ['of', 'open file', 42], ['of', 'Overflow', 32],
        ['fb', 'foo_bar', 44], ['fb', 'fooBar', 44], ['fb', 'foobar', 35], ['fb', 'Foo Bar Baz', 41],
        ['abc', 'abc', 89], ['abc', 'xabc', 48], ['abc', 'a-b-c', 66], ['abc', 'aXbXc', 46], ['abc', 'azzzzzzzbc', 50],
        ['save', 'Save File As...', 106], ['sv', 'Save', 35], ['open file', 'Open File', 157], ['o f', 'Open File', 40],
        ['fileopen', 'File Open', 157], ['src/a', 'src/app.js', 136], ['ttt', 'TheTestTool', 51], ['tt', 'the-test', 43],
        ['a', 'a', 51], ['a', 'A', 50], ['A', 'a', 50],
      ];
      for (const [q, t, want] of cases) assert.equal(score(q, t), want, `${q} in ${t}`);
    });

    test('score: leading skips and gaps are capped', () => {
      assert.equal(score('o', 'xxxxxxxxxxxxo'), 0);
      assert.equal(score('o', 'xxxxxxxxxxxxxxxxxxxxxxxxo'), -2);
      assert.equal(score('o', 'xo'), 10);
      assert.equal(score('o', 'xxxxxxxxxxo'), 0);
      assert.equal(score('ab', 'azzzzzzzzzzzzb'), 31);
      assert.equal(score('ab', 'azb'), 36);
      assert.equal(score('ab', 'azzzzzb'), 26 + 10 + 1 - 5 - 0);
      assert.equal(score('ab', 'azzzzb'), 26 + 10 + 1 - 4 - 0);
    });

    test('score: nulls and empties', () => {
      assert.equal(score('xyz', 'abc'), null);
      assert.equal(score('ab', 'ba'), null);
      assert.equal(score('', 'anything'), 0);
      assert.equal(score('  ', 'x'), 0);
      assert.equal(score('', ''), 0);
      assert.equal(score('a', ''), null);
    });

    test('score: the prefix bonus and the length penalty', () => {
      assert.ok(score('ope', 'open') > score('ope', 'xopen'));
      assert.equal(score('a', 'abcdefg'), 10 + 1 + 15 + 25);
      assert.equal(score('a', 'abcdefgh'), 10 + 1 + 15 + 25 - 1);
      assert.equal(score('a', 'abcdefghijklmno'), 10 + 1 + 15 + 25 - 1);
      assert.equal(score('a', 'abcdefghijklmnop'), 10 + 1 + 15 + 25 - 2);
      assert.equal(score('a', 'Abcdefg'), 10 + 15 + 25);
    });

    test('rank: palette examples', () => {
      assert.deepEqual(rank('fil', ITEMS), ['File: New', 'Open File', 'Save File As...', 'Close File', 'Go to File...', 'Find in Files']);
      assert.deepEqual(rank('of', ITEMS), ['Open File', 'Open Folder', 'Close File', 'Go to File...', 'Toggle Fullscreen']);
      assert.deepEqual(rank('sa', ITEMS), ['Save All', 'Save File As...']);
      assert.deepEqual(rank('fo', ITEMS), ['Fold All', 'Format Document', 'Open Folder']);
      assert.deepEqual(rank('fa', ITEMS), ['Fold All', 'Format Document', 'Save File As...']);
      assert.deepEqual(rank('f n', ITEMS), ['File: New', 'Find in Files', 'Format Document', 'Toggle Fullscreen']);
      assert.deepEqual(rank('Open', ITEMS), ['Open File', 'Open Folder', 'Reopen Closed Editor']);
      assert.deepEqual(rank('xyz', ITEMS), []);
    });

    test('rank: empty query keeps everything in order, limit applies', () => {
      assert.deepEqual(rank('', ITEMS, { limit: 3 }), ['Open File', 'Open Folder', 'Close File']);
      assert.deepEqual(rank('   ', ITEMS), ITEMS);
      assert.notEqual(rank('', ITEMS), ITEMS);
      assert.deepEqual(rank('fil', ITEMS, { limit: 2 }), ['File: New', 'Open File']);
      assert.deepEqual(rank('fil', ITEMS, { limit: 100 }).length, 6);
      assert.deepEqual(rank('fil', ITEMS, { limit: 0 }).length, 6);
      assert.deepEqual(rank('fil', ITEMS, { limit: 1 }), ['File: New']);
    });

    test('rank: ties by length, then text, then position', () => {
      assert.deepEqual(rank('x', ['bx', 'ax']), ['ax', 'bx']);
      assert.deepEqual(rank('x', ['ax', 'bx']), ['ax', 'bx']);
      assert.deepEqual(rank('x', ['bx', 'AX', 'ax']), ['ax', 'bx', 'AX']);
      assert.deepEqual(rank('x', ['Ax', 'ax']), ['Ax', 'ax']);
      assert.deepEqual(rank('x', ['ax', 'Ax']), ['ax', 'Ax']);
      assert.deepEqual(rank('x', ['aaax', 'bx']), ['bx', 'aaax']);
      assert.deepEqual(rank('x', ['Bx', 'ax']), ['ax', 'Bx']);
    });

    test('rank: keys', () => {
      const cmds = [{ id: 1, title: 'Open File' }, { id: 2, title: 'Close File' }, { id: 3, title: 'Save' }];
      assert.deepEqual(rank('file', cmds, { key: 'title' }).map((c) => c.id), [1, 2]);
      assert.deepEqual(rank('file', cmds, { key: (c) => c.title.toUpperCase() }).map((c) => c.id), [1, 2]);
      assert.deepEqual(rank('7', [17, 70, 5]), [70, 17]);
      assert.equal(rank('file', cmds, { key: 'title' })[0], cmds[0]);
    });

    test('rank does not modify its input', () => {
      const items = ['b', 'a', 'ab'];
      rank('a', items);
      assert.deepEqual(items, ['b', 'a', 'ab']);
    });

    test('highlight', () => {
      assert.equal(highlight('of', 'Open File'), '[O]pen [F]ile');
      assert.equal(highlight('fil', 'Find in Files'), '[Fi]nd in Fi[l]es');
      assert.equal(highlight('abc', 'abc'), '[abc]');
      assert.equal(highlight('abc', 'aXbXc'), '[a]X[b]X[c]');
      assert.equal(highlight('sv', 'Save'), '[S]a[v]e');
      assert.equal(highlight('fb', 'fooBar'), '[f]oo[B]ar');
      assert.equal(highlight('o f', 'Open File'), '[O]pen [F]ile');
      assert.equal(highlight('fo', 'Format Document'), '[Fo]rmat Document');
      assert.equal(highlight('ee', 'Reopen Closed Editor'), 'R[e]op[e]n Closed Editor');
      assert.equal(highlight('ar', 'bar'), 'b[ar]');
      assert.equal(highlight('b', 'bar'), '[b]ar');
    });

    test('highlight: custom marks, no match and empty query', () => {
      assert.equal(highlight('of', 'Open File', '<b>', '</b>'), '<b>O</b>pen <b>F</b>ile');
      assert.equal(highlight('xyz', 'abc'), null);
      assert.equal(highlight('', 'abc'), 'abc');
      assert.equal(highlight('c', 'abc', '(', ')'), 'ab(c)');
    });
''')

LIB = Lib(
    name="fuzzrank", lang="javascript", title="the fuzzrank matcher",
    blurb="The command palette of the editor ranks its entries with fuzzrank as the user types.",
    files={"package.json": PACKAGE_JSON % "fuzzrank", "src/boundary.js": BOUNDARY, "src/match.js": MATCH, "README.md": README, ".gitignore": "node_modules/\n"},
    visible_tests={"test/basic.test.js": VISIBLE},
    hidden_tests={"test/full.test.js": HIDDEN},
    mutate=["src/match.js", "src/boundary.js"], difficulty=3, tags=["search", "ranking", "fuzzy"],
    verify=JS_VERIFY,
    probe_import="const { positions, score, highlight, rank } = require('./src/match');\nconst { isBoundary } = require('./src/boundary');",
    probes=[
        "isBoundary('aB', 1)",
        "isBoundary('AB', 1)",
        "isBoundary('a-b', 2)",
        "positions('aa', 'banana')",
        "positions('o f', 'Open File')",
        "score('of', 'Open File')",
        "score('OF', 'Open File')",
        "score('fb', 'foo_bar')",
        "score('fb', 'foobar')",
        "score('abc', 'azzzzzzzbc')",
        "score('o', 'xxxxxxxxxxxxxxxxxxxxxxxxo')",
        "score('save', 'Save File As...')",
        "score('', 'anything')",
        "score('ab', 'ba')",
        "score('a', 'abcdefgh')",
        "rank('fil', ['Open File', 'Open Folder', 'Close File', 'Save File As...', 'Save All', 'Find in Files', 'File: New', 'Fold All'])",
        "rank('sa', ['Open File', 'Open Folder', 'Close File', 'Save File As...', 'Save All', 'Find in Files', 'File: New', 'Fold All'])",
        "rank('fo', ['Open File', 'Open Folder', 'Close File', 'Save File As...', 'Save All', 'Find in Files', 'File: New', 'Fold All'])",
        "rank('', ['Open File', 'Open Folder', 'Close File', 'Save File As...', 'Save All', 'Find in Files', 'File: New', 'Fold All'], { limit: 3 })",
        "rank('fil', ['Open File', 'Open Folder', 'Close File', 'Save File As...', 'Save All', 'Find in Files', 'File: New', 'Fold All'], { limit: 2 })",
        "rank('x', ['bx', 'ax'])",
        "highlight('of', 'Open File')",
        "highlight('fil', 'Find in Files')",
        "highlight('abc', 'aXbXc')",
        "highlight('ar', 'bar')",
        "highlight('xyz', 'abc')",
    ],
)

register_libs([LIB], n=8)
