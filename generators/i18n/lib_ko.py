"""Native bug-fix family in Korean: josa selection, Hangul jamo decomposition and choseong search (python)."""
from fx import Lib, dd

from ._native import register_native

README = dd('''
    # josa

    한국어 알림 메시지를 만드는 쇼핑몰 백엔드용 작은 도우미입니다. 받침에 따라 조사를 고르고, 한글 음절을 자모로
    나누고, 초성 검색을 합니다. 표준 라이브러리만 씁니다.

    ## 받침

    ### `has_batchim(word) -> bool`
    `word`의 **마지막 글자**를 읽었을 때 받침이 있으면 `True`입니다. 뒤쪽의 글자·숫자가 아닌 문자(공백, 따옴표, 괄호,
    마침표 등)는 건너뛰고, 남은 것의 마지막 문자로 판단합니다.

    * 한글 음절(`가`–`힣`): 종성이 있으면 `True`.
    * 숫자는 한자어 읽기를 따릅니다: `0` 영, `1` 일, `3` 삼, `6` 육, `7` 칠, `8` 팔은 받침 있음, `2` 이, `4` 사, `5` 오, `9` 구는
      받침 없음.
    * 영문자는 글자 이름으로 판단합니다(대소문자 구분 없음): `L` 엘, `M` 엠, `N` 엔, `R` 알은 받침 있음, 나머지 모든
      알파벳은 받침 없음.
    * 글자나 숫자가 하나도 없으면(`""`, `"..."`, 한글·ASCII 밖의 문자만 있는 경우 포함) `ValueError`.

    ## 조사

    ### `with_josa(word, kind) -> str`
    `word` 바로 뒤에 조사를 붙여 돌려줍니다(공백 없이, `word` 전체 뒤에). `kind`는 다음 중 하나이며, 그 밖의 값은
    `ValueError`입니다. 받침이 있으면 앞의 형태, 없으면 뒤의 형태를 씁니다.

    | `kind` | 받침 있음 | 받침 없음 |
    |---|---|---|
    | `"은/는"` | 은 | 는 |
    | `"이/가"` | 이 | 가 |
    | `"을/를"` | 을 | 를 |
    | `"와/과"` | **과** | **와** |
    | `"으로/로"` | 으로 | 로 |
    | `"이나/나"` | 이나 | 나 |
    | `"이랑/랑"` | 이랑 | 랑 |

    (`"와/과"`는 받침이 있을 때 `과`, 없을 때 `와`입니다.) `"으로/로"`에는 예외가 하나 있습니다. 마지막 글자의 받침이
    `ㄹ`이면 받침이 있어도 `로`를 씁니다(`서울로`, `부산으로`). 숫자 `1` `7` `8`(일, 칠, 팔)과 영문자 `L` `R`(엘, 알)도 `ㄹ`
    받침으로 취급합니다(`1로`, `6으로`, `M으로`, `L로`).

    ## 자모

    ### `decompose(syllable) -> tuple`
    한글 음절 한 글자를 `(초성, 중성, 종성)`으로 나눕니다. 자모는 호환 자모(`ㄱ`, `ㅏ`, ...)이고, 종성이 없으면 빈 문자열
    `""`입니다. `"한"` → `("ㅎ", "ㅏ", "ㄴ")`, `"가"` → `("ㄱ", "ㅏ", "")`, `"값"` → `("ㄱ", "ㅏ", "ㅄ")`.
    초성은 `ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ`, 중성은 `ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ`, 종성은 `ㄱ ㄲ ㄳ ㄴ ㄵ ㄶ ㄷ
    ㄹ ㄺ ㄻ ㄼ ㄽ ㄾ ㄿ ㅀ ㅁ ㅂ ㅄ ㅅ ㅆ ㅇ ㅈ ㅊ ㅋ ㅌ ㅍ ㅎ` 순서입니다(음절 번호 = `(초성 순번 × 21 + 중성 순번) × 28 + 종성 순번`,
    종성 순번 0은 없음). 글자가 한 글자의 한글 음절이 아니면 `ValueError`.

    ### `compose(cho, jung, jong="") -> str`
    `decompose`의 반대. 자모가 위 목록에 없으면 `ValueError`.

    ### `decompose_text(s) -> str`
    문자열의 한글 음절을 모두 자모 나열로 바꾸고 다른 문자는 그대로 둡니다. `"한글 abc"` → `"ㅎㅏㄴㄱㅡㄹ abc"`.

    ## 초성 검색

    ### `choseong_of(s) -> str`
    한글 음절은 초성 한 글자로, 그 밖의 문자는 그대로 바꿉니다. `"한글 사전"` → `"ㅎㄱ ㅅㅈ"`.

    ### `matches_choseong(query, text) -> bool`
    `query`가 초성 자모(`ㄱ`–`ㅎ` 19자)로만 이루어진 비어 있지 않은 문자열이면, `text`에서 한글 음절만 이어 붙인
    초성열(공백 등은 빼고)에 `query`가 부분 문자열로 들어 있을 때 `True`입니다. 그렇지 않으면(질의가 비었거나 초성이 아닌 문자를
    포함) `ValueError`.
''')

