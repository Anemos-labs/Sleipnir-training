"""Native bug-fix family in German: public holidays and working days per Bundesland (python)."""
from fx import Lib, dd

from ._native import register_native

README = dd('''
    # feiertage

    Kleine Bibliothek für die Personalplanung eines Handwerksbetriebs: gesetzliche Feiertage einiger Bundesländer
    und Rechnen mit Arbeitstagen. Alle Daten sind `datetime.date`.

    Unterstützte Länderkürzel: `BW`, `BY`, `BE`, `HE`, `NW`, `SN`, `NI`, `HH`. Jedes andere Kürzel ist ein
    `ValueError` (das gilt für alle Funktionen, die ein Land bekommen).

    ## `ostersonntag(jahr) -> date`
    Ostersonntag nach dem gregorianischen Kalender. Jahre vor 1583 sind ein `ValueError`.

    ## `feiertage(jahr, land) -> dict`
    Abbildung `date -> Name` aller gesetzlichen Feiertage des Landes im Jahr. Bundesweit (alle Länder):

    | Feiertag | Datum |
    |---|---|
    | Neujahr | 1. Januar |
    | Karfreitag | 2 Tage vor Ostersonntag |
    | Ostermontag | 1 Tag nach Ostersonntag |
    | Tag der Arbeit | 1. Mai |
    | Christi Himmelfahrt | 39 Tage nach Ostersonntag |
    | Pfingstmontag | 50 Tage nach Ostersonntag |
    | Tag der Deutschen Einheit | 3. Oktober |
    | 1. Weihnachtstag | 25. Dezember |
    | 2. Weihnachtstag | 26. Dezember |

    Nur in einzelnen Ländern:

    | Feiertag | Datum | Länder |
    |---|---|---|
    | Heilige Drei Könige | 6. Januar | BW, BY |
    | Internationaler Frauentag | 8. März | BE, aber erst ab 2019 |
    | Fronleichnam | 60 Tage nach Ostersonntag | BW, BY, HE, NW |
    | Reformationstag | 31. Oktober | SN, NI, HH |
    | Allerheiligen | 1. November | BW, BY, NW |
    | Buß- und Bettag | der Mittwoch vor dem 23. November (der 16. bis 22. November) | SN |

    Die Namen sind genau die in den Tabellen.

    ## `ist_arbeitstag(tag, land) -> bool`
    `True`, wenn `tag` von Montag bis Freitag liegt und kein Feiertag des Landes ist. Samstage und Sonntage sind
    keine Arbeitstage.

    ## `naechster_arbeitstag(tag, land) -> date`
    Der erste Arbeitstag am oder nach `tag` (ist `tag` selbst ein Arbeitstag, kommt `tag` zurück).

    ## `arbeitstage_zwischen(von, bis, land) -> int`
    Anzahl der Arbeitstage im halboffenen Bereich `[von, bis)`: `von` zählt mit, `bis` nicht. Ist `bis` vor `von`,
    gibt es einen `ValueError`; gleiche Daten ergeben `0`.

    ## `addiere_arbeitstage(start, n, land) -> date`
    Das Datum, das man erreicht, wenn man ab `start` genau `n` Arbeitstage weiterzählt; `start` selbst zählt nie
    mit, auch wenn er ein Arbeitstag ist. Mit `n == 0` kommt `start` unverändert zurück (auch an einem Feiertag
    oder Wochenende). Das Ergebnis ist für `n >= 1` immer selbst ein Arbeitstag. Ein negatives `n` ist ein
    `ValueError`.
''')

