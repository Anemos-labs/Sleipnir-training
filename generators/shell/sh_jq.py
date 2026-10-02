"""Shell tasks: jq programs with exact expected output (jq 1.7): flattening, grouping, latest-per-key, dotted paths, joins, validation, weeks, trees."""
import json

from fx import dd, family
from generators.shell import _shkit as K
from generators.shell._shkit import D, F, L, Run, scn

S = K.ShellSpec
RUN = ("jq", "-f")
NOTE = " The tests run jq 1.7 as `jq -f PROGRAM [options] FILE`."


def js(o):
    return json.dumps(o, ensure_ascii=False)


# ------------------------------------------------------------------------------------------------ 1. flatten harvests

REF_FLAT = dd('''
    ["bed", "date", "crop", "kg"],
    (.[] | . as $h | .picks[] | [$h.bed, $h.date, .crop, .kg])
    | @csv
''')


def make_flat(rng):
    ex = scn("example", {"h.json": F(js([{"bed": "B1", "date": "2031-05-01", "picks": [{"crop": "kale", "kg": 2.5}, {"crop": "chard", "kg": 1}]}]))}, Run("-r", "h.json"))
    data = [{"bed": "North \"A\"", "date": "2031-06-01", "picks": [{"crop": "radish, red", "kg": 0.75}, {"crop": "kale", "kg": 3}]}, {"bed": "B2", "date": "2031-06-02", "picks": []},
            {"bed": "C3", "date": "2031-06-03", "picks": [{"crop": "leek"}, {"crop": "pea", "kg": 12.25}]}, {"bed": "ünï", "date": "2031-06-04", "picks": [{"crop": "ça", "kg": 1.5}]}]
    return ex, [scn("harvest log", {"h.json": F(js(data))}, Run("-r", "h.json")), scn("nothing", {"h.json": F("[]")}, Run("-r", "h.json"))]


# ------------------------------------------------------------------------------------------------ 2. group and sum

REF_GROUP = dd('''
    group_by(.crop)
    | map({key: .[0].crop, value: (map(.kg) | add * 100 | round / 100)})
    | from_entries
''')


def make_group(rng):
    ex = scn("example", {"p.json": F(js([{"crop": "kale", "kg": 1.5, "plot": 1}, {"crop": "leek", "kg": 2, "plot": 2}, {"crop": "kale", "kg": 0.25, "plot": 3}]))}, Run("p.json"))
    data = [{"crop": c, "kg": k, "plot": i} for i, (c, k) in enumerate([("pea", 0.1), ("pea", 0.2), ("Zucchini", 4), ("pea", 0.7), ("bean", 1.005), ("bean", 2.01), ("kale", 10), ("Zucchini", 0.333), ("kale", 0.001)], 1)]
    return ex, [scn("float sums", {"p.json": F(js(data))}, Run("p.json")), scn("empty", {"p.json": F("[]")}, Run("p.json"))]


# ------------------------------------------------------------------------------------------------ 3. latest per sensor

REF_LATEST = dd('''
    group_by(.sensor)
    | map(reduce .[] as $r (null; if . == null or $r.ts >= .ts then $r else . end))
''')


def make_latest(rng):
    ex = scn("example", {"r.json": F(js([{"sensor": "a", "ts": "2031-01-01T10:00:00Z", "value": 1}, {"sensor": "a", "ts": "2031-01-01T11:00:00Z", "value": 2}, {"sensor": "b", "ts": "2031-01-01T09:00:00Z", "value": 3}]))}, Run("-c", "r.json"))
    rows = [{"sensor": s, "ts": t, "value": v} for s, t, v in [("t-2", "2031-02-01T00:00:00Z", 5), ("t-1", "2031-02-01T00:00:00Z", 1), ("t-2", "2031-03-01T00:00:00Z", 6), ("t-1", "2031-01-31T23:59:59Z", 2),
                                                               ("t-2", "2031-03-01T00:00:00Z", 7), ("Z", "2030-12-31T00:00:00Z", 0), ("t-1", "2031-02-01T00:00:00Z", 9)]]
    return ex, [scn("ties go to the later record", {"r.json": F(js(rows))}, Run("-c", "r.json")), scn("empty", {"r.json": F("[]")}, Run("-c", "r.json"))]


# ------------------------------------------------------------------------------------------------ 4. dotted paths

