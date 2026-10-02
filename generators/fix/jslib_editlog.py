"""Undo/redo history with typing coalescing and transactions (javascript): bugs injected into an editor-model library."""
from fx import Lib, dd
from generators.fix._lang2 import JS_VERIFY, PACKAGE_JSON, register_libs

README = dd(r'''
    # editlog

    The document model behind a small text editor: a string with an undo/redo history. CommonJS:
    `const { Editor } = require('./src/editor')`.

    ## `new Editor(initial = '', opts = {}, clock)`

    * `opts.limit` (default `100`): the largest number of undo steps kept; an integer `>= 1` (else `RangeError`). When a
      new step makes the stack longer, the *oldest* steps are dropped.
    * `opts.coalesceMs` (default `1000`): see below.
    * `clock` is any object with `now()` (milliseconds); it defaults to `Date.now`.
    * `text()` is the document; `canUndo()` and `canRedo()` say whether `undo()` / `redo()` would do something.
    * `history()` lists the labels of the undo steps, oldest first (`'type'`, `'erase'`, or the label of a transaction).

    ## Editing

    * `insert(pos, text)`: inserts `text` before index `pos`. `pos` must be an integer in `0..text().length` (else
      `RangeError`). An empty `text` does nothing and leaves no history. The edit is a *typing* edit.
    * `remove(pos, len)`: deletes up to `len` characters starting at `pos` (the count is cut at the end of the document).
      `pos` must be an integer in `0..text().length` (else `RangeError`); `len < 1` or nothing to delete does nothing.
      The edit is an *erase* edit.
    * Every edit clears the redo stack.

    ## Steps and coalescing

    Each edit is one undo step, except that it is *merged into the latest step* when all of the following hold: no
    transaction is open; the latest step is not sealed (below) and has the same kind (`type` or `erase`); at most
    `coalesceMs` milliseconds (inclusive) have passed since the latest step was last extended or created; and the edit is
    adjacent to it:

    * typing: the new text starts exactly where the step's inserted text ends, and neither the new text nor the step's text
      contains a newline `\n`;
    * erase: the edit starts at the same position as the step's deletion (forward delete), or ends exactly where it starts
      (backspace).

    Merging extends the step (so one `undo()` removes a whole run of typing, or restores a whole run of deletions) and
    moves its time stamp to now, so the window slides with every merged edit. A step that was just created gets the time of
    its edit.

    ## Undo and redo

    `undo()` reverts the latest step and returns `true` (`false` when there is none); `redo()` re-applies the latest undone
    step. Calling either while a transaction is open is an `Error`. After `undo()` or `redo()` the step now on top of the undo
    stack is *sealed*: later edits never merge into it.

    ## Transactions

    `begin(label = 'group')` starts grouping; calls nest, and only the outermost one has a label. All edits until the matching
    outermost `end()` become one step with that label, whatever the timing, and never merge with anything. A transaction
    without edits leaves no step. `end()` without `begin()` is an `Error`.

    ## Saved state

    `markSaved()` remembers the current state and seals the latest step; `isDirty()` is `false` exactly while the latest step
    on the undo stack is the one that was latest when `markSaved()` was called (no step at all counts as a state too). A new
    editor is clean. Once the remembered step has been dropped by `limit`, the editor stays dirty.
''')

