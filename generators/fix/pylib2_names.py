"""Text-format libraries (python), batch: personal names."""
from fx import Lib, dd, register_libs

# ======================================================================================================================
# namefmt: parsing and formatting of personal names with titles, particles and suffixes
# ======================================================================================================================

NF_README = dd(r'''
    # namefmt

    Name handling for the mailing-list tool. One module, `namefmt.py`.

    ## Word lists
    All comparisons ignore case and remove every `.` first (`Ph.D.` is `phd`).
    * titles: `dr prof mr mrs ms mx sir dame rev`
    * suffixes: `jr sr ii iii iv phd md esq`
    * particles: `de del della di da dos du van von der den ten ter la le bin ibn`

    ## `parse_name(text) -> Name`
    `Name` is a `namedtuple` `(title, given, family, suffix)` of strings (`""` when absent). Titles and suffixes keep the spelling they were written
    with (`Dr.`, `Jr`); several tokens are joined by single spaces. Surrounding blanks are ignored and tokens are separated by any run of whitespace.

    The text is split at commas into parts (each stripped); an empty part, or more than three parts, is a `ValueError`; empty text is a `ValueError`.
    * **One part** (`First Middle Last`): the tokens are `[titles] given... family... [suffixes]`. Leading title tokens are taken as the title and trailing
      suffix tokens as the suffix, but never the last remaining token (so `Dr.` alone and `Jr.` alone are family names). Of the rest, the last token starts the
      family name; the particle tokens directly in front of it are part of the family name too, but at least one token (the first) always stays with
      the given names. A single remaining token is the family name and `given` is `""`. (`Ludwig van Beethoven` has family `van Beethoven`; `Van Morrison`
      has given `Van`.)
    * **Two parts** (`Family, First Middle`): the first part is the family name as written. The second part is split into leading titles, trailing
      suffixes and the given names; here everything may be consumed, so `Smith, Jr.` has an empty `given`.
    * **Three parts** (`Family, First Middle, Suffix`): like two parts, and the third part must consist only of suffix tokens (otherwise `ValueError`), which
      become `suffix`; a suffix also found in the second part is a `ValueError`.

    ## `format_name(name, style="full") -> str`
    * `full`: title, given, family, suffix, the non-empty ones separated by a space.
    * `short`: the first given token (if any) and the family name.
    * `initials`: the initials of the given tokens, then the family name (the given part is left out if empty). The initial of a token is its first letter
      in upper case followed by `.`; a hyphenated token gives one initial per hyphen-separated piece, joined by `-` (`Mary-Jane` gives `M.-J.`); `J.` gives `J.`.
    * `cite`: the family name, then `, ` and the initials (if there is a given part), then `, ` and the suffix (if any): `Public, J. Q., Jr.`.
    * `sort`: the leading particles of the family name (the particle tokens at its start, never its last token) are moved behind the given names. The result is
      the rest of the family name, then `, ` and the given names followed by those particles (all non-empty pieces separated by a space; omitted completely
      when there are none), then `, ` and the suffix if any: `Beethoven, Ludwig van`, `Public, John Q., Jr.`.
    The title is only used by `full`. Any other style is a `ValueError`.

    ## `sort_key(text) -> tuple`
    `parse_name(text)` reduced to `(family without leading particles, given, suffix without dots)`, each part case-folded. `sort_names(texts) -> list` sorts
    name texts by this key (stable).
''')

