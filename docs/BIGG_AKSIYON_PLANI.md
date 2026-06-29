# CogniVault Medical AI — BiGG Aksiyon Planı

Kaynak: `CogniVaultAI_BiGG_IsPlani_TAM_v2.docx` (TÜBİTAK BiGG 1812 İş Planı, Revize v2)
Proje süresi (resmi): 1 Ekim 2026 – 30 Eylül 2027 (12 ay)
Son güncelleme: 2026-06-19

> **Nasıl kullanıyoruz:** Her gün yeni iş aramıyoruz. Bu dosyadaki sıradaki açık maddeyi alıyoruz, bitirince başına `✅ YAPILDI (tarih)` yazıp bir sonrakine geçiyoruz. Aktif olarak çalıştığımız madde **🔵 ŞU AN** ile işaretli.
>
> Durum etiketleri: `⬜ AÇIK` · `🔵 ŞU AN` · `🟡 DEVAM` · `✅ YAPILDI`

---

## Genel İlerleme Özeti

| İş Paketi | Konu | Resmi Ay | Durum |
|-----------|------|----------|-------|
| İP-1 | Türkçe Diş Triyaj NLU + Kalibre Çekimser Yönlendirici | Ay 1–7 | 🟡 MVP iskeleti var, Ar-Ge açık |
| İP-2 | Deterministik Yönetişim Zarfı'nın Sertleştirilmesi | Ay 1–8 | 🟡 Zarf çalışıyor, kanıt/test açık |
| İP-3 | On-prem Yerel Yığın Optimizasyonu | Ay 3–9 | 🟡 Yerel yığın var, optimizasyon açık |
| İP-4 | Hekim-Döngülü İyileştirme + Öngörücü Süreklilik | Ay 5–10 | 🟡 Shadow Mode var, no-show motoru açık |
| İP-5 | Pilot Saha & Klinik Doğrulama | Ay 7–12 | ⬜ Açık |
| İP-6 | Ticarileştirme & Fikri Mülkiyet | Ay 9–12 | ⬜ Açık |

**🔵 ŞU ANKİ ODAK:** İP-1 / Madde 1.6 — çekimser/selective prediction (düşük-güvende insana yükseltme).

---

## İP-1 — Türkçe Diş Triyaj NLU + Kalibre Çekimser Yönlendirici
**Başarı ölçütü:** Branş eşlemede ≥%90 · kalibrasyon ECE<0,05 · acil-recall ≈ %100 (kaçan acil ≈ 0) · ≥500 anonim senaryo.
**Çıktı:** Yönlendirici + kalibrasyon raporu. **Sorumlu:** Efe.

