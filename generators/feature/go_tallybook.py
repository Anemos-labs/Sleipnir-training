"""tallybook (go): a double-entry ledger extended with as-of balances, tags, reversals, period close, budgets, journal import, currencies."""
import json
import random

from fx import dd, langs
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # tallybook

    A small double-entry ledger for a club treasurer (Go, standard library only). `go test ./...` runs the tests.

    ## Layout

    * `book.go`: `Book`, `Account`s, `Entry`, `Line`.
    * `book_test.go`: tests.

    ## Basics

    Money is whole cents (`int64`). Days are whole numbers from 0. Errors are package variables; they are returned
    wrapped (`fmt.Errorf("%w: ...")`), so callers use `errors.Is`.

    * `New()` makes an empty book. `Open(name, kind) error` creates an account. A name is trimmed and must look like
      `assets:cash`: lower-case words (letters, digits and dashes, starting with a letter) joined by colons
      (`ErrBadName`); the kind is one of `Asset`, `Liability`, `Income`, `Expense` (`ErrBadKind`); a name that exists is
      `ErrDuplicate`. `Accounts()` lists the names in alphabetical order.
    * `Post(day, memo, lines...) (int, error)` records an entry and returns its id (1, 2, 3, ... in order). A `Line` is
      `{Account string, Cents int64}`: positive cents debit the account, negative cents credit it. The checks run in this
      order and a failed call records nothing: a negative day (`ErrBadDay`); fewer than two lines (`ErrTooFew`); for each
      line in order an unknown account (`ErrUnknownAccount`) and then zero cents (`ErrBadAmount`); lines that do not add
      up to zero (`ErrUnbalanced`). The memo is trimmed.
    * `Balance(name) (int64, error)` is the sum of all lines of the account (debits minus credits;
      `ErrUnknownAccount` for an unknown name).
    * `Entries() []Entry` returns copies of all entries in id order (`ID`, `Day`, `Memo`, `Lines`); changing them does
      not change the book.
    * `Report() string` has one line per account in alphabetical order: the name left-aligned in 24 characters, a space,
      and the balance as `-12.34` right-aligned in 10 characters, each line ending in a newline.
''')

BOOK = '''\
// Package tallybook is a small double-entry ledger.
package tallybook

import (
	"errors"
	"fmt"
	"regexp"
	"sort"
	"strings"
@@uniq imports
)

// Kind classifies an account.
type Kind int

const (
	Asset Kind = iota
	Liability
	Income
	Expense
)

var (
	ErrBadName        = errors.New("tallybook: bad account name")
	ErrBadKind        = errors.New("tallybook: bad account kind")
	ErrDuplicate      = errors.New("tallybook: account already exists")
	ErrUnknownAccount = errors.New("tallybook: unknown account")
	ErrBadDay         = errors.New("tallybook: bad day")
	ErrTooFew         = errors.New("tallybook: an entry needs at least two lines")
	ErrBadAmount      = errors.New("tallybook: a line needs a non-zero amount")
	ErrUnbalanced     = errors.New("tallybook: the entry does not balance")
	@@slot errors
)

var nameRE = regexp.MustCompile(`^[a-z][a-z0-9-]*(:[a-z][a-z0-9-]*)*$`)

// Line is one side of an entry: positive cents debit the account, negative cents credit it.
type Line struct {
	Account string
	Cents   int64
	@@slot line_fields
}

// Entry is a recorded transaction.
type Entry struct {
	ID    int
	Day   int
	Memo  string
	Lines []Line
	@@slot entry_fields
}

@@blocks types

type account struct {
	name string
	kind Kind
	@@slot account_fields
}

// Book holds the accounts and the entries.
type Book struct {
	accounts map[string]*account
	entries  []Entry
	@@slot book_fields
}

// New returns an empty book.
func New() *Book {
	b := &Book{accounts: map[string]*account{}}
	@@slot new_book
	return b
}

// Open creates an account.
func (b *Book) Open(name string, kind Kind) error {
	name = strings.TrimSpace(name)
	if !nameRE.MatchString(name) {
		return fmt.Errorf("%w: %q", ErrBadName, name)
	}
	if kind < Asset || kind > Expense {
		return fmt.Errorf("%w: %d", ErrBadKind, int(kind))
	}
	if _, ok := b.accounts[name]; ok {
		return fmt.Errorf("%w: %s", ErrDuplicate, name)
	}
	b.accounts[name] = &account{name: name, kind: kind}
	@@slot on_open
	return nil
}

// Accounts lists the account names in alphabetical order.
func (b *Book) Accounts() []string {
	names := make([]string, 0, len(b.accounts))
	for n := range b.accounts {
		names = append(names, n)
	}
	sort.Strings(names)
	return names
}

// Post records an entry and returns its id.
func (b *Book) Post(day int, memo string, lines ...Line) (int, error) {
	if day < 0 {
		return 0, fmt.Errorf("%w: %d", ErrBadDay, day)
	}
	@@slot post_pre
	if len(lines) < 2 {
		return 0, ErrTooFew
	}
	var sum int64
	@@slot post_vars
	for _, l := range lines {
		if _, ok := b.accounts[l.Account]; !ok {
			return 0, fmt.Errorf("%w: %q", ErrUnknownAccount, l.Account)
		}
		if l.Cents == 0 {
			return 0, ErrBadAmount
		}
		@@slot line_checks
		sum += l.Cents
	}
	@@default balance_check
	if sum != 0 {
		return 0, ErrUnbalanced
	}
	@@end
	@@slot post_checks
	e := Entry{ID: len(b.entries) + 1, Day: day, Memo: strings.TrimSpace(memo), Lines: append([]Line(nil), lines...)}
	@@slot entry_init
	b.entries = append(b.entries, e)
	@@slot on_post
	return e.ID, nil
}

// Balance is the sum of all lines of the account.
func (b *Book) Balance(name string) (int64, error) {
	if _, ok := b.accounts[name]; !ok {
		return 0, fmt.Errorf("%w: %q", ErrUnknownAccount, name)
	}
	var sum int64
	for _, e := range b.entries {
		for _, l := range e.Lines {
			if l.Account == name {
				sum += l.Cents
			}
		}
	}
	return sum, nil
}

// Entries returns copies of all entries.
func (b *Book) Entries() []Entry {
	out := make([]Entry, len(b.entries))
	for i, e := range b.entries {
		e.Lines = append([]Line(nil), e.Lines...)
		out[i] = e
	}
	return out
}

func money(c int64) string {
	sign := ""
	if c < 0 {
		sign = "-"
		c = -c
	}
	return fmt.Sprintf("%s%d.%02d", sign, c/100, c%100)
}

// Report is the balance of every account, one line each.
func (b *Book) Report() string {
	var sb strings.Builder
	for _, n := range b.Accounts() {
		bal, _ := b.Balance(n)
		@@default report_line
		sb.WriteString(fmt.Sprintf("%-24s %10s\\n", n, money(bal)))
		@@end
	}
	return sb.String()
}

@@blocks methods
'''

TEST_HELPERS = '''\
var _ = strings.ToUpper
var _ = fmt.Sprint
var _ = reflect.DeepEqual
var _ = errors.Is

func __P__Ln(acct string, cents int64) Line { return Line{Account: acct, Cents: cents} }

func __P__Post(b *Book, day int, memo string, lines ...Line) int {
	id, err := b.Post(day, memo, lines...)
	if err != nil {
		panic(err)
	}
	return id
}

// __P__Book: a small club ledger. Balances: bank 600.00, cash 235.50, food 14.50, rent 400.00, sales -250.00, loan -1000.00.
func __P__Book() *Book {
	b := New()
	for _, a := range []struct {
		name string
		kind Kind
	}{{"assets:cash", Asset}, {"assets:bank", Asset}, {"liabilities:loan", Liability}, {"income:sales", Income}, {"expenses:rent", Expense}, {"expenses:food", Expense}} {
		if err := b.Open(a.name, a.kind); err != nil {
			panic(err)
		}
	}
	__P__Post(b, 1, "Opening loan", __P__Ln("assets:bank", 100000), __P__Ln("liabilities:loan", -100000))
	__P__Post(b, 2, "Sale", __P__Ln("assets:cash", 25000), __P__Ln("income:sales", -25000))
	__P__Post(b, 3, "Rent", __P__Ln("expenses:rent", 40000), __P__Ln("assets:bank", -40000))
	__P__Post(b, 5, "Groceries", __P__Ln("expenses:food", 1450), __P__Ln("assets:cash", -1450))
	return b
}

func __P__IDs(es []Entry) []int {
	out := []int{}
	for _, e := range es {
		out = append(out, e.ID)
	}
	return out
}
'''

VISIBLE = '''\
package tallybook

import (
	"errors"
	"fmt"
	"reflect"
	"strings"
	"testing"
@@uniq imports
)

''' + TEST_HELPERS.replace("__P__", "v") + '''
func TestOpenAndPost(t *testing.T) {
	b := vBook()
	if err := b.Open("assets:cash", Asset); !errors.Is(err, ErrDuplicate) {
		t.Fatalf("duplicate: %v", err)
	}
	if err := b.Open("Cash", Asset); !errors.Is(err, ErrBadName) {
		t.Fatalf("bad name: %v", err)
	}
	if _, err := b.Post(1, "x", vLn("assets:cash", 5)); !errors.Is(err, ErrTooFew) {
		t.Fatalf("one line: %v", err)
	}
	if _, err := b.Post(1, "x", vLn("assets:cash", 5), vLn("income:sales", -4)); !errors.Is(err, ErrUnbalanced) {
		t.Fatalf("unbalanced: %v", err)
	}
	if id := vPost(b, 6, "  Tea  ", vLn("expenses:food", 300), vLn("assets:cash", -300)); id != 5 {
		t.Fatalf("id %d", id)
	}
	if es := b.Entries(); len(es) != 5 || es[4].Memo != "Tea" {
		t.Fatalf("entries %+v", es)
	}
}