NF_SRC = dd(r'''
    """Personal names."""
    from collections import namedtuple

    Name = namedtuple("Name", "title given family suffix")

    TITLES = {"dr", "prof", "mr", "mrs", "ms", "mx", "sir", "dame", "rev"}
    SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "phd", "md", "esq"}
    PARTICLES = {"de", "del", "della", "di", "da", "dos", "du", "van", "von", "der", "den", "ten", "ter", "la", "le", "bin", "ibn"}


    def _norm(token):
        return token.lower().replace(".", "")


    def _peel(tokens, keep_one):
        """Split off leading titles and trailing suffixes."""
        lo, hi = 0, len(tokens)
        floor = 1 if keep_one else 0
        while hi - lo > floor and _norm(tokens[lo]) in TITLES:
            lo += 1
        while hi - lo > floor and _norm(tokens[hi - 1]) in SUFFIXES:
            hi -= 1
        return " ".join(tokens[:lo]), tokens[lo:hi], " ".join(tokens[hi:])


    def parse_name(text):
        text = text.strip()
        if not text:
            raise ValueError("empty name")
        parts = [p.strip() for p in text.split(",")]
        if any(not p for p in parts) or len(parts) > 3:
            raise ValueError("bad commas in name")
        if len(parts) == 1:
            title, toks, suffix = _peel(parts[0].split(), True)
            start = len(toks) - 1
            while start > 1 and _norm(toks[start - 1]) in PARTICLES:
                start -= 1
            if len(toks) == 1:
                start = 0
            return Name(title, " ".join(toks[:start]), " ".join(toks[start:]), suffix)
        title, toks, suffix = _peel(parts[1].split(), False)
        if len(parts) == 3:
            extra = parts[2].split()
            if any(_norm(t) not in SUFFIXES for t in extra) or suffix:
                raise ValueError("bad suffix")
            suffix = " ".join(extra)
        return Name(title, " ".join(toks), parts[0], suffix)


    def _initials(given):
        out = []
        for tok in given.split():
            out.append("-".join(p[0].upper() + "." for p in tok.split("-") if p))
        return " ".join(out)


    def _split_family(family):
        toks = family.split()
        k = 0
        while k < len(toks) - 1 and _norm(toks[k]) in PARTICLES:
            k += 1
        return " ".join(toks[:k]), " ".join(toks[k:])


    def format_name(name, style="full"):
        if style == "full":
            return " ".join(x for x in (name.title, name.given, name.family, name.suffix) if x)
        if style == "short":
            return " ".join(x for x in (name.given.split()[0] if name.given else "", name.family) if x)
        if style == "initials":
            return " ".join(x for x in (_initials(name.given), name.family) if x)
        if style == "cite":
            out = name.family
            if name.given:
                out += ", " + _initials(name.given)
            if name.suffix:
                out += ", " + name.suffix
            return out
        if style == "sort":
            lead, core = _split_family(name.family)
            tail = " ".join(x for x in (name.given, lead) if x)
            out = core + (", " + tail if tail else "")
            if name.suffix:
                out += ", " + name.suffix
            return out
        raise ValueError("unknown style: %r" % (style,))


    def sort_key(text):
        name = parse_name(text)
        return (_split_family(name.family)[1].casefold(), name.given.casefold(), name.suffix.replace(".", "").casefold())


    def sort_names(texts):
        return sorted(texts, key=sort_key)
''')

NF_VISIBLE = dd(r'''
    import unittest

    from namefmt import Name, format_name, parse_name, sort_names


    class BasicTests(unittest.TestCase):
        def test_parse(self):
            self.assertEqual(parse_name("Dr. John Q. Public Jr."), Name("Dr.", "John Q.", "Public", "Jr."))

        def test_particles(self):
            self.assertEqual(parse_name("Ludwig van Beethoven"), Name("", "Ludwig", "van Beethoven", ""))

        def test_format(self):
            self.assertEqual(format_name(Name("", "Ludwig", "van Beethoven", ""), "sort"), "Beethoven, Ludwig van")

        def test_sort(self):
            self.assertEqual(sort_names(["Zed Young", "Ann Able"]), ["Ann Able", "Zed Young"])


    if __name__ == "__main__":
        unittest.main()
''')

