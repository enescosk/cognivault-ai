# Customer Intake Architecture

Bu dokuman, hastalarin/musterilerin sisteme nereden konusacagini ve bu taleplerin klinik operasyon akisine nasil islenecegini tanimlar.

## Hedef

CogniVault Medical icin ana hedef, hastanin kendi aliskanligini bozmadan sisteme ulasmasi ve her kanalin tek bir guvenli intake hattina dusmesidir. Kullanici WhatsApp'tan yazar, klinigi arar, web chat widget'i kullanir veya klinik formunu doldurur; backend bunlari tek bir `IncomingClinicalMessage` sozlesmesine normalize eder.

## Kanal Stratejisi

1. WhatsApp
   - Production icin iki yol var: Meta WhatsApp Cloud API veya Twilio WhatsApp.
   - Mevcut backend her iki payload tipine hazir: JSON Meta payload'i `parse_meta_payload`, form-urlencoded Twilio payload'i `parse_twilio_form` ile okunuyor.
   - Endpoint: `POST /api/webhooks/whatsapp`.
   - Mesajlar hasta, konusma, klinik kanal ve doktor inbox kayitlarina donusur.

2. Telefon
   - Klinik numarasi bir voice provider'a yonlenir.
   - Gelen cagri `POST /api/webhooks/voice/incoming` endpoint'ine duser.
   - Sistem TwiML `Gather` ile hastanin konusmasini alir, `POST /api/webhooks/voice/gather` uzerinden metne cevirilmis sonucu isler.
   - Endpoint, konusmayi `ClinicChannel.PHONE` olarak kaydeder ve gerekirse doktor onayina dusurur.

3. Web Chat Widget
   - Klinik sitesine kucuk bir chat widget'i eklenir.
   - Widget backend'e `POST /api/clinical/web-intake` gibi imzali, rate-limited bir endpoint ile gelir.
   - Bu kanal WhatsApp ve telefonla ayni `IncomingClinicalMessage` contract'ina iner.

4. Lead/Randevu Formu
   - Google Ads, landing page veya klinik sitesindeki formlar dogrudan intake service'e POST edilir.
   - Form alanlari serbest metinle birlikte saklanir; AI sadece niyet ve eksik bilgi tespiti yapar.

## Tek Intake Pipeline

Her kanalin izlemesi gereken yol:

1. Verify: provider imzasi, token, IP/rate limit ve payload boyutu kontrol edilir.
2. Normalize: provider payload'i `IncomingClinicalMessage` yapisina cevrilir.
3. Idempotency: `external_message_id` ve `external_thread_id` ile tekrar teslimatlar tekilleştirilir.
4. Resolve patient: telefon veya channel identity ile `ClinicPatient` bulunur ya da olusturulur.
5. Resolve conversation: aktif konusma bulunur ya da yeni `ClinicConversation` acilir.
6. Store raw event: ham payload audit/debug icin metadata olarak saklanir.
7. AI triage: dil, niyet, guven skoru, persona ve risk sebebi hesaplanir.
8. Safety gate: acil/tibbi riskli/guven dusuk mesajlar `ShadowReview` ve doktor inbox'a duser.
9. Action routing: randevu, fiyat, sigorta, doktor mesaji veya genel bilgi akisina yonlenir.
10. Delivery: otomatik cevap guvenliyse ayni kanaldan gonderilir; degilse insan onayi beklenir.

## Mevcut Kod Durumu

- `backend/app/api/routes/clinical.py`
  - WhatsApp simulate endpoint'i var.
  - Voice simulate endpoint'i var.
  - Meta webhook verify endpoint'i var.
  - WhatsApp webhook POST endpoint'i var.
  - Voice incoming/gather endpoint'leri var.

- `backend/app/services/clinical_service.py`
  - `IncomingClinicalMessage` kanal bagimsiz contract gorevini goruyor.
  - Hasta ve konusma cozumleme var.
  - AI cevap, shadow review, doktor inbox ve frustration log akisi var.

Bu temel dogru. Bir sonraki buyuk kalite sicramasi, provider dogrulama, idempotency tablosu, outbound delivery outbox'i ve golden scenario eval'lari ile bu hatti production seviyesine kilitlemek.

## Production Gereksinimleri

- WhatsApp webhook icin Meta `X-Hub-Signature-256` dogrulamasi.
- Twilio webhook icin request signature validation.
- `external_message_id` uzerinden unique index veya `inbound_events` tablosu.
- Outbound cevaplar icin retry edilebilir `delivery_outbox` tablosu.
- Klinik bazli kanal konfigrasyonu: provider, phone number id, token ref, aktif/pasif durum.
- Audio icin max duration, MIME/type allowlist, transcript confidence ve noisy-call senaryolari.
- Medikal guvenlik icin acil durum/escalation politikasi.
- CI'da golden conversation regression: yazim hatasi, ofkeli hasta, eksik bilgi, acil belirti, provider retry, duplicate webhook.

## Kaynaklar

- Meta WhatsApp Cloud API collection: https://www.postman.com/meta/whatsapp-business-platform/documentation/wlk6lh4/whatsapp-cloud-api
- Twilio Voice webhooks: https://www.twilio.com/docs/usage/webhooks/voice-webhooks
- Twilio incoming messaging webhooks: https://www.twilio.com/docs/messaging/guides/webhook-request
- Twilio WhatsApp API overview: https://www.twilio.com/docs/whatsapp/api
