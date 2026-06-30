# İP-6.4 + İP-6.5 — Patent Novelty Araştırması ve İstem Taslakları

> **DURUM: TASLAK — hukuki tavsiye değildir.** Bu belge mühendislik tarafının patent
> vekiline girdi hazırlamasıdır. Başvuru öncesi **patent vekili** tarafından resmî
> novelty ve buluş-basamağı (inventive step) analizi TÜRKPATENT EPATS / Espacenet /
> Google Patents üzerinde yürütülmelidir. İstemler taslaktır; nihai kapsam vekille
> belirlenir.
> İlgili: mevcut [dental-ai-patent-dossier.md](../dental-ai-patent-dossier.md) (EN).

---

## Bölüm A — İP-6.4: Novelty / Prior-Art Araştırması

### A.1 Korunmak istenen çekirdek (buluşun özü)
Sistemin ayırt edici teknik fikri, modeli **daha yetenekli** kılmak değil, olasılıksal
dil/ses modelini **deterministik bir ön-çıktı kapısıyla yapısal olarak sınırlamaktır**.
Bu, yazılımı tıbbi cihaz tarafından (SaMD) uzak tutarken KVKK özel-nitelikli veri
rejimi altında çalışmasını sağlar. Üç ayrılabilir yenilik ekseni:

1. **Deterministik klinik-yönetişim & veri-yerleşim zarfı** — her aday model çıktısı,
   otomatik gönderimden önce: veri-sınıfı tespiti → teşhis/tedavi bloklama →
   acil/sigorta/kimlik/düşük-güven insan-yükseltme → sınır-ötesi engelleme →
   PII maskeleme → maskeli denetim izi.
2. **Kalibre + çekimser (selective/conformal) Türkçe diş triyajı** — güveni gerçek
   doğrulukla eşitleyen kalibrasyon (ECE) + güven düşükse/kanıt tutarsızsa kararı
   otomatik insana yükselten çekimserlik + acil-recall ≈ %100 garantisi.
3. **Hekim-onay paketi & mahremiyet-kapılı öğrenme döngüsü** — hekim kararından
   (onay/düzeltme/ret) ham hasta metni taşımadan, redaksiyon-onayı verilmeden
   eğitime girmeyen mahremiyet-kapılı etiket üretimi.

### A.2 Arama stratejisi (vekilin EPATS/Espacenet'te yürüteceği)
**Sınıflandırma (CPC/IPC) başlangıç noktaları:**
- `G16H 80/00` (sağlık bilişimi / iletişim), `G16H 50/20` (klinik karar destek),
  `G16H 10/60` (hasta kayıtları), `G06N 7/01`/`G06N 20/00` (olasılıksal/ML),
  `G10L 15/00` (konuşma tanıma), `G06F 21/62` (veri erişim/gizlilik).

**Anahtar terim kümeleri (EN — uluslararası arama için):**
- Zarf: `deterministic guardrail`, `policy gate LLM output`, `pre-send compliance gate`,
  `cross-border data residency block`, `PII redaction before processor`, `audit trail masked`.
- Triyaj: `calibrated confidence triage`, `selective prediction abstention medical`,
  `conformal risk control referral`, `expected calibration error routing`,
  `Turkish dental symptom classification`.
- Öğrenme: `human-in-the-loop label privacy gate`, `RLHF clinical redaction`,
  `shadow mode approval training signal`.

**TR terimleri (TÜRKPATENT için):** "deterministik yönetişim kapısı", "kalibre güven
triyaj", "çekimser tahmin sağlık", "sınır-ötesi veri engelleme", "hekim onay döngüsü".

