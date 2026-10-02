"""parcelhub (go): a parcel-locker network extended with filters, JSON, policies, expiry, idempotency, events."""
import random

from fx import dd, langs
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # parcelhub

    Bookkeeping for a small network of parcel lockers. A locker bank has compartments in three sizes; a courier
    assigns a parcel to a locker and gets a pickup code, the customer redeems the code. Go, standard library only;
    `go test ./...` runs the tests.

    ## Layout

    * `hub.go`: `Hub`, `Locker`, `Parcel` and the rules.
    * `cli.go`: `Run(hub, args, stdout, stderr) int`, a tiny command interpreter around a hub.
    * `hub_test.go`: tests.

    ## Basics

    * `Size` is `Small`, `Medium` or `Large` (`String()` gives `small`, `medium`, `large`); `ParseSize` is the inverse.
    * `NewHub()`; `AddLocker(id, small, medium, large)` registers a locker with that many compartments of each size
      (error for an empty or duplicate id, or a negative count). `Free(id, size)` counts the free compartments of a
      size (0 for an unknown locker).
    * `Assign(lockerID, Parcel{ID, Size})` puts the parcel into the **smallest free compartment that is at least as big
      as the parcel** and returns the pickup code `<locker>-<n>`, where `n` is a 4-digit counter over the whole hub
      starting at 0001. `ErrFull` when nothing fits, an error for an unknown locker.
    * `Pickup(code)` returns the parcel and frees its compartment; `ErrNoSuchCode` for an unknown code.
    * `Held()` lists the stored parcels ordered by code.

    ## Command line

    `Run` understands `add-locker [--small N] [--medium N] [--large N] ID`, `assign [--size S] LOCKER PARCEL`,
    `pickup CODE` and `status`. Flags come before positional arguments. Errors print `parcelhub: <message>` on the
    error stream and give exit status 1; a missing or unknown command gives status 2. `status` prints one line per
    stored parcel: `CODE  PARCEL  SIZE  LOCKER` (two spaces between columns).
''')

HUB = '''\
// Package parcelhub models a small network of parcel lockers.
package parcelhub

import (
	"errors"
	"fmt"
	"sort"
@@uniq imports
)

// Size is a compartment or parcel size class.
type Size int

const (
	Small Size = iota + 1
	Medium
	Large
)

func (s Size) String() string {
	switch s {
	case Small:
		return "small"
	case Medium:
		return "medium"
	case Large:
		return "large"
	}
	return "unknown"
}

// ParseSize turns "small", "medium" or "large" into a Size.
func ParseSize(s string) (Size, error) {
	switch s {
	case "small":
		return Small, nil
	case "medium":
		return Medium, nil
	case "large":
		return Large, nil
	}
	return 0, fmt.Errorf("unknown size %q", s)
}

var (
	ErrFull       = errors.New("no free compartment")
	ErrNoSuchCode = errors.New("no parcel with that code")
)

// Parcel is something a courier drops off.
type Parcel struct {
	ID   string
	Size Size
}

// Locker is one bank of compartments; Slots counts the FREE compartments of each size.
type Locker struct {
	ID    string
	Slots map[Size]int
}

// Stored is a parcel waiting for pickup.
type Stored struct {
	Parcel Parcel
	Locker string
	Slot   Size // size of the compartment it occupies
	Code   string
@@slot held_fields
}

@@blocks types

// Hub is the whole network.
type Hub struct {
	lockers map[string]*Locker
	order   []string
	held    map[string]*Stored
	seq     int
@@slot hub_fields
}

// NewHub returns an empty hub.
func NewHub() *Hub {
	h := &Hub{lockers: map[string]*Locker{}, held: map[string]*Stored{}}
@@slot new_hub
	return h
}

// AddLocker registers a locker with the given number of compartments of each size.
func (h *Hub) AddLocker(id string, small, medium, large int) error {
	if id == "" {
		return errors.New("empty locker id")
	}
	if _, dup := h.lockers[id]; dup {
		return fmt.Errorf("locker %q already exists", id)
	}
	if small < 0 || medium < 0 || large < 0 {
		return errors.New("negative compartment count")
	}
	h.lockers[id] = &Locker{ID: id, Slots: map[Size]int{Small: small, Medium: medium, Large: large}}
	h.order = append(h.order, id)
	return nil
}

// Free counts the free compartments of one size in a locker.
func (h *Hub) Free(id string, s Size) int {
	if l, ok := h.lockers[id]; ok {
		return l.Slots[s]
	}
	return 0
}

// pickSlot returns the smallest free compartment size that is at least want.
func pickSlot(l *Locker, want Size) (Size, bool) {
	for s := want; s <= Large; s++ {
		if l.Slots[s] > 0 {
			return s, true
		}
	}
	return 0, false
}

// Assign stores a parcel in a locker and returns its pickup code.
func (h *Hub) Assign(lockerID string, p Parcel) (string, error) {
	l, ok := h.lockers[lockerID]
	if !ok {
		return "", fmt.Errorf("unknown locker %q", lockerID)
	}
@@default assign_pick
	slot, ok := pickSlot(l, p.Size)
@@end
	if !ok {
		return "", ErrFull
	}
	l.Slots[slot]--
	h.seq++
	code := fmt.Sprintf("%s-%04d", lockerID, h.seq)
	h.held[code] = &Stored{Parcel: p, Locker: lockerID, Slot: slot, Code: code}
@@slot on_assign
	return code, nil
}

// Pickup hands a parcel over and frees its compartment.
func (h *Hub) Pickup(code string) (Parcel, error) {
	e, ok := h.held[code]
	if !ok {
		return Parcel{}, ErrNoSuchCode
	}
	delete(h.held, code)
	h.lockers[e.Locker].Slots[e.Slot]++
@@slot on_pickup
	return e.Parcel, nil
}

// Held lists the stored parcels ordered by pickup code.
func (h *Hub) Held() []Stored {
	out := make([]Stored, 0, len(h.held))
	for _, e := range h.held {
		out = append(out, *e)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Code < out[j].Code })
	return out
}

@@blocks methods
'''

CLI = '''\
package parcelhub

import (
	"errors"
	"flag"
	"fmt"
	"io"
@@uniq imports
)

// Run executes one command against the hub and returns the exit status.
func Run(h *Hub, args []string, out, errw io.Writer) int {
	if len(args) == 0 {
		fmt.Fprintln(errw, "parcelhub: missing command")
		return 2
	}
	cmd, rest := args[0], args[1:]
	var err error
	switch cmd {
	case "add-locker":
		err = cmdAddLocker(h, rest, out)
	case "assign":
		err = cmdAssign(h, rest, out)
	case "pickup":
		err = cmdPickup(h, rest, out)
	case "status":
		err = cmdStatus(h, rest, out)
@@slot cases
	default:
		fmt.Fprintf(errw, "parcelhub: unknown command %q\\n", cmd)
		return 2
	}
	if err != nil {
		fmt.Fprintf(errw, "parcelhub: %v\\n", err)
		return 1
	}
	return 0
}

