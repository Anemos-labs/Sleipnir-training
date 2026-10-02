"""Native bug-fix family in Chinese: resident ID numbers and 万/亿 amounts (python)."""
from fx import Lib, dd

from ._native import register_native

README = dd('''
    # cnid

    某社区医院的挂号系统使用的小工具：校验和解析中国居民身份证号码（18 位和旧的 15 位），以及把金额写成
    “万”“亿”的口语形式。只用标准库。本项目里的号码都是为测试编造的，不对应真实的人。

    ## 身份证号码（18 位）

    结构：`AAAAAA YYYYMMDD SSS C`，即 6 位地址码、8 位出生日期、3 位顺序码、1 位校验码。

    * 地址码的前两位是省级代码，只允许下表中的代码：

      | 代码 | 名称 | 代码 | 名称 | 代码 | 名称 |
      |---|---|---|---|---|---|
      | 11 | 北京市 | 12 | 天津市 | 13 | 河北省 |
      | 14 | 山西省 | 15 | 内蒙古自治区 | 21 | 辽宁省 |
      | 22 | 吉林省 | 23 | 黑龙江省 | 31 | 上海市 |
      | 32 | 江苏省 | 33 | 浙江省 | 34 | 安徽省 |
      | 35 | 福建省 | 36 | 江西省 | 37 | 山东省 |
      | 41 | 河南省 | 42 | 湖北省 | 43 | 湖南省 |
      | 44 | 广东省 | 45 | 广西壮族自治区 | 46 | 海南省 |
      | 50 | 重庆市 | 51 | 四川省 | 52 | 贵州省 |
      | 53 | 云南省 | 54 | 西藏自治区 | 61 | 陕西省 |
      | 62 | 甘肃省 | 63 | 青海省 | 64 | 宁夏回族自治区 |
      | 65 | 新疆维吾尔自治区 | 71 | 台湾省 | 81 | 香港特别行政区 |
      | 82 | 澳门特别行政区 | 91 | 国外 | | |

    * 出生日期必须是公历上真实存在的日期（注意闰年：1900 年不是闰年，2000 年是），并且不早于 1900-01-01。
    * 顺序码的最后一位（整个号码的第 17 位）奇数为男，偶数为女。
    * 校验码：前 17 位依次乘以权重 `7 9 10 5 8 4 2 1 6 3 7 9 10 5 8 4 2` 后求和，对 11 取余，按余数
      `0 1 2 3 4 5 6 7 8 9 10` 依次对应 `1 0 X 9 8 7 6 5 4 3 2`。校验码里的 `X` 输入时大小写都接受（`x` 等同于 `X`）。

    ### `valid_id(id18, today=None) -> bool`
    全部满足才返回 `True`：长度恰好 18，前 17 位都是 ASCII 数字 `0`–`9`，第 18 位是数字或 `X`/`x`，省级代码在表中，
    出生日期合法，校验码正确。如果给了 `today`（一个 `date`），出生日期不得晚于 `today`（等于是可以的）。

    ### `parse_id(id18) -> dict`
    对合法号码返回 `{"province": 省级名称, "birth": date, "gender": "男" 或 "女"}`；不合法则抛出 `ValueError`。

    ### `mask_id(id18) -> str`
    脱敏显示：保留前 6 位和后 4 位，中间 8 位换成 `*`。长度不是 18 时抛出 `ValueError`（这里不检查号码是否合法）。

    ## 旧的 15 位号码

    ### `upgrade_15(id15) -> str`
    15 位号码（6 位地址码、6 位 `YYMMDD`、3 位顺序码）升级为 18 位：在出生日期的年份前加 `19`，再在末尾补上校验码。
    必须是恰好 15 个 ASCII 数字，并且升级后的出生日期（`19YY-MM-DD`）要合法，否则 `ValueError`。结果不检查省级代码。

    ## 金额口语

    ### `format_amount_cn(n) -> str`
    把整数写成带“万”“亿”的短格式，数值用 `decimal.Decimal` 做“四舍五入（0.5 进位）”，最多保留两位小数，小数末尾的 0
    去掉。

    * `abs(n) < 10000`：原样写成整数（`9999` → `"9999"`）。
    * `10000 <= abs(n) < 10**8`：除以 `10000` 后加“万”（`12345` → `"1.23万"`，`15000` → `"1.5万"`，`20000` → `"2万"`）；
      如果四舍五入后达到 `10000` 万，就改按“亿”写（`99999999` → `"1亿"`）。
    * `abs(n) >= 10**8`：除以 `10**8` 后加“亿”，不再有更大的单位（`10**12` → `"10000亿"`）。
    * 负数在前面加 `-`（`-12345` → `"-1.23万"`）。四舍五入针对绝对值。
''')

