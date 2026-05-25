# CogniVault Clinical — Patient & Clinic Experience Design

> **Statü:** Ürün tasarım dokümanı (henüz onaylanmadı)
> **Tarih:** 2026-05-25
> **Kapsam:** Hasta-yüzlü chat sayfası, klinik admin paneli, mevcut operatör panelin sadeleşmesi
> **Bağlam:** Bu doküman [Gemini Deep Research araştırmasının](../research/gemini-deep-research-2026-05-25.md) ürün ucudur; oradaki Bölüm A1-A8 akışları burada UI/UX'e çevriliyor.

---

## 1. Ürün vizyonu — tek cümle

CogniVault Clinical, bir klinik için **kendi markasını taşıyan public bir hasta sayfası** sunar; hasta o sayfaya hiçbir giriş yapmadan girer, KVKK onayı verir ve klinik-spesifik bir AI asistanıyla canlı sohbet ederek randevusunu alır. Klinik tarafında **3 farklı yetki seviyesi** ile aynı sohbet uçtan uca yönetilir, denetlenir ve ölçülür.

## 2. Roller ve deneyimler

Üç rol, üç farklı sayfa setı:

| Rol | URL deseni | Auth | Birinci amacı |
|---|---|---|---|
| **Hasta** | `/c/<klinik-slug>` (public) | Yok (anonim → KVKK consent) | Randevu almak veya soru sormak |
| **Klinik Personeli** (operatör/sekreter) | `/operator/*` | Login (operator/admin role) | Doktor inbox + shadow review + sohbet detayı |
| **Klinik Admini** (owner) | `/clinic/admin/*` | Login (admin role + clinic owner membership) | Klinik kimliği, hekim/branş, persona ve slot yönetimi |

Mevcut durumda `/operator/*` var ama klinik admini için **ayrı bir alan yok** — admin role'ü `/operator`'ı görüyor. Bu doküman **klinik admin için ayrı bir mental space** öneriyor.

## 3. Hasta deneyimi (asıl yenilik)

### 3.1 5 adımlı akış

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  1. LANDING │ →  │  2. CONSENT │ →  │ 3. ONBOARD  │ →  │   4. CHAT   │ →  │  5. CONFIRM │
│             │    │             │    │             │    │             │    │             │
│  Klinik     │    │  KVKK       │    │  Ad +       │    │  Canlı AI   │    │  Randevu    │
│  branding'i │    │  aydınlatma │    │  Telefon    │    │  sohbeti    │    │  + SMS      │
│  + CTA      │    │  + buton    │    │  (minimal)  │    │  + slot     │    │  onayı      │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

### 3.2 Adım detayları

#### 1. Landing (`GET /c/<slug>`)

Anonim. Kliniğin "vitrini":

- Klinik adı, logo, kısa açıklama
- Hekim kartları (foto, isim, uzmanlık)
- Hizmet/branş şeritleri (Endodonti, Estetik, Ortodonti...)
- Tek bir büyük CTA: **"Randevu almak için AI ile sohbet et"**
- Alt bantta: çalışma saatleri, adres, telefon (fallback için)
- Footer: KVKK aydınlatma metnine link, ana site link

UX notu: hasta direkt arama/WhatsApp yerine bu sayfaya yönlendirildiğinde "ne yapacağımı biliyorum" hissini almalı. Aksi halde telefonu kapatma reflexi (Bölüm C: %43 drop @15s) bu sayfada da geçerlidir — landing **6 saniyede taranabilmeli**.

#### 2. Consent (modal, sayfa içi)

CTA'ya tıklayınca **bloklayıcı modal**:

- Aydınlatma metni başlık + 3-4 madde özet (yurt dışı aktarım, saklama süresi, hakları)
- Detay link: "Tam metni oku" → ayrı sayfa/sekme
- 2 buton: **"Kabul ediyorum, devam et"** · **"Vazgeç"**
- Hasta "Vazgeç" derse → landing'e dön (Bölüm C: KVKK m.6/2 — hizmetten men etme yasağı, alternatif iletişim kanalı (telefon) gösterilir)
- Hasta kabul ederse → backend'e `POST /api/public/clinics/<slug>/consent` çağırılır, `consent_token` döner (15 dakika geçerli, sessionStorage'da tutulur)

