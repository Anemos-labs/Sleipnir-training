"""Serialisation round trips that lose information: a typed JSON codec (python) and struct JSON in go."""
from fx import dd, family, langs
from generators.fix._hand_kit import Base, Bug, tasks_from

# ------------------------------------------------------------------------------------------------------------------
# Base A (python): a codec for the save files of a farm simulation.
# ------------------------------------------------------------------------------------------------------------------

A_README = dd('''
    # savefile

    Save files of a farm simulation are JSON text produced by `savefile.codec.dumps(value)` and read back by `loads(text)`. The
    round trip must be exact: `loads(dumps(v))` has the same value **and the same types** as `v`.

    Supported values: `None`, `bool`, `int` (any size), finite `float`, `str`, `list`, `dict`, `tuple`, `set`/`frozenset` (loaded
    back as `set`), `decimal.Decimal` (exact, with its trailing zeros: `Decimal("0.10")`), `datetime.date`, `datetime.datetime`
    (naive or timezone-aware, with microseconds and the UTC offset), and the floats `nan`, `inf`, `-inf`. Anything else is a
    `TypeError`.

    * Dict keys may be of any supported hashable type (ints, tuples, ...): they are loaded back with their types, and such a dict
      keeps its insertion order. A dict whose keys are all strings is written as a plain JSON object (its keys come out sorted).
    * The output is strict JSON (no `NaN` literals) and sorts the keys of plain objects.
    * Players choose their own names, so any string may be a dict key: a dict with a key named `__t` must round-trip like any other.
''')

A_CODEC = dd('''
    import datetime as dt
    import json
    import math
    from decimal import Decimal

    TAG = "__t"


    def _enc(v):
        if v is None or isinstance(v, (bool, int, str)):
            return v
        if isinstance(v, float):
            if math.isnan(v) or math.isinf(v):
                return {TAG: "float", "v": repr(v)}
            return v
        if isinstance(v, Decimal):
            return {TAG: "decimal", "v": str(v)}
        if isinstance(v, dt.datetime):
            return {TAG: "datetime", "v": v.isoformat()}
        if isinstance(v, dt.date):
            return {TAG: "date", "v": v.isoformat()}
        if isinstance(v, tuple):
            return {TAG: "tuple", "v": [_enc(x) for x in v]}
        if isinstance(v, (set, frozenset)):
            return {TAG: "set", "v": sorted((_enc(x) for x in v), key=lambda e: json.dumps(e, sort_keys=True))}
        if isinstance(v, list):
            return [_enc(x) for x in v]
        if isinstance(v, dict):
            if all(isinstance(k, str) for k in v) and TAG not in v:
                return {k: _enc(x) for k, x in v.items()}
            return {TAG: "dict", "v": [[_enc(k), _enc(x)] for k, x in v.items()]}
        raise TypeError(f"cannot save a value of type {type(v).__name__}")


    def _dec(v):
        if isinstance(v, list):
            return [_dec(x) for x in v]
        if isinstance(v, dict):
            if TAG in v:
                kind, data = v[TAG], v["v"]
                if kind == "float":
                    return float(data)
                if kind == "decimal":
                    return Decimal(data)
                if kind == "datetime":
                    return dt.datetime.fromisoformat(data)
                if kind == "date":
                    return dt.date.fromisoformat(data)
                if kind == "tuple":
                    return tuple(_dec(x) for x in data)
                if kind == "set":
                    return {_dec(x) for x in data}
                if kind == "dict":
                    return {_dec(k): _dec(x) for k, x in data}
                raise ValueError(f"unknown tag {kind!r}")
            return {k: _dec(x) for k, x in v.items()}
        return v


    def dumps(value):
        return json.dumps(_enc(value), sort_keys=True, allow_nan=False)


    def loads(text):
        return _dec(json.loads(text))
''')

