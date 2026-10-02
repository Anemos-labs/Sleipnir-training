"""Derived bug-fix tasks written in Arabic (right-to-left prose around left-to-right code)."""
import re

from fx import family

from ._derive import derive, source, take

# the Arabic words of the source prompt, verbatim (the vowelled spelling matters to the checker's fixture)
_AR = re.findall(r"[؀-ۿ]+", source("fix-hand-unicode-fold-12-marks-limited-range")["prompt"])

AR = [
    ("fix-hand-sort-order-07-median-sorted-as-text", "01-typical-price", "digits",
     "في قائمة المنتجات يظهر «السعر المعتاد» بقيمة غير منطقية عندما تختلف الأسعار في عدد الخانات: للأسعار ٥ و٢٥ و١٠٠ و١ "
     "يعطي ٦٢٫٥ بدلًا من ١٥، وللأسعار ١٠ و٩ و١٠٠ يعطي ١٠٠ بدلًا من ١٠. يبدو أن الأرقام تُرتَّب كنصوص."),
    ("fix-hand-text-encoding-02-bare-cr-left-alone", "02-bare-cr", "casual",
     "أسطر السجل القادمة من خادم الطباعة القديم المبني على Mac تصل ملتصقة ببعضها: الملف يستخدم CR وحده فاصلًا بين الأسطر، "
     "والـ normaliser عندنا يتركه كما هو، فيصبح الملف كله سطرًا واحدًا ضخمًا. ملفات Windows ذات CRLF سليمة."),
    ("fix-hand-config-merge-02-bool-from-truthiness", "03-app-debug", "terse",
     "`§0` يترك وضع debug مفعّلًا، وكذلك `§1` يبقى مفعّلًا. طبعتُ ما يُرجعه التحويل للنص \"false\" فكانت النتيجة: True. "
     "المفروض أن يفهم false/no/off/0."),
    ("fix-hand-config-merge-04-lists-are-concatenated", "04-list-override", "terse",
     "إعداد `§0` يتضخم بدل أن يُستبدل: مع القيمة الافتراضية `§1` وملف إعدادات فيه `§2` نحصل على `§3`. "
     "المفروض أن تحلّ القائمة القادمة من الملف محلّ الافتراضية لا أن تُضاف إليها."),
    ("fix-hand-unicode-fold-12-marks-limited-range", "05-arabic-search",
     "native",
     "البحث غير الحسّاس للتشكيل يعمل مع الملاحظات الفرنسية والتركية لكنه لا يعمل مع العربية والعبرية: البحث عن " + _AR[0] +
     " لا يجد الملاحظات التي فيها الكتابة المشكولة " + _AR[1] + ". ملف README يقول إن `§0` تحذف كل العلامات المركّبة "
     "(combining marks)."),
    ("fix-hand-date-ranges-03-day-not-clamped-to-the-month", "06-billing-day-31", "report",
     "توقّف تشغيل الفوترة الشهرية عند اليوم 31 من شهر طويل مع الخطأ `§0` أثناء نقل تاريخ فوترة عميل بمقدار شهر واحد:\n\n"
     "```\n¶0\n```\n\nملف README ينص على أن اليوم يُقصّ إلى آخر يوم من الشهر المستهدف."),
    ("fix-hand-cart-flow-10-tax-rounded-per-line", "07-tax-per-class", "ticket",
     "سطران قيمة كل منهما 1.02 يظهر لهما في الفاتورة 0.20 + 0.20 ضريبةً بنسبة 20 %. قاعدتنا الضريبية أن نقرّب مرة واحدة لكل "
     "فئة ضريبية على مجموع المبالغ (2.04 تعطي 0.41)."),
    ("fix-hand-event-ledger-05-snapshot-forgets-the-keys", "08-snapshot-keys", "story",
     "الحركات المكرّرة تعود بعد إعادة التشغيل. حركة `§0` مرتبطة بدفعة بالمفتاح `§1` طُبّقت قبل اللقطة (snapshot)، وعندما أعاد "
     "معالج الدفع محاولتها بعد إعادة التشغيل ارتفع المخزون مرة ثانية. بدون إعادة تشغيل تُتجاهل المحاولة المعادة كما يجب."),
    ("fix-hand-error-flow-06-retry-silent-and-no-rollback", "09-importer-two-symptoms", "detailed",
     "عَرَضان في أداة الاستيراد أظن أن لكل منهما سببًا مختلفًا. (1) أداة إعادة التشغيل التي تحاكي الوجهة المتقطعة "
     "(flaky-sink replay harness) لم تعد ترى أي عملية استيراد مُلغاة حتى عندما تفشل الوجهة في كل كتابة، لكن أعداد الصفوف "
     "خاطئة. (2) عندما يفشل الـ commit النهائي تفشل عملية الاستيراد التالية على الاتصال نفسه برسالة 'transaction already "
     "open'. كلاهما كان يعمل سابقًا، والاختبارات الظاهرة لا تختبر حالات الفشل إطلاقًا. أرجو أن تجد الخلل في كل موضع."),
]


@family("i18n-ar-fix", category="i18n", lang="mixed", kind="fix", n=len(AR), mode="fixture",
        summary="derived: bug reports written in Arabic (python, js, go), d1-d5, right-to-left prose around code")
def ar_fix(rng, n):
    for src, slug, style, prompt in take(AR, n):
        yield derive(src, prompt, slug, "ar", style=style)
