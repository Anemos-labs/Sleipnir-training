"""Native constrained-writing tasks in Arabic (Arabic-Indic digits, Arabic punctuation, no Latin letters)."""
from fx import family

from ._writing import writing_task

TERMS = ".؟!"


def phrase_sentences(p):
    return ("%d جمل بالضبط" % p["min"] if p["min"] == p["max"] else "من %d إلى %d جمل" % (p["min"], p["max"])) + " (تنتهي الجملة بنقطة أو بعلامة الاستفهام العربية ؟ أو بعلامة تعجب)"


PH = {
    "sentences": phrase_sentences,
    "words": lambda p: "عدد الكلمات بين %d و%d" % (p["min"], p["max"]),
    "chars": lambda p: "عدد الحروف بين %d و%d من دون احتساب المسافات" % (p["min"], p["max"]),
    "include": lambda p: "أدرج هذه العبارات حرفيًا كما هي: " + "، ".join("«%s»" % w for w in p["words"]),
    "exclude": lambda p: "لا تستخدم هذه الكلمات: " + "، ".join("«%s»" % w for w in p["words"]),
    "no_latin": lambda p: "من دون أي حرف لاتيني (A-Z)",
    "indic_digits": lambda p: "اكتب الأرقام بالأرقام العربية-الهندية (٠-٩) فقط ولا تستخدم الأرقام اللاتينية (0-9)، وفي النص رقم واحد على الأقل",
    "ar_punct": lambda p: "لا تستخدم الفاصلة اللاتينية (,) ولا علامة الاستفهام اللاتينية (?) ولا الفاصلة المنقوطة اللاتينية (;)، واستعمل الفاصلة العربية ، أو علامة الاستفهام العربية ؟ مرة واحدة على الأقل",
    "bullets": lambda p: "قائمة من %d نقاط بالضبط، كل نقطة في سطر وتبدأ بـ «- »، ولا شيء خارج القائمة غير العنوان إن وُجد" % p["n"],
    "title": lambda p: "السطر الأول عنوان يبدأ بـ «# »",
}


def render(constraints):
    return "\n".join("- " + PH[c["kind"]](c) for c in constraints if c["kind"] in PH)


def sent(lo, hi):
    return {"kind": "sentences", "min": lo, "max": hi, "terms": TERMS}


