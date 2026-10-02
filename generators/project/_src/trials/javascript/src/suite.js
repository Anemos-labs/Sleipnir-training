'use strict';
// Reader for suite.txt.
const C = require('./config');

const NAME_RE = /^[A-Za-z][A-Za-z0-9_]*$/;
const LITERAL_RE = /^[A-Za-z0-9_.-]{1,16}$/;
const SCOPES = { test: 0, module: 1, session: 2 };

class SuiteError extends Error {}

function fail(n, msg) {
  throw new SuiteError(`suite.txt:${n}: ${msg}`);
}

// `needs A B marks x` -> { needs: [A, B], marks: [x] }; a clause word needs at least one value and may appear once.
function clauses(words, n, allowed) {
  const out = {};
  let cur = null;
  for (const w of words) {
    if (allowed.includes(w)) {
      if (Object.prototype.hasOwnProperty.call(out, w)) fail(n, 'bad line');
      out[w] = [];
      cur = w;
    } else if (cur === null) fail(n, 'bad line');
    else out[cur].push(w);
  }
  if (Object.values(out).some((v) => v.length === 0)) fail(n, 'bad line');
  return out;
}

function parseStep(words, n, where) {
  const kind = words[0];
  const rest = words.slice(1);
  const badStep = () => fail(n, `bad step '${words.join(' ')}'`);
  if (kind === 'log') return { kind: 'log', args: [rest.join(' ')], line: n };
  if (kind === 'fail') return { kind: 'fail', args: [rest.join(' ')], line: n };
  if (kind === 'raise') {
    if (rest.length !== 1 || !NAME_RE.test(rest[0])) badStep();
    return { kind: 'raise', args: rest, line: n };
  }
  if (kind === 'tick') {
    if (rest.length !== 1 || !/^[0-9]{1,5}$/.test(rest[0])) badStep();
    return { kind: 'tick', args: [parseInt(rest[0], 10)], line: n };
  }
  if (kind === 'expect' && where === 'test') {
    if (rest.length !== 3 || !['==', '!=', '<', '>'].includes(rest[1]) || !LITERAL_RE.test(rest[2])) badStep();
    return { kind: 'expect', args: rest, line: n };
  }
  if (kind === 'flaky' && where === 'test' && C.HAS_FLAKY) {
    if (rest.length !== 1 || !/^[0-9]$/.test(rest[0])) badStep();
    return { kind: 'flaky', args: [parseInt(rest[0], 10)], line: n };
  }
  return badStep();
}

function readSuite(text) {
  const fixtures = new Map();
  const tests = [];
  const modules = [];
  let cur = null;
  let curKind = null;
  let module = 'main';
  text.split('\n').forEach((raw, idx) => {
    const n = idx + 1;
    const body = raw.split('#')[0].replace(/\s+$/, '');
    if (!body.trim()) return;
    const words = body.trim().split(/\s+/);
    if (body[0] === ' ' || body[0] === '\t') {
      if (cur === null) fail(n, 'indented line outside a block');
      if (curKind === 'fixture') {
        if (words[0] === 'setup' || words[0] === 'teardown') {
          if (words.length < 2) fail(n, `bad step '${words.join(' ')}'`);
          (words[0] === 'setup' ? cur.setup : cur.teardown).push(parseStep(words.slice(1), n, 'fixture'));
        } else if (words[0] === 'value') {
          if (words.length !== 2 || !LITERAL_RE.test(words[1])) fail(n, 'bad value');
          cur.value = words[1];
        } else fail(n, `unknown fixture line '${words[0]}'`);
      } else {
        if (words[0] !== 'step' || words.length < 2) fail(n, `unknown test line '${words[0]}'`);
        cur.steps.push(parseStep(words.slice(1), n, 'test'));
      }
      return;
    }
    const d = words[0];
    if (d === 'module') {
      if (words.length !== 2 || !NAME_RE.test(words[1])) fail(n, 'bad line');
      module = words[1];
      cur = null;
    } else if (d === 'fixture') {
      if (words.length < 2 || !NAME_RE.test(words[1])) fail(n, 'bad line');
      const name = words[1];
      if (fixtures.has(name)) fail(n, `duplicate fixture '${name}'`);
      const cl = clauses(words.slice(2), n, ['scope', 'needs']);
      let scope = 'test';
      if (cl.scope) {
        if (cl.scope.length !== 1) fail(n, 'bad line');
        if (!(cl.scope[0] in SCOPES)) fail(n, `bad scope '${cl.scope[0]}'`);
        scope = cl.scope[0];
      }
      cur = { name, scope, needs: cl.needs || [], line: n, setup: [], teardown: [], value: '-' };
      curKind = 'fixture';
      fixtures.set(name, cur);
    } else if (d === 'test') {
      if (words.length < 2 || !NAME_RE.test(words[1])) fail(n, 'bad line');
      const name = words[1];
      if (tests.some((t) => t.name === name)) fail(n, `duplicate test '${name}'`);
      const cl = clauses(words.slice(2), n, ['needs', 'marks', 'param']);
      for (const v of cl.param || []) if (!LITERAL_RE.test(v)) fail(n, 'bad value');
      cur = { name, needs: cl.needs || [], marks: cl.marks || [], params: cl.param || [], line: n, module, steps: [] };
      curKind = 'test';
      tests.push(cur);
      if (!modules.includes(module)) modules.push(module);
    } else fail(n, `unknown directive '${d}'`);
  });
  for (const f of fixtures.values()) for (const need of f.needs) if (!fixtures.has(need)) fail(f.line, `unknown fixture '${need}'`);
  for (const t of tests) for (const need of t.needs) if (!fixtures.has(need)) fail(t.line, `unknown fixture '${need}'`);
  const visit = (f, path) => {
    if (path.includes(f.name)) fail(f.line, 'fixture cycle ' + path.slice(path.indexOf(f.name)).concat([f.name]).join(' -> '));
    for (const need of f.needs) visit(fixtures.get(need), path.concat([f.name]));
  };
  for (const f of fixtures.values()) visit(f, []);
  for (const f of fixtures.values()) {
    for (const need of f.needs) {
      if (SCOPES[fixtures.get(need).scope] < SCOPES[f.scope]) fail(f.line, `fixture '${f.name}' has a wider scope than its dependency '${need}'`);
    }
  }
  return { fixtures, tests, modules };
}

module.exports = { readSuite, SuiteError };
