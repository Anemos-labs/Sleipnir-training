"""Text-format libraries (python), batch: invented-country formats."""
from fx import Lib, dd, register_libs

# ======================================================================================================================
# veldoria: national id, phone and postal code formats of the invented country of Veldoria
# ======================================================================================================================

VEL_README = dd(r'''
    # veldoria

    Format helpers for the (fictional) Republic of Veldoria, used by the registration forms. Package `veldoria` with three
    modules: `ids`, `phone` and `post`. Every function raises `ValueError` for input that breaks its rules.

    ## `veldoria.ids`
    A *citizen number* has 10 digits `YYMMDD R SS C`:
    * `YYMMDD` birth date; `R` the *registry digit* `1`-`8`; `SS` a serial `00`-`99`; `C` the check digit.
    * The century comes from `R`: `1`,`2` are 1800-1899, `3`,`4` 1900-1999, `5`,`6` 2000-2099, `7`,`8` 2100-2199. An odd `R` means
      registry `"north"`, an even one `"south"`. `R` of `0` or `9` is invalid.
    * Check digit: the first nine digits times the weights `3 1 4 1 5 9 2 6 5`, summed, modulo 7.
    * Written as `YYMMDD-RSS-C` (for example `870314-352-2` when the check works out); when reading, the dashes are
      optional, but when present they must be exactly at those two places. Surrounding whitespace is ignored.

    ### `check_digit(first9) -> int`
    For a string of nine digits. Anything else is a `ValueError`.

    ### `parse_id(text, today=None) -> VeldId`
    `VeldId` is a `namedtuple` `(birth, registry, serial, check)` (`birth` a `datetime.date`, `registry` `"north"`/`"south"`,
    `serial` and `check` ints). Validates the shape, the registry digit, the check digit and that the birth date exists. If `today` (a
    `date`) is given, a birth date after `today` is invalid (born today is fine).

    ### `make_id(birth, registry, serial) -> str`
    The formatted number for a `date` between 1800-01-01 and 2199-12-31, `registry` `"north"` or `"south"`, `serial` 0-99. Result
    always parses back to the same fields.

    ### `age_on(birth, day) -> int`
    Completed years of age on `day`. A birthday on 29 February is celebrated on 1 March in years that have no 29 February.
    `day` before `birth` is a `ValueError`.

    ## `veldoria.phone`
    Numbers have the country code `999`. The national significant number (NSN) decides the kind: **mobile** = 9 digits starting
    with `7`; **landline** = 8 digits starting with `2`-`6`; **toll-free** = 8 digits starting with `800`.

    ### `parse_phone(text) -> Phone`
    `Phone` is a `namedtuple` `(kind, nsn)` with kind `"mobile"`, `"landline"` or `"toll-free"`. The text may contain spaces, `-`, `.`, `(`
    and `)` anywhere; they are removed. What is left must be digits with an optional leading `+`. The prefix decides the NSN:
    `+999...` or `00999...` (the rest is the NSN), or a trunk `0` (the rest after that `0` is the NSN). Text without one of those
    prefixes, other country codes and NSNs of no kind are a `ValueError`.

    ### `format_phone(text, style="e164") -> str`
    Parses and writes the number. `style` `"e164"`: `+999` + NSN. `"national"` and `"international"` group digits, separated by single
    spaces, according to the kind:

    | kind | national (`0` + NSN) groups | international (`+999 ` + NSN) groups |
    |---|---|---|
    | mobile | 4 3 3 | 3 3 3 |
    | landline | 3 3 3 | 2 3 3 |
    | toll-free | 4 5 | 3 5 |
    Any other style is a `ValueError`.

    ## `veldoria.post`
    ### `normalize_postcode(text) -> str`
    A postal code is four digits (the first not `0`) and two letters, possibly separated by spaces or one or more dashes, in any
    letter case, with leading and trailing whitespace ignored. The letters must come from `ABCDEFGHJKLMNPRSTUVWXYZ` (no `I`, `O`,
    `Q`). The result is written `NNNN-LL` in capitals.

    ### `postcode_region(text) -> str`
    The region of the normalized code by its first digit: `1` North, `2` Harbour, `3` Highlands, `4` Midlands, `5` Lakes, `6` Coast,
    `7` Capital, `8` Islands, `9` Offshore. Input is validated with `normalize_postcode`.

    ### `format_address(name, street, number, postcode, city, unit=None) -> list[str]`
    Three lines: `name` (stripped); `street number` or, when `unit` is given, `street number/unit`; `NNNN-LL CITY` with the
    normalized postcode and the city in capitals. `number` is an int or str; `name`, `street` and `city` must not be blank after
    stripping (else `ValueError`); a `unit` that is blank counts as no unit.
''')