NF_HIDDEN = dd(r'''
    import unittest

    from namefmt import Name, format_name, parse_name, sort_key, sort_names


    def N(title="", given="", family="", suffix=""):
        return Name(title, given, family, suffix)


    class OnePart(unittest.TestCase):
        def test_plain(self):
            self.assertEqual(parse_name("John Q. Public"), N("", "John Q.", "Public"))
            self.assertEqual(parse_name("Ada Lovelace"), N("", "Ada", "Lovelace"))
            self.assertEqual(parse_name("Ada Augusta King Lovelace"), N("", "Ada Augusta King", "Lovelace"))
            self.assertEqual(parse_name("  John    Public  "), N("", "John", "Public"))
            self.assertEqual(parse_name("John\tPublic"), N("", "John", "Public"))

        def test_mononym(self):
            self.assertEqual(parse_name("Cher"), N("", "", "Cher"))

        def test_titles(self):
            self.assertEqual(parse_name("Dr. John Q. Public"), N("Dr.", "John Q.", "Public"))
            self.assertEqual(parse_name("Prof. Dr. Ada Lovelace"), N("Prof. Dr.", "Ada", "Lovelace"))
            self.assertEqual(parse_name("dr ada lovelace"), N("dr", "ada", "lovelace"))
            self.assertEqual(parse_name("Mrs Jane Doe"), N("Mrs", "Jane", "Doe"))
            self.assertEqual(parse_name("Sir Isaac Newton"), N("Sir", "Isaac", "Newton"))
            self.assertEqual(parse_name("Dr. Who"), N("Dr.", "", "Who"))

        def test_lone_title_or_suffix_stays_a_name(self):
            self.assertEqual(parse_name("Dr."), N("", "", "Dr."))
            self.assertEqual(parse_name("Jr."), N("", "", "Jr."))
            self.assertEqual(parse_name("Dr. Jr."), N("Dr.", "", "Jr."))
            self.assertEqual(parse_name("Dr. Prof."), N("Dr.", "", "Prof."))

        def test_titles_only_at_the_start_suffixes_only_at_the_end(self):
            self.assertEqual(parse_name("John Dr. Smith"), N("", "John Dr.", "Smith"))
            self.assertEqual(parse_name("Jr. Smith"), N("", "Jr.", "Smith"))
            self.assertEqual(parse_name("John Smith Dr."), N("", "John Smith", "Dr."))

        def test_suffixes(self):
            self.assertEqual(parse_name("John Smith Jr."), N("", "John", "Smith", "Jr."))
            self.assertEqual(parse_name("John Smith Jr"), N("", "John", "Smith", "Jr"))
            self.assertEqual(parse_name("Henry Tudor III"), N("", "Henry", "Tudor", "III"))
            self.assertEqual(parse_name("Ann Lee Ph.D. MD"), N("", "Ann", "Lee", "Ph.D. MD"))
            self.assertEqual(parse_name("Henry III"), N("", "", "Henry", "III"))
            self.assertEqual(parse_name("Dr. Ann Lee Ph.D."), N("Dr.", "Ann", "Lee", "Ph.D."))
            self.assertEqual(parse_name("Bob Ng ESQ."), N("", "Bob", "Ng", "ESQ."))

        def test_particles(self):
            self.assertEqual(parse_name("Ludwig van Beethoven"), N("", "Ludwig", "van Beethoven"))
            self.assertEqual(parse_name("Maria de la Cruz"), N("", "Maria", "de la Cruz"))
            self.assertEqual(parse_name("Vincent van der Berg"), N("", "Vincent", "van der Berg"))
            self.assertEqual(parse_name("Leonardo da Vinci"), N("", "Leonardo", "da Vinci"))
            self.assertEqual(parse_name("Ada VON Braun"), N("", "Ada", "VON Braun"))
            self.assertEqual(parse_name("Hans Christian von der Heide"), N("", "Hans Christian", "von der Heide"))

        def test_particle_at_the_start_stays_given(self):
            self.assertEqual(parse_name("Van Morrison"), N("", "Van", "Morrison"))
            self.assertEqual(parse_name("De Niro"), N("", "De", "Niro"))
            self.assertEqual(parse_name("Van Der Berg"), N("", "Van", "Der Berg"))
            self.assertEqual(parse_name("De La Cruz"), N("", "De", "La Cruz"))

        def test_particle_only_directly_before_the_last_token(self):
            self.assertEqual(parse_name("Ann van Berg Smith"), N("", "Ann van Berg", "Smith"))
            self.assertEqual(parse_name("Ann Van Dyke Jr."), N("", "Ann", "Van Dyke", "Jr."))

        def test_hyphens_and_dots(self):
            self.assertEqual(parse_name("Mary-Jane Watson-Parker"), N("", "Mary-Jane", "Watson-Parker"))
            self.assertEqual(parse_name("J. R. R. Tolkien"), N("", "J. R. R.", "Tolkien"))

        def test_errors(self):
            for bad in ("", "   ", "\t\n"):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    parse_name(bad)


    class CommaForms(unittest.TestCase):
        def test_two_parts(self):
            self.assertEqual(parse_name("Smith, John"), N("", "John", "Smith"))
            self.assertEqual(parse_name("van Beethoven, Ludwig"), N("", "Ludwig", "van Beethoven"))
            self.assertEqual(parse_name("  Smith ,  John  Q.  "), N("", "John Q.", "Smith"))
            self.assertEqual(parse_name("Smith, Dr. John"), N("Dr.", "John", "Smith"))
            self.assertEqual(parse_name("Smith, Dr. John Jr."), N("Dr.", "John", "Smith", "Jr."))
            self.assertEqual(parse_name("Smith, John Q. III"), N("", "John Q.", "Smith", "III"))

        def test_family_part_is_taken_as_written(self):
            self.assertEqual(parse_name("de la Cruz, Maria"), N("", "Maria", "de la Cruz"))
            self.assertEqual(parse_name("Smith Jones, Ann"), N("", "Ann", "Smith Jones"))
            self.assertEqual(parse_name("Dr, Ann"), N("", "Ann", "Dr"))

        def test_everything_may_be_consumed_after_a_comma(self):
            self.assertEqual(parse_name("Smith, Jr."), N("", "", "Smith", "Jr."))
            self.assertEqual(parse_name("Smith, Dr."), N("Dr.", "", "Smith"))
            self.assertEqual(parse_name("Smith, Dr. Jr."), N("Dr.", "", "Smith", "Jr."))

        def test_three_parts(self):
            self.assertEqual(parse_name("Smith, John, Jr."), N("", "John", "Smith", "Jr."))
            self.assertEqual(parse_name("Smith, Dr. John, Sr."), N("Dr.", "John", "Smith", "Sr."))
            self.assertEqual(parse_name("Lee, Ann, Ph.D. MD"), N("", "Ann", "Lee", "Ph.D. MD"))
            self.assertEqual(parse_name("Tudor, Henry, III"), N("", "Henry", "Tudor", "III"))

        def test_errors(self):
            for bad in ("Smith,", ", John", "Smith,,John", "a, b, c, d", "Smith, John, Bob", "Smith, John Jr., Sr.", "Smith, John, Jr. Bob", ",", ",,", "Smith, John,",
                        "Smith, John, , Jr."):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    parse_name(bad)


    class Formats(unittest.TestCase):
        BEETHOVEN = N("", "Ludwig", "van Beethoven")
        PUBLIC = N("Dr.", "John Q.", "Public", "Jr.")

        def test_full(self):
            self.assertEqual(format_name(self.PUBLIC), "Dr. John Q. Public Jr.")
            self.assertEqual(format_name(self.PUBLIC, "full"), "Dr. John Q. Public Jr.")
            self.assertEqual(format_name(self.BEETHOVEN), "Ludwig van Beethoven")
            self.assertEqual(format_name(N("", "", "Cher")), "Cher")
            self.assertEqual(format_name(N("Dr.", "", "Who")), "Dr. Who")

        def test_short(self):
            self.assertEqual(format_name(self.PUBLIC, "short"), "John Public")
            self.assertEqual(format_name(self.BEETHOVEN, "short"), "Ludwig van Beethoven")
            self.assertEqual(format_name(N("", "", "Cher"), "short"), "Cher")
            self.assertEqual(format_name(N("", "Mary-Jane Ann", "Watson"), "short"), "Mary-Jane Watson")

        def test_initials(self):
            self.assertEqual(format_name(self.PUBLIC, "initials"), "J. Q. Public")
            self.assertEqual(format_name(self.BEETHOVEN, "initials"), "L. van Beethoven")
            self.assertEqual(format_name(N("", "Mary-Jane", "Watson"), "initials"), "M.-J. Watson")
            self.assertEqual(format_name(N("", "jean-luc", "picard"), "initials"), "J.-L. picard")
            self.assertEqual(format_name(N("", "J.", "Smith"), "initials"), "J. Smith")
            self.assertEqual(format_name(N("", "J. R. R.", "Tolkien"), "initials"), "J. R. R. Tolkien")
            self.assertEqual(format_name(N("", "", "Cher"), "initials"), "Cher")
            self.assertEqual(format_name(N("", "Ann Marie Lou", "X"), "initials"), "A. M. L. X")

        def test_cite(self):
            self.assertEqual(format_name(self.PUBLIC, "cite"), "Public, J. Q., Jr.")
            self.assertEqual(format_name(self.BEETHOVEN, "cite"), "van Beethoven, L.")
            self.assertEqual(format_name(N("", "", "Cher"), "cite"), "Cher")
            self.assertEqual(format_name(N("", "", "Smith", "Jr."), "cite"), "Smith, Jr.")
            self.assertEqual(format_name(N("", "Mary-Jane", "Watson"), "cite"), "Watson, M.-J.")

        def test_sort(self):
            self.assertEqual(format_name(self.PUBLIC, "sort"), "Public, John Q., Jr.")
            self.assertEqual(format_name(self.BEETHOVEN, "sort"), "Beethoven, Ludwig van")
            self.assertEqual(format_name(N("", "Maria", "de la Cruz"), "sort"), "Cruz, Maria de la")
            self.assertEqual(format_name(N("", "", "van Beethoven"), "sort"), "Beethoven, van")
            self.assertEqual(format_name(N("", "", "Cher"), "sort"), "Cher")
            self.assertEqual(format_name(N("", "Van", "Morrison"), "sort"), "Morrison, Van")
            self.assertEqual(format_name(N("", "Ann", "Van"), "sort"), "Van, Ann")
            self.assertEqual(format_name(N("", "", "de la"), "sort"), "la, de")
            self.assertEqual(format_name(N("", "Ann", "Smith", "III"), "sort"), "Smith, Ann, III")
            self.assertEqual(format_name(N("", "", "Smith", "Jr."), "sort"), "Smith, Jr.")
            self.assertEqual(format_name(N("", "Hans", "von der Heide", "Sr."), "sort"), "Heide, Hans von der, Sr.")

        def test_unknown_style(self):
            for style in ("", "FULL", "last-first", None):
                with self.assertRaises(ValueError):
                    format_name(self.PUBLIC, style)

        def test_round_trip_through_full(self):
            for text in ("John Q. Public", "Dr. John Q. Public Jr.", "Ludwig van Beethoven", "Cher", "Dr. Who"):
                self.assertEqual(parse_name(format_name(parse_name(text), "full")), parse_name(text))


    class Sorting(unittest.TestCase):
        def test_key(self):
            self.assertEqual(sort_key("Ludwig van Beethoven"), ("beethoven", "ludwig", ""))
            self.assertEqual(sort_key("Dr. John Q. Public Jr."), ("public", "john q.", "jr"))
            self.assertEqual(sort_key("Public, John Q., Ph.D."), ("public", "john q.", "phd"))
            self.assertEqual(sort_key("Cher"), ("cher", "", ""))
            self.assertEqual(sort_key("Van Morrison"), ("morrison", "van", ""))
            self.assertEqual(sort_key("Maria de la Cruz"), ("cruz", "maria", ""))
            self.assertEqual(sort_key("ADA LOVELACE"), ("lovelace", "ada", ""))

        def test_sort_names(self):
            names = ["Ludwig van Beethoven", "Alan Turing", "Ada Lovelace", "Dr. Ada King", "Vincent van Gogh", "Zed Aaron", "Maria de la Cruz", "Cher"]
            self.assertEqual(sort_names(names), ["Zed Aaron", "Ludwig van Beethoven", "Cher", "Maria de la Cruz", "Vincent van Gogh", "Dr. Ada King", "Ada Lovelace", "Alan Turing"])

        def test_ties_use_given_then_suffix(self):
            names = ["John Smith Jr.", "John Smith", "Ann Smith", "John Smith Sr.", "Smith, Zoe"]
            self.assertEqual(sort_names(names), ["Ann Smith", "John Smith", "John Smith Jr.", "John Smith Sr.", "Smith, Zoe"])

        def test_stable_for_equal_keys(self):
            names = ["Ann Lee", "ann lee", "ANN LEE"]
            self.assertEqual(sort_names(names), names)

        def test_case_insensitive(self):
            self.assertEqual(sort_names(["bob Zed", "Al Young", "cy ABEL"]), ["cy ABEL", "Al Young", "bob Zed"])

        def test_errors_propagate(self):
            with self.assertRaises(ValueError):
                sort_names(["Ann Lee", ""])


    if __name__ == "__main__":
        unittest.main()
''')

