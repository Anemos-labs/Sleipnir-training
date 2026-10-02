"""Derived feature requests written in Indonesian."""
from fx import family

from ._derive import derive, take

ID = [
    ("feature-rb-tidelog-18-mean", "01-tidelog-rata-rata", "polite",
     "Minta tolong ya, untuk tidelog: `§0` mengembalikan rata-rata semua ketinggian sebagai bilangan bulat, dibulatkan ke "
     "atas pada nilai setengah (ke arah tak hingga positif, jadi `§1` menjadi `§2` dan `§3` menjadi `§4`), dan `§5` untuk "
     "tabel kosong. `§6` mengembalikan ketinggian tertinggi dikurangi ketinggian terendah (0 untuk satu pembacaan, `§7` "
     "untuk tabel kosong). Perilaku yang sudah ada tidak boleh berubah bagi pemanggil yang tidak memakai fitur ini."),
    ("feature-py-labelmaker-03-names", "02-labelmaker-catatan-desain", "short",
     "Ada catatan desain di `§0` untuk perubahan di labelmaker. Tolong kerjakan sesuai isinya, dan perbarui README-nya juga ya."),
    ("feature-py-meterreads-11-monthly", "03-meterreads-bulanan", "casual",
     "Bro, ada design note di `§0` buat perubahan di meterreads. Implementasikan yang diminta di situ. "
     "Test yang sudah ada jangan sampai rusak ya."),
    ("feature-java-seatmap-07-seat-map", "04-seatmap-peta-teks", "notes",
     "Catatan standup untuk seatmap.\n\n1. Peta kursi berbentuk teks\n"
     "   - `§0` mengembalikan peta kursi sebagai teks: satu baris per baris kursi, `§1`, dengan ROW berupa huruf barisnya, lalu "
     "satu spasi, lalu satu karakter per kursi dari kiri ke kanan: `§2` untuk kursi kosong dan `§3` untuk kursi yang sudah "
     "terisi. Setiap baris diakhiri newline.\n"
     "   - Peta selalu menampilkan keadaan terkini (pemesanan dan pembatalan).\n\n"
     "README-nya tolong diperbarui juga."),
    ("feature-js-notepad-08-words-events", "05-notepad-kata-event", "polite",
     "Permintaan untuk perubahan notepad berikutnya sudah ditulis di `§0`. Tolong implementasikan seperti yang tertulis di "
     "sana. Jangan menambah dependensi baru, ya."),
    ("feature-py-etlpipe-03-from-spec", "06-etlpipe-from-spec", "formal",
     "Bisakah Anda mengerjakan perubahan yang dijelaskan di `§0`? Catatan itu adalah spesifikasi lengkapnya; README "
     "menjelaskan cara kerja yang ada sekarang."),
    ("feature-rs-kvmem-08-ttl-watch", "07-kvmem-ttl-watch", "short",
     "Ada catatan desain di `§0` untuk perubahan di kvmem. Implementasikan yang diminta, tanpa dependensi baru."),
    ("feature-py-meterreads-03-config", "08-meterreads-config", "short",
     "Ada catatan desain di `§0` untuk perubahan di meterreads. Implementasikan yang diminta dan ikuti gaya kode di sekitarnya."),
]


@family("i18n-id-feature", category="i18n", lang="mixed", kind="feature", n=len(ID), mode="fixture",
        summary="derived: feature requests written in Indonesian (ruby, python, java, js, rust), d1-d5")
def id_feature(rng, n):
    for src, slug, style, prompt in take(ID, n):
        yield derive(src, prompt, slug, "id", style=style)