SRC = dd('''
    from datetime import date
    from decimal import ROUND_HALF_UP, Decimal

    _WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
    _CHECK = "10X98765432"
    PROVINCES = {
        "11": "北京市", "12": "天津市", "13": "河北省", "14": "山西省", "15": "内蒙古自治区", "21": "辽宁省", "22": "吉林省",
        "23": "黑龙江省", "31": "上海市", "32": "江苏省", "33": "浙江省", "34": "安徽省", "35": "福建省", "36": "江西省",
        "37": "山东省", "41": "河南省", "42": "湖北省", "43": "湖南省", "44": "广东省", "45": "广西壮族自治区", "46": "海南省",
        "50": "重庆市", "51": "四川省", "52": "贵州省", "53": "云南省", "54": "西藏自治区", "61": "陕西省", "62": "甘肃省",
        "63": "青海省", "64": "宁夏回族自治区", "65": "新疆维吾尔自治区", "71": "台湾省", "81": "香港特别行政区",
        "82": "澳门特别行政区", "91": "国外",
    }


    def _digits(s: str) -> bool:
        return all(c in "0123456789" for c in s)


    def _check_char(first17: str) -> str:
        return _CHECK[sum(int(c) * w for c, w in zip(first17, _WEIGHTS)) % 11]


    def _birth(text: str):
        try:
            d = date(int(text[0:4]), int(text[4:6]), int(text[6:8]))
        except ValueError:
            return None
        return d if d >= date(1900, 1, 1) else None


    def _parse(id18: str, today=None):
        if len(id18) != 18 or not _digits(id18[:17]) or not (_digits(id18[17]) or id18[17] in "Xx"):
            return None
        if id18[:2] not in PROVINCES:
            return None
        birth = _birth(id18[6:14])
        if birth is None or (today is not None and birth > today):
            return None
        if _check_char(id18[:17]) != id18[17].upper():
            return None
        return {"province": PROVINCES[id18[:2]], "birth": birth, "gender": "男" if int(id18[16]) % 2 == 1 else "女"}


    def valid_id(id18: str, today=None) -> bool:
        return _parse(id18, today) is not None


    def parse_id(id18: str) -> dict:
        info = _parse(id18)
        if info is None:
            raise ValueError("invalid ID number")
        return info


    def mask_id(id18: str) -> str:
        if len(id18) != 18:
            raise ValueError("expected 18 characters")
        return id18[:6] + "*" * 8 + id18[14:]


    def upgrade_15(id15: str) -> str:
        if len(id15) != 15 or not _digits(id15):
            raise ValueError("expected 15 digits")
        if _birth("19" + id15[6:12]) is None:
            raise ValueError("invalid birth date")
        first17 = id15[:6] + "19" + id15[6:]
        return first17 + _check_char(first17)


    def _short(value: Decimal) -> str:
        return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP).normalize(), "f")


    def format_amount_cn(n: int) -> str:
        sign = "-" if n < 0 else ""
        a = abs(n)
        if a < 10000:
            return sign + str(a)
        if a < 10 ** 8:
            wan = Decimal(a) / Decimal(10000)
            if wan.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) < Decimal(10000):
                return sign + _short(wan) + "万"
        return sign + _short(Decimal(a) / Decimal(10 ** 8)) + "亿"
''')

VISIBLE = dd('''
    import unittest

    from cnid import format_amount_cn, mask_id, valid_id


    class 基础(unittest.TestCase):
        def test_valid(self):
            self.assertTrue(valid_id("11010519491231002X"))

        def test_mask(self):
            self.assertEqual(mask_id("11010519491231002X"), "110105********002X")

        def test_amount(self):
            self.assertEqual(format_amount_cn(12345), "1.23万")


    if __name__ == "__main__":
        unittest.main()
''')