A_VISIBLE = {
    "tests/test_codec.py": dd('''
        import unittest

        from savefile.codec import dumps, loads


        class CodecTests(unittest.TestCase):
            def test_plain_values(self):
                value = {"farm": "Elm", "acres": 12, "crops": ["rye", "oat"], "open": True, "note": None}
                self.assertEqual(loads(dumps(value)), value)

            def test_unsupported_type(self):
                with self.assertRaises(TypeError):
                    dumps(object())


        if __name__ == "__main__":
            unittest.main()
    '''),
}

A_HIDDEN = {
    "tests/test_hidden_codec.py": dd('''
        import datetime as dt
        import json
        import math
        import unittest
        from decimal import Decimal

        from savefile.codec import dumps, loads


        def shape(v):
            """Value and type of everything, so that 1 and 1.0, tuples and lists, str and int keys differ."""
            if isinstance(v, dict):
                items = [(shape(k), shape(x)) for k, x in v.items()]
                if all(isinstance(k, str) for k in v):
                    items.sort(key=repr)  # plain objects are written with sorted keys
                return ("dict", items)
            if isinstance(v, set):
                return ("set", sorted(repr(shape(x)) for x in v))
            if isinstance(v, (list, tuple)):
                return (type(v).__name__, [shape(x) for x in v])
            return (type(v).__name__, repr(v))


        def round_trip(v):
            text = dumps(v)
            json.loads(text)  # must be valid JSON
            return loads(text)


        class Types(unittest.TestCase):
            def check(self, v):
                self.assertEqual(shape(round_trip(v)), shape(v))

            def test_scalars(self):
                for v in (None, True, False, 0, -7, 2 ** 70, 1.5, -0.0, 1e300, "", "text \\u00e9\\U0001f600", "a\\nb"):
                    self.check(v)

            def test_tuples_stay_tuples(self):
                self.check((1, 2, (3, [4, (5,)])))
                self.check({"pos": (3, 4), "path": [(0, 0), (1, 1)]})
                self.check(())

            def test_decimals_are_exact(self):
                self.check({"gold": Decimal("123456789.123456789"), "price": Decimal("0.10"), "neg": Decimal("-0.005"), "big": Decimal("1E+3")})
                self.assertEqual(round_trip(Decimal("19.99")), Decimal("19.99"))
                self.assertIsInstance(round_trip(Decimal("19.99")), Decimal)

            def test_dates_and_datetimes(self):
                tz = dt.timezone(dt.timedelta(hours=5, minutes=30))
                for v in (dt.datetime(2025, 3, 1, 12, 30, 45, 123456, tzinfo=tz), dt.datetime(2025, 3, 1, 12, 30, 45), dt.date(2025, 3, 1),
                          dt.datetime(2025, 3, 1, 0, 0, tzinfo=dt.timezone.utc)):
                    self.check(v)
                back = round_trip(dt.datetime(2025, 3, 1, 12, 30, 45, 123456, tzinfo=tz))
                self.assertEqual(back.utcoffset(), dt.timedelta(hours=5, minutes=30))
                self.assertEqual(back.microsecond, 123456)

            def test_sets(self):
                self.check({1, 2, 3})
                self.check({"a", "b"})
                self.check({(1, 2), (3, 4)})
                self.assertEqual(round_trip(frozenset({1, 2})), {1, 2})
                self.assertIsInstance(round_trip(frozenset({1})), set)

            def test_non_finite_floats(self):
                back = round_trip([float("nan"), float("inf"), float("-inf"), 1.0])
                self.assertTrue(math.isnan(back[0]))
                self.assertEqual(back[1:], [float("inf"), float("-inf"), 1.0])
                self.assertNotIn("NaN", dumps(float("nan")))
                self.assertNotIn("Infinity", dumps([float("inf")]))


        class Dicts(unittest.TestCase):
            def check(self, v):
                self.assertEqual(shape(round_trip(v)), shape(v))

            def test_non_string_keys(self):
                self.check({1: "a", 2: ("x", 3)})
                self.check({(1, 2): [None, True, 1.5], (3, 4): "far"})
                self.check({1: "int", "1": "str", 2.5: "float"})
                self.check({dt.date(2025, 1, 1): "new year", Decimal("1.50"): "price"})

            def test_insertion_order_is_kept(self):
                v = {3: "c", 1: "a", 2: "b"}
                self.assertEqual(list(round_trip(v)), [3, 1, 2])

            def test_plain_objects_are_plain_json(self):
                self.assertEqual(json.loads(dumps({"b": 1, "a": [1, 2]})), {"b": 1, "a": [1, 2]})
                self.assertEqual(dumps({"b": 1, "a": 2}), '{"a": 2, "b": 1}')

            def test_a_key_named_like_the_codec_internals(self):
                for v in ({"__t": "tuple", "v": [1, 2]}, {"__t": 1}, {"__t": "dict", "v": [["a", 1]]}, {"outer": {"__t": "set", "v": [1]}},
                          {"__t": "float", "v": "nan", "other": 2}, {"v": 1}):
                    self.assertEqual(shape(round_trip(v)), shape(v), v)

            def test_deep_nesting(self):
                v = {"farms": [{"id": 1, "fields": {(0, 1): {"crop": "rye", "yield": Decimal("2.50"), "sown": dt.date(2025, 4, 2)}}}], "tags": {"a", "b"}}
                self.assertEqual(shape(round_trip(v)), shape(v))


        class Errors(unittest.TestCase):
            def test_unsupported_values(self):
                for v in (object(), b"bytes", complex(1, 2), {"x": object()}, [lambda: 1]):
                    with self.assertRaises(TypeError):
                        dumps(v)


        if __name__ == "__main__":
            unittest.main()
    '''),
}


