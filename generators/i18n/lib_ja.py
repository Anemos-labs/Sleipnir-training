"""Native bug-fix family in Japanese: era dates (wareki), display width, yen and 万/億 formatting (python)."""
from fx import Lib, dd

from ._native import register_native

README = dd('''
    # jpcal

    社内の帳票ツールで使う、日本語向けの小さな書式ライブラリです。和暦の変換、全角・半角を考慮した表示幅、
    円と万・億の表記を扱います。標準ライブラリだけで動きます。

    ## 和暦

    対応する元号と、その最初の日:

    | 元号 | 略称 | 初日 | 元年にあたる西暦 |
    |---|---|---|---|
    | 令和 | R | 2019-05-01 | 2019 |
    | 平成 | H | 1989-01-08 | 1989 |
    | 昭和 | S | 1926-12-25 | 1926 |
    | 大正 | T | 1912-07-30 | 1912 |
    | 明治 | M | 1873-01-01 | 1868 |

    明治は 1873 年 1 月 1 日(明治 6 年 1 月 1 日、グレゴリオ暦の採用日)から対応します。それより前の日付は扱いません。
    和暦の年数は「西暦の年 − 元年にあたる西暦 + 1」で、元号の途中から始まる年も 1 年目として数えます
    (令和 1 年は 2019 年全体、2020 年が令和 2 年)。

    ### `to_wareki(d) -> str`
    `date` を `"令和7年4月1日"` の形式にします。数字は半角でゼロ埋めなし。1 年目は `"元"` と書きます
    (`"令和元年5月1日"`、`"平成元年1月8日"`)。1873-01-01 より前は `ValueError`。

    ### `from_wareki(text) -> date`
    次の 2 つの形式を読み取ります。どちらも前後と各要素の間の空白は無視します。

    * `"令和7年4月1日"`: 年に `元` または数字(半角・全角どちらも可。`"令和７年４月１日"`)。
    * 略称形式 `"R7.4.1"`(大文字 1 文字の略称、年・月・日を `.` で区切る。`"H31.4.30"`)。

    年が 0、存在しない日付、その元号の期間に入っていない日付(`"平成31年5月1日"` は令和なので不可、`"昭和64年1月8日"` は
    平成なので不可、`"明治5年12月31日"` は対象外)、形式の誤りはすべて `ValueError`。

    ## 表示幅

    ### `display_width(s) -> int`
    等幅フォントでの表示幅(桁数)。文字ごとに次の規則で数えて合計します。

    * `unicodedata.east_asian_width` が `"W"` または `"F"` の文字は 2。
    * 結合文字(Unicode の一般カテゴリが `M` で始まるもの、例: 濁点の結合文字 `\\u3099`)と、幅ゼロの文字
      `\\u200b` `\\u200c` `\\u200d` `\\ufeff` は 0。
    * それ以外(半角カナ `"H"`、曖昧幅 `"A"` の `…` など含む)は 1。

    ### `truncate_width(s, width, ellipsis="…") -> str`
    表示幅が `width` を超える文字列を、省略記号を付けて `width` 以内に切り詰めます。`display_width(s) <= width` なら
    `s` をそのまま返します。超えるときは、先頭から文字を取り、`省略記号を足した幅が width 以内` になる最長の接頭辞に
    `ellipsis` を付けて返します(全角文字を途中で切ることはありません)。省略記号だけで `width` を超える場合は
    空文字列を返します。

    ### `pad_width(s, width, align="left", fill=" ") -> str`
    表示幅が `width` になるまで `fill` を足します。すでに `width` 以上なら `s` のまま。`align` は `"left"`(右側に足す)、
    `"right"`(左側に足す)、`"center"`(足す数を 2 で割り、小さい方を左側にする)。`fill` の表示幅が 1 でない場合と、
    `align` が不明な場合は `ValueError`。

    ## 金額の表記

    ### `format_yen(n, style="symbol") -> str`
    整数の円表記。`style="symbol"` は `"¥1,234,567"`(記号は `\\u00a5`)、`style="kanji"` は `"1,234,567円"`。3 桁区切りはカンマ。
    負数は先頭に半角ハイフン `-` を付けます(`"-¥500"`, `"-500円"`)。それ以外の `style` は `ValueError`。

    ### `format_man(n) -> str`
    整数を 4 桁ごとの万・億・兆で表記します。各単位は 0 でない部分だけ「数字+単位」と書き、0 の部分は省きます。
    万未満の部分は数字だけ。`0` は `"0"`。`12345` → `"1万2345"`、`100000000` → `"1億"`、`123456789` → `"1億2345万6789"`、
    `100020003` → `"1億2万3"`、`10005` → `"1万5"`。単位は 万(10⁴)・億(10⁸)・兆(10¹²)。負数は先頭に `-`。
    10¹⁶ 以上は `ValueError`。
''')