EDITOR = dd(r'''
    'use strict';

    class Editor {
      constructor(initial = '', opts = {}, clock = { now: () => Date.now() }) {
        this.doc = initial;
        this.limit = opts.limit === undefined ? 100 : opts.limit;
        this.coalesceMs = opts.coalesceMs === undefined ? 1000 : opts.coalesceMs;
        if (!Number.isInteger(this.limit) || this.limit < 1) throw new RangeError('limit must be an integer >= 1');
        this.clock = clock;
        this.undoStack = [];
        this.redoStack = [];
        this.tx = null;
        this.depth = 0;
        this.saveToken = null;
      }

      text() {
        return this.doc;
      }

      canUndo() {
        return this.undoStack.length > 0;
      }

      canRedo() {
        return this.redoStack.length > 0;
      }

      history() {
        return this.undoStack.map((e) => e.label);
      }

      isDirty() {
        return this.top() !== this.saveToken;
      }

      markSaved() {
        this.saveToken = this.top();
        this.seal();
      }

      top() {
        return this.undoStack.length > 0 ? this.undoStack[this.undoStack.length - 1] : null;
      }

      seal() {
        const t = this.top();
        if (t !== null) t.sealed = true;
      }

      apply(op) {
        if (op.type === 'ins') {
          this.doc = this.doc.slice(0, op.pos) + op.text + this.doc.slice(op.pos);
        } else {
          this.doc = this.doc.slice(0, op.pos) + this.doc.slice(op.pos + op.text.length);
        }
      }

      insert(pos, text) {
        this.checkPos(pos);
        if (text === '') return;
        const op = { type: 'ins', pos, text };
        this.apply(op);
        this.record(op, 'type');
      }

      remove(pos, len) {
        this.checkPos(pos);
        const text = this.doc.slice(pos, pos + Math.max(0, len));
        if (text === '') return;
        const op = { type: 'del', pos, text };
        this.apply(op);
        this.record(op, 'erase');
      }

      checkPos(pos) {
        if (!Number.isInteger(pos) || pos < 0 || pos > this.doc.length) throw new RangeError(`position out of range: ${pos}`);
      }

      canMerge(step, op, kind, now) {
        if (step.sealed || step.kind !== kind) return false;
        if (now - step.at > this.coalesceMs) return false;
        const last = step.ops[0];
        if (kind === 'type') {
          return last.pos + last.text.length === op.pos && !op.text.includes('\n') && !last.text.includes('\n');
        }
        return op.pos === last.pos || op.pos + op.text.length === last.pos;
      }

      merge(step, op) {
        const last = step.ops[0];
        if (op.type === 'ins' || op.pos === last.pos) {
          last.text += op.text;
        } else {
          last.pos = op.pos;
          last.text = op.text + last.text;
        }
      }

      record(op, kind) {
        const now = this.clock.now();
        this.redoStack = [];
        if (this.tx !== null) {
          this.tx.ops.push(op);
          return;
        }
        const step = this.top();
        if (step !== null && this.canMerge(step, op, kind, now)) {
          this.merge(step, op);
          step.at = now;
          return;
        }
        this.push({ ops: [op], at: now, kind, label: kind });
      }

      push(step) {
        this.undoStack.push(step);
        while (this.undoStack.length > this.limit) this.undoStack.shift();
      }

      begin(label = 'group') {
        if (this.depth === 0) this.tx = { ops: [], at: this.clock.now(), kind: 'tx', label };
        this.depth += 1;
      }

      end() {
        if (this.depth === 0) throw new Error('end() without begin()');
        this.depth -= 1;
        if (this.depth === 0) {
          const tx = this.tx;
          this.tx = null;
          if (tx.ops.length > 0) this.push(tx);
        }
      }

      undo() {
        if (this.depth > 0) throw new Error('cannot undo inside a transaction');
        const step = this.undoStack.pop();
        if (step === undefined) return false;
        for (let i = step.ops.length - 1; i >= 0; i--) {
          const op = step.ops[i];
          this.apply({ type: op.type === 'ins' ? 'del' : 'ins', pos: op.pos, text: op.text });
        }
        this.redoStack.push(step);
        this.seal();
        return true;
      }

      redo() {
        if (this.depth > 0) throw new Error('cannot redo inside a transaction');
        const step = this.redoStack.pop();
        if (step === undefined) return false;
        for (const op of step.ops) this.apply(op);
        this.undoStack.push(step);
        this.seal();
        return true;
      }
    }

    module.exports = { Editor };
''')

VISIBLE = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { Editor } = require('../src/editor');

    const clock = () => ({ t: 0, now() { return this.t; } });

    test('insert and undo', () => {
      const ed = new Editor('', {}, clock());
      ed.insert(0, 'hello');
      assert.equal(ed.text(), 'hello');
      assert.equal(ed.undo(), true);
      assert.equal(ed.text(), '');
      assert.equal(ed.redo(), true);
      assert.equal(ed.text(), 'hello');
    });
