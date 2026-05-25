# KVKK Hukuki Hazırlık Paketi

Bu klasör, CogniVault Clinical (sesli ve mesajlaşma tabanlı klinik AI asistanı) için **KVKK avukat görüşmesi öncesi** hazırlanmış teknik-hukuki brief'i içerir. Amaç: avukata gidip "neyi konuşacağız" diye boş başlamamak; sistemin gerçek veri akışını, mevcut korumaları ve risk noktalarını net olarak ortaya koymak.

## Bu pakette ne var?

| Doküman | İçerik | Avukatla nasıl kullanılır |
|---|---|---|
| [data-flow-map.md](data-flow-map.md) | Sistemin uçtan uca veri akışı (kanal → endpoint → işleme → depolama → 3. parti) | "Verimiz fiziksel olarak nereye gidiyor" sorusunun cevabı |
| [data-inventory.md](data-inventory.md) | İşlenen kişisel veri envanteri, kategoriler, hukuki sebep, saklama süresi | VERBİS kaydı için temel; m.4-6-9 analizi |
| [legal-consultation-brief.md](legal-consultation-brief.md) | Sistem 1 sayfa özet + avukata sorulacak 12 spesifik soru | Görüşme gündemi |
| [risk-register.md](risk-register.md) | Mühendislik tarafından tahmin edilen 14 risk, olasılık × etki | "Hangi risk gerçekten ciddi?" diye triage |
| [../ai-stack-decision.md](../ai-stack-decision.md) | LLM / STT / TTS teknoloji seçimi ve gerekçesi | "Hangi modelle çalışacaksınız" sorusuna ispatlı cevap |

## Bağlam — proje ne yapıyor

CogniVault Clinical, hastalardan **WhatsApp / telefon / web chat** üzerinden gelen randevu ve şikayet mesajlarını yapay zeka ile işleyip:
- Niyetini sınıflandırır (randevu, fiyat, sigorta, şikayet, acil semptom)
- Uygun cevabı üretir (otomatik veya doktor onaylı)
- Slot atar veya doktor inbox'a düşürür
- Konuşmayı kayıt altına alır

Bu süreçte işlenen veri **KVKK Madde 6 kapsamında özel nitelikli kişisel veri** (sağlık verisi) içerir.

## Mevcut durum (kod tarafından)

- Veri tabanı: PostgreSQL — lokal Docker'da çalışıyor ([backend/docker-compose.yml](../../docker-compose.yml))
- AI sağlayıcılar: **şu anda OpenAI (Whisper-1 STT, TTS, GPT)** — yurt dışı aktarım var
- Compliance flag: [clinical_compliance_service.py:80](../../backend/app/services/clinical_compliance_service.py) `data_residency_mode = "tr_local_first"` — flag konuldu ama gerçek lokal stack bağlı değil
- Son commit (`91a2ff4`): "Lock clinical flow to local-first mode for KVKK compliance" — hazırlık başladı

## Sonraki adım

Avukat görüşmesi → bu pakette çıkacak hukuki yönlendirmelere göre engineering fazları (Faz 1-7) başlatılır. Detay: [../../docs](..) altındaki master roadmap.
