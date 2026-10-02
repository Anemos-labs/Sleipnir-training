"""Turn-order tracker for a tabletop skirmish game (javascript): bugs injected into an initiative-tracker library."""
from fx import Lib, dd
from generators.fix._lang2 import JS_VERIFY, PACKAGE_JSON, register_libs

README = dd(r'''
    # initiative

    The turn tracker of the *Embergate* skirmish game. CommonJS: `const { Tracker, compare } = require('./src/tracker')`.

    ## Order

    A combatant is `{ id, name, init, dex, side }`. `init` is a finite number, `id` a non-empty string; `name` defaults to
    the id, `dex` to `0` and `side` to `'foe'`. `compare(a, b)` orders combatants for play (negative: `a` acts first):

    1. higher `init` first, then higher `dex`;
    2. then by side: `'party'` before `'foe'` before any other side;
    3. then by `id`, lower first (plain `<` comparison).

    ## `new Tracker()`

    * `add(input)` returns the stored combatant (`{ id, name, init, dex, side, out: false, conditions: [] }`). A repeated id
      is an `Error`; a bad `id` or `init` is a `TypeError`. The newcomer is inserted before the first combatant it
      sorts ahead of (at the end if there is none). If combat has started and the newcomer is inserted at or before the
      active position, the active position moves along so the same combatant stays active; if the list was empty, the
      newcomer becomes active. Late joiners therefore first act in the next round.
    * `order()` lists the ids in turn order. `current()` is the active combatant, or `null` when combat has not started or
      the combatant at the active position is defeated.
    * `start()` begins round 1 with the first combatant that is not defeated and returns it (`null` if all are defeated).
      Starting twice, or with nobody present, is an `Error`.
    * `next()` ends the active turn and returns `{ active, round, expired }`. It requires a started combat (`Error`
      otherwise). First, every condition of the combatant whose turn ends loses one round; conditions that reach `0` are
      removed and reported in `expired` as `{ id, name }` (in the order they were added). Then the turn passes to the next
      combatant after the current position who is not defeated; passing the end of the list wraps to the start and adds one
      to `round`. A lone survivor gets the next turn in a new round. If everybody is defeated, `active` is `null` and the
      round does not change.
    * `addCondition(id, name, rounds)`: `rounds` is an integer `>= 1` (`RangeError`), an unknown id an `Error`. Adding a
      condition the combatant already has keeps the larger remaining count.
    * `defeat(id)` / `revive(id)` set and clear the `out` flag (unknown id: `Error`). They do not move the active position.
    * `remove(id)` takes a combatant out of the list (unknown id: `Error`). Removing someone before the active position
      moves it back by one; removing the active combatant makes the following one active (no conditions tick); if the
      active combatant was last, the first becomes active and `round` goes up by one (when the list is not empty).
    * `delay(afterId)` lets the active combatant wait: it moves to just behind combatant `afterId`, which must come later
      in the order than the active one (otherwise `RangeError`; unknown id: `Error`; before `start()` an `Error`). The
      position now holds the combatant that followed it, who becomes active (skipping defeated ones, no wrap-around, no
      conditions tick). The new order is kept for later rounds. It returns the new active combatant.
    * `status()` returns one entry per combatant in order: `{ id, name, active, out, conditions }` where `active` is true for
      the current combatant and `conditions` is a copy of `[{ name, rounds }]`.
''')

