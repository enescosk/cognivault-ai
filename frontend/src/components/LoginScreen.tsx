import { useState } from "react";

import { useT } from "../i18n";

function LocaleSwitcherChip() {
  const { locale, setLocale } = useT();
  return (
    <div className="locale-switcher" role="tablist" aria-label="Language">
      <button
        type="button"
        className={locale === "tr" ? "active" : ""}
        onClick={() => setLocale("tr")}
      >
        TR
      </button>
      <button
        type="button"
        className={locale === "en" ? "active" : ""}
        onClick={() => setLocale("en")}
      >
        EN
      </button>
    </div>
  );
}

type Props = {
  onLogin: (email: string, password: string) => Promise<void>;
  onRegister: (fullName: string, email: string, password: string) => Promise<void>;
};

const staffUsers = [
  {
    label: "Resepsiyon",
    email: "operator@cognivault.com",
    password: "demo123",
    description: "Canli hasta akisini, geri donusleri ve randevu adaylarini yonetir.",
  },
  {
    label: "Klinik Sahibi",
    email: "admin@cognivault.com",
    password: "demo123",
    description: "Doluluk, kacirilan temas, doktor onayi ve audit guvenligini izler.",
  },
];

const productPillars = [
  "AI resepsiyon",
  "Doctor approval",
  "Telefon + WhatsApp",
  "Randevu donusumu",
];

const previewMetrics = [
  { label: "Bugunku temas", value: "42", trend: "+18%" },
  { label: "Kacirilan arama", value: "3", trend: "-9" },
  { label: "Randevu adayi", value: "16", trend: "+6" },
  { label: "Doktor onayi", value: "5", trend: "riskli" },
];

const previewQueue = [
  { time: "09:20", patient: "Ayse K.", note: "Dis agrisi · acil oncelik", tone: "urgent" },
  { time: "10:05", patient: "Mert D.", note: "Implant kontrol · uygun slot", tone: "ok" },
  { time: "11:30", patient: "Zeynep A.", note: "Fiyat sorusu · WhatsApp", tone: "info" },
];

const proofPoints = [
  "Tani koymaz, riskli ifadeyi doktora tasir",
  "Hasta bilgisi tek kayitta toplanir",
  "Her AI aksiyonu audit trail'e duser",
];

