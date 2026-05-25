# Gemini Deep Research Addendum

Bu ek, CogniVault Clinical araştırmasının ürünle doğrudan uygulanabilir hale gelmesi için Gemini promptuna eklenmelidir. Amaç yalnızca pazar araştırması almak değil; KVKK, klinik operasyon, yerel AI mimarisi ve yazılım backlog'u açısından doğrulanabilir kararlar çıkarmaktır.

## Ek Araştırma Talimatları

1. Her iddiayı kaynak sınıfıyla etiketle:
   - `official`: KVKK, Resmi Gazete, Sağlık Bakanlığı, TTB, SGK, Meta/Twilio resmi dokümanı.
   - `academic`: hakemli makale, üniversite yayını, PubMed/PMC.
   - `vendor`: rakip ürün sayfası, case study, blog.
   - `inference`: kaynaklardan çıkarım, doğrudan mevzuat hükmü değildir.

2. Conversion, drop-off, doğruluk ve benchmark yüzdeleri için kesin kaynak yoksa rakam verme. “Saha varsayımı” veya “ürün hedefi” olarak işaretle.

3. Sağlıkta fiyat, kampanya, indirim, muayenesiz yönlendirme ve reklam iddialarını özellikle resmi kaynaklarla doğrula. Bu bölümde hukuki yorum ile ürün stratejisini ayrı yaz.

4. KVKK analizinde şu ayrımı zorunlu yap:
   - kişisel veri
   - özel nitelikli kişisel veri
   - sağlık verisi
   - ses kaydı
   - biyometrik veri olup olmadığına dair kesin hüküm / tartışmalı yorum
   - yurt dışına aktarım
   - açık rıza, aydınlatma, veri minimizasyonu ve hizmet şartına bağlama riski

5. WhatsApp/Meta Cloud API için ayrıca değerlendir:
   - hangi veri Meta altyapısına gider
   - sağlık verisi yazdırılmadan randevu alma mümkün mü
   - açık rıza reddinde alternatif yerel kanal nasıl sunulur
   - 24 saat müşteri hizmetleri penceresi ve template mesaj gereksinimi

6. Yerel AI mimarisi için kabul kriterleri üret:
   - LLM: Qwen2.5-7B-Instruct veya eşdeğeri yerel model
   - STT: faster-whisper large-v3-turbo
   - TTS: Coqui XTTS-v2 / F5-TTS lisans uygunluğu kontrolü
   - VAD: silero-vad
   - tüm sağlık verisi işleme Türkiye içi veri merkezinde
   - harici API kullanımında açık rıza, sözleşme, log ve veri sınıflandırma şartları

7. Akışları bizim enum ve state modelimize map et:
   - intent: `book_appointment`, `reschedule_appointment`, `cancel_appointment`, `ask_price`, `ask_insurance`, `ask_location`, `ask_working_hours`, `medical_emergency`, `general_question`, `unknown`
   - status: `active`, `waiting_human`, `appointment_pending`, `closed`
   - her akışta hangi tool çağrılır, hangi tool çağrılmadan yanıt verilemez, hangi durumda `waiting_human` olur

8. Hallucination önleme için “LLM asla tek başına karar veremez” bariyerlerini yaz:
   - randevu slotu sadece takvim API yanıtından gelir
   - fiyat sadece izinli idari metin / muayene yönlendirmesiyle cevaplanır
   - ilaç, tanı, doz, tedavi önerisi verilmez
   - acil semptomlarda normal konuşma akışı bypass edilir
   - prompt injection mesajları klinik idari yardım dışına çıkamaz

9. Klinik panel ve doktor ekranı için somut modül listesi çıkar:
   - canlı inbox
   - AI shadow review
   - doktor onayı gerektiren mesajlar
   - acil alarm paneli
   - randevu slot simülatörü
   - hasta timeline'ı
   - KVKK consent audit trail
   - veri sınıfı ve kanal risk göstergeleri
   - SLA ve bekleyen devralma kuyruğu
   - kalite/eval panosu

10. Test edilebilir golden dataset öner:
    - en az 100 Türkçe hasta mesajı
    - yaşlı hasta, aksan, yazım hatası, argo, kısa ses kaydı transkripti, multi-intent, öfkeli hasta, çocuk hasta, acil semptom, fiyat ısrarı, sigorta sorgusu, prompt injection, slot dolu senaryosu
    - her örnekte beklenen intent, status, tool call, güven skoru, hasta yanıtı ve kabul kriteri

11. Patent hazırlığı için “teknik yenilik” eksenlerini ayır:
    - yerel veri egemenliği ve KVKK audit token mimarisi
    - sağlık konuşmalarında deterministik tool-gated LLM akışı
    - çok kanallı consent-aware state machine
    - acil semptom bypass ve çoklu alarm sistemi
    - klinik personeli shadow review geri-besleme döngüsü
    - randevu slot doğrulama ve hallucinated availability sıfırlama yaklaşımı

12. Final çıktıda doğrudan geliştirilebilir backlog ver:
    - backend endpoint/model değişiklikleri
    - frontend klinik panel ve doktor ekranı değişiklikleri
    - veri tabanı tabloları
    - audit/event log alanları
    - eval testleri
    - demo senaryoları
    - “slotlar doluysa nasıl görünür” akışı

## Beklenen Ek Çıktı Formatı

Her bölüm sonunda şu blok bulunmalı:

```text
Ürün Kararı:
Uygulama Etkisi:
Gerekli Backend Değişikliği:
Gerekli Frontend Değişikliği:
Test / Kabul Kriteri:
Kaynak Güvenilirliği:
```

## Özellikle Kaçınılacaklar

- Ürünü rakip isimleriyle konumlandırma. Karşılaştırma yapılabilir, ancak final öneriler CogniVault Clinical'a özgü olmalı.
- Kaynaksız yüzde ve “sektör standardı” iddiası.
- Muayenesiz tanı, tedavi veya ilaç önerisi.
- WhatsApp üzerinden gereksiz sağlık verisi toplama.
- Rıza vermeyen hastayı tamamen hizmet dışı bırakma.
- LLM'in takvim, fiyat, sigorta veya acil durum konularında tool çağrısı olmadan kesin karar vermesi.