### A.3 Bilinen genel sanattan farklılaşma (mühendislik gerekçesi)
| Bilinen genel yaklaşım | Bizim farkımız (iddia edilen yenilik) |
|------------------------|----------------------------------------|
| Bulut LLM tıbbi/sağlık asistanları (ör. genel sohbet botları) | Özel-nitelikli veriyi sınır-ötesine taşımaz; **yapısal** local-first + sınır-ötesi engel |
| Daha iyi teşhis için model yeteneğini artırma | Tersine: modeli **kasıtlı sınırlayan negatif-yetenek** katmanı → non-SaMD konumu |
| Eşik-tabanlı basit "düşük güven → insana" kuralı | **Kalibre** güven (ECE<0,05) + **konformal risk-kontrollü** çekimserlik + acil-recall garantisi |
| İnsan geri-bildirimini doğrudan eğitime alma | **Mahremiyet-kapılı**: redaksiyon-onayı olmadan ham metin eğitime asla girmez |
| Genel kalibrasyon (görüntü/metin sınıflandırma) | Klinik triyajda **aciliyet kaçırma ≈ 0** kısıtıyla birleşik kalibrasyon+çekimserlik |

> **Dürüstlük notu:** Bu tablo mühendislik argümanıdır; resmî novelty, vekilin arama
> sonuçlarına göre teyit edilmelidir. "Yenilik bulundu" ifadesi henüz kullanılamaz.

### A.4 Buluş-basamağı (inventive step) argümanı
Sektörün genel motivasyonu modeli daha yetenekli kılmaktır; bunun bedeli yazılımın
tıbbi cihaza dönüşmesidir (AB MDR Class IIa+, AB AI Act yüksek-risk, TR TİTCK). Bizim
çözümümüz **bu motivasyonun tersine** giderek modeli sınırlandırır ve böylece hem
hukuki sınıfı (non-SaMD) hem KVKK uyumunu **teknik bir mimariyle** elde eder — bu
"teknik önyargıyı aşma" (overcoming a technical prejudice) argümanına uygundur.

---

## Bölüm B — İP-6.5: Bağımsız + Bağımlı İstem Taslakları

> Taslak; numaralandırma ve kapsam vekille kesinleşir. Üç bağımsız istem, A.1'deki üç
> yenilik eksenine karşılık gelir.

### Bağımsız İstem 1 — Deterministik Klinik-Yönetişim Zarfı (yöntem)
**1.** Bir klinik iletişim sisteminde, olasılıksal bir dil veya ses modelinin ürettiği
aday yanıtın otomatik iletilmesini denetlemeye yönelik bir **bilgisayarla uygulanan
yöntem** olup; şunları içerir:
- (a) aday yanıt ve ilişkili girdi için bir **veri-sınıfı** belirleme (en az: iletişim,
  özel-nitelikli sağlık, finansal/sigorta, ulusal kimlik);
- (b) aday yanıtı, gönderimden önce **deterministik bir kapı** dizisinden geçirme; kapı:
  (i) teşhis/tedavi talimatını engeller, (ii) acil/sigorta/kimlik/düşük-güven olaylarını
  insana yükseltir, (iii) açık rıza ve sözleşme yoksa sınır-ötesi işleyiciyi engeller,
  (iv) kişisel veriyi her işleyiciden önce maskeler;
- (c) kapı kararını ve maskeli önizlemeyi **denetlenebilir bir ize** yazma;
- (d) yalnızca tüm kapı koşulları sağlandığında otomatik gönderime izin verme;
karakterize edici özelliği, kapının **ifadeye/duruma bağlı olmayan, çıktıların her biri
için yapısal olarak çalışan** deterministik bir ön-çıktı katmanı olmasıdır.

### Bağımsız İstem 2 — Kalibre & Çekimser Triyaj Yönlendiricisi (sistem)
**2.** Bir hasta iletisini bir uzmanlık branşına ve aciliyet seviyesine yönlendiren bir
**sistem** olup; şunları içerir: bir normalleştirme modülü (günlük/argo Türkçe ifadeyi
kanonik terimlere genişletir); bir skorlama yönlendiricisi; ve bir **kalibrasyon-çekimserlik
modülü** olup şu şekilde yapılandırılmıştır:
- (a) yönlendirme güvenini, beklenen kalibrasyon hatası bir eşiğin altında olacak
  biçimde **kalibre** eder;
- (b) kalibre güven bir eşiğin altındaysa veya en yüksek iki branş skoru ayırt
  edilemiyorsa kararı **çekimser** kılıp insana yükseltir;
