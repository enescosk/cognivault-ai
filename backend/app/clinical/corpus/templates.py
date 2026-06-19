"""Branş bazlı argo/günlük Türkçe şikâyet şablonları — İP-1.2.

Şablonlar `{slot}` yer tutucuları içerir; `build.py` bunları deterministik
biçimde doldurarak çeşitli ama gerçekçi senaryolar üretir. Her şablon
kümesi bir yer-doğruluğu (ground-truth) aciliyet seviyesi taşır:

    ROUTINE  — ağrı/şişlik/kanama işareti yok, normal randevu.
    PRIORITY — ağrı/zonklama/şişlik/kanama içerir, ivedi slot.
    EMERGENCY — branştan bağımsız, 112/insan yükseltmesi gerektiren tablolar.

Etiket = şablon yazarının niyeti. Amaç doğal konuşma dilini (argo, ünlem,
yazım sapması, kod-değiştirme) yakalamak; cilalı tıbbi terim değil.
"""

from __future__ import annotations

from app.clinical.ontology import UrgencyLevel

# ─────────────────────────────────────────────────────────────────────────────
# Ortak slot doldurucuları
# ─────────────────────────────────────────────────────────────────────────────

FILLERS: tuple[str, ...] = ("", "ya", "yaa", "abi", "hocam", "valla", "ya hocam")

INTENSIFIERS: tuple[str, ...] = (
    "çok", "feci", "baya", "aşırı", "resmen", "dayanılmaz derecede", "müthiş",
)

TIME_AGO: tuple[str, ...] = (
    "iki gündür", "dünden beri", "bir haftadır", "sabahtan beri",
    "gece boyu", "birkaç gündür", "akşamdan beri", "üç gündür",
)

TEETH: tuple[str, ...] = (
    "üst azı dişim", "alt azı dişim", "ön dişim", "köpek dişim",
    "sağ üstteki diş", "sol alttaki diş", "kesici dişim", "azı dişim",
    "arka dişim", "alttaki diş",
)

REQUESTS: tuple[str, ...] = (
    "randevu alabilir miyim", "ne zaman gelebilirim", "bir bakabilir misiniz",
    "müsait yer var mı", "en yakın gün ne", "yarına yer var mı",
    "bugün gelsem olur mu", "acil bakabilir misiniz",
)

CHANNELS: tuple[str, ...] = ("whatsapp", "phone", "web", "form")


# ─────────────────────────────────────────────────────────────────────────────
# Branş şablonları: code → {urgency -> [şablonlar]}
# ─────────────────────────────────────────────────────────────────────────────

SpecialtyTemplates = dict[UrgencyLevel, tuple[str, ...]]

