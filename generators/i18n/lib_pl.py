"""Native bug-fix family in Polish: PESEL, NIP and postal code helpers (python)."""
from fx import Lib, dd

from ._native import register_native

README = dd('''
    # polskie_numery

    Walidacja i rozbiór numerów używanych w polskich formularzach: PESEL, NIP, kod pocztowy. Wszystkie funkcje
    przyjmują tekst (`str`).

    ## PESEL

    Jedenaście cyfr: `RRMMDDPPPPK`. `RR` to dwie ostatnie cyfry roku, `MM` to miesiąc z przesunięciem określającym
    stulecie, `DD` to dzień, `PPPP` to numer porządkowy, `K` to cyfra kontrolna. Dziesiąta cyfra (ostatnia z `PPPP`)
    jest nieparzysta dla mężczyzn i parzysta dla kobiet.

    | zakres w polu `MM` | stulecie | miesiąc |
    |---|---|---|
    | 81–92 | 1800–1899 | `MM - 80` |
    | 01–12 | 1900–1999 | `MM` |
    | 21–32 | 2000–2099 | `MM - 20` |
    | 41–52 | 2100–2199 | `MM - 40` |
    | 61–72 | 2200–2299 | `MM - 60` |

    Cyfra kontrolna: pierwsze dziesięć cyfr mnoży się przez wagi `1 3 7 9 1 3 7 9 1 3`, sumuje iloczyny, a
    `K = (10 - (suma mod 10)) mod 10`.

    ### `pesel_poprawny(pesel) -> bool`
    `True` tylko wtedy, gdy tekst ma dokładnie 11 znaków, wszystkie są cyframi ASCII `0`–`9`, pole `MM` mieści się w
    tabeli, data (z uwzględnieniem lat przestępnych według kalendarza gregoriańskiego; rok 1900 i 2100 nie są
    przestępne, 2000 jest) istnieje, a cyfra kontrolna się zgadza. Spacje i myślniki nie są dozwolone.

    ### `pesel_data_urodzenia(pesel) -> date`
    Data urodzenia zapisana w numerze. Dla niepoprawnego numeru `ValueError`.

    ### `pesel_plec(pesel) -> str`
    `"M"` lub `"K"`. Dla niepoprawnego numeru `ValueError`.

    ## NIP

    ### `nip_poprawny(nip) -> bool`
    Dziesięć cyfr; dozwolone są myślniki i spacje w dowolnych miejscach (`"123-456-32-18"`, `"123 456 32 18"`), które
    najpierw się usuwa. Po usunięciu muszą zostać dokładnie 10 cyfr ASCII. Suma kontrolna: pierwsze dziewięć cyfr
    mnoży się przez wagi `6 5 7 2 3 4 5 6 7`, sumuje i bierze resztę z dzielenia przez 11; reszta musi być równa
    dziesiątej cyfrze. Jeśli reszta wynosi 10, numer jest niepoprawny.

    ## Kod pocztowy

    ### `kod_pocztowy(tekst) -> str`
    Sprowadza kod do postaci `NN-NNN`. Najpierw usuwa się wszystkie białe znaki (spacje, tabulatory), potem tekst musi
    mieć postać pięciu cyfr z jednym opcjonalnym myślnikiem po drugiej cyfrze (`"00950"`, `"00-950"`,
    `" 00 950 "`). Wszystko inne to `ValueError`.

    ## Wiek

    ### `wiek(data_urodzenia, na_dzien) -> int`
    Liczba pełnych lat. Urodzony 29 lutego kończy kolejny rok życia w roku nieprzestępnym 1 marca. Jeśli
    `na_dzien` jest przed `data_urodzenia`, `ValueError`.
''')