VEL_IDS = dd(r'''
    """Veldorian citizen numbers."""
    import re
    from collections import namedtuple
    from datetime import date

    VeldId = namedtuple("VeldId", "birth registry serial check")

    _WEIGHTS = (3, 1, 4, 1, 5, 9, 2, 6, 5)
    _SHAPE = re.compile(r"(\d{6})(-?)(\d{3})(-?)(\d)")


    def check_digit(first9):
        if not re.fullmatch(r"\d{9}", first9):
            raise ValueError("need exactly nine digits")
        return sum(int(d) * w for d, w in zip(first9, _WEIGHTS)) % 7


    def parse_id(text, today=None):
        m = _SHAPE.fullmatch(text.strip())
        if not m:
            raise ValueError("bad citizen number: %r" % text)
        if bool(m.group(2)) != bool(m.group(4)):
            raise ValueError("dashes must be used in both places or in none")
        digits = m.group(1) + m.group(3) + m.group(5)
        era = int(digits[6])
        if not 1 <= era <= 8:
            raise ValueError("bad registry digit")
        if check_digit(digits[:9]) != int(digits[9]):
            raise ValueError("check digit does not match")
        year = 1800 + 100 * ((era - 1) // 2) + int(digits[0:2])
        birth = date(year, int(digits[2:4]), int(digits[4:6]))
        if today is not None and birth > today:
            raise ValueError("born in the future")
        return VeldId(birth, "north" if era % 2 == 1 else "south", int(digits[7:9]), int(digits[9]))


    def make_id(birth, registry, serial):
        if not date(1800, 1, 1) <= birth <= date(2199, 12, 31):
            raise ValueError("birth date outside 1800..2199")
        if registry not in ("north", "south"):
            raise ValueError("bad registry")
        if not 0 <= serial <= 99:
            raise ValueError("serial must be 0..99")
        era = 2 * ((birth.year - 1800) // 100) + (1 if registry == "north" else 2)
        body = "%02d%02d%02d%d%02d" % (birth.year % 100, birth.month, birth.day, era, serial)
        return "%s-%s-%d" % (body[:6], body[6:], check_digit(body))


    def age_on(birth, day):
        if day < birth:
            raise ValueError("day is before the birth date")
        years = day.year - birth.year
        if birth.month == 2 and birth.day == 29:
            try:
                birthday = date(day.year, 2, 29)
            except ValueError:
                birthday = date(day.year, 3, 1)
        else:
            birthday = date(day.year, birth.month, birth.day)
        return years - 1 if day < birthday else years
''')

