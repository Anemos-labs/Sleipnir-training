"""cronspec (go): a cron expression matcher extended with aliases, ranges, steps, names, zones, last-day, next-run and window listing."""
import random

from fx import dd, langs
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # cronspec

    A small cron expression library for a job scheduler (Go, standard library only). `go test ./...` runs the tests.

    ## Layout

    * `cronspec.go`: `Schedule`, `Parse`.
    * `cron_test.go`: tests.

    ## Basics

    An expression has five fields separated by white space: minute (0-59), hour (0-23), day of month (1-31), month (1-12)
    and day of week (0-6, 0 is Sunday). A field is `*` (every value) or a comma-separated list of numbers (`5,10,30`);
    numbers are plain digits (leading zeros are fine). Errors are package variables and are returned wrapped
    (`fmt.Errorf("%w: ...")`), so callers use `errors.Is`.

    * `Parse(expr) (*Schedule, error)`: the wrong number of fields is `ErrFields`; a field that cannot be read (empty
      parts like `1,,2`, a `*` inside a list, anything but digits) is `ErrSyntax`; a number outside the range of its
      field is `ErrRange`.
    * `schedule.Matches(t time.Time) bool` is true when the minute, hour and month of `t` (seconds and below are ignored, the
      fields of `t` are taken in its own location) are allowed and the day is allowed. The day rule is the classic one: when
      both the day-of-month and the day-of-week field are restricted (not `*`), a day matches if **either** matches; when only
      one of them is restricted, that one decides; when both are `*` every day matches.
    * `schedule.String()` returns the five fields as written, joined by single spaces.
''')

CRON = '''\
// Package cronspec parses and evaluates cron expressions.
package cronspec

import (
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"
@@uniq imports
)

var (
	ErrFields = errors.New("cronspec: wrong number of fields")
	ErrSyntax = errors.New("cronspec: syntax error")
	ErrRange  = errors.New("cronspec: value out of range")
)

type field struct {
	any bool
	set map[int]bool
	@@slot field_fields
}

func (f field) matches(v int) bool { return f.any || f.set[v] }

// Schedule is a parsed expression.
type Schedule struct {
	minute, hour, dom, month, dow field
	text                          []string
	@@slot schedule_fields
}

type fieldSpec struct {
	name   string
	lo, hi int
	@@slot spec_fields
}

func newSpecs() [5]fieldSpec {
	s := [5]fieldSpec{
		{name: "minute", lo: 0, hi: 59},
		{name: "hour", lo: 0, hi: 23},
		{name: "day of month", lo: 1, hi: 31},
		{name: "month", lo: 1, hi: 12},
		{name: "day of week", lo: 0, hi: 6},
	}
	@@slot specs_extra
	return s
}

@@blocks types

func parseNumber(s string, sp fieldSpec) (int, error) {
	@@slot number_names
	if s == "" {
		return 0, fmt.Errorf("%w: %s: empty value", ErrSyntax, sp.name)
	}
	for _, c := range s {
		if c < '0' || c > '9' {
			return 0, fmt.Errorf("%w: %s: %q", ErrSyntax, sp.name, s)
		}
	}
	n, err := strconv.Atoi(s)
	if err != nil {
		return 0, fmt.Errorf("%w: %s: %q", ErrRange, sp.name, s)
	}
	if n < sp.lo || n > sp.hi {
		return 0, fmt.Errorf("%w: %s must be %d-%d, got %d", ErrRange, sp.name, sp.lo, sp.hi, n)
	}
	return n, nil
}

func parsePart(part string, sp fieldSpec) ([]int, error) {
	step, hasStep := 1, false
	star := false
	@@slot step_split
	lo, hi := 0, 0
	isRange := false
	if star {
		lo, hi, isRange = sp.lo, sp.hi, true
	} else {
		@@default part_bounds
		n, err := parseNumber(part, sp)
		if err != nil {
			return nil, err
		}
		lo, hi = n, n
		@@end
	}
	if hasStep && !isRange {
		return nil, fmt.Errorf("%w: %s: a step needs * or a range: %q", ErrSyntax, sp.name, part)
	}
	var out []int
	for v := lo; v <= hi; v += step {
		out = append(out, v)
	}
	return out, nil
}

func parseField(text string, sp fieldSpec) (field, error) {
	f := field{}
	if text == "*" {
		f.any = true
		return f, nil
	}
	f.set = map[int]bool{}
	for _, part := range strings.Split(text, ",") {
		@@slot part_pre
		vals, err := parsePart(part, sp)
		if err != nil {
			return f, err
		}
		for _, v := range vals {
			f.set[v] = true
		}
	}
	return f, nil
}

// Parse reads a cron expression.
func Parse(expr string) (*Schedule, error) {
	parts := strings.Fields(expr)
	@@slot parse_pre
	if len(parts) != 5 {
		return nil, fmt.Errorf("%w: need 5 fields, got %d", ErrFields, len(parts))
	}
	sp := newSpecs()
	s := &Schedule{text: parts}
	targets := []*field{&s.minute, &s.hour, &s.dom, &s.month, &s.dow}
	for i, p := range parts {
		f, err := parseField(p, sp[i])
		if err != nil {
			return nil, err
		}
		*targets[i] = f
	}
	@@slot parse_post
	return s, nil
}

// String returns the five fields as written.
func (s *Schedule) String() string { return strings.Join(s.text, " ") }

func (s *Schedule) dayMatches(t time.Time) bool {
	domOK := s.dom.matches(t.Day())
	dowOK := s.dow.matches(int(t.Weekday()))
	@@slot dom_extra
	switch {
	case s.dom.any && s.dow.any:
		return true
	case s.dom.any:
		return dowOK
	case s.dow.any:
		return domOK
	}
	return domOK || dowOK
}

// Matches reports whether t is one of the minutes of the schedule.
func (s *Schedule) Matches(t time.Time) bool {
	@@slot matches_pre
	return s.minute.matches(t.Minute()) && s.hour.matches(t.Hour()) && s.month.matches(int(t.Month())) && s.dayMatches(t)
}

@@blocks methods
'''

TEST_HELPERS = '''\
@@uniq imports

var _ = errors.Is
var _ = strings.ToUpper
var _ = reflect.DeepEqual

func __P__T(y int, mo time.Month, d, h, mi int) time.Time {
	return time.Date(y, mo, d, h, mi, 0, 0, time.UTC)
}

func __P__Must(t *testing.T, expr string) *Schedule {
	t.Helper()
	s, err := Parse(expr)
	if err != nil {
		t.Fatalf("Parse(%q): %v", expr, err)
	}
	return s
}
'''

VISIBLE = '''\
package cronspec

import (
	"errors"
	"reflect"
	"strings"
	"testing"
	"time"
)

''' + TEST_HELPERS.replace("__P__", "v").replace("@@uniq imports\n\n", "") + '''
func TestParseErrors(t *testing.T) {
	cases := []struct {
		expr string
		want error
	}{
		{"* * * *", ErrFields}, {"* * * * * *", ErrFields}, {"", ErrFields}, {"60 * * * *", ErrRange}, {"* 24 * * *", ErrRange},
		{"* * 0 * *", ErrRange}, {"* * * 13 *", ErrRange}, {"* * * * 7", ErrRange}, {"a * * * *", ErrSyntax}, {"1,,2 * * * *", ErrSyntax},
	}
	for _, c := range cases {
		if _, err := Parse(c.expr); !errors.Is(err, c.want) {
			t.Errorf("%q: got %v, want %v", c.expr, err, c.want)
		}
	}
}

