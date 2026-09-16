# Ses & Telefon Alanı — Takvimli Yol Haritası

> **Kapsam:** yalnız ses ve telefon hattı (ROADMAP-2026-09.md'deki **F1** ve
> **F2**). Diğer fazlar bu dosyanın konusu değil.
>
> **Başlangıç:** 2026-09-16 (Çarşamba) · **Hedef:** F1 kabul kapısı 2026-09-28
>
> Durum etiketleri: `⬜ AÇIK` · `🔵 ŞU AN` · `🟡 DEVAM` · `✅ YAPILDI` · `⛔ BLOKE`

---

## Takvimin tek kuralı

**Numara tedariki bizde değil, kod bizde.** 1.1 (Netgsm SIP trunk + coğrafi +90
numara) idari bir süreç; ne kadar süreceğini biz belirlemiyoruz. Bu yüzden
takvim tek sıra hâlinde değil, **iki paralel hat** olarak kurulur:

- **Hat A — Kod (bizde):** bugün başlar, numaraya bakmaz.
- **Hat B — Tedarik (dışarıda):** bugün *başvurusu yapılır*, sonra beklenir.

İkisi 1.5'te (ilk gerçek arama) buluşur. Hat B gecikirse Hat A yine de ilerler;
Hat A gecikirse ilk arama anlamsız olur — çünkü arayan insanın söyleyeceği ilk
cümleleri sistem anlamaz.

---

## Haftalık takvim

| Tarih | Gün | Madde | Hat | Süre | Durum |
|---|---|---|---|---|---|
| **09-16** | Çar | **1.1** Netgsm SIP trunk + numara **başvurusu** | B | 1 sa | ⬜ |
| 09-16 | Çar | **1.6** Niyet katmanını telefon akışına taşı | A | ~~2 gün~~ 1 gün | ✅ |
| 09-17 | Per | **1.7** Klinik bazlı karşılama + anons kısaltma | A | 1 gün | 🔵 |
| 09-22 | Sal | **1.6+1.7 regresyon** — `simulate_call` ile uçtan uca | A | 0.5 gün | ⬜ |
| 09-23 | Çar | **1.2** Twilio SIP Domain + IP ACL | B | 0.5 gün | ⛔ 1.1 |
| 09-23 | Çar | **1.3** Public HTTPS (ngrok → domain + TLS) | B | 0.5 gün | ⬜ |
| 09-24 | Per | **1.4** `bind_channel` + strict mod | B | 0.5 gün | ⛔ 1.1 |
| **09-25** | **Cum** | **1.5 İlk gerçek arama** | A+B | 0.5 gün | ⛔ hepsi |
| 09-28 | Pzt | **F1 kabul kapısı** — 90 sn içinde SMS + panelde randevu | — | — | ⬜ |
| 09-29 → 10-02 | Sal–Cum | **F2** Gerçek cihaz QA — 12 senaryo | — | 3-4 gün | ⬜ |
| 10-05 | Pzt | **1.8 kararı** — Yol B'ye geçilecek mi? | — | 0.5 gün | ⬜ |

> **09-25 tarihi 1.1'e bağlıdır.** Numara o güne yetişmezse Hat A tarihleri
> sabit kalır, Hat B ve 1.5 kayar. Takvimi yeniden yazmaya gerek yok — kayan
> satırların tarihini güncelle, gerekçeyi Değişiklik Günlüğü'ne yaz.

---

## Maddeler — ne bitti sayılır

### 1.6 — Niyet katmanını `phone_flow_service`'e taşı · ✅ YAPILDI (2026-09-16)
**Neden ilk:** telefonu açan insanın söyleyeceği ilk cümleler ("kimsiniz?",
"meşgulüm", "ne kadar tutuyor?") bugün telefon akışında karşılıksız. Numara
gelmeden bu kapanmazsa ilk gerçek arama kötü bir izlenimle biter.

**Ne yapılacak:** deterministik niyet sınıflandırıcısı ortak bir modüle çıkarılır;
`voice_studio_service` ve `phone_flow_service` ikisi de onu kullanır. **Yanıt
metinleri ortaklaşmaz** — stüdyo satış dilinde, telefon klinik dilinde konuşur.
Ortaklaşan tek şey "kullanıcı ne demek istedi" kararıdır.

