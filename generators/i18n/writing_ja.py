"""Native constrained-writing tasks in Japanese (kana-only text, polite endings, kanji counts, character budgets)."""
from fx import family

from ._writing import writing_task

TERMS = "。！？"
POLITE = ["です", "ます", "ください", "ました", "でした", "ません"]


def phrase_sentences(p):
    return ("ちょうど%d文" % p["min"] if p["min"] == p["max"] else "文の数は%d〜%d文" % (p["min"], p["max"])) + "(「。」「！」「？」で終わるものを1文と数える)"


PH = {
    "sentences": phrase_sentences,
    "chars": lambda p: "全体で%d〜%d文字(空白と改行は数えない)" % (p["min"], p["max"]),
    "kana_only": lambda p: "ひらがなとカタカナだけで書く(漢字・アルファベット・算用数字は使わない。記号は「、」「。」「！」「？」「ー」だけ。リスト記号の - と見出し記号の # は使ってよい)",
    "endings": lambda p: "どの文も丁寧な言い方で終える(文末が " + "・".join("「%s」" % e for e in p["endings"]) + " のどれかになること)",
    "include": lambda p: "次の語句を一字一句そのまま入れる: " + "、".join("「%s」" % w for w in p["words"]),
    "exclude": lambda p: "次の語句は使わない: " + "、".join("「%s」" % w for w in p["words"]),
    "kanji": lambda p: "漢字を%d文字以上使う" % p["min"],
    "bullets": lambda p: "ちょうど%d行の箇条書き(各行を「- 」で始める。タイトルがある場合のタイトル行を除き、ほかの文章は書かない)" % p["n"],
    "title": lambda p: "1行目は「# 」で始まるタイトルにする",
    "no_latin": lambda p: "アルファベットは使わない",
}


def render(constraints):
    return "\n".join("・" + PH[c["kind"]](c) for c in constraints if c["kind"] in PH)


def sent(lo, hi):
    return {"kind": "sentences", "min": lo, "max": hi, "terms": TERMS}