SRC = dd('''
    import re
    import unicodedata
    from datetime import date

    _ERAS = [  # (name, abbreviation, first day, gregorian year of year 1)
        ("令和", "R", date(2019, 5, 1), 2019),
        ("平成", "H", date(1989, 1, 8), 1989),
        ("昭和", "S", date(1926, 12, 25), 1926),
        ("大正", "T", date(1912, 7, 30), 1912),
        ("明治", "M", date(1873, 1, 1), 1868),
    ]
    _FULL = str.maketrans("０１２３４５６７８９", "0123456789")
    _KANJI_RE = re.compile(r"\\s*(令和|平成|昭和|大正|明治)\\s*(元|[0-9０-９]+)\\s*年\\s*([0-9０-９]+)\\s*月\\s*([0-9０-９]+)\\s*日\\s*")
    _ABBR_RE = re.compile(r"\\s*([RHSTM])\\s*([0-9０-９]+)\\s*\\.\\s*([0-9０-９]+)\\s*\\.\\s*([0-9０-９]+)\\s*")
    _ZERO_WIDTH = {"\\u200b", "\\u200c", "\\u200d", "\\ufeff"}


    def _era_of(d: date):
        for era in _ERAS:
            if d >= era[2]:
                return era
        raise ValueError("date before 1873-01-01")


    def to_wareki(d: date) -> str:
        name, _, _, base = _era_of(d)
        year = d.year - base + 1
        return "%s%s年%d月%d日" % (name, "元" if year == 1 else year, d.month, d.day)


    def from_wareki(text: str) -> date:
        m = _KANJI_RE.fullmatch(text)
        if m:
            name = m.group(1)
            era = next(e for e in _ERAS if e[0] == name)
            year_text, month_text, day_text = m.group(2), m.group(3), m.group(4)
        else:
            m = _ABBR_RE.fullmatch(text)
            if not m:
                raise ValueError("unreadable date: %r" % (text,))
            era = next(e for e in _ERAS if e[1] == m.group(1))
            year_text, month_text, day_text = m.group(2), m.group(3), m.group(4)
        year = 1 if year_text == "元" else int(year_text.translate(_FULL))
        if year < 1:
            raise ValueError("year must be at least 1")
        d = date(era[3] + year - 1, int(month_text.translate(_FULL)), int(day_text.translate(_FULL)))
        if d < era[2] or _era_of(d) is not era:
            raise ValueError("date is outside the era")
        return d


    def _char_width(ch: str) -> int:
        if ch in _ZERO_WIDTH or unicodedata.category(ch).startswith("M"):
            return 0
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            return 2
        return 1


    def display_width(s: str) -> int:
        return sum(_char_width(ch) for ch in s)


    def truncate_width(s: str, width: int, ellipsis: str = "…") -> str:
        if display_width(s) <= width:
            return s
        budget = width - display_width(ellipsis)
        if budget < 0:
            return ""
        out = ""
        used = 0
        for ch in s:
            w = _char_width(ch)
            if used + w > budget:
                break
            out += ch
            used += w
        return out + ellipsis


    def pad_width(s: str, width: int, align: str = "left", fill: str = " ") -> str:
        if display_width(fill) != 1:
            raise ValueError("fill must be one column wide")
        gap = width - display_width(s)
        if align not in ("left", "right", "center"):
            raise ValueError("unknown alignment")
        if gap <= 0:
            return s
        if align == "left":
            return s + fill * gap
        if align == "right":
            return fill * gap + s
        left = gap // 2
        return fill * left + s + fill * (gap - left)


    def format_yen(n: int, style: str = "symbol") -> str:
        if style not in ("symbol", "kanji"):
            raise ValueError("unknown style")
        body = "{:,}".format(abs(n))
        text = "\\u00a5" + body if style == "symbol" else body + "円"
        return "-" + text if n < 0 else text


    def format_man(n: int) -> str:
        if abs(n) >= 10 ** 16:
            raise ValueError("too large")
        if n == 0:
            return "0"
        rest = abs(n)
        parts = []
        for unit, size in (("兆", 10 ** 12), ("億", 10 ** 8), ("万", 10 ** 4)):
            q, rest = divmod(rest, size)
            if q:
                parts.append("%d%s" % (q, unit))
        if rest:
            parts.append(str(rest))
        return ("-" if n < 0 else "") + "".join(parts)
''')

