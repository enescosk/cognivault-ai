"""Arayan niyeti — deterministik sınıflandırıcı (saf, DB'siz, ağsız).

Telefonu açan insanın söyleyeceği ilk cümleler ("kimsiniz?", "tekrar eder
misiniz?", "yetkiliye bağlayın") bir randevu cümlesi değildir; küçük bir yerel
modele sorulduğunda da güvenilir çözülmezler. Bu modül o kararı **kuralla**
verir: aynı girdi her zaman aynı niyeti üretir, ölçülebilir ve denetlenebilir.

Neden ortak modül: aynı tablo hem operatör prova stüdyosunda
(`voice_studio_service`) hem gerçek telefon akışında (`phone_flow_service`)
kullanılır. **Ortaklaşan tek şey niyet kararıdır** — yanıt metinleri kanala
aittir ve burada durmaz: stüdyo satış dilinde, klinik hattı klinik dilinde
konuşur. Metinleri de ortaklaştırmak, iki kanalın birbirinin ağzıyla konuşması
demek olurdu.

Sınıflandırıcı eşleşme bulamazsa `None` döner — çağıran taraf kendi varsayılan
akışına devam eder. Yani bu katman akışı **genişletir**, ele geçirmez.
"""
from __future__ import annotations

import re
from collections.abc import Collection

from app.ai.text_understanding import normalize_for_intent

# ─────────────────────────────────────────────────────────────────────────────
# Türkçe zaman ifadesi — konuşmacının KENDİ sözünden okunur
# ─────────────────────────────────────────────────────────────────────────────
# Tarihsel hata: zaman, modelin döndürdüğü metnin kullanıcının cümlesinde
# aranmasıyla doğrulanıyordu. Model "saat 15" yerine "15:00" yazınca eşleşme
# kırılıyor ve asistan aynı soruyu tekrar tekrar soruyordu. Karar artık burada.
DAY_WORDS = (
    'bugun', 'yarin', 'obur gun', 'pazartesi', 'sali', 'carsamba', 'persembe',
    'cuma', 'cumartesi', 'pazar', 'hafta ici', 'hafta sonu', 'haftaya',
    'gelecek hafta', 'onumuzdeki', 'ayin',
)
HOUR_WORDS = (
    'birde', 'ikide', 'ucte', 'dortte', 'beste', 'altida', 'yedide', 'sekizde',
    'dokuzda', 'onda', 'on birde', 'on ikide', 'yarimda', 'bucukta', 'sabah',
    'ogleden sonra', 'aksamustu',
)
CLOCK = re.compile(r'\b\d{1,2}[:.]\d{2}\b')


def stated_time(text: str) -> bool:
    """Konuşmacı gerçekten bir gün/saat söyledi mi?"""
    n = normalize_for_intent(text)
    if any(word in n for word in DAY_WORDS) or any(word in n for word in HOUR_WORDS):
        return True
    # Saat ayıracı HAM metinde aranır: normalize ':' ve '.' karakterlerini siler,
    # "15:30" normalize edilince "15 30" olur ve kalıp kaçar.
    if CLOCK.search(text):
        return True
    return 'saat' in n and re.search(r'\b\d{1,2}\b', n) is not None


AFFIRMATIVE = (
    'evet', 'tabii', 'tabi', 'elbette', 'buyurun', 'olur', 'tamam', 'dogru',
    'peki', 'anlatabilirsiniz', 'musaitim', 'dinliyorum',
)


def short_affirmative(normalized: str) -> bool:
    """Kısa onay ("Evet, doğrudur.") — küçük model bunu randevu sanabiliyordu.

    Girdi `normalize_for_intent`'ten geçmiş olmalıdır.
    """
    return (
        len(normalized.split()) <= 4
        and normalized.startswith(AFFIRMATIVE)
        and 'hayir' not in normalized
        and 'degil' not in normalized
    )


