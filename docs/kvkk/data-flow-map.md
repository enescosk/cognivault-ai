# Veri Akış Haritası — CogniVault Clinical

Bu doküman, hasta verisinin sisteme girdiği andan silinene kadar her teknik bileşende **nereye gittiğini** gösterir. KVKK Madde 4 (genel ilkeler) ve Madde 9 (yurt dışı aktarım) analizi için temel kaynak budur.

## Kanal 1: WhatsApp

```
Hasta telefonu → Meta WhatsApp Cloud API (Meta sunucuları, ABD/AB)
              → POST /api/webhooks/whatsapp  [backend/app/api/routes/clinical.py:398]
              → parse_meta_payload() → IncomingClinicalMessage
              → clinical_service.handle_incoming()
                  ├─→ ClinicPatient tablosu (PostgreSQL, lokal)
                  ├─→ ClinicConversation tablosu
                  ├─→ ClinicMessage tablosu (RAW İÇERİK)
                  └─→ clinical_ai_service.triage()
                        └─→ ⚠️ OpenAI Chat Completions API (ABD)
                              [agent/orchestrator.py:1032]
              → AI cevap:
                  ├─ Güvenli ise → Meta WhatsApp API → hasta
                  └─ Riskli ise → ShadowReview tablosu → doktor inbox
```

**Yurt dışı temas noktaları:**
1. Meta WhatsApp Cloud API (mesaj iletimi — bu zaten Meta'nın altyapısı, kaçınılmaz)
2. **OpenAI Chat Completions** (kaldırılacak — Faz 1-2 hedefi)

## Kanal 2: Telefon (Sesli arama)

```
Hasta arar → Twilio Voice (veya benzer telco) (ABD)
          → POST /api/webhooks/voice/incoming  [clinical.py:333]
          → TwiML <Gather speech> ile ses Twilio'da → metne çevriliyor
          → POST /api/webhooks/voice/gather  [clinical.py:347]
          → IncomingClinicalMessage (transcript)
          → Aynı pipeline...

Frontend chat (sesli mod) → MediaRecorder webm blob
                          → POST /api/voice/transcribe  [voice.py:38]
                          → ⚠️ OpenAI Whisper-1 (ABD)
                          → metin
                          → POST /api/voice/synthesize  [voice.py:88]
                          → ⚠️ OpenAI TTS (ABD) → mp3 → hasta
```

**Yurt dışı temas noktaları:**
1. Twilio Voice (ses kaydı + STT) — değiştirilebilir (yerli VoIP + lokal Whisper)
2. **OpenAI Whisper-1** (kaldırılacak)
3. **OpenAI TTS** (kaldırılacak)

## Kanal 3: Web Chat Widget

```
Klinik web sitesi → POST /api/clinical/web-intake (planlı)
                → Aynı IncomingClinicalMessage pipeline
                → ⚠️ OpenAI LLM
```

## Kanal 4: Manuel Simülasyon (test)

`POST /api/clinical/simulate-whatsapp` ve `POST /api/clinical/simulate-voice-call` — geliştirici/demo amaçlı, prod'da kapalı olmalı.

---

## Veri kategorileri ve nerede saklanıyor

| Veri | Saklandığı tablo | Konum | Şifreleme | Kategori (KVKK) |
|---|---|---|---|---|
| Hasta adı-soyadı | `clinic_patients.full_name` | PostgreSQL lokal | App-level yok, FS-level yok | Genel kişisel |
| Telefon | `clinic_patients.phone` | PostgreSQL lokal | yok | Genel kişisel + İletişim |
| Şikayet metni / semptom | `clinic_messages.content` | PostgreSQL lokal | yok | **Özel nitelikli (sağlık)** |
| Ses kaydı (raw) | henüz kalıcı değil (Twilio'da) | Twilio (ABD) | Twilio default | **Özel nitelikli + biyometrik** |
| Transcript | `clinic_messages.content` | PostgreSQL lokal | yok | **Özel nitelikli (sağlık)** |
| AI cevap taslağı | `shadow_reviews.draft_reply` | PostgreSQL lokal | yok | İşlenmiş türev |
| Randevu detayı | `clinical_appointments` | PostgreSQL lokal | yok | Sağlık + Genel |
| Doktor inceleme notu | `shadow_reviews.final_reply` | PostgreSQL lokal | yok | Sağlık |
| OpenAI istek logu | OpenAI sunucuları (ABD) | ⚠️ ABD | OpenAI default | **Özel nitelikli sağlık yurt dışında** |
| Audit log | `audit_logs` | PostgreSQL lokal | yok | İşlem kaydı |

## Yurt dışı aktarım envanteri (kritik)

| Veri tipi | Alıcı | Ülke | Hukuki temel (mevcut) | Risk |
|---|---|---|---|---|
| Şikayet metni | OpenAI | ABD | YOK (kritik açık) | 🔴 Yüksek |
| Ses kaydı | OpenAI (Whisper) | ABD | YOK | 🔴 Yüksek |
| AI cevabı için context | OpenAI | ABD | YOK | 🔴 Yüksek |
| WhatsApp mesaj transit | Meta | ABD/AB | Hasta kanal seçimi | 🟡 Orta (kullanıcı kanal seçti) |
| Telefon ses transit | Twilio | ABD | Hasta arama seçimi | 🟡 Orta |

## Veri saklama süreleri (mevcut)

**Şu anda hiçbir retention/silme job yok.** Veriler süresiz saklanıyor. KVKK Madde 4(d) "ilgili olduğu amaç için gerekli olan süre" ilkesine aykırı.

Önerilen (avukat onayına tabi):
- Klinik konuşma: 90 gün (anonimleştirme), 1 yıl (silme)
- Randevu kaydı: yasal saklama yükümlülüğü kadar (Sağlık Bakanlığı — genelde 20 yıl)
- Ses kaydı: 30 gün (transcript varsa raw audio silinir)
- AI cevap taslağı: 30 gün
- Audit log: 2 yıl (KVKK 12. madde kanıt için)

## Hedef mimari (Faz 2 sonrası)

```
Tüm AI çağrıları → app/ai/factory.py
                → assert_provider_allowed("tr_local_first") gate
                → LocalProvider (vLLM + Qwen2.5 + faster-whisper + Coqui XTTS)
                → veri yurt dışına ÇIKMAZ

Twilio Voice → değiştirilecek: yerli VoIP veya Twilio TR region
Meta WhatsApp → alternatifi yok; ama mesaj **lokal**de işlenir, sadece transit'te Meta'da
```
