"""docindex (go): an in-memory full-text index extended with stopwords, prefixes, paging, OR search, stemming, cache, phrases."""
import random

from fx import dd, langs
from generators.feature._slices import App, Slice, fmt, register_app

README = dd('''
    # docindex

    A small in-memory full-text index for notes (Go, standard library only). `go test ./...` runs the tests.

    ## Layout

    * `index.go`: `Index`, `Hit`.
    * `index_test.go`: tests.

    ## Basics

    * `New()` makes an empty index. `Add(id, text) error` stores a document (an empty id is an error); adding an id that
      exists replaces its text. `Remove(id) bool` reports whether something was removed. `Len()` counts the documents.
    * Text is split into **words**: maximal runs of letters and digits, lower-cased. Everything else separates words.
    * `Search(query) []Hit` finds the documents that contain **all** the words of the query. A `Hit` is `{ID string, Score int}`:
      the score is the sum, over the query's words, of how many times each occurs in the document. A word that appears
      more than once in the query counts once. Hits are ordered by score (highest first), then by id. A query without words
      returns no hits (`nil`).
''')

INDEX = '''\
// Package docindex is a small in-memory full-text index.
package docindex

import (
	"errors"
	"sort"
	"strings"
	"unicode"
@@uniq imports
)

// Hit is one search result.
type Hit struct {
	ID    string
	Score int
}

type doc struct {
	text   string
	tokens []string
}

// qterm is one parsed piece of a query.
type qterm struct {
	text string
	@@slot qterm_fields
}

@@blocks types

// Index holds the documents.
type Index struct {
	docs map[string]*doc
	@@slot index_fields
}

// New returns an empty index.
func New() *Index {
	ix := &Index{docs: map[string]*doc{}}
	@@slot new_index
	return ix
}

func tokenize(text string) []string {
	return strings.FieldsFunc(strings.ToLower(text), func(r rune) bool {
		return !unicode.IsLetter(r) && !unicode.IsDigit(r)
	})
}

// terms turns text into index terms.
func (ix *Index) terms(text string) []string {
	var out []string
	for _, w := range tokenize(text) {
		@@slot term_filter
		@@slot term_map
		out = append(out, w)
	}
	return out
}

// Add stores or replaces a document.
func (ix *Index) Add(id, text string) error {
	if id == "" {
		return errors.New("empty document id")
	}
	ix.docs[id] = &doc{text: text, tokens: ix.terms(text)}
	@@slot on_change
	return nil
}

// Remove deletes a document and reports whether it existed.
func (ix *Index) Remove(id string) bool {
	if _, ok := ix.docs[id]; !ok {
		return false
	}
	delete(ix.docs, id)
	@@slot on_change
	return true
}

// Len is the number of documents.
func (ix *Index) Len() int { return len(ix.docs) }

@@default split_query
func splitQuery(query string) []string {
	return strings.Fields(query)
}
@@end

func (ix *Index) parseQuery(query string) []qterm {
	var out []qterm
	seen := map[string]bool{}
	for _, piece := range splitQuery(query) {
		@@slot piece_special
		for _, w := range ix.terms(piece) {
			if !seen[w] {
				seen[w] = true
				out = append(out, qterm{text: w})
			}
		}
	}
	return out
}

func count(tokens []string, w string) int {
	n := 0
	for _, t := range tokens {
		if t == w {
			n++
		}
	}
	return n
}

func (ix *Index) matchCount(d *doc, q qterm) int {
	@@slot match_special
	return count(d.tokens, q.text)
}

func sortHits(hits []Hit) {
	sort.Slice(hits, func(i, j int) bool {
		if hits[i].Score != hits[j].Score {
			return hits[i].Score > hits[j].Score
		}
		return hits[i].ID < hits[j].ID
	})
}

// Search finds the documents that contain every word of the query.
func (ix *Index) Search(query string) []Hit {
	@@slot search_pre
	terms := ix.parseQuery(query)
	if len(terms) == 0 {
		return nil
	}
	var hits []Hit
	for id, d := range ix.docs {
		score, ok := 0, true
		for _, q := range terms {
			n := ix.matchCount(d, q)
			if n == 0 {
				ok = false
				break
			}
			score += n
		}
		if ok {
			hits = append(hits, Hit{ID: id, Score: score})
		}
	}
	sortHits(hits)
	@@slot search_post
	return hits
}

@@blocks methods
'''

