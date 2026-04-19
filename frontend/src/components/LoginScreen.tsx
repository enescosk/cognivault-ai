import { useState } from "react";

type Props = {
  onLogin: (email: string, password: string) => Promise<void>;
  onRegister: (fullName: string, email: string, password: string) => Promise<void>;
};

const staffUsers = [
  {
    label: "Operator",
    email: "operator@cognivault.local",
    password: "demo123",
    description: "Müşteri iş akışlarını ve operasyonel kayıtları yönetir.",
  },
  {
    label: "Admin",
    email: "admin@cognivault.local",
    password: "demo123",
    description: "Logları, kullanıcıları ve platform aktivitesini görüntüler.",
  },
];

const demoCustomers = [
  {
    initials: "AD",
    name: "Ayse Demir",
    email: "ayse@cognivault.local",
    password: "demo123",
    color: "#63b3ed",
    bg: "rgba(99,179,237,0.14)",
  },
];

export function LoginScreen({ onLogin, onRegister }: Props) {
  const [tab, setTab] = useState<"login" | "signup">("login");

  // Login state
  const [loginEmail, setLoginEmail] = useState(demoCustomers[0].email);
  const [loginPassword, setLoginPassword] = useState(demoCustomers[0].password);
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

  function pickCustomer(c: { email: string; password: string }) {
    setLoginEmail(c.email);
    setLoginPassword(c.password);
    setTab("login");
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
          <span>Cognivault AI</span>
        </div>

        <div className="brand-hero">
          <h1>Secure <em>Enterprise</em><br/>AI Agents</h1>
          <p>Auditable, role-aware AI assistance for bilingual enterprise workflows. Guided appointment booking with RBAC, tool execution, and traceable logs.</p>

          {/* Mevcut Müşteriler */}
          <div className="lp-section-label">Mevcut Müşteriler</div>
          <div className="lp-customer-grid">
            {demoCustomers.map((c) => (
              <button
                key={c.email}
                className="lp-customer-card"
                type="button"
                onClick={() => pickCustomer(c)}
              >
                <div className="lp-customer-avatar" style={{ background: c.bg, color: c.color }}>
                  {c.initials}
                </div>
                <div className="lp-customer-info">
                  <div className="lp-customer-name">{c.name}</div>
                  <div className="lp-customer-email">{c.email}</div>
                </div>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.3, flexShrink: 0 }}>
                  <polyline points="9 18 15 12 9 6"/>
                </svg>
              </button>
            ))}
            <button
              className="lp-customer-card lp-customer-card--new"
              type="button"
              onClick={() => { setTab("signup"); }}
            >
              <div className="lp-customer-avatar lp-customer-avatar--new">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
                </svg>
              </div>
              <div className="lp-customer-info">
                <div className="lp-customer-name">Yeni Müşteri</div>
                <div className="lp-customer-email">Hesap oluştur</div>
              </div>
            </button>
          </div>

          {/* Personel (Operator / Admin) */}
          <div className="lp-section-label" style={{ marginTop: 20 }}>Personel Erişimi</div>
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

        <div style={{ display: "flex", gap: "24px", color: "var(--text-3)", fontSize: "0.78rem", fontFamily: "var(--font-mono)" }}>
          <span>ISO 27001</span>
          <span>RBAC Enforced</span>
          <span>Full Audit Trail</span>
        </div>
      </div>

      {/* ── Sağ panel ── */}
      <div className="login-card">
        <div className="login-card-header">
          <div className="login-badge">
            <span className="login-badge-dot" />
            {tab === "login" ? "Güvenli Giriş" : "Yeni Hesap"}
          </div>
          <h2>{tab === "login" ? "Workspace'e giriş yap" : "Müşteri hesabı oluştur"}</h2>
          <p>
            {tab === "login"
              ? "Mevcut hesabınızla giriş yapın ya da sol panelden bir kullanıcı seçin."
              : "Ücretsiz müşteri hesabı oluşturun, randevu alın."}
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
                placeholder="email@cognivault.local"
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
              Hesabınız yok mu?{" "}
              <button type="button" className="lp-switch-link" onClick={() => setTab("signup")}>
                Kayıt Ol
              </button>
            </div>
          </form>
        ) : (
          <form className="login-form" onSubmit={handleSignup}>
            <div className="form-field">
              <label>Ad Soyad</label>
              <input
                type="text"
                value={signupName}
                onChange={(e) => setSignupName(e.target.value)}
                placeholder="Adınız Soyadınız"
                required
              />
            </div>
            <div className="form-field">
              <label>E-posta</label>
              <input
                type="email"
                value={signupEmail}
                onChange={(e) => setSignupEmail(e.target.value)}
                placeholder="email@ornek.com"
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
              {signupLoading ? "Hesap oluşturuluyor..." : "Hesap Oluştur →"}
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
