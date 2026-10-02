"""Native bug-fix family in Dutch: name parsing with tussenvoegsels, IJ title case, postcode and BSN (python)."""
from fx import Lib, dd

from ._native import register_native

README = dd(r'''
    # nlnamen

    Hulpfuncties voor het ledenbestand van een Nederlandse sportvereniging: namen splitsen en sorteren, titels met de juiste
    hoofdletters, postcodes normaliseren en een BSN controleren. Alleen de standaardbibliotheek. Alle gegevens in voorbeelden
    en tests zijn verzonnen.

    ## Tussenvoegsels

    De tussenvoegsels zijn (zonder onderscheid tussen hoofd- en kleine letters): `van de der den het 't te ten ter op in aan
    bij`. De constante heet `TUSSENVOEGSELS`.

    ### `split_naam(volledige_naam) -> tuple`
    Splitst een volledige naam (woorden gescheiden door witruimte, overtollige witruimte telt niet mee) in
    `(voornamen, tussenvoegsel, achternaam)`, elk een string zoals de woorden in de invoer geschreven staan, met één spatie
    ertussen. Regels:

    * Geen woorden -> `ValueError`. Eén woord -> `("", "", woord)`.
    * Zoek vanaf het tweede woord het eerste woord dat een tussenvoegsel is. Het tussenvoegsel is die reeks aaneengesloten
      tussenvoegsel-woorden; de achternaam is alles wat erna komt, de voornamen alles wat ervoor staat. Komt er na de
      reeks niets meer, dan is er geen achternaam en volgt een `ValueError` (`"Jan van"`).
    * Is er geen tussenvoegsel, dan is het laatste woord de achternaam en de rest de voornamen, het tussenvoegsel is `""`.
    * Het eerste woord is altijd (onderdeel van) de voornamen, ook als het een tussenvoegsel lijkt (`"De Jong"` bij één
      woord is gewoon de achternaam, bij `"Dick de Jong"` begint de zoektocht bij het tweede woord).

    ### `sorteer_sleutel(volledige_naam) -> tuple`
    Sorteersleutel `(achternaam, voornamen)`, beide in kleine letters, met het tussenvoegsel genegeerd (`Jan van der Berg`
    sorteert onder de B) en met `ij` vervangen door `y` (zodat `IJsselstein` na `Hoorn` en voor `Zwolle` komt). Fouten van
    `split_naam` blijven `ValueError`.

    ### `achternaam_eerst(volledige_naam) -> str`
    `"Berg, Jan van der"`: achternaam, komma, spatie, voornamen en (als dat er is) het tussenvoegsel erachter, zoals in de naam
    geschreven. Zijn er geen voornamen (één woord), dan alleen de achternaam, zonder komma.

    ## Hoofdletters

    ### `titel_nl(s) -> str`
    Zet een titel of naam om. De tekst wordt in delen gesneden op spaties en op `-`; de scheidingstekens blijven staan zoals ze
    waren (ook meerdere spaties). Voor elk deel (onafhankelijk van hoe het was getypt):

    * Is het een tussenvoegsel (`TUSSENVOEGSELS`) en is het **niet** het eerste deel van de tekst, dan wordt het volledig kleine
      letters.
    * Begint het met `ij` (in welke hoofdletterstand ook), dan worden de eerste twee letters `IJ` en de rest kleine letters
      (`ijsje` -> `IJsje`, `IJSSELMEER` -> `IJsselmeer`).
    * Anders: eerste teken hoofdletter, de rest kleine letters.

    Voorbeelden: `"jan van der berg"` -> `"Jan van der Berg"`, `"anne-marie van den berg"` -> `"Anne-Marie van den Berg"`,
    `"de jong"` -> `"De Jong"`.

    ## Postcode

    ### `normaliseer_postcode(tekst) -> str`
    Maakt van een postcode de vorm `"1234 AB"`. Eerst worden spaties en tabs aan de uiteinden weggehaald; daarna moeten er vier
    cijfers volgen waarvan het eerste niet `0` is, hoogstens **één** spatie en twee letters `A`-`Z` of `a`-`z`. De letters mogen
    niet `SA`, `SD` of `SS` zijn (in welke hoofdletterstand ook). Het resultaat heeft altijd precies één spatie en
    hoofdletters. Al het andere is een `ValueError`.

    ## BSN

    ### `bsn_geldig(bsn) -> bool`
    Het BSN bestaat uit 9 cijfers (ASCII); een nummer van 8 cijfers krijgt er links een `0` voor. Andere lengtes of andere tekens
    zijn ongeldig. De elfproef: vermenigvuldig de cijfers van links naar rechts met `9 8 7 6 5 4 3 2 -1`, tel op; de som moet
    deelbaar zijn door 11 en mag niet 0 zijn (`000000000` is ongeldig).
''')