def _a_prompts():
    p = {}
    p["int-keys"] = lambda c: (
        "After loading a saved game the field table is empty for every plot: the plots are stored in a dict keyed by plot number and "
        "come back keyed by text. A quick round trip of `{1: 'rye', 2: 'oat'}` gives back "
        + c.probe("from savefile.codec import dumps, loads\nprint(loads(dumps({1: 'rye', 2: 'oat'})))\n")[1]
        + ". Dicts with tuple keys do not save at all."
    )
    p["tuple"] = (
        "Saved positions come back as lists, which then fail as dict keys (`TypeError: unhashable type: 'list'`) in the pathfinding code that "
        "expects tuples. Tuples must survive a save and load."
    )
    p["decimal"] = lambda c: (
        "Prices drift by a tiny amount every save and load. `Decimal('123456789.123456789')` comes back as "
        + c.probe("from decimal import Decimal\nfrom savefile.codec import dumps, loads\nprint(repr(loads(dumps(Decimal('123456789.123456789')))))\n")[1]
        + " and sums over many saves no longer match the ledger. Money must stay `Decimal`, exactly."
    )
    p["datetime"] = (
        "Timestamps in saved games lose their time zone and their microseconds: a timezone-aware event comes back naive "
        "and the replay ordering breaks. Dates and naive datetimes are fine."
    )
    p["nan"] = lambda c: (
        "Saving a game crashes when a sensor reading is `nan`:\n\n```\n"
        + c.bad_run("from savefile.codec import dumps\ndumps({'moisture': float('nan')})\n").splitlines()[-1]
        + "\n```\n\nThe README says non-finite floats are supported and the output must be strict JSON."
    )
    p["tag"] = (
        "A player named a plot `__t` and now the whole save file fails to load (or loads as a different kind of object). Names are chosen by "
        "players, so any string can be a dict key. Please make sure arbitrary dicts survive."
    )
    p["two"] = (
        "Two kinds of damage in saved games: plot tables keyed by number come back with text keys, and prices lose digits (Decimal "
        "becomes a float). The visible test only saves strings and plain ints. Please fix the codec properly."
    )
    return p


