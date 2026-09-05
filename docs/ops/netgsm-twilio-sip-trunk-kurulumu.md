# Netgsm ↔ Twilio SIP Trunk Kurulumu (Yol A)

> **Amaç:** Türk hastaların arayabileceği bir **coğrafi +90 numara**yı Netgsm'den
> alıp, çağrıyı SIP trunk ile Twilio'ya taşımak. Böylece mevcut TwiML tabanlı
> telefon akışı (`/api/webhooks/voice/*`, `phone_flow_service`) **hiç değişmeden**
> gerçek bir +90 numarada çalışır.
>
> **Neden bu yol:** Twilio Türkiye'de yerel numara **satmıyor**. Numarayı Türk
> operatörden (Netgsm) alıp Twilio'ya SIP ile besliyoruz; Twilio yalnızca "beyin"
> (TwiML + STT). Ses hâlâ Twilio ABD STT'sinden geçtiği için KVKK açısından
> sınır-ötesi işlemci sorunu **devam eder** — kalıcı çözüm Yol B (Netgsm-native +
> lokal Whisper). Bkz. kod: `backend/app/api/routes/clinical.py` (TwiML uçları).

## Mimari (çağrı yolu)

```
Hasta (PSTN)
   │  arar → +90 312 XXX XX XX  (Netgsm coğrafi numara)
   ▼
Netgsm SIP Trunk  ──(SIP INVITE, hedef: cognivault-klinik.sip.twilio.com:5060)──►
   ▼
Twilio SIP Domain (IP ACL ile Netgsm'i tanır)
   │  "A CALL COMES IN" → HTTP POST (X-Twilio-Signature imzalı)
   ▼
CogniVault backend  POST /api/webhooks/voice/incoming
   │  → TwiML (<Gather input="speech" tr-TR> + <Play> kendi TTS'imiz)
   │  → SpeechResult → /api/webhooks/voice/gather → phone_flow_service
   ▼
Randevu slotu kilit + hasta/doktor SMS (Netgsm SMS)
```

İki ayrı "hop" var, ikisini de ayrı güvenlik altına alıyoruz:
1. **Netgsm → Twilio** = SIP (IP whitelisting ile korunur).
2. **Twilio → backend** = HTTPS webhook (`X-Twilio-Signature` ile korunur — SIP
   değişikliği bu imzayı **etkilemez**, `CLINICAL_WEBHOOK_SIGNATURE_REQUIRED=true`
   olarak kalabilir).

---

## Önkoşullar

- [ ] Netgsm hesabı (SMS için zaten var) + **Ses Hizmeti / SIP Trunk** aktif + bir
      **coğrafi (+90) numara** kiralanmış.
- [ ] Twilio hesabı — **ödemeli** (upgrade edilmiş) öneririz; deneme hesabında SIP
      Domain kısıtlı olabilir.
- [ ] Backend **public HTTPS**'te erişilebilir:
      - Test: `ngrok http 8000` → `https://xxxx.ngrok-free.app`
      - Prod: gerçek domain + TLS.
- [ ] `.env` ayarları:
  ```
  TWILIO_ACCOUNT_SID=ACxxxx
  TWILIO_AUTH_TOKEN=xxxx
  CLINICAL_WEBHOOK_SIGNATURE_REQUIRED=true
  CLINICAL_WEBHOOK_BASE_URL=https://<gerçek-domain>     # imza bu URL'e göre doğrulanır
  CLINICAL_CHANNEL_BINDING_STRICT=true                  # gerçek pilotta önerilir
  SMS_PROVIDER=netgsm                                    # onay SMS'i için
  ```

> ⚠️ **IP ve edge adreslerini UYDURMA.** Netgsm'in SIP sinyal IP blokları ve
> Twilio'nun SIP edge IP'leri bu dokümanda **bilerek yok** — güncel değerleri
> Netgsm destekten ve Twilio dokümanından al (aşağıda linkli). Yanlış IP =
> sessizce düşen çağrı.

---

## Adım 1 — Twilio: SIP Domain oluştur

