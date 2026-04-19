import type {
  Appointment,
  AuditLog,
  AuthResponse,
  ChatSessionDetail,
  ChatSessionSummary,
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

export function getCurrentUser(token: string): Promise<User> {
  return request<User>("/auth/me", { method: "GET" }, token);
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

export function deleteSession(sessionId: number, token: string): Promise<{deleted: number}> {
  return request<{deleted: number}>(`/chat/sessions/${sessionId}`, { method: "DELETE" }, token);
}
