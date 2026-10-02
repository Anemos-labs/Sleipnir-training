"""Native bug-fix family in Hindi: Indian rupee grouping, parsing, Devanagari digits and amounts in words (python)."""
from fx import Lib, dd

from ._native import register_native

README = dd('''
    # inrfmt

    एक छोटे ऑनलाइन स्टोर के बिलिंग मॉड्यूल के लिए रुपये की राशि से जुड़े सहायक फ़ंक्शन: भारतीय अंक-समूहन (lakh/crore) में
    फ़ॉर्मेट करना, लिखी हुई राशि को पढ़ना, देवनागरी अंक बदलना और चेक पर लिखने के लिए अंग्रेज़ी शब्दों में राशि। केवल
    मानक लाइब्रेरी।

    ## `format_inr(amount, decimals=2, symbol=True) -> str`
    `amount` (`int`, `float`, `Decimal` या `str`) को भारतीय समूहन में लिखता है: दाईं ओर के **तीन** अंक एक समूह में, उसके बाद
    **दो-दो** अंकों के समूह, कॉमा से अलग (`1234567` -> `12,34,567`, `123456789` -> `12,34,56,789`; `999` में कोई कॉमा
    नहीं, `12345` -> `12,345`)।

    * राशि को `decimals` दशमलव स्थानों तक `decimal.Decimal(str(amount))` से "आधा ऊपर" (ROUND_HALF_UP, निरपेक्ष मान पर) गोल
      किया जाता है: `0.005` -> `0.01`, `2.675` -> `2.68`; `decimals=0` पर `0.5` -> `1`, `-1234.5` -> `-1,235`।
      `decimals=0` में दशमलव बिंदु नहीं लिखा जाता। `decimals < 0` पर `ValueError`।
    * `symbol=True` में अंकों के ठीक पहले ₹ (U+20B9) आता है, बीच में कोई खाली जगह नहीं; `symbol=False` में नहीं।
    * ऋणात्मक राशि के आगे ASCII `-` आता है, चिह्न (₹) से भी पहले: `-₹1,234.50`। अगर गोल करने के बाद शून्य बचे तो `-` नहीं
      लिखा जाता (`-0.004` -> `₹0.00`)।

    ## `parse_inr(text) -> Decimal`
    लिखी हुई राशि को `Decimal` में बदलता है। पहले देवनागरी अंक (`०`–`९`) ASCII में बदले जाते हैं, फिर आगे-पीछे की खाली जगह
    हटती है। स्वीकार किया जाने वाला रूप: वैकल्पिक `-`, वैकल्पिक उपसर्ग `₹`, `Rs`, `Rs.` या `INR` (अंग्रेज़ी अक्षर छोटे-बड़े कुछ भी),
    उपसर्ग के बाद खाली जगह चल सकती है, उपसर्ग के बाद भी एक वैकल्पिक `-` (`₹-1,234`), फिर अंक और कॉमा (कॉमा कहीं भी हो सकते हैं
    और बस हटा दिए जाते हैं), वैकल्पिक दशमलव भाग (`.5` ठीक है, `5.` ठीक नहीं), और अंत में वैकल्पिक `/-`। `-` चिह्न दोनों जगह
    एक साथ नहीं हो सकता (`--5` गलत)। कोई अंक न हो, या कुछ और बचे (`"1 000"`, `"abc"`, `""`), तो `ValueError`।

    ## `to_devanagari(s) -> str` और `from_devanagari(s) -> str`
    `to_devanagari` ASCII अंकों `0`–`9` को देवनागरी `०`–`९` में बदलता है और बाकी अक्षरों को वैसे ही रहने देता है;
    `from_devanagari` उल्टा करता है।

    ## `rupees_in_words(amount) -> str`
    चेक पर लिखने वाला अंग्रेज़ी शब्द-रूप, भारतीय इकाइयों (`Crore` = 10^7, `Lakh` = 10^5, `Thousand`) के साथ, हर शब्द बड़े
    अक्षर से शुरू और अंत में `Only`। `amount` ऋणात्मक हो तो `ValueError`।

    * राशि पहले निकटतम पैसे तक (ROUND_HALF_UP) गोल होती है; फिर रुपये और पैसे अलग किए जाते हैं।
    * हर समूह का नाम: `Crore` से पहले की संख्या 1–999 हो सकती है (`One Hundred Twenty Three Crore`), `Lakh` और `Thousand` से पहले
      1–99, बाकी बचा हिस्सा 1–999। शून्य वाले समूह छोड़ दिए जाते हैं। सैकड़े के लिए `Hundred`; बीस से ऊपर दहाई और इकाई के बीच
      खाली जगह (`Thirty Four`), कोई `And` या `-` नहीं।
    * रुपये 1 हो तो `Rupee`, नहीं तो `Rupees`। पैसे 1 हो तो `Paisa`, नहीं तो `Paise`। दोनों हों तो रुपये के बाद ` And ` और फिर पैसे
      (`One Rupee And One Paisa Only`); केवल पैसे हों तो `Fifty Paise Only`; दोनों शून्य हों तो `Zero Rupees Only`।
    * `10**10` रुपये या उससे ऊपर (1000 Crore या ज़्यादा) पर `ValueError`।
''')