VEL_PHONE = dd(r'''
    """Veldorian phone numbers."""
    import re
    from collections import namedtuple

    Phone = namedtuple("Phone", "kind nsn")

    _GROUPS = {
        ("mobile", "national"): (4, 3, 3),
        ("mobile", "international"): (3, 3, 3),
        ("landline", "national"): (3, 3, 3),
        ("landline", "international"): (2, 3, 3),
        ("toll-free", "national"): (4, 5),
        ("toll-free", "international"): (3, 5),
    }


    def _kind(nsn):
        if len(nsn) == 9 and nsn[0] == "7":
            return "mobile"
        if len(nsn) == 8 and nsn[0] in "23456":
            return "landline"
        if len(nsn) == 8 and nsn.startswith("800"):
            return "toll-free"
        raise ValueError("not a Veldorian number: %r" % nsn)


    def parse_phone(text):
        cleaned = re.sub(r"[ \-.()]", "", text)
        if not re.fullmatch(r"\+?\d+", cleaned):
            raise ValueError("bad characters in phone number: %r" % text)
        if cleaned.startswith("+999"):
            nsn = cleaned[4:]
        elif cleaned.startswith("00999"):
            nsn = cleaned[5:]
        elif cleaned.startswith("0") and not cleaned.startswith("00"):
            nsn = cleaned[1:]
        else:
            raise ValueError("unsupported prefix: %r" % text)
        return Phone(_kind(nsn), nsn)


    def _group(digits, sizes):
        out = []
        pos = 0
        for size in sizes:
            out.append(digits[pos:pos + size])
            pos += size
        return " ".join(out)


    def format_phone(text, style="e164"):
        p = parse_phone(text)
        if style == "e164":
            return "+999" + p.nsn
        if style == "national":
            return _group("0" + p.nsn, _GROUPS[(p.kind, style)])
        if style == "international":
            return "+999 " + _group(p.nsn, _GROUPS[(p.kind, style)])
        raise ValueError("unknown style: %r" % (style,))
''')

VEL_POST = dd(r'''
    """Veldorian postal codes and addresses."""
    import re

    _LETTERS = "ABCDEFGHJKLMNPRSTUVWXYZ"
    _REGIONS = {"1": "North", "2": "Harbour", "3": "Highlands", "4": "Midlands", "5": "Lakes", "6": "Coast", "7": "Capital",
                "8": "Islands", "9": "Offshore"}


    def normalize_postcode(text):
        m = re.fullmatch(r"([1-9][0-9]{3})[ \t-]*([A-Za-z]{2})", text.strip())
        if not m:
            raise ValueError("bad postal code: %r" % text)
        letters = m.group(2).upper()
        if any(c not in _LETTERS for c in letters):
            raise ValueError("letter not allowed in postal code: %r" % text)
        return "%s-%s" % (m.group(1), letters)


    def postcode_region(text):
        return _REGIONS[normalize_postcode(text)[0]]


    def format_address(name, street, number, postcode, city, unit=None):
        name, street, city = name.strip(), street.strip(), city.strip()
        if not name or not street or not city:
            raise ValueError("name, street and city are required")
        line2 = "%s %s" % (street, number)
        if unit is not None and str(unit).strip():
            line2 += "/%s" % str(unit).strip()
        return [name, line2, "%s %s" % (normalize_postcode(postcode), city.upper())]
''')

VEL_INIT = ""

VEL_VISIBLE = dd(r'''
    import unittest
    from datetime import date

    from veldoria.ids import check_digit, make_id
    from veldoria.phone import format_phone
    from veldoria.post import normalize_postcode


    class BasicTests(unittest.TestCase):
        def test_check_digit(self):
            self.assertEqual(check_digit("870314352"), 2)

        def test_make_id(self):
            self.assertEqual(make_id(date(1987, 3, 14), "north", 52), "870314-352-2")

        def test_phone(self):
            self.assertEqual(format_phone("+999 712 345 678"), "+999712345678")

        def test_postcode(self):
            self.assertEqual(normalize_postcode("1234 ab"), "1234-AB")


    if __name__ == "__main__":
        unittest.main()
''')

