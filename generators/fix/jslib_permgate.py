"""Role-based permission checks with inheritance and deny rules (javascript): bugs injected into an access-control library."""
from fx import Lib, dd
from generators.fix._lang2 import JS_VERIFY, PACKAGE_JSON, register_libs

README = dd(r'''
    # permgate

    Permission checks for the back office of a small publishing tool. CommonJS:
    `const { Policy } = require('./src/policy')`, `const { parseRule, patternMatch, ruleMatches } = require('./src/rules')`.

    ## Rules (`src/rules.js`)

    A rule is a string `action:resource` with an optional condition after a space: `write:doc/* @owner`.

    * `parseRule(text)` returns `{ action, resource, cond, text }`; `cond` is `'owner'`, `'team'` or `null`; `text` is the input
      with surrounding whitespace removed. The action has no `:` and no whitespace; the resource has no whitespace and
      may contain `:`; the condition is `@owner` or `@team`. Anything else is a `TypeError`.
    * `patternMatch(pattern, value)`: `'*'` matches everything; a pattern ending in `*` matches every value that starts with
      the pattern minus that star (`'doc/*'` matches `'doc/'` and `'doc/a/b'`, not `'doc'`); any other pattern must equal
      the value.
    * `ruleMatches(rule, user, action, resource)`: the action pattern must match `action` and the resource pattern the
      `resource.path`. `@owner` also needs `resource.owner` to be defined and equal to `user.id`; `@team` needs
      `resource.team` to be defined and in `user.teams` (missing `teams` means none).

    ## `new Policy(def)` (`src/policy.js`)

    `def.roles` maps role names to `{ inherits = [], allow = [], deny = [] }` where `allow` and `deny` are lists of rule
    strings (parsed at construction). An `inherits` entry naming an unknown role, or an inheritance cycle (including a role
    inheriting itself), is a `RangeError`.

    * `policy.expand(roleNames)` returns the effective roles as an array without duplicates, breadth first: the given roles in
      order, then the roles they inherit (each role's `inherits` in order, roles taken in the order they were first
      reached), and so on. Names that are not roles of the policy are skipped.
    * `policy.explain(user, action, resource)` looks at the roles of `expand(user.roles || [])`, in that order. If some `deny`
      rule matches (`ruleMatches`), the first one found (roles in order, rules in order) decides:
      `{ allowed: false, by: '<role>: <rule text>', reason: 'deny' }`. Otherwise the first matching `allow` rule gives
      `{ allowed: true, by: '<role>: <rule text>', reason: 'allow' }`. With no match at all:
      `{ allowed: false, by: null, reason: 'default' }`. So an explicit deny anywhere in the effective roles beats any allow.
    * `policy.can(user, action, resource)` is `explain(...).allowed`.
    * `policy.filter(user, action, resources)` keeps the resources the user may act on, in their original order.
''')

RULES = dd(r'''
    'use strict';

    const RULE = /^\s*([^:\s]+):(\S+)(?:\s+@(owner|team))?\s*$/;

    function parseRule(text) {
      const m = RULE.exec(text);
      if (m === null) throw new TypeError(`bad rule: ${text}`);
      return { action: m[1], resource: m[2], cond: m[3] || null, text: text.trim() };
    }

    function patternMatch(pattern, value) {
      if (pattern === '*') return true;
      if (pattern.endsWith('*')) return value.startsWith(pattern.slice(0, -1));
      return pattern === value;
    }

    function ruleMatches(rule, user, action, resource) {
      if (!patternMatch(rule.action, action)) return false;
      if (!patternMatch(rule.resource, resource.path)) return false;
      if (rule.cond === 'owner') return resource.owner !== undefined && resource.owner === user.id;
      if (rule.cond === 'team') return resource.team !== undefined && (user.teams || []).includes(resource.team);
      return true;
    }

    module.exports = { parseRule, patternMatch, ruleMatches };
''')

