"""taskplan (javascript): a project task planner extended with removal, progress, reports, lags, working-day dates, slack and resources."""
import datetime
import random

from fx import dd
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # taskplan

    A tiny critical-path planner for project managers (Node.js, CommonJS, no dependencies). Run the tests with `npm test`
    (`node --test test/*.test.js`).

    ## Layout

    * `index.js`: exports `Plan` and `PlanError`.
    * `src/plan.js`: the planner.

    ## Basics

    * `new Plan(options)`: there are no options yet; unknown options are a `TypeError`.
    * `plan.add(name, days, deps = [])` adds a task and returns a copy of it, `{ name, days, deps }`. The name is a non-empty
      string, `days` a positive integer (`RangeError`), `deps` an array of task names (`TypeError` otherwise); a dependency may name a
      task that is added later, and naming a dependency twice counts once. A name that exists is a `PlanError` with code
      `DUPLICATE`.
    * `plan.get(name)` returns a copy of a task (`PlanError`, code `UNKNOWN`, for an unknown name); `plan.names()` lists the names in
      the order they were added.
    * `plan.order()` returns the task names in a valid working order: a task comes after all its dependencies, and among the
      tasks that are ready the one added first comes first. A dependency on a task that does not exist is a `PlanError` with code
      `UNKNOWN`; a cycle is a `PlanError` with code `CYCLE` whose `tasks` property lists the names that could not be ordered (the
      tasks on a cycle and those waiting for one), in the order they were added.
    * `plan.schedule()` returns an object with an entry `{ start, finish }` for every task, in `order()` order. Time is counted
      in whole days from 0; a task starts when all its dependencies have finished (day 0 for a task without dependencies) and
      finishes `days` later. `plan.duration()` is the latest finish (0 for an empty plan).
    * `PlanError` extends `Error` and has a `code` string.
''')

PLAN = '''\
'use strict';
@@uniq requires

class PlanError extends Error {
  constructor(code, message, extra = {}) {
    super(message);
    this.code = code;
    Object.assign(this, extra);
  }
}

@@blocks helpers

class Plan {
  constructor(options = {}) {
    const rest = { ...options };
    @@slot init_opts
    if (Object.keys(rest).length) throw new TypeError(`unknown option(s): ${Object.keys(rest).sort().join(', ')}`);
    this.tasks = new Map();
    @@slot init
  }

  add(name, days, deps = [], extra = {}) {
    if (typeof name !== 'string' || name === '') throw new TypeError('a task needs a name');
    if (!Number.isInteger(days) || days < 1) throw new RangeError('days must be a positive integer');
    if (!Array.isArray(deps)) throw new TypeError('deps must be an array');
    if (this.tasks.has(name)) throw new PlanError('DUPLICATE', `task already exists: ${name}`);
    const task = { name, days, deps: [] };
    @@default dep_loop
    for (const d of deps) {
      if (typeof d !== 'string') throw new TypeError('a dependency is a task name');
      if (!task.deps.includes(d)) task.deps.push(d);
    }
    @@end
    @@slot add_checks
    this.tasks.set(name, task);
    @@slot on_add
    return this.get(name);
  }

  get(name) {
    const t = this.tasks.get(name);
    if (!t) throw new PlanError('UNKNOWN', `no such task: ${name}`);
    return { name: t.name, days: t.days, deps: [...t.deps] };
  }

  names() {
    return [...this.tasks.keys()];
  }

  order() {
    for (const t of this.tasks.values()) {
      for (const d of t.deps) {
        if (!this.tasks.has(d)) throw new PlanError('UNKNOWN', `${t.name} depends on unknown task ${d}`);
      }
    }
    const placed = new Set();
    const out = [];
    while (out.length < this.tasks.size) {
      const next = [...this.tasks.values()].find((t) => !placed.has(t.name) && t.deps.every((d) => placed.has(d)));
      if (!next) {
        const tasks = this.names().filter((n) => !placed.has(n));
        throw new PlanError('CYCLE', `dependency cycle among: ${tasks.join(', ')}`, { tasks });
      }
      placed.add(next.name);
      out.push(next.name);
    }
    return out;
  }

  @@default lag_method
  _lag() {
    return 0;
  }
  @@end

  schedule() {
    const result = {};
    @@slot schedule_pre
    for (const name of this.order()) {
      const t = this.tasks.get(name);
      let start = 0;
      for (const d of t.deps) start = Math.max(start, result[d].finish + this._lag(t, d));
      @@slot place_task
      result[name] = { start, finish: start + t.days };
      @@slot task_placed
    }
    return result;
  }

  duration() {
    return Math.max(0, ...Object.values(this.schedule()).map((s) => s.finish));
  }

  @@blocks methods
}

module.exports = { Plan, PlanError };
'''

HEAD = '''\
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
@@uniq requires
const { Plan, PlanError } = require('../index.js');

/** design 3, build 5 after design, test 2 after build, docs 2 after design, release 1 after test and docs. */
const mk = (options) => {
  const p = new Plan(options);
  p.add('design', 3);
  p.add('build', 5, ['design']);
  p.add('test', 2, ['build']);
  p.add('docs', 2, ['design']);
  p.add('release', 1, ['test', 'docs']);
  return p;
};
'''

VISIBLE = HEAD + '''
test('order and schedule', () => {
  const p = mk();
  assert.deepEqual(p.order(), ['design', 'build', 'test', 'docs', 'release']);
  assert.deepEqual(p.schedule().release, { start: 10, finish: 11 });
  assert.deepEqual(p.schedule().docs, { start: 3, finish: 5 });
  assert.equal(p.duration(), 11);
});

