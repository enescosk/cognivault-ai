# CogniVault — Session Handoff (2026-06-19)

Bu session üç iş yaptı: (1) BiGG iş planı revizyonu, (2) web tasarım sistemi +
governance yüzeyleri, (3) mobil **Hekim app**'in başlangıcı. Mobil app **devam
edilecek** — aşağıda tam olarak nerede kalındığı ve sıradaki adımlar var.

---

## 1) BiGG iş planı revizyonu — `docs/bigg-revize/`
- `CogniVaultAI_Yenilikcilik_Revizyon_Notu_v2.docx/.pdf` — koça kapak/yanıt notu.
- `CogniVaultAI_BiGG_IsPlani_TAM_v2.docx/.pdf` — AGY 112 yapısında tam plan.
- Çekirdek reframe: **deterministik KVKK governance zarfı (non-SaMD)** + kalibre-çekimser
  Türkçe diş triyajı + on-prem yığın; federe öğrenme Faz-2 (Owkin/NVIDIA prior-art kabul edildi).
- Dosyalar Desktop'a da kopyalandı.

## 2) Web tasarım sistemi + governance yüzeyleri — `frontend/`
- `frontend/DESIGN_SYSTEM.md` — **tek tasarım kaynağı**. Token'lar + iterasyon döngüsü +
  **çift-tema notu**: koyu `:root` (varsayılan) vs açık `.clinical-view` (operatör paneli).
- `frontend/src/styles/ui.css` — primitive katmanı + `ShadowReviewCard` + `DecisionLog`
  stilleri + `.clinical-view` açık-tema override'ları.
- `frontend/src/components/ui/*` — `Button/Card/Panel/Badge/StatusDot/Field` (tipli, yeniden kullanılabilir).
- `frontend/src/components/Styleguide.tsx` — `/styleguide` (public route, `App.tsx`'e eklendi).
- `frontend/src/components/clinical/ShadowReviewCard.tsx` — **"Karar Kartı"**: bir `ShadowReview`'ı
  governance ile gösterir (güven/kalibrasyon, çekimserlik+neden, "AI taslağı·teşhis yok",
  "yerel işlendi·ham veri çıkmadı"+veri sınıfları+maskeli önizleme, onayla/düzenle/reddet).
  `ClinicalPanel`'in onay listesine entegre edildi (handler'lar birebir korundu).
- `frontend/src/components/DecisionLogView.tsx` — **yeniden yazıldı**: denetim-izi odaklı karar
  günlüğü (risk rozeti · insana/otomatik · %güven · `iz·#id`).
- Hepsi **gerçek backend verisiyle canlı doğrulandı**; `cd frontend && npm run build` geçiyor.

## 3) Mobil Hekim app — `mobile/` — ⏳ DEVAM EDİLECEK
Expo + React Native + TypeScript, web render destekli (`react-native-web` kurulu, çalışıyor).
Stack toolchain doğrulandı (Expo web default app render etti).

**Yazıldı (hazır):**
- `mobile/src/theme.ts` — açık medikal tema token'ları (web klinik temasıyla uyumlu).
- `mobile/src/api.ts` — `api.login / me / overview / decide` + `readGovernance`. **Gerçek backend**
  (`http://localhost:8000/api`), web client'la birebir endpoint'ler:
  `POST /auth/login`, `GET /clinical/overview`, `PATCH /clinical/shadow-reviews/{id}` `{status, final_reply}`.
- `mobile/src/auth.tsx` — `AuthProvider` + `useAuth` (token `AsyncStorage`'da, `cognivault_token`).

**YAZILACAK (sıradaki adımlar, bu sırayla):**
1. `mobile/src/components/ui.tsx` — RN primitive'leri: `Badge` (tone'lu), `Button`
   (primary/ghost/danger), `Meter` (güven çubuğu, track+fill), `Dot`/`StatusRow`.
   Web `ui.css` + `ShadowReviewCard.tsx`'i referans al, RN `StyleSheet`'e çevir.
2. `mobile/src/components/ShadowReviewCard.tsx` — native Karar Kartı. Web component'inin
   (`frontend/src/components/clinical/ShadowReviewCard.tsx`) RN hali: branş badge, güven meter,
   "insana yükseltildi"+neden, AI taslağı kutusu, governance satırı (`readGovernance`), onayla/düzenle/reddet.
3. `mobile/src/screens/LoginScreen.tsx` — giriş formu (demo: `operator@cognivault.com` / `demo123`),
   `useAuth().login`, hata gösterimi.
4. `mobile/src/screens/QueueScreen.tsx` — Hekim onay kuyruğu: `api.overview(token)` → `shadow_reviews`
   `FlatList`'i, pull-to-refresh, header (klinik adı + bekleyen sayısı + çıkış), `api.decide` ile onay/düzenle/reddet, optimistic update + refetch.
5. `mobile/App.tsx` — `AuthProvider` ile sar; `loading ? spinner : token ? <QueueScreen/> : <LoginScreen/>`.
   (Şu an default Expo template; değiştirilecek.)
6. (Sonra) navigasyon/sekmeler (expo-router), `expo-notifications` ile push.

**Çalıştırma:** `cd mobile && npm run web -- --port 5195` → `http://localhost:5195`
(5195 CORS-izinli; backend açık olmalı).

**Backend bağlama notu (Faz-2):** Hekim (`clinician`) login'i **henüz yok** —
`ClinicUserRole.CLINICIAN` modelde var ama auth akışına bağlı değil, `Doctor` ise login olmayan kayıt.
Şimdilik `operator`/`admin` token'ı klinik veriye erişiyor (app çalışır). Sonra: clinician login aç +
`Doctor` kaydını login'e bağla + onay kuyruğunu o hekime daralt.

---

## Çalışan servisler / ortam
- Backend: `./scripts/run_backend.sh` (uvicorn :8000, startup'ta seed). LLM gerekmez (kural-bazlı fallback).
- Gerçek shadow review üret: operator login → `POST /api/clinical/simulate-whatsapp`
  `{ "from_phone":"+90...", "body":"<acil/ağrı mesajı>", "patient_name":"..." }` (acil mesaj → governance'lı review).
- CORS izinli portlar: `5173/5174/5185/5195`. Web `5185`, mobil web `5195`.
- `.claude/launch.json` (gitignore'lu) preview config'leri içerir: `frontend` (5185), `mobile` (5195).

## Mimari karar — mobil (2 app, 4 persona)
- **Cogni Klinik** (personel): Hekim / Asistan-operatör / Admin-sahip (role göre deneyim).
- **Cogni** (hasta): AI sohbet/triyaj + randevu + KVKK rıza.
- Şu an inşa edilen: Cogni Klinik → **Hekim** deneyimi (Shadow Mode onay kuyruğu).
- Roller (kod doğrulandı): sistem `RoleName` = customer/operator/admin; klinik `ClinicUserRole` = owner/operator/clinician; `Doctor` ayrı kayıt.
