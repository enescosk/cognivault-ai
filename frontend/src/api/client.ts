import type {
  Appointment,
  AICapabilities,
  AuditLog,
  AuthResponse,
  ChatSessionDetail,
  ChatSessionSummary,
  ClinicalAppointment,
  ClinicalAppointmentRow,
  ClinicalComplianceProfile,
  ClinicalConversationDetail,
  ClinicalOverview,
  ClinicalPatentDossier,
  ClinicalSlotBoard,
  ClinicDoctor,
  ClinicDoctorSlot,
  ClinicalPersona,
  EnterpriseMessageResponse,
  EnterpriseOverview,
  EnterpriseSessionDetail,
  EnterpriseTicket,
  KnowledgeArticle,
  KnowledgeSearchResult,
  Metrics,
  QualityReport,
  SendMessageResponse,
  ShadowReview,
  User,
  WebhookIngestionResponse
} from "../types/api";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";

/** Thrown for non-2xx HTTP responses; carries the HTTP status code. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string
): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {})
    }
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Request failed" }));
    throw new ApiError(response.status, error.detail ?? "Request failed");
  }

  return response.json() as Promise<T>;
}

export function login(email: string, password: string): Promise<AuthResponse> {
  return request<AuthResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password })
  });
}

export function register(fullName: string, email: string, password: string): Promise<AuthResponse> {
  return request<AuthResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ full_name: fullName, email, password, locale: "tr" })
  });
}

export function getCurrentUser(token: string): Promise<User> {
  return request<User>("/auth/me", { method: "GET" }, token);
}

export function updateCurrentUserLocale(token: string, locale: "tr" | "en"): Promise<User> {
  return request<User>(
    "/users/me",
    {
      method: "PATCH",
      body: JSON.stringify({ locale })
    },
    token
  );
}

export function listSessions(token: string): Promise<ChatSessionSummary[]> {
  return request<ChatSessionSummary[]>("/chat/sessions", { method: "GET" }, token);
}

export function createSession(token: string): Promise<ChatSessionDetail> {
  return request<ChatSessionDetail>(
    "/chat/sessions",
    {
      method: "POST",
      body: JSON.stringify({})
    },
    token
  );
}

export function getSession(sessionId: number, token: string): Promise<ChatSessionDetail> {
  return request<ChatSessionDetail>(`/chat/sessions/${sessionId}`, { method: "GET" }, token);
}

export function sendMessage(
  sessionId: number,
  content: string,
  token: string
): Promise<SendMessageResponse> {
  return request<SendMessageResponse>(
    `/chat/sessions/${sessionId}/messages`,
    {
      method: "POST",
      body: JSON.stringify({ content })
    },
    token
  );
}

export function getAuditLogs(token: string): Promise<AuditLog[]> {
  return request<AuditLog[]>("/audit-logs?limit=120", { method: "GET" }, token);
}

export function getMetrics(token: string): Promise<Metrics> {
  return request<Metrics>("/audit-logs/metrics", { method: "GET" }, token);
}

export function getAICapabilities(token: string): Promise<AICapabilities> {
  return request<AICapabilities>("/ai/capabilities", { method: "GET" }, token);
}

export function getQualityReport(token: string): Promise<QualityReport> {
  return request<QualityReport>("/quality/report", { method: "GET" }, token);
}

export function getAppointments(token: string): Promise<Appointment[]> {
  return request<Appointment[]>("/appointments", { method: "GET" }, token);
}

export type AppointmentSlot = {
  id: number;
  department: string;
  start_time: string;
  end_time: string;
  location: string;
  is_booked: boolean;
};

export function getAppointmentSlots(token: string, department?: string): Promise<AppointmentSlot[]> {
  const params = new URLSearchParams();
  if (department) params.set("department", department);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return request<AppointmentSlot[]>(`/appointments/slots${suffix}`, { method: "GET" }, token);
}

export function cancelAppointment(appointmentId: number, token: string): Promise<Appointment> {
  return request<Appointment>(`/appointments/${appointmentId}/cancel`, { method: "PATCH" }, token);
}

export function rescheduleAppointment(appointmentId: number, slotId: number, token: string): Promise<Appointment> {
  return request<Appointment>(
    `/appointments/${appointmentId}/reschedule`,
    {
      method: "PATCH",
      body: JSON.stringify({ slot_id: slotId })
    },
    token
  );
}

export function deleteSession(sessionId: number, token: string): Promise<{deleted: number}> {
  return request<{deleted: number}>(`/chat/sessions/${sessionId}`, { method: "DELETE" }, token);
}

export function listUsers(token: string): Promise<User[]> {
  return request<User[]>("/users", { method: "GET" }, token);
}

export function getEnterpriseOverview(token: string): Promise<EnterpriseOverview> {
  return request<EnterpriseOverview>("/enterprise/overview", { method: "GET" }, token);
}

export function createEnterpriseSession(
  token: string,
  payload: { customer_name: string; customer_email?: string; customer_phone?: string }
): Promise<EnterpriseSessionDetail> {
  return request<EnterpriseSessionDetail>(
    "/enterprise/sessions",
    {
      method: "POST",
      body: JSON.stringify(payload)
    },
    token
  );
}

export function getEnterpriseSession(sessionId: number, token: string): Promise<EnterpriseSessionDetail> {
  return request<EnterpriseSessionDetail>(`/enterprise/sessions/${sessionId}`, { method: "GET" }, token);
}

export function sendEnterpriseMessage(
  sessionId: number,
  content: string,
  token: string
): Promise<EnterpriseMessageResponse> {
  return request<EnterpriseMessageResponse>(
    `/enterprise/sessions/${sessionId}/messages`,
    {
      method: "POST",
      body: JSON.stringify({ content })
    },
    token
  );
}

export function updateEnterpriseTicketStatus(
  ticketId: number,
  status: "open" | "in_progress" | "escalated" | "closed",
  token: string,
  resolutionNote?: string
): Promise<EnterpriseTicket> {
  return request<EnterpriseTicket>(
    `/enterprise/tickets/${ticketId}/status`,
    {
      method: "PATCH",
      body: JSON.stringify({ status, resolution_note: resolutionNote })
    },
    token
  );
}

export function updateEnterpriseTicket(
  ticketId: number,
  payload: {
    status?: "open" | "in_progress" | "escalated" | "closed";
    priority?: "low" | "normal" | "high" | "urgent";
    assigned_agent_id?: number | null;
    resolution_note?: string;
  },
  token: string
): Promise<EnterpriseTicket> {
  return request<EnterpriseTicket>(
    `/enterprise/tickets/${ticketId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload)
    },
    token
  );
}

export function listKnowledgeArticles(token: string): Promise<KnowledgeArticle[]> {
  return request<KnowledgeArticle[]>("/knowledge/articles", { method: "GET" }, token);
}

export function createKnowledgeArticle(
  token: string,
  payload: { title: string; content: string; tags: string[] }
): Promise<KnowledgeArticle> {
  return request<KnowledgeArticle>(
    "/knowledge/articles",
    {
      method: "POST",
      body: JSON.stringify(payload)
    },
    token
  );
}

export function searchKnowledgeArticles(token: string, query: string): Promise<KnowledgeSearchResult[]> {
  const params = new URLSearchParams({ q: query, limit: "5" });
  return request<KnowledgeSearchResult[]>(`/knowledge/search?${params.toString()}`, { method: "GET" }, token);
}

export function createClinicalAppointment(
  token: string,
  payload: {
    conversation_id: number;
    department: string;
    doctor_id?: number | null;
    slot_id?: number | null;
    starts_at?: string | null;
    duration_minutes?: number;
    visit_reason?: string | null;
    notes?: string | null;
  }
): Promise<ClinicalAppointment> {
  return request<ClinicalAppointment>(
    "/clinical/appointments",
    {
      method: "POST",
      body: JSON.stringify(payload)
    },
    token
  );
}

export function getUpcomingClinicalAppointments(token: string, withinMinutes = 120): Promise<ClinicalAppointment[]> {
  return request<ClinicalAppointment[]>(
    `/clinical/appointments/upcoming?within_minutes=${withinMinutes}`,
    { method: "GET" },
    token
  );
}

export function listClinicalAppointments(token: string, limit = 50): Promise<ClinicalAppointmentRow[]> {
  return request<ClinicalAppointmentRow[]>(`/clinical/appointments?limit=${limit}`, { method: "GET" }, token);
}

export function getClinicalOverview(token: string): Promise<ClinicalOverview> {
  return request<ClinicalOverview>("/clinical/overview", { method: "GET" }, token);
}

export function getClinicalConversation(conversationId: number, token: string): Promise<ClinicalConversationDetail> {
  return request<ClinicalConversationDetail>(`/clinical/conversations/${conversationId}`, { method: "GET" }, token);
}

export function getClinicalComplianceProfile(token: string): Promise<ClinicalComplianceProfile> {
  return request<ClinicalComplianceProfile>("/clinical/compliance-profile", { method: "GET" }, token);
}

export function getClinicalPatentDossier(token: string): Promise<ClinicalPatentDossier> {
  return request<ClinicalPatentDossier>("/clinical/patent-dossier", { method: "GET" }, token);
}

export function getClinicalSlotBoard(token: string): Promise<ClinicalSlotBoard> {
  return request<ClinicalSlotBoard>("/clinical/slot-board", { method: "GET" }, token);
}

export function getClinicalDoctors(token: string): Promise<ClinicDoctor[]> {
  return request<ClinicDoctor[]>("/clinical/doctors", { method: "GET" }, token);
}

export function getDoctorSlots(token: string, doctorId: number, date?: string): Promise<ClinicDoctorSlot[]> {
  const params = new URLSearchParams();
  if (date) params.set("date", date);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return request<ClinicDoctorSlot[]>(`/clinical/doctors/${doctorId}/slots${suffix}`, { method: "GET" }, token);
}

export function simulateWhatsAppMessage(
  token: string,
  payload: { from_phone: string; body: string; patient_name?: string }
): Promise<WebhookIngestionResponse> {
  return request<WebhookIngestionResponse>(
    "/clinical/simulate-whatsapp",
    { method: "POST", body: JSON.stringify(payload) },
    token
  );
}

export function simulateVoiceCall(
  token: string,
  payload: { from_phone: string; speech: string; patient_name?: string; persona_id?: "selin" | "arzu" | "can" }
): Promise<WebhookIngestionResponse> {
  return request<WebhookIngestionResponse>(
    "/clinical/simulate-voice-call",
    { method: "POST", body: JSON.stringify(payload) },
    token
  );
}

export function updateShadowReview(
  reviewId: number,
  token: string,
  payload: { status: "approved" | "edited" | "rejected"; final_reply?: string | null }
): Promise<ShadowReview> {
  return request<ShadowReview>(
    `/clinical/shadow-reviews/${reviewId}`,
    { method: "PATCH", body: JSON.stringify(payload) },
    token
  );
}

export type ClinicalProcedureInput = {
  id?: number;
  name: string;
  code?: string | null;
  tooth?: string | null;
  status?: "planned" | "in_progress" | "completed" | "cancelled";
  notes?: string | null;
  sort_order?: number;
};

export function updateClinicalAppointmentDetails(
  token: string,
  appointmentId: number,
  payload: {
    starts_at?: string | null;
    duration_minutes?: number;
    visit_reason?: string | null;
    notes?: string | null;
    procedures?: ClinicalProcedureInput[];
  }
): Promise<ClinicalAppointmentRow> {
  return request<ClinicalAppointmentRow>(
    `/clinical/appointments/${appointmentId}/clinical-details`,
    { method: "PATCH", body: JSON.stringify(payload) },
    token
  );
}

export function updateClinicalAppointmentStatus(
  token: string,
  appointmentId: number,
  status: "pending" | "confirmed" | "cancelled"
): Promise<ClinicalAppointmentRow> {
  return request<ClinicalAppointmentRow>(
    `/clinical/appointments/${appointmentId}/status`,
    { method: "POST", body: JSON.stringify({ status }) },
    token
  );
}

export type ClinicalManualAppointmentInput = {
  full_name?: string | null;
  phone: string;
  department: string;
  starts_at?: string | null;
  duration_minutes?: number;
  visit_reason?: string | null;
  physician_name?: string | null;
  branch_name?: string | null;
  notes?: string | null;
};

export function createManualClinicalAppointment(
  token: string,
  payload: ClinicalManualAppointmentInput
): Promise<ClinicalAppointmentRow> {
  return request<ClinicalAppointmentRow>(
    "/clinical/appointments/manual",
    { method: "POST", body: JSON.stringify(payload) },
    token
  );
}

/**
 * AI yanıtını SSE stream olarak okur.
 * Her yield: { t: "tk", v: "<token>" }  veya  { t: "done", card: ... }
 *
 * Mimari:
 *   Backend → Faz1 tool loop (sync) → Faz2 OpenAI stream → SSE satırları
 *   Frontend → ReadableStream → TextDecoder → SSE parser → token buffer
 */
