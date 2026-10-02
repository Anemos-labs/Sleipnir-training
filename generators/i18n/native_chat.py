"""Native answer-mode chat families: everyday calculations rooted in one country's rules, asked in that language.

Every answer is computed with exact decimal arithmetic from the numbers in the prompt (the prompt states the rules it needs),
and every ``answer.contains`` string is a plain number (no thousands separators) so the check does not depend on the language
the agent answers in.
"""
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

from fx import Task, family

D = Decimal


def q(x, places=0, mode=ROUND_HALF_UP):
    return D(x).quantize(D(1).scaleb(-places), rounding=mode)


def num(x, places=0):
    """A plain ASCII number string with exactly ``places`` decimals."""
    return format(q(x, places), "f")


def plain(x):
    """The shortest plain decimal text of x (1250.50 -> '1250.5', 1250.00 -> '1250'); a prefix of every longer spelling."""
    return format(D(x).normalize(), "f")


def loc(x, places=2):
    """German/Turkish style number text: dots between thousands, a comma before the decimals (1.234,56)."""
    return format(q(x, places), ",f").replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def make(slug, prompt, d, contains, gold, notes, fold=True):
    return Task(slug=slug, prompt=prompt, difficulty=d, answer={"contains": contains, "fold": fold}, gold_answer=gold,
                start={".gitkeep": ""}, kind="calc", lang="text", tags=["native", "computed"], notes=notes)


# ---------------------------------------------------------------------------------------------------------------- ja
JA_ITEMS_8 = [("おにぎり(持ち帰り)", 120, 180), ("お茶(持ち帰り)", 110, 160), ("お弁当(持ち帰り)", 480, 780), ("サンドイッチ(持ち帰り)", 250, 420),
              ("牛乳", 150, 230), ("パン(持ち帰り)", 130, 260), ("みかん", 300, 580), ("納豆", 90, 160)]
JA_ITEMS_10 = [("ビール", 230, 330), ("日本酒", 800, 1500), ("ノート", 120, 280), ("ボールペン", 100, 250), ("コーヒー(店内)", 380, 560),
               ("雑誌", 550, 1100), ("洗剤", 300, 480), ("ティッシュ", 200, 380)]


def _ja_receipt(rng, lines):
    chosen = []
    pool8, pool10 = list(JA_ITEMS_8), list(JA_ITEMS_10)
    rng.shuffle(pool8)
    rng.shuffle(pool10)
    n8 = rng.randint(1, lines - 1)
    for it in pool8[:n8]:
        chosen.append((it[0], rng.randrange(it[1], it[2] + 1, 10), rng.randint(1, 4), 8))
    for it in pool10[: lines - n8]:
        chosen.append((it[0], rng.randrange(it[1], it[2] + 1, 10), rng.randint(1, 3), 10))
    rng.shuffle(chosen)
    return chosen


@family("i18n-ja-chat-shouhizei", category="i18n", lang="text", kind="calc", n=8, mode="answer",
        summary="native: Japanese consumption-tax receipts (8% / 10%, rounding per rate), computed answers")
