"""Native bug-fix family in Italian: codice fiscale computation and checking (python)."""
from fx import Lib, dd

from ._native import register_native

README = dd(r'''
    # codfisc

    Calcolo e controllo del codice fiscale per il gestionale di un ambulatorio. Solo libreria standard. I dati negli
    esempi e nei test sono inventati.

    Il codice fiscale ha 16 caratteri: `CCC NNN AA M GG LLLL K`, cioè 3 lettere del cognome, 3 del nome, le ultime due cifre
    dell'anno di nascita, una lettera per il mese, due cifre per il giorno (più 40 per le donne), il codice del comune (una
    lettera e tre cifre, ad esempio `A562`) e un carattere di controllo.

    ## Lettere del cognome e del nome

    Si lavora sulle lettere dell'alfabeto latino: le lettere accentate valgono la lettera di base (`è` -> `E`, `ò` -> `O`;
    scomposizione NFD e scarto dei segni), tutto in maiuscolo, e spazi, apostrofi e ogni altro carattere vengono ignorati.

    ### `codice_cognome(cognome) -> str`
    Prima le consonanti nell'ordine in cui compaiono, poi le vocali nell'ordine in cui compaiono; si prendono le prime tre. Se
    mancano lettere si completa con `X` (`Fo` -> `FOX`, `Ng` -> `NGX`). Esempi: `Rossi` -> `RSS`, `De Luca` -> `DLC`,
    `Dell'Orto` -> `DLL`, `Li` -> `LIX`.

    ### `codice_nome(nome) -> str`
    Come per il cognome, con una differenza: se il nome ha **quattro o più** consonanti, si usano la prima, la terza e la quarta
    (`Giovanni` -> `GNN`, `Gianluca` -> `GLC`). Con meno di quattro consonanti vale la regola del cognome (`Mario` -> `MRA`,
    `Anna` -> `NNA`, nome vuoto -> `XXX`).

    ## Data

    ### `codice_data(data, sesso) -> str`
    Cinque caratteri: ultime due cifre dell'anno (con lo zero iniziale), la lettera del mese, due cifre del giorno. Le lettere dei
    mesi sono, da gennaio a dicembre: `A B C D E H L M P R S T`. Per `sesso == "F"` si somma 40 al giorno (il 5 diventa `45`);
    `"M"` lascia il giorno com'è. Ogni altro valore di `sesso` è un `ValueError`. Esempi: 10/12/1985 maschio -> `85T10`, stessa
    data donna -> `85T50`, 29/02/2024 maschio -> `24B29`.

    ## Carattere di controllo

    ### `carattere_controllo(quindici) -> str`
    Calcolato sui primi 15 caratteri (maiuscoli). Ogni carattere vale un numero, e il valore dipende dalla posizione contata da 1:
    nelle posizioni **dispari** (1, 3, ..., 15) si usa questa tabella, nelle posizioni **pari** (2, 4, ..., 14) la cifra vale la cifra
    e la lettera vale la sua posizione nell'alfabeto a partire da 0 (`A` = 0, `B` = 1, ..., `Z` = 25).

    | posizione dispari | valore |
    |---|---|
    | `0` `1` `2` `3` `4` `5` `6` `7` `8` `9` | 1 0 5 7 9 13 15 17 19 21 |
    | `A` `B` `C` `D` `E` `F` `G` `H` `I` `J` | 1 0 5 7 9 13 15 17 19 21 |
    | `K` `L` `M` `N` `O` `P` `Q` `R` `S` `T` | 2 4 18 20 11 3 6 8 12 14 |
    | `U` `V` `W` `X` `Y` `Z` | 16 10 22 25 24 23 |

    La somma di tutti i valori diviso 26 dà un resto; il carattere di controllo è la lettera con quella posizione nell'alfabeto
    (resto 0 -> `A`, resto 18 -> `S`).

    ## Insieme

    ### `calcola_codice(cognome, nome, data, sesso, comune) -> str`
    Concatena `codice_cognome`, `codice_nome`, `codice_data`, `comune` e il carattere di controllo. `comune` deve essere una
    lettera maiuscola seguita da tre cifre ASCII (`"A562"`), altrimenti `ValueError`. Esempio: `calcola_codice("Rossi", "Mario",
    date(1985, 12, 10), "M", "A562")` -> `"RSSMRA85T10A562S"`.

    ### `valida_codice(cf) -> bool`
    `True` solo se, dopo aver portato `cf` in maiuscolo (senza altro trattamento: niente spazi), ha esattamente la forma
    6 lettere, 2 cifre, 1 lettera, 2 cifre, 1 lettera, 3 cifre, 1 lettera (le sostituzioni per omocodia non sono ammesse), la lettera
    del mese è una di `ABCDEHLMPRST`, il giorno è tra 1 e 31 oppure tra 41 e 71, e il carattere di controllo è giusto. Non si
    controlla che la data esista davvero.

    ### `sesso_da_codice(cf) -> str`
    `"F"` se il giorno è maggiore di 40, altrimenti `"M"`. `ValueError` se il codice non è valido (secondo `valida_codice`).

    ### `data_da_codice(cf, riferimento) -> date`
    La data di nascita. Il giorno è quello del codice meno 40 per le donne. L'anno è `2000 + AA` se questo valore non supera
    `riferimento.year`, altrimenti `1900 + AA` (`riferimento` è una `date`). `ValueError` se il codice non è valido o la data non
    esiste (30 febbraio).
''')