export type StreamEvent =
  | { t: "tk"; v: string }
  | { t: "done"; card: unknown }
  | { t: "err"; v: string }
  | { t: "thinking" }
  | { t: "tool"; name: string; status: "running" | "done" };

export async function* streamMessage(
  sessionId: number,
  content: string,
  token: string
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${API_URL}/chat/sessions/${sessionId}/messages/stream`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ content }),
  });

  if (!res.ok || !res.body) {
    const err = await res.json().catch(() => ({ detail: "Stream failed" }));
    throw new Error((err as { detail?: string }).detail ?? "Stream failed");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // SSE: her mesaj "data: ...\n\n" formatında
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";          // son tamamlanmamış parçayı tut

    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data: ")) continue;
      try {
        const payload = JSON.parse(line.slice(6)) as {
          t: string;
          v?: string;
          card?: unknown;
          name?: string;
          status?: string;
        };
        if (payload.t === "tk")       yield { t: "tk",   v: payload.v ?? "" };
        if (payload.t === "done")     yield { t: "done", card: payload.card ?? null };
        if (payload.t === "err")      yield { t: "err",  v: payload.v ?? "Unknown error" };
        if (payload.t === "thinking") yield { t: "thinking" };
        if (payload.t === "tool" && payload.name && (payload.status === "running" || payload.status === "done")) {
          yield { t: "tool", name: payload.name, status: payload.status };
        }
      } catch { /* malformed line — skip */ }
    }
  }
}

/**
 * Ses kaydını aktif backend STT sağlayıcısı ile metne çevirir.
 */
export async function transcribeAudio(
  blob: Blob,
  token: string,
  lang = "tr"
): Promise<string> {
  const form = new FormData();
  form.append("file", blob, "recording.webm");

  const params = new URLSearchParams({ language: lang });
  const res = await fetch(`${API_URL}/voice/transcribe?${params.toString()}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Transcription failed" }));
    throw new Error(err.detail ?? "Transcription failed");
  }

  const data = await res.json() as { text: string };
  return data.text;
}