VEL_HIDDEN = dd(r'''
    import unittest
    from datetime import date

    from veldoria.ids import VeldId, age_on, check_digit, make_id, parse_id
    from veldoria.phone import Phone, format_phone, parse_phone
    from veldoria.post import format_address, normalize_postcode, postcode_region


    class CheckDigit(unittest.TestCase):
        def test_values(self):
            self.assertEqual(check_digit("000000000"), 0)
            self.assertEqual(check_digit("870314352"), 2)
            self.assertEqual(check_digit("100000000"), 3)
            self.assertEqual(check_digit("010000000"), 1)
            self.assertEqual(check_digit("001000000"), 4)
            self.assertEqual(check_digit("000100000"), 1)
            self.assertEqual(check_digit("000010000"), 5)
            self.assertEqual(check_digit("000001000"), 2)
            self.assertEqual(check_digit("000000100"), 2)
            self.assertEqual(check_digit("000000010"), 6)
            self.assertEqual(check_digit("000000001"), 5)
            self.assertEqual(check_digit("999999999"), (3 + 1 + 4 + 1 + 5 + 9 + 2 + 6 + 5) * 9 % 7)

        def test_bad_input(self):
            for bad in ("", "12345678", "1234567890", "12345678a", " 12345678", "12345678 "):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    check_digit(bad)


    class ParseId(unittest.TestCase):
        def test_valid(self):
            got = parse_id("870314-352-2")
            self.assertEqual(got, VeldId(date(1987, 3, 14), "north", 52, 2))
            self.assertEqual(parse_id("8703143522"), got)
            self.assertEqual(parse_id("  870314-352-2\n"), got)

        def test_century_and_registry_from_digit(self):
            expected = {1: (1800, "north"), 2: (1800, "south"), 3: (1900, "north"), 4: (1900, "south"), 5: (2000, "north"),
                        6: (2000, "south"), 7: (2100, "north"), 8: (2100, "south")}
            for era, (century, registry) in expected.items():
                body = "050607%d00" % era
                text = body + str(check_digit(body))
                got = parse_id(text)
                self.assertEqual(got.birth, date(century + 5, 6, 7), era)
                self.assertEqual(got.registry, registry, era)

        def test_serial_and_check_fields(self):
            body = "991231399"
            got = parse_id(body + str(check_digit(body)))
            self.assertEqual((got.birth, got.serial, got.check), (date(1999, 12, 31), 99, check_digit(body)))

        def test_bad_shapes(self):
            for bad in ("", "870314352", "87031435225", "870314-3525", "870314352-5", "87-0314-352-5", "870314--352-5", "870314 352 5",
                        "87031x-352-5", "870314_352_5", "870314-352-25", "８７０３１４-352-5"):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    parse_id(bad)

        def test_dashes_all_or_nothing(self):
            for bad in ("870314-3525", "8703143-52-5", "870314352-5"):
                with self.assertRaises(ValueError, msg=bad):
                    parse_id(bad)

        def test_bad_registry_digit(self):
            for era in (0, 9):
                body = "870314%d52" % era
                with self.assertRaises(ValueError):
                    parse_id(body + str(check_digit(body)))

        def test_check_digit_must_match(self):
            for c in range(10):
                if c != 2:
                    with self.assertRaises(ValueError):
                        parse_id("870314352" + str(c))

        def test_impossible_dates(self):
            for body in ("870230352", "870431352", "871301352", "870300352", "870100352", "990229352"):
                with self.assertRaises(ValueError, msg=body):
                    parse_id(body + str(check_digit(body)))

        def test_leap_days(self):
            body = "000229552"
            self.assertEqual(parse_id(body + str(check_digit(body))).birth, date(2000, 2, 29))
            body = "000229352"
            with self.assertRaises(ValueError):
                parse_id(body + str(check_digit(body)))
            body = "000229152"
            with self.assertRaises(ValueError):
                parse_id(body + str(check_digit(body)))
            body = "040229552"
            self.assertEqual(parse_id(body + str(check_digit(body))).birth, date(2004, 2, 29))

        def test_today(self):
            text = make_id(date(2020, 5, 17), "south", 3)
            self.assertEqual(parse_id(text, today=date(2020, 5, 17)).birth, date(2020, 5, 17))
            self.assertEqual(parse_id(text, today=date(2021, 1, 1)).birth, date(2020, 5, 17))
            with self.assertRaises(ValueError):
                parse_id(text, today=date(2020, 5, 16))
            self.assertEqual(parse_id(text).birth, date(2020, 5, 17))


    class MakeId(unittest.TestCase):
        def test_format(self):
            self.assertEqual(make_id(date(1987, 3, 14), "north", 52), "870314-352-2")
            self.assertEqual(make_id(date(1987, 3, 14), "south", 52), "870314-452-" + str(check_digit("870314452")))
            self.assertEqual(make_id(date(2005, 1, 2), "north", 0), "050102-500-" + str(check_digit("050102500")))
            self.assertEqual(make_id(date(1800, 1, 1), "north", 99), "000101-199-" + str(check_digit("000101199")))
            self.assertEqual(make_id(date(2199, 12, 31), "south", 7), "991231-807-" + str(check_digit("991231807")))
            self.assertEqual(make_id(date(1999, 12, 31), "south", 1), "991231-401-" + str(check_digit("991231401")))
            self.assertEqual(make_id(date(2000, 1, 1), "north", 10), "000101-510-" + str(check_digit("000101510")))
            self.assertEqual(make_id(date(2100, 1, 1), "south", 10), "000101-810-" + str(check_digit("000101810")))

        def test_era_boundaries(self):
            self.assertEqual(make_id(date(1899, 12, 31), "north", 0)[7], "1")
            self.assertEqual(make_id(date(1900, 1, 1), "north", 0)[7], "3")
            self.assertEqual(make_id(date(1999, 12, 31), "north", 0)[7], "3")
            self.assertEqual(make_id(date(2000, 1, 1), "south", 0)[7], "6")
            self.assertEqual(make_id(date(2099, 12, 31), "south", 0)[7], "6")
            self.assertEqual(make_id(date(2100, 1, 1), "north", 0)[7], "7")
            self.assertEqual(make_id(date(2199, 12, 31), "north", 0)[7], "7")

        def test_round_trip(self):
            for d in (date(1800, 1, 1), date(1899, 12, 31), date(1900, 2, 28), date(2000, 2, 29), date(2024, 7, 4), date(2100, 3, 1), date(2199, 12, 31)):
                for registry in ("north", "south"):
                    for serial in (0, 1, 50, 99):
                        got = parse_id(make_id(d, registry, serial))
                        self.assertEqual((got.birth, got.registry, got.serial), (d, registry, serial))

        def test_errors(self):
            with self.assertRaises(ValueError):
                make_id(date(1799, 12, 31), "north", 1)
            with self.assertRaises(ValueError):
                make_id(date(2200, 1, 1), "north", 1)
            with self.assertRaises(ValueError):
                make_id(date(2000, 1, 1), "east", 1)
            with self.assertRaises(ValueError):
                make_id(date(2000, 1, 1), "north", 100)
            with self.assertRaises(ValueError):
                make_id(date(2000, 1, 1), "north", -1)


    class AgeOn(unittest.TestCase):
        def test_birthday_boundary(self):
            b = date(1990, 6, 15)
            self.assertEqual(age_on(b, date(2020, 6, 14)), 29)
            self.assertEqual(age_on(b, date(2020, 6, 15)), 30)
            self.assertEqual(age_on(b, date(2020, 6, 16)), 30)
            self.assertEqual(age_on(b, date(2020, 5, 31)), 29)
            self.assertEqual(age_on(b, date(2020, 7, 1)), 30)
            self.assertEqual(age_on(b, date(1990, 6, 15)), 0)
            self.assertEqual(age_on(b, date(1991, 6, 14)), 0)
            self.assertEqual(age_on(b, date(1991, 6, 15)), 1)

        def test_month_before_and_after(self):
            self.assertEqual(age_on(date(2000, 3, 31), date(2001, 3, 30)), 0)
            self.assertEqual(age_on(date(2000, 3, 31), date(2001, 4, 1)), 1)
            self.assertEqual(age_on(date(2000, 12, 31), date(2001, 1, 1)), 0)

        def test_leapling(self):
            b = date(2000, 2, 29)
            self.assertEqual(age_on(b, date(2001, 2, 28)), 0)
            self.assertEqual(age_on(b, date(2001, 3, 1)), 1)
            self.assertEqual(age_on(b, date(2004, 2, 28)), 3)
            self.assertEqual(age_on(b, date(2004, 2, 29)), 4)
            self.assertEqual(age_on(b, date(2004, 3, 1)), 4)
            self.assertEqual(age_on(b, date(2100, 2, 28)), 99)
            self.assertEqual(age_on(b, date(2100, 3, 1)), 100)
            self.assertEqual(age_on(b, date(2023, 2, 28)), 22)
            self.assertEqual(age_on(b, date(2023, 3, 1)), 23)

        def test_day_before_birth(self):
            with self.assertRaises(ValueError):
                age_on(date(2000, 1, 2), date(2000, 1, 1))
            with self.assertRaises(ValueError):
                age_on(date(2000, 1, 1), date(1999, 12, 31))


    class Phone_(unittest.TestCase):
        def test_prefixes(self):
            for text in ("+999 712 345 678", "00999 712345678", "0712 345 678", "+999-712-345-678", "(+999) 712.345.678", " 0 7 1 2 3 4 5 6 7 8 "):
                self.assertEqual(parse_phone(text), Phone("mobile", "712345678"), text)

        def test_kinds(self):
            self.assertEqual(parse_phone("+999 21234567"), Phone("landline", "21234567"))
            self.assertEqual(parse_phone("+999 61234567"), Phone("landline", "61234567"))
            self.assertEqual(parse_phone("+999 80012345"), Phone("toll-free", "80012345"))
            self.assertEqual(parse_phone("0800 12345"), Phone("toll-free", "80012345"))
            self.assertEqual(parse_phone("0 21 23 45 67"), Phone("landline", "21234567"))

        def test_kind_boundaries(self):
            for first in "2345 6".replace(" ", ""):
                self.assertEqual(parse_phone("+999" + first + "1234567").kind, "landline")
            for bad in ("+999 11234567", "+999 71234567", "+999 7123456789", "+999 8123456", "+999 81234567", "+999 8001234", "+999 800123456",
                        "+999 9", "+999", "+999 3123456", "+999 312345678"):
                with self.assertRaises(ValueError, msg=bad):
                    parse_phone(bad)

        def test_bad_prefixes_and_characters(self):
            for bad in ("712345678", "+44 712345678", "0044 712345678", "00 712345678", "++999712345678", "+999 7123x5678",
                        "", "   ", "+", "0", "00", "tel:+999712345678", "+999 712 345 678 ext 5", "9997 12345678"):
                with self.assertRaises(ValueError, msg=bad):
                    parse_phone(bad)

        def test_trunk_zero_only_once(self):
            with self.assertRaises(ValueError):
                parse_phone("00712345678")
            with self.assertRaises(ValueError):
                parse_phone("0021234567")

        def test_e164(self):
            self.assertEqual(format_phone("0712 345 678"), "+999712345678")
            self.assertEqual(format_phone("021 234 567"), "+99921234567")
            self.assertEqual(format_phone("0800 12345", "e164"), "+99980012345")

        def test_national_groups(self):
            self.assertEqual(format_phone("+999712345678", "national"), "0712 345 678")
            self.assertEqual(format_phone("+99921234567", "national"), "021 234 567")
            self.assertEqual(format_phone("+99980012345", "national"), "0800 12345")
            self.assertEqual(format_phone("+99961234567", "national"), "061 234 567")

        def test_international_groups(self):
            self.assertEqual(format_phone("0712345678", "international"), "+999 712 345 678")
            self.assertEqual(format_phone("021234567", "international"), "+999 21 234 567")
            self.assertEqual(format_phone("080012345", "international"), "+999 800 12345")

        def test_unknown_style(self):
            for style in ("E164", "nat", "", None):
                with self.assertRaises(ValueError):
                    format_phone("0712345678", style)

        def test_format_round_trip(self):
            for text in ("0712 345 678", "021 234 567", "0800 12345"):
                for style in ("e164", "national", "international"):
                    self.assertEqual(parse_phone(format_phone(text, style)), parse_phone(text))


    class Post(unittest.TestCase):
        def test_normalize(self):
            for text in ("1234AB", "1234 AB", "1234-AB", "1234 ab", "1234--ab", "1234 - ab", "  1234\tAb  ", "1234 - - aB"):
                self.assertEqual(normalize_postcode(text), "1234-AB", text)

        def test_bad_codes(self):
            for text in ("0123 AB", "123 AB", "12345 AB", "1234 A", "1234 ABC", "1234 A1", "1234", "AB 1234", "1234 IA", "1234 AO", "1234 QQ",
                         "1234 Ab-", "1234_AB", "", "12 34 AB", "1234 ÄB"):
                with self.assertRaises(ValueError, msg=repr(text)):
                    normalize_postcode(text)

        def test_allowed_letters(self):
            for letter in "ABCDEFGHJKLMNPRSTUVWXYZ":
                self.assertEqual(normalize_postcode("5000 %s%s" % (letter, letter.lower())), "5000-%s%s" % (letter, letter))
            for letter in "IOQ":
                with self.assertRaises(ValueError):
                    normalize_postcode("5000 A%s" % letter)
                with self.assertRaises(ValueError):
                    normalize_postcode("5000 %sA" % letter.lower())

        def test_regions(self):
            names = ["North", "Harbour", "Highlands", "Midlands", "Lakes", "Coast", "Capital", "Islands", "Offshore"]
            for d, name in zip("123456789", names):
                self.assertEqual(postcode_region("%s234 ab" % d), name)
            with self.assertRaises(ValueError):
                postcode_region("0234 AB")

        def test_address(self):
            self.assertEqual(format_address("  Ada Veld ", " Quay Road ", 12, "7011 ab", " Port Anselm "),
                             ["Ada Veld", "Quay Road 12", "7011-AB PORT ANSELM"])
            self.assertEqual(format_address("A", "B", "4a", "2000-cd", "C", unit="3"), ["A", "B 4a/3", "2000-CD C"])
            self.assertEqual(format_address("A", "B", 1, "2000CD", "C", unit="  "), ["A", "B 1", "2000-CD C"])
            self.assertEqual(format_address("A", "B", 1, "2000CD", "C", unit=" 7 "), ["A", "B 1/7", "2000-CD C"])
            self.assertEqual(format_address("A", "B", 1, "2000CD", "C", unit=0), ["A", "B 1/0", "2000-CD C"])

        def test_address_errors(self):
            for kw in ({"name": " "}, {"street": ""}, {"city": "  "}, {"postcode": "bad"}):
                args = dict(name="A", street="B", number=1, postcode="2000CD", city="C")
                args.update(kw)
                with self.assertRaises(ValueError, msg=str(kw)):
                    format_address(**args)


    if __name__ == "__main__":
        unittest.main()
''')

