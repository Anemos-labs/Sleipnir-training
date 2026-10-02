"""Native bug-fix family in Russian: plural forms, number/date/duration formatting, name shortening (python)."""
from fx import Lib, dd

from ._native import register_native

README = dd('''
    # ruformat

    Помощники форматирования для русскоязычного интерфейса магазина: склонение слов после числа, числа, даты,
    длительности и сокращённые имена. Всё без внешних зависимостей.

    ## `plural_ru(n, forms) -> str`
    Выбирает форму слова по числу `n`. `forms` — кортеж из трёх форм: для «1», для «2–4» и для «5–0»
    (например, `("файл", "файла", "файлов")`); в другом случае `ValueError`.

    * Целые числа (и вещественные с целым значением, например `2.0`): последняя цифра 1, кроме 11 → первая форма;
      последняя цифра 2, 3, 4, кроме 12, 13, 14 → вторая форма; всё остальное, включая 0 → третья форма.
      Правило применяется к последним двум цифрам числа, поэтому 111 → третья форма, 121 → первая, 112 → третья.
    * Знак числа не важен: `-1` как `1`.
    * Дробные числа (`1.5`, `0.25`) всегда берут вторую форму («1,5 часа»).

    ## `format_number_ru(x, decimals=None) -> str`
    Число в русской записи: целая часть группами по три цифры, разделитель групп — неразрывный пробел `\\u00a0`
    (группировка начинается с 1000, то есть `1\\u00a0000`, но `999`); десятичный разделитель — запятая; минус —
    знак `\\u2212` (не дефис). Целое число выводится без дробной части.

    * `decimals=None`: у вещественного числа выводятся все знаки так, как их печатает `str(x)` (`2.5` → `2,5`,
      `2.0` → `2,0`).
    * `decimals=k`: ровно `k` знаков после запятой, округление «половина вверх» (по модулю: `2.5` с `decimals=0`
      даёт `3`, `-2.5` даёт `\\u22123`), вычисления через `decimal.Decimal(str(x))`.
      Если после округления получился ноль, знак минус не пишется (`-0.004` с `decimals=2` даёт `0,00`).

    ## `count_ru(n, forms) -> str`
    `format_number_ru(n)`, один обычный пробел и `plural_ru(n, forms)`: `count_ru(21, ("файл", "файла", "файлов"))`
    → `"21 файл"`.

    ## `duration_ru(seconds) -> str`
    Длительность в днях, часах, минутах и секундах, только ненулевые части, через пробел, каждая с правильной формой
    слова: дни (`день`, `дня`, `дней`), часы (`час`, `часа`, `часов`), минуты (`минута`, `минуты`, `минут`), секунды
    (`секунда`, `секунды`, `секунд`). Дольше суток не переводится в недели. `0` → `"0 секунд"`. Отрицательное число
    или нецелое → `ValueError`. Пример: `93784` → `"1 день 2 часа 3 минуты 4 секунды"`.

    ## `date_ru(d, with_year=True) -> str`
    Дата с месяцем в родительном падеже и без ведущего нуля у дня: `date_ru(date(2026, 3, 5))` →
    `"5 марта 2026 г."`; с `with_year=False` → `"5 марта"`. Месяцы: января, февраля, марта, апреля, мая, июня, июля,
    августа, сентября, октября, ноября, декабря.

    ## `short_name_ru(full) -> str`
    Сокращает «Фамилия Имя Отчество» до «Фамилия И. О.»: `"Иванов Иван Иванович"` → `"Иванов И. И."`; без отчества
    `"Иванов Иван"` → `"Иванов И."`; одно слово возвращается как есть. Части между пробелами; лишние пробелы
    игнорируются. Двойное имя через дефис сокращается по частям: `"Петров Анна-Мария Сергеевна"` →
    `"Петров А.-М. С."`. Больше трёх слов или пустая строка → `ValueError`.

    ## `search_key_ru(s) -> str`
    Ключ для поиска без учёта регистра, буквы «ё» и лишних пробелов: сначала `str.casefold()`, затем `ё` → `е`,
    затем пробельные последовательности (в том числе в начале и в конце) схлопываются до одного пробела, края
    обрезаются.
''')