POLICY = dd(r'''
    'use strict';

    const { parseRule, ruleMatches } = require('./rules');

    class Policy {
      constructor(def) {
        this.roles = {};
        for (const [name, role] of Object.entries(def.roles)) {
          this.roles[name] = {
            inherits: role.inherits || [],
            allow: (role.allow || []).map(parseRule),
            deny: (role.deny || []).map(parseRule),
          };
        }
        for (const [name, role] of Object.entries(this.roles)) {
          for (const parent of role.inherits) {
            if (!(parent in this.roles)) throw new RangeError(`role ${name} inherits unknown role ${parent}`);
          }
        }
        this.checkCycles();
      }

      checkCycles() {
        const state = {};
        const visit = (name) => {
          if (state[name] === 'done') return;
          if (state[name] === 'active') throw new RangeError(`inheritance cycle at ${name}`);
          state[name] = 'active';
          for (const parent of this.roles[name].inherits) visit(parent);
          state[name] = 'done';
        };
        for (const name of Object.keys(this.roles)) visit(name);
      }

      expand(roleNames) {
        const order = [];
        const queue = roleNames.filter((n) => n in this.roles);
        while (queue.length > 0) {
          const name = queue.shift();
          if (order.includes(name)) continue;
          order.push(name);
          queue.push(...this.roles[name].inherits);
        }
        return order;
      }

      explain(user, action, resource) {
        const order = this.expand(user.roles || []);
        for (const name of order) {
          for (const rule of this.roles[name].deny) {
            if (ruleMatches(rule, user, action, resource)) return { allowed: false, by: `${name}: ${rule.text}`, reason: 'deny' };
          }
        }
        for (const name of order) {
          for (const rule of this.roles[name].allow) {
            if (ruleMatches(rule, user, action, resource)) return { allowed: true, by: `${name}: ${rule.text}`, reason: 'allow' };
          }
        }
        return { allowed: false, by: null, reason: 'default' };
      }

      can(user, action, resource) {
        return this.explain(user, action, resource).allowed;
      }

      filter(user, action, resources) {
        return resources.filter((r) => this.can(user, action, r));
      }
    }

    module.exports = { Policy };
''')

VISIBLE = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { Policy } = require('../src/policy');
    const { patternMatch } = require('../src/rules');

    test('pattern matching', () => {
      assert.equal(patternMatch('doc/*', 'doc/12'), true);
      assert.equal(patternMatch('doc/12', 'doc/13'), false);
    });

    test('viewer can read', () => {
      const p = new Policy({ roles: { viewer: { allow: ['read:doc/*'] } } });
      assert.equal(p.can({ id: 'u1', roles: ['viewer'] }, 'read', { path: 'doc/1' }), true);
      assert.equal(p.can({ id: 'u1', roles: ['viewer'] }, 'write', { path: 'doc/1' }), false);
    });