- ✅ **1.1** YAPILDI (2026-06-19) Branş + aciliyet ontolojisi tanımlandı — tek doğru kaynak `backend/app/clinical/ontology.py` (10 branş + genel, 3 aciliyet seviyesi). `clinical_ai_service` ontolojiye bağlandı; 40 test geçti (`tests/test_clinical_ontology.py`). Hekim onayına hazır şema.
- ✅ **1.2** YAPILDI (2026-06-19) Türkçe diş şikâyeti korpusu kuruldu — `backend/app/clinical/corpus/`. Deterministik sentetik üretici (`build.py`) → **546 etiketli senaryo** (11 branş + 3 aciliyet + 4 kanal, dengeli, PII-temiz); 35 vakalık elle küratörlü **golden** değerlendirme seti (`build_golden.py`). Etiketler ontolojiye bağlı (yer-doğruluğu). 13 test (`tests/test_corpus.py`), üretici↔dosya senkron kapısı dahil. KVKK: tamamen sentetik/anonim, gerçek hasta verisi yok.
- ✅ **1.3** YAPILDI (2026-06-22) Türkçe argo normalizasyon hattı — `app/clinical/normalizer.py`. 35 argo → kanonik terim kuralı (endodonti, restoratif, periodontoloji, pedodonti, ortodonti, çene cerrahisi, implant, estetik, medikal estetik, dermatoloji, acil). `expand_complaint()` ham metni zenginleştirir; `triage()` sarmalayıcı ham metin → branş + aciliyet tek adımda verir. `tests/test_normalizer.py` — 45 test (genişletme kuralları, uçtan uca branş yönlendirme, aciliyet tespiti, yanlış-pozitif koruması). Tüm mevcut testler regresyonsuz.
- ✅ **1.4** YAPILDI (2026-06-22) Branş yönlendirme modeli — sentetik korpusta **%99.3 doğruluk** (542/546), hedef ≥%90 aşıldı. `match_specialty` skorlama tabanlına yükseltildi (en çok+en uzun eşleşme; normalize tekilleştirme) — "dudak dolgusu"nun "dolgu"ya kapılması gibi alt-dizi çakışmaları çözüldü. Ontoloji anahtar kelimeleri genişletildi (perio: "diş etler"/"kanama"; çene: "çene kırığı"), zamir çakışması yapan dermatoloji "ben" anahtarı kaldırıldı. Normalizer'a kalan argo kuralları eklendi (apse→endodonti, çatladı, kaşınma/mol, termal hassasiyet, çekim varyantları, 20lik genişletme). Yeniden kullanılabilir değerlendirme harness'ı: `app/clinical/evaluate.py` (`python -m app.clinical.evaluate`). Golden set (kasıtlı zor) %62.9 — kalan X→genel_dis kaçışları İP-1.6 çekimser tahminin (insana yükseltme) hedefi, kurala zorla uydurulmadı. Tüm bağımsız testler (ontoloji+korpus+normalizer = 78) geçti.
- ✅ **1.5** YAPILDI (2026-06-23) Güven kalibrasyon katmanı — `app/clinical/calibration.py` (saf Python, numpy/sklearn yok; KVKK local-first). Eşleşme marjından ham güven sinyali + isotonic regresyon (Pool-Adjacent-Violators) ile [0,1] kalibre güven. Sentetik korpus TEST setinde **ECE = 0.0107 < 0,05** (hedef karşılandı; naif normda 0,5421'di). `app/clinical/calibrate.py` rapor+artefakt üreticisi (`python -m app.clinical.calibrate`); kalibratör `data/calibration.json`'a yazılır (JSON, denetlenebilir). `triage()` artık kalibre `confidence` döndürür (kalibratör yoksa 0.0 → güvenli varsayılan, İP-1.6 insana yükseltir). `ontology.rank_specialties()` tek skorlama kaynağı olarak eklendi (match_specialty davranışı korundu). `tests/test_calibration.py` — 13 test. Golden set ECE 0,357 (aşırı-güvenli) → İP-1.6'nın hedefi.
- ⬜ **1.6** Çekimser/selective prediction: düşük-güven veya tutarsız kanıtta otomatik insan-yükseltme (conformal prediction eşiği).
- ⬜ **1.7** Acil-recall ≈ %100 garantili kapsama testi (kaçan acil ≈ 0). Adversarial acil senaryolarıyla doğrula.
- ⬜ **1.8** Kalibrasyon raporu üret (ECE, recall, branş doğruluğu metrik panosu).

## İP-2 — Deterministik Yönetişim Zarfı'nın Sertleştirilmesi
**Başarı ölçütü:** 150+ senaryoda %100 doğru kapı · kapı ihlali = 0 (adversarial) · teşhis/sınır-ötesi/kimlik sızıntısı = 0.
**Çıktı:** Zarf + test koşumu + denetim izi. **Sorumlu:** Enes.

- ✅ **2.1** Veri-sınıfı kapısı (özel-nitelikli sağlık / finansal / kimlik / ses metadata sınıflandırması). — Mevcut: `services/clinical_compliance_service.py`, `agent/policy.py`.
- ✅ **2.2** İnsan-yükseltme tetikleyicileri (acil/sigorta/kimlik/düşük-güven). — Mevcut: `policy.py` GovernanceContext.
- 🟡 **2.3** Teşhis/tedavi talimatı bloklama — mevcut zarfta var; adversarial testle ihlal-edilemezliği kanıtlanacak.
- 🟡 **2.4** Sınır-ötesi (residency) modu ve rıza kapıları — temel var; rızasız harici işleyici engeli formal test edilecek.
- ✅ **2.5** Maskeli denetim izi (PII maskeleme + audit log). — Mevcut: `services/audit_service.py`, redaction hattı.
- ⬜ **2.6** Property-based test paketi (kapı kuralları için değişmezler).
- ⬜ **2.7** Adversarial test paketi — 150+ senaryo, hedef kapı-ihlali = 0. Mevcut `tests/test_hardening.py` genişletilecek.
- ⬜ **2.8** Kapı ihlal-edilemezliği kanıt raporu (test koşumu + denetim izi örnekleri).

## İP-3 — On-prem Yerel Yığın Optimizasyonu
**Başarı ölçütü:** On-prem yanıt gecikmesi hedefi karşılanır · modest donanımda klinik-yönlendirme kalitesi.
**Çıktı:** Optimize yerel yığın + gecikme raporu. **Sorumlu:** Efe.

- ✅ **3.1** Yerel ASR (faster-whisper) entegrasyonu. — Mevcut: commit `890102d`, `ai/voice_factory.py`.
- ✅ **3.2** Yerel TTS (Piper tr_TR) entegrasyonu. — Mevcut: commit `890102d`.
- ✅ **3.3** Yerel LLM (Qwen2.5 sınıfı / Ollama) entegrasyonu. — Mevcut: commit `ad6d49b`, `ai/ai_factory.py`.
- ✅ **3.4** PII maskeleme hattı (her işleyiciden önce). — Mevcut: compliance service.
- ✅ **3.5** Harici LLM/STT/TTS klinik veride varsayılan kapalı. — Mevcut: residency varsayılanları.
- ⬜ **3.6** Küçük on-prem modelin TR diş korpusunda damıtma/ince-ayarı (İP-1.2 korpusuna bağlı).
- ⬜ **3.7** Gerçek-zamanlı ses: VAD, gürültü toleransı, kesinti yönetimi.
- ⬜ **3.8** Gecikme optimizasyonu — modest donanımda hedef latency ölç ve raporla.
- ⬜ **3.9** Gecikme + kalite raporu.

## İP-4 — Hekim-Döngülü İyileştirme + Öngörücü Süreklilik
**Başarı ölçütü:** Onay başına karar <30 sn · no-show AUC≥0,75 · pilotta iptal/kaçan-çağrı kurtarımı ≥%60.
**Çıktı:** RLHF döngüsü + süreklilik servisi. **Sorumlu:** Enes.

- ✅ **4.1** Shadow Mode hekim onay akışı. — Mevcut: clinic admin panel + decision log (`DecisionLogView.tsx`, `test_phase3_decisions.py`).
- ⬜ **4.2** Hekim onay/düzeltmelerinden etiket üretimi (RLHF veri toplama döngüsü).
- ⬜ **4.3** Zarf-içi politika eşiği iyileştirme (onaylardan öğrenme, kapı kurallarını ihlal etmeden).
- ⬜ **4.4** Onay başına karar süresi <30 sn ölçüm + optimizasyon.
- ⬜ **4.5** No-show / süreklilik risk modeli — AUC≥0,75 hedefi.
- ⬜ **4.6** Dinamik slot önerisi motoru.
- ⬜ **4.7** Kişiye özel proaktif geri-çağırma zamanlaması (yarım kalan tedavi, geciken kontrol).

## İP-5 — Pilot Saha & Klinik Doğrulama
**Başarı ölçütü:** ≥%85 memnuniyet · ≥3 referans · saha kalibrasyon raporu · sıfır güvenlik-kapısı ihlali.
**Çıktı:** Metrik panosu + saha raporu. **Sorumlu:** Enes+Efe.

- ⬜ **5.1** 3–5 pilot klinik bul ve sözleşme/rıza süreçlerini hazırla.
- ⬜ **5.2** Canlı pilot dağıtımı (on-prem kurulum + onboarding).
- ⬜ **5.3** Saha kalibrasyon ve güvenlik kapısı doğrulaması.
- ⬜ **5.4** Kaçan çağrı kurtarma / dönüşüm / memnuniyet metrik panosu.
- ⬜ **5.5** Haftalık iterasyon döngüsü.
- ⬜ **5.6** Saha raporu + ≥3 referans toplama.

## İP-6 — Ticarileştirme & Fikri Mülkiyet
**Başarı ölçütü:** ≥5 ücretli klinik · vekil-incelemeli patent başvuru paketi (3 bağımsız istem) · onboarding <1 gün.
**Çıktı:** Faturalama + patent dosyası + Faz-2 notu. **Sorumlu:** Efe+Enes.

- 🟡 **6.1** Abonelik + başarı-bazlı faturalama (Starter/Growth/Enterprise). — Mevcut: `services/billing_service.py` temeli var; tam fiyat modeli açık.
- 🟡 **6.2** Çoklu-kiracı (multi-tenant) dağıtım. — Mevcut: `test_phase1_tenant.py` tenant izolasyonu var; onboarding <1 gün hedefi açık.
- ⬜ **6.3** Onboarding akışını <1 güne indir.
- ⬜ **6.4** Yöntem patenti novelty araştırması (prior-art, TÜRKPATENT EPATS).
- ⬜ **6.5** Patent istem taslakları — 3 bağımsız istem (yönetişim zarfı / kalibre triyaj / hekim onay paketi) + bağımlı istemler.
- ⬜ **6.6** Vekil-incelemeli patent başvuru paketi.
- ⬜ **6.7** Federe öğrenme Faz-2 fizibilite notu.
- ⬜ **6.8** ≥5 ücretli klinik dönüşümü.

---

## 🔍 Kod İncelemesi Bulguları — Üretim Sertleştirme Backlog'u (2026-06-29)

Kaynak: Gemini/Antigravity dış inceleme raporu (`cognivault_review.md`). Her madde **gerçek kodla doğrulandı** (3 paralel inceleme ajanı). BiGG Ar-Ge milestone'larından ayrı; üretim/pilot (İP-5) hazırlığı ve zarf sertleştirme (İP-2) backlog'u. Madde önekleri: **R-n**.

### Raporun yanıldığı / abarttığı noktalar (önce bunlar — gereksiz iş açma)
- ❌ **"Webhook imza doğrulaması yok" → YANLIŞ.** `app/core/webhook_security.py` mevcut; `clinical.py`'de Twilio (`X-Twilio-Signature`) + Meta (`X-Hub-Signature-256`) doğrulanıyor, `signature_required()` config kapısıyla. Eylem: bug değil → prod config'te açık olduğunu doğrula + test ekle.
- ❌ **"FK indeksleri büyük ölçüde eksik" → YANLIŞ/ABARTILI.** 98 FK'nın ~%64'ü `index=True`. Eylem: yalnız N+1'e konu birkaç sıcak FK'yı (örn. `appointment.branch_id`) indeksle.
- ⚠️ **"Mobil disclaimer butonların altında" → KISMEN/YANLIŞ.** `ShadowReviewCard.tsx:92`'de disclaimer butonların **üstünde**. Eylem: düşük öncelik, küçük-ekran taşma koruması.
- ⚠️ **"Injection savunması tamamen baypas" → KISMEN.** Yalnız `</patient_message>` kapatma-etiketi alt-kuralı ölü (normalize `<>`'i siliyor); "ignore previous instructions" vb. geniş desenler çalışıyor. Yine de gerçek açık → R-1.
- ⚠️ **"AsyncStorage eksik" → YANLIŞ.** `mobile/package.json:7`'de var; yalnız `netinfo` eksik (R-15).

### P0 — Emniyet & Güvenlik (doğrulandı)
- ⬜ **R-1** Injection: `</patient_message>` etiket kontrolünü **ham (normalize edilmemiş) metin** üzerinde çalıştır. `customer_understanding.py:227-239`. → İP-2.7 ile birleştir.
- ⬜ **R-2** Auth eviction: token'ı yalnız HTTP **401/403**'te sil; ağ hatası/timeout'ta koru + "sunucuya bağlanılamadı" uyarısı. `mobile/src/auth.tsx:32`, `frontend/src/context/AuthContext.tsx:44`. [her iki uygulama]
- ⬜ **R-3** LLM geçmişinde çift kullanıcı mesajı: son mesaj zaten `session.messages`'taysa tekrar push etme. `orchestrator.py:530, 668`.
- ⬜ **R-4** Anthropic stream onay kartı yutuluyor (`pass`): parse edilen kartı dış `confirmation_card`'a ata. `orchestrator.py:840-843, 856`. [yalnız Anthropic yolu; diğer yol doğru]
- ⬜ **R-5** Held-slot sweeper yok: `expire_stale_slot_offers` yalnız lazy/inline çağrılıyor → `repeat_every` ile periyodik koş. Ek nüans: fonksiyon HELD'i `offered`'a değil `EXPIRED`'a çeviriyor; slot'un tekrar açılması için davranışı gözden geçir. `clinical_slot_service.py:262`.
- ⬜ **R-6** Intent-injection regex sıkılaştır: hardcoded 3-intent yerine `intent(?:ini)? [a-z_]+ yap`. `customer_understanding.py:231`. → İP-2.7.

### P1 — Performans & Veri Doğruluğu (doğrulandı)
- ⬜ **R-7** N+1 randevu listeleme: `ClinicalAppointment`'a `patient`/`branch` ORM ilişkisi + `selectinload`; `appointment_row_payload`'daki döngü-içi `db.get` kaldır. `clinical_appointment_service.py:167`, `clinical.py:388`. [doctor zaten eager]
- ⬜ **R-8** N+1 shadow review: `list_shadow_reviews`'a `selectinload(ShadowReview.assigned_doctor)`. `clinical_service.py:1047`.
- ⬜ **R-9** Mobil saat dilimi: randevu saatlerini cihaz local yerine klinik tz'ine (`Europe/Istanbul`) kilitle. `mobile/src/screens/AppointmentsScreen.tsx:71`. [hasta-emniyeti açısından önemli]
- ⬜ **R-10** Ölü/mükerrer servis kodu sil: `clinical_service.py:1084-1329` (create/status/manual/update_shadow) — tüketiciler `clinical_appointment_service`/`clinical_feedback_service`'ten import ediyor. NOT: `list_shadow_reviews` hâlâ canlı, silme.
- ⬜ **R-11** Web ses/mikrofon sızıntısı: unmount cleanup'ta `stream.getTracks().forEach(t=>t.stop())` + `AudioContext.close()`. `ChatWindow.tsx:107, 219`. [mic yalnız `onstop`'ta duruyor → unmount'ta sızıyor]
- ⬜ **R-12** Admin sayfalarında hardcoded hex → token/CSS değişkenleri (koyu tema okunabilirliği). `AdminDoctorsPage.tsx`, `AppointmentsPage.tsx`.

### P2 — Mimari & UX (doğrulandı)
- ⬜ **R-13** Doctor ↔ ClinicDoctor şema birleştirme: iki ayrı tablo (`doctors` user-linked login + `clinic_doctors` slot); appointment ikisine de referans veriyor (`doctor_id`+`assigned_doctor_id`), FK bağı yok. Büyük refactor.
- ⬜ **R-14** Mobil global state: kuyruk verisini Context/Zustand'a taşı (sekme geçişinde flicker). `QueueScreen.tsx`, `App.tsx:36`.
- ⬜ **R-15** `@react-native-community/netinfo` ekle + offline banner + `expo-haptics`.
- ⬜ **R-16** Web karar kartına "Vazgeç/Kapat"; mobil disclaimer küçük-ekran taşma koruması; Google Fonts lokalize (on-prem/offline). [düşük öncelik]

---

## Kilometre Taşları (resmi takvim)
- **Ay 6:** Kalibre çekimser yönlendirici (ECE<0,05) MVP — İP-1 çıktısı.
- **Ay 8:** Adversarial-test ile ihlal-edilemezliği kanıtlanmış yönetişim zarfı — İP-2 çıktısı.
- **Ay 10:** Hekim-döngülü iyileştirme + öngörücü süreklilik pilotta — İP-4 çıktısı.
- **Ay 12:** ≥5 ücretli klinik + vekil-incelemeli patent paketi (3 bağımsız istem) — İP-6 çıktısı.

## Değişiklik Günlüğü
- 2026-06-19: Plan oluşturuldu. Mevcut MVP üzerinden İP-2 (zarf), İP-3 (yerel yığın), İP-4 (shadow mode) temel maddeleri YAPILDI işaretlendi. Aktif odak İP-1.1.
- 2026-06-19: İP-1.1 YAPILDI. `app/clinical/ontology.py` ontoloji modülü eklendi (branş + aciliyet, tek kaynak); `clinical_ai_service` yinelenen tanımlardan arındırılıp ontolojiye bağlandı; `tests/test_clinical_ontology.py` (12 test) eklendi. Odak İP-1.2'ye taşındı.
- 2026-06-19: İP-1.2 YAPILDI. `app/clinical/corpus/` paketi eklendi: schema (CorpusEntry + JSONL + PII tarama), şablonlar, deterministik üretici (546 senaryo) ve 35 vakalık golden set. `tests/test_corpus.py` (13 test). Tüm paket 168 test geçti, regresyon yok. Odak İP-1.3'e taşındı.
- 2026-06-22: İP-1.3 YAPILDI. `app/clinical/normalizer.py` eklendi: 35 kural argo → kanonik terim genişletme motoru + `triage()` sarmalayıcı. `tests/test_normalizer.py` (45 test). Odak İP-1.4'e taşındı.
- 2026-06-22: İP-1.4 YAPILDI. Skorlama tabanlı `match_specialty` + genişletilmiş normalizer/ontoloji → sentetik korpusta %74→%99.3. `app/clinical/evaluate.py` değerlendirme harness'ı eklendi. NOT: çalışma ağacındaki `app/models/entities.py` bozuk (eksik import'lar + kayıp `OutreachDraft` sınıfı) — İP-1.4 dışı, ayrı blocker; servis tarafı testleri (`test_clinical.py`) bu yüzden koşmuyor. Odak İP-1.5'e taşındı.
- 2026-06-23: `entities.py` blocker'ı çözüldü (commit `c368d31`); `test_clinical.py` tekrar koşuyor. Alembic çift-head bug'ı (merge yan etkisi) `0009_merge_heads` ile giderildi. Reverted `codex/clinical-receptionist-foundation` branch'inden 21 faydalı test + 3 doküman kurtarıldı; kurtarılan test `voice.py`'de gerçek bir `NameError` (500) bug'ı yakaladı, düzeltildi.
- 2026-06-29: Dış kod incelemesi (`cognivault_review.md`) 3 paralel ajanla gerçek kodla doğrulandı. 16 doğrulanmış bulgu "Üretim Sertleştirme Backlog'u" (R-1…R-16) olarak eklendi. Raporun 5 yanlış/abartılı iddiası ayıklandı (webhook imzası VAR; FK indeksleri ~%64 mevcut; mobil disclaimer butonların üstünde; injection yalnız tag alt-kuralında ölü; AsyncStorage mevcut). R-1 ve R-6 İP-2.7 ile birleştirilecek.
- 2026-06-23: İP-1.5 YAPILDI. Saf-Python isotonic kalibrasyon (`calibration.py`) + rapor/artefakt üreticisi (`calibrate.py`). Sentetik TEST ECE **0.0107 < 0,05**. `triage()` kalibre `confidence` alanı kazandı (İP-1.6 köprüsü). `ontology.rank_specialties()` eklendi. `tests/test_calibration.py` (13 test). Backend 526 passed, 1 skipped. Odak İP-1.6'ya taşındı.