SRC = dd('''
    from datetime import date
    from decimal import ROUND_HALF_UP, Decimal

    NBSP = "\\u00a0"
    MINUS = "\\u2212"

    _MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября",
               "декабря"]
    _DURATION = [
        (86400, ("день", "дня", "дней")),
        (3600, ("час", "часа", "часов")),
        (60, ("минута", "минуты", "минут")),
        (1, ("секунда", "секунды", "секунд")),
    ]


    def plural_ru(n, forms) -> str:
        if len(forms) != 3:
            raise ValueError("forms must have three entries")
        if isinstance(n, float) and not n.is_integer():
            return forms[1]
        n = abs(int(n))
        last, last2 = n % 10, n % 100
        if last == 1 and last2 != 11:
            return forms[0]
        if 2 <= last <= 4 and not 12 <= last2 <= 14:
            return forms[1]
        return forms[2]


    def _group(digits: str) -> str:
        if len(digits) <= 3:
            return digits
        head = len(digits) % 3
        parts = [digits[:head]] if head else []
        parts += [digits[i:i + 3] for i in range(head, len(digits), 3)]
        return NBSP.join(parts)


    def format_number_ru(x, decimals=None) -> str:
        if isinstance(x, int):
            text = str(abs(x))
            neg = x < 0
        elif decimals is None:
            text = str(abs(x))
            neg = x < 0
        else:
            d = Decimal(str(abs(x))).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
            text = format(d, "f")
            neg = x < 0 and d != 0
        if decimals is not None and isinstance(x, int):
            text = text + ("." + "0" * decimals if decimals else "")
        whole, _, frac = text.partition(".")
        out = _group(whole)
        if frac:
            out += "," + frac
        return (MINUS if neg else "") + out


    def count_ru(n, forms) -> str:
        return format_number_ru(n) + " " + plural_ru(n, forms)


    def duration_ru(seconds) -> str:
        if isinstance(seconds, float) and not seconds.is_integer():
            raise ValueError("seconds must be an integer")
        seconds = int(seconds)
        if seconds < 0:
            raise ValueError("negative duration")
        if seconds == 0:
            return "0 секунд"
        parts = []
        for size, forms in _DURATION:
            q, seconds = divmod(seconds, size)
            if q:
                parts.append("%d %s" % (q, plural_ru(q, forms)))
        return " ".join(parts)


    def date_ru(d: date, with_year: bool = True) -> str:
        text = "%d %s" % (d.day, _MONTHS[d.month - 1])
        if with_year:
            text += " %d г." % d.year
        return text


    def _initial(part: str) -> str:
        return "-".join(p[0].upper() + "." for p in part.split("-") if p)


    def short_name_ru(full: str) -> str:
        words = full.split()
        if not words or len(words) > 3:
            raise ValueError("expected one to three words")
        return " ".join([words[0]] + [_initial(w) for w in words[1:]])


    def search_key_ru(s: str) -> str:
        return " ".join(s.casefold().replace("ё", "е").split())
''')

VISIBLE = dd('''
    import unittest
    from datetime import date

    from ruformat import date_ru, duration_ru, plural_ru


    class Основы(unittest.TestCase):
        def test_plural(self):
            self.assertEqual(plural_ru(3, ("файл", "файла", "файлов")), "файла")

        def test_date(self):
            self.assertEqual(date_ru(date(2026, 3, 5)), "5 марта 2026 г.")

        def test_duration(self):
            self.assertEqual(duration_ru(61), "1 минута 1 секунда")


    if __name__ == "__main__":
        unittest.main()
''')

