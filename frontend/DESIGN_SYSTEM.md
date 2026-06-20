# CogniVault — Tasarım Sistemi & Claude ile Tasarım Akışı

> Bu dosya, CogniVault arayüzünün **tek tasarım kaynağıdır**. Claude (ve insan)
> herhangi bir ekran/komponent tasarlamadan **önce bunu okur**. Buradaki
> token'lar dışına çıkılmaz: yeni renk / font / radius **icat edilmez**,
> aşağıdakiler kullanılır. Token kaynağı: `frontend/src/styles/tokens.css`.

---

## 1) Nasıl çalışıyoruz (iterasyon döngüsü)

1. **Tarif et** — ekranı/akışı veya sadece ekran adını söyle ("operatör paneli",
   "triyaj sohbeti", "no-show kartı"). İstersen 1-2 referans/duygu da ver.
2. **Hızlı mockup** — Claude önce tek seferlik bir önizleme çıkarır (inline,
   bu token'larla). Yön doğru mu, 30 saniyede görürsün.
3. **Gerçek koda dök** — onayınca `frontend/src`'e React + `tokens.css` token'ları
   ile yazılır. Mevcut desen varsa onu kullanır, yoksa **küçük, yeniden
   kullanılabilir** bir primitive ekler.
4. **Canlı bak & rötuş** — `./scripts/run_demo.sh` ile çalıştırıp ekranda görür,
   kritik eder, düzeltiriz.

**Altın kural:** yeni bir ekran için 50 yeni sınıf icat etmeden önce — "bu desen
zaten var mı?" diye bak. Tutarlılık > yenilik.

---

## 2) Token'lar (`tokens.css`)

### Renk — koyu, premium, "klinik güven"
| Token | Değer | Kullanım |
|---|---|---|
| `--bg` / `--bg-2` | `#050810` / `#080c14` | sayfa zemini |
| `--surface` / `--surface-hover` / `--surface-active` | beyaz %3.2 / %5.5 / mavi %10 | kartlar, panel yüzeyleri (cam etkisi) |
| `--border` / `--border-hover` / `--border-active` | beyaz %7 / %14 / mavi %28 | ince çerçeveler |
| `--text` / `--text-2` / `--text-3` | `#e8edf5` / `#8a99b3` / `#4a5568` | birincil / ikincil / silik |
| `--accent` / `--accent-2` | `#63b3ed` / `#4299e1` | **seyrek ve anlamlı** vurgular, aktif durum |
| `--accent-glow` | mavi %18 | hafif ışıma (focus, aktif kart) |

**Semantic (yalnızca durum için):**
`--green #68d391` (onaylı/başarı) · `--amber #f6ad55` (bekleyen/uyarı) ·
`--red #fc8181` (iptal/acil) · `--purple #b794f4` (özel/AI). Her birinin `-bg`
(%10 dolgu) varyantı var → rozet/etiket zemini.

### Tipografi
- `--font-display` **Syne** (400-800) → başlıklar, kısa vurgu metni.
- `--font-body` **DM Sans** → tüm gövde metni.
- `--font-mono` **DM Mono** → **sayısal/teknik veri**: skorlar, randevu kodu, ID,
  süre, para. (Klinik veriye "kesinlik" hissi verir.)

### Şekil & derinlik
- Radius: `--radius-sm 8` · `--radius 14` · `--radius-lg 20` · `--radius-xl 28`px.
- Gölge: `--shadow-sm` · `--shadow` · `--shadow-lg` (koyu temada yumuşak, geniş).
- Geçiş: `--transition: 200ms cubic-bezier(.4,0,.2,1)` (tüm hover/aktif).

### Layout
- `--sidebar-w: 280px` · `--audit-w: 320px`.
- Zemin dokusu: çok hafif nokta deseni + sağ-üstte mavi radial glow (gözü
  yormayan atmosfer). Yeni tam-ekran yüzeylerde bu zemini koru.

---

## 3) Tasarım prensipleri

- **Sakin ve yoğun değil.** Bol boşluk, az çizgi, net hiyerarşi. Sağlık + KVKK
  ciddiyeti; "gösterişli SaaS" değil, "güvenilir klinik aracı".
- **Cam yüzey dili.** İçerik = `--surface` kart + `--border` ince çerçeve + ufak
  radius. Kutu içinde kutu yığma.
- **Accent kıt.** Mavi yalnızca aktif/önemli olanı işaret eder. Her şey maviyse
  hiçbir şey önemli değildir.
- **Durum = renk + şekil.** Renk körlüğü için renge ek olarak nokta/ikon/etiket
  kullan (ör. `status-dot` + metin).
- **Mono ile güven.** Sayısal klinik veri her zaman `--font-mono`.
- **Erişilebilirlik.** Metin kontrastı yeterli, görünür `:focus` halkası
  (`--accent-glow`), dokunma hedefi ≥ 40px, animasyonlar 200ms civarı ve kapatılabilir.

---

## 4) Mevcut bileşen desenleri (yeniden kullan)

Adlandırma BEM-vari: `bilesen-prefix-eleman` (ör. `apanel-card`, `adm-user-row`).
Sık desenler:
- **Panel** (`apanel-*`): başlık + alt başlık + liste + footer ipucu.
- **Kart satırı** (`*-row`, `*-card`): sol içerik / sağ meta + durum.
- **Rozet/etiket** (`*-badge`, `*-dept-badge`, `*-role-badge`): semantic `-bg` + metin.
- **Durum noktası** (`*-dot`): renkli küçük daire + etiket.
- **Sidebar** (280px) + **denetim paneli** (320px) sabit kolonlar.
- UI primitive'leri: `components/ui/` → `EmptyState`, `Skeleton`, `Toast`.

Stil sahipliği:

- `tokens.css`: koyu + açık tema token'ları.
- `ui.css`: ortak primitive ve governance bileşenleri.
- `patient.css`: public hasta deneyimi.
- `clinic-appointments.css`: klinik takvim/randevu ekranı.
- `global.css`: kalan shell ve eski ekranlar; yeni ekran stilleri buraya eklenmez.

---

## 5) Önerilen sonraki adımlar (opsiyonel, istersen kurarız)

- **`/styleguide` canlı sayfası** — tüm token + primitive galerisi tek ekranda.
  Yeni tasarımları aynı çalışan app içinde, tutarlı görerek yaparız.
- **Reusable primitive seti** — `components/ui/` altına `Card`, `Panel`, `Badge`,
  `Button`, `Field`, `StatusDot`. Yeni ekranlar sınıf icat etmek yerine bunları diz.
- Kalan eski ekranları kullanım gördükçe `global.css`'ten ekran dosyalarına taşı;
  import sırasını koru ve production CSS hash/boyutunu karşılaştır.

## 6) İki tema — bileşenler ikisinde de okunur olmalı (DİKKAT)

Uygulamada **iki tema** var:
- **Koyu (varsayılan):** `:root` token'ları — müşteri paneli, styleguide, hasta akışı.
- **Açık (klinik):** `.dashboard-shell.clinical-view` operatör panelini açık "medikal"
  temaya çevirir (zemin `#eaf3ef`, metin `#15231f`, accent teal `#1f6f68`) — ama
  aynı token isimlerini `.dashboard-shell.clinical-view` altında override eder.

Sonuç: token kullanan bileşenler iki temaya otomatik uyar. Yalnız token'la ifade
edilemeyen yarı saydam/tinted farklar için `.clinical-view <bileşen>` override'ı yazılır.
Ham renk tekrarına başlamadan önce computed değerin token'la aynı olup olmadığını kontrol et.
