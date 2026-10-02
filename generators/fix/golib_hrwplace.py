"""Rendezvous placement (go): weighted highest-score hashing with zone-aware replicas and rebalance plans."""
from fx import Lib, dd, langs

from generators.fix._lang1 import gosrc, register_libs

README = dd('''
    # hrwplace

    Decides which storage nodes hold a key, with *rendezvous* (highest-score) hashing: every key scores every node and the
    best scores win. Adding or removing a node only moves the keys that node wins or wins no longer.

    ```go
    type Node struct {
        ID     string
        Weight int    // >= 1
        Zone   string // failure domain; "" means "no zone"
    }
    ```

    ## `Hash(id, key string) uint64`
    FNV-1a (64-bit; offset basis `14695981039346656037`, prime `1099511628211`) over the bytes of `id`, then one `0xFF`
    byte, then the bytes of `key`; the result is passed through the finaliser
    `h ^= h>>33; h *= 0xff51afd7ed558ccd; h ^= h>>33; h *= 0xc4ceb9fe1a85ec53; h ^= h>>33` (all `uint64`, wrapping).

    ## Scoring and ranking
    A node's score for a key is the full 128-bit product `Hash(node.ID, key) * Weight`. Nodes are ranked by score, highest
    first; equal scores are ordered by `ID` (ascending). The ranking does not depend on the order of the input slice.
    (Heavier nodes win disproportionately often: this is a deliberate simplification, not a proportional share.)

    ## `Locate(nodes []Node, key string, n int) ([]string, error)`
    Returns the IDs of the `n` replicas for `key`, primary first. Selection works in two passes over the ranking:

    1. walk the ranking and take a node whenever its zone has not been taken yet (nodes with an empty zone are always
       eligible in this pass), until `n` are chosen;
    2. if fewer than `n` were found, walk the ranking again and add the best nodes that are not yet chosen.

    The result is in order of selection. With fewer than `n` nodes all of them are returned. Errors: `ErrBadCount`
    when `n < 1`, `ErrBadWeight` for a node with `Weight < 1`, `ErrDuplicate` for two nodes with the same `ID` (checked
    for every node, also when `n` is small).

    ## `Counts(nodes []Node, keys []string) (map[string]int, error)`
    How many keys each node is primary for. Every node appears in the map, with 0 if it owns no key. Same errors as `Locate`;
    an empty node list gives an empty map.

    ## `Moves(oldNodes, newNodes []Node, keys []string) ([]Move, error)`
    The rebalance plan after a membership change: for each key, in input order, the primary on the old node set and on the
    new one; keys whose primary differs yield `Move{Key, From, To}`. An empty node set has no primary (`""`), so
    growing from nothing moves every key from `""`. Keys that stay put are not listed.
''')