TRACKER = dd(r'''
    'use strict';

    const SIDE_RANK = { party: 0, foe: 1 };

    function sideRank(side) {
      return Object.prototype.hasOwnProperty.call(SIDE_RANK, side) ? SIDE_RANK[side] : 2;
    }

    function compare(a, b) {
      if (a.init !== b.init) return b.init - a.init;
      if (a.dex !== b.dex) return b.dex - a.dex;
      if (sideRank(a.side) !== sideRank(b.side)) return sideRank(a.side) - sideRank(b.side);
      if (a.id === b.id) return 0;
      return a.id < b.id ? -1 : 1;
    }

    class Tracker {
      constructor() {
        this.list = [];
        this.index = 0;
        this.round = 0;
        this.started = false;
      }

      find(id) {
        const i = this.list.findIndex((c) => c.id === id);
        if (i < 0) throw new Error(`unknown combatant ${id}`);
        return i;
      }

      add(input) {
        if (typeof input.id !== 'string' || input.id === '') throw new TypeError('id must be a non-empty string');
        if (typeof input.init !== 'number' || !Number.isFinite(input.init)) throw new TypeError('init must be a finite number');
        if (this.list.some((c) => c.id === input.id)) throw new Error(`duplicate combatant ${input.id}`);
        const c = {
          id: input.id,
          name: input.name || input.id,
          init: input.init,
          dex: input.dex || 0,
          side: input.side || 'foe',
          out: false,
          conditions: [],
        };
        const wasEmpty = this.list.length === 0;
        let pos = this.list.findIndex((o) => compare(c, o) < 0);
        if (pos < 0) pos = this.list.length;
        this.list.splice(pos, 0, c);
        if (wasEmpty) this.index = 0;
        else if (this.started && pos <= this.index) this.index += 1;
        return c;
      }

      order() {
        return this.list.map((c) => c.id);
      }

      current() {
        if (!this.started) return null;
        const c = this.list[this.index];
        return c !== undefined && !c.out ? c : null;
      }

      start() {
        if (this.started) throw new Error('combat already started');
        if (this.list.length === 0) throw new Error('nobody to start with');
        this.started = true;
        this.round = 1;
        this.index = 0;
        while (this.index < this.list.length && this.list[this.index].out) this.index += 1;
        if (this.index === this.list.length) {
          this.index = 0;
          return null;
        }
        return this.list[this.index];
      }

      next() {
        if (!this.started) throw new Error('combat has not started');
        const expired = [];
        const me = this.list[this.index];
        if (me !== undefined) {
          me.conditions = me.conditions.filter((cond) => {
            cond.rounds -= 1;
            if (cond.rounds > 0) return true;
            expired.push({ id: me.id, name: cond.name });
            return false;
          });
        }
        const n = this.list.length;
        for (let step = 1; step <= n; step++) {
          const i = (this.index + step) % n;
          if (!this.list[i].out) {
            this.round += Math.floor((this.index + step) / n);
            this.index = i;
            return { active: this.list[i], round: this.round, expired };
          }
        }
        return { active: null, round: this.round, expired };
      }

      addCondition(id, name, rounds) {
        const c = this.list[this.find(id)];
        if (!Number.isInteger(rounds) || rounds < 1) throw new RangeError('rounds must be an integer >= 1');
        const existing = c.conditions.find((x) => x.name === name);
        if (existing) existing.rounds = Math.max(existing.rounds, rounds);
        else c.conditions.push({ name, rounds });
      }

      defeat(id) {
        this.list[this.find(id)].out = true;
      }

      revive(id) {
        this.list[this.find(id)].out = false;
      }

      remove(id) {
        const pos = this.find(id);
        this.list.splice(pos, 1);
        if (pos < this.index) {
          this.index -= 1;
        } else if (pos === this.index && this.index >= this.list.length) {
          this.index = 0;
          if (this.started && this.list.length > 0) this.round += 1;
        }
      }

      delay(afterId) {
        if (!this.started) throw new Error('combat has not started');
        const target = this.find(afterId);
        const me = this.list[this.index];
        if (me === undefined || target <= this.index) throw new RangeError('can only wait for a later combatant');
        this.list.splice(this.index, 1);
        this.list.splice(target, 0, me);
        while (this.index < this.list.length - 1 && this.list[this.index].out) this.index += 1;
        return this.current();
      }

      status() {
        return this.list.map((c, i) => ({
          id: c.id,
          name: c.name,
          active: this.started && i === this.index && !c.out,
          out: c.out,
          conditions: c.conditions.map((x) => ({ name: x.name, rounds: x.rounds })),
        }));
      }
    }

    module.exports = { Tracker, compare };
''')

VISIBLE = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { Tracker } = require('../src/tracker');

    test('higher initiative acts first', () => {
      const t = new Tracker();
      t.add({ id: 'a', init: 5 });
      t.add({ id: 'b', init: 12 });
      assert.deepEqual(t.order(), ['b', 'a']);
      assert.equal(t.start().id, 'b');
      assert.equal(t.next().active.id, 'a');
    });