VISIBLE = '''\
package docindex

import (
	"reflect"
	"testing"
@@uniq imports
)

func vIndex() *Index {
	ix := New()
	ix.Add("a", "The quick brown fox jumps over the lazy dog")
	ix.Add("b", "A quick brown dog and a quick red fox")
	ix.Add("c", "Lazy afternoons: the dog sleeps, the fox runs")
	ix.Add("d", "Foxes and dogs are not friends")
	return ix
}

func vIDs(hits []Hit) []string {
	var out []string
	for _, h := range hits {
		out = append(out, h.ID)
	}
	return out
}

func TestSearchAll(t *testing.T) {
	ix := vIndex()
	if got := ix.Search("quick fox"); !reflect.DeepEqual(got, []Hit{{"b", 3}, {"a", 2}}) {
		t.Fatalf("got %v", got)
	}
	if got := vIDs(ix.Search("dog")); !reflect.DeepEqual(got, []string{"a", "b", "c"}) {
		t.Fatalf("got %v", got)
	}
	if ix.Search("zebra") != nil || ix.Search("  ,. ") != nil {
		t.Fatal("expected no hits")
	}
}

func TestAddRemove(t *testing.T) {
	ix := vIndex()
	if err := ix.Add("", "x"); err == nil {
		t.Fatal("empty id accepted")
	}
	ix.Add("a", "completely different")
	if len(ix.Search("fox")) != 2 || ix.Len() != 4 {
		t.Fatalf("replace failed")
	}
	if !ix.Remove("a") || ix.Remove("a") || ix.Len() != 3 {
		t.Fatal("remove failed")
	}
}
@@blocks tests
'''

HIDDEN = '''\
package docindex

import (
	"reflect"
	"strings"
	"testing"
@@uniq imports
)

var _ = strings.ToUpper

func hIndex() *Index {
	ix := New()
	ix.Add("a", "The quick brown fox jumps over the lazy dog")
	ix.Add("b", "A quick brown dog and a quick red fox")
	ix.Add("c", "Lazy afternoons: the dog sleeps, the fox runs")
	ix.Add("d", "Foxes and dogs are not friends")
	return ix
}

func hIDs(hits []Hit) []string {
	out := []string{}
	for _, h := range hits {
		out = append(out, h.ID)
	}
	return out
}

func hEq(t *testing.T, name string, got, want interface{}) {
	t.Helper()
	if !reflect.DeepEqual(got, want) {
		t.Errorf("%s: got %v, want %v", name, got, want)
	}
}

func TestBaseSearch(t *testing.T) {
	ix := hIndex()
	hEq(t, "quick fox", ix.Search("quick fox"), []Hit{{"b", 3}, {"a", 2}})
	hEq(t, "punctuation and case", ix.Search("QUICK, Fox!"), ix.Search("quick fox"))
	hEq(t, "ties by id", ix.Search("the"), []Hit{{"a", 2}, {"c", 2}})
	hEq(t, "brown dog", ix.Search("brown dog"), []Hit{{"a", 2}, {"b", 2}})
	hEq(t, "repeated query word counts once", ix.Search("fox fox"), ix.Search("fox"))
	hEq(t, "fox", hIDs(ix.Search("fox")), []string{"a", "b", "c"})
	hEq(t, "foxes is a different word", hIDs(ix.Search("foxes")), []string{"d"})
	if ix.Search("") != nil || ix.Search("zebra") != nil || ix.Search("?!") != nil {
		t.Error("expected nil for empty and unmatched queries")
	}
	if err := ix.Add("", "x"); err == nil {
		t.Error("empty id accepted")
	}
	ix.Add("a", "no longer about animals")
	hEq(t, "replaced", hIDs(ix.Search("fox")), []string{"b", "c"})
	hEq(t, "len", ix.Len(), 4)
	hEq(t, "remove", []bool{ix.Remove("b"), ix.Remove("b"), ix.Remove("nope")}, []bool{true, false, false})
	hEq(t, "after remove", hIDs(ix.Search("fox")), []string{"c"})
	ix.Add("x1", "Ünïcode wörds 42 and R2D2")
	hEq(t, "unicode and digits", hIDs(ix.Search("wörds 42 r2d2")), []string{"x1"})
}
@@blocks tests
'''


