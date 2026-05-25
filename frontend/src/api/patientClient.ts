/**
 * Public patient endpoint'leri için API istemcisi.
 *
 * Mevcut `api/client.ts`'tan farkı: kullanıcı login token'ı yerine
 * kısa-ömürlü `consent_token` veya `session_token` taşır. İkisi de
 * `Authorization: Bearer …` header'ı ile gider.
 *
 * Bu istemci hiçbir AuthContext'e bağımlı değildir; patient page
 * sessionStorage üzerinden token yönetir.
 */

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";

export type DisclosureSummary = {
  version: string;
  body_hash: string;
  headline: string;
};

export type PublicBranch = {
  name: string;
  address?: string | null;
  phone?: string | null;
  working_hours?: Record<string, string> | null;
};

export type PublicClinicView = {
  slug: string;
  name: string;
  headline: string;
  sub_headline: string;
  logo_url?: string | null;
  primary_color: string;
  accent_color: string;
  contact_phone?: string | null;
  public_address?: string | null;
  branches: PublicBranch[];
  services: string[];
  disclosure: DisclosureSummary;
};

export type DisclosureFull = DisclosureSummary & { body: string };

export type ConsentRequestBody = {
  full_name: string;
  phone: string;
  disclosure_version: string;
  disclosure_hash: string;
  accepted_cross_border: boolean;
};

export type ConsentResponse = {
  consent_token: string;
  expires_in_seconds: number;
};

export type StartConversationBody = {
  full_name: string;
  phone: string;
  initial_message?: string | null;
};

export type StartConversationResponse = {
  session_token: string;
  conversation_id: number;
  patient_id: number;
  welcome_message?: string | null;
};

export type PublicMessageView = {
  id: number;
  sender: "patient" | "assistant" | "operator" | "system";
  body: string;
  intent: string | null;
  confidence_score: number | null;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
};

export type PublicMessageResponse = {
  patient_message: PublicMessageView;
  assistant_message: PublicMessageView | null;
  requires_human_review: boolean;
  conversation_status: string;
};

export type AppointmentConfirmResponse = {
  appointment_id: number;
  status: string;
  starts_at: string | null;
  department: string;
  summary: string;
};

async function jsonFetch<T>(
  path: string,
  options: RequestInit = {},
  token?: string,
): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "request_failed" }));
    throw new Error(error.detail ?? `request_failed:${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ─── Endpoints ──────────────────────────────────────────────────────────────

export function getPublicClinic(slug: string): Promise<PublicClinicView> {
  return jsonFetch<PublicClinicView>(`/public/clinics/${encodeURIComponent(slug)}`);
}

export function getPublicDisclosure(slug: string): Promise<DisclosureFull> {
  return jsonFetch<DisclosureFull>(`/public/clinics/${encodeURIComponent(slug)}/disclosure`);
}

export function submitConsent(
  slug: string,
  body: ConsentRequestBody,
): Promise<ConsentResponse> {
  return jsonFetch<ConsentResponse>(
    `/public/clinics/${encodeURIComponent(slug)}/consent`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export function startConversation(
  slug: string,
  consentToken: string,
  body: StartConversationBody,
): Promise<StartConversationResponse> {
  return jsonFetch<StartConversationResponse>(
    `/public/clinics/${encodeURIComponent(slug)}/conversations`,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
    consentToken,
  );
}

export function sendPatientMessage(
  slug: string,
  conversationId: number,
  sessionToken: string,
  body: string,
): Promise<PublicMessageResponse> {
  return jsonFetch<PublicMessageResponse>(
    `/public/clinics/${encodeURIComponent(slug)}/conversations/${conversationId}/messages`,
    {
      method: "POST",
      body: JSON.stringify({ body }),
    },
    sessionToken,
  );
}

export function confirmAppointment(
  slug: string,
  conversationId: number,
  sessionToken: string,
  payload: {
    department: string;
    starts_at?: string | null;
    notes?: string | null;
    slot_offer_id?: string | null;
  },
): Promise<AppointmentConfirmResponse> {
  return jsonFetch<AppointmentConfirmResponse>(
    `/public/clinics/${encodeURIComponent(slug)}/conversations/${conversationId}/appointments`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    sessionToken,
  );
}

// ─── Local session helpers ─────────────────────────────────────────────────

const STORAGE_KEY = "cognivault.patient.session";

export type PatientSessionState = {
  slug: string;
  consent_token?: string;
  session_token?: string;
  conversation_id?: number;
  patient_id?: number;
  disclosure_version?: string;
  consent_expires_at?: number;
  session_expires_at?: number;
};

export function loadPatientSession(slug: string): PatientSessionState | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PatientSessionState;
    if (parsed.slug !== slug) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function savePatientSession(state: PatientSessionState): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* sessionStorage disabled — ignore */
  }
}

export function clearPatientSession(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}
