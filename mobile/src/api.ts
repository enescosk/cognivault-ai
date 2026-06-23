// Gerçek CogniVault backend'ine bağlanır (web client ile birebir aynı endpoint'ler).
// Web dev'de localhost; cihazdan denemek için bilgisayarın LAN IP'siyle değiştir.
const BASE = process.env.EXPO_PUBLIC_API_URL?.replace(/\/$/, "") || "http://localhost:8000/api";

export type ShadowReview = {
  id: number;
  clinic_id: number;
  conversation_id: number;
  patient_message_id: number;
  assigned_doctor_id?: number | null;
  assigned_doctor_name?: string | null;
  assigned_doctor_specialty?: string | null;
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
  title?: string | null;
  role: { name: string };
};

export type AuthResponse = { access_token: string; token_type: string; user: AuthUser };

export type ClinicalOverview = {
  viewer: {
    clinic_role: "owner" | "operator" | "clinician";
    doctor_id?: number | null;
    doctor_name?: string | null;
    specialty?: string | null;
  };
  metrics: {
    clinic_name: string;
    pending_shadow_reviews: number;
    conversations_today: number;
    doctor_inbox_count: number;
  };
  shadow_reviews: ShadowReview[];
};

export type DecisionStatus = "approved" | "edited" | "rejected";
export type AppointmentStatus = "pending" | "confirmed" | "cancelled";
export type ProcedureStatus = "planned" | "in_progress" | "completed" | "cancelled";

export type ClinicalProcedure = {
  id: number;
  name: string;
  code?: string | null;
  tooth?: string | null;
  status: ProcedureStatus;
  notes?: string | null;
  sort_order: number;
  performed_by_doctor_id?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
};

export type ClinicalProcedureInput = Omit<
  ClinicalProcedure,
  "id" | "performed_by_doctor_id" | "started_at" | "completed_at"
> & { id?: number };

export type ClinicalAppointment = {
  id: number;
  patient_id: number;
  patient_name?: string | null;
  patient_phone?: string | null;
  conversation_id?: number | null;
  assigned_doctor_id?: number | null;
  department: string;
  physician_name?: string | null;
  branch_name?: string | null;
  starts_at?: string | null;
  ends_at?: string | null;
  duration_minutes: number;
  visit_reason?: string | null;
  status: AppointmentStatus;
  notes?: string | null;
  procedures: ClinicalProcedure[];
  created_at: string;
};

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
  appointments: (token: string) =>
    req<ClinicalAppointment[]>("/clinical/appointments?limit=200", { method: "GET" }, token),
  updateAppointment: (id: number, token: string, status: AppointmentStatus) =>
    req<ClinicalAppointment>(
      `/clinical/appointments/${id}/status`,
      { method: "POST", body: JSON.stringify({ status }) },
      token,
    ),
  updateAppointmentDetails: (
    id: number,
    token: string,
    details: {
      starts_at?: string | null;
      duration_minutes?: number;
      visit_reason?: string | null;
      notes?: string | null;
      procedures?: ClinicalProcedureInput[];
    },
  ) =>
    req<ClinicalAppointment>(
      `/clinical/appointments/${id}/clinical-details`,
      { method: "PATCH", body: JSON.stringify(details) },
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
