"""Native bug-fix family in Indonesian: NIK parsing and rupiah formatting (python)."""
from fx import Lib, dd

from ._native import register_native

README = dd(r'''
    # idtools

    Fungsi bantu untuk aplikasi pendaftaran pasien sebuah klinik: membaca Nomor Induk Kependudukan (NIK) dan menulis serta
    membaca jumlah uang dalam rupiah. Hanya memakai pustaka standar. NIK dalam contoh dan tes dibuat-buat, bukan milik orang
    sungguhan.

    ## NIK

    NIK terdiri dari 16 digit: `PPKKCC DDMMYY SSSS` yaitu kode provinsi (2 digit), kode kabupaten/kota (2), kode kecamatan (2),
    tanggal lahir `DD` `MM` `YY` (masing-masing 2 digit) dan nomor urut (4 digit). Untuk perempuan, `DD` ditambah 40
    (tanggal 15 menjadi `55`).

    Kode provinsi yang dikenal (di luar ini NIK ditolak): `11 12 13 14 15 16 17 18 19 21 31 32 33 34 35 36 51 52 53 61 62 63 64
    65 71 72 73 74 75 76 81 82 91 94`.

    Karena tahun hanya 2 digit, abad ditentukan dari tanggal acuan `today`: tahun lahir adalah `2000 + YY` jika angka itu tidak
    melebihi `today.year`, selain itu `1900 + YY`.

    ### `parse_nik(nik, today) -> dict`
    Mengembalikan `{"province": "PP", "regency": "KK", "district": "CC", "birth": date, "gender": "L" atau "P", "serial": "SSSS"}`;
    kode berupa string apa adanya. `gender` adalah `"P"` bila `DD > 40` (lalu `DD` dikurangi 40), selain itu `"L"`. `ValueError`
    bila: panjangnya bukan tepat 16 atau ada karakter selain digit ASCII `0`-`9`, kode provinsi tidak dikenal, tanggal tidak ada
    di kalender (perhatikan tahun kabisat: 1900 bukan kabisat, 2000 kabisat), atau tanggal lahir lebih besar dari `today`
    (sama dengan `today` boleh).

    ### `valid_nik(nik, today) -> bool`
    `True` bila `parse_nik` berhasil, selain itu `False`.

    ## Rupiah

    ### `format_rupiah(amount, decimals=0, symbol=True) -> str`
    `amount` (`int`, `float`, `Decimal` atau `str`) ditulis dengan titik sebagai pemisah ribuan (kelompok tiga digit) dan koma
    sebagai pemisah desimal: `1234567` -> `Rp 1.234.567`, `1234567.5` dengan `decimals=2` -> `Rp 1.234.567,50`.

    * Pembulatan ke `decimals` angka di belakang koma memakai `decimal.Decimal(str(amount))` dengan "setengah ke atas"
      (ROUND_HALF_UP, pada nilai mutlak): `0.5` -> `Rp 1`, `2.5` -> `Rp 3`, `1234.565` dengan `decimals=2` -> `Rp 1.234,57`.
      Dengan `decimals=0` tidak ada koma. `decimals < 0` adalah `ValueError`.
    * `symbol=True` menambahkan `Rp` dan satu spasi biasa di depan angka; `symbol=False` tidak.
    * Bilangan negatif diberi `-` di paling depan, sebelum `Rp` (`-Rp 1.500`). Jika hasil pembulatan nol, tanda minus tidak
      ditulis (`-0.4` -> `Rp 0`).

    ### `parse_rupiah(text) -> Decimal`
    Kebalikannya. Bentuk yang diterima (spasi di awal dan akhir diabaikan, `Rp` boleh huruf besar atau kecil): `-` opsional,
    awalan opsional `Rp` atau `Rp.` (boleh diikuti spasi), `-` opsional lagi setelah awalan, lalu angka. Angka harus berupa
    digit saja (`5000`) atau dikelompokkan dengan titik dengan benar: satu sampai tiga digit di depan, lalu satu atau lebih
    kelompok tepat tiga digit (`1.234.567`). Setelahnya boleh ada bagian desimal berupa koma dan satu digit atau lebih
    (`1.234,5`). Tanda minus tidak boleh muncul di dua tempat sekaligus. Selain itu `ValueError`: pengelompokan salah
    (`12.34`, `1.2345`, `1..234`, `1.234.`), format Inggris (`1,234.5`), koma tanpa digit (`1.000,`), tidak ada angka (`Rp`, ``).
''')

