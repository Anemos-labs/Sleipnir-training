"""Security families for JavaScript (Node 22, node:test) and Go (go test). Inert payloads only; catastrophic regular expressions are run in a child
process with a hard timeout."""
from fx import dd, family

from . import _sec
from ._sec import patched, readme

JT = dd(r'''
    'use strict';
    const test = require('node:test');
    const { afterEach } = require('node:test');
    const assert = require('node:assert/strict');
    const fs = require('node:fs');
    const os = require('node:os');
    const path = require('node:path');
    const { spawnSync } = require('node:child_process');

    function finishes(code, ms = 2500) {
        const r = spawnSync(process.execPath, ['-e', code], { timeout: ms });
        return r.status === 0;
    }

    function throws(fn) {
        try { fn(); } catch (e) { return true; }
        return false;
    }

''')


def js_task(slug, d, product, func, cwe, finding, src, readme_text, solution, test, tags=None, extra=""):
    mod = f"src/{slug.replace('-', '_')}.js"
    return dict(slug=slug, d=d, lang="javascript", product=product, func=func, cwe=cwe, finding=finding, extra=extra,
                start={mod: src, "README.md": readme(slug, readme_text)},
                solution={mod: solution},
                hidden={f"test/{slug.replace('-', '_')}.test.js": JT + dd(test)}, tags=tags or [])


JS = []

# ---------------------------------------------------------------------------------------------------------------------------------
JS.append(js_task("comment-html", 1, "the comment widget", "renderComment", "CWE-79",
                  "`renderComment` interpolates the author and the text into an HTML string unescaped, so a comment containing `<script>` or `<img onerror=...>` runs in every reader's browser (stored XSS).",
                  dd(r'''
        'use strict';

        /** HTML of one comment: `<div class="comment"><b>AUTHOR</b>: TEXT</div>`. Author and text are plain text supplied by users: `&` becomes `&amp;`, `<` `&lt;`, `>` `&gt;`,
         *  `"` `&quot;` and `'` `&#39;`. null and undefined are shown as nothing, other non-strings with String(). */
        function renderComment(author, text) {
          return `<div class="comment"><b>${author}</b>: ${text}</div>`;
        }

        module.exports = { renderComment };
    '''),
                  "`renderComment(author, text)` escapes exactly the five characters listed in its comment (the ampersand first, so `&amp;` in the input shows as `&amp;amp;`), converts null/undefined to the empty string and other values with `String`. The markup around them is unchanged.",
                  dd(r'''
        'use strict';

        const ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

        function escapeHtml(value) {
          if (value === null || value === undefined) return '';
          return String(value).replace(/[&<>"']/g, (c) => ESCAPES[c]);
        }

        /** HTML of one comment: `<div class="comment"><b>AUTHOR</b>: TEXT</div>`. Author and text are plain text supplied by users: `&` becomes `&amp;`, `<` `&lt;`, `>` `&gt;`,
         *  `"` `&quot;` and `'` `&#39;`. null and undefined are shown as nothing, other non-strings with String(). */
        function renderComment(author, text) {
          return `<div class="comment"><b>${escapeHtml(author)}</b>: ${escapeHtml(text)}</div>`;
        }

        module.exports = { renderComment };
    '''),
                  r'''
    const { renderComment } = require('../src/comment_html');

    test('plain text is unchanged', () => {
      assert.equal(renderComment('Ann', 'hello world'), '<div class="comment"><b>Ann</b>: hello world</div>');
      assert.equal(renderComment('Émile', 'café 中文'), '<div class="comment"><b>Émile</b>: café 中文</div>');
      assert.equal(renderComment(null, undefined), '<div class="comment"><b></b>: </div>');
      assert.equal(renderComment(42, false), '<div class="comment"><b>42</b>: false</div>');
    });

    test('markup characters are escaped', () => {
      assert.equal(renderComment('a & b', '<script>alert(1)</script>'), '<div class="comment"><b>a &amp; b</b>: &lt;script&gt;alert(1)&lt;/script&gt;</div>');
      assert.equal(renderComment('"quoted"', "it's"), '<div class="comment"><b>&quot;quoted&quot;</b>: it&#39;s</div>');
      assert.equal(renderComment('x', '&amp; &lt;'), '<div class="comment"><b>x</b>: &amp;amp; &amp;lt;</div>');
      assert.equal(renderComment('<img src=x onerror=alert(1)>', '"><svg onload=alert(1)>'), '<div class="comment"><b>&lt;img src=x onerror=alert(1)&gt;</b>: &quot;&gt;&lt;svg onload=alert(1)&gt;</div>');
      const out = renderComment('<b>', '</div><div class="evil">');
      assert.equal((out.match(/</g) || []).length, 4);
    });
    '''))

