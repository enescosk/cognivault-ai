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

const API_URL = import.meta.env.VITE_API_URL ?? "/api";

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
  full_name?: string | null;
  phone?: string | null;
  disclosure_version: string;
  disclosure_hash: string;
  accepted_cross_border: boolean;
  accepted_voice_processing?: boolean;
};

export type ConsentResponse = {
  consent_token: string;
  expires_in_seconds: number;
};

export type StartConversationBody = {
  // Yeni akışta her ikisi de opsiyonel — kimlik AI sohbet sırasında toplanır.
  // Legacy clientlar full_name+phone gönderiyorsa backend hâlâ kabul ediyor.
  full_name?: string | null;
  phone?: string | null;
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

export type PublicSlotOfferView = {
  id: number;
  department: string;
  physician_name?: string | null;
  starts_at: string;
  ends_at?: string | null;
  status: string;
  expires_at: string;
  label: string;
  metadata_json: Record<string, unknown> | null;
};

export type PublicMessageResponse = {
  patient_message: PublicMessageView;
  assistant_message: PublicMessageView | null;
  requires_human_review: boolean;
  conversation_status: string;
  slot_offers: PublicSlotOfferView[];
  detected_intent?: string | null;
  specialty?: string | null;
  emergency?: boolean;
};

export type PublicVoiceMetadata = {
  provider?: string;
  language?: string;
  audio_bytes?: number;
  confidence?: number | null;
  duration_seconds?: number | null;
  processing_ms?: number | null;
  source?: "voice_call" | "voice_input";
  retry_count?: number;
};

export type PublicTranscriptionResult = PublicVoiceMetadata & {
  text: string;
  provider: string;
  language: string;
  audio_bytes: number;
  confidence: number | null;
  duration_seconds: number | null;
  processing_ms: number | null;
};

export type PublicVoiceEventInput = {
  event_type: "no_result" | "retry_prompt" | "stt_failure" | "mic_denied" | "unsupported" | "recorder_error" | string;
  reason?: string | null;
  retry_count?: number | null;
  step?: string | null;
  phase?: string | null;
  provider?: string | null;
  metadata_json?: Record<string, unknown> | null;
};

export type AppointmentConfirmResponse = {
  appointment_id: number;
  status: string;
  starts_at: string | null;
  department: string;
  summary: string;
};

export type SlotHoldResponse = {
  slot_offer: PublicSlotOfferView;
};

/**
 * FastAPI 422 hatalarında detail bir array of {loc, msg, type} olarak
 * dönüyor; düz string'e çevirince "[object Object],[object Object]"
 * çıkıyor. Bu helper hem array hem object hem string detail formatlarını
 * insan-okur bir mesaja indirger.
 */
function formatBackendDetail(detail: unknown, status: number): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((d) => {
        if (typeof d === "string") return d;
        if (d && typeof d === "object") {
          const msg = (d as { msg?: string }).msg ?? "";
          const loc = (d as { loc?: (string | number)[] }).loc ?? [];
          const locStr = loc.length ? ` (${loc.join(".")})` : "";
          return `${msg}${locStr}`.trim();
        }
        return String(d);
      })
      .filter(Boolean);
    if (parts.length) return parts.join(" · ");
  }
  if (detail && typeof detail === "object") {
    const obj = detail as Record<string, unknown>;
    if (typeof obj.msg === "string") return obj.msg;
  }
  return `request_failed:${status}`;
}

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
    const body = await res.json().catch(() => null);
    throw new Error(formatBackendDetail(body?.detail, res.status));
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

export type PatientIdentityResponse = {
  patient_id: number;
  full_name: string | null;
  phone: string;
  is_anonymous: boolean;
};

/**
 * Sohbet sırasında AI veya UI hastanın adını/telefonunu yazdığında bu
 * endpoint'i çağırır. Anonim placeholder patient gerçek değerlere güncellenir.
 */