SRC = dd(r'''
    import re

    TUSSENVOEGSELS = frozenset(["van", "de", "der", "den", "het", "'t", "te", "ten", "ter", "op", "in", "aan", "bij"])
    _POSTCODE = re.compile(r"([1-9][0-9]{3}) ?([A-Za-z]{2})")
    _WEIGHTS = (9, 8, 7, 6, 5, 4, 3, 2, -1)


    def split_naam(volledige_naam: str):
        words = volledige_naam.split()
        if not words:
            raise ValueError("lege naam")
        if len(words) == 1:
            return ("", "", words[0])
        for i in range(1, len(words)):
            if words[i].lower() in TUSSENVOEGSELS:
                j = i
                while j < len(words) and words[j].lower() in TUSSENVOEGSELS:
                    j += 1
                if j == len(words):
                    raise ValueError("geen achternaam")
                return (" ".join(words[:i]), " ".join(words[i:j]), " ".join(words[j:]))
        return (" ".join(words[:-1]), "", words[-1])


    def sorteer_sleutel(volledige_naam: str):
        voornamen, _, achternaam = split_naam(volledige_naam)
        return (achternaam.lower().replace("ij", "y"), voornamen.lower().replace("ij", "y"))


    def achternaam_eerst(volledige_naam: str) -> str:
        voornamen, tussen, achternaam = split_naam(volledige_naam)
        if not voornamen:
            return achternaam
        return achternaam + ", " + " ".join(part for part in (voornamen, tussen) if part)


    def titel_nl(s: str) -> str:
        out = []
        first = True
        for part in re.split(r"([ -])", s):
            if part in (" ", "-", ""):
                out.append(part)
                continue
            low = part.lower()
            if not first and low in TUSSENVOEGSELS:
                out.append(low)
            elif low.startswith("ij"):
                out.append("IJ" + low[2:])
            else:
                out.append(low[:1].upper() + low[1:])
            first = False
        return "".join(out)


    def normaliseer_postcode(tekst: str) -> str:
        m = _POSTCODE.fullmatch(tekst.strip(" \t"))
        if not m or m.group(2).upper() in ("SA", "SD", "SS"):
            raise ValueError("ongeldige postcode: %r" % (tekst,))
        return m.group(1) + " " + m.group(2).upper()


    def bsn_geldig(bsn: str) -> bool:
        if not bsn.isascii() or not bsn.isdigit() or len(bsn) not in (8, 9):
            return False
        bsn = bsn.zfill(9)
        total = sum(int(c) * w for c, w in zip(bsn, _WEIGHTS))
        return total != 0 and total % 11 == 0
''')

VISIBLE = dd('''
    import unittest

    from nlnamen import bsn_geldig, normaliseer_postcode, split_naam


    class Basis(unittest.TestCase):
        def test_split(self):
            self.assertEqual(split_naam("Jan Jansen"), ("Jan", "", "Jansen"))

        def test_postcode(self):
            self.assertEqual(normaliseer_postcode("1234ab"), "1234 AB")

        def test_bsn(self):
            self.assertTrue(bsn_geldig("111222333"))


    if __name__ == "__main__":
        unittest.main()
''')