REF_PATHS = dd('''
    [paths as $p
     | select(getpath($p) | type | . != "object" and . != "array")
     | {key: ($p | map(if type == "number" then "[\\(.)]" else "." + . end) | join("") | ltrimstr(".")), value: getpath($p)}]
    | from_entries
''')


def make_paths(rng):
    ex = scn("example", {"c.json": F(js({"a": {"b": [1, {"c": True}]}, "n": None}))}, Run("-S", "c.json"))
    doc = {"server": {"host": "h", "ports": [80, 443, {"alt": 8080}], "tls": {"on": False, "cert": None}}, "tags": ["x", ["y", "z"]], "empty": {}, "list": [], "n": 0, "weird.key": {"a b": 1}}
    return ex, [scn("nested config", {"c.json": F(js(doc))}, Run("-S", "c.json")), scn("root array", {"c.json": F(js([1, [2, 3], {"k": "v"}]))}, Run("-S", "c.json")), scn("scalar root", {"c.json": F("42")}, Run("-S", "c.json"))]


# ------------------------------------------------------------------------------------------------ 5. join with slurpfile

REF_JOIN = dd('''
    ($prices[0] | map({(.sku): .price}) | add // {}) as $p
    | map({id, total: ([.items[] | ($p[.sku] // 0) * .qty] | add // 0 | . * 100 | round / 100), missing: [.items[].sku | select($p[.] == null)]})
    | map(if .missing == [] then del(.missing) else . end)
''')


def make_join(rng):
    prices = [{"sku": "bolt", "price": 0.25}, {"sku": "nut", "price": 0.1}, {"sku": "washer", "price": 0.05}, {"sku": "rod", "price": 4.99}]
    orders = [{"id": "o1", "items": [{"sku": "bolt", "qty": 10}, {"sku": "nut", "qty": 10}]}, {"id": "o2", "items": []}, {"id": "o3", "items": [{"sku": "rod", "qty": 3}, {"sku": "gear", "qty": 2}, {"sku": "cog", "qty": 1}]},
              {"id": "o4", "items": [{"sku": "washer", "qty": 7}, {"sku": "washer", "qty": 3}]}]
    ex = scn("example", {"prices.json": F(js(prices[:2])), "orders.json": F(js(orders[:1]))}, Run("-c", "--slurpfile", "prices", "prices.json", "orders.json"))
    return ex, [scn("orders", {"prices.json": F(js(prices)), "orders.json": F(js(orders))}, Run("-c", "--slurpfile", "prices", "prices.json", "orders.json")),
                scn("empty price list", {"prices.json": F("[]"), "orders.json": F(js(orders[:1]))}, Run("-c", "--slurpfile", "prices", "prices.json", "orders.json"))]


# ------------------------------------------------------------------------------------------------ 6. validation

REF_VALID = dd('''
    def problems:
      [ (if (.id | type) == "number" and .id > 0 and .id == (.id | floor) then empty else "id" end),
        (if (.age | type) == "number" and .age >= 0 and .age <= 130 then empty else "age" end),
        (if (.email | type) == "string" and (.email | test("^[^@ ]+@[^@ .]+(\\\\.[^@ .]+)+$")) then empty else "email" end) ];
    . as $all
    | {valid: [$all[] | select(problems == []) | .id],
       invalid: [$all[] | select(problems != []) | {id: (.id // null), reasons: problems}]}
''')


def make_valid(rng):
    ex = scn("example", {"u.json": F(js([{"id": 1, "age": 30, "email": "a@b.co"}, {"id": 2, "age": -1, "email": "nope"}]))}, Run("-c", "u.json"))
    rows = [{"id": 1, "age": 0, "email": "a@b.io"}, {"id": 2, "age": 130, "email": "x.y@z.org"}, {"id": 3, "age": 131, "email": "a@b.io"}, {"id": 0, "age": 20, "email": "a@b.io"}, {"id": 4.5, "age": 20, "email": "a@b.io"},
            {"id": "7", "age": 20, "email": "a@b.io"}, {"id": 8, "age": "20", "email": "a@b.io"}, {"id": 9, "age": 20, "email": "a@@b.io"}, {"id": 10, "age": 20, "email": "a@b"}, {"id": 11, "age": 20, "email": "a @b.io"},
            {"id": 12, "age": 20}, {"age": 20, "email": "a@b.io"}, {"id": 13, "age": 20, "email": "a@b.c.d"}, {"id": 14, "age": 20, "email": "a@b.c."}, {"id": 15, "age": None, "email": None}]
    return ex, [scn("mixed records", {"u.json": F(js(rows))}, Run("-c", "u.json")), scn("all good", {"u.json": F(js(rows[:2]))}, Run("-c", "u.json")), scn("empty", {"u.json": F("[]")}, Run("-c", "u.json"))]