SRC = dd('''
    from datetime import date, timedelta

    BUNDESWEIT = ("BW", "BY", "BE", "HE", "NW", "SN", "NI", "HH")
    LAENDER = frozenset(BUNDESWEIT)

    _DREI_KOENIGE = {"BW", "BY"}
    _FRONLEICHNAM = {"BW", "BY", "HE", "NW"}
    _REFORMATION = {"SN", "NI", "HH"}
    _ALLERHEILIGEN = {"BW", "BY", "NW"}


    def _pruefe_land(land: str) -> None:
        if land not in LAENDER:
            raise ValueError("unbekanntes Land: %r" % (land,))


    def ostersonntag(jahr: int) -> date:
        if jahr < 1583:
            raise ValueError("Jahr vor 1583")
        a = jahr % 19
        b = jahr // 100
        c = jahr % 100
        d = b // 4
        e = b % 4
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i = c // 4
        k = c % 4
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        monat = (h + l - 7 * m + 114) // 31
        tag = (h + l - 7 * m + 114) % 31 + 1
        return date(jahr, monat, tag)


    def feiertage(jahr: int, land: str) -> dict:
        _pruefe_land(land)
        ostern = ostersonntag(jahr)
        tage = {
            date(jahr, 1, 1): "Neujahr",
            ostern - timedelta(days=2): "Karfreitag",
            ostern + timedelta(days=1): "Ostermontag",
            date(jahr, 5, 1): "Tag der Arbeit",
            ostern + timedelta(days=39): "Christi Himmelfahrt",
            ostern + timedelta(days=50): "Pfingstmontag",
            date(jahr, 10, 3): "Tag der Deutschen Einheit",
            date(jahr, 12, 25): "1. Weihnachtstag",
            date(jahr, 12, 26): "2. Weihnachtstag",
        }
        if land in _DREI_KOENIGE:
            tage[date(jahr, 1, 6)] = "Heilige Drei Könige"
        if land == "BE" and jahr >= 2019:
            tage[date(jahr, 3, 8)] = "Internationaler Frauentag"
        if land in _FRONLEICHNAM:
            tage[ostern + timedelta(days=60)] = "Fronleichnam"
        if land in _REFORMATION:
            tage[date(jahr, 10, 31)] = "Reformationstag"
        if land in _ALLERHEILIGEN:
            tage[date(jahr, 11, 1)] = "Allerheiligen"
        if land == "SN":
            bussbettag = date(jahr, 11, 22)
            while bussbettag.weekday() != 2:
                bussbettag -= timedelta(days=1)
            tage[bussbettag] = "Buß- und Bettag"
        return tage


    def ist_arbeitstag(tag: date, land: str) -> bool:
        _pruefe_land(land)
        if tag.weekday() >= 5:
            return False
        return tag not in feiertage(tag.year, land)


    def naechster_arbeitstag(tag: date, land: str) -> date:
        while not ist_arbeitstag(tag, land):
            tag += timedelta(days=1)
        return tag


    def arbeitstage_zwischen(von: date, bis: date, land: str) -> int:
        _pruefe_land(land)
        if bis < von:
            raise ValueError("bis liegt vor von")
        anzahl = 0
        tag = von
        while tag < bis:
            if ist_arbeitstag(tag, land):
                anzahl += 1
            tag += timedelta(days=1)
        return anzahl


    def addiere_arbeitstage(start: date, n: int, land: str) -> date:
        _pruefe_land(land)
        if n < 0:
            raise ValueError("n ist negativ")
        tag = start
        while n > 0:
            tag += timedelta(days=1)
            if ist_arbeitstag(tag, land):
                n -= 1
        return tag
''')

VISIBLE = dd('''
    import unittest
    from datetime import date

    from feiertage import arbeitstage_zwischen, feiertage, ostersonntag


    class Grundlagen(unittest.TestCase):
        def test_ostern_2025(self):
            self.assertEqual(ostersonntag(2025), date(2025, 4, 20))

        def test_neujahr(self):
            self.assertIn(date(2025, 1, 1), feiertage(2025, "BY"))

        def test_woche(self):
            self.assertEqual(arbeitstage_zwischen(date(2025, 3, 3), date(2025, 3, 10), "NW"), 5)


    if __name__ == "__main__":
        unittest.main()
''')