SRC = dd('''
    _CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
    _JUNG = "ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ"
    _JONG = ["", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ", "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ", "ㅆ",
             "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]
    _DIGIT_BATCHIM = {"0": True, "1": True, "2": False, "3": True, "4": False, "5": False, "6": True, "7": True, "8": True, "9": False}
    _LETTER_BATCHIM = set("LMNR")
    _RIEUL_DIGITS = set("178")
    _RIEUL_LETTERS = set("LR")
    PAIRS = {
        "은/는": ("은", "는"), "이/가": ("이", "가"), "을/를": ("을", "를"), "와/과": ("과", "와"),
        "으로/로": ("으로", "로"), "이나/나": ("이나", "나"), "이랑/랑": ("이랑", "랑"),
    }


    def _is_syllable(ch: str) -> bool:
        return len(ch) == 1 and "\\uac00" <= ch <= "\\ud7a3"


    def _core_last(word: str) -> str:
        for ch in reversed(word):
            if _is_syllable(ch) or ch in "0123456789" or (ch.isascii() and ch.isalpha()):
                return ch
        raise ValueError("no letter or digit in %r" % (word,))


    def has_batchim(word: str) -> bool:
        ch = _core_last(word)
        if _is_syllable(ch):
            return (ord(ch) - 0xAC00) % 28 != 0
        if ch in "0123456789":
            return _DIGIT_BATCHIM[ch]
        return ch.upper() in _LETTER_BATCHIM


    def _ends_in_rieul(word: str) -> bool:
        ch = _core_last(word)
        if _is_syllable(ch):
            return (ord(ch) - 0xAC00) % 28 == 8
        if ch in "0123456789":
            return ch in _RIEUL_DIGITS
        return ch.upper() in _RIEUL_LETTERS


    def with_josa(word: str, kind: str) -> str:
        if kind not in PAIRS:
            raise ValueError("unknown josa kind: %r" % (kind,))
        with_batchim, without = PAIRS[kind]
        if kind == "으로/로":
            particle = without if (not has_batchim(word) or _ends_in_rieul(word)) else with_batchim
        else:
            particle = with_batchim if has_batchim(word) else without
        return word + particle


    def decompose(syllable: str) -> tuple:
        if not _is_syllable(syllable):
            raise ValueError("not a Hangul syllable: %r" % (syllable,))
        n = ord(syllable) - 0xAC00
        return (_CHO[n // 588], _JUNG[(n % 588) // 28], _JONG[n % 28])


    def compose(cho: str, jung: str, jong: str = "") -> str:
        if len(cho) != 1 or cho not in _CHO or len(jung) != 1 or jung not in _JUNG or jong not in _JONG:
            raise ValueError("invalid jamo")
        return chr(0xAC00 + (_CHO.index(cho) * 21 + _JUNG.index(jung)) * 28 + _JONG.index(jong))


    def decompose_text(s: str) -> str:
        return "".join("".join(decompose(ch)) if _is_syllable(ch) else ch for ch in s)


    def choseong_of(s: str) -> str:
        return "".join(decompose(ch)[0] if _is_syllable(ch) else ch for ch in s)


    def matches_choseong(query: str, text: str) -> bool:
        if not query or any(ch not in _CHO for ch in query):
            raise ValueError("query must consist of choseong jamo")
        return query in "".join(decompose(ch)[0] for ch in text if _is_syllable(ch))
''')

VISIBLE = dd('''
    import unittest

    from josa import decompose, has_batchim, with_josa


    class 기본(unittest.TestCase):
        def test_batchim(self):
            self.assertTrue(has_batchim("책"))
            self.assertFalse(has_batchim("사과"))

        def test_josa(self):
            self.assertEqual(with_josa("사과", "을/를"), "사과를")

        def test_decompose(self):
            self.assertEqual(decompose("한"), ("ㅎ", "ㅏ", "ㄴ"))


    if __name__ == "__main__":
        unittest.main()
''')