# ------------------------------------------------------------------------------------------------ 7. ISO weeks

REF_WEEKS = dd('''
    map(. + {week: (.at | strptime("%Y-%m-%dT%H:%M:%SZ") | mktime | strftime("%G-W%V"))})
    | group_by(.week)
    | map({week: .[0].week, count: length, total: (map(.amount) | add)})
''')


def make_weeks(rng):
    ex = scn("example", {"e.json": F(js([{"at": "2031-03-03T10:00:00Z", "amount": 5}, {"at": "2031-03-04T10:00:00Z", "amount": 7}, {"at": "2031-03-10T00:00:00Z", "amount": 1}]))}, Run("-c", "e.json"))
    ev = [{"at": a, "amount": m} for a, m in [("2030-12-29T23:59:59Z", 1), ("2030-12-30T00:00:00Z", 2), ("2031-01-05T12:00:00Z", 3), ("2031-01-06T00:00:00Z", 4), ("2031-01-01T00:00:00Z", 5), ("2032-01-01T00:00:00Z", 6),
                                              ("2031-12-31T23:00:00Z", 7), ("2031-12-28T09:00:00Z", 8), ("2032-12-31T00:00:00Z", 9), ("2033-01-01T00:00:00Z", 10)]]
    return ex, [scn("ISO week-year edges", {"e.json": F(js(ev))}, Run("-c", "e.json")), scn("empty", {"e.json": F("[]")}, Run("-c", "e.json"))]


# ------------------------------------------------------------------------------------------------ 8. directory tree sizes

REF_TREE = dd('''
    def total: if has("children") then ([.children[] | total] | add // 0) else .size end;
    def dirs($prefix): ($prefix + .name) as $p
      | if has("children") then ({path: $p, size: total}, (.children[] | dirs($p + "/"))) else empty end;
    [dirs("")] | sort_by(.path)
''')


def make_tree(rng):
    ex = scn("example", {"t.json": F(js({"name": "root", "children": [{"name": "a.txt", "size": 3}, {"name": "d", "children": [{"name": "b", "size": 4}]}]}))}, Run("-c", "t.json"))
    tree = {"name": "proj", "children": [{"name": "src", "children": [{"name": "main.c", "size": 120}, {"name": "util", "children": [{"name": "u.c", "size": 80}, {"name": "u.h", "size": 20}]}, {"name": "empty", "children": []}]},
                                         {"name": "README", "size": 7}, {"name": "docs", "children": [{"name": "a b.md", "size": 33}]}, {"name": "Build", "children": [{"name": "x", "size": 0}]}]}
    return ex, [scn("tree", {"t.json": F(js(tree))}, Run("-c", "t.json")), scn("single file", {"t.json": F(js({"name": "f", "size": 1}))}, Run("-c", "t.json")), scn("empty dir", {"t.json": F(js({"name": "e", "children": []}))}, Run("-c", "t.json"))]


# ------------------------------------------------------------------------------------------------ 9. CSV to objects

REF_CSV = dd('''
    split("\\n") | map(select(length > 0) | split(","))
    | if length == 0 then [] else
        .[0] as $h
        | .[1:] | map([$h, .] | transpose | map({key: .[0], value: (.[1] // "" | if . == "" then null elif test("^-?[0-9]+(\\\\.[0-9]+)?$") then tonumber else . end)}) | from_entries)
      end
''')


def make_csv(rng):
    ex = scn("example", {}, Run("-R", "-s", "-c", stdin="name,qty\nbolt,12\nnut,\n"))
    txt = "id,name,price,note\n1,widget,9.5,fine\n2,x,-3,\n003,gadget,1e3,ok\n4,thing\n\n5,last,0.25,end\n"
    return ex, [scn("typed values", {}, Run("-R", "-s", "-c", stdin=txt), Run("-R", "-s", "-c", stdin="h1,h2\n"), Run("-R", "-s", "-c", stdin=""), Run("-R", "-s", "-c", stdin="a\n1\n2\n3\n"))]


