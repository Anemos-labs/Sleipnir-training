"""boardflow (javascript): a kanban board library extended with labels, owners, history, markdown, WIP limits, rules, archive, events."""
import random

from fx import dd
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # boardflow

    The logic of a small kanban board (Node.js, CommonJS, no dependencies). Run the tests with `npm test`
    (`node --test test/*.test.js`).

    ## Layout

    * `index.js`: exports `Board`, `BoardError`.
    * `src/board.js`: the board.

    ## Basics

    * `new Board(columns)`: `columns` is an array of at least two distinct column names, left to right; the last column is
      the "done" column. Anything else throws a `RangeError`.
    * `board.add(title, column = firstColumn)` creates a card `{ id, title, column }` (ids are 1, 2, 3, ...; the title is
      trimmed and must be a non-empty string, else `TypeError`; an unknown column throws a `RangeError`) and returns it.
    * `board.move(id, column)` moves a card to another column and returns the card. Unknown ids (`Error`) and unknown columns
      (`RangeError`) are rejected. Moving a card to the column it is already in is allowed and changes nothing.
    * `board.get(id)` returns the card (`Error` for an unknown id). `board.list(column)` returns the cards of a column
      ordered by id (`RangeError` for an unknown column).
    * `BoardError` is the base class of the errors that describe a refused board action (none are raised yet).
''')

BOARD = '''\
'use strict';
@@uniq requires

class BoardError extends Error {}

@@blocks errors

class Board {
  constructor(columns) {
    if (!Array.isArray(columns) || columns.length < 2) throw new RangeError('a board needs at least two columns');
    if (new Set(columns).size !== columns.length) throw new RangeError('duplicate column name');
    this.columns = [...columns];
    this.cards = new Map();
    this.nextId = 1;
    this.moveSeq = 0;
    @@slot init
  }

  _column(name) {
    if (!this.columns.includes(name)) throw new RangeError(`unknown column: ${name}`);
  }

  get(id) {
    const card = this.cards.get(id);
    if (!card) throw new Error(`no such card: ${id}`);
    return card;
  }

  add(title, column = this.columns[0]) {
    if (typeof title !== 'string' || title.trim() === '') throw new TypeError('title must be a non-empty string');
    this._column(column);
    @@slot add_checks
    const card = { id: this.nextId++, title: title.trim(), column };
    @@slot card_init
    this.cards.set(card.id, card);
    @@slot on_add
    return card;
  }

  move(id, column) {
    const card = this.get(id);
    this._column(column);
    if (card.column === column) return card;
    @@slot move_checks
    const from = card.column;
    card.column = column;
    this.moveSeq += 1;
    @@slot on_move
    return card;
  }

  list(column) {
    this._column(column);
    return [...this.cards.values()].filter((c) => c.column === column).sort((a, b) => a.id - b.id);
  }

  @@blocks methods
}

const exported = { Board, BoardError };
@@slot export_items
module.exports = exported;
'''

HEAD = '''\
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
@@uniq requires
const { Board, BoardError } = require('../index.js');

const COLUMNS = ['backlog', 'doing', 'review', 'done'];
const mk = () => new Board(COLUMNS);
const count = (b) => COLUMNS.reduce((n, c) => n + b.list(c).length, 0);
'''

VISIBLE = HEAD + '''
test('add and list', () => {
  const b = mk();
  const a = b.add('  Write intro ');
  b.add('Fix typo', 'doing');
  assert.equal(a.id, 1);
  assert.equal(a.title, 'Write intro');
  assert.equal(a.column, 'backlog');
  assert.deepEqual(b.list('backlog').map((c) => c.id), [1]);
  assert.equal(b.get(2).column, 'doing');
});

test('move', () => {
  const b = mk();
  b.add('a');
  b.add('b');
  assert.equal(b.move(2, 'done').column, 'done');
  assert.equal(b.move(2, 'done').column, 'done');
  assert.deepEqual(b.list('done').map((c) => c.id), [2]);
  assert.throws(() => b.move(9, 'done'), /no such card/);
  assert.throws(() => b.move(1, 'nowhere'), RangeError);
});

