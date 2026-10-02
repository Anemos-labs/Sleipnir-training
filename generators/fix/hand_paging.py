"""Pagination defects that sit in different layers of a small service (offset paging in python, keyset feed in js)."""
from fx import dd, family
from generators.fix._hand_kit import Base, Bug, tasks_from

# --------------------------------------------------------------------------------------------------------------
# Base A (python): a maintenance-job board with offset pagination: store / pager / api layers.
# --------------------------------------------------------------------------------------------------------------

A_README = dd('''
    # jobboard

    The listing endpoint of a fleet-maintenance board. `jobboard.api.list_jobs(store, params)` takes the query
    parameters as a dict (values may be strings) and returns a dict.

    ## Parameters
    * `page` (default 1): 1-based. A value below 1, or one that is not an integer, is a `ValueError`.
    * `per_page` (default 25): an integer. Values above 100 are *capped* to 100 (not rejected, not reset).
      A value below 1, or a non-integer, is a `ValueError`.
    * `status` (optional): only jobs with this status are listed (and counted).

    ## Result
    `items` (jobs ordered by `id`), `page`, `per_page` (the effective, capped value), `total` (jobs matching the
    filter), `pages`, `prev`, `next`.

    * `pages` = ceil(total / per_page), but never less than 1: an empty listing is still one (empty) page.
    * `next` is the next page number, `None` on the last page. It is never a page that does not exist.
    * `prev` is `None` on page 1; otherwise the previous page number, except that for a page past the end it is
      the last page (`pages`).
    * A page past the end has no items.

    ## Layers
    `store.JobStore` owns the data (`count(status)`, `fetch(offset, limit, status)`: `offset` is 0-based and the
    status filter is applied *before* slicing), `pager` holds the arithmetic, `api` glues them together.
''')

A_STORE = dd('''
    class JobStore:
        """Maintenance jobs, kept ordered by id."""

        def __init__(self, jobs):
            self._jobs = sorted(jobs, key=lambda j: j["id"])

        def _matching(self, status):
            if status is None:
                return self._jobs
            return [j for j in self._jobs if j["status"] == status]

        def count(self, status=None):
            return len(self._matching(status))

        def fetch(self, offset, limit, status=None):
            """`limit` jobs starting at the 0-based `offset` among the jobs that have `status` (all when None)."""
            return self._matching(status)[offset:offset + limit]
''')

A_PAGER = dd('''
    DEFAULT_PER_PAGE = 25
    MAX_PER_PAGE = 100


    def normalize_per_page(raw):
        if raw is None:
            return DEFAULT_PER_PAGE
        n = int(raw)
        if n < 1:
            raise ValueError("per_page must be at least 1")
        return min(n, MAX_PER_PAGE)


    def page_count(total, per_page):
        if total == 0:
            return 1
        return (total + per_page - 1) // per_page


    def offset_of(page, per_page):
        if page < 1:
            raise ValueError("page must be at least 1")
        return (page - 1) * per_page


    def neighbours(page, pages):
        """(prev, next) page numbers."""
        nxt = page + 1 if page < pages else None
        prev = min(page - 1, pages) if page > 1 else None
        return prev, nxt
''')

A_API = dd('''
    from .pager import neighbours, normalize_per_page, offset_of, page_count


    def list_jobs(store, params):
        per_page = normalize_per_page(params.get("per_page"))
        page = int(params.get("page", 1))
        status = params.get("status")
        total = store.count(status)
        pages = page_count(total, per_page)
        items = store.fetch(offset_of(page, per_page), per_page, status)
        prev, nxt = neighbours(page, pages)
        return {
            "items": items,
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": pages,
            "prev": prev,
            "next": nxt,
        }
''')

A_VISIBLE = {
    "tests/test_listing.py": dd('''
        import unittest

        from jobboard.api import list_jobs
        from jobboard.store import JobStore


        def make_jobs(n, statuses=("open",)):
            return [{"id": i, "title": f"job {i}", "status": statuses[i % len(statuses)]} for i in range(1, n + 1)]


        class ListingTests(unittest.TestCase):
            def test_default_page_size(self):
                r = list_jobs(JobStore(make_jobs(60)), {})
                self.assertEqual([j["id"] for j in r["items"]], list(range(1, 26)))
                self.assertEqual((r["page"], r["per_page"], r["total"], r["pages"]), (1, 25, 60, 3))

            def test_second_page_by_string_params(self):
                r = list_jobs(JobStore(make_jobs(12)), {"page": "2", "per_page": "5"})
                self.assertEqual([j["id"] for j in r["items"]], [6, 7, 8, 9, 10])
                self.assertEqual((r["prev"], r["next"]), (1, 3))


        if __name__ == "__main__":
            unittest.main()
    '''),
}