export function LoginScreen({ onLogin, onRegister }: Props) {
  const [tab, setTab] = useState<"login" | "signup">("login");

  // Login state
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginError, setLoginError] = useState<string | null>(null);
  const [loginLoading, setLoginLoading] = useState(false);

  // Signup state
  const [signupName, setSignupName] = useState("");
  const [signupEmail, setSignupEmail] = useState("");
  const [signupPassword, setSignupPassword] = useState("");
  const [signupPassword2, setSignupPassword2] = useState("");
  const [signupError, setSignupError] = useState<string | null>(null);
  const [signupLoading, setSignupLoading] = useState(false);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoginLoading(true);
    setLoginError(null);
    try {
      await onLogin(loginEmail, loginPassword);
    } catch (err) {
      setLoginError(err instanceof Error ? err.message : "Giriş başarısız");
    } finally {
      setLoginLoading(false);
    }
  }

  async function handleSignup(e: React.FormEvent) {
    e.preventDefault();
    if (signupPassword !== signupPassword2) {
      setSignupError("Şifreler eşleşmiyor");
      return;
    }
    if (signupPassword.length < 6) {
      setSignupError("Şifre en az 6 karakter olmalı");
      return;
    }
    setSignupLoading(true);
    setSignupError(null);
    try {
      await onRegister(signupName, signupEmail, signupPassword);
    } catch (err) {
      setSignupError(err instanceof Error ? err.message : "Kayıt başarısız");
    } finally {
      setSignupLoading(false);
    }
  }

  function pickStaff(s: { email: string; password: string }) {
    setLoginEmail(s.email);
    setLoginPassword(s.password);
    setTab("login");
  }

  return (
    <div className="login-shell">
      {/* ── Sol panel ── */}
      <div className="brand-panel">
        <div className="brand-wordmark">
          <div className="brand-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2L2 7l10 5 10-5-10-5z"/>
              <path d="M2 17l10 5 10-5"/>
              <path d="M2 12l10 5 10-5"/>
            </svg>
          </div>
          <span>CogniVault Medical</span>
          <div style={{ marginLeft: "auto" }}><LocaleSwitcherChip /></div>
        </div>

        <div className="brand-hero">
          <div className="login-product-kicker">Butik klinikler ve dis hekimleri icin AI operasyon masasi</div>
          <h1>Hasta temasini <em>randevuya</em> ceviren klinik asistan.</h1>
          <p>
            Cognivault, klinigin telefon ve WhatsApp trafigini karsilar; hastayi guvenli sekilde
            siniflandirir, doktor ekranina ozet dusurur ve resepsiyona net aksiyon listesi verir.
          </p>

          <div className="login-pillar-row">
            {productPillars.map((pillar) => <span key={pillar}>{pillar}</span>)}
          </div>

          <div className="login-ops-preview" aria-label="Klinik operasyon ozeti">
            <div className="ops-preview-header">
              <div>
                <span>Live clinic desk</span>
                <strong>Acibadem Dental Studio</strong>
              </div>
              <b>09:42</b>
            </div>
            <div className="ops-preview-metrics">
              {previewMetrics.map((metric) => (
                <article key={metric.label}>
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                  <small>{metric.trend}</small>
                </article>
              ))}
            </div>
            <div className="ops-preview-body">
              <div className="ops-queue-card">
                <div className="ops-card-title">
                  <span>Hasta Akisi</span>
                  <b>3 oncelik</b>
                </div>
                {previewQueue.map((item) => (
                  <div className={`ops-queue-item ops-queue-item--${item.tone}`} key={`${item.time}-${item.patient}`}>
                    <time>{item.time}</time>
                    <div>
                      <strong>{item.patient}</strong>
                      <span>{item.note}</span>
                    </div>
                  </div>
                ))}
              </div>
              <div className="ops-ai-card">
                <div className="ops-card-title">
                  <span>AI Ozet</span>
                  <b>doktor onayi</b>
                </div>
                <p>
                  Hasta siddetli agri bildiriyor. Tani onerilmedi; acil durum belirtileri soruldu
                  ve doktor inbox'a oncelikli not dusuldu.
                </p>
                <div className="ops-ai-footer">
                  <span>Risk skoru</span>
                  <strong>82%</strong>
                </div>
              </div>
            </div>
          </div>

          <div className="login-proof-row">
            {proofPoints.map((point) => <span key={point}>{point}</span>)}
          </div>
        </div>

        <div className="login-compliance-row">
          <span>Shadow Mode</span>
          <span>Doctor Approval</span>
          <span>Audit Trail</span>
        </div>
      </div>

      {/* ── Sağ panel ── */}
      <div className="login-card">
        <div className="login-card-header">
          <div className="login-badge">
            <span className="login-badge-dot" />
            {tab === "login" ? "Klinik Girisi" : "Yeni Klinik"}
          </div>
          <h2>{tab === "login" ? "Medikal komuta merkezine gir" : "Klinik hesabı oluştur"}</h2>
          <p>
            {tab === "login"
              ? "Demo hesabini sec veya bilgileri elle gir."
              : "Butik klinik icin demo workspace hesabi olustur."}
          </p>
        </div>

        {tab === "login" ? (
          <div className="demo-account-stack">
            {staffUsers.map((u) => (
              <button
                key={u.email}
                className="demo-account-card"
                type="button"
                onClick={() => pickStaff(u)}
              >
                <span>{u.label}</span>
                <strong>{u.email}</strong>
                <small>{u.description}</small>
              </button>
            ))}
          </div>
        ) : (
          <button
            className="demo-account-card demo-account-card--new"
            type="button"
            onClick={() => setTab("signup")}
          >
            <span>Yeni klinik</span>
            <strong>Demo workspace olustur</strong>
            <small>Kayit sonrasi hasta tarafindan baslayan akislari test edebilirsin.</small>
          </button>
        )}

        {/* Tab bar */}
        <div className="lp-tab-bar">
          <button
            className={`lp-tab ${tab === "login" ? "lp-tab--active" : ""}`}
            type="button"
            onClick={() => setTab("login")}
          >
            Giriş Yap
          </button>
          <button
            className={`lp-tab ${tab === "signup" ? "lp-tab--active" : ""}`}
            type="button"
            onClick={() => setTab("signup")}
          >
            Kayıt Ol
          </button>
        </div>

        {tab === "login" ? (
          <form className="login-form" onSubmit={handleLogin}>
            <div className="form-field">
              <label>E-posta</label>
              <input
                type="email"
                value={loginEmail}
                onChange={(e) => setLoginEmail(e.target.value)}
                placeholder="operator@cognivault.com"
                required
              />
            </div>
            <div className="form-field">
              <label>Şifre</label>
              <input
                type="password"
                value={loginPassword}
                onChange={(e) => setLoginPassword(e.target.value)}
                placeholder="••••••••"
                required
              />
            </div>
            {loginError && <div className="error-box">{loginError}</div>}
            <button className="primary-button" type="submit" disabled={loginLoading}>
              {loginLoading ? "Giriş yapılıyor..." : "Operasyon paneline gir"}
            </button>
            <div className="lp-switch-hint">
              Klinik hesabiniz yok mu?{" "}
              <button type="button" className="lp-switch-link" onClick={() => setTab("signup")}>
                Kayıt Ol
              </button>
            </div>
          </form>
        ) : (
          <form className="login-form" onSubmit={handleSignup}>
            <div className="form-field">
              <label>Klinik Yetkilisi</label>
              <input
                type="text"
                value={signupName}
                onChange={(e) => setSignupName(e.target.value)}
                placeholder="Ad Soyad"
                required
              />
            </div>
            <div className="form-field">
              <label>Klinik E-postası</label>
              <input
                type="email"
                value={signupEmail}
                onChange={(e) => setSignupEmail(e.target.value)}
                placeholder="klinik@ornek.com"
                required
              />
            </div>
            <div className="form-field">
              <label>Şifre</label>
              <input
                type="password"
                value={signupPassword}
                onChange={(e) => setSignupPassword(e.target.value)}
                placeholder="En az 6 karakter"
                required
              />
            </div>
            <div className="form-field">
              <label>Şifre Tekrar</label>
              <input
                type="password"
                value={signupPassword2}
                onChange={(e) => setSignupPassword2(e.target.value)}
                placeholder="••••••••"
                required
              />
            </div>
            {signupError && <div className="error-box">{signupError}</div>}
            <button className="primary-button" type="submit" disabled={signupLoading}>
              {signupLoading ? "Workspace oluşturuluyor..." : "Klinik Workspace Oluştur →"}
            </button>
            <div className="lp-switch-hint">
              Zaten hesabınız var mı?{" "}
              <button type="button" className="lp-switch-link" onClick={() => setTab("login")}>
                Giriş Yap
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
