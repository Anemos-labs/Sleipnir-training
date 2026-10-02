"""Native bug-fix family in Turkish: Turkish-aware casing, collation and suffix helpers (python)."""
from fx import Lib, dd

from ._native import register_native

README = dd('''
    # trmetin

    Bir yayınevinin web sitesi için yazılmış küçük Türkçe metin yardımcıları. Türkçede `i`/`ı` ve `I`/`İ` ayrı
    harflerdir; Python'un `str.lower()` ve `str.upper()` fonksiyonları bunu bilmez (`"I".lower()` sonucu `"i"` olur,
    `"İ".lower()` ise iki karakterlik bir dize verir). Bu paket farkı doğru ele alır.

    Türk alfabesi: `a b c ç d e f g ğ h ı i j k l m n o ö p r s ş t u ü v y z`. Q, W ve X Türk alfabesinde yoktur ama
    yabancı özel adlarda geçer; sıralamada Latin alfabesindeki yerlerinde sayılırlar (bkz. `collation_key_tr`).

    ## `lower_tr(s) -> str`
    Türkçe küçük harfe çevirir: `I` -> `ı`, `İ` -> `i`. Diğer karakterler `str.lower()` gibi çevrilir. Uzunluk
    değişmez.

    ## `upper_tr(s) -> str`
    Türkçe büyük harfe çevirir: `i` -> `İ`, `ı` -> `I`. Diğer karakterler `str.upper()` gibi çevrilir.

    ## `title_tr(s) -> str`
    Her sözcüğün ilk karakterini `upper_tr` ile büyütür, geri kalan karakterlerini `lower_tr` ile küçültür.
    Sözcükleri yalnızca boşluk karakterleri ve `-` ayırır; kesme işareti sözcüğü *bölmez*, yani
    `title_tr("ANKARA'DA")` sonucu `"Ankara'da"` olur. Sözcük harfle başlamıyorsa ilk karakteri olduğu gibi kalır
    (`"1.SINIF"` -> `"1.sınıf"`).

    ## `ascii_fold_tr(s) -> str`
    Türkçe harfleri ASCII karşılıklarına çevirir: `ç ğ ı ö ş ü İ` -> `c g i o s u I` (büyük harfler büyük kalır:
    `Ç Ğ Ö Ş Ü` -> `C G O S U`). Diğer karakterlere dokunmaz.

    ## `collation_key_tr(s) -> tuple`
    Türk alfabesine göre sıralama anahtarı. Harfler şu sırayla karşılaştırılır:
    `a b c ç d e f g ğ h ı i j k l m n o ö p q r s ş t u ü v w x y z`; büyük/küçük harf farkı (`lower_tr` ile
    küçültülerek) önce yok sayılır. Harf olmayan karakterler (rakam, boşluk, noktalama) her harften önce gelir ve
    kendi aralarında Unicode kod noktasına göre sıralanır. Kısa dize, onunla başlayan uzun dizeden önce gelir
    (`"ada" < "adam"`). İki dize harfleri aynı ama yazımı farklıysa, ilk farklı büyük/küçük harf konumunda küçük
    harfli olan önce gelir (`"ada" < "aDa" < "Ada"`).

    ## `sorted_tr(items) -> list`
    Dizeleri `collation_key_tr` ile sıralayıp yeni bir liste döndürür.

    ## `initials_tr(name) -> str`
    Bir adın baş harflerini büyük harfle birleştirir. Sözcükleri boşluk ve `-` ayırır; harfle başlamayan sözcükler
    atlanır. `initials_tr("ışıl çiçek")` -> `"IÇ"`, `initials_tr("ismail ışık")` -> `"İI"`.

    ## `plural_tr(word) -> str`
    Çoğul eki ekler: sözcükteki *son* ünlü `a ı o u` ise `lar`, `e i ö ü` ise `ler` (büyük/küçük harf fark etmez).
    Ek her zaman küçük harfle yazılır, sözcüğün kendisi değişmez. Ünlü yoksa `ValueError`.
    `plural_tr("kitap")` -> `"kitaplar"`, `plural_tr("göz")` -> `"gözler"`.

    ## `locative_tr(word) -> str`
    Bulunma (-DA) ekini ekler. Ünlü uyumu: son ünlü `a ı o u` ise `a`, `e i ö ü` ise `e`. Ünsüz benzeşmesi: sözcük
    `f s t k ç ş h p` harflerinden biriyle bitiyorsa `t`, aksi halde (ünlüyle bitenler dahil) `d` kullanılır.
    Ek her zaman küçük harfle yazılır. Sözcük büyük harfle başlıyorsa (özel ad) ek kesme işaretiyle eklenir: `locative_tr("Ankara")` ->
    `"Ankara'da"`, `locative_tr("kitap")` -> `"kitapta"`, `locative_tr("ev")` -> `"evde"`. Ünlü yoksa `ValueError`.
''')