SRC = dd(r'''
    import re
    import unicodedata
    from datetime import date

    _MONTHS = "ABCDEHLMPRST"
    _ODD = dict(zip("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                    [1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12, 14,
                     16, 10, 22, 25, 24, 23]))
    _VOWELS = "AEIOU"
    _PLACE = re.compile(r"[A-Z][0-9]{3}")
    _SHAPE = re.compile(r"[A-Z]{6}[0-9]{2}[A-Z][0-9]{2}[A-Z][0-9]{3}[A-Z]")


    def _letters(text: str) -> str:
        base = unicodedata.normalize("NFD", text)
        return "".join(ch for ch in base.upper() if "A" <= ch <= "Z")


    def _consonants_vowels(text: str):
        letters = _letters(text)
        return [c for c in letters if c not in _VOWELS], [c for c in letters if c in _VOWELS]


    def codice_cognome(cognome: str) -> str:
        cons, vow = _consonants_vowels(cognome)
        return ("".join(cons + vow) + "XXX")[:3]


    def codice_nome(nome: str) -> str:
        cons, vow = _consonants_vowels(nome)
        if len(cons) >= 4:
            cons = [cons[0], cons[2], cons[3]]
        return ("".join(cons + vow) + "XXX")[:3]


    def codice_data(data: date, sesso: str) -> str:
        if sesso not in ("M", "F"):
            raise ValueError("sesso deve essere M o F")
        day = data.day + (40 if sesso == "F" else 0)
        return "%02d%s%02d" % (data.year % 100, _MONTHS[data.month - 1], day)


    def carattere_controllo(quindici: str) -> str:
        total = 0
        for i, ch in enumerate(quindici):
            total += _ODD[ch] if i % 2 == 0 else (int(ch) if ch.isdigit() else ord(ch) - 65)
        return chr(65 + total % 26)


    def calcola_codice(cognome: str, nome: str, data: date, sesso: str, comune: str) -> str:
        if not _PLACE.fullmatch(comune):
            raise ValueError("codice del comune non valido: %r" % (comune,))
        base = codice_cognome(cognome) + codice_nome(nome) + codice_data(data, sesso) + comune
        return base + carattere_controllo(base)


    def _parse(cf: str):
        cf = cf.upper()
        if not _SHAPE.fullmatch(cf) or cf[8] not in _MONTHS:
            return None
        day = int(cf[9:11])
        if not (1 <= day <= 31 or 41 <= day <= 71):
            return None
        if carattere_controllo(cf[:15]) != cf[15]:
            return None
        return cf


    def valida_codice(cf: str) -> bool:
        return _parse(cf) is not None


    def sesso_da_codice(cf: str) -> str:
        cf = _parse(cf)
        if cf is None:
            raise ValueError("codice non valido")
        return "F" if int(cf[9:11]) > 40 else "M"


    def data_da_codice(cf: str, riferimento: date) -> date:
        cf = _parse(cf)
        if cf is None:
            raise ValueError("codice non valido")
        day = int(cf[9:11])
        day = day - 40 if day > 40 else day
        yy = int(cf[6:8])
        year = 2000 + yy if 2000 + yy <= riferimento.year else 1900 + yy
        try:
            return date(year, _MONTHS.index(cf[8]) + 1, day)
        except ValueError:
            raise ValueError("data non valida")
''')