SRC = gosrc(dd(r'''
    // Package hrwplace places keys on nodes with weighted rendezvous hashing.
    package hrwplace

    import (
        "errors"
        "math/bits"
        "sort"
    )

    var (
        ErrBadCount  = errors.New("hrwplace: replica count must be at least 1")
        ErrBadWeight = errors.New("hrwplace: node weight must be at least 1")
        ErrDuplicate = errors.New("hrwplace: duplicate node id")
    )

    // Node is a storage node.
    type Node struct {
        ID     string
        Weight int
        Zone   string
    }

    // Move is one key changing its primary node.
    type Move struct {
        Key, From, To string
    }

    const (
        fnvOffset = 14695981039346656037
        fnvPrime  = 1099511628211
    )

    // Hash is the placement hash of a (node, key) pair.
    func Hash(id, key string) uint64 {
        h := uint64(fnvOffset)
        for i := 0; i < len(id); i++ {
            h ^= uint64(id[i])
            h *= fnvPrime
        }
        h ^= 0xFF
        h *= fnvPrime
        for i := 0; i < len(key); i++ {
            h ^= uint64(key[i])
            h *= fnvPrime
        }
        h ^= h >> 33
        h *= 0xff51afd7ed558ccd
        h ^= h >> 33
        h *= 0xc4ceb9fe1a85ec53
        h ^= h >> 33
        return h
    }

    type scored struct {
        node   Node
        hi, lo uint64
    }

    func rank(nodes []Node, key string) ([]scored, error) {
        seen := make(map[string]bool, len(nodes))
        out := make([]scored, 0, len(nodes))
        for _, nd := range nodes {
            if nd.Weight < 1 {
                return nil, ErrBadWeight
            }
            if seen[nd.ID] {
                return nil, ErrDuplicate
            }
            seen[nd.ID] = true
            hi, lo := bits.Mul64(Hash(nd.ID, key), uint64(nd.Weight))
            out = append(out, scored{nd, hi, lo})
        }
        sort.Slice(out, func(i, j int) bool {
            a, b := out[i], out[j]
            if a.hi != b.hi {
                return a.hi > b.hi
            }
            if a.lo != b.lo {
                return a.lo > b.lo
            }
            return a.node.ID < b.node.ID
        })
        return out, nil
    }

    // Locate returns the replica set for key, primary first.
    func Locate(nodes []Node, key string, n int) ([]string, error) {
        if n < 1 {
            return nil, ErrBadCount
        }
        ranked, err := rank(nodes, key)
        if err != nil {
            return nil, err
        }
        var out []string
        taken := make([]bool, len(ranked))
        zones := map[string]bool{}
        for i, s := range ranked {
            if len(out) == n {
                break
            }
            if z := s.node.Zone; z != "" && zones[z] {
                continue
            } else {
                zones[z] = true
            }
            taken[i] = true
            out = append(out, s.node.ID)
        }
        for i, s := range ranked {
            if len(out) == n {
                break
            }
            if !taken[i] {
                out = append(out, s.node.ID)
            }
        }
        return out, nil
    }

    func primary(nodes []Node, key string) (string, error) {
        if len(nodes) == 0 {
            return "", nil
        }
        ids, err := Locate(nodes, key, 1)
        if err != nil {
            return "", err
        }
        return ids[0], nil
    }

    // Counts reports how many keys each node is primary for.
    func Counts(nodes []Node, keys []string) (map[string]int, error) {
        counts := make(map[string]int, len(nodes))
        for _, nd := range nodes {
            counts[nd.ID] = 0
        }
        for _, k := range keys {
            id, err := primary(nodes, k)
            if err != nil {
                return nil, err
            }
            if id != "" {
                counts[id]++
            }
        }
        return counts, nil
    }

    // Moves lists the keys whose primary node differs between two memberships.
    func Moves(oldNodes, newNodes []Node, keys []string) ([]Move, error) {
        var out []Move
        for _, k := range keys {
            from, err := primary(oldNodes, k)
            if err != nil {
                return nil, err
            }
            to, err := primary(newNodes, k)
            if err != nil {
                return nil, err
            }
            if from != to {
                out = append(out, Move{k, from, to})
            }
        }
        return out, nil
    }
'''))

VISIBLE = gosrc(dd(r'''
    package hrwplace

    import "testing"

    func TestSingleNodeOwnsEverything(t *testing.T) {
        ids, err := Locate([]Node{{ID: "solo", Weight: 1}}, "any-key", 1)
        if err != nil || len(ids) != 1 || ids[0] != "solo" {
            t.Fatalf("got %v, %v", ids, err)
        }
    }

    func TestRejectsZeroReplicas(t *testing.T) {
        if _, err := Locate([]Node{{ID: "a", Weight: 1}}, "k", 0); err == nil {
            t.Fatal("expected an error")
        }
    }
'''))