HIDDEN = dd('''
    import unittest

    from nlnamen import (TUSSENVOEGSELS, achternaam_eerst, bsn_geldig, normaliseer_postcode, sorteer_sleutel, split_naam,
                         titel_nl)


    class Split(unittest.TestCase):
        def test_zonder_tussenvoegsel(self):
            self.assertEqual(split_naam("Jan Jansen"), ("Jan", "", "Jansen"))
            self.assertEqual(split_naam("Anna Maria Jansen"), ("Anna Maria", "", "Jansen"))

        def test_met_tussenvoegsel(self):
            self.assertEqual(split_naam("Jan van der Berg"), ("Jan", "van der", "Berg"))
            self.assertEqual(split_naam("Piet de Vries"), ("Piet", "de", "Vries"))
            self.assertEqual(split_naam("Anna Maria van den Heuvel"), ("Anna Maria", "van den", "Heuvel"))
            self.assertEqual(split_naam("Marie ter Horst"), ("Marie", "ter", "Horst"))
            self.assertEqual(split_naam("Henk van Dijk"), ("Henk", "van", "Dijk"))
            self.assertEqual(split_naam("Jan 't Hart"), ("Jan", "'t", "Hart"))
            self.assertEqual(split_naam("Pieter in 't Veld"), ("Pieter", "in 't", "Veld"))
            self.assertEqual(split_naam("Els op den Kamp"), ("Els", "op den", "Kamp"))

        def test_alle_tussenvoegsels_herkend(self):
            for tv in sorted(TUSSENVOEGSELS):
                self.assertEqual(split_naam("Jan %s Berg" % tv), ("Jan", tv, "Berg"), tv)

        def test_hoofdletters_blijven_zoals_getypt(self):
            self.assertEqual(split_naam("Jan Van Der Berg"), ("Jan", "Van Der", "Berg"))
            self.assertEqual(split_naam("JAN VAN BERG"), ("JAN", "VAN", "BERG"))

        def test_witruimte(self):
            self.assertEqual(split_naam(" Jan  van   Berg "), ("Jan", "van", "Berg"))
            self.assertEqual(split_naam("Jan\\tJansen\\n"), ("Jan", "", "Jansen"))

        def test_een_woord(self):
            self.assertEqual(split_naam("Jansen"), ("", "", "Jansen"))
            self.assertEqual(split_naam("De"), ("", "", "De"))

        def test_eerste_woord_is_nooit_tussenvoegsel(self):
            self.assertEqual(split_naam("De Jong"), ("De", "", "Jong"))
            self.assertEqual(split_naam("Van Gogh"), ("Van", "", "Gogh"))
            self.assertEqual(split_naam("Dick de Jong"), ("Dick", "de", "Jong"))

        def test_alleen_tussenvoegsels_erna(self):
            for naam in ("Jan van", "Jan van der", "Jan de het"):
                with self.assertRaises(ValueError, msg=naam):
                    split_naam(naam)

        def test_leeg(self):
            for naam in ("", "   ", "\\t\\n"):
                with self.assertRaises(ValueError, msg=repr(naam)):
                    split_naam(naam)

        def test_tussenvoegsel_in_het_midden_van_voornamen(self):
            self.assertEqual(split_naam("Jan de Pieter van Berg"), ("Jan", "de", "Pieter van Berg"))
            self.assertEqual(split_naam("Jan Pieter van Berg"), ("Jan Pieter", "van", "Berg"))


    class Sorteren(unittest.TestCase):
        def test_sleutel(self):
            self.assertEqual(sorteer_sleutel("Jan van der Berg"), ("berg", "jan"))
            self.assertEqual(sorteer_sleutel("Piet de Vries"), ("vries", "piet"))
            self.assertEqual(sorteer_sleutel("Jansen"), ("jansen", ""))
            self.assertEqual(sorteer_sleutel("Anna Maria Jansen"), ("jansen", "anna maria"))

        def test_ij_als_y(self):
            self.assertEqual(sorteer_sleutel("Henk van Dijk"), ("dyk", "henk"))
            self.assertEqual(sorteer_sleutel("Ijsbrand Smit"), ("smit", "ysbrand"))
            self.assertEqual(sorteer_sleutel("Anna IJsselstein"), ("ysselstein", "anna"))

        def test_volgorde(self):
            namen = ["Jan van der Berg", "Piet Bakker", "Kees de Bruin", "Els Zwart", "Henk van Dijk", "Anna IJsselstein",
                     "Tom Dijkstra", "Sara van Dam"]
            self.assertEqual(sorted(namen, key=sorteer_sleutel),
                             ["Piet Bakker", "Jan van der Berg", "Kees de Bruin", "Sara van Dam", "Henk van Dijk", "Tom Dijkstra",
                              "Anna IJsselstein", "Els Zwart"])

        def test_zelfde_achternaam_dan_voornamen(self):
            namen = ["Piet de Vries", "Anna van Vries", "Karel Vries"]
            self.assertEqual(sorted(namen, key=sorteer_sleutel), ["Anna van Vries", "Karel Vries", "Piet de Vries"])

        def test_hoofdletters_tellen_niet(self):
            self.assertEqual(sorteer_sleutel("JAN VAN BERG"), sorteer_sleutel("jan van berg"))

        def test_fouten(self):
            with self.assertRaises(ValueError):
                sorteer_sleutel("Jan van")
            with self.assertRaises(ValueError):
                sorteer_sleutel("")


    class AchternaamEerst(unittest.TestCase):
        def test_voorbeelden(self):
            self.assertEqual(achternaam_eerst("Jan van der Berg"), "Berg, Jan van der")
            self.assertEqual(achternaam_eerst("Jan Jansen"), "Jansen, Jan")
            self.assertEqual(achternaam_eerst("Anna Maria van den Heuvel"), "Heuvel, Anna Maria van den")
            self.assertEqual(achternaam_eerst("Jan 't Hart"), "Hart, Jan 't")
            self.assertEqual(achternaam_eerst("Pieter in 't Veld"), "Veld, Pieter in 't")

        def test_een_woord(self):
            self.assertEqual(achternaam_eerst("Jansen"), "Jansen")
            self.assertEqual(achternaam_eerst("De"), "De")

        def test_hoofdletters_zoals_getypt(self):
            self.assertEqual(achternaam_eerst("Jan Van Der Berg"), "Berg, Jan Van Der")

        def test_witruimte(self):
            self.assertEqual(achternaam_eerst("  Jan   de   Vries "), "Vries, Jan de")

        def test_fouten(self):
            with self.assertRaises(ValueError):
                achternaam_eerst("Jan van")


    class Titel(unittest.TestCase):
        def test_namen(self):
            self.assertEqual(titel_nl("jan van der berg"), "Jan van der Berg")
            self.assertEqual(titel_nl("anne-marie van den berg"), "Anne-Marie van den Berg")
            self.assertEqual(titel_nl("maarten van rossum"), "Maarten van Rossum")
            self.assertEqual(titel_nl("jan op de beek"), "Jan op de Beek")
            self.assertEqual(titel_nl("willem-alexander"), "Willem-Alexander")

        def test_eerste_deel_blijft_hoofdletter(self):
            self.assertEqual(titel_nl("de jong"), "De Jong")
            self.assertEqual(titel_nl("DE JONG"), "De Jong")
            self.assertEqual(titel_nl("van gogh"), "Van Gogh")
            self.assertEqual(titel_nl("'t hart"), "'t Hart")
            self.assertEqual(titel_nl("jan 't hart"), "Jan 't Hart")

        def test_hoofdletterstand_van_de_invoer_maakt_niet_uit(self):
            self.assertEqual(titel_nl("JAN VAN DER BERG"), "Jan van der Berg")
            self.assertEqual(titel_nl("Jan Van Der Berg"), "Jan van der Berg")
            self.assertEqual(titel_nl("jAn VaN bErG"), "Jan van Berg")

        def test_ij(self):
            self.assertEqual(titel_nl("ijsje"), "IJsje")
            self.assertEqual(titel_nl("IJSSELMEER"), "IJsselmeer")
            self.assertEqual(titel_nl("ij"), "IJ")
            self.assertEqual(titel_nl("iJ"), "IJ")
            self.assertEqual(titel_nl("koninkrijk der nederlanden"), "Koninkrijk der Nederlanden")
            self.assertEqual(titel_nl("jan ijsselstein"), "Jan IJsselstein")
            self.assertEqual(titel_nl("anna-ijsbrand"), "Anna-IJsbrand")
            self.assertEqual(titel_nl("rijn"), "Rijn")

        def test_scheidingstekens_blijven(self):
            self.assertEqual(titel_nl("  jan   van "), "  Jan   van ")
            self.assertEqual(titel_nl("a--b"), "A--B")
            self.assertEqual(titel_nl(""), "")
            self.assertEqual(titel_nl("-jan"), "-Jan")

        def test_tussenvoegsel_na_streepje(self):
            self.assertEqual(titel_nl("jansen-van der berg"), "Jansen-van der Berg")
            self.assertEqual(titel_nl("van-der"), "Van-der")


    class Postcode(unittest.TestCase):
        def test_geldig(self):
            for tekst, verwacht in (("1234 AB", "1234 AB"), ("1234AB", "1234 AB"), ("1234 ab", "1234 AB"), ("1234ab", "1234 AB"),
                                    ("  1234 ab  ", "1234 AB"), ("\\t1234AB", "1234 AB"), ("1000 AA", "1000 AA"),
                                    ("9999 ZZ", "9999 ZZ"), ("1234 SB", "1234 SB"), ("1234 Ab", "1234 AB")):
                self.assertEqual(normaliseer_postcode(tekst), verwacht, tekst)

        def test_eerste_cijfer(self):
            for tekst in ("0123 AB", "0000 AA"):
                with self.assertRaises(ValueError, msg=tekst):
                    normaliseer_postcode(tekst)

        def test_verboden_lettercombinaties(self):
            for tekst in ("1234 SA", "1234 sd", "1234 SS", "1234SA", "1234 sS", "1234 Sd"):
                with self.assertRaises(ValueError, msg=tekst):
                    normaliseer_postcode(tekst)
            self.assertEqual(normaliseer_postcode("1234 AS"), "1234 AS")
            self.assertEqual(normaliseer_postcode("1234 DS"), "1234 DS")

        def test_vorm(self):
            for tekst in ("", "1234", "123 AB", "12345 AB", "1234 A", "1234 ABC", "1234-AB", "1234  AB", "1234 A B", "AB 1234",
                          "1234 A1", "1234 12", "1234 ÀB", "1234 İB", "１２３４ AB"):
                with self.assertRaises(ValueError, msg=repr(tekst)):
                    normaliseer_postcode(tekst)


    class Bsn(unittest.TestCase):
        def test_geldig(self):
            for bsn in ("111222333", "123456782", "10000021", "010000021", "10000033"):
                self.assertTrue(bsn_geldig(bsn), bsn)

        def test_acht_cijfers_krijgen_een_nul(self):
            self.assertTrue(bsn_geldig("10000021"))
            self.assertTrue(bsn_geldig("010000021"))
            self.assertEqual(bsn_geldig("10000021"), bsn_geldig("0" + "10000021"))

        def test_ongeldige_som(self):
            for bsn in ("123456789", "123456783", "111222334", "111222332", "11122233"):
                self.assertFalse(bsn_geldig(bsn), bsn)

        def test_nul_is_ongeldig(self):
            for bsn in ("000000000", "00000000"):
                self.assertFalse(bsn_geldig(bsn), bsn)

        def test_lengte_en_tekens(self):
            for bsn in ("", "1234567", "1234567890", "12345678a", "１２３４５６７８２", "123 456 782", "123-456-782", "-12345678",
                        "123456782 ", " 123456782"):
                self.assertFalse(bsn_geldig(bsn), repr(bsn))

        def test_gewichten(self):
            # het laatste cijfer telt met -1: 111222333 -> 66 is deelbaar door 11; verander het laatste cijfer met 1 en het klopt niet
            for laatste in "0124567890":
                if laatste != "3":
                    self.assertFalse(bsn_geldig("11122233" + laatste), laatste)


    if __name__ == "__main__":
        unittest.main()
''')