# ------------------------------------------------------------------------------------------------ 10. config update

REF_UPDATE = dd('''
    .version |= (split(".") | .[2] |= ((tonumber + 1) | tostring) | join("."))
    | .updated = $date
    | del(.. | .debug?)
    | .features.beta //= false
''')


def make_update(rng):
    ex = scn("example", {"c.json": F(js({"version": "1.0.9", "debug": True}))}, Run("--arg", "date", "2031-06-01", "c.json"))
    doc = {"name": "svc", "version": "2.14.99", "debug": True, "features": {"beta": True, "debug": 1, "x": None}, "nested": {"deep": {"debug": {"level": 3}, "keep": 1}}, "list": [{"debug": 0, "a": 1}, {"b": 2}], "updated": "old"}
    return ex, [scn("full config", {"c.json": F(js(doc))}, Run("--arg", "date", "2031-06-01", "c.json")), scn("minimal", {"c.json": F(js({"version": "0.0.0"}))}, Run("--arg", "date", "2031-12-31", "c.json")),
                scn("beta already false", {"c.json": F(js({"version": "3.3.3", "features": {"beta": False}}))}, Run("--arg", "date", "2031-01-02", "c.json"))]


# ------------------------------------------------------------------------------------------------ 11. fix: totals

BUG_TOTAL = dd('''
    {count: length,
     total: ([.[] | .price * .qty] | add),
     average: (([.[] | .price * .qty] | add) / length)}
''')
REF_TOTAL = dd('''
    def line: .price * (.qty // 1);
    def r2: . * 100 | round / 100;
    {count: length,
     total: ([.[] | line] | add // 0 | r2),
     average: (if length == 0 then null else ([.[] | line] | add / length | r2) end)}
''')


def make_total(rng):
    ex = scn("example", {"i.json": F(js([{"price": 2.5, "qty": 2}, {"price": 1, "qty": 3}]))}, Run("-c", "i.json"))
    return ex, [scn("missing quantities", {"i.json": F(js([{"price": 1.1, "qty": 3}, {"price": 2.25}, {"price": 0.1, "qty": 3}]))}, Run("-c", "i.json")), scn("empty list", {"i.json": F("[]")}, Run("-c", "i.json")),
                scn("single", {"i.json": F(js([{"price": 9.99, "qty": 1}]))}, Run("-c", "i.json"))]


# ------------------------------------------------------------------------------------------------ 12. top three scores with ties

REF_TOP = dd('''
    group_by(.score) | reverse | .[0:3] | to_entries
    | map({rank: (.key + 1), score: .value[0].score, names: (.value | map(.name) | sort)})
''')


def make_top(rng):
    ex = scn("example", {"s.json": F(js([{"name": "a", "score": 5}, {"name": "b", "score": 9}, {"name": "c", "score": 5}]))}, Run("-c", "s.json"))
    rows = [{"name": n, "score": s} for n, s in [("zed", 70), ("amy", 90), ("bob", 90), ("cy", 85), ("dee", 85), ("eli", 85), ("fay", 70), ("gus", 60), ("hal", 60.5), ("ivy", 100), ("jo", 100)]]
    return ex, [scn("ties", {"s.json": F(js(rows))}, Run("-c", "s.json")), scn("fewer than three", {"s.json": F(js(rows[:2]))}, Run("-c", "s.json")), scn("empty", {"s.json": F("[]")}, Run("-c", "s.json"))]


