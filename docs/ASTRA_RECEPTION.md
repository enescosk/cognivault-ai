# Astra ve görüşme bağlamı

Klinik resepsiyon yoluna ayrı Astra sağlayıcısı eklendi. Genel kurumsal chat modeli
ve yerel ses modelleri değişmedi. Astra yalnızca cevap taslağı üretir; takvim,
randevu onayı ve mesaj gönderimi backend servislerinde kalır.

## Çalışma biçimi

- Selam, teşekkür, kimlik sorusu ve bağlantı kontrolü yerelde cevaplanır.
- Aynı görüşmede yeniden selam verildiğinde asistan kendini tekrar tanıtmaz.
- Son altı hasta/asistan mesajı aynı klinik ve görüşmeden alınır. Her mesaj
  kimlik tanımlayıcıları maskelendikten sonra en fazla 900 karakterle modele gider.
- Kısa devam cümleleri önceki talep türünü korur; model son düzeltmeyi dikkate alır.
- Acil durumlarda model beklenmez. `use_ai=False` semptom yolunda da uygulanır.
- Hasta rızası en son kayıt üzerinden değerlendirilir; eski bir onay yeni ret
  veya geri çekmeyi geçersiz kılamaz. Ses yolu da aynı sorguyu kullanır.
- Model cevabı şema, mevcut niyet/insan onayı kontrolleri ve doğrulanmamış
  işlem iddiaları için denetlenir. Metin denetimi ek savunmadır; klinik doğruluk
  veya tüm halüsinasyonların engellenmesi garantisi değildir.

## Yapılandırma

```dotenv
CLINICAL_LLM_PROVIDER=astra
CLINICAL_ASTRA_MODEL=gpt-6-astra
CLINICAL_ASTRA_REASONING=low
CLINICAL_ASTRA_TIMEOUT=15
CLINICAL_ASTRA_MAX_OUTPUT_TOKENS=1800
```

Anahtar mevcut `OPENAI_API_KEY` alanından okunur. Gerçek hasta mesajının Astra'ya
gidebilmesi için ayrıca `CLINICAL_AI_ENABLED`, `CLINICAL_EXTERNAL_AI_ALLOWED`,
kliniğin `allow_cross_border_processors` politikası ve o hasta/görüşmenin aktif
`CROSS_BORDER_TRANSFER` rızası gerekir. Kurulum bu izinleri kendiliğinden açmaz.
Hasta sayfasının rehberli randevu endpoint'i `use_ai=False` kullanmaya devam eder.
Bu entegrasyon serbest klinik mesajlarını işleyen `ingest_clinical_message` yolundadır.

`CLINICAL_LLM_PROVIDER=local` yerel sağlayıcıyı seçer; `auto` eski sağlayıcı
önceliğini korur. Astra anahtarı yoksa yerel sağlayıcı seçilir. Astra yanıtı
başarısız/eksikse kural cevabı kullanılır; başka bulut sağlayıcısına gizli tekrar
yapılmaz. `/api/ai/capabilities` klinik model tercihini ve izin gereksinimlerini gösterir.

## API ve maliyet

Responses API, strict JSON şeması, `store=False`, düşük reasoning, 15 saniye
timeout ve sıfır otomatik yeniden deneme kullanılır. `store=False` sağlayıcının
tüm veri saklama politikalarının kapandığı anlamına gelmez. Rıza kapıları korunur.
Token maliyeti mevcut kullanım kayıtlarına yazılır. Astra için 1M giriş/çıkış
tokenı başına 10/50 USD temel tahmin kullanılır; cache indirimleri hesaplanmaz.
Bu yolun sınırlı bağlamı büyük bağlam fiyat eşiğine ulaşmaz.

## Doğrulama

`backend/tests/test_astra_reception.py`: sağlayıcı sözleşmesi, hatalı/eksik çıktı,
timeout, aktarım kapıları, bağlam maskeleme, sosyal cevaplar, acil durum,
işlem yapılmış gibi konuşmanın reddi, görüşme ayrımı ve rıza geri çekme testleri.
2026-09-14'te gerçek API'ye yalnızca sentetik bir klinik sorusu gönderildi ve
`openai_astra` yapılandırılmış cevabı alındı. Gerçek hasta, SMS veya arama kullanılmadı.
Bu bir bağlantı doğrulamasıdır; gerçek hasta kalitesi veya gecikme benchmark'ı değildir.

Kaynaklar: [model](https://developers.openai.com/api/docs/models/gpt-6-astra),
[API geçişi](https://developers.openai.com/api/docs/guides/latest-model),
[yapılandırılmış çıktı](https://developers.openai.com/api/docs/guides/structured-outputs).
