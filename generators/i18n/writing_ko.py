"""Native constrained-writing tasks in Korean (polite speech endings, no hanja or Latin letters, syllable budgets)."""
from fx import family

from ._writing import writing_task

TERMS = ".?!"
POLITE = ["니다", "요"]


def phrase_sentences(p):
    return ("문장은 정확히 %d개" % p["min"] if p["min"] == p["max"] else "문장은 %d~%d개" % (p["min"], p["max"])) + "(., ?, ! 로 끝나는 것을 한 문장으로 셈)"


PH = {
    "sentences": phrase_sentences,
    "syllables": lambda p: "한글 음절(글자) 수는 모두 합쳐 %d~%d자" % (p["min"], p["max"]),
    "include": lambda p: "다음 표현을 그대로 넣기: " + ", ".join("'%s'" % w for w in p["words"]),
    "exclude": lambda p: "다음 표현은 쓰지 않기: " + ", ".join("'%s'" % w for w in p["words"]),
    "no_han": lambda p: "한자는 쓰지 않기",
    "no_latin": lambda p: "알파벳(영문자)은 쓰지 않기",
    "endings": lambda p: "모든 문장을 존댓말로 끝내기(문장의 마지막이 '니다' 또는 '요')",
    "bullets": lambda p: "정확히 %d줄의 목록(각 줄은 '- ' 로 시작, 제목이 있으면 제목 줄 외에 다른 글은 쓰지 않기)" % p["n"],
    "title": lambda p: "첫 줄은 '# ' 로 시작하는 제목",
}


def render(constraints):
    return "\n".join("- " + PH[c["kind"]](c) for c in constraints if c["kind"] in PH)


def sent(lo, hi):
    return {"kind": "sentences", "min": lo, "max": hi, "terms": TERMS}


