"""In-process URL router with params, constraints and wildcards (javascript): bugs injected into a routing library."""
from fx import Lib, dd
from generators.fix._lang2 import JS_VERIFY, PACKAGE_JSON, register_libs

README = dd(r'''
    # routetable

    A small in-process router: register patterns, then ask which one serves a request. CommonJS:
    `const { Router, buildPath } = require('./src/router')`.

    ## Patterns

    A pattern starts with `/` and is made of segments separated by `/`. Empty segments are a `TypeError`.

    | segment | meaning |
    |---|---|
    | `users` | literal text |
    | `:id` | a parameter: any one non-empty path segment |
    | `:id(\d+)` | a constrained parameter: the segment must match the JavaScript regular expression in the parentheses *completely* (it is anchored). The expression may not contain `/` |
    | `:slug?` | an optional parameter; allowed only as the **last** segment, and cannot be constrained |
    | `*rest` or `*` | a wildcard; allowed only as the **last** segment; captures one or more remaining segments joined with `/`. The parameter is named `rest`, or `*` for a bare `*` |

    A parameter name is `[A-Za-z_][A-Za-z0-9_]*`. Using one name twice in a pattern, a misplaced optional or wildcard
    segment, or a malformed `:` segment is a `TypeError` (raised by `add`).

    ## `new Router({ caseSensitive = true })` and `add(method, pattern, value)`

    `method` is an HTTP method in any letter case (stored upper-case) or `'*'` for any method. `value` is returned
    unchanged by `match`. Registration order matters for ties (below).

    ## `router.match(method, path)`

    Always returns an object with a `status`:

    * `{ status: 200, value, params, pattern }` for the best route;
    * `{ status: 405, allow }` when the path matches routes but none of them serves this method; `allow` lists the methods
      of those routes, upper-case, without duplicates, sorted alphabetically, with `'HEAD'` added whenever `'GET'` is there;
    * `{ status: 404 }` when no route matches the path, or when `path` does not start with `/`.

    The path is cut at the first `?` or `#`. Empty segments are ignored, so `//a//b/` is the same as `/a/b`, and `/` has no
    segments. Literal segments are compared with the *raw* path text (so the pattern `/a%20b` matches the path `/a%20b`);
    with `caseSensitive: false` literals are compared ignoring case. Captured values are decoded with
    `decodeURIComponent`; a value that cannot be decoded is returned as it is. Matching rules:

    * a plain, constrained or literal segment consumes exactly one path segment;
    * an optional parameter matches the last path segment, or nothing (then the parameter is absent from `params`);
    * a wildcard needs at least one remaining segment and takes all of them, each decoded, joined with `/`;
    * otherwise the number of segments must be equal.

    When several routes match, the best one wins. Compare their segments from left to right; at the first position where
    the kinds differ the higher rank wins: literal (4), constrained parameter (3), plain parameter (2), optional
    parameter (1), wildcard (0). If all compared positions are equal, the route with fewer segments wins. Still tied? The
    route whose method fits better wins: the request's own method first, then `GET` for a `HEAD` request, then `'*'`;
    routes with the same fit are ordered by registration (first added wins). A route whose method does not fit at all
    (e.g. `POST` for a `GET` request) is not a candidate.

    ## `buildPath(pattern, params = {})`

    Builds a path from a pattern. Literals are copied; a parameter value is `String(value)` encoded with
    `encodeURIComponent`; a constrained parameter whose text does not match its expression is a `TypeError`; a missing
    (`undefined` or `null`) required parameter is a `TypeError`, a missing optional one is left out; a wildcard takes an
    array of segments or a string that is split at `/`, each part encoded, and must be non-empty. Parameters that the
    pattern does not use go into a query string, `?k=v&k2=v2`, sorted by key, keys and values encoded; `undefined`
    ones are skipped. The root pattern `/` builds `/`.
''')