def make_slices(rng: random.Random):
    stop_words = rng.choice([("the", "a", "and"), ("the", "and", "over"), ("a", "are", "not")])
    S = []

    S.append(Slice(
        id="stopwords", title="Stop words", d=1,
        pitch=("Searches for `the dog` match half the notes because of `the`.",
               "Common words like 'and' and 'the' clutter the scores."),
        reqs=("`Index.SetStopwords(words ...string)` replaces the list of ignored words (each given word is split into words like any text and lower-cased; no arguments clears the list). Stop words are dropped from documents and from queries, so they never count towards a score.",
              "Setting the list applies to the documents already in the index. A query made only of stop words has no words, so it returns no hits. The default is an empty list."),
        code={
            "index.go::index_fields": "stop map[string]bool",
            "index.go::term_filter": '''
                if ix.stop[w] {
                	continue
                }
            ''',
            "index.go::methods": '''
                // SetStopwords replaces the ignored words and re-indexes the documents.
                func (ix *Index) SetStopwords(words ...string) {
                	ix.stop = map[string]bool{}
                	for _, w := range words {
                		for _, t := range tokenize(w) {
                			ix.stop[t] = true
                		}
                	}
                	for _, d := range ix.docs {
                		d.tokens = ix.terms(d.text)
                	}
                	@@slot on_reconfigure
                }
            ''',
        },
        readme="## Stop words\n\n`SetStopwords(words...)` makes the index ignore those words in documents and queries (existing documents are re-indexed; no arguments clears the list).\n",
        vtests='''
            func TestStopwordsBasic(t *testing.T) {
            	ix := vIndex()
            	ix.SetStopwords("the")
            	if got := ix.Search("the quick"); len(got) != 2 {
            		t.Fatalf("got %v", got)
            	}
            }
        ''',
        tests=fmt('''
            func TestStopwordsAreIgnored(t *testing.T) {
            	ix := hIndex()
            	before := ix.Search("the dog")
            	ix.SetStopwords("THE", "__B__", "__C__")
            	hEq(t, "stop word in query", ix.Search("the dog"), ix.Search("dog"))
            	hEq(t, "scores without stop words", ix.Search("the dog"), []Hit{{"a", 1}, {"b", 1}, {"c", 1}})
            	if ix.Search("the __B__ __C__") != nil || ix.Search("The") != nil {
            		t.Error("a query of stop words only should return nothing")
            	}
            	ix.SetStopwords()
            	hEq(t, "cleared", ix.Search("the dog"), before)
            	ix.SetStopwords("the")
            	ix.Add("e", "the end of the dog")
            	hEq(t, "applies to new documents", ix.Search("the dog"), []Hit{{"a", 1}, {"b", 1}, {"c", 1}, {"e", 1}})
            	ix.SetStopwords("Dog Fox")
            	hEq(t, "each word of an entry counts", ix.Search("dog fox"), []Hit(nil))
            	hEq(t, "the has come back", hIDs(ix.Search("the")), []string{"a", "c", "e"})
            }
        ''', B=stop_words[1], C=stop_words[2]),
    ))

    S.append(Slice(
        id="prefix", title="Prefix search", d=2,
        pitch=("People type half a word and expect results.",
               "Search-as-you-type needs prefix matching."),
        reqs=("A query word followed directly by `*` is a prefix term: `qui*` matches every word that starts with `qui` (the word itself included). The `*` is only recognised at the end of a whitespace-separated piece of the query; the part before it is split into words like any text and the **last** of those words is the prefix (the earlier ones are ordinary words).",
              "A prefix term needs at least one word before the `*`: a lone `*` is ignored. For a document the prefix term counts all occurrences of all words that start with it; it must occur at least once for the document to match, like any word. Prefix terms combine with ordinary words in one query (all must match)."),
        code={
            "index.go::qterm_fields": "prefix bool",
            "index.go::piece_special": '''
                if strings.HasSuffix(piece, "*") {
                	words := ix.terms(strings.TrimRight(piece, "*"))
                	for k, w := range words {
                		out = append(out, qterm{text: w, prefix: k == len(words)-1})
                	}
                	continue
                }
            ''',
            "index.go::match_special": '''
                if q.prefix {
                	n := 0
                	for _, t := range d.tokens {
                		if strings.HasPrefix(t, q.text) {
                			n++
                		}
                	}
                	return n
                }
            ''',
        },
        readme="## Prefix search\n\nA query piece ending in `*` makes its last word a prefix: `qui*` matches `quick`, `quiet`, ... The prefix is matched against every word of the document and all matches are counted.\n",
        vtests='''
            func TestPrefixBasic(t *testing.T) {
            	if got := vIDs(vIndex().Search("qui*")); !reflect.DeepEqual(got, []string{"b", "a"}) {
            		t.Fatalf("got %v", got)
            	}
            }
        ''',
        tests='''
            func TestPrefixTerms(t *testing.T) {
            	ix := hIndex()
            	hEq(t, "qui*", ix.Search("qui*"), []Hit{{"b", 2}, {"a", 1}})
            	hEq(t, "q*", ix.Search("q*"), []Hit{{"b", 2}, {"a", 1}})
            	hEq(t, "fox* includes foxes", hIDs(ix.Search("fox*")), []string{"a", "b", "c", "d"})
            	hEq(t, "dog* includes dogs", hIDs(ix.Search("dog*")), []string{"a", "b", "c", "d"})
            	hEq(t, "prefix plus word", ix.Search("fox* lazy"), []Hit{{"a", 2}, {"c", 2}})
            	hEq(t, "word plus prefix", ix.Search("lazy fox*"), []Hit{{"a", 2}, {"c", 2}})
            	hEq(t, "no match", ix.Search("zeb*"), []Hit(nil))
            }

            func TestPrefixEdgeCases(t *testing.T) {
            	ix := hIndex()
            	if ix.Search("*") != nil || ix.Search("** *") != nil {
            		t.Error("a lone star should be ignored")
            	}
            	hEq(t, "star alone is dropped", ix.Search("* fox"), ix.Search("fox"))
            	hEq(t, "last word is the prefix", ix.Search("brown fo*"), []Hit{{"a", 2}, {"b", 2}})
            	hEq(t, "earlier words stay whole", ix.Search("bro-fo*"), []Hit(nil))
            	hEq(t, "star in the middle is punctuation", ix.Search("q*uick"), ix.Search("q uick"))
            	ix.Add("e", "aa aab aac")
            	hEq(t, "all matching words are counted", ix.Search("aa*"), []Hit{{"e", 3}})
            }
        ''',
    ))

    S.append(Slice(
        id="paging", title="Result pages", d=2,
        pitch=("Common words produce hundreds of hits and the UI wants one page at a time.",
               "The search endpoint has to return results in pages."),
        reqs=("`Index.SearchPage(query string, page, size int) (hits []Hit, total int, err error)` returns page `page` (counting from 1) of the results `Search(query)` would give, `size` hits per page, and `total`, the number of hits in all pages.",
              "`page < 1` or `size < 1` is an error (`hits` nil, `total` 0). A page past the end is empty (`len(hits) == 0`) but `total` is still reported; the last page may be shorter."),
        code={
            "index.go::methods": '''
                // SearchPage returns one page of the results of Search.
                func (ix *Index) SearchPage(query string, page, size int) ([]Hit, int, error) {
                	if page < 1 || size < 1 {
                		return nil, 0, errors.New("page and size must be at least 1")
                	}
                	all := ix.Search(query)
                	start := (page - 1) * size
                	if start >= len(all) {
                		return []Hit{}, len(all), nil
                	}
                	end := start + size
                	if end > len(all) {
                		end = len(all)
                	}
                	return all[start:end], len(all), nil
                }
            ''',
        },
        readme="## Result pages\n\n`SearchPage(query, page, size)` returns `(hits, total, err)` for page `page` (from 1) of the results of `Search`.\n",
        vtests='''
            func TestPageBasic(t *testing.T) {
            	hits, total, err := vIndex().SearchPage("fox", 1, 2)
            	if err != nil || total != 3 || len(hits) != 2 {
            		t.Fatalf("%v %d %v", hits, total, err)
            	}
            }
        ''',
        tests='''
            func TestSearchPage(t *testing.T) {
            	ix := hIndex()
            	hits, total, err := ix.SearchPage("fox", 1, 2)
            	hEq(t, "page 1", []interface{}{hIDs(hits), total, err}, []interface{}{[]string{"a", "b"}, 3, error(nil)})
            	hits, total, _ = ix.SearchPage("fox", 2, 2)
            	hEq(t, "page 2", []interface{}{hIDs(hits), total}, []interface{}{[]string{"c"}, 3})
            	hits, total, err = ix.SearchPage("fox", 3, 2)
            	hEq(t, "past the end", []interface{}{len(hits), total, err}, []interface{}{0, 3, error(nil)})
            	hits, total, _ = ix.SearchPage("fox", 1, 50)
            	hEq(t, "one big page", []interface{}{len(hits), total}, []interface{}{3, 3})
            	hits, total, _ = ix.SearchPage("zebra", 1, 5)
            	hEq(t, "no results", []interface{}{len(hits), total}, []interface{}{0, 0})
            	first, _, _ := ix.SearchPage("quick fox", 1, 1)
            	hEq(t, "same order as Search", first[0], ix.Search("quick fox")[0])
            }

            func TestSearchPageErrors(t *testing.T) {
            	ix := hIndex()
            	for _, args := range [][2]int{{0, 5}, {-1, 5}, {1, 0}, {1, -3}} {
            		hits, total, err := ix.SearchPage("fox", args[0], args[1])
            		if err == nil || hits != nil || total != 0 {
            			t.Errorf("%v: %v %d %v", args, hits, total, err)
            		}
            	}
            }
        ''',
    ))

    S.append(Slice(
        id="any", title="Match any word", d=2,
        pitch=("`Search` is too strict when people list several alternative words.",
               "Sometimes people want documents that mention any of the words."),
        reqs=("`Index.SearchAny(query string) []Hit` returns the documents that contain **at least one** word of the query. The score is the sum, over the query's words, of how many times each occurs (a word repeated in the query counts once); ordering is the same as for `Search` (score descending, then id). A query without words returns `nil`.",),
        code={
            "index.go::methods": '''
                // SearchAny finds the documents that contain at least one word of the query.
                func (ix *Index) SearchAny(query string) []Hit {
                	terms := ix.parseQuery(query)
                	if len(terms) == 0 {
                		return nil
                	}
                	var hits []Hit
                	for id, d := range ix.docs {
                		score := 0
                		for _, q := range terms {
                			score += ix.matchCount(d, q)
                		}
                		if score > 0 {
                			hits = append(hits, Hit{ID: id, Score: score})
                		}
                	}
                	sortHits(hits)
                	return hits
                }
            ''',
        },
        readme="## Match any word\n\n`SearchAny(query)` returns documents containing at least one query word, scored like `Search`.\n",
        vtests='''
            func TestSearchAnyBasic(t *testing.T) {
            	if got := vIDs(vIndex().SearchAny("quick lazy")); !reflect.DeepEqual(got, []string{"a", "b", "c"}) {
            		t.Fatalf("got %v", got)
            	}
            }
        ''',
        tests='''
            func TestSearchAny(t *testing.T) {
            	ix := hIndex()
            	hEq(t, "quick lazy", ix.SearchAny("quick lazy"), []Hit{{"a", 2}, {"b", 2}, {"c", 1}})
            	hEq(t, "repeated word", ix.SearchAny("fox fox"), []Hit{{"a", 1}, {"b", 1}, {"c", 1}})
            	hEq(t, "one unknown word", ix.SearchAny("zebra red"), []Hit{{"b", 1}})
            	hEq(t, "superset of Search", len(ix.SearchAny("quick fox")) >= len(ix.Search("quick fox")), true)
            	hEq(t, "all words must not be needed", hIDs(ix.SearchAny("friends afternoons")), []string{"c", "d"})
            	if ix.SearchAny("") != nil || ix.SearchAny("zebra yak") != nil || ix.SearchAny("  ,. ") != nil {
            		t.Error("expected nil")
            	}
            }
        ''',
        cross={
            "prefix": {"tests": '''
                func TestSearchAnyAcceptsPrefixTerms(t *testing.T) {
                	ix := hIndex()
                	hEq(t, "prefix or word", ix.SearchAny("qui* zebra"), []Hit{{"b", 2}, {"a", 1}})
                	hEq(t, "prefix or prefix", hIDs(ix.SearchAny("fri* afte*")), []string{"c", "d"})
                }
            '''},
        },
    ))

    S.append(Slice(
        id="stemmer", title="Word normalisation", d=3,
        pitch=("`dog` does not find `dogs` and `box` does not find `boxes`.",
               "Plural forms should find each other, and teams want to plug in their own stemming."),
        reqs=("`Index.SetStemmer(fn func(string) string)` sets a function that is applied to every word of documents and queries after lower-casing (and after stop words are removed, if there are any); `nil` removes it. Setting it re-indexes the documents already stored. By default there is no stemming.",
              "`docindex.PluralStemmer(w string) string` is a ready-made stemmer that applies the first rule that fits: (1) a word longer than 4 letters ending in `ies` becomes the part before `ies` plus `y` (`parties` -> `party`); (2) a word longer than 3 letters ending in `es` whose letter before the `es` is `s`, `x` or `z`, or that ends in `ches` or `shes`, loses the `es` (`boxes` -> `box`, `glasses` -> `glass`, `dishes` -> `dish`); (3) a word longer than 3 letters ending in `s` but not `ss` loses the `s` (`dogs` -> `dog`); (4) anything else is unchanged (`class`, `bus`)."),
        code={
            "index.go::index_fields": "stem func(string) string",
            "index.go::term_map": '''
                if ix.stem != nil {
                	w = ix.stem(w)
                }
            ''',
            "index.go::methods": '''
                // SetStemmer sets the word normaliser and re-indexes the documents.
                func (ix *Index) SetStemmer(fn func(string) string) {
                	ix.stem = fn
                	for _, d := range ix.docs {
                		d.tokens = ix.terms(d.text)
                	}
                	@@slot on_reconfigure
                }

                // PluralStemmer strips common English plural endings.
                func PluralStemmer(w string) string {
                	n := len(w)
                	switch {
                	case n > 4 && strings.HasSuffix(w, "ies"):
                		return w[:n-3] + "y"
                	case n > 3 && strings.HasSuffix(w, "es") && (strings.ContainsRune("sxz", rune(w[n-3])) || strings.HasSuffix(w, "ches") || strings.HasSuffix(w, "shes")):
                		return w[:n-2]
                	case n > 3 && strings.HasSuffix(w, "s") && !strings.HasSuffix(w, "ss"):
                		return w[:n-1]
                	}
                	return w
                }
            ''',
        },
        readme="## Word normalisation\n\n`SetStemmer(fn)` applies `fn` to every word of documents and queries (re-indexing existing documents; `nil` removes it). `docindex.PluralStemmer` strips plural endings.\n",
        vtests='''
            func TestStemmerBasic(t *testing.T) {
            	ix := vIndex()
            	ix.SetStemmer(PluralStemmer)
            	if got := vIDs(ix.Search("dog")); len(got) != 4 {
            		t.Fatalf("got %v", got)
            	}
            }
        ''',
        tests='''
            func TestPluralStemmer(t *testing.T) {
            	for in, want := range map[string]string{
            		"foxes": "fox", "dogs": "dog", "parties": "party", "glasses": "glass", "boxes": "box", "dishes": "dish",
            		"churches": "church", "class": "class", "bus": "bus", "cats": "cat", "ties": "tie", "was": "was",
            		"fox": "fox", "series": "sery", "does": "doe", "": "",
            	} {
            		if got := PluralStemmer(in); got != want {
            			t.Errorf("PluralStemmer(%q) = %q, want %q", in, got, want)
            		}
            	}
            }

            func TestStemmerAppliesToDocumentsAndQueries(t *testing.T) {
            	ix := hIndex()
            	hEq(t, "before", hIDs(ix.Search("dog")), []string{"a", "b", "c"})
            	ix.SetStemmer(PluralStemmer)
            	hEq(t, "dog finds dogs", hIDs(ix.Search("dog")), []string{"a", "b", "c", "d"})
            	hEq(t, "foxes finds fox", hIDs(ix.Search("foxes")), []string{"a", "b", "c", "d"})
            	hEq(t, "dogs finds dog", hIDs(ix.Search("DOGS")), []string{"a", "b", "c", "d"})
            	ix.Add("e", "three boxes")
            	hEq(t, "new documents too", hIDs(ix.Search("box")), []string{"e"})
            	ix.SetStemmer(nil)
            	hEq(t, "removed", hIDs(ix.Search("dog")), []string{"a", "b", "c"})
            	hEq(t, "boxes is a word again", hIDs(ix.Search("box")), []string{})
            }

            func TestCustomStemmer(t *testing.T) {
            	ix := hIndex()
            	ix.SetStemmer(func(w string) string {
            		if len(w) > 3 {
            			return w[:3]
            		}
            		return w
            	})
            	hEq(t, "quick -> qui", ix.Search("quiet"), []Hit{{"b", 2}, {"a", 1}})
            	hEq(t, "brown -> bro", hIDs(ix.Search("brow")), []string{"a", "b"})
            }
        ''',
        cross={
            "stopwords": {
                "reqs": ("Stop words are compared before stemming (with the word as it was written, lower-cased); a stemmed word is not checked against the stop words again.",),
                "tests": '''
                    func TestStopwordsComeBeforeStemming(t *testing.T) {
                    	ix := hIndex()
                    	ix.SetStopwords("dogs")
                    	ix.SetStemmer(PluralStemmer)
                    	hEq(t, "dogs is a stop word", hIDs(ix.Search("dog")), []string{"a", "b", "c"})
                    	if ix.Search("dogs") != nil {
                    		t.Error("the stop word itself should not be searchable")
                    	}
                    }
                '''},
        },
    ))

    S.append(Slice(
        id="cache", title="Query cache", d=3,
        pitch=("The same few queries run thousands of times per minute against a rarely changing index.",
               "Repeated searches should be answered from memory."),
        reqs=("`Search` remembers its result for each exact query string (case and spacing included). Asking again with the identical string returns an equal result without searching, and `Index.CacheHits() int` counts how many searches were answered that way (0 at the start).",
              "`Add` and `Remove` forget everything that was remembered (a `Remove` of an id that does not exist does not). The slice that `Search` returns is the caller's own: changing it must not change what is remembered."),
        code={
            "index.go::index_fields": "cache     map[string][]Hit\ncacheHits int",
            "index.go::new_index": "ix.cache = map[string][]Hit{}",
            "index.go::on_change": "ix.cache = map[string][]Hit{}",
            "index.go::search_pre": '''
                if hits, ok := ix.cache[query]; ok {
                	ix.cacheHits++
                	return append([]Hit(nil), hits...)
                }
            ''',
            "index.go::search_post": "ix.cache[query] = append([]Hit(nil), hits...)",
            "index.go::methods": '''
                // CacheHits counts the searches answered from memory.
                func (ix *Index) CacheHits() int { return ix.cacheHits }
            ''',
        },
        readme="## Query cache\n\n`Search` remembers results per exact query string; `CacheHits()` counts repeats. `Add`/`Remove` clear the memory.\n",
        vtests='''
            func TestCacheBasic(t *testing.T) {
            	ix := vIndex()
            	ix.Search("fox")
            	ix.Search("fox")
            	if ix.CacheHits() != 1 {
            		t.Fatalf("hits %d", ix.CacheHits())
            	}
            }
        ''',
        tests='''
            func TestCacheCountsRepeats(t *testing.T) {
            	ix := hIndex()
            	hEq(t, "start", ix.CacheHits(), 0)
            	first := ix.Search("quick fox")
            	hEq(t, "first search", ix.CacheHits(), 0)
            	second := ix.Search("quick fox")
            	hEq(t, "second search", ix.CacheHits(), 1)
            	hEq(t, "same result", second, first)
            	ix.Search("QUICK FOX")
            	ix.Search("quick  fox")
            	hEq(t, "different strings miss", ix.CacheHits(), 1)
            	ix.Search("QUICK FOX")
            	hEq(t, "exact string hits", ix.CacheHits(), 2)
            	ix.Search("zebra")
            	hEq(t, "empty results are remembered too", []interface{}{ix.Search("zebra") == nil, ix.CacheHits()}, []interface{}{true, 3})
            }

            func TestCacheIsClearedByChanges(t *testing.T) {
            	ix := hIndex()
            	ix.Search("fox")
            	ix.Add("e", "a fox again")
            	hEq(t, "add invalidates", hIDs(ix.Search("fox")), []string{"a", "b", "c", "e"})
            	hEq(t, "no hit after add", ix.CacheHits(), 0)
            	ix.Search("fox")
            	hEq(t, "now cached", ix.CacheHits(), 1)
            	ix.Remove("nothing")
            	ix.Search("fox")
            	hEq(t, "failed remove keeps the cache", ix.CacheHits(), 2)
            	ix.Remove("e")
            	hEq(t, "remove invalidates", hIDs(ix.Search("fox")), []string{"a", "b", "c"})
            	hEq(t, "no hit after remove", ix.CacheHits(), 2)
            }

            func TestCachedResultsAreCopies(t *testing.T) {
            	ix := hIndex()
            	got := ix.Search("fox")
            	got[0].ID = "tampered"
            	again := ix.Search("fox")
            	got2 := ix.Search("fox")
            	got2[1].Score = 99
            	hEq(t, "first copy does not leak", again[0].ID, "a")
            	hEq(t, "second copy does not leak", ix.Search("fox")[1].Score, 1)
            }
        ''',
        cross={
            "stopwords": {
                "reqs": ("`SetStopwords` forgets the remembered results too.",),
                "code": {"index.go::on_reconfigure": "ix.cache = map[string][]Hit{}"},
                "tests": '''
                    func TestCacheClearedByStopwords(t *testing.T) {
                    	ix := hIndex()
                    	hEq(t, "before", ix.Search("the dog"), []Hit{{"a", 3}, {"c", 3}})
                    	ix.SetStopwords("the")
                    	hEq(t, "after", ix.Search("the dog"), []Hit{{"a", 1}, {"b", 1}, {"c", 1}})
                    }
                '''},
            "stemmer": {
                "reqs": ("`SetStemmer` forgets the remembered results too.",),
                "code": {"index.go::on_reconfigure": "ix.cache = map[string][]Hit{}"},
                "tests": '''
                    func TestCacheClearedByStemmer(t *testing.T) {
                    	ix := hIndex()
                    	hEq(t, "before", hIDs(ix.Search("dog")), []string{"a", "b", "c"})
                    	ix.SetStemmer(PluralStemmer)
                    	hEq(t, "after", hIDs(ix.Search("dog")), []string{"a", "b", "c", "d"})
                    }
                '''},
        },
    ))

    S.append(Slice(
        id="phrase", title="Phrase search", d=4,
        pitch=("`red fox` finds notes that mention a red car and a fox in different places.",
               "People want to search for exact phrases in quotes."),
        reqs=("A part of the query in double quotes is a **phrase**: it matches where its words occur consecutively in a document, in that order. Outside quotes words work as before. A phrase counts in the score once for every place it occurs (overlapping places all count: `ha ha` occurs twice in `ha ha ha`). A document matches only if every term of the query, phrase or word, matches.",
              "A phrase is split into words exactly like document text. A phrase of one word is an ordinary word; a phrase without words (`\"\"`) is ignored; a quote that is never closed makes the rest of the query a phrase. Quotes may follow a word directly (`fox\"red fox\"` is the word `fox` and the phrase `red fox`)."),
        code={
            "index.go::qterm_fields": "phrase []string",
            "index.go::split_query": '''
                func splitQuery(query string) []string {
                	var pieces []string
                	var cur strings.Builder
                	inQuote := false
                	flush := func() {
                		if cur.Len() > 0 {
                			pieces = append(pieces, cur.String())
                			cur.Reset()
                		}
                	}
                	for _, r := range query {
                		switch {
                		case r == '"' && !inQuote:
                			flush()
                			cur.WriteRune(r)
                			inQuote = true
                		case r == '"' && inQuote:
                			cur.WriteRune(r)
                			flush()
                			inQuote = false
                		case unicode.IsSpace(r) && !inQuote:
                			flush()
                		default:
                			cur.WriteRune(r)
                		}
                	}
                	flush()
                	return pieces
                }
            ''',
            "index.go::piece_special": '''
                if strings.HasPrefix(piece, "\\"") {
                	words := ix.terms(piece)
                	switch len(words) {
                	case 0:
                	case 1:
                		out = append(out, qterm{text: words[0]})
                	default:
                		out = append(out, qterm{phrase: words})
                	}
                	continue
                }
            ''',
            "index.go::match_special": '''
                if q.phrase != nil {
                	n := 0
                	for i := 0; i+len(q.phrase) <= len(d.tokens); i++ {
                		match := true
                		for k, w := range q.phrase {
                			if d.tokens[i+k] != w {
                				match = false
                				break
                			}
                		}
                		if match {
                			n++
                		}
                	}
                	return n
                }
            ''',
        },
        readme="## Phrase search\n\nQuery parts in double quotes are phrases: their words must occur consecutively (every occurrence counts, overlaps included). A one-word phrase is a plain word, `\"\"` is ignored, an unclosed quote runs to the end.\n",
        vtests='''
            func TestPhraseBasic(t *testing.T) {
            	if got := vIDs(vIndex().Search("\\"brown fox\\"")); !reflect.DeepEqual(got, []string{"a"}) {
            		t.Fatalf("got %v", got)
            	}
            }
        ''',
        tests='''
            func TestPhrases(t *testing.T) {
            	ix := hIndex()
            	hEq(t, "brown fox", ix.Search("\\"brown fox\\""), []Hit{{"a", 1}})
            	hEq(t, "quick brown", ix.Search("\\"quick brown\\""), []Hit{{"a", 1}, {"b", 1}})
            	hEq(t, "order matters", ix.Search("\\"fox brown\\""), []Hit(nil))
            	hEq(t, "words need not be adjacent without quotes", hIDs(ix.Search("red fox")), []string{"b"})
            	hEq(t, "phrase plus word", ix.Search("fox \\"quick brown\\""), []Hit{{"a", 2}, {"b", 2}})
            	hEq(t, "word plus phrase after it", ix.Search("\\"quick brown\\" fox"), []Hit{{"a", 2}, {"b", 2}})
            	hEq(t, "case and punctuation", ix.Search("\\"Lazy  AFTERNOONS: the\\""), []Hit{{"c", 1}})
            	hEq(t, "word glued to a quote", ix.Search("fox\\"quick brown\\""), []Hit{{"a", 2}, {"b", 2}})
            }

            func TestPhraseEdgeCases(t *testing.T) {
            	ix := hIndex()
            	hEq(t, "one word is a word", ix.Search("\\"fox\\""), ix.Search("fox"))
            	hEq(t, "empty phrase is ignored", ix.Search("\\"\\" fox"), ix.Search("fox"))
            	if ix.Search("\\"\\"") != nil || ix.Search("\\"") != nil || ix.Search("\\" ,; \\"") != nil {
            		t.Error("queries without words should return nil")
            	}
            	hEq(t, "unclosed quote", ix.Search("\\"lazy dog"), []Hit{{"a", 1}})
            	hEq(t, "unclosed quote after a word", ix.Search("fox \\"lazy dog"), []Hit{{"a", 2}})
            	ix.Add("h", "ha ha ha ho")
            	hEq(t, "overlapping occurrences", ix.Search("\\"ha ha\\""), []Hit{{"h", 2}})
            	hEq(t, "phrase longer than the document", ix.Search("\\"ha ha ha ho ho\\""), []Hit(nil))
            	hEq(t, "phrase equal to the whole document", ix.Search("\\"ha ha ha ho\\""), []Hit{{"h", 1}})
            }
        ''',
        cross={
            "any": {"tests": '''
                func TestSearchAnyAcceptsPhrases(t *testing.T) {
                	ix := hIndex()
                	hEq(t, "two phrases", ix.SearchAny("\\"brown fox\\" \\"red fox\\""), []Hit{{"a", 1}, {"b", 1}})
                	hEq(t, "phrase or word", ix.SearchAny("\\"brown fox\\" friends"), []Hit{{"a", 1}, {"d", 1}})
                }
            '''},
            "prefix": {
                "reqs": ("Inside quotes a `*` is just punctuation (it separates words), so phrases have no prefix terms.",),
                "tests": '''
                    func TestStarInsidePhraseIsPunctuation(t *testing.T) {
                    	ix := hIndex()
                    	hEq(t, "brown fo*", ix.Search("\\"brown fo*\\""), []Hit(nil))
                    	hEq(t, "quick* brown", ix.Search("\\"quick* brown\\""), ix.Search("\\"quick brown\\""))
                    }
                '''},
            "stopwords": {
                "reqs": ("Stop words are dropped from phrases before the words are compared, so with `the` as a stop word the phrase `\"dog the fox\"` and the document text `the dog the fox` both reduce to `dog fox`.",),
                "tests": '''
                    func TestPhrasesIgnoreStopwords(t *testing.T) {
                    	ix := New()
                    	ix.SetStopwords("the")
                    	ix.Add("p", "see the dog the fox run")
                    	ix.Add("q", "dog and fox")
                    	hEq(t, "stop word inside the phrase", hIDs(ix.Search("\\"dog the fox\\"")), []string{"p"})
                    	hEq(t, "adjacent after dropping", hIDs(ix.Search("\\"dog fox\\"")), []string{"p"})
                    }
                '''},
            "stemmer": {
                "reqs": ("Phrase words are stemmed like all other words.",),
                "tests": '''
                    func TestPhrasesAreStemmed(t *testing.T) {
                    	ix := New()
                    	ix.SetStemmer(PluralStemmer)
                    	ix.Add("p", "two red foxes ran")
                    	hEq(t, "plural in the phrase", hIDs(ix.Search("\\"red fox\\"")), []string{"p"})
                    	hEq(t, "plural in the document", hIDs(ix.Search("\\"red foxes ran\\"")), []string{"p"})
                    }
                '''},
        },
    ))

    order = ["stopwords", "phrase", "prefix", "paging", "any", "stemmer", "cache"]
    S.sort(key=lambda x: order.index(x.id))
    return S


APP = App(
    name="docindex", lang="go", title="the note search library", role="a note-taking app developer", key="IDX",
    base={
        "README.md": README + "\n@@blocks features\n",
        "go.mod": langs.go_mod("docindex"),
        "index.go": INDEX,
        ".gitignore": "*.test\n",
    },
    visible={"index_test.go": VISIBLE},
    hidden={"features_test.go": HIDDEN},
)

register_app("feature-go-docindex", APP, make_slices, n=16, summary="note search index: stop words, prefixes, paging, OR search, stemming, cache, phrases")
