# Randevu Hatırlatma — kurulum ve şablon

Randevudan **24 saat** ve **2 saat** önce hastaya hatırlatma gider:

> Merhaba Ayşe, Demo Klinik yarınki randevunuzu hatırlatırız: 25 Eylül Perşembe,
> 10:30 (Genel Diş Hekimliği). Gelebilecek misiniz?
> **[Geleceğim] [İptal] [Ertele]**

| Hasta seçer | Sistem yapar |
|---|---|
| **Geleceğim** | Katılım teyidi kaydedilir (`patient_attendance`). Kliniğin onay durumu değişmez — hekim ataması ayrı karardır. |
| **İptal** | Randevu iptal, **takvim slotu serbest** — saat başka hastaya önerilebilir. |
| **Ertele** | Randevu **korunur**, konuşma ekibe düşer (`reschedule_requested`). Yeni saat bulunmadan iptal edilmez. |

Hasta düğmeye basmak yerine kısa yazarsa da anlaşılır ("gelemeyeceğim",
"iptal", "ertele"). Uzun mesajlar ("iptal edersem ücret alınır mı?") randevuyu
iptal etmez; normal akışa (yapay zekâ + hekim) gider.

Kod: `backend/app/services/clinic_reminders.py`.

## Kime gider, kime gitmez

- ✅ Klinik tarafından onaylanmış randevu.
- ✅ Hastanın telefon ya da web üzerinden kendisinin seçtiği randevu.
- ✅ Operatörün hastayla konuşup panelden açtığı randevu.
- ❌ **Yapay zekânın hekim ekranı için hazırladığı taslak.** Saati olsa bile
  hasta o saati kabul etmedi; "randevunuzu hatırlatırız" demek yanlış olur.
- ❌ İptal edilmiş, geçmiş randevu. Saati değişen randevunun eski planı silinir.

Worker bir süre durmuşsa aynı randevu için iki hatırlatma birden gitmez; yalnız
en yenisi gider.

## Kanal

1. Hastanın **WhatsApp** konuşması varsa WhatsApp. Hatırlatma çoğunlukla 24 saat
   penceresinin dışında olduğu için **onaylı şablon** gerekir (aşağıda).
2. Şablon yoksa, hastanın WhatsApp'ı yoksa ya da mesaj gidemeyeceği belliyse
   **SMS** (Netgsm). SMS'te düğme olmadığı için metin "İptal ya da değişiklik için
   kliniğimizi arayın" diye biter.

Başarısız hatırlatma hekim gelen kutusunu doldurmaz; SMS'e düşer.

## Onaya gönderilecek şablon

**Meta** — ad: `randevu_hatirlatma` · kategori: UTILITY · dil: tr

> Merhaba {{1}}, {{2}} randevunuzu hatırlatırız: {{3}}. Gelebilecek misiniz?

Hızlı yanıt düğmeleri (bu sırayla): `Geleceğim` · `İptal` · `Ertele`

Örnek değerler: `{{1}}` Ayşe · `{{2}}` Demo Klinik · `{{3}}` 25 Eylül Perşembe, 10:30

Düğme kimlikleri her gönderimde randevuya özgü verilir (`r:cancel:<randevu>`).

**Twilio** — Content API'de aynı gövde ve üç hızlı yanıt. Twilio'da düğme
kimlikleri şablonda sabittir; şunları kullanın: `r:confirm` · `r:cancel` ·
`r:reschedule`. Sistem bu durumda hastanın son hatırlatılan randevusunu bulur.

## Açmak için

```
CLINIC_REMINDERS_ENABLED=true
CLINIC_WHATSAPP_SEND_ENABLED=true            # WhatsApp'tan gitmesi için
CLINIC_WA_TEMPLATE_REMINDER=randevu_hatirlatma   # Meta
CLINIC_TWILIO_REMINDER_CONTENT_SID=HX...         # Twilio
SMS_PROVIDER=netgsm                          # SMS yedeği gerçekten gitsin
```

Outbox worker çalışmalı (`python -m app.workers.outbox_worker`): planlama,
gönderim ve WhatsApp teslimi onun turunda yapılır.

## Bilinçli olarak yapılmayanlar

- **Gelmeme riskine göre seçim yok.** `learning/noshow` modeli sentetik veriyle
  eğitildi; gerçek hastaya kimin mesaj alacağına onunla karar verilmez.
  Hatırlatma herkese gider. Gerçek pilot verisi birikince yeniden eğitilip
  (ör. yüksek riskliye ek hatırlatma) bağlanabilir.
- **Ertele'de otomatik yeni saat önerilmiyor.** Ekip döner; WhatsApp'ta düğmeyle
  saat seçimi K.D'de.
