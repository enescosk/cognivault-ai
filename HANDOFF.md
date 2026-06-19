# CogniVault — Session Handoff (2026-06-19)

Bu session dört iş yaptı: (1) BiGG iş planı revizyonu, (2) web tasarım sistemi +
governance yüzeyleri, (3) mobil **Hekim app**, (4) hekim bazlı profesyonel randevu
takvimi ve klinik işlem planı. Aşağıda güncel durum ve sıradaki adımlar var.

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

## 3) Mobil Hekim app — `mobile/` — ✅ İlk karar kuyruğu dilimi hazır
Expo + React Native + TypeScript, web render destekli (`react-native-web` kurulu, çalışıyor).
Stack toolchain doğrulandı (Expo web default app render etti).

**Yazıldı (hazır):**
- `mobile/src/theme.ts` — açık medikal tema token'ları (web klinik temasıyla uyumlu).
- `mobile/src/api.ts` — `api.login / me / overview / decide` + `readGovernance`. **Gerçek backend**
  (`http://localhost:8000/api`), web client'la birebir endpoint'ler:
  `POST /auth/login`, `GET /clinical/overview`, `PATCH /clinical/shadow-reviews/{id}` `{status, final_reply}`.
  `EXPO_PUBLIC_API_URL` ile cihaz/LAN backend adresi override edilebilir.