KVKK ispat altyapısı:
- `consent_token` → veritabanında `PatientConsent` kaydı (versiyon, IP, user agent, timestamp)
- Aydınlatma metninin SHA256 hash'i kaydedilir
- Metin güncellenirse yeni versiyon ihtiyacı

#### 3. Onboarding (minimal form)

Sadece **ad-soyad + telefon**. Başka hiçbir şey sorulmaz (KVKK §9 minimization).

- Telefon format: TR cep `+90 5XX XXX XX XX`
- Telefon zaten klinikte kayıtlıysa: "Tekrar hoş geldiniz, [Ad]" → otomatik gider chat'e
- Yeni hastaysa: ad-soyad alınır
- Submit → backend `POST .../conversations` çağırır → conversation_id + initial_token döner
- "AI sohbeti başlatılıyor..." spinner

#### 4. Chat (asıl deneyim)

Sayfa düzeni:
- Üstte hasta adı + klinik adı + dur/yardım butonu
- Orta alan: mesaj balonları (mevcut ChatWindow stilinden esinlenen)
- Alt: mesaj kutusu + "ses kaydı" (Faz 1.5 — lokal Whisper geldiğinde) + gönder
- Sağ alt (mobilde gizli): klinik bilgisi mini kart

AI davranışı:
- İlk mesaj klinikten gelir: persona seçimi (default "Selin" - randevu) + Türkçe karşılama
- Hasta yazar → backend `clinical_service.ingest_clinical_message` → AI cevap
- **Streaming** (SSE) — kullanıcı tipik "AI düşünüyor" loading'i değil, token-by-token cevap görür (Gemini Bölüm F#3 — <1.5s p50)
- Multi-intent (Bölüm A8): "Randevu alayım, fiyat ne kadar?" → AI iki ayrı paragrafta cevaplar
- Slot önerisi gelirse: chip-style buton **"📅 Salı 14:30"** **"📅 Perşembe 10:00"** (özel UI komponenti)
- Acil semptom (Bölüm A6): AI hemen "112'yi arayın" + üst alanda kırmızı banner + klinik personeline alarm
- Düşük güven cevabı (eşik altı): AI cevap göndermez, hasta "klinik personeli size yazacak" mesajı görür → backend tarafı `shadow_review` zaten yapıyor

#### 5. Confirm

Hasta slot'u seçince:
- AI "Onaylıyor musunuz?" der
- Hasta "Evet" der
- Backend `create_pending_appointment` → `confirm_appointment_hbys` (mock şimdilik)
- Hasta için onay ekranı: ✅ Randevu detayları + "SMS gönderildi" + iCal indirme butonu (opsiyonel)
- Hasta "sohbeti kapat" der → conversation `closed` olur
- 24 saat içinde tekrar girerse: aynı telefon → "Devam mı, yeni başlangıç mı?"

### 3.3 Bölüm A senaryolarının patient page'de karşılığı

Gemini Bölüm A'daki 8 senaryo bu sayfada şöyle ele alınır:

| Senaryo | Patient page'de davranış |
|---|---|
| A1 Yeni hasta randevu (telefon) | Bu sayfada karşılığı: chat üzerinden randevu. Telefon kanalı paralel akış |
| A2 Mevcut hasta erteleme | Hasta telefonu girince sistem aktif randevuyu bulur, chat'te "erteleyelim mi?" diye sorar |
| A3 İptal | Aynı şekilde aktif randevu tespiti |
| A4 Fiyat sorgusu | AI yasal yanıtı verir + ücretsiz muayene CTA → slot seçim |
| A5 Sigorta sorgusu | Insurance matrisi sorgu → cevap + ön muayene CTA |
| A6 Acil semptom | Kırmızı banner + 112 hatırlatması + chat kilitlenir, operatöre düşer |
| A7 Öfkeli hasta | UI'da otomatik müdahale yok — backend zaten shadow_review yapıyor, hasta "operatöre aktarıldınız" görür |
| A8 Multi-intent | Cevap bloklarla gelir (1, 2, 3 madde) |

## 4. Klinik Admini Paneli (yeni mental space)

### 4.1 Niçin ayrı bir alan?