JS.append(js_task("profile-assign", 1, "the profile endpoint", "updateProfile", "CWE-915",
                  "`updateProfile` copies every field of the request body onto the user object with `Object.assign`: a body with `isAdmin: true` escalates privileges, and a JSON body with a `__proto__` key replaces the user's prototype so inherited flags such as `isAdmin` appear out of nowhere.",
                  dd(r'''
        'use strict';

        /** Apply the request body `fields` to the `user` object in place and return it. Members may change `displayName`, `email` and `bio`; any other key (own enumerable keys,
         *  `__proto__` from JSON.parse included) makes the whole update fail with an Error and nothing is changed. */
        function updateProfile(user, fields) {
          Object.assign(user, fields);
          return user;
        }

        module.exports = { updateProfile };
    '''),
                  "`updateProfile(user, fields)` applies only `displayName`, `email` and `bio`, in place, atomically: if the body contains any other key the function throws an `Error` before changing anything. Empty bodies are fine.",
                  dd(r'''
        'use strict';

        const ALLOWED = new Set(['displayName', 'email', 'bio']);

        /** Apply the request body `fields` to the `user` object in place and return it. Members may change `displayName`, `email` and `bio`; any other key (own enumerable keys,
         *  `__proto__` from JSON.parse included) makes the whole update fail with an Error and nothing is changed. */
        function updateProfile(user, fields) {
          const keys = Object.keys(fields);
          const bad = keys.filter((k) => !ALLOWED.has(k));
          if (bad.length) throw new Error('fields not editable: ' + bad.join(', '));
          for (const k of keys) user[k] = fields[k];
          return user;
        }

        module.exports = { updateProfile };
    '''),
                  r'''
    const { updateProfile } = require('../src/profile_assign');

    const base = () => ({ id: 7, displayName: 'Ann', email: 'ann@example.com', bio: '', isAdmin: false });

    test('editable fields', () => {
      const u = base();
      assert.equal(updateProfile(u, { displayName: 'Ann O.', bio: 'hi' }), u);
      assert.deepEqual(u, { id: 7, displayName: 'Ann O.', email: 'ann@example.com', bio: 'hi', isAdmin: false });
      assert.deepEqual(updateProfile(base(), {}), base());
    });

    test('other fields are refused and nothing changes', () => {
      const bodies = [
        { displayName: 'Mallory', isAdmin: true }, { displayName: 'Mallory', id: 1 }, { displayName: 'Mallory', role: 'admin' }, { displayName: 'Mallory', Email: 'x' },
        { displayName: 'Mallory', constructor: 'x' }, { displayName: 'Mallory', toString: 1 }, JSON.parse('{"displayName": "Mallory", "__proto__": {"isAdmin": true}}'), JSON.parse('{"__proto__": null}'),
      ];
      for (const body of bodies) {
        const u = base();
        assert.throws(() => updateProfile(u, body));
        assert.deepEqual({ ...u }, base());
        assert.equal(Object.getPrototypeOf(u), Object.prototype);
        assert.equal(u.isAdmin, false);
      }
      assert.equal(({}).isAdmin, undefined);
    });
    '''))

JS.append(js_task("shell-echo", 1, "the archive tool", "archiveLabel", "CWE-78",
                  "`archiveLabel` builds a shell command line from the archive name (`echo archiving <name>`) and runs it with `exec`: a name such as `x; echo INJECTED` or `$(echo INJECTED)` runs extra commands, and names with quotes or `$` are mangled.",
                  dd(r'''
        'use strict';
        const { execSync } = require('node:child_process');

        /** Runs the labelling tool (stand-in: `echo archiving <name>`) and returns what it printed. The name arrives as ONE argument, unchanged, whatever characters it contains. */
        function archiveLabel(name) {
          return execSync('echo archiving ' + name, { encoding: 'utf8' });
        }

        module.exports = { archiveLabel };
    '''),
                  "`archiveLabel(name)` returns exactly `archiving <name>\\n`: the tool receives the name as a single argument; `;`, `&&`, `|`, `$(...)`, backticks, quotes, `*`, newlines and spaces are ordinary characters. No shell may be involved.",
                  dd(r'''
        'use strict';
        const { execFileSync } = require('node:child_process');

        /** Runs the labelling tool (stand-in: `echo archiving <name>`) and returns what it printed. The name arrives as ONE argument, unchanged, whatever characters it contains. */
        function archiveLabel(name) {
          return execFileSync('echo', ['archiving', String(name)], { encoding: 'utf8' });
        }

        module.exports = { archiveLabel };
    '''),
                  r'''
    const { archiveLabel } = require('../src/shell_echo');

    test('the name is one argument', () => {
      const names = ['plain', 'two words', "it's", 'say "hi"', '$HOME and ${PATH}', 'wild * ? [a-z]', 'a;b', 'x; echo INJECTED', 'x && echo INJECTED', 'x | echo INJECTED', '$(echo INJECTED)', '`echo INJECTED`',
        'x\necho INJECTED', "'; echo INJECTED; '", '"; echo INJECTED; "', '-n', '-e', 'back\\slash', 'tab\there', 'ünïcöde'];
      for (const name of names) assert.equal(archiveLabel(name), `archiving ${name}\n`, JSON.stringify(name));
    });
    '''))

# ---------------------------------------------------------------------------------------------------------------------------------
JS.append(js_task("query-builder", 2, "the user search API", "findUserQuery", "CWE-89",
                  "`findUserQuery` and `listUsersQuery` paste the search term and the sort column into the SQL text (`WHERE name = '<name>'`, `ORDER BY <column>`), so `' OR '1'='1` returns every user and `name; DROP TABLE users` is a stacked statement waiting for a driver that allows it.",
                  dd(r'''
        'use strict';

        /** The parameterised query that finds users by exact name: `{ text, values }` where `text` contains only the placeholder `$1` and no part of the name, and `values` is `[name]`.
         *  The statement is `SELECT id, name, email FROM users WHERE name = $1`. */
        function findUserQuery(name) {
          return { text: "SELECT id, name, email FROM users WHERE name = '" + name + "'", values: [] };
        }

        /** The query that lists users ordered by `column` (one of `id`, `name`, `email`, `created`) in `direction` (`asc` or `desc`, any letter case, default asc):
         *  `SELECT id, name, email FROM users ORDER BY <column> <ASC|DESC>`. Anything else throws an Error. */
        function listUsersQuery(column, direction = 'asc') {
          return { text: `SELECT id, name, email FROM users ORDER BY ${column} ${direction}`, values: [] };
        }

        module.exports = { findUserQuery, listUsersQuery };
    '''),
                  "`findUserQuery(name)` returns `{ text: 'SELECT id, name, email FROM users WHERE name = $1', values: [name] }` for every name (the name never appears in `text`). `listUsersQuery(column, direction)` only accepts the listed columns and directions (it cannot be parameterised, so it validates) and returns the normalised upper-case direction; anything else throws.",
                  dd(r'''
        'use strict';

        const COLUMNS = new Set(['id', 'name', 'email', 'created']);

        /** The parameterised query that finds users by exact name: `{ text, values }` where `text` contains only the placeholder `$1` and no part of the name, and `values` is `[name]`.
         *  The statement is `SELECT id, name, email FROM users WHERE name = $1`. */
        function findUserQuery(name) {
          return { text: 'SELECT id, name, email FROM users WHERE name = $1', values: [name] };
        }

        /** The query that lists users ordered by `column` (one of `id`, `name`, `email`, `created`) in `direction` (`asc` or `desc`, any letter case, default asc):
         *  `SELECT id, name, email FROM users ORDER BY <column> <ASC|DESC>`. Anything else throws an Error. */
        function listUsersQuery(column, direction = 'asc') {
          const dir = typeof direction === 'string' ? direction.toLowerCase() : '';
          if (typeof column !== 'string' || !COLUMNS.has(column) || (dir !== 'asc' && dir !== 'desc')) throw new Error('invalid sort');
          return { text: `SELECT id, name, email FROM users ORDER BY ${column} ${dir.toUpperCase()}`, values: [] };
        }

        module.exports = { findUserQuery, listUsersQuery };
    '''),
                  r'''
    const { findUserQuery, listUsersQuery } = require('../src/query_builder');

    test('lookups are parameterised', () => {
      for (const name of ['ann', "O'Brien", "' OR '1'='1", 'x; DROP TABLE users; --', '', '$1', '%', '"quoted"', 'é', 'a\nb']) {
        const q = findUserQuery(name);
        assert.deepEqual(q, { text: 'SELECT id, name, email FROM users WHERE name = $1', values: [name] });
      }
    });

    test('sort columns are validated', () => {
      assert.deepEqual(listUsersQuery('name'), { text: 'SELECT id, name, email FROM users ORDER BY name ASC', values: [] });
      assert.deepEqual(listUsersQuery('created', 'DESC'), { text: 'SELECT id, name, email FROM users ORDER BY created DESC', values: [] });
      assert.deepEqual(listUsersQuery('email', 'dEsC').text, 'SELECT id, name, email FROM users ORDER BY email DESC');
      for (const [column, direction] of [['name; DROP TABLE users', 'asc'], ['name', 'asc; DROP TABLE users'], ['(SELECT 1)', 'asc'], ['name,id', 'asc'], ['NAME', 'asc'], ['', 'asc'], ['name', ''], ['name', 'up'], [undefined, 'asc'], ['name', null], ['password', 'asc'], [['name'], 'asc'], ['name', 'desc --']]) {
        assert.ok(throws(() => listUsersQuery(column, direction)), JSON.stringify([column, direction]));
      }
    });
    '''))