SRC = dd(r'''
    import re
    from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

    RUPEE = "₹"
    _DEV = "०१२३४५६७८९"
    _TO_DEV = str.maketrans("0123456789", _DEV)
    _FROM_DEV = str.maketrans(_DEV, "0123456789")
    _ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen",
             "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
    _TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
    _PARSE = re.compile(r"\s*(-?)\s*(?:(?:₹|rs\.?|inr)\s*)?(-?)\s*([0-9,]+(?:\.[0-9]+)?|\.[0-9]+)\s*(?:/-)?\s*", re.I)


    def _group_indian(digits: str) -> str:
        if len(digits) <= 3:
            return digits
        head, tail = digits[:-3], digits[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        return ",".join(parts + [tail])


    def format_inr(amount, decimals: int = 2, symbol: bool = True) -> str:
        if decimals < 0:
            raise ValueError("decimals must not be negative")
        d = Decimal(str(amount))
        q = abs(d).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
        whole, _, frac = format(q, "f").partition(".")
        out = _group_indian(whole) + ("." + frac if frac else "")
        neg = d < 0 and q != 0
        return ("-" if neg else "") + (RUPEE if symbol else "") + out


    def parse_inr(text: str) -> Decimal:
        m = _PARSE.fullmatch(text.translate(_FROM_DEV))
        if not m or (m.group(1) and m.group(2)):
            raise ValueError("unreadable amount: %r" % (text,))
        body = m.group(3).replace(",", "")
        if not body or body == ".":
            raise ValueError("unreadable amount: %r" % (text,))
        try:
            value = Decimal(body)
        except InvalidOperation:
            raise ValueError("unreadable amount: %r" % (text,))
        return -value if (m.group(1) or m.group(2)) else value


    def to_devanagari(s: str) -> str:
        return s.translate(_TO_DEV)


    def from_devanagari(s: str) -> str:
        return s.translate(_FROM_DEV)


    def _words_below_1000(n: int) -> str:
        out = []
        if n >= 100:
            out.append(_ONES[n // 100] + " Hundred")
            n %= 100
        if n >= 20:
            out.append(_TENS[n // 10] + ((" " + _ONES[n % 10]) if n % 10 else ""))
        elif n:
            out.append(_ONES[n])
        return " ".join(out)


    def rupees_in_words(amount) -> str:
        d = Decimal(str(amount))
        if d < 0:
            raise ValueError("negative amount")
        total_paise = int((d * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
        rupees, paise = divmod(total_paise, 100)
        if rupees >= 10 ** 10:
            raise ValueError("amount too large")
        parts = []
        crore, rest = divmod(rupees, 10 ** 7)
        lakh, rest = divmod(rest, 10 ** 5)
        thousand, rest = divmod(rest, 1000)
        if crore:
            parts.append(_words_below_1000(crore) + " Crore")
        if lakh:
            parts.append(_words_below_1000(lakh) + " Lakh")
        if thousand:
            parts.append(_words_below_1000(thousand) + " Thousand")
        if rest:
            parts.append(_words_below_1000(rest))
        text = ""
        if rupees:
            text = " ".join(parts) + (" Rupee" if rupees == 1 else " Rupees")
        if paise:
            paise_text = _words_below_1000(paise) + (" Paisa" if paise == 1 else " Paise")
            text = (text + " And " + paise_text) if text else paise_text
        if not text:
            text = "Zero Rupees"
        return text + " Only"
''')