SRC = dd('''
    ALPHABET = "abcçdefgğhıijklmnoöpqrsştuüvwxyz"
    _RANK = {ch: i for i, ch in enumerate(ALPHABET)}
    VOWELS_BACK = "aıou"
    VOWELS_FRONT = "eiöü"
    HARD = "fstkçşhp"

    _LOWER = {"I": "ı", "İ": "i"}
    _UPPER = {"i": "İ", "ı": "I"}
    _FOLD = str.maketrans("çğıöşüİÇĞÖŞÜ", "cgiosuICGOSU")


    def lower_tr(s: str) -> str:
        return "".join(_LOWER.get(ch) or ch.lower() for ch in s)


    def upper_tr(s: str) -> str:
        return "".join(_UPPER.get(ch) or ch.upper() for ch in s)


    def title_tr(s: str) -> str:
        out = []
        at_start = True
        for ch in s:
            if ch.isspace() or ch == "-":
                out.append(ch)
                at_start = True
            elif at_start:
                out.append(upper_tr(ch))
                at_start = False
            else:
                out.append(lower_tr(ch))
        return "".join(out)


    def ascii_fold_tr(s: str) -> str:
        return s.translate(_FOLD)


    def collation_key_tr(s: str) -> tuple:
        low = lower_tr(s)
        primary = []
        for ch in low:
            if ch in _RANK:
                primary.append((1, _RANK[ch]))
            else:
                primary.append((0, ord(ch)))
        case = tuple(0 if lower_tr(ch) == ch else 1 for ch in s)
        return (tuple(primary), case)


    def sorted_tr(items) -> list:
        return sorted(items, key=collation_key_tr)


    def initials_tr(name: str) -> str:
        out = []
        word = ""
        for ch in name + " ":
            if ch.isspace() or ch == "-":
                if word and word[0].isalpha():
                    out.append(upper_tr(word[0]))
                word = ""
            else:
                word += ch
        return "".join(out)


    def _last_vowel_kind(word: str) -> str:
        for ch in reversed(lower_tr(word)):
            if ch in VOWELS_BACK:
                return "back"
            if ch in VOWELS_FRONT:
                return "front"
        raise ValueError("word has no vowel: %r" % word)


    def plural_tr(word: str) -> str:
        return word + ("lar" if _last_vowel_kind(word) == "back" else "ler")


    def locative_tr(word: str) -> str:
        vowel = "a" if _last_vowel_kind(word) == "back" else "e"
        consonant = "t" if lower_tr(word)[-1] in HARD else "d"
        sep = "'" if word[0] != lower_tr(word[0]) else ""
        return word + sep + consonant + vowel
''')

VISIBLE = dd('''
    import unittest

    from trmetin import locative_tr, lower_tr, plural_tr, upper_tr


    class TemelTestler(unittest.TestCase):
        def test_kucuk_harf(self):
            self.assertEqual(lower_tr("IĞDIR"), "ığdır")

        def test_buyuk_harf(self):
            self.assertEqual(upper_tr("istanbul"), "İSTANBUL")

        def test_cogul(self):
            self.assertEqual(plural_tr("ev"), "evler")

        def test_bulunma(self):
            self.assertEqual(locative_tr("okul"), "okulda")


    if __name__ == "__main__":
        unittest.main()
''')