ROUTER = dd(r'''
    'use strict';

    const RANK = { lit: 4, re: 3, param: 2, opt: 1, wild: 0 };

    function parsePattern(pattern) {
      if (typeof pattern !== 'string' || pattern[0] !== '/') throw new TypeError('pattern must start with /');
      const parts = pattern === '/' ? [] : pattern.slice(1).split('/');
      const names = new Set();
      return parts.map((raw, i) => {
        if (raw === '') throw new TypeError('empty segment in pattern');
        const last = i === parts.length - 1;
        let seg;
        if (raw[0] === '*') {
          if (!last) throw new TypeError('a wildcard must be the last segment');
          seg = { kind: 'wild', name: raw.length > 1 ? raw.slice(1) : '*' };
        } else if (raw[0] === ':') {
          const m = /^:([A-Za-z_][A-Za-z0-9_]*)(?:\((.+)\))?(\?)?$/.exec(raw);
          if (m === null) throw new TypeError(`bad parameter segment ${raw}`);
          if (m[3] !== undefined) {
            if (!last) throw new TypeError('an optional parameter must be the last segment');
            if (m[2] !== undefined) throw new TypeError('an optional parameter cannot be constrained');
            seg = { kind: 'opt', name: m[1] };
          } else if (m[2] !== undefined) {
            seg = { kind: 're', name: m[1], re: new RegExp(`^(?:${m[2]})$`) };
          } else {
            seg = { kind: 'param', name: m[1] };
          }
        } else {
          seg = { kind: 'lit', text: raw };
        }
        if (seg.name !== undefined) {
          if (names.has(seg.name)) throw new TypeError(`duplicate parameter ${seg.name}`);
          names.add(seg.name);
        }
        return seg;
      });
    }

    function splitPath(path) {
      const cut = path.search(/[?#]/);
      const clean = cut >= 0 ? path.slice(0, cut) : path;
      if (clean[0] !== '/') return null;
      return clean.split('/').filter((s) => s !== '');
    }

    function decode(text) {
      try {
        return decodeURIComponent(text);
      } catch (e) {
        return text;
      }
    }

    function matchSegments(segments, parts, caseSensitive) {
      const params = {};
      for (let i = 0; i < segments.length; i++) {
        const seg = segments[i];
        if (seg.kind === 'wild') {
          if (i >= parts.length) return null;
          params[seg.name] = parts.slice(i).map(decode).join('/');
          return params;
        }
        if (seg.kind === 'opt') {
          if (i === parts.length) return params;
          if (i === parts.length - 1) {
            params[seg.name] = decode(parts[i]);
            return params;
          }
          return null;
        }
        if (i >= parts.length) return null;
        const part = parts[i];
        if (seg.kind === 'lit') {
          const same = caseSensitive ? part === seg.text : part.toLowerCase() === seg.text.toLowerCase();
          if (!same) return null;
        } else {
          const value = decode(part);
          if (seg.kind === 're' && !seg.re.test(value)) return null;
          params[seg.name] = value;
        }
      }
      return parts.length === segments.length ? params : null;
    }

    function compareRank(a, b) {
      const n = Math.min(a.length, b.length);
      for (let i = 0; i < n; i++) {
        const d = RANK[b[i].kind] - RANK[a[i].kind];
        if (d !== 0) return d;
      }
      return a.length - b.length;
    }

    class Router {
      constructor(opts = {}) {
        this.caseSensitive = opts.caseSensitive !== false;
        this.routes = [];
      }

      add(method, pattern, value) {
        const segments = parsePattern(pattern);
        this.routes.push({ method: method.toUpperCase(), pattern, segments, value, order: this.routes.length });
        return this;
      }

      match(method, path) {
        const parts = splitPath(path);
        if (parts === null) return { status: 404 };
        const verb = method.toUpperCase();
        const found = [];
        for (const route of this.routes) {
          const params = matchSegments(route.segments, parts, this.caseSensitive);
          if (params !== null) found.push({ route, params });
        }
        if (found.length === 0) return { status: 404 };

        const fit = (route) => {
          if (route.method === verb) return 0;
          if (verb === 'HEAD' && route.method === 'GET') return 1;
          if (route.method === '*') return 2;
          return -1;
        };
        const usable = found.filter((f) => fit(f.route) >= 0);
        if (usable.length > 0) {
          usable.sort((a, b) => compareRank(a.route.segments, b.route.segments) || fit(a.route) - fit(b.route) || a.route.order - b.route.order);
          const best = usable[0];
          return { status: 200, value: best.route.value, params: best.params, pattern: best.route.pattern };
        }
        const allow = new Set(found.map((f) => f.route.method));
        if (allow.has('GET')) allow.add('HEAD');
        return { status: 405, allow: [...allow].sort() };
      }
    }

    function buildPath(pattern, params = {}) {
      const segments = parsePattern(pattern);
      const used = new Set();
      const out = [];
      for (const seg of segments) {
        if (seg.kind === 'lit') {
          out.push(seg.text);
          continue;
        }
        used.add(seg.name);
        const value = params[seg.name];
        if (seg.kind === 'wild') {
          const items = Array.isArray(value) ? value : value === undefined || value === null ? [] : String(value).split('/');
          if (items.length === 0 || items.some((s) => s === '')) throw new TypeError(`missing value for ${seg.name}`);
          out.push(items.map((s) => encodeURIComponent(s)).join('/'));
        } else if (value === undefined || value === null) {
          if (seg.kind !== 'opt') throw new TypeError(`missing value for ${seg.name}`);
        } else {
          const text = String(value);
          if (seg.kind === 're' && !seg.re.test(text)) throw new TypeError(`${seg.name} does not match its pattern`);
          out.push(encodeURIComponent(text));
        }
      }
      let path = '/' + out.join('/');
      const extra = Object.keys(params).filter((k) => !used.has(k) && params[k] !== undefined).sort();
      if (extra.length > 0) {
        path += '?' + extra.map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(String(params[k]))}`).join('&');
      }
      return path;
    }

    module.exports = { Router, buildPath, parsePattern };
''')