- (c) aciliyet sınıfı için, kabul edilen tahminlerde **acil vaka kaçırma oranını
  sıfıra yakın** tutan yüksek-recall bir tespit uygular;
karakterize edici özelliği, kalibrasyon ve çekimserliğin, aciliyet-recall kısıtı
altında **birlikte** bir risk-kontrollü kabul eşiği üretmesidir.

### Bağımsız İstem 3 — Hekim-Onay Paketi & Mahremiyet-Kapılı Öğrenme (yöntem)
**3.** Bir gölge-mod (shadow mode) hekim onay akışından model iyileştirme sinyali
üretmeye yönelik bir **bilgisayarla uygulanan yöntem** olup; şunları içerir:
- (a) aday yanıtı bir hekime sunup karar (onay/düzeltme/ret) alma;
- (b) kararı, **ham hasta metnini kopyalamadan**, yalnızca bir referans, niyet etiketi ve
  karar türü içeren mahremiyet-güvenli bir kayda dönüştürme;
- (c) kaydı varsayılan olarak **redaksiyon-bekleyen** durumda tutma ve yalnızca açık bir
  redaksiyon-onayı verildikten sonra eğitime uygun kılma;
- (d) onayları kullanarak, **kapı kurallarını gevşetmeden** (acil daima insana; güvenlik
  tabanı altına inmeden) otomatik-yanıt güven eşiğini veri-temelli kalibre etme;
karakterize edici özelliği, öğrenme sinyalinin **mahremiyet-kapısı** ve **kapı-değişmezleri**
ile sınırlanmış olmasıdır.

### Bağımlı İstemler (taslak)
1. İstem 2'ye göre, argo Türkçe ifadelerin ("zonkluyor", "dolgu düştü", "diş eti kanıyor",
   "çenem kilitlendi", "implant kontrolü") kanonik branş terimlerine eşlendiği.
2. İstem 1'e göre, local-first dağıtım modunun sınır-ötesi işleyicileri varsayılan
   engellediği ve seçilen işleme modunu denetim izine yazdığı.
3. İstem 1'e göre, maskeli önizlemenin telefon, ulusal kimlik (nokta-ayraçlı varyant
   dâhil), e-posta ve kart-benzeri numaraları maskelediği.
4. İstem 2'ye göre, çekimserlik eşiğinin **konformal risk-kontrolü** ile, kabul edilen
   tahminlerde ampirik hata bir bütçenin altında kalacak şekilde belirlendiği.
5. İstem 3'e göre, otomatik-yanıt eşiği öğrenmesinin acil/sigorta niyetlerini havuzdan
   yapısal olarak dışladığı ve önerilen eşiğin bir güvenlik tabanının altına inemediği.
6. İstem 1–3'ten herhangi birine göre, PMS yazımının yalnızca branş, randevu slotu, rıza
   durumu ve hekim-inceleme durumu doğrulandıktan sonra yapıldığı.
7. İstem 2'ye göre, no-show riskinin bir saf-yerel modelle tahmin edilip slot önerisi ve
   proaktif geri-çağırma zamanlamasını (rıza + sessiz-saat + cooldown kapılarıyla)
   beslediği.

---

## Bölüm C — Vekile teslim paketi & sonraki adımlar
- [ ] Vekil EPATS/Espacenet/Google Patents'te A.2 stratejisiyle resmî novelty araması yürütür.
- [ ] Şekiller: zarf akış diyagramı, triyaj kalibrasyon/çekimserlik akışı, hekim-onay döngüsü
      (mevcut dossier "Figure List" bölümü temel alınır).
- [ ] Kanıt paketi: ECE/recall/AUC artefaktları (`backend/app/{clinical,learning}/data/*.json`),
      kapı-ihlali = 0 raporu (`app/governance/data/gate_report.json`).
- [ ] İstem kapsamı ve bağımlılık ağacı vekille kesinleştirilir (bu belge başlangıç taslağı).
- [ ] Buluş sahipliği/devir: kurucu ortaklar (Efe Kağan Ürersoy, Enes Coşkun).

> Bu belge yalnızca teknik girdidir; resmî novelty teyidi ve nihai istem dili vekilindir.
