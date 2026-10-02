"""Derived research questions (answer mode) in Turkish."""
from fx import family

from ._derive import derive, take

TR = [
    ("research-quick-facts-01-tiny-1hop", "01-annex-yeniden-aciliyor", "friendly",
     "Merhaba, Ullswater Annex yeni zemin yapımı için kapandıktan sonra hangi tarihte yeniden açılıyor? "
     "Cevabı YYYY-MM-DD biçiminde yaz lütfen. Teşekkürler!"),
    ("research-quick-facts-16-tiny-1hop", "02-guvenlik-yelegi", "friendly",
     "Selam, ekipman komitesi kaç tane güvenlik yeleği almaya karar verdi? Teşekkürler!"),
    ("research-quick-facts-11-small-2hop", "03-beceri-gunu-salonu", "friendly",
     "Beceri günü için salonu kim ayırtmış? Soyadını ve directory.csv'deki ekibini yazar mısın? Teşekkürler!"),
    ("research-authority-lookup-01-value", "04-kopru-yuk-siniri", "careful",
     "Quartz Footbridge'in yük sınırı nedir? Yanıtını `§0` satırıyla bitir. Tahmin yürütme; dosyalar söylemiyorsa bana söyle."),
    ("research-byelaw-lookup-01-value-on", "05-tezgah-ucreti-tarihte", "careful",
     "Bu klasördeki hukuk arşivine göre, Market Hall Regulations kapsamında 25 Kasım 2034 tarihinde tezgah ücreti "
     "(stall fee) rakamı neydi? Yanıtını `§0` satırıyla bitir. Lütfen sonraki belgelerle de karşılaştır, bu metinler "
     "sık değişiyor."),
    ("research-incident-lookup-04-month-minutes", "06-kesinti-dakikalari", "overwhelmed",
     "Bu klasörü devraldım ve içinde kayboldum. No. 37 Basalt için Mayıs 2031'deki toplam kesinti dakikasını hesaplar mısın? "
     "Tek bir sayı istiyorum, sadece sayı."),
    ("research-thread-approvals-09-who", "07-talep-karari", "brief",
     "Kısa bir soru: satın alma politikasına göre REQ-0140 talebinde yürürlükteki kararı kim vermiş ve hangi tarihte? "
     "Soyadını ve tarihi YYYY-MM-DD olarak yaz, son satıra da `§0` ekle."),
    ("research-timeline-gaps-09-gap", "08-proje-takvimi-fark", "deadline",
     "Yarınki toplantıdan önce lazım: proje başlangıç toplantısının yapıldığı olaydan pilotun bittiği olaya kadar kaç gün "
     "geçmiş? Planlanan değil, gerçekleşen tarihleri kullan. Yanıtını `§0` satırıyla bitir."),
    ("research-tariff-bill-04-bill", "09-fatura-tutari", "formal",
     "Müşteri Faturalama ekibinden bir soru: AC-5033 hesabının 2033-10-09 tarihli okumasından bir sonraki okumasına kadar "
     "olan ölçüm dönemi için fatura tutarı nedir? Kredi cinsinden, iki ondalıkla ve ondalık ayracı nokta olacak şekilde yaz. "
     "Faturaların nasıl hesaplandığı README'de anlatılıyor. Hangi dosyadan aldığını da göster."),
    ("research-compat-matrix-01-newest", "10-uyumlu-surum", "quick",
     "Kısa bir soru: kurulumumuzda Umber 2.3.1 ve Quillon 1.0.0 yüklü. Bununla uyumlu en yeni Dunnock hangisi? "
     "(Gereksinimleri iki yönlü kontrol etmeyi ve geri çekilmiş sürümleri atlamayı unutma.) Teşekkürler!"),
]


@family("i18n-tr-research", category="i18n", lang="text", kind="research", n=len(TR), mode="answer",
        summary="derived: lookup and reasoning questions over a local document corpus, in Turkish")
def tr_research(rng, n):
    for src, slug, style, prompt in take(TR, n):
        yield derive(src, prompt, slug, "tr", style=style)