VISIBLE = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { Router, buildPath } = require('../src/router');

    test('literal and param routes', () => {
      const r = new Router();
      r.add('GET', '/users', 'list').add('GET', '/users/:id', 'show');
      assert.equal(r.match('GET', '/users').value, 'list');
      const m = r.match('GET', '/users/42');
      assert.equal(m.value, 'show');
      assert.deepEqual(m.params, { id: '42' });
    });

    test('unknown path is a 404', () => {
      assert.equal(new Router().match('GET', '/nope').status, 404);
    });

    test('buildPath', () => {
      assert.equal(buildPath('/users/:id', { id: 7 }), '/users/7');
    });
''')

HIDDEN = dd(r'''
    'use strict';
    const test = require('node:test');
    const assert = require('node:assert/strict');
    const { Router, buildPath, parsePattern } = require('../src/router');

    const router = (...routes) => {
      const r = new Router();
      for (const [m, p, v] of routes) r.add(m, p, v);
      return r;
    };

    test('params are captured and decoded', () => {
      const r = router(['GET', '/files/:name', 'file']);
      assert.deepEqual(r.match('GET', '/files/a%20b').params, { name: 'a b' });
      assert.deepEqual(r.match('GET', '/files/caf%C3%A9').params, { name: 'café' });
      assert.deepEqual(r.match('GET', '/files/100%').params, { name: '100%' });
      assert.deepEqual(r.match('GET', '/files/%E0%A4%A').params, { name: '%E0%A4%A' });
    });

    test('result shape', () => {
      const r = router(['GET', '/a/:x', 'V']);
      assert.deepEqual(r.match('GET', '/a/1'), { status: 200, value: 'V', params: { x: '1' }, pattern: '/a/:x' });
      assert.deepEqual(r.match('GET', '/b'), { status: 404 });
    });

    test('paths are cut at ? and #, slashes collapse, trailing slash ignored', () => {
      const r = router(['GET', '/a/b', 'ab'], ['GET', '/', 'root']);
      assert.equal(r.match('GET', '/a/b?x=1').value, 'ab');
      assert.equal(r.match('GET', '/a/b#frag').value, 'ab');
      assert.equal(r.match('GET', '/a/b/?x=/c').value, 'ab');
      assert.equal(r.match('GET', '//a///b//').value, 'ab');
      assert.equal(r.match('GET', '/').value, 'root');
      assert.equal(r.match('GET', '//').value, 'root');
      assert.equal(r.match('GET', '/?q=1').value, 'root');
      assert.equal(r.match('GET', '#top').status, 404);
      assert.equal(r.match('GET', 'a/b').status, 404);
      assert.equal(r.match('GET', '').status, 404);
    });

    test('a path needs the same number of segments', () => {
      const r = router(['GET', '/a/:x', 'V']);
      assert.equal(r.match('GET', '/a').status, 404);
      assert.equal(r.match('GET', '/a/1/2').status, 404);
      assert.equal(r.match('GET', '/a/').status, 404);
      assert.equal(r.match('GET', '/').status, 404);
    });

    test('literals are case sensitive by default', () => {
      const r = router(['GET', '/Accounts/:id', 'U']);
      assert.equal(r.match('GET', '/accounts/1').status, 404);
      assert.equal(r.match('GET', '/Accounts/1').status, 200);
      const loose = new Router({ caseSensitive: false });
      loose.add('GET', '/Accounts/:id', 'U').add('GET', '/ABOUT', 'about');
      assert.equal(loose.match('GET', '/accounts/Ab').value, 'U');
      assert.deepEqual(loose.match('GET', '/aCCOUNTS/Ab').params, { id: 'Ab' });
      assert.equal(loose.match('GET', '/about').value, 'about');
      assert.equal(new Router({ caseSensitive: true }).add('GET', '/a', 1).match('GET', '/A').status, 404);
    });

    test('literals compare raw text', () => {
      const r = router(['GET', '/a%20b', 'raw']);
      assert.equal(r.match('GET', '/a%20b').value, 'raw');
      assert.equal(r.match('GET', '/a b').status, 404);
    });

    test('constrained params', () => {
      const r = router(['GET', '/users/:id(\\d+)', 'num'], ['GET', '/users/:name', 'name']);
      assert.deepEqual(r.match('GET', '/users/42'), { status: 200, value: 'num', params: { id: '42' }, pattern: '/users/:id(\\d+)' });
      assert.equal(r.match('GET', '/users/4x2').value, 'name');
      assert.equal(r.match('GET', '/users/x42').value, 'name');
      const only = router(['GET', '/v/:n(\\d{2}|x)', 'v']);
      assert.equal(only.match('GET', '/v/12').status, 200);
      assert.equal(only.match('GET', '/v/x').status, 200);
      assert.equal(only.match('GET', '/v/123').status, 404);
      assert.equal(only.match('GET', '/v/1').status, 404);
      assert.equal(only.match('GET', '/v/x1').status, 404);
      assert.equal(only.match('GET', '/v/1x').status, 404);
    });

    test('constraints see the decoded value', () => {
      const r = router(['GET', '/t/:tag([a-z ]+)', 't']);
      assert.deepEqual(r.match('GET', '/t/big%20cat').params, { tag: 'big cat' });
      assert.equal(r.match('GET', '/t/big%2Fcat').status, 404);
    });

    test('optional parameter', () => {
      const r = router(['GET', '/blog/:slug?', 'blog']);
      assert.deepEqual(r.match('GET', '/blog').params, {});
      assert.deepEqual(r.match('GET', '/blog/').params, {});
      assert.deepEqual(r.match('GET', '/blog/hello').params, { slug: 'hello' });
      assert.equal(r.match('GET', '/blog/hello/more').status, 404);
      assert.equal(r.match('GET', '/').status, 404);
      const nested = router(['GET', '/a/:b/:c?', 'x']);
      assert.deepEqual(nested.match('GET', '/a/1').params, { b: '1' });
      assert.deepEqual(nested.match('GET', '/a/1/2').params, { b: '1', c: '2' });
      assert.equal(nested.match('GET', '/a').status, 404);
    });

    test('wildcards', () => {
      const r = router(['GET', '/static/*path', 's'], ['GET', '/any/*', 'a']);
      assert.deepEqual(r.match('GET', '/static/css/site%20x.css').params, { path: 'css/site x.css' });
      assert.deepEqual(r.match('GET', '/static/a').params, { path: 'a' });
      assert.equal(r.match('GET', '/static').status, 404);
      assert.equal(r.match('GET', '/static/').status, 404);
      assert.deepEqual(r.match('GET', '/any/x/y/z').params, { '*': 'x/y/z' });
      assert.deepEqual(r.match('GET', '/static/a%2Fb/c').params, { path: 'a/b/c' });
    });

    test('pattern errors', () => {
      const bad = ['users', '', '/a//b', '/*x/y', '/:a?/b', '/:a/:a', '/:1x', '/:', '/:a(\\d+)?', '/a/*/*', '/:a(x', '/:a-b'];
      for (const p of bad) assert.throws(() => new Router().add('GET', p, 1), TypeError, p);
      assert.throws(() => new Router().add('GET', null, 1), TypeError);
      assert.doesNotThrow(() => new Router().add('GET', '/', 1));
      assert.doesNotThrow(() => new Router().add('GET', '/:a/:b/*rest', 1));
      assert.doesNotThrow(() => new Router().add('GET', '/_x1/:_y2?', 1));
    });

    test('specificity: literal beats constrained beats param beats optional beats wildcard', () => {
      const r = router(
        ['GET', '/x/*any', 'wild'],
        ['GET', '/x/:p', 'param'],
        ['GET', '/x/:n(\\d+)', 're'],
        ['GET', '/x/me', 'lit'],
      );
      assert.equal(r.match('GET', '/x/me').value, 'lit');
      assert.equal(r.match('GET', '/x/12').value, 're');
      assert.equal(r.match('GET', '/x/abc').value, 'param');
      assert.equal(r.match('GET', '/x/a/b').value, 'wild');
      const o = router(['GET', '/y/*z', 'wild'], ['GET', '/y/:o?', 'opt']);
      assert.equal(o.match('GET', '/y/1').value, 'opt');
      assert.equal(o.match('GET', '/y/1/2').value, 'wild');
    });

    test('a plain parameter beats an optional one', () => {
      const r = router(['GET', '/y/:o?', 'opt'], ['GET', '/y/:p', 'param']);
      assert.equal(r.match('GET', '/y/1').value, 'param');
      assert.equal(r.match('GET', '/y').value, 'opt');
      const re = router(['GET', '/y/:p', 'param'], ['GET', '/y/:n(\\d+)', 're'], ['GET', '/y/:o?', 'opt']);
      assert.equal(re.match('GET', '/y/7').value, 're');
      assert.equal(re.match('GET', '/y/seven').value, 'param');
    });

    test('method fit never depends on registration order', () => {
      const all = [['*', '/p', 'any'], ['GET', '/p', 'get'], ['HEAD', '/p', 'head']];
      const perms = [[0, 1, 2], [0, 2, 1], [1, 0, 2], [1, 2, 0], [2, 0, 1], [2, 1, 0]];
      for (const perm of perms) {
        const r = router(...perm.map((i) => all[i]));
        assert.equal(r.match('HEAD', '/p').value, 'head', perm.join());
        assert.equal(r.match('GET', '/p').value, 'get', perm.join());
        assert.equal(r.match('POST', '/p').value, 'any', perm.join());
      }
      const noHead = [['*', '/p', 'any'], ['GET', '/p', 'get'], ['POST', '/p', 'post']];
      for (const perm of perms) {
        const r = router(...perm.map((i) => noHead[i]));
        assert.equal(r.match('HEAD', '/p').value, 'get', perm.join());
        assert.equal(r.match('POST', '/p').value, 'post', perm.join());
        assert.equal(r.match('PUT', '/p').value, 'any', perm.join());
      }
    });

    test('a missing segment is a miss, also when matching ignores case', () => {
      const loose = new Router({ caseSensitive: false });
      loose.add('GET', '/a/b', 1).add('GET', '/c/:d', 2).add('GET', '/e/:f(\\d+)', 3);
      assert.equal(loose.match('GET', '/a').status, 404);
      assert.equal(loose.match('GET', '/c').status, 404);
      assert.equal(loose.match('GET', '/e').status, 404);
      assert.equal(loose.match('GET', '/').status, 404);
    });

    test('parameter names may use upper case letters and digits', () => {
      const r = router(['GET', '/:userId9/:Zed/:a_B0', 'v']);
      assert.deepEqual(r.match('GET', '/1/2/3').params, { userId9: '1', Zed: '2', a_B0: '3' });
      assert.throws(() => new Router().add('GET', '/:9a', 1), TypeError);
    });

    test('specificity is decided left to right', () => {
      const r = router(['GET', '/:a/b', 'param-first'], ['GET', '/a/:b', 'literal-first']);
      assert.equal(r.match('GET', '/a/b').value, 'literal-first');
      assert.equal(r.match('GET', '/z/b').value, 'param-first');
      const s = router(['GET', '/a/:b/c', 'one'], ['GET', '/a/b/:c', 'two']);
      assert.equal(s.match('GET', '/a/b/c').value, 'two');
    });

    test('a shorter route wins when everything compared is equal', () => {
      const r = router(['GET', '/a/:b?', 'opt'], ['GET', '/a', 'lit']);
      assert.equal(r.match('GET', '/a').value, 'lit');
      assert.equal(r.match('GET', '/a/q').value, 'opt');
      const w = router(['GET', '/a/*rest', 'wild'], ['GET', '/a/b', 'lit']);
      assert.equal(w.match('GET', '/a/b').value, 'lit');
    });

    test('ties go to the first registered', () => {
      const r = router(['GET', '/a/:x', 'first'], ['GET', '/a/:y', 'second']);
      assert.equal(r.match('GET', '/a/1').value, 'first');
      assert.deepEqual(r.match('GET', '/a/1').params, { x: '1' });
    });

    test('methods are case insensitive and separate routes', () => {
      const r = router(['get', '/a', 'read'], ['POST', '/a', 'write']);
      assert.equal(r.match('GET', '/a').value, 'read');
      assert.equal(r.match('post', '/a').value, 'write');
      assert.deepEqual(r.match('DELETE', '/a'), { status: 405, allow: ['GET', 'HEAD', 'POST'] });
    });

    test('405 lists methods sorted and unique', () => {
      const r = router(['PUT', '/a/:x', 1], ['DELETE', '/a/1', 2], ['PUT', '/a/:y', 3], ['PATCH', '/a/*r', 4]);
      assert.deepEqual(r.match('GET', '/a/1'), { status: 405, allow: ['DELETE', 'PATCH', 'PUT'] });
      assert.deepEqual(router(['POST', '/a', 1]).match('GET', '/a'), { status: 405, allow: ['POST'] });
      assert.deepEqual(router(['GET', '/a', 1]).match('POST', '/a'), { status: 405, allow: ['GET', 'HEAD'] });
      assert.deepEqual(router(['POST', '/a', 1]).match('GET', '/b'), { status: 404 });
    });

    test('any-method routes', () => {
      const r = router(['*', '/ping', 'any'], ['GET', '/ping', 'get']);
      assert.equal(r.match('GET', '/ping').value, 'get');
      assert.equal(r.match('POST', '/ping').value, 'any');
      assert.equal(r.match('HEAD', '/ping').value, 'get');
      const solo = router(['*', '/p', 'any']);
      assert.equal(solo.match('OPTIONS', '/p').value, 'any');
      assert.equal(solo.match('options', '/p').status, 200);
    });

    test('an any-method route is more specific only through its segments', () => {
      const r = router(['GET', '/u/:id', 'param'], ['*', '/u/me', 'me']);
      assert.equal(r.match('GET', '/u/me').value, 'me');
      assert.equal(r.match('GET', '/u/you').value, 'param');
      const t = router(['*', '/u/:id', 'any'], ['GET', '/u/:id', 'get']);
      assert.equal(t.match('GET', '/u/1').value, 'get');
      const order = router(['*', '/w/:a', 'any-first'], ['POST', '/w/:b', 'post']);
      assert.equal(order.match('POST', '/w/1').value, 'post');
    });

    test('HEAD falls back to GET', () => {
      const r = router(['GET', '/page', 'get']);
      assert.equal(r.match('HEAD', '/page').value, 'get');
      const both = router(['GET', '/page', 'get'], ['HEAD', '/page', 'head']);
      assert.equal(both.match('HEAD', '/page').value, 'head');
      assert.equal(both.match('GET', '/page').value, 'get');
      const star = router(['*', '/page', 'any'], ['GET', '/page', 'get']);
      assert.equal(star.match('HEAD', '/page').value, 'get');
      assert.equal(router(['POST', '/page', 'post']).match('HEAD', '/page').status, 405);
    });

    test('parsePattern', () => {
      const segs = parsePattern('/a/:b/:c(\\d+)/*rest');
      assert.deepEqual(segs.map((s) => s.kind), ['lit', 'param', 're', 'wild']);
      assert.equal(segs[0].text, 'a');
      assert.equal(segs[3].name, 'rest');
      assert.deepEqual(parsePattern('/'), []);
      assert.equal(parsePattern('/*')[0].name, '*');
      assert.equal(parsePattern('/:x?')[0].kind, 'opt');
    });

    test('buildPath fills and encodes', () => {
      assert.equal(buildPath('/users/:id', { id: 7 }), '/users/7');
      assert.equal(buildPath('/users/:id/posts/:slug', { id: 'a b', slug: 'x/y' }), '/users/a%20b/posts/x%2Fy');
      assert.equal(buildPath('/', {}), '/');
      assert.equal(buildPath('/about'), '/about');
      assert.equal(buildPath('/n/:v', { v: 0 }), '/n/0');
      assert.equal(buildPath('/n/:v', { v: '' }), '/n/');
    });

    test('buildPath optional, constrained and wildcard parts', () => {
      assert.equal(buildPath('/blog/:slug?', {}), '/blog');
      assert.equal(buildPath('/blog/:slug?', { slug: undefined }), '/blog');
      assert.equal(buildPath('/blog/:slug?', { slug: null }), '/blog');
      assert.equal(buildPath('/blog/:slug?', { slug: 'hi' }), '/blog/hi');
      assert.equal(buildPath('/u/:id(\\d+)', { id: 42 }), '/u/42');
      assert.throws(() => buildPath('/u/:id(\\d+)', { id: '4x' }), TypeError);
      assert.equal(buildPath('/s/*path', { path: ['a b', 'c'] }), '/s/a%20b/c');
      assert.equal(buildPath('/s/*path', { path: 'a/b c' }), '/s/a/b%20c');
      assert.equal(buildPath('/s/*', { '*': 'q' }), '/s/q');
    });

    test('buildPath errors', () => {
      assert.throws(() => buildPath('/u/:id', {}), TypeError);
      assert.throws(() => buildPath('/u/:id', { id: null }), TypeError);
      assert.throws(() => buildPath('/s/*path', {}), TypeError);
      assert.throws(() => buildPath('/s/*path', { path: [] }), TypeError);
      assert.throws(() => buildPath('/s/*path', { path: '' }), TypeError);
      assert.throws(() => buildPath('/s/*path', { path: ['a', ''] }), TypeError);
      assert.throws(() => buildPath('nope', {}), TypeError);
    });

    test('buildPath puts unused parameters in a sorted query string', () => {
      assert.equal(buildPath('/u/:id', { id: 1, z: 'last', a: 'first one' }), '/u/1?a=first%20one&z=last');
      assert.equal(buildPath('/u/:id', { id: 1, q: undefined }), '/u/1');
      assert.equal(buildPath('/', { b: 2, a: 1 }), '/?a=1&b=2');
      assert.equal(buildPath('/u/:id', { id: 1, 'a&b': 'c=d' }), '/u/1?a%26b=c%3Dd');
      assert.equal(buildPath('/u/:id/:opt?', { id: 1, k: 0 }), '/u/1?k=0');
    });

    test('built paths match their own pattern', () => {
      const r = router(['GET', '/org/:org/repo/:repo(\\w+)/*file', 'v']);
      const path = buildPath('/org/:org/repo/:repo(\\w+)/*file', { org: 'a b', repo: 'x_1', file: ['src', 'm.js'] });
      assert.deepEqual(r.match('GET', path).params, { org: 'a b', repo: 'x_1', file: 'src/m.js' });
    });
