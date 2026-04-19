import { useState } from "react";

type LoginScreenProps = {
  onSubmit: (email: string, password: string) => Promise<void>;
};

const sampleUsers = [
  {
    label: "Customer",
    email: "ayse@cognivault.local",
    password: "demo123",
    description: "Can chat with the agent and create only her own appointment."
  },
  {
    label: "Operator",
    email: "operator@cognivault.local",
    password: "demo123",
    description: "Can supervise customer workflows and operational records."
  },
  {
    label: "Admin",
    email: "admin@cognivault.local",
    password: "demo123",
    description: "Can inspect logs, users, and platform-wide activity."
  }
];

export function LoginScreen({ onSubmit }: LoginScreenProps) {
  const [email, setEmail] = useState(sampleUsers[0].email);
  const [password, setPassword] = useState(sampleUsers[0].password);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(email, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="login-shell">
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
          <div className="sample-grid">
            {sampleUsers.map((user) => (
              <button
                key={user.email}
                className="sample-user-card"
                type="button"
                onClick={() => { setEmail(user.email); setPassword(user.password); }}
              >
                <span className="role-tag">{user.label}</span>
                <strong>{user.email}</strong>
                <p>{user.description}</p>
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

      <div className="login-card">
        <div className="login-card-header">
          <div className="login-badge">
            <span className="login-badge-dot" />
            Demo Access
          </div>
          <h2>Sign in to the workspace</h2>
          <p>Use one of the seeded users to explore customer, operator, and admin views.</p>
        </div>

        <form className="login-form" onSubmit={handleSubmit}>
          <div className="form-field">
            <label>Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="email@cognivault.local"
            />
          </div>
          <div className="form-field">
            <label>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </div>
          {error && <div className="error-box">{error}</div>}
          <button className="primary-button" type="submit" disabled={submitting}>
            {submitting ? "Signing in..." : "Enter Dashboard →"}
          </button>
        </form>
      </div>
    </div>
  );
}