1. **Twilio Console → Voice → Manage → SIP Domains → Create new SIP Domain.**
2. **SIP URI** (benzersiz olmalı): `cognivault-klinik.sip.twilio.com`
3. **Voice Configuration → "A CALL COMES IN":**
   - **CONFIGURE WITH:** Webhook / TwiML
   - **URL:** `https://<domain>/api/webhooks/voice/incoming`
   - **HTTP:** `POST`
4. (Opsiyonel) **Call Status Changes:** `https://<domain>/api/webhooks/voice/status` (POST).
5. **Voice Authentication (ZORUNLU — en az biri):**
   - **IP Access Control List (ACL):** Yeni ACL oluştur, içine **Netgsm'in SIP
     sinyal IP'lerini** ekle. Twilio, INVITE'ın kaynağı bu listede değilse paketi
     **düşürür**. (Netgsm IP bloklarını destekten iste.)
   - _veya_ **Credential List:** Netgsm çağrıyı SIP kullanıcı adı/şifre ile
     gönderebiliyorsa alternatif kimlik doğrulama. Genelde operatör tarafında
     IP-tabanlı daha kolay.
6. **Secure Media / SIP:** Netgsm çoğunlukla **UDP + RTP (şifresiz), G.711 alaw
   (PCMA)** kullanır → Twilio SIP Domain'de **Secure Media'yı KAPAT**. (Netgsm
   TLS/SRTP destekliyorsa aç — güvenliği artırır ama karşı taraf desteklemeli.)
7. **Save.**

---

## Adım 2 — Netgsm: SIP Trunk yönlendirmesi