def ja_shouhizei(rng, n):
    for i in range(n):
        kind = ["total", "total", "tax", "split", "total", "split", "tax", "split"][i % 8]
        lines = 3 + (i % 3)
        items = _ja_receipt(rng, lines)
        s8 = sum(p * k for _, p, k, r in items if r == 8)
        s10 = sum(p * k for _, p, k, r in items if r == 10)
        t8, t10 = int(q(D(s8) * 8 / 100, 0, ROUND_FLOOR)), int(q(D(s10) * 10 / 100, 0, ROUND_FLOOR))
        total = s8 + s10 + t8 + t10
        people = rng.choice([2, 3, 4, 5])
        per = int(q(D(total) / people, 0, ROUND_CEILING))
        block = "\n".join("%s %d円 × %d (%d%%)" % (name, p, k, r) for name, p, k, r in items)
        rules = "消費税は税率ごと(8%と10%)に税抜の合計を出してから計算し、1円未満は切り捨てます。"
        if kind == "total":
            q_text = ["税込の支払い合計はいくらですか?", "最終的にレジでいくら払うことになりますか(税込)?", "合計金額(税込)を教えてください。"][i % 3]
            contains, d = [str(total)], 2 + (lines > 3)
        elif kind == "tax":
            q_text = "消費税額の合計と、税込の合計をそれぞれ教えてください。"
            contains, d = [str(t8 + t10), str(total)], 3
        else:
            q_text = "税込合計を%d人で割り勘にします。端数は切り上げで1人あたりいくらですか?(合計金額も一緒に教えてください)" % people
            contains, d = [str(per), str(total)], 4
        voice = i % 3
        if voice == 0:
            prompt = ("こんにちは。先週の買い物のレシートを写していて、計算が合っているか確認したいです。税抜の明細はこうです。\n\n```\n%s\n```\n\n%s\n%s\n"
                      "答えは数字だけ(カンマなし)で書いてください。" % (block, rules, q_text))
        elif voice == 1:
            prompt = ("ねえ、ちょっと計算お願い!会社の備品と軽食をまとめて買ったんだけど、税込でいくらになる?\n\n%s\n\n%s\n%s 数字はカンマなしでね。" % (block, rules, q_text))
        else:
            prompt = ("経理の確認です。明細(税抜):\n\n%s\n\n条件: %s\n質問: %s\n数値はカンマ・円記号なしで回答してください。" % (block, rules, q_text))
        gold = "計算結果: " + "、".join(contains) + "(税率ごとの合計は8%%対象が%d円、10%%対象が%d円)。" % (s8, s10)
        yield make("%02d-%s-%dp" % (i + 1, kind, lines), prompt, d, contains, gold, {"kind": kind, "s8": s8, "s10": s10, "t8": t8, "t10": t10})


# ---------------------------------------------------------------------------------------------------------------- ko
@family("i18n-ko-chat-pyeong-wolse", category="i18n", lang="text", kind="calc", n=8, mode="answer",
        summary="native: Korean area (pyeong vs square metres) and jeonse-to-monthly-rent conversion, computed answers")