TEMPLATES: dict[str, SpecialtyTemplates] = {
    "genel_dis": {
        UrgencyLevel.ROUTINE: (
            "{filler} altı aylık kontrol zamanım geldi {request}",
            "dişlerime genel bir bakım yaptırmak istiyorum {request}",
            "{filler} diş taşı temizliği için {request}",
            "rutin diş kontrolü olmak istiyorum {filler} {request}",
            "uzun zamandır dişçiye gitmedim genel bakı olsun {request}",
            "{filler} dişlerim sararmış kontrol olayım {request}",
        ),
        UrgencyLevel.PRIORITY: (
            "{tooth} {time} {intensifier} ağrıyor {filler} {request}",
            "{filler} ağzımın içi {intensifier} rahatsız sürekli ağrı var {request}",
        ),
    },
    "restoratif": {
        UrgencyLevel.ROUTINE: (
            "{filler} dolgum düştü gene {request}",
            "{tooth} kırıldı bi parçası koptu {request}",
            "eski dolgularımı yeniletmek istiyorum {filler} {request}",
            "{filler} dişimde çürük var galiba dolgu lazım {request}",
            "{tooth} çatladı {request}",
        ),
        UrgencyLevel.PRIORITY: (
            "{tooth} kırıldı {intensifier} ağrıyor {filler} {request}",
            "dolgum düştü {tooth} {time} {intensifier} sızlıyor {request}",
        ),
    },
    "endodonti": {
        UrgencyLevel.ROUTINE: (
            "{filler} bana kanal tedavisi gerekiyormuş {request}",
            "geçen dişimin sinirini almışlardı devamı için {request}",
        ),
        UrgencyLevel.PRIORITY: (
            "{tooth} {intensifier} zonkluyor {time} uyuyamıyorum {request}",
            "{filler} gece ağrısı tutuyor {tooth} {intensifier} sızlıyor {request}",
            "{tooth} sinire vurdu sanırım {intensifier} ağrıyor {request}",
            "{filler} kanal tedavisi gereken diş {time} {intensifier} ağrıyor {request}",
            "soğuk sıcak değince {tooth} {intensifier} ağrıyor {request}",
        ),
    },
    "periodontoloji": {
        UrgencyLevel.ROUTINE: (
            "{filler} diş etlerim çekilmiş {request}",
            "diş taşı çok birikmiş diş eti tedavisi için {request}",
            "{filler} diş etlerimden kötü koku geliyor {request}",
        ),
        UrgencyLevel.PRIORITY: (
            "{filler} diş etlerim fırçalayınca {intensifier} kanıyor {time} {request}",
            "diş etim {intensifier} şişti kanıyor {filler} {request}",
            "diş etlerim {time} kanıyor durmuyor {request}",
        ),
    },
    "pedodonti": {
        UrgencyLevel.ROUTINE: (
            "{filler} çocuğumun süt dişi sallanıyor {request}",
            "5 yaşındaki çocuğuma diş kontrolü {request}",
            "{filler} çocuğumun dişinde çürük var {request}",
            "oğlumun süt dişleri için {request}",
        ),
        UrgencyLevel.PRIORITY: (
            "{filler} çocuğumun dişi {intensifier} ağrıyor {time} ağlıyor {request}",
            "çocuğun dişi kırıldı {intensifier} ağrıyor {request}",
        ),
    },
    "ortodonti": {
        UrgencyLevel.ROUTINE: (
            "{filler} dişlerim çapraşık tel taktırmak istiyorum {request}",
            "şeffaf plak ortodonti için bilgi almak istiyorum {request}",
            "{filler} braket fiyatları için {request}",
            "telim koptu yapıştırmak lazım {request}",
            "çocuğuma ortodonti gerekiyormuş {filler} {request}",
        ),
        UrgencyLevel.PRIORITY: (
            "{filler} telimin teli battı yanağım {intensifier} acıyor {request}",
        ),
    },
    "implantoloji": {
        UrgencyLevel.ROUTINE: (
            "{filler} eksik dişim var implant düşünüyorum {request}",
            "{tooth} yok yerine implant olsun istiyorum {request}",
            "implant kontrolü için {filler} {request}",
            "alt çenemde iki diş eksik implant için {request}",
        ),
        UrgencyLevel.PRIORITY: (
            "{filler} implant yaptırdığım yer {intensifier} şişti ağrıyor {request}",
        ),
    },
    "cene_cerrahisi": {
        UrgencyLevel.ROUTINE: (
            "{filler} yirmilik dişim çıkıyor çektirmek istiyorum {request}",
            "20lik dişim gömülü kalmış {request}",
            "{tooth} çekilecek demişlerdi {request}",
        ),
        UrgencyLevel.PRIORITY: (
            "{filler} yirmilik diş {intensifier} ağrıyor {time} şişti {request}",
            "gömülü diş {intensifier} sancıyor çenem {intensifier} ağrıyor {request}",
            "{filler} 20lik çıkarken diş eti şişti {intensifier} ağrıyor {request}",
        ),
    },
    "estetik_dis": {
        UrgencyLevel.ROUTINE: (
            "{filler} diş beyazlatma yaptırmak istiyorum {request}",
            "ön dişlerime lamina düşünüyorum {request}",
            "{filler} gülüş tasarımı için bilgi almak istiyorum {request}",
            "zirkonyum kaplama için {request}",
            "dişlerim sarı beyazlatma olur mu {filler} {request}",
        ),
        UrgencyLevel.PRIORITY: (
            "{filler} laminam düştü ön dişim açıkta {request}",
        ),
    },
    "dermatoloji": {
        UrgencyLevel.ROUTINE: (
            "{filler} yüzümde akne var dermatoloğa görünmek istiyorum {request}",
            "ciltteki lekeler için randevu {request}",
            "{filler} saç dökülmem arttı {request}",
            "sırtımda egzama çıktı {request}",
        ),
        UrgencyLevel.PRIORITY: (
            "{filler} bende ben var büyüdü {intensifier} kaşınıyor {request}",
        ),
    },
    "medikal_estetik": {
        UrgencyLevel.ROUTINE: (
            "{filler} botoks yaptırmak istiyorum {request}",
            "dudak dolgusu için bilgi almak istiyorum {request}",
            "{filler} cilt bakımı ve mezoterapi için {request}",
            "lazer epilasyon fiyatları {request}",
        ),
        UrgencyLevel.PRIORITY: (
            "{filler} dudak dolgusu yaptırdım {intensifier} şişti morardı {request}",
        ),
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Acil durum şablonları (branştan bağımsız) — her zaman EMERGENCY.
# (specialty_code, template) — acil tablo en olası branşa bağlanır.
# ─────────────────────────────────────────────────────────────────────────────

EMERGENCY_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("cene_cerrahisi", "{filler} yüzüm {intensifier} şişti gözüm kapanıyor"),
    ("cene_cerrahisi", "{filler} çenem kırıldı düştüm kanıyor"),
    ("cene_cerrahisi", "ağzımdaki şişlik boğazıma vurdu yutamıyorum {filler}"),
    ("periodontoloji", "{filler} diş çekiminden sonra kanama bir türlü durmuyor"),
    ("periodontoloji", "ağzımdan durmayan kanama var {filler}"),
    ("genel_dis", "{filler} nefes alamıyorum yüzüm şişti"),
    ("genel_dis", "bayıldı çocuğun ağzı kanıyor {filler}"),
    ("endodonti", "{filler} diş apsesi patladı yüzüm şişti yutkunamıyorum"),
)