Mevcut `/operator/*` paneli **günlük operasyon** içindir: inbox, shadow review, conversation list. Klinik admini ise **konfigürasyon ve kimlik** ile uğraşır. İki bakış birbirine karışınca admin "doğru ayarı nerede yapacağım" sorusunu yaşıyor.

### 4.2 Yapılandırma alanları

URL: `/clinic/admin/*`. Sol nav menüsü:

- **Kimlik** (`/identity`) — ad, logo, kısa açıklama, branding renkleri (primary/accent), slug
- **Hekimler** (`/doctors`) — liste, foto, uzmanlık, çalışma saatleri
- **Hizmetler/Branşlar** (`/services`) — liste, hangi hekime atanmış, kısa açıklama
- **Persona** (`/persona`) — hangi varsayılan persona aktif (Selin/Arzu/Can), opsiyonel custom prompt
- **Slot/Takvim** (`/slots`) — hekim başına müsait saatler, blackout dates
- **Aydınlatma metni** (`/disclosure`) — versiyonlanmış KVKK metni editörü, hangi versiyon aktif
- **Public URL preview** (`/preview`) — hastanın gördüğü sayfayı klinik admin'e iframe içinde gösterir, "şimdi açıkken halini gör" deneyimi
- **Public URL paylaş** (`/share`) — QR kod, kısa link, WhatsApp/SMS paylaşım

### 4.3 Klinik Admini ↔ Operatör ilişkisi