def ko_pyeong(rng, n):
    for i in range(n):
        kind = ["pyeong", "sqm", "wolse", "wolse", "pyeong", "sqm", "wolse", "wolse"][i % 8]
        if kind == "pyeong":
            area = D(rng.randint(4000, 14500)) / 100
            result = q(area / D("3.3058"), 1)
            d = 1 + (i % 2)
            question = ["전용면적 %s㎡는 몇 평인가요? 소수 첫째 자리까지 반올림해 주세요." % area,
                        "분양 광고에 전용 %s㎡라고 나와 있는데, 평수로는 얼마예요? (소수점 첫째 자리까지, 반올림)" % area][i % 2]
            prompt = "1평은 3.3058㎡로 계산하기로 해요. " + question + " 숫자만 소수점(.)으로 적어 주세요."
            contains, gold = [plain(num(result, 1))], "약 %s평입니다." % num(result, 1)
            notes = {"area": str(area)}
        elif kind == "sqm":
            pyeong = D(rng.randint(150, 600)) / 10
            result = q(pyeong * D("3.3058"), 1)
            d = 2
            prompt = ("집주인이 %s평이라고 하는데, ㎡로는 몇 ㎡일까요? 1평 = 3.3058㎡ 로 계산하고 소수점 첫째 자리까지 반올림해 주세요. "
                      "숫자만 소수점(.)으로 알려 주세요." % pyeong)
            contains, gold = [plain(num(result, 1))], "%s㎡입니다." % num(result, 1)
            notes = {"pyeong": str(pyeong)}
        else:
            jeonse = rng.randrange(20000, 90001, 1000)
            deposit = rng.randrange(2000, jeonse // 2, 500)
            rate = D(rng.choice([4, 4.5, 5, 5.5, 6]))
            monthly = q(D(jeonse - deposit) * rate / 100 / 12, 1)
            d = 3 + (i % 2)
            prompt = ("전세 시세가 %s만원인 집을 보증금 %s만원에 월세로 돌리려고 합니다. 전월세 전환율이 연 %s%%라면 월세는 얼마가 되나요? "
                      "계산식은 (전세금 − 보증금) × 전환율 ÷ 12 이고, 만원 단위로 소수점 첫째 자리까지 반올림해 주세요. 숫자만 소수점(.)으로 적어 주세요."
                      % (format(jeonse, ","), format(deposit, ","), rate))
            if i % 2:
                prompt = ("집주인과 월세 협상 중이에요. 전세로는 %s만원이고 보증금을 %s만원 걸면, 연 %s%% 전환율로 월세가 얼마여야 하죠? "
                          "(전세금 − 보증금) × 전환율 ÷ 12 로 만원 단위 소수점 첫째 자리까지 반올림해서 숫자만 알려 주세요." % (format(jeonse, ","), format(deposit, ","), rate))
            contains, gold = [plain(num(monthly, 1))], "월세는 %s만원입니다." % num(monthly, 1)
            notes = {"jeonse": jeonse, "deposit": deposit, "rate": str(rate)}
        yield make("%02d-%s" % (i + 1, kind), prompt, d, contains, gold, notes)


# ---------------------------------------------------------------------------------------------------------------- tr
@family("i18n-tr-chat-kdv", category="i18n", lang="text", kind="calc", n=8, mode="answer",
        summary="native: Turkish VAT (KDV) included/excluded and instalment questions, computed answers")
def tr_kdv(rng, n):
    for i in range(n):
        kind = ["haric", "dahil", "haric", "taksit", "iskonto", "haric", "taksit", "iskonto"][i % 8]
        rate = rng.choice([1, 10, 20])
        if kind in ("haric", "dahil"):
            gross = D(rng.randint(1500, 90000)) / 100 if kind == "haric" else None
            if kind == "haric":
                net = q(gross / (1 + D(rate) / 100), 2)
                vat = q(gross - net, 2)
                prompt = ["Fiş üzerinde KDV dahil toplam %s TL yazıyor, KDV oranı %%%d. KDV hariç tutar ne, KDV tutarı ne kadar? Kuruşa yuvarla "
                          "(yarım ve üstü yukarı); cevapta ondalık ayıracı olarak nokta kullan (örnek: 1234.56)." % (loc(gross), rate),
                          "Müşteriye %s TL'lik (KDV dahil) fatura kesmişim, oran %%%d. KDV'siz fiyatı ve KDV'yi bulur musun? İki ondalık yaz, ondalık için "
                          "nokta kullan lütfen (1234.56 gibi)." % (loc(gross), rate)][i // 2 % 2]
                contains, d = [num(net, 2), num(vat, 2)], 2 + (rate != 20)
                gold = "KDV hariç: %s TL, KDV: %s TL." % (num(net, 2), num(vat, 2))
            else:
                netv = D(rng.randint(1000, 80000)) / 100
                vat = q(netv * D(rate) / 100, 2)
                total = netv + vat
                prompt = "Bir ürünün KDV hariç fiyatı %s TL ve KDV oranı %%%d. KDV dahil kaç TL öderim? Cevapta ondalık ayıracı nokta olsun (1234.56 gibi), kuruşa yuvarla." % (loc(netv), rate)
                contains, d = [num(total, 2)], 2
                gold = "KDV dahil fiyat %s TL." % num(total, 2)
        elif kind == "taksit":
            price = rng.randrange(6000, 60001, 500)
            months = rng.choice([3, 6, 9, 12])
            monthly_rate = D(rng.choice([2, 3, 4])) / 100
            total_interest = q(D(price) * monthly_rate * months, 2)
            installment = q((D(price) + total_interest) / months, 2)
            prompt = ("%d TL'lik bir telefonu %d taksitle alıyorum. Mağaza aylık %%%s basit faiz uyguluyor (faiz = fiyat × aylık oran × ay sayısı, anaparaya eklenir, "
                      "sonra taksit sayısına bölünür). Taksit tutarı ne kadar? Kuruşa yuvarla; cevapta ondalık için nokta kullan, binlik ayıracı yazma (1234.56 gibi)."
                      % (price, months, str((monthly_rate * 100).normalize())))
            contains, d = [num(installment, 2)], 3
            gold = "Aylık taksit %s TL." % num(installment, 2)
        else:
            price = D(rng.randrange(20000, 150001, 500)) / 100
            disc = rng.choice([10, 15, 20, 25, 30])
            after = price * (100 - disc) / 100
            vat = q(after * D(rate) / 100, 2)
            total = q(after + vat, 2)
            prompt = ("Etiket fiyatı %s TL (KDV hariç), %%%d indirim var, sonra %%%d KDV ekleniyor. Kasada kaç TL ödenir? Kuruşa yuvarla; cevapta ondalık ayıracı nokta, "
                      "binlik ayıracı yok (1234.56 gibi)." % (loc(price), disc, rate))
            contains, d = [num(total, 2)], 3
            gold = "Kasada %s TL ödenir." % num(total, 2)
        yield make("%02d-%s" % (i + 1, kind), prompt, d, contains, gold, {"kind": kind, "rate": rate})


# ---------------------------------------------------------------------------------------------------------------- hi
@family("i18n-hi-chat-gst", category="i18n", lang="text", kind="calc", n=8, mode="answer",
        summary="native: Indian GST invoices (CGST + SGST), rupee totals, computed answers in Hindi")
def hi_gst(rng, n):
    goods = [("चावल", 5), ("आटा", 5), ("कपड़े", 12), ("मोबाइल कवर", 18), ("हेडफ़ोन", 18), ("बर्तन", 12), ("कोल्ड ड्रिंक", 28), ("पेंट", 28), ("साबुन", 18),
             ("किताबें", 5), ("जूते", 12)]
    for i in range(n):
        kind = ["total", "split", "total", "back", "split", "total", "back", "split"][i % 8]
        lines = 2 + i % 3
        pool = list(goods)
        rng.shuffle(pool)
        items = [(name, rate, rng.randrange(100, 3000, 25)) for name, rate in pool[:lines]]
        base = sum(p for _, _, p in items)
        gst = sum(q(D(p) * r / 100, 2) for _, r, p in items)
        total = q(D(base) + gst, 2)
        cgst = q(gst / 2, 2)
        block = "\n".join("%s: ₹%d (GST %d%%)" % (name, p, r) for name, r, p in items)
        if kind == "total":
            prompt = ("नमस्ते! दुकान के बिल की जाँच करनी है। नीचे हर सामान की GST से पहले की कीमत और GST दर है।\n\n```\n%s\n```\n\n"
                      "हर सामान पर GST अलग-अलग निकालिए (दो दशमलव तक, आधा ऊपर), फिर बिल की कुल रकम बताइए। जवाब सिर्फ़ संख्या में, दशमलव बिंदु (.) के साथ, "
                      "कॉमा के बिना।" % block)
            contains, d, gold = [num(total, 2)], 2 + (lines > 2), "बिल की कुल रकम ₹%s है।" % num(total, 2)
        elif kind == "split":
            prompt = ("भाई, एक GST बिल बनाना है। सामान और उनकी GST-पूर्व कीमत:\n\n%s\n\nराज्य के भीतर की बिक्री है, तो कुल GST आधा CGST और आधा SGST होता है। "
                      "हर सामान की GST दो दशमलव तक (आधा ऊपर) निकालकर जोड़िए। कुल GST, CGST और बिल की कुल रकम बताइए (संख्याएँ दशमलव बिंदु के साथ, कॉमा के बिना)।"
                      % block)
            contains, d = [num(gst, 2), num(cgst, 2), num(total, 2)], 3 + (lines > 3)
            gold = "कुल GST ₹%s, CGST ₹%s, SGST ₹%s, कुल रकम ₹%s।" % (num(gst, 2), num(cgst, 2), num(gst - cgst, 2), num(total, 2))
        else:
            name, r, _ = items[0]
            while True:  # no answer string may occur inside the prompt text itself
                base0 = rng.randrange(100, 3000, 25)
                gst0 = q(D(base0) * r / 100, 2)
                price_incl = D(base0) + gst0
                prompt = ("एक ग्राहक ने बताया कि %s का GST समेत दाम ₹%s है और GST दर %d%% है। GST से पहले का दाम (पूर्ण रुपये) और उसमें लगा GST (दो दशमलव तक) "
                          "कितना होना चाहिए? सिर्फ़ संख्याएँ लिखिए, दशमलव बिंदु (.) के साथ, कॉमा के बिना।" % (name, num(price_incl, 2), r))
                contains = [str(base0), num(gst0, 2)]
                if not any(c in prompt for c in contains):
                    break
            d = 3
            gold = "GST से पहले का दाम ₹%d और GST ₹%s है।" % (base0, num(gst0, 2))
        yield make("%02d-%s" % (i + 1, kind), prompt, d, contains, gold, {"kind": kind, "lines": lines})


# ---------------------------------------------------------------------------------------------------------------- ar
@family("i18n-ar-chat-zakat", category="i18n", lang="text", kind="calc", n=8, mode="answer",
        summary="native: zakat on savings (2.5% above the nisab) and related percentage questions in Arabic, computed answers")
def ar_zakat(rng, n):
    for i in range(n):
        kind = ["zakat", "zakat", "below", "gold", "zakat", "installment", "below", "gold"][i % 8]
        use_hindi_digits = i % 2 == 1

        def fmt(x):
            s = format(x, ",") if isinstance(x, int) else str(x)
            return s.translate(str.maketrans("0123456789,.", "٠١٢٣٤٥٦٧٨٩٬٫")) if use_hindi_digits else s

        nisab = rng.randrange(18000, 30001, 500)
        if kind == "zakat":
            savings = rng.randrange(nisab + 2000, nisab * 3, 100)
            zakat = q(D(savings) * D("0.025"), 2)
            prompt = ("السلام عليكم، عندي مدخرات %s ريال مرّت عليها سنة هجرية كاملة، والنصاب عندنا %s ريال. إذا بلغ المال النصاب فالزكاة ٢٫٥٪ منه، "
                      "وإذا لم يبلغه فلا زكاة. كم تبلغ زكاتي؟ اكتب الجواب بالأرقام اللاتينية (0-9) وبنقطة عشرية إن لزم، ومن دون فواصل للآلاف." % (fmt(savings), fmt(nisab)))
            contains = [plain(zakat)]
            gold = "الزكاة المستحقة: %s ريال." % contains[0]
            d = 2
        elif kind == "below":
            savings = rng.randrange(nisab // 3, nisab - 100, 100)
            shortfall = nisab - savings
            prompt = ("لو سمحت، النصاب %s ريال ومعي مبلغ %s ريال محفوظ منذ أكثر من عام، فلا تجب فيه الزكاة بعد. كم ريالًا ينقصني ليبلغ النصاب؟ "
                      "وكم تبلغ زكاة مبلغ النصاب نفسه (٢٫٥٪ منه)؟ اكتب الرقمين بالأرقام اللاتينية وبنقطة عشرية إن لزم، ومن غير فواصل للآلاف."
                      % (fmt(nisab), fmt(savings)))
            reached = q(D(nisab) * D("0.025"), 2)
            contains = [str(shortfall), plain(reached)]
            gold = "ينقصك %d ريالًا، وزكاة مبلغ النصاب %s ريال." % (shortfall, plain(reached))
            d = 3
        elif kind == "gold":
            grams = rng.randrange(90, 250)
            price = rng.randrange(180, 320)
            value = grams * price
            zakat = q(D(value) * D("0.025"), 2)
            prompt = ("عندي %s غرامًا من الذهب، وسعر الغرام اليوم %s ريال. زكاة الذهب ٢٫٥٪ من قيمته إذا بلغ النصاب (٨٥ غرامًا). كم الزكاة؟ "
                      "اكتب الرقم بالأرقام اللاتينية وبنقطة عشرية إن لزم، ومن غير فاصلة للآلاف." % (fmt(grams), fmt(price)))
            zres = plain(zakat)
            contains, d = [zres], 4
            gold = "الزكاة: %s ريال." % zres
        else:
            price = rng.randrange(12000, 60001, 500)
            months = rng.choice([6, 10, 12, 20, 24])
            down = rng.choice([10, 20, 25])
            rest = D(price) * (100 - down) / 100
            monthly = q(rest / months, 2)
            prompt = ("اشتريت جهازًا بسعر %s ريال، دفعت مقدمًا %s٪ والباقي على %s قسطًا شهريًا متساويًا بلا أرباح. كم قيمة القسط الشهري؟ "
                      "اكتب الجواب بالأرقام اللاتينية وبنقطة عشرية وبدون فواصل للآلاف." % (fmt(price), fmt(down), fmt(months)))
            contains, d, gold = [plain(monthly)], 3, "القسط الشهري %s ريال." % num(monthly, 2)
        yield make("%02d-%s" % (i + 1, kind), prompt, d, contains, gold, {"kind": kind})


# ---------------------------------------------------------------------------------------------------------------- id
@family("i18n-id-chat-thr", category="i18n", lang="text", kind="calc", n=8, mode="answer",
        summary="native: Indonesian THR holiday bonus (pro-rated by months worked) and pension-contribution questions, computed answers")
def id_thr(rng, n):
    for i in range(n):
        kind = ["thr", "thr", "thr_allow", "pensiun", "thr", "thr_allow", "pensiun", "thr_allow"][i % 8]
        salary = rng.randrange(3000000, 12000001, 250000)
        months = rng.choice([3, 5, 7, 9, 11, 12, 14])
        fmt = lambda x: format(x, ",").replace(",", ".")
        if kind == "thr":
            thr = salary if months >= 12 else int(q(D(salary) * months / 12, 0))
            prompt = ["Aku karyawan baru di sebuah toko, gaji pokokku Rp %s per bulan dan sudah bekerja %d bulan. THR dihitung sebesar satu bulan gaji kalau masa kerja "
                      "sudah 12 bulan atau lebih; kalau kurang, dihitung masa kerja ÷ 12 × gaji. Berapa THR-ku? Tulis angka saja tanpa titik pemisah ribuan (bulatkan ke rupiah terdekat)."
                      % (fmt(salary), months),
                      "Bantu hitung THR dong. Gaji Rp %s, masa kerja %d bulan. Aturannya: masa kerja ≥ 12 bulan → 1 × gaji; kurang dari itu → masa kerja/12 × gaji. "
                      "Jawab dengan angka tanpa titik/koma, dibulatkan ke rupiah." % (fmt(salary), months)][i // 2 % 2]
            contains, d = [str(thr)], 2
            gold = "THR yang diterima: %d rupiah." % thr
        elif kind == "thr_allow":
            allowance = rng.randrange(200000, 1500001, 50000)
            thr = salary + allowance if months >= 12 else int(q(D(salary + allowance) * months / 12, 0))
            prompt = ("Gaji pokok Rp %s ditambah tunjangan tetap Rp %s per bulan. Masa kerja %d bulan. THR = (gaji pokok + tunjangan tetap) × (masa kerja ÷ 12), tetapi kalau masa kerja 12 bulan "
                      "atau lebih, THR = satu kali (gaji pokok + tunjangan tetap). Berapa THR-nya? Tulis angkanya saja, tanpa pemisah ribuan, dibulatkan ke rupiah terdekat."
                      % (fmt(salary), fmt(allowance), months))
            contains, d, gold = [str(thr)], 3, "THR: %d rupiah." % thr
        else:
            rate_emp = D(rng.choice([1, 2]))
            cap = rng.choice([9559600, 10000000, 12000000])
            base = min(salary, cap)
            contribution = q(D(base) * rate_emp / 100, 0)
            prompt = ("Iuran jaminan pensiun yang dipotong dari karyawan adalah %s%% dari gaji, dengan batas dasar perhitungan Rp %s (gaji di atas batas dihitung sebagai batas). "
                      "Gajiku Rp %s. Berapa rupiah yang dipotong per bulan? Jawab dengan angka tanpa titik pemisah, dibulatkan ke rupiah terdekat (setengah ke atas)."
                      % (rate_emp, fmt(cap), fmt(salary)))
            contains, d, gold = [str(int(contribution))], 3, "Potongan per bulan: %d rupiah." % int(contribution)
        yield make("%02d-%s" % (i + 1, kind), prompt, d, contains, gold, {"kind": kind, "salary": salary})


# ---------------------------------------------------------------------------------------------------------------- ru
BRACKETS = [(2400000, 13), (5000000, 15), (20000000, 18), (50000000, 20), (None, 22)]


def ndfl(income):
    tax, prev = D(0), 0
    for limit, rate in BRACKETS:
        top = income if limit is None else min(income, limit)
        if top > prev:
            tax += D(top - prev) * rate / 100
        prev = limit if limit is not None else income
        if limit is None or income <= limit:
            break
    return q(tax, 0)


@family("i18n-ru-chat-ndfl", category="i18n", lang="text", kind="calc", n=8, mode="answer",
        summary="native: Russian progressive income tax brackets and VAT questions, computed answers")
def ru_ndfl(rng, n):
    table = "до 2 400 000 ₽ — 13%, свыше 2 400 000 до 5 000 000 ₽ — 15%, свыше 5 000 000 до 20 000 000 ₽ — 18%, свыше 20 000 000 до 50 000 000 ₽ — 20%, свыше 50 000 000 ₽ — 22%"
    for i in range(n):
        kind = ["tax", "net", "tax", "vat", "net", "tax", "vat", "net"][i % 8]
        if kind in ("tax", "net"):
            income = rng.choice([rng.randrange(1800000, 2400001, 10000), rng.randrange(2500000, 5000001, 10000), rng.randrange(5200000, 20000001, 50000),
                                 rng.randrange(20500000, 50000001, 100000)])
            tax = ndfl(income)
            net = income - int(tax)
            voice = i % 2
            if kind == "tax":
                prompt = [("Подскажите, пожалуйста, сколько налога на доход нужно заплатить за год при доходе %s ₽? Ставки прогрессивные, каждая применяется только к части дохода "
                           "внутри своего интервала: %s. Налог округлите до целого рубля (0,5 и выше — вверх). Ответ — одно число без пробелов." % (format(income, ",").replace(",", " "), table)),
                          ("Привет! Зарплата за год вышла %s ₽. Налог считаем по шкале: %s (каждая ставка — только на свою часть дохода). Сколько налог в рублях? "
                           "Округли до рубля, ответ числом без пробелов." % (format(income, ",").replace(",", " "), table))][voice]
                contains, d, gold = [str(int(tax))], 3 + (income > 5000000), "Налог за год: %d ₽." % int(tax)
            else:
                prompt = ("Годовой доход до налога — %s ₽. Шкала налога: %s (каждая ставка применяется только к части дохода внутри своего интервала). "
                          "Сколько денег останется после уплаты налога? Налог округлите до целого рубля (0,5 и выше — вверх). Ответ — число без пробелов, и налог тоже назовите."
                          % (format(income, ",").replace(",", " "), table))
                contains, d, gold = [str(net), str(int(tax))], 4, "На руки: %d ₽, налог: %d ₽." % (net, int(tax))
        else:
            rate = rng.choice([10, 20])
            gross = rng.randrange(1500, 90000, 10)
            net_amount = q(D(gross) * 100 / (100 + rate), 2)
            vat = q(D(gross) - net_amount, 2)
            prompt = ("В чеке сумма с НДС %d ₽, ставка НДС %d%%. Сколько в этой сумме сам НДС и сколько стоит товар без НДС? Округляйте до копеек (0,005 и выше — вверх), "
                      "в ответе десятичная точка, без пробелов." % (gross, rate))
            contains, d, gold = [num(vat, 2), num(net_amount, 2)], 3, "НДС: %s ₽, без НДС: %s ₽." % (num(vat, 2), num(net_amount, 2))
        yield make("%02d-%s" % (i + 1, kind), prompt, d, contains, gold, {"kind": kind})


# ---------------------------------------------------------------------------------------------------------------- de
@family("i18n-de-chat-nebenkosten", category="i18n", lang="text", kind="calc", n=8, mode="answer",
        summary="native: German utility-cost settlement (Nebenkostenabrechnung by area and months), computed answers")
def de_nebenkosten(rng, n):
    for i in range(n):
        kind = ["nach", "guthaben", "nach", "personen", "guthaben", "nach", "personen", "guthaben"][i % 8]
        if kind in ("nach", "guthaben"):
            total_cost = D(rng.randrange(900000, 3600001, 5000)) / 100
            total_area = rng.choice([420, 480, 540, 600, 650])
            area = rng.randrange(45, 110, 1)
            months = rng.choice([6, 8, 9, 10, 12, 12, 12])
            share = q(total_cost * D(area) / total_area * D(months) / 12, 2)
            factor = D("0.8") if kind == "nach" else D("1.2")
            prepaid_month = q(share / months * factor / D("0.5"), 0) * D("0.5")
            diff = share - prepaid_month * months
            result = abs(diff)
            word = "Nachzahlung" if diff > 0 else "Guthaben"
            prompt = ("Hallo, ich habe gerade die Nebenkostenabrechnung für das Haus bekommen und will sie nachrechnen. Gesamtkosten des Hauses für das Jahr: %s EUR, Gesamtwohnfläche "
                      "des Hauses: %d m². Meine Wohnung hat %d m², und ich habe dort nur %d Monate gewohnt. Mein Anteil = Gesamtkosten × (meine Fläche ÷ Gesamtfläche) × (Monate ÷ 12), "
                      "auf Cent gerundet (ab 0,5 Cent aufrunden). Ich habe monatlich %s EUR Vorauszahlung geleistet. Wie hoch ist mein Anteil, und wie hoch ist die Nachzahlung beziehungsweise "
                      "das Guthaben (Betrag ohne Vorzeichen)? Bitte in der Antwort einen Punkt als Dezimaltrenner und keine Tausendertrennzeichen verwenden (z. B. 1234.56)." % (loc(total_cost), total_area, area, months, loc(prepaid_month)))
            contains = [num(share, 2), num(result, 2)]
            d = 3
            gold = "Mein Anteil: %s EUR; %s: %s EUR." % (num(share, 2), word, num(result, 2))
        else:
            total_cost = D(rng.randrange(120000, 600001, 2500)) / 100
            persons = [rng.randint(1, 4) for _ in range(3)]
            days = [rng.choice([365, 365, 300, 240, 180]) for _ in range(3)]
            weights = [p * dd_ for p, dd_ in zip(persons, days)]
            tw = sum(weights)
            shares = [q(total_cost * w / tw, 2) for w in weights]
            prompt = ("Wir sind drei Parteien im Haus und teilen die Müllgebühren nach Personentagen (Personen × Tage mit Bewohnern). Gesamtbetrag: %s EUR. Partei A: %d Personen, %d Tage; "
                      "Partei B: %d Personen, %d Tage; Partei C: %d Personen, %d Tage. Wie viel zahlt jede Partei, auf Cent gerundet (ab 0,5 Cent aufrunden)? "
                      "Bitte in der Antwort einen Punkt als Dezimaltrenner verwenden (z. B. 1234.56), A, B und C nacheinander." % (loc(total_cost), persons[0], days[0], persons[1], days[1], persons[2], days[2]))
            contains = [num(s, 2) for s in shares]
            d = 4
            gold = "A: %s EUR, B: %s EUR, C: %s EUR." % tuple(num(s, 2) for s in shares)
        yield make("%02d-%s" % (i + 1, kind), prompt, d, contains, gold, {"kind": kind})
