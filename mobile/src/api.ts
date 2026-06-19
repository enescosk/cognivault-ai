// Gerçek CogniVault backend'ine bağlanır (web client ile birebir aynı endpoint'ler).
// Web dev'de localhost; cihazdan denemek için bilgisayarın LAN IP'siyle değiştir.
const BASE = "http://localhost:8000/api";

export type ShadowReview = {
  id: number;
  clinic_id: number;
  conversation_id: number;
  patient_message_id: number;
  draft_reply: string;
  intent: string;
  confidence_score: number;
  risk_reason: string;
  status: string;
  persona_name?: string | null;
  channel?: string | null;
  final_reply?: string | null;
  metadata_json?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type AuthUser = {
  id: number;
  full_name: string;
  email: string;
  role: { name: string };
};

export type AuthResponse = { access_token: string; token_type: string; user: AuthUser };

export type ClinicalOverview = {
  metrics: {
    clinic_name: string;
    pending_shadow_reviews: number;
    conversations_today: number;
    doctor_inbox_count: number;
  };
  shadow_reviews: ShadowReview[];
};

export type DecisionStatus = "approved" | "edited" | "rejected";

async function req<T>(path: string, init: RequestInit, token?: string): Promise<T> {
  const res = await fetch(BASE + path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers || {}),
    },
  });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`${res.status} · ${txt.slice(0, 160)}`);
  }
  return (await res.json()) as T;
}

export const api = {
  login: (email: string, password: string) =>
    req<AuthResponse>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),
  me: (token: string) => req<AuthUser>("/auth/me", { method: "GET" }, token),
  overview: (token: string) => req<ClinicalOverview>("/clinical/overview", { method: "GET" }, token),
  decide: (id: number, token: string, status: DecisionStatus, final_reply?: string) =>
    req<ShadowReview>(
      `/clinical/shadow-reviews/${id}`,
      { method: "PATCH", body: JSON.stringify({ status, ...(final_reply !== undefined ? { final_reply } : {}) }) },
      token,
    ),
};

// Governance (privacy_guardrail) okuma — backend clinical_service.py ile aynı yol.
export function readGovernance(review: ShadowReview) {
  const data = ((review.metadata_json as Record<string, unknown> | null | undefined)?.data ?? {}) as Record<string, unknown>;
  const gov = (data.privacy_guardrail ?? {}) as Record<string, unknown>;
  return {
    residency: typeof gov.data_residency_mode === "string" ? (gov.data_residency_mode as string) : undefined,
    dataClasses: Array.isArray(gov.data_classes) ? (gov.data_classes as string[]) : [],
    redacted: typeof gov.redacted_preview === "string" ? (gov.redacted_preview as string) : undefined,
  };
}