SRC = dd(r'''
    import re
    from datetime import date
    from decimal import ROUND_HALF_UP, Decimal

    PROVINCES = frozenset("11 12 13 14 15 16 17 18 19 21 31 32 33 34 35 36 51 52 53 61 62 63 64 65 71 72 73 74 75 76 81 82 91 94".split())
    _GROUPED = re.compile(r"[0-9]{1,3}(?:\.[0-9]{3})+|[0-9]+")
    _RUPIAH = re.compile(r"\s*(-?)\s*(?:rp\.?\s*)?(-?)\s*([0-9.]+)(?:,([0-9]+))?\s*", re.I)


    def parse_nik(nik: str, today: date) -> dict:
        if len(nik) != 16 or any(c not in "0123456789" for c in nik):
            raise ValueError("NIK must be 16 digits")
        province = nik[0:2]
        if province not in PROVINCES:
            raise ValueError("unknown province code")
        day = int(nik[6:8])
        gender = "L"
        if day > 40:
            gender = "P"
            day -= 40
        yy = int(nik[10:12])
        year = 2000 + yy if 2000 + yy <= today.year else 1900 + yy
        try:
            birth = date(year, int(nik[8:10]), day)
        except ValueError:
            raise ValueError("invalid birth date")
        if birth > today:
            raise ValueError("birth date is in the future")
        return {"province": province, "regency": nik[2:4], "district": nik[4:6], "birth": birth, "gender": gender,
                "serial": nik[12:]}


    def valid_nik(nik: str, today: date) -> bool:
        try:
            parse_nik(nik, today)
        except ValueError:
            return False
        return True


    def _group(digits: str) -> str:
        head = len(digits) % 3
        parts = [digits[:head]] if head else []
        parts += [digits[i:i + 3] for i in range(head, len(digits), 3)]
        return ".".join(parts)


    def format_rupiah(amount, decimals: int = 0, symbol: bool = True) -> str:
        if decimals < 0:
            raise ValueError("decimals must not be negative")
        d = Decimal(str(amount))
        q = abs(d).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
        whole, _, frac = format(q, "f").partition(".")
        out = _group(whole) + ("," + frac if frac else "")
        neg = d < 0 and q != 0
        return ("-" if neg else "") + ("Rp " if symbol else "") + out


    def parse_rupiah(text: str) -> Decimal:
        m = _RUPIAH.fullmatch(text)
        if not m or (m.group(1) and m.group(2)):
            raise ValueError("unreadable amount: %r" % (text,))
        whole = m.group(3)
        if not _GROUPED.fullmatch(whole):
            raise ValueError("bad digit grouping: %r" % (text,))
        value = Decimal(whole.replace(".", "") + ("." + m.group(4) if m.group(4) else ""))
        return -value if (m.group(1) or m.group(2)) else value
''')

VISIBLE = dd('''
    import unittest
    from datetime import date

    from idtools import format_rupiah, parse_nik, parse_rupiah


    class Dasar(unittest.TestCase):
        def test_nik(self):
            info = parse_nik("3171051503950001", date(2025, 6, 1))
            self.assertEqual(info["birth"], date(1995, 3, 15))

        def test_format(self):
            self.assertEqual(format_rupiah(1234567), "Rp 1.234.567")

        def test_parse(self):
            self.assertEqual(str(parse_rupiah("Rp 5.000")), "5000")


    if __name__ == "__main__":
        unittest.main()
''')

