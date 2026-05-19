# Cognivault AI — Improvement Plan

`SYSTEM_AUDIT.md` icindeki bulgulari uygulanabilir fazlara ayirir. Her faz icin: hedef, dokunulan dosyalar, riskli noktalar ve geri donus stratejisi belirtildi. Mevcut bireysel + kurumsal akislari **kirmadan** ilerlenecek.

## Faz 0 — Hizli Guvenlik & Polish (BU PR)

Dusuk risk, yuksek deger, mevcut akislari etkilemez.

1. **JWT secret prod'da fail-fast** — `app/core/config.py` icinde validator: `ENVIRONMENT in {"production","staging"}` iken default secret reddedilir. Dev davranisi degismez.
2. **Request ID middleware** — Tum yanitlara `X-Request-ID` ekler; agent karar log'u ve audit trail icin temel.
3. **Agent registry skeleton** — `app/services/agents/registry.py`: tip-guvenli `AgentType` enumu (`appointment`, `support`, `form`, `routing`, `corporate_assistant`) ve `register/get/dispatch` API'si. Mevcut clinical/chat servisleri degismez, sadece register edilir.
4. **Frontend ErrorBoundary kullanimi** — Dashboard ana panellerini sarmalar; tek panel cokmesi tum uygulamayi cokertmez.
5. **Frontend Toast wiring** — Mevcut `Toast.tsx` component'i `App.tsx`'e bagli; Dashboard ve diger panellerdeki `error` state'i `showToast(..., "error")` ile kullaniciya bildirir.
6. **Frontend ProtectedRoute** — `requireRole` wrapper'i Dashboard icindeki rol-bazli render'i tek bir yere toplar (URL bazli route gecisi gerekmiyor; davranis ayni, kod tek noktada).
7. **Docs** — `SYSTEM_AUDIT.md`, `IMPROVEMENT_PLAN.md`, README setup adimlari.

## Faz 1 — Tenant izolasyonu (TAMAMLANDI ✅)

Veri modelinde nullable kolon eklendi; mevcut tek-organizasyon kurulumu icin geriye uyumlu.

1. ✅ `Organization` <-> `Clinic` iliskisi
   - Migration `a1b2c3d4e5f6`: `clinics.organization_id` (FK, nullable), `users.organization_id` (FK, nullable).
   - Seed: `_backfill_tenant_scopes()` mevcut default klinigi ve staff kullanicilari default organizasyona bagliyor.
2. ✅ JWT claim'inde `org_id`
   - `app/core/security.py`: `create_access_token(subject, organization_id=...)`; staff girisinde token'a `org_id` claim'i ekleniyor.
3. ⏳ Servis katmaninda zorunlu scope (Faz 1.5)
   - `enterprise_service`, `clinical_service` `list_*`/`get_*` fonksiyonlarina `organization_id` filtreleme — sonraki adim.
4. ✅ Audit log'a `clinic_id`, `organization_id`, `request_id` (nullable) eklenmesi + service kwargs.

## Faz 2 — Webhook & Idempotency Sertlestirme (TAMAMLANDI ✅)

1. ✅ **Twilio imza dogrulamasi**: `verify_twilio_signature()` `X-Twilio-Signature`'i HMAC-SHA1+base64 ile dogrulayip canonical URL+sorted-params ile karsilastirir.
2. ✅ **Meta `X-Hub-Signature-256` dogrulamasi**: HMAC SHA256 + `hmac.compare_digest()` zaman-sabit karsilastirma.
3. ✅ **`inbound_events` tablosu**: `(provider, external_id)` benzersiz; `ingest_clinical_message` tekrar gelen webhook'larda ayni `IngestionResult.message`'i `action="duplicate_ignored"` ile dondurur.
4. ⏳ **Outbound `delivery_outbox` tablosu**: Faz 2.5 — retry, dead-letter, audit (sonraki adim).

**Feature flag**: `clinical_webhook_signature_required` (default `False`) — dev/test gercek imza istemeden calisir; prod'da `True` yapilirsa imzasiz inbound 401 doner.

## Faz 1.5 — Service-Layer Organization Filtering (Siradaki)

Mevcut sorgularda `organization_id` filtresi henuz koklu degil. Eklenmesi gerekenler:

- `enterprise_service.list_enterprise_sessions/get/...` -> `current_user.organization_id` ile filtrele.
- `clinical_service.list_*` icin clinic'in `organization_id`'sini parametre olarak kabul et.
- `require_roles` dependency'sine isteğe bağlı `require_organization` mode ekle.
- `get_current_organization(user)` dependency'si sade bir yardimci olarak eklenebilir.

## Faz 3 — Ajan Mimari Genisletme

1. Registry'e gercek implementasyon ekle (Faz 0'da skeleton).
2. Her ajan tipi icin `decide()` -> `AgentDecision` (intent, confidence, action, requires_human, reason).
3. `AgentDecisionLog` tablosu: tum ajan kararlari audit'lenebilir.
4. Klinik akisi `clinical_ai_service` -> `AppointmentAgent` + `SupportAgent`'a refactor (mevcut testler korunur, sadece dispatch yolu uzar).
5. Mock/Demo akislari: gercek LLM key olmadiginda predictable yanitlar.

## Faz 4 — Frontend Olgunlasma

1. **React Router** entegrasyonu: `/customer/*`, `/operator/*`, `/admin/*` rotalari; her grup icin protected layout.
2. **i18n**: `react-i18next` + `tr.json`/`en.json` sozluk dosyalari; hardcoded TR stringler asamali olarak cikarilir.
3. **Mobile responsiveness**: `@media` breakpoint'leri + sidebar collapse.
4. **React Query** (TanStack Query) ile API state cache'i; manuel `loadDashboard` kaldirilir.
5. **Skeleton kullanimi**: tum panellerin loading durumu skeleton ile gosterilir.
6. **Toast / ErrorBoundary** sertlestirme: Faz 0'da eklenen altyapi tum panellerde kullanilir.

## Faz 5 — Gozlemleme & SLO

1. **Structured logging** (`structlog`): tum servisler JSON log.
2. **OpenTelemetry tracing** entegrasyonu.
3. **Health & readiness** endpoint'leri (`/healthz`, `/readyz`).
4. **Metrics (Prometheus)**: `/metrics` Prometheus scrape, per-tenant counters.
5. **SLO alerting**: latency, error rate, queue depth.

## Faz 6 — Billing & Plan

1. `Plan`, `Subscription`, `UsageRecord` tablolari.
2. Plan limitleri: aylik konusma sayisi, dakika basina ses suresi, ajan sayisi.
3. Stripe (veya benzeri) entegrasyonu icin webhook + audit log.

## Cikis Olcutleri (Production-ready)

- Tum tenant verisi `organization_id` scope'unda izole.
- Webhook'lar imza ile dogrulanir; idempotency aktif.
- Audit log her kritik aksiyon icin yazilir ve tenant scope'una sahiptir.
- Frontend rotalari role gore protected; ErrorBoundary + Toast tum panellerde aktif.
- Backend type-checked (mypy) ve frontend lint hatasiz.
- Asgari 80% test coverage kritik servis dosyalarinda.