def _base_a() -> Base:
    P = _a_prompts()
    good = {"README.md": A_README, "savefile/__init__.py": '"""Save file codec."""\n', "savefile/codec.py": A_CODEC}
    c = "savefile/codec.py"
    int_keys = ('''        if all(isinstance(k, str) for k in v) and TAG not in v:
            return {k: _enc(x) for k, x in v.items()}
        return {TAG: "dict", "v": [[_enc(k), _enc(x)] for k, x in v.items()]}
''', '''        return {str(k): _enc(x) for k, x in v.items()}
''')
    decimal = ('        return {TAG: "decimal", "v": str(v)}\n', "        return float(v)\n")
    bugs = [
        Bug("tuples-become-lists", 2, {c: [('        return {TAG: "tuple", "v": [_enc(x) for x in v]}\n', "        return [_enc(x) for x in v]\n")]}, P["tuple"]),
        Bug("dict-keys-become-text", 3, {c: [int_keys]}, P["int-keys"]),
        Bug("decimals-go-through-float", 3, {c: [decimal]}, P["decimal"]),
        Bug("datetimes-lose-zone-and-microseconds", 3, {c: [('        return {TAG: "datetime", "v": v.isoformat()}\n', '        return {TAG: "datetime", "v": v.strftime("%Y-%m-%dT%H:%M:%S")}\n')]}, P["datetime"]),
        Bug("non-finite-floats-unsupported", 3, {c: [('        if math.isnan(v) or math.isinf(v):\n            return {TAG: "float", "v": repr(v)}\n', "")]}, P["nan"]),
        Bug("user-dicts-can-forge-tags", 4, {c: [("        if all(isinstance(k, str) for k in v) and TAG not in v:\n", "        if all(isinstance(k, str) for k in v):\n")]}, P["tag"]),
        Bug("text-keys-and-float-decimals", 5, {c: [int_keys, decimal]}, P["two"]),
    ]
    return Base("savefile", "python", good, A_VISIBLE, A_HIDDEN, bugs)


# ------------------------------------------------------------------------------------------------------------------
# Base B (go): JSON for a user profile.
# ------------------------------------------------------------------------------------------------------------------

B_README = dd('''
    # profile

    JSON storage of user profiles. `Encode(p)` and `Decode(data)` must round-trip every `Profile` exactly.

    * `Name` string. `Nick *string`: `nil` is `null`; a pointer to the empty string is `""` and must stay a pointer to the empty string.
    * `Tags []string` and `Scores map[string]int`: **`nil` and empty are different**: `nil` is written `null`, an empty slice or map is
      `[]` / `{}`, and decoding gives back a nil or an empty (non-nil) value accordingly.
    * `Joined time.Time`: RFC 3339 with the nanoseconds and the **UTC offset it was created with** (a profile created at +05:30 reads back
      at +05:30).
    * `Balance Money`: an amount in cents, written as a JSON **string** with two decimals (`"12.34"`, `"-0.05"`, `"0.00"`); anything
      else (a number, `"12.3"`, `"abc"`) is a decode error. This also holds when a `Profile` is encoded by value.
    * `Extra map[string]any`: arbitrary JSON; numbers written without fraction or exponent decode as `int64` (all the way up to 2^63-1,
      without losing digits), other numbers as `float64`; nested arrays and objects are normalised the same way.
    * `Decode` ignores fields it does not know (newer writers add fields) and leaves missing fields at their zero value.
''')