func TestBalancesAndReport(t *testing.T) {
	b := vBook()
	if bal, err := b.Balance("assets:bank"); err != nil || bal != 60000 {
		t.Fatalf("bank %d %v", bal, err)
	}
	if _, err := b.Balance("nope"); !errors.Is(err, ErrUnknownAccount) {
		t.Fatalf("unknown: %v", err)
	}
	lines := strings.Split(b.Report(), "\\n")
	if !strings.HasPrefix(lines[0], "assets:bank") || !strings.HasSuffix(lines[0], "  600.00") || !strings.HasSuffix(lines[5], " -1000.00") {
		t.Fatalf("report: %q", lines)
	}
	if !reflect.DeepEqual(b.Accounts()[:2], []string{"assets:bank", "assets:cash"}) {
		t.Fatalf("accounts %v", b.Accounts())
	}
}
@@blocks tests
'''

HIDDEN = '''\
package tallybook

import (
	"errors"
	"fmt"
	"reflect"
	"strings"
	"testing"
@@uniq imports
)

''' + TEST_HELPERS.replace("__P__", "h") + '''
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

func TestBaseOpen(t *testing.T) {
	b := New()
	for _, bad := range []string{"", "  ", "Cash", "assets:", ":x", "a b", "1abc", "assets::cash", "a_b", "assets:Cash"} {
		hIs(t, "name "+bad, b.Open(bad, Asset), ErrBadName)
	}
	hIs(t, "kind", b.Open("assets:cash", Kind(9)), ErrBadKind)
	hIs(t, "negative kind", b.Open("assets:cash", Kind(-1)), ErrBadKind)
	hEq(t, "nothing opened", b.Accounts(), []string{})
	if err := b.Open("  assets:petty-cash ", Asset); err != nil {
		t.Fatal(err)
	}
	if err := b.Open("expenses:food2", Expense); err != nil {
		t.Fatal(err)
	}
	hIs(t, "duplicate", b.Open("assets:petty-cash", Liability), ErrDuplicate)
	hEq(t, "accounts", b.Accounts(), []string{"assets:petty-cash", "expenses:food2"})
}

func TestBasePost(t *testing.T) {
	b := hBook()
	n := len(b.Entries())
	_, err := b.Post(-1, "x")
	hIs(t, "negative day comes first", err, ErrBadDay)
	_, err = b.Post(1, "x")
	hIs(t, "no lines", err, ErrTooFew)
	_, err = b.Post(1, "x", hLn("assets:cash", 5))
	hIs(t, "one line", err, ErrTooFew)
	_, err = b.Post(1, "x", hLn("assets:cash", 5), hLn("nope", -5))
	hIs(t, "unknown", err, ErrUnknownAccount)
	_, err = b.Post(1, "x", hLn("assets:cash", 0), hLn("income:sales", 0))
	hIs(t, "zero", err, ErrBadAmount)
	_, err = b.Post(1, "x", hLn("assets:cash", 5), hLn("income:sales", -4))
	hIs(t, "unbalanced", err, ErrUnbalanced)
	_, err = b.Post(1, "x", hLn("assets:cash", 5), hLn("income:sales", -3), hLn("income:sales", -2), hLn("assets:bank", 0))
	hIs(t, "zero line among others", err, ErrBadAmount)
	hEq(t, "nothing recorded", len(b.Entries()), n)
	id, err := b.Post(0, "  spaced memo \\n", hLn("assets:cash", 7), hLn("income:sales", -3), hLn("income:sales", -4))
	if err != nil || id != 5 {
		t.Fatalf("post: %d %v", id, err)
	}
	es := b.Entries()
	hEq(t, "memo trimmed", es[4].Memo, "spaced memo")
	hEq(t, "lines", es[4].Lines, []Line{hLn("assets:cash", 7), hLn("income:sales", -3), hLn("income:sales", -4)})
	hEq(t, "day", es[4].Day, 0)
	es[4].Lines[0].Cents = 99
	es[0].Memo = "changed"
	again := b.Entries()
	hEq(t, "copies", []interface{}{again[4].Lines[0].Cents, again[0].Memo}, []interface{}{int64(7), "Opening loan"})
}

