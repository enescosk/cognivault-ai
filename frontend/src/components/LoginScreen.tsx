import { useState } from "react";

type LoginScreenProps = {
  onSubmit: (email: string, password: string) => Promise<void>;
};

const sampleUsers = [
  {
    label: "Customer / Musteri",
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

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
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
        <div className="brand-chip">Secure Enterprise AI Agent</div>
        <h1>Cognivault AI</h1>
        <p>
          Auditable, role-aware AI assistance for bilingual enterprise workflows. This MVP
          demonstrates guided appointment booking with RBAC, tool execution, and traceable logs.
        </p>
        <div className="sample-grid">
          {sampleUsers.map((user) => (
            <button
              key={user.email}
              className="sample-user-card"
              type="button"
              onClick={() => {
                setEmail(user.email);
                setPassword(user.password);
              }}
            >
              <strong>{user.label}</strong>
              <span>{user.email}</span>
              <p>{user.description}</p>
            </button>
          ))}
        </div>
      </div>

      <form className="login-card" onSubmit={handleSubmit}>
        <div className="eyebrow">Demo Access</div>
        <h2>Sign in to the workspace</h2>
        <p className="muted">
          Use one of the seeded users to explore customer, operator, and admin views.
        </p>
        <label>
          Email
          <input value={email} onChange={(event) => setEmail(event.target.value)} />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {error ? <div className="error-box">{error}</div> : null}
        <button className="primary-button" type="submit" disabled={submitting}>
          {submitting ? "Signing in..." : "Enter Dashboard"}
        </button>
      </form>
    </div>
  );
}
