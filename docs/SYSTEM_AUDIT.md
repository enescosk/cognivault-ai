# Cognivault AI — System Audit

Bu dokuman backend, frontend, data model, guvenlik, ajan mimarisi ve dokumantasyon katmanlarinin enterprise B2B SaaS hazirligi acisindan kapsamli denetimini ozetler. Mevcut surum: `main @ d4b3207` + bu daldaki iyilestirmeler.

## 1. Stack ve Kapsam

- **Backend**: FastAPI + SQLAlchemy 2.x + Alembic + Pydantic v2; SQLite (dev) / Postgres (prod) hedefli. Servis katmani (`app/services`), route katmani (`app/api/routes`), model (`app/models/entities.py`), schema (`app/schemas`) net ayrilmis.
- **Frontend**: Vite + React 18 + TypeScript + vanilla CSS (Tailwind kismi olarak ui altinda). Route yok, `App.tsx` icinde rol bazli toggle ile Dashboard secimi yapiliyor.
- **AI**: OpenAI ve Anthropic icin paralel istemci sarmalayicilari (`clinical_ai_service`, `chat_service`, `external_intent_service`, `intelligence_service`). Persona katmani sadece klinik tarafta.
- **Operasyonel**: Tek alembic migration (`ff0507ce5844_initial`), rate limit middleware (global 200/min), CORS env'den okunuyor, security headers middleware var.

## 2. Mevcut Yetenekler

| Alan | Durum |
| --- | --- |
| Kayit / giris (JWT) | Mevcut |
| Rol bazli erisim (`customer`, `operator`, `admin`) | Mevcut |
| Bireysel randevu akisi | Mevcut |
| Klinik mesajlasma (WhatsApp/Voice/Form sim) | Mevcut |
| Shadow review (insan onayli AI cevabi) | Mevcut |
| Doktor inbox + frustration log | Mevcut |
| Enterprise oturumlari, ticket, organizasyon, agent | Mevcut (ayrik modul) |
| Intelligence (lead toplama, taslak cevap, onay) | Mevcut |
| Audit log (her endpoint icin degil) | Kismi |
| **Multi-tenant izolasyon (clinic <-> organization)** | **YOK** |
| **Webhook imza dogrulamasi** | **YOK** |
| **Tenant scoped audit log** | **YOK** |
| **Frontend route guard / role enforcement** | **YOK** |
| Frontend i18n altyapisi | YOK |
| Mobil duyarli layout | YOK |

## 3. Bulgular — Backend

### 3.1 Multi-tenancy: KISMI

- `Clinic` ve `Organization` birbirinden bagimsiz iki ust seviye tenant olarak yasiyor. Tek bir kurumsal musteri (ornegin bir hastane zinciri) hem `Organization` hem birden cok `Clinic` sahibi olamiyor.
- `User` tablosunda `organization_id` veya `clinic_id` yok; bir kullanicinin hangi kuruma ait oldugu sadece dolayli olarak `ClinicMembership` ve `EnterpriseAgent` join tablolari uzerinden cikarilabiliyor.
- Enterprise route'larinda `ensure_enterprise_access()` sadece role kontrolu yapiyor, organization scope kontrolu yapmiyor. Aym instance'a birden fazla organizasyon eklenirse cross-tenant veri sizinti riski var.
- Klinik webhook'lari (`/api/webhooks/whatsapp`, `/api/webhooks/voice/*`) auth-siz calismak zorunda; ancak imza / shared secret dogrulamasi yapilmadigi icin instance disindan herhangi biri default clinic'e ham mesaj enjekte edebilir.

### 3.2 Guvenlik

- **JWT secret prod'da kontrolsuz default**: `app/core/config.py:17` "change-me-in-production"; main.py warning logluyor ama startup'i durdurmuyor.
- **Sifre hash'leme**: `app/core/security.py` SHA256 + tuz. Kabul edilebilir ama bcrypt/argon2 standart degil; mevcut kullanicilari kirmadan migrate edilmesi sonraki faza birakilmali.
- **Webhook imza dogrulamasi**: Meta `X-Hub-Signature-256` ve Twilio signature dogrulamasi yok; sadece verify_token kontrolu (`receive_whatsapp_webhook`).
- **Rate limit**: Global 200/req-min ve `/api/chat/messages` icin 30/req-min mevcut; clinic/organization seviyesinde bucket yok.
- **Audit log kapsami**: appointment, intelligence onayi, shadow review kararlari icin var; login/logout, role degisikligi, webhook ingestion ve clinic settings degisikligi icin yok.
- **Webhook idempotency**: `external_message_id` benzersizlik kontrolu yok; ayni Twilio mesaji ikinci kez postalanirsa duplicate kayit olusur.

