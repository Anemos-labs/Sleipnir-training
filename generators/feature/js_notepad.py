"""notepad (javascript): the text-buffer logic of a small editor, extended with lines, limits, words, events, selection, search, undo."""
import random

from fx import dd
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # notepad

    The text buffer behind a small editor (Node.js, CommonJS, no dependencies). Run the tests with `npm test`
    (`node --test test/*.test.js`).

    ## Layout

    * `index.js`: exports `Buffer`.
    * `src/buffer.js`: the buffer.

    ## Basics

    Positions are indexes into the text string (JavaScript string indexes, 0 to `text().length`).

    * `new Buffer(text = '')`: the cursor starts at the end of the text.
    * `buffer.text()` returns the whole text; `buffer.cursor` is the cursor position.
    * `buffer.moveTo(pos)`: `pos` must be an integer from 0 to the length of the text, otherwise `RangeError`.
      `buffer.moveBy(delta)` moves relative to the cursor and stops at the ends of the text (`delta` an integer, else `RangeError`).
    * `buffer.insert(str)` inserts a string at the cursor (anything else is a `TypeError`) and leaves the cursor after it.
    * `buffer.delete(n = 1)` removes up to `n` characters after the cursor; `buffer.backspace(n = 1)` removes up to `n`
      characters before it and moves the cursor back. `n` must be a non-negative integer (`RangeError` otherwise). Both
      return the removed text (possibly empty).
''')

BUFFER = '''\
'use strict';
@@uniq requires

class Buffer {
  constructor(text = '', options = {}) {
    this._text = String(text);
    this.cursor = this._text.length;
    @@slot init
  }

  text() {
    return this._text;
  }

  _checkCount(n) {
    if (!Number.isInteger(n) || n < 0) throw new RangeError('n must be a non-negative integer');
  }

  moveTo(pos) {
    if (!Number.isInteger(pos) || pos < 0 || pos > this._text.length) throw new RangeError(`position out of range: ${pos}`);
    this.cursor = pos;
    @@slot on_move
  }

  moveBy(delta) {
    if (!Number.isInteger(delta)) throw new RangeError('delta must be an integer');
    this.cursor = Math.max(0, Math.min(this._text.length, this.cursor + delta));
    @@slot on_move
  }

  // Replace text[start, end) by str, put the cursor at cursorAfter and return the removed text.
  _replace(start, end, str, cursorAfter) {
    @@slot replace_checks
    const removed = this._text.slice(start, end);
    @@slot replace_before
    this._text = this._text.slice(0, start) + str + this._text.slice(end);
    this.cursor = cursorAfter;
    @@slot replace_after
    return removed;
  }

  insert(str) {
    if (typeof str !== 'string') throw new TypeError('insert needs a string');
    let start = this.cursor;
    let end = this.cursor;
    @@slot insert_range
    this._replace(start, end, str, start + str.length);
  }

  delete(n = 1) {
    this._checkCount(n);
    @@slot delete_pre
    return this._replace(this.cursor, Math.min(this._text.length, this.cursor + n), '', this.cursor);
  }

  backspace(n = 1) {
    this._checkCount(n);
    @@slot backspace_pre
    const start = Math.max(0, this.cursor - n);
    return this._replace(start, this.cursor, '', start);
  }

  @@blocks methods
}

module.exports = { Buffer };
'''

HEAD = '''\
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
@@uniq requires
const { Buffer } = require('../index.js');
'''

VISIBLE = HEAD + '''
test('insert moves the cursor', () => {
  const b = new Buffer('hello');
  b.moveTo(0);
  b.insert('oh, ');
  assert.equal(b.text(), 'oh, hello');
  assert.equal(b.cursor, 4);
  b.moveBy(100);
  b.insert('!');
  assert.equal(b.text(), 'oh, hello!');
});

test('delete and backspace', () => {
  const b = new Buffer('abcdef');
  b.moveTo(3);
  assert.equal(b.delete(2), 'de');
  assert.equal(b.text(), 'abcf');
  assert.equal(b.backspace(), 'c');
  assert.equal(b.text(), 'abf');
  assert.equal(b.cursor, 2);
  assert.equal(b.backspace(10), 'ab');
  assert.equal(b.delete(10), 'f');
  assert.equal(b.text(), '');
});