HIDDEN = dd('''
    import unittest

    from trmetin import (ascii_fold_tr, collation_key_tr, initials_tr, locative_tr, lower_tr, plural_tr, sorted_tr,
                         title_tr, upper_tr)


    class Lower(unittest.TestCase):
        def test_dotted_and_dotless(self):
            self.assertEqual(lower_tr("I"), "ı")
            self.assertEqual(lower_tr("İ"), "i")
            self.assertEqual(lower_tr("Iİ"), "ıi")
            self.assertEqual(lower_tr("İSTANBUL"), "istanbul")
            self.assertEqual(lower_tr("DİYARBAKIR"), "diyarbakır")

        def test_length_preserved(self):
            s = "İİİ ISIK"
            self.assertEqual(len(lower_tr(s)), len(s))

        def test_other_letters(self):
            self.assertEqual(lower_tr("ÇĞÖŞÜ"), "çğöşü")
            self.assertEqual(lower_tr("ABC xyz 123"), "abc xyz 123")
            self.assertEqual(lower_tr(""), "")

        def test_already_lower(self):
            self.assertEqual(lower_tr("ığdır"), "ığdır")
            self.assertEqual(lower_tr("i"), "i")
            self.assertEqual(lower_tr("ı"), "ı")


    class Upper(unittest.TestCase):
        def test_dotted_and_dotless(self):
            self.assertEqual(upper_tr("i"), "İ")
            self.assertEqual(upper_tr("ı"), "I")
            self.assertEqual(upper_tr("iı"), "İI")
            self.assertEqual(upper_tr("ısparta"), "ISPARTA")
            self.assertEqual(upper_tr("diyarbakır"), "DİYARBAKIR")

        def test_other_letters(self):
            self.assertEqual(upper_tr("çğöşü"), "ÇĞÖŞÜ")
            self.assertEqual(upper_tr("abc xyz 123"), "ABC XYZ 123")
            self.assertEqual(upper_tr(""), "")

        def test_already_upper(self):
            self.assertEqual(upper_tr("İSTANBUL"), "İSTANBUL")
            self.assertEqual(upper_tr("I"), "I")


    class Title(unittest.TestCase):
        def test_words(self):
            self.assertEqual(title_tr("iSTANBUL boğazı"), "İstanbul Boğazı")
            self.assertEqual(title_tr("ışıl ıŞIL"), "Işıl Işıl")
            self.assertEqual(title_tr("IĞDIR"), "Iğdır")
            self.assertEqual(title_tr("İZMİR"), "İzmir")

        def test_hyphen_and_whitespace_split_words(self):
            self.assertEqual(title_tr("ayşe-gül hanım"), "Ayşe-Gül Hanım")
            self.assertEqual(title_tr("a  b\\tc"), "A  B\\tC")

        def test_apostrophe_does_not_split(self):
            self.assertEqual(title_tr("ANKARA'DA"), "Ankara'da")
            self.assertEqual(title_tr("istanbul'un"), "İstanbul'un")
            self.assertEqual(title_tr("İZMİR’İN"), "İzmir’in")

        def test_non_letter_start(self):
            self.assertEqual(title_tr("1.SINIF"), "1.sınıf")
            self.assertEqual(title_tr("(ISPARTA)"), "(ısparta)")

        def test_empty(self):
            self.assertEqual(title_tr(""), "")


    class AsciiFold(unittest.TestCase):
        def test_lower(self):
            self.assertEqual(ascii_fold_tr("çağrı öğüt şükür ığdır"), "cagri ogut sukur igdir")

        def test_upper(self):
            self.assertEqual(ascii_fold_tr("ÇAĞRI ÖĞÜT ŞÜKÜR İZMİR"), "CAGRI OGUT SUKUR IZMIR")

        def test_untouched(self):
            self.assertEqual(ascii_fold_tr("abc XYZ 123 é"), "abc XYZ 123 é")
            self.assertEqual(ascii_fold_tr("I"), "I")


    class Collation(unittest.TestCase):
        def test_alphabet_order(self):
            letters = "abcçdefgğhıijklmnoöprsştuüvyz"
            self.assertEqual(sorted_tr(list(reversed(letters))), list(letters))

        def test_q_w_x_in_latin_positions(self):
            self.assertEqual(sorted_tr(["x", "y", "w", "v", "q", "p", "r"]), ["p", "q", "r", "v", "w", "x", "y"])

        def test_words(self):
            words = ["şeker", "sakız", "çay", "cam", "ağaç", "zeytin", "ılık", "iyi", "ışık", "göl", "gül", "ğ"]
            self.assertEqual(sorted_tr(words), ["ağaç", "cam", "çay", "göl", "gül", "ğ", "ılık", "ışık", "iyi", "sakız", "şeker", "zeytin"])

        def test_cedilla_and_umlaut_differ_from_base(self):
            self.assertEqual(sorted_tr(["ci", "çi", "cı"]), ["cı", "ci", "çi"])
            self.assertEqual(sorted_tr(["oz", "öz", "oy"]), ["oy", "oz", "öz"])
            self.assertEqual(sorted_tr(["su", "şu", "sü"]), ["su", "sü", "şu"])

        def test_dotless_before_dotted(self):
            self.assertEqual(sorted_tr(["iz", "ız", "hz", "jz"]), ["hz", "ız", "iz", "jz"])

        def test_capital_dotted_and_dotless(self):
            self.assertEqual(sorted_tr(["İzmir", "Iğdır", "Isparta", "Hatay"]), ["Hatay", "Iğdır", "Isparta", "İzmir"])

        def test_prefix_first(self):
            self.assertEqual(sorted_tr(["adam", "ada", "adamlar"]), ["ada", "adam", "adamlar"])

        def test_case_ignored_in_primary(self):
            self.assertEqual(sorted_tr(["Bal", "arı", "Çiçek", "bal2", "ARI2"]), ["arı", "ARI2", "Bal", "bal2", "Çiçek"])

        def test_case_tiebreak_lowercase_first(self):
            self.assertEqual(sorted_tr(["Ada", "ada", "ADA", "aDa"]), ["ada", "aDa", "Ada", "ADA"])
            self.assertEqual(sorted_tr(["Işık", "ışık"]), ["ışık", "Işık"])

        def test_non_letters_first(self):
            self.assertEqual(sorted_tr(["a", "1", " ", "-", "A1", "a b"]), [" ", "-", "1", "a", "a b", "A1"])
            self.assertEqual(sorted_tr(["b", "1", " ", "-"]), [" ", "-", "1", "b"])
            self.assertEqual(sorted_tr(["a b", "ab", "a-b"]), ["a b", "a-b", "ab"])

        def test_key_shape(self):
            k = collation_key_tr("Iş")
            self.assertEqual(k[0], ((1, 10), (1, 23)))
            self.assertEqual(k[1], (1, 0))
            self.assertLess(collation_key_tr("a"), collation_key_tr("b"))

        def test_stability_and_empty(self):
            self.assertEqual(sorted_tr([]), [])
            self.assertEqual(sorted_tr(["a", "a"]), ["a", "a"])
            self.assertLess(collation_key_tr(""), collation_key_tr("a"))


    class Initials(unittest.TestCase):
        def test_basic(self):
            self.assertEqual(initials_tr("ışıl çiçek"), "IÇ")
            self.assertEqual(initials_tr("ismail ışık"), "İI")
            self.assertEqual(initials_tr("mustafa kemal atatürk"), "MKA")

        def test_hyphen(self):
            self.assertEqual(initials_tr("ayşe-gül yılmaz"), "AGY")

        def test_skip_non_letters(self):
            self.assertEqual(initials_tr("ali 2. veli"), "AV")
            self.assertEqual(initials_tr("  ali   veli  "), "AV")
            self.assertEqual(initials_tr("(ali) veli"), "V")

        def test_empty(self):
            self.assertEqual(initials_tr(""), "")
            self.assertEqual(initials_tr("   "), "")


    class Plural(unittest.TestCase):
        def test_back_vowels(self):
            for word in ("kitap", "okul", "ışık", "kız", "masa", "yol", "sınıf"):
                self.assertEqual(plural_tr(word), word + "lar")

        def test_front_vowels(self):
            for word in ("ev", "göz", "gül", "dil", "çiçek", "köpek", "ütü"):
                self.assertEqual(plural_tr(word), word + "ler")

        def test_last_vowel_decides(self):
            self.assertEqual(plural_tr("kalem"), "kalemler")
            self.assertEqual(plural_tr("saat"), "saatlar")
            self.assertEqual(plural_tr("kardeş"), "kardeşler")
            self.assertEqual(plural_tr("elma"), "elmalar")
            self.assertEqual(plural_tr("anne"), "anneler")

        def test_case_insensitive_vowels(self):
            self.assertEqual(plural_tr("OKUL"), "OKULlar")
            self.assertEqual(plural_tr("İSİM"), "İSİMler")
            self.assertEqual(plural_tr("ISIK"), "ISIKlar")

        def test_no_vowel(self):
            for word in ("", "str", "123"):
                with self.assertRaises(ValueError):
                    plural_tr(word)


    class Locative(unittest.TestCase):
        def test_voiced(self):
            self.assertEqual(locative_tr("ev"), "evde")
            self.assertEqual(locative_tr("okul"), "okulda")
            self.assertEqual(locative_tr("göz"), "gözde")
            self.assertEqual(locative_tr("kız"), "kızda")

        def test_hard_consonants(self):
            self.assertEqual(locative_tr("kitap"), "kitapta")
            self.assertEqual(locative_tr("sokak"), "sokakta")
            self.assertEqual(locative_tr("sınıf"), "sınıfta")
            self.assertEqual(locative_tr("kuş"), "kuşta")
            self.assertEqual(locative_tr("ağaç"), "ağaçta")
            self.assertEqual(locative_tr("kapı"), "kapıda")
            self.assertEqual(locative_tr("yurt"), "yurtta")
            self.assertEqual(locative_tr("ders"), "derste")
            self.assertEqual(locative_tr("sabah"), "sabahta")

        def test_vowel_final(self):
            self.assertEqual(locative_tr("masa"), "masada")
            self.assertEqual(locative_tr("anne"), "annede")
            self.assertEqual(locative_tr("dolu"), "doluda")
            self.assertEqual(locative_tr("ütü"), "ütüde")

        def test_vowel_harmony_uses_last_vowel(self):
            self.assertEqual(locative_tr("saat"), "saatta")
            self.assertEqual(locative_tr("hastane"), "hastanede")
            self.assertEqual(locative_tr("kalem"), "kalemde")
            self.assertEqual(locative_tr("park"), "parkta")
            self.assertEqual(locative_tr("kent"), "kentte")
            self.assertEqual(locative_tr("çiçek"), "çiçekte")

        def test_proper_nouns(self):
            self.assertEqual(locative_tr("Ankara"), "Ankara'da")
            self.assertEqual(locative_tr("İzmir"), "İzmir'de")
            self.assertEqual(locative_tr("Işık"), "Işık'ta")
            self.assertEqual(locative_tr("Edirne"), "Edirne'de")
            self.assertEqual(locative_tr("Çorum"), "Çorum'da")
            self.assertEqual(locative_tr("Ağrı"), "Ağrı'da")

        def test_uppercase_word_hard_final(self):
            self.assertEqual(locative_tr("Bursa"), "Bursa'da")
            self.assertEqual(locative_tr("Antep"), "Antep'te")
            self.assertEqual(locative_tr("Kars"), "Kars'ta")

        def test_no_vowel(self):
            with self.assertRaises(ValueError):
                locative_tr("str")


    if __name__ == "__main__":
        unittest.main()
''')

