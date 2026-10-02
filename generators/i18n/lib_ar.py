"""Native bug-fix family in Arabic: digit normalisation, amount parsing, search keys and text direction (python)."""
from fx import Lib, dd

from ._native import register_native

README = dd(r'''
    # arnorm

    أدوات صغيرة لمتجر إلكتروني عربي: تحويل الأرقام العربية، وقراءة المبالغ التي يكتبها المستخدمون، وتوحيد النصوص
    للبحث، ومعرفة اتجاه النص. تعتمد على المكتبة القياسية فقط.

    ## `normalize_digits(s) -> str`
    يحوّل الأرقام العربية-الهندية `٠١٢٣٤٥٦٧٨٩` (من U+0660 إلى U+0669) والأرقام الفارسية `۰۱۲۳۴۵۶۷۸۹` (من U+06F0 إلى U+06F9)
    إلى الأرقام اللاتينية `0123456789`. باقي المحارف تبقى كما هي.

    ## `strip_bidi(s) -> str`
    يحذف محارف التحكم في الاتجاه: `U+200E` `U+200F` `U+061C` و`U+202A` إلى `U+202E` و`U+2066` إلى `U+2069`. باقي المحارف تبقى.

    ## `parse_amount(text) -> Decimal`
    يقرأ مبلغًا كتبه مستخدم. الخطوات بالترتيب: تحويل الأرقام بـ `normalize_digits`، حذف محارف الاتجاه بـ `strip_bidi`،
    حذف المسافات من الطرفين فقط، ثم استبدال علامة الناقص `−` (U+2212) بالشرطة `-`، وحذف فاصل الآلاف (`٬` U+066C وكذلك
    الفاصلة العادية `,`) أينما وُجد، وتحويل الفاصل العشري العربي `٫` (U+066B) إلى `.`. بعدها يجب أن يبقى بالضبط: إشارة
    اختيارية `+` أو `-`، ثم رقم واحد أو أكثر، ثم جزء كسري اختياري (`.` متبوعة برقم واحد أو أكثر). أي شيء آخر
    (مسافات داخل الرقم، إشارة بعد الرقم، فاصلان عشريان، نص فارغ، `٫٥` بلا جزء صحيح، `٥٫` بلا جزء كسري) هو `ValueError`.
    النتيجة `decimal.Decimal` دقيق، والإشارة `-` تعطي قيمة سالبة، و`+` لا تغيّر القيمة.

    ## `strip_diacritics(s) -> str`
    يحذف التشكيل: المحارف من `U+064B` إلى `U+0652` (فتحتان إلى سكون، وتشمل الشدة `U+0651`) وألف الخنجرية `U+0670`.
    لا يحذف التطويل `ـ` (U+0640).

    ## `search_key_ar(s) -> str`
    مفتاح للبحث لا يتأثر بالتشكيل ولا بأشكال الحروف المتقاربة. الخطوات بالترتيب:
    `normalize_digits`، ثم `strip_bidi`، ثم `strip_diacritics`، ثم حذف التطويل `ـ`، ثم استبدال الحروف:
    `أ إ آ ٱ` -> `ا`، و`ى` -> `ي`، و`ة` -> `ه`، و`ؤ` -> `و`، و`ئ` -> `ي`؛ ثم `str.casefold()`؛ ثم دمج المسافات المتتالية في مسافة
    واحدة وحذف مسافات الطرفين. مثال: `search_key_ar("مُحَمَّد")` هو `"محمد"` و`search_key_ar("إبراهيم")` هو `"ابراهيم"`.

    ## `is_rtl_text(s) -> bool`
    اتجاه النص حسب أول حرف «قوي» الاتجاه (قاعدة P2 في خوارزمية Unicode للاتجاه): ننظر إلى المحارف بالترتيب باستخدام
    `unicodedata.bidirectional`؛ أول محرف فئته `R` أو `AL` يعطي `True`، وأول محرف فئته `L` يعطي `False`، وتُتجاهل
    الأرقام والعلامات والمسافات (فئات أخرى). إن لم يوجد محرف قوي الاتجاه فالنتيجة `False`. محرف الاتجاه `U+200F` فئته `R` فيُحتسب.
''')