1. **Netgsm Web Portal → Ses Hizmeti > Ayarlar > SIP Bilgileri** → SIP Trunk'ı aktif et.
2. **Hedef (çağrının yönlendirileceği yer):**
   - **Domain:** `cognivault-klinik.sip.twilio.com`  ← IP yerine **domain** kullan
     (Twilio edge IP'leri değişebilir; domain daha dayanıklı).
   - **Port:** `5060`
3. **Prefix ayarları (KRİTİK — kodun numarayı doğru eşlemesi buna bağlı):**
   - **Alıcı (Recipient) prefix `+90`** → aranan numara Twilio'ya **E.164** olarak
     gider (`+90312XXXXXXX`). Kod `To` alanını `resolve_webhook_clinic` ile
     `ClinicChannelBinding`'e eşliyor; E.164 olmazsa "hizmet dışı" anonsu döner.
   - **Arayan (Caller) prefix `+90`** → `From` E.164 gelir → hasta onay SMS'i doğru
     numaraya gider.
4. **Coğrafi numarayı bu trunk'a bağla:** gelen çağrı +90 numaraya düşünce SIP
   trunk'a yönlensin.
5. **Kaydet:** "SIP Trunk Ayarlarını Kaydet" + "Prefix Ayarlarını Kaydet".

---

## Adım 3 — İki yönlü IP güvenliği kilidi

- **Netgsm → Twilio:** Netgsm'in çıkış SIP IP'leri **Twilio ACL'inde** olmalı
  (Adım 1.5). Eksikse Twilio INVITE'ı sessizce düşürür → çağrı bağlanmaz.
- **Twilio → Netgsm (karşı yön whitelisting):** Netgsm hedef tarafında IP kısıtı
  istiyorsa, **Twilio SIP edge IP aralıklarını** Netgsm'e ver. Güncel liste:
  Twilio "SIP Domains / Interconnect — IP addresses" dokümanı (aşağıda linkli).

---

## Adım 4 — Numarayı kliniğe bağla (uygulama tarafı)

`CLINICAL_CHANNEL_BINDING_STRICT=true` iken numara mutlaka bir kliniğe bağlı
olmalı; yoksa `receive_voice_speech` "Bu numara şu anda hizmet dışıdır" der.

Bir `ClinicChannelBinding` kaydı oluştur (channel=`PHONE`, address=`+90312XXXXXXX`,
`is_active=True`). Küçük bir provizyon script'i ile yapılabilir — bkz.
`backend/app/seed/data.py::_seed_channel_bindings` (demo için aynı deseni kullanıyor).

> Not: `resolve_webhook_clinic` adresi `normalize_phone` ile normalize edip eşliyor
> (`clinic_service.py:167`). Binding'e yazdığın adres ile Netgsm'in gönderdiği `To`
> formatı normalize sonrası **aynı** olmalı (boşluksuz E.164 önerilir).

---

## Adım 5 — Doğrulama / test çağrısı

1. **+90 numarayı ara.**
2. **Twilio Console → Monitor → Logs → Calls** (ve **SIP** sekmesi): INVITE geldi
   mi, `200 OK` döndü mü, TwiML `voice_url`'den çekildi mi?
3. **Backend log** (`/tmp/cognivault-backend.log`): `POST /api/webhooks/voice/incoming`
   isabet etti mi, `resolve_webhook_clinic` kliniği buldu mu?
4. Telefonda beklenen akış: **Selin karşılama + KVKK anonsu** → şikâyetini söyle →
   **sesli slot teklifleri** → sözlü onay → **randevu kilit + SMS**.

### Sorun giderme

| Belirti | Muhtemel sebep | Çözüm |
|---|---|---|
| Çağrı hiç bağlanmıyor / `403`/`486` | Netgsm IP Twilio ACL'inde değil | Adım 1.5 — Netgsm SIP IP'lerini ACL'e ekle |
| Bağlanıyor ama ses yok / tek yön | RTP/media portu, NAT, codec (alaw) uyumsuz | Secure Media kapat; Netgsm ile codec (PCMA) teyidi |
| "Bu numara hizmet dışıdır" anonsu | `To` E.164 değil **veya** binding yok | Adım 2.3 recipient prefix `+90`; Adım 4 binding |
| Selin konuşuyor ama seni anlamıyor | Türkçe STT / gürültü | `<Gather language="tr-TR">` doğru; hat kalitesi |
| İmza hatası (`401 Invalid Twilio signature`) | `CLINICAL_WEBHOOK_BASE_URL` yanlış | Public HTTPS URL ile birebir eşleşmeli |
| Ses "alice" (robotik) | Native TTS kapalı/hata | `VOICE_PHONE_NATIVE_TTS_ENABLED=true`; TTS modeli var mı |

---

## Maliyet ve KVKK notu (karar için)

- **Çift faturalandırma:** Netgsm (numara kirası + gelen dakika) **+** Twilio (inbound
  SIP dakika + `<Gather>` konuşma tanıma ücreti). Pilot hacminde küçük, ama ölçekte
  Yol B'yi cazip kılan kalem budur.
- **KVKK:** Ses akışı **hâlâ Twilio ABD** STT'sinden geçer → sınır-ötesi işlemci.
  Çağrı başı KVKK anonsu bunu kapsar **ama nihai anons metninin avukat onayı** hâlâ
  açık madde (İP-5/6 hukuk paketi). "Local-first" tezini tam karşılamak için kalıcı
  hedef **Yol B**.
- **İmza güvenliği korunur:** SIP hop'u yalnız Netgsm→Twilio arasında; Twilio→backend
  HTTP hop'u değişmez ve `X-Twilio-Signature` ile imzalı kalır.

---

## Kaynaklar

- Twilio — [Inbound: Sending SIP to Twilio](https://www.twilio.com/docs/voice/api/sending-sip)
- Twilio — [Use SIP with Twilio Voice (SIP Interface)](https://www.twilio.com/docs/voice/api/sip-interface)
- Twilio — [SIP Domain Resource](https://www.twilio.com/docs/voice/sip/api/sip-domain-resource)
- Twilio — [SIP IP Access Control List Mapping](https://www.twilio.com/docs/voice/sip/api/sip-ipaccesscontrollistmapping-resource)
- Netgsm — [SIP Trunk yönlendirme hizmeti](https://bilgibankasi.netgsm.com.tr/sabit-telefon/sip-trunk-yoenlendirme-hizmeti)
- Netgsm — [Coğrafi (sabit) numara](https://www.netgsm.com.tr/sabit-telefon/cografi-numara)