JS.append(js_task("url-allowlist", 2, "the webhook sender", "isAllowedTarget", "CWE-918",
                  "`isAllowedTarget` checks the text of the URL with `startsWith('https://hooks.partner.example')`, so `https://hooks.partner.example.evil.io/`, `https://hooks.partner.example@evil.io/` and `https://hooks.partner.example:8443/` are accepted and the sender posts to hosts nobody approved.",
                  dd(r'''
        'use strict';

        /** True when `url` may receive webhooks: an https URL on the partner host `hooks.partner.example` (any path or query, no user info, port 443 may be written out, letter case of the host
         *  is irrelevant). Everything else - other hosts, schemes, ports, unparsable text, non-strings - is false. */
        function isAllowedTarget(url) {
          return url.startsWith('https://hooks.partner.example');
        }

        module.exports = { isAllowedTarget };
    '''),
                  "`isAllowedTarget(url)` parses the URL with the WHATWG `URL` class and compares the parsed parts (protocol `https:`, hostname exactly `hooks.partner.example`, port empty or 443, no username/password). Whatever the parser disagrees with the old string test about is not allowed.",
                  dd(r'''
        'use strict';

        /** True when `url` may receive webhooks: an https URL on the partner host `hooks.partner.example` (any path or query, no user info, port 443 may be written out, letter case of the host
         *  is irrelevant). Everything else - other hosts, schemes, ports, unparsable text, non-strings - is false. */
        function isAllowedTarget(url) {
          if (typeof url !== 'string') return false;
          let u;
          try {
            u = new URL(url);
          } catch (e) {
            return false;
          }
          return u.protocol === 'https:' && u.hostname === 'hooks.partner.example' && (u.port === '' || u.port === '443') && u.username === '' && u.password === '';
        }

        module.exports = { isAllowedTarget };
    '''),
                  r'''
    const { isAllowedTarget } = require('../src/url_allowlist');

    test('partner urls', () => {
      for (const url of ['https://hooks.partner.example', 'https://hooks.partner.example/', 'https://hooks.partner.example/a/b?x=1&y=2', 'https://hooks.partner.example:443/x', 'HTTPS://HOOKS.Partner.Example/x']) {
        assert.equal(isAllowedTarget(url), true, url);
      }
    });

    test('everything else', () => {
      for (const url of ['https://hooks.partner.example.evil.io/x', 'https://hooks.partner.example@evil.io/', 'https://hooks.partner.exampleevil.io/', 'http://hooks.partner.example/', 'https://hooks.partner.example:8443/',
        'https://hooks.partner.example:pw@evil.io/', 'https://evil.io\\@hooks.partner.example/', 'https://evil.io\\.hooks.partner.example/', '//hooks.partner.example/x', 'https://evil.io/https://hooks.partner.example',
        'ftp://hooks.partner.example/', 'https://user@hooks.partner.example/', 'not a url', '', 'https://hooks.partner.example:99999/', 'javascript:alert(1)//https://hooks.partner.example', 'https://hooks.partner.example.']) {
        assert.equal(isAllowedTarget(url), false, url);
      }
      for (const value of [null, undefined, 5, {}, ['https://hooks.partner.example/']]) assert.equal(isAllowedTarget(value), false);
    });
    '''))