HIDDEN = dd('''
    import unittest
    from datetime import date

    from feiertage import (addiere_arbeitstage, arbeitstage_zwischen, feiertage, ist_arbeitstag, naechster_arbeitstag,
                           ostersonntag)

    D = date
    LAENDER = ["BW", "BY", "BE", "HE", "NW", "SN", "NI", "HH"]


    class Ostern(unittest.TestCase):
        def test_bekannte_daten(self):
            erwartet = {
                1583: D(1583, 4, 10), 1818: D(1818, 3, 22), 1900: D(1900, 4, 15), 1954: D(1954, 4, 18),
                2000: D(2000, 4, 23), 2008: D(2008, 3, 23), 2019: D(2019, 4, 21), 2024: D(2024, 3, 31),
                2025: D(2025, 4, 20), 2026: D(2026, 4, 5), 2027: D(2027, 3, 28), 2038: D(2038, 4, 25),
                2285: D(2285, 3, 22),
            }
            for jahr, tag in erwartet.items():
                self.assertEqual(ostersonntag(jahr), tag, jahr)

        def test_immer_sonntag(self):
            for jahr in range(1583, 2200, 7):
                self.assertEqual(ostersonntag(jahr).weekday(), 6, jahr)

        def test_zu_alt(self):
            with self.assertRaises(ValueError):
                ostersonntag(1582)
            with self.assertRaises(ValueError):
                ostersonntag(0)


    class Feiertage(unittest.TestCase):
        def test_bundesweit_2024(self):
            f = feiertage(2024, "NI")
            self.assertEqual(f[D(2024, 1, 1)], "Neujahr")
            self.assertEqual(f[D(2024, 3, 29)], "Karfreitag")
            self.assertEqual(f[D(2024, 4, 1)], "Ostermontag")
            self.assertEqual(f[D(2024, 5, 1)], "Tag der Arbeit")
            self.assertEqual(f[D(2024, 5, 9)], "Christi Himmelfahrt")
            self.assertEqual(f[D(2024, 5, 20)], "Pfingstmontag")
            self.assertEqual(f[D(2024, 10, 3)], "Tag der Deutschen Einheit")
            self.assertEqual(f[D(2024, 12, 25)], "1. Weihnachtstag")
            self.assertEqual(f[D(2024, 12, 26)], "2. Weihnachtstag")

        def test_anzahl_je_land_2024(self):
            erwartet = {"BW": 12, "BY": 12, "BE": 10, "HE": 10, "NW": 11, "SN": 11, "NI": 10, "HH": 10}
            for land, n in erwartet.items():
                self.assertEqual(len(feiertage(2024, land)), n, land)

        def test_mindestens_bundesweite(self):
            for land in LAENDER:
                self.assertGreaterEqual(len(feiertage(2023, land)), 9)

        def test_drei_koenige(self):
            for land in LAENDER:
                self.assertEqual(D(2025, 1, 6) in feiertage(2025, land), land in ("BW", "BY"), land)
            self.assertEqual(feiertage(2025, "BY")[D(2025, 1, 6)], "Heilige Drei Könige")

        def test_frauentag_nur_berlin_ab_2019(self):
            self.assertEqual(feiertage(2019, "BE")[D(2019, 3, 8)], "Internationaler Frauentag")
            self.assertNotIn(D(2018, 3, 8), feiertage(2018, "BE"))
            for land in LAENDER:
                if land != "BE":
                    self.assertNotIn(D(2025, 3, 8), feiertage(2025, land), land)

        def test_fronleichnam(self):
            for land in LAENDER:
                self.assertEqual(D(2025, 6, 19) in feiertage(2025, land), land in ("BW", "BY", "HE", "NW"), land)
            self.assertEqual(feiertage(2024, "HE")[D(2024, 5, 30)], "Fronleichnam")

        def test_reformationstag(self):
            for land in LAENDER:
                self.assertEqual(D(2025, 10, 31) in feiertage(2025, land), land in ("SN", "NI", "HH"), land)
            self.assertEqual(feiertage(2025, "SN")[D(2025, 10, 31)], "Reformationstag")

        def test_allerheiligen(self):
            for land in LAENDER:
                self.assertEqual(D(2025, 11, 1) in feiertage(2025, land), land in ("BW", "BY", "NW"), land)
            self.assertEqual(feiertage(2025, "NW")[D(2025, 11, 1)], "Allerheiligen")

        def test_buss_und_bettag(self):
            self.assertEqual(feiertage(2024, "SN")[D(2024, 11, 20)], "Buß- und Bettag")
            self.assertEqual(feiertage(2025, "SN")[D(2025, 11, 19)], "Buß- und Bettag")
            self.assertEqual(feiertage(2026, "SN")[D(2026, 11, 18)], "Buß- und Bettag")
            # der 22. November selbst, wenn er ein Mittwoch ist
            self.assertEqual(feiertage(2023, "SN")[D(2023, 11, 22)], "Buß- und Bettag")
            # der 16. November, wenn der 23. ein Donnerstag ist
            self.assertEqual(feiertage(2022, "SN")[D(2022, 11, 16)], "Buß- und Bettag")
            for land in LAENDER:
                if land != "SN":
                    self.assertNotIn(D(2024, 11, 20), feiertage(2024, land), land)

        def test_buss_und_bettag_immer_mittwoch_vor_dem_23(self):
            for jahr in range(2000, 2060):
                tag = [d for d, n in feiertage(jahr, "SN").items() if n == "Buß- und Bettag"][0]
                self.assertEqual(tag.weekday(), 2)
                self.assertTrue(D(jahr, 11, 16) <= tag <= D(jahr, 11, 22), jahr)

        def test_ostern_abhaengige_tage_2026(self):
            f = feiertage(2026, "BW")
            self.assertEqual(f[D(2026, 4, 3)], "Karfreitag")
            self.assertEqual(f[D(2026, 4, 6)], "Ostermontag")
            self.assertEqual(f[D(2026, 5, 14)], "Christi Himmelfahrt")
            self.assertEqual(f[D(2026, 5, 25)], "Pfingstmontag")
            self.assertEqual(f[D(2026, 6, 4)], "Fronleichnam")

        def test_unbekanntes_land(self):
            for land in ("XX", "by", "", "Bayern"):
                with self.assertRaises(ValueError):
                    feiertage(2025, land)
                with self.assertRaises(ValueError):
                    ist_arbeitstag(D(2025, 5, 5), land)
                with self.assertRaises(ValueError):
                    naechster_arbeitstag(D(2025, 5, 5), land)
                with self.assertRaises(ValueError):
                    arbeitstage_zwischen(D(2025, 5, 5), D(2025, 5, 6), land)
                with self.assertRaises(ValueError):
                    addiere_arbeitstage(D(2025, 5, 5), 1, land)


    class Arbeitstag(unittest.TestCase):
        def test_wochentage(self):
            self.assertTrue(ist_arbeitstag(D(2025, 3, 3), "NW"))   # Montag
            self.assertTrue(ist_arbeitstag(D(2025, 3, 7), "NW"))   # Freitag
            self.assertFalse(ist_arbeitstag(D(2025, 3, 8), "NW"))  # Samstag
            self.assertFalse(ist_arbeitstag(D(2025, 3, 9), "NW"))  # Sonntag

        def test_feiertag_unter_der_woche(self):
            self.assertFalse(ist_arbeitstag(D(2025, 5, 1), "HH"))   # Donnerstag
            self.assertFalse(ist_arbeitstag(D(2025, 12, 25), "BY"))
            self.assertFalse(ist_arbeitstag(D(2025, 4, 18), "SN"))  # Karfreitag
            self.assertFalse(ist_arbeitstag(D(2025, 4, 21), "NI"))  # Ostermontag

        def test_landesspezifisch(self):
            self.assertFalse(ist_arbeitstag(D(2025, 6, 19), "BW"))
            self.assertTrue(ist_arbeitstag(D(2025, 6, 19), "NI"))
            self.assertFalse(ist_arbeitstag(D(2025, 11, 19), "SN"))
            self.assertTrue(ist_arbeitstag(D(2025, 11, 19), "BY"))
            self.assertFalse(ist_arbeitstag(D(2024, 3, 8), "BE"))   # Freitag, Frauentag
            self.assertTrue(ist_arbeitstag(D(2024, 3, 8), "HH"))

        def test_jahr_wird_vom_datum_genommen(self):
            self.assertFalse(ist_arbeitstag(D(2026, 1, 1), "HH"))
            self.assertFalse(ist_arbeitstag(D(2027, 1, 1), "HH"))   # Freitag
            self.assertTrue(ist_arbeitstag(D(2026, 1, 2), "HH"))


    class Naechster(unittest.TestCase):
        def test_arbeitstag_bleibt(self):
            self.assertEqual(naechster_arbeitstag(D(2025, 3, 4), "BY"), D(2025, 3, 4))

        def test_wochenende(self):
            self.assertEqual(naechster_arbeitstag(D(2025, 3, 8), "BY"), D(2025, 3, 10))
            self.assertEqual(naechster_arbeitstag(D(2025, 3, 9), "BY"), D(2025, 3, 10))

        def test_ostern(self):
            self.assertEqual(naechster_arbeitstag(D(2025, 4, 18), "BY"), D(2025, 4, 22))

        def test_jahreswechsel(self):
            self.assertEqual(naechster_arbeitstag(D(2024, 12, 25), "BY"), D(2024, 12, 27))
            self.assertEqual(naechster_arbeitstag(D(2024, 12, 28), "BY"), D(2024, 12, 30))
            self.assertEqual(naechster_arbeitstag(D(2025, 1, 1), "HH"), D(2025, 1, 2))
            self.assertEqual(naechster_arbeitstag(D(2025, 1, 1), "BY"), D(2025, 1, 2))
            self.assertEqual(naechster_arbeitstag(D(2026, 1, 1), "BY"), D(2026, 1, 2))
            self.assertEqual(naechster_arbeitstag(D(2027, 12, 31), "HH"), D(2027, 12, 31))
            self.assertEqual(naechster_arbeitstag(D(2028, 12, 31), "HH"), D(2029, 1, 2))


    class Zwischen(unittest.TestCase):
        def test_halboffen(self):
            self.assertEqual(arbeitstage_zwischen(D(2025, 3, 3), D(2025, 3, 3), "BY"), 0)
            self.assertEqual(arbeitstage_zwischen(D(2025, 3, 3), D(2025, 3, 4), "BY"), 1)
            self.assertEqual(arbeitstage_zwischen(D(2025, 3, 8), D(2025, 3, 10), "BY"), 0)
            self.assertEqual(arbeitstage_zwischen(D(2025, 3, 3), D(2025, 3, 8), "BY"), 5)
            self.assertEqual(arbeitstage_zwischen(D(2025, 3, 3), D(2025, 3, 7), "BY"), 4)

        def test_rueckwaerts(self):
            with self.assertRaises(ValueError):
                arbeitstage_zwischen(D(2025, 3, 4), D(2025, 3, 3), "BY")

        def test_weihnachtszeit(self):
            self.assertEqual(arbeitstage_zwischen(D(2024, 12, 23), D(2025, 1, 2), "BY"), 5)
            self.assertEqual(arbeitstage_zwischen(D(2024, 12, 23), D(2025, 1, 2), "HH"), 5)

        def test_ganzes_jahr(self):
            self.assertEqual(arbeitstage_zwischen(D(2024, 1, 1), D(2025, 1, 1), "BY"), 251)
            self.assertEqual(arbeitstage_zwischen(D(2025, 1, 1), D(2026, 1, 1), "NW"), 251)

        def test_landesunterschied(self):
            a = arbeitstage_zwischen(D(2025, 6, 1), D(2025, 7, 1), "BY")
            b = arbeitstage_zwischen(D(2025, 6, 1), D(2025, 7, 1), "NI")
            self.assertEqual((a, b), (19, 20))

        def test_ueber_jahre(self):
            self.assertEqual(arbeitstage_zwischen(D(2024, 12, 30), D(2025, 1, 3), "HH"), 3)


    class Addiere(unittest.TestCase):
        def test_null(self):
            self.assertEqual(addiere_arbeitstage(D(2025, 3, 8), 0, "BY"), D(2025, 3, 8))
            self.assertEqual(addiere_arbeitstage(D(2025, 12, 25), 0, "BY"), D(2025, 12, 25))
            self.assertEqual(addiere_arbeitstage(D(2025, 3, 4), 0, "BY"), D(2025, 3, 4))

        def test_start_zaehlt_nicht(self):
            self.assertEqual(addiere_arbeitstage(D(2025, 3, 3), 1, "BY"), D(2025, 3, 4))
            self.assertEqual(addiere_arbeitstage(D(2025, 3, 3), 5, "BY"), D(2025, 3, 10))
            self.assertEqual(addiere_arbeitstage(D(2025, 3, 7), 1, "BY"), D(2025, 3, 10))

        def test_start_am_wochenende(self):
            self.assertEqual(addiere_arbeitstage(D(2025, 3, 8), 1, "BY"), D(2025, 3, 10))
            self.assertEqual(addiere_arbeitstage(D(2025, 3, 9), 2, "BY"), D(2025, 3, 11))

        def test_ueber_feiertage(self):
            self.assertEqual(addiere_arbeitstage(D(2025, 4, 17), 1, "BY"), D(2025, 4, 22))
            self.assertEqual(addiere_arbeitstage(D(2024, 12, 23), 3, "BY"), D(2024, 12, 30))
            self.assertEqual(addiere_arbeitstage(D(2024, 12, 23), 5, "HH"), D(2025, 1, 2))

        def test_frist_arbeitstage(self):
            self.assertEqual(addiere_arbeitstage(D(2025, 5, 1), 30, "BW"), D(2025, 6, 16))
            self.assertEqual(addiere_arbeitstage(D(2025, 5, 1), 30, "NI"), D(2025, 6, 16))
            self.assertEqual(addiere_arbeitstage(D(2025, 5, 1), 40, "BW"), D(2025, 7, 1))
            self.assertEqual(addiere_arbeitstage(D(2025, 5, 1), 40, "NI"), D(2025, 6, 30))

        def test_ergebnis_ist_arbeitstag(self):
            for n in range(1, 40):
                for land in ("BY", "SN", "HH"):
                    erg = addiere_arbeitstage(D(2025, 12, 1), n, land)
                    self.assertTrue(ist_arbeitstag(erg, land), (n, land))

        def test_zaehlt_wie_arbeitstage_zwischen(self):
            for n in range(1, 30):
                erg = addiere_arbeitstage(D(2025, 12, 1), n, "SN")
                self.assertEqual(arbeitstage_zwischen(D(2025, 12, 2), erg, "SN"), n - 1)

        def test_negativ(self):
            with self.assertRaises(ValueError):
                addiere_arbeitstage(D(2025, 3, 3), -1, "BY")


    if __name__ == "__main__":
        unittest.main()
''')