func TestBaseBalancesAndReport(t *testing.T) {
	b := hBook()
	for name, want := range map[string]int64{"assets:bank": 60000, "assets:cash": 23550, "liabilities:loan": -100000, "income:sales": -25000, "expenses:rent": 40000, "expenses:food": 1450} {
		got, err := b.Balance(name)
		if err != nil || got != want {
			t.Errorf("%s: %d %v", name, got, err)
		}
	}
	_, err := b.Balance("assets:petty")
	hIs(t, "unknown balance", err, ErrUnknownAccount)
	b.Open("assets:petty", Asset)
	hPost(b, 9, "Tiny", hLn("assets:petty", 5), hLn("income:sales", -5))
	hPost(b, 9, "Debt", hLn("expenses:food", 123456), hLn("liabilities:loan", -123456))
	@@default base_report
	hEq(t, "report", b.Report(), __REPORT__)
	@@end
	hEq(t, "empty report", New().Report(), "")
}
@@blocks tests
'''


def _report(rows, fmtstr="%-24s %10s\n"):
    return "".join(fmtstr % (n, ("-" if c < 0 else "") + "%d.%02d" % (abs(c) // 100, abs(c) % 100)) for n, c in rows)


def make_slices(rng: random.Random):
    tag_max = rng.choice([12, 16, 20])
    rev_word = rng.choice(["reversal of", "undo of"])
    cm = rng.choice([";", "%"])
    cur = rng.choice(["EUR", "USD", "GBP"])
    other = rng.choice([c for c in ("EUR", "USD", "GBP", "CHF") if c != cur])
    S = []

    S.append(Slice(
        id="as-of", title="Balances as of a day", d=1,
        pitch=("The treasurer needs to know what the bank balance was at the end of last month.",
               "Members ask what an account held on a given day, not only today."),
        reqs=("`Book.BalanceAt(name string, day int) (int64, error)` is the balance of an account counting only the entries dated on or before `day`. An unknown account is `ErrUnknownAccount` (checked first) and a negative day is `ErrBadDay`.",
              "Entries are counted by the day they are dated, not by the order they were posted in."),
        code={
            "book.go::methods": '''
                // BalanceAt is the balance counting entries dated on or before day.
                func (b *Book) BalanceAt(name string, day int) (int64, error) {
                	if _, ok := b.accounts[name]; !ok {
                		return 0, fmt.Errorf("%w: %q", ErrUnknownAccount, name)
                	}
                	if day < 0 {
                		return 0, fmt.Errorf("%w: %d", ErrBadDay, day)
                	}
                	var sum int64
                	for _, e := range b.entries {
                		if e.Day > day {
                			continue
                		}
                		for _, l := range e.Lines {
                			if l.Account == name {
                				sum += l.Cents
                			}
                		}
                	}
                	return sum, nil
                }
            ''',
        },
        readme="## Balances as of a day\n\n`BalanceAt(name, day)` counts only the entries dated on or before `day` (`ErrUnknownAccount` first, then `ErrBadDay` for a negative day).\n",
        vtests='''
            func TestBalanceAtBasic(t *testing.T) {
            	b := vBook()
            	if got, _ := b.BalanceAt("assets:bank", 1); got != 100000 {
            		t.Fatalf("got %d", got)
            	}
            }
        ''',
        tests='''
            func TestBalanceAt(t *testing.T) {
            	b := hBook()
            	cases := []struct {
            		name string
            		day  int
            		want int64
            	}{
            		{"assets:bank", 0, 0}, {"assets:bank", 1, 100000}, {"assets:bank", 2, 100000}, {"assets:bank", 3, 60000},
            		{"assets:bank", 99, 60000}, {"assets:cash", 4, 25000}, {"assets:cash", 5, 23550},
            		{"income:sales", 1, 0}, {"income:sales", 2, -25000}, {"expenses:food", 4, 0}, {"expenses:food", 5, 1450},
            	}
            	for _, c := range cases {
            		got, err := b.BalanceAt(c.name, c.day)
            		if err != nil || got != c.want {
            			t.Errorf("%s at %d: %d %v, want %d", c.name, c.day, got, err, c.want)
            		}
            	}
            	hPost(b, 2, "Late booking", hLn("assets:bank", 500), hLn("income:sales", -500))
            	if got, _ := b.BalanceAt("assets:bank", 2); got != 100500 {
            		t.Errorf("late entry counts by its day: %d", got)
            	}
            	if got, _ := b.BalanceAt("assets:bank", 1); got != 100000 {
            		t.Errorf("but not before it: %d", got)
            	}
            }

            func TestBalanceAtErrors(t *testing.T) {
            	b := hBook()
            	_, err := b.BalanceAt("nope", -5)
            	hIs(t, "unknown first", err, ErrUnknownAccount)
            	_, err = b.BalanceAt("assets:bank", -1)
            	hIs(t, "negative day", err, ErrBadDay)
            	got, _ := b.BalanceAt("assets:bank", 1000000)
            	want, _ := b.Balance("assets:bank")
            	hEq(t, "far future equals Balance", got, want)
            }
        ''',
    ))

    S.append(Slice(
        id="entries-for", title="Entries of an account", d=1,
        pitch=("Auditors want to see every entry that touched the cash box.",
               "People keep asking for the history of a single account."),
        reqs=("`Book.EntriesFor(name string) ([]Entry, error)` returns copies of the entries that have at least one line on the account, in id order (an entry that touches the account twice appears once). An account without entries gives an empty slice; an unknown account is `ErrUnknownAccount`.",
              "Changing the returned entries does not change the book."),
        code={
            "book.go::methods": '''
                // EntriesFor returns copies of the entries that touch the account.
                func (b *Book) EntriesFor(name string) ([]Entry, error) {
                	if _, ok := b.accounts[name]; !ok {
                		return nil, fmt.Errorf("%w: %q", ErrUnknownAccount, name)
                	}
                	out := []Entry{}
                	for _, e := range b.Entries() {
                		for _, l := range e.Lines {
                			if l.Account == name {
                				out = append(out, e)
                				break
                			}
                		}
                	}
                	return out, nil
                }
            ''',
        },
        readme="## Entries of an account\n\n`EntriesFor(name)` returns copies of the entries that touch the account, in id order, each once.\n",
        vtests='''
            func TestEntriesForBasic(t *testing.T) {
            	b := vBook()
            	es, err := b.EntriesFor("assets:cash")
            	if err != nil || len(es) != 2 {
            		t.Fatalf("got %v %v", es, err)
            	}
            }
        ''',
        tests='''
            func TestEntriesFor(t *testing.T) {
            	b := hBook()
            	es, err := b.EntriesFor("assets:cash")
            	if err != nil {
            		t.Fatal(err)
            	}
            	hEq(t, "cash", hIDs(es), []int{2, 4})
            	es, _ = b.EntriesFor("expenses:rent")
            	hEq(t, "rent", hIDs(es), []int{3})
            	b.Open("assets:petty", Asset)
            	es, err = b.EntriesFor("assets:petty")
            	if err != nil || es == nil || len(es) != 0 {
            		t.Errorf("empty: %v %v", es, err)
            	}
            	hPost(b, 6, "Split", hLn("assets:cash", 100), hLn("assets:cash", -60), hLn("assets:cash", -40))
            	es, _ = b.EntriesFor("assets:cash")
            	hEq(t, "once each", hIDs(es), []int{2, 4, 5})
            	_, err = b.EntriesFor("nope")
            	hIs(t, "unknown", err, ErrUnknownAccount)
            }

            func TestEntriesForReturnsCopies(t *testing.T) {
            	b := hBook()
            	es, _ := b.EntriesFor("assets:cash")
            	es[0].Memo = "changed"
            	es[0].Lines[0].Cents = 1
            	again, _ := b.EntriesFor("assets:cash")
            	hEq(t, "memo", again[0].Memo, "Sale")
            	hEq(t, "lines", again[0].Lines[0].Cents, int64(25000))
            }
        ''',
    ))

    S.append(Slice(
        id="natural", title="Natural balances", d=2,
        pitch=("Reports show the loan as -1000.00 and the board keeps asking why a debt is negative.",
               "Liabilities and income should read as positive numbers in reports for humans."),
        reqs=("`Book.KindOf(name string) (Kind, error)` returns the kind of an account and `Book.NaturalBalance(name string) (int64, error)` the balance as people read it: for `Asset` and `Expense` accounts the plain balance, for `Liability` and `Income` accounts the plain balance with the sign flipped. Unknown accounts are `ErrUnknownAccount`.",
              "`Kind` gets a `String()` method: `asset`, `liability`, `income`, `expense`, and `kind(N)` for any other value."),
        code={
            "book.go::methods": '''
                // KindOf returns the kind of an account.
                func (b *Book) KindOf(name string) (Kind, error) {
                	a, ok := b.accounts[name]
                	if !ok {
                		return 0, fmt.Errorf("%w: %q", ErrUnknownAccount, name)
                	}
                	return a.kind, nil
                }

                // NaturalBalance is the balance with the sign people expect for the kind of account.
                func (b *Book) NaturalBalance(name string) (int64, error) {
                	k, err := b.KindOf(name)
                	if err != nil {
                		return 0, err
                	}
                	bal, _ := b.Balance(name)
                	if k == Liability || k == Income {
                		return -bal, nil
                	}
                	return bal, nil
                }

                func (k Kind) String() string {
                	switch k {
                	case Asset:
                		return "asset"
                	case Liability:
                		return "liability"
                	case Income:
                		return "income"
                	case Expense:
                		return "expense"
                	}
                	return fmt.Sprintf("kind(%d)", int(k))
                }
            ''',
        },
        readme="## Natural balances\n\n`KindOf(name)`, `NaturalBalance(name)` (sign flipped for liabilities and income) and `Kind.String()`.\n",
        vtests='''
            func TestNaturalBasic(t *testing.T) {
            	b := vBook()
            	if got, _ := b.NaturalBalance("liabilities:loan"); got != 100000 {
            		t.Fatalf("got %d", got)
            	}
            }
        ''',
        tests='''
            func TestNaturalBalance(t *testing.T) {
            	b := hBook()
            	want := map[string]int64{"assets:bank": 60000, "assets:cash": 23550, "liabilities:loan": 100000, "income:sales": 25000, "expenses:rent": 40000, "expenses:food": 1450}
            	for name, w := range want {
            		got, err := b.NaturalBalance(name)
            		if err != nil || got != w {
            			t.Errorf("%s: %d %v, want %d", name, got, err, w)
            		}
            	}
            	hPost(b, 6, "Refund", hLn("assets:cash", 2000), hLn("expenses:food", -2000))
            	got, _ := b.NaturalBalance("expenses:food")
            	hEq(t, "negative expense stays negative", got, int64(-550))
            	_, err := b.NaturalBalance("nope")
            	hIs(t, "unknown balance", err, ErrUnknownAccount)
            }

            func TestKindOfAndString(t *testing.T) {
            	b := hBook()
            	k, err := b.KindOf("income:sales")
            	if err != nil || k != Income {
            		t.Fatalf("got %v %v", k, err)
            	}
            	_, err = b.KindOf("nope")
            	hIs(t, "unknown", err, ErrUnknownAccount)
            	hEq(t, "strings", []string{Asset.String(), Liability.String(), Income.String(), Expense.String(), Kind(7).String()},
            		[]string{"asset", "liability", "income", "expense", "kind(7)"})
            	hEq(t, "Sprint", fmt.Sprint(Expense), "expense")
            }
        ''',
    ))

    S.append(Slice(
        id="tags", title="Line tags", d=2,
        pitch=("The club wants to know what the summer party cost across rent, food and drinks.",
               "Money spent on one event is scattered over several accounts and nobody can add it up."),
        reqs=(f"A `Line` gets an optional `Tag string`: empty, or 1 to {tag_max} characters from `a-z`, `0-9` and `-`, not starting with a dash (`ErrBadTag` otherwise, checked per line after the account and amount checks). Entries keep the tags of their lines.",
              "`Book.BalanceTagged(name, tag string) (int64, error)` sums the lines of an account that carry exactly that tag (the empty tag means the untagged lines; an unknown account is `ErrUnknownAccount`). `Book.Tags() []string` lists the tags in use, without duplicates, alphabetically."),
        code={
            "book.go::line_fields": "Tag     string",
            "book.go::errors": 'ErrBadTag = errors.New("tallybook: bad tag")',
            "book.go::types": fmt('''
                var tagRE = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{0,__M__}$`)
            ''', M=tag_max - 1),
            "book.go::line_checks": '''
                if l.Tag != "" && !tagRE.MatchString(l.Tag) {
                	return 0, fmt.Errorf("%w: %q", ErrBadTag, l.Tag)
                }
            ''',
            "book.go::methods": '''
                // BalanceTagged sums the lines of the account with exactly this tag.
                func (b *Book) BalanceTagged(name, tag string) (int64, error) {
                	if _, ok := b.accounts[name]; !ok {
                		return 0, fmt.Errorf("%w: %q", ErrUnknownAccount, name)
                	}
                	var sum int64
                	for _, e := range b.entries {
                		for _, l := range e.Lines {
                			if l.Account == name && l.Tag == tag {
                				sum += l.Cents
                			}
                		}
                	}
                	return sum, nil
                }

                // Tags lists the tags in use.
                func (b *Book) Tags() []string {
                	seen := map[string]bool{}
                	out := []string{}
                	for _, e := range b.entries {
                		for _, l := range e.Lines {
                			if l.Tag != "" && !seen[l.Tag] {
                				seen[l.Tag] = true
                				out = append(out, l.Tag)
                			}
                		}
                	}
                	sort.Strings(out)
                	return out
                }
            ''',
        },
        readme=f"## Line tags\n\n`Line.Tag` is empty or 1 to {tag_max} characters of `a-z0-9-` (not starting with a dash; `ErrBadTag`). `BalanceTagged(name, tag)` sums the lines with exactly that tag (empty = untagged) and `Tags()` lists the tags in use.\n",
        vtests='''
            func TestTagsBasic(t *testing.T) {
            	b := vBook()
            	vPost(b, 6, "Party", Line{Account: "expenses:food", Cents: 800, Tag: "party"}, Line{Account: "assets:cash", Cents: -800})
            	if got, _ := b.BalanceTagged("expenses:food", "party"); got != 800 {
            		t.Fatalf("got %d", got)
            	}
            }
        ''',
        tests=fmt('''
            func TestTags(t *testing.T) {
            	b := hBook()
            	hPost(b, 6, "Party food", Line{Account: "expenses:food", Cents: 800, Tag: "party"}, Line{Account: "assets:cash", Cents: -800, Tag: "party"})
            	hPost(b, 7, "Party rent", Line{Account: "expenses:rent", Cents: 5000, Tag: "party"}, Line{Account: "assets:bank", Cents: -5000})
            	hPost(b, 8, "Trip", Line{Account: "expenses:food", Cents: 300, Tag: "trip-2"}, Line{Account: "assets:cash", Cents: -300})
            	cases := []struct {
            		name, tag string
            		want      int64
            	}{
            		{"expenses:food", "party", 800}, {"expenses:food", "trip-2", 300}, {"expenses:food", "", 1450},
            		{"expenses:rent", "party", 5000}, {"expenses:rent", "", 40000}, {"assets:cash", "party", -800},
            		{"assets:cash", "", 23250}, {"assets:bank", "party", 0}, {"expenses:food", "nothing", 0},
            	}
            	for _, c := range cases {
            		got, err := b.BalanceTagged(c.name, c.tag)
            		if err != nil || got != c.want {
            			t.Errorf("%s/%s: %d %v, want %d", c.name, c.tag, got, err, c.want)
            		}
            	}
            	_, err := b.BalanceTagged("nope", "party")
            	hIs(t, "unknown", err, ErrUnknownAccount)
            	hEq(t, "tags", b.Tags(), []string{"party", "trip-2"})
            	hEq(t, "no tags", hBook().Tags(), []string{})
            	hEq(t, "entry keeps tags", b.Entries()[4].Lines[0].Tag, "party")
            }

            func TestTagValidation(t *testing.T) {
            	b := hBook()
            	n := len(b.Entries())
            	long := strings.Repeat("a", __M__)
            	for _, bad := range []string{"Party", "-x", "a b", "a_b", "x!", long + "a"} {
            		_, err := b.Post(6, "x", Line{Account: "expenses:food", Cents: 5, Tag: bad}, Line{Account: "assets:cash", Cents: -5})
            		hIs(t, "tag "+bad, err, ErrBadTag)
            	}
            	_, err := b.Post(6, "x", Line{Account: "expenses:food", Cents: 5}, Line{Account: "assets:cash", Cents: -5, Tag: "Bad"})
            	hIs(t, "second line", err, ErrBadTag)
            	_, err = b.Post(6, "x", Line{Account: "nope", Cents: 5, Tag: "Bad"}, Line{Account: "assets:cash", Cents: -5})
            	hIs(t, "unknown account is reported before the tag", err, ErrUnknownAccount)
            	_, err = b.Post(6, "x", Line{Account: "expenses:food", Cents: 0, Tag: "Bad"}, Line{Account: "assets:cash", Cents: -5})
            	hIs(t, "zero amount is reported before the tag", err, ErrBadAmount)
            	hEq(t, "nothing recorded", len(b.Entries()), n)
            	for _, good := range []string{long, "0", "a-b-c", "9lives"} {
            		if _, err := b.Post(6, "x", Line{Account: "expenses:food", Cents: 5, Tag: good}, Line{Account: "assets:cash", Cents: -5}); err != nil {
            			t.Errorf("tag %s: %v", good, err)
            		}
            	}
            }
        ''', M=tag_max),
        cross={
            "journal": {
                "reqs": ("In a journal a posting may end with a tag written as `#tag` (a `#` followed by at least one non-space character, separated from the amount by whitespace). The tag follows the rules of `Line.Tag`: an invalid tag fails the entry like any other posting error, reported with the entry's line number.",),
                "code": {
                    "book.go::journal_posting_re": 'var postingRE = regexp.MustCompile(`^\\s+(\\S+)\\s+([+-]?\\d+(?:\\.\\d{1,2})?)(\\s+#\\S+)?\\s*$`)',
                    "book.go::journal_tag": '''
                        if t := strings.TrimSpace(m[3]); t != "" {
                        	l.Tag = t[1:]
                        }
                    ''',
                },
                "tests": '''
                    func TestJournalTags(t *testing.T) {
                    	b := hBook()
                    	n, err := b.LoadJournal(strings.NewReader("9 Party\\n  expenses:food  8.00  #party\\n  assets:cash   -8.00\\n"))
                    	if err != nil || n != 1 {
                    		t.Fatalf("%d %v", n, err)
                    	}
                    	got, _ := b.BalanceTagged("expenses:food", "party")
                    	hEq(t, "tagged", got, int64(800))
                    	hEq(t, "tags", b.Tags(), []string{"party"})
                    	_, err = b.LoadJournal(strings.NewReader("10 Bad\\n  expenses:food  8.00  #Party\\n  assets:cash   -8.00\\n"))
                    	hIs(t, "invalid tag", err, ErrBadTag)
                    	if err == nil || !strings.Contains(err.Error(), "line 1") {
                    		t.Errorf("line number missing: %v", err)
                    	}
                    	_, err = b.LoadJournal(strings.NewReader("10 Bad\\n  expenses:food  8.00  #\\n  assets:cash   -8.00\\n"))
                    	hIs(t, "bare hash", err, ErrSyntax)
                    	hEq(t, "nothing added", len(b.Entries()), 5)
                    }
                '''},
            "reverse": {
                "reqs": ("A reversal keeps the tags of the lines it reverses.",),
                "tests": '''
                    func TestReversalKeepsTags(t *testing.T) {
                    	b := hBook()
                    	id := hPost(b, 6, "Party", Line{Account: "expenses:food", Cents: 800, Tag: "party"}, Line{Account: "assets:cash", Cents: -800})
                    	if _, err := b.Reverse(id, 7, ""); err != nil {
                    		t.Fatal(err)
                    	}
                    	got, _ := b.BalanceTagged("expenses:food", "party")
                    	hEq(t, "tag cancels out", got, int64(0))
                    	hEq(t, "reversal line", b.Entries()[5].Lines[0].Tag, "party")
                    }
                '''},
        },
    ))

    S.append(Slice(
        id="reverse", title="Reversing entries", d=3,
        pitch=("Entries can't be edited, so a wrong booking stays in the books forever.",
               "The treasurer needs a clean way to undo a mistaken booking without erasing history."),
        reqs=(f"`Book.Reverse(id, day int, memo string) (int, error)` posts a new entry that cancels entry `id` (every line with the sign flipped, same accounts, same order) dated `day`, and returns the new id. An empty (or blank) memo becomes `{rev_word} #ID` with the original's id. The new entry has `ReverseOf` set to `id` (a new `Entry` field; 0 for ordinary entries) and the original gets `Reversed` set to true (another new `Entry` field).",
              "Checks in this order, a failed call changing nothing: an unknown id (`ErrNoEntry`); an entry that is itself a reversal (`ErrIsReversal`); an entry that was already reversed (`ErrAlreadyReversed`); a `day` before the original's day (`ErrBadDay`; same day is fine). After that the reversal is posted like any entry, so every check of `Post` applies."),
        code={
            "book.go::errors": '''
                ErrNoEntry         = errors.New("tallybook: no such entry")
                ErrIsReversal      = errors.New("tallybook: a reversal cannot be reversed")
                ErrAlreadyReversed = errors.New("tallybook: entry already reversed")
            ''',
            "book.go::entry_fields": '''
                ReverseOf int
                Reversed  bool
            ''',
            "book.go::methods": fmt('''
                // Reverse posts an entry that cancels entry id.
                func (b *Book) Reverse(id, day int, memo string) (int, error) {
                	if id < 1 || id > len(b.entries) {
                		return 0, fmt.Errorf("%w: %d", ErrNoEntry, id)
                	}
                	orig := b.entries[id-1]
                	if orig.ReverseOf != 0 {
                		return 0, fmt.Errorf("%w: entry %d", ErrIsReversal, id)
                	}
                	if orig.Reversed {
                		return 0, fmt.Errorf("%w: entry %d", ErrAlreadyReversed, id)
                	}
                	if day < orig.Day {
                		return 0, fmt.Errorf("%w: entry %d is dated day %d", ErrBadDay, id, orig.Day)
                	}
                	if strings.TrimSpace(memo) == "" {
                		memo = fmt.Sprintf("__W__ #%d", id)
                	}
                	lines := make([]Line, len(orig.Lines))
                	for i, l := range orig.Lines {
                		l.Cents = -l.Cents
                		lines[i] = l
                	}
                	rid, err := b.Post(day, memo, lines...)
                	if err != nil {
                		return 0, err
                	}
                	b.entries[rid-1].ReverseOf = id
                	b.entries[id-1].Reversed = true
                	return rid, nil
                }
            ''', W=rev_word),
        },
        readme=f"## Reversing entries\n\n`Reverse(id, day, memo)` posts the opposite entry and returns its id. `Entry.ReverseOf` points at the original, `Entry.Reversed` marks a reversed original. Default memo `{rev_word} #ID`. Errors, in order: `ErrNoEntry`, `ErrIsReversal`, `ErrAlreadyReversed`, `ErrBadDay` (before the original).\n",
        vtests='''
            func TestReverseBasic(t *testing.T) {
            	b := vBook()
            	id, err := b.Reverse(4, 6, "")
            	if err != nil || id != 5 {
            		t.Fatalf("%d %v", id, err)
            	}
            	if got, _ := b.Balance("expenses:food"); got != 0 {
            		t.Fatalf("food %d", got)
            	}
            }
        ''',
        tests=fmt('''
            func TestReverse(t *testing.T) {
            	b := hBook()
            	id, err := b.Reverse(4, 6, "")
            	if err != nil || id != 5 {
            		t.Fatalf("%d %v", id, err)
            	}
            	es := b.Entries()
            	hEq(t, "memo", es[4].Memo, "__W__ #4")
            	hEq(t, "reverse of", []interface{}{es[4].ReverseOf, es[4].Reversed, es[4].Day}, []interface{}{4, false, 6})
            	hEq(t, "lines", es[4].Lines, []Line{hLn("expenses:food", -1450), hLn("assets:cash", 1450)})
            	hEq(t, "original", []interface{}{es[3].Reversed, es[3].ReverseOf, es[3].Lines[0].Cents}, []interface{}{true, 0, int64(1450)})
            	food, _ := b.Balance("expenses:food")
            	cash, _ := b.Balance("assets:cash")
            	hEq(t, "balances", []int64{food, cash}, []int64{0, 25000})
            	id, err = b.Reverse(3, 3, "  oops, wrong month  ")
            	if err != nil || id != 6 {
            		t.Fatalf("same day: %d %v", id, err)
            	}
            	hEq(t, "custom memo", b.Entries()[5].Memo, "oops, wrong month")
            	hEq(t, "untouched entry", b.Entries()[0].Reversed, false)
            }

            func TestReverseErrors(t *testing.T) {
            	b := hBook()
            	n := len(b.Entries())
            	for _, id := range []int{0, -1, 5, 99} {
            		_, err := b.Reverse(id, 9, "")
            		hIs(t, "unknown id", err, ErrNoEntry)
            	}
            	_, err := b.Reverse(3, 2, "")
            	hIs(t, "before the original", err, ErrBadDay)
            	_, err = b.Reverse(3, -1, "")
            	hIs(t, "negative day", err, ErrBadDay)
            	hEq(t, "nothing recorded", len(b.Entries()), n)
            	hEq(t, "not marked", b.Entries()[2].Reversed, false)
            	rid, err := b.Reverse(3, 4, "")
            	if err != nil {
            		t.Fatal(err)
            	}
            	_, err = b.Reverse(3, 9, "")
            	hIs(t, "twice", err, ErrAlreadyReversed)
            	_, err = b.Reverse(3, 0, "")
            	hIs(t, "already reversed is reported before the day", err, ErrAlreadyReversed)
            	_, err = b.Reverse(rid, 9, "")
            	hIs(t, "reversal of a reversal", err, ErrIsReversal)
            	_, err = b.Reverse(rid, 0, "")
            	hIs(t, "reversal check is before the day check", err, ErrIsReversal)
            	hEq(t, "only one reversal", len(b.Entries()), n+1)
            }
        ''', W=rev_word),
        cross={
            "close": {
                "reqs": ("A reversal dated inside a closed period is refused with `ErrClosed` (and the original is not marked as reversed); a reversal dated after the closed period is fine even if the original lies inside it.",),
                "tests": '''
                    func TestReverseAndClose(t *testing.T) {
                    	b := hBook()
                    	if err := b.Close(5); err != nil {
                    		t.Fatal(err)
                    	}
                    	_, err := b.Reverse(4, 5, "")
                    	hIs(t, "inside the closed period", err, ErrClosed)
                    	hEq(t, "not marked", b.Entries()[3].Reversed, false)
                    	id, err := b.Reverse(4, 6, "")
                    	if err != nil || id != 5 {
                    		t.Fatalf("%d %v", id, err)
                    	}
                    }
                '''},
            "budget": {
                "reqs": ("A reversal that lowers an expense balance is never refused because of a budget.",),
                "tests": '''
                    func TestReverseIgnoresBudgetWhenSpendingDrops(t *testing.T) {
                    	b := hBook()
                    	if err := b.SetBudget("expenses:food", 100); err != nil {
                    		t.Fatal(err)
                    	}
                    	if _, err := b.Reverse(4, 6, ""); err != nil {
                    		t.Fatalf("reversal refused: %v", err)
                    	}
                    	got, _ := b.Balance("expenses:food")
                    	hEq(t, "food", got, int64(0))
                    }
                '''},
        },
    ))

    S.append(Slice(
        id="close", title="Closing a period", d=3,
        pitch=("Last quarter's figures were already sent to the bank and somebody backdated a booking into them.",
               "Once a period is reported, nobody may post into it any more."),
        reqs=("`Book.Close(day int) error` closes the books through `day` (that day included) and `Book.ClosedThrough() int` returns the last closed day (`-1` when nothing is closed). Closing can only move forward: a day before the current one is `ErrBadDay`, closing the same day again is fine, a negative day is `ErrBadDay`.",
              "`Post` refuses an entry dated on or before the closed day with `ErrClosed`. That check comes right after the check for a negative day, before the number of lines is looked at. Balances are not affected by closing."),
        code={
            "book.go::errors": 'ErrClosed = errors.New("tallybook: the period is closed")',
            "book.go::book_fields": "closed int",
            "book.go::new_book": "b.closed = -1",
            "book.go::post_pre": '''
                if day <= b.closed {
                	return 0, fmt.Errorf("%w: day %d (closed through day %d)", ErrClosed, day, b.closed)
                }
            ''',
            "book.go::methods": '''
                // Close closes the books through day.
                func (b *Book) Close(day int) error {
                	if day < 0 {
                		return fmt.Errorf("%w: %d", ErrBadDay, day)
                	}
                	if day < b.closed {
                		return fmt.Errorf("%w: already closed through day %d", ErrBadDay, b.closed)
                	}
                	b.closed = day
                	return nil
                }

                // ClosedThrough is the last closed day, or -1.
                func (b *Book) ClosedThrough() int { return b.closed }
            ''',
        },
        readme="## Closing a period\n\n`Close(day)` closes the books through `day` (forward only; `ErrBadDay` otherwise) and `ClosedThrough()` reports it (-1 if none). `Post` refuses entries dated on or before it with `ErrClosed`, right after the negative-day check.\n",
        vtests='''
            func TestCloseBasic(t *testing.T) {
            	b := vBook()
            	b.Close(3)
            	if _, err := b.Post(3, "late", vLn("assets:cash", 1), vLn("income:sales", -1)); !errors.Is(err, ErrClosed) {
            		t.Fatalf("got %v", err)
            	}
            }
        ''',
        tests='''
            func TestClose(t *testing.T) {
            	b := hBook()
            	hEq(t, "initially", b.ClosedThrough(), -1)
            	if err := b.Close(3); err != nil {
            		t.Fatal(err)
            	}
            	hEq(t, "closed through", b.ClosedThrough(), 3)
            	_, err := b.Post(3, "late", hLn("assets:cash", 1), hLn("income:sales", -1))
            	hIs(t, "on the closed day", err, ErrClosed)
            	_, err = b.Post(0, "early", hLn("assets:cash", 1), hLn("income:sales", -1))
            	hIs(t, "before it", err, ErrClosed)
            	_, err = b.Post(2, "one line", hLn("assets:cash", 1))
            	hIs(t, "closed is reported before the line count", err, ErrClosed)
            	_, err = b.Post(-1, "negative", hLn("assets:cash", 1), hLn("income:sales", -1))
            	hIs(t, "negative day first", err, ErrBadDay)
            	id, err := b.Post(4, "open", hLn("assets:cash", 1), hLn("income:sales", -1))
            	if err != nil || id != 5 {
            		t.Fatalf("%d %v", id, err)
            	}
            	hEq(t, "balances untouched", func() int64 { v, _ := b.Balance("assets:bank"); return v }(), int64(60000))
            	hEq(t, "nothing else recorded", len(b.Entries()), 5)
            }

            func TestCloseMovesForwardOnly(t *testing.T) {
            	b := hBook()
            	b.Close(10)
            	hIs(t, "backwards", b.Close(9), ErrBadDay)
            	hEq(t, "unchanged", b.ClosedThrough(), 10)
            	if err := b.Close(10); err != nil {
            		t.Errorf("same day: %v", err)
            	}
            	hIs(t, "negative", New().Close(-1), ErrBadDay)
            	if err := b.Close(12); err != nil {
            		t.Fatal(err)
            	}
            	hEq(t, "moved", b.ClosedThrough(), 12)
            	empty := New()
            	if err := empty.Close(0); err != nil {
            		t.Fatal(err)
            	}
            	empty.Open("assets:a", Asset)
            	empty.Open("income:b", Income)
            	_, err := empty.Post(0, "x", hLn("assets:a", 1), hLn("income:b", -1))
            	hIs(t, "day 0 is closed", err, ErrClosed)
            }
        ''',
    ))

    S.append(Slice(
        id="budget", title="Budgets for expense accounts", d=3,
        pitch=("The food account has no ceiling and the club overspent its catering money twice this year.",
               "Expense accounts need a spending limit that the book enforces."),
        reqs=("`Book.SetBudget(name string, cents int64) error` sets a spending limit on an `Expense` account and `Book.ClearBudget(name string) error` removes it; `Book.Budget(name string) (int64, bool)` returns the limit and whether there is one. Errors for `SetBudget`, in order: unknown account (`ErrUnknownAccount`), not an expense account (`ErrNotExpense`), `cents` not positive (`ErrBadAmount`). `ClearBudget` fails only for an unknown account; clearing an account without a budget is fine.",
              "`Post` refuses an entry with `ErrOverBudget` when, for an expense account with a budget, the entry raises the account's balance (the sum of its lines in the entry is positive) and the resulting balance would exceed the limit. Reaching the limit exactly is fine; entries that lower or keep the balance are never refused, even when the account is over its limit (for example after the limit was lowered). The check comes after `ErrUnbalanced` and nothing is recorded when it fails."),
        code={
            "book.go::errors": '''
                ErrNotExpense = errors.New("tallybook: not an expense account")
                ErrOverBudget = errors.New("tallybook: over budget")
            ''',
            "book.go::book_fields": "budgets map[string]int64",
            "book.go::new_book": "b.budgets = map[string]int64{}",
            "book.go::post_checks": '''
                if err := b.checkBudgets(lines); err != nil {
                	return 0, err
                }
            ''',
            "book.go::methods": '''
                // SetBudget sets a spending limit on an expense account.
                func (b *Book) SetBudget(name string, cents int64) error {
                	a, ok := b.accounts[name]
                	if !ok {
                		return fmt.Errorf("%w: %q", ErrUnknownAccount, name)
                	}
                	if a.kind != Expense {
                		return fmt.Errorf("%w: %s", ErrNotExpense, name)
                	}
                	if cents <= 0 {
                		return ErrBadAmount
                	}
                	b.budgets[name] = cents
                	return nil
                }

                // ClearBudget removes the limit of an account.
                func (b *Book) ClearBudget(name string) error {
                	if _, ok := b.accounts[name]; !ok {
                		return fmt.Errorf("%w: %q", ErrUnknownAccount, name)
                	}
                	delete(b.budgets, name)
                	return nil
                }

                // Budget returns the limit of an account, if it has one.
                func (b *Book) Budget(name string) (int64, bool) {
                	v, ok := b.budgets[name]
                	return v, ok
                }

                func (b *Book) checkBudgets(lines []Line) error {
                	net := map[string]int64{}
                	for _, l := range lines {
                		net[l.Account] += l.Cents
                	}
                	names := make([]string, 0, len(net))
                	for n := range net {
                		names = append(names, n)
                	}
                	sort.Strings(names)
                	for _, n := range names {
                		limit, ok := b.budgets[n]
                		if !ok || net[n] <= 0 {
                			continue
                		}
                		cur, _ := b.Balance(n)
                		if cur+net[n] > limit {
                			return fmt.Errorf("%w: %s would be %d, limit %d", ErrOverBudget, n, cur+net[n], limit)
                		}
                	}
                	return nil
                }
            ''',
        },
        readme="## Budgets for expense accounts\n\n`SetBudget(name, cents)` (errors: `ErrUnknownAccount`, `ErrNotExpense`, `ErrBadAmount`), `ClearBudget(name)`, `Budget(name)`. `Post` refuses with `ErrOverBudget` an entry that raises a budgeted expense balance above its limit; entries that do not raise it are always fine.\n",
        vtests='''
            func TestBudgetBasic(t *testing.T) {
            	b := vBook()
            	if err := b.SetBudget("expenses:food", 2000); err != nil {
            		t.Fatal(err)
            	}
            	if _, err := b.Post(6, "feast", vLn("expenses:food", 551), vLn("assets:cash", -551)); !errors.Is(err, ErrOverBudget) {
            		t.Fatalf("got %v", err)
            	}
            }
        ''',
        tests='''
            func TestBudget(t *testing.T) {
            	b := hBook()
            	if v, ok := b.Budget("expenses:food"); ok || v != 0 {
            		t.Errorf("no budget yet: %d %v", v, ok)
            	}
            	if err := b.SetBudget("expenses:food", 2000); err != nil {
            		t.Fatal(err)
            	}
            	if v, ok := b.Budget("expenses:food"); !ok || v != 2000 {
            		t.Errorf("budget: %d %v", v, ok)
            	}
            	n := len(b.Entries())
            	_, err := b.Post(6, "too much", hLn("expenses:food", 551), hLn("assets:cash", -551))
            	hIs(t, "one cent over", err, ErrOverBudget)
            	hEq(t, "nothing recorded", len(b.Entries()), n)
            	if _, err := b.Post(6, "exactly", hLn("expenses:food", 550), hLn("assets:cash", -550)); err != nil {
            		t.Errorf("reaching the limit: %v", err)
            	}
            	_, err = b.Post(7, "more", hLn("expenses:food", 1), hLn("assets:cash", -1))
            	hIs(t, "now full", err, ErrOverBudget)
            	if _, err := b.Post(7, "refund", hLn("assets:cash", 100), hLn("expenses:food", -100)); err != nil {
            		t.Errorf("refund: %v", err)
            	}
            	if _, err := b.Post(8, "again", hLn("expenses:food", 100), hLn("assets:cash", -100)); err != nil {
            		t.Errorf("back to the limit: %v", err)
            	}
            	if _, err := b.Post(8, "rent has no budget", hLn("expenses:rent", 999999), hLn("assets:bank", -999999)); err != nil {
            		t.Errorf("rent: %v", err)
            	}
            	_, err = b.Post(9, "unbalanced beats budget", hLn("expenses:food", 5000), hLn("assets:cash", -1))
            	hIs(t, "unbalanced first", err, ErrUnbalanced)
            }

            func TestBudgetNetPerEntry(t *testing.T) {
            	b := hBook()
            	b.SetBudget("expenses:food", 1500)
            	if _, err := b.Post(6, "net +50", hLn("expenses:food", 300), hLn("expenses:food", -250), hLn("assets:cash", -50)); err != nil {
            		t.Errorf("net 50 fits: %v", err)
            	}
            	_, err := b.Post(6, "net +60", hLn("expenses:food", 300), hLn("expenses:food", -240), hLn("assets:cash", -60))
            	hIs(t, "net 60 does not", err, ErrOverBudget)
            	b.SetBudget("expenses:food", 100)
            	_, err = b.Post(7, "plus one", hLn("expenses:food", 1), hLn("assets:cash", -1))
            	hIs(t, "lowered limit", err, ErrOverBudget)
            	if _, err := b.Post(7, "minus fifty", hLn("assets:cash", 50), hLn("expenses:food", -50)); err != nil {
            		t.Errorf("lowering a balance that is over its limit: %v", err)
            	}
            	if _, err := b.Post(7, "neutral", hLn("expenses:food", 10), hLn("expenses:food", -10)); err != nil {
            		t.Errorf("neutral entry: %v", err)
            	}
            }

            func TestBudgetManagement(t *testing.T) {
            	b := hBook()
            	hIs(t, "unknown", b.SetBudget("nope", 5), ErrUnknownAccount)
            	hIs(t, "not an expense", b.SetBudget("income:sales", 5), ErrNotExpense)
            	hIs(t, "unknown comes first", b.SetBudget("nope", -5), ErrUnknownAccount)
            	hIs(t, "not an expense comes before the amount", b.SetBudget("assets:cash", 0), ErrNotExpense)
            	hIs(t, "zero", b.SetBudget("expenses:food", 0), ErrBadAmount)
            	hIs(t, "negative", b.SetBudget("expenses:food", -5), ErrBadAmount)
            	if _, ok := b.Budget("expenses:food"); ok {
            		t.Error("failed calls set nothing")
            	}
            	hIs(t, "clear unknown", b.ClearBudget("nope"), ErrUnknownAccount)
            	if err := b.ClearBudget("expenses:food"); err != nil {
            		t.Errorf("clear without budget: %v", err)
            	}
            	b.SetBudget("expenses:food", 1450)
            	if _, err := b.Post(6, "x", hLn("expenses:food", 1), hLn("assets:cash", -1)); err == nil {
            		t.Error("limit not enforced")
            	}
            	if err := b.ClearBudget("expenses:food"); err != nil {
            		t.Fatal(err)
            	}
            	if _, err := b.Post(6, "x", hLn("expenses:food", 1), hLn("assets:cash", -1)); err != nil {
            		t.Errorf("after clearing: %v", err)
            	}
            }
        ''',
    ))

    S.append(Slice(
        id="journal", title="Loading a journal file", d=4,
        pitch=("The treasurer keeps the monthly bookings in a plain text file and retypes them into the program.",
               "Bookings should be loadable from a text journal instead of being posted one by one."),
        reqs=(f"`Book.LoadJournal(r io.Reader) (int, error)` reads a journal and posts every entry in it, returning how many entries were posted. The format is line based (a trailing `\\r` is ignored): an empty or blank line ends the current entry; a line whose first non-blank character is `{cm}` is a comment and is skipped; a line starting with a digit begins an entry: the day (digits only), then optionally whitespace and the memo (the rest of the line); a line starting with a space or tab is a posting of the current entry: an account name, whitespace and an amount with an optional sign and up to two decimals (`1200`, `-14.5`, `+0.05`), which is the line's cents (`-14.5` is -1450).",
              "Anything else is a syntax error (`ErrSyntax`), for example an unreadable header, an amount like `5.123` or a posting outside an entry. Errors are returned wrapped with the 1-based line number as `line N: ...`; entries that fail when they are posted (unknown account, unbalanced, a single posting, ...) report the line of their header and wrap the error of `Post`. The load is all or nothing: if anything fails, nothing is posted and the result is `0` and the error. An empty journal posts nothing and returns `0, nil`."),
        code={
            "book.go::imports": '''
                "io"
                "strconv"
            ''',
            "book.go::errors": 'ErrSyntax = errors.New("tallybook: syntax error")',
            "book.go::methods": fmt('''
                var headerRE = regexp.MustCompile(`^(\\d+)(?:\\s+(.*))?$`)

                @@default journal_posting_re
                var postingRE = regexp.MustCompile(`^\\s+(\\S+)\\s+([+-]?\\d+(?:\\.\\d{1,2})?)\\s*$`)
                @@end

                func parseCents(s string) (int64, bool) {
                	neg := strings.HasPrefix(s, "-")
                	s = strings.TrimLeft(s, "+-")
                	whole, frac := s, ""
                	if i := strings.IndexByte(s, '.'); i >= 0 {
                		whole, frac = s[:i], s[i+1:]
                	}
                	for len(frac) < 2 {
                		frac += "0"
                	}
                	w, err1 := strconv.ParseInt(whole, 10, 64)
                	f, err2 := strconv.ParseInt(frac, 10, 64)
                	if err1 != nil || err2 != nil || w > 1<<40 {
                		return 0, false
                	}
                	c := w*100 + f
                	if neg {
                		c = -c
                	}
                	return c, true
                }

                type journalEntry struct {
                	line  int
                	day   int
                	memo  string
                	lines []Line
                }

                // LoadJournal posts every entry of a journal; it is all or nothing.
                func (b *Book) LoadJournal(r io.Reader) (int, error) {
                	data, err := io.ReadAll(r)
                	if err != nil {
                		return 0, err
                	}
                	var all []*journalEntry
                	var cur *journalEntry
                	for i, raw := range strings.Split(string(data), "\\n") {
                		n := i + 1
                		raw = strings.TrimRight(raw, "\\r")
                		trim := strings.TrimSpace(raw)
                		switch {
                		case trim == "":
                			cur = nil
                		case strings.HasPrefix(trim, "__C__"):
                		case raw[0] == ' ' || raw[0] == '\\t':
                			if cur == nil {
                				return 0, fmt.Errorf("line %d: %w: posting outside an entry", n, ErrSyntax)
                			}
                			m := postingRE.FindStringSubmatch(raw)
                			if m == nil {
                				return 0, fmt.Errorf("line %d: %w: bad posting %q", n, ErrSyntax, trim)
                			}
                			cents, ok := parseCents(m[2])
                			if !ok {
                				return 0, fmt.Errorf("line %d: %w: bad amount %q", n, ErrSyntax, m[2])
                			}
                			l := Line{Account: m[1], Cents: cents}
                			@@slot journal_tag
                			cur.lines = append(cur.lines, l)
                		default:
                			m := headerRE.FindStringSubmatch(raw)
                			if m == nil {
                				return 0, fmt.Errorf("line %d: %w: bad entry header %q", n, ErrSyntax, trim)
                			}
                			day, err := strconv.Atoi(m[1])
                			if err != nil {
                				return 0, fmt.Errorf("line %d: %w: bad day %q", n, ErrSyntax, m[1])
                			}
                			cur = &journalEntry{line: n, day: day, memo: m[2]}
                			all = append(all, cur)
                		}
                	}
                	start := len(b.entries)
                	for _, p := range all {
                		if _, err := b.Post(p.day, p.memo, p.lines...); err != nil {
                			b.entries = b.entries[:start]
                			return 0, fmt.Errorf("line %d: %w", p.line, err)
                		}
                	}
                	return len(all), nil
                }
            ''', C=cm),
        },
        readme=f"## Loading a journal file\n\n`LoadJournal(r)` posts the entries of a text journal (`DAY memo` header, indented `account amount` postings, blank line between entries, `{cm}` comments) and returns their number. Syntax problems are `ErrSyntax`; every error is prefixed `line N:`; the load is all or nothing.\n",
        vtests='''
            func TestJournalBasic(t *testing.T) {
            	b := vBook()
            	n, err := b.LoadJournal(strings.NewReader("9 Tea\\n  expenses:food  3.00\\n  assets:cash  -3.00\\n"))
            	if err != nil || n != 1 {
            		t.Fatalf("%d %v", n, err)
            	}
            }
        ''',
        tests=fmt('''
            func hJournal(t *testing.T, b *Book, text string) (int, error) {
            	t.Helper()
            	return b.LoadJournal(strings.NewReader(text))
            }

            func TestJournalLoads(t *testing.T) {
            	b := hBook()
            	text := "__C__ March\\n12 Rent for March\\n  expenses:rent      1200.00\\n  assets:bank       -1200.00\\n\\n13 Coffee beans\\n  expenses:food        14.5\\n__C__ the cash side\\n  assets:cash         -14.50\\n"
            	n, err := hJournal(t, b, text)
            	if err != nil || n != 2 {
            		t.Fatalf("%d %v", n, err)
            	}
            	es := b.Entries()
            	hEq(t, "first", []interface{}{es[4].ID, es[4].Day, es[4].Memo}, []interface{}{5, 12, "Rent for March"})
            	hEq(t, "first lines", es[4].Lines, []Line{hLn("expenses:rent", 120000), hLn("assets:bank", -120000)})
            	hEq(t, "second", []interface{}{es[5].ID, es[5].Day, es[5].Memo}, []interface{}{6, 13, "Coffee beans"})
            	hEq(t, "second lines", es[5].Lines, []Line{hLn("expenses:food", 1450), hLn("assets:cash", -1450)})
            	bank, _ := b.Balance("assets:bank")
            	hEq(t, "balance", bank, int64(-60000))
            }

            func TestJournalFormats(t *testing.T) {
            	b := hBook()
            	text := "14\\r\\n\\tassets:cash\\t7\\r\\n  income:sales   -7.00  \\r\\n15   spaced   memo  \\n  assets:cash  +0.05\\n  income:sales  -.05\\n"
            	_, err := hJournal(t, b, text)
            	hIs(t, "'.05' without a digit before the point is not an amount", err, ErrSyntax)
            	hEq(t, "all or nothing", len(b.Entries()), 4)
            	text = "14\\r\\n\\tassets:cash\\t7\\r\\n  income:sales   -7.00  \\r\\n15   spaced   memo  \\n  assets:cash  +0.05\\n  income:sales  -0.05\\n\\n\\n\\n16 x\\n  assets:cash 0.5\\n  income:sales -.5"
            	_, err = hJournal(t, b, text)
            	hIs(t, "still bad", err, ErrSyntax)
            	text = "14\\r\\n\\tassets:cash\\t7\\r\\n  income:sales   -7.00  \\r\\n15   spaced   memo  \\n  assets:cash  +0.05\\n  income:sales  -0.05\\n\\n\\n\\n16 x\\n  assets:cash 0.5\\n  income:sales -0.50"
            	n, err := hJournal(t, b, text)
            	if err != nil || n != 3 {
            		t.Fatalf("%d %v", n, err)
            	}
            	es := b.Entries()
            	hEq(t, "no memo", []interface{}{es[4].Day, es[4].Memo, es[4].Lines}, []interface{}{14, "", []Line{hLn("assets:cash", 700), hLn("income:sales", -700)}})
            	hEq(t, "memo is the rest of the line, trimmed", es[5].Memo, "spaced   memo")
            	hEq(t, "plus sign and small amounts", es[5].Lines, []Line{hLn("assets:cash", 5), hLn("income:sales", -5)})
            	hEq(t, "half", es[6].Lines[0].Cents, int64(50))
            	n, err = hJournal(t, b, "")
            	hEq(t, "empty", []interface{}{n, err}, []interface{}{0, error(nil)})
            	n, err = hJournal(t, b, "\\n\\n__C__ only a comment\\n")
            	hEq(t, "blank", []interface{}{n, err}, []interface{}{0, error(nil)})
            }

            func TestJournalSyntaxErrors(t *testing.T) {
            	cases := []struct{ text, line string }{
            		{"x 5\\n", "line 1"},
            		{"12abc\\n  assets:cash 1\\n  income:sales -1\\n", "line 1"},
            		{"  assets:cash 5\\n", "line 1"},
            		{"__C__ c\\n\\n  assets:cash 5\\n", "line 3"},
            		{"12 ok\\n  assets:cash 5.123\\n  income:sales -5\\n", "line 2"},
            		{"12 ok\\n  assets:cash\\n  income:sales -5\\n", "line 2"},
            		{"12 ok\\n  assets:cash five\\n", "line 2"},
            		{"12 ok\\n  assets:cash 5\\n  income:sales -5\\nrent 3\\n", "line 4"},
            	}
            	for _, c := range cases {
            		b := hBook()
            		n, err := b.LoadJournal(strings.NewReader(c.text))
            		hIs(t, c.text, err, ErrSyntax)
            		if err == nil || !strings.Contains(err.Error(), c.line+":") {
            			t.Errorf("%q: want %s in %v", c.text, c.line, err)
            		}
            		hEq(t, "result", n, 0)
            		hEq(t, "nothing posted", len(b.Entries()), 4)
            	}
            }

            func TestJournalPostErrorsAreAllOrNothing(t *testing.T) {
            	b := hBook()
            	text := "10 fine\\n  assets:cash 1\\n  income:sales -1\\n\\n11 unknown\\n  assets:cash 1\\n  nope -1\\n"
            	n, err := hJournal(t, b, text)
            	hIs(t, "unknown account", err, ErrUnknownAccount)
            	if err == nil || !strings.Contains(err.Error(), "line 5:") {
            		t.Errorf("want the header line: %v", err)
            	}
            	hEq(t, "result", n, 0)
            	hEq(t, "first entry was rolled back", len(b.Entries()), 4)
            	_, err = hJournal(t, b, "10 off\\n  assets:cash 5\\n  income:sales -4\\n")
            	hIs(t, "unbalanced", err, ErrUnbalanced)
            	_, err = hJournal(t, b, "10 alone\\n  assets:cash 5\\n")
            	hIs(t, "single posting", err, ErrTooFew)
            	_, err = hJournal(t, b, "10 zero\\n  assets:cash 0\\n  income:sales 0.00\\n")
            	hIs(t, "zero amounts", err, ErrBadAmount)
            	_, err = hJournal(t, b, "10 header only\\n")
            	hIs(t, "entry without postings", err, ErrTooFew)
            	hEq(t, "still nothing", len(b.Entries()), 4)
            	if _, err := hJournal(t, b, "10 fine\\n  assets:cash 1\\n  income:sales -1\\n"); err != nil {
            		t.Fatal(err)
            	}
            	hEq(t, "ids continue", b.Entries()[4].ID, 5)
            }
        ''', C=cm),
        cross={
            "close": {"tests": '''
                func TestJournalIntoClosedPeriod(t *testing.T) {
                	b := hBook()
                	b.Close(5)
                	n, err := b.LoadJournal(strings.NewReader("9 later\\n  assets:cash 1\\n  income:sales -1\\n\\n5 too early\\n  assets:cash 1\\n  income:sales -1\\n"))
                	hIs(t, "closed", err, ErrClosed)
                	if err == nil || !strings.Contains(err.Error(), "line 5:") {
                		t.Errorf("want line 5: %v", err)
                	}
                	hEq(t, "result", []interface{}{n, len(b.Entries())}, []interface{}{0, 4})
                }
            '''},
            "budget": {"tests": '''
                func TestJournalHonoursBudgets(t *testing.T) {
                	b := hBook()
                	b.SetBudget("expenses:food", 2000)
                	_, err := b.LoadJournal(strings.NewReader("9 a\\n  expenses:food 3.00\\n  assets:cash -3.00\\n\\n10 b\\n  expenses:food 3.00\\n  assets:cash -3.00\\n"))
                	hIs(t, "second entry is over", err, ErrOverBudget)
                	hEq(t, "all or nothing", len(b.Entries()), 4)
                	if n, err := b.LoadJournal(strings.NewReader("9 a\\n  expenses:food 3.00\\n  assets:cash -3.00\\n")); err != nil || n != 1 {
                		t.Fatalf("%d %v", n, err)
                	}
                }
            '''},
        },
    ))

    S.append(Slice(
        id="currency", title="Accounts in different currencies", d=4,
        pitch=("The club now holds a euro account and a dollar account, but the ledger pretends everything is the same money.",
               "Accounts need a currency, and entries must balance in each currency separately."),
        reqs=(f"Every account has a currency, a 3-letter upper-case code. `Book.OpenIn(name string, kind Kind, currency string) error` opens an account in a given currency (`ErrBadCurrency` for anything that is not three letters `A-Z`, checked first, then everything `Open` checks); plain `Open` uses the package constant `DefaultCurrency`, `\"{cur}\"`. `Book.CurrencyOf(name string) (string, error)` returns it (`ErrUnknownAccount` otherwise). The new code goes into a new file `currency.go`.",
              "An entry must now balance in every currency on its own: the lines on accounts of each currency add up to zero, otherwise `ErrUnbalanced` (the check keeps its place in the order). `Balance` stays in the currency of the account. In `Report` the balance column is preceded by the currency code: the name left-aligned in 24 characters, a space, the currency, a space, and the balance right-aligned in 10 characters."),
        files={
            "currency.go": fmt('''\
package tallybook

import (
	"errors"
	"fmt"
	"regexp"
	"strings"
)

// DefaultCurrency is the currency of accounts opened with Open.
const DefaultCurrency = "__CUR__"

// ErrBadCurrency is returned for a currency code that is not three capital letters.
var ErrBadCurrency = errors.New("tallybook: bad currency code")

var currencyRE = regexp.MustCompile(`^[A-Z]{3}$`)

// OpenIn creates an account in the given currency.
func (b *Book) OpenIn(name string, kind Kind, currency string) error {
	if !currencyRE.MatchString(currency) {
		return fmt.Errorf("%w: %q", ErrBadCurrency, currency)
	}
	if err := b.Open(name, kind); err != nil {
		return err
	}
	b.accounts[strings.TrimSpace(name)].currency = currency
	return nil
}

// CurrencyOf returns the currency of an account.
func (b *Book) CurrencyOf(name string) (string, error) {
	a, ok := b.accounts[name]
	if !ok {
		return "", fmt.Errorf("%w: %q", ErrUnknownAccount, name)
	}
	return a.currency, nil
}
''', CUR=cur),
        },
        code={
            "book.go::account_fields": "currency string",
            "book.go::on_open": "b.accounts[name].currency = DefaultCurrency",
            "book.go::post_vars": "perCurrency := map[string]int64{}",
            "book.go::line_checks": "perCurrency[b.accounts[l.Account].currency] += l.Cents",
            "book.go::balance_check": '''
                _ = sum
                codes := make([]string, 0, len(perCurrency))
                for c := range perCurrency {
                	codes = append(codes, c)
                }
                sort.Strings(codes)
                for _, c := range codes {
                	if perCurrency[c] != 0 {
                		return 0, fmt.Errorf("%w: %s is off by %d", ErrUnbalanced, c, perCurrency[c])
                	}
                }
            ''',
            "book.go::report_line": '''
                sb.WriteString(fmt.Sprintf("%-24s %s %10s\\n", n, b.accounts[n].currency, money(bal)))
            ''',
            "T::base_report": "hEq(t, \"report\", b.Report(), " + json.dumps(_fix_report([(n, c, cur) for n, c in BASE_ROWS2], "%-24s %s %10s\n")) + ")",
        },
        readme=f"## Accounts in different currencies\n\nAccounts have a currency: `OpenIn(name, kind, \"USD\")` (`ErrBadCurrency` unless three capital letters), `Open` uses `DefaultCurrency` (`{cur}`), `CurrencyOf(name)` reads it. Entries must balance per currency (`ErrUnbalanced`) and `Report` shows the code before the balance.\n",
        vtests=fmt('''
            func TestCurrencyBasic(t *testing.T) {
            	b := vBook()
            	if c, err := b.CurrencyOf("assets:cash"); err != nil || c != "__CUR__" {
            		t.Fatalf("got %q %v", c, err)
            	}
            }
        ''', CUR=cur),
        tests=fmt('''
            func TestCurrencies(t *testing.T) {
            	b := hBook()
            	hEq(t, "default", DefaultCurrency, "__CUR__")
            	c, err := b.CurrencyOf("income:sales")
            	hEq(t, "default account", []interface{}{c, err}, []interface{}{"__CUR__", error(nil)})
            	if err := b.OpenIn("assets:other", Asset, "__OTHER__"); err != nil {
            		t.Fatal(err)
            	}
            	if err := b.OpenIn(" equity:fx-other ", Liability, "__OTHER__"); err != nil {
            		t.Fatal(err)
            	}
            	if err := b.OpenIn("equity:fx-home", Liability, "__CUR__"); err != nil {
            		t.Fatal(err)
            	}
            	c, _ = b.CurrencyOf("equity:fx-other")
            	hEq(t, "trimmed name", c, "__OTHER__")
            	_, err = b.CurrencyOf("nope")
            	hIs(t, "unknown", err, ErrUnknownAccount)
            	// an exchange: 100.00 home currency for 110.00 other currency, through two clearing accounts
            	hPost(b, 6, "Exchange", hLn("equity:fx-home", -10000), hLn("assets:cash", 10000), hLn("assets:other", 11000), hLn("equity:fx-other", -11000))
            	got, _ := b.Balance("assets:other")
            	hEq(t, "balance in its own currency", got, int64(11000))
            	n := len(b.Entries())
            	_, err = b.Post(7, "mixed", hLn("assets:cash", 10000), hLn("assets:other", -10000))
            	hIs(t, "balanced only in total", err, ErrUnbalanced)
            	_, err = b.Post(7, "half", hLn("assets:cash", 10000), hLn("income:sales", -10000), hLn("assets:other", 5), hLn("equity:fx-other", -4))
            	hIs(t, "one currency is off", err, ErrUnbalanced)
            	hEq(t, "nothing recorded", len(b.Entries()), n)
            	if _, err := b.Post(7, "fine", hLn("assets:other", 500), hLn("equity:fx-other", -500)); err != nil {
            		t.Errorf("single-currency entry: %v", err)
            	}
            }

            func TestOpenInErrors(t *testing.T) {
            	b := New()
            	for _, bad := range []string{"", "usd", "US", "USDX", "U5D", " USD", "EU$"} {
            		hIs(t, "code "+bad, b.OpenIn("assets:x", Asset, bad), ErrBadCurrency)
            	}
            	hIs(t, "the currency is checked first", b.OpenIn("Bad Name", Asset, "usd"), ErrBadCurrency)
            	hIs(t, "then the name", b.OpenIn("Bad Name", Asset, "USD"), ErrBadName)
            	hIs(t, "then the kind", b.OpenIn("assets:x", Kind(9), "USD"), ErrBadKind)
            	hEq(t, "nothing opened", b.Accounts(), []string{})
            	if err := b.OpenIn("assets:x", Asset, "USD"); err != nil {
            		t.Fatal(err)
            	}
            	hIs(t, "duplicate", b.OpenIn("assets:x", Asset, "EUR"), ErrDuplicate)
            	c, _ := b.CurrencyOf("assets:x")
            	hEq(t, "the original stays", c, "USD")
            }

            func TestReportShowsCurrencies(t *testing.T) {
            	b := hBook()
            	b.OpenIn("assets:other", Asset, "__OTHER__")
            	b.OpenIn("equity:fx-other", Liability, "__OTHER__")
            	hPost(b, 6, "Gift", hLn("assets:other", 1234), hLn("equity:fx-other", -1234))
            	hEq(t, "report", b.Report(), __REPORT__)
            }
        ''', CUR=cur, OTHER=other, REPORT=json.dumps(_fix_report(
            [("assets:bank", 60000, cur), ("assets:cash", 23550, cur), ("assets:other", 1234, other), ("equity:fx-other", -1234, other),
             ("expenses:food", 1450, cur), ("expenses:rent", 40000, cur), ("income:sales", -25000, cur), ("liabilities:loan", -100000, cur)],
            "%-24s %s %10s\n"))),
    ))

    return S