### 3.3 AI Agent Mimarisi

- Tek ortak `Agent` soyutlamasi yok. Klinik tarafi `clinical_ai_service` icinde dogrudan LLM cagrisi yapiyor; persona katmani sadece bu alana ozel.
- Chat tarafi (`chat_service`) gerekirse Anthropic streaming yapiyor ama "agent tipi" kavrami yok.
- Karar gerekceleri (intent, confidence, risk) `ClinicMessage.metadata_json` ve `ShadowReview.metadata_json` icine yaziliyor ama insan tarafi icin tutarli bir "agent karar log'u" yok.

### 3.4 API Tutarliligi

- Cogu route REST'e yakin ama bazi yerlerde tekil/cogul karisik (`/clinical/conversations/{id}` vs `/clinical/doctor-inbox` vs `/clinical/shadow-reviews`). Yeni eklenen `/clinical/pre-intakes` cogul kuralini takip ediyor.
- Pagination yok; `list_*` endpoint'leri `limit` query parametresiyle sinirlandiriliyor.
- Hata gosterimi `HTTPException` ile tutarli ama hata kodu kataloglanmamis.

### 3.5 Test Kapsami

- 66 backend pytest (PreIntake testleri dahil). Auth, RBAC, appointment, clinical, intelligence, security headers, rate limit kapsiyor.
- Eksikler: webhook auth/imza, multi-tenant izolasyon, IDOR senaryolari, frontend smoke testleri.

## 4. Bulgular — Frontend

### 4.1 Mimari

- Tek `App.tsx` -> `AuthProvider` -> `Dashboard` zinciri; React Router yok. Rol bazli gorunum `view` state'i ile yonetiliyor.
- API katmani `src/api/client.ts` icinde tek dosyada toplanmis; token'i context'ten cekiyor.
- Stil: `styles/global.css` 118KB; SaaS goruntusu profesyonel (Syne+DM Sans, koyu tema, tutarli boslama). Ancak Tailwind sinifi yer yer kosulsuz kullanilmis (ErrorBoundary, ui/EmptyState) — global CSS palette ile celisiyor.
- Loading/error: `loading-shell` ve `error-box` divleri yer yer kullanilmis; `Toast.tsx` component mevcut ama hicbir yerden cagrilmiyor. `ErrorBoundary` mevcut ama hicbir panele sarilmamis.

### 4.2 Bireysel vs Kurumsal Ayrim

- Sidebar role gore farkli ozet gosteriyor ama URL bazli ayrim yok; admin/operator URL'i degistirip customer komponentlerini de getirebilir (gercek bir IDOR olmasa da kullanici beklentilerine aykiri).
- Customer dashboardu `AppointmentPanel` + chat odakli; kurumsal kullanici `ClinicalPanel` + `AdminPanel` goruyor. Mevcut deneyim "PARTIAL" — temel bolunme var, sayfa duzeyinde izolasyon yok.

### 4.3 Polish Eksikleri

- ErrorBoundary kullanilmiyor — tek panel cokmesi tum uygulamayi cokertiyor.
- Empty state'ler bazen sade ama bazen bos div birakiliyor (Sohbetler bos durumu, AppointmentsPage bos liste).
- Loading skeleton'i (`ui/Skeleton.tsx`) tanimli ama kullanilmiyor.

## 5. Multi-tenancy Sonucu

Sistem tek-organizasyon veya tek-klinik pilot dagitimi icin uygun. Asagidaki adimlar gerekli olmadan **gercek B2B SaaS** olarak satisa cikmamali:

1. `Clinic.organization_id` (nullable) ekle, mevcut clinic'leri default organizasyona migrate et.
2. `User.organization_id` (nullable) ekle, login token'ina `org_id` claim'i koy.
3. Tum enterprise/clinical sorgu fonksiyonlarinda `organization_id` filtresi zorunlu hale gel.
4. Webhook'larda tenant secimi route param'dan veya provider numarasindan turetilsin.
5. Audit log'a `clinic_id`/`organization_id` kolonlari eklensin.

## 6. Sonuc

Cognivault temel altyapi, persona katmani ve klinik akisinda guclu. Enterprise SaaS dengesi icin ana eksik: **tenant izolasyonunun veri ve route katmaninda zorunlu hale gelmesi**, **webhook imza dogrulamasi**, **frontend route guard + error boundary**, ve **ajan tiplerinin tek bir kayit defteri altinda toplanmasi**. Bu kalemler `IMPROVEMENT_PLAN.md` icinde fazlara dagitildi.
