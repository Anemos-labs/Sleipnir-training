'use strict';
// Running a suite: fixture instances by scope, setup and teardown order, retries, outcomes.
const C = require('./config');

class Failure extends Error {
  constructor(kind, msg) {
    super(msg);
    this.kind = kind; // fail error timeout
    this.msg = msg;
  }
}

const LABEL = { pass: 'PASS', fail: 'FAIL', error: 'ERROR', timeout: 'TIMEOUT', xfail: 'XFAIL', xpass: 'XPASS' };
const KEY = { pass: 'passed', fail: 'failed', error: 'errors', timeout: 'timeouts', xfail: 'xfailed', xpass: 'xpassed' };

function numeric(a, b, op) {
  const num = (x) => (/^-?[0-9]+$/.test(x) ? parseInt(x, 10) : null);
  const x = num(a);
  const y = num(b);
  if (x === null || y === null) return false;
  return op === '<' ? x < y : x > y;
}

class Runner {
  constructor(fixtures, tests, modules, opts, say) {
    this.fixtures = fixtures;
    this.tests = tests;
    this.modules = modules;
    this.opts = opts;
    this.say = say;
    this.clock = 0;
    this.counts = { passed: 0, failed: 0, errors: 0, timeouts: 0, skipped: 0, xfailed: 0, xpassed: 0 };
    this.stop = false;
    this.cache = { module: new Map(), session: new Map() };
    this.stack = { module: [], session: [] };
  }

  runStep(step, ctx) {
    const k = step.kind;
    if (k === 'log') this.say('    log: ' + step.args[0]);
    else if (k === 'tick') {
      this.clock += step.args[0];
      if (ctx !== null) {
        ctx.ticks += step.args[0];
        if (ctx.ticks > C.TIMEOUT) throw new Failure('timeout', `timeout after ${ctx.ticks} ms`);
      }
    } else if (k === 'fail') throw new Failure(ctx !== null ? 'fail' : 'error', step.args[0] || 'failed');
    else if (k === 'raise') throw new Failure('error', 'raised ' + step.args[0]);
    else if (k === 'flaky') {
      if (ctx.attempt <= step.args[0]) throw new Failure('fail', `flaky failure (attempt ${ctx.attempt})`);
    } else if (k === 'expect') {
      const [name, op, lit] = step.args;
      let got;
      if (name === 'param' && ctx.param !== null) got = ctx.param;
      else if (ctx.values.has(name)) got = ctx.values.get(name);
      else throw new Failure('error', `unknown name '${name}'`);
      const ok = op === '==' ? got === lit : op === '!=' ? got !== lit : numeric(got, lit, op);
      if (!ok) throw new Failure('fail', `expected ${name} ${op} ${lit} but got ${got}`);
    }
  }

  ensure(name, testStack, ctx) {
    const f = this.fixtures.get(name);
    const cache = f.scope === 'test' ? ctx.fixtures : this.cache[f.scope];
    if (cache.has(name)) {
      const inst = cache.get(name);
      if (inst.error !== null) throw new Failure('error', inst.error);
      return;
    }
    for (const dep of f.needs) this.ensure(dep, testStack, ctx);
    this.say('  setup ' + name);
    try {
      for (const step of f.setup) this.runStep(step, null);
    } catch (e) {
      if (!(e instanceof Failure)) throw e;
      const msg = `setup ${name} failed: ${e.msg}`;
      cache.set(name, { error: msg });
      throw new Failure('error', msg);
    }
    cache.set(name, { error: null });
    if (f.scope === 'test') testStack.push(f);
    else this.stack[f.scope].push(f);
  }

  // Tears fixtures down in reverse order; returns the first error message or null.
  teardownList(list) {
    let first = null;
    for (let i = list.length - 1; i >= 0; i--) {
      const f = list[i];
      this.say('  teardown ' + f.name);
      try {
        for (const step of f.teardown) this.runStep(step, null);
      } catch (e) {
        if (!(e instanceof Failure)) throw e;
        if (first === null) first = `teardown ${f.name} failed: ${e.msg}`;
      }
    }
    return first;
  }