func newFlags(name string) *flag.FlagSet {
	fs := flag.NewFlagSet(name, flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	return fs
}

func cmdAddLocker(h *Hub, args []string, out io.Writer) error {
	fs := newFlags("add-locker")
	small := fs.Int("small", 0, "small compartments")
	medium := fs.Int("medium", 0, "medium compartments")
	large := fs.Int("large", 0, "large compartments")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if fs.NArg() != 1 {
		return errors.New("usage: add-locker [--small N] [--medium N] [--large N] ID")
	}
	if err := h.AddLocker(fs.Arg(0), *small, *medium, *large); err != nil {
		return err
	}
	fmt.Fprintf(out, "locker %s: %d small, %d medium, %d large\\n", fs.Arg(0), *small, *medium, *large)
	return nil
}

func cmdAssign(h *Hub, args []string, out io.Writer) error {
	fs := newFlags("assign")
	size := fs.String("size", "small", "small, medium or large")
@@slot assign_flags
	if err := fs.Parse(args); err != nil {
		return err
	}
	if fs.NArg() != 2 {
		return errors.New("usage: assign [--size S] LOCKER PARCEL")
	}
	sz, err := ParseSize(*size)
	if err != nil {
		return err
	}
@@slot assign_post
@@default assign_call
	code, err := h.Assign(fs.Arg(0), Parcel{ID: fs.Arg(1), Size: sz})
@@end
	if err != nil {
		return err
	}
	fmt.Fprintf(out, "%s -> %s\\n", fs.Arg(1), code)
	return nil
}

func cmdPickup(h *Hub, args []string, out io.Writer) error {
	if len(args) != 1 {
		return errors.New("usage: pickup CODE")
	}
	p, err := h.Pickup(args[0])
	if err != nil {
		return err
	}
	fmt.Fprintf(out, "picked up %s\\n", p.ID)
	return nil
}

func cmdStatus(h *Hub, args []string, out io.Writer) error {
	fs := newFlags("status")
@@slot status_flags
	if err := fs.Parse(args); err != nil {
		return err
	}
	held := h.Held()
@@slot status_filter
@@default status_render
	for _, e := range held {
		fmt.Fprintf(out, "%s  %s  %s  %s\\n", e.Code, e.Parcel.ID, e.Parcel.Size, e.Locker)
	}
@@end
	return nil
}

@@blocks commands
'''

VISIBLE = '''\
package parcelhub

import (
	"bytes"
	"errors"
	"testing"
@@uniq imports
)

func vHub(t *testing.T) *Hub {
	t.Helper()
	h := NewHub()
	if err := h.AddLocker("north", 2, 1, 1); err != nil {
		t.Fatal(err)
	}
	if err := h.AddLocker("south", 1, 2, 0); err != nil {
		t.Fatal(err)
	}
	return h
}

func vRun(h *Hub, args ...string) (int, string, string) {
	var out, errw bytes.Buffer
	code := Run(h, args, &out, &errw)
	return code, out.String(), errw.String()
}

func TestAssignPicksSmallestFit(t *testing.T) {
	h := vHub(t)
	code, err := h.Assign("north", Parcel{ID: "P1", Size: Medium})
	if err != nil || code != "north-0001" {
		t.Fatalf("got %q, %v", code, err)
	}
	if h.Free("north", Medium) != 0 || h.Free("north", Large) != 1 {
		t.Errorf("medium parcel should use the medium compartment")
	}
	code, _ = h.Assign("north", Parcel{ID: "P2", Size: Medium})
	if code != "north-0002" || h.Free("north", Large) != 0 {
		t.Errorf("second medium parcel should overflow into the large compartment, got %q", code)
	}
	if _, err := h.Assign("north", Parcel{ID: "P3", Size: Medium}); !errors.Is(err, ErrFull) {
		t.Errorf("expected ErrFull, got %v", err)
	}
}

func TestPickup(t *testing.T) {
	h := vHub(t)
	code, _ := h.Assign("south", Parcel{ID: "P9", Size: Small})
	p, err := h.Pickup(code)
	if err != nil || p.ID != "P9" {
		t.Fatalf("got %+v, %v", p, err)
	}
	if h.Free("south", Small) != 1 {
		t.Errorf("compartment not freed")
	}
	if _, err := h.Pickup(code); !errors.Is(err, ErrNoSuchCode) {
		t.Errorf("second pickup: %v", err)
	}
}

func TestCLIBasics(t *testing.T) {
	h := NewHub()
	if code, out, _ := vRun(h, "add-locker", "--small", "1", "--large", "1", "dock"); code != 0 || out != "locker dock: 1 small, 0 medium, 1 large\\n" {
		t.Fatalf("add-locker: %d %q", code, out)
	}
	if code, out, _ := vRun(h, "assign", "--size", "large", "dock", "BOX1"); code != 0 || out != "BOX1 -> dock-0001\\n" {
		t.Fatalf("assign: %d %q", code, out)
	}
	if _, out, _ := vRun(h, "status"); out != "dock-0001  BOX1  large  dock\\n" {
		t.Fatalf("status: %q", out)
	}
	if code, _, errs := vRun(h, "pickup", "nope"); code != 1 || errs != "parcelhub: no parcel with that code\\n" {
		t.Fatalf("pickup: %d %q", code, errs)
	}
	if code, _, _ := vRun(h, "bogus"); code != 2 {
		t.Fatalf("unknown command should give status 2, got %d", code)
	}
}
@@blocks tests
'''

HIDDEN = '''\
package parcelhub

import (
	"bytes"
	"errors"
	"reflect"
	"strings"
	"testing"
@@uniq imports
)

var _ = errors.Is
var _ = strings.Contains

func hHub(t *testing.T) *Hub {
	t.Helper()
	h := NewHub()
	if err := h.AddLocker("north", 2, 1, 1); err != nil {
		t.Fatal(err)
	}
	if err := h.AddLocker("south", 1, 2, 0); err != nil {
		t.Fatal(err)
	}
	return h
}

func hRun(h *Hub, args ...string) (int, string, string) {
	var out, errw bytes.Buffer
	code := Run(h, args, &out, &errw)
	return code, out.String(), errw.String()
}

func hAssign(t *testing.T, h *Hub, locker, id string, s Size) string {
	t.Helper()
	code, err := h.Assign(locker, Parcel{ID: id, Size: s})
	if err != nil {
		t.Fatalf("assign %s: %v", id, err)
	}
	return code
}

func hEq(t *testing.T, name string, got, want interface{}) {
	t.Helper()
	if !reflect.DeepEqual(got, want) {
		t.Errorf("%s: got %v, want %v", name, got, want)
	}
}

func hIDs(held []Stored) []string {
	ids := []string{}
	for _, e := range held {
		ids = append(ids, e.Parcel.ID)
	}
	return ids
}

func TestBaseRules(t *testing.T) {
	h := hHub(t)
	hEq(t, "free", []int{h.Free("north", Small), h.Free("north", Medium), h.Free("north", Large), h.Free("nowhere", Small)}, []int{2, 1, 1, 0})
	c1 := hAssign(t, h, "north", "P1", Small)
	c2 := hAssign(t, h, "south", "P2", Small)
	c3 := hAssign(t, h, "north", "P3", Small)
	hEq(t, "codes", []string{c1, c2, c3}, []string{"north-0001", "south-0002", "north-0003"})
	c4 := hAssign(t, h, "north", "P4", Large)
	hEq(t, "large code", c4, "north-0004")
	if _, err := h.Assign("north", Parcel{ID: "P5", Size: Large}); !errors.Is(err, ErrFull) {
		t.Errorf("second large parcel: %v", err)
	}
	if _, err := h.Assign("mars", Parcel{ID: "P6", Size: Small}); err == nil || errors.Is(err, ErrFull) {
		t.Errorf("unknown locker should be a distinct error, got %v", err)
	}
	hEq(t, "held", hIDs(h.Held()), []string{"P1", "P3", "P4", "P2"})
	if err := h.AddLocker("north", 1, 1, 1); err == nil {
		t.Error("duplicate locker id accepted")
	}
	if err := h.AddLocker("", 1, 1, 1); err == nil {
		t.Error("empty locker id accepted")
	}
	if err := h.AddLocker("east", -1, 0, 0); err == nil {
		t.Error("negative count accepted")
	}
}
@@blocks tests
'''


def make_slices(rng: random.Random):
    hold = rng.choice([2, 3, 5])
    limits = rng.choice([((10, 20, 30), (20, 35, 50), (40, 60, 80)), ((8, 25, 35), (20, 30, 45), (38, 55, 70)), ((12, 22, 30), (24, 38, 52), (40, 58, 75))])
    (s1, s2, s3) = limits
    nonmatch = rng.choice(["roomy", "exact"])
    S = []

    S.append(Slice(
        id="status-locker", title="Status per locker", d=1,
        pitch=("The couriers only care about the locker they are standing in front of.",
               "`status` dumps every parcel in the network, which is useless when one site has a problem."),
        reqs=("`Hub.HeldAt(lockerID) ([]Stored, error)` returns the stored parcels of one locker ordered by code (an empty, non-nil slice when there are none); an unknown locker is an error.",
              "`status --locker ID` prints only that locker's parcels, in the usual format. An unknown locker is an ordinary command error (`parcelhub: unknown locker \"ID\"`, status 1).",
              "`status` without the flag is unchanged."),
        code={
            "hub.go::methods": '''
                // HeldAt lists the parcels stored in one locker, ordered by code.
                func (h *Hub) HeldAt(lockerID string) ([]Stored, error) {
                	if _, ok := h.lockers[lockerID]; !ok {
                		return nil, fmt.Errorf("unknown locker %q", lockerID)
                	}
                	out := []Stored{}
                	for _, e := range h.Held() {
                		if e.Locker == lockerID {
                			out = append(out, e)
                		}
                	}
                	return out, nil
                }
            ''',
            "cli.go::status_flags": 'locker := fs.String("locker", "", "only parcels in this locker")',
            "cli.go::status_filter": '''
                if *locker != "" {
                	var err error
                	if held, err = h.HeldAt(*locker); err != nil {
                		return err
                	}
                }
            ''',
        },
        readme=dd('''
            ## Per-locker status

            `Hub.HeldAt(lockerID)` lists one locker's parcels ordered by code (error for an unknown locker). `status --locker ID`
            prints just those lines.
        '''),
        vtests='''
            func TestHeldAtBasic(t *testing.T) {
            	h := vHub(t)
            	h.Assign("north", Parcel{ID: "P1", Size: Small})
            	got, err := h.HeldAt("north")
            	if err != nil || len(got) != 1 {
            		t.Fatalf("got %v, %v", got, err)
            	}
            }
        ''',
        tests='''
            func TestHeldAt(t *testing.T) {
            	h := hHub(t)
            	hAssign(t, h, "north", "P1", Small)
            	hAssign(t, h, "south", "P2", Medium)
            	hAssign(t, h, "north", "P3", Large)
            	got, err := h.HeldAt("north")
            	if err != nil {
            		t.Fatal(err)
            	}
            	hEq(t, "north", hIDs(got), []string{"P1", "P3"})
            	got, _ = h.HeldAt("south")
            	hEq(t, "south", hIDs(got), []string{"P2"})
            	if _, err := h.HeldAt("nowhere"); err == nil {
            		t.Error("unknown locker should be an error")
            	}
            	h2 := hHub(t)
            	empty, err := h2.HeldAt("south")
            	if err != nil || empty == nil || len(empty) != 0 {
            		t.Errorf("empty locker: %#v, %v", empty, err)
            	}
            }

            func TestStatusLockerFlag(t *testing.T) {
            	h := hHub(t)
            	hAssign(t, h, "north", "P1", Small)
            	hAssign(t, h, "south", "P2", Medium)
            	code, out, _ := hRun(h, "status", "--locker", "south")
            	hEq(t, "code", code, 0)
            	hEq(t, "out", out, "south-0002  P2  medium  south\\n")
            	code, out, errs := hRun(h, "status", "--locker", "nowhere")
            	hEq(t, "code", code, 1)
            	hEq(t, "out", out, "")
            	if !strings.Contains(errs, "unknown locker") {
            		t.Errorf("stderr %q", errs)
            	}
            	_, out, _ = hRun(h, "status")
            	hEq(t, "all lines", strings.Count(out, "\\n"), 2)
            }
        ''',
    ))

    S.append(Slice(
        id="usage", title="Locker usage report", d=2,
        pitch=("Operations wants to know which lockers are filling up.",
               "We keep getting asked how full each locker bank is."),
        reqs=("`Hub.Usage() []LockerUsage` returns one entry per locker in registration order: `LockerUsage{ID string; Used, Total int}`, where `Total` is the number of compartments of all sizes and `Used` the occupied ones.",
              "`usage` (a new command) prints one line per locker, `ID  USED/TOTAL  PCT%` (two spaces between columns), the percentage being `100*Used/Total` rounded to the nearest integer with halves rounding up; a locker with no compartments shows `0%`."),
        code={
            "hub.go::types": '''
                // LockerUsage is how full one locker is.
                type LockerUsage struct {
                	ID          string
                	Used, Total int
                }
            ''',
            "hub.go::methods": '''
                // Usage reports the occupancy of every locker in registration order.
                func (h *Hub) Usage() []LockerUsage {
                	out := make([]LockerUsage, 0, len(h.order))
                	for _, id := range h.order {
                		l := h.lockers[id]
                		free := l.Slots[Small] + l.Slots[Medium] + l.Slots[Large]
                		used := 0
                		for _, e := range h.held {
                			if e.Locker == id {
                				used++
                			}
                		}
                		out = append(out, LockerUsage{ID: id, Used: used, Total: free + used})
                	}
                	return out
                }
            ''',
            "cli.go::cases": '''
                case "usage":
                	err = cmdUsage(h, rest, out)
            ''',
            "cli.go::commands": '''
                func cmdUsage(h *Hub, args []string, out io.Writer) error {
                	if len(args) != 0 {
                		return errors.New("usage: usage")
                	}
                	for _, u := range h.Usage() {
                		pct := 0
                		if u.Total > 0 {
                			pct = (200*u.Used + u.Total) / (2 * u.Total)
                		}
                		fmt.Fprintf(out, "%s  %d/%d  %d%%\\n", u.ID, u.Used, u.Total, pct)
                	}
                	return nil
                }
            ''',
        },
        readme=dd('''
            ## Usage report

            `Hub.Usage()` returns `[]LockerUsage{ID, Used, Total}` in registration order. The `usage` command prints
            `ID  USED/TOTAL  PCT%` per locker (percentage rounded half up, `0%` for an empty locker bank).
        '''),
        vtests='''
            func TestUsageBasic(t *testing.T) {
            	h := vHub(t)
            	if u := h.Usage(); len(u) != 2 || u[0].Total != 4 {
            		t.Fatalf("usage %+v", u)
            	}
            }
        ''',
        tests='''
            func TestUsage(t *testing.T) {
            	h := hHub(t)
            	hEq(t, "fresh", h.Usage(), []LockerUsage{{"north", 0, 4}, {"south", 0, 3}})
            	hAssign(t, h, "north", "P1", Small)
            	hAssign(t, h, "south", "P2", Small)
            	hAssign(t, h, "south", "P3", Medium)
            	hEq(t, "used", h.Usage(), []LockerUsage{{"north", 1, 4}, {"south", 2, 3}})
            	code := hAssign(t, h, "north", "P4", Large)
            	h.Pickup(code)
            	hEq(t, "after pickup", h.Usage()[0], LockerUsage{"north", 1, 4})
            }

            func TestUsageCommand(t *testing.T) {
            	h := hHub(t)
            	hRun(h, "add-locker", "empty")
            	hAssign(t, h, "north", "P1", Small)
            	hAssign(t, h, "south", "P2", Small)
            	code, out, _ := hRun(h, "usage")
            	hEq(t, "code", code, 0)
            	hEq(t, "out", out, "north  1/4  25%\\nsouth  1/3  33%\\nempty  0/0  0%\\n")
            	hAssign(t, h, "north", "P4", Small)
            	hAssign(t, h, "north", "P5", Small)
            	hAssign(t, h, "north", "P6", Medium)
            	_, out, _ = hRun(h, "usage")
            	hEq(t, "first line", strings.SplitN(out, "\\n", 2)[0], "north  4/4  100%")
            }

            func TestUsageRoundsHalfUp(t *testing.T) {
            	h := NewHub()
            	h.AddLocker("w", 8, 0, 0)
            	hAssign(t, h, "w", "a", Small)
            	_, out, _ := hRun(h, "usage")
            	hEq(t, "1/8", out, "w  1/8  13%\\n")
            }
        ''',
    ))

    S.append(Slice(
        id="status-json", title="JSON status", d=2,
        pitch=("The monitoring script scrapes the status lines with cut; JSON would be much safer.",
               "Dashboards want the status in a machine-readable form."),
        reqs=("`status --json` prints the stored parcels as one JSON array (followed by a newline), ordered by code: objects with the string fields `code`, `parcel`, `size` (`small`, `medium` or `large`: the size of the parcel, not of the compartment) and `locker`.",
              "With nothing stored the output is `[]` (never `null`). Without the flag `status` is unchanged."),
        code={
            "cli.go::imports": '"encoding/json"',
            "cli.go::status_flags": 'asJSON := fs.Bool("json", false, "print JSON")',
            "cli.go::status_render": '''
                if *asJSON {
                	rows := []map[string]string{}
                	for _, e := range held {
                		rows = append(rows, map[string]string{"code": e.Code, "parcel": e.Parcel.ID, "size": e.Parcel.Size.String(), "locker": e.Locker})
                	}
                	return json.NewEncoder(out).Encode(rows)
                }
                for _, e := range held {
                	fmt.Fprintf(out, "%s  %s  %s  %s\\n", e.Code, e.Parcel.ID, e.Parcel.Size, e.Locker)
                }
            ''',
        },
        readme=dd('''
            ## JSON status

            `status --json` prints a JSON array of `{"code", "parcel", "size", "locker"}` objects ordered by code (`[]` when
            empty).
        '''),
        vtests='''
            func TestStatusJSONFlagAccepted(t *testing.T) {
            	h := vHub(t)
            	if code, out, _ := vRun(h, "status", "--json"); code != 0 || out != "[]\\n" {
            		t.Fatalf("%d %q", code, out)
            	}
            }
        ''',
        tests='''
            func TestStatusJSON(t *testing.T) {
            	h := hHub(t)
            	_, out, _ := hRun(h, "status", "--json")
            	hEq(t, "empty", strings.TrimSpace(out), "[]")
            	hAssign(t, h, "north", "P1", Small)
            	hAssign(t, h, "south", "P2", Medium)
            	code, out, _ := hRun(h, "status", "--json")
            	hEq(t, "code", code, 0)
            	var rows []map[string]string
            	if err := json.Unmarshal([]byte(out), &rows); err != nil {
            		t.Fatalf("not JSON: %v\\n%s", err, out)
            	}
            	hEq(t, "rows", rows, []map[string]string{
            		{"code": "north-0001", "parcel": "P1", "size": "small", "locker": "north"},
            		{"code": "south-0002", "parcel": "P2", "size": "medium", "locker": "south"},
            	})
            	if !strings.HasSuffix(out, "\\n") {
            		t.Error("output should end with a newline")
            	}
            }
        ''',
        cross={
            "status-locker": {"tests": '''
                func TestStatusJSONLocker(t *testing.T) {
                	h := hHub(t)
                	hAssign(t, h, "north", "P1", Small)
                	hAssign(t, h, "south", "P2", Medium)
                	_, out, _ := hRun(h, "status", "--json", "--locker", "south")
                	var rows []map[string]string
                	if err := json.Unmarshal([]byte(out), &rows); err != nil || len(rows) != 1 || rows[0]["parcel"] != "P2" {
                		t.Errorf("rows %v, err %v", rows, err)
                	}
                	_, out, _ = hRun(h, "status", "--locker", "north", "--json")
                	if strings.Contains(out, "P2") {
                		t.Errorf("filter ignored: %s", out)
                	}
                }
            '''},
        },
    ))
    S[-1].code["T::imports"] = '"encoding/json"'

    S.append(Slice(
        id="dims", title="Size from dimensions", d=2,
        pitch=("Couriers measure the parcel, they do not decide on small, medium or large.",
               "Nobody at the depot knows the size classes by heart; they just have a tape measure."),
        reqs=(f"`ClassifyDims(w, h, d int) (Size, error)` classifies a parcel from its dimensions in centimetres. Sort the three numbers ascending as `a <= b <= c`; the parcel is `Small` if `a <= {s1[0]}`, `b <= {s1[1]}` and `c <= {s1[2]}`, else `Medium` if `a <= {s2[0]}`, `b <= {s2[1]}` and `c <= {s2[2]}`, else `Large` if `a <= {s3[0]}`, `b <= {s3[1]}` and `c <= {s3[2]}`. Anything bigger, or a dimension that is zero or negative, is an error. The order in which the dimensions are given does not matter.",
              "`assign --dims WxHxD LOCKER PARCEL` (for example `--dims 12x30x8`, three positive integers separated by a lower-case `x`) classifies the parcel instead of `--size`. A malformed value or an oversized parcel is an ordinary command error (status 1). Giving both `--size` and `--dims` is an error too."),
        readme=dd('''
            ## Size from dimensions

            `ClassifyDims(w, h, d)` maps centimetre dimensions (any order) to a `Size`, or an error when a dimension is not
            positive or the parcel is too big. `assign --dims WxHxD` uses it instead of `--size`.
        '''),
        vtests='''
            func TestClassifyDimsBasic(t *testing.T) {
            	if s, err := ClassifyDims(1, 1, 1); err != nil || s != Small {
            		t.Fatalf("%v %v", s, err)
            	}
            }
        ''',
        tests=fmt('''
            func TestClassifyDims(t *testing.T) {
            	cases := []struct {
            		w, h, d int
            		want    Size
            	}{
            		{1, 1, 1, Small},
            		{__S0__, __S1__, __S2__, Small},
            		{__S2__, __S0__, __S1__, Small},
            		{__S0__ + 1, __S1__, __S2__, Medium},
            		{__S0__, __S1__, __S2__ + 1, Medium},
            		{__M2__, __M0__, __M1__, Medium},
            		{__M0__ + 1, __M1__, __M2__, Large},
            		{__L1__, __L2__, __L0__, Large},
            	}
            	for _, c := range cases {
            		got, err := ClassifyDims(c.w, c.h, c.d)
            		if err != nil || got != c.want {
            			t.Errorf("ClassifyDims(%d,%d,%d) = %v, %v; want %v", c.w, c.h, c.d, got, err, c.want)
            		}
            	}
            	for _, bad := range [][3]int{{0, 5, 5}, {5, -1, 5}, {__L0__ + 1, __L0__ + 1, __L0__ + 1}, {1, __L1__ + 1, __L1__ + 1}, {1, 1, __L2__ + 1}} {
            		if s, err := ClassifyDims(bad[0], bad[1], bad[2]); err == nil {
            			t.Errorf("ClassifyDims(%v) = %v, want an error", bad, s)
            		}
            	}
            }

            func TestAssignDimsFlag(t *testing.T) {
            	h := hHub(t)
            	code, out, _ := hRun(h, "assign", "--dims", "__S2__x__S0__x1", "north", "BOX")
            	hEq(t, "code", code, 0)
            	hEq(t, "out", out, "BOX -> north-0001\\n")
            	hEq(t, "slot", h.Free("north", Small), 1)
            	code, _, _ = hRun(h, "assign", "--dims", "__M2__x__M1__x__M0__", "north", "BOX2")
            	hEq(t, "medium code", code, 0)
            	hEq(t, "medium slot", h.Free("north", Medium), 0)
            	for _, args := range [][]string{
            		{"assign", "--dims", "10x20", "north", "X"},
            		{"assign", "--dims", "axbxc", "north", "X"},
            		{"assign", "--dims", "0x5x5", "north", "X"},
            		{"assign", "--dims", "500x500x500", "north", "X"},
            		{"assign", "--dims", "1x1x1", "--size", "small", "north", "X"},
            	} {
            		code, out, errs := hRun(h, args...)
            		if code != 1 || out != "" || !strings.HasPrefix(errs, "parcelhub: ") {
            			t.Errorf("%v: %d %q %q", args, code, out, errs)
            		}
            	}
            	hEq(t, "nothing stored by failures", len(h.Held()), 2)
            }
        ''', S0=s1[0], S1=s1[1], S2=s1[2], M0=s2[0], M1=s2[1], M2=s2[2], L0=s3[0], L1=s3[1], L2=s3[2]),
    ))
    # new source file and CLI hooks for the dims slice
    S[-1].files = {"dims.go": dd(f'''
        package parcelhub

        import (
        	"errors"
        	"sort"
        )

        // ClassifyDims picks the size class of a parcel from its dimensions in centimetres.
        func ClassifyDims(w, h, d int) (Size, error) {{
        	dims := []int{{w, h, d}}
        	for _, v := range dims {{
        		if v <= 0 {{
        			return 0, errors.New("dimensions must be positive")
        		}}
        	}}
        	sort.Ints(dims)
        	limits := []struct {{
        		size Size
        		max  [3]int
        	}}{{
        		{{Small, [3]int{{{s1[0]}, {s1[1]}, {s1[2]}}}}},
        		{{Medium, [3]int{{{s2[0]}, {s2[1]}, {s2[2]}}}}},
        		{{Large, [3]int{{{s3[0]}, {s3[1]}, {s3[2]}}}}},
        	}}
        	for _, l := range limits {{
        		if dims[0] <= l.max[0] && dims[1] <= l.max[1] && dims[2] <= l.max[2] {{
        			return l.size, nil
        		}}
        	}}
        	return 0, errors.New("parcel is too big for any compartment")
        }}
    ''')}
    S[-1].code = {
        "cli.go::assign_flags": 'dims := fs.String("dims", "", "parcel dimensions WxHxD in cm (instead of --size)")',
        "cli.go::assign_post": '''
            if *dims != "" {
            	both := false
            	fs.Visit(func(f *flag.Flag) {
            		if f.Name == "size" {
            			both = true
            		}
            	})
            	if both {
            		return errors.New("use either --size or --dims, not both")
            	}
            	var w, hh, dd int
            	if _, err := fmt.Sscanf(*dims, "%dx%dx%d", &w, &hh, &dd); err != nil {
            		return fmt.Errorf("bad --dims %q (want WxHxD)", *dims)
            	}
            	if sz, err = ClassifyDims(w, hh, dd); err != nil {
            		return err
            	}
            }
        ''',
    }

    S.append(Slice(
        id="fit-policy", title="Compartment policies", d=3,
        pitch=("The north depot wants the biggest free compartment used first so that small ones stay free for walk-ins; another site wants exact fits only.",
               "How a compartment is chosen is hard-wired; operations wants to switch the rule per hub."),
        reqs=("`Hub.SetPolicy(name string) error` selects how `Assign` picks a compartment: `smallest` (the default and today's rule: the smallest free compartment that fits), `roomy` (the largest free compartment, which always fits) and `exact` (only a free compartment of exactly the parcel's size). An unknown name is an error and keeps the current policy.",
              "Everything else about `Assign` (codes, `ErrFull` when no compartment qualifies, the counter) is unchanged: a failed assignment does not consume a code number. The policy applies to the whole hub and to later assignments only.",
              "`policy NAME` (a new command) sets it and prints `policy NAME`; an unknown name is an ordinary command error (status 1)."),
        code={
            "hub.go::hub_fields": "policy string",
            "hub.go::new_hub": 'h.policy = "smallest"',
            "hub.go::assign_pick": "slot, ok := h.pick(l, p.Size)",
            "hub.go::methods": '''
                // SetPolicy chooses how Assign picks a compartment: smallest, roomy or exact.
                func (h *Hub) SetPolicy(name string) error {
                	switch name {
                	case "smallest", "roomy", "exact":
                		h.policy = name
                		return nil
                	}
                	return fmt.Errorf("unknown policy %q", name)
                }

                func (h *Hub) pick(l *Locker, want Size) (Size, bool) {
                	switch h.policy {
                	case "exact":
                		return want, l.Slots[want] > 0
                	case "roomy":
                		for s := Large; s >= want; s-- {
                			if l.Slots[s] > 0 {
                				return s, true
                			}
                		}
                		return 0, false
                	}
                	return pickSlot(l, want)
                }
            ''',
            "cli.go::cases": '''
                case "policy":
                	err = cmdPolicy(h, rest, out)
            ''',
            "cli.go::commands": '''
                func cmdPolicy(h *Hub, args []string, out io.Writer) error {
                	if len(args) != 1 {
                		return errors.New("usage: policy NAME")
                	}
                	if err := h.SetPolicy(args[0]); err != nil {
                		return err
                	}
                	fmt.Fprintf(out, "policy %s\\n", args[0])
                	return nil
                }
            ''',
        },
        readme=dd('''
            ## Compartment policies

            `Hub.SetPolicy(name)` picks the rule `Assign` uses: `smallest` (default), `roomy` (largest free compartment) or
            `exact` (same size only). Unknown names are errors. CLI: `policy NAME`.
        '''),
        vtests='''
            func TestPolicyDefault(t *testing.T) {
            	h := vHub(t)
            	if err := h.SetPolicy("smallest"); err != nil {
            		t.Fatal(err)
            	}
            }
        ''',
        tests='''
            func TestPolicyRoomy(t *testing.T) {
            	h := hHub(t)
            	if err := h.SetPolicy("roomy"); err != nil {
            		t.Fatal(err)
            	}
            	hAssign(t, h, "north", "P1", Small)
            	hEq(t, "large used", []int{h.Free("north", Small), h.Free("north", Medium), h.Free("north", Large)}, []int{2, 1, 0})
            	hAssign(t, h, "north", "P2", Small)
            	hEq(t, "medium next", []int{h.Free("north", Small), h.Free("north", Medium), h.Free("north", Large)}, []int{2, 0, 0})
            	hAssign(t, h, "north", "P3", Small)
            	hEq(t, "then small", h.Free("north", Small), 1)
            	hAssign(t, h, "south", "P4", Medium)
            	hEq(t, "medium parcel never shrinks", h.Free("south", Medium), 1)
            }

            func TestPolicyExact(t *testing.T) {
            	h := hHub(t)
            	h.SetPolicy("exact")
            	hAssign(t, h, "north", "P1", Medium)
            	if _, err := h.Assign("north", Parcel{ID: "P2", Size: Medium}); !errors.Is(err, ErrFull) {
            		t.Errorf("exact policy must not overflow, got %v", err)
            	}
            	hEq(t, "large untouched", h.Free("north", Large), 1)
            	code := hAssign(t, h, "south", "P3", Small)
            	hEq(t, "failed assign burns no code", code, "south-0002")
            }

            func TestPolicyErrorsAndCommand(t *testing.T) {
            	h := hHub(t)
            	h.SetPolicy("roomy")
            	if err := h.SetPolicy("bogus"); err == nil {
            		t.Fatal("unknown policy accepted")
            	}
            	hAssign(t, h, "north", "P1", Small)
            	hEq(t, "kept roomy", h.Free("north", Large), 0)
            	code, out, _ := hRun(h, "policy", "exact")
            	hEq(t, "cli", []interface{}{code, out}, []interface{}{0, "policy exact\\n"})
            	code, out, errs := hRun(h, "policy", "bogus")
            	if code != 1 || out != "" || !strings.HasPrefix(errs, "parcelhub: ") {
            		t.Errorf("bad policy: %d %q %q", code, out, errs)
            	}
            	h2 := NewHub()
            	h2.AddLocker("x", 1, 0, 1)
            	hAssign(t, h2, "x", "A", Small)
            	hEq(t, "default is smallest", h2.Free("x", Small), 0)
            }
        ''',
    ))

    S.append(Slice(
        id="expiry", title="Pickup deadline", d=3,
        pitch=("Parcels that nobody collects block compartments for weeks.",
               "Compartments stay occupied by parcels that were never picked up; the hub needs a deadline."),
        reqs=(f"The hub has a day counter: `Hub.SetDay(n int) error` (days are plain integers starting at 0; going backwards is an error) and a hold period `Hub.SetHoldDays(n int) error` (at least 1, default {hold}).",
              "A stored parcel remembers the day it was assigned: the `Stored` struct gets an `int` field `Since`.",
              "`Hub.Sweep() []Parcel` removes every stored parcel whose age `day - Since` is greater than the hold period (exactly equal is still fine), frees their compartments and returns the removed parcels ordered by pickup code. Their codes stop working (`Pickup` gives `ErrNoSuchCode`).",
              "Commands: `day N` sets the day and prints `day N`; `sweep` prints one line `expired CODE PARCEL` per removed parcel (in code order) and then `swept K`. Errors are ordinary command errors (status 1)."),
        code={
            "hub.go::held_fields": "Since int // day the parcel was assigned",
            "hub.go::hub_fields": "today    int\nholdDays int",
            "hub.go::new_hub": f"h.holdDays = {hold}",
            "hub.go::on_assign": "h.held[code].Since = h.today",
            "hub.go::methods": '''
                // SetDay moves the hub's day counter forward.
                func (h *Hub) SetDay(n int) error {
                	if n < h.today {
                		return fmt.Errorf("day %d is before day %d", n, h.today)
                	}
                	h.today = n
                	return nil
                }

                // SetHoldDays sets how many days a parcel may wait for pickup.
                func (h *Hub) SetHoldDays(n int) error {
                	if n < 1 {
                		return errors.New("hold period must be at least 1 day")
                	}
                	h.holdDays = n
                	return nil
                }

                // Sweep removes parcels that waited longer than the hold period.
                func (h *Hub) Sweep() []Parcel {
                	var gone []Parcel
                	for _, e := range h.sweep() {
                		gone = append(gone, e.Parcel)
                	}
                	return gone
                }

                func (h *Hub) sweep() []Stored {
                	var gone []Stored
                	for _, e := range h.Held() {
                		if h.today-e.Since > h.holdDays {
                			delete(h.held, e.Code)
                			h.lockers[e.Locker].Slots[e.Slot]++
                			gone = append(gone, e)
                			@@slot on_expire
                		}
                	}
                	return gone
                }
            ''',
            "cli.go::imports": '"strconv"',
            "cli.go::cases": '''
                case "day":
                	err = cmdDay(h, rest, out)
                case "sweep":
                	err = cmdSweep(h, rest, out)
            ''',
            "cli.go::commands": '''
                func cmdDay(h *Hub, args []string, out io.Writer) error {
                	if len(args) != 1 {
                		return errors.New("usage: day N")
                	}
                	n, err := strconv.Atoi(args[0])
                	if err != nil {
                		return fmt.Errorf("bad day %q", args[0])
                	}
                	if err := h.SetDay(n); err != nil {
                		return err
                	}
                	fmt.Fprintf(out, "day %d\\n", n)
                	return nil
                }

                func cmdSweep(h *Hub, args []string, out io.Writer) error {
                	gone := h.sweep()
                	for _, e := range gone {
                		fmt.Fprintf(out, "expired %s %s\\n", e.Code, e.Parcel.ID)
                	}
                	fmt.Fprintf(out, "swept %d\\n", len(gone))
                	return nil
                }
            ''',
        },
        cross={
            "events": {
                "reqs": ("`Sweep` records an `expired` event (with the parcel's code, locker and id) for every parcel it removes, in code order.",),
                "code": {"hub.go::on_expire": 'h.record("expired", e.Code, e.Locker, e.Parcel.ID)'},
                "tests": '''
                    func TestSweepRecordsEvents(t *testing.T) {
                    	h := hHub(t)
                    	hAssign(t, h, "south", "P2", Small)
                    	hAssign(t, h, "north", "P1", Small)
                    	h.SetDay(50)
                    	h.Sweep()
                    	ev := h.Events()
                    	hEq(t, "events", ev[2:], []Event{{3, "expired", "north-0002", "north", "P1"}, {4, "expired", "south-0001", "south", "P2"}})
                    }
                '''},
        },
        readme=fmt(dd('''
            ## Pickup deadline

            The hub counts days (`SetDay`, never backwards) and keeps parcels for `SetHoldDays` days (default __HOLD__). `Sweep()`
            removes parcels with `day - Since > holdDays`, frees their compartments and returns them ordered by code. CLI:
            `day N`, `sweep`.
        '''), HOLD=hold),
        vtests='''
            func TestSetDayBasic(t *testing.T) {
            	h := vHub(t)
            	if err := h.SetDay(3); err != nil {
            		t.Fatal(err)
            	}
            }
        ''',
        tests=fmt('''
            func TestSweep(t *testing.T) {
            	h := hHub(t)
            	hAssign(t, h, "north", "P1", Small)
            	h.SetDay(2)
            	hAssign(t, h, "south", "P2", Small)
            	hAssign(t, h, "north", "P3", Medium)
            	held := h.Held()
            	hEq(t, "since", []int{held[0].Since, held[1].Since, held[2].Since}, []int{0, 2, 2})
            	h.SetDay(__HOLD__)
            	hEq(t, "exactly at the limit is fine", len(h.Sweep()), 0)
            	h.SetDay(__HOLD__ + 1)
            	gone := h.Sweep()
            	hEq(t, "expired", gone, []Parcel{{ID: "P1", Size: Small}})
            	hEq(t, "freed", h.Free("north", Small), 2)
            	if _, err := h.Pickup("north-0001"); !errors.Is(err, ErrNoSuchCode) {
            		t.Errorf("expired code still works: %v", err)
            	}
            	h.SetDay(__HOLD__ + 2)
            	hEq(t, "age equal to the hold period is still fine", len(h.Sweep()), 0)
            	h.SetDay(__HOLD__ + 3)
            	gone = h.Sweep()
            	hEq(t, "later sweep", []string{gone[0].ID, gone[1].ID}, []string{"P3", "P2"})
            }

            func TestDayAndHoldErrors(t *testing.T) {
            	h := hHub(t)
            	h.SetDay(5)
            	if err := h.SetDay(4); err == nil {
            		t.Error("going back in time should fail")
            	}
            	if err := h.SetDay(5); err != nil {
            		t.Errorf("same day should be fine: %v", err)
            	}
            	if err := h.SetHoldDays(0); err == nil {
            		t.Error("hold of 0 days accepted")
            	}
            	if err := h.SetHoldDays(1); err != nil {
            		t.Fatal(err)
            	}
            	hAssign(t, h, "north", "P1", Small)
            	h.SetDay(6)
            	hEq(t, "one day old is fine", len(h.Sweep()), 0)
            	h.SetDay(7)
            	hEq(t, "two days old is not", len(h.Sweep()), 1)
            }

            func TestSweepCommands(t *testing.T) {
            	h := hHub(t)
            	hAssign(t, h, "south", "P2", Small)
            	hAssign(t, h, "north", "P1", Small)
            	code, out, _ := hRun(h, "day", "20")
            	hEq(t, "day", []interface{}{code, out}, []interface{}{0, "day 20\\n"})
            	code, out, _ = hRun(h, "sweep")
            	hEq(t, "sweep", []interface{}{code, out}, []interface{}{0, "expired north-0002 P1\\nexpired south-0001 P2\\nswept 2\\n"})
            	_, out, _ = hRun(h, "sweep")
            	hEq(t, "nothing left", out, "swept 0\\n")
            	for _, args := range [][]string{{"day", "x"}, {"day", "3"}, {"day"}} {
            		code, out, errs := hRun(h, args...)
            		if code != 1 || out != "" || !strings.HasPrefix(errs, "parcelhub: ") {
            			t.Errorf("%v: %d %q %q", args, code, out, errs)
            		}
            	}
            }
        ''', HOLD=hold),
    ))

    S.append(Slice(
        id="events", title="Event history", d=3,
        pitch=("When a customer says the parcel was never there, nobody can reconstruct what the hub did.",
               "Support needs a history of what the hub did, in order."),
        reqs=("The hub keeps an ordered history: `Hub.Events() []Event` returns a copy, oldest first. `Event` has the fields `Seq int` (1 for the first event, then 1 more each time), `Kind string`, `Code string`, `Locker string` and `Parcel string` (the parcel id).",
              "A successful `Assign` records kind `assigned`; a successful `Pickup` records `picked_up`. Failed calls record nothing.",
              "`events` (a new command) prints one line per event: `#<seq> <kind> <code> <parcel>`."),
        code={
            "hub.go::types": '''
                // Event is one entry of the hub's history.
                type Event struct {
                	Seq    int
                	Kind   string // "assigned", "picked_up", ...
                	Code   string
                	Locker string
                	Parcel string // parcel id
                }
            ''',
            "hub.go::hub_fields": "events []Event",
            "hub.go::on_assign": 'h.record("assigned", code, lockerID, p.ID)',
            "hub.go::on_pickup": 'h.record("picked_up", code, e.Locker, e.Parcel.ID)',
            "hub.go::methods": '''
                func (h *Hub) record(kind, code, locker, parcel string) {
                	ev := Event{Seq: len(h.events) + 1, Kind: kind, Code: code, Locker: locker, Parcel: parcel}
                	h.events = append(h.events, ev)
                	@@slot on_record
                }

                // Events returns the history, oldest first.
                func (h *Hub) Events() []Event {
                	return append([]Event{}, h.events...)
                }
            ''',
            "cli.go::cases": '''
                case "events":
                	err = cmdEvents(h, rest, out)
            ''',
            "cli.go::commands": '''
                func cmdEvents(h *Hub, args []string, out io.Writer) error {
                	for _, ev := range h.Events() {
                		fmt.Fprintf(out, "#%d %s %s %s\\n", ev.Seq, ev.Kind, ev.Code, ev.Parcel)
                	}
                	return nil
                }
            ''',
        },
        readme=dd('''
            ## Event history

            `Hub.Events()` returns the history (`Seq`, `Kind`, `Code`, `Locker`, `Parcel`), oldest first: `assigned` for each
            successful `Assign`, `picked_up` for each successful `Pickup`. The `events` command prints
            `#<seq> <kind> <code> <parcel>` lines.
        '''),
        vtests='''
            func TestEventsBasic(t *testing.T) {
            	h := vHub(t)
            	h.Assign("north", Parcel{ID: "P1", Size: Small})
            	if ev := h.Events(); len(ev) != 1 || ev[0].Kind != "assigned" {
            		t.Fatalf("events %+v", ev)
            	}
            }
        ''',
        tests='''
            func TestEvents(t *testing.T) {
            	h := hHub(t)
            	c1 := hAssign(t, h, "north", "P1", Small)
            	hAssign(t, h, "south", "P2", Medium)
            	h.Assign("north", Parcel{ID: "P3", Size: Large + 1})
            	h.Assign("mars", Parcel{ID: "P4", Size: Small})
            	if _, err := h.Pickup(c1); err != nil {
            		t.Fatal(err)
            	}
            	h.Pickup("nope")
            	hEq(t, "events", h.Events(), []Event{
            		{1, "assigned", "north-0001", "north", "P1"},
            		{2, "assigned", "south-0002", "south", "P2"},
            		{3, "picked_up", "north-0001", "north", "P1"},
            	})
            	ev := h.Events()
            	ev[0].Kind = "tampered"
            	hEq(t, "copy", h.Events()[0].Kind, "assigned")
            	hEq(t, "fresh hub", len(NewHub().Events()), 0)
            }

            func TestEventsCommand(t *testing.T) {
            	h := hHub(t)
            	hRun(h, "assign", "north", "BOX")
            	hRun(h, "assign", "--size", "medium", "south", "CRATE")
            	hRun(h, "pickup", "north-0001")
            	code, out, _ := hRun(h, "events")
            	hEq(t, "events", []interface{}{code, out}, []interface{}{0, "#1 assigned north-0001 BOX\\n#2 assigned south-0002 CRATE\\n#3 picked_up north-0001 BOX\\n"})
            }
        ''',
    ))

    S.append(Slice(
        id="idempotent", title="Safe retries for assign", d=3,
        pitch=("The courier app retries on bad reception and sometimes parcels end up in two compartments.",
               "A retried assign request must not take a second compartment."),
        reqs=("`Hub.AssignOnce(key, lockerID string, p Parcel) (string, error)` is `Assign` with an idempotency key. The first call with a key behaves exactly like `Assign`; any later call with the same key returns the same code and changes nothing, whatever its other arguments are (even if the parcel has been picked up or swept since).",
              "A call that fails is not remembered, so the same key can be retried later. An empty key is an error.",
              "`assign --key K ...` uses `AssignOnce` when `--key` is given (a replay prints the same `PARCEL -> CODE` line as the first call; the parcel argument of a replay is ignored)."),
        code={
            "hub.go::hub_fields": "keys map[string]string",
            "hub.go::new_hub": "h.keys = map[string]string{}",
            "hub.go::methods": '''
                // AssignOnce is Assign with an idempotency key: replays return the first code and change nothing.
                func (h *Hub) AssignOnce(key, lockerID string, p Parcel) (string, error) {
                	if key == "" {
                		return "", errors.New("empty idempotency key")
                	}
                	if code, ok := h.keys[key]; ok {
                		return code, nil
                	}
                	code, err := h.Assign(lockerID, p)
                	if err != nil {
                		return "", err
                	}
                	h.keys[key] = code
                	return code, nil
                }
            ''',
            "cli.go::assign_flags": 'key := fs.String("key", "", "idempotency key")',
            "cli.go::assign_call": '''
                var code string
                if *key != "" {
                	code, err = h.AssignOnce(*key, fs.Arg(0), Parcel{ID: fs.Arg(1), Size: sz})
                } else {
                	code, err = h.Assign(fs.Arg(0), Parcel{ID: fs.Arg(1), Size: sz})
                }
            ''',
        },
        readme=dd('''
            ## Idempotent assignment

            `Hub.AssignOnce(key, lockerID, parcel)` returns the original code for a repeated key without touching the hub
            again; failures are not remembered; an empty key is an error. CLI: `assign --key K`.
        '''),
        vtests='''
            func TestAssignOnceBasic(t *testing.T) {
            	h := vHub(t)
            	a, _ := h.AssignOnce("k", "north", Parcel{ID: "P1", Size: Small})
            	b, _ := h.AssignOnce("k", "north", Parcel{ID: "P1", Size: Small})
            	if a == "" || a != b {
            		t.Fatalf("%q %q", a, b)
            	}
            }
        ''',
        tests='''
            func TestAssignOnce(t *testing.T) {
            	h := hHub(t)
            	c1, err := h.AssignOnce("k1", "north", Parcel{ID: "P1", Size: Small})
            	if err != nil {
            		t.Fatal(err)
            	}
            	hEq(t, "first code", c1, "north-0001")
            	c2, err := h.AssignOnce("k1", "south", Parcel{ID: "OTHER", Size: Large})
            	hEq(t, "replay", []interface{}{c2, err}, []interface{}{"north-0001", error(nil)})
            	hEq(t, "stored once", hIDs(h.Held()), []string{"P1"})
            	hEq(t, "south untouched", h.Free("south", Small), 1)
            	c3, _ := h.AssignOnce("k2", "north", Parcel{ID: "P2", Size: Small})
            	hEq(t, "new key, next code", c3, "north-0002")
            	if _, err := h.Pickup(c1); err != nil {
            		t.Fatal(err)
            	}
            	c4, err := h.AssignOnce("k1", "north", Parcel{ID: "P1", Size: Small})
            	hEq(t, "replay after pickup", []interface{}{c4, err}, []interface{}{"north-0001", error(nil)})
            	hEq(t, "nothing re-stored", hIDs(h.Held()), []string{"P2"})
            }

            func TestAssignOnceFailuresAndEmptyKey(t *testing.T) {
            	h := NewHub()
            	h.AddLocker("y", 1, 0, 0)
            	first := hAssign(t, h, "y", "P1", Small)
            	if _, err := h.AssignOnce("k", "y", Parcel{ID: "P2", Size: Small}); !errors.Is(err, ErrFull) {
            		t.Fatalf("want ErrFull, got %v", err)
            	}
            	if _, err := h.AssignOnce("k", "nowhere", Parcel{ID: "P2", Size: Small}); err == nil {
            		t.Error("unknown locker accepted")
            	}
            	h.Pickup(first)
            	c, err := h.AssignOnce("k", "y", Parcel{ID: "P2", Size: Small})
            	if err != nil || c != "y-0002" {
            		t.Errorf("retry after failure: %q, %v", c, err)
            	}
            	if _, err := h.AssignOnce("", "y", Parcel{ID: "P3", Size: Small}); err == nil {
            		t.Error("empty key accepted")
            	}
            }

            func TestAssignKeyFlag(t *testing.T) {
            	h := hHub(t)
            	_, out1, _ := hRun(h, "assign", "--key", "abc", "north", "BOX")
            	code, out2, _ := hRun(h, "assign", "--key", "abc", "north", "BOX")
            	hEq(t, "replay", []interface{}{code, out1, out2}, []interface{}{0, "BOX -> north-0001\\n", "BOX -> north-0001\\n"})
            	hEq(t, "stored once", len(h.Held()), 1)
            	_, out3, _ := hRun(h, "assign", "north", "BOX")
            	hEq(t, "without a key it is a new parcel", out3, "BOX -> north-0002\\n")
            }
        ''',
        cross={
            "events": {
                "reqs": ("A replayed `AssignOnce` records no event.",),
                "tests": '''
                    func TestReplayRecordsNoEvent(t *testing.T) {
                    	h := hHub(t)
                    	h.AssignOnce("k", "north", Parcel{ID: "P1", Size: Small})
                    	h.AssignOnce("k", "north", Parcel{ID: "P1", Size: Small})
                    	hEq(t, "events", len(h.Events()), 1)
                    }
                '''},
        },
    ))

    S.append(Slice(
        id="listeners", title="Event subscribers", d=3, needs=("events",),
        pitch=("The notification service should be told the moment something happens instead of polling the history.",
               "Other components want to react to hub events as they happen."),
        reqs=("`Hub.Subscribe(fn func(Event)) (cancel func())` registers `fn`. Every event recorded afterwards is passed to every subscriber, synchronously, in subscription order, right after it has been appended to the history (so `Events()` already contains it when `fn` runs).",
              "Calling the returned `cancel` stops deliveries to that subscriber; calling it again does nothing. A subscriber may cancel itself, or subscribe another function, from inside a callback without disturbing the delivery in progress."),
        code={
            "hub.go::types": '''
                type subscription struct {
                	id int
                	fn func(Event)
                }
            ''',
            "hub.go::hub_fields": "subs    []subscription\nnextSub int",
            "hub.go::on_record": '''
                for _, s := range append([]subscription(nil), h.subs...) {
                	s.fn(ev)
                }
            ''',
            "hub.go::methods": '''
                // Subscribe calls fn for every event recorded from now on; the returned func unsubscribes.
                func (h *Hub) Subscribe(fn func(Event)) (cancel func()) {
                	h.nextSub++
                	id := h.nextSub
                	h.subs = append(h.subs, subscription{id, fn})
                	return func() {
                		for i, s := range h.subs {
                			if s.id == id {
                				h.subs = append(h.subs[:i], h.subs[i+1:]...)
                				return
                			}
                		}
                	}
                }
            ''',
        },
        readme=dd('''
            ## Subscribers

            `Hub.Subscribe(fn)` delivers every later event synchronously, in subscription order, after it is in the history;
            the returned func cancels (idempotently).
        '''),
        vtests='''
            func TestSubscribeBasic(t *testing.T) {
            	h := vHub(t)
            	n := 0
            	h.Subscribe(func(Event) { n++ })
            	h.Assign("north", Parcel{ID: "P1", Size: Small})
            	if n != 1 {
            		t.Fatalf("got %d deliveries", n)
            	}
            }
        ''',
        tests='''
            func TestSubscribeOrderAndCancel(t *testing.T) {
            	h := hHub(t)
            	var log []string
            	h.Subscribe(func(ev Event) { log = append(log, "a"+ev.Kind) })
            	cancelB := h.Subscribe(func(ev Event) { log = append(log, "b"+ev.Kind) })
            	c := hAssign(t, h, "north", "P1", Small)
            	hEq(t, "both", log, []string{"aassigned", "bassigned"})
            	cancelB()
            	cancelB()
            	h.Pickup(c)
            	hEq(t, "only a", log, []string{"aassigned", "bassigned", "apicked_up"})
            }

            func TestSubscribeSeesHistory(t *testing.T) {
            	h := hHub(t)
            	var seen []int
            	h.Subscribe(func(ev Event) { seen = append(seen, len(h.Events())*10+ev.Seq) })
            	hAssign(t, h, "north", "P1", Small)
            	hAssign(t, h, "north", "P2", Small)
            	hEq(t, "history already updated", seen, []int{11, 22})
            }

            func TestSubscribeInsideCallback(t *testing.T) {
            	h := hHub(t)
            	var log []string
            	var cancel func()
            	cancel = h.Subscribe(func(ev Event) {
            		log = append(log, "once")
            		cancel()
            	})
            	h.Subscribe(func(ev Event) { log = append(log, "second") })
            	hAssign(t, h, "north", "P1", Small)
            	hAssign(t, h, "north", "P2", Small)
            	hEq(t, "log", log, []string{"once", "second", "second"})
            }
        ''',
        cross={
            "expiry": {"tests": '''
                func TestSubscribersSeeExpiry(t *testing.T) {
                	h := hHub(t)
                	hAssign(t, h, "north", "P1", Small)
                	var kinds []string
                	h.Subscribe(func(ev Event) { kinds = append(kinds, ev.Kind) })
                	h.SetDay(100)
                	h.Sweep()
                	hEq(t, "kinds", kinds, []string{"expired"})
                }
            '''},
        },
    ))

    return S


APP = App(
    name="parcelhub", lang="go", title="the parcel locker hub library", role="a courier at the depot", key="HUB",
    base={
        "README.md": README + "\n@@blocks features\n",
        "go.mod": langs.go_mod("parcelhub"),
        "hub.go": HUB,
        "cli.go": CLI,
        ".gitignore": langs.GITIGNORE["go"] or "*.test\n",
    },
    visible={"hub_test.go": VISIBLE},
    hidden={"features_test.go": HIDDEN},
)

# register after the slices are fixed up
register_app("feature-go-parcelhub", APP, make_slices, n=16, summary="parcel locker hub: filters, usage, JSON, dims, policies, deadlines")