**Dokunulmaz:** acil vaka ve insan-yükseltme yolları. Niyet katmanı
`shadow_review` üretilen turlarda **devreye girmez**; mevcut eskalasyon yanıtı
korunur.

**Kabul:** telefon akışında 8 niyet için test var; acil vaka regresyon testi
yeşil; `simulate_call` ile uçtan uca oynatıldığında akış slot teklifine takılmıyor.

**Sonuç:** ortak modül `app/ai/caller_intent.py`; 14 yeni test; paket 5399 yeşil;
`simulate_call --all` → 22/22 kapı. Yolda aracın kendisinde **iki yanlış kırmızı**
bulundu ve düzeltildi (native TTS'te metin göremeyen acil kontrolü; yeniden
kullanılan görüşmeyi bulamayan DB doğrulaması). Tahmin 2 gündü, 1 günde kapandı.

### 1.7 — Klinik bazlı karşılama · ⬜
**Kabul:** iki farklı kliniğe bağlı iki numara arandığında karşılama metni ve
sesi farklı geliyor; anons 20 kelimenin altında; detaylı aydınlatma SMS ile
gidiyor; `voice_profile`'daki ses karakteri telefonda da duyuluyor.

### 1.1–1.4 — Hat B · ⬜
**Kabul:** `docs/ops/netgsm-twilio-sip-trunk-kurulumu.md` adım adım koşuldu,
`bind_channel --list` numarayı doğru klinikte gösteriyor,
`CLINICAL_WEBHOOK_SIGNATURE_REQUIRED=true` ile imza doğrulaması geçiyor.

### 1.5 — İlk gerçek arama · ⛔
**Kabul:** bir insan telefonu eline alıp arıyor, konuşuyor, **90 saniye içinde**
onay SMS'i geliyor, randevu operatör panelinde slot'a bağlı görünüyor, elle
müdahale yok. Kayıt alınır, gecikmeler ölçülür.

### 1.8 — Yol B kararı · ⬜
F1 kapandıktan sonra verilir, **pilot sözleşmesi imzalanmadan önce**. Karar
girdisi: 1.5'te ölçülen Twilio STT doğruluğu + gecikme, ve pilot kliniğin
sınır-ötesi işlemeye bakışı.

---

## Riskler

| Risk | Etki | Ne yapıyoruz |
|---|---|---|
| Numara tedariki uzar | 1.5 kayar, F2 kayar | Hat A'yı numaraya bağlamadık; kod numara gelmeden hazır olur |
| Twilio STT Türkçe'de zayıf çıkar | 1.5 kabul kapısı geçmez | 1.5'te doğruluk ölçülür; kötüyse 1.8 öne alınır |
| Anons uzunluğu arayanı kaçırır | Pilot metrikleri bozulur | 1.7'de 20 kelime sınırı kabul kriteri |
| Telefon STT'si ABD'de (KVKK) | Pilot sözleşmesi riski | Bilinçli kabul; sözleşmede açıkça yazılacak, 1.8 kalıcı çözüm |

---

## Haftalık kontrol noktası

**Her Pazartesi:** bu tablodaki durum etiketlerini güncelle, kayan satırların
tarihini düzelt, gerekçeyi `ROADMAP-2026-09.md`'nin Değişiklik Günlüğü'ne yaz.
Tahmini süreleri geçmişe dönük düzeltme — kaymanın kendisi bilgidir.

---

## Değişiklik Günlüğü

- **2026-09-16 (ii)** — **1.6 kapandı.** Niyet katmanı ortak modüle çıkarıldı ve
  telefon akışına bağlandı; tıbbi içerik koruması (`conversational_only`) ile
  birlikte. `simulate_call`'daki iki yanlış kırmızı da yolda düzeltildi. Sıradaki:
  **1.7 — klinik bazlı karşılama**.
- **2026-09-16** — Dosya oluşturuldu. F1'in 1.6–1.8 maddeleri tarihlendirildi,
  tedarik ve kod işleri iki ayrı hatta ayrıldı. 1.6 başlatıldı.