/**
 * Metni aktif backend TTS sağlayıcısı ile sese çevirir.
 * Backend ses stream'i döner → AudioContext ile çalınır.
 */
export async function synthesizeSpeech(
  text: string,
  token: string,
  voice = "nova",   // nova | onyx | shimmer | alloy
  speed = 1.0
): Promise<ArrayBuffer> {
  const res = await fetch(`${API_URL}/voice/synthesize`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ text, voice, speed }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "TTS failed" }));
    throw new Error(err.detail ?? "TTS failed");
  }

  return res.arrayBuffer();
}

export interface AgentDecisionLog {
  id: number;
  agent_type: string;
  intent: string;
  confidence: number;
  risk: "low" | "medium" | "high" | string;
  requires_human: boolean;
  action: string | null;
  reason: string | null;
  organization_id: number | null;
  clinic_id: number | null;
  conversation_id: number | null;
  chat_session_id: number | null;
  user_id: number | null;
  request_id: string | null;
  payload_json: Record<string, unknown>;
  created_at: string;
}

export interface AgentDecisionFilters {
  agent_type?: string;
  requires_human?: boolean;
  risk?: "low" | "medium" | "high";
  conversation_id?: number;
  limit?: number;
}

export function listAgentDecisions(
  token: string,
  filters: AgentDecisionFilters = {},
): Promise<AgentDecisionLog[]> {
  const params = new URLSearchParams();
  if (filters.agent_type) params.set("agent_type", filters.agent_type);
  if (filters.requires_human !== undefined) params.set("requires_human", String(filters.requires_human));
  if (filters.risk) params.set("risk", filters.risk);
  if (filters.conversation_id !== undefined) params.set("conversation_id", String(filters.conversation_id));
  if (filters.limit) params.set("limit", String(filters.limit));
  const qs = params.toString();
  return request<AgentDecisionLog[]>(`/agents/decisions${qs ? `?${qs}` : ""}`, {}, token);
}