test('argument checks', () => {
  const b = new Buffer('abc');
  assert.throws(() => b.moveTo(4), RangeError);
  assert.throws(() => b.insert(5), TypeError);
  assert.throws(() => b.delete(-1), RangeError);
});
@@blocks tests
'''

HIDDEN = HEAD + '''
test('base editing rules', () => {
  const b = new Buffer();
  assert.equal(b.text(), '');
  assert.equal(b.cursor, 0);
  b.insert('héllo wörld');
  assert.equal(b.cursor, 11);
  b.moveTo(5);
  b.insert(',');
  assert.equal(b.text(), 'héllo, wörld');
  assert.equal(b.delete(0), '');
  assert.equal(b.backspace(0), '');
  b.moveBy(-100);
  assert.equal(b.cursor, 0);
  assert.equal(b.backspace(), '');
  b.moveBy(2);
  assert.equal(b.cursor, 2);
  for (const bad of [-1, 13, 1.5, '2', NaN]) assert.throws(() => b.moveTo(bad), RangeError);
  for (const bad of [1.5, '1', NaN]) assert.throws(() => b.moveBy(bad), RangeError);
  for (const bad of [1.5, '1', null]) assert.throws(() => b.delete(bad), RangeError);
  for (const bad of [-2, 0.5]) assert.throws(() => b.backspace(bad), RangeError);
  for (const bad of [null, undefined, 3, {}]) assert.throws(() => b.insert(bad), TypeError);
  assert.equal(b.text(), 'héllo, wörld');
  assert.equal(new Buffer(42).text(), '42');
});
@@blocks tests
'''


def make_slices(rng: random.Random):
    maxlen = rng.choice([20, 30, 40])
    S = []

    S.append(Slice(
        id="lines", title="Line and column", d=1,
        pitch=("The status bar needs to show the cursor as line and column.",
               "Editors show `Ln 3, Col 7`; the buffer has to provide those numbers."),
        reqs=("Lines are separated by `\\n`. `buffer.lineCount()` is the number of lines (an empty text has 1). `buffer.lineAt(n)` returns line `n` (counting from 0) without its newline; an index outside the text is a `RangeError`.",
              "`buffer.position()` returns `{ line, col }` for the cursor, both counting from 0: `line` is the number of newlines before the cursor and `col` the distance to the start of that line."),
        code={
            "src/buffer.js::methods": '''
                lineCount() {
                  return this._text.split('\\n').length;
                }

                lineAt(n) {
                  const lines = this._text.split('\\n');
                  if (!Number.isInteger(n) || n < 0 || n >= lines.length) throw new RangeError(`no such line: ${n}`);
                  return lines[n];
                }

                position() {
                  const before = this._text.slice(0, this.cursor);
                  const line = before.split('\\n').length - 1;
                  return { line, col: this.cursor - (before.lastIndexOf('\\n') + 1) };
                }
            ''',
        },
        readme="## Line and column\n\n`lineCount()`, `lineAt(n)` and `position()` (`{ line, col }`, zero-based) for text split at `\\n`.\n",
        vtests='''
            test('position basics', () => {
              const b = new Buffer('ab\\ncd');
              assert.deepEqual(b.position(), { line: 1, col: 2 });
            });
        ''',
        tests='''
            test('lines', () => {
              const b = new Buffer('one\\ntwo\\n\\nfour');
              assert.equal(b.lineCount(), 4);
              assert.deepEqual([0, 1, 2, 3].map((i) => b.lineAt(i)), ['one', 'two', '', 'four']);
              for (const bad of [-1, 4, 1.5, '1']) assert.throws(() => b.lineAt(bad), RangeError);
              assert.equal(new Buffer().lineCount(), 1);
              assert.equal(new Buffer().lineAt(0), '');
              assert.equal(new Buffer('a\\n').lineCount(), 2);
            });

            test('cursor position', () => {
              const b = new Buffer('one\\ntwo\\n\\nfour');
              assert.deepEqual(b.position(), { line: 3, col: 4 });
              b.moveTo(0);
              assert.deepEqual(b.position(), { line: 0, col: 0 });
              b.moveTo(3);
              assert.deepEqual(b.position(), { line: 0, col: 3 });
              b.moveTo(4);
              assert.deepEqual(b.position(), { line: 1, col: 0 });
              b.moveTo(8);
              assert.deepEqual(b.position(), { line: 2, col: 0 });
              b.insert('x\\ny');
              assert.deepEqual(b.position(), { line: 3, col: 1 });
            });
        ''',
    ))

    S.append(Slice(
        id="max-length", title="Length limit", d=2,
        pitch=("The notes field is capped at a few kilobytes and the editor has to refuse text beyond it.",
               "A buffer used for tweets must never grow past its limit."),
        reqs=(f"`new Buffer(text, { '{' } maxLength { '}' })` takes an optional `maxLength` (a positive integer, else `RangeError` from the constructor; the initial text must fit, else `RangeError` too). Without it there is no limit.",
              "An `insert` that would make the text longer than `maxLength` throws a `RangeError` and changes nothing (text and cursor stay as they were). Edits that do not make the text longer are always allowed. `buffer.maxLength` holds the limit (`null` when there is none)."),
        code={
            "src/buffer.js::init": '''
                this.maxLength = options.maxLength === undefined ? null : options.maxLength;
                if (this.maxLength !== null) {
                  if (!Number.isInteger(this.maxLength) || this.maxLength < 1) throw new RangeError('maxLength must be a positive integer');
                  if (this._text.length > this.maxLength) throw new RangeError('initial text is longer than maxLength');
                }
            ''',
            "src/buffer.js::replace_checks": '''
                if (this.maxLength !== null && this._text.length - (end - start) + str.length > this.maxLength && str.length > end - start) {
                  throw new RangeError(`text would exceed ${this.maxLength} characters`);
                }
            ''',
        },
        readme=dd('''
            ## Length limit

            `new Buffer(text, { maxLength })`: inserts that would exceed the limit throw a `RangeError` and change nothing.
            `buffer.maxLength` is `null` without a limit.
        '''),
        vtests='''
            test('maxLength basics', () => {
              const b = new Buffer('abc', { maxLength: 4 });
              assert.throws(() => b.insert('xy'), RangeError);
              assert.equal(b.text(), 'abc');
            });
        ''',
        tests=fmt('''
            test('maxLength refuses growth', () => {
              const b = new Buffer('', { maxLength: __N__ });
              assert.equal(b.maxLength, __N__);
              b.insert('a'.repeat(__N__ - 1));
              assert.throws(() => b.insert('xx'), RangeError);
              assert.equal(b.text().length, __N__ - 1);
              assert.equal(b.cursor, __N__ - 1);
              b.insert('b');
              assert.equal(b.text().length, __N__);
              assert.throws(() => b.insert('c'), RangeError);
              assert.equal(b.cursor, __N__);
              b.moveTo(3);
              b.insert('');
              assert.equal(b.delete(2), 'aa');
              b.insert('12');
              assert.equal(b.text().length, __N__);
              assert.throws(() => b.insert('1'), RangeError);
            });

            test('maxLength validation', () => {
              assert.equal(new Buffer('abc').maxLength, null);
              for (const bad of [0, -3, 2.5, '5']) assert.throws(() => new Buffer('', { maxLength: bad }), RangeError);
              assert.throws(() => new Buffer('abcdef', { maxLength: 5 }), RangeError);
              assert.equal(new Buffer('abcde', { maxLength: 5 }).text(), 'abcde');
            });
        ''', N=maxlen),
    ))

    S.append(Slice(
        id="words", title="Word movement", d=2,
        pitch=("Ctrl+arrow and Ctrl+Backspace need word boundaries.",
               "Keyboard users expect to jump and delete by word."),
        reqs=("A *word character* is an ASCII letter, a digit or an underscore; every other character separates words.",
              "`buffer.moveWord(dir)` (`dir` is `1` or `-1`, otherwise `RangeError`) moves the cursor: forward it skips separators and then the word, ending right after that word (or at the end of the text); backward it skips separators and then the word before the cursor, ending at the start of that word (or at 0).",
              "`buffer.deleteWord()` deletes from the cursor to the position `moveWord(1)` would reach, leaves the cursor where it is and returns the removed text (empty at the end of the text)."),
        code={
            "src/buffer.js::methods": '''
                moveWord(dir) {
                  if (dir !== 1 && dir !== -1) throw new RangeError('dir must be 1 or -1');
                  this.cursor = dir === 1 ? this._wordEnd(this.cursor) : this._wordStart(this.cursor);
                  @@slot on_move
                }

                deleteWord() {
                  @@slot word_pre
                  return this._replace(this.cursor, this._wordEnd(this.cursor), '', this.cursor);
                }

                _isWord(ch) {
                  return /[A-Za-z0-9_]/.test(ch);
                }

                _wordEnd(pos) {
                  let i = pos;
                  while (i < this._text.length && !this._isWord(this._text[i])) i += 1;
                  while (i < this._text.length && this._isWord(this._text[i])) i += 1;
                  return i;
                }

                _wordStart(pos) {
                  let i = pos;
                  while (i > 0 && !this._isWord(this._text[i - 1])) i -= 1;
                  while (i > 0 && this._isWord(this._text[i - 1])) i -= 1;
                  return i;
                }
            ''',
        },
        readme="## Word movement\n\n`moveWord(1 | -1)` and `deleteWord()`; word characters are ASCII letters, digits and `_`.\n",
        vtests='''
            test('moveWord basics', () => {
              const b = new Buffer('foo bar');
              b.moveTo(0);
              b.moveWord(1);
              assert.equal(b.cursor, 3);
            });
        ''',
        tests='''
            test('moveWord forward and backward', () => {
              const b = new Buffer('foo  bar_baz, qux!');
              b.moveTo(0);
              const stops = [];
              for (let i = 0; i < 5; i++) {
                b.moveWord(1);
                stops.push(b.cursor);
              }
              assert.deepEqual(stops, [3, 12, 17, 18, 18]);
              const back = [];
              for (let i = 0; i < 5; i++) {
                b.moveWord(-1);
                back.push(b.cursor);
              }
              assert.deepEqual(back, [14, 5, 0, 0, 0]);
              for (const bad of [0, 2, '1', null]) assert.throws(() => b.moveWord(bad), RangeError);
            });

            test('deleteWord', () => {
              const b = new Buffer('foo  bar_baz, qux!');
              b.moveTo(3);
              assert.equal(b.deleteWord(), '  bar_baz');
              assert.equal(b.text(), 'foo, qux!');
              assert.equal(b.cursor, 3);
              b.moveTo(0);
              assert.equal(b.deleteWord(), 'foo');
              assert.equal(b.text(), ', qux!');
              b.moveTo(b.text().length);
              assert.equal(b.deleteWord(), '');
              assert.equal(b.text(), ', qux!');
              assert.equal(new Buffer('').deleteWord(), '');
            });
        ''',
    ))

    S.append(Slice(
        id="events", title="Change notifications", d=2,
        pitch=("The syntax highlighter and the autosave both need to know when the text changes.",
               "Other components have to be told about every edit."),
        reqs=("`buffer.onChange(fn)` registers a listener and returns a function that removes it (calling that function again does nothing). A non-function is a `TypeError`.",
              "After every edit that changes the text, each listener is called synchronously, in registration order, with `{ start, removed, inserted }`: the position of the change, the text that was taken out and the text that was put in. An edit that removes nothing and inserts nothing (`insert('')`, `delete(0)`, a `delete` at the end, ...) notifies nobody; moving the cursor never does."),
        code={
            "src/buffer.js::init": "this._listeners = [];",
            "src/buffer.js::replace_after": '''
                if (removed !== '' || str !== '') {
                  for (const fn of [...this._listeners]) fn({ start, removed, inserted: str });
                }
            ''',
            "src/buffer.js::methods": '''
                onChange(fn) {
                  if (typeof fn !== 'function') throw new TypeError('listener must be a function');
                  this._listeners.push(fn);
                  return () => {
                    const i = this._listeners.indexOf(fn);
                    if (i >= 0) this._listeners.splice(i, 1);
                  };
                }
            ''',
        },
        readme="## Change notifications\n\n`buffer.onChange(fn)` (returns an unsubscribe function) is called after each edit with `{ start, removed, inserted }`; no-op edits and cursor moves are silent.\n",
        vtests='''
            test('onChange basics', () => {
              const b = new Buffer('abc');
              const seen = [];
              b.onChange((e) => seen.push(e));
              b.insert('d');
              assert.equal(seen.length, 1);
            });
        ''',
        tests='''
            test('listeners see every change', () => {
              const b = new Buffer('hello');
              const log = [];
              const off = b.onChange((e) => log.push(['a', e]));
              b.onChange((e) => log.push(['b', e.start]));
              b.moveTo(0);
              b.insert('oh ');
              b.delete(2);
              b.backspace(1);
              assert.deepEqual(log, [
                ['a', { start: 0, removed: '', inserted: 'oh ' }], ['b', 0],
                ['a', { start: 3, removed: 'he', inserted: '' }], ['b', 3],
                ['a', { start: 2, removed: ' ', inserted: '' }], ['b', 2],
              ]);
              assert.equal(b.text(), 'ohllo');
              log.length = 0;
              off();
              off();
              b.insert('x');
              assert.deepEqual(log, [['b', 2]]);
            });

            test('silent operations', () => {
              const b = new Buffer('abc');
              let calls = 0;
              b.onChange(() => { calls += 1; });
              b.insert('');
              b.delete(0);
              b.backspace(0);
              b.delete(3);
              b.moveTo(0);
              b.moveBy(2);
              b.backspace(0);
              assert.equal(calls, 0);
              b.delete(5);
              assert.equal(calls, 1);
              b.backspace(5);
              assert.equal(calls, 2);
              assert.equal(b.text(), '');
              for (const bad of [null, 'x', 5]) assert.throws(() => b.onChange(bad), TypeError);
            });
        ''',
    ))

    S.append(Slice(
        id="selection", title="Selections", d=3,
        pitch=("Typing over a selected word should replace it, like in every other editor.",
               "The buffer has no notion of a selection yet."),
        reqs=("`buffer.select(from, to)` selects the text between two positions (integers from 0 to the text length, else `RangeError`; the order does not matter) and moves the cursor to `to`, the second argument. An empty selection (`from === to`) means no selection. `buffer.selection` is `null` or `{ from, to }` with `from <= to`; `buffer.selectedText()` returns the selected text (empty when there is none).",
              "`moveTo`, `moveBy` and every edit clear the selection. With a selection, `insert(str)` replaces the selected text (the cursor ends after the inserted text), and `delete(n)` and `backspace(n)` remove exactly the selected text whatever `n` is, leaving the cursor at the start of the removed range, and return it."),
        code={
            "src/buffer.js::init": "this._sel = null;",
            "src/buffer.js::on_move": "this._sel = null;",
            "src/buffer.js::replace_after": "this._sel = null;",
            "src/buffer.js::insert_range": '''
                if (this._sel) {
                  start = this._sel.from;
                  end = this._sel.to;
                  this._pendingSel = this._sel;
                }
            ''',
            "src/buffer.js::delete_pre": '''
                if (this._sel) {
                  const { from, to } = this._sel;
                  this._pendingSel = this._sel;
                  return this._replace(from, to, '', from);
                }
            ''',
            "src/buffer.js::backspace_pre": '''
                if (this._sel) {
                  const { from, to } = this._sel;
                  this._pendingSel = this._sel;
                  return this._replace(from, to, '', from);
                }
            ''',
            "src/buffer.js::methods": '''
                select(from, to) {
                  for (const p of [from, to]) {
                    if (!Number.isInteger(p) || p < 0 || p > this._text.length) throw new RangeError(`position out of range: ${p}`);
                  }
                  this.cursor = to;
                  this._sel = from === to ? null : { from: Math.min(from, to), to: Math.max(from, to) };
                }

                get selection() {
                  return this._sel ? { ...this._sel } : null;
                }

                selectedText() {
                  return this._sel ? this._text.slice(this._sel.from, this._sel.to) : '';
                }
            ''',
        },
        readme="## Selections\n\n`select(from, to)`, `selection`, `selectedText()`. Edits replace or remove the selection; moving the cursor or editing clears it.\n",
        vtests='''
            test('selection basics', () => {
              const b = new Buffer('hello world');
              b.select(6, 11);
              assert.equal(b.selectedText(), 'world');
            });
        ''',
        tests='''
            test('select and read', () => {
              const b = new Buffer('hello world');
              assert.equal(b.selection, null);
              assert.equal(b.selectedText(), '');
              b.select(6, 11);
              assert.deepEqual(b.selection, { from: 6, to: 11 });
              assert.equal(b.selectedText(), 'world');
              assert.equal(b.cursor, 11);
              b.select(11, 6);
              assert.deepEqual(b.selection, { from: 6, to: 11 });
              assert.equal(b.cursor, 6);
              b.select(3, 3);
              assert.equal(b.selection, null);
              assert.equal(b.cursor, 3);
              for (const bad of [[-1, 2], [0, 12], [1.5, 2], ['1', 2], [0, NaN]]) assert.throws(() => b.select(...bad), RangeError);
              b.select(0, 5);
              b.selection.from = 99;
              assert.deepEqual(b.selection, { from: 0, to: 5 });
            });

            test('edits replace the selection', () => {
              const b = new Buffer('hello world');
              b.select(6, 11);
              b.insert('there');
              assert.equal(b.text(), 'hello there');
              assert.equal(b.cursor, 11);
              assert.equal(b.selection, null);
              b.select(0, 5);
              assert.equal(b.delete(3), 'hello');
              assert.equal(b.text(), ' there');
              assert.equal(b.cursor, 0);
              b.select(3, 1);
              assert.equal(b.backspace(5), 'th');
              assert.equal(b.text(), ' ere');
              assert.equal(b.cursor, 1);
              assert.equal(b.selection, null);
              assert.equal(b.delete(1), 'e');
            });

            test('moving clears the selection', () => {
              const b = new Buffer('hello world');
              b.select(0, 5);
              b.moveTo(2);
              assert.equal(b.selection, null);
              b.select(0, 5);
              b.moveBy(1);
              assert.equal(b.selection, null);
              b.select(0, 5);
              b.moveBy(0);
              assert.equal(b.selection, null);
              b.select(0, 5);
              b.insert('');
              assert.equal(b.text(), ' world');
            });
        ''',
        cross={
            "words": {
                "reqs": ("`moveWord` clears the selection like any move; `deleteWord` with a selection removes exactly the selection (like `delete`) and returns it.",),
                "code": {"src/buffer.js::word_pre": '''
                    if (this._sel) {
                      const { from, to } = this._sel;
                      this._pendingSel = this._sel;
                      return this._replace(from, to, '', from);
                    }
                '''},
                "tests": '''
                    test('words and selections', () => {
                      const b = new Buffer('foo bar baz');
                      b.select(0, 3);
                      assert.equal(b.deleteWord(), 'foo');
                      assert.equal(b.text(), ' bar baz');
                      b.select(1, 4);
                      b.moveWord(1);
                      assert.equal(b.selection, null);
                    });
                '''},
        },
    ))

    S.append(Slice(
        id="search", title="Find and replace", d=3,
        pitch=("Find/replace is the first thing people ask an editor for.",
               "The buffer should be able to search and to replace every occurrence."),
        reqs=("`buffer.find(needle, options = {})` returns the index of the first occurrence of `needle` at or after `options.from` (default: the cursor), or -1. `options.caseSensitive` defaults to `true`; `false` compares ignoring case. `needle` must be a non-empty string (`TypeError`), `from` an integer from 0 to the text length (`RangeError`).",
              "`buffer.replaceAll(needle, replacement, options = {})` replaces every non-overlapping occurrence of `needle`, scanning from the start of the text (the replacement is not searched again), and returns how many were replaced. `options.caseSensitive` works as above; `needle` and `replacement` must be strings, the needle non-empty (`TypeError`). When there is no match nothing changes.",
              "The text change is one edit: the cursor stays where it was, but not past the end of the new text."),
        code={
            "src/buffer.js::methods": '''
                _matches(needle, caseSensitive, from) {
                  const hay = caseSensitive ? this._text : this._text.toLowerCase();
                  const n = caseSensitive ? needle : needle.toLowerCase();
                  const found = [];
                  let i = hay.indexOf(n, from);
                  while (i !== -1) {
                    found.push(i);
                    i = hay.indexOf(n, i + n.length);
                  }
                  return found;
                }

                find(needle, options = {}) {
                  if (typeof needle !== 'string' || needle === '') throw new TypeError('needle must be a non-empty string');
                  const from = options.from === undefined ? this.cursor : options.from;
                  if (!Number.isInteger(from) || from < 0 || from > this._text.length) throw new RangeError('from is out of range');
                  const hay = options.caseSensitive === false ? this._text.toLowerCase() : this._text;
                  return hay.indexOf(options.caseSensitive === false ? needle.toLowerCase() : needle, from);
                }

                replaceAll(needle, replacement, options = {}) {
                  if (typeof needle !== 'string' || needle === '') throw new TypeError('needle must be a non-empty string');
                  if (typeof replacement !== 'string') throw new TypeError('replacement must be a string');
                  const hits = this._matches(needle, options.caseSensitive !== false, 0);
                  if (hits.length === 0) return 0;
                  let out = '';
                  let last = 0;
                  for (const i of hits) {
                    out += this._text.slice(last, i) + replacement;
                    last = i + needle.length;
                  }
                  out += this._text.slice(last);
                  this._replace(0, this._text.length, out, Math.min(this.cursor, out.length));
                  return hits.length;
                }
            ''',
        },
        readme="## Find and replace\n\n`find(needle, { from, caseSensitive })` and `replaceAll(needle, replacement, { caseSensitive })` (non-overlapping, one edit, cursor clamped).\n",
        vtests='''
            test('find basics', () => {
              const b = new Buffer('the cat');
              b.moveTo(0);
              assert.equal(b.find('cat'), 4);
            });
        ''',
        tests='''
            test('find', () => {
              const b = new Buffer('The cat sat on the mat. The end.');
              assert.equal(b.find('the'), -1);
              assert.equal(b.find('the', { from: 0 }), 15);
              assert.equal(b.find('the', { from: 0, caseSensitive: false }), 0);
              b.moveTo(16);
              assert.equal(b.find('the', { caseSensitive: false }), 24);
              assert.equal(b.find('cat', { from: 5 }), -1);
              assert.equal(b.find('cat', { from: 4 }), 4);
              assert.equal(b.find('.', { from: 32 }), -1);
              for (const bad of ['', 5, null]) assert.throws(() => b.find(bad), TypeError);
              for (const bad of [-1, 33, 1.5, '2']) assert.throws(() => b.find('a', { from: bad }), RangeError);
            });

            test('replaceAll', () => {
              const b = new Buffer('The cat sat on the mat. The end.');
              assert.equal(b.replaceAll('The', 'A'), 2);
              assert.equal(b.text(), 'A cat sat on the mat. A end.');
              assert.equal(b.replaceAll('THE', 'a', { caseSensitive: false }), 1);
              assert.equal(b.text(), 'A cat sat on a mat. A end.');
              assert.equal(b.replaceAll('zzz', 'y'), 0);
              assert.equal(b.text(), 'A cat sat on a mat. A end.');
              const c = new Buffer('aaaa');
              assert.equal(c.replaceAll('aa', 'b'), 2);
              assert.equal(c.text(), 'bb');
              const d = new Buffer('aaa');
              assert.equal(d.replaceAll('aa', 'b'), 1);
              assert.equal(d.text(), 'ba');
              const e = new Buffer('ab');
              assert.equal(e.replaceAll('a', 'aa'), 1);
              assert.equal(e.text(), 'aab');
              assert.equal(e.replaceAll('a', ''), 2);
              assert.equal(e.text(), 'b');
              for (const bad of [['', 'x'], [5, 'x'], ['a', 5], ['a', null]]) assert.throws(() => e.replaceAll(...bad), TypeError);
            });

            test('replaceAll keeps the cursor inside the text', () => {
              const b = new Buffer('abc');
              assert.equal(b.cursor, 3);
              b.replaceAll('abc', 'x');
              assert.equal(b.text(), 'x');
              assert.equal(b.cursor, 1);
              const c = new Buffer('a b a');
              c.moveTo(2);
              c.replaceAll('a', 'zzz');
              assert.equal(c.text(), 'zzz b zzz');
              assert.equal(c.cursor, 2);
            });
        ''',
        cross={
            "max-length": {"tests": fmt('''
                test('replaceAll respects the length limit', () => {
                  const b = new Buffer('a'.repeat(__H__), { maxLength: __N__ });
                  assert.throws(() => b.replaceAll('a', 'bb'), RangeError);
                  assert.equal(b.text(), 'a'.repeat(__H__));
                  assert.equal(b.replaceAll('a', 'b'), __H__);
                });
            ''', H=maxlen // 2 + 3, N=maxlen)},
            "selection": {"tests": '''
                test('replaceAll clears the selection', () => {
                  const b = new Buffer('a b a');
                  b.select(0, 3);
                  b.replaceAll('a', 'c');
                  assert.equal(b.selection, null);
                  assert.equal(b.text(), 'c b c');
                });
            '''},
            "events": {"tests": '''
                test('replaceAll is one notification', () => {
                  const b = new Buffer('a b a');
                  const seen = [];
                  b.onChange((e) => seen.push(e));
                  b.replaceAll('a', 'xx');
                  assert.deepEqual(seen, [{ start: 0, removed: 'a b a', inserted: 'xx b xx' }]);
                  b.replaceAll('q', 'z');
                  assert.equal(seen.length, 1);
                });
            '''},
        },
    ))

    S.append(Slice(
        id="undo", title="Undo and redo", d=4,
        pitch=("Everybody expects Ctrl+Z.",
               "Edits need to be undoable and redoable."),
        reqs=("`buffer.undo()` reverts the most recent edit and returns `true` (or `false` when there is nothing to undo); `buffer.redo()` re-applies the most recently undone edit (returns `true`/`false`). `buffer.canUndo()` and `buffer.canRedo()` tell whether they would succeed.",
              "An *edit* is one `insert`, `delete`, `backspace` (and `deleteWord`, `replaceAll` where they exist) that changes the text. Edits that change nothing are not recorded, cursor moves are not edits. A new edit empties the redo history.",
              "Undo puts back the text and the cursor exactly as they were before the edit; redo puts the cursor where the original edit left it. `replaceAll` is a single edit however many occurrences it replaced."),
        code={
            "src/buffer.js::init": "this._undo = [];\nthis._redo = [];\nthis._replaying = false;",
            "src/buffer.js::replace_before": "const rec = { start, removed, inserted: str, cursorBefore: this.cursor };",
            "src/buffer.js::replace_after": '''
                if (!this._replaying && (removed !== '' || str !== '')) {
                  rec.cursorAfter = cursorAfter;
                  this._undo.push(rec);
                  this._redo = [];
                }
            ''',
            "src/buffer.js::methods": '''
                canUndo() {
                  return this._undo.length > 0;
                }

                canRedo() {
                  return this._redo.length > 0;
                }

                undo() {
                  const rec = this._undo.pop();
                  if (!rec) return false;
                  this._replaying = true;
                  try {
                    this._replace(rec.start, rec.start + rec.inserted.length, rec.removed, rec.cursorBefore);
                  } finally {
                    this._replaying = false;
                  }
                  this._redo.push(rec);
                  @@slot after_undo
                  return true;
                }

                redo() {
                  const rec = this._redo.pop();
                  if (!rec) return false;
                  this._replaying = true;
                  try {
                    this._replace(rec.start, rec.start + rec.removed.length, rec.inserted, rec.cursorAfter);
                  } finally {
                    this._replaying = false;
                  }
                  this._undo.push(rec);
                  return true;
                }
            ''',
        },
        readme="## Undo and redo\n\n`undo()`, `redo()`, `canUndo()`, `canRedo()`: edits that change the text are undoable one by one (cursor restored); a new edit clears the redo history.\n",
        vtests='''
            test('undo basics', () => {
              const b = new Buffer('abc');
              b.insert('d');
              assert.equal(b.undo(), true);
              assert.equal(b.text(), 'abc');
            });
        ''',
        tests='''
            test('undo and redo walk through the edits', () => {
              const b = new Buffer('abc');
              assert.equal(b.canUndo(), false);
              assert.equal(b.undo(), false);
              b.insert('d');
              b.moveTo(1);
              b.delete(2);
              assert.equal(b.text(), 'ad');
              assert.equal(b.undo(), true);
              assert.equal([b.text(), b.cursor].join('|'), 'abcd|1');
              assert.equal(b.undo(), true);
              assert.equal([b.text(), b.cursor].join('|'), 'abc|3');
              assert.equal(b.undo(), false);
              assert.equal(b.canUndo(), false);
              assert.equal(b.canRedo(), true);
              assert.equal(b.redo(), true);
              assert.equal([b.text(), b.cursor].join('|'), 'abcd|4');
              assert.equal(b.redo(), true);
              assert.equal([b.text(), b.cursor].join('|'), 'ad|1');
              assert.equal(b.redo(), false);
              assert.equal(b.canRedo(), false);
            });

            test('new edits clear redo, no-ops and moves are not edits', () => {
              const b = new Buffer('abc');
              b.insert('d');
              b.moveTo(0);
              b.insert('X');
              b.moveBy(2);
              b.insert('');
              b.delete(0);
              b.backspace(0);
              b.moveTo(b.text().length);
              b.delete(3);
              assert.equal(b.undo(), true);
              assert.equal(b.text(), 'abcd');
              assert.equal(b.canRedo(), true);
              b.insert('Z');
              assert.equal(b.text(), 'Zabcd');
              assert.equal(b.canRedo(), false);
              assert.equal(b.redo(), false);
              assert.equal(b.undo(), true);
              assert.equal(b.text(), 'abcd');
              assert.equal(b.undo(), true);
              assert.equal(b.text(), 'abc');
              assert.equal(b.undo(), false);
            });

            test('backspace is undone with the cursor', () => {
              const b = new Buffer('hello');
              b.moveTo(3);
              assert.equal(b.backspace(2), 'el');
              assert.equal(b.cursor, 1);
              b.undo();
              assert.equal([b.text(), b.cursor].join('|'), 'hello|3');
              b.redo();
              assert.equal([b.text(), b.cursor].join('|'), 'hlo|1');
            });
        ''',
        cross={
            "search": {"tests": '''
                test('replaceAll is a single undo step', () => {
                  const b = new Buffer('a b a');
                  b.moveTo(2);
                  b.replaceAll('a', 'xx');
                  assert.equal(b.text(), 'xx b xx');
                  assert.equal(b.undo(), true);
                  assert.equal([b.text(), b.cursor].join('|'), 'a b a|2');
                  assert.equal(b.undo(), false);
                  assert.equal(b.redo(), true);
                  assert.equal(b.text(), 'xx b xx');
                  const none = new Buffer('abc');
                  none.replaceAll('q', 'z');
                  assert.equal(none.canUndo(), false);
                });
            '''},
            "events": {
                "reqs": ("Undo and redo notify listeners like any change, with the change they actually apply (undoing the removal of `bc` at 1 reports `{ start: 1, removed: '', inserted: 'bc' }`).",),
                "tests": '''
                    test('undo and redo notify', () => {
                      const b = new Buffer('abcd');
                      b.moveTo(1);
                      b.delete(2);
                      const seen = [];
                      b.onChange((e) => seen.push(e));
                      b.undo();
                      b.redo();
                      assert.deepEqual(seen, [
                        { start: 1, removed: '', inserted: 'bc' },
                        { start: 1, removed: 'bc', inserted: '' },
                      ]);
                    });
                '''},
            "words": {"tests": '''
                test('deleteWord is one undo step', () => {
                  const b = new Buffer('foo  bar baz');
                  b.moveTo(3);
                  b.deleteWord();
                  assert.equal(b.text(), 'foo baz');
                  b.undo();
                  assert.equal([b.text(), b.cursor].join('|'), 'foo  bar baz|3');
                });
            '''},
            "selection": {
                "reqs": ("Undoing an edit that replaced or removed a selection puts the text back, restores that selection and puts the cursor where it was before the edit; redoing it leaves no selection.",),
                "code": {
                    "src/buffer.js::replace_before": "rec.selBefore = this._pendingSel || null;\nthis._pendingSel = null;",
                    "src/buffer.js::after_undo": "this._sel = rec.selBefore ? { from: rec.selBefore.from, to: rec.selBefore.to } : null;",
                },
                "tests": '''
                    test('undo restores a replaced selection', () => {
                      const b = new Buffer('hello world');
                      b.select(6, 11);
                      b.insert('there');
                      assert.equal(b.text(), 'hello there');
                      b.undo();
                      assert.equal(b.text(), 'hello world');
                      assert.deepEqual(b.selection, { from: 6, to: 11 });
                      assert.equal(b.cursor, 11);
                      b.redo();
                      assert.equal(b.text(), 'hello there');
                      assert.equal(b.selection, null);
                      b.select(0, 5);
                      b.delete();
                      b.undo();
                      assert.equal(b.selectedText(), 'hello');
                      b.insert('X');
                      b.undo();
                      assert.deepEqual(b.selection, { from: 0, to: 5 });
                      b.moveTo(2);
                      b.insert('Y');
                      b.undo();
                      assert.equal(b.selection, null);
                    });
                '''},
        },
    ))

    order = ["lines", "max-length", "words", "events", "selection", "search", "undo"]
    S.sort(key=lambda x: order.index(x.id))
    return S


APP = App(
    name="notepad", lang="javascript", title="the editor buffer library", role="an editor plugin author", key="PAD",
    base={
        "README.md": README + "\n@@blocks features\n",
        "package.json": '{\n  "name": "notepad",\n  "version": "1.0.0",\n  "private": true,\n  "main": "index.js",\n  "scripts": {\n    "test": "node --test test/*.test.js"\n  }\n}\n',
        "index.js": "'use strict';\nmodule.exports = require('./src/buffer');\n",
        "src/buffer.js": BUFFER,
        ".gitignore": "node_modules/\n",
    },
    visible={"test/basic.test.js": VISIBLE},
    hidden={"test/features.test.js": HIDDEN},
    verify="node --test test/*.test.js",
)

register_app("feature-js-notepad", APP, make_slices, n=16, summary="editor buffer: lines, limit, words, events, selection, find/replace, undo")