''')

HIDDEN = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { Editor } = require('../src/editor');

    const mk = (initial = '', opts = {}) => {
      const clock = { t: 0, now() { return this.t; } };
      const ed = new Editor(initial, opts, clock);
      return { ed, clock };
    };
    // type text one character at a time at the end of the document, `gap` ms apart
    const typeRun = (ed, clock, text, gap) => {
      for (const ch of text) {
        ed.insert(ed.text().length, ch);
        clock.t += gap;
      }
    };

    test('insert, remove and bounds', () => {
      const { ed } = mk('abc');
      ed.insert(1, 'XY');
      assert.equal(ed.text(), 'aXYbc');
      ed.remove(1, 2);
      assert.equal(ed.text(), 'abc');
      ed.remove(2, 10);
      assert.equal(ed.text(), 'ab');
      assert.throws(() => ed.insert(3, 'x'), RangeError);
      assert.throws(() => ed.insert(-1, 'x'), RangeError);
      assert.throws(() => ed.insert(1.5, 'x'), RangeError);
      assert.throws(() => ed.remove(3, 1), RangeError);
      assert.throws(() => ed.remove(-1, 1), RangeError);
      ed.insert(2, 'z');
      assert.equal(ed.text(), 'abz');
      ed.insert(0, 'q');
      assert.equal(ed.text(), 'qabz');
    });

    test('no-op edits leave no history', () => {
      const { ed } = mk('abc');
      ed.insert(1, '');
      ed.remove(1, 0);
      ed.remove(1, -3);
      ed.remove(3, 2);
      assert.equal(ed.canUndo(), false);
      assert.deepEqual(ed.history(), []);
      assert.equal(ed.text(), 'abc');
    });

    test('undo and redo walk the history', () => {
      const { ed, clock } = mk('');
      ed.insert(0, 'one');
      clock.t += 5000;
      ed.insert(3, ' two');
      clock.t += 5000;
      ed.insert(7, ' three');
      assert.equal(ed.text(), 'one two three');
      assert.equal(ed.undo(), true);
      assert.equal(ed.text(), 'one two');
      assert.equal(ed.undo(), true);
      assert.equal(ed.text(), 'one');
      assert.equal(ed.redo(), true);
      assert.equal(ed.text(), 'one two');
      assert.equal(ed.undo(), true);
      assert.equal(ed.undo(), true);
      assert.equal(ed.text(), '');
      assert.equal(ed.undo(), false);
      assert.equal(ed.canUndo(), false);
      assert.equal(ed.canRedo(), true);
      assert.equal(ed.redo(), true);
      assert.equal(ed.redo(), true);
      assert.equal(ed.redo(), true);
      assert.equal(ed.redo(), false);
      assert.equal(ed.text(), 'one two three');
      assert.equal(ed.canRedo(), false);
    });

    test('a new edit clears the redo stack', () => {
      const { ed, clock } = mk('');
      ed.insert(0, 'a');
      clock.t += 5000;
      ed.insert(1, 'b');
      ed.undo();
      assert.equal(ed.canRedo(), true);
      ed.insert(1, 'c');
      assert.equal(ed.canRedo(), false);
      assert.equal(ed.redo(), false);
      assert.equal(ed.text(), 'ac');
      ed.undo();
      ed.remove(0, 1);
      assert.equal(ed.canRedo(), false);
    });

    test('typing coalesces into one step', () => {
      const { ed, clock } = mk('');
      typeRun(ed, clock, 'hello', 100);
      assert.deepEqual(ed.history(), ['type']);
      ed.undo();
      assert.equal(ed.text(), '');
      ed.redo();
      assert.equal(ed.text(), 'hello');
    });

    test('the coalescing window is inclusive and slides', () => {
      const a = mk('');
      a.ed.insert(0, 'a');
      a.clock.t = 1000;
      a.ed.insert(1, 'b');
      assert.deepEqual(a.ed.history(), ['type']);
      const b = mk('');
      b.ed.insert(0, 'a');
      b.clock.t = 1001;
      b.ed.insert(1, 'b');
      assert.deepEqual(b.ed.history(), ['type', 'type']);
      const c = mk('');
      typeRun(c.ed, c.clock, 'abcdef', 900);
      assert.deepEqual(c.ed.history(), ['type']);
      const d = mk('', { coalesceMs: 50 });
      d.ed.insert(0, 'a');
      d.clock.t = 50;
      d.ed.insert(1, 'b');
      d.clock.t = 101;
      d.ed.insert(2, 'c');
      assert.deepEqual(d.ed.history(), ['type', 'type']);
      d.ed.undo();
      assert.equal(d.ed.text(), 'ab');
    });

    test('a pause starts a new step', () => {
      const { ed, clock } = mk('');
      typeRun(ed, clock, 'ab', 100);
      clock.t += 2000;
      typeRun(ed, clock, 'cd', 100);
      assert.equal(ed.text(), 'abcd');
      ed.undo();
      assert.equal(ed.text(), 'ab');
      ed.undo();
      assert.equal(ed.text(), '');
    });

    test('typing that is not adjacent does not merge', () => {
      const { ed } = mk('');
      ed.insert(0, 'abc');
      ed.insert(0, 'x');
      assert.deepEqual(ed.history(), ['type', 'type']);
      ed.insert(3, 'y');
      assert.deepEqual(ed.history(), ['type', 'type', 'type']);
      ed.undo();
      ed.undo();
      assert.equal(ed.text(), 'abc');
      ed.insert(3, 'd');
      assert.equal(ed.text(), 'abcd');
      ed.insert(1, 'e');
      assert.deepEqual(ed.history(), ['type', 'type', 'type']);
    });

    test('a merged paste continues a typing run', () => {
      const { ed } = mk('');
      ed.insert(0, 'ab');
      ed.insert(2, 'cde');
      ed.insert(5, 'f');
      assert.deepEqual(ed.history(), ['type']);
      ed.undo();
      assert.equal(ed.text(), '');
    });

    test('newlines break typing runs on both sides', () => {
      const { ed } = mk('');
      ed.insert(0, 'a');
      ed.insert(1, '\n');
      assert.deepEqual(ed.history(), ['type', 'type']);
      ed.insert(2, 'b');
      assert.deepEqual(ed.history(), ['type', 'type', 'type']);
      ed.insert(3, 'c');
      assert.deepEqual(ed.history(), ['type', 'type', 'type']);
      ed.undo();
      assert.equal(ed.text(), 'a\n');
      ed.undo();
      assert.equal(ed.text(), 'a');
      const multi = mk('');
      multi.ed.insert(0, 'x');
      multi.ed.insert(1, 'y\nz');
      assert.deepEqual(multi.ed.history(), ['type', 'type']);
    });

    test('backspace runs coalesce and restore together', () => {
      const { ed, clock } = mk('abcdef');
      ed.remove(5, 1);
      clock.t += 100;
      ed.remove(4, 1);
      clock.t += 100;
      ed.remove(3, 1);
      assert.equal(ed.text(), 'abc');
      assert.deepEqual(ed.history(), ['erase']);
      ed.undo();
      assert.equal(ed.text(), 'abcdef');
      ed.redo();
      assert.equal(ed.text(), 'abc');
    });

    test('backspace over longer ranges', () => {
      const { ed } = mk('0123456789');
      ed.remove(8, 2);
      ed.remove(6, 2);
      assert.equal(ed.text(), '012345');
      assert.deepEqual(ed.history(), ['erase']);
      ed.undo();
      assert.equal(ed.text(), '0123456789');
    });

    test('forward delete runs coalesce and restore together', () => {
      const { ed, clock } = mk('abcdef');
      ed.remove(1, 1);
      clock.t += 100;
      ed.remove(1, 1);
      clock.t += 100;
      ed.remove(1, 2);
      assert.equal(ed.text(), 'af');
      assert.deepEqual(ed.history(), ['erase']);
      ed.undo();
      assert.equal(ed.text(), 'abcdef');
      ed.redo();
      assert.equal(ed.text(), 'af');
      ed.undo();
      ed.undo();
      assert.equal(ed.text(), 'abcdef');
    });

    test('erases that are not adjacent do not merge', () => {
      const { ed } = mk('abcdefgh');
      ed.remove(2, 1);
      ed.remove(5, 1);
      assert.deepEqual(ed.history(), ['erase', 'erase']);
      assert.equal(ed.text(), 'abdefh');
      ed.remove(1, 1);
      assert.deepEqual(ed.history(), ['erase', 'erase', 'erase']);
      ed.undo();
      assert.equal(ed.text(), 'abdefh');
    });

    test('erase and typing never merge with each other', () => {
      const { ed } = mk('abc');
      ed.remove(2, 1);
      ed.insert(2, 'x');
      ed.remove(2, 1);
      assert.deepEqual(ed.history(), ['erase', 'type', 'erase']);
      ed.undo();
      ed.undo();
      assert.equal(ed.text(), 'ab');
    });

    test('erase window is inclusive', () => {
      const a = mk('abcdef');
      a.ed.remove(5, 1);
      a.clock.t = 1000;
      a.ed.remove(4, 1);
      assert.deepEqual(a.ed.history(), ['erase']);
      const b = mk('abcdef');
      b.ed.remove(5, 1);
      b.clock.t = 1001;
      b.ed.remove(4, 1);
      assert.deepEqual(b.ed.history(), ['erase', 'erase']);
    });

    test('undo seals the step below: typing after an undo starts a new step', () => {
      const { ed, clock } = mk('', { coalesceMs: 100000 });
      ed.insert(0, 'x');
      clock.t += 10;
      ed.insert(0, 'q');
      assert.equal(ed.text(), 'qx');
      ed.undo();
      assert.equal(ed.text(), 'x');
      ed.insert(1, 'z');
      assert.deepEqual(ed.history(), ['type', 'type']);
      ed.undo();
      assert.equal(ed.text(), 'x');
    });

    test('redo seals the redone step too', () => {
      const { ed, clock } = mk('', { coalesceMs: 100000 });
      ed.insert(0, 'a');
      clock.t += 10;
      ed.undo();
      ed.redo();
      ed.insert(1, 'b');
      assert.deepEqual(ed.history(), ['type', 'type']);
      ed.undo();
      assert.equal(ed.text(), 'a');
    });

    test('transactions group edits', () => {
      const { ed, clock } = mk('abc');
      ed.begin('rename');
      ed.remove(0, 3);
      clock.t += 99999;
      ed.insert(0, 'xyz');
      ed.insert(3, '!');
      ed.end();
      assert.equal(ed.text(), 'xyz!');
      assert.deepEqual(ed.history(), ['rename']);
      ed.undo();
      assert.equal(ed.text(), 'abc');
      ed.redo();
      assert.equal(ed.text(), 'xyz!');
    });

    test('transactions: default label, nesting, empty ones', () => {
      const { ed } = mk('');
      ed.begin();
      ed.insert(0, 'a');
      ed.begin('inner');
      ed.insert(1, 'b');
      ed.end();
      ed.insert(2, 'c');
      assert.deepEqual(ed.history(), []);
      ed.end();
      assert.deepEqual(ed.history(), ['group']);
      assert.equal(ed.text(), 'abc');
      ed.undo();
      assert.equal(ed.text(), '');
      ed.begin('nothing');
      ed.end();
      ed.begin('noop');
      ed.insert(0, '');
      ed.end();
      assert.equal(ed.canUndo(), false);
      assert.equal(ed.canRedo(), true);
    });

    test('transactions undo their operations in reverse order', () => {
      const { ed } = mk('0123456789');
      ed.begin('shuffle');
      ed.remove(2, 3);
      ed.insert(0, 'AB');
      ed.remove(0, 1);
      ed.insert(4, '-');
      ed.end();
      assert.equal(ed.text(), 'B015-6789');
      ed.undo();
      assert.equal(ed.text(), '0123456789');
    });

    test('transaction errors', () => {
      const { ed } = mk('abc');
      assert.throws(() => ed.end(), Error);
      ed.begin();
      assert.throws(() => ed.undo(), Error);
      assert.throws(() => ed.redo(), Error);
      ed.end();
      assert.throws(() => ed.end(), Error);
      ed.begin();
      ed.begin();
      ed.end();
      assert.throws(() => ed.undo(), Error);
      ed.end();
      assert.equal(ed.undo(), false);
    });

    test('a transaction step never merges with the edits around it', () => {
      const { ed } = mk('');
      ed.insert(0, 'a');
      ed.begin('t');
      ed.insert(1, 'b');
      ed.end();
      ed.insert(2, 'c');
      assert.deepEqual(ed.history(), ['type', 't', 'type']);
      ed.undo();
      ed.undo();
      assert.equal(ed.text(), 'a');
    });

    test('a transaction starts fresh even right after typing', () => {
      const { ed } = mk('');
      ed.insert(0, 'a');
      ed.begin('t');
      ed.insert(1, 'b');
      ed.end();
      assert.deepEqual(ed.history(), ['type', 't']);
    });

    test('limit drops the oldest steps', () => {
      const { ed, clock } = mk('', { limit: 3 });
      for (const ch of 'abcde') {
        ed.insert(ed.text().length, ch);
        clock.t += 5000;
      }
      assert.deepEqual(ed.history(), ['type', 'type', 'type']);
      assert.equal(ed.undo(), true);
      assert.equal(ed.undo(), true);
      assert.equal(ed.undo(), true);
      assert.equal(ed.undo(), false);
      assert.equal(ed.text(), 'ab');
      ed.redo();
      ed.redo();
      ed.redo();
      assert.equal(ed.text(), 'abcde');
    });

    test('limit counts transactions as one step and validates', () => {
      const { ed } = mk('', { limit: 2 });
      ed.begin('big');
      ed.insert(0, 'abc');
      ed.insert(3, 'def');
      ed.end();
      ed.insert(6, 'x');
      ed.insert(0, 'y');
      assert.deepEqual(ed.history(), ['type', 'type']);
      assert.throws(() => mk('', { limit: 0 }), RangeError);
      assert.throws(() => mk('', { limit: 2.5 }), RangeError);
      assert.throws(() => mk('', { limit: -1 }), RangeError);
      assert.doesNotThrow(() => mk('', { limit: 1 }));
      const one = mk('', { limit: 1 });
      one.ed.insert(0, 'a');
      one.ed.insert(0, 'b');
      assert.equal(one.ed.undo(), true);
      assert.equal(one.ed.undo(), false);
      assert.equal(one.ed.text(), 'a');
    });

    test('isDirty and markSaved', () => {
      const { ed, clock } = mk('');
      assert.equal(ed.isDirty(), false);
      ed.insert(0, 'a');
      assert.equal(ed.isDirty(), true);
      ed.markSaved();
      assert.equal(ed.isDirty(), false);
      clock.t += 10;
      ed.insert(1, 'b');
      assert.equal(ed.isDirty(), true);
      assert.deepEqual(ed.history(), ['type', 'type']);
      ed.undo();
      assert.equal(ed.isDirty(), false);
      ed.redo();
      assert.equal(ed.isDirty(), true);
      ed.undo();
      ed.undo();
      assert.equal(ed.isDirty(), true);
      ed.redo();
      assert.equal(ed.isDirty(), false);
    });

    test('saving an empty history, and undoing back to it', () => {
      const { ed } = mk('start');
      ed.markSaved();
      assert.equal(ed.isDirty(), false);
      ed.insert(5, '!');
      assert.equal(ed.isDirty(), true);
      ed.undo();
      assert.equal(ed.isDirty(), false);
      const other = mk('start');
      other.ed.insert(5, '!');
      other.ed.markSaved();
      other.ed.undo();
      assert.equal(other.ed.isDirty(), true);
    });

    test('a dropped save point keeps the editor dirty', () => {
      const { ed, clock } = mk('', { limit: 2 });
      ed.insert(0, 'a');
      ed.markSaved();
      for (const ch of 'bcd') {
        clock.t += 5000;
        ed.insert(ed.text().length, ch);
      }
      assert.equal(ed.isDirty(), true);
      ed.undo();
      ed.undo();
      assert.equal(ed.isDirty(), true);
      assert.equal(ed.text(), 'ab');
    });

    test('saving seals the step so later typing is a new one', () => {
      const { ed } = mk('');
      ed.insert(0, 'a');
      ed.markSaved();
      ed.insert(1, 'b');
      assert.deepEqual(ed.history(), ['type', 'type']);
    });

    test('redo of a transaction and of a coalesced run restores everything', () => {
      const { ed, clock } = mk('');
      typeRun(ed, clock, 'abc', 10);
      ed.begin('tx');
      ed.remove(0, 1);
      ed.insert(2, 'Z');
      ed.end();
      assert.equal(ed.text(), 'bcZ');
      ed.undo();
      ed.undo();
      assert.equal(ed.text(), '');
      ed.redo();
      assert.equal(ed.text(), 'abc');
      ed.redo();
      assert.equal(ed.text(), 'bcZ');
    });
''')

LIB = Lib(
    name="editlog", lang="javascript", title="the editlog document model",
    blurb="The note-taking app's editor keeps its text and undo history in editlog.",
    files={"package.json": PACKAGE_JSON % "editlog", "src/editor.js": EDITOR, "README.md": README, ".gitignore": "node_modules/\n"},
    visible_tests={"test/basic.test.js": VISIBLE},
    hidden_tests={"test/full.test.js": HIDDEN},
    mutate=["src/editor.js"], difficulty=2, tags=["editor", "undo", "history"],
    verify=JS_VERIFY,
)

register_libs([LIB], n=8)