// ─── LLM Usage / Cost ───────────────────────────────────────────────────────
export interface UsageSummaryByModel {
  model: string;
  provider: string;
  calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
}

export interface UsageSummary {
  range_days: number;
  total_calls: number;
  total_tokens: number;
  total_cost_usd: number;
  by_model: UsageSummaryByModel[];
  by_agent_type: Record<string, number>;
}

export function getUsageSummary(token: string, days: number = 7): Promise<UsageSummary> {
  return request<UsageSummary>(`/agents/usage/summary?days=${days}`, {}, token);
}

// ─── Clinic Admin API ───────────────────────────────────────────────────────
export interface Doctor {
  id: number;
  clinic_id: number;
  full_name: string;
  specialty: string;
  is_active: boolean;
  created_at: string;
}

export interface ClinicService {
  id: number;
  clinic_id: number;
  name: string;
  description: string | null;
  is_active: boolean;
  created_at: string;
}

export interface KVKKDisclosure {
  id: number;
  clinic_id: number;
  version: string;
  disclosure_text: string;
  is_active: boolean;
  created_at: string;
}

export function getBranding(token: string): Promise<{ branding: Record<string, any> }> {
  return request<{ branding: Record<string, any> }>("/clinic/admin/branding", {}, token);
}

export function updateBranding(token: string, payload: Record<string, any>): Promise<{ branding: Record<string, any> }> {
  return request<{ branding: Record<string, any> }>("/clinic/admin/branding", {
    method: "PATCH",
    body: JSON.stringify(payload)
  }, token);
}