VISIBLE = dd('''
    import unittest
    from datetime import date

    from codfisc import calcola_codice, codice_cognome, valida_codice


    class Base(unittest.TestCase):
        def test_cognome(self):
            self.assertEqual(codice_cognome("Rossi"), "RSS")

        def test_calcolo(self):
            self.assertEqual(calcola_codice("Rossi", "Mario", date(1985, 12, 10), "M", "A562"), "RSSMRA85T10A562S")

        def test_valida(self):
            self.assertTrue(valida_codice("RSSMRA85T10A562S"))


    if __name__ == "__main__":
        unittest.main()
''')

HIDDEN = dd('''
    import unittest
    from datetime import date

    from codfisc import (calcola_codice, carattere_controllo, codice_cognome, codice_data, codice_nome, data_da_codice,
                         sesso_da_codice, valida_codice)

    D = date


    class Cognome(unittest.TestCase):
        def test_esempi(self):
            casi = {"Rossi": "RSS", "Bianchi": "BNC", "De Luca": "DLC", "Dell'Orto": "DLL", "Bruno": "BRN", "Esposito": "SPS",
                    "D'Angelo": "DNG", "Mario": "MRA", "Li": "LIX", "Fo": "FOX", "Ng": "NGX", "Ye": "YEX", "Aei": "AEI"}
            for cognome, atteso in casi.items():
                self.assertEqual(codice_cognome(cognome), atteso, cognome)

        def test_consonanti_prima_delle_vocali(self):
            self.assertEqual(codice_cognome("Aldo"), "LDA")
            self.assertEqual(codice_cognome("Eva"), "VEA")
            self.assertEqual(codice_cognome("Oro"), "ROO")
            self.assertEqual(codice_cognome("Ada"), "DAA")

        def test_accenti_e_caratteri_estranei(self):
            self.assertEqual(codice_cognome("Perché"), "PRC")
            self.assertEqual(codice_cognome("Ōkami"), "KMO")
            self.assertEqual(codice_cognome("  r o s s i  "), "RSS")
            self.assertEqual(codice_cognome("rossi"), "RSS")
            self.assertEqual(codice_cognome("R-o.s'si"), "RSS")
            self.assertEqual(codice_cognome("Nicolò"), "NCL")

        def test_vuoto(self):
            self.assertEqual(codice_cognome(""), "XXX")
            self.assertEqual(codice_cognome("123 !"), "XXX")


    class Nome(unittest.TestCase):
        def test_poche_consonanti(self):
            casi = {"Mario": "MRA", "Anna": "NNA", "Luca": "LCU", "Giulia": "GLI", "Maria": "MRA", "Li": "LIX", "Xu": "XUX"}
            for nome, atteso in casi.items():
                self.assertEqual(codice_nome(nome), atteso, nome)

        def test_quattro_o_piu_consonanti(self):
            casi = {"Giovanni": "GNN", "Gianluca": "GLC", "Francesca": "FNC", "Gianfranco": "GFR", "Christian": "CRS",
                    "Nicolò": "NCL", "Roberto": "RRT"}
            for nome, atteso in casi.items():
                self.assertEqual(codice_nome(nome), atteso, nome)

        def test_esattamente_tre_consonanti(self):
            self.assertEqual(codice_nome("Marco"), "MRC")
            self.assertEqual(codice_nome("Luigi"), "LGU")
            self.assertEqual(codice_nome("Carlo"), "CRL")

        def test_esattamente_quattro_consonanti(self):
            self.assertEqual(codice_nome("Marcos"), "MCS")
            self.assertEqual(codice_nome("Alberto"), "LRT")
            self.assertEqual(codice_nome("Pietro"), "PTR")

        def test_vuoto(self):
            self.assertEqual(codice_nome(""), "XXX")
            self.assertEqual(codice_nome("A"), "AXX")


    class Data(unittest.TestCase):
        def test_maschio(self):
            self.assertEqual(codice_data(D(1985, 12, 10), "M"), "85T10")
            self.assertEqual(codice_data(D(2001, 1, 31), "M"), "01A31")
            self.assertEqual(codice_data(D(2024, 2, 29), "M"), "24B29")
            self.assertEqual(codice_data(D(1999, 7, 1), "M"), "99L01")

        def test_femmina(self):
            self.assertEqual(codice_data(D(1985, 12, 10), "F"), "85T50")
            self.assertEqual(codice_data(D(1999, 7, 1), "F"), "99L41")
            self.assertEqual(codice_data(D(1950, 5, 15), "F"), "50E55")
            self.assertEqual(codice_data(D(2003, 3, 31), "F"), "03C71")

        def test_lettere_dei_mesi(self):
            for mese, lettera in enumerate("ABCDEHLMPRST", 1):
                self.assertEqual(codice_data(D(2020, mese, 15), "M")[2], lettera, mese)

        def test_anno_a_due_cifre(self):
            self.assertEqual(codice_data(D(2000, 6, 6), "M")[:2], "00")
            self.assertEqual(codice_data(D(1909, 6, 6), "M")[:2], "09")
            self.assertEqual(codice_data(D(1999, 6, 6), "M")[:2], "99")

        def test_sesso_non_valido(self):
            for s in ("", "m", "f", "X", "MF", None):
                with self.assertRaises(ValueError, msg=repr(s)):
                    codice_data(D(1985, 12, 10), s)


    class Controllo(unittest.TestCase):
        def test_esempio_classico(self):
            self.assertEqual(carattere_controllo("RSSMRA85T10A562"), "S")

        def test_altri(self):
            self.assertEqual(carattere_controllo("VRDGLI90C45H501"), "L")
            self.assertEqual(carattere_controllo("NRELCU10B28F205"), "W")
            self.assertEqual(carattere_controllo("NRELCU26B28F205"), "H")
            self.assertEqual(carattere_controllo("NRELCU00B29F205"), "Z")
            self.assertEqual(carattere_controllo("NRELCU00B28F205"), "X")
            self.assertEqual(carattere_controllo("NRELCU00B30F205"), "G")

        def test_posizioni_pari_e_dispari(self):
            # scambiando due caratteri vicini il controllo cambia
            self.assertNotEqual(carattere_controllo("RSSMRA85T10A562"), carattere_controllo("SRSMRA85T10A562"))
            self.assertNotEqual(carattere_controllo("RSSMRA85T10A562"), carattere_controllo("RSSMRA58T10A562"))

        def test_tabella_dispari_per_ogni_simbolo(self):
            # un solo simbolo in prima posizione (dispari), il resto 'A' (valore pari 0, dispari 1)
            resto = "A" * 14
            valori = dict(zip("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                              [1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12, 14,
                               16, 10, 22, 25, 24, 23]))
            base_dispari = 7  # posizioni 3, 5, ..., 15 con 'A' valgono 1 ciascuna
            for simbolo, v in valori.items():
                totale = v + base_dispari
                self.assertEqual(carattere_controllo(simbolo + resto), chr(65 + totale % 26), simbolo)

        def test_tabella_pari_per_ogni_simbolo(self):
            for k, simbolo in enumerate("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
                valore = k if k < 10 else k - 10
                testo = "A" + simbolo + "A" * 13
                totale = 8 * 1 + valore  # otto posizioni dispari con 'A' (1 ciascuna) e la posizione 2 con il simbolo, le altre pari 0
                self.assertEqual(carattere_controllo(testo), chr(65 + totale % 26), simbolo)


    class Insieme(unittest.TestCase):
        def test_classico(self):
            self.assertEqual(calcola_codice("Rossi", "Mario", D(1985, 12, 10), "M", "A562"), "RSSMRA85T10A562S")

        def test_donna(self):
            self.assertEqual(calcola_codice("Verdi", "Giulia", D(1990, 3, 5), "F", "H501"), "VRDGLI90C45H501L")

        def test_altri(self):
            self.assertEqual(calcola_codice("Neri", "Luca", D(2010, 2, 28), "M", "F205"), "NRELCU10B28F205W")
            self.assertEqual(calcola_codice("Neri", "Luca", D(2000, 2, 29), "M", "F205"), "NRELCU00B29F205Z")

        def test_comune_non_valido(self):
            for c in ("", "A", "AB1", "a123", "A12", "A1234", "1234", "AA12", "A56 ", "A56٢"):
                with self.assertRaises(ValueError, msg=repr(c)):
                    calcola_codice("Rossi", "Mario", D(1985, 12, 10), "M", c)

        def test_sesso_non_valido(self):
            with self.assertRaises(ValueError):
                calcola_codice("Rossi", "Mario", D(1985, 12, 10), "X", "A562")


    class Validazione(unittest.TestCase):
        def test_valido(self):
            for cf in ("RSSMRA85T10A562S", "VRDGLI90C45H501L", "NRELCU10B28F205W", "NRELCU00B30F205G"):
                self.assertTrue(valida_codice(cf), cf)

        def test_minuscole(self):
            self.assertTrue(valida_codice("rssmra85t10a562s"))
            self.assertTrue(valida_codice("RssMra85T10a562S"))

        def test_controllo_sbagliato(self):
            for k in "ABCDEFGHIJKLMNOPQRTUVWXYZ":
                self.assertFalse(valida_codice("RSSMRA85T10A562" + k), k)

        def test_forma_sbagliata(self):
            for cf in ("", "RSSMRA85T10A562", "RSSMRA85T10A562SS", " RSSMRA85T10A562S", "RSSMRA85T10A562S ", "RSS MRA85T10A562S",
                       "RSSMR085T10A562S", "RSSMRA8ST10A562S", "RSSMRA85110A562S", "RSSMRA85T1OA562S", "RSSMRA85T10562S",
                       "RSSMRA85T10AA62S", "RSSMRA85T10A5628", "1SSMRA85T10A562S"):
                self.assertFalse(valida_codice(cf), repr(cf))

        def test_mese(self):
            for lettera in "ABCDEHLMPRST":
                cf = "RSSMRA85" + lettera + "10A562"
                self.assertTrue(valida_codice(cf + carattere_controllo(cf)), lettera)
            for lettera in "FGIJKNOQUVWXYZ":
                cf = "RSSMRA85" + lettera + "10A562"
                self.assertFalse(valida_codice(cf + carattere_controllo(cf)), lettera)

        def test_giorno(self):
            for giorno in ("01", "15", "31", "41", "55", "71"):
                cf = "RSSMRA85T" + giorno + "A562"
                self.assertTrue(valida_codice(cf + carattere_controllo(cf)), giorno)
            for giorno in ("00", "32", "39", "40", "72", "99"):
                cf = "RSSMRA85T" + giorno + "A562"
                self.assertFalse(valida_codice(cf + carattere_controllo(cf)), giorno)

        def test_data_inesistente_ma_valida(self):
            cf = "NRELCU00B30F205"
            self.assertTrue(valida_codice(cf + "G"))


    class Estrazione(unittest.TestCase):
        def test_sesso(self):
            self.assertEqual(sesso_da_codice("RSSMRA85T10A562S"), "M")
            self.assertEqual(sesso_da_codice("VRDGLI90C45H501L"), "F")
            self.assertEqual(sesso_da_codice("rssmra85t10a562s"), "M")
            cf = "RSSMRA85T41A562"
            self.assertEqual(sesso_da_codice(cf + carattere_controllo(cf)), "F")
            cf = "RSSMRA85T31A562"
            self.assertEqual(sesso_da_codice(cf + carattere_controllo(cf)), "M")

        def test_data(self):
            self.assertEqual(data_da_codice("RSSMRA85T10A562S", D(2025, 6, 1)), D(1985, 12, 10))
            self.assertEqual(data_da_codice("VRDGLI90C45H501L", D(2025, 6, 1)), D(1990, 3, 5))
            self.assertEqual(data_da_codice("NRELCU10B28F205W", D(2025, 6, 1)), D(2010, 2, 28))
            self.assertEqual(data_da_codice("NRELCU00B29F205Z", D(2025, 6, 1)), D(2000, 2, 29))

        def test_secolo_dal_riferimento(self):
            self.assertEqual(data_da_codice("NRELCU26B28F205H", D(2025, 6, 1)), D(1926, 2, 28))
            self.assertEqual(data_da_codice("NRELCU26B28F205H", D(2026, 6, 1)), D(2026, 2, 28))
            self.assertEqual(data_da_codice("NRELCU25B28F205" + carattere_controllo("NRELCU25B28F205"), D(2025, 1, 1)), D(2025, 2, 28))
            self.assertEqual(data_da_codice("NRELCU00B28F205X", D(1999, 1, 1)), D(1900, 2, 28))

        def test_giorno_donna(self):
            cf = "VRDGLI90C45H501L"
            self.assertEqual(data_da_codice(cf, D(2025, 6, 1)).day, 5)

        def test_errori(self):
            for cf in ("", "RSSMRA85T10A562X", "RSSMRA85T10A562"):
                with self.assertRaises(ValueError, msg=cf):
                    data_da_codice(cf, D(2025, 6, 1))
                with self.assertRaises(ValueError, msg=cf):
                    sesso_da_codice(cf)
            with self.assertRaises(ValueError):
                data_da_codice("NRELCU00B30F205G", D(2025, 6, 1))   # 30 febbraio


    if __name__ == "__main__":
        unittest.main()
''')

