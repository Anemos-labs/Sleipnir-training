"""Derived bug-fix tasks in Japanese and Chinese (many of them about text handling in the writer's own script)."""
import unicodedata

from fx import family

from ._derive import derive, take

JA = [
    ("fix-hand-unicode-fold-01-lower-instead-of-casefold", "01-casefold-strasse", "polite",
     "サービス上で \"Straße\" と \"STRASSE\" がそれぞれ別のハンドルとして登録できてしまいました。後者は重複として弾かれる"
     "はずです。README には、正規形は大文字小文字を case *fold* したものだと書いてあります。正規化の処理を直してください。"),
    ("fix-hand-escaping-09-sql-quotes-not-doubled", "02-sql-quote", "security",
     "セキュリティスキャンで指摘されました。`§0` で INSERT 文を組み立てると `§1` になり、SQL として不正なうえ、細工された名前を"
     "入れればインジェクションにもなります。文字列の中のシングルクォートは 2 つ重ねてエスケープしてください。"),
    ("fix-hand-text-encoding-09-pad-center-by-bytes", "03-center-pad-cjk", "casual",
     "アクセント付き文字や CJK 文字を含む列見出しの中央揃えが、目に見えてずれます。幅 4 のセルで \"é\" を中央揃えにすると、"
     "右側の空白が 1 つ足りません。パディングをバイト長から計算しているように見えます。"),
    ("fix-hand-sort-order-05-dense-ranks", "04-ranking-ties", "polite",
     "ポイント表が 90, 80, 80, 70 を [1, 2, 2, 3] とランク付けしますが、リーグ規約(リーフレットに印刷されています)では"
     "同順位の次の順位を飛ばして 1, 2, 2, 4 になります。`§0` を修正してください。"),
    ("fix-hand-backup-ctl-05-hidden-files-left-out", "05-dotfiles-restore", "terse",
     "スナップショットから復元すると `§0` と `§1` が入っていません。ドットファイルがアーカイブに含まれていないようです。"),
    ("fix-hand-unicode-fold-02-nfc-misses-compat-forms", "06-zenkaku-admin", "security",
     "サポートからのセキュリティ報告です。誰かがハンドル \"ａｄｍｉｎ\"(全角文字)を登録し、チャットでスタッフのように見えて"
     "しまっています。`admin` は予約済みのはずですが、互換文字を見抜けていないようです。原因を調べて、そうした見た目が同じ"
     "名前もすべて通常の名前と同じ扱いになるように直してください。"),
    ("fix-hand-text-encoding-04-truncate-leaves-replacement", "07-truncate-utf8", "detailed",
     "バイト数の上限で切ったプレビュー文字列が、切れ目がアクセント付き文字や日本語の文字の途中に当たると、末尾にひし形の"
     "疑問符(U+FFFD)が付くことがあります。入りきらない文字の手前で素直に止まるようにしてください。"),
    ("fix-hand-money-rounding-09-percent-via-double", "08-refund-half-cent", "detailed",
     "払い戻しの額が、半セントになるケースで絶対値が 1 セント小さくなります。6.25 の 10% を返金すると -0.62 になりますが、"
     "本来は -0.63 のはずで、請求側は 0.63 を返します。ルールは正負どちらの方向でも「0 から遠い方へ丸める」です。"
     "`§0` を見てください。"),
    ("fix-hand-tz-wallclock-05-dst-end-bound", "09-dst-1-jikan", "puzzled",
     "スケジューラのバグのように見えますが、スケジューラの中には原因が見つかりません。`§0` は、10 月 1 日に壁時計で最初に "
     "02:30 になる時刻、つまり 20:30 UTC になるはずなのに、実際は 1 時間遅い 21:30 UTC になります。同じ日の繰り返される 1 時間の"
     "中の時刻も、監査用エクスポートでは誤った瞬間に変換されます。`§1` のループが悪いのだと思っていましたが、そこに怪しい"
     "箇所は見当たりません。その 1 時間がどこで消えているのか突き止めてください。"),
    ("fix-hand-text-encoding-07-bom-and-csv-newlines", "10-excel-csv-bom", "detailed",
     "Excel から届くファイルで 2 つ問題があります。1 つ目は最初の列が見つからないこと(ヘッダーに `§0` がなく、ヘックスダンプでは"
     "先頭に EF BB BF が見えます)。2 つ目は、改行を含むセルの改行コードが、ファイルの中身と違うものになってしまうことです。"
     "どちらも直前のインポート処理のリファクタリング前は動いていました。そうしたファイルの CSV インポートを壊しているものを"
     "すべて直してください。"),
]