HIDDEN = dd('''
    import unittest
    from datetime import date
    from decimal import Decimal

    from idtools import format_rupiah, parse_nik, parse_rupiah, valid_nik

    D = date
    T = D(2025, 6, 1)


    class Nik(unittest.TestCase):
        def test_male(self):
            self.assertEqual(parse_nik("3171051503950001", T), {
                "province": "31", "regency": "71", "district": "05", "birth": D(1995, 3, 15), "gender": "L", "serial": "0001"})

        def test_female_day_plus_40(self):
            self.assertEqual(parse_nik("3171055503950002", T), {
                "province": "31", "regency": "71", "district": "05", "birth": D(1995, 3, 15), "gender": "P", "serial": "0002"})
            self.assertEqual(parse_nik("3171054503950001", T)["birth"], D(1995, 3, 5))
            self.assertEqual(parse_nik("3171054503950001", T)["gender"], "P")

        def test_day_40_is_male_and_41_is_female(self):
            self.assertEqual(parse_nik("3171050103950001", T)["gender"], "L")
            self.assertEqual(parse_nik("3171054103950001", T)["birth"], D(1995, 3, 1))
            self.assertEqual(parse_nik("3171054103950001", T)["gender"], "P")
            self.assertFalse(valid_nik("3171054003950001", T))   # DD = 40 is no real day
            self.assertFalse(valid_nik("3171057203950001", T))   # 72 - 40 = 32

        def test_century_from_today(self):
            self.assertEqual(parse_nik("1101010101000001", D(2025, 1, 1))["birth"], D(2000, 1, 1))
            self.assertEqual(parse_nik("1101010101250001", T)["birth"], D(2025, 1, 1))
            self.assertEqual(parse_nik("1101013101260001", T)["birth"], D(1926, 1, 31))
            self.assertEqual(parse_nik("1101010101260001", D(2026, 6, 1))["birth"], D(2026, 1, 1))
            self.assertEqual(parse_nik("1101010101990001", T)["birth"], D(1999, 1, 1))
            self.assertEqual(parse_nik("1101010101260001", D(2025, 12, 31))["birth"], D(1926, 1, 1))

        def test_future_birth(self):
            self.assertFalse(valid_nik("1101012606250001", T))
            self.assertTrue(valid_nik("1101010106250001", T))
            self.assertTrue(valid_nik("3171051503950001", D(1995, 3, 15)))
            self.assertFalse(valid_nik("3171051503950001", D(1995, 3, 14)))
            self.assertTrue(valid_nik("3171051503950001", D(1995, 3, 16)))

        def test_leap_days(self):
            self.assertEqual(parse_nik("3273012902000003", T)["birth"], D(2000, 2, 29))
            self.assertFalse(valid_nik("3273012902010003", T))
            self.assertEqual(parse_nik("3273012902960003", T)["birth"], D(1996, 2, 29))
            self.assertFalse(valid_nik("3273012902970003", T))
            self.assertEqual(parse_nik("3273016902000003", T)["gender"], "P")

        def test_bad_dates(self):
            for dd_mm in ("3102", "3104", "0001", "0100", "0113", "3113", "3200"):
                nik = "317105" + dd_mm + "950001"
                self.assertFalse(valid_nik(nik, T), nik)

        def test_province_codes(self):
            for ok in ("11", "19", "21", "31", "36", "51", "53", "65", "76", "82", "91", "94"):
                self.assertTrue(valid_nik(ok + "71051503950001", T), ok)
            for bad in ("00", "10", "20", "22", "30", "37", "41", "54", "66", "77", "83", "90", "92", "99"):
                self.assertFalse(valid_nik(bad + "71051503950001", T), bad)

        def test_shape(self):
            for bad in ("", "317105150395000", "31710515039500012", "317105150395000x", " 3171051503950001", "3171051503950001 ",
                        "３１７１０５１５０３９５０００１", "3171-0515-0395-0001"):
                self.assertFalse(valid_nik(bad, T), repr(bad))
                with self.assertRaises(ValueError, msg=repr(bad)):
                    parse_nik(bad, T)

        def test_codes_are_strings(self):
            info = parse_nik("1101010101250007", T)
            self.assertEqual((info["province"], info["regency"], info["district"], info["serial"]), ("11", "01", "01", "0007"))


    class Format(unittest.TestCase):
        def test_grouping(self):
            cases = {0: "Rp 0", 5: "Rp 5", 999: "Rp 999", 1000: "Rp 1.000", 12345: "Rp 12.345", 123456: "Rp 123.456",
                     1234567: "Rp 1.234.567", 1000000000: "Rp 1.000.000.000", 12345678901: "Rp 12.345.678.901"}
            for n, text in cases.items():
                self.assertEqual(format_rupiah(n), text, n)

        def test_decimals(self):
            self.assertEqual(format_rupiah(1234567.5, 2), "Rp 1.234.567,50")
            self.assertEqual(format_rupiah(1234567, 2), "Rp 1.234.567,00")
            self.assertEqual(format_rupiah(12, 1), "Rp 12,0")
            self.assertEqual(format_rupiah(1234.5, 3), "Rp 1.234,500")

        def test_rounding_half_up(self):
            self.assertEqual(format_rupiah(1234567.5), "Rp 1.234.568")
            self.assertEqual(format_rupiah(0.5), "Rp 1")
            self.assertEqual(format_rupiah(2.5), "Rp 3")
            self.assertEqual(format_rupiah(0.4), "Rp 0")
            self.assertEqual(format_rupiah(1234.565, 2), "Rp 1.234,57")
            self.assertEqual(format_rupiah(1.005, 2), "Rp 1,01")
            self.assertEqual(format_rupiah("2.675", 2), "Rp 2,68")
            self.assertEqual(format_rupiah(Decimal("999.5")), "Rp 1.000")
            self.assertEqual(format_rupiah(999999.5), "Rp 1.000.000")

        def test_no_symbol(self):
            self.assertEqual(format_rupiah(1234567, symbol=False), "1.234.567")
            self.assertEqual(format_rupiah(1234.5, 2, False), "1.234,50")
            self.assertEqual(format_rupiah(-1500, symbol=False), "-1.500")

        def test_negative(self):
            self.assertEqual(format_rupiah(-1500), "-Rp 1.500")
            self.assertEqual(format_rupiah(-1234567.5, 2), "-Rp 1.234.567,50")
            self.assertEqual(format_rupiah(-2.5), "-Rp 3")
            self.assertEqual(format_rupiah(-999), "-Rp 999")

        def test_negative_zero(self):
            self.assertEqual(format_rupiah(-0.4), "Rp 0")
            self.assertEqual(format_rupiah(-0.004, 2), "Rp 0,00")
            self.assertEqual(format_rupiah(-0.5), "-Rp 1")

        def test_bad_decimals(self):
            with self.assertRaises(ValueError):
                format_rupiah(5, -1)


    class Parse(unittest.TestCase):
        def test_prefixes(self):
            self.assertEqual(parse_rupiah("Rp 1.234.567,50"), Decimal("1234567.50"))
            self.assertEqual(parse_rupiah("Rp1.234"), Decimal("1234"))
            self.assertEqual(parse_rupiah("Rp. 5.000"), Decimal("5000"))
            self.assertEqual(parse_rupiah("rp 5.000"), Decimal("5000"))
            self.assertEqual(parse_rupiah("RP.5000"), Decimal("5000"))
            self.assertEqual(parse_rupiah("1.234.567"), Decimal("1234567"))
            self.assertEqual(parse_rupiah("5000"), Decimal("5000"))

        def test_spaces(self):
            self.assertEqual(parse_rupiah("  Rp  1.000  "), Decimal("1000"))
            self.assertEqual(parse_rupiah("\\tRp 7\\n"), Decimal("7"))

        def test_negative(self):
            self.assertEqual(parse_rupiah("-Rp 5.000"), Decimal("-5000"))
            self.assertEqual(parse_rupiah("Rp -5.000"), Decimal("-5000"))
            self.assertEqual(parse_rupiah("-5000"), Decimal("-5000"))
            self.assertEqual(parse_rupiah("- Rp 1.000,5"), Decimal("-1000.5"))
            for t in ("--5", "-Rp -5", "- Rp. -5.000"):
                with self.assertRaises(ValueError, msg=t):
                    parse_rupiah(t)

        def test_decimal_comma(self):
            self.assertEqual(parse_rupiah("1234,5"), Decimal("1234.5"))
            self.assertEqual(parse_rupiah("1.234,5"), Decimal("1234.5"))
            self.assertEqual(parse_rupiah("0,5"), Decimal("0.5"))
            self.assertEqual(str(parse_rupiah("1.000,50")), "1000.50")
            self.assertEqual(str(parse_rupiah("Rp 12,345")), "12.345")

        def test_grouping_must_be_exact(self):
            for t in ("12.34", "1.2345", "1..234", "1.234.", ".234", "1234.567", "12.3456.789", "1.23.456", "1.234.56"):
                with self.assertRaises(ValueError, msg=t):
                    parse_rupiah(t)

        def test_big_groups(self):
            self.assertEqual(parse_rupiah("Rp 100.000.000"), Decimal("100000000"))
            self.assertEqual(parse_rupiah("999.999"), Decimal("999999"))
            self.assertEqual(parse_rupiah("12.345.678.901"), Decimal("12345678901"))

        def test_english_style_and_junk(self):
            for t in ("1,234.5", "1,234,567", "1.000,", "1.000,x", "Rp", "", "   ", "abc", "Rp 1 000", "Rp 5 rupiah", "$5",
                      "Rp Rp 5", "Rp 5,5,5", "1.000,5.0", ",5"):
                with self.assertRaises(ValueError, msg=repr(t)):
                    parse_rupiah(t)

        def test_round_trip(self):
            for n in (0, 7, 999, 1000, 123456, 1234567, 10 ** 9):
                self.assertEqual(parse_rupiah(format_rupiah(n)), Decimal(n))
                self.assertEqual(parse_rupiah(format_rupiah(-n)), Decimal(-n))
            self.assertEqual(parse_rupiah(format_rupiah(1234567.5, 2)), Decimal("1234567.50"))


    if __name__ == "__main__":
        unittest.main()
''')