''')

HIDDEN = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { Policy } = require('../src/policy');
    const { parseRule, patternMatch, ruleMatches } = require('../src/rules');

    const POLICY = new Policy({
      roles: {
        viewer: { allow: ['read:doc/*', 'read:folder/*'] },
        editor: { inherits: ['viewer'], allow: ['write:doc/* @owner', 'write:doc/shared/* @team', 'comment:*'], deny: ['write:doc/locked/*'] },
        intern: { inherits: ['viewer'], deny: ['read:doc/hr/*'] },
        billing: { allow: ['read:invoice/*', 'write:invoice/*'] },
        admin: { inherits: ['editor', 'billing'], allow: ['*:*'], deny: ['delete:audit/*'] },
      },
    });
    const user = (roles, extra = {}) => ({ id: 'u1', roles, teams: [], ...extra });

    test('parseRule', () => {
      assert.deepEqual(parseRule('read:doc/*'), { action: 'read', resource: 'doc/*', cond: null, text: 'read:doc/*' });
      assert.deepEqual(parseRule('  write:doc/* @owner '), { action: 'write', resource: 'doc/*', cond: 'owner', text: 'write:doc/* @owner' });
      assert.deepEqual(parseRule('*:*  @team'), { action: '*', resource: '*', cond: 'team', text: '*:*  @team' });
      assert.deepEqual(parseRule('a:b:c'), { action: 'a', resource: 'b:c', cond: null, text: 'a:b:c' });
    });

    test('parseRule rejects bad rules', () => {
      for (const bad of ['', 'read', 'read:', ':doc', 'read doc', 'read:doc @boss', 'read:doc @owner extra', 'read:do c', '@owner', 'read:doc  @']) {
        assert.throws(() => parseRule(bad), TypeError, JSON.stringify(bad));
      }
    });

    test('patternMatch', () => {
      assert.equal(patternMatch('*', ''), true);
      assert.equal(patternMatch('*', 'anything'), true);
      assert.equal(patternMatch('doc/*', 'doc/'), true);
      assert.equal(patternMatch('doc/*', 'doc/a/b'), true);
      assert.equal(patternMatch('doc/*', 'doc'), false);
      assert.equal(patternMatch('doc/*', 'docs/a'), false);
      assert.equal(patternMatch('doc*', 'docs/a'), true);
      assert.equal(patternMatch('doc/1', 'doc/1'), true);
      assert.equal(patternMatch('doc/1', 'doc/12'), false);
      assert.equal(patternMatch('doc/12', 'doc/1'), false);
      assert.equal(patternMatch('read', 'read'), true);
      assert.equal(patternMatch('read', 'Read'), false);
    });

    test('ruleMatches checks action and resource', () => {
      const r = parseRule('read:doc/*');
      assert.equal(ruleMatches(r, user([]), 'read', { path: 'doc/1' }), true);
      assert.equal(ruleMatches(r, user([]), 'write', { path: 'doc/1' }), false);
      assert.equal(ruleMatches(r, user([]), 'read', { path: 'img/1' }), false);
      assert.equal(ruleMatches(parseRule('*:*'), user([]), 'x', { path: 'y' }), true);
    });

    test('ruleMatches: owner and team conditions', () => {
      const own = parseRule('write:doc/* @owner');
      assert.equal(ruleMatches(own, { id: 'u1' }, 'write', { path: 'doc/1', owner: 'u1' }), true);
      assert.equal(ruleMatches(own, { id: 'u1' }, 'write', { path: 'doc/1', owner: 'u2' }), false);
      assert.equal(ruleMatches(own, { id: 'u1' }, 'write', { path: 'doc/1' }), false);
      assert.equal(ruleMatches(own, {}, 'write', { path: 'doc/1' }), false);
      assert.equal(ruleMatches(own, { id: 'u1' }, 'read', { path: 'doc/1', owner: 'u1' }), false);
      const team = parseRule('write:doc/* @team');
      assert.equal(ruleMatches(team, { teams: ['a', 'b'] }, 'write', { path: 'doc/1', team: 'b' }), true);
      assert.equal(ruleMatches(team, { teams: ['a'] }, 'write', { path: 'doc/1', team: 'b' }), false);
      assert.equal(ruleMatches(team, {}, 'write', { path: 'doc/1', team: 'b' }), false);
      assert.equal(ruleMatches(team, { teams: ['a'] }, 'write', { path: 'doc/1' }), false);
      assert.equal(ruleMatches(team, { teams: [undefined] }, 'write', { path: 'doc/1' }), false);
    });

    test('expand is breadth first without duplicates', () => {
      assert.deepEqual(POLICY.expand(['admin']), ['admin', 'editor', 'billing', 'viewer']);
      assert.deepEqual(POLICY.expand(['editor']), ['editor', 'viewer']);
      assert.deepEqual(POLICY.expand(['viewer', 'editor']), ['viewer', 'editor']);
      assert.deepEqual(POLICY.expand(['intern', 'editor']), ['intern', 'editor', 'viewer']);
      assert.deepEqual(POLICY.expand([]), []);
      assert.deepEqual(POLICY.expand(['ghost', 'viewer', 'ghost2']), ['viewer']);
      assert.deepEqual(POLICY.expand(['billing', 'billing']), ['billing']);
    });

    test('viewer and default deny', () => {
      const v = user(['viewer']);
      assert.equal(POLICY.can(v, 'read', { path: 'doc/1' }), true);
      assert.equal(POLICY.can(v, 'read', { path: 'folder/x/y' }), true);
      assert.equal(POLICY.can(v, 'write', { path: 'doc/1', owner: 'u1' }), false);
      assert.equal(POLICY.can(v, 'read', { path: 'invoice/1' }), false);
      assert.equal(POLICY.can(user([]), 'read', { path: 'doc/1' }), false);
      assert.equal(POLICY.can({ id: 'u9' }, 'read', { path: 'doc/1' }), false);
      assert.equal(POLICY.can(user(['nonexistent']), 'read', { path: 'doc/1' }), false);
    });

    test('explain shapes', () => {
      assert.deepEqual(POLICY.explain(user(['viewer']), 'read', { path: 'doc/1' }), { allowed: true, by: 'viewer: read:doc/*', reason: 'allow' });
      assert.deepEqual(POLICY.explain(user(['viewer']), 'read', { path: 'folder/1' }), { allowed: true, by: 'viewer: read:folder/*', reason: 'allow' });
      assert.deepEqual(POLICY.explain(user(['viewer']), 'delete', { path: 'doc/1' }), { allowed: false, by: null, reason: 'default' });
      assert.deepEqual(POLICY.explain(user(['intern']), 'read', { path: 'doc/hr/pay' }), { allowed: false, by: 'intern: read:doc/hr/*', reason: 'deny' });
    });

    test('editor: inheritance and conditions', () => {
      const e = user(['editor'], { teams: ['t1'] });
      assert.equal(POLICY.can(e, 'read', { path: 'doc/1' }), true);
      assert.equal(POLICY.can(e, 'write', { path: 'doc/1', owner: 'u1' }), true);
      assert.equal(POLICY.can(e, 'write', { path: 'doc/1', owner: 'u2' }), false);
      assert.equal(POLICY.can(e, 'write', { path: 'doc/shared/1', owner: 'u2', team: 't1' }), true);
      assert.equal(POLICY.can(e, 'write', { path: 'doc/shared/1', owner: 'u2', team: 't2' }), false);
      assert.equal(POLICY.can(e, 'write', { path: 'doc/1', team: 't1' }), false);
      assert.equal(POLICY.can(e, 'comment', { path: 'anything/at/all' }), true);
      assert.equal(POLICY.can(e, 'read', { path: 'invoice/1' }), false);
      assert.deepEqual(POLICY.explain(e, 'write', { path: 'doc/shared/1', team: 't1' }).by, 'editor: write:doc/shared/* @team');
    });

    test('an explicit deny beats an allow, whichever role grants it', () => {
      const e = user(['editor']);
      assert.deepEqual(POLICY.explain(e, 'write', { path: 'doc/locked/1', owner: 'u1' }), { allowed: false, by: 'editor: write:doc/locked/*', reason: 'deny' });
      const a = user(['admin']);
      assert.equal(POLICY.can(a, 'write', { path: 'doc/locked/1' }), false);
      assert.equal(POLICY.can(a, 'delete', { path: 'audit/2024' }), false);
      assert.equal(POLICY.can(a, 'delete', { path: 'doc/1' }), true);
      assert.equal(POLICY.can(a, 'read', { path: 'audit/2024' }), true);
      assert.deepEqual(POLICY.explain(a, 'purge', { path: 'cache' }), { allowed: true, by: 'admin: *:*', reason: 'allow' });
      const i = user(['intern', 'admin']);
      assert.equal(POLICY.can(i, 'read', { path: 'doc/hr/pay' }), false);
      assert.equal(POLICY.can(i, 'read', { path: 'doc/other' }), true);
    });

    test('deny is found in role order, then rule order', () => {
      const p = new Policy({
        roles: {
          a: { deny: ['x:one', 'x:*'] },
          b: { deny: ['x:*'] },
        },
      });
      assert.equal(p.explain({ roles: ['a', 'b'] }, 'x', { path: 'one' }).by, 'a: x:one');
      assert.equal(p.explain({ roles: ['a', 'b'] }, 'x', { path: 'two' }).by, 'a: x:*');
      assert.equal(p.explain({ roles: ['b', 'a'] }, 'x', { path: 'one' }).by, 'b: x:*');
    });

    test('allow is found in role order, then rule order', () => {
      const p = new Policy({
        roles: {
          base: { allow: ['r:*'] },
          a: { inherits: ['base'], allow: ['r:one', 'r:*'] },
          b: { allow: ['r:one'] },
        },
      });
      assert.equal(p.explain({ roles: ['a'] }, 'r', { path: 'one' }).by, 'a: r:one');
      assert.equal(p.explain({ roles: ['a'] }, 'r', { path: 'two' }).by, 'a: r:*');
      assert.equal(p.explain({ roles: ['b', 'a'] }, 'r', { path: 'one' }).by, 'b: r:one');
      assert.equal(p.explain({ roles: ['base', 'b'] }, 'r', { path: 'one' }).by, 'base: r:*');
    });

    test('filter keeps order', () => {
      const docs = [
        { path: 'doc/3', owner: 'u1' },
        { path: 'doc/locked/1', owner: 'u1' },
        { path: 'doc/2', owner: 'u2' },
        { path: 'doc/1', owner: 'u1' },
      ];
      const got = POLICY.filter(user(['editor']), 'write', docs);
      assert.deepEqual(got.map((d) => d.path), ['doc/3', 'doc/1']);
      assert.strictEqual(got[0], docs[0]);
      assert.deepEqual(POLICY.filter(user([]), 'read', docs), []);
      assert.equal(POLICY.filter(user(['viewer']), 'read', docs).length, 4);
    });

    test('policy validation', () => {
      assert.throws(() => new Policy({ roles: { a: { inherits: ['missing'] } } }), RangeError);
      assert.throws(() => new Policy({ roles: { a: { inherits: ['a'] } } }), RangeError);
      assert.throws(() => new Policy({ roles: { a: { inherits: ['b'] }, b: { inherits: ['c'] }, c: { inherits: ['a'] } } }), RangeError);
      assert.throws(() => new Policy({ roles: { a: { allow: ['bad rule'] } } }), TypeError);
      assert.throws(() => new Policy({ roles: { a: { deny: ['read'] } } }), TypeError);
      assert.doesNotThrow(() => new Policy({ roles: { a: { inherits: ['b', 'c'] }, b: { inherits: ['d'] }, c: { inherits: ['d'] }, d: {} } }));
      assert.doesNotThrow(() => new Policy({ roles: {} }));
    });

    test('diamond inheritance is not a cycle', () => {
      const p = new Policy({ roles: { top: { inherits: ['l', 'r'] }, l: { inherits: ['base'] }, r: { inherits: ['base'] }, base: { allow: ['x:y'] } } });
      assert.deepEqual(p.expand(['top']), ['top', 'l', 'r', 'base']);
      assert.equal(p.can({ roles: ['top'] }, 'x', { path: 'y' }), true);
    });
''')