LIB = Lib(
    name="feiertage", lang="python", title="`feiertage`",
    blurb="Die Personalplanung eines Handwerksbetriebs rechnet damit Fristen, Lieferfenster und Urlaubstage aus.",
    files={"feiertage/__init__.py": "from .kalender import *  # noqa: F401,F403\n", "feiertage/kalender.py": SRC,
           "README.md": README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_grundlagen.py": VISIBLE},
    hidden_tests={"tests/test_vollstaendig.py": HIDDEN},
    mutate=["feiertage/kalender.py"], difficulty=3, tags=["calendar", "holidays", "dates"],
    probes=[
        "ostersonntag(2026)",
        "ostersonntag(2008)",
        "feiertage(2024, 'BY')[date(2024, 5, 30)]",
        "sorted(feiertage(2024, 'BE'))[:3]",
        "len(feiertage(2024, 'SN'))",
        "date(2025, 11, 19) in feiertage(2025, 'SN')",
        "date(2018, 3, 8) in feiertage(2018, 'BE')",
        "ist_arbeitstag(date(2025, 3, 8), 'NW')",
        "ist_arbeitstag(date(2025, 6, 19), 'BW')",
        "naechster_arbeitstag(date(2025, 4, 18), 'BY')",
        "arbeitstage_zwischen(date(2024, 12, 23), date(2025, 1, 2), 'BY')",
        "arbeitstage_zwischen(date(2025, 3, 3), date(2025, 3, 8), 'BY')",
        "addiere_arbeitstage(date(2025, 3, 8), 1, 'BY')",
        "addiere_arbeitstage(date(2025, 4, 17), 1, 'BY')",
    ],
    probe_import="from datetime import date\nfrom feiertage import *",
)

register_native(LIB, "de", "fix-feiertage", n=9,
                summary="native: injected bugs in a German public-holiday/working-day library, reports in German")