HIDDEN = dd('''
    import unittest

    from josa import compose, choseong_of, decompose, decompose_text, has_batchim, matches_choseong, with_josa


    class Batchim(unittest.TestCase):
        def test_hangul(self):
            for w in ("책", "한글", "서울", "부산", "집", "값", "닭", "읽", "강", "밖", "앉"):
                self.assertTrue(has_batchim(w), w)
            for w in ("사과", "학교", "나", "의", "개", "뭐", "아이", "커피"):
                self.assertFalse(has_batchim(w), w)

        def test_only_last_character_counts(self):
            self.assertFalse(has_batchim("책상자"))
            self.assertTrue(has_batchim("사과책"))

        def test_digits(self):
            for d in "013678":
                self.assertTrue(has_batchim(d), d)
            for d in "2459":
                self.assertFalse(has_batchim(d), d)
            self.assertTrue(has_batchim("100"))
            self.assertFalse(has_batchim("10개"))
            self.assertTrue(has_batchim("10년"))
            self.assertTrue(has_batchim("3월"))
            self.assertTrue(has_batchim("2024년 6"))

        def test_letters(self):
            for c in "LMNRlmnr":
                self.assertTrue(has_batchim(c), c)
            for c in "ABCDEFGHIJKOPQSTUVWXYZabcdefghijkopqstuvwxyz":
                self.assertFalse(has_batchim(c), c)
            self.assertTrue(has_batchim("Seoul"))
            self.assertFalse(has_batchim("Cafe"))
            self.assertTrue(has_batchim("Busan"))
            self.assertTrue(has_batchim("PC방"))
            self.assertFalse(has_batchim("방PC"))

        def test_trailing_non_letters_skipped(self):
            self.assertTrue(has_batchim('"서울"'))
            self.assertFalse(has_batchim("(사과)"))
            self.assertTrue(has_batchim("책!?"))
            self.assertTrue(has_batchim("책 "))
            self.assertFalse(has_batchim("사과..."))
            self.assertTrue(has_batchim("「한글」"))
            self.assertTrue(has_batchim("3."))
            self.assertTrue(has_batchim("[L]"))

        def test_no_letter(self):
            for w in ("", " ", "...", "()", "!?", "日本語", "ㄱㄴ", "é"):
                with self.assertRaises(ValueError, msg=repr(w)):
                    has_batchim(w)

        def test_boundaries_of_hangul_block(self):
            self.assertFalse(has_batchim("가"))
            self.assertTrue(has_batchim("힣"))
            self.assertFalse(has_batchim("히"))


    class Josa(unittest.TestCase):
        def test_topic(self):
            self.assertEqual(with_josa("사과", "은/는"), "사과는")
            self.assertEqual(with_josa("책", "은/는"), "책은")

        def test_subject(self):
            self.assertEqual(with_josa("서울", "이/가"), "서울이")
            self.assertEqual(with_josa("부산", "이/가"), "부산이")

        def test_object(self):
            self.assertEqual(with_josa("사과", "을/를"), "사과를")
            self.assertEqual(with_josa("책", "을/를"), "책을")

        def test_with(self):
            self.assertEqual(with_josa("사과", "와/과"), "사과와")
            self.assertEqual(with_josa("책", "와/과"), "책과")

        def test_direction(self):
            self.assertEqual(with_josa("부산", "으로/로"), "부산으로")
            self.assertEqual(with_josa("집", "으로/로"), "집으로")
            self.assertEqual(with_josa("학교", "으로/로"), "학교로")
            self.assertEqual(with_josa("서울", "으로/로"), "서울로")
            self.assertEqual(with_josa("지하철", "으로/로"), "지하철로")
            self.assertEqual(with_josa("물", "으로/로"), "물로")
            self.assertEqual(with_josa("연필", "으로/로"), "연필로")

        def test_direction_digits_and_letters(self):
            self.assertEqual(with_josa("1", "으로/로"), "1로")
            self.assertEqual(with_josa("6", "으로/로"), "6으로")
            self.assertEqual(with_josa("7", "으로/로"), "7로")
            self.assertEqual(with_josa("8", "으로/로"), "8로")
            self.assertEqual(with_josa("3", "으로/로"), "3으로")
            self.assertEqual(with_josa("0", "으로/로"), "0으로")
            self.assertEqual(with_josa("2", "으로/로"), "2로")
            self.assertEqual(with_josa("L", "으로/로"), "L로")
            self.assertEqual(with_josa("R", "으로/로"), "R로")
            self.assertEqual(with_josa("M", "으로/로"), "M으로")
            self.assertEqual(with_josa("N", "으로/로"), "N으로")
            self.assertEqual(with_josa("A", "으로/로"), "A로")

        def test_or_and_with_colleague(self):
            self.assertEqual(with_josa("사과", "이나/나"), "사과나")
            self.assertEqual(with_josa("책", "이나/나"), "책이나")
            self.assertEqual(with_josa("사과", "이랑/랑"), "사과랑")
            self.assertEqual(with_josa("책", "이랑/랑"), "책이랑")

        def test_digits_and_letters_in_other_kinds(self):
            self.assertEqual(with_josa("3", "은/는"), "3은")
            self.assertEqual(with_josa("2", "이/가"), "2가")
            self.assertEqual(with_josa("A", "을/를"), "A를")
            self.assertEqual(with_josa("K", "이/가"), "K가")
            self.assertEqual(with_josa("Seoul", "이/가"), "Seoul이")
            self.assertEqual(with_josa("PC방", "이/가"), "PC방이")
            self.assertEqual(with_josa("2024년", "은/는"), "2024년은")

        def test_quotes_and_brackets(self):
            self.assertEqual(with_josa('"서울"', "은/는"), '"서울"은')
            self.assertEqual(with_josa("(사과)", "을/를"), "(사과)를")
            self.assertEqual(with_josa("「책」", "와/과"), "「책」과")

        def test_unknown_kind(self):
            for kind in ("", "은", "는/은", "이/가 ", "으로", "을를"):
                with self.assertRaises(ValueError, msg=kind):
                    with_josa("책", kind)

        def test_no_letters(self):
            with self.assertRaises(ValueError):
                with_josa("...", "은/는")
            with self.assertRaises(ValueError):
                with_josa("", "이/가")


    class Jamo(unittest.TestCase):
        def test_decompose(self):
            self.assertEqual(decompose("한"), ("ㅎ", "ㅏ", "ㄴ"))
            self.assertEqual(decompose("가"), ("ㄱ", "ㅏ", ""))
            self.assertEqual(decompose("값"), ("ㄱ", "ㅏ", "ㅄ"))
            self.assertEqual(decompose("힣"), ("ㅎ", "ㅣ", "ㅎ"))
            self.assertEqual(decompose("뛰"), ("ㄸ", "ㅟ", ""))
            self.assertEqual(decompose("읽"), ("ㅇ", "ㅣ", "ㄺ"))
            self.assertEqual(decompose("꽃"), ("ㄲ", "ㅗ", "ㅊ"))
            self.assertEqual(decompose("의"), ("ㅇ", "ㅢ", ""))
            self.assertEqual(decompose("쌍"), ("ㅆ", "ㅏ", "ㅇ"))

        def test_decompose_errors(self):
            for bad in ("", "ab", "a", "ㄱ", "日", "가나", "\\uabff", "\\ud7a4"):
                with self.assertRaises(ValueError, msg=repr(bad)):
                    decompose(bad)

        def test_compose(self):
            self.assertEqual(compose("ㅎ", "ㅏ", "ㄴ"), "한")
            self.assertEqual(compose("ㄱ", "ㅏ"), "가")
            self.assertEqual(compose("ㄱ", "ㅏ", "ㅄ"), "값")
            self.assertEqual(compose("ㅎ", "ㅣ", "ㅎ"), "힣")
            self.assertEqual(compose("ㄸ", "ㅟ"), "뛰")

        def test_compose_errors(self):
            for args in (("a", "ㅏ"), ("ㄱ", "a"), ("ㄱ", "ㅏ", "a"), ("ㄸㄸ", "ㅏ"), ("ㄱ", "ㅏㅏ"), ("ㄱ", "ㅏ", "ㄱㄱ"),
                         ("", "ㅏ"), ("ㄱ", ""), ("ㅄ", "ㅏ")):
                with self.assertRaises(ValueError, msg=repr(args)):
                    compose(*args)

        def test_round_trip_every_syllable(self):
            for code in range(0xAC00, 0xD7A4):
                ch = chr(code)
                self.assertEqual(compose(*decompose(ch)), ch)

        def test_decompose_text(self):
            self.assertEqual(decompose_text("한글 abc"), "ㅎㅏㄴㄱㅡㄹ abc")
            self.assertEqual(decompose_text("값!"), "ㄱㅏㅄ!")
            self.assertEqual(decompose_text(""), "")
            self.assertEqual(decompose_text("日本 1"), "日本 1")
            self.assertEqual(decompose_text("가"), "ㄱㅏ")


    class Choseong(unittest.TestCase):
        def test_choseong_of(self):
            self.assertEqual(choseong_of("한글 사전"), "ㅎㄱ ㅅㅈ")
            self.assertEqual(choseong_of("값 abc 1"), "ㄱ abc 1")
            self.assertEqual(choseong_of("뛰다"), "ㄸㄷ")
            self.assertEqual(choseong_of(""), "")

        def test_matches(self):
            self.assertTrue(matches_choseong("ㅎㄱ", "한글"))
            self.assertTrue(matches_choseong("ㅎㄱ", "대한 글쓰기"))
            self.assertTrue(matches_choseong("ㄱㅅ", "한글 사전"))
            self.assertTrue(matches_choseong("ㅅㅈ", "한글 사전"))
            self.assertTrue(matches_choseong("ㅎㄱㅅㅈ", "한글 사전"))
            self.assertTrue(matches_choseong("ㄱ", "한글"))
            self.assertFalse(matches_choseong("ㄱㅎ", "한글"))
            self.assertFalse(matches_choseong("ㅎㄱㅎ", "한글"))
            self.assertFalse(matches_choseong("ㅂ", "한글"))
            self.assertFalse(matches_choseong("ㅎ", "abc 123"))
            self.assertFalse(matches_choseong("ㅎ", ""))

        def test_spaces_and_others_are_skipped_in_text(self):
            self.assertTrue(matches_choseong("ㅎㄱ", "한 글"))
            self.assertTrue(matches_choseong("ㅎㄱ", "한-글"))
            self.assertTrue(matches_choseong("ㅎㄱ", "한abc글"))
            self.assertTrue(matches_choseong("ㅎㄱ", "한ㄱ글"))

        def test_double_consonant_is_its_own(self):
            self.assertTrue(matches_choseong("ㄸ", "뛰다"))
            self.assertFalse(matches_choseong("ㄷㄷ", "뛰다"))
            self.assertTrue(matches_choseong("ㄸㄷ", "뛰다"))

        def test_bad_query(self):
            for q in ("", "한", "ㅎa", "a", "ㅏ", "ㅎ ㄱ", "ㄳ"):
                with self.assertRaises(ValueError, msg=repr(q)):
                    matches_choseong(q, "한글")


    if __name__ == "__main__":
        unittest.main()
''')