B_PROFILE = dd('''
    package profile

    import (
    	"bytes"
    	"encoding/json"
    	"fmt"
    	"strconv"
    	"strings"
    	"time"
    )

    // Money is an amount in cents. Its JSON form is a string with two decimals.
    type Money int64

    func (m Money) MarshalJSON() ([]byte, error) {
    	v := int64(m)
    	sign := ""
    	if v < 0 {
    		sign = "-"
    		v = -v
    	}
    	return json.Marshal(fmt.Sprintf("%s%d.%02d", sign, v/100, v%100))
    }

    func (m *Money) UnmarshalJSON(b []byte) error {
    	var s string
    	if err := json.Unmarshal(b, &s); err != nil {
    		return err
    	}
    	neg := strings.HasPrefix(s, "-")
    	s = strings.TrimPrefix(s, "-")
    	whole, frac, ok := strings.Cut(s, ".")
    	if !ok || len(frac) != 2 {
    		return fmt.Errorf("bad money %q", s)
    	}
    	w, err := strconv.ParseUint(whole, 10, 62)
    	if err != nil {
    		return fmt.Errorf("bad money %q: %w", s, err)
    	}
    	f, err := strconv.ParseUint(frac, 10, 7)
    	if err != nil {
    		return fmt.Errorf("bad money %q: %w", s, err)
    	}
    	v := int64(w)*100 + int64(f)
    	if neg {
    		v = -v
    	}
    	*m = Money(v)
    	return nil
    }

    // Profile is what the service stores per user.
    type Profile struct {
    	Name    string         `json:"name"`
    	Nick    *string        `json:"nick"`
    	Tags    []string       `json:"tags"`
    	Scores  map[string]int `json:"scores"`
    	Joined  time.Time      `json:"joined"`
    	Balance Money          `json:"balance"`
    	Extra   map[string]any `json:"extra"`
    }

    // Encode writes the JSON form of a profile.
    func Encode(p Profile) ([]byte, error) {
    	return json.Marshal(p)
    }

    // Decode reads a profile written by Encode (or by a newer writer).
    func Decode(data []byte) (Profile, error) {
    	var p Profile
    	dec := json.NewDecoder(bytes.NewReader(data))
    	dec.UseNumber()
    	if err := dec.Decode(&p); err != nil {
    		return Profile{}, err
    	}
    	for k, v := range p.Extra {
    		p.Extra[k] = normalise(v)
    	}
    	return p, nil
    }

    func normalise(v any) any {
    	switch x := v.(type) {
    	case json.Number:
    		if i, err := x.Int64(); err == nil {
    			return i
    		}
    		f, _ := x.Float64()
    		return f
    	case []any:
    		for i := range x {
    			x[i] = normalise(x[i])
    		}
    		return x
    	case map[string]any:
    		for k, e := range x {
    			x[k] = normalise(e)
    		}
    		return x
    	}
    	return v
    }
''')

B_VISIBLE = {
    "profile_test.go": dd('''
        package profile

        import (
        	"testing"
        	"time"
        )

        func TestSimpleRoundTrip(t *testing.T) {
        	p := Profile{Name: "ann", Joined: time.Date(2025, 3, 1, 12, 0, 0, 0, time.UTC), Balance: 1234}
        	data, err := Encode(p)
        	if err != nil {
        		t.Fatal(err)
        	}
        	q, err := Decode(data)
        	if err != nil {
        		t.Fatal(err)
        	}
        	if q.Name != "ann" || q.Balance != 1234 || !q.Joined.Equal(p.Joined) {
        		t.Fatalf("got %+v", q)
        	}
        }
    '''),
}