test('add and get', () => {
  const p = new Plan();
  assert.deepEqual(p.add('a', 2, ['b', 'b']), { name: 'a', days: 2, deps: ['b'] });
  assert.throws(() => p.add('a', 1), (e) => e instanceof PlanError && e.code === 'DUPLICATE');
  assert.throws(() => p.order(), (e) => e.code === 'UNKNOWN');
  assert.throws(() => p.get('zzz'), (e) => e.code === 'UNKNOWN');
  assert.throws(() => p.add('c', 0), RangeError);
});
@@blocks tests
'''

HIDDEN = HEAD + '''
test('base: add validation', () => {
  const p = new Plan();
  for (const bad of ['', null, undefined, 5, {}]) assert.throws(() => p.add(bad, 1), TypeError, String(bad));
  for (const bad of [0, -1, 1.5, '2', null, NaN, Infinity]) assert.throws(() => p.add('x', bad), RangeError, String(bad));
  assert.throws(() => p.add('x', 1, 'a'), TypeError);
  assert.throws(() => p.add('x', 1, [1]), TypeError);
  assert.throws(() => p.add('x', 1, [null]), TypeError);
  assert.throws(() => new Plan({ colour: 'red' }), TypeError);
  assert.deepEqual(p.names(), []);
  const t = p.add('x', 3, ['y', 'z', 'y']);
  assert.deepEqual(t, { name: 'x', days: 3, deps: ['y', 'z'] });
  t.deps.push('hacked');
  assert.deepEqual(p.get('x').deps, ['y', 'z']);
  assert.throws(() => p.add('x', 1), (e) => e instanceof PlanError && e.code === 'DUPLICATE');
  assert.deepEqual(p.names(), ['x']);
  assert.ok(new PlanError('X', 'm') instanceof Error);
  assert.equal(new PlanError('X', 'm').code, 'X');
});

test('base: order', () => {
  const p = new Plan();
  assert.deepEqual(p.order(), []);
  p.add('c', 1, ['b']);
  p.add('b', 1, ['a']);
  p.add('a', 1);
  assert.deepEqual(p.order(), ['a', 'b', 'c']);
  const q = new Plan();
  q.add('x', 1);
  q.add('y', 1);
  q.add('z', 1, ['y', 'x']);
  q.add('w', 1);
  assert.deepEqual(q.order(), ['x', 'y', 'z', 'w']);
  assert.deepEqual(mk().order(), ['design', 'build', 'test', 'docs', 'release']);
  const r = new Plan();
  r.add('late', 1, ['early']);
  r.add('mid', 1);
  r.add('early', 1);
  assert.deepEqual(r.order(), ['mid', 'early', 'late']);
});

test('base: order errors', () => {
  const p = new Plan();
  p.add('ok', 1);
  p.add('a', 1, ['b']);
  p.add('b', 1, ['c']);
  p.add('c', 1, ['a']);
  p.add('waits', 1, ['a']);
  assert.throws(() => p.order(), (e) => e instanceof PlanError && e.code === 'CYCLE' && JSON.stringify(e.tasks) === '["a","b","c","waits"]');
  const s = new Plan();
  s.add('me', 1, ['me']);
  assert.throws(() => s.order(), (e) => e.code === 'CYCLE' && e.tasks.length === 1);
  const u = new Plan();
  u.add('a', 1, ['ghost']);
  assert.throws(() => u.order(), (e) => e.code === 'UNKNOWN' && /ghost/.test(e.message));
  assert.throws(() => u.schedule(), (e) => e.code === 'UNKNOWN');
  u.add('ghost', 2);
  assert.deepEqual(u.order(), ['ghost', 'a']);
});