VISIBLE = dd('''
    import unittest
    from datetime import date

    from jpcal import display_width, format_yen, to_wareki


    class 基本(unittest.TestCase):
        def test_wareki(self):
            self.assertEqual(to_wareki(date(2025, 4, 1)), "令和7年4月1日")

        def test_width(self):
            self.assertEqual(display_width("日本語abc"), 9)

        def test_yen(self):
            self.assertEqual(format_yen(1500), "\\u00a51,500")


    if __name__ == "__main__":
        unittest.main()
''')

HIDDEN = dd('''
    import unittest
    from datetime import date

    from jpcal import (display_width, format_man, format_yen, from_wareki, pad_width, to_wareki, truncate_width)

    D = date


    class ToWareki(unittest.TestCase):
        def test_boundaries(self):
            cases = [
                (D(2019, 5, 1), "令和元年5月1日"), (D(2019, 4, 30), "平成31年4月30日"),
                (D(1989, 1, 8), "平成元年1月8日"), (D(1989, 1, 7), "昭和64年1月7日"),
                (D(1926, 12, 25), "昭和元年12月25日"), (D(1926, 12, 24), "大正15年12月24日"),
                (D(1912, 7, 30), "大正元年7月30日"), (D(1912, 7, 29), "明治45年7月29日"),
                (D(1873, 1, 1), "明治6年1月1日"),
            ]
            for d, text in cases:
                self.assertEqual(to_wareki(d), text, d)

        def test_year_counting(self):
            self.assertEqual(to_wareki(D(2019, 12, 31)), "令和元年12月31日")
            self.assertEqual(to_wareki(D(2020, 1, 1)), "令和2年1月1日")
            self.assertEqual(to_wareki(D(2025, 12, 31)), "令和7年12月31日")
            self.assertEqual(to_wareki(D(2026, 1, 1)), "令和8年1月1日")
            self.assertEqual(to_wareki(D(1990, 1, 1)), "平成2年1月1日")
            self.assertEqual(to_wareki(D(1927, 1, 1)), "昭和2年1月1日")
            self.assertEqual(to_wareki(D(1913, 1, 1)), "大正2年1月1日")
            self.assertEqual(to_wareki(D(1900, 6, 15)), "明治33年6月15日")

        def test_no_zero_padding(self):
            self.assertEqual(to_wareki(D(2024, 2, 9)), "令和6年2月9日")
            self.assertEqual(to_wareki(D(2024, 11, 30)), "令和6年11月30日")

        def test_too_early(self):
            for d in (D(1872, 12, 31), D(1800, 1, 1), D(1, 1, 1)):
                with self.assertRaises(ValueError):
                    to_wareki(d)


    class FromWareki(unittest.TestCase):
        def test_kanji(self):
            self.assertEqual(from_wareki("令和7年4月1日"), D(2025, 4, 1))
            self.assertEqual(from_wareki("令和元年5月1日"), D(2019, 5, 1))
            self.assertEqual(from_wareki("平成31年4月30日"), D(2019, 4, 30))
            self.assertEqual(from_wareki("平成元年1月8日"), D(1989, 1, 8))
            self.assertEqual(from_wareki("昭和64年1月7日"), D(1989, 1, 7))
            self.assertEqual(from_wareki("昭和元年12月25日"), D(1926, 12, 25))
            self.assertEqual(from_wareki("大正15年12月24日"), D(1926, 12, 24))
            self.assertEqual(from_wareki("大正元年7月30日"), D(1912, 7, 30))
            self.assertEqual(from_wareki("明治45年7月29日"), D(1912, 7, 29))
            self.assertEqual(from_wareki("明治6年1月1日"), D(1873, 1, 1))

        def test_fullwidth_digits_and_spaces(self):
            self.assertEqual(from_wareki("令和７年４月１日"), D(2025, 4, 1))
            self.assertEqual(from_wareki("  令和 7 年 4 月 1 日  "), D(2025, 4, 1))
            self.assertEqual(from_wareki("平成１２年１２月３１日"), D(2000, 12, 31))

        def test_abbreviated(self):
            self.assertEqual(from_wareki("R7.4.1"), D(2025, 4, 1))
            self.assertEqual(from_wareki("H31.4.30"), D(2019, 4, 30))
            self.assertEqual(from_wareki("S64.1.7"), D(1989, 1, 7))
            self.assertEqual(from_wareki("T15.12.24"), D(1926, 12, 24))
            self.assertEqual(from_wareki("M45.7.29"), D(1912, 7, 29))
            self.assertEqual(from_wareki(" R 7 . 4 . 1 "), D(2025, 4, 1))
            self.assertEqual(from_wareki("R７.４.１"), D(2025, 4, 1))

        def test_round_trip(self):
            d = D(1873, 1, 1)
            while d < D(2030, 1, 1):
                self.assertEqual(from_wareki(to_wareki(d)), d)
                d = D.fromordinal(d.toordinal() + 37)

        def test_outside_era(self):
            for text in ("平成31年5月1日", "令和元年4月30日", "昭和64年1月8日", "平成元年1月7日", "大正元年7月29日",
                         "明治45年7月30日", "昭和元年12月24日", "令和0年5月1日", "R1.4.30", "H31.5.1", "S64.1.8"):
                with self.assertRaises(ValueError, msg=text):
                    from_wareki(text)

        def test_before_meiji_6(self):
            for text in ("明治5年12月31日", "明治1年1月1日", "M5.12.31"):
                with self.assertRaises(ValueError, msg=text):
                    from_wareki(text)

        def test_bad_dates_and_formats(self):
            for text in ("令和7年2月30日", "令和7年13月1日", "令和7年4月0日", "令和7年4月", "令和x年4月1日", "7年4月1日",
                         "令和7-4-1", "X7.4.1", "r7.4.1", "R7/4/1", "", "令和元年元月1日", "令和7年4月1日です"):
                with self.assertRaises(ValueError, msg=text):
                    from_wareki(text)

        def test_leap_day(self):
            self.assertEqual(from_wareki("令和6年2月29日"), D(2024, 2, 29))
            with self.assertRaises(ValueError):
                from_wareki("令和7年2月29日")


    class Width(unittest.TestCase):
        def test_basic(self):
            self.assertEqual(display_width(""), 0)
            self.assertEqual(display_width("abc"), 3)
            self.assertEqual(display_width("日本語"), 6)
            self.assertEqual(display_width("日本語abc"), 9)
            self.assertEqual(display_width("한국어"), 6)
            self.assertEqual(display_width("中文"), 4)

        def test_fullwidth_and_halfwidth(self):
            self.assertEqual(display_width("ＡＢＣ"), 6)
            self.assertEqual(display_width("１２３"), 6)
            self.assertEqual(display_width("ｱｲｳ"), 3)
            self.assertEqual(display_width("ｶﾞ"), 2)
            self.assertEqual(display_width("　"), 2)

        def test_combining(self):
            self.assertEqual(display_width("か\\u3099"), 2)
            self.assertEqual(display_width("e\\u0301"), 1)
            self.assertEqual(display_width("\\u0301"), 0)

        def test_zero_width(self):
            self.assertEqual(display_width("a\\u200bb"), 2)
            self.assertEqual(display_width("\\ufeffabc"), 3)
            self.assertEqual(display_width("日\\u200d本"), 4)
            self.assertEqual(display_width("a\\u200cb"), 2)

        def test_ambiguous_and_emoji(self):
            self.assertEqual(display_width("…"), 1)
            self.assertEqual(display_width("€"), 1)
            self.assertEqual(display_width("😀"), 2)
            self.assertEqual(display_width("é"), 1)


    class Truncate(unittest.TestCase):
        def test_fits(self):
            self.assertEqual(truncate_width("日本語", 6), "日本語")
            self.assertEqual(truncate_width("abc", 3), "abc")
            self.assertEqual(truncate_width("", 0), "")

        def test_cut(self):
            self.assertEqual(truncate_width("日本語のテキスト", 7), "日本語…")
            self.assertEqual(truncate_width("日本語のテキスト", 8), "日本語…")
            self.assertEqual(truncate_width("日本語のテキスト", 9), "日本語の…")
            self.assertEqual(truncate_width("abcdefgh", 5), "abcd…")
            self.assertEqual(truncate_width("abc日本", 5), "abc…")
            self.assertEqual(truncate_width("abc日本", 6), "abc日…")

        def test_custom_ellipsis(self):
            self.assertEqual(truncate_width("abcdefgh", 6, "..."), "abc...")
            self.assertEqual(truncate_width("日本語のテキスト", 8, "…"), "日本語…")
            self.assertEqual(truncate_width("日本語のテキスト", 8, "…。"), "日本…。")
            self.assertEqual(truncate_width("abcdefgh", 4, ""), "abcd")

        def test_tiny_width(self):
            self.assertEqual(truncate_width("abcdefgh", 1), "…")
            self.assertEqual(truncate_width("日本語", 1), "…")
            self.assertEqual(truncate_width("abcdefgh", 0), "")
            self.assertEqual(truncate_width("abcdefgh", 2, "..."), "")
            self.assertEqual(truncate_width("日本語", 2), "…")

        def test_result_never_wider(self):
            text = "日本語のテキストabcｱｲｳ😀ＡＢＣ"
            for w in range(0, display_width(text) + 3):
                self.assertLessEqual(display_width(truncate_width(text, w)), w)


    class Pad(unittest.TestCase):
        def test_left_right_center(self):
            self.assertEqual(pad_width("日本", 8), "日本    ")
            self.assertEqual(pad_width("日本", 8, "right"), "    日本")
            self.assertEqual(pad_width("日本", 9, "center"), "  日本   ")
            self.assertEqual(pad_width("abc", 6, "center"), " abc  ")
            self.assertEqual(pad_width("abc", 7, "center"), "  abc  ")
            self.assertEqual(pad_width("abc", 6), "abc   ")

        def test_fill(self):
            self.assertEqual(pad_width("日本", 6, "left", "*"), "日本**")
            self.assertEqual(pad_width("a", 4, "right", "-"), "---a")
            self.assertEqual(pad_width("a", 4, "center", "."), ".a..")

        def test_already_wide(self):
            self.assertEqual(pad_width("日本語", 6), "日本語")
            self.assertEqual(pad_width("日本語", 4, "right"), "日本語")
            self.assertEqual(pad_width("abcd", 2, "center"), "abcd")
            self.assertEqual(pad_width("", 0), "")

        def test_bad_arguments(self):
            with self.assertRaises(ValueError):
                pad_width("a", 5, "left", "日")
            with self.assertRaises(ValueError):
                pad_width("a", 5, "left", "")
            with self.assertRaises(ValueError):
                pad_width("a", 5, "left", "ab")
            with self.assertRaises(ValueError):
                pad_width("a", 5, "middle")
            with self.assertRaises(ValueError):
                pad_width("abcdef", 2, "middle")

        def test_combining_fill_counts_zero(self):
            with self.assertRaises(ValueError):
                pad_width("a", 5, "left", "\\u0301")


    class Yen(unittest.TestCase):
        def test_symbol(self):
            self.assertEqual(format_yen(0), "\\u00a50")
            self.assertEqual(format_yen(999), "\\u00a5999")
            self.assertEqual(format_yen(1000), "\\u00a51,000")
            self.assertEqual(format_yen(1234567), "\\u00a51,234,567")
            self.assertEqual(format_yen(-500), "-\\u00a5500")
            self.assertEqual(format_yen(-1234567), "-\\u00a51,234,567")

        def test_kanji(self):
            self.assertEqual(format_yen(0, "kanji"), "0円")
            self.assertEqual(format_yen(1234567, "kanji"), "1,234,567円")
            self.assertEqual(format_yen(-500, "kanji"), "-500円")
            self.assertEqual(format_yen(1000000000, style="kanji"), "1,000,000,000円")

        def test_bad_style(self):
            with self.assertRaises(ValueError):
                format_yen(1, "words")


    class Man(unittest.TestCase):
        def test_examples(self):
            self.assertEqual(format_man(0), "0")
            self.assertEqual(format_man(5), "5")
            self.assertEqual(format_man(9999), "9999")
            self.assertEqual(format_man(10000), "1万")
            self.assertEqual(format_man(12345), "1万2345")
            self.assertEqual(format_man(100000000), "1億")
            self.assertEqual(format_man(123456789), "1億2345万6789")
            self.assertEqual(format_man(100020003), "1億2万3")
            self.assertEqual(format_man(10005), "1万5")
            self.assertEqual(format_man(10 ** 12), "1兆")
            self.assertEqual(format_man(10 ** 12 + 10 ** 8 + 10 ** 4 + 1), "1兆1億1万1")

        def test_big_groups(self):
            self.assertEqual(format_man(99999999), "9999万9999")
            self.assertEqual(format_man(5000 * 10 ** 12), "5000兆")
            self.assertEqual(format_man(1234 * 10 ** 12 + 5678 * 10 ** 8 + 9012 * 10 ** 4 + 3456), "1234兆5678億9012万3456")
            self.assertEqual(format_man(10 ** 16 - 1), "9999兆9999億9999万9999")

        def test_zero_groups_skipped(self):
            self.assertEqual(format_man(30000), "3万")
            self.assertEqual(format_man(300000007), "3億7")
            self.assertEqual(format_man(2 * 10 ** 12 + 5), "2兆5")
            self.assertEqual(format_man(4 * 10 ** 8 + 6 * 10 ** 4), "4億6万")

        def test_negative(self):
            self.assertEqual(format_man(-12345), "-1万2345")
            self.assertEqual(format_man(-100000000), "-1億")
            self.assertEqual(format_man(-5), "-5")

        def test_too_large(self):
            for n in (10 ** 16, -(10 ** 16), 10 ** 20):
                with self.assertRaises(ValueError):
                    format_man(n)


    if __name__ == "__main__":
        unittest.main()
''')

