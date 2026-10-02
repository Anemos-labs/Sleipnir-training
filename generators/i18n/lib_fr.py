"""Native bug-fix family in French: typography (narrow no-break spaces), elision, ordinals, dates (python)."""
from fx import Lib, dd

from ._native import register_native

README = dd(r'''
    # typofr

    Petits outils de typographie française pour la génération d'e-mails et de factures d'une librairie en ligne :
    espaces insécables, élision, ordinaux, listes, guillemets et dates. Uniquement la bibliothèque standard.

    Espaces utilisées : espace insécable `NBSP` = `U+00A0`, espace fine insécable `NNBSP` = `U+202F`.

    ## `nbsp_punct(text) -> str`
    Normalise l'espacement autour de la ponctuation.

    * Avant `;` `!` `?` : une `NNBSP`. Avant `:` : une `NBSP`. Les espaces déjà présents juste avant le signe (espace,
      `NBSP` ou `NNBSP`, en nombre quelconque) sont remplacés par cette seule espace ; s'il n'y en avait pas, elle est
      ajoutée.
    * Exceptions : (a) un signe au début du texte (précédé seulement d'espaces ou de rien) reste tel quel, espaces
      comprises ; (b) quand le signe suit un autre signe de `; ! ? :` (en ignorant les espaces entre les deux), les signes
      restent collés : les espaces entre eux disparaissent et rien n'est ajouté (`"Quoi ?!"` et `"Quoi ? !"` donnent
      tous deux `"Quoi" + NNBSP + "?!"`) ; (c) pour `:` collé au caractère précédent (aucune espace avant), rien n'est
      ajouté si ce caractère est un chiffre **et** que le caractère suivant est un chiffre (`12:30`, `3:1`), ni quand
      le signe est suivi de `//` (`https://exemple.org`). Si une espace précède, la règle générale s'applique
      (`3 : 1` devient `3` + `NBSP` + `: 1`).
    * Guillemets : après `«` il y a exactement une `NBSP` (les espaces existantes de tous types sont remplacées, ou une
      `NBSP` est ajoutée) et avant `»` exactement une `NBSP`, de la même façon.
    * Tout le reste du texte est inchangé.

    ## `elide(prefix, word) -> str`
    Colle un petit mot à `word`, avec élision quand il le faut, sinon sépare par une espace normale.

    * `prefix` (sans tenir compte de la casse) parmi `le la de je me te se ne que si` ; autre chose, ou `word` vide :
      `ValueError`.
    * Pour `le la de je me te se ne que` : on élide (`l' d' j' m' t' s' n' qu'`, avec l'apostrophe typographique `’`
      `U+2019`) si `word` commence par une voyelle `a e i o u à â ä é è ê ë î ï ô ö ù û ü œ æ`, par un `h` muet (tout `h`
      initial sauf les mots de `H_ASPIRE`, comparés en entier et sans tenir compte de la casse), ou si `word` est
      exactement `y` (`j’y`, `n’y`). Sinon : `prefix + " " + word`.
    * Pour `si` : on n'élide que devant `il` et `ils` (`s’il`, `s’ils`), jamais devant `elle`.
    * La casse du préfixe est conservée : si `prefix` commence par une majuscule, la forme élidée commence par une
      majuscule (`elide("Le", "ami")` donne `"L’ami"`, `elide("LE", "ami")` aussi).
    `H_ASPIRE` : `hache hall handicap haricot hasard hibou hockey homard honte hurler héros harpe hamac hanche hanter`.

    ## `ordinal_fr(n, feminine=False) -> str`
    `1` donne `"1er"` (ou `"1re"` si `feminine`), tous les autres nombres `"Ne"` : `"2e"`, `"11e"`, `"21e"`, `"101e"`, `"0e"`.
    Un nombre négatif est une `ValueError`.

    ## `join_list_fr(items, conj="et") -> str`
    Énumération : liste vide -> `""` ; un élément -> lui-même ; deux -> `"a et b"` ; plus -> `"a, b et c"` (pas de virgule
    avant la conjonction). `conj` remplace `et` (`"a, b ou c"`).

    ## `quote_fr(text) -> str`
    `text` (débarrassé des espaces ordinaires au début et à la fin) entre guillemets français : `«`, `NBSP`, le texte,
    `NBSP`, `»`.

    ## `date_fr(d, weekday=False) -> str`
    `"1er mars 2026"`, `"2 mars 2026"` : jour sans zéro initial, mais `1er` pour le premier du mois ; mois en minuscules
    avec accents (`février`, `août`, `décembre`) ; année sur quatre chiffres telle quelle. Avec `weekday=True`, le jour de la semaine
    en minuscules et une espace en tête : `"dimanche 1er mars 2026"`. Jours : lundi mardi mercredi jeudi vendredi samedi dimanche.
''')