def _fix_report(rows, fmtstr):
    out = ""
    for n, c, cu in rows:
        out += fmtstr % (n, cu, ("-" if c < 0 else "") + "%d.%02d" % (abs(c) // 100, abs(c) % 100))
    return out


BASE_ROWS2 = [("assets:bank", 60000), ("assets:cash", 23550), ("assets:petty", 5), ("expenses:food", 124906),
              ("expenses:rent", 40000), ("income:sales", -25005), ("liabilities:loan", -223456)]
BASE_ROWS = [("assets:bank", 60000), ("assets:cash", 23550), ("expenses:food", 1450), ("expenses:rent", 40000),
             ("income:sales", -25000), ("liabilities:loan", -100000)]

APP = App(
    name="tallybook", lang="go", title="the club ledger library", role="the club treasurer", key="TALLY",
    base={
        "README.md": README + "\n@@blocks features\n",
        "go.mod": langs.go_mod("tallybook"),
        "book.go": BOOK,
        ".gitignore": "*.test\n",
    },
    visible={"book_test.go": VISIBLE},
    hidden={"features_test.go": HIDDEN.replace("__REPORT__", json.dumps(
        _report(BASE_ROWS2)))},
)

register_app("feature-go-tallybook", APP, make_slices, n=18, summary="club ledger: as-of balances, tags, reversals, period close, budgets, journal import, currencies")