LIB = Lib(
    name="josa", lang="python", title="`josa`",
    blurb="쇼핑몰 백엔드가 이 도우미로 알림 메시지의 조사를 고르고 상품명을 초성으로 검색합니다.",
    files={"josa/__init__.py": "from .core import *  # noqa: F401,F403\n", "josa/core.py": SRC,
           "README.md": README, ".gitignore": "__pycache__/\n*.pyc\n"},
    visible_tests={"tests/test_gibon.py": VISIBLE},
    hidden_tests={"tests/test_jeonche.py": HIDDEN},
    mutate=["josa/core.py"], difficulty=3, tags=["unicode", "hangul", "text"],
    probes=[
        'has_batchim("서울")',
        'has_batchim("3")',
        'has_batchim("Seoul")',
        'has_batchim("(사과)")',
        'with_josa("책", "와/과")',
        'with_josa("서울", "으로/로")',
        'with_josa("6", "으로/로")',
        'with_josa("L", "으로/로")',
        'with_josa("PC방", "이/가")',
        'decompose("값")',
        'decompose("뛰")',
        'compose("ㄱ", "ㅏ", "ㅄ")',
        'decompose_text("한글 abc")',
        'choseong_of("한글 사전")',
        'matches_choseong("ㅎㄱ", "대한 글쓰기")',
        'matches_choseong("ㄸ", "뛰다")',
    ],
    probe_import="from josa import *",
)

register_native(LIB, "ko", "fix-josa", n=9,
                summary="native: injected bugs in a Korean josa/jamo/choseong library, reports in Korean")