SRC = dd('''
    import re
    from datetime import date

    _WAGI_PESEL = (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)
    _WAGI_NIP = (6, 5, 7, 2, 3, 4, 5, 6, 7)
    _STULECIA = {0: 1900, 1: 2000, 2: 2100, 3: 2200, 4: 1800}
    _KOD = re.compile(r"[0-9]{2}-?[0-9]{3}")


    def _cyfry(tekst: str) -> bool:
        return all(c in "0123456789" for c in tekst)


    def _rozbierz_pesel(pesel: str):
        if len(pesel) != 11 or not _cyfry(pesel):
            return None
        suma = sum(int(c) * w for c, w in zip(pesel, _WAGI_PESEL))
        if (10 - suma % 10) % 10 != int(pesel[10]):
            return None
        mm = int(pesel[2:4])
        if mm // 20 not in _STULECIA or not 1 <= mm % 20 <= 12:
            return None
        rok = _STULECIA[mm // 20] + int(pesel[0:2])
        try:
            return date(rok, mm % 20, int(pesel[4:6]))
        except ValueError:
            return None


    def pesel_poprawny(pesel: str) -> bool:
        return _rozbierz_pesel(pesel) is not None


    def pesel_data_urodzenia(pesel: str) -> date:
        data = _rozbierz_pesel(pesel)
        if data is None:
            raise ValueError("niepoprawny PESEL")
        return data


    def pesel_plec(pesel: str) -> str:
        if _rozbierz_pesel(pesel) is None:
            raise ValueError("niepoprawny PESEL")
        return "M" if int(pesel[9]) % 2 == 1 else "K"


    def nip_poprawny(nip: str) -> bool:
        cyfry = "".join(c for c in nip if c not in "- ")
        if len(cyfry) != 10 or not _cyfry(cyfry):
            return False
        reszta = sum(int(c) * w for c, w in zip(cyfry, _WAGI_NIP)) % 11
        return reszta != 10 and reszta == int(cyfry[9])


    def kod_pocztowy(tekst: str) -> str:
        bez = "".join(tekst.split())
        if not _KOD.fullmatch(bez):
            raise ValueError("niepoprawny kod pocztowy: %r" % (tekst,))
        cyfry = bez.replace("-", "")
        return cyfry[:2] + "-" + cyfry[2:]


    def wiek(data_urodzenia: date, na_dzien: date) -> int:
        if na_dzien < data_urodzenia:
            raise ValueError("data przed urodzeniem")
        lata = na_dzien.year - data_urodzenia.year
        m, d = data_urodzenia.month, data_urodzenia.day
        if m == 2 and d == 29 and not _przestepny(na_dzien.year):
            m, d = 3, 1
        if (na_dzien.month, na_dzien.day) < (m, d):
            lata -= 1
        return lata


    def _przestepny(rok: int) -> bool:
        return rok % 4 == 0 and (rok % 100 != 0 or rok % 400 == 0)
''')

VISIBLE = dd('''
    import unittest
    from datetime import date

    from polskie_numery import kod_pocztowy, nip_poprawny, pesel_data_urodzenia, pesel_poprawny


    class Podstawy(unittest.TestCase):
        def test_pesel(self):
            self.assertTrue(pesel_poprawny("44051401359"))
            self.assertEqual(pesel_data_urodzenia("44051401359"), date(1944, 5, 14))

        def test_nip(self):
            self.assertTrue(nip_poprawny("123-456-32-18"))

        def test_kod(self):
            self.assertEqual(kod_pocztowy("00950"), "00-950")


    if __name__ == "__main__":
        unittest.main()
''')