VISIBLE = dd(r'''
    import unittest
    from decimal import Decimal

    from inrfmt import format_inr, parse_inr, rupees_in_words


    class बुनियादी(unittest.TestCase):
        def test_format(self):
            self.assertEqual(format_inr(1234567), "₹12,34,567.00")

        def test_parse(self):
            self.assertEqual(parse_inr("Rs. 1,00,000"), Decimal("100000"))

        def test_words(self):
            self.assertEqual(rupees_in_words(100), "One Hundred Rupees Only")


    if __name__ == "__main__":
        unittest.main()
''')

HIDDEN = dd(r'''
    import unittest
    from decimal import Decimal

    from inrfmt import format_inr, from_devanagari, parse_inr, rupees_in_words, to_devanagari

    R = "₹"


    class Format(unittest.TestCase):
        def test_grouping(self):
            cases = {0: "0.00", 5: "5.00", 999: "999.00", 1000: "1,000.00", 1234: "1,234.00", 12345: "12,345.00",
                     123456: "1,23,456.00", 1234567: "12,34,567.00", 12345678: "1,23,45,678.00",
                     123456789: "12,34,56,789.00", 1234567890: "1,23,45,67,890.00", 10 ** 9: "1,00,00,00,000.00",
                     100000: "1,00,000.00", 99999: "99,999.00", 10000000: "1,00,00,000.00"}
            for n, text in cases.items():
                self.assertEqual(format_inr(n), R + text, n)

        def test_no_symbol(self):
            self.assertEqual(format_inr(1234567.5, symbol=False), "12,34,567.50")
            self.assertEqual(format_inr(-5, symbol=False), "-5.00")
            self.assertEqual(format_inr(0, 0, False), "0")

        def test_decimals(self):
            self.assertEqual(format_inr(1234567.5), R + "12,34,567.50")
            self.assertEqual(format_inr(1234567.5, 0), R + "12,34,568")
            self.assertEqual(format_inr(1234567.5, 3), R + "12,34,567.500")
            self.assertEqual(format_inr(1, 1), R + "1.0")
            self.assertEqual(format_inr(12345, 0), R + "12,345")

        def test_rounding_half_up(self):
            self.assertEqual(format_inr(0.005), R + "0.01")
            self.assertEqual(format_inr(0.004), R + "0.00")
            self.assertEqual(format_inr(1.005), R + "1.01")
            self.assertEqual(format_inr(2.675), R + "2.68")
            self.assertEqual(format_inr(0.5, 0), R + "1")
            self.assertEqual(format_inr(2.5, 0), R + "3")
            self.assertEqual(format_inr(99999999.995), R + "10,00,00,000.00")
            self.assertEqual(format_inr("2.675"), R + "2.68")
            self.assertEqual(format_inr(Decimal("1234.565")), R + "1,234.57")

        def test_negative(self):
            self.assertEqual(format_inr(-1234.5), "-" + R + "1,234.50")
            self.assertEqual(format_inr(-1234.5, 0), "-" + R + "1,235")
            self.assertEqual(format_inr(-1234567), "-" + R + "12,34,567.00")
            self.assertEqual(format_inr(-999), "-" + R + "999.00")

        def test_negative_zero(self):
            self.assertEqual(format_inr(-0.004), R + "0.00")
            self.assertEqual(format_inr(-0.4, 0), R + "0")
            self.assertEqual(format_inr(0), R + "0.00")
            self.assertEqual(format_inr(-0.005), "-" + R + "0.01")

        def test_bad_decimals(self):
            with self.assertRaises(ValueError):
                format_inr(5, -1)


    class Parse(unittest.TestCase):
        def test_prefixes(self):
            self.assertEqual(parse_inr("₹ 12,34,567.50"), Decimal("1234567.50"))
            self.assertEqual(parse_inr("₹1,234"), Decimal("1234"))
            self.assertEqual(parse_inr("Rs. 1,00,000"), Decimal("100000"))
            self.assertEqual(parse_inr("Rs 5,000"), Decimal("5000"))
            self.assertEqual(parse_inr("rs.5"), Decimal("5"))
            self.assertEqual(parse_inr("INR 5000"), Decimal("5000"))
            self.assertEqual(parse_inr("inr5000"), Decimal("5000"))
            self.assertEqual(parse_inr("1234"), Decimal("1234"))

        def test_suffix_and_spaces(self):
            self.assertEqual(parse_inr("rs 5,000/-"), Decimal("5000"))
            self.assertEqual(parse_inr("5000/-"), Decimal("5000"))
            self.assertEqual(parse_inr("  42  "), Decimal("42"))
            self.assertEqual(parse_inr("\t₹ 7 /- "), Decimal("7"))

        def test_negative(self):
            self.assertEqual(parse_inr("-₹1,234"), Decimal("-1234"))
            self.assertEqual(parse_inr("₹-1,234"), Decimal("-1234"))
            self.assertEqual(parse_inr("- ₹ 99.5"), Decimal("-99.5"))
            self.assertEqual(parse_inr("-5"), Decimal("-5"))
            self.assertEqual(parse_inr("Rs.-5"), Decimal("-5"))

        def test_double_minus(self):
            for t in ("--5", "-₹-5", "- Rs -5"):
                with self.assertRaises(ValueError, msg=t):
                    parse_inr(t)

        def test_devanagari_digits(self):
            self.assertEqual(parse_inr("१२,३४५"), Decimal("12345"))
            self.assertEqual(parse_inr("₹१२३.५०"), Decimal("123.50"))

        def test_commas_anywhere(self):
            self.assertEqual(parse_inr("₹1,2,3"), Decimal("123"))
            self.assertEqual(parse_inr("1,234,567"), Decimal("1234567"))
            self.assertEqual(parse_inr("12,34,567.5"), Decimal("1234567.5"))

        def test_fraction_forms(self):
            self.assertEqual(parse_inr(".5"), Decimal("0.5"))
            self.assertEqual(parse_inr("0.50"), Decimal("0.50"))
            for t in ("5.", "1.2.3", "."):
                with self.assertRaises(ValueError, msg=t):
                    parse_inr(t)

        def test_result_is_decimal_exact(self):
            self.assertEqual(str(parse_inr("0.10")), "0.10")
            self.assertIsInstance(parse_inr("1"), Decimal)

        def test_unreadable(self):
            for t in ("", "   ", "₹", "Rs.", "abc", "1 000", "₹ 1 000", "12a", "$5", "5 rupees", "Rs. Rs. 5", "5/-/-",
                      ",", ",5x"):
                with self.assertRaises(ValueError, msg=repr(t)):
                    parse_inr(t)


    class Digits(unittest.TestCase):
        def test_to(self):
            self.assertEqual(to_devanagari("0123456789"), "०१२३४५६७८९")
            self.assertEqual(to_devanagari("Rs. 1,234.50"), "Rs. १,२३४.५०")
            self.assertEqual(to_devanagari("abc"), "abc")
            self.assertEqual(to_devanagari(""), "")

        def test_from(self):
            self.assertEqual(from_devanagari("०१२३४५६७८९"), "0123456789")
            self.assertEqual(from_devanagari("₹१२,३४५"), "₹12,345")
            self.assertEqual(from_devanagari("123 abc"), "123 abc")

        def test_round_trip(self):
            self.assertEqual(from_devanagari(to_devanagari("2024-06-01 9.50")), "2024-06-01 9.50")


    class Words(unittest.TestCase):
        def test_small(self):
            cases = {0: "Zero Rupees Only", 1: "One Rupee Only", 2: "Two Rupees Only", 15: "Fifteen Rupees Only",
                     20: "Twenty Rupees Only", 21: "Twenty One Rupees Only", 99: "Ninety Nine Rupees Only",
                     100: "One Hundred Rupees Only", 101: "One Hundred One Rupees Only", 119: "One Hundred Nineteen Rupees Only",
                     999: "Nine Hundred Ninety Nine Rupees Only"}
            for n, text in cases.items():
                self.assertEqual(rupees_in_words(n), text, n)

        def test_units(self):
            cases = {1000: "One Thousand Rupees Only", 12345: "Twelve Thousand Three Hundred Forty Five Rupees Only",
                     100000: "One Lakh Rupees Only", 123456: "One Lakh Twenty Three Thousand Four Hundred Fifty Six Rupees Only",
                     1234567: "Twelve Lakh Thirty Four Thousand Five Hundred Sixty Seven Rupees Only",
                     10000000: "One Crore Rupees Only",
                     12345678: "One Crore Twenty Three Lakh Forty Five Thousand Six Hundred Seventy Eight Rupees Only",
                     123456789: "Twelve Crore Thirty Four Lakh Fifty Six Thousand Seven Hundred Eighty Nine Rupees Only",
                     1234567890: "One Hundred Twenty Three Crore Forty Five Lakh Sixty Seven Thousand Eight Hundred Ninety Rupees Only",
                     9999999999: "Nine Hundred Ninety Nine Crore Ninety Nine Lakh Ninety Nine Thousand Nine Hundred Ninety Nine Rupees Only"}
            for n, text in cases.items():
                self.assertEqual(rupees_in_words(n), text, n)

        def test_zero_groups_skipped(self):
            self.assertEqual(rupees_in_words(1000005), "Ten Lakh Five Rupees Only")
            self.assertEqual(rupees_in_words(10000001), "One Crore One Rupees Only")
            self.assertEqual(rupees_in_words(20000000), "Two Crore Rupees Only")
            self.assertEqual(rupees_in_words(100100), "One Lakh One Hundred Rupees Only")
            self.assertEqual(rupees_in_words(1010000), "Ten Lakh Ten Thousand Rupees Only")

        def test_paise(self):
            self.assertEqual(rupees_in_words(0.5), "Fifty Paise Only")
            self.assertEqual(rupees_in_words(0.01), "One Paisa Only")
            self.assertEqual(rupees_in_words(1.01), "One Rupee And One Paisa Only")
            self.assertEqual(rupees_in_words(25.5), "Twenty Five Rupees And Fifty Paise Only")
            self.assertEqual(rupees_in_words("1234.5"), "One Thousand Two Hundred Thirty Four Rupees And Fifty Paise Only")
            self.assertEqual(rupees_in_words(1000000.01), "Ten Lakh Rupees And One Paisa Only")
            self.assertEqual(rupees_in_words(9999999999.99),
                             "Nine Hundred Ninety Nine Crore Ninety Nine Lakh Ninety Nine Thousand Nine Hundred Ninety Nine Rupees And Ninety Nine Paise Only")
            self.assertEqual(rupees_in_words(0.99), "Ninety Nine Paise Only")
            self.assertEqual(rupees_in_words(2.02), "Two Rupees And Two Paise Only")

        def test_rounding_to_paisa(self):
            self.assertEqual(rupees_in_words(0.995), "One Rupee Only")
            self.assertEqual(rupees_in_words(0.004), "Zero Rupees Only")
            self.assertEqual(rupees_in_words(0.005), "One Paisa Only")
            self.assertEqual(rupees_in_words(10.125), "Ten Rupees And Thirteen Paise Only")
            self.assertEqual(rupees_in_words(10.124), "Ten Rupees And Twelve Paise Only")

        def test_limits(self):
            for bad in (-1, -0.01, 10 ** 10, 10 ** 10 + 1, 9999999999.999):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    rupees_in_words(bad)


    if __name__ == "__main__":
        unittest.main()
''')

