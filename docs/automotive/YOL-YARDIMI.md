# Yol Yardım Hattı — telefon, WhatsApp ve çekici

Müşteri arar ya da WhatsApp'tan yazar → iş açılır → konum WhatsApp'tan gelir →
en yakın uygun çekiciye **otomatik** iş teklifi gider → çekici tek dokunuşla
kabul eder → müşteri her adımda bilgilendirilir.

Kod: `backend/app/automotive/roadside.py` (motor), `whatsapp.py` (Meta
biçimi), `phone.py` (Twilio), ekran: `frontend/src/components/automotive/RoadsideLine.tsx`.

## Akış

```
MÜŞTERİ                         SİSTEM                              ÇEKİCİ
arar / yazar ─────────────▶ iş açılır, sorun anlaşılır
                            (çekici · akü · lastik · yakıt · anahtar ·
                             elektrikli · kaza · bakım · arıza · …)
◀── "Güvende misiniz?"       [Güvendeyiz, kenarda] [Şeritte kaldım] [Yaralı / tehlike var]
◀── "📍 Konumunuzu paylaşın" (WhatsApp'ın yerel konum düğmesi)
◀── "Plaka ve model?"
◀── "Nereye götürelim?"      (yalnız çekici gereken işlerde; akü/lastik/yakıt yerinde)
◀── "Konumu ekiple paylaşalım mı?"
                            en yakın · uygun ekipmanlı · boşta · daha önce
                            reddetmemiş ekip seçilir ───────────▶ iş kartı + harita linki
◀── "En yakın ekibimize ilettik"                                  [15 dk'da gelirim] [30 dk'da gelirim] [Reddet]
◀── "✅ Kabul etti, ~15 dk"   ◀──────────────────────────────── kabul
                                                    ───────────▶ konum pini + [Yola çıktım]
◀── "🚛 Ekibimiz yola çıktı"  ◀──────────────────────────────── yola çıktı
◀── "Ekibimiz ulaştı"         ◀──────────────────────────────── [Ulaştım]
◀── "Aracınız taşınıyor"      ◀──────────────────────────────── [Araç yüklendi]
◀── "Tamamlandı"              ◀──────────────────────────────── [Teslim ettim]
```

Müşteri sırayı bozabilir (önce konum atabilir); yalnız **eksik olan** sorulur.
Sevk sonrası "nerede kaldı / kaç dakika" sorusuna ekibin bildirdiği süreyle,
"iptal" isteğine ekip kabul etmediyse otomatik, ettiyse danışman teyidiyle
cevap verilir.

## Değişmezler — bilinçli kararlar

| Karar | Neden |
|---|---|
| "Çekici yola çıktı" yalnız ekip **Yola çıktım**'a dokununca söylenir | Teklif ≠ kabul ≠ yola çıkış. Müsait ekip yokken "yolluyoruz" demek, insanı otoyol kenarında gelmeyecek bir çekiciyi beklemeye bırakır. |
| Acil sinyal (yaralı, yangın, duman, sıkıştı, nefes…) her aşamada akışı keser | 112 önce söylenir, iş danışmana düşer. Bu hat acil yardımın yerine geçmez. |
| "Şeritte kaldım" → öncelik + güvenlik tavsiyesi | Dörtlü, bariyerin arkası, reflektör; otoyolda 112'ye haber. Ekip kartında **ÖNCELİKLİ** yazar. |
| Ekip yanıtı yalnız ayarlardaki ekip numarasından, yalnız o ekibe atanmış iş için geçer | Müşteri "kabul" butonunu taklit edemez; başka ekip başkasının işini ilerletemez. |
| Yanıtsız teklif **5 dakikada** düşer, sıradaki ekibe geçer | Teslim edilemeyen mesajı ve telefona bakmayan şoförü aynı mekanizma yakalar. Uygun ekip kalmazsa iş danışmana düşer, müşteriye söylenir. |
| Aynı ekip iki açık işe atanamaz | Veritabanı tekilliği (`uq_automotive_active_team`). |
| Durum değişikliği + giden mesaj **tek işlemde** | Transactional outbox: ya ikisi birden yazılır ya hiçbiri. |
| Teslim durumu ayrı tabloda (`automotive_messages`) | Sağlayıcıdan sonradan gelir; iş kaydını güncelleseydi operatörün işlemiyle yarışırdı. |
| Arama hiçbir koşulda düşmez | İş açılamazsa (ayar eksik, hata) arayan yine dispeçere aktarılır. |
| Telefonda "WhatsApp'tan mesaj gönderdik" yalnız mesaj gerçekten kuyruğa girdiyse söylenir | Gönderim kapalıysa ya da şablon yoksa bu cümle kurulmaz. |
| Müşteri numarası panelde maskeli | Ham numara yalnız gönderim için sunucuda; arama indeksi numaranın sha256 özeti. |

## WhatsApp 24 saat kuralı — neden şablon gerekiyor

İşletme, son 24 saatte kendisine **yazmamış** birine serbest mesaj gönderemez;
yalnız Meta'nın önceden onayladığı şablon gidebilir. Pratikte:

- **Müşteri WhatsApp'tan yazdıysa** → pencere açık, tüm sorular serbest mesajla gider.
- **Müşteri telefonla aradıysa** → pencere kapalı. Konum isteği **şablonla** gider;
  müşteri şablondaki "Konum göndereceğim" düğmesine dokununca pencere açılır ve
  WhatsApp'ın yerel konum düğmesi gönderilir.
- **Çekiciye ilk iş teklifi** → pencere kapalı, **şablonla** gider. Şoför bir
  düğmeye dokununca pencere açılır; sonraki adımlar (konum pini, "Yola çıktım"…)
  serbest mesajla gider.