SCENARIOS = [
    ("01-warsha-alkhat", 3,
     "أحتاج إعلانًا قصيرًا لورشة في المكتبة سأعلّقه عند المدخل. بيانات الورشة في الملف `maelumat.txt`.",
     "الفعالية: ورشة الخط العربي\nاليوم: الخميس\nالوقت: ٥ مساءً\nالمكان: مكتبة النور\nالمدة: ساعتان\n",
     "ealan.md",
     [sent(3, 4), {"kind": "words", "min": 20, "max": 60}, {"kind": "include", "words": ["ورشة الخط العربي", "الخميس"]}, {"kind": "no_latin"},
      {"kind": "indic_digits"}, {"kind": "ar_punct"}],
     "هل تحب الكتابة الجميلة؟ تنظم مكتبة النور ورشة الخط العربي يوم الخميس في الساعة ٥ مساءً، وتستمر ساعتين. المقاعد محدودة، فاحجز مكانك من الآن."),
    ("02-itidhar-taakhir", 3,
     "اكتب لي رسالة اعتذار مهذبة لزميل تأخرت في الرد على بريده. التفاصيل في `maelumat.txt`.",
     "السبب: سفر عمل لمدة يومين\nالموضوع: مراجعة تقرير المبيعات\nالموعد الجديد للتسليم: الأحد\n",
     "risala.md",
     [sent(3, 4), {"kind": "include", "words": ["أعتذر", "الأحد"]}, {"kind": "exclude", "words": ["للأسف", "مشغول"]}, {"kind": "ar_punct"}, {"kind": "no_latin"},
      {"kind": "words", "min": 25, "max": 60}],
     "أعتذر عن تأخري في الرد على بريدك بخصوص مراجعة تقرير المبيعات، فقد كنت في سفر عمل لمدة يومين. أنهيت المراجعة الآن وسأرسل لك ملاحظاتي يوم الأحد. "
     "هل يناسبك هذا الموعد؟"),
    ("03-wasfa-aruzz", 4,
     "اكتب وصفة أرز بالخضار على شكل قائمة نقاط مع عنوان، لمن يطبخ لأول مرة. المقادير في `maelumat.txt`.",
     "الأرز: كوب ونصف\nالماء: ثلاثة أكواب\nالجزر والبازلاء: كوب\nالزيت: ملعقة كبيرة\nالملح: ملعقة صغيرة\nالنضج: ٢٠ دقيقة\n",
     "wasfa.md",
     [{"kind": "title"}, {"kind": "bullets", "n": 5}, {"kind": "include", "words": ["الأرز", "ملعقة"]}, {"kind": "indic_digits"}, {"kind": "no_latin"},
      {"kind": "words", "min": 30, "max": 80}],
     "# أرز بالخضار\n- اغسل الأرز جيدًا ثم صفِّه من الماء.\n- سخّن ملعقة كبيرة من الزيت وقلّب فيها الجزر والبازلاء قليلًا.\n"
     "- أضف الأرز وثلاثة أكواب من الماء وملعقة صغيرة من الملح.\n- غطِّ القدر واتركه على نار هادئة ٢٠ دقيقة.\n- قدّم الأرز ساخنًا بعد أن ترفع القدر وتتركه خمس دقائق."),
    ("04-aard-shita", 2,
     "صغ لي نصًا إعلانيًا قصيرًا لمحل ملابس عن عرض الشتاء. المعلومات في `maelumat.txt`.",
     "المحل: بيت الأناقة\nالعرض: خصم ٣٠٪ على المعاطف\nالمدة: حتى نهاية الشهر\n",
     "ealan2.md",
     [{"kind": "words", "min": 18, "max": 40}, {"kind": "include", "words": ["عرض", "٣٠٪", "بيت الأناقة"]}, {"kind": "exclude", "words": ["مجانا", "مجانًا"]}, {"kind": "indic_digits"},
      {"kind": "ar_punct"}, sent(2, 3)],
     "عرض الشتاء وصل إلى بيت الأناقة! خصم ٣٠٪ على جميع المعاطف حتى نهاية الشهر، فهل ستفوّت الفرصة؟ تعال واختر معطفك الدافئ."),
    ("05-talab-ejaza", 3,
     "اكتب طلب إجازة رسميًا إلى المدير (نص الرسالة فقط). التفاصيل في `maelumat.txt`.",
     "الاسم: سلمى الحداد\nالقسم: الموارد البشرية\nمدة الإجازة: ٣ أيام\nالتاريخ: من ١٢ إلى ١٤ مارس\nالسبب: ظرف عائلي\n",
     "talab.md",
     [sent(4, 5), {"kind": "include", "words": ["إجازة", "سلمى الحداد"]}, {"kind": "indic_digits"}, {"kind": "ar_punct"}, {"kind": "no_latin"}, {"kind": "words", "min": 35, "max": 80}],
     "السيد المدير المحترم، أتقدم أنا سلمى الحداد من قسم الموارد البشرية بطلب إجازة لمدة ٣ أيام، من ١٢ إلى ١٤ مارس، بسبب ظرف عائلي. "
     "وقد رتبت أعمالي مع زملائي لضمان سير العمل خلال غيابي. هل يمكن التفضل بالموافقة على الطلب؟ شاكرة لكم حسن تعاونكم. وتفضلوا بقبول فائق الاحترام."),
    ("06-tagreeda-sibaq", 2,
     "اكتب تغريدة قصيرة تدعو الناس إلى سباق الجري في الحي. المعلومات في `maelumat.txt`.",
     "الفعالية: سباق الحي للجري\nالموعد: الجمعة صباحًا\nالمسافة: ٥ كيلومترات\nالتسجيل: عند بوابة الحديقة\n",
     "tagreeda.md",
     [sent(2, 3), {"kind": "chars", "min": 60, "max": 140}, {"kind": "include", "words": ["سباق", "الجمعة"]}, {"kind": "no_latin"}, {"kind": "exclude", "words": ["أفضل"]}],
     "جاهز للجري؟ سباق الحي ينطلق يوم الجمعة صباحًا لمسافة ٥ كيلومترات. سجّل عند بوابة الحديقة وانضم إلينا!"),
]


@family("i18n-ar-write-notices", category="i18n", lang="text", kind="feature", n=len(SCENARIOS), mode="fixture",
        summary="native: Arabic constrained-writing tasks (Arabic-Indic digits, Arabic punctuation, no Latin letters) checked by a hidden script")
def ar_write(rng, n):
    voices = [
        "{intro}\n\nالشروط:\n{rules}\n\nاحفظ النتيجة في الملف `{path}`.",
        "{intro} شروط النص:\n{rules}\nاكتب الناتج في `{path}` من فضلك.",
        "{intro}\n\n{rules}\n\n(المطلوب حفظ النص في `{path}`.)",
    ]
    for i, (slug, d, intro, facts, path, constraints, solution) in enumerate(SCENARIOS[:n]):
        prompt = voices[i % 3].format(intro=intro, rules=render(constraints), path=path)
        yield writing_task(slug, d, prompt, {"maelumat.txt": facts}, path, constraints, solution, ["ar"], {"prompt_lang": "ar", "constraints": [c["kind"] for c in constraints]})
