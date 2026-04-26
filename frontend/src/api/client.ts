import type {
  Appointment,
  AuditLog,
  AuthResponse,
  ChatSessionDetail,
  ChatSessionSummary,
  EnterpriseMessageResponse,
  EnterpriseOverview,
  EnterpriseSessionDetail,
  EnterpriseTicket,
  KnowledgeArticle,
  KnowledgeSearchResult,
  Metrics,
  SendMessageResponse,
  User
} from "../types/api";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api";

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
    throw new Error(error.detail ?? "Request failed");
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

/**
 * AI yanıtını SSE stream olarak okur.
 * Her yield: { t: "tk", v: "<token>" }  veya  { t: "done", card: ... }
 *
 * Mimari:
 *   Backend → Faz1 tool loop (sync) → Faz2 OpenAI stream → SSE satırları
 *   Frontend → ReadableStream → TextDecoder → SSE parser → token buffer
 */
export async function* streamMessage(
  sessionId: number,
  content: string,
  token: string
): AsyncGenerator<{ t: "tk"; v: string } | { t: "done"; card: unknown } | { t: "err"; v: string }> {
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
        const payload = JSON.parse(line.slice(6)) as { t: string; v?: string; card?: unknown };
        if (payload.t === "tk")   yield { t: "tk",   v: payload.v ?? "" };
        if (payload.t === "done") yield { t: "done", card: payload.card ?? null };
        if (payload.t === "err")  yield { t: "err",  v: payload.v ?? "Unknown error" };
      } catch { /* malformed line — skip */ }
    }
  }
}

/**
 * Ses kaydını OpenAI Whisper ile metne çevirir.
 */
export async function transcribeAudio(
  blob: Blob,
  token: string,
  lang = "tr"
): Promise<string> {
  const form = new FormData();
  form.append("file", blob, "recording.webm");
  form.append("language", lang);

  const res = await fetch(`${API_URL}/voice/transcribe`, {
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
 * Metni OpenAI TTS ile sese çevirir.
 * Backend mp3 stream döner → AudioContext ile çalınır.
 * Web Speech Synthesis'ten çok daha doğal ses kalitesi.
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