SRC = dd(r'''
    import re
    from datetime import date

    NBSP = " "
    NNBSP = " "
    _SPACES = "   "
    _MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre",
               "décembre"]
    _WEEKDAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    H_ASPIRE = frozenset("hache hall handicap haricot hasard hibou hockey homard honte hurler héros harpe hamac hanche hanter".split())
    _VOWELS = "aeiouàâäéèêëîïôöùûüœæ"
    _ELIDING = {"le": "l", "la": "l", "de": "d", "je": "j", "me": "m", "te": "t", "se": "s", "ne": "n", "que": "qu"}


    def nbsp_punct(text: str) -> str:
        out = []
        n = len(text)
        for i, ch in enumerate(text):
            if ch in ";!?:":
                j = len(out)
                while j > 0 and out[j - 1] in _SPACES:
                    j -= 1
                spaces = len(out) - j
                prev = out[j - 1] if j else ""
                nxt = text[i + 1] if i + 1 < n else ""
                if j == 0:
                    out.append(ch)
                elif prev in ";!?:":
                    del out[j:]
                    out.append(ch)
                elif spaces == 0 and ch == ":" and prev.isdigit() and nxt.isdigit():
                    out.append(ch)
                elif spaces == 0 and ch == ":" and text.startswith("//", i + 1):
                    out.append(ch)
                else:
                    del out[j:]
                    out.append(NBSP if ch == ":" else NNBSP)
                    out.append(ch)
            else:
                out.append(ch)
        s = "".join(out)
        s = re.sub("«[   ]*", "« ", s)
        s = re.sub("[   ]*»", " »", s)
        return s


    def elide(prefix: str, word: str) -> str:
        p = prefix.lower()
        w = word.lower()
        if not word:
            raise ValueError("empty word")
        if p == "si":
            elides = w in ("il", "ils")
            short = "s"
        elif p in _ELIDING:
            elides = w[0] in _VOWELS or w == "y" or (w[0] == "h" and w not in H_ASPIRE)
            short = _ELIDING[p]
        else:
            raise ValueError("unknown prefix: %r" % (prefix,))
        if elides:
            return (short.capitalize() if prefix[0].isupper() else short) + "’" + word
        return prefix + " " + word


    def ordinal_fr(n: int, feminine: bool = False) -> str:
        if n < 0:
            raise ValueError("negative ordinal")
        if n == 1:
            return "1re" if feminine else "1er"
        return "%de" % n


    def join_list_fr(items, conj: str = "et") -> str:
        items = list(items)
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        return ", ".join(items[:-1]) + " " + conj + " " + items[-1]


    def quote_fr(text: str) -> str:
        return "«" + NBSP + text.strip(" ") + NBSP + "»"


    def date_fr(d: date, weekday: bool = False) -> str:
        day = "1er" if d.day == 1 else str(d.day)
        text = "%s %s %d" % (day, _MONTHS[d.month - 1], d.year)
        return _WEEKDAYS[d.weekday()] + " " + text if weekday else text
''')

VISIBLE = dd(r'''
    import unittest
    from datetime import date

    from typofr import date_fr, elide, ordinal_fr


    class Bases(unittest.TestCase):
        def test_elide(self):
            self.assertEqual(elide("le", "hôtel"), "l’hôtel")

        def test_ordinal(self):
            self.assertEqual(ordinal_fr(2), "2e")

        def test_date(self):
            self.assertEqual(date_fr(date(2026, 3, 2)), "2 mars 2026")


    if __name__ == "__main__":
        unittest.main()
''')