LIB = Lib(
    name="jpcal", lang="python", title="`jpcal`",
    blurb="社内の帳票ツールがこのライブラリで和暦の日付、表示幅の揃った表、円や万・億の金額を出力しています。",
    files={"jpcal/__init__.py": "from .core import *  # noqa: F401,F403\n", "jpcal/core.py": SRC,
           "README.md": README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_kihon.py": VISIBLE},
    hidden_tests={"tests/test_zentai.py": HIDDEN},
    mutate=["jpcal/core.py"], difficulty=3, tags=["unicode", "dates", "formatting", "east-asian-width"],
    probes=[
        'to_wareki(date(2019, 4, 30))',
        'to_wareki(date(1989, 1, 7))',
        'to_wareki(date(2019, 12, 31))',
        'from_wareki("令和元年5月1日")',
        'from_wareki("H31.4.30")',
        'from_wareki("平成31年5月1日")',
        'display_width("日本語abc")',
        'display_width("ｶﾞ")',
        'display_width("a\\u200bb")',
        'truncate_width("日本語のテキスト", 8)',
        'truncate_width("abcdefgh", 1)',
        'pad_width("日本", 9, "center")',
        'format_yen(-1234567)',
        'format_yen(1234567, "kanji")',
        'format_man(123456789)',
        'format_man(100020003)',
    ],
    probe_import="from datetime import date\nfrom jpcal import *",
)

register_native(LIB, "ja", "fix-jpcal", n=9,
                summary="native: injected bugs in a Japanese era-date/width/yen formatting library, reports in Japanese")