SCENARIOS = [
    ("01-ensoku-oshirase", 3,
     "小学1年生の保護者向けに、遠足のお知らせを書いてください。子どもも読めるように、やさしい書き方でお願いします。必要な情報は `joho.txt` にあります。",
     "行事: 遠足\n日にち: 6月12日(木)\n行き先: 市民公園\n集合: 午前8時30分に校庭\nもちもの: お弁当、水筒、帽子\n",
     "oshirase.md",
     [{"kind": "kana_only"}, sent(3, 5), {"kind": "endings", "endings": POLITE, "terms": TERMS}, {"kind": "include", "words": ["えんそく", "しみんこうえん"]},
      {"kind": "chars", "min": 60, "max": 140}],
     "えんそくの おしらせです。 ろくがつ じゅうににち もくようびに、しみんこうえんへ いきます。 あさ はちじ さんじっぷんに こうていに あつまります。 "
     "おべんとうと すいとうと ぼうしを もってきてください。"),
    ("02-kaigi-henko", 3,
     "会議の日程変更を知らせる社内メールの本文を書いてください(宛名と署名は不要)。変更の内容は `joho.txt` のとおりです。",
     "会議名: 月次営業会議\n元の日程: 5月9日(金)14時\n新しい日程: 5月12日(月)15時\n場所: 会議室B\n理由: 部長の出張\n",
     "mail.md",
     [sent(3, 4), {"kind": "endings", "endings": POLITE, "terms": TERMS}, {"kind": "kanji", "min": 20}, {"kind": "chars", "min": 70, "max": 170},
      {"kind": "include", "words": ["会議室B", "15時"]}, {"kind": "exclude", "words": ["すみません", "!"]}],
     "月次営業会議の日程が変更になりましたので、お知らせいたします。新しい日程は5月12日(月)15時からで、場所は会議室Bです。部長の出張に伴う変更となります。"
     "お忙しいところ恐れ入りますが、ご予定の調整をお願いいたします。"),
    ("03-shohin-setsumei", 3,
     "ネットショップの商品ページ用に、レインコートの紹介文を箇条書きで作ってください。素材などの情報は `joho.txt` に書いてあります。",
     "商品名: そよかぜレインコート\n素材: ナイロン(防水加工)\n重さ: 約180グラム\nたたむと: 手のひらサイズ\n色: ネイビー、イエロー\n",
     "shohin.md",
     [{"kind": "title"}, {"kind": "bullets", "n": 4}, {"kind": "include", "words": ["防水", "そよかぜレインコート"]}, {"kind": "chars", "min": 50, "max": 140},
      {"kind": "exclude", "words": ["最高", "!"]}],
     "# そよかぜレインコート\n- ナイロン素材に防水加工をほどこしています。\n- 重さは約180グラムで、持ち歩いても負担になりません。\n"
     "- たたむと手のひらサイズになり、かばんにすっと入ります。\n- ネイビーとイエローの2色から選べます。"),
    ("04-toshoshitsu-kimari", 2,
     "小学校の図書室に貼る「きまり」を書いてください。低学年の子が読むので、ひらがなとカタカナだけでお願いします。内容のもとは `joho.txt` です。",
     "貸出: 1人2さつまで\n期間: 2週間\n飲食: 禁止\n返すところ: 入口のポスト\n",
     "kimari.md",
     [{"kind": "title"}, {"kind": "bullets", "n": 4}, {"kind": "kana_only"}, {"kind": "include", "words": ["ほん", "ポスト"]}, {"kind": "chars", "min": 40, "max": 120}],
     "# としょしつの きまり\n- ほんは ひとり ふたりさつまで かりられます。\n- かりた ほんは にしゅうかん いないに かえします。\n"
     "- としょしつでは たべたり のんだり しません。\n- かえすときは いりぐちの ポストに いれます。"),
    ("05-orei-jo", 3,
     "お世話になった先生へのお礼状を書いてください。気持ちが伝わる、落ち着いた文章でお願いします。事実関係は `joho.txt` にあります。",
     "相手: 田中先生\n内容: 卒業論文の指導\n時期: 先月で卒業\n今の様子: 4月から設計会社で働いている\n",
     "orei.md",
     [sent(3, 4), {"kind": "endings", "endings": POLITE, "terms": TERMS}, {"kind": "kanji", "min": 25}, {"kind": "include", "words": ["田中先生", "ありがとうございました"]},
      {"kind": "exclude", "words": ["！", "!"]}, {"kind": "chars", "min": 70, "max": 150}],
     "田中先生、卒業論文のご指導をいただき、本当にありがとうございました。先生の的確な助言のおかげで、無事に先月卒業することができました。"
     "現在は4月から設計会社で働いており、毎日学ぶことばかりです。どうぞお体に気をつけてお過ごしください。"),
    ("06-sns-shinhatsubai", 4,
     "新発売のクッキーをSNSで紹介する投稿文を書いてください。短く、軽い雰囲気で。商品情報は `joho.txt` です。",
     "商品名: ほろほろレモンクッキー\n発売日: 6月1日\n価格: 税込480円\n特徴: 国産レモンの皮入り\n",
     "post.md",
     [sent(2, 3), {"kind": "chars", "min": 40, "max": 100}, {"kind": "include", "words": ["ほろほろレモンクッキー", "6月1日"]}, {"kind": "exclude", "words": ["最高", "絶対"]},
      {"kind": "endings", "endings": ["です", "ます", "ね", "よ"], "terms": TERMS}, {"kind": "no_latin"}],
     "6月1日にほろほろレモンクッキーが新登場です！国産レモンの皮入りで、さわやかな香りが広がりますよ。税込480円で買えますね。"),
]


@family("i18n-ja-write-notices", category="i18n", lang="text", kind="feature", n=len(SCENARIOS), mode="fixture",
        summary="native: Japanese constrained-writing tasks (kana-only, polite endings, kanji counts, character budgets) checked by a hidden script")
def ja_write(rng, n):
    voices = [
        "{intro}\n\n条件:\n{rules}\n\n結果は `{path}` に保存してください。",
        "{intro}文章の条件は次のとおりです。\n{rules}\n`{path}` に書いてください。",
        "{intro}\n\n{rules}\n\n(書いたものは `{path}` へお願いします。)",
    ]
    for i, (slug, d, intro, facts, path, constraints, solution) in enumerate(SCENARIOS[:n]):
        prompt = voices[i % 3].format(intro=intro, rules=render(constraints), path=path)
        yield writing_task(slug, d, prompt, {"joho.txt": facts}, path, constraints, solution, ["ja"], {"prompt_lang": "ja", "constraints": [c["kind"] for c in constraints]})