LIB = Lib(
    name="permgate", lang="javascript", title="the permgate policy library",
    blurb="The back office of the publishing tool asks permgate whether a user may read, edit or delete a document.",
    files={"package.json": PACKAGE_JSON % "permgate", "src/rules.js": RULES, "src/policy.js": POLICY, "README.md": README, ".gitignore": "node_modules/\n"},
    visible_tests={"test/basic.test.js": VISIBLE},
    hidden_tests={"test/full.test.js": HIDDEN},
    mutate=["src/policy.js", "src/rules.js"], difficulty=2, tags=["access-control", "roles", "permissions"],
    verify=JS_VERIFY,
    probe_import="const { Policy } = require('./src/policy');\nconst { parseRule, patternMatch, ruleMatches } = require('./src/rules');",
    probes=[
        "patternMatch('doc/*', 'doc')",
        "patternMatch('doc/*', 'doc/')",
        "patternMatch('doc/1', 'doc/12')",
        "patternMatch('*', '')",
        "parseRule('  write:doc/* @owner ')",
        "ruleMatches(parseRule('write:doc/* @owner'), { id: 'u1' }, 'write', { path: 'doc/1' })",
        "ruleMatches(parseRule('write:doc/* @team'), {}, 'write', { path: 'doc/1', team: 'b' })",
        "new Policy({ roles: { viewer: { allow: ['read:doc/*'] }, editor: { inherits: ['viewer'], allow: ['write:doc/* @owner', 'write:doc/shared/* @team'], deny: ['write:doc/locked/*'] }, intern: { inherits: ['viewer'], deny: ['read:doc/hr/*'] }, admin: { inherits: ['editor'], allow: ['*:*'], deny: ['delete:audit/*'] } } }).expand(['admin'])",
        "new Policy({ roles: { viewer: { allow: ['read:doc/*'] }, editor: { inherits: ['viewer'], allow: ['write:doc/* @owner', 'write:doc/shared/* @team'], deny: ['write:doc/locked/*'] }, intern: { inherits: ['viewer'], deny: ['read:doc/hr/*'] }, admin: { inherits: ['editor'], allow: ['*:*'], deny: ['delete:audit/*'] } } }).expand(['intern', 'editor'])",
        "new Policy({ roles: { viewer: { allow: ['read:doc/*'] }, editor: { inherits: ['viewer'], allow: ['write:doc/* @owner', 'write:doc/shared/* @team'], deny: ['write:doc/locked/*'] }, intern: { inherits: ['viewer'], deny: ['read:doc/hr/*'] }, admin: { inherits: ['editor'], allow: ['*:*'], deny: ['delete:audit/*'] } } }).expand(['ghost', 'viewer'])",
        "new Policy({ roles: { viewer: { allow: ['read:doc/*'] }, editor: { inherits: ['viewer'], allow: ['write:doc/* @owner', 'write:doc/shared/* @team'], deny: ['write:doc/locked/*'] }, intern: { inherits: ['viewer'], deny: ['read:doc/hr/*'] }, admin: { inherits: ['editor'], allow: ['*:*'], deny: ['delete:audit/*'] } } }).explain({ id: 'u1', roles: ['viewer'] }, 'read', { path: 'doc/1' })",
        "new Policy({ roles: { viewer: { allow: ['read:doc/*'] }, editor: { inherits: ['viewer'], allow: ['write:doc/* @owner', 'write:doc/shared/* @team'], deny: ['write:doc/locked/*'] }, intern: { inherits: ['viewer'], deny: ['read:doc/hr/*'] }, admin: { inherits: ['editor'], allow: ['*:*'], deny: ['delete:audit/*'] } } }).explain({ id: 'u1', roles: ['intern'] }, 'read', { path: 'doc/hr/pay' })",
        "new Policy({ roles: { viewer: { allow: ['read:doc/*'] }, editor: { inherits: ['viewer'], allow: ['write:doc/* @owner', 'write:doc/shared/* @team'], deny: ['write:doc/locked/*'] }, intern: { inherits: ['viewer'], deny: ['read:doc/hr/*'] }, admin: { inherits: ['editor'], allow: ['*:*'], deny: ['delete:audit/*'] } } }).explain({ id: 'u1', roles: ['editor'] }, 'write', { path: 'doc/locked/1', owner: 'u1' })",
        "new Policy({ roles: { viewer: { allow: ['read:doc/*'] }, editor: { inherits: ['viewer'], allow: ['write:doc/* @owner', 'write:doc/shared/* @team'], deny: ['write:doc/locked/*'] }, intern: { inherits: ['viewer'], deny: ['read:doc/hr/*'] }, admin: { inherits: ['editor'], allow: ['*:*'], deny: ['delete:audit/*'] } } }).can({ id: 'u1', roles: ['admin'] }, 'delete', { path: 'audit/2024' })",
        "new Policy({ roles: { viewer: { allow: ['read:doc/*'] }, editor: { inherits: ['viewer'], allow: ['write:doc/* @owner', 'write:doc/shared/* @team'], deny: ['write:doc/locked/*'] }, intern: { inherits: ['viewer'], deny: ['read:doc/hr/*'] }, admin: { inherits: ['editor'], allow: ['*:*'], deny: ['delete:audit/*'] } } }).can({ id: 'u1', roles: ['admin'] }, 'delete', { path: 'doc/1' })",
        "new Policy({ roles: { viewer: { allow: ['read:doc/*'] }, editor: { inherits: ['viewer'], allow: ['write:doc/* @owner', 'write:doc/shared/* @team'], deny: ['write:doc/locked/*'] }, intern: { inherits: ['viewer'], deny: ['read:doc/hr/*'] }, admin: { inherits: ['editor'], allow: ['*:*'], deny: ['delete:audit/*'] } } }).can({ id: 'u1', roles: ['editor'] }, 'write', { path: 'doc/1', owner: 'u2' })",
        "new Policy({ roles: { viewer: { allow: ['read:doc/*'] }, editor: { inherits: ['viewer'], allow: ['write:doc/* @owner', 'write:doc/shared/* @team'], deny: ['write:doc/locked/*'] }, intern: { inherits: ['viewer'], deny: ['read:doc/hr/*'] }, admin: { inherits: ['editor'], allow: ['*:*'], deny: ['delete:audit/*'] } } }).can({ id: 'u1', roles: ['editor'], teams: ['t1'] }, 'write', { path: 'doc/shared/1', owner: 'u2', team: 't1' })",
        "new Policy({ roles: { viewer: { allow: ['read:doc/*'] }, editor: { inherits: ['viewer'], allow: ['write:doc/* @owner', 'write:doc/shared/* @team'], deny: ['write:doc/locked/*'] }, intern: { inherits: ['viewer'], deny: ['read:doc/hr/*'] }, admin: { inherits: ['editor'], allow: ['*:*'], deny: ['delete:audit/*'] } } }).can({ id: 'u9' }, 'read', { path: 'doc/1' })",
        "new Policy({ roles: { a: { inherits: ['b'] }, b: { inherits: ['a'] } } })",
        "new Policy({ roles: { a: { inherits: ['zzz'] } } })",
    ],
)

register_libs([LIB], n=8)