- `mobile/src/auth.tsx` — `AuthProvider` + `useAuth` (token `AsyncStorage`'da, `cognivault_token`).
- `mobile/src/components/ui.tsx` — RN primitive'leri: `Badge`, `Button`, `Meter`, `Dot`,
  `StatusRow`, `EmptyState`.
- `mobile/src/components/ShadowReviewCard.tsx` — native Karar Kartı: güven, eskalasyon,
  AI taslağı, governance/veri sınıfları/maskeli önizleme ve karar aksiyonları.
- `mobile/src/screens/LoginScreen.tsx` — demo bilgileriyle giriş, loading/error durumları.
- `mobile/src/screens/QueueScreen.tsx` — gerçek backend onay kuyruğu, pull-to-refresh,
  optimistic onay/düzeltme/ret ve hata halinde rollback.
- `mobile/src/screens/AppointmentsScreen.tsx` + `AppTabs.tsx` — uygulama artık varsayılan
  **Randevular** (bekleyen) sekmesiyle açılır; **Onaylanan** randevular ikinci sekmeye,
  AI taslakları **AI Kararlar** sekmesine ayrıldı. Randevu onayı optimistic olarak ilk
  listeden çıkar ve onaylanan listeye geçer. Hekime özel gün şeridi; başlangıç/bitiş
  saati; hasta, geliş nedeni ve işlem planı gösterilir. Klinik plan modalında tarih-saat,
  süre, not ve işlem durumları (`planlandı / sürüyor / tamamlandı / iptal`) düzenlenebilir.
- `mobile/App.tsx` — auth restore spinner → login veya hekim kuyruğu.
- Expo app adı/slug'ı `Cogni Klinik` / `cogni-klinik` olarak güncellendi.
- Doğrulama: `npx tsc --noEmit`, `npx expo install --check`, Expo web export geçti;
  masaüstü + 390×844 mobil web render, login ve düzenle/vazgeç akışı gerçek backend ile test edildi.

**SIRADAKİ ADIMLAR:**
1. ✅ Hekim (`clinician`) login'i + `Doctor.user_id` + `ShadowReview.assigned_doctor_id`
   bağlantısı açıldı. Demo: `hekim@cognivault.com / demo123` → Dr. Deniz Aksoy;
   hekim yalnızca kendisine atanmış kartları görebilir ve karara bağlayabilir.
2. ✅ Gerçek telefon LAN akışı hazır: backend `0.0.0.0:8000`,
   `./scripts/run_mobile_phone.sh` otomatik LAN IP + Expo Go QR üretir. Ayrıntı `mobile/README.md`.
3. ✅ `ClinicalAppointment.assigned_doctor_id` eklendi; hekim yalnız kendi bekleyen/onaylanan
   randevularını listeler ve yalnız kendi randevusunun durumunu değiştirebilir.
4. ✅ `0007_clinical_calendar_procedures.py`: randevu bitişi/süresi/geliş nedeni ve
   `ClinicalAppointmentProcedure` modeli eklendi. Aynı hekimin çakışan onaylı
   randevusuna API `409` döner; tamamlanan işlem hekime ve zamanına bağlanır.
5. ✅ Web operatör paneli ve `/operator/appointments`, randevuları gün/saat çizelgesinde
   hekim, hasta, geliş nedeni ve işlem detaylarıyla gösterir. Hekim API kapsamı kendi
   takvimiyle sınırlıdır.
6. Sıradaki: gerçek iPhone'da son dokunmatik QA ve ad hoc iOS imzalama/build.
   - iOS EAS hazırlığı yapıldı: `mobile/eas.json`, bundle id
     `com.cognivault.cogniklinik`, `iphone-local` ad hoc profili ve TestFlight production
     profili hazır. Build blokajı: bu Mac'te Expo oturumu açık değil; Xcode da kurulu değil.
7. Karar aksiyonlarına native onay/haptic ve başarı toast'ı; ağ durumu/offline geri bildirimleri.
8. Expo Router'a geçiş, karar geçmişi ve `expo-notifications` push.

**Çalıştırma:** `cd mobile && npm run web -- --port 5195` → `http://localhost:5195`
(5195 CORS-izinli; backend açık olmalı).

**Backend bağlama durumu:** Hekim (`clinician`) login'i aktif; kullanıcı `Doctor.user_id`
üzerinden doktor kaydına bağlıdır. Shadow review ve randevu sorguları hekimin kendi
kayıtlarıyla sınırlandırılır. Seed, slot hekimleri için ayrı demo clinician hesapları üretir.

---

## Çalışan servisler / ortam
- Backend: `./scripts/run_backend.sh` (uvicorn :8000, startup'ta seed). LLM gerekmez (kural-bazlı fallback).
- Gerçek shadow review üret: operator login → `POST /api/clinical/simulate-whatsapp`
  `{ "from_phone":"+90...", "body":"<acil/ağrı mesajı>", "patient_name":"..." }` (acil mesaj → governance'lı review).
- CORS izinli portlar: `5173/5174/5185/5195`. Web `5185`, mobil web `5195`.
- `.claude/launch.json` (gitignore'lu) preview config'leri içerir: `frontend` (5185), `mobile` (5195).

## 4) Müşteri dili / klinik LLM güvenlik katmanı
- `backend/app/services/customer_understanding.py`: Türkçe/İngilizce konuşma dili,
  yaygın yazım hataları, çoklu niyet ve kısa konuşma devamlarını ağırlıklı ve
  denetlenebilir kanıtlarla sınıflandırır.
- Hafif diş eti kanaması artık otomatik 112 sayılmaz; yalnız yüksek özgüllüklü
  acil ifadeler acil yönlendirmeyi tetikler.
- Generatif model deterministik acil kararını düşüremez. Çelişkide intent, yanıt
  ve aksiyon güvenli şablona kilitlenir; düşük güven/çelişki insan incelemesine gider.
- Lokal model fallback'i prompt kurallarını hasta mesajı sanmaz; yalnız
  `Patient message` bölümünü sınıflandırır.
- `backend/tests/test_customer_understanding.py` gerçek müşteri ifadeleri, typo,
  çoklu talep, bağlam devamı, yanlış-acil ve model downgrade senaryolarını kapsar.
- Unit kapsamı genişletildi: `test_customer_understanding.py` konuşma dili,
  Unicode/Türkçe büyük-İ, ekli kelimeler, olumsuzlama, false-positive, prompt
  injection, bozuk JSON ve güvenli action vakalarını; `test_clinical_ai_unit.py`
  branş, aciliyet, tercih zamanı, sentiment, hayali slot ve consent kararlarını kapsar.
- Hasta metni `<patient_message>` sınırları içinde güvenilmeyen veri olarak modele
  verilir; kapanış etiketi enjeksiyonu nötralize edilir. İlaç/doz/teşhis üreten model
  yanıtı güvenli şablonla değiştirilip insan incelemesine gönderilir.
- Tüm OpenAI/Anthropic/lokal sağlayıcı çıktıları ortak, 64 KB limitli JSON-object
  parser'ından geçer; fenced JSON desteklenir, liste/bozuk/aşırı büyük çıktı reddedilir.
- Son doğrulama: **319 backend testi geçti**; compileall ve `git diff --check` temiz.

## Mimari karar — mobil (2 app, 4 persona)
- **Cogni Klinik** (personel): Hekim / Asistan-operatör / Admin-sahip (role göre deneyim).
- **Cogni** (hasta): AI sohbet/triyaj + randevu + KVKK rıza.
- Şu an inşa edilen: Cogni Klinik → **Hekim** deneyimi (Shadow Mode onay kuyruğu).
- Roller (kod doğrulandı): sistem `RoleName` = customer/operator/admin; klinik `ClinicUserRole` = owner/operator/clinician; `Doctor` ayrı kayıt.