JS.append(js_task("upload-path", 2, "the upload viewer", "readUpload", "CWE-22",
                  "`readUpload` joins the requested name onto the upload directory with `path.join`, which happily normalises `../` out of the directory: `GET /files?name=../../etc/passwd` (or an absolute path, or a symlink that was uploaded) reads files anywhere the server can.",
                  dd(r'''
        'use strict';
        const fs = require('node:fs');
        const path = require('node:path');

        /** The text of the upload `name` inside the directory `root` (UTF-8). `name` is a relative path below `root` (`a.txt`, `sub/b.txt`; `sub/../a.txt` is fine because it stays inside).
         *  Anything that resolves outside `root` - `..` climbing, absolute paths, symbolic links pointing out - throws an Error, as do names with NUL bytes and non-strings. */
        function readUpload(root, name) {
          return fs.readFileSync(path.join(root, name), 'utf8');
        }

        module.exports = { readUpload };
    '''),
                  "`readUpload(root, name)` keeps working for every name that stays inside `root` (also `sub/../ok.txt`, `a..b.txt`, `..hidden`) and throws for everything that leaves it, including symbolic links inside `root` that point outside (check the real path).",
                  dd(r'''
        'use strict';
        const fs = require('node:fs');
        const path = require('node:path');

        function inside(root, target) {
          const rel = path.relative(root, target);
          return rel === '' || (!rel.startsWith('..' + path.sep) && rel !== '..' && !path.isAbsolute(rel));
        }

        /** The text of the upload `name` inside the directory `root` (UTF-8). `name` is a relative path below `root` (`a.txt`, `sub/b.txt`; `sub/../a.txt` is fine because it stays inside).
         *  Anything that resolves outside `root` - `..` climbing, absolute paths, symbolic links pointing out - throws an Error, as do names with NUL bytes and non-strings. */
        function readUpload(root, name) {
          if (typeof name !== 'string' || name.includes('\0') || path.isAbsolute(name)) throw new Error('invalid name');
          const realRoot = fs.realpathSync(root);
          const target = path.resolve(realRoot, name);
          if (!inside(realRoot, target)) throw new Error('outside the upload directory');
          const real = fs.realpathSync(target);
          if (!inside(realRoot, real)) throw new Error('outside the upload directory');
          return fs.readFileSync(real, 'utf8');
        }

        module.exports = { readUpload };
    '''),
                  r'''
    const { readUpload } = require('../src/upload_path');

    function setup() {
      const base = fs.mkdtempSync(path.join(os.tmpdir(), 'sec-'));
      const root = path.join(base, 'uploads');
      fs.mkdirSync(path.join(root, 'sub'), { recursive: true });
      fs.writeFileSync(path.join(root, 'ok.txt'), 'ok');
      fs.writeFileSync(path.join(root, 'sub', 'a.txt'), 'a');
      fs.writeFileSync(path.join(root, 'a..b.txt'), 'dots');
      fs.writeFileSync(path.join(root, '..hidden'), 'hidden');
      fs.writeFileSync(path.join(base, 'secret.txt'), 'SECRET');
      fs.writeFileSync(path.join(base, 'uploads-evil.txt'), 'SIBLING');
      fs.symlinkSync(path.join(base, 'secret.txt'), path.join(root, 'link.txt'));
      fs.symlinkSync(path.join(root, 'ok.txt'), path.join(root, 'inner-link.txt'));
      return { base, root };
    }

    test('names inside the directory', () => {
      const { root } = setup();
      for (const [name, want] of [['ok.txt', 'ok'], ['sub/a.txt', 'a'], ['sub/../ok.txt', 'ok'], ['./ok.txt', 'ok'], ['a..b.txt', 'dots'], ['..hidden', 'hidden'], ['inner-link.txt', 'ok']]) {
        assert.equal(readUpload(root, name), want, name);
      }
    });

    test('names that leave it', () => {
      const { base, root } = setup();
      for (const name of ['../secret.txt', 'sub/../../secret.txt', path.join(base, 'secret.txt'), '/etc/hostname', '../uploads-evil.txt', '../uploads/../secret.txt', 'link.txt', 'ok.txt\0.png', '', '..', '.', '../../../../../../etc/hostname']) {
        let result;
        try { result = readUpload(root, name); } catch (e) { result = undefined; }
        assert.ok(result === undefined || (name === '.' || name === ''), JSON.stringify(name) + ' returned ' + JSON.stringify(result));
        assert.notEqual(result, 'SECRET');
        assert.notEqual(result, 'SIBLING');
      }
      for (const value of [null, undefined, 5, ['ok.txt']]) assert.ok(throws(() => readUpload(root, value)));
    });
    '''))

JS.append(js_task("search-regex", 2, "the catalogue search", "filterItems", "CWE-1333",
                  "`filterItems` turns the search box content into a regular expression: `(` or `[` makes the request throw, `.` and `*` match more than the user typed, and a query like `(a+)+$` against a long item name makes the single-threaded server spin in catastrophic backtracking.",
                  dd(r'''
        'use strict';

        /** The items (strings) that contain `query` as plain text, case-insensitively, in their original order. The query is data, not a pattern: `.`, `*`, `(`, `[`, `\` and every other character
         *  match themselves. An empty query matches everything. Must be fast whatever the query and the items look like. */
        function filterItems(items, query) {
          const re = new RegExp(query, 'i');
          return items.filter((item) => re.test(item));
        }

        module.exports = { filterItems };
    '''),
                  "`filterItems(items, query)` is a case-insensitive substring search (no regular expressions): `a.c` finds `a.c` but not `abc`, `(` and `[` are harmless, hostile patterns cost nothing.",
                  dd(r'''
        'use strict';

        /** The items (strings) that contain `query` as plain text, case-insensitively, in their original order. The query is data, not a pattern: `.`, `*`, `(`, `[`, `\` and every other character
         *  match themselves. An empty query matches everything. Must be fast whatever the query and the items look like. */
        function filterItems(items, query) {
          const needle = String(query).toLowerCase();
          return items.filter((item) => String(item).toLowerCase().includes(needle));
        }

        module.exports = { filterItems };
    '''),
                  r'''
    const { filterItems } = require('../src/search_regex');

    test('plain substring search', () => {
      const items = ['abc', 'a.c', 'A*C', 'x(y', 'p[q', 'back\\slash', 'ABCdef', 'café'];
      assert.deepEqual(filterItems(items, 'a.c'), ['a.c']);
      assert.deepEqual(filterItems(items, 'A*'), ['A*C']);
      assert.deepEqual(filterItems(items, '('), ['x(y']);
      assert.deepEqual(filterItems(items, '['), ['p[q']);
      assert.deepEqual(filterItems(items, '\\'), ['back\\slash']);
      assert.deepEqual(filterItems(items, 'ABC'), ['abc', 'ABCdef']);
      assert.deepEqual(filterItems(items, ''), items);
      assert.deepEqual(filterItems(items, 'CAFÉ'), ['café']);
      assert.deepEqual(filterItems(items, '.*'), []);
      assert.deepEqual(filterItems(items, '(?:'), []);
    });

    test('hostile queries are cheap', () => {
      const code = "const { filterItems } = require('./src/search_regex'); const items = ['a'.repeat(60) + '!']; " +
        "filterItems(items, '(a+)+$'); filterItems(items, '^(a|aa)+$'); filterItems(items, '([a-z]+)*x'); filterItems(['x'.repeat(100000)], '(x+x+)+y');";
      assert.ok(finishes(code), 'catastrophic backtracking');
    });
    '''))

