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

## Faz 1.5 — Service-Layer Organization Filtering (TAMAMLANDI ✅)

- ✅ `resolve_user_organization(db, user)` helper'i: user.organization_id varsa o organizasyonu, yoksa default'u doner (legacy uyumluluk).
- ✅ `enterprise_service.list_enterprise_sessions/get_enterprise_session/list_enterprise_tickets/update_enterprise_ticket_status/list_departments/create_enterprise_session/process_enterprise_message/enterprise_metrics` artik kullaniciya bagli organizasyona scope ediliyor.
- ✅ `clinical_service.ensure_clinic_access` user.organization_id varsa o klinige duser; yoksa default'a fallback.
- ✅ `dependencies.get_current_organization` dependency'si route'lar icin yardimci.
- ✅ Cross-tenant izolasyon testi: iki org / iki operator / iki enterprise session → listeler ayri, baska org'un kaynagina GET 404 doner.

## Faz 3 — Ajan Mimari Genisletme (TAMAMLANDI ✅)

1. ✅ `AgentDecisionLog` tablosu (migration `b2c3d4e5f6a7`) — agent_type, intent, confidence, risk, requires_human, action, reason, organization_id, clinic_id, conversation_id, chat_session_id, user_id, request_id, payload_json, created_at.
2. ✅ `services/agents/logging.py:record_agent_decision(db, decision, ...)` — tek soyutlama tum kararlari tabloya yazar.
3. ✅ `services/agents/logging.py:build_decision(...)` — caller'lar dataclass'i bilmek zorunda kalmadan AgentDecision uretebilir.
4. ✅ `clinical_service.ingest_clinical_message` her iki return path'inde de karari logluyor (SUPPORT auto_reply / ROUTING shadow_review).
5. ✅ `clinical_service.update_shadow_review` operator kararini ROUTING agent decision olarak kaydediyor (approved/edited/rejected).
6. ✅ `clinical_service.update_pre_intake` FORM agent decision yaziyor (persist_pre_intake / ask_next_question).
7. ✅ REST endpoint'ler `GET /api/agents/decisions` (filtreli: agent_type, requires_human, risk, conversation_id) ve `GET /api/agents/decisions/{id}` — organization scope, operator/admin only, cross-tenant 404.
8. ⏳ Mock agentlerin gercek LLM bag(la)nti'sina refactor'u (Faz 3.5).

## Faz 4 — Frontend Olgunlasma (KISMI TAMAMLANDI ✅)

1. ✅ **React Router** entegrasyonu: `/login`, `/customer/*`, `/operator/*`, `/admin/*` rotalari. `RequireRole` guard'i yanlis role gore kanonik home'a yonlendiriyor; `RoleRedirect` root URL'i role gore homepage'e yolluyor.
2. ✅ **i18n iskelet**: hafif vanilla `I18nProvider` + `useT()` + `dict.ts` (TR/EN). Locale `localStorage`'a persist ediliyor; LoginScreen header'inda TR/EN switcher chip mevcut. (Tum stringlerin extraction'i siradaki adim — `react-i18next` migration'i ihtiyaca gore.)
3. ✅ **Mobile responsiveness**: `@media (max-width: 980px)` ile dashboard grid tek kolona dusuyor, sidebar sticky banner oluyor; 640px altinda toast container full-width.
4. ⏳ **React Query** — bu PR'da yok; mevcut manuel `loadDashboard` calisiyor, sonraki olgunlasma adimi.
5. ✅ **Skeleton**: `SkeletonText`, `SkeletonBlock` vanilla CSS'e port (eski Tailwind sinifleri olu kod). DecisionLogView yukleme durumunda kullaniyor.
6. ✅ **Decision log mini view**: `/api/agents/decisions` Phase 3 endpoint'ini tuketen DecisionLogView; operator/admin icin clinical panelin sagina yerlesti. Filtreler: tumu / insan-onayi / otomatik.

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