B_HIDDEN = {
    "profile_hidden_test.go": dd('''
        package profile

        import (
        	"math"
        	"reflect"
        	"strings"
        	"testing"
        	"time"
        )

        func str(s string) *string { return &s }

        func roundTrip(t *testing.T, p Profile) Profile {
        	t.Helper()
        	data, err := Encode(p)
        	if err != nil {
        		t.Fatalf("encode: %v", err)
        	}
        	q, err := Decode(data)
        	if err != nil {
        		t.Fatalf("decode %s: %v", data, err)
        	}
        	return q
        }

        func TestNilAndEmptyStayDifferent(t *testing.T) {
        	nils := roundTrip(t, Profile{Name: "n"})
        	if nils.Tags != nil || nils.Scores != nil || nils.Extra != nil || nils.Nick != nil {
        		t.Fatalf("nil values changed: %+v", nils)
        	}
        	empties := roundTrip(t, Profile{Name: "e", Nick: str(""), Tags: []string{}, Scores: map[string]int{}, Extra: map[string]any{}})
        	if empties.Tags == nil || len(empties.Tags) != 0 {
        		t.Errorf("empty Tags became %#v", empties.Tags)
        	}
        	if empties.Scores == nil || len(empties.Scores) != 0 {
        		t.Errorf("empty Scores became %#v", empties.Scores)
        	}
        	if empties.Extra == nil {
        		t.Errorf("empty Extra became nil")
        	}
        	if empties.Nick == nil || *empties.Nick != "" {
        		t.Errorf("pointer to empty string became %v", empties.Nick)
        	}
        }

        func TestValuesSurvive(t *testing.T) {
        	p := Profile{Name: "ann", Nick: str("annie"), Tags: []string{"a", "b"}, Scores: map[string]int{"x": 0, "y": -3}}
        	q := roundTrip(t, p)
        	if q.Name != "ann" || *q.Nick != "annie" || !reflect.DeepEqual(q.Tags, p.Tags) || !reflect.DeepEqual(q.Scores, p.Scores) {
        		t.Fatalf("got %+v", q)
        	}
        }

        func TestTimeKeepsNanosecondsAndOffset(t *testing.T) {
        	zone := time.FixedZone("", 5*3600+30*60)
        	joined := time.Date(2025, 3, 1, 12, 30, 45, 123456789, zone)
        	q := roundTrip(t, Profile{Name: "t", Joined: joined})
        	if !q.Joined.Equal(joined) {
        		t.Errorf("instant changed: %v vs %v", q.Joined, joined)
        	}
        	if _, off := q.Joined.Zone(); off != 5*3600+30*60 {
        		t.Errorf("offset %d, want %d", off, 5*3600+30*60)
        	}
        	if q.Joined.Nanosecond() != 123456789 {
        		t.Errorf("nanoseconds %d", q.Joined.Nanosecond())
        	}
        }

        func TestMoneyIsAStringEvenWhenEncodedByValue(t *testing.T) {
        	cases := map[Money]string{1234: `"12.34"`, -5: `"-0.05"`, 0: `"0.00"`, 100: `"1.00"`, 9223372036854775: `"92233720368547.75"`}
        	for m, want := range cases {
        		data, err := Encode(Profile{Balance: m})
        		if err != nil {
        			t.Fatal(err)
        		}
        		if !strings.Contains(string(data), `"balance":`+want) {
        			t.Errorf("Money %d encoded as %s, want balance %s", m, data, want)
        		}
        		if got := roundTrip(t, Profile{Balance: m}).Balance; got != m {
        			t.Errorf("Money %d came back as %d", m, got)
        		}
        	}
        }

        func TestBadMoneyIsAnError(t *testing.T) {
        	for _, bad := range []string{`"12.3"`, `"abc"`, `12.34`, `"1.234"`, `""`, `"--1.00"`} {
        		if _, err := Decode([]byte(`{"name":"x","balance":` + bad + `}`)); err == nil {
        			t.Errorf("balance %s should be rejected", bad)
        		}
        	}
        }

        func TestExtraNumbers(t *testing.T) {
        	p := Profile{Name: "x", Extra: map[string]any{
        		"big":    int64(math.MaxInt64),
        		"small":  int64(-9007199254740993),
        		"count":  int64(3),
        		"ratio":  1.5,
        		"nested": map[string]any{"id": int64(9007199254740993), "list": []any{int64(1), 2.5, "s"}},
        		"text":   "t",
        		"flag":   true,
        		"nothing": nil,
        	}}
        	q := roundTrip(t, p)
        	if !reflect.DeepEqual(q.Extra, p.Extra) {
        		t.Fatalf("Extra changed:\\n got %#v\\nwant %#v", q.Extra, p.Extra)
        	}
        }

        func TestUnknownAndMissingFields(t *testing.T) {
        	q, err := Decode([]byte(`{"name":"ann","newer_field":{"a":[1,2,3]},"tags":["a"]}`))
        	if err != nil {
        		t.Fatalf("unknown fields must be ignored: %v", err)
        	}
        	if q.Name != "ann" || len(q.Tags) != 1 || q.Scores != nil || q.Balance != 0 || !q.Joined.IsZero() || q.Nick != nil {
        		t.Fatalf("got %+v", q)
        	}
        }

        func TestInvalidJSON(t *testing.T) {
        	if _, err := Decode([]byte(`{"name": `)); err == nil {
        		t.Fatal("truncated JSON accepted")
        	}
        }
    '''),
}