JS.append(js_task("token-alg", 2, "the API tokens", "verifyToken", "CWE-347",
                  "`verifyToken` reads the algorithm from the token header and treats `alg: none` as \"nothing to verify\": a token with any claims and an empty signature is accepted, and other `alg` values are verified as HS256 without question.",
                  dd(r'''
        'use strict';
        const crypto = require('node:crypto');

        const b64 = (buf) => Buffer.from(buf).toString('base64url');

        /** `header.payload.signature` (base64url, HS256, no padding) for the claims object. */
        function signToken(claims, secret) {
          const head = b64(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
          const body = b64(JSON.stringify(claims));
          const sig = crypto.createHmac('sha256', secret).update(head + '.' + body).digest();
          return head + '.' + body + '.' + b64(sig);
        }

        /** The claims of a valid token made by signToken with `secret`; throws an Error for everything else. The algorithm is chosen by the server: the header must say HS256, exactly. */
        function verifyToken(token, secret) {
          const [head, body, sig] = token.split('.');
          const header = JSON.parse(Buffer.from(head, 'base64url').toString());
          if (header.alg !== 'none') {
            const expected = crypto.createHmac('sha256', secret).update(head + '.' + body).digest('base64url');
            if (expected !== sig) throw new Error('bad signature');
          }
          return JSON.parse(Buffer.from(body, 'base64url').toString());
        }

        module.exports = { signToken, verifyToken };
    '''),
                  "`verifyToken(token, secret)` accepts only tokens whose header `alg` is exactly `HS256` and whose HMAC verifies (compare with `crypto.timingSafeEqual`, handling length differences). `none`, other spellings, other algorithms, missing or empty signatures, wrong part counts and bad encodings all throw.",
                  dd(r'''
        'use strict';
        const crypto = require('node:crypto');

        const b64 = (buf) => Buffer.from(buf).toString('base64url');

        /** `header.payload.signature` (base64url, HS256, no padding) for the claims object. */
        function signToken(claims, secret) {
          const head = b64(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
          const body = b64(JSON.stringify(claims));
          const sig = crypto.createHmac('sha256', secret).update(head + '.' + body).digest();
          return head + '.' + body + '.' + b64(sig);
        }

        /** The claims of a valid token made by signToken with `secret`; throws an Error for everything else. The algorithm is chosen by the server: the header must say HS256, exactly. */
        function verifyToken(token, secret) {
          if (typeof token !== 'string') throw new Error('bad token');
          const parts = token.split('.');
          if (parts.length !== 3) throw new Error('bad token');
          const [head, body, sig] = parts;
          const header = JSON.parse(Buffer.from(head, 'base64url').toString());
          if (header === null || typeof header !== 'object' || header.alg !== 'HS256') throw new Error('unsupported algorithm');
          const expected = crypto.createHmac('sha256', secret).update(head + '.' + body).digest();
          const given = Buffer.from(sig, 'base64url');
          if (given.length !== expected.length || !crypto.timingSafeEqual(given, expected)) throw new Error('bad signature');
          return JSON.parse(Buffer.from(body, 'base64url').toString());
        }

        module.exports = { signToken, verifyToken };
    '''),
                  r'''
    const crypto = require('node:crypto');
    const { signToken, verifyToken } = require('../src/token_alg');

    const b64 = (v) => Buffer.from(typeof v === 'string' ? v : JSON.stringify(v)).toString('base64url');
    const forge = (header, claims, sig = '') => b64(header) + '.' + b64(claims) + '.' + sig;

    test('valid tokens', () => {
      const claims = { sub: 'ann', admin: false, n: [1, 2] };
      assert.deepEqual(verifyToken(signToken(claims, 'secret'), 'secret'), claims);
    });

    test('the algorithm is not negotiable', () => {
      const claims = { sub: 'admin' };
      for (const alg of ['none', 'None', 'NONE', '', 'HS512', 'hs256', 'RS256', 'HS256 ', null, ['HS256']]) {
        const header = { typ: 'JWT', alg };
        assert.ok(throws(() => verifyToken(forge(header, claims), 'secret')), String(alg));
        assert.ok(throws(() => verifyToken(forge(header, claims, 'garbage'), 'secret')), String(alg));
        const head = b64(header);
        const sig = crypto.createHmac('sha256', 'secret').update(head + '.' + b64(claims)).digest('base64url');
        assert.ok(throws(() => verifyToken(head + '.' + b64(claims) + '.' + sig, 'secret')), 'valid hmac, header ' + String(alg));
      }
      assert.ok(throws(() => verifyToken(forge({ typ: 'JWT' }, claims), 'secret')));
    });

    test('malformed or forged tokens', () => {
      const good = signToken({ sub: 'ann' }, 'secret');
      const [h, , s] = good.split('.');
      for (const tok of [good + 'x', good.slice(0, -3), h + '.' + b64({ sub: 'admin' }) + '.' + s, good + '.extra', 'a.b', '', '..', h + '.' + good.split('.')[1] + '.', signToken({ sub: 'x' }, 'other'), null, 5]) {
        assert.ok(throws(() => verifyToken(tok, 'secret')), String(tok));
      }
    });
    '''))