Aynı kullanıcı her ikisini de görebilir (admin role → her iki nav set'i). Operatör role → sadece `/operator/*`. Bu role-based nav switching gerektirir.

## 5. Mimari kararlar

### 5.1 Tek React app, çoklu route

Hem patient hem operator hem admin **aynı Vite bundle**'ında. Sebep:
- Mevcut React Query + ErrorBoundary + i18n altyapısı paylaşılır
- Deploy basitliği
- Patient sayfaları için ekstra `lazy()` import kullanılır, JS bundle parçalanır

Alternatif (reddedildi): ayrı patient-app/. Multi-tenant subdomain stratejisi geleceğe.

### 5.2 Public vs Authenticated API ayrımı

```
backend/app/api/routes/
  public.py    # ← YENİ. Hiçbir Authorization header gerektirmez.
  clinical.py  # Mevcut. Operator/admin login zorunlu.
  clinic_admin.py # ← YENİ. Admin role + clinic owner zorunlu.
```

Public endpoint'ler:
- `GET /api/public/clinics/<slug>` → klinik kimliği (logo, ad, hekimler, hizmetler, KVKK metin hash)
- `POST /api/public/clinics/<slug>/consent` → `{name, phone, disclosure_version_hash}` → `consent_token` (JWT-like, 15 dk)
- `POST /api/public/clinics/<slug>/conversations` → `consent_token` → `{conversation_id, session_token}`
- `POST /api/public/clinics/<slug>/conversations/<id>/messages` → `session_token` ile mesaj gönderme
- `GET /api/public/clinics/<slug>/conversations/<id>/stream` → SSE stream (AI cevabı)
- `POST /api/public/clinics/<slug>/conversations/<id>/appointments` → slot onayı

Rate limit: IP bazlı sıkı (saatlik 30 mesaj/IP).

### 5.3 Anonim hasta consent flow

1. Hasta CTA'ya tıklar → modal aydınlatma metni gösterir, hash gönderilir frontend'e
2. Hasta "Kabul" → frontend `POST /consent` çağırır, body: `{name, phone, disclosure_version_hash, locale, ip_user_agent}`
3. Backend doğrular (hash güncel mi), `PatientConsent` kaydeder, `consent_token` döner (JWT, 15dk, signed)
4. Frontend `sessionStorage`'a koyar
5. Sonraki tüm patient endpoint çağrılarında `Authorization: Bearer <consent_token>` header
6. Backend her çağrıda token'ı parse edip `clinic_id` + `patient_id` + `consent_version`'ı çeker

Patient login değil — sadece "yetkilendirilmiş anonim".

### 5.4 Slot picker UI bileşeni

Mevcut `clinical_slot_service.py` zaten slot decision üretiyor. Chat içinde slot ID + saat ile chip'ler render edilecek. Hasta tıklayınca yeni mesaj otomatik gönderilir ("Salı 14:30 olsun").

Custom React component: `<SlotPickerInChat />` — backend AI cevabının `slot_offers: [{id, label}]` metadata'sından besler.

## 6. Veritabanı değişiklikleri

Çoğu zaten var. Eklenenler:

### Yeni tablolar (Faz P1)

```python
class ClinicBranding(Base):
    # Mevcut Clinic.settings_json'a entegre edilebilir; ayrı tablo daha temiz
    __tablename__ = "clinic_brandings"
    clinic_id: int (FK clinics.id, unique)
    logo_url: str | None
    primary_color: str  # hex
    accent_color: str
    hero_headline: str  # "AI ile randevu al"
    hero_subheadline: str
    contact_phone: str | None  # consent reddinde gösterilen
    public_address: str | None
    updated_at: datetime

class KVKKDisclosureVersion(Base):
    __tablename__ = "kvkk_disclosures"
    id: int
    clinic_id: int (FK)
    version: str  # "v1", "v2"
    body_text: text
    body_hash: str (SHA256)
    is_active: bool
    created_at: datetime

class PatientConsent(Base):
    __tablename__ = "patient_consents"
    id: int
    clinic_id: int (FK)
    patient_id: int (FK clinic_patients.id)
    conversation_id: int | None (FK clinic_conversations.id, nullable)
    disclosure_version_id: int (FK kvkk_disclosures.id)
    granted_via: str  # "patient_page_button" | "ivr_dtmf" | "ivr_voice"
    granted_at: datetime
    ip_address: str
    user_agent: str
    consent_token_jti: str  # token id, ileride revoke için
```

### Yeni tablolar (Faz P2 — Klinik admin)

```python
class Doctor(Base):
    __tablename__ = "doctors"
    id: int
    clinic_id: int (FK)
    full_name: str
    specialty: str
    photo_url: str | None
    working_hours_json: dict  # gün:saat map
    is_active: bool

class ClinicService(Base):
    __tablename__ = "clinic_services"
    id: int
    clinic_id: int (FK)
    name: str
    description: str
    default_persona_id: str  # "selin" | "arzu" | "can"
    doctors: many-to-many → Doctor
    is_active: bool
```

Mevcut `AppointmentSlot` zaten var, doctor_id ile ilişkilendirilecek.

## 7. MVP scope ve faz planı

### Faz P0 — Spec onayı (BU DOKUMAN)

Bu doc'un onaylanması. Ön karar:
- ✅ Multi-tenant SaaS yön
- ✅ Anonim patient + consent gate
- ✅ Tek React bundle, çoklu route
- ✅ Yeni public.py + clinic_admin.py route'ları

### Faz P1 — Patient Page MVP (1-2 oturum, ~6-8 saat)

1. **Backend**:
   - `app/api/routes/public.py` yeni dosya
   - `ClinicBranding`, `KVKKDisclosureVersion`, `PatientConsent` migration
   - Seed data: bir test klinik için branding + KVKK metni
   - 5 yeni endpoint (yukarıda listelendi)
   - Rate limit middleware: public route için sıkı
2. **Frontend**:
   - `frontend/src/components/patient/` yeni klasör
     - `PatientLanding.tsx` (klinik vitrini)
     - `PatientConsentModal.tsx`
     - `PatientOnboardingForm.tsx`
     - `PatientChatRoom.tsx` (Chat + slot picker)
     - `PatientConfirmation.tsx`
   - `App.tsx`'e `<Route path="/c/:slug" ...>` ekle (RequireRole değil, public)
   - `frontend/src/api/patientClient.ts` (consent_token aware fetch)
   - i18n: ~20 yeni key (TR/EN)
3. **Smoke test**: Operatör panelinden simulate kullanmadan, gerçek hasta sayfasından mesaj at, backend `clinical_service.ingest_clinical_message`'a düşsün

### Faz P2 — Klinik Admin Paneli MVP (1 oturum, ~4-6 saat)

1. **Backend**:
   - `app/api/routes/clinic_admin.py`
   - `Doctor`, `ClinicService` migration
   - Endpoint'ler: branding CRUD, doctors CRUD, services CRUD, persona/slot config
2. **Frontend**:
   - `frontend/src/components/admin/` (klinik admin)
   - Route: `/clinic/admin/*` (admin role + clinic owner guard)
   - 7 sayfa: Identity, Doctors, Services, Persona, Slots, Disclosure, Preview/Share

### Faz P3 — UX polishing

- Patient page'de:
  - Mobil duyarlılık
  - Streaming chat
  - Slot picker chip'leri
  - Acil banner
  - Hata durumları (network kopması, consent süresi dolması)
- Klinik admin'de:
  - Logo upload
  - Renk seçici
  - Live preview iframe

### Faz P4 — Multi-tenant onboarding

- Yeni klinik kayıt formu (`/clinic/signup`)
- Trial dönem mantığı (Phase 8-12'den `billing_service` var)
- Subdomain stratejisi (DNS wildcard, opsiyonel)

## 8. Açık sorular (karar için)

### S1. Hasta sayfası tek bir klinik için mi yoksa multi-tenant'tan mı başlasın?

- **Önerilen:** Multi-tenant'tan başla. Backend `<slug>` ile çalışsın. İlk anda sadece 1 klinik seed'lensin (default `demo`). Frontend `/c/<slug>` desteklesin. Mimari ileride DNS subdomain'e dönüşür.

### S2. Klinik admin login akışı mevcut `/login` ile aynı mı?

- **Önerilen:** Evet, aynı. `admin` role + `ClinicMembership` kontrolü ile `/clinic/admin/*` görünür. Yeni bir login deneyimi gerek yok.

### S3. Patient consent token süresi?

- **Önerilen:** 15 dakika. Süresi dolarsa hasta tekrar consent verir (UX'te uyarı).

### S4. SMS/E-posta bildirim entegrasyonu?

- **Önerilen:** Faz P1'de **mock** (loga yazar). Faz P3'te gerçek Twilio/Netgsm entegre. KVKK'ya uygun TR SMS sağlayıcı tercih.

### S5. Hekim/branş yönetimi olmadan patient page çalışır mı?

- **Cevap:** Evet. Faz P1'de `clinical_slot_service` zaten generic slot üretiyor. Hekim listesi vitrinde "Demo Hekim" placeholder olarak gösterilir. Faz P2'de gerçek model devreye girer.

### S6. Patient page'in URL formatı?

- **Önerilen:** `https://app.cognivault.com/c/<slug>` — pratik, hızlı deploy edilebilir.
- **Alternatif (gelecek):** `https://<slug>.cognivault.com` — branding'i güçlendirir, DNS gerekir.

### S7. Anonim mesaj gönderme limiti?

- **Önerilen:** IP başına saatlik 30 mesaj. Session token başına 5dk içinde 20 mesaj. Aşılırsa "şu an sistem yoğun" mesajı + operatöre düşme.

## 9. Başarı kriterleri (Faz P1 sonunda)

- [ ] Tarayıcıya `/c/demo` girdiğimde klinik branding görüyorum
- [ ] "Randevu al" → consent modal → kabul → ad/telefon → chat ekranı, kesintisiz
- [ ] "Yarın için randevu istiyorum" yazıyorum → AI cevap veriyor + slot chip'leri görüyorum
- [ ] Chip'e tıklıyorum → onay mesajı + "randevu oluştu" ekranı
- [ ] Operatör panelinde aynı konuşma `clinic_conversations`'ta görünüyor (mevcut `simulate-whatsapp`'tan farklı olarak `channel=web_chat` ile)
- [ ] DB'de `patient_consents` kaydı var, IP + version + timestamp dolu
- [ ] Mobil ekranda (375px) tüm akış kullanılabilir
- [ ] Lighthouse mobile performans skoru >85

## 10. Görsel referanslar (önerilen)

UX dilini benzettiğim ürünler:

| Ürün | Hangi yönü | Not |
|---|---|---|
| **Doctolib** | Hasta arama + branding | Klinik kartlarının nasıl gösterildiği |
| **Klara** | Inbox + güvenli mesajlaşma | Hekim/sekreter conversation paneli |
| **Mediktor** | Triyaj akışı | Kademeli soru-cevap yapısı |
| **Linear** | Admin UI | Klinik admin paneli için temiz form deneyimi |
| **Intercom Messenger** | Chat widget | Patient chat'in görsel dili |

Bu doküman, gelecekteki bütün patient/clinic kararlarının referans noktasıdır. Her büyük UX değişikliği bu doc'un güncellenmesiyle başlamalı.