HIDDEN = dd(r'''
    import unittest
    from datetime import date

    from typofr import H_ASPIRE, date_fr, elide, join_list_fr, nbsp_punct, ordinal_fr, quote_fr

    N = " "
    T = " "


    class Punctuation(unittest.TestCase):
        def test_narrow_before_semicolon_bang_question(self):
            self.assertEqual(nbsp_punct("Bonjour !"), "Bonjour" + T + "!")
            self.assertEqual(nbsp_punct("Bonjour!"), "Bonjour" + T + "!")
            self.assertEqual(nbsp_punct("a ; b"), "a" + T + "; b")
            self.assertEqual(nbsp_punct("a;b"), "a" + T + ";b")
            self.assertEqual(nbsp_punct("Quoi ?"), "Quoi" + T + "?")

        def test_nbsp_before_colon(self):
            self.assertEqual(nbsp_punct("Voici : un test"), "Voici" + N + ": un test")
            self.assertEqual(nbsp_punct("Voici: un test"), "Voici" + N + ": un test")
            self.assertEqual(nbsp_punct("a:b"), "a" + N + ":b")

        def test_existing_spaces_are_replaced(self):
            self.assertEqual(nbsp_punct("Bonjour  !"), "Bonjour" + T + "!")
            self.assertEqual(nbsp_punct("a" + N + "?"), "a" + T + "?")
            self.assertEqual(nbsp_punct("a" + T + "!"), "a" + T + "!")
            self.assertEqual(nbsp_punct("a " + N + T + " ?"), "a" + T + "?")
            self.assertEqual(nbsp_punct("a" + T + ":"), "a" + N + ":")
            self.assertEqual(nbsp_punct("a" + N + ":"), "a" + N + ":")

        def test_glued_runs(self):
            self.assertEqual(nbsp_punct("Quoi ?!"), "Quoi" + T + "?!")
            self.assertEqual(nbsp_punct("Quoi? !"), "Quoi" + T + "?!")
            self.assertEqual(nbsp_punct("Quoi ? !"), "Quoi" + T + "?!")
            self.assertEqual(nbsp_punct("Quoi ?!?"), "Quoi" + T + "?!?")
            self.assertEqual(nbsp_punct("a ;:"), "a" + T + ";:")

        def test_digits_around_colon(self):
            self.assertEqual(nbsp_punct("Il est 12:30 ici"), "Il est 12:30 ici")
            self.assertEqual(nbsp_punct("Ratio 3:1"), "Ratio 3:1")
            self.assertEqual(nbsp_punct("3 : 1"), "3" + N + ": 1")
            self.assertEqual(nbsp_punct("12 :30"), "12" + N + ":30")
            self.assertEqual(nbsp_punct("a:1"), "a" + N + ":1")
            self.assertEqual(nbsp_punct("1:a"), "1" + N + ":a")
            self.assertEqual(nbsp_punct("12:30 !"), "12:30" + T + "!")

        def test_urls(self):
            self.assertEqual(nbsp_punct("https://exemple.org"), "https://exemple.org")
            self.assertEqual(nbsp_punct("http ://x"), "http" + N + "://x")
            self.assertEqual(nbsp_punct("voir http://a.fr/b?x=1 !"), "voir http://a.fr/b" + T + "?x=1" + T + "!")

        def test_start_of_text_untouched(self):
            self.assertEqual(nbsp_punct("?"), "?")
            self.assertEqual(nbsp_punct("  ?"), "  ?")
            self.assertEqual(nbsp_punct(": oui"), ": oui")
            self.assertEqual(nbsp_punct(" ! non"), " ! non")

        def test_guillemets(self):
            self.assertEqual(nbsp_punct("« Bonjour »"), "«" + N + "Bonjour" + N + "»")
            self.assertEqual(nbsp_punct("«Bonjour»"), "«" + N + "Bonjour" + N + "»")
            self.assertEqual(nbsp_punct("«  Bonjour  »"), "«" + N + "Bonjour" + N + "»")
            self.assertEqual(nbsp_punct("«" + T + "Bonjour" + T + "»"), "«" + N + "Bonjour" + N + "»")
            self.assertEqual(nbsp_punct("« Quoi ? »"), "«" + N + "Quoi" + T + "?" + N + "»")
            self.assertEqual(nbsp_punct("Il dit : « Oui ! »"), "Il dit" + N + ": «" + N + "Oui" + T + "!" + N + "»")

        def test_other_text_unchanged(self):
            for s in ("Fin.", "a, b", "x…", "Tiret - ici", "", "a  b", "2 + 2 = 4", "(oui)"):
                self.assertEqual(nbsp_punct(s), s)

        def test_several_marks(self):
            self.assertEqual(nbsp_punct("Liste: a; b; c!"), "Liste" + N + ": a" + T + "; b" + T + "; c" + T + "!")
            self.assertEqual(nbsp_punct("x : y: z"), "x" + N + ": y" + N + ": z")

        def test_idempotent(self):
            for s in ("Bonjour !", "Il dit : « Oui ! »", "Quoi ?!", "12:30 !", "Liste: a; b"):
                once = nbsp_punct(s)
                self.assertEqual(nbsp_punct(once), once)


    class Elision(unittest.TestCase):
        def test_vowels(self):
            self.assertEqual(elide("le", "ami"), "l’ami")
            self.assertEqual(elide("la", "école"), "l’école")
            self.assertEqual(elide("de", "un"), "d’un")
            self.assertEqual(elide("je", "ai"), "j’ai")
            self.assertEqual(elide("me", "aime"), "m’aime")
            self.assertEqual(elide("te", "il"), "t’il")
            self.assertEqual(elide("se", "est"), "s’est")
            self.assertEqual(elide("ne", "a"), "n’a")
            self.assertEqual(elide("que", "il"), "qu’il")

        def test_accented_and_ligature_vowels(self):
            for w in ("âne", "élève", "être", "île", "ôter", "ouvrir", "ulcère", "œuf", "æsir", "ïle", "üvula", "àla", "ëtre"):
                self.assertEqual(elide("le", w), "l’" + w, w)

        def test_consonants(self):
            for w in ("livre", "maison", "sac", "yaourt", "zèbre", "wagon", "tête", "ça"):
                self.assertEqual(elide("le", w), "le " + w, w)
            self.assertEqual(elide("de", "livre"), "de livre")
            self.assertEqual(elide("que", "tu"), "que tu")
            self.assertEqual(elide("je", "te"), "je te")

        def test_mute_h(self):
            self.assertEqual(elide("le", "hôtel"), "l’hôtel")
            self.assertEqual(elide("la", "heure"), "l’heure")
            self.assertEqual(elide("la", "héroïne"), "l’héroïne")
            self.assertEqual(elide("de", "homme"), "d’homme")
            self.assertEqual(elide("le", "hiver"), "l’hiver")

        def test_aspirated_h(self):
            for w in sorted(H_ASPIRE):
                self.assertEqual(elide("le", w), "le " + w, w)
            self.assertEqual(elide("de", "héros"), "de héros")
            self.assertEqual(elide("la", "HACHE"), "la HACHE")
            self.assertEqual(elide("le", "Héros"), "le Héros")

        def test_y(self):
            self.assertEqual(elide("je", "y"), "j’y")
            self.assertEqual(elide("ne", "y"), "n’y")
            self.assertEqual(elide("le", "y"), "l’y")
            self.assertEqual(elide("me", "yeux"), "me yeux")

        def test_si(self):
            self.assertEqual(elide("si", "il"), "s’il")
            self.assertEqual(elide("si", "ils"), "s’ils")
            self.assertEqual(elide("si", "elle"), "si elle")
            self.assertEqual(elide("si", "on"), "si on")
            self.assertEqual(elide("si", "ami"), "si ami")
            self.assertEqual(elide("Si", "il"), "S’il")
            self.assertEqual(elide("si", "IL"), "s’IL")

        def test_case(self):
            self.assertEqual(elide("Le", "ami"), "L’ami")
            self.assertEqual(elide("LE", "ami"), "L’ami")
            self.assertEqual(elide("Que", "il"), "Qu’il")
            self.assertEqual(elide("LA", "école"), "L’école")
            self.assertEqual(elide("Le", "livre"), "Le livre")
            self.assertEqual(elide("LE", "Ami"), "L’Ami")
            self.assertEqual(elide("le", "Œuf"), "l’Œuf")
            self.assertEqual(elide("le", "ÉCOLE"), "l’ÉCOLE")

        def test_errors(self):
            for prefix, word in (("ce", "est"), ("du", "ami"), ("", "ami"), ("lé", "ami"), ("le", ""), ("si", "")):
                with self.assertRaises(ValueError, msg=(prefix, word)):
                    elide(prefix, word)


    class Ordinals(unittest.TestCase):
        def test_ordinals(self):
            self.assertEqual(ordinal_fr(1), "1er")
            self.assertEqual(ordinal_fr(1, True), "1re")
            for n in (0, 2, 3, 4, 10, 11, 12, 21, 31, 101, 111, 1000):
                self.assertEqual(ordinal_fr(n), "%de" % n)
                self.assertEqual(ordinal_fr(n, feminine=True), "%de" % n)

        def test_negative(self):
            with self.assertRaises(ValueError):
                ordinal_fr(-1)


    class Lists(unittest.TestCase):
        def test_lists(self):
            self.assertEqual(join_list_fr([]), "")
            self.assertEqual(join_list_fr(["a"]), "a")
            self.assertEqual(join_list_fr(["a", "b"]), "a et b")
            self.assertEqual(join_list_fr(["a", "b", "c"]), "a, b et c")
            self.assertEqual(join_list_fr(["a", "b", "c", "d"]), "a, b, c et d")
            self.assertEqual(join_list_fr(["a", "b"], "ou"), "a ou b")
            self.assertEqual(join_list_fr(["a", "b", "c"], "ou"), "a, b ou c")
            self.assertEqual(join_list_fr(("x", "y")), "x et y")
            self.assertEqual(join_list_fr(iter(["x", "y", "z"])), "x, y et z")


    class Quotes(unittest.TestCase):
        def test_quote(self):
            self.assertEqual(quote_fr("Bonjour"), "«" + N + "Bonjour" + N + "»")
            self.assertEqual(quote_fr("  Bonjour  "), "«" + N + "Bonjour" + N + "»")
            self.assertEqual(quote_fr("deux mots"), "«" + N + "deux mots" + N + "»")
            self.assertEqual(quote_fr(" a "), "«" + N + "a" + N + "»")

        def test_inner_spaces_kept(self):
            self.assertEqual(quote_fr(" a  b "), "«" + N + "a  b" + N + "»")
            self.assertEqual(quote_fr("\tx"), "«" + N + "\tx" + N + "»")


    class Dates(unittest.TestCase):
        def test_first_of_month(self):
            self.assertEqual(date_fr(date(2026, 3, 1)), "1er mars 2026")
            self.assertEqual(date_fr(date(2025, 1, 1)), "1er janvier 2025")
            self.assertEqual(date_fr(date(2025, 11, 1)), "1er novembre 2025")

        def test_other_days(self):
            self.assertEqual(date_fr(date(2026, 3, 2)), "2 mars 2026")
            self.assertEqual(date_fr(date(2025, 12, 31)), "31 décembre 2025")
            self.assertEqual(date_fr(date(2024, 2, 29)), "29 février 2024")
            self.assertEqual(date_fr(date(2026, 8, 15)), "15 août 2026")
            self.assertEqual(date_fr(date(2026, 10, 11)), "11 octobre 2026")
            self.assertEqual(date_fr(date(2026, 3, 21)), "21 mars 2026")

        def test_months(self):
            names = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
                     "novembre", "décembre"]
            for m, name in enumerate(names, 1):
                self.assertEqual(date_fr(date(2025, m, 15)), "15 %s 2025" % name)

        def test_weekday(self):
            self.assertEqual(date_fr(date(2026, 3, 1), weekday=True), "dimanche 1er mars 2026")
            self.assertEqual(date_fr(date(2026, 3, 2), True), "lundi 2 mars 2026")
            self.assertEqual(date_fr(date(2025, 12, 31), True), "mercredi 31 décembre 2025")
            self.assertEqual(date_fr(date(2024, 2, 29), True), "jeudi 29 février 2024")
            self.assertEqual(date_fr(date(2026, 8, 15), True), "samedi 15 août 2026")

        def test_every_weekday(self):
            names = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
            for k, name in enumerate(names):
                self.assertTrue(date_fr(date(2026, 3, 2 + k), True).startswith(name + " "))

        def test_short_year_not_padded(self):
            self.assertEqual(date_fr(date(999, 1, 2)), "2 janvier 999")


    if __name__ == "__main__":
        unittest.main()
''')