SRC = dd(r'''
    import re
    import unicodedata
    from decimal import Decimal

    _DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
    _BIDI_MARKS = "‎‏؜‪‫‬‭‮⁦⁧⁨⁩"
    _DROP_BIDI = str.maketrans("", "", _BIDI_MARKS)
    _DIACRITICS = set(chr(c) for c in range(0x064B, 0x0653)) | {"ٰ"}
    _LETTERS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})
    _AMOUNT = re.compile(r"([-+]?)([0-9]+)(?:\.([0-9]+))?")


    def normalize_digits(s: str) -> str:
        return s.translate(_DIGITS)


    def strip_bidi(s: str) -> str:
        return s.translate(_DROP_BIDI)


    def parse_amount(text: str) -> Decimal:
        t = strip_bidi(normalize_digits(text)).strip()
        t = t.replace("−", "-")
        t = t.replace("٬", "").replace(",", "").replace("٫", ".")
        m = _AMOUNT.fullmatch(t)
        if not m:
            raise ValueError("unreadable amount: %r" % (text,))
        value = Decimal(m.group(2) + ("." + m.group(3) if m.group(3) else ""))
        return -value if m.group(1) == "-" else value


    def strip_diacritics(s: str) -> str:
        return "".join(ch for ch in s if ch not in _DIACRITICS)


    def search_key_ar(s: str) -> str:
        s = strip_bidi(normalize_digits(s))
        s = strip_diacritics(s).replace("ـ", "")
        s = s.translate(_LETTERS).casefold()
        return " ".join(s.split())


    def is_rtl_text(s: str) -> bool:
        for ch in s:
            d = unicodedata.bidirectional(ch)
            if d in ("R", "AL"):
                return True
            if d == "L":
                return False
        return False
''')

VISIBLE = dd(r'''
    import unittest
    from decimal import Decimal

    from arnorm import normalize_digits, parse_amount, search_key_ar


    class الأساسيات(unittest.TestCase):
        def test_digits(self):
            self.assertEqual(normalize_digits("٢٠٢٥"), "2025")

        def test_amount(self):
            self.assertEqual(parse_amount("١٢٣"), Decimal("123"))

        def test_key(self):
            self.assertEqual(search_key_ar("كِتَابٌ"), "كتاب")


    if __name__ == "__main__":
        unittest.main()
''')