HIDDEN = dd('''
    import unittest
    from datetime import date

    from cnid import format_amount_cn, mask_id, parse_id, upgrade_15, valid_id

    D = date

    # (号码, 省, 出生日期, 性别)
    GOOD = [
        ("11010519491231002X", "北京市", D(1949, 12, 31), "女"),
        ("110101199003070011", "北京市", D(1990, 3, 7), "男"),
        ("11010119900307002X", "北京市", D(1990, 3, 7), "女"),
        ("310101198712310017", "上海市", D(1987, 12, 31), "男"),
        ("650102196001019990", "新疆维吾尔自治区", D(1960, 1, 1), "男"),
        ("370202202402290147", "山东省", D(2024, 2, 29), "女"),
        ("510104190001010018", "四川省", D(1900, 1, 1), "男"),
        ("820000199911301204", "澳门特别行政区", D(1999, 11, 30), "女"),
        ("910000197506150337", "国外", D(1975, 6, 15), "男"),
        ("530102198810080785", "云南省", D(1988, 10, 8), "女"),
        ("120105199211220069", "天津市", D(1992, 11, 22), "女"),
    ]


    class Valid(unittest.TestCase):
        def test_good(self):
            for n, _, _, _ in GOOD:
                self.assertTrue(valid_id(n), n)

        def test_lowercase_x(self):
            self.assertTrue(valid_id("11010519491231002x"))
            self.assertTrue(valid_id("11010119900307002x"))

        def test_wrong_check(self):
            for n, _, _, _ in GOOD:
                for c in "0123456789X":
                    if c != n[17]:
                        self.assertFalse(valid_id(n[:17] + c), n[:17] + c)

        def test_length(self):
            self.assertFalse(valid_id(""))
            self.assertFalse(valid_id("11010519491231002"))
            self.assertFalse(valid_id("11010519491231002XX"))
            self.assertFalse(valid_id(" 11010519491231002X"))
            self.assertFalse(valid_id("11010519491231002X "))

        def test_non_digits(self):
            self.assertFalse(valid_id("1101051949123100AX"))
            self.assertFalse(valid_id("a1010519491231002X"))
            self.assertFalse(valid_id("１１０１０５１９４９１２３１００２X"))  # 全角数字
            self.assertFalse(valid_id("11010519491231002Y"))

        def test_x_only_last(self):
            self.assertFalse(valid_id("1101051949123100XX"))

        def test_province(self):
            for prov in ("00", "10", "16", "20", "30", "47", "55", "66", "72", "83", "92", "99"):
                base = prov + "0101" + "19900307" + "001"
                w = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
                c = "10X98765432"[sum(int(a) * b for a, b in zip(base, w)) % 11]
                self.assertFalse(valid_id(base + c), prov)

        def test_birth_dates(self):
            def make(date_text):
                base = "110101" + date_text + "001"
                w = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
                return base + "10X98765432"[sum(int(a) * b for a, b in zip(base, w)) % 11]
            for ok in ("20000229", "20240229", "19960229", "19001231", "19000101", "20991231"):
                self.assertTrue(valid_id(make(ok)), ok)
            for bad in ("19000229", "21000229", "20010229", "19991301", "19990001", "19990100", "19990132", "19990431",
                        "18991231", "18000101", "00000101", "19990230"):
                self.assertFalse(valid_id(make(bad)), bad)

        def test_today(self):
            n = "110101199003070011"
            self.assertTrue(valid_id(n, today=D(1990, 3, 7)))
            self.assertTrue(valid_id(n, today=D(2025, 1, 1)))
            self.assertFalse(valid_id(n, today=D(1990, 3, 6)))
            self.assertFalse(valid_id(n, today=D(1980, 1, 1)))
            self.assertTrue(valid_id(n, today=None))


    class Parse(unittest.TestCase):
        def test_parse(self):
            for n, prov, birth, gender in GOOD:
                self.assertEqual(parse_id(n), {"province": prov, "birth": birth, "gender": gender}, n)

        def test_gender_by_17th_digit(self):
            self.assertEqual(parse_id("110101199003070011")["gender"], "男")
            self.assertEqual(parse_id("11010119900307002X")["gender"], "女")
            self.assertEqual(parse_id("650102196001019990")["gender"], "男")   # 顺序码 999
            self.assertEqual(parse_id("370202202402290147")["gender"], "女")   # 顺序码 014
            self.assertEqual(parse_id("910000197506150337")["gender"], "男")   # 顺序码 033

        def test_lowercase_x_parses(self):
            self.assertEqual(parse_id("11010519491231002x")["gender"], "女")

        def test_invalid(self):
            for bad in ("", "123", "110101199003070012", "11010519491231002Z", "990101199003070015"):
                with self.assertRaises(ValueError, msg=bad):
                    parse_id(bad)


    class Mask(unittest.TestCase):
        def test_mask(self):
            self.assertEqual(mask_id("11010519491231002X"), "110105********002X")
            self.assertEqual(mask_id("110101199003070011"), "110101********0011")
            self.assertEqual(mask_id("AAAAAABBBBBBBBCCCC"), "AAAAAA********CCCC")

        def test_length_only(self):
            with self.assertRaises(ValueError):
                mask_id("1234567890123456789")
            with self.assertRaises(ValueError):
                mask_id("12345678901234567")
            with self.assertRaises(ValueError):
                mask_id("")


    class Upgrade(unittest.TestCase):
        def test_upgrade(self):
            self.assertEqual(upgrade_15("110105491231002"), "11010519491231002X")
            self.assertEqual(upgrade_15("110101900307001"), "110101199003070011")
            self.assertEqual(upgrade_15("310101871231001"), "310101198712310017")

        def test_result_is_valid(self):
            for n in ("110105491231002", "110101900307001", "310101871231001", "110101040229001"):
                self.assertTrue(valid_id(upgrade_15(n)), n)

        def test_province_not_checked(self):
            self.assertEqual(upgrade_15("990101900101001"), "990101199001010019")
            self.assertFalse(valid_id(upgrade_15("990101900101001")))

        def test_century_is_19(self):
            self.assertEqual(upgrade_15("110101040229001"), "110101190402290010")
            self.assertEqual(upgrade_15("110101000101001")[6:14], "19000101")
            with self.assertRaises(ValueError):
                upgrade_15("110101000229001")   # 1900 不是闰年

        def test_bad(self):
            for bad in ("", "11010549123100", "1101054912310020", "11010549123100X", "110105491331002", "110105490231002",
                        "１１０１０５４９１２３１００２"):
                with self.assertRaises(ValueError, msg=bad):
                    upgrade_15(bad)


    class Amount(unittest.TestCase):
        def test_small(self):
            for n, text in ((0, "0"), (7, "7"), (9999, "9999"), (-9999, "-9999")):
                self.assertEqual(format_amount_cn(n), text)

        def test_wan(self):
            cases = {10000: "1万", 12345: "1.23万", 15000: "1.5万", 20000: "2万", 10050: "1.01万", 10049: "1万",
                     12350: "1.24万", 12349: "1.23万", 99990000: "9999万", 55555555: "5555.56万", 100000: "10万",
                     1234567: "123.46万", 50000000: "5000万"}
            for n, text in cases.items():
                self.assertEqual(format_amount_cn(n), text, n)

        def test_wan_rolls_over_to_yi(self):
            self.assertEqual(format_amount_cn(99999999), "1亿")
            self.assertEqual(format_amount_cn(99999950), "1亿")
            self.assertEqual(format_amount_cn(99999949), "9999.99万")
            self.assertEqual(format_amount_cn(99995000), "9999.5万")
            self.assertEqual(format_amount_cn(99994000), "9999.4万")

        def test_yi(self):
            cases = {10 ** 8: "1亿", 123456789: "1.23亿", 150000000: "1.5亿", 10 ** 12: "10000亿", 2 * 10 ** 8 + 5 * 10 ** 5: "2.01亿",
                     2 * 10 ** 8 + 4 * 10 ** 5: "2亿", 999999999: "10亿", 98765432100: "987.65亿"}
            for n, text in cases.items():
                self.assertEqual(format_amount_cn(n), text, n)

        def test_negative(self):
            self.assertEqual(format_amount_cn(-12345), "-1.23万")
            self.assertEqual(format_amount_cn(-10000), "-1万")
            self.assertEqual(format_amount_cn(-99999999), "-1亿")
            self.assertEqual(format_amount_cn(-123456789), "-1.23亿")

        def test_half_up_on_magnitude(self):
            self.assertEqual(format_amount_cn(10050), "1.01万")
            self.assertEqual(format_amount_cn(-10050), "-1.01万")
            self.assertEqual(format_amount_cn(100500000), "1.01亿")
            self.assertEqual(format_amount_cn(-100500000), "-1.01亿")


    if __name__ == "__main__":
        unittest.main()
''')