# ─────────────────────────────────────────────────────────────────────────────
# Niyet tablosu
# ─────────────────────────────────────────────────────────────────────────────
# Sıra önemlidir: önce görüşmeyi bitiren/güvenlik kuralları, sonra konuşmayı
# ilerleten niyetler. İlk eşleşen kazanır.
RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('stop', ('bir daha arama', 'aramayin', 'aramani istemiyorum', 'ilgilenmiyorum',
              'gorusmeyi bitir', 'hosca kal', 'hoscakal', 'kapatiyorum', 'istemiyoruz')),
    ('wrong_number', ('yanlis numara', 'yanlis sirket', 'burasi degil', 'boyle bir sirket yok')),
    ('out_of_scope', ('makarna', 'yemek tarifi', 'hava durumu', 'hava nasil', 'mac sonucu',
                      'futbol', 'siyaset', 'bitcoin', 'siir yaz', 'sifreyi soyle',
                      'talimatlari unut', 'sistem promptu')),
    ('repeat', ('anlamadim', 'tekrar eder misiniz', 'tekrarlar misiniz', 'duyamadim',
                'ne dediniz', 'sesiniz kesildi')),
    ('identity', ('kimsiniz', 'kiminle gorusuyorum', 'nereden ariyorsunuz', 'hangi sirket',
                  'robot musunuz', 'insan misiniz', 'gercek misiniz')),
    ('busy', ('musait degilim', 'toplantidayim', 'simdi olmaz', 'sonra arayin', 'yogunum',
              'mesgulum', 'arabadayim', 'sonra konusalim')),
    ('human', ('yetkiliye baglayin', 'insanla gorusmek', 'satis ekibi', 'birine baglayin',
               'muduru', 'yetkiliyle gorusmek')),
    ('email', ('mail atin', 'e posta', 'eposta', 'mail gonderin', 'bilgi gonderin',
               'dokuman gonderin', 'sunum gonderin')),
    ('message', ('mesaj birakmak', 'mesaj birakabilir', 'not birakmak', 'mesaj iletebilir')),
    ('pricing', ('fiyat', 'ucret', 'ne kadar', 'maliyet', 'abonelik', 'kac para')),
)

ALL_INTENTS: frozenset[str] = frozenset(name for name, _ in RULES)

# Klinik telefon hattında bu katmanın ele alacağı alt küme. Dışarıda bırakılanlar
# bilerek dışarıda: `pricing` ve `email` klinik tarafında zaten ingest'in kendi
# intent'lerine (ASK_PRICE vb.) bağlı, `busy`/`message` ise giden arama kurgusuna
# ait. Burada tekrar ele almak, çalışan bir yolu ikinci kez cevaplamak olurdu.
PHONE_INTENTS: frozenset[str] = frozenset(
    {'stop', 'wrong_number', 'out_of_scope', 'repeat', 'identity', 'human'}
)


# ─────────────────────────────────────────────────────────────────────────────
# Tıbbi içerik koruması
# ─────────────────────────────────────────────────────────────────────────────
# Klinik hattında bu katmanın devreye girmesi için sözün **görüşmenin kendisi**
# hakkında olması gerekir. Tehlike şurada: "Anlamadım, dişim çok ağrıyor"
# cümlesi `repeat` kuralına takılır ve asistan tıbbi içeriği yutup "tekrar
# ediyorum" der. Belirti kelimesi geçen ya da uzun söylemler bu katmana
# bırakılmaz — mevcut triyaj/eskalasyon yolu işler.
MEDICAL_SIGNALS = (
    'agri', 'agriyor', 'aciyor', 'zonkl', 'sisti', 'sislik', 'kanama', 'kaniyor',
    'apse', 'iltihap', 'ates', 'nefes', 'bayil', 'travma', 'kirildi', 'kirik',
    'dusuk', 'acil', 'yaralan', 'morar', 'uyusma',
)
MAX_CONVERSATIONAL_WORDS = 10


def conversational_only(text: str) -> bool:
    """Söz, tıbbi içerik taşımayan, görüşmenin kendisi hakkında kısa bir söz mü?

    İki kapı birden: belirti kelimesi geçmeyecek VE kısa olacak. Uzun söylemler
    neredeyse her zaman gerçek bir talep taşır; onları konuşma katmanına
    bırakmak, asıl içeriği duymamak demektir.
    """
    n = normalize_for_intent(text)
    if len(n.split()) > MAX_CONVERSATIONAL_WORDS:
        return False
    return not any(signal in n for signal in MEDICAL_SIGNALS)


def classify_caller_intent(
    text: str, *, allowed: Collection[str] | None = None
) -> str | None:
    """Metni niyet tablosuna göre sınıflandırır; eşleşme yoksa None.

    `allowed` verilirse yalnız o niyetler değerlendirilir — kanalın ele almadığı
    bir niyet, tabloda daha önce geldiği için gerçek eşleşmeyi gölgelemesin diye
    filtre eşleşmeden ÖNCE uygulanır.
    """
    normalized = normalize_for_intent(text)
    for intent, phrases in RULES:
        if allowed is not None and intent not in allowed:
            continue
        if any(phrase in normalized for phrase in phrases):
            return intent
    return None