SPECS = [
    S("harvest-log-to-csv", 2,
      "Write `harvest.jq`: turn a nested harvest log into CSV lines (header first) with `jq -r`." + NOTE,
      "`jq -f harvest.jq -r FILE`: the input is an array of beds `{bed, date, picks: [{crop, kg}]}`. Output (raw, so run with `-r`) is the CSV header `\"bed\",\"date\",\"crop\",\"kg\"` followed by one CSV line per pick, in input order (beds without picks produce nothing), "
      "formatted with jq's `@csv` (strings quoted with doubled inner quotes, numbers as jq prints them, a missing `kg` as an empty field). An empty input array outputs only the header.",
      REF_FLAT, make_flat, script="harvest.jq", runner=RUN, title="Harvest log to CSV", wrong=(".[]\n",)),
    S("totals-per-crop", 2,
      "Write `totals.jq`: sum kilograms per crop into one object with keys in alphabetical order, totals rounded to two decimals." + NOTE,
      "`jq -f totals.jq FILE`: the input is an array of `{crop, kg, plot}`. Output one JSON object mapping each crop to the sum of its `kg`, rounded to two decimals (so `0.1 + 0.2` gives `0.3`), keys in byte-wise sorted order. Empty input gives `{}`.",
      REF_GROUP, make_group, script="totals.jq", runner=RUN, title="Totals per crop", wrong=("group_by(.crop) | map({key: .[0].crop, value: (map(.kg) | add)}) | from_entries\n",)),
    S("latest-reading-per-sensor", 3,
      "Write `latest.jq`: output, for every sensor, its most recent reading, sensors in alphabetical order." + NOTE,
      "`jq -f latest.jq -c FILE`: the input is an array of readings `{sensor, ts, value}` with ISO-8601 UTC timestamps (`ts` strings compare chronologically). Output a single array holding, per sensor, the reading with the greatest `ts` "
      "(if several readings of a sensor share it, the **last one in the input**), ordered by sensor name (byte-wise). Readings are output unchanged.",
      REF_LATEST, make_latest, script="latest.jq", runner=RUN, title="Latest reading per sensor", wrong=("group_by(.sensor) | map(.[0])\n",)),
    S("dotted-paths", 3,
      "Write `paths.jq`: flatten any JSON document into one object whose keys are dotted/bracketed paths to the leaf values." + NOTE,
      "`jq -f paths.jq -S FILE` (`-S` sorts the output keys) turns the document into a single object mapping the path of every scalar leaf (string, number, boolean, `null`) to its value. "
      "A path is built from object keys joined with `.` and array indexes written `[N]` directly after the previous part: `{\"a\":{\"b\":[1,{\"c\":true}]}}` gives `a.b[0]` and `a.b[1].c`. At the root an array index starts the path as `[0]`. "
      "Empty objects and arrays have no leaves and do not appear. Keys are used literally even if they contain dots or spaces. A document that is itself a scalar gives `{}`.",
      REF_PATHS, make_paths, script="paths.jq", runner=RUN, title="Dotted paths", wrong=("[paths(scalars)] | length\n",)),
    S("join-orders-and-prices", 4,
      "Write `totals.jq` to price orders using a separate price list passed with `--slurpfile prices`, flagging unknown SKUs." + NOTE,
      "`jq -f totals.jq -c --slurpfile prices prices.json orders.json`: `prices.json` is an array of `{sku, price}` (available as `$prices[0]`), `orders.json` an array of `{id, items: [{sku, qty}]}`. "
      "Output an array with one object per order, in input order: `{\"id\": ..., \"total\": ...}` where `total` is the sum of `price * qty` over the known items, rounded to two decimals (0 for no items), and, only when some item SKUs are not in the price list, "
      "a third key `missing` listing those SKUs (once per occurrence, in order). Unknown SKUs contribute 0 to the total.",
      REF_JOIN, make_join, script="totals.jq", runner=RUN, title="Price orders from a list", wrong=("map({id})\n",)),
    S("validate-records", 3,
      "Write `check.jq`: split user records into valid ids and invalid ones with the reasons, following the README's rules." + NOTE,
      "`jq -f check.jq -c FILE`: the input is an array of user records. A record has three checks, reported by name when they fail: `id` (must be a whole number greater than 0), `age` (a number from 0 to 130 inclusive), `email` (a string with exactly one `@`, a non-empty part before it and a domain after it that has at least one dot with non-empty parts, no spaces). "
      "Output one object `{\"valid\": [ids of records passing all checks, in order], \"invalid\": [{\"id\": <id or null>, \"reasons\": [failed check names in the order id, age, email]}, ...]}` (invalid in input order). Missing fields fail their check.",
      REF_VALID, make_valid, script="check.jq", runner=RUN, title="Validate records", wrong=("{valid: map(.id), invalid: []}\n",)),
    S("events-per-iso-week", 4,
      "Write `weeks.jq`: count and sum events per ISO week (`2031-W10`), weeks in chronological order." + NOTE,
      "`jq -f weeks.jq -c FILE`: the input is an array of events `{at, amount}` with UTC timestamps like `2031-03-04T10:00:00Z`. Group them by ISO-8601 week (week-based year and week number, so `2030-12-30` belongs to `2031-W01`) and output an array of `{\"week\": \"YYYY-Www\", \"count\": N, \"total\": sum of amount}` ordered by week. Empty input gives `[]`.",
      REF_WEEKS, make_weeks, script="weeks.jq", runner=RUN, title="Events per ISO week", wrong=("group_by(.at[0:7]) | map({week: .[0].at[0:7], count: length})\n",)),
    S("directory-sizes", 4,
      "Write `sizes.jq`: given a JSON directory tree, list every directory with the total size of the files below it." + NOTE,
      "`jq -f sizes.jq -c FILE`: the input is a node `{name, size}` (a file) or `{name, children: [...]}` (a directory, possibly with no children). Output an array of `{\"path\": ..., \"size\": ...}` for every **directory** (files are not listed), "
      "where the path is the names from the root joined with `/` (the root is just its own name) and the size is the sum of the sizes of all files anywhere below it. Sorted by path (byte-wise). A file at the root gives `[]`.",
      REF_TREE, make_tree, script="sizes.jq", runner=RUN, title="Directory sizes from a tree", wrong=("[.name]\n",)),
    S("csv-text-to-objects", 3,
      "Write `rows.jq`: convert simple CSV text (read with `-R -s`) into an array of objects keyed by the header, with numbers converted." + NOTE,
      "`jq -f rows.jq -R -s -c`: the whole standard input arrives as one string. Blank lines are ignored; the first remaining line is the header (field names separated by commas; fields never contain commas or quotes); every other line becomes an object keyed by the header. "
      "A value that is empty (or missing because the line is short) becomes `null`; a value that matches `-?digits` optionally followed by `.digits` becomes a JSON number (`003` becomes `3`); anything else (`1e3`, `x`) stays a string. "
      "Input without any line gives `[]`; a header only gives `[]`.",
      REF_CSV, make_csv, script="rows.jq", runner=RUN, title="CSV text to objects", wrong=("split(\"\\n\")\n",)),
    S("bump-and-clean-config", 3,
      "Write `bump.jq`: bump the patch version of a config, stamp a date passed with `--arg date`, remove every `debug` key at any depth and make sure `features.beta` exists." + NOTE,
      "`jq -f bump.jq --arg date DATE FILE`: in the config object (1) `version` is a `MAJOR.MINOR.PATCH` string whose patch part is increased by one (`2.14.99` becomes `2.14.100`); (2) `updated` is set to `$date`; "
      "(3) every key named `debug` is deleted wherever it appears, in nested objects and in objects inside arrays; (4) `features.beta` is set to `false` if it is missing or null, an existing value (also `false` or `true`) stays. Everything else, including key order, is unchanged.",
      REF_UPDATE, make_update, script="bump.jq", runner=RUN, title="Bump and clean a config", wrong=(".updated = $date\n",)),
    S("fix-order-statistics", 2,
      "`stats.jq` should print the count, total and average of order lines but fails on lines without a quantity and on an empty list. Fix it." + NOTE,
      "`jq -f stats.jq -c FILE`: the input is an array of `{price, qty}`. Print `{\"count\": N, \"total\": T, \"average\": A}` where a missing `qty` counts as 1, `T` is the sum of `price * qty` and `A = T / N`, both rounded to two decimals. "
      "For an empty array `count` is 0, `total` is 0 and `average` is `null`.",
      REF_TOTAL, make_total, script="stats.jq", runner=RUN, buggy=BUG_TOTAL, title="Order statistics", wrong=(BUG_TOTAL,)),
    S("top-three-scores-with-ties", 3,
      "Write `podium.jq`: list the three highest distinct scores with everybody who has them." + NOTE,
      "`jq -f podium.jq -c FILE`: the input is an array of `{name, score}`. Output an array of at most three objects `{\"rank\": 1|2|3, \"score\": S, \"names\": [sorted names]}` for the three highest **distinct** scores (dense ranking: equal scores share a rank, the next distinct score is the next rank), best first, names sorted byte-wise. Empty input gives `[]`.",
      REF_TOP, make_top, script="podium.jq", runner=RUN, title="Podium with ties", wrong=("sort_by(-.score) | .[0:3]\n",)),
]


@family("shell-jq-programs", category="shell", lang="bash", kind="feature", n=len(SPECS),
        summary="jq programs with exact output: CSV flattening, grouping, latest-per-key, dotted paths, joins via --slurpfile, validation, ISO weeks, trees")
def jq_programs(rng, n):
    return K.shell_tasks("jq-programs", SPECS, rng, n)