LIB = Lib(
    name="idtools", lang="python", title="`idtools`",
    blurb="Aplikasi pendaftaran pasien sebuah klinik memakai fungsi-fungsi ini untuk membaca NIK dan menulis jumlah biaya dalam rupiah.",
    files={"idtools/__init__.py": "from .core import *  # noqa: F401,F403\n", "idtools/core.py": SRC,
           "README.md": README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_dasar.py": VISIBLE},
    hidden_tests={"tests/test_lengkap.py": HIDDEN},
    mutate=["idtools/core.py"], difficulty=3, tags=["i18n", "validation", "money", "dates"],
    probes=[
        'parse_nik("3171055503950002", date(2025, 6, 1))["gender"]',
        'parse_nik("3171054503950001", date(2025, 6, 1))["birth"]',
        'parse_nik("1101013101260001", date(2025, 6, 1))["birth"]',
        'valid_nik("3273012902010003", date(2025, 6, 1))',
        'valid_nik("1101012606250001", date(2025, 6, 1))',
        'valid_nik("9901010101950001", date(2025, 6, 1))',
        'format_rupiah(1234567)',
        'format_rupiah(1234567.5, 2)',
        'format_rupiah(2.5)',
        'format_rupiah(-1500)',
        'format_rupiah(-0.4)',
        'parse_rupiah("Rp. 5.000")',
        'parse_rupiah("1.234,5")',
        'parse_rupiah("12.34")',
        'parse_rupiah("1,234.5")',
    ],
    probe_import="from datetime import date\nfrom idtools import *",
)

register_native(LIB, "id", "fix-idtools", n=9,
                summary="native: injected bugs in an Indonesian NIK/rupiah library, reports in Indonesian")