@family("i18n-ja-fix", category="i18n", lang="mixed", kind="fix", n=len(JA), mode="fixture",
        summary="derived: bug reports written in Japanese (python, js, rust, java), d1-d5, many about text handling")
def ja_fix(rng, n):
    for src, slug, style, prompt in take(JA, n):
        yield derive(src, prompt, slug, "ja", style=style)


ZH = [
    ("fix-hand-text-encoding-01-utf8-bom-kept", "01-excel-bom", "ticket",
     "客户从 Excel 导出“CSV UTF-8”之后再导入，会报错说没有 `§0` 这一列。表头在文本编辑器里看着明明是对的。用十六进制查看，"
     "文件开头是 EF BB BF。我们解析出来的是：\n\n```\n¶0\n```\n应该是 `§1`。"),
    ("fix-hand-unicode-fold-10-truncate-code-units", "02-emoji-truncate", "casual",
     "笔记预览会在表情符号中间被截断（有些预览末尾出现了替换字符），而且只含一个表情的短笔记明明没超过限制，却被加上了省略号。"
     "限制是按字符计算的。预览代码用的是 `§1` 里的 `§0`。"),
    ("fix-hand-unicode-fold-03-length-in-bytes", "03-handle-length", "report",
     "我们的俄语用户没法注册超过大约十个字母的用户名（\"Александрия\" 被判定为太长），而像 \"ян\" 这样只有两个字母的名字"
     "反而能通过，尽管最短长度是三。看起来是合法性检查的某个地方把单位弄混了。"),
    ("fix-hand-text-encoding-11-initials-first-byte", "04-avatar-initials", "report",
     "头像徽章上，\"émile zola\" 显示成 \"ÃZ\"，以 ñ 或日文字符开头的名字则显示成乱码。首字母应该是每个单词第一个*字符*"
     "的大写形式。"),
    ("fix-hand-unicode-fold-05-search-query-not-normalised", "05-mac-search", "chatty",
     "我在 Mac 上输入 \"José\" 去用户目录里搜，什么也搜不到，可 José 明明已经注册了（他自己的客户端发的是组合形式）。"
     "搜 \"jos\" 倒是能搜到。看起来是查询和已存储的 handle 被区别对待了。请帮忙找一下原因。"),
    ("fix-hand-text-encoding-03-latin1-tried-first", "06-mojibake", "ticket",
     "自从重构了解码器，所有非 ASCII 字符都变成了乱码：以 UTF-8 保存的 \"café\" 被读成了 \"cafÃ©\"。真正是 Latin-1 的文件"
     "没有问题。README 里写着，有效的 UTF-8 必须按 UTF-8 读取。"),
    ("fix-hand-unicode-fold-14-highlight-folded-indexes", "07-highlight-nfd", "detailed",
     "从 Mac 上粘贴来的笔记（重音以基础字母加组合符号的形式保存）搜索命中后高亮会错位或乱掉。例如 \"" + unicodedata.normalize("NFD", "Crème brûlée") + "\" 配上查询 "
     "\"brule\" 时，[[ ]] 标记包住了错误的部分。预组合形式的文本没有问题。请修复 `§0`。"),
    ("fix-hand-unicode-fold-08-compat-and-stale-index", "08-fullwidth-and-rename", "detailed",
     "两个目录相关的问题同时出现了。(1) 全角的花式写法 \"ＡＤＭＩＮ\" 居然还能注册，尽管 `§0` 是保留名。(2) 用户改名之后，"
     "搜索会崩溃。我不知道这两个问题有没有关联；可见的测试都能通过。请把所有有问题的地方都修好。"),
]


@family("i18n-zh-fix", category="i18n", lang="mixed", kind="fix", n=len(ZH), mode="fixture",
        summary="derived: Unicode and text-encoding bug reports written in Simplified Chinese (python, js, rust), d1-d5")
def zh_fix(rng, n):
    for src, slug, style, prompt in take(ZH, n):
        yield derive(src, prompt, slug, "zh", style=style)