func TestMatchesAndString(t *testing.T) {
	s := vMust(t, "  0,30   9 * * *  ")
	if !s.Matches(vT(2025, time.September, 1, 9, 30)) || s.Matches(vT(2025, time.September, 1, 9, 31)) {
		t.Fatal("minute list")
	}
	if got := s.String(); got != "0,30 9 * * *" {
		t.Fatalf("String: %q", got)
	}
	_ = reflect.DeepEqual
	_ = strings.ToUpper
}
@@blocks tests
'''

HIDDEN = '''\
package cronspec

import (
	"errors"
	"reflect"
	"strings"
	"testing"
	"time"
)

''' + TEST_HELPERS.replace("__P__", "h").replace("@@uniq imports\n\n", "") + '''
func hEq(t *testing.T, name string, got, want interface{}) {
	t.Helper()
	if !reflect.DeepEqual(got, want) {
		t.Errorf("%s: got %v, want %v", name, got, want)
	}
}

func hIs(t *testing.T, name string, err, target error) {
	t.Helper()
	if !errors.Is(err, target) {
		t.Errorf("%s: got %v, want %v", name, err, target)
	}
}

func hSame(t *testing.T, name string, got, want time.Time) {
	t.Helper()
	if !got.Equal(want) {
		t.Errorf("%s: got %v, want %v", name, got, want)
	}
}

func hMatches(t *testing.T, expr string, yes, no []time.Time) {
	t.Helper()
	s := hMust(t, expr)
	for _, tm := range yes {
		if !s.Matches(tm) {
			t.Errorf("%q should match %v", expr, tm)
		}
	}
	for _, tm := range no {
		if s.Matches(tm) {
			t.Errorf("%q should not match %v", expr, tm)
		}
	}
}

func TestBaseParseErrors(t *testing.T) {
	cases := []struct {
		expr string
		want error
	}{
		{"", ErrFields}, {"* * * *", ErrFields}, {"* * * * * *", ErrFields}, {"   ", ErrFields},
		{"60 * * * *", ErrRange}, {"* 24 * * *", ErrRange}, {"* * 0 * *", ErrRange}, {"* * 32 * *", ErrRange}, {"* * * 0 *", ErrRange},
		{"* * * 13 *", ErrRange}, {"* * * * 7", ErrRange}, {"1,60 * * * *", ErrRange}, {"99999999999999999999 * * * *", ErrRange},
		{"a * * * *", ErrSyntax}, {"1,,2 * * * *", ErrSyntax}, {"1, * * * *", ErrSyntax}, {",1 * * * *", ErrSyntax},
		{"*,5 * * * *", ErrSyntax}, {"5,* * * * *", ErrSyntax}, {"-1 * * * *", ErrSyntax}, {"+1 * * * *", ErrSyntax},
		{"1.5 * * * *", ErrSyntax}, {"** * * * *", ErrSyntax}, {"1 2 3 4 five", ErrSyntax},
	}
	for _, c := range cases {
		s, err := Parse(c.expr)
		hIs(t, c.expr, err, c.want)
		if s != nil {
			t.Errorf("%q: schedule returned with an error", c.expr)
		}
	}
	for _, ok := range []string{"* * * * *", "0 0 1 1 0", "59 23 31 12 6", "05 007 01 01 00", "1,2,3 4,5 6 7 1,2"} {
		if _, err := Parse(ok); err != nil {
			t.Errorf("%q: %v", ok, err)
		}
	}
}

func TestBaseMatches(t *testing.T) {
	hMatches(t, "30 2 * * *",
		[]time.Time{hT(2025, time.September, 1, 2, 30), hT(2024, time.February, 29, 2, 30), hT(2030, time.December, 31, 2, 30)},
		[]time.Time{hT(2025, time.September, 1, 2, 31), hT(2025, time.September, 1, 3, 30), hT(2025, time.September, 1, 14, 30)})
	hMatches(t, "0,30 9,17 * * *",
		[]time.Time{hT(2025, time.September, 1, 9, 0), hT(2025, time.September, 1, 9, 30), hT(2025, time.September, 1, 17, 0), hT(2025, time.September, 1, 17, 30)},
		[]time.Time{hT(2025, time.September, 1, 9, 15), hT(2025, time.September, 1, 10, 0), hT(2025, time.September, 1, 17, 31)})
	hMatches(t, "0 0 1 1 *",
		[]time.Time{hT(2025, time.January, 1, 0, 0), hT(2031, time.January, 1, 0, 0)},
		[]time.Time{hT(2025, time.January, 2, 0, 0), hT(2025, time.February, 1, 0, 0)})
	hMatches(t, "0 12 * 6,12 *",
		[]time.Time{hT(2025, time.June, 17, 12, 0), hT(2025, time.December, 1, 12, 0)},
		[]time.Time{hT(2025, time.July, 17, 12, 0)})
	hMatches(t, "0 8 * * 0",
		[]time.Time{hT(2025, time.September, 7, 8, 0), hT(2025, time.September, 14, 8, 0)},
		[]time.Time{hT(2025, time.September, 8, 8, 0), hT(2025, time.September, 6, 8, 0)})
	hMatches(t, "* * * * *", []time.Time{hT(2025, time.September, 1, 0, 0), hT(2025, time.December, 31, 23, 59)}, nil)
	s := hMust(t, "15 10 * * *")
	if !s.Matches(time.Date(2025, time.September, 1, 10, 15, 59, 999, time.UTC)) {
		t.Error("seconds and nanoseconds must be ignored")
	}
	plus2 := time.FixedZone("plus2", 2*3600)
	if !s.Matches(time.Date(2025, time.September, 1, 10, 15, 0, 0, plus2)) || s.Matches(time.Date(2025, time.September, 1, 8, 15, 0, 0, plus2)) {
		t.Error("the fields of t are taken in its own location")
	}
}

func TestBaseDayRule(t *testing.T) {
	// 2025-09-01 is a Monday: Mondays are the 1st, 8th, 15th, 22nd and 29th.
	hMatches(t, "0 0 15 * 1",
		[]time.Time{hT(2025, time.September, 15, 0, 0), hT(2025, time.September, 8, 0, 0), hT(2025, time.September, 1, 0, 0), hT(2025, time.October, 15, 0, 0)},
		[]time.Time{hT(2025, time.September, 16, 0, 0), hT(2025, time.September, 9, 0, 0), hT(2025, time.October, 14, 0, 0)})
	hMatches(t, "0 0 15 * *",
		[]time.Time{hT(2025, time.September, 15, 0, 0)},
		[]time.Time{hT(2025, time.September, 8, 0, 0), hT(2025, time.September, 16, 0, 0)})
	hMatches(t, "0 0 * * 1",
		[]time.Time{hT(2025, time.September, 8, 0, 0), hT(2025, time.September, 29, 0, 0)},
		[]time.Time{hT(2025, time.September, 16, 0, 0)})
	hMatches(t, "0 0 1,31 * 0,6",
		[]time.Time{hT(2025, time.September, 6, 0, 0), hT(2025, time.September, 7, 0, 0), hT(2025, time.September, 1, 0, 0), hT(2025, time.October, 31, 0, 0)},
		[]time.Time{hT(2025, time.September, 2, 0, 0), hT(2025, time.October, 30, 0, 0)})
}