LIB = Lib(
    name="codfisc", lang="python", title="`codfisc`",
    blurb="Il gestionale di un ambulatorio usa questa libreria per calcolare e controllare il codice fiscale dei pazienti.",
    files={"codfisc/__init__.py": "from .core import *  # noqa: F401,F403\n", "codfisc/core.py": SRC,
           "README.md": README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_base.py": VISIBLE},
    hidden_tests={"tests/test_completo.py": HIDDEN},
    mutate=["codfisc/core.py"], difficulty=4, tags=["validation", "checksum", "text", "dates"],
    probes=[
        'codice_cognome("De Luca")',
        'codice_cognome("Aldo")',
        'codice_cognome("Fo")',
        'codice_nome("Giovanni")',
        'codice_nome("Marco")',
        'codice_nome("Gianluca")',
        'codice_data(date(1985, 12, 10), "F")',
        'codice_data(date(2024, 2, 29), "M")',
        'carattere_controllo("VRDGLI90C45H501")',
        'calcola_codice("Rossi", "Mario", date(1985, 12, 10), "M", "A562")',
        'valida_codice("rssmra85t10a562s")',
        'valida_codice("RSSMRA85T40A562S")',
        'sesso_da_codice("VRDGLI90C45H501L")',
        'data_da_codice("NRELCU26B28F205H", date(2025, 6, 1))',
    ],
    probe_import="from datetime import date\nfrom codfisc import *",
)

register_native(LIB, "it", "fix-codfisc", n=9,
                summary="native: injected bugs in an Italian codice fiscale library, reports in Italian")