LIB = Lib(
    name="trmetin", lang="python", title="`trmetin`",
    blurb="Bir yayınevinin web sitesi bu yardımcılarla Türkçe başlıkları büyütüp küçültüyor, sıralıyor ve ek getiriyor.",
    files={"trmetin/__init__.py": "from .core import *  # noqa: F401,F403\n", "trmetin/core.py": SRC,
           "README.md": README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_temel.py": VISIBLE},
    hidden_tests={"tests/test_tam.py": HIDDEN},
    mutate=["trmetin/core.py"], difficulty=3, tags=["unicode", "locale", "text"],
    probes=[
        'lower_tr("IĞDIR")',
        'lower_tr("İSTANBUL")',
        'upper_tr("ısparta")',
        'upper_tr("diyarbakır")',
        'title_tr("ANKARA\'DA")',
        'title_tr("ayşe-gül hanım")',
        'ascii_fold_tr("ÇAĞRI ÖĞÜT ŞÜKÜR İZMİR")',
        'sorted_tr(["su", "şu", "sü"])',
        'sorted_tr(["iz", "ız", "hz", "jz"])',
        'sorted_tr(["Ada", "ada", "ADA", "aDa"])',
        'initials_tr("ismail ışık")',
        'plural_tr("saat")',
        'locative_tr("kitap")',
        'locative_tr("Ankara")',
        'locative_tr("saat")',
    ],
    probe_import="from trmetin import *",
)

register_native(LIB, "tr", "fix-trmetin", n=9,
                summary="native: injected bugs in a Turkish casing/collation/suffix library, reports in Turkish")