HIDDEN = dd(r'''
    import unittest
    from decimal import Decimal

    from arnorm import is_rtl_text, normalize_digits, parse_amount, search_key_ar, strip_bidi, strip_diacritics


    class Digits(unittest.TestCase):
        def test_arabic_indic(self):
            self.assertEqual(normalize_digits("٠١٢٣٤٥٦٧٨٩"), "0123456789")

        def test_persian(self):
            self.assertEqual(normalize_digits("۰۱۲۳۴۵۶۷۸۹"), "0123456789")

        def test_mixed_text(self):
            self.assertEqual(normalize_digits("رقم ٥٠ و ۶۰ و 70"), "رقم 50 و 60 و 70")
            self.assertEqual(normalize_digits(""), "")
            self.assertEqual(normalize_digits("abc ٫٬"), "abc ٫٬")

        def test_each_digit_separately(self):
            for i, ch in enumerate("٠١٢٣٤٥٦٧٨٩"):
                self.assertEqual(normalize_digits(ch), str(i))
            for i, ch in enumerate("۰۱۲۳۴۵۶۷۸۹"):
                self.assertEqual(normalize_digits(ch), str(i))


    class Bidi(unittest.TestCase):
        def test_marks(self):
            for mark in "‎‏؜‪‫‬‭‮⁦⁧⁨⁩":
                self.assertEqual(strip_bidi("a" + mark + "b"), "ab", hex(ord(mark)))

        def test_other_format_characters_stay(self):
            self.assertEqual(strip_bidi("a​b"), "a​b")
            self.assertEqual(strip_bidi("a‍b"), "a‍b")
            self.assertEqual(strip_bidi("a b"), "a b")
            self.assertEqual(strip_bidi("a⁥b"), "a⁥b")
            self.assertEqual(strip_bidi("a‪b"), "ab")

        def test_plain(self):
            self.assertEqual(strip_bidi("مرحبا"), "مرحبا")
            self.assertEqual(strip_bidi(""), "")


    class Amount(unittest.TestCase):
        def test_digits_and_separators(self):
            self.assertEqual(parse_amount("١٢٣٤٥"), Decimal("12345"))
            self.assertEqual(parse_amount("١٬٢٣٤٫٥٠"), Decimal("1234.50"))
            self.assertEqual(parse_amount("1,234.50"), Decimal("1234.50"))
            self.assertEqual(parse_amount("۱۲۳"), Decimal("123"))
            self.assertEqual(parse_amount("١٬٢٣٤٬٥٦٧"), Decimal("1234567"))
            self.assertEqual(parse_amount("٣٫١٤"), Decimal("3.14"))
            self.assertEqual(parse_amount("1,5"), Decimal("15"))
            self.assertEqual(parse_amount("0.10"), Decimal("0.10"))

        def test_exact_decimal(self):
            self.assertEqual(str(parse_amount("٠٫١٠")), "0.10")
            self.assertEqual(str(parse_amount("١٢٫٣٤٥٦٧٨٩٠١٢٣٤٥٦٧٨٩٠")), "12.34567890123456789" + "0")

        def test_signs(self):
            self.assertEqual(parse_amount("-١٢٣"), Decimal("-123"))
            self.assertEqual(parse_amount("−١٢٣٫٥"), Decimal("-123.5"))
            self.assertEqual(parse_amount("+٥"), Decimal("5"))
            self.assertEqual(parse_amount("-0"), Decimal("0"))

        def test_spaces_and_bidi_marks(self):
            self.assertEqual(parse_amount(" ١٢٣ "), Decimal("123"))
            self.assertEqual(parse_amount("\t١٢٣\n"), Decimal("123"))
            self.assertEqual(parse_amount("‏١٢٣‏"), Decimal("123"))
            self.assertEqual(parse_amount("‫-١٢٣‬"), Decimal("-123"))
            self.assertEqual(parse_amount("-‏١٢٣"), Decimal("-123"))
            self.assertEqual(parse_amount("؜-١٢٣"), Decimal("-123"))

        def test_unreadable(self):
            for t in ("", "   ", "١٢٣-", "١٫٢٫٣", "١٢٣ ٤٥", "٫٥", "٥٫", "abc", "١٢ ريال", "--٥", "+-٥", "٥+", ".", "١.٢٫٣",
                      "‏", "- ١٢٣", "١٢٣−", "١٬٫"):
                with self.assertRaises(ValueError, msg=repr(t)):
                    parse_amount(t)

        def test_separator_only_drops_thousands_marks(self):
            self.assertEqual(parse_amount("1٬0٬0"), Decimal("100"))
            self.assertEqual(parse_amount("١,٠٠٠"), Decimal("1000"))
            self.assertEqual(parse_amount("١,٠٠٠٫٥"), Decimal("1000.5"))


    class Diacritics(unittest.TestCase):
        def test_strip(self):
            self.assertEqual(strip_diacritics("مُحَمَّد"), "محمد")
            self.assertEqual(strip_diacritics("كِتَابٌ"), "كتاب")

        def test_each_mark_in_range(self):
            for code in range(0x064B, 0x0653):
                self.assertEqual(strip_diacritics("ب" + chr(code)), "ب", hex(code))
            self.assertEqual(strip_diacritics("بٰ"), "ب")

        def test_neighbours_stay(self):
            self.assertEqual(strip_diacritics("بي"), "بي")       # ي (U+064A) is a letter
            self.assertEqual(strip_diacritics("بٓ"), "بٓ")   # maddah above is not in the range
            self.assertEqual(strip_diacritics("بـب"), "بـب")  # tatweel stays
            self.assertEqual(strip_diacritics("بٱ"), "بٱ")   # alef wasla stays

        def test_plain(self):
            self.assertEqual(strip_diacritics("abc ١٢٣"), "abc ١٢٣")
            self.assertEqual(strip_diacritics(""), "")


    class SearchKey(unittest.TestCase):
        def test_examples(self):
            self.assertEqual(search_key_ar("مُحَمَّد"), "محمد")
            self.assertEqual(search_key_ar("إبراهيم"), "ابراهيم")
            self.assertEqual(search_key_ar("أحمد"), "احمد")
            self.assertEqual(search_key_ar("آمنة"), "امنه")

        def test_alef_variants(self):
            for ch in "أإآٱ":
                self.assertEqual(search_key_ar(ch + "ب"), "اب", ch)

        def test_yeh_and_teh_marbuta(self):
            self.assertEqual(search_key_ar("على"), "علي")
            self.assertEqual(search_key_ar("مدرسة"), "مدرسه")
            self.assertEqual(search_key_ar("ئ"), "ي")
            self.assertEqual(search_key_ar("رئيس"), "رييس")

        def test_hamza_on_waw(self):
            self.assertEqual(search_key_ar("مؤمن"), "مومن")

        def test_hamza_alone_stays(self):
            self.assertEqual(search_key_ar("قِرَاءَة"), "قراءه")
            self.assertEqual(search_key_ar("ء"), "ء")

        def test_tatweel(self):
            self.assertEqual(search_key_ar("مـحـمـد"), "محمد")
            self.assertEqual(search_key_ar("ـــ"), "")

        def test_digits_case_spaces(self):
            self.assertEqual(search_key_ar("١٢٣ ABC  xyz"), "123 abc xyz")
            self.assertEqual(search_key_ar("  كتاب\t\nجديد  "), "كتاب جديد")
            self.assertEqual(search_key_ar("Straße"), "strasse")

        def test_bidi_marks(self):
            self.assertEqual(search_key_ar("‏مرحبا‏"), "مرحبا")
            self.assertEqual(search_key_ar("a‫b"), "ab")

        def test_equal_keys_for_variants(self):
            self.assertEqual(search_key_ar("كِتَابٌ"), search_key_ar("كتاب"))
            self.assertEqual(search_key_ar("الإسلام"), search_key_ar("الاسلام"))

        def test_empty(self):
            self.assertEqual(search_key_ar(""), "")
            self.assertEqual(search_key_ar("   "), "")


    class Direction(unittest.TestCase):
        def test_rtl(self):
            self.assertTrue(is_rtl_text("مرحبا"))
            self.assertTrue(is_rtl_text("שלום"))
            self.assertTrue(is_rtl_text("123 مرحبا"))
            self.assertTrue(is_rtl_text("  : مرحبا abc"))
            self.assertTrue(is_rtl_text("‏abc"))
            self.assertTrue(is_rtl_text("١٢٣ مرحبا"))

        def test_ltr(self):
            self.assertFalse(is_rtl_text("hello"))
            self.assertFalse(is_rtl_text("abc مرحبا"))
            self.assertFalse(is_rtl_text("١٢٣ abc"))
            self.assertFalse(is_rtl_text("‎مرحبا"))

        def test_no_strong_character(self):
            for s in ("", "123", "!?", " ", "١٢٣", "٫٬"):
                self.assertFalse(is_rtl_text(s), repr(s))


    if __name__ == "__main__":
        unittest.main()
''')