# ---------------------------------------------------------------------------------------------------------------------------------
JS.append(js_task("deep-merge", 2, "the settings service", "deepMerge", "CWE-1321",
                  "`deepMerge` recurses into whatever keys the source has: merging a JSON body such as `{\"__proto__\": {\"isAdmin\": true}}` writes `isAdmin` into `Object.prototype`, so every object in the process suddenly has it (prototype pollution).",
                  dd(r'''
        'use strict';

        function isObject(value) {
          return typeof value === 'object' && value !== null && !Array.isArray(value);
        }

        /** Recursively merge the plain objects of `source` into `target` (in place) and return `target`: nested objects are merged, arrays and scalars replace what is there (null too).
         *  The keys `__proto__`, `constructor` and `prototype` are never copied or followed: they are skipped silently. */
        function deepMerge(target, source) {
          for (const key of Object.keys(source)) {
            if (isObject(source[key])) {
              if (!isObject(target[key])) target[key] = {};
              deepMerge(target[key], source[key]);
            } else {
              target[key] = source[key];
            }
          }
          return target;
        }

        module.exports = { deepMerge };
    '''),
                  "`deepMerge(target, source)` keeps its merge semantics (nested objects merged, arrays/scalars/null replace) and silently skips the keys `__proto__`, `constructor` and `prototype` at every depth; `Object.prototype` is never modified and neither are other prototypes reachable through the target.",
                  dd(r'''
        'use strict';

        const FORBIDDEN = new Set(['__proto__', 'constructor', 'prototype']);

        function isObject(value) {
          return typeof value === 'object' && value !== null && !Array.isArray(value);
        }

        /** Recursively merge the plain objects of `source` into `target` (in place) and return `target`: nested objects are merged, arrays and scalars replace what is there (null too).
         *  The keys `__proto__`, `constructor` and `prototype` are never copied or followed: they are skipped silently. */
        function deepMerge(target, source) {
          for (const key of Object.keys(source)) {
            if (FORBIDDEN.has(key)) continue;
            const own = Object.prototype.hasOwnProperty.call(target, key);
            if (isObject(source[key])) {
              if (!own || !isObject(target[key])) target[key] = {};
              deepMerge(target[key], source[key]);
            } else {
              target[key] = source[key];
            }
          }
          return target;
        }

        module.exports = { deepMerge };
    '''),
                  r'''
    const { deepMerge } = require('../src/deep_merge');

    const KEYS = ['polluted', 'isAdmin', 'p2', 'p3'];
    function clean() { for (const k of KEYS) { delete Object.prototype[k]; } }
    afterEach(clean);

    test('merging', () => {
      const t = { a: 1, b: { c: 2, d: { e: 3 } }, list: [1, 2], keep: 'x' };
      const out = deepMerge(t, { b: { d: { f: 4 }, g: 5 }, list: [9], n: null, a: { nested: true }, keep: undefined });
      assert.equal(out, t);
      assert.deepEqual(t, { a: { nested: true }, b: { c: 2, d: { e: 3, f: 4 }, g: 5 }, list: [9], keep: undefined, n: null });
      assert.deepEqual(deepMerge({}, { x: { y: { z: 1 } } }), { x: { y: { z: 1 } } });
      assert.deepEqual(deepMerge({ proto: 1 }, { proto: 2, constructors: 3, prototypes: 4 }), { proto: 2, constructors: 3, prototypes: 4 });
      assert.deepEqual(deepMerge({ x: 1 }, {}), { x: 1 });
    });

    test('prototype pollution is impossible', () => {
      for (const body of ['{"__proto__": {"polluted": "yes"}}', '{"a": {"__proto__": {"isAdmin": true}}}', '{"constructor": {"prototype": {"p2": 1}}}', '{"a": {"constructor": {"prototype": {"p3": 1}}}}',
        '{"__proto__": {"__proto__": {"polluted": 1}}}', '{"x": {"prototype": {"polluted": 1}}, "ok": 1}']) {
        const target = { a: {} };
        deepMerge(target, JSON.parse(body));
        for (const k of KEYS) {
          assert.equal(Object.prototype[k], undefined, body + ' polluted ' + k);
          assert.equal(({})[k], undefined);
          assert.equal(target[k], undefined);
        }
        assert.equal(Object.getPrototypeOf(target), Object.prototype);
        assert.equal(Object.getPrototypeOf(target.a), Object.prototype);
      }
      const t = deepMerge({}, JSON.parse('{"__proto__": {"polluted": 1}, "ok": 1}'));
      assert.equal(t.ok, 1);
      assert.equal(Object.prototype.hasOwnProperty.call(t, '__proto__'), false);
    });
    '''))