HIDDEN = dd('''
    import unittest
    from datetime import date

    from polskie_numery import (kod_pocztowy, nip_poprawny, pesel_data_urodzenia, pesel_plec, pesel_poprawny, wiek)

    D = date

    # (pesel, data, plec)
    DOBRE = [
        ("44051401359", D(1944, 5, 14), "M"),
        ("85123112346", D(1985, 12, 31), "K"),
        ("02270803624", D(2002, 7, 8), "K"),
        ("00222900177", D(2000, 2, 29), "M"),
        ("99923100526", D(1899, 12, 31), "K"),
        ("00410101001", D(2100, 1, 1), "K"),
        ("50661532196", D(2250, 6, 15), "M"),
        ("12910307719", D(1812, 11, 3), "M"),
        ("60022904506", D(1960, 2, 29), "K"),
        ("23230920083", D(2023, 3, 9), "K"),
        ("99123100959", D(1999, 12, 31), "M"),
        ("90010102070", D(1990, 1, 1), "M"),
    ]


    class Pesel(unittest.TestCase):
        def test_poprawne(self):
            for pesel, _, _ in DOBRE:
                self.assertTrue(pesel_poprawny(pesel), pesel)

        def test_daty(self):
            for pesel, data, _ in DOBRE:
                self.assertEqual(pesel_data_urodzenia(pesel), data, pesel)

        def test_plec(self):
            for pesel, _, plec in DOBRE:
                self.assertEqual(pesel_plec(pesel), plec, pesel)

        def test_zla_cyfra_kontrolna(self):
            for pesel, _, _ in DOBRE:
                k = int(pesel[10])
                for inna in (str((k + 1) % 10), str((k + 9) % 10)):
                    self.assertFalse(pesel_poprawny(pesel[:10] + inna), pesel)

        def test_zla_dlugosc(self):
            self.assertFalse(pesel_poprawny(""))
            self.assertFalse(pesel_poprawny("4405140135"))
            self.assertFalse(pesel_poprawny("440514013599"))
            self.assertFalse(pesel_poprawny("44051401359 "))

        def test_nie_cyfry(self):
            self.assertFalse(pesel_poprawny("4405140135a"))
            self.assertFalse(pesel_poprawny("44-05140135"))
            self.assertFalse(pesel_poprawny("٤٤٠٥١٤٠١٣٥٩"))  # cyfry arabsko-indyjskie
            self.assertFalse(pesel_poprawny("４４０５１４０１３５９"))  # cyfry pełnej szerokości

        def test_zly_miesiac(self):
            # miesiac 13, 00, 33, 93: cyfra kontrolna dobrana tak, by suma sie zgadzala
            for mm in ("13", "00", "33", "93", "20", "40", "99"):
                baza = "44" + mm + "140135"
                suma = sum(int(c) * w for c, w in zip(baza, (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)))
                pesel = baza + str((10 - suma % 10) % 10)
                self.assertFalse(pesel_poprawny(pesel), pesel)

        def test_zly_dzien(self):
            for dd_ in ("00", "32", "31"):
                baza = "44" + "04" + dd_ + "0135"
                if dd_ == "31":
                    baza = "4404310135"   # kwiecien ma 30 dni
                suma = sum(int(c) * w for c, w in zip(baza, (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)))
                pesel = baza + str((10 - suma % 10) % 10)
                self.assertFalse(pesel_poprawny(pesel), pesel)

        def test_29_lutego(self):
            def zbuduj(rr, mm, dd_):
                baza = "%02d%02d%02d0135" % (rr, mm, dd_)
                suma = sum(int(c) * w for c, w in zip(baza, (1, 3, 7, 9, 1, 3, 7, 9, 1, 3)))
                return baza + str((10 - suma % 10) % 10)
            self.assertTrue(pesel_poprawny(zbuduj(0, 22, 29)))    # 2000 jest przestepny
            self.assertTrue(pesel_poprawny(zbuduj(4, 2, 29)))     # 1904
            self.assertFalse(pesel_poprawny(zbuduj(0, 2, 29)))    # 1900 nie jest przestepny
            self.assertFalse(pesel_poprawny(zbuduj(0, 42, 29)))   # 2100 nie jest przestepny
            self.assertFalse(pesel_poprawny(zbuduj(1, 2, 29)))    # 1901
            self.assertFalse(pesel_poprawny(zbuduj(23, 22, 29)))  # 2023
            self.assertFalse(pesel_poprawny(zbuduj(0, 82, 29)))   # 1800 nie jest przestepny
            self.assertTrue(pesel_poprawny(zbuduj(4, 82, 29)))    # 1804

        def test_wyjatki(self):
            for zly in ("44051401350", "abc", ""):
                with self.assertRaises(ValueError):
                    pesel_data_urodzenia(zly)
                with self.assertRaises(ValueError):
                    pesel_plec(zly)

        def test_stulecia(self):
            self.assertEqual(pesel_data_urodzenia("99923100526").year, 1899)
            self.assertEqual(pesel_data_urodzenia("02270803624").year, 2002)
            self.assertEqual(pesel_data_urodzenia("00410101001").year, 2100)
            self.assertEqual(pesel_data_urodzenia("50661532196").year, 2250)
            self.assertEqual(pesel_data_urodzenia("12910307719").year, 1812)
            self.assertEqual(pesel_data_urodzenia("99123100959").year, 1999)

        def test_kontrolna_zero(self):
            # suma wazona konczy sie zerem, wiec cyfra kontrolna to 0 (a nie 10)
            self.assertTrue(pesel_poprawny("90010102070"))
            self.assertFalse(pesel_poprawny("90010102071"))
            self.assertFalse(pesel_poprawny("90010102079"))


    class Nip(unittest.TestCase):
        def test_poprawne(self):
            for nip in ("1234563218", "5260250995", "123-456-32-18", "123 456 32 18", "526-025-09-95", "5 2 6-0-2 5 0 9-9 5"):
                self.assertTrue(nip_poprawny(nip), nip)

        def test_zla_suma(self):
            self.assertFalse(nip_poprawny("1234563219"))
            self.assertFalse(nip_poprawny("1234563210"))
            self.assertFalse(nip_poprawny("5260250996"))

        def test_reszta_10_zawsze_zla(self):
            for k in range(10):
                self.assertFalse(nip_poprawny("130000000" + str(k)), k)

        def test_reszta_0_wymaga_zera(self):
            self.assertTrue(nip_poprawny("1000000070"))
            self.assertFalse(nip_poprawny("1000000071"))
            self.assertFalse(nip_poprawny("1000000079"))

        def test_dlugosc(self):
            self.assertFalse(nip_poprawny("123456321"))
            self.assertFalse(nip_poprawny("12345632180"))
            self.assertFalse(nip_poprawny(""))
            self.assertFalse(nip_poprawny("---"))

        def test_znaki(self):
            self.assertFalse(nip_poprawny("12345632a8"))
            self.assertFalse(nip_poprawny("PL1234563218"))
            self.assertFalse(nip_poprawny("123.456.32.18"))

        def test_wagi(self):
            # zmiana kazdej z pierwszych dziewieciu cyfr psuje sume (waga i 11 sa wzglednie pierwsze)
            baza = "1234563218"
            for i in range(9):
                cyfry = list(baza)
                cyfry[i] = str((int(cyfry[i]) + 1) % 10)
                self.assertFalse(nip_poprawny("".join(cyfry)), i)


    class Kod(unittest.TestCase):
        def test_postacie(self):
            self.assertEqual(kod_pocztowy("00950"), "00-950")
            self.assertEqual(kod_pocztowy("00-950"), "00-950")
            self.assertEqual(kod_pocztowy(" 00 950 "), "00-950")
            self.assertEqual(kod_pocztowy("\\t30-001\\n"), "30-001")
            self.assertEqual(kod_pocztowy("3 0 0 0 1"), "30-001")
            self.assertEqual(kod_pocztowy("30 - 001"), "30-001")
            self.assertEqual(kod_pocztowy("99999"), "99-999")
            self.assertEqual(kod_pocztowy("01-000"), "01-000")

        def test_zle(self):
            for zly in ("", "0095", "009500", "00-95", "00-9500", "0-0950", "000-50", "00--950", "ab-cde", "00 95a",
                        "-00950", "00950-", "00-950-", "٠٠-٩٥٠"):
                with self.assertRaises(ValueError, msg=repr(zly)):
                    kod_pocztowy(zly)


    class Wiek(unittest.TestCase):
        def test_zwykle(self):
            self.assertEqual(wiek(D(1990, 6, 15), D(2025, 6, 14)), 34)
            self.assertEqual(wiek(D(1990, 6, 15), D(2025, 6, 15)), 35)
            self.assertEqual(wiek(D(1990, 6, 15), D(2025, 6, 16)), 35)
            self.assertEqual(wiek(D(1990, 6, 15), D(2025, 1, 1)), 34)
            self.assertEqual(wiek(D(1990, 6, 15), D(2025, 12, 31)), 35)
            self.assertEqual(wiek(D(2000, 1, 1), D(2000, 1, 1)), 0)
            self.assertEqual(wiek(D(2000, 1, 31), D(2000, 2, 1)), 0)

        def test_29_lutego(self):
            self.assertEqual(wiek(D(2000, 2, 29), D(2025, 2, 28)), 24)
            self.assertEqual(wiek(D(2000, 2, 29), D(2025, 3, 1)), 25)
            self.assertEqual(wiek(D(2000, 2, 29), D(2024, 2, 28)), 23)
            self.assertEqual(wiek(D(2000, 2, 29), D(2024, 2, 29)), 24)
            self.assertEqual(wiek(D(2000, 2, 29), D(2024, 3, 1)), 24)
            self.assertEqual(wiek(D(2000, 2, 29), D(2023, 3, 1)), 23)
            self.assertEqual(wiek(D(2000, 2, 29), D(2023, 2, 28)), 22)

        def test_przed_urodzeniem(self):
            with self.assertRaises(ValueError):
                wiek(D(2000, 1, 2), D(2000, 1, 1))


    if __name__ == "__main__":
        unittest.main()
''')