test('base: schedule', () => {
  const p = mk();
  assert.deepEqual(p.schedule(), {
    design: { start: 0, finish: 3 },
    build: { start: 3, finish: 8 },
    test: { start: 8, finish: 10 },
    docs: { start: 3, finish: 5 },
    release: { start: 10, finish: 11 },
  });
  assert.deepEqual(Object.keys(p.schedule()), ['design', 'build', 'test', 'docs', 'release']);
  assert.equal(p.duration(), 11);
  assert.equal(new Plan().duration(), 0);
  assert.deepEqual(new Plan().schedule(), {});
  const q = new Plan();
  q.add('a', 4);
  q.add('b', 2);
  q.add('c', 1, ['a', 'b']);
  assert.deepEqual(q.schedule().c, { start: 4, finish: 5 });
  assert.equal(q.duration(), 5);
  q.add('long', 9);
  assert.equal(q.duration(), 9);
});
@@blocks tests
'''


def iso_work_dates(start_iso, offsets):
    """Reference: the date of each working day offset, weekends skipped."""
    d = datetime.date.fromisoformat(start_iso)
    while d.weekday() >= 5:
        d += datetime.timedelta(days=1)
    out = {}
    cur = d
    n = 0
    days = []
    # build a list of enough working days
    while n <= max(offsets) + 1:
        days.append(cur)
        cur += datetime.timedelta(days=1)
        while cur.weekday() >= 5:
            cur += datetime.timedelta(days=1)
        n += 1
    return {o: days[o].isoformat() for o in offsets}


def make_slices(rng: random.Random):
    max_pct = 100
    bar = rng.choice(["#", "*"])
    done_bar = rng.choice(["=", "+"])
    lag_max = rng.choice([10, 30])
    S = []

    S.append(Slice(
        id="remove", title="Removing tasks", d=1,
        pitch=("A task was cancelled and the only way to get rid of it is to rebuild the whole plan.",
               "Planners need to be able to delete a task."),
        reqs=("`plan.remove(name)` deletes a task and returns a copy of it (`{ name, days, deps }`). An unknown name is a `PlanError` with code `UNKNOWN`. A task that other tasks still depend on cannot be removed: that is a `PlanError` with code `BLOCKED` whose `tasks` property lists the dependents in the order they were added, and nothing changes.",),
        code={
            "src/plan.js::methods": '''
                remove(name) {
                  const t = this.get(name);
                  const dependents = [...this.tasks.values()].filter((o) => o.deps.includes(name)).map((o) => o.name);
                  if (dependents.length) {
                    throw new PlanError('BLOCKED', `${name} is needed by ${dependents.join(', ')}`, { tasks: dependents });
                  }
                  @@slot remove_checks
                  this.tasks.delete(name);
                  @@slot on_remove
                  return t;
                }
            ''',
        },
        readme="## Removing tasks\n\n`plan.remove(name)` deletes a task and returns it. Unknown names are `UNKNOWN`; tasks that others depend on are `BLOCKED` (`err.tasks` lists the dependents).\n",
        vtests='''
          test('remove basic', () => {
            const p = mk();
            assert.equal(p.remove('release').name, 'release');
            assert.equal(p.names().includes('release'), false);
          });
        ''',
        tests='''
          test('remove', () => {
            const p = mk();
            assert.deepEqual(p.remove('release'), { name: 'release', days: 1, deps: ['test', 'docs'] });
            assert.deepEqual(p.names(), ['design', 'build', 'test', 'docs']);
            assert.equal(p.duration(), 10);
            assert.deepEqual(p.remove('docs').deps, ['design']);
            assert.deepEqual(p.remove('test').deps, ['build']);
            assert.equal(p.duration(), 8);
            p.add('release', 4, ['build']);
            assert.deepEqual(p.names(), ['design', 'build', 'release']);
          });

          test('remove errors', () => {
            const p = mk();
            assert.throws(() => p.remove('nope'), (e) => e instanceof PlanError && e.code === 'UNKNOWN');
            assert.throws(() => p.remove('design'), (e) => e.code === 'BLOCKED' && JSON.stringify(e.tasks) === '["build","docs"]');
            assert.throws(() => p.remove('build'), (e) => e.code === 'BLOCKED' && JSON.stringify(e.tasks) === '["test"]');
            assert.deepEqual(p.names(), ['design', 'build', 'test', 'docs', 'release']);
            assert.equal(p.duration(), 11);
            const q = new Plan();
            q.add('a', 1, ['ghost']);
            assert.throws(() => q.remove('ghost'), (e) => e.code === 'UNKNOWN');
            assert.deepEqual(q.remove('a').deps, ['ghost']);
          });
        ''',
    ))

    S.append(Slice(
        id="progress", title="Progress tracking", d=2,
        pitch=("The weekly status mail needs to say how far along the project is and nobody keeps count.",
               "Managers want to mark tasks as done and see how much of the work is complete."),
        reqs=("`plan.complete(name)` marks a task as done (marking it again is fine; unknown names are a `PlanError` with code `UNKNOWN`) and `plan.isComplete(name)` tells. `plan.remaining()` lists the names of the tasks that are not done, in `order()` order. `plan.percentDone()` is the share of finished work: the days of the done tasks divided by the days of all tasks, as a whole percentage rounded half up (0 for an empty plan).",),
        code={
            "src/plan.js::init": "this.done = new Set();",
            "src/plan.js::methods": '''
                complete(name) {
                  this.get(name);
                  this.done.add(name);
                }

                isComplete(name) {
                  this.get(name);
                  return this.done.has(name);
                }

                remaining() {
                  return this.order().filter((n) => !this.done.has(n));
                }

                percentDone() {
                  let all = 0;
                  let done = 0;
                  for (const t of this.tasks.values()) {
                    all += t.days;
                    if (this.done.has(t.name)) done += t.days;
                  }
                  return all === 0 ? 0 : Math.floor((done * 100) / all + 0.5);
                }
            ''',
        },
        readme="## Progress tracking\n\n`complete(name)`, `isComplete(name)`, `remaining()` (in `order()` order) and `percentDone()` (done days over all days, whole percent, half up).\n",
        vtests='''
          test('progress basic', () => {
            const p = mk();
            p.complete('design');
            assert.equal(p.isComplete('design'), true);
            assert.deepEqual(p.remaining(), ['build', 'test', 'docs', 'release']);
          });
        ''',
        tests='''
          test('progress', () => {
            const p = mk();
            assert.equal(p.percentDone(), 0);
            assert.equal(p.isComplete('docs'), false);
            p.complete('design');
            p.complete('design');
            assert.equal(p.percentDone(), 23);
            p.complete('docs');
            assert.equal(p.percentDone(), 38);
            assert.deepEqual(p.remaining(), ['build', 'test', 'release']);
            p.complete('build');
            p.complete('test');
            assert.equal(p.percentDone(), 92);
            p.complete('release');
            assert.equal(p.percentDone(), 100);
            assert.deepEqual(p.remaining(), []);
            assert.equal(new Plan().percentDone(), 0);
            const q = new Plan();
            q.add('a', 1);
            q.add('b', 2);
            q.complete('a');
            assert.equal(q.percentDone(), 33);
            q.add('c', 2);
            q.complete('c');
            assert.equal(q.percentDone(), 60);
            const r = new Plan();
            r.add('a', 1);
            r.add('b', 1);
            r.add('c', 1);
            r.add('d', 1);
            r.add('e', 1);
            r.add('f', 1);
            r.add('g', 1);
            r.add('h', 1);
            r.complete('a');
            assert.equal(r.percentDone(), 13);
            r.complete('b');
            r.complete('c');
            assert.equal(r.percentDone(), 38);
          });

          test('progress errors', () => {
            const p = mk();
            assert.throws(() => p.complete('nope'), (e) => e instanceof PlanError && e.code === 'UNKNOWN');
            assert.throws(() => p.isComplete('nope'), (e) => e.code === 'UNKNOWN');
            assert.equal(p.percentDone(), 0);
          });
        ''',
        cross={
            "remove": {
                "reqs": ("Removing a task also forgets that it was done.",),
                "tests": '''
                  test('removed tasks are forgotten', () => {
                    const p = mk();
                    p.complete('release');
                    p.remove('release');
                    p.add('release', 1);
                    assert.equal(p.isComplete('release'), false);
                    assert.equal(p.percentDone(), 0);
                  });
                ''',
                "code": {"src/plan.js::on_remove": "this.done.delete(name);"},
            },
        },
    ))

    S.append(Slice(
        id="report", title="Text report", d=2,
        pitch=("The steering committee gets the plan as a plain-text mail and the raw object dump is unreadable.",
               "Planners want a printable overview of the schedule with bars."),
        reqs=(f"`plan.toText()` returns one line per task in `order()` order, each ending in a newline: the name padded on the right to the width of the longest name, a space, the start day right-aligned in 3 characters, a space, the finish day right-aligned in 3 characters, a space, then as many spaces as the start day and `{bar}` characters as the task has days (so the bars line up like a Gantt chart). An empty plan gives `''`.",),
        code={
            "src/plan.js::methods": f'''
                toText() {{
                  const sched = this.schedule();
                  const names = Object.keys(sched);
                  const width = Math.max(0, ...names.map((n) => n.length));
                  let out = '';
                  for (const name of names) {{
                    const s = sched[name];
                    let barText = '{bar}'.repeat(s.finish - s.start);
                    @@slot bar_text
                    out += `${{name.padEnd(width)}} ${{String(s.start).padStart(3)}} ${{String(s.finish).padStart(3)}} ${{' '.repeat(s.start)}}${{barText}}\\n`;
                  }}
                  return out;
                }}
            ''',
        },
        readme=f"## Text report\n\n`plan.toText()` prints `NAME START FINISH BAR` per task (bars of `{bar}`, one per day, indented by the start day).\n",
        vtests='''
          test('report basic', () => {
            const p = mk();
            assert.equal(p.toText().split('\\n')[0].startsWith('design'), true);
          });
        ''',
        tests=f'''
          test('report', () => {{
            const p = mk();
            const b = '{bar}';
            assert.equal(
              p.toText(),
              `design    0   3 ${{b.repeat(3)}}\\nbuild     3   8    ${{b.repeat(5)}}\\ntest      8  10         ${{b.repeat(2)}}\\ndocs      3   5    ${{b.repeat(2)}}\\nrelease  10  11           ${{b}}\\n`,
            );
            assert.equal(new Plan().toText(), '');
            const q = new Plan();
            q.add('x', 1);
            assert.equal(q.toText(), `x   0   1 ${{b}}\\n`);
          }});
        ''',
        cross={
            "progress": {
                "reqs": (f"Finished tasks are drawn with `{done_bar}` instead of `{bar}`.",),
                "code": {"src/plan.js::bar_text": f"if (this.done.has(name)) barText = '{done_bar}'.repeat(s.finish - s.start);"},
                "tests": f'''
                  test('report marks finished tasks', () => {{
                    const p = mk();
                    p.complete('design');
                    p.complete('docs');
                    const lines = p.toText().split('\\n');
                    assert.equal(lines[0], 'design    0   3 {done_bar * 3}');
                    assert.equal(lines[1], 'build     3   8    {bar * 5}');
                    assert.equal(lines[3], 'docs      3   5    {done_bar * 2}');
                  }});
                '''},
        },
    ))

    S.append(Slice(
        id="lag", title="Dependency lags", d=2,
        pitch=("Concrete has to cure for four days before the next task can start, and the plan can't say so.",
               "Some dependencies need a waiting time between the end of one task and the start of the next."),
        reqs=(f"A dependency can be written as `{{ name, lag }}` instead of a plain name: the dependent task starts `lag` days after that dependency has finished (`lag` is an integer from 0 to {lag_max}, otherwise `RangeError`; an object without a string `name` is a `TypeError`). Plain names have lag 0. Naming a dependency twice keeps it once with the largest lag. `plan.get(name).deps` still lists plain names.",
              "`plan.lagOf(task, dep)` returns the lag of a dependency (`PlanError` with code `UNKNOWN` when the task does not exist or `dep` is not one of its dependencies). `schedule()` starts a task at the latest of `finish + lag` over its dependencies."),
        code={
            "src/plan.js::init": "this.lags = new Map();",
            "src/plan.js::dep_loop": f'''
                const lags = {{}};
                for (const d of deps) {{
                  const dep = typeof d === 'string' ? {{ name: d, lag: 0 }} : d;
                  if (typeof dep !== 'object' || dep === null || typeof dep.name !== 'string') throw new TypeError('a dependency is a task name or {{ name, lag }}');
                  const lag = dep.lag === undefined ? 0 : dep.lag;
                  if (!Number.isInteger(lag) || lag < 0 || lag > {lag_max}) throw new RangeError('lag must be an integer from 0 to {lag_max}');
                  if (!task.deps.includes(dep.name)) task.deps.push(dep.name);
                  lags[dep.name] = Math.max(lags[dep.name] || 0, lag);
                }}
            ''',
            "src/plan.js::on_add": "this.lags.set(name, lags);",
            "src/plan.js::lag_method": '''
                _lag(task, dep) {
                  return (this.lags.get(task.name) || {})[dep] || 0;
                }
            ''',
            "src/plan.js::methods": '''
                lagOf(task, dep) {
                  const t = this.tasks.get(task);
                  if (!t || !t.deps.includes(dep)) throw new PlanError('UNKNOWN', `${task} does not depend on ${dep}`);
                  return this._lag(t, dep);
                }
            ''',
        },
        readme=f"## Dependency lags\n\nDependencies may be `{{ name, lag }}` (lag 0 to {lag_max} days of waiting after the dependency finished); `lagOf(task, dep)` returns it and `schedule()` honours it.\n",
        vtests='''
          test('lag basic', () => {
            const p = new Plan();
            p.add('pour', 2);
            p.add('frame', 3, [{ name: 'pour', lag: 4 }]);
            assert.deepEqual(p.schedule().frame, { start: 6, finish: 9 });
          });
        ''',
        tests=fmt('''
          test('lags delay the start', () => {
            const p = new Plan();
            p.add('pour', 2);
            p.add('paint', 1);
            assert.deepEqual(p.add('frame', 3, [{ name: 'pour', lag: 4 }, 'paint']).deps, ['pour', 'paint']);
            p.add('roof', 1, ['frame', { name: 'paint', lag: 7 }]);
            assert.deepEqual(p.schedule(), {
              pour: { start: 0, finish: 2 },
              paint: { start: 0, finish: 1 },
              frame: { start: 6, finish: 9 },
              roof: { start: 9, finish: 10 },
            });
            assert.equal(p.duration(), 10);
            assert.equal(p.lagOf('frame', 'pour'), 4);
            assert.equal(p.lagOf('frame', 'paint'), 0);
            assert.equal(p.lagOf('roof', 'paint'), 7);
            p.add('late', 1, [{ name: 'paint', lag: 1 }, { name: 'paint', lag: 5 }, 'paint', { name: 'paint', lag: 2 }]);
            assert.equal(p.lagOf('late', 'paint'), 5);
            assert.deepEqual(p.get('late').deps, ['paint']);
            assert.deepEqual(p.schedule().late, { start: 6, finish: 7 });
            p.add('top', 1, [{ name: 'pour', lag: __M__ }]);
            assert.deepEqual(p.schedule().top, { start: 2 + __M__, finish: 3 + __M__ });
          });

          test('lag validation', () => {
            const p = new Plan();
            p.add('a', 1);
            for (const bad of [-1, __M__ + 1, 1.5, '2', null, NaN]) {
              assert.throws(() => p.add('b', 1, [{ name: 'a', lag: bad }]), RangeError, String(bad));
            }
            for (const bad of [{ lag: 1 }, { name: 5 }, null, 5, []]) {
              assert.throws(() => p.add('b', 1, [bad]), TypeError, JSON.stringify(bad));
            }
            assert.deepEqual(p.names(), ['a']);
            assert.throws(() => p.lagOf('nope', 'a'), (e) => e instanceof PlanError && e.code === 'UNKNOWN');
            p.add('c', 1);
            assert.throws(() => p.lagOf('c', 'a'), (e) => e.code === 'UNKNOWN');
            assert.deepEqual(p.add('d', 1, [{ name: 'a' }]).deps, ['a']);
            assert.equal(p.lagOf('d', 'a'), 0);
          });
        ''', M=lag_max),
        cross={
            "remove": {
                "reqs": ("Removing a task also removes its lags.",),
                "tests": '''
                  test('removing a task forgets its lags', () => {
                    const p = new Plan();
                    p.add('a', 1);
                    p.add('b', 1, [{ name: 'a', lag: 3 }]);
                    p.remove('b');
                    p.add('b', 1, ['a']);
                    assert.equal(p.lagOf('b', 'a'), 0);
                    assert.deepEqual(p.schedule().b, { start: 1, finish: 2 });
                  });
                ''',
                "code": {"src/plan.js::on_remove": "this.lags.delete(name);"},
            },
        },
    ))

    start_cases = ["2025-09-01", "2025-09-06", "2025-12-29", "2024-02-26"]
    ref = {s: iso_work_dates(s, list(range(0, 14))) for s in start_cases}

    def dates_for(start):
        # offsets for mk(): design 0-3, build 3-8, test 8-10, docs 3-5, release 10-11 (task occupies start..finish-1)
        o = ref[start]
        return {
            "design": (o[0], o[2]), "build": (o[3], o[7]), "test": (o[8], o[9]), "docs": (o[3], o[4]), "release": (o[10], o[10]),
        }

    def js_dates(start):
        d = dates_for(start)
        return "{ " + ", ".join(f"{k}: {{ start: '{a}', end: '{b}' }}" for k, (a, b) in d.items()) + " }"

    S.append(Slice(
        id="calendar", title="Working-day dates", d=3,
        pitch=("The schedule says 'day 8' and the team wants to know which Thursday that is.",
               "Day offsets need to be turned into calendar dates, skipping weekends."),
        reqs=("`plan.dates(startIso)` maps the schedule onto the calendar. `startIso` is a date `YYYY-MM-DD` (anything else, including dates that do not exist such as `2025-02-30`, is a `RangeError`). Working day 0 is that date, or the following Monday when it falls on a Saturday or Sunday; Saturdays and Sundays are skipped when counting further days. The result has an entry `{ start, end }` for every task (ISO dates, in `order()` order): `start` is the date of the task's first working day and `end` the date of its last one (working day `finish - 1`).",),
        code={
            "src/plan.js::helpers": '''
                function workingDays(startIso, count) {
                  const m = /^(\\d{4})-(\\d{2})-(\\d{2})$/.exec(startIso);
                  const d = m ? new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]))) : null;
                  if (!d || d.toISOString().slice(0, 10) !== startIso) throw new RangeError(`bad date: ${startIso}`);
                  const out = [];
                  while (out.length < count) {
                    const wd = d.getUTCDay();
                    if (wd !== 0 && wd !== 6) out.push(d.toISOString().slice(0, 10));
                    d.setUTCDate(d.getUTCDate() + 1);
                  }
                  return out;
                }
            ''',
            "src/plan.js::methods": '''
                dates(startIso) {
                  const sched = this.schedule();
                  const days = workingDays(startIso, this.duration() + 1);
                  const out = {};
                  for (const [name, s] of Object.entries(sched)) out[name] = { start: days[s.start], end: days[s.finish - 1] };
                  return out;
                }
            ''',
        },
        readme="## Working-day dates\n\n`plan.dates('YYYY-MM-DD')` returns `{ start, end }` dates per task: working day 0 is the given date (or the next Monday on a weekend), weekends are skipped, `end` is the date of the task's last working day.\n",
        vtests=f'''
          test('dates basic', () => {{
            const d = mk().dates('2025-09-01');
            assert.equal(d.design.start, '{ref["2025-09-01"][0]}');
          }});
        ''',
        tests=fmt('''
          test('dates skip weekends', () => {
            assert.deepEqual(mk().dates('2025-09-01'), __A__);
            assert.deepEqual(mk().dates('2024-02-26'), __D__);
            assert.deepEqual(mk().dates('2025-12-29'), __C__);
            assert.deepEqual(Object.keys(mk().dates('2025-09-01')), ['design', 'build', 'test', 'docs', 'release']);
          });

          test('dates starting on a weekend', () => {
            assert.deepEqual(mk().dates('2025-09-06'), __B__);
            assert.deepEqual(mk().dates('2025-09-07'), __B__);
            assert.deepEqual(new Plan().dates('2025-09-06'), {});
          });

          test('dates validation', () => {
            const p = mk();
            for (const bad of ['2025-02-30', '2025-13-01', '2025-9-1', '01.09.2025', '', null, 20250901, '2025-09-01T00:00', '2025-00-10', '2025-04-31']) {
              assert.throws(() => p.dates(bad), RangeError, String(bad));
            }
            assert.deepEqual(p.dates('2024-02-29').design.start, '2024-02-29');
          });
        ''', A=js_dates("2025-09-01"), B=js_dates("2025-09-06"), C=js_dates("2025-12-29"), D=js_dates("2024-02-26")),
        cross={
            "lag": {
                "reqs": ("Lags count working days.",),
                "tests": '''
                  test('lags are working days', () => {
                    const p = new Plan();
                    p.add('pour', 3);
                    p.add('frame', 2, [{ name: 'pour', lag: 3 }]);
                    assert.deepEqual(p.dates('2025-09-01'), {
                      pour: { start: '2025-09-01', end: '2025-09-03' },
                      frame: { start: '2025-09-09', end: '2025-09-10' },
                    });
                  });
                '''},
        },
    ))

    S.append(Slice(
        id="slack", title="Slack and critical tasks", d=3,
        pitch=("Everyone argues about which tasks can slip without delaying the release.",
               "Planners need to know how much each task can be delayed and which tasks are critical."),
        reqs=("`plan.slack(name)` is the number of days a task can start later than its earliest start without delaying the end of the project (`PlanError` with code `UNKNOWN` for an unknown name). The latest finish of a task is the earliest of the latest starts of the tasks that depend on it (a task nobody depends on may finish as late as the project duration); the slack is the latest start minus the earliest start.",
              "`plan.criticalTasks()` lists the names of the tasks with slack 0 in `order()` order."),
        code={
            "src/plan.js::methods": '''
                _latest() {
                  const order = this.order();
                  const sched = {};
                  let end = 0;
                  for (const name of order) {
                    const t = this.tasks.get(name);
                    let start = 0;
                    for (const d of t.deps) start = Math.max(start, sched[d].finish + this._lag(t, d));
                    sched[name] = { start, finish: start + t.days };
                    end = Math.max(end, start + t.days);
                  }
                  const latestFinish = {};
                  for (const name of [...order].reverse()) {
                    let lf = end;
                    for (const o of this.tasks.values()) {
                      if (o.deps.includes(name)) lf = Math.min(lf, latestFinish[o.name] - o.days - this._lag(o, name));
                    }
                    latestFinish[name] = lf;
                  }
                  return { sched, latestFinish };
                }

                slack(name) {
                  const t = this.get(name);
                  const { sched, latestFinish } = this._latest();
                  return latestFinish[name] - t.days - sched[name].start;
                }

                criticalTasks() {
                  return this.order().filter((n) => this.slack(n) === 0);
                }
            ''',
        },
        readme="## Slack and critical tasks\n\n`slack(name)` is latest start minus earliest start; `criticalTasks()` lists the tasks without slack in `order()` order.\n",
        vtests='''
          test('slack basic', () => {
            assert.equal(mk().slack('docs'), 5);
          });
        ''',
        tests='''
          test('slack', () => {
            const p = mk();
            assert.deepEqual(['design', 'build', 'test', 'docs', 'release'].map((n) => p.slack(n)), [0, 0, 0, 5, 0]);
            assert.deepEqual(p.criticalTasks(), ['design', 'build', 'test', 'release']);
            p.add('audit', 2, ['design']);
            assert.equal(p.slack('audit'), 6);
            p.add('long', 20);
            assert.equal(p.slack('long'), 0);
            assert.deepEqual(p.criticalTasks(), ['long']);
            assert.equal(p.slack('release'), 9);
            assert.equal(p.slack('design'), 9);
          });

          test('slack with parallel chains', () => {
            const p = new Plan();
            p.add('a1', 2);
            p.add('a2', 3, ['a1']);
            p.add('b1', 3);
            p.add('b2', 2, ['b1']);
            p.add('end', 1, ['a2', 'b2']);
            assert.deepEqual(['a1', 'a2', 'b1', 'b2', 'end'].map((n) => p.slack(n)), [0, 0, 0, 0, 0]);
            assert.deepEqual(p.criticalTasks(), ['a1', 'a2', 'b1', 'b2', 'end']);
            p.add('c', 1, ['a1']);
            assert.equal(p.slack('c'), 3);
            const q = new Plan();
            assert.deepEqual(q.criticalTasks(), []);
            q.add('only', 3);
            assert.equal(q.slack('only'), 0);
            assert.throws(() => q.slack('nope'), (e) => e instanceof PlanError && e.code === 'UNKNOWN');
          });
        ''',
        cross={
            "lag": {
                "reqs": ("Lags are part of the calculation: a lag makes the dependency chain longer.",),
                "tests": '''
                  test('slack honours lags', () => {
                    const p = new Plan();
                    p.add('pour', 2);
                    p.add('frame', 3, [{ name: 'pour', lag: 4 }]);
                    p.add('paint', 1);
                    p.add('finish', 1, ['frame', 'paint']);
                    assert.equal(p.duration(), 10);
                    assert.deepEqual(['pour', 'frame', 'paint', 'finish'].map((n) => p.slack(n)), [0, 0, 8, 0]);
                    assert.deepEqual(p.criticalTasks(), ['pour', 'frame', 'finish']);
                  });
                '''},
        },
    ))

    S.append(Slice(
        id="resources", title="Limited workers", d=4,
        pitch=("The plan has six tasks running in parallel and the team has two people.",
               "The planner should respect the number of people available."),
        reqs=("`new Plan({ workers: n })` limits how many people work at the same time (`n` an integer of at least 1, `RangeError` otherwise; the default is no limit). `plan.add(name, days, deps, { needs })` takes a fourth argument with the number of people the task needs on every day (an integer of at least 1, default 1; more than `workers` is a `RangeError`; an unknown key is a `TypeError`).",
              "With a limit, `schedule()` places the tasks one by one in `order()` order. A task cannot start before its dependencies are done (plus lags, if there are any) and, within that, it starts on the earliest day from which it fits: on each of its `days` days the people already placed plus its own `needs` must not exceed `workers`. Earlier gaps are used when a task fits into them. `duration()` and everything built on `schedule()` follow."),
        code={
            "src/plan.js::init_opts": '''
                this.workers = Infinity;
                if (rest.workers !== undefined) {
                  if (!Number.isInteger(rest.workers) || rest.workers < 1) throw new RangeError('workers must be an integer of at least 1');
                  this.workers = rest.workers;
                  delete rest.workers;
                }
            ''',
            "src/plan.js::add_checks": '''
                task.needs = 1;
                for (const k of Object.keys(extra)) {
                  if (k !== 'needs') throw new TypeError(`unknown task option: ${k}`);
                }
                if (extra.needs !== undefined) {
                  if (!Number.isInteger(extra.needs) || extra.needs < 1) throw new RangeError('needs must be an integer of at least 1');
                  if (extra.needs > this.workers) throw new RangeError('the task needs more people than there are');
                  task.needs = extra.needs;
                }
            ''',
            "src/plan.js::schedule_pre": "const usage = [];",
            "src/plan.js::place_task": '''
                if (this.workers !== Infinity) {
                  const fits = (s) => {
                    for (let day = s; day < s + t.days; day++) if ((usage[day] || 0) + t.needs > this.workers) return false;
                    return true;
                  };
                  while (!fits(start)) start += 1;
                }
            ''',
            "src/plan.js::task_placed": '''
                for (let day = start; day < start + t.days; day++) usage[day] = (usage[day] || 0) + t.needs;
            ''',
        },
        readme="## Limited workers\n\n`new Plan({ workers: n })` and `plan.add(name, days, deps, { needs })`: `schedule()` places tasks in `order()` order on the earliest day from which the people placed plus `needs` never exceed `workers`; gaps are reused.\n",
        vtests='''
          test('workers basic', () => {
            const p = new Plan({ workers: 1 });
            p.add('a', 2);
            p.add('b', 2);
            assert.equal(p.duration(), 4);
          });
        ''',
        tests='''
          function sized(workers) {
            const p = new Plan({ workers });
            p.add('design', 3);
            p.add('build', 5, ['design'], { needs: Math.min(2, workers) });
            p.add('test', 2, ['build']);
            p.add('docs', 2, ['design']);
            p.add('release', 1, ['test', 'docs']);
            return p;
          }

          test('two workers', () => {
            const p = sized(2);
            assert.deepEqual(p.schedule(), {
              design: { start: 0, finish: 3 },
              build: { start: 3, finish: 8 },
              test: { start: 8, finish: 10 },
              docs: { start: 8, finish: 10 },
              release: { start: 10, finish: 11 },
            });
            assert.equal(p.duration(), 11);
          });

          test('one worker', () => {
            const p = sized(1);
            assert.deepEqual(p.schedule(), {
              design: { start: 0, finish: 3 },
              build: { start: 3, finish: 8 },
              test: { start: 8, finish: 10 },
              docs: { start: 10, finish: 12 },
              release: { start: 12, finish: 13 },
            });
            assert.equal(p.duration(), 13);
            assert.equal(mk().duration(), 11);
            assert.equal(sized(5).duration(), 11);
          });

          test('earlier gaps are used', () => {
            const p = new Plan({ workers: 2 });
            p.add('long', 4);
            p.add('wide', 2, [], { needs: 2 });
            p.add('short', 1);
            p.add('also', 1, ['short']);
            assert.deepEqual(p.schedule(), {
              long: { start: 0, finish: 4 },
              wide: { start: 4, finish: 6 },
              short: { start: 0, finish: 1 },
              also: { start: 1, finish: 2 },
            });
            const q = new Plan({ workers: 3 });
            q.add('a', 2, [], { needs: 2 });
            q.add('b', 2, [], { needs: 2 });
            q.add('c', 1);
            q.add('d', 3, [], { needs: 3 });
            assert.deepEqual(q.schedule(), {
              a: { start: 0, finish: 2 },
              b: { start: 2, finish: 4 },
              c: { start: 0, finish: 1 },
              d: { start: 4, finish: 7 },
            });
          });

          test('worker option validation', () => {
            for (const bad of [0, -1, 1.5, '2', null, NaN, Infinity]) assert.throws(() => new Plan({ workers: bad }), RangeError, String(bad));
            assert.throws(() => new Plan({ colour: 'red' }), TypeError);
            const p = new Plan({ workers: 2 });
            assert.throws(() => p.add('x', 1, [], { needs: 3 }), RangeError);
            assert.throws(() => p.add('x', 1, [], { needs: 0 }), RangeError);
            assert.throws(() => p.add('x', 1, [], { needs: 1.5 }), RangeError);
            assert.throws(() => p.add('x', 1, [], { color: 1 }), TypeError);
            assert.deepEqual(p.names(), []);
            p.add('x', 1, [], { needs: 2 });
            const free = new Plan();
            free.add('big', 2, [], { needs: 50 });
            free.add('big2', 2, [], { needs: 50 });
            assert.equal(free.duration(), 2);
          });
        ''',
        cross={
            "slack": {
                "reqs": ("Slack ignores the worker limit: it is computed from the dependencies alone, so a task that was pushed back by the limit can still show slack 0 or more as if people were unlimited.",),
                "tests": '''
                  test('slack ignores the worker limit', () => {
                    const p = new Plan({ workers: 1 });
                    p.add('a', 3);
                    p.add('b', 3);
                    p.add('end', 1, ['a', 'b']);
                    assert.equal(p.duration(), 7);
                    assert.equal(p.slack('a'), 0);
                    assert.equal(p.slack('b'), 0);
                    assert.deepEqual(p.criticalTasks(), ['a', 'b', 'end']);
                  });
                '''},
            "lag": {"tests": '''
                test('lags and workers', () => {
                  const p = new Plan({ workers: 1 });
                  p.add('a', 2);
                  p.add('b', 1, [{ name: 'a', lag: 2 }]);
                  p.add('c', 2);
                  assert.deepEqual(p.schedule(), {
                    a: { start: 0, finish: 2 },
                    b: { start: 4, finish: 5 },
                    c: { start: 2, finish: 4 },
                  });
                });
            '''},
        },
    ))

    return S


APP = App(
    name="taskplan", lang="javascript", title="the project planner library", role="a project manager", key="PLAN",
    base={
        "README.md": README + "\n@@blocks features\n",
        "package.json": '{\n  "name": "taskplan",\n  "version": "1.0.0",\n  "private": true,\n  "main": "index.js",\n  "scripts": {\n    "test": "node --test test/*.test.js"\n  }\n}\n',
        "index.js": "'use strict';\nmodule.exports = require('./src/plan');\n",
        "src/plan.js": PLAN,
        ".gitignore": "node_modules/\n",
    },
    visible={"test/basic.test.js": VISIBLE},
    hidden={"test/features.test.js": HIDDEN},
    verify="node --test test/*.test.js",
)

register_app("feature-js-taskplan", APP, make_slices, n=18, summary="critical-path planner: removal, progress, text report, lags, working-day dates, slack, limited workers")