''')

HIDDEN = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { Tracker, compare } = require('../src/tracker');

    const SQUAD = [
      { id: 'k', name: 'Knight', init: 15, dex: 3, side: 'party' },
      { id: 'g1', name: 'Goblin', init: 15, dex: 3, side: 'foe' },
      { id: 'a', name: 'Archer', init: 15, dex: 5, side: 'party' },
      { id: 'w', name: 'Wolf', init: 12, dex: 4, side: 'foe' },
      { id: 'm', name: 'Mage', init: 9, dex: 2, side: 'party' },
      { id: 'i', name: 'Imp', init: 9, dex: 2, side: 'party' },
    ];
    // order: a (dex 5), k (party), g1, w, i (id before m), m
    const make = () => {
      const t = new Tracker();
      for (const c of SQUAD) t.add(c);
      return t;
    };
    const ids = (t) => t.order().join(',');

    test('compare: init, dex, side, id', () => {
      const c = (init, dex, side, id) => ({ init, dex, side, id });
      assert.ok(compare(c(10, 0, 'foe', 'b'), c(9, 5, 'party', 'a')) < 0);
      assert.ok(compare(c(9, 5, 'party', 'a'), c(10, 0, 'foe', 'b')) > 0);
      assert.ok(compare(c(10, 3, 'foe', 'b'), c(10, 2, 'party', 'a')) < 0);
      assert.ok(compare(c(10, 2, 'party', 'b'), c(10, 3, 'foe', 'a')) > 0);
      assert.ok(compare(c(10, 2, 'party', 'b'), c(10, 2, 'foe', 'a')) < 0);
      assert.ok(compare(c(10, 2, 'foe', 'b'), c(10, 2, 'party', 'a')) > 0);
      assert.ok(compare(c(10, 2, 'foe', 'b'), c(10, 2, 'neutral', 'a')) < 0);
      assert.ok(compare(c(10, 2, 'neutral', 'a'), c(10, 2, 'foe', 'b')) > 0);
      assert.ok(compare(c(10, 2, 'toString', 'a'), c(10, 2, 'neutral', 'b')) < 0);
      assert.ok(compare(c(10, 2, 'neutral', 'a'), c(10, 2, 'neutral', 'b')) < 0);
      assert.ok(compare(c(10, 2, 'neutral', 'b'), c(10, 2, 'neutral', 'a')) > 0);
      assert.equal(compare(c(10, 2, 'foe', 'a'), c(10, 2, 'foe', 'a')), 0);
      assert.ok(compare(c(10.5, 0, 'foe', 'a'), c(10, 0, 'foe', 'a')) < 0);
    });

    test('add: order and defaults', () => {
      const t = make();
      assert.equal(ids(t), 'a,k,g1,w,i,m');
      const n = new Tracker();
      const c = n.add({ id: 'x', init: 3 });
      assert.deepEqual(c, { id: 'x', name: 'x', init: 3, dex: 0, side: 'foe', out: false, conditions: [] });
      const d = n.add({ id: 'y', name: 'Yak', init: 3.5, dex: 1, side: 'party' });
      assert.deepEqual(n.order(), ['y', 'x']);
      assert.equal(d.name, 'Yak');
    });

    test('add: ties are broken by id when everything else is equal', () => {
      const t = new Tracker();
      t.add({ id: 'b', init: 5 });
      t.add({ id: 'c', init: 5 });
      t.add({ id: 'a', init: 5 });
      assert.equal(ids(t), 'a,b,c');
      t.add({ id: 'B', init: 5 });
      assert.equal(ids(t), 'B,a,b,c');
    });

    test('add: validation', () => {
      const t = new Tracker();
      t.add({ id: 'a', init: 1 });
      assert.throws(() => t.add({ id: 'a', init: 2 }), Error);
      assert.throws(() => t.add({ id: '', init: 2 }), TypeError);
      assert.throws(() => t.add({ id: 5, init: 2 }), TypeError);
      assert.throws(() => t.add({ init: 2 }), TypeError);
      assert.throws(() => t.add({ id: 'b' }), TypeError);
      assert.throws(() => t.add({ id: 'b', init: NaN }), TypeError);
      assert.throws(() => t.add({ id: 'b', init: Infinity }), TypeError);
      assert.throws(() => t.add({ id: 'b', init: '7' }), TypeError);
      assert.deepEqual(t.order(), ['a']);
      assert.doesNotThrow(() => t.add({ id: 'z', init: 0 }));
      assert.doesNotThrow(() => t.add({ id: 'neg', init: -3 }));
    });

    test('start and current', () => {
      const t = make();
      assert.equal(t.current(), null);
      const first = t.start();
      assert.equal(first.id, 'a');
      assert.equal(t.current().id, 'a');
      assert.deepEqual(t.status().map((s) => s.active), [true, false, false, false, false, false]);
      assert.throws(() => t.start(), Error);
      assert.throws(() => new Tracker().start(), Error);
      assert.throws(() => new Tracker().next(), Error);
    });

    test('start skips defeated combatants', () => {
      const t = make();
      t.defeat('a');
      t.defeat('k');
      assert.equal(t.start().id, 'g1');
      const all = make();
      for (const c of SQUAD) all.defeat(c.id);
      assert.equal(all.start(), null);
      assert.equal(all.current(), null);
    });

    test('next walks the order and counts rounds', () => {
      const t = make();
      t.start();
      const seen = [];
      for (let i = 0; i < 13; i++) {
        const r = t.next();
        seen.push(`${r.active.id}${r.round}`);
      }
      assert.deepEqual(seen, ['k1', 'g11', 'w1', 'i1', 'm1', 'a2', 'k2', 'g12', 'w2', 'i2', 'm2', 'a3', 'k3']);
    });

    test('conditions tick at the end of the afflicted combatant turn', () => {
      const t = make();
      t.start();
      t.addCondition('k', 'stunned', 2);
      t.addCondition('k', 'burning', 1);
      t.addCondition('w', 'marked', 1);
      const r1 = t.next();
      assert.equal(r1.active.id, 'k');
      assert.deepEqual(r1.expired, []);
      const r2 = t.next();
      assert.deepEqual(r2.expired, [{ id: 'k', name: 'burning' }]);
      assert.deepEqual(t.status()[1].conditions, [{ name: 'stunned', rounds: 1 }]);
      t.next();
      const r4 = t.next();
      assert.equal(r4.active.id, 'i');
      assert.deepEqual(r4.expired, [{ id: 'w', name: 'marked' }]);
      for (let i = 0; i < 3; i++) t.next();
      assert.equal(t.current().id, 'k');
      const r = t.next();
      assert.deepEqual(r.expired, [{ id: 'k', name: 'stunned' }]);
      assert.deepEqual(t.status()[1].conditions, []);
    });

    test('several conditions expire together in the order they were added', () => {
      const t = make();
      t.start();
      t.addCondition('a', 'x', 1);
      t.addCondition('a', 'y', 1);
      t.addCondition('a', 'z', 2);
      const r = t.next();
      assert.deepEqual(r.expired, [{ id: 'a', name: 'x' }, { id: 'a', name: 'y' }]);
      assert.deepEqual(t.status()[0].conditions, [{ name: 'z', rounds: 1 }]);
    });

    test('adding a condition again keeps the larger count', () => {
      const t = make();
      t.addCondition('a', 'slow', 1);
      t.addCondition('a', 'slow', 3);
      assert.deepEqual(t.status()[0].conditions, [{ name: 'slow', rounds: 3 }]);
      t.addCondition('a', 'slow', 2);
      assert.deepEqual(t.status()[0].conditions, [{ name: 'slow', rounds: 3 }]);
      t.addCondition('a', 'haste', 1);
      assert.deepEqual(t.status()[0].conditions, [{ name: 'slow', rounds: 3 }, { name: 'haste', rounds: 1 }]);
    });

    test('condition errors', () => {
      const t = make();
      assert.throws(() => t.addCondition('a', 'x', 0), RangeError);
      assert.throws(() => t.addCondition('a', 'x', 1.5), RangeError);
      assert.throws(() => t.addCondition('a', 'x', '2'), RangeError);
      assert.throws(() => t.addCondition('nobody', 'x', 1), Error);
      assert.throws(() => t.defeat('nobody'), Error);
      assert.throws(() => t.revive('nobody'), Error);
      assert.throws(() => t.remove('nobody'), Error);
      assert.deepEqual(t.status()[0].conditions, []);
    });

    test('defeated combatants are skipped, revived ones return', () => {
      const t = make();
      t.start();
      t.next();
      t.defeat('g1');
      assert.equal(t.next().active.id, 'w');
      t.revive('g1');
      for (let i = 0; i < 4; i++) t.next();
      assert.equal(t.current().id, 'k');
      assert.equal(t.next().active.id, 'g1');
    });

    test('defeating the active combatant does not advance the turn', () => {
      const t = make();
      t.start();
      t.defeat('a');
      assert.equal(t.current(), null);
      assert.deepEqual(t.status().map((s) => s.active), [false, false, false, false, false, false]);
      assert.equal(t.next().active.id, 'k');
      assert.equal(t.round, 1);
    });

    test('the end of the list wraps even when the tail is defeated', () => {
      const t = make();
      t.defeat('i');
      t.defeat('m');
      t.start();
      const seen = [];
      for (let i = 0; i < 4; i++) {
        const r = t.next();
        seen.push(`${r.active.id}${r.round}`);
      }
      assert.deepEqual(seen, ['k1', 'g11', 'w1', 'a2']);
    });

    test('a lone survivor gets every turn, in a new round each time', () => {
      const t = make();
      t.start();
      for (const id of ['k', 'g1', 'i', 'm']) t.defeat(id);
      t.defeat('a');
      const r1 = t.next();
      assert.equal(r1.active.id, 'w');
      assert.equal(r1.round, 1);
      const r2 = t.next();
      assert.equal(r2.active.id, 'w');
      assert.equal(r2.round, 2);
      const r3 = t.next();
      assert.equal(r3.round, 3);
    });

    test('everybody defeated: next returns no one and the round stays', () => {
      const t = make();
      t.start();
      t.addCondition('a', 'doomed', 1);
      for (const c of SQUAD) t.defeat(c.id);
      const r = t.next();
      assert.equal(r.active, null);
      assert.equal(r.round, 1);
      assert.deepEqual(r.expired, [{ id: 'a', name: 'doomed' }]);
      assert.equal(t.next().round, 1);
    });

    test('a late joiner acts next round and does not steal the turn', () => {
      const t = make();
      t.start();
      t.next();
      assert.equal(t.current().id, 'k');
      t.add({ id: 'z', init: 20 });
      assert.equal(ids(t), 'z,a,k,g1,w,i,m');
      assert.equal(t.current().id, 'k');
      assert.equal(t.next().active.id, 'g1');
      for (let i = 0; i < 3; i++) t.next();
      const wrap = t.next();
      assert.equal(wrap.active.id, 'z');
      assert.equal(wrap.round, 2);
    });

    test('a joiner inserted exactly at the active slot or after it', () => {
      const t = make();
      t.start();
      t.next();
      t.add({ id: 'k2', init: 15, dex: 4, side: 'party' });
      assert.equal(ids(t), 'a,k2,k,g1,w,i,m');
      assert.equal(t.current().id, 'k');
      t.add({ id: 'tail', init: 1 });
      assert.equal(t.current().id, 'k');
      assert.equal(ids(t), 'a,k2,k,g1,w,i,m,tail');
      t.add({ id: 'mid', init: 10 });
      assert.equal(ids(t), 'a,k2,k,g1,w,mid,i,m,tail');
      assert.equal(t.current().id, 'k');
      assert.equal(t.next().active.id, 'g1');
    });

    test('a joiner before combat starts leaves the start untouched', () => {
      const t = new Tracker();
      t.add({ id: 'a', init: 5 });
      t.add({ id: 'b', init: 9 });
      assert.equal(t.start().id, 'b');
    });

    test('adding to an emptied tracker makes the newcomer active', () => {
      const t = new Tracker();
      t.add({ id: 'a', init: 5 });
      t.start();
      t.remove('a');
      assert.equal(t.current(), null);
      t.add({ id: 'b', init: 1 });
      assert.equal(t.current().id, 'b');
    });

    test('remove: before, at and after the active position', () => {
      const t = make();
      t.start();
      t.next();
      t.next();
      assert.equal(t.current().id, 'g1');
      t.remove('a');
      assert.equal(ids(t), 'k,g1,w,i,m');
      assert.equal(t.current().id, 'g1');
      t.remove('m');
      assert.equal(t.current().id, 'g1');
      t.remove('g1');
      assert.equal(ids(t), 'k,w,i');
      assert.equal(t.current().id, 'w');
      assert.equal(t.round, 1);
      assert.equal(t.next().active.id, 'i');
    });

    test('remove the active combatant when it is last', () => {
      const t = make();
      t.start();
      for (let i = 0; i < 5; i++) t.next();
      assert.equal(t.current().id, 'm');
      t.remove('m');
      assert.equal(t.current().id, 'a');
      assert.equal(t.round, 2);
      assert.equal(t.next().active.id, 'k');
    });

    test('remove the only combatant', () => {
      const t = new Tracker();
      t.add({ id: 'a', init: 5 });
      t.start();
      t.remove('a');
      assert.equal(t.current(), null);
      assert.equal(t.round, 1);
      assert.deepEqual(t.order(), []);
    });

    test('removing does not tick conditions', () => {
      const t = make();
      t.start();
      t.next();
      t.addCondition('k', 'x', 1);
      t.addCondition('g1', 'y', 1);
      t.remove('k');
      assert.equal(t.current().id, 'g1');
      assert.deepEqual(t.status().find((s) => s.id === 'g1').conditions, [{ name: 'y', rounds: 1 }]);
      const r = t.next();
      assert.deepEqual(r.expired, [{ id: 'g1', name: 'y' }]);
    });

    test('delay moves the active combatant behind a later one', () => {
      const t = make();
      t.start();
      const next = t.delay('g1');
      assert.equal(next.id, 'k');
      assert.equal(ids(t), 'k,g1,a,w,i,m');
      assert.equal(t.round, 1);
      assert.equal(t.next().active.id, 'g1');
      assert.equal(t.next().active.id, 'a');
      assert.equal(t.next().active.id, 'w');
    });

    test('the delayed order is kept in the next round', () => {
      const t = make();
      t.start();
      t.delay('m');
      assert.equal(ids(t), 'k,g1,w,i,m,a');
      for (let i = 0; i < 5; i++) t.next();
      assert.equal(t.current().id, 'a');
      const r = t.next();
      assert.equal(r.active.id, 'k');
      assert.equal(r.round, 2);
    });

    test('delay does not tick conditions and skips defeated combatants', () => {
      const t = make();
      t.start();
      t.addCondition('a', 'x', 1);
      t.defeat('k');
      const now = t.delay('w');
      assert.equal(now.id, 'g1');
      assert.deepEqual(t.status().find((s) => s.id === 'a').conditions, [{ name: 'x', rounds: 1 }]);
      assert.equal(ids(t), 'k,g1,w,a,i,m');
    });

    test('delay errors', () => {
      const t = make();
      assert.throws(() => t.delay('k'), Error);
      t.start();
      assert.throws(() => t.delay('a'), RangeError);
      t.next();
      assert.throws(() => t.delay('a'), RangeError);
      assert.throws(() => t.delay('k'), RangeError);
      assert.throws(() => t.delay('nobody'), Error);
      assert.equal(ids(t), 'a,k,g1,w,i,m');
      for (let i = 0; i < 4; i++) t.next();
      assert.equal(t.current().id, 'm');
      assert.throws(() => t.delay('i'), RangeError);
    });

    test('status reports copies', () => {
      const t = make();
      t.start();
      t.addCondition('a', 'x', 2);
      const s = t.status();
      assert.deepEqual(s[0], { id: 'a', name: 'Archer', active: true, out: false, conditions: [{ name: 'x', rounds: 2 }] });
      s[0].conditions[0].rounds = 99;
      assert.deepEqual(t.status()[0].conditions, [{ name: 'x', rounds: 2 }]);
      t.defeat('a');
      assert.equal(t.status()[0].out, true);
      assert.equal(t.status()[0].active, false);
    });
''')

LIB = Lib(
    name="initiative", lang="javascript", title="the initiative tracker",
    blurb="The game master's table app uses the initiative tracker to run turn order, conditions and late arrivals in Embergate skirmishes.",
    files={"package.json": PACKAGE_JSON % "initiative", "src/tracker.js": TRACKER, "README.md": README, ".gitignore": "node_modules/\n"},
    visible_tests={"test/basic.test.js": VISIBLE},
    hidden_tests={"test/full.test.js": HIDDEN},
    mutate=["src/tracker.js"], difficulty=4, tags=["games", "turn-order", "state"],
    verify=JS_VERIFY,
)

register_libs([LIB], n=8)