LIB = Lib(
    name="inrfmt", lang="python", title="`inrfmt`",
    blurb="एक ऑनलाइन स्टोर का बिलिंग मॉड्यूल इन फ़ंक्शनों से रुपये की राशि लिखता, पढ़ता और चेक के लिए शब्दों में बदलता है।",
    files={"inrfmt/__init__.py": "from .core import *  # noqa: F401,F403\n", "inrfmt/core.py": SRC,
           "README.md": README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_buniyadi.py": VISIBLE},
    hidden_tests={"tests/test_poora.py": HIDDEN},
    mutate=["inrfmt/core.py"], difficulty=3, tags=["i18n", "money", "formatting", "devanagari"],
    probes=[
        'format_inr(1234567)',
        'format_inr(123456789)',
        'format_inr(1234567.5, 0)',
        'format_inr(2.675)',
        'format_inr(-1234.5)',
        'format_inr(-0.004)',
        'parse_inr("Rs. 1,00,000")',
        'parse_inr("₹-1,234")',
        'parse_inr("१२,३४५")',
        'parse_inr("5.")',
        'to_devanagari("Rs. 1,234.50")',
        'rupees_in_words(1234567)',
        'rupees_in_words(1000005)',
        'rupees_in_words(1.01)',
        'rupees_in_words(0.995)',
    ],
    probe_import="from inrfmt import *",
)

register_native(LIB, "hi", "fix-inrfmt", n=9,
                summary="native: injected bugs in a Hindi-documented rupee formatting/parsing library, reports in Hindi")