LIB = Lib(
    name="typofr", lang="python", title="`typofr`",
    blurb="Une librairie en ligne utilise ces fonctions pour mettre en forme ses e-mails et ses factures en français.",
    files={"typofr/__init__.py": "from .core import *  # noqa: F401,F403\n", "typofr/core.py": SRC,
           "README.md": README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_bases.py": VISIBLE},
    hidden_tests={"tests/test_complet.py": HIDDEN},
    mutate=["typofr/core.py"], difficulty=3, tags=["unicode", "typography", "text"],
    probes=[
        'nbsp_punct("Bonjour !")',
        'nbsp_punct("Voici: un test")',
        'nbsp_punct("Quoi ? !")',
        'nbsp_punct("Il est 12:30 ici")',
        'nbsp_punct("https://exemple.org")',
        'nbsp_punct("« Quoi ? »")',
        'elide("la", "héroïne")',
        'elide("le", "héros")',
        'elide("si", "elle")',
        'elide("LE", "ami")',
        'elide("je", "y")',
        'ordinal_fr(1, True)',
        'ordinal_fr(21)',
        'join_list_fr(["a", "b", "c"])',
        'quote_fr("  Bonjour  ")',
        'date_fr(date(2026, 3, 1), weekday=True)',
        'date_fr(date(2024, 2, 29))',
    ],
    probe_import="from datetime import date\nfrom typofr import *",
)

register_native(LIB, "fr", "fix-typofr", n=9,
                summary="native: injected bugs in a French typography/elision/date library, reports in French")