Sistem her mesajda pencereyi kontrol edip seçer. Şablon tanımlı değilse mesaj
`blocked_no_template` olur, **"gönderildi" denmez** ve iş danışmana düşer.

### Meta'ya onaya gönderilecek şablonlar (kategori: UTILITY, dil: tr)

Metinler öneridir; Meta onayından önce hukuk/marka ile gözden geçirin.

**1. `yol_yardim_konum`** — telefonla arayan müşteriye konum isteği
> Merhaba, {{1}} talebiniz için kaydınızı açtık. Size en yakın ekibimizi
> yönlendirebilmemiz için lütfen aşağıdaki düğmeye dokunup konumunuzu paylaşın.

Hızlı yanıt düğmesi: `Konum göndereceğim` · `{{1}}` örneği: *çekici çağır*

**2. `yol_yardim_durum`** — penceresi kapalı müşteriye durum bildirimi
> Yol yardım talebinizle ilgili güncelleme: {{1}}

`{{1}}` örneği: *Ekibimiz yola çıktı, yaklaşık 20 dakika.*

**3. `yol_yardim_is_teklifi`** — çekiciye iş teklifi
> Yeni yol yardım işi: {{1}}. Mesafe: {{2}}. Araç: {{3}}. Konum: {{4}}

Hızlı yanıt düğmeleri (bu sırayla): `15 dk'da gelirim` · `30 dk'da gelirim` · `Reddet`

Düğmelerin **kimliği** her gönderimde o işe özgü verilir (`t:accept15:<iş>`);
şablonun kendisi her iş için aynıdır.

## Kurulum (canlı)

1. **Ayrı Meta uygulaması + WhatsApp Business numarası.** Oto servis ayrı bir
   işletmedir; klinik tarafının `META_*` ayarlarıyla karışmaz.
2. Webhook adresi: `https://<alan-adı>/api/automotive/webhooks/whatsapp`
   (doğrulama: `AUTOMOTIVE_META_VERIFY_TOKEN`; imza her zaman zorunlu).
3. Yukarıdaki 3 şablonu onaya gönderin.
4. `.env`:
   ```
   AUTOMOTIVE_INBOUND_OWNER_EMAIL=dispec@firma.com     # gelen işlerin sahibi
   AUTOMOTIVE_BRAND=Firma Yol Yardım
   AUTOMOTIVE_SERVICE_NAME=Firma Oto Servis
   AUTOMOTIVE_WHATSAPP_ENABLED=true
   AUTOMOTIVE_WHATSAPP_PHONE_NUMBER_ID=...
   AUTOMOTIVE_META_ACCESS_TOKEN=...
   AUTOMOTIVE_META_APP_SECRET=...
   AUTOMOTIVE_META_VERIFY_TOKEN=...
   AUTOMOTIVE_WA_TEMPLATE_CUSTOMER_LOCATION=yol_yardim_konum
   AUTOMOTIVE_WA_TEMPLATE_CUSTOMER_UPDATE=yol_yardim_durum
   AUTOMOTIVE_WA_TEMPLATE_TEAM_OFFER=yol_yardim_is_teklifi
   AUTOMOTIVE_TEAM_PHONES={"atlas-01": "+90...", "atlas-02": "+90..."}
   ```
   Telefon için ayrıca `AUTOMOTIVE_VOICE_ENABLED`, `AUTOMOTIVE_INBOUND_NUMBER`,
   `AUTOMOTIVE_DISPATCH_NUMBER`, `AUTOMOTIVE_WEBHOOK_BASE_URL` (bkz. `.env.example`).
5. **Outbox worker çalışmalı:** `python -m app.workers.outbox_worker`. Mesajları
   o gönderir ve yanıtsız teklifleri o düşürür. Worker yoksa mesajlar `queued`
   kalır ve zaman aşımı işlemez.

## Demo (numara olmadan)

Operatör olarak giriş → **Oto Servis Pilotu → Yol yardım hattı**. Solda müşteri,
sağda çekici şoförünün WhatsApp'ı simüle edilir; düğmeler tıklanabilir, akış
canlıdaki kodun aynısından geçer, hiçbir numaraya mesaj gitmez. "Telefonla ara"
ile çağrı yolu, "teklif süresini doldur" ile zaman aşımı denenir.

Simülatör **canlı WhatsApp açıkken kapalıdır** — aksi halde operatör panelden
herhangi bir numaraya gerçek mesaj attırabilirdi.

## Bilinen sınırlar

- **Ekipler kodda sabit** (`operations.TEAMS`): konum, kapsama yarıçapı,
  ekipman, müsaitlik. Ekip yönetimi ekranı ve canlı müsaitlik yok.
- **Mesafe kuş uçuşu**, varış süresi değil. Varış tahmini ekibin beyanıdır.
- **Anahtar içeride** işine uygun ekip (çilingir) yok → her zaman danışmana düşer.
- **Sesli mesaj / fotoğraf işlenmiyor**; müşteriden yazması istenir. (Yerel
  Whisper zaten var; medya indirme eklenirse sesli mesaj da anlaşılabilir.)
- **Tek dağıtım = tek işletme**: gelen işlerin tek sahibi var
  (`AUTOMOTIVE_INBOUND_OWNER_EMAIL`).
- **Ücret hesaplanmaz**; fiyat soruları ekip/danışman teyidine bırakılır.
- **KVKK:** konum, talep edilen hizmetin ifası için ekiple paylaşılır; yine de
  müşteriye açıkça sorulur ve reddederse ekip yerine danışman arar. Aydınlatma
  metni ve ekiplerin (taşeronsa) veri işleyen sözleşmesi canlıdan önce hukukla
  netleşmeli.
- Meta API sürümü `whatsapp.py` içinde sabit (`v21.0`); yükseltme orada yapılır.