HIDDEN = dd('''
    import unittest
    from datetime import date

    from ruformat import count_ru, date_ru, duration_ru, format_number_ru, plural_ru, search_key_ru, short_name_ru

    F = ("файл", "файла", "файлов")
    NB = "\\u00a0"
    MN = "\\u2212"


    class Plural(unittest.TestCase):
        def test_first_forms(self):
            for n in (1, 21, 31, 101, 121, 1001, 2021, 1000001):
                self.assertEqual(plural_ru(n, F), "файл", n)

        def test_second_forms(self):
            for n in (2, 3, 4, 22, 23, 24, 102, 104, 122, 1003, 2024):
                self.assertEqual(plural_ru(n, F), "файла", n)

        def test_third_forms(self):
            for n in (0, 5, 6, 9, 10, 11, 12, 13, 14, 15, 19, 20, 25, 30, 100, 111, 112, 113, 114, 211, 1011, 1012, 1014, 5000):
                self.assertEqual(plural_ru(n, F), "файлов", n)

        def test_every_number_up_to_130(self):
            for n in range(0, 131):
                last, last2 = n % 10, n % 100
                if last == 1 and last2 != 11:
                    want = "файл"
                elif 2 <= last <= 4 and not (12 <= last2 <= 14):
                    want = "файла"
                else:
                    want = "файлов"
                self.assertEqual(plural_ru(n, F), want, n)

        def test_negative(self):
            self.assertEqual(plural_ru(-1, F), "файл")
            self.assertEqual(plural_ru(-2, F), "файла")
            self.assertEqual(plural_ru(-5, F), "файлов")
            self.assertEqual(plural_ru(-11, F), "файлов")
            self.assertEqual(plural_ru(-21, F), "файл")

        def test_fractions_take_second_form(self):
            for x in (1.5, 0.25, 2.5, 5.5, 11.5, 21.1, 0.1, -1.5):
                self.assertEqual(plural_ru(x, F), "файла", x)

        def test_whole_floats_like_ints(self):
            self.assertEqual(plural_ru(1.0, F), "файл")
            self.assertEqual(plural_ru(2.0, F), "файла")
            self.assertEqual(plural_ru(5.0, F), "файлов")
            self.assertEqual(plural_ru(11.0, F), "файлов")
            self.assertEqual(plural_ru(21.0, F), "файл")

        def test_bad_forms(self):
            for forms in (("файл", "файла"), ("а", "б", "в", "г"), ()):
                with self.assertRaises(ValueError):
                    plural_ru(1, forms)


    class FormatNumber(unittest.TestCase):
        def test_integers(self):
            self.assertEqual(format_number_ru(0), "0")
            self.assertEqual(format_number_ru(7), "7")
            self.assertEqual(format_number_ru(999), "999")
            self.assertEqual(format_number_ru(1000), "1" + NB + "000")
            self.assertEqual(format_number_ru(12345), "12" + NB + "345")
            self.assertEqual(format_number_ru(123456), "123" + NB + "456")
            self.assertEqual(format_number_ru(1234567), "1" + NB + "234" + NB + "567")
            self.assertEqual(format_number_ru(1000000), "1" + NB + "000" + NB + "000")

        def test_negative_uses_minus_sign(self):
            self.assertEqual(format_number_ru(-5), MN + "5")
            self.assertEqual(format_number_ru(-1234), MN + "1" + NB + "234")
            self.assertEqual(format_number_ru(-2.5), MN + "2,5")

        def test_floats_without_decimals_argument(self):
            self.assertEqual(format_number_ru(2.5), "2,5")
            self.assertEqual(format_number_ru(2.0), "2,0")
            self.assertEqual(format_number_ru(1234.5), "1" + NB + "234,5")
            self.assertEqual(format_number_ru(0.125), "0,125")

        def test_decimals(self):
            self.assertEqual(format_number_ru(1234.5, 2), "1" + NB + "234,50")
            self.assertEqual(format_number_ru(3.14159, 2), "3,14")
            self.assertEqual(format_number_ru(3.145, 2), "3,15")
            self.assertEqual(format_number_ru(2.5, 0), "3")
            self.assertEqual(format_number_ru(0.5, 0), "1")
            self.assertEqual(format_number_ru(1.005, 2), "1,01")
            self.assertEqual(format_number_ru(2.0, 1), "2,0")
            self.assertEqual(format_number_ru(1999.999, 2), "2" + NB + "000,00")

        def test_decimals_negative(self):
            self.assertEqual(format_number_ru(-2.5, 0), MN + "3")
            self.assertEqual(format_number_ru(-1234.567, 1), MN + "1" + NB + "234,6")
            self.assertEqual(format_number_ru(-0.004, 2), "0,00")

        def test_decimals_with_int(self):
            self.assertEqual(format_number_ru(5, 2), "5,00")
            self.assertEqual(format_number_ru(-1500, 1), MN + "1" + NB + "500,0")
            self.assertEqual(format_number_ru(5, 0), "5")


    class Count(unittest.TestCase):
        def test_count(self):
            self.assertEqual(count_ru(1, F), "1 файл")
            self.assertEqual(count_ru(2, F), "2 файла")
            self.assertEqual(count_ru(5, F), "5 файлов")
            self.assertEqual(count_ru(21, F), "21 файл")
            self.assertEqual(count_ru(1234, F), "1" + NB + "234 файла")
            self.assertEqual(count_ru(1.5, ("час", "часа", "часов")), "1,5 часа")
            self.assertEqual(count_ru(-3, F), MN + "3 файла")
            self.assertEqual(count_ru(0, F), "0 файлов")


    class Duration(unittest.TestCase):
        def test_examples(self):
            self.assertEqual(duration_ru(93784), "1 день 2 часа 3 минуты 4 секунды")
            self.assertEqual(duration_ru(0), "0 секунд")
            self.assertEqual(duration_ru(1), "1 секунда")
            self.assertEqual(duration_ru(60), "1 минута")
            self.assertEqual(duration_ru(3600), "1 час")
            self.assertEqual(duration_ru(86400), "1 день")

        def test_zero_parts_skipped(self):
            self.assertEqual(duration_ru(3601), "1 час 1 секунда")
            self.assertEqual(duration_ru(86460), "1 день 1 минута")
            self.assertEqual(duration_ru(7200), "2 часа")
            self.assertEqual(duration_ru(300), "5 минут")

        def test_plural_forms(self):
            self.assertEqual(duration_ru(11 * 86400 + 12 * 3600 + 14 * 60 + 11), "11 дней 12 часов 14 минут 11 секунд")
            self.assertEqual(duration_ru(21 * 3600 + 22 * 60 + 23), "21 час 22 минуты 23 секунды")
            self.assertEqual(duration_ru(5 * 86400 + 4 * 3600 + 5 * 60 + 2), "5 дней 4 часа 5 минут 2 секунды")

        def test_no_weeks(self):
            self.assertEqual(duration_ru(30 * 86400), "30 дней")
            self.assertEqual(duration_ru(100 * 86400 + 1), "100 дней 1 секунда")

        def test_whole_float(self):
            self.assertEqual(duration_ru(61.0), "1 минута 1 секунда")

        def test_invalid(self):
            for bad in (-1, -3600, 1.5, 0.5):
                with self.assertRaises(ValueError):
                    duration_ru(bad)


    class Dates(unittest.TestCase):
        def test_months(self):
            names = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября", "декабря"]
            for m, name in enumerate(names, 1):
                self.assertEqual(date_ru(date(2025, m, 15)), "15 %s 2025 г." % name)
                self.assertEqual(date_ru(date(2025, m, 15), with_year=False), "15 " + name)

        def test_no_leading_zero(self):
            self.assertEqual(date_ru(date(2026, 3, 5)), "5 марта 2026 г.")
            self.assertEqual(date_ru(date(2026, 12, 1), with_year=False), "1 декабря")
            self.assertEqual(date_ru(date(2026, 12, 31)), "31 декабря 2026 г.")

        def test_year_not_padded(self):
            self.assertEqual(date_ru(date(999, 1, 2)), "2 января 999 г.")


    class ShortName(unittest.TestCase):
        def test_three_words(self):
            self.assertEqual(short_name_ru("Иванов Иван Иванович"), "Иванов И. И.")
            self.assertEqual(short_name_ru("Ёлкин Пётр Сергеевич"), "Ёлкин П. С.")

        def test_two_words(self):
            self.assertEqual(short_name_ru("Иванов Иван"), "Иванов И.")

        def test_one_word(self):
            self.assertEqual(short_name_ru("Иванов"), "Иванов")

        def test_spaces(self):
            self.assertEqual(short_name_ru("  Иванов   Иван  Иванович "), "Иванов И. И.")

        def test_hyphen(self):
            self.assertEqual(short_name_ru("Петров Анна-Мария Сергеевна"), "Петров А.-М. С.")
            self.assertEqual(short_name_ru("Петров-Водкин Кузьма"), "Петров-Водкин К.")

        def test_lowercase_input_initials_uppercase(self):
            self.assertEqual(short_name_ru("иванов иван иванович"), "иванов И. И.")

        def test_invalid(self):
            for bad in ("", "   ", "а б в г"):
                with self.assertRaises(ValueError):
                    short_name_ru(bad)


    class SearchKey(unittest.TestCase):
        def test_case_and_yo(self):
            self.assertEqual(search_key_ru("Ёлка"), "елка")
            self.assertEqual(search_key_ru("ПЁТР"), "петр")
            self.assertEqual(search_key_ru("Всё"), "все")

        def test_whitespace(self):
            self.assertEqual(search_key_ru("  Иван   Иванов \\t"), "иван иванов")
            self.assertEqual(search_key_ru("а\\nб"), "а б")
            self.assertEqual(search_key_ru("   "), "")

        def test_casefold(self):
            self.assertEqual(search_key_ru("Straße"), "strasse")

        def test_equal_keys(self):
            self.assertEqual(search_key_ru("Пётр  Первый"), search_key_ru("петр первый"))


    if __name__ == "__main__":
        unittest.main()
''')