def _b_prompts():
    p = {}
    p["omitempty"] = (
        "A profile with no tags is saved as `\"tags\": []` and read back as having no tags at all (nil); the new sync code treats nil as 'not "
        "loaded yet' and refuses to write. `Tags` and `Scores` must keep the difference between nil and empty."
    )
    p["money-ptr"] = lambda c: (
        "Profiles encoded by value store the balance as a bare number (`\"balance\":1234`) and then cannot be decoded: "
        + c.visible_out()
        + "\nThe money type's JSON form is a string everywhere."
    )
    p["utc"] = (
        "Everyone's join time shows up as UTC after a save and load. Customers in India (+05:30) see their join date shift by hours near "
        "midnight. The offset the profile was created with has to survive."
    )
    p["extra-float"] = (
        "Large ids stored in a profile's `extra` data (`9007199254740993`) come back off by one or two, and every number there decodes as a float64. "
        "The README says integers must decode as int64 without losing digits."
    )
    p["strict"] = (
        "Deploying a newer profile writer (it adds a `locale` field) broke every older reader with `json: unknown field \"locale\"`. Readers must "
        "ignore fields they do not know."
    )
    return p


def _base_b() -> Base:
    P = _b_prompts()
    good = {"README.md": B_README, "go.mod": langs.go_mod("profile"), "profile.go": B_PROFILE}
    rep_money = {"reported_test.go": dd('''
        package profile

        import "testing"

        func TestBalanceEncodedByValueIsAString(t *testing.T) {
        	data, err := Encode(Profile{Name: "a", Balance: 1234})
        	if err != nil {
        		t.Fatal(err)
        	}
        	if _, err := Decode(data); err != nil {
        		t.Fatalf("decode of %s: %v", data, err)
        	}
        }
    ''')}
    f = "profile.go"
    bugs = [
        Bug("empty-slices-and-maps-omitted", 3, {f: [('Tags    []string       `json:"tags"`', 'Tags    []string       `json:"tags,omitempty"`'), ('Scores  map[string]int `json:"scores"`', 'Scores  map[string]int `json:"scores,omitempty"`')]}, P["omitempty"]),
        Bug("money-marshals-through-a-pointer", 3, {f: [("func (m Money) MarshalJSON() ([]byte, error) {\n\tv := int64(m)\n", "func (m *Money) MarshalJSON() ([]byte, error) {\n\tv := int64(*m)\n")]}, P["money-ptr"], reported=rep_money),
        Bug("join-time-forced-to-utc", 2, {f: [("func Encode(p Profile) ([]byte, error) {\n\treturn json.Marshal(p)\n", "func Encode(p Profile) ([]byte, error) {\n\tp.Joined = p.Joined.UTC()\n\treturn json.Marshal(p)\n")]}, P["utc"]),
        Bug("extra-numbers-are-floats", 4, {f: [("\tdec := json.NewDecoder(bytes.NewReader(data))\n\tdec.UseNumber()\n\tif err := dec.Decode(&p); err != nil {\n\t\treturn Profile{}, err\n\t}\n",
                                                 "\tif err := json.Unmarshal(data, &p); err != nil {\n\t\treturn Profile{}, err\n\t}\n"), ('\t"bytes"\n', "")]}, P["extra-float"]),
        Bug("unknown-fields-rejected", 2, {f: [("\tdec.UseNumber()\n", "\tdec.UseNumber()\n\tdec.DisallowUnknownFields()\n")]}, P["strict"]),
    ]
    return Base("profile", "go", good, B_VISIBLE, B_HIDDEN, bugs)


@family("fix-hand-roundtrip", category="fix", lang="python", kind="fix", n=12,
        summary="serialisation round-trip loss: typed JSON codec (python), struct JSON with nil/empty, money and times (go)")
def gen(rng, n):
    return tasks_from([_base_a(), _base_b()])