JS.append(js_task("set-path", 3, "the form binding layer", "setPath", "CWE-1321",
                  "`setPath(obj, 'a.b.c', value)` walks the dotted path from user-chosen form field names (`user.address.city`) and creates what is missing; a field named `__proto__.isAdmin` walks into `Object.prototype` and sets the flag on every object of the process.",
                  dd(r'''
        'use strict';

        /** Sets the value at a dotted path (`'a.b.c'`, or an array of keys) inside `obj`, creating missing objects on the way - arrays when the NEXT key is a non-negative integer
         *  (`items.0.name`) - and returns `obj`. A path that contains the segment `__proto__`, `constructor` or `prototype`, an empty path or an empty segment is rejected with a TypeError
         *  *before* anything is changed. Only own properties are followed; inherited objects are never modified. */
        function setPath(obj, path, value) {
          const keys = typeof path === 'string' ? path.split('.') : path;
          let cur = obj;
          for (let i = 0; i < keys.length - 1; i++) {
            const k = keys[i];
            if (typeof cur[k] !== 'object' || cur[k] === null) cur[k] = /^\d+$/.test(keys[i + 1]) ? [] : {};
            cur = cur[k];
          }
          cur[keys[keys.length - 1]] = value;
          return obj;
        }

        module.exports = { setPath };
    '''),
                  "`setPath(obj, path, value)` validates the whole path first (TypeError for `__proto__`, `constructor`, `prototype` segments, empty paths and empty segments) and only then writes. Creation of objects/arrays and replacement of non-object values on the way work as before; inherited properties are never followed or written.",
                  dd(r'''
        'use strict';

        const FORBIDDEN = new Set(['__proto__', 'constructor', 'prototype']);

        /** Sets the value at a dotted path (`'a.b.c'`, or an array of keys) inside `obj`, creating missing objects on the way - arrays when the NEXT key is a non-negative integer
         *  (`items.0.name`) - and returns `obj`. A path that contains the segment `__proto__`, `constructor` or `prototype`, an empty path or an empty segment is rejected with a TypeError
         *  *before* anything is changed. Only own properties are followed; inherited objects are never modified. */
        function setPath(obj, path, value) {
          const keys = typeof path === 'string' ? path.split('.') : Array.from(path);
          if (keys.length === 0 || keys.some((k) => typeof k !== 'string' && typeof k !== 'number')) throw new TypeError('invalid path');
          const names = keys.map(String);
          if (names.some((k) => k === '' || FORBIDDEN.has(k))) throw new TypeError('invalid path segment');
          let cur = obj;
          for (let i = 0; i < names.length - 1; i++) {
            const k = names[i];
            const own = Object.prototype.hasOwnProperty.call(cur, k);
            if (!own || typeof cur[k] !== 'object' || cur[k] === null) cur[k] = /^\d+$/.test(names[i + 1]) ? [] : {};
            cur = cur[k];
          }
          cur[names[names.length - 1]] = value;
          return obj;
        }

        module.exports = { setPath };
    '''),
                  r'''
    const { setPath } = require('../src/set_path');

    const KEYS = ['polluted', 'isAdmin', 'p2', 'p3', 'toString2'];
    afterEach(() => { for (const k of KEYS) delete Object.prototype[k]; });

    test('creating and replacing', () => {
      const o = {};
      assert.equal(setPath(o, 'a.b.c', 1), o);
      assert.deepEqual(o, { a: { b: { c: 1 } } });
      setPath(o, 'a.b.d', 2);
      setPath(o, 'items.0.name', 'x');
      setPath(o, 'items.1.name', 'y');
      assert.deepEqual(o, { a: { b: { c: 1, d: 2 } }, items: [{ name: 'x' }, { name: 'y' }] });
      assert.ok(Array.isArray(o.items));
      setPath(o, ['a', 'b', 'c'], 9);
      setPath(o, 'a.b.c.deeper', 5);
      assert.deepEqual(o.a.b.c, { deeper: 5 });
      assert.deepEqual(setPath({}, 'single', 1), { single: 1 });
      assert.deepEqual(setPath({ x: null }, 'x.y', 1), { x: { y: 1 } });
      assert.deepEqual(setPath({}, ['a.b', 'c'], 1), { 'a.b': { c: 1 } });
    });

    test('forbidden segments change nothing', () => {
      for (const p of ['__proto__.polluted', 'a.__proto__.isAdmin', 'constructor.prototype.p2', 'a.constructor.prototype.p3', ['__proto__', 'polluted'], 'prototype.polluted', 'a.b.__proto__', '', 'a..b', '.a', 'a.', []]) {
        const o = { keep: 1 };
        assert.ok(throws(() => setPath(o, p, true)), JSON.stringify(p));
        assert.deepEqual(o, { keep: 1 }, JSON.stringify(p));
        for (const k of KEYS) assert.equal(Object.prototype[k], undefined, k);
      }
      const o = {};
      assert.ok(throws(() => setPath(o, 'fresh.__proto__.isAdmin', true)));
      assert.deepEqual(o, {});
      assert.equal(({}).isAdmin, undefined);
    });
    '''))

JS.append(js_task("slug-regex", 3, "the CMS routes", "isValidSlug", "CWE-1333",
                  "`isValidSlug` uses `/^([a-z0-9]+-?)+$/`: a 40-character slug followed by an invalid character makes the engine try every way of splitting the run of letters, which takes exponential time, and a single request freezes the whole single-threaded server.",
                  dd(r'''
        'use strict';

        /** True when `s` is a slug: lower-case letters and digits in groups separated by single hyphens (`my-post-2`), no leading, trailing or doubled hyphens, at least one character, at most 200.
         *  Must answer quickly for every input. */
        function isValidSlug(s) {
          return typeof s === 'string' && /^([a-z0-9]+-?)+$/.test(s);
        }

        module.exports = { isValidSlug };
    '''),
                  "`isValidSlug(s)` follows its comment exactly (the old pattern also accepted a trailing hyphen: `abc-` is no longer valid) and runs in linear time for any input, up to megabytes.",
                  dd(r'''
        'use strict';

        const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

        /** True when `s` is a slug: lower-case letters and digits in groups separated by single hyphens (`my-post-2`), no leading, trailing or doubled hyphens, at least one character, at most 200.
         *  Must answer quickly for every input. */
        function isValidSlug(s) {
          return typeof s === 'string' && s.length <= 200 && SLUG.test(s);
        }

        module.exports = { isValidSlug };
    '''),
                  r'''
    const { isValidSlug } = require('../src/slug_regex');

    test('table', () => {
      for (const s of ['a', 'my-post', 'my-post-2', '2024-review', 'a1-b2-c3', 'x'.repeat(200)]) assert.equal(isValidSlug(s), true, s);
      for (const s of ['', '-a', 'a-', 'a--b', 'My-Post', 'a_b', 'a b', 'a.b', 'é', 'x'.repeat(201), 'a-', '-', '--', 'a\n', null, undefined, 5]) assert.equal(isValidSlug(s), false, String(s));
    });

    test('adversarial inputs finish', () => {
      const code = "const { isValidSlug } = require('./src/slug_regex'); " +
        "for (const s of ['a'.repeat(40) + '!', 'ab-'.repeat(30) + '!', 'a'.repeat(100000) + '!', ('a-'.repeat(50000)) + '!', '1'.repeat(30) + '_']) if (isValidSlug(s) !== false) process.exit(3);";
      assert.ok(finishes(code), 'catastrophic backtracking');
    });
    '''))