LIB = Lib(
    name="ruformat", lang="python", title="`ruformat`",
    blurb="Интернет-магазин использует эти функции, чтобы выводить числа, даты и длительности в интерфейсе по-русски.",
    files={"ruformat/__init__.py": "from .core import *  # noqa: F401,F403\n", "ruformat/core.py": SRC,
           "README.md": README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_osnovy.py": VISIBLE},
    hidden_tests={"tests/test_polnyj.py": HIDDEN},
    mutate=["ruformat/core.py"], difficulty=3, tags=["i18n", "plurals", "formatting"],
    probes=[
        'plural_ru(11, ("файл", "файла", "файлов"))',
        'plural_ru(121, ("файл", "файла", "файлов"))',
        'plural_ru(112, ("файл", "файла", "файлов"))',
        'plural_ru(1.5, ("файл", "файла", "файлов"))',
        'plural_ru(-21, ("файл", "файла", "файлов"))',
        'format_number_ru(1234567)',
        'format_number_ru(-2.5)',
        'format_number_ru(3.145, 2)',
        'format_number_ru(-2.5, 0)',
        'format_number_ru(5, 2)',
        'duration_ru(93784)',
        'duration_ru(86460)',
        'duration_ru(0)',
        'date_ru(date(2026, 3, 5))',
        'short_name_ru("Петров Анна-Мария Сергеевна")',
        'search_key_ru("  Пётр   Первый ")',
    ],
    probe_import="from datetime import date\nfrom ruformat import *",
)

register_native(LIB, "ru", "fix-ruformat", n=9,
                summary="native: injected bugs in a Russian plural/number/date formatting library, reports in Russian")