''')

LIB = Lib(
    name="routetable", lang="javascript", title="the routetable router",
    blurb="The in-process API gateway dispatches every request through routetable: patterns with parameters in, the serving route out.",
    files={"package.json": PACKAGE_JSON % "routetable", "src/router.js": ROUTER, "README.md": README, ".gitignore": "node_modules/\n"},
    visible_tests={"test/basic.test.js": VISIBLE},
    hidden_tests={"test/full.test.js": HIDDEN},
    mutate=["src/router.js"], difficulty=4, tags=["routing", "url", "http"],
    verify=JS_VERIFY,
    probe_import="const { Router, buildPath } = require('./src/router');",
    probes=[
        "new Router().add('GET', '/files/:name', 'f').match('GET', '/files/a%20b').params",
        "new Router().add('GET', '/a/b', 'ab').match('GET', '//a///b//').status",
        "new Router().add('GET', '/a/b', 'ab').match('GET', '/a/b?x=1').status",
        "new Router().add('GET', '/users/:id(\\\\\\\\d+)', 'num').add('GET', '/users/:name', 'name').match('GET', '/users/42').value",
        "new Router().add('GET', '/users/:id(\\\\\\\\d+)', 'num').add('GET', '/users/:name', 'name').match('GET', '/users/4x2').value",
        "new Router().add('GET', '/blog/:slug?', 'blog').match('GET', '/blog').params",
        "new Router().add('GET', '/blog/:slug?', 'blog').match('GET', '/blog/hello/more').status",
        "new Router().add('GET', '/static/*path', 's').match('GET', '/static/css/site%20x.css').params",
        "new Router().add('GET', '/static/*path', 's').match('GET', '/static').status",
        "new Router().add('GET', '/x/*any', 'wild').add('GET', '/x/:p', 'param').add('GET', '/x/me', 'lit').match('GET', '/x/abc').value",
        "new Router().add('GET', '/:a/b', 'param-first').add('GET', '/a/:b', 'literal-first').match('GET', '/a/b').value",
        "new Router().add('GET', '/a/:b?', 'opt').add('GET', '/a', 'lit').match('GET', '/a').value",
        "new Router().add('PUT', '/a/:x', 1).add('DELETE', '/a/1', 2).add('PUT', '/a/:y', 3).match('GET', '/a/1')",
        "new Router().add('GET', '/page', 'get').match('HEAD', '/page').status",
        "new Router().add('*', '/ping', 'any').add('GET', '/ping', 'get').match('HEAD', '/ping').value",
        "new Router().add('get', '/a', 'read').match('DELETE', '/a')",
        "new Router({ caseSensitive: false }).add('GET', '/ABOUT', 1).match('GET', '/about').status",
        "buildPath('/users/:id/posts/:slug', { id: 'a b', slug: 'x/y' })",
        "buildPath('/blog/:slug?', {})",
        "buildPath('/s/*path', { path: ['a b', 'c'] })",
        "buildPath('/u/:id', { id: 1, z: 'last', a: 'first one' })",
        "buildPath('/u/:id', {})",
    ],
)

register_libs([LIB], n=8)