  neededClosure(test) {
    const seen = [];
    const go = (n) => {
      if (!seen.includes(n)) {
        seen.push(n);
        for (const d of this.fixtures.get(n).needs) go(d);
      }
    };
    for (const n of test.needs) go(n);
    return seen;
  }

  attempt(test, param, attemptNo) {
    const ctx = { ticks: 0, attempt: attemptNo, param, values: new Map(), fixtures: new Map() };
    const stack = [];
    let outcome = 'pass';
    let msg = '';
    try {
      for (const name of test.needs) this.ensure(name, stack, ctx);
      for (const n of this.neededClosure(test)) ctx.values.set(n, this.fixtures.get(n).value);
      for (const step of test.steps) this.runStep(step, ctx);
    } catch (e) {
      if (!(e instanceof Failure)) throw e;
      outcome = e.kind;
      msg = e.msg;
    }
    const err = this.teardownList(stack);
    if (err !== null && outcome === 'pass') {
      outcome = 'error';
      msg = err;
    }
    return [outcome, msg];
  }

  runOne(test, name, param) {
    if (test.marks.includes('skip') || (C.HAS_SKIP_SLOW && this.opts.skipSlow && test.marks.includes('slow'))) {
      this.say('  SKIP ' + name);
      this.counts.skipped += 1;
      return 'skip';
    }
    const retries = this.opts.retries;
    let k = 0;
    let outcome;
    let msg;
    for (;;) {
      if (k > 0) this.say(`  retry ${k}`);
      [outcome, msg] = this.attempt(test, param, k + 1);
      if (outcome === 'pass' || k >= retries) break;
      k += 1;
    }
    const suffix = k ? ` [retried ${k}]` : '';
    if (test.marks.includes('xfail')) {
      if (outcome === 'fail') outcome = 'xfail';
      else if (outcome === 'pass') outcome = 'xpass';
    }
    this.counts[KEY[outcome]] += 1;
    const tail = msg && outcome !== 'xpass' && outcome !== 'pass' ? ': ' + msg : '';
    this.say(`  ${LABEL[outcome]} ${name}${tail}${suffix}`);
    return outcome;
  }

  expanded() {
    const out = [];
    for (const t of this.tests) {
      if (t.params.length) for (const v of t.params) out.push([t, `${t.name}[${v}]`, v]);
      else out.push([t, t.name, null]);
    }
    return out;
  }

  run() {
    const selected = this.expanded().filter(([, n]) => this.opts.only === null || n.includes(this.opts.only));
    for (const module of this.modules) {
      const mine = selected.filter((x) => x[0].module === module);
      if (!mine.length) continue;
      this.say('module ' + module);
      for (const [t, n, p] of mine) {
        if (this.stop) break;
        const res = this.runOne(t, n, p);
        if (this.opts.failFast && ['fail', 'error', 'timeout', 'xpass'].includes(res)) {
          this.say('  stopped by --fail-fast');
          this.stop = true;
        }
      }
      const err = this.teardownList(this.stack.module);
      this.stack.module = [];
      this.cache.module = new Map();
      if (err) {
        this.say('  ERROR ' + err);
        this.counts.errors += 1;
      }
      if (this.stop) break;
    }
    if (this.stack.session.length) {
      const err = this.teardownList(this.stack.session);
      if (err) {
        this.say('  ERROR ' + err);
        this.counts.errors += 1;
      }
    }
    const c = this.counts;
    this.say(`summary: ${c.passed} passed, ${c.failed} failed, ${c.errors} errors, ${c.timeouts} timeouts, ${c.skipped} skipped, ${c.xfailed} xfailed, ${c.xpassed} xpassed`);
    this.say(`clock: ${this.clock} ms`);
    return c.failed + c.errors + c.timeouts + c.xpassed > 0;
  }
}

module.exports = { Runner };