test('constructor checks', () => {
  assert.throws(() => new Board(['one']), RangeError);
  assert.throws(() => new Board(['a', 'a']), RangeError);
  assert.ok(new BoardError('x') instanceof Error);
});
@@blocks tests
'''

HIDDEN = HEAD + '''
test('base validation', () => {
  const b = mk();
  for (const bad of ['', '   ', null, 5]) assert.throws(() => b.add(bad), TypeError);
  assert.throws(() => b.add('x', 'nowhere'), RangeError);
  assert.throws(() => new Board('abc'), RangeError);
  assert.equal(b.add('first').id, 1);
  assert.equal(b.add('second', 'review').id, 2);
  assert.throws(() => b.list('nope'), RangeError);
  assert.throws(() => b.get(7), /no such card: 7/);
  b.add('third');
  assert.deepEqual(b.list('backlog').map((c) => c.title), ['first', 'third']);
  b.move(1, 'doing');
  b.move(3, 'doing');
  assert.deepEqual(b.list('doing').map((c) => c.id), [1, 3]);
  assert.deepEqual(b.list('backlog'), []);
  assert.deepEqual(b.columns, COLUMNS);
});
@@blocks tests
'''


def make_slices(rng: random.Random):
    limit_default = rng.choice([2, 3])
    S = []

    S.append(Slice(
        id="labels", title="Card labels", d=1,
        pitch=("Cards need coloured tags like `bug` or `urgent` so people can filter the board.",
               "The team wants to tag cards and pull up all cards with a tag."),
        reqs=("Every card gets a `labels` array (empty at first). `board.label(id, name)` adds a label: the name is trimmed and lower-cased, a blank or non-string name is a `TypeError`, a label the card already has is ignored; it returns the card.",
              "`board.withLabel(name)` returns the cards that carry the label (name trimmed and lower-cased before comparing), ordered by id."),
        code={
            "src/board.js::card_init": "card.labels = [];",
            "src/board.js::methods": '''
                label(id, name) {
                  const card = this.get(id);
                  if (typeof name !== 'string' || name.trim() === '') throw new TypeError('label must be a non-empty string');
                  const clean = name.trim().toLowerCase();
                  if (!card.labels.includes(clean)) card.labels.push(clean);
                  return card;
                }

                withLabel(name) {
                  const want = String(name).trim().toLowerCase();
                  return [...this.cards.values()].filter((c) => c.labels.includes(want)).sort((a, b) => a.id - b.id);
                }
            ''',
        },
        readme="## Card labels\n\nCards have `labels` (lower-cased, no duplicates); `board.label(id, name)` adds one and `board.withLabel(name)` finds cards by label.\n",
        vtests='''
            test('labels basics', () => {
              const b = mk();
              b.add('a');
              b.label(1, 'Bug');
              assert.deepEqual(b.get(1).labels, ['bug']);
            });
        ''',
        tests='''
            test('labels are normalised and searchable', () => {
              const b = mk();
              b.add('a');
              b.add('b');
              b.add('c');
              assert.deepEqual(b.get(1).labels, []);
              assert.equal(b.label(1, '  Bug '), b.get(1));
              b.label(1, 'bug');
              b.label(1, 'UI');
              b.label(3, 'bug');
              assert.deepEqual(b.get(1).labels, ['bug', 'ui']);
              assert.deepEqual(b.withLabel(' BUG ').map((c) => c.id), [1, 3]);
              assert.deepEqual(b.withLabel('ui').map((c) => c.id), [1]);
              assert.deepEqual(b.withLabel('none'), []);
              assert.deepEqual(b.get(2).labels, []);
            });

            test('label validation', () => {
              const b = mk();
              b.add('a');
              for (const bad of ['', '  ', null, 7]) assert.throws(() => b.label(1, bad), TypeError);
              assert.throws(() => b.label(9, 'x'), /no such card/);
              assert.deepEqual(b.get(1).labels, []);
            });
        ''',
    ))

    S.append(Slice(
        id="owners", title="Card owners", d=2,
        pitch=("Nobody knows who is working on what.",
               "Each card should have an owner and the lead wants to see everyone's load."),
        reqs=("Every card gets an `owner` (`null` at first). `board.assign(id, person)` sets it (the name is trimmed; `null` clears it; a blank or non-string name other than `null` is a `TypeError`) and returns the card.",
              "`board.workload()` returns a plain object that maps each owner to the number of their cards that are **not** in the last column; owners with no open cards are left out, and the keys are in alphabetical order."),
        code={
            "src/board.js::card_init": "card.owner = null;",
            "src/board.js::methods": '''
                assign(id, person) {
                  const card = this.get(id);
                  if (person !== null && (typeof person !== 'string' || person.trim() === '')) throw new TypeError('owner must be a non-empty string or null');
                  card.owner = person === null ? null : person.trim();
                  return card;
                }

                workload() {
                  const last = this.columns[this.columns.length - 1];
                  const counts = {};
                  for (const c of this.cards.values()) {
                    if (c.owner !== null && c.column !== last) counts[c.owner] = (counts[c.owner] || 0) + 1;
                  }
                  return Object.fromEntries(Object.entries(counts).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)));
                }
            ''',
        },
        readme="## Card owners\n\n`card.owner` (null by default), `board.assign(id, person)` and `board.workload()` (open cards per owner, alphabetical keys).\n",
        vtests='''
            test('assign basics', () => {
              const b = mk();
              b.add('a');
              b.assign(1, 'ana');
              assert.equal(b.get(1).owner, 'ana');
            });
        ''',
        tests='''
            test('assign and clear', () => {
              const b = mk();
              b.add('a');
              assert.equal(b.get(1).owner, null);
              assert.equal(b.assign(1, '  ana '), b.get(1));
              assert.equal(b.get(1).owner, 'ana');
              b.assign(1, 'bo');
              assert.equal(b.get(1).owner, 'bo');
              b.assign(1, null);
              assert.equal(b.get(1).owner, null);
              for (const bad of ['', '  ', 5, undefined]) assert.throws(() => b.assign(1, bad), TypeError);
              assert.throws(() => b.assign(9, 'x'), /no such card/);
            });

            test('workload counts open cards only', () => {
              const b = mk();
              for (const t of ['a', 'b', 'c', 'd', 'e']) b.add(t);
              b.assign(1, 'zoe');
              b.assign(2, 'ana');
              b.assign(3, 'ana');
              b.assign(4, 'bo');
              b.move(3, 'done');
              b.move(4, 'done');
              assert.deepEqual(b.workload(), { ana: 1, zoe: 1 });
              assert.deepEqual(Object.keys(b.workload()), ['ana', 'zoe']);
              b.assign(5, 'bo');
              b.move(1, 'review');
              assert.deepEqual(Object.keys(b.workload()), ['ana', 'bo', 'zoe']);
              assert.deepEqual(mk().workload(), {});
            });
        ''',
    ))

    S.append(Slice(
        id="history", title="Move history", d=2,
        pitch=("When a card is stuck nobody can tell where it has been.",
               "The team wants to see how a card travelled across the board."),
        reqs=("`board.history(id)` returns an array of `{ seq, from, to }` for the card, oldest first: one entry for every move that changed its column. `seq` is a counter shared by the whole board that starts at 1 and counts every successful column change of any card.",
              "Creating a card and moving a card to the column it is already in are not moves. A failed `move` records nothing. The returned array is a copy; an unknown id throws an `Error`."),
        code={
            "src/board.js::init": "this.moves = [];",
            "src/board.js::on_move": "this.moves.push({ id, seq: this.moveSeq, from, to: column });",
            "src/board.js::methods": '''
                history(id) {
                  this.get(id);
                  return this.moves.filter((m) => m.id === id).map(({ seq, from, to }) => ({ seq, from, to }));
                }
            ''',
        },
        readme="## Move history\n\n`board.history(id)` lists `{ seq, from, to }` for each column change of a card (`seq` counts moves across the whole board).\n",
        vtests='''
            test('history basics', () => {
              const b = mk();
              b.add('a');
              b.move(1, 'doing');
              assert.deepEqual(b.history(1), [{ seq: 1, from: 'backlog', to: 'doing' }]);
            });
        ''',
        tests='''
            test('history records column changes with a shared counter', () => {
              const b = mk();
              b.add('a');
              b.add('b');
              b.move(1, 'doing');
              b.move(2, 'review');
              b.move(1, 'done');
              b.move(1, 'done');
              assert.throws(() => b.move(1, 'nowhere'), RangeError);
              assert.deepEqual(b.history(1), [{ seq: 1, from: 'backlog', to: 'doing' }, { seq: 3, from: 'doing', to: 'done' }]);
              assert.deepEqual(b.history(2), [{ seq: 2, from: 'backlog', to: 'review' }]);
              b.add('c');
              assert.deepEqual(b.history(3), []);
              b.history(1).push('x');
              assert.equal(b.history(1).length, 2);
              assert.throws(() => b.history(9), /no such card/);
            });
        ''',
    ))

    S.append(Slice(
        id="markdown", title="Markdown export", d=2,
        pitch=("The weekly status mail is copy-pasted from the board by hand.",
               "We want to paste the board into the wiki as Markdown."),
        reqs=("`board.toMarkdown()` renders the board as text. For every column, left to right, there is a heading `## NAME (COUNT)` followed by one line `- #ID TITLE` per card (ordered by id); sections are separated by one blank line and the text ends with a single newline (no blank line at the end). A column without cards is just its heading.",),
        code={
            "src/board.js::methods": '''
                toMarkdown() {
                  const sections = this.columns.map((name) => {
                    const cards = this.list(name);
                    const lines = [`## ${name} (${cards.length})`];
                    for (const c of cards) {
                      let line = `- #${c.id} ${c.title}`;
                      @@slot md_card
                      lines.push(line);
                    }
                    return lines.join('\\n');
                  });
                  return `${sections.join('\\n\\n')}\\n`;
                }
            ''',
        },
        readme="## Markdown export\n\n`board.toMarkdown()` prints `## column (count)` sections with `- #id title` lines, separated by blank lines.\n",
        vtests='''
            test('markdown basics', () => {
              const b = mk();
              b.add('a');
              assert.ok(b.toMarkdown().startsWith('## backlog (1)\\n- #1 a\\n'));
            });
        ''',
        tests='''
            test('markdown layout', () => {
              const b = mk();
              b.add('Write intro');
              b.add('Ship', 'done');
              b.add('Fix typo');
              assert.equal(b.toMarkdown(), '## backlog (2)\\n- #1 Write intro\\n- #3 Fix typo\\n\\n## doing (0)\\n\\n## review (0)\\n\\n## done (1)\\n- #2 Ship\\n');
              assert.equal(new Board(['a', 'b']).toMarkdown(), '## a (0)\\n\\n## b (0)\\n');
              b.move(1, 'review');
              assert.ok(b.toMarkdown().includes('## review (1)\\n- #1 Write intro\\n'));
            });
        ''',
        cross={
            "labels": {
                "reqs": ("A card with labels gets them after the title as ` [label1, label2]` (comma and space between labels); a card without labels is unchanged.",),
                "code": {"src/board.js::md_card": "if (c.labels.length) line += ` [${c.labels.join(', ')}]`;"},
                "tests": '''
                    test('markdown shows labels', () => {
                      const b = mk();
                      b.add('a');
                      b.add('b');
                      b.label(1, 'bug');
                      b.label(1, 'ui');
                      assert.equal(b.toMarkdown().split('\\n')[1], '- #1 a [bug, ui]');
                      assert.ok(b.toMarkdown().includes('\\n- #2 b\\n'));
                    });
                '''},
            "owners": {
                "reqs": ("A card with an owner gets ` @OWNER` at the very end of its line (after the labels, if any).",),
                "code": {"src/board.js::md_card": "if (c.owner !== null) line += ` @${c.owner}`;"},
                "tests": '''
                    test('markdown shows owners', () => {
                      const b = mk();
                      b.add('a');
                      b.add('b');
                      b.assign(2, 'ana');
                      assert.ok(b.toMarkdown().includes('\\n- #2 b @ana\\n'));
                      assert.ok(b.toMarkdown().includes('- #1 a\\n'));
                    });
                '''},
        },
    ))

    S.append(Slice(
        id="wip-limits", title="WIP limits", d=3,
        pitch=("The doing column is always overloaded; the team agreed on work-in-progress limits and wants the board to enforce them.",
               "Columns should refuse new cards beyond an agreed limit."),
        reqs=("`board.setLimit(column, n)` limits how many cards a column may hold: `n` is a positive integer, or `null` to remove the limit; anything else is a `RangeError` (as is an unknown column). `board.limit(column)` returns the limit or `null`.",
              "New error class `WipError` (extends `BoardError`, exported from the package) with `column` and `limit` properties. `add` into a full column and `move` into a full column throw it and change nothing. Moving a card within its own column is not affected. Lowering a limit below the current count is allowed: the cards stay, but nothing more can enter that column.",
              f"The last column has no limit by default; every other column starts without one too."),
        code={
            "src/board.js::errors": '''
                class WipError extends BoardError {
                  constructor(column, limit) {
                    super(`column ${column} is full (limit ${limit})`);
                    this.column = column;
                    this.limit = limit;
                  }
                }
            ''',
            "src/board.js::init": "this.limits = new Map();",
            "src/board.js::add_checks": "this._checkRoom(column);",
            "src/board.js::move_checks": "this._checkRoom(column);",
            "src/board.js::methods": '''
                setLimit(column, n) {
                  this._column(column);
                  if (n === null) {
                    this.limits.delete(column);
                    return;
                  }
                  if (!Number.isInteger(n) || n < 1) throw new RangeError('limit must be a positive integer or null');
                  this.limits.set(column, n);
                }

                limit(column) {
                  this._column(column);
                  return this.limits.has(column) ? this.limits.get(column) : null;
                }

                _checkRoom(column) {
                  const limit = this.limits.get(column);
                  if (limit !== undefined && this.list(column).length >= limit) throw new WipError(column, limit);
                }
            ''',
            "src/board.js::export_items": "exported.WipError = WipError;",
        },
        readme="## WIP limits\n\n`board.setLimit(column, n | null)` / `board.limit(column)`. `add` and `move` into a full column throw `WipError` (`column`, `limit`); existing cards are never evicted.\n",
        vtests='''
            test('limit basics', () => {
              const b = mk();
              b.setLimit('doing', 1);
              b.add('a', 'doing');
              assert.throws(() => b.add('b', 'doing'), BoardError);
            });
        ''',
        tests=fmt('''
            test('wip limit blocks add and move', () => {
              const { WipError } = require('../index.js');
              const b = mk();
              assert.equal(b.limit('doing'), null);
              b.setLimit('doing', __N__);
              assert.equal(b.limit('doing'), __N__);
              for (let i = 0; i < __N__; i++) b.add(`d${i}`, 'doing');
              b.add('t1');
              const before = count(b);
              assert.throws(() => b.add('x', 'doing'), (e) => e instanceof WipError && e instanceof BoardError && e.column === 'doing' && e.limit === __N__);
              assert.throws(() => b.move(__N__ + 1, 'doing'), WipError);
              assert.equal(count(b), before);
              assert.equal(b.get(__N__ + 1).column, 'backlog');
              b.move(1, 'doing');
              b.move(1, 'review');
              b.move(__N__ + 1, 'doing');
              assert.equal(b.list('doing').length, __N__);
            });

            test('wip limit edge cases', () => {
              const b = mk();
              b.add('a', 'doing');
              b.add('b', 'doing');
              b.add('c', 'doing');
              b.setLimit('doing', 1);
              assert.equal(b.list('doing').length, 3);
              assert.equal(b.move(1, 'doing').column, 'doing');
              assert.throws(() => b.add('d', 'doing'), BoardError);
              b.setLimit('doing', null);
              assert.equal(b.limit('doing'), null);
              b.add('d', 'doing');
              for (const bad of [0, -1, 1.5, '2', undefined]) assert.throws(() => b.setLimit('doing', bad), RangeError);
              assert.throws(() => b.setLimit('nowhere', 2), RangeError);
              assert.throws(() => b.limit('nowhere'), RangeError);
              b.setLimit('done', 1);
              b.add('z', 'done');
              assert.throws(() => b.add('y', 'done'), BoardError);
            });
        ''', N=limit_default),
    ))

    S.append(Slice(
        id="rules", title="Allowed moves", d=3,
        pitch=("Cards jump from backlog straight to done and skip review.",
               "The team's process says which columns a card may move to; the board should enforce it."),
        reqs=("`board.allowMoves(map)` sets the rules: `map` maps a column to the array of columns a card may move to from there. Column names that are not on the board are a `RangeError`; `board.allowMoves(null)` removes all rules. Until rules are set every move is allowed.",
              "Once rules are set, `move` only accepts a move from `A` to `B` when `B` is listed under `A`; a column that does not appear as a key allows no moves out of it. A refused move throws the new `TransitionError` (extends `BoardError`, exported from the package, with `from` and `to` properties) and changes nothing. Moving a card within its own column stays allowed. `add` is not affected."),
        code={
            "src/board.js::errors": '''
                class TransitionError extends BoardError {
                  constructor(from, to) {
                    super(`moving from ${from} to ${to} is not allowed`);
                    this.from = from;
                    this.to = to;
                  }
                }
            ''',
            "src/board.js::export_items": "exported.TransitionError = TransitionError;",
            "src/board.js::init": "this.rules = null;",
            "src/board.js::move_checks": '''
                if (this.rules !== null && !(this.rules[card.column] || []).includes(column)) throw new TransitionError(card.column, column);
            ''',
            "src/board.js::methods": '''
                allowMoves(map) {
                  if (map === null) {
                    this.rules = null;
                    return;
                  }
                  for (const [from, tos] of Object.entries(map)) {
                    this._column(from);
                    for (const to of tos) this._column(to);
                  }
                  this.rules = Object.fromEntries(Object.entries(map).map(([k, v]) => [k, [...v]]));
                }
            ''',
        },
        readme="## Allowed moves\n\n`board.allowMoves({ from: [to, ...] })` restricts `move` (a column that is not a key allows no moves out); `allowMoves(null)` lifts the rules. Refused moves throw `TransitionError`.\n",
        vtests='''
            test('rules basics', () => {
              const b = mk();
              b.allowMoves({ backlog: ['doing'] });
              b.add('a');
              assert.throws(() => b.move(1, 'done'), BoardError);
            });
        ''',
        tests='''
            test('moves follow the rules', () => {
              const { TransitionError } = require('../index.js');
              const b = mk();
              b.add('a');
              b.add('b', 'review');
              b.allowMoves({ backlog: ['doing'], doing: ['review', 'backlog'], review: ['done', 'doing'] });
              assert.throws(() => b.move(1, 'done'), (e) => e instanceof TransitionError && e instanceof BoardError && e.from === 'backlog' && e.to === 'done');
              assert.equal(b.get(1).column, 'backlog');
              b.move(1, 'doing');
              b.move(1, 'backlog');
              b.move(1, 'doing');
              assert.equal(b.move(1, 'doing').column, 'doing');
              b.move(2, 'done');
              assert.throws(() => b.move(2, 'review'), TransitionError);
              assert.equal(b.add('c', 'done').column, 'done');
              b.allowMoves(null);
              assert.equal(b.move(2, 'backlog').column, 'backlog');
            });

            test('allowMoves validates names', () => {
              const b = mk();
              assert.throws(() => b.allowMoves({ nowhere: ['backlog'] }), RangeError);
              assert.throws(() => b.allowMoves({ backlog: ['nowhere'] }), RangeError);
              b.add('a');
              assert.equal(b.move(1, 'done').column, 'done');
              const map = { backlog: ['doing'] };
              b.allowMoves(map);
              map.backlog.push('done');
              b.add('b');
              assert.throws(() => b.move(2, 'done'), BoardError);
            });
        ''',
        cross={
            "wip-limits": {
                "reqs": ("When both a move rule and a WIP limit would refuse a move, the rule is reported (`TransitionError`).",),
                "tests": '''
                    test('rule violations win over full columns', () => {
                      const { TransitionError } = require('../index.js');
                      const b = mk();
                      b.setLimit('done', 1);
                      b.add('x', 'done');
                      b.add('a');
                      b.allowMoves({ backlog: ['doing'] });
                      assert.throws(() => b.move(2, 'done'), TransitionError);
                    });
                '''},
        },
    ))
    order = ["labels", "owners", "history", "markdown", "rules", "wip-limits"]
    S.sort(key=lambda x: order.index(x.id))
    return S


APP = App(
    name="boardflow", lang="javascript", title="the kanban board library", role="a team lead", key="BOARD",
    base={
        "README.md": README + "\n@@blocks features\n",
        "package.json": '{\n  "name": "boardflow",\n  "version": "1.0.0",\n  "private": true,\n  "main": "index.js",\n  "scripts": {\n    "test": "node --test test/*.test.js"\n  }\n}\n',
        "index.js": "'use strict';\nmodule.exports = require('./src/board');\n",
        "src/board.js": BOARD,
        ".gitignore": "node_modules/\n",
    },
    visible={"test/basic.test.js": VISIBLE},
    hidden={"test/features.test.js": HIDDEN},
    verify="node --test test/*.test.js",
)

register_app("feature-js-boardflow", APP, make_slices, n=14, summary="kanban board: labels, owners, history, markdown, WIP limits, move rules")