SCENARIOS = [
    ("01-elevator-gongji", 3,
     "아파트 게시판에 붙일 엘리베이터 점검 공지를 써 주세요. 필요한 내용은 `jeongbo.txt` 에 있어요.",
     "내용: 엘리베이터 정기 점검\n일시: 6월 3일 화요일 오전 10시부터 오후 2시까지\n대상: 101동 엘리베이터 두 대 모두\n대안: 비상계단 이용, 1층 관리실에서 도움\n",
     "gongji.md",
     [sent(3, 4), {"kind": "endings", "endings": POLITE, "terms": TERMS}, {"kind": "no_latin"}, {"kind": "include", "words": ["엘리베이터", "오전 10시"]},
      {"kind": "syllables", "min": 50, "max": 140}],
     "101동 엘리베이터 정기 점검 안내입니다. 6월 3일 화요일 오전 10시부터 오후 2시까지 엘리베이터 두 대를 모두 사용하실 수 없습니다. "
     "불편하시겠지만 비상계단을 이용해 주시고, 도움이 필요하시면 1층 관리실로 연락해 주세요."),
    ("02-hoesik-annae", 2,
     "팀 단톡방에 올릴 회식 안내 메시지를 써 주세요. 정보는 `jeongbo.txt` 에 정리해 뒀어요.",
     "행사: 팀 회식\n요일과 시간: 금요일 저녁 7시\n장소: 역 앞 한식집 '소담'\n회비: 인당 2만 원\n참석 확인: 수요일까지\n",
     "annae.md",
     [sent(3, 4), {"kind": "endings", "endings": POLITE, "terms": TERMS}, {"kind": "include", "words": ["금요일", "7시"]}, {"kind": "exclude", "words": ["!", "강제"]},
      {"kind": "syllables", "min": 45, "max": 130}],
     "이번 주 금요일 저녁 7시에 역 앞 한식집 소담에서 팀 회식이 있어요. 회비는 인당 2만 원이에요. 수요일까지 참석 여부를 알려 주세요."),
    ("03-hwanbul-yocheong", 3,
     "온라인 쇼핑몰에 보낼 정중한 환불 요청 메일 본문을 써 주세요. 주문 정보는 `jeongbo.txt` 에 있습니다.",
     "주문번호: 20250311-07\n상품: 무선 청소기\n문제: 받았는데 충전이 안 됨\n희망 처리: 전액 환불\n",
     "mail.md",
     [sent(5, 6), {"kind": "endings", "endings": POLITE, "terms": TERMS}, {"kind": "include", "words": ["환불", "20250311-07"]}, {"kind": "no_han"}, {"kind": "no_latin"},
      {"kind": "syllables", "min": 70, "max": 170}],
     "안녕하세요. 주문번호 20250311-07로 구매한 무선 청소기에 대해 환불을 요청드립니다. 제품을 받아 보니 충전이 전혀 되지 않아 사용할 수 없습니다. "
     "교환보다는 전액 환불을 원합니다. 반품 절차를 안내해 주시면 바로 따르겠습니다. 빠른 답변 부탁드립니다."),
    ("04-sangpum-mokrok", 3,
     "무선 이어폰 상세 페이지에 넣을 특징을 제목과 함께 목록으로 정리해 주세요. 사양은 `jeongbo.txt` 에 있어요.",
     "제품명: 소리샘 무선 이어폰\n배터리: 이어폰 6시간, 케이스 포함 24시간\n충전: C타입, 10분 충전에 1시간 재생\n방수: 생활방수\n무게: 한쪽 4.5그램\n",
     "mokrok.md",
     [{"kind": "title"}, {"kind": "bullets", "n": 4}, {"kind": "include", "words": ["무선", "충전"]}, {"kind": "no_latin"}, {"kind": "syllables", "min": 40, "max": 120}],
     "# 소리샘 무선 이어폰\n- 이어폰만 6시간, 케이스까지 쓰면 24시간 들을 수 있어요.\n- 10분만 충전해도 1시간 동안 재생돼요.\n- 생활방수가 되어 가벼운 비에도 걱정 없어요.\n"
     "- 한쪽 무게가 4.5그램이라 오래 끼고 있어도 편해요."),
    ("05-aleumjang", 3,
     "어린이집 알림장에 쓸 오늘의 소식을 학부모님께 쓰는 글로 작성해 주세요. 오늘 있었던 일은 `jeongbo.txt` 에 있어요.",
     "활동: 봄 산책\n장소: 어린이집 옆 작은 공원\n간식: 삶은 고구마\n특이사항: 지호가 낮잠을 잘 잤음\n내일 준비물: 여벌 옷\n",
     "aleumjang.md",
     [sent(3, 4), {"kind": "endings", "endings": POLITE, "terms": TERMS}, {"kind": "no_han"}, {"kind": "include", "words": ["산책", "여벌 옷"]},
      {"kind": "syllables", "min": 50, "max": 130}],
     "오늘은 어린이집 옆 작은 공원으로 봄 산책을 다녀왔습니다. 간식으로 삶은 고구마를 맛있게 먹었고, 지호는 낮잠도 잘 잤어요. "
     "내일은 여벌 옷을 챙겨서 보내 주세요."),
    ("06-hanjul-hugi", 2,
     "배송이 빨랐던 가게에 남길 한 줄 후기를 써 주세요. 내용은 `jeongbo.txt` 를 참고하세요.",
     "가게: 달빛 문구점\n주문일: 월요일 저녁\n도착: 화요일 오전\n포장: 꼼꼼함\n",
     "hugi.md",
     [sent(2, 2), {"kind": "syllables", "min": 25, "max": 70}, {"kind": "include", "words": ["배송"]}, {"kind": "exclude", "words": ["최악", "별로"]},
      {"kind": "endings", "endings": POLITE, "terms": TERMS}, {"kind": "no_latin"}],
     "월요일 저녁에 주문했는데 화요일 오전에 도착했어요. 배송도 빠르고 포장도 꼼꼼해서 만족합니다."),
]


@family("i18n-ko-write-notices", category="i18n", lang="text", kind="feature", n=len(SCENARIOS), mode="fixture",
        summary="native: Korean constrained-writing tasks (polite endings, no hanja/Latin letters, syllable budgets) checked by a hidden script")
def ko_write(rng, n):
    voices = [
        "{intro}\n\n조건:\n{rules}\n\n결과는 `{path}` 에 저장해 주세요.",
        "{intro} 글의 조건은 다음과 같아요.\n{rules}\n`{path}` 에 써 주세요.",
        "{intro}\n\n{rules}\n\n(작성한 글은 `{path}` 로 부탁드려요.)",
    ]
    for i, (slug, d, intro, facts, path, constraints, solution) in enumerate(SCENARIOS[:n]):
        prompt = voices[i % 3].format(intro=intro, rules=render(constraints), path=path)
        yield writing_task(slug, d, prompt, {"jeongbo.txt": facts}, path, constraints, solution, ["ko"], {"prompt_lang": "ko", "constraints": [c["kind"] for c in constraints]})
