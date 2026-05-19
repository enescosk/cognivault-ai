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
    description: "Telefon, WhatsApp, Doctor Inbox ve randevu adaylarini yonetir.",
  },
  {
    label: "Klinik Sahibi",
    email: "admin@cognivault.com",
    password: "demo123",
    description: "Klinik performansi, onay kuyrugu, audit ve operasyon guvenligini izler.",
  },
];

const productPillars = [
  "Telefon + WhatsApp tek hasta akisi",
  "Tani koymayan guvenli medikal triyaj",
  "Konusmadan randevu adayina gecis",
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
          <div className="login-product-kicker">Butik klinikler ve dis hekimleri icin</div>
          <h1>Medical <em>Command</em><br/>Center</h1>
          <p>
            Telefonu ve WhatsApp'i karsilayan, hastayi guvenli medikal triyajdan geciren,
            doktor ekranina ozet dusen ve konusmadan randevu adayi olusturan AI resepsiyon sistemi.
          </p>

          <div className="login-pillar-row">
            {productPillars.map((pillar) => <span key={pillar}>{pillar}</span>)}
          </div>

          {/* Klinik onboarding */}
          <div className="lp-section-label">Klinik Onboarding</div>
          <div className="lp-customer-grid">
            <button
              className="lp-customer-card lp-customer-card--new"
              type="button"
              onClick={() => setTab("signup")}
            >
              <div className="lp-customer-avatar lp-customer-avatar--new">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2"/>
                  <circle cx="9" cy="7" r="4"/>
                  <line x1="19" y1="8" x2="19" y2="14"/>
                  <line x1="22" y1="11" x2="16" y2="11"/>
                </svg>
              </div>
              <div className="lp-customer-info">
                <div className="lp-customer-name">Yeni Klinik Basvurusu</div>
                <div className="lp-customer-email">Demo klinik hesabi olustur</div>
              </div>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.3, flexShrink: 0 }}>
                <polyline points="9 18 15 12 9 6"/>
              </svg>
            </button>
            <button
              className="lp-customer-card"
              type="button"
              onClick={() => setTab("login")}
            >
              <div className="lp-customer-avatar" style={{ background: "rgba(31,111,104,0.12)", color: "#1f6f68" }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M15 3h4a2 2 0 012 2v14a2 2 0 01-2 2h-4"/>
                  <polyline points="10 17 15 12 10 7"/>
                  <line x1="15" y1="12" x2="3" y2="12"/>
                </svg>
              </div>
              <div className="lp-customer-info">
                <div className="lp-customer-name">Mevcut Klinik Girisi</div>
                <div className="lp-customer-email">Operator veya admin hesabi sec</div>
              </div>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.3, flexShrink: 0 }}>
                <polyline points="9 18 15 12 9 6"/>
              </svg>
            </button>
          </div>

          {/* Klinik personeli */}
          <div className="lp-section-label" style={{ marginTop: 24 }}>Klinik Personeli</div>
          <div className="sample-grid">
            {staffUsers.map((u) => (
              <button
                key={u.email}
                className="sample-user-card"
                type="button"
                onClick={() => pickStaff(u)}
              >
                <span className="role-tag">{u.label}</span>
                <strong>{u.email}</strong>
                <p>{u.description}</p>
              </button>
            ))}
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
              ? "Demo icin sol panelden resepsiyon veya klinik sahibi hesabini sec."
              : "Butik klinik icin demo workspace hesabi olustur."}
          </p>
        </div>

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
              {loginLoading ? "Giriş yapılıyor..." : "Dashboard'a Gir →"}
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