func TestBaseString(t *testing.T) {
	hEq(t, "plain", hMust(t, "5,10 3 * * *").String(), "5,10 3 * * *")
	hEq(t, "spaces", hMust(t, "\\t 5,10   3 *\\t* * \\n").String(), "5,10 3 * * *")
}
@@blocks tests
'''


def make_slices(rng: random.Random):
    weekly_dow = rng.choice([0, 1])
    horizon = rng.choice([3, 5])
    S = []

    S.append(Slice(
        id="aliases", title="Alias expressions", d=1,
        pitch=("Half of the crontabs in the shop are `@daily` and `@hourly` and the parser rejects them.",
               "People want to write the usual shortcuts instead of five fields."),
        reqs=(f"`Parse` understands these aliases as the whole expression: `@yearly` and `@annually` (`0 0 1 1 *`), `@monthly` (`0 0 1 * *`), `@weekly` (`0 0 * * {weekly_dow}`), `@daily` and `@midnight` (`0 0 * * *`) and `@hourly` (`0 * * * *`). Aliases are lower-case. An unknown alias, or an alias together with other fields, is `ErrSyntax`. `String()` of an alias schedule returns the five fields it stands for.",),
        code={
            "cronspec.go::types": f'''
                var aliases = map[string]string{{
                	"@yearly":   "0 0 1 1 *",
                	"@annually": "0 0 1 1 *",
                	"@monthly":  "0 0 1 * *",
                	"@weekly":   "0 0 * * {weekly_dow}",
                	"@daily":    "0 0 * * *",
                	"@midnight": "0 0 * * *",
                	"@hourly":   "0 * * * *",
                }}
            ''',
            "cronspec.go::parse_pre": '''
                if len(parts) > 0 && strings.HasPrefix(parts[0], "@") {
                	exp, ok := aliases[parts[0]]
                	if !ok || len(parts) != 1 {
                		return nil, fmt.Errorf("%w: alias %q", ErrSyntax, strings.Join(parts, " "))
                	}
                	parts = strings.Fields(exp)
                }
            ''',
        },
        readme=f"## Alias expressions\n\n`@yearly`/`@annually`, `@monthly`, `@weekly` (`0 0 * * {weekly_dow}`), `@daily`/`@midnight` and `@hourly` stand for five-field expressions; `String()` returns the expansion. Unknown aliases and aliases with extra fields are `ErrSyntax`.\n",
        vtests='''
            func TestAliasBasic(t *testing.T) {
            	s := vMust(t, "@hourly")
            	if !s.Matches(vT(2025, time.September, 1, 7, 0)) || s.Matches(vT(2025, time.September, 1, 7, 1)) {
            		t.Fatal("@hourly")
            	}
            }
        ''',
        tests=fmt('''
            func TestAliases(t *testing.T) {
            	hEq(t, "yearly", hMust(t, "@yearly").String(), "0 0 1 1 *")
            	hEq(t, "annually", hMust(t, "@annually").String(), "0 0 1 1 *")
            	hEq(t, "monthly", hMust(t, "@monthly").String(), "0 0 1 * *")
            	hEq(t, "weekly", hMust(t, "@weekly").String(), "0 0 * * __W__")
            	hEq(t, "daily", hMust(t, "@daily").String(), "0 0 * * *")
            	hEq(t, "midnight", hMust(t, "@midnight").String(), "0 0 * * *")
            	hEq(t, "hourly", hMust(t, "  @hourly  ").String(), "0 * * * *")
            	hMatches(t, "@monthly", []time.Time{hT(2025, time.September, 1, 0, 0)}, []time.Time{hT(2025, time.September, 2, 0, 0), hT(2025, time.September, 1, 0, 1)})
            	hMatches(t, "@daily", []time.Time{hT(2025, time.September, 9, 0, 0)}, []time.Time{hT(2025, time.September, 9, 1, 0)})
            	hMatches(t, "@weekly", []time.Time{hT(2025, time.September, 7+__W__, 0, 0)}, []time.Time{hT(2025, time.September, 9, 0, 0)})
            }

            func TestAliasErrors(t *testing.T) {
            	for _, bad := range []string{"@never", "@Daily", "@", "@daily *", "@daily 1 2 3 4", "@reboot", "@hourly@daily", "daily"} {
            		_, err := Parse(bad)
            		if err == nil {
            			t.Errorf("%q accepted", bad)
            		}
            	}
            	_, err := Parse("@daily extra")
            	hIs(t, "extra field", err, ErrSyntax)
            	_, err = Parse("@sometimes")
            	hIs(t, "unknown alias", err, ErrSyntax)
            	_, err = Parse("@daily 1 2 3 4")
            	hIs(t, "alias with a full expression", err, ErrSyntax)
            }
        ''', W=weekly_dow),
    ))

    S.append(Slice(
        id="ranges", title="Ranges", d=2,
        pitch=("Weekday-only jobs have to be written as `1,2,3,4,5` and nobody can read the crontab any more.",
               "Fields should accept ranges such as `9-17`."),
        reqs=("A part of a field can be a range `a-b` (both ends included, both inside the range of the field) and ranges can be mixed with single numbers in a list (`0,15-17,59`). A range whose start is after its end is `ErrRange`; a range with a missing or unreadable end (`1-`, `-5`, `1-2-3`) is `ErrSyntax`; ends outside the field are `ErrRange` like single numbers. A range of one value (`5-5`) is fine.",),
        code={
            "cronspec.go::part_bounds": '''
                a, b, found := strings.Cut(part, "-")
                if found {
                	x, err := parseNumber(a, sp)
                	if err != nil {
                		return nil, err
                	}
                	y, err := parseNumber(b, sp)
                	if err != nil {
                		return nil, err
                	}
                	if x > y {
                		return nil, fmt.Errorf("%w: %s: reversed range %q", ErrRange, sp.name, part)
                	}
                	lo, hi, isRange = x, y, true
                } else {
                	n, err := parseNumber(part, sp)
                	if err != nil {
                		return nil, err
                	}
                	lo, hi = n, n
                }
            ''',
        },
        readme="## Ranges\n\nParts of a field can be ranges `a-b` (inclusive) mixed with numbers (`0,15-17,59`). Reversed ranges are `ErrRange`; malformed ones (`1-`, `-5`, `1-2-3`) are `ErrSyntax`.\n",
        vtests='''
            func TestRangeBasic(t *testing.T) {
            	s := vMust(t, "0 9-17 * * *")
            	if !s.Matches(vT(2025, time.September, 1, 12, 0)) || s.Matches(vT(2025, time.September, 1, 18, 0)) {
            		t.Fatal("hour range")
            	}
            }
        ''',
        tests='''
            func TestRanges(t *testing.T) {
            	hMatches(t, "10-14 * * * *",
            		[]time.Time{hT(2025, time.September, 1, 5, 10), hT(2025, time.September, 1, 5, 12), hT(2025, time.September, 1, 5, 14)},
            		[]time.Time{hT(2025, time.September, 1, 5, 9), hT(2025, time.September, 1, 5, 15)})
            	hMatches(t, "0 9-17 * * *",
            		[]time.Time{hT(2025, time.September, 1, 9, 0), hT(2025, time.September, 1, 17, 0)},
            		[]time.Time{hT(2025, time.September, 1, 8, 0), hT(2025, time.September, 1, 18, 0)})
            	hMatches(t, "0 0 * * 1-5",
            		[]time.Time{hT(2025, time.September, 1, 0, 0), hT(2025, time.September, 5, 0, 0)},
            		[]time.Time{hT(2025, time.September, 6, 0, 0), hT(2025, time.September, 7, 0, 0)})
            	hMatches(t, "0,15-17,59 * * * *",
            		[]time.Time{hT(2025, time.September, 1, 5, 0), hT(2025, time.September, 1, 5, 15), hT(2025, time.September, 1, 5, 16), hT(2025, time.September, 1, 5, 17), hT(2025, time.September, 1, 5, 59)},
            		[]time.Time{hT(2025, time.September, 1, 5, 1), hT(2025, time.September, 1, 5, 14), hT(2025, time.September, 1, 5, 18)})
            	hMatches(t, "5-5 * * * *", []time.Time{hT(2025, time.September, 1, 5, 5)}, []time.Time{hT(2025, time.September, 1, 5, 6)})
            	hMatches(t, "0 0 28-31 2,12 *", []time.Time{hT(2025, time.February, 28, 0, 0), hT(2025, time.December, 31, 0, 0)}, []time.Time{hT(2025, time.December, 27, 0, 0), hT(2025, time.March, 30, 0, 0)})
            	hEq(t, "String keeps the text", hMust(t, "10-14 9-17 * * 1-5").String(), "10-14 9-17 * * 1-5")
            }

            func TestRangeErrors(t *testing.T) {
            	cases := []struct {
            		expr string
            		want error
            	}{
            		{"5-3 * * * *", ErrRange}, {"0-60 * * * *", ErrRange}, {"* 0-24 * * *", ErrRange}, {"* * 0-5 * *", ErrRange}, {"* * * * 5-7", ErrRange},
            		{"1- * * * *", ErrSyntax}, {"-5 * * * *", ErrSyntax}, {"1-2-3 * * * *", ErrSyntax}, {"a-b * * * *", ErrSyntax}, {"1-x * * * *", ErrSyntax},
            		{"1--2 * * * *", ErrSyntax}, {"1,2- * * * *", ErrSyntax}, {"* * * 12-1 *", ErrRange},
            	}
            	for _, c := range cases {
            		_, err := Parse(c.expr)
            		hIs(t, c.expr, err, c.want)
            	}
            }
        ''',
    ))

    S.append(Slice(
        id="steps", title="Steps", d=2,
        pitch=("Running something every five minutes means typing twelve numbers.",
               "Fields should support the `*/5` shorthand."),
        reqs=("A part of a field can have a step suffix `/n`. `*/n` means every n-th value of the field starting at its lowest value (`*/15` in the minute field is 0, 15, 30, 45; `*/10` in the day-of-month field is 1, 11, 21, 31). The step must be a number from 1 to the highest value of the field (`ErrRange` otherwise; unreadable steps such as `*/` or `*/x` are `ErrSyntax`). A step on anything that is not `*` or a range (`5/10`) is `ErrSyntax`. A bare `*` inside a list (`*,5`) stays an error.",),
        code={
            "cronspec.go::step_split": '''
                if i := strings.IndexByte(part, '/'); i >= 0 {
                	n, err := parseNumber(part[i+1:], fieldSpec{name: sp.name, lo: 1, hi: sp.hi})
                	if err != nil {
                		return nil, err
                	}
                	step, hasStep = n, true
                	part = part[:i]
                }
                star = part == "*" && hasStep
            ''',
        },
        readme="## Steps\n\n`*/n` runs every n-th value of the field starting at its lowest value (`*/15` in the minute field: 0, 15, 30, 45). The step is 1 to the field's highest value; steps on single numbers are `ErrSyntax`.\n",
        vtests='''
            func TestStepBasic(t *testing.T) {
            	s := vMust(t, "*/15 * * * *")
            	if !s.Matches(vT(2025, time.September, 1, 7, 45)) || s.Matches(vT(2025, time.September, 1, 7, 50)) {
            		t.Fatal("*/15")
            	}
            }
        ''',
        tests='''
            func TestSteps(t *testing.T) {
            	hMatches(t, "*/15 * * * *",
            		[]time.Time{hT(2025, time.September, 1, 5, 0), hT(2025, time.September, 1, 5, 15), hT(2025, time.September, 1, 5, 30), hT(2025, time.September, 1, 5, 45)},
            		[]time.Time{hT(2025, time.September, 1, 5, 1), hT(2025, time.September, 1, 5, 14), hT(2025, time.September, 1, 5, 59)})
            	hMatches(t, "0 */8 * * *",
            		[]time.Time{hT(2025, time.September, 1, 0, 0), hT(2025, time.September, 1, 8, 0), hT(2025, time.September, 1, 16, 0)},
            		[]time.Time{hT(2025, time.September, 1, 4, 0), hT(2025, time.September, 1, 23, 0)})
            	hMatches(t, "0 0 */10 * *",
            		[]time.Time{hT(2025, time.October, 1, 0, 0), hT(2025, time.October, 11, 0, 0), hT(2025, time.October, 21, 0, 0), hT(2025, time.October, 31, 0, 0)},
            		[]time.Time{hT(2025, time.October, 10, 0, 0), hT(2025, time.October, 20, 0, 0)})
            	hMatches(t, "0 0 1 */4 *",
            		[]time.Time{hT(2025, time.January, 1, 0, 0), hT(2025, time.May, 1, 0, 0), hT(2025, time.September, 1, 0, 0)},
            		[]time.Time{hT(2025, time.February, 1, 0, 0), hT(2025, time.December, 1, 0, 0)})
            	hMatches(t, "0 0 * * */2",
            		[]time.Time{hT(2025, time.September, 7, 0, 0), hT(2025, time.September, 2, 0, 0), hT(2025, time.September, 4, 0, 0), hT(2025, time.September, 6, 0, 0)},
            		[]time.Time{hT(2025, time.September, 1, 0, 0), hT(2025, time.September, 3, 0, 0), hT(2025, time.September, 5, 0, 0)})
            	hMatches(t, "*/20,5 * * * *",
            		[]time.Time{hT(2025, time.September, 1, 5, 0), hT(2025, time.September, 1, 5, 5), hT(2025, time.September, 1, 5, 40)},
            		[]time.Time{hT(2025, time.September, 1, 5, 10), hT(2025, time.September, 1, 5, 59)})
            	hMatches(t, "*/59 * * * *", []time.Time{hT(2025, time.September, 1, 5, 0), hT(2025, time.September, 1, 5, 59)}, []time.Time{hT(2025, time.September, 1, 5, 30)})
            	hMatches(t, "*/1 * * * *", []time.Time{hT(2025, time.September, 1, 5, 17)}, nil)
            }

            func TestStepErrors(t *testing.T) {
            	cases := []struct {
            		expr string
            		want error
            	}{
            		{"*/0 * * * *", ErrRange}, {"*/60 * * * *", ErrRange}, {"* */24 * * *", ErrRange}, {"* * */32 * *", ErrRange}, {"* * * * */7", ErrRange},
            		{"*/ * * * *", ErrSyntax}, {"*/x * * * *", ErrSyntax}, {"5/10 * * * *", ErrSyntax}, {"*/5/2 * * * *", ErrSyntax}, {"*,5 * * * *", ErrSyntax},
            		{"*/-5 * * * *", ErrSyntax}, {"/5 * * * *", ErrSyntax}, {"1,/5 * * * *", ErrSyntax},
            	}
            	for _, c := range cases {
            		_, err := Parse(c.expr)
            		hIs(t, c.expr, err, c.want)
            	}
            }
        ''',
        cross={
            "ranges": {
                "reqs": ("Steps also work on ranges: `a-b/n` means a, a+n, a+2n, ... up to b (`10-30/10` is 10, 20, 30). A reversed range with a step is `ErrRange` and `5-5/2` is just 5.",),
                "tests": '''
                    func TestSteppedRanges(t *testing.T) {
                    	hMatches(t, "10-30/10 * * * *",
                    		[]time.Time{hT(2025, time.September, 1, 5, 10), hT(2025, time.September, 1, 5, 20), hT(2025, time.September, 1, 5, 30)},
                    		[]time.Time{hT(2025, time.September, 1, 5, 0), hT(2025, time.September, 1, 5, 40), hT(2025, time.September, 1, 5, 15)})
                    	hMatches(t, "0-59/30 * * * *", []time.Time{hT(2025, time.September, 1, 5, 0), hT(2025, time.September, 1, 5, 30)}, []time.Time{hT(2025, time.September, 1, 5, 59)})
                    	hMatches(t, "0 0 * * 1-5/2",
                    		[]time.Time{hT(2025, time.September, 1, 0, 0), hT(2025, time.September, 3, 0, 0), hT(2025, time.September, 5, 0, 0)},
                    		[]time.Time{hT(2025, time.September, 2, 0, 0), hT(2025, time.September, 4, 0, 0)})
                    	hMatches(t, "5-5/2 * * * *", []time.Time{hT(2025, time.September, 1, 5, 5)}, []time.Time{hT(2025, time.September, 1, 5, 7)})
                    	hMatches(t, "1-10/4,50 * * * *", []time.Time{hT(2025, time.September, 1, 5, 1), hT(2025, time.September, 1, 5, 5), hT(2025, time.September, 1, 5, 9), hT(2025, time.September, 1, 5, 50)},
                    		[]time.Time{hT(2025, time.September, 1, 5, 13)})
                    	_, err := Parse("5-3/2 * * * *")
                    	hIs(t, "reversed", err, ErrRange)
                    	_, err = Parse("1-10/0 * * * *")
                    	hIs(t, "zero step", err, ErrRange)
                    	_, err = Parse("1-10/ * * * *")
                    	hIs(t, "empty step", err, ErrSyntax)
                    }
                '''},
        },
    ))

    S.append(Slice(
        id="names", title="Month and day names", d=2,
        pitch=("Nobody remembers whether 0 is Sunday or Monday, and `* * * * 1-5` needs a comment every time.",
               "Month and weekday fields should accept names."),
        reqs=("The month field accepts the names `JAN` to `DEC` (1 to 12) and the day-of-week field the names `SUN` to `SAT` (0 to 6), in upper or lower case or mixed, wherever a number is allowed (single values, list items, range ends). Names are not accepted in the other fields; an unknown name is `ErrSyntax`. `String()` keeps the text as written.",),
        code={
            "cronspec.go::spec_fields": "names map[string]int",
            "cronspec.go::types": '''
                var monthNames = map[string]int{"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}
                var dayNames = map[string]int{"SUN": 0, "MON": 1, "TUE": 2, "WED": 3, "THU": 4, "FRI": 5, "SAT": 6}
            ''',
            "cronspec.go::specs_extra": '''
                s[3].names = monthNames
                s[4].names = dayNames
            ''',
            "cronspec.go::number_names": '''
                if v, ok := sp.names[strings.ToUpper(s)]; ok {
                	return v, nil
                }
            ''',
        },
        readme="## Month and day names\n\nThe month field takes `JAN`-`DEC`, the day-of-week field `SUN`-`SAT` (any case) wherever numbers are allowed. Other fields reject names.\n",
        vtests='''
            func TestNamesBasic(t *testing.T) {
            	s := vMust(t, "0 0 * * sun")
            	if !s.Matches(vT(2025, time.September, 7, 0, 0)) {
            		t.Fatal("sun")
            	}
            }
        ''',
        tests='''
            func TestNames(t *testing.T) {
            	hMatches(t, "0 0 1 JAN,mar,Dec *",
            		[]time.Time{hT(2025, time.January, 1, 0, 0), hT(2025, time.March, 1, 0, 0), hT(2025, time.December, 1, 0, 0)},
            		[]time.Time{hT(2025, time.February, 1, 0, 0), hT(2025, time.December, 2, 0, 0)})
            	hMatches(t, "0 0 * * sun,WED",
            		[]time.Time{hT(2025, time.September, 7, 0, 0), hT(2025, time.September, 3, 0, 0)},
            		[]time.Time{hT(2025, time.September, 1, 0, 0), hT(2025, time.September, 6, 0, 0)})
            	hMatches(t, "0 0 * 1,feb *", []time.Time{hT(2025, time.January, 9, 0, 0), hT(2025, time.February, 9, 0, 0)}, []time.Time{hT(2025, time.March, 9, 0, 0)})
            	hMatches(t, "0 0 * * Sat", []time.Time{hT(2025, time.September, 6, 0, 0)}, []time.Time{hT(2025, time.September, 7, 0, 0)})
            	hMatches(t, "0 0 * dec *", []time.Time{hT(2025, time.December, 24, 0, 0)}, []time.Time{hT(2025, time.November, 24, 0, 0)})
            	hEq(t, "String keeps the text", hMust(t, "0 0 * Jan mon,FRI").String(), "0 0 * Jan mon,FRI")
            }

            func TestNameErrors(t *testing.T) {
            	for _, bad := range []string{"mon 0 * * *", "0 mon * * *", "0 0 mon * *", "0 0 * * jan", "0 0 * mon *", "0 0 * jann *", "0 0 * * mo", "0 0 * * sunday", "0 0 * * mon,", "0 0 * sun *"} {
            		_, err := Parse(bad)
            		hIs(t, bad, err, ErrSyntax)
            	}
            	if _, err := Parse("0 0 * * 6"); err != nil {
            		t.Errorf("numbers still work: %v", err)
            	}
            	_, err := Parse("0 0 * 13 *")
            	hIs(t, "numbers keep their range", err, ErrRange)
            }
        ''',
        cross={
            "ranges": {"tests": '''
                func TestNamedRanges(t *testing.T) {
                	hMatches(t, "0 0 * * MON-FRI",
                		[]time.Time{hT(2025, time.September, 1, 0, 0), hT(2025, time.September, 5, 0, 0)},
                		[]time.Time{hT(2025, time.September, 6, 0, 0), hT(2025, time.September, 7, 0, 0)})
                	hMatches(t, "0 0 1 jan-mar *", []time.Time{hT(2025, time.February, 1, 0, 0)}, []time.Time{hT(2025, time.April, 1, 0, 0)})
                	hMatches(t, "0 0 * * 1-fri,sun", []time.Time{hT(2025, time.September, 3, 0, 0), hT(2025, time.September, 7, 0, 0)}, []time.Time{hT(2025, time.September, 6, 0, 0)})
                	_, err := Parse("0 0 * * FRI-MON")
                	hIs(t, "reversed names", err, ErrRange)
                	_, err = Parse("0 0 * * MON-xyz")
                	hIs(t, "unknown end", err, ErrSyntax)
                }
            '''},
        },
    ))

    S.append(Slice(
        id="zone", title="Schedules in a fixed UTC offset", d=2,
        pitch=("The nightly report is meant for 03:00 in Mumbai, but the scheduler server thinks in UTC.",
               "A schedule should be able to run in the time zone of the team that owns it."),
        reqs=("`schedule.WithOffset(minutes int) (*Schedule, error)` returns a copy of the schedule that is bound to a fixed UTC offset (in minutes, from -840 to 840, otherwise `ErrRange`; the original is not changed). A bound schedule converts every `t` it is given into that offset before looking at its fields, so `30 9 * * *` bound to 330 (UTC+05:30) matches 04:00 UTC. `schedule.Offset() (minutes int, bound bool)` tells whether and how a schedule is bound.",
              "An unbound schedule keeps taking the fields of `t` in its own location, as before."),
        code={
            "cronspec.go::schedule_fields": '''
                loc    *time.Location
                offset int
            ''',
            "cronspec.go::matches_pre": '''
                if s.loc != nil {
                	t = t.In(s.loc)
                }
            ''',
            "cronspec.go::methods": '''
                // WithOffset returns a copy bound to a fixed UTC offset in minutes.
                func (s *Schedule) WithOffset(minutes int) (*Schedule, error) {
                	if minutes < -840 || minutes > 840 {
                		return nil, fmt.Errorf("%w: offset %d minutes", ErrRange, minutes)
                	}
                	c := *s
                	c.loc = time.FixedZone(fmt.Sprintf("UTC%+d", minutes), minutes*60)
                	c.offset = minutes
                	return &c, nil
                }

                // Offset reports the bound offset in minutes, if any.
                func (s *Schedule) Offset() (int, bool) { return s.offset, s.loc != nil }
            ''',
        },
        readme="## Schedules in a fixed UTC offset\n\n`WithOffset(minutes)` returns a copy bound to a fixed offset (-840 to 840); a bound schedule looks at the fields of `t` in that offset. `Offset()` reports it. Unbound schedules use the location of `t`.\n",
        vtests='''
            func TestZoneBasic(t *testing.T) {
            	s, err := vMust(t, "30 9 * * *").WithOffset(330)
            	if err != nil || !s.Matches(vT(2025, time.September, 1, 4, 0)) {
            		t.Fatalf("%v", err)
            	}
            }
        ''',
        tests='''
            func TestZone(t *testing.T) {
            	base := hMust(t, "30 9 * * *")
            	ist, err := base.WithOffset(330)
            	if err != nil {
            		t.Fatal(err)
            	}
            	if !ist.Matches(hT(2025, time.September, 1, 4, 0)) || ist.Matches(hT(2025, time.September, 1, 9, 30)) {
            		t.Error("bound schedule must look at UTC+05:30")
            	}
            	if !base.Matches(hT(2025, time.September, 1, 9, 30)) || base.Matches(hT(2025, time.September, 1, 4, 0)) {
            		t.Error("the original must not change")
            	}
            	if m, ok := ist.Offset(); m != 330 || !ok {
            		t.Errorf("Offset: %d %v", m, ok)
            	}
            	if m, ok := base.Offset(); m != 0 || ok {
            		t.Errorf("unbound Offset: %d %v", m, ok)
            	}
            	hEq(t, "String", ist.String(), "30 9 * * *")
            	west, _ := hMust(t, "0 8 1 * *").WithOffset(-300)
            	if !west.Matches(hT(2025, time.September, 1, 13, 0)) || west.Matches(hT(2025, time.September, 1, 8, 0)) {
            		t.Error("negative offset")
            	}
            	other := time.FixedZone("x", 3*3600)
            	if !ist.Matches(time.Date(2025, time.September, 1, 7, 0, 0, 0, other)) {
            		t.Error("the location of t does not matter for a bound schedule")
            	}
            	rebound, _ := ist.WithOffset(0)
            	if !rebound.Matches(hT(2025, time.September, 1, 9, 30)) {
            		t.Error("a bound schedule can be bound again")
            	}
            	if m, _ := ist.Offset(); m != 330 {
            		t.Error("rebinding changed the first copy")
            	}
            	day, _ := hMust(t, "0 0 2 9 *").WithOffset(600)
            	if !day.Matches(hT(2025, time.September, 1, 14, 0)) {
            		t.Error("the day is taken in the offset too")
            	}
            }

            func TestZoneRange(t *testing.T) {
            	s := hMust(t, "* * * * *")
            	for _, bad := range []int{841, -841, 10000} {
            		_, err := s.WithOffset(bad)
            		hIs(t, "offset", err, ErrRange)
            	}
            	for _, ok := range []int{840, -840, 0, 45} {
            		if _, err := s.WithOffset(ok); err != nil {
            			t.Errorf("%d: %v", ok, err)
            		}
            	}
            }
        ''',
    ))

    S.append(Slice(
        id="last-day", title="Last day of the month", d=3,
        pitch=("Month-end reports can't be scheduled because months have different lengths.",
               "Schedules need a way to say \"the last day of the month\"."),
        reqs=("In the day-of-month field the letter `L` (upper case only) stands for the last day of the month (28, 29, 30 or 31 depending on the month and the year); it can be mixed with numbers in a list (`1,L`). `L` is not accepted in any other field and not as a range end or with a step (`ErrSyntax`).",
              "A field with `L` counts as restricted for the day rule: with a restricted day-of-week field a day matches if it is the last day of the month **or** the weekday matches."),
        code={
            "cronspec.go::field_fields": "last bool",
            "cronspec.go::part_pre": '''
                if sp.name == "day of month" && part == "L" {
                	f.last = true
                	continue
                }
            ''',
            "cronspec.go::dom_extra": '''
                if s.dom.last && t.Day() == time.Date(t.Year(), t.Month()+1, 0, 0, 0, 0, 0, time.UTC).Day() {
                	domOK = true
                }
            ''',
        },
        readme="## Last day of the month\n\nThe day-of-month field accepts `L` (upper case) for the last day of the month, also in lists (`1,L`). A field with `L` is restricted for the day rule (OR with a restricted weekday field).\n",
        vtests='''
            func TestLastDayBasic(t *testing.T) {
            	s := vMust(t, "0 0 L * *")
            	if !s.Matches(vT(2025, time.February, 28, 0, 0)) || s.Matches(vT(2025, time.February, 27, 0, 0)) {
            		t.Fatal("L")
            	}
            }
        ''',
        tests='''
            func TestLastDay(t *testing.T) {
            	hMatches(t, "0 0 L * *",
            		[]time.Time{hT(2025, time.February, 28, 0, 0), hT(2024, time.February, 29, 0, 0), hT(2025, time.April, 30, 0, 0), hT(2025, time.December, 31, 0, 0), hT(2100, time.February, 28, 0, 0)},
            		[]time.Time{hT(2025, time.February, 27, 0, 0), hT(2024, time.February, 28, 0, 0), hT(2025, time.April, 29, 0, 0), hT(2025, time.December, 30, 0, 0), hT(2025, time.January, 30, 0, 0)})
            	hMatches(t, "0 0 1,L * *",
            		[]time.Time{hT(2025, time.September, 1, 0, 0), hT(2025, time.September, 30, 0, 0)},
            		[]time.Time{hT(2025, time.September, 15, 0, 0), hT(2025, time.September, 29, 0, 0)})
            	hMatches(t, "0 0 L 2 *", []time.Time{hT(2025, time.February, 28, 0, 0)}, []time.Time{hT(2025, time.March, 31, 0, 0)})
            	// the day rule: the last day or a Monday (2025-09-30 is a Tuesday, the 8th a Monday)
            	hMatches(t, "0 0 L * 1",
            		[]time.Time{hT(2025, time.September, 30, 0, 0), hT(2025, time.September, 8, 0, 0)},
            		[]time.Time{hT(2025, time.September, 9, 0, 0), hT(2025, time.September, 8, 1, 0)})
            	hEq(t, "String", hMust(t, "0 0 L * *").String(), "0 0 L * *")
            }

            func TestLastDayErrors(t *testing.T) {
            	for _, bad := range []string{"L * * * *", "0 L * * *", "0 0 * L *", "0 0 * * L", "0 0 l * *", "0 0 L-5 * *", "0 0 5-L * *", "0 0 LL * *", "0 0 L/2 * *", "0 0 1,,L * *"} {
            		_, err := Parse(bad)
            		if err == nil {
            			t.Errorf("%q accepted", bad)
            		}
            	}
            }
        ''',
    ))

    S.append(Slice(
        id="next", title="Next run", d=3,
        pitch=("The scheduler wakes up every minute and asks whether anything matches, instead of sleeping until the next run.",
               "The scheduler needs to know when a job runs next."),
        reqs=(f"`schedule.Next(after time.Time) (time.Time, bool)` returns the first matching minute strictly after `after` (seconds and below of `after` do not matter: the answer for 10:07:59 is the same as for 10:07:00). The result is a whole minute in the location of `after`, and `Matches` is true for it. When there is no matching minute within the next {horizon} years (counted from `after`), the result is the zero time and `false` (for example `0 0 31 2 *`).",),
        code={
            "cronspec.go::methods": f'''
                // Next returns the first matching minute strictly after the given time.
                func (s *Schedule) Next(after time.Time) (time.Time, bool) {{
                	loc := after.Location()
                	@@slot next_loc
                	after = after.In(loc)
                	t := time.Date(after.Year(), after.Month(), after.Day(), after.Hour(), after.Minute()+1, 0, 0, loc)
                	limit := after.AddDate({horizon}, 0, 0)
                	for t.Before(limit) {{
                		if !s.month.matches(int(t.Month())) || !s.dayMatches(t) {{
                			t = time.Date(t.Year(), t.Month(), t.Day()+1, 0, 0, 0, 0, loc)
                			continue
                		}}
                		if !s.hour.matches(t.Hour()) {{
                			t = time.Date(t.Year(), t.Month(), t.Day(), t.Hour()+1, 0, 0, 0, loc)
                			continue
                		}}
                		if !s.minute.matches(t.Minute()) {{
                			t = t.Add(time.Minute)
                			continue
                		}}
                		return t, true
                	}}
                	return time.Time{{}}, false
                }}
            ''',
        },
        readme=f"## Next run\n\n`schedule.Next(after)` returns the first matching minute strictly after `after` (in the location of `after`) and `true`, or the zero time and `false` when nothing matches within {horizon} years.\n",
        vtests='''
            func TestNextBasic(t *testing.T) {
            	got, ok := vMust(t, "0,30 * * * *").Next(vT(2025, time.September, 1, 10, 7))
            	if !ok || !got.Equal(vT(2025, time.September, 1, 10, 30)) {
            		t.Fatalf("%v %v", got, ok)
            	}
            }
        ''',
        tests=fmt('''
            func hNext(t *testing.T, expr string, from, want time.Time) {
            	t.Helper()
            	got, ok := hMust(t, expr).Next(from)
            	if !ok || !got.Equal(want) {
            		t.Errorf("%q after %v: got %v %v, want %v", expr, from, got, ok, want)
            		return
            	}
            	if !hMust(t, expr).Matches(got) {
            		t.Errorf("%q: the result %v does not match", expr, got)
            	}
            }

            func TestNext(t *testing.T) {
            	hNext(t, "0,15,30,45 * * * *", hT(2025, time.September, 1, 10, 7), hT(2025, time.September, 1, 10, 15))
            	hNext(t, "0,15,30,45 * * * *", hT(2025, time.September, 1, 10, 15), hT(2025, time.September, 1, 10, 30))
            	hNext(t, "0,15,30,45 * * * *", hT(2025, time.September, 1, 10, 59), hT(2025, time.September, 1, 11, 0))
            	hNext(t, "0,15,30,45 * * * *", time.Date(2025, time.September, 1, 10, 7, 45, 123, time.UTC), hT(2025, time.September, 1, 10, 15))
            	hNext(t, "0,15,30,45 * * * *", time.Date(2025, time.September, 1, 10, 15, 59, 0, time.UTC), hT(2025, time.September, 1, 10, 30))
            	hNext(t, "0 0 * * *", hT(2025, time.September, 1, 0, 0), hT(2025, time.September, 2, 0, 0))
            	hNext(t, "0 0 * * *", hT(2025, time.September, 30, 23, 59), hT(2025, time.October, 1, 0, 0))
            	hNext(t, "0 0 1 1 *", hT(2025, time.January, 1, 0, 0), hT(2026, time.January, 1, 0, 0))
            	hNext(t, "59 23 31 12 *", hT(2025, time.December, 31, 23, 59), hT(2026, time.December, 31, 23, 59))
            	hNext(t, "30 2 29 2 *", hT(2025, time.March, 1, 0, 0), hT(2028, time.February, 29, 2, 30))
            	hNext(t, "0 12 * 6 *", hT(2025, time.July, 1, 0, 0), hT(2026, time.June, 1, 12, 0))
            	hNext(t, "* * * * *", hT(2025, time.December, 31, 23, 59), hT(2026, time.January, 1, 0, 0))
            	hNext(t, "5 4 * * 0", hT(2025, time.September, 1, 0, 0), hT(2025, time.September, 7, 4, 5))
            }

            func TestNextDayRule(t *testing.T) {
            	hNext(t, "0 0 15 * 1", hT(2025, time.September, 2, 0, 0), hT(2025, time.September, 8, 0, 0))
            	hNext(t, "0 0 15 * 1", hT(2025, time.September, 8, 0, 0), hT(2025, time.September, 15, 0, 0))
            	hNext(t, "0 0 15 * 1", hT(2025, time.September, 15, 0, 0), hT(2025, time.September, 22, 0, 0))
            	hNext(t, "0 0 15 * 1", hT(2025, time.September, 29, 0, 0), hT(2025, time.October, 6, 0, 0))
            	hNext(t, "0 0 13 * 5", hT(2025, time.January, 1, 0, 0), hT(2025, time.January, 3, 0, 0))
            }

            func TestNextNeverAndLocation(t *testing.T) {
            	for _, expr := range []string{"0 0 31 2 *", "0 0 31 4 *", "0 0 30 2 *"} {
            		got, ok := hMust(t, expr).Next(hT(2025, time.January, 1, 0, 0))
            		if ok || !got.IsZero() {
            			t.Errorf("%q: got %v %v", expr, got, ok)
            		}
            	}
            	if _, ok := hMust(t, "0 0 29 2 *").Next(hT(2096, time.March, 1, 0, 0)); ok {
            		t.Error("the next leap day after 2096 is eight years away")
            	}
            	plus2 := time.FixedZone("plus2", 2*3600)
            	from := time.Date(2025, time.September, 1, 10, 7, 0, 0, plus2)
            	got, ok := hMust(t, "0 12 * * *").Next(from)
            	if !ok || !got.Equal(time.Date(2025, time.September, 1, 12, 0, 0, 0, plus2)) {
            		t.Errorf("fixed zone: %v %v", got, ok)
            	}
            	if _, off := got.Zone(); off != 2*3600 {
            		t.Errorf("the result must be in the location of the argument, got offset %d", off)
            	}
            	same, _ := hMust(t, "0 12 * * *").Next(time.Date(2025, time.September, 1, 10, 7, 59, 0, plus2))
            	if !same.Equal(got) {
            		t.Error("seconds must not matter")
            	}
            }
        '''),
        cross={
            "last-day": {"tests": '''
                func TestNextLastDay(t *testing.T) {
                	hNext(t, "0 0 L * *", hT(2025, time.February, 10, 0, 0), hT(2025, time.February, 28, 0, 0))
                	hNext(t, "0 0 L * *", hT(2024, time.February, 10, 0, 0), hT(2024, time.February, 29, 0, 0))
                	hNext(t, "0 0 L * *", hT(2025, time.February, 28, 0, 0), hT(2025, time.March, 31, 0, 0))
                	hNext(t, "30 6 L 4,6 *", hT(2025, time.May, 1, 0, 0), hT(2025, time.June, 30, 6, 30))
                	hNext(t, "0 0 L * 1", hT(2025, time.September, 24, 0, 0), hT(2025, time.September, 29, 0, 0))
                	hNext(t, "0 0 L * 1", hT(2025, time.September, 29, 0, 0), hT(2025, time.September, 30, 0, 0))
                }
            '''},
            "zone": {
                "reqs": ("For a schedule bound with `WithOffset`, `Next` works in that offset: the result is in the schedule's offset, whatever location `after` has.",),
                "code": {"cronspec.go::next_loc": '''
                    if s.loc != nil {
                    	loc = s.loc
                    }
                '''},
                "tests": '''
                    func TestNextInAnOffset(t *testing.T) {
                    	s, _ := hMust(t, "30 9 * * *").WithOffset(330)
                    	got, ok := s.Next(hT(2025, time.September, 1, 0, 0))
                    	if !ok || !got.Equal(hT(2025, time.September, 1, 4, 0)) {
                    		t.Fatalf("got %v %v", got, ok)
                    	}
                    	if _, off := got.Zone(); off != 330*60 {
                    		t.Errorf("offset %d", off)
                    	}
                    	got, _ = s.Next(hT(2025, time.September, 1, 4, 0))
                    	if !got.Equal(hT(2025, time.September, 2, 4, 0)) {
                    		t.Errorf("next day: %v", got)
                    	}
                    	west, _ := hMust(t, "0 22 * * *").WithOffset(-120)
                    	got, _ = west.Next(time.Date(2025, time.September, 1, 23, 30, 0, 0, time.FixedZone("far", 9*3600)))
                    	if !got.Equal(hT(2025, time.September, 2, 0, 0)) {
                    		t.Errorf("west: %v", got)
                    	}
                    }
                '''},
            "steps": {"tests": '''
                func TestNextWithSteps(t *testing.T) {
                	hNext(t, "*/20 */8 * * *", hT(2025, time.September, 1, 0, 40), hT(2025, time.September, 1, 8, 0))
                	hNext(t, "*/20 */8 * * *", hT(2025, time.September, 1, 16, 40), hT(2025, time.September, 2, 0, 0))
                }
            '''},
        },
    ))

    S.append(Slice(
        id="between", title="Runs in a window", d=3, needs=("next",),
        pitch=("The calendar view wants to draw every run of a job during the coming week.",
               "Callers want all the runs inside a time window, not just the next one."),
        reqs=("`schedule.Between(after, until time.Time, max int) ([]time.Time, error)` returns the matching minutes `t` with `after < t <= until` in ascending order (the same \"strictly after\" rule as `Next`; a result is only included when it is not after `until`), at most `max` of them. `max` must be at least 1, otherwise `ErrRange`. A window without runs, or with `until` not after `after`, gives an empty (non-nil) slice.",),
        code={
            "cronspec.go::methods": '''
                // Between lists the runs in (after, until], at most max of them.
                func (s *Schedule) Between(after, until time.Time, max int) ([]time.Time, error) {
                	if max < 1 {
                		return nil, fmt.Errorf("%w: max must be at least 1", ErrRange)
                	}
                	out := []time.Time{}
                	cur := after
                	for len(out) < max {
                		n, ok := s.Next(cur)
                		if !ok || n.After(until) {
                			break
                		}
                		out = append(out, n)
                		cur = n
                	}
                	return out, nil
                }
            ''',
        },
        readme="## Runs in a window\n\n`schedule.Between(after, until, max)` lists the runs `t` with `after < t <= until`, at most `max` (`ErrRange` for `max < 1`), ascending; empty (non-nil) when there are none.\n",
        vtests='''
            func TestBetweenBasic(t *testing.T) {
            	got, err := vMust(t, "0 0,12 * * *").Between(vT(2025, time.September, 1, 0, 0), vT(2025, time.September, 3, 0, 0), 10)
            	if err != nil || len(got) != 4 {
            		t.Fatalf("%v %v", got, err)
            	}
            }
        ''',
        tests='''
            func hTimes(ts []time.Time) []string {
            	out := []string{}
            	for _, t := range ts {
            		out = append(out, t.Format("2006-01-02T15:04"))
            	}
            	return out
            }

            func TestBetween(t *testing.T) {
            	s := hMust(t, "0 0,6,12,18 * * *")
            	got, err := s.Between(hT(2025, time.September, 1, 0, 0), hT(2025, time.September, 2, 0, 0), 100)
            	if err != nil {
            		t.Fatal(err)
            	}
            	hEq(t, "a day", hTimes(got), []string{"2025-09-01T06:00", "2025-09-01T12:00", "2025-09-01T18:00", "2025-09-02T00:00"})
            	got, _ = s.Between(hT(2025, time.September, 1, 0, 0), hT(2025, time.September, 2, 0, 0), 2)
            	hEq(t, "max", hTimes(got), []string{"2025-09-01T06:00", "2025-09-01T12:00"})
            	got, _ = s.Between(hT(2025, time.September, 1, 5, 59), hT(2025, time.September, 1, 6, 0), 5)
            	hEq(t, "the end is included", hTimes(got), []string{"2025-09-01T06:00"})
            	got, _ = s.Between(hT(2025, time.September, 1, 6, 0), hT(2025, time.September, 1, 11, 59), 5)
            	if got == nil || len(got) != 0 {
            		t.Errorf("no runs: %#v", got)
            	}
            	got, _ = s.Between(hT(2025, time.September, 2, 0, 0), hT(2025, time.September, 1, 0, 0), 5)
            	if got == nil || len(got) != 0 {
            		t.Errorf("reversed window: %#v", got)
            	}
            	got, _ = hMust(t, "0 0 31 2 *").Between(hT(2025, time.January, 1, 0, 0), hT(2030, time.January, 1, 0, 0), 5)
            	if got == nil || len(got) != 0 {
            		t.Errorf("never: %#v", got)
            	}
            	got, _ = hMust(t, "0 0 1 * *").Between(hT(2025, time.January, 1, 0, 0), hT(2026, time.January, 1, 0, 0), 100)
            	hEq(t, "monthly", len(got), 12)
            	hEq(t, "monthly first", hTimes(got)[0], "2025-02-01T00:00")
            }

            func TestBetweenValidation(t *testing.T) {
            	s := hMust(t, "* * * * *")
            	for _, bad := range []int{0, -1} {
            		_, err := s.Between(hT(2025, time.September, 1, 0, 0), hT(2025, time.September, 2, 0, 0), bad)
            		hIs(t, "max", err, ErrRange)
            	}
            	got, err := s.Between(hT(2025, time.September, 1, 0, 0), hT(2025, time.September, 1, 0, 10), 1000)
            	if err != nil || len(got) != 10 {
            		t.Errorf("every minute: %d %v", len(got), err)
            	}
            }
        ''',
    ))

    return S


APP = App(
    name="cronspec", lang="go", title="the cron expression library", role="a job scheduler developer", key="CRON",
    base={
        "README.md": README + "\n@@blocks features\n",
        "go.mod": langs.go_mod("cronspec"),
        "cronspec.go": CRON,
        ".gitignore": "*.test\n",
    },
    visible={"cron_test.go": VISIBLE},
    hidden={"features_test.go": HIDDEN},
)

register_app("feature-go-cronspec", APP, make_slices, n=18, summary="cron expressions: aliases, ranges, steps, names, UTC offsets, last day, next run, windows")