A_HIDDEN = {
    "tests/test_hidden_paging.py": dd('''
        import unittest

        from jobboard.api import list_jobs
        from jobboard.pager import neighbours, normalize_per_page, offset_of, page_count
        from jobboard.store import JobStore


        def make_jobs(n, statuses=("open", "done", "held")):
            return [{"id": i, "title": f"job {i}", "status": statuses[i % len(statuses)]} for i in range(1, n + 1)]


        def ids(r):
            return [j["id"] for j in r["items"]]


        class PagerArithmetic(unittest.TestCase):
            def test_offset(self):
                self.assertEqual(offset_of(1, 25), 0)
                self.assertEqual(offset_of(2, 25), 25)
                self.assertEqual(offset_of(3, 10), 20)
                self.assertEqual(offset_of(7, 1), 6)

            def test_offset_rejects_bad_pages(self):
                for bad in (0, -1, -40):
                    with self.assertRaises(ValueError):
                        offset_of(bad, 10)

            def test_page_count_boundaries(self):
                cases = {(0, 10): 1, (1, 10): 1, (9, 10): 1, (10, 10): 1, (11, 10): 2, (20, 10): 2, (21, 10): 3,
                         (100, 25): 4, (101, 25): 5, (60, 20): 3, (61, 20): 4, (1, 100): 1}
                for (total, per), want in cases.items():
                    self.assertEqual(page_count(total, per), want, (total, per))

            def test_per_page(self):
                self.assertEqual(normalize_per_page(None), 25)
                self.assertEqual(normalize_per_page("40"), 40)
                self.assertEqual(normalize_per_page(100), 100)
                self.assertEqual(normalize_per_page(101), 100)
                self.assertEqual(normalize_per_page("5000"), 100)
                self.assertEqual(normalize_per_page(1), 1)
                for bad in (0, "0", -3):
                    with self.assertRaises(ValueError):
                        normalize_per_page(bad)

            def test_neighbours(self):
                self.assertEqual(neighbours(1, 1), (None, None))
                self.assertEqual(neighbours(1, 3), (None, 2))
                self.assertEqual(neighbours(2, 3), (1, 3))
                self.assertEqual(neighbours(3, 3), (2, None))
                self.assertEqual(neighbours(5, 3), (3, None))
                self.assertEqual(neighbours(4, 3), (3, None))


        class StoreContract(unittest.TestCase):
            def setUp(self):
                self.store = JobStore(make_jobs(30))

            def test_count(self):
                self.assertEqual(self.store.count(), 30)
                self.assertEqual(self.store.count("open"), 10)
                self.assertEqual(self.store.count("nope"), 0)

            def test_fetch_filters_before_slicing(self):
                got = [j["id"] for j in self.store.fetch(0, 3, "open")]
                self.assertEqual(got, [3, 6, 9])
                got = [j["id"] for j in self.store.fetch(3, 4, "open")]
                self.assertEqual(got, [12, 15, 18, 21])
                got = [j["id"] for j in self.store.fetch(8, 10, "open")]
                self.assertEqual(got, [27, 30])

            def test_fetch_unfiltered(self):
                self.assertEqual([j["id"] for j in self.store.fetch(28, 5)], [29, 30])
                self.assertEqual(self.store.fetch(40, 5), [])

            def test_fetch_orders_by_id(self):
                s = JobStore([{"id": 5, "status": "open"}, {"id": 2, "status": "open"}, {"id": 9, "status": "open"}])
                self.assertEqual([j["id"] for j in s.fetch(0, 10)], [2, 5, 9])


        class Listing(unittest.TestCase):
            def test_exact_multiple(self):
                store = JobStore(make_jobs(60))
                r1 = list_jobs(store, {"per_page": 20})
                r3 = list_jobs(store, {"per_page": 20, "page": 3})
                self.assertEqual((r1["pages"], r1["next"], r1["prev"]), (3, 2, None))
                self.assertEqual(ids(r3), list(range(41, 61)))
                self.assertEqual((r3["pages"], r3["next"], r3["prev"]), (3, None, 2))

            def test_one_over(self):
                store = JobStore(make_jobs(61))
                r = list_jobs(store, {"per_page": 20, "page": 4})
                self.assertEqual(ids(r), [61])
                self.assertEqual((r["pages"], r["next"], r["prev"]), (4, None, 3))
                self.assertEqual(list_jobs(store, {"per_page": 20, "page": 3})["next"], 4)

            def test_single_full_page_has_no_next(self):
                store = JobStore(make_jobs(25))
                r = list_jobs(store, {})
                self.assertEqual((len(r["items"]), r["pages"], r["next"], r["prev"]), (25, 1, None, None))

            def test_empty(self):
                r = list_jobs(JobStore([]), {})
                self.assertEqual((r["items"], r["total"], r["pages"], r["prev"], r["next"]), ([], 0, 1, None, None))

            def test_empty_filter_result(self):
                r = list_jobs(JobStore(make_jobs(10)), {"status": "scrapped", "page": "1"})
                self.assertEqual((r["items"], r["total"], r["pages"], r["next"]), ([], 0, 1, None))

            def test_past_the_end(self):
                r = list_jobs(JobStore(make_jobs(30)), {"per_page": 10, "page": 9})
                self.assertEqual((r["items"], r["pages"], r["prev"], r["next"], r["page"]), ([], 3, 3, None, 9))

            def test_per_page_is_capped(self):
                store = JobStore(make_jobs(450, ("open",)))
                r = list_jobs(store, {"per_page": "250"})
                self.assertEqual((len(r["items"]), r["per_page"], r["pages"]), (100, 100, 5))
                r = list_jobs(store, {"per_page": "250", "page": "2"})
                self.assertEqual(ids(r)[:3], [101, 102, 103])
                self.assertEqual(ids(r)[-1], 200)
                r = list_jobs(store, {"per_page": 101, "page": 5})
                self.assertEqual(ids(r), list(range(401, 451)))

            def test_status_filter_pages(self):
                store = JobStore(make_jobs(90))
                open_ids = [i for i in range(1, 91) if i % 3 == 0]
                r = list_jobs(store, {"status": "open", "per_page": 10, "page": 2})
                self.assertEqual(ids(r), open_ids[10:20])
                self.assertEqual((r["total"], r["pages"], r["next"], r["prev"]), (30, 3, 3, 1))
                r = list_jobs(store, {"status": "open", "per_page": 7, "page": 5})
                self.assertEqual(ids(r), open_ids[28:30])
                self.assertEqual((r["pages"], r["next"]), (5, None))

            def test_walking_every_page_covers_everything_once(self):
                store = JobStore(make_jobs(53))
                for status, per in ((None, 7), ("done", 4), ("held", 6), ("open", 100)):
                    seen, page = [], 1
                    while page is not None:
                        r = list_jobs(store, {"page": page, "per_page": per, "status": status})
                        seen.extend(ids(r))
                        page = r["next"]
                    want = [j["id"] for j in store.fetch(0, 1000, status)]
                    self.assertEqual(seen, want, (status, per))

            def test_bad_params(self):
                store = JobStore(make_jobs(5))
                for params in ({"page": 0}, {"page": "-2"}, {"page": "x"}, {"per_page": 0}, {"per_page": "0"}, {"per_page": "many"}):
                    with self.assertRaises(ValueError):
                        list_jobs(store, params)


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _a_prompts():
    p = {}
    p["offset"] = (
        "The jobs board is skipping the first page. Opening the list with no parameters shows jobs starting at 26 instead "
        "of 1, and the last few jobs never appear on any page. `tests/test_reported.py` has a minimal reproduction. "
        "Please fix whatever is wrong in the paging code."
    )
    p["extra-page"] = lambda c: (
        "Dispatchers complain that the job board always has one page too many when the number of jobs divides evenly: "
        "with 60 jobs and `per_page=20` the footer says \"page 1 of "
        + c.probe("from jobboard.api import list_jobs\nfrom jobboard.store import JobStore\n"
                  "s = JobStore([{'id': i, 'status': 'open'} for i in range(1, 61)])\n"
                  "print(list_jobs(s, {'per_page': 20})['pages'])\n")[1]
        + "\" and the last page is blank. Other totals look right. Find and fix it."
    )
    p["cap-fallback"] = (
        "Our mobile client asks for `per_page=500` to cut down on round trips and gets 25 rows back, as if it had not "
        "asked for anything. The README says oversized values are capped. Look into it."
    )
    p["next-on-full-last"] = lambda c: (
        "QA note, ticket JB-212: on the last page the \"Next\" button is sometimes live and leads to an empty page. It "
        "depends on how many jobs there are, which made it look like a data problem, but I think it is in the code. "
        "I reproduced it with 40 jobs and `per_page=20`: page 2 "
        "reports `next: "
        + c.probe("from jobboard.api import list_jobs\nfrom jobboard.store import JobStore\n"
                  "s = JobStore([{'id': i, 'status': 'open'} for i in range(1, 41)])\n"
                  "print(list_jobs(s, {'per_page': 20, 'page': 2})['next'])\n")[1]
        + "`. Fix the root cause rather than hiding the button."
    )
    p["empty-zero"] = (
        "An empty board (nothing matches the status filter) renders as \"page 1 of 0\" and the pager widget divides by "
        "zero. According to README.md an empty listing is one empty page. Please fix it in the code, not in the widget."
    )
    p["filter-after-slice"] = (
        "Tester note: filtering the board by status gives ragged pages. With 90 jobs of which 30 are `open`, "
        "`status=open&per_page=10&page=2` returns only 3 or 4 jobs although the footer says there are 3 pages of "
        "`open` jobs, and page 3 is sometimes empty. Without the filter everything is fine. I suspect the count query. "
        "Please find the real cause."
    )
    p["offset-raw"] = (
        "Odd one from the mobile team: for normal page sizes the board is fine, but `per_page=250&page=2` returns "
        "items 501-600 (or nothing) instead of 101-200. The `per_page` in the response says 100, as the README promises. "
        "Fix it so consecutive pages tile the list, whatever size the client asks for."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "jobboard/__init__.py": '"""Maintenance job board."""\n', "jobboard/store.py": A_STORE,
            "jobboard/pager.py": A_PAGER, "jobboard/api.py": A_API}
    rep_first = {"tests/test_reported.py": dd('''
        import unittest

        from jobboard.api import list_jobs
        from jobboard.store import JobStore


        class Reported(unittest.TestCase):
            def test_first_page_starts_at_the_first_job(self):
                store = JobStore([{"id": i, "status": "open"} for i in range(1, 61)])
                r = list_jobs(store, {})
                self.assertEqual(r["items"][0]["id"], 1)
                self.assertEqual(len(r["items"]), 25)
    ''')}
    bugs = [
        Bug("first-page-skipped", 1, {"jobboard/pager.py": [("return (page - 1) * per_page", "return page * per_page")]}, P["offset"], reported=rep_first),
        Bug("pages-off-by-one", 2, {"jobboard/pager.py": [("    if total == 0:\n        return 1\n    return (total + per_page - 1) // per_page",
                                                          "    return total // per_page + 1")]}, P["extra-page"]),
        Bug("cap-resets", 2, {"jobboard/pager.py": [("    return min(n, MAX_PER_PAGE)", "    if n > MAX_PER_PAGE:\n        return DEFAULT_PER_PAGE\n    return n")]}, P["cap-fallback"]),
        Bug("empty-is-zero-pages", 1, {"jobboard/pager.py": [("    if total == 0:\n        return 1\n    return (total + per_page - 1) // per_page",
                                                             "    return (total + per_page - 1) // per_page")]}, P["empty-zero"]),
        Bug("next-from-item-count", 3, {"jobboard/api.py": [("    prev, nxt = neighbours(page, pages)\n",
                                                            "    prev, _ = neighbours(page, pages)\n    nxt = page + 1 if len(items) == per_page else None\n")]},
            P["next-on-full-last"]),
        Bug("offset-from-raw-size", 3, {"jobboard/api.py": [
            ('    per_page = normalize_per_page(params.get("per_page"))\n', '    raw = params.get("per_page")\n    per_page = normalize_per_page(raw)\n'),
            ("    items = store.fetch(offset_of(page, per_page), per_page, status)\n",
             "    size = int(raw) if raw is not None else per_page\n    items = store.fetch(offset_of(page, size), per_page, status)\n")]}, P["offset-raw"]),
        Bug("filter-after-slice", 4, {
            "jobboard/store.py": [("        return self._matching(status)[offset:offset + limit]", "        return self._jobs[offset:offset + limit]")],
            "jobboard/api.py": [("    items = store.fetch(offset_of(page, per_page), per_page, status)\n",
                                 "    items = store.fetch(offset_of(page, per_page), per_page)\n    if status is not None:\n        items = [j for j in items if j[\"status\"] == status]\n")]},
            P["filter-after-slice"]),
    ]
    return Base("jobboard", "python", good, A_VISIBLE, A_HIDDEN, bugs)


# --------------------------------------------------------------------------------------------------------------
# Base B (javascript): an event feed with keyset (cursor) pagination.
# --------------------------------------------------------------------------------------------------------------

B_README = dd('''
    # eventfeed

    A small in-memory activity feed read by clients with *keyset* pagination: each response carries an opaque cursor
    for the next request instead of a page number.

    * An event is `{ id, ts, text }`. `ts` is an integer (milliseconds). `id` looks like `e-<number>`.
    * The feed is ordered by `ts`, and events with the same `ts` are ordered by the **number** in their id
      (`e-9` comes before `e-10`).
    * `feed.page({ after, limit })` returns `{ items, nextCursor }`. Without `after` it starts at the beginning;
      with a cursor it returns the events that sort strictly after the event the cursor was made from.
      `limit` defaults to 10, is capped at 50, and must be an integer >= 1 (otherwise `RangeError('bad limit')`).
    * `nextCursor` is the cursor of the last returned item, or `null` when no event sorts after the returned
      items. Following `nextCursor` until it is `null` visits every event exactly once, in order.
    * `feed.add(event)` adds an event at any time (live updates). It must be visible to the next `page` call at
      its sorted place.
    * `cursor.encode(event)` / `cursor.decode(text)`: a cursor is opaque to clients; a malformed one is a
      `RangeError('bad cursor')` and `decode` returns `{ ts, id }`.
    * `http.handle(feed, query)` takes the raw query strings (`after`, `limit`) and returns `{ status, body }`:
      `200` with `{ items, next }`, or `400` with `{ error }` for a bad cursor or a bad limit (`"0"`, `"abc"`, `""`,
      `"-1"` and `"2.5"` are all bad limits).
''')

B_CURSOR = dd('''
    'use strict';

    // A cursor is the base64url form of "<ts>:<id>" of the event it was made from.
    function encode(ev) {
      return Buffer.from(`${ev.ts}:${ev.id}`).toString('base64url');
    }

    function decode(text) {
      const raw = Buffer.from(String(text), 'base64url').toString('utf8');
      const m = /^(\\d+):(e-\\d+)$/.exec(raw);
      if (!m) throw new RangeError('bad cursor');
      return { ts: Number(m[1]), id: m[2] };
    }

    module.exports = { encode, decode };
''')

B_ORDER = dd('''
    'use strict';

    // Order of the feed: by ts, then by the number inside the id ("e-9" before "e-10").
    function idNumber(id) {
      return Number(id.slice(2));
    }

    function compare(a, b) {
      if (a.ts !== b.ts) return a.ts - b.ts;
      return idNumber(a.id) - idNumber(b.id);
    }

    module.exports = { compare, idNumber };
''')

B_FEED = dd('''
    'use strict';
    const { encode, decode } = require('./cursor');
    const { compare } = require('./order');

    const DEFAULT_LIMIT = 10;
    const MAX_LIMIT = 50;

    class Feed {
      constructor(events = []) {
        this.events = [...events].sort(compare);
      }

      add(ev) {
        const last = this.events[this.events.length - 1];
        this.events.push(ev);
        if (last && compare(ev, last) < 0) this.events.sort(compare);
      }

      page({ after, limit = DEFAULT_LIMIT } = {}) {
        if (!Number.isInteger(limit) || limit < 1) throw new RangeError('bad limit');
        const lim = Math.min(limit, MAX_LIMIT);
        let start = 0;
        if (after !== undefined && after !== null) {
          const c = decode(after);
          start = this.events.findIndex((e) => compare(e, c) > 0);
          if (start === -1) start = this.events.length;
        }
        const items = this.events.slice(start, start + lim);
        const more = start + items.length < this.events.length;
        return { items, nextCursor: more ? encode(items[items.length - 1]) : null };
      }
    }

    module.exports = { Feed, DEFAULT_LIMIT, MAX_LIMIT };
''')

B_HTTP = dd('''
    'use strict';

    function handle(feed, query = {}) {
      let limit;
      if (query.limit !== undefined) {
        if (!/^\\d+$/.test(query.limit) || Number(query.limit) < 1) {
          return { status: 400, body: { error: 'bad limit' } };
        }
        limit = Number(query.limit);
      }
      try {
        const { items, nextCursor } = feed.page({ after: query.after, limit });
        return { status: 200, body: { items, next: nextCursor } };
      } catch (e) {
        if (e instanceof RangeError) return { status: 400, body: { error: e.message } };
        throw e;
      }
    }

    module.exports = { handle };
''')

B_VISIBLE = {
    "test/feed.test.js": dd('''
        const test = require('node:test');
        const assert = require('node:assert');
        const { Feed } = require('../src/feed');

        const mk = (n) => Array.from({ length: n }, (_, i) => ({ id: `e-${i + 1}`, ts: 1000 + i * 10, text: `event ${i + 1}` }));

        test('first page', () => {
          const feed = new Feed(mk(25));
          const r = feed.page({ limit: 10 });
          assert.deepStrictEqual(r.items.map((e) => e.id), mk(10).map((e) => e.id));
          assert.notStrictEqual(r.nextCursor, null);
        });

        test('follow cursors to the end', () => {
          const feed = new Feed(mk(25));
          let after;
          const seen = [];
          for (let guard = 0; guard < 10; guard++) {
            const r = feed.page({ after, limit: 10 });
            seen.push(...r.items.map((e) => e.id));
            if (r.nextCursor === null) break;
            after = r.nextCursor;
          }
          assert.strictEqual(seen.length, 25);
        });
    '''),
}

B_HIDDEN = {
    "test/hidden_feed.test.js": dd('''
        const test = require('node:test');
        const assert = require('node:assert');
        const { Feed } = require('../src/feed');
        const { encode, decode } = require('../src/cursor');
        const { handle } = require('../src/http');

        const ev = (n, ts) => ({ id: `e-${n}`, ts, text: `event ${n}` });
        const spread = (n) => Array.from({ length: n }, (_, i) => ev(i + 1, 1000 + i * 10));
        const sameTs = (n) => Array.from({ length: n }, (_, i) => ev(i + 1, 500));

        function walk(feed, limit) {
          const seen = [];
          let after;
          for (let guard = 0; guard < 500; guard++) {
            const r = feed.page({ after, limit });
            seen.push(...r.items.map((e) => e.id));
            if (r.nextCursor === null) return seen;
            after = r.nextCursor;
          }
          throw new Error('cursor never ends');
        }

        test('cursor round trip', () => {
          assert.deepStrictEqual(decode(encode(ev(12, 1700000000123))), { ts: 1700000000123, id: 'e-12' });
          assert.throws(() => decode('???'), RangeError);
          assert.throws(() => decode(Buffer.from('12:foo').toString('base64url')), RangeError);
        });

        test('orders by ts then by numeric id, whatever the insertion order', () => {
          const feed = new Feed([ev(10, 500), ev(9, 500), ev(2, 700), ev(100, 400), ev(11, 500)]);
          assert.deepStrictEqual(feed.page({ limit: 50 }).items.map((e) => e.id), ['e-100', 'e-9', 'e-10', 'e-11', 'e-2']);
        });

        test('ties on ts are not skipped or repeated at page boundaries', () => {
          const feed = new Feed(sameTs(23));
          const want = sameTs(23).map((e) => e.id);
          for (const limit of [1, 2, 3, 5, 7, 10, 22, 23, 50]) {
            assert.deepStrictEqual(walk(feed, limit), want, `limit ${limit}`);
          }
        });

        test('mixed ties walk', () => {
          const events = [];
          for (let i = 1; i <= 40; i++) events.push(ev(i, 100 + Math.floor(i / 4) * 5));
          const feed = new Feed(events.reverse());
          const want = [...events].sort((a, b) => a.ts - b.ts || Number(a.id.slice(2)) - Number(b.id.slice(2))).map((e) => e.id);
          for (const limit of [1, 3, 4, 6, 9, 13]) assert.deepStrictEqual(walk(feed, limit), want, `limit ${limit}`);
        });

        test('nextCursor is null exactly when nothing follows', () => {
          const feed = new Feed(spread(9));
          const r1 = feed.page({ limit: 3 });
          const r2 = feed.page({ after: r1.nextCursor, limit: 3 });
          const r3 = feed.page({ after: r2.nextCursor, limit: 3 });
          assert.strictEqual(r3.items.length, 3);
          assert.strictEqual(r3.nextCursor, null);
          assert.notStrictEqual(r2.nextCursor, null);
          assert.deepStrictEqual(decode(r1.nextCursor), { ts: 1020, id: 'e-3' });
          const one = new Feed(spread(4)).page({ limit: 4 });
          assert.strictEqual(one.nextCursor, null);
        });

        test('empty feed and cursor at the very end', () => {
          assert.deepStrictEqual(new Feed([]).page({}), { items: [], nextCursor: null });
          const feed = new Feed(spread(5));
          const last = feed.events[4];
          assert.deepStrictEqual(feed.page({ after: encode(last) }), { items: [], nextCursor: null });
        });

        test('limit default, cap and validation', () => {
          const feed = new Feed(spread(120));
          assert.strictEqual(feed.page({}).items.length, 10);
          assert.strictEqual(feed.page({ limit: 500 }).items.length, 50);
          assert.strictEqual(feed.page({ limit: 50 }).items.length, 50);
          for (const bad of [0, -1, 2.5, NaN, '3']) assert.throws(() => feed.page({ limit: bad }), RangeError);
        });

        test('add keeps the order, including ties and late arrivals', () => {
          const feed = new Feed([ev(7, 900), ev(8, 900)]);
          feed.add(ev(1, 100));
          feed.add(ev(5, 900));
          feed.add(ev(9, 900));
          feed.add(ev(20, 1000));
          feed.add(ev(12, 1000));
          assert.deepStrictEqual(feed.page({ limit: 50 }).items.map((e) => e.id), ['e-1', 'e-5', 'e-7', 'e-8', 'e-9', 'e-12', 'e-20']);
        });

        test('an event added behind the client cursor is not served, one ahead of it is', () => {
          const feed = new Feed([ev(1, 10), ev(2, 20), ev(3, 30)]);
          const r = feed.page({ limit: 2 });
          feed.add(ev(4, 15));
          feed.add(ev(10, 20));
          feed.add(ev(5, 40));
          const rest = feed.page({ after: r.nextCursor, limit: 10 });
          assert.deepStrictEqual(rest.items.map((e) => e.id), ['e-10', 'e-3', 'e-5']);
        });

        test('http: limits', () => {
          const feed = new Feed(spread(30));
          for (const bad of ['0', 'abc', '', '-1', '2.5', '1e1']) {
            assert.deepStrictEqual(handle(feed, { limit: bad }), { status: 400, body: { error: 'bad limit' } }, JSON.stringify(bad));
          }
          const ok = handle(feed, { limit: '5' });
          assert.strictEqual(ok.status, 200);
          assert.strictEqual(ok.body.items.length, 5);
          assert.strictEqual(handle(feed, {}).body.items.length, 10);
          assert.strictEqual(handle(feed, { limit: '900' }).body.items.length, 30);
        });

        test('http: cursors', () => {
          const feed = new Feed(spread(30));
          const first = handle(feed, { limit: '12' });
          const second = handle(feed, { limit: '12', after: first.body.next });
          assert.strictEqual(second.body.items[0].id, 'e-13');
          assert.deepStrictEqual(handle(feed, { after: 'not-a-cursor' }), { status: 400, body: { error: 'bad cursor' } });
          const third = handle(feed, { limit: '12', after: second.body.next });
          assert.strictEqual(third.body.items.length, 6);
          assert.strictEqual(third.body.next, null);
        });
    '''),
}


def _b_prompts():
    p = {}
    p["lenient-limit"] = (
        "A client sent `?limit=0` by mistake and got a normal ten-item page back instead of an error; `?limit=abc` does "
        "the same. The README says a bad limit is a 400 with `bad limit`. Please make the endpoint strict again."
    )
    p["same-ts-skip"] = (
        "Support ticket #4471: a customer's export is missing events. Looking at the logs, they are always events that "
        "happened in the same millisecond as the last event of the previous page. I'd guess an off-by-one in the "
        "pagination, but where? The feed is ordered by `ts` and then id."
    )
    p["id-text-order"] = (
        "In the feed, `e-10` is shown before `e-9` when both have the same timestamp (import jobs stamp whole batches "
        "with one `ts`). Clients that follow cursors then see events out of order. Fix the ordering."
    )
    p["peek-cursor"] = (
        "Clients paging through the feed lose exactly one event at every page boundary, and the lost event is always the "
        "first one of the next page. Totals are right on the first page and wrong after. Can you track it down?"
    )
    p["add-late"] = (
        "Since live updates (`feed.add`) shipped we get reports that some events never reach clients that are in the "
        "middle of paging. It looks timing related, but in the unit tests I can make it happen deterministically with "
        "two events with the same timestamp that arrive in the wrong order. Please fix the cause."
    )
    p["two-causes"] = (
        "Two reports against the activity feed that may or may not be related. (1) Batch imports with the same `ts` "
        "show `e-10` before `e-9`. (2) After the live-update change, an event that arrives late with the same `ts` as "
        "a newer one is never delivered to clients who are paging. The visible tests pass. I want both fixed properly, "
        "in the right places."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "src/cursor.js": B_CURSOR, "src/order.js": B_ORDER, "src/feed.js": B_FEED, "src/http.js": B_HTTP,
            "package.json": '{\n  "name": "eventfeed",\n  "version": "1.0.0",\n  "private": true\n}\n'}
    add_bug = ("    if (last && compare(ev, last) < 0) this.events.sort(compare);", "    if (last && ev.ts < last.ts) this.events.sort(compare);")
    order_bug = ("  return idNumber(a.id) - idNumber(b.id);", "  return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;")
    bugs = [
        Bug("lenient-limit", 2, {"src/http.js": [
            ("    if (!/^\\d+$/.test(query.limit) || Number(query.limit) < 1) {\n      return { status: 400, body: { error: 'bad limit' } };\n    }\n    limit = Number(query.limit);\n",
             "    limit = Number(query.limit) || undefined;\n    if (limit !== undefined && (!Number.isInteger(limit) || limit < 1)) {\n      return { status: 400, body: { error: 'bad limit' } };\n    }\n")]},
            P["lenient-limit"]),
        Bug("same-ts-skipped", 3, {"src/feed.js": [("      start = this.events.findIndex((e) => compare(e, c) > 0);", "      start = this.events.findIndex((e) => e.ts > c.ts);")]}, P["same-ts-skip"]),
        Bug("id-compared-as-text", 3, {"src/order.js": [order_bug]}, P["id-text-order"]),
        Bug("cursor-of-peeked-item", 3, {"src/feed.js": [
            ("    const items = this.events.slice(start, start + lim);\n    const more = start + items.length < this.events.length;\n    return { items, nextCursor: more ? encode(items[items.length - 1]) : null };",
             "    const batch = this.events.slice(start, start + lim + 1);\n    const items = batch.slice(0, lim);\n    return { items, nextCursor: batch.length > lim ? encode(batch[lim]) : null };")]},
            P["peek-cursor"]),
        Bug("add-skips-resort", 4, {"src/feed.js": [add_bug]}, P["add-late"]),
        Bug("order-and-add", 5, {"src/order.js": [order_bug], "src/feed.js": [add_bug]}, P["two-causes"]),
    ]
    return Base("eventfeed", "javascript", good, B_VISIBLE, B_HIDDEN, bugs)


@family("fix-hand-paging", category="fix", lang="python", kind="fix", n=13,
        summary="pagination bugs hiding in different layers: offset paging (python) and a keyset feed (javascript)")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b()])
