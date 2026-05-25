# Risk Register (Mühendislik Perspektifi)

Mühendislik tarafından tespit edilen, hukuki danışmanlık ile triage edilmesi gereken **14 risk**. Her risk için: olasılık (1-5), etki (1-5), KVKK referansı, mevcut durum, önerilen önlem.

> Skor = Olasılık × Etki. **15 ve üzeri** kritik (avukat görüşmesinde mutlaka konuşulmalı), 8-14 yüksek, 4-7 orta, <4 düşük.

| # | Risk | Olasılık | Etki | Skor | KVKK | Mevcut durum | Önerilen önlem |
|---|---|---|---|---|---|---|---|
| 1 | Sağlık verisinin OpenAI üzerinden ABD'ye aktarılması | 5 | 5 | **25 🔴** | m.6, m.9 | Aktif, her konuşmada oluyor | Faz 1-2: local stack zorunlu |
| 2 | Açık rıza alınmadan özel nitelikli veri işleme | 5 | 5 | **25 🔴** | m.6/2 | Hiçbir rıza akışı yok | Faz 3: IVR + dijital onay |
| 3 | VERBİS kaydının yapılmamış olması | 5 | 4 | **20 🔴** | m.16 | Yapılmadı | Avukat + danışmanlık ile başvuru |
| 4 | Aydınlatma metninin bulunmaması | 5 | 4 | **20 🔴** | m.10 | Yok | Avukat hazırlayacak |
| 5 | Veri sahibi haklarını kullanma endpoint'lerinin olmaması | 5 | 3 | **15 🔴** | m.11, m.13 | Yok | Faz 4: erasure/export endpoint |
| 6 | Saklama süresi belirlenmemiş, sınırsız depolama | 5 | 3 | **15 🔴** | m.4/d, m.7 | Hiç silme yok | Faz 4: retention job |
| 7 | Audit log eksik (kim hangi hasta verisini gördü) | 4 | 3 | **12 🟡** | m.12 | Tablo var ama klinik veri erişimi loglanmıyor | Faz 4: access audit middleware |
| 8 | Veri tabanında at-rest şifreleme olmaması | 3 | 4 | **12 🟡** | m.12 (uygun güvenlik) | Postgres default, encryption yok | Faz 5: pgcrypto + LUKS |
| 9 | Klinikle imzalı DPA (Veri İşleyen Sözleşmesi) olmaması | 4 | 3 | **12 🟡** | m.12/5 | Yok | Avukat şablonu üretecek |
| 10 | RBAC'ın klinik bazlı izolasyon garantisinin test edilmemiş olması | 3 | 4 | **12 🟡** | m.12 | Var ama sızdırma testi yapılmadı | Faz 5: penetrasyon testi |
| 11 | Twilio (ABD) üzerinden ses transit | 4 | 3 | **12 🟡** | m.9 | Aktif (varsayılan) | Yerli VoIP alternatifi araştırması |
| 12 | PII'nin loglarda görünmesi (Sentry, stdout, dosya) | 4 | 3 | **12 🟡** | m.12 | Redactor yok | Faz 4: log redaction middleware |
| 13 | Backup'ların şifresiz veya yurt dışı bulutlarda olması | 3 | 3 | **9 🟡** | m.12, m.9 | Backup stratejisi tanımlı değil | Faz 5: TR'de şifreli backup |
| 14 | Acil semptom tespitinde sistemin yanlış pozitif/negatif vermesi (tıbbi sorumluluk) | 3 | 5 | **15 🔴** | KVKK dışı — tıbbi mevzuat | Sınırlı eval | Golden eval suite + doktor-onay-gate |

---

## Kritik 6 — avukat görüşmesinde ilk konuşulacaklar

1. **Risk #1** — OpenAI yurt dışı aktarımı (pilot dönem için ne yapacağız?)
2. **Risk #2** — Açık rıza akışı (sözlü onay yeterli mi, yazılı şart mı?)
3. **Risk #3** — VERBİS kaydı (deadline ne, danışmanlık şart mı?)
4. **Risk #4** — Aydınlatma metni (avukat hazırlayacak — biz teknik kapsamı vereceğiz)
5. **Risk #5** — Veri sahibi hakları endpoint'leri (öncelik sırası ne olmalı?)
6. **Risk #14** — Tıbbi sorumluluk (avukat KVKK + tıbbi sorumluluk birleşim noktasını netleştirsin)

---

## Pilot dönem geçici azaltma planı

Avukat görüşmesi yapılana ve Faz 1-2 tamamlanana kadar (~3-4 hafta) **canlı hasta verisi sisteme alınmamalı**. Pilot dönemde:

- Sadece **sentetik test verisi** veya **eski kayıtların anonimleştirilmiş kopyası** kullanılmalı
- Demolar **rol oynama** (klinik personeli kendisi hasta gibi yazar) ile yapılmalı
- "Erken erişim katılımcısı" sıfatıyla klinik personeliyle ayrı NDA + pilot sözleşmesi imzalanmalı
- OpenAI çağrıları **devre dışı** veya **demo modu** flag'i ile sınırlandırılmalı

Bu, KVKK Kurulu'na "iyi niyetli ihlal" değil "uyum öncesi pilot" olarak gösterilebilir bir konum sağlar.