export function updatePatientIdentity(
  slug: string,
  conversationId: number,
  sessionToken: string,
  payload: { full_name?: string | null; phone?: string | null },
): Promise<PatientIdentityResponse> {
  return jsonFetch<PatientIdentityResponse>(
    `/public/clinics/${encodeURIComponent(slug)}/conversations/${conversationId}/patient`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
    sessionToken,
  );
}

export function sendPatientMessage(
  slug: string,
  conversationId: number,
  sessionToken: string,
  body: string,
  options?: { voice_metadata?: PublicVoiceMetadata | null },
): Promise<PublicMessageResponse> {
  return jsonFetch<PublicMessageResponse>(
    `/public/clinics/${encodeURIComponent(slug)}/conversations/${conversationId}/messages`,
    {
      method: "POST",
      body: JSON.stringify({ body, voice_metadata: options?.voice_metadata ?? undefined }),
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
    notes?: string | null;
    slot_offer_id: number;
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

export function holdSlotOffer(
  slug: string,
  conversationId: number,
  sessionToken: string,
  offerId: number,
): Promise<SlotHoldResponse> {
  return jsonFetch<SlotHoldResponse>(
    `/public/clinics/${encodeURIComponent(slug)}/conversations/${conversationId}/slot-offers/${offerId}/hold`,
    {
      method: "POST",
      body: JSON.stringify({}),
    },
    sessionToken,
  );
}

/**
 * Hasta sayfası için doğal sesli yanıt (OpenAI nova). Tarayıcının robotik
 * Web Speech sesi yerine kullanılır. MP3 ArrayBuffer döner; başarısız olursa
 * çağıran taraf Web Speech'e fallback yapar.
 */
export async function synthesizePublicSpeech(
  slug: string,
  text: string,
  sessionToken?: string,
  voice = "nova",
): Promise<Blob> {
  const res = await fetch(
    `${API_URL}/public/clinics/${encodeURIComponent(slug)}/voice/synthesize`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(sessionToken ? { Authorization: `Bearer ${sessionToken}` } : {}),
      },
      body: JSON.stringify({ text, voice }),
    },
  );
  if (!res.ok) throw new Error("tts_failed");
  // Blob döndürüyoruz ki içerik tipi (lokal=wav / openai=mp3) korunsun.
  return res.blob();
}

/**
 * Hasta sesli görüşmesi için konuşmayı metne çevirir — varsayılan lokal
 * faster-whisper (ses yurt içinde işlenir, dışarı çıkmaz).
 */
export async function transcribePublicSpeech(
  slug: string,
  audio: Blob,
  sessionToken?: string,
  language = "tr",
): Promise<PublicTranscriptionResult> {
  const fd = new FormData();
  fd.append("file", audio, "speech.webm");
  const res = await fetch(
    `${API_URL}/public/clinics/${encodeURIComponent(slug)}/voice/transcribe?language=${encodeURIComponent(language)}`,
    {
      method: "POST",
      headers: sessionToken ? { Authorization: `Bearer ${sessionToken}` } : undefined,
      body: fd,
    },
  );
  if (!res.ok) throw new Error("stt_failed");
  const data = (await res.json()) as PublicTranscriptionResult;
  return {
    ...data,
    text: data.text ?? "",
    provider: data.provider ?? "unknown",
    language: data.language ?? language,
    audio_bytes: data.audio_bytes ?? audio.size,
    confidence: data.confidence ?? null,
    duration_seconds: data.duration_seconds ?? null,
    processing_ms: data.processing_ms ?? null,
  };
}

export async function recordPublicVoiceEvent(
  slug: string,
  conversationId: number,
  sessionToken: string,
  payload: PublicVoiceEventInput,
): Promise<{ ok: boolean; counters: Record<string, number> }> {
  const res = await fetch(
    `${API_URL}/public/clinics/${encodeURIComponent(slug)}/conversations/${conversationId}/voice-events`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${sessionToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    },
  );
  if (!res.ok) throw new Error("voice_event_failed");
  return res.json() as Promise<{ ok: boolean; counters: Record<string, number> }>;
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