VEL = Lib(
    name="veldoria", lang="python", title="the Veldorian format package (`veldoria/`)",
    blurb="The registration forms of the Veldoria portal validate and print citizen numbers, phone numbers and postal codes with this package.",
    files={"veldoria/__init__.py": VEL_INIT, "veldoria/ids.py": VEL_IDS, "veldoria/phone.py": VEL_PHONE, "veldoria/post.py": VEL_POST,
           "README.md": VEL_README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_basic.py": VEL_VISIBLE},
    hidden_tests={"tests/test_full.py": VEL_HIDDEN},
    mutate=["veldoria/ids.py", "veldoria/phone.py", "veldoria/post.py"], difficulty=3, tags=["formats", "validation", "dates"],
    probes=[
        'check_digit("870314352")',
        'make_id(date(2100, 1, 1), "north", 7)',
        'make_id(date(1899, 12, 31), "south", 0)',
        'parse_id("870314-352-2")',
        'age_on(date(2000, 2, 29), date(2001, 2, 28))',
        'age_on(date(1990, 6, 15), date(2020, 6, 14))',
        'parse_phone("00999 21234567")',
        'format_phone("0712345678", "international")',
        'format_phone("080012345", "national")',
        'format_phone("021234567", "international")',
        'normalize_postcode("1234 - ab")',
        'postcode_region("7011ab")',
        'format_address("Ada", "Quay Road", 12, "7011 ab", "Port", unit=3)',
    ],
    probe_import="from datetime import date\nfrom veldoria.ids import *\nfrom veldoria.phone import *\nfrom veldoria.post import *",
)


LIBS = [VEL]
register_libs(LIBS, n=10)