HIDDEN = gosrc(dd(r'''
    package hrwplace

    import (
        "errors"
        "fmt"
        "reflect"
        "testing"
    )

    var four = []Node{{"n1", 1, "a"}, {"n2", 1, "a"}, {"n3", 1, "b"}, {"n4", 1, "c"}}

    func keys(n int, prefix string) []string {
        out := make([]string, n)
        for i := range out {
            out[i] = fmt.Sprintf("%s%d", prefix, i)
        }
        return out
    }

    func TestHashLiterals(t *testing.T) {
        cases := []struct {
            id, key string
            want    uint64
        }{
            {"n1", "k0", 11822315084036828747},
            {"n2", "k0", 16194623332231321380},
            {"", "", 1998855519756462295},
            {"a", "bc", 3462142018808893216},
            {"ab", "c", 8881672327746025411},
        }
        for _, c := range cases {
            if got := Hash(c.id, c.key); got != c.want {
                t.Errorf("Hash(%q, %q) = %d, want %d", c.id, c.key, got, c.want)
            }
        }
    }

    func TestPrimaryLiterals(t *testing.T) {
        want := []string{"n2", "n1", "n4", "n4", "n2", "n3", "n4", "n3", "n3", "n4", "n1", "n1", "n2", "n2", "n3", "n3", "n2", "n3", "n1", "n4"}
        for i, k := range keys(20, "k") {
            ids, err := Locate(four, k, 1)
            if err != nil || len(ids) != 1 || ids[0] != want[i] {
                t.Errorf("Locate(%s) = %v, %v; want %s", k, ids, err, want[i])
            }
        }
    }

    func TestReplicaLiterals(t *testing.T) {
        want := [][]string{
            {"n2", "n3", "n4"}, {"n1", "n4", "n3"}, {"n4", "n3", "n1"}, {"n4", "n3", "n2"}, {"n2", "n4", "n3"}, {"n3", "n4", "n2"},
        }
        for i, k := range keys(6, "k") {
            got, err := Locate(four, k, 3)
            if err != nil || !reflect.DeepEqual(got, want[i]) {
                t.Errorf("Locate(%s, 3) = %v, %v; want %v", k, got, err, want[i])
            }
        }
    }

    func TestZoneSpreadPassesBeforeFill(t *testing.T) {
        zoned := []Node{{"a1", 1, "x"}, {"a2", 1, "x"}, {"b1", 1, "y"}, {"b2", 1, "y"}, {"c1", 1, "z"}, {"c2", 1, "z"}}
        want := [][]string{
            {"a1", "c1", "b2", "c2"}, {"c2", "b2", "a1", "c1"}, {"c1", "b2", "a1", "c2"}, {"b1", "a2", "c1", "b2"},
        }
        for i, k := range keys(4, "k") {
            got, err := Locate(zoned, k, 4)
            if err != nil || !reflect.DeepEqual(got, want[i]) {
                t.Errorf("Locate(%s, 4) = %v, %v; want %v", k, got, err, want[i])
            }
        }
    }

    func TestReplicasLandInDistinctZonesWhenPossible(t *testing.T) {
        zones := map[string]string{}
        for _, n := range four {
            zones[n.ID] = n.Zone
        }
        for _, k := range keys(300, "obj-") {
            got, err := Locate(four, k, 3)
            if err != nil || len(got) != 3 {
                t.Fatalf("%s: %v %v", k, got, err)
            }
            seen := map[string]bool{}
            for _, id := range got {
                if seen[zones[id]] {
                    t.Fatalf("%s: zone %s repeated in %v", k, zones[id], got)
                }
                seen[zones[id]] = true
            }
        }
    }

    func TestMoreReplicasThanZones(t *testing.T) {
        zoned := []Node{{"a1", 1, "x"}, {"a2", 1, "x"}, {"b1", 1, "y"}, {"b2", 1, "y"}}
        for _, k := range keys(100, "k") {
            got, _ := Locate(zoned, k, 3)
            if len(got) != 3 {
                t.Fatalf("%s: %v", k, got)
            }
            z := map[string]int{}
            for _, id := range got {
                z[id[:1]]++
            }
            if len(z) != 2 {
                t.Fatalf("%s: %v does not use both zones", k, got)
            }
            first, _ := Locate(zoned, k, 2)
            if first[0] != got[0] || first[1] != got[1] {
                t.Fatalf("%s: prefix changed: %v vs %v", k, first, got)
            }
        }
    }

    func TestEmptyZonesNeverConflict(t *testing.T) {
        flat := []Node{{"p", 1, ""}, {"q", 1, ""}, {"r", 1, ""}}
        for _, k := range keys(50, "k") {
            got, err := Locate(flat, k, 3)
            if err != nil || len(got) != 3 {
                t.Fatalf("%s: %v %v", k, got, err)
            }
        }
        // ranking order is the plain score order when nothing has a zone
        ids, _ := Locate([]Node{{"n1", 1, ""}, {"n2", 1, ""}, {"n3", 1, ""}, {"n4", 1, ""}}, "k0", 4)
        if !reflect.DeepEqual(ids[:1], []string{"n2"}) || len(ids) != 4 {
            t.Errorf("got %v", ids)
        }
    }

    func TestInputOrderDoesNotMatter(t *testing.T) {
        rev := []Node{four[3], four[2], four[1], four[0]}
        mid := []Node{four[2], four[0], four[3], four[1]}
        for _, k := range keys(100, "k") {
            a, _ := Locate(four, k, 4)
            b, _ := Locate(rev, k, 4)
            c, _ := Locate(mid, k, 4)
            if !reflect.DeepEqual(a, b) || !reflect.DeepEqual(a, c) {
                t.Fatalf("%s: %v %v %v", k, a, b, c)
            }
        }
    }

    func TestMoreReplicasThanNodes(t *testing.T) {
        got, err := Locate(four[:2], "k", 5)
        if err != nil || len(got) != 2 {
            t.Fatalf("got %v, %v", got, err)
        }
        got, err = Locate(nil, "k", 2)
        if err != nil || len(got) != 0 {
            t.Fatalf("no nodes: %v, %v", got, err)
        }
    }

    func TestErrors(t *testing.T) {
        if _, err := Locate(four, "k", 0); !errors.Is(err, ErrBadCount) {
            t.Errorf("n=0: %v", err)
        }
        if _, err := Locate(four, "k", -2); !errors.Is(err, ErrBadCount) {
            t.Errorf("n=-2: %v", err)
        }
        if _, err := Locate([]Node{{"a", 0, ""}}, "k", 1); !errors.Is(err, ErrBadWeight) {
            t.Errorf("weight 0: %v", err)
        }
        if _, err := Locate([]Node{{"a", 1, ""}, {"b", -3, ""}}, "k", 1); !errors.Is(err, ErrBadWeight) {
            t.Errorf("negative weight: %v", err)
        }
        if _, err := Locate([]Node{{"a", 1, ""}, {"b", 1, ""}, {"a", 2, "z"}}, "k", 1); !errors.Is(err, ErrDuplicate) {
            t.Errorf("duplicate: %v", err)
        }
        if _, err := Locate([]Node{{"a", 1, ""}, {"a", 1, ""}}, "k", 1); !errors.Is(err, ErrDuplicate) {
            t.Errorf("duplicate 2: %v", err)
        }
        // count is validated before the nodes
        if _, err := Locate([]Node{{"a", 0, ""}}, "k", 0); !errors.Is(err, ErrBadCount) {
            t.Errorf("order of checks: %v", err)
        }
    }

    func TestCountsAndWeights(t *testing.T) {
        ks := keys(1000, "key-")
        got, err := Counts(four, ks)
        if err != nil || !reflect.DeepEqual(got, map[string]int{"n1": 249, "n2": 254, "n3": 244, "n4": 253}) {
            t.Errorf("equal weights: %v, %v", got, err)
        }
        heavy := []Node{{"n1", 1, ""}, {"n2", 1, ""}, {"n3", 1, ""}, {"n4", 100, ""}}
        got, _ = Counts(heavy, ks)
        if !reflect.DeepEqual(got, map[string]int{"n1": 5, "n2": 1, "n3": 2, "n4": 992}) {
            t.Errorf("heavy: %v", got)
        }
        graded := []Node{{"n1", 1, ""}, {"n2", 2, ""}, {"n3", 3, ""}, {"n4", 4, ""}}
        got, _ = Counts(graded, ks)
        if !reflect.DeepEqual(got, map[string]int{"n1": 8, "n2": 100, "n3": 321, "n4": 571}) {
            t.Errorf("graded: %v", got)
        }
    }

    func TestCountsEdges(t *testing.T) {
        got, err := Counts(nil, keys(5, "k"))
        if err != nil || len(got) != 0 {
            t.Errorf("no nodes: %v %v", got, err)
        }
        got, _ = Counts(four, nil)
        if !reflect.DeepEqual(got, map[string]int{"n1": 0, "n2": 0, "n3": 0, "n4": 0}) {
            t.Errorf("no keys: %v", got)
        }
        if _, err := Counts([]Node{{"a", 0, ""}}, keys(2, "k")); !errors.Is(err, ErrBadWeight) {
            t.Errorf("bad weight: %v", err)
        }
        got, _ = Counts([]Node{{"only", 3, "z"}}, keys(7, "k"))
        if got["only"] != 7 {
            t.Errorf("single node: %v", got)
        }
    }

    func TestRemovingANodeOnlyMovesItsKeys(t *testing.T) {
        ks := keys(1000, "key-")
        smaller := []Node{four[0], four[1], four[3]}
        moves, err := Moves(four, smaller, ks)
        if err != nil {
            t.Fatal(err)
        }
        if len(moves) != 244 {
            t.Errorf("%d moves, want 244", len(moves))
        }
        for _, m := range moves {
            if m.From != "n3" || m.To == "n3" || m.To == "" {
                t.Fatalf("unexpected move %+v", m)
            }
        }
        want := []Move{{"key-3", "n3", "n2"}, {"key-4", "n3", "n1"}, {"key-8", "n3", "n1"}}
        if !reflect.DeepEqual(moves[:3], want) {
            t.Errorf("first moves %+v", moves[:3])
        }
    }

    func TestAddingANodeOnlyMovesKeysToIt(t *testing.T) {
        ks := keys(1000, "key-")
        bigger := append(append([]Node(nil), four...), Node{"n5", 1, "a"})
        moves, err := Moves(four, bigger, ks)
        if err != nil || len(moves) != 182 {
            t.Fatalf("%d moves, %v", len(moves), err)
        }
        for _, m := range moves {
            if m.To != "n5" {
                t.Fatalf("move %+v does not go to the new node", m)
            }
        }
        want := []Move{{"key-0", "n1", "n5"}, {"key-1", "n4", "n5"}, {"key-8", "n3", "n5"}}
        if !reflect.DeepEqual(moves[:3], want) {
            t.Errorf("first moves %+v", moves[:3])
        }
    }

    func TestMovesFromAndToNothing(t *testing.T) {
        ks := []string{"x", "y", "z"}
        moves, err := Moves(nil, four, ks)
        if err != nil || len(moves) != 3 {
            t.Fatalf("%+v %v", moves, err)
        }
        for i, m := range moves {
            if m.Key != ks[i] || m.From != "" || m.To == "" {
                t.Errorf("move %+v", m)
            }
        }
        moves, _ = Moves(four, nil, ks)
        if len(moves) != 3 || moves[0].To != "" || moves[0].From == "" {
            t.Errorf("to nothing: %+v", moves)
        }
        moves, _ = Moves(nil, nil, ks)
        if len(moves) != 0 {
            t.Errorf("nothing to nothing: %+v", moves)
        }
        moves, _ = Moves(four, four, keys(100, "k"))
        if len(moves) != 0 {
            t.Errorf("same membership: %+v", moves)
        }
    }

    func TestMovesReportErrors(t *testing.T) {
        bad := []Node{{"a", 0, ""}}
        if _, err := Moves(bad, four, []string{"k"}); !errors.Is(err, ErrBadWeight) {
            t.Errorf("old: %v", err)
        }
        if _, err := Moves(four, bad, []string{"k"}); !errors.Is(err, ErrBadWeight) {
            t.Errorf("new: %v", err)
        }
        if _, err := Moves(four, []Node{{"a", 1, ""}, {"a", 1, ""}}, []string{"k"}); !errors.Is(err, ErrDuplicate) {
            t.Errorf("dup: %v", err)
        }
    }

    func TestWeightChangeMovesTowardsTheHeavierNode(t *testing.T) {
        ks := keys(500, "w-")
        flat := []Node{{"n1", 1, ""}, {"n2", 1, ""}, {"n3", 1, ""}}
        up := []Node{{"n1", 1, ""}, {"n2", 5, ""}, {"n3", 1, ""}}
        moves, _ := Moves(flat, up, ks)
        for _, m := range moves {
            if m.To != "n2" {
                t.Fatalf("a weight increase moved %+v", m)
            }
        }
        if len(moves) == 0 {
            t.Errorf("no key moved")
        }
    }
'''))

LIB = Lib(
    name="hrwplace", lang="go", title="the hrwplace package",
    blurb="The object store uses hrwplace to decide which storage nodes hold each key, with zone-aware replicas and a rebalance plan when nodes join or leave.",
    files={"go.mod": langs.go_mod("hrwplace"), "hrwplace.go": SRC, "README.md": README},
    visible_tests={"hrwplace_basic_test.go": VISIBLE},
    hidden_tests={"hrwplace_full_test.go": HIDDEN},
    mutate=["hrwplace.go"], difficulty=3, tags=["hashing", "placement", "distributed"],
)

register_libs([LIB], n=8)