LIB = Lib(
    name="arnorm", lang="python", title="`arnorm`",
    blurb="متجر إلكتروني عربي يستخدم هذه الأدوات لقراءة المبالغ التي يكتبها العملاء ولتوحيد نصوص البحث.",
    files={"arnorm/__init__.py": "from .core import *  # noqa: F401,F403\n", "arnorm/core.py": SRC,
           "README.md": README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_asasiyat.py": VISIBLE},
    hidden_tests={"tests/test_kamila.py": HIDDEN},
    mutate=["arnorm/core.py"], difficulty=3, tags=["unicode", "arabic", "bidi", "text"],
    probes=[
        'normalize_digits("رقم ٥٠ و ۶۰")',
        'strip_bidi("a\\u202ab")',
        'parse_amount("١٬٢٣٤٫٥٠")',
        'parse_amount("−١٢٣٫٥")',
        'parse_amount("\\u200f١٢٣\\u200f")',
        'parse_amount("١٢٣-")',
        'strip_diacritics("مُحَمَّد")',
        'strip_diacritics("ب\\u0653")',
        'search_key_ar("إبراهيم")',
        'search_key_ar("مدرسة")',
        'search_key_ar("مؤمن")',
        'search_key_ar("مـحـمـد")',
        'is_rtl_text("123 مرحبا")',
        'is_rtl_text("abc مرحبا")',
        'is_rtl_text("١٢٣ abc")',
    ],
    probe_import="from arnorm import *",
)

register_native(LIB, "ar", "fix-arnorm", n=9,
                summary="native: injected bugs in an Arabic digit/amount/search-key/direction library, reports in Arabic")