NF = Lib(
    name="namefmt", lang="python", title="the personal-name helpers (`namefmt.py`)",
    blurb="The mailing-list tool parses, prints and sorts personal names with this module.",
    files={"namefmt.py": NF_SRC, "README.md": NF_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": NF_VISIBLE},
    hidden_tests={"tests/test_full.py": NF_HIDDEN},
    mutate=["namefmt.py"], difficulty=2, tags=["names", "text"],
    probes=[
        'parse_name("Dr. John Q. Public Jr.")',
        'parse_name("Vincent van der Berg")',
        'parse_name("Van Morrison")',
        'parse_name("Ann van Berg Smith")',
        'parse_name("Smith, Jr.")',
        'parse_name("Smith, Dr. John, Sr.")',
        'parse_name("Dr. Jr.")',
        'format_name(parse_name("Ludwig van Beethoven"), "sort")',
        'format_name(parse_name("Mary-Jane Watson"), "initials")',
        'format_name(parse_name("Dr. John Q. Public Jr."), "cite")',
        'format_name(parse_name("Dr. John Q. Public Jr."), "short")',
        'sort_key("Public, John Q., Ph.D.")',
        'sort_names(["John Smith Jr.", "John Smith", "Ann Smith", "Maria de la Cruz"])',
    ],
    probe_import="from namefmt import *",
)


LIBS = [NF]
register_libs(LIBS, n=10)