LIB = Lib(
    name="nlnamen", lang="python", title="`nlnamen`",
    blurb="Het ledenbestand van een sportvereniging gebruikt deze functies om namen te sorteren en postcodes en BSN's te controleren.",
    files={"nlnamen/__init__.py": "from .core import *  # noqa: F401,F403\n", "nlnamen/core.py": SRC,
           "README.md": README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basis.py": VISIBLE},
    hidden_tests={"tests/test_volledig.py": HIDDEN},
    mutate=["nlnamen/core.py"], difficulty=3, tags=["i18n", "names", "validation", "text"],
    probes=[
        'split_naam("Jan van der Berg")',
        'split_naam("Pieter in \'t Veld")',
        'split_naam("De Jong")',
        'split_naam("Jan Pieter van Berg")',
        'sorteer_sleutel("Henk van Dijk")',
        'sorteer_sleutel("Piet de Vries")',
        'achternaam_eerst("Anna Maria van den Heuvel")',
        'titel_nl("jan van der berg")',
        'titel_nl("IJSSELMEER")',
        'titel_nl("DE JONG")',
        'titel_nl("anne-marie van den berg")',
        'normaliseer_postcode("  1234ab ")',
        'normaliseer_postcode("1234 SD")',
        'bsn_geldig("10000021")',
        'bsn_geldig("000000000")',
    ],
    probe_import="from nlnamen import *",
)

register_native(LIB, "nl", "fix-nlnamen", n=9,
                summary="native: injected bugs in a Dutch name/postcode/BSN library, reports in Dutch")