LIB = Lib(
    name="polskie_numery", lang="python", title="`polskie_numery`",
    blurb="Formularz rejestracji przychodni używa tych funkcji do sprawdzania numeru PESEL, NIP-u i kodu pocztowego.",
    files={"polskie_numery/__init__.py": "from .numery import *  # noqa: F401,F403\n", "polskie_numery/numery.py": SRC,
           "README.md": README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_podstawy.py": VISIBLE},
    hidden_tests={"tests/test_pelny.py": HIDDEN},
    mutate=["polskie_numery/numery.py"], difficulty=3, tags=["validation", "checksum", "dates"],
    probes=[
        'pesel_poprawny("44051401359")',
        'pesel_poprawny("02270803624")',
        'pesel_poprawny("00222900177")',
        'pesel_data_urodzenia("99923100526")',
        'pesel_data_urodzenia("00410101001")',
        'pesel_plec("85123112346")',
        'pesel_plec("44051401359")',
        'nip_poprawny("5260250995")',
        'nip_poprawny("123 456 32 18")',
        'nip_poprawny("1300000000")',
        'kod_pocztowy("30 - 001")',
        'kod_pocztowy(" 00 950 ")',
        'wiek(date(2000, 2, 29), date(2025, 3, 1))',
        'wiek(date(1990, 6, 15), date(2025, 6, 14))',
    ],
    probe_import="from datetime import date\nfrom polskie_numery import *",
)

register_native(LIB, "pl", "fix-polskie-numery", n=9,
                summary="native: injected bugs in a Polish PESEL/NIP/postal-code library, reports in Polish")