LIB = Lib(
    name="cnid", lang="python", title="`cnid`",
    blurb="某社区医院的挂号系统用这个库校验居民身份证号码，并把金额写成“万”“亿”的口语形式。",
    files={"cnid/__init__.py": "from .core import *  # noqa: F401,F403\n", "cnid/core.py": SRC,
           "README.md": README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_jichu.py": VISIBLE},
    hidden_tests={"tests/test_quanbu.py": HIDDEN},
    mutate=["cnid/core.py"], difficulty=3, tags=["validation", "checksum", "unicode", "formatting"],
    probes=[
        'valid_id("11010519491231002X")',
        'valid_id("11010519491231002x")',
        'valid_id("110101199003070012")',
        'valid_id("110101199003070011", today=date(1990, 3, 6))',
        'parse_id("11010119900307002X")',
        'parse_id("910000197506150337")["gender"]',
        'mask_id("110101199003070011")',
        'upgrade_15("110105491231002")',
        'upgrade_15("310101871231001")',
        'format_amount_cn(12345)',
        'format_amount_cn(99999999)',
        'format_amount_cn(10050)',
        'format_amount_cn(-123456789)',
        'format_amount_cn(10 ** 12)',
    ],
    probe_import="from datetime import date\nfrom cnid import *",
)

register_native(LIB, "zh", "fix-cnid", n=9,
                summary="native: injected bugs in a Chinese ID-number/amount library, reports in Chinese")