JS.append(js_task("calculator", 3, "the dashboard calculator", "calculate", "CWE-95",
                  "`calculate` runs what the user typed through `new Function('return ' + expr)()`: `(globalThis.pwned = 1)`, `constructor.constructor('...')()` or `process.exit()` execute arbitrary JavaScript in the server process.",
                  dd(r'''
        'use strict';

        /** The value of an arithmetic expression: decimal numbers (`12`, `3.5`, `.5`), the binary operators `+ - * / % **`, unary `+` and `-`, and parentheses; whitespace is ignored.
         *  `**` is right-associative and binds tighter than unary minus (`-2 ** 2` is -4); `*`, `/`, `%` bind tighter than `+`, `-`. Division or modulo by zero, an exponent above 100 in absolute value,
         *  any other character or word, an unbalanced parenthesis, an empty expression and non-strings throw an Error. */
        function calculate(expr) {
          return new Function('return ' + expr)();
        }

        module.exports = { calculate };
    '''),
                  "`calculate(expr)` is a small recursive-descent (or shunting-yard) evaluator for the grammar in its comment; it never evaluates JavaScript. Results are JavaScript numbers; the usual floating point rules apply (`0.1 + 0.2`).",
                  dd(r'''
        'use strict';

        /** The value of an arithmetic expression: decimal numbers (`12`, `3.5`, `.5`), the binary operators `+ - * / % **`, unary `+` and `-`, and parentheses; whitespace is ignored.
         *  `**` is right-associative and binds tighter than unary minus (`-2 ** 2` is -4); `*`, `/`, `%` bind tighter than `+`, `-`. Division or modulo by zero, an exponent above 100 in absolute value,
         *  any other character or word, an unbalanced parenthesis, an empty expression and non-strings throw an Error. */
        function calculate(expr) {
          if (typeof expr !== 'string' || expr.length > 500) throw new Error('bad expression');
          const tokens = expr.match(/\s*(\d+\.?\d*|\.\d+|\*\*|[-+*/%()]|\S)/g);
          if (!tokens) throw new Error('empty expression');
          const toks = tokens.map((t) => t.trim());
          let pos = 0;
          const peek = () => toks[pos];
          const next = () => toks[pos++];

          function primary() {
            const t = next();
            if (t === undefined) throw new Error('unexpected end');
            if (t === '(') {
              const v = additive();
              if (next() !== ')') throw new Error('unbalanced parenthesis');
              return v;
            }
            if (/^(\d+\.?\d*|\.\d+)$/.test(t)) return Number(t);
            throw new Error('unexpected ' + t);
          }
          function power() {
            const base = primary();
            if (peek() === '**') {
              next();
              const exponent = unary();
              if (Math.abs(exponent) > 100) throw new Error('exponent too large');
              return base ** exponent;
            }
            return base;
          }
          function unary() {
            if (peek() === '-') { next(); return -unary(); }
            if (peek() === '+') { next(); return unary(); }
            return power();
          }
          function multiplicative() {
            let v = unary();
            while (peek() === '*' || peek() === '/' || peek() === '%') {
              const op = next();
              const r = unary();
              if ((op === '/' || op === '%') && r === 0) throw new Error('division by zero');
              v = op === '*' ? v * r : op === '/' ? v / r : v % r;
            }
            return v;
          }
          function additive() {
            let v = multiplicative();
            while (peek() === '+' || peek() === '-') {
              const op = next();
              const r = multiplicative();
              v = op === '+' ? v + r : v - r;
            }
            return v;
          }

          const result = additive();
          if (pos !== toks.length) throw new Error('unexpected ' + toks[pos]);
          return result;
        }

        module.exports = { calculate };
    '''),
                  r'''
    const { calculate } = require('../src/calculator');

    test('arithmetic', () => {
      for (const [expr, want] of [['1+2*3', 7], ['(1+2)*3', 9], ['7 % 4', 3], ['-3 % 5', -3], ['2 ** 3 ** 2', 512], ['-2 ** 2', -4], ['(-2) ** 2', 4], ['2 ** -1', 0.5], ['1/2', 0.5], ['.5 + .25', 0.75],
        ['10 - 2 - 3', 5], ['  4  ', 4], ['-(-3)', 3], ['+5', 5], ['2*-3', -6], ['1.5 * 4', 6], ['((((2))))', 2], ['0.1 + 0.2', 0.1 + 0.2], ['100 / 8 / 5', 2.5], ['2 ** 100', 2 ** 100], ['3.', 3]]) {
        assert.equal(calculate(expr), want, expr);
      }
    });

    test('nothing but arithmetic runs', () => {
      delete globalThis.__pwned;
      for (const expr of ['(globalThis.__pwned = 1)', 'globalThis.__pwned = 1', "constructor.constructor('globalThis.__pwned = 1')()", 'process', 'this', '1; globalThis.__pwned = 1', '1 + (globalThis.__pwned = 2)',
        'x', 'Math.max(1, 2)', '"a" + "b"', '[1]', '1 ? 2 : 3', '1 < 2', '1 && 2', '1 / 0', '1 % 0', '2 ** 101', '2 ** -101', '', '   ', '(', '1 +', '1 + * 2', ')', '1 2', '0x10', '1e3', '1_000', '`1`', '~1', '!0', '1,2',
        '1 // 2', '/* c */ 1', "'1'", 'NaN', 'Infinity', '() => 1', 'a.b', '1..2', '1 . 2', '+-+-1x']) {
        assert.ok(throws(() => calculate(expr)), expr);
      }
      assert.equal(globalThis.__pwned, undefined);
      for (const value of [null, undefined, 5, ['1']]) assert.ok(throws(() => calculate(value)));
    });
    '''))

ORDER = ["comment-html", "profile-assign", "shell-echo", "query-builder", "url-allowlist", "upload-path", "search-regex", "token-alg", "deep-merge", "set-path", "slug-regex", "calculator"]
JS.sort(key=lambda s: (s["d"], ORDER.index(s["slug"])))


@family("security-javascript", category="security", lang="javascript", kind="fix", n=12,
        summary="Node.js: XSS escaping, prototype pollution, mass assignment, injection, SSRF allow-lists, path traversal, ReDoS, token algorithm confusion")
def gen_js(rng, n):
    return list(_sec.emit(rng, JS[:n], tags=["javascript", "node"]))