export function getDoctors(token: string): Promise<Doctor[]> {
  return request<Doctor[]>("/clinic/admin/doctors", {}, token);
}

export function createDoctor(token: string, payload: { full_name: string; specialty: string; is_active?: boolean }): Promise<Doctor> {
  return request<Doctor>("/clinic/admin/doctors", {
    method: "POST",
    body: JSON.stringify(payload)
  }, token);
}

export function updateDoctor(token: string, id: number, payload: { full_name: string; specialty: string; is_active?: boolean }): Promise<Doctor> {
  return request<Doctor>(`/clinic/admin/doctors/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  }, token);
}

export function deleteDoctor(token: string, id: number): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/clinic/admin/doctors/${id}`, { method: "DELETE" }, token);
}

export function getServices(token: string): Promise<ClinicService[]> {
  return request<ClinicService[]>("/clinic/admin/services", {}, token);
}

export function createService(token: string, payload: { name: string; description?: string; is_active?: boolean }): Promise<ClinicService> {
  return request<ClinicService>("/clinic/admin/services", {
    method: "POST",
    body: JSON.stringify(payload)
  }, token);
}

export function updateService(token: string, id: number, payload: { name: string; description?: string; is_active?: boolean }): Promise<ClinicService> {
  return request<ClinicService>(`/clinic/admin/services/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  }, token);
}

export function deleteService(token: string, id: number): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/clinic/admin/services/${id}`, { method: "DELETE" }, token);
}

export function getDisclosures(token: string): Promise<KVKKDisclosure[]> {
  return request<KVKKDisclosure[]>("/clinic/admin/disclosures", {}, token);
}

export function createDisclosure(token: string, payload: { version: string; disclosure_text: string; is_active?: boolean }): Promise<KVKKDisclosure> {
  return request<KVKKDisclosure>("/clinic/admin/disclosures", {
    method: "POST",
    body: JSON.stringify(payload)
  }, token);
}
