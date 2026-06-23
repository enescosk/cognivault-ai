import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import {
  createSession,
  deleteSession,
  getAppointments,
  getAuditLogs,
  getMetrics,
  getSession,
  listSessions,
  listUsers,
  streamMessage,
} from "../api/client";
import { dashboardKeys } from "../api/queryKeys";
import { useAuth } from "../context/AuthContext";
import { useNavigate } from "react-router-dom";
import type { ChatSessionSummary } from "../types/api";
import { AuditLogPanel } from "./AuditLogPanel";
import { AppointmentPanel } from "./AppointmentPanel";
import { AppointmentsPage } from "./AppointmentsPage";
import { AdminPanel } from "./AdminPanel";
import { ChatWindow } from "./ChatWindow";
import { ClinicalPanel } from "./ClinicalPanel";
import { ClinicAdminPanel } from "./ClinicAdminPanel";
import { ClinicalPlayground } from "./ClinicalPlayground";
import { DecisionLogView } from "./DecisionLogView";
import { UsageCostCard } from "./UsageCostCard";
import { ErrorBoundary } from "./ErrorBoundary";
import { MetricsBar } from "./MetricsBar";
import { Sidebar } from "./Sidebar";
import { showToast } from "./ui/Toast";

interface DashboardProps {
  /**
   * Audience hint coming from the router (`/customer/*` vs `/operator/*`).
   * Used only as metadata today — actual rendering still branches on the
   * authenticated user's role so backend RBAC remains the source of truth.
   */
  audience?: "customer" | "operator";
  defaultView?: "chat" | "appointments" | "clinical" | "clinic-admin";
}

function toSessionSummary(session: {
  id: number;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
}): ChatSessionSummary {
  return { ...session, last_message_preview: null };
}

export function Dashboard({ audience, defaultView }: DashboardProps = {}) {
  const { token, user, logout } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null);
  const [sending, setSending] = useState(false);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [streamingContent, setStreamingContent] = useState<string | null>(null);
  const [activeTools, setActiveTools] = useState<string[]>([]);  // şu an çalışan tool'lar
  const [isThinking, setIsThinking] = useState(false);            // LLM düşünüyor mu
  const [actionError, setActionError] = useState<string | null>(null);

  const role = user?.role.name ?? "customer";
  const isCustomer = role === "customer";
  const isOperator = role === "operator";
  const isAdmin    = role === "admin";
  const [view, setView] = useState<"chat" | "appointments" | "clinical" | "clinic-admin">(
    defaultView ?? (isOperator || isAdmin ? "clinical" : "chat"),
  );

  const sessionIndexQuery = useQuery({
    queryKey: dashboardKeys.sessions(token),
    enabled: Boolean(token && user),
    queryFn: async () => {
      const sessionList = await listSessions(token!);
      // Bir tane taslak oturum korunur; eski boş taslaklar sessizce temizlenir.
      const emptySessions = sessionList.filter((session) => session.last_message_preview === null);
      const staleDrafts = emptySessions.slice(1);
      if (staleDrafts.length > 0) {
        await Promise.all(staleDrafts.map((session) => deleteSession(session.id, token!).catch(() => undefined)));
      }
      const cleaned = sessionList.filter((session) => !staleDrafts.some((draft) => draft.id === session.id));
      if (cleaned.length > 0) return cleaned;

      const created = await createSession(token!);
      queryClient.setQueryData(dashboardKeys.session(token, created.id), created);
      return [toSessionSummary(created)];
    },
  });

  const sessions = sessionIndexQuery.data ?? [];
  const resolvedSessionId =
    selectedSessionId && sessions.some((session) => session.id === selectedSessionId)
      ? selectedSessionId
      : sessions[0]?.id ?? null;

  const selectedSessionQuery = useQuery({
    queryKey: dashboardKeys.session(token, resolvedSessionId),
    enabled: Boolean(token && resolvedSessionId),
    queryFn: () => getSession(resolvedSessionId!, token!),
  });
  const appointmentsQuery = useQuery({
    queryKey: dashboardKeys.appointments(token),
    enabled: Boolean(token && user),
    queryFn: () => getAppointments(token!),
  });
  const metricsQuery = useQuery({
    queryKey: dashboardKeys.metrics(token),
    enabled: Boolean(token && user),
    queryFn: () => getMetrics(token!),
  });
  const logsQuery = useQuery({
    queryKey: dashboardKeys.auditLogs(token),
    enabled: Boolean(token && isAdmin),
    queryFn: () => getAuditLogs(token!),
  });
  const usersQuery = useQuery({
    queryKey: dashboardKeys.users(token),
    enabled: Boolean(token && (isOperator || isAdmin)),
    queryFn: () => listUsers(token!),
    retry: false,
  });

  const selectedSession = selectedSessionQuery.data ?? null;
  const appointments = appointmentsQuery.data ?? [];
  const metrics = metricsQuery.data ?? null;
  const logs = logsQuery.data ?? [];
  const users = usersQuery.data ?? [];

  const createSessionMutation = useMutation({
    mutationFn: () => createSession(token!),
    onSuccess: (created) => {
      queryClient.setQueryData<ChatSessionSummary[]>(dashboardKeys.sessions(token), (current = []) => [
        toSessionSummary(created),
        ...current,
      ]);
      queryClient.setQueryData(dashboardKeys.session(token, created.id), created);
      setSelectedSessionId(created.id);
    },
  });

  const deleteSessionMutation = useMutation({
    mutationFn: (sessionId: number) => deleteSession(sessionId, token!),
    onSuccess: async (_result, sessionId) => {
      queryClient.removeQueries({ queryKey: dashboardKeys.session(token, sessionId) });
      if (selectedSessionId === sessionId) setSelectedSessionId(null);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: dashboardKeys.sessions(token) }),
        queryClient.invalidateQueries({ queryKey: dashboardKeys.metrics(token) }),
        queryClient.invalidateQueries({ queryKey: dashboardKeys.appointments(token) }),
      ]);
    },
  });

  async function handleNewSession() {
    if (!token) return;
    // Seçili oturum zaten boşsa yeni oturum açma, onu öne getir
    if (selectedSession && selectedSession.messages.length === 0) {
      setView("chat");
      return;
    }
    setActionError(null);
    try {
      await createSessionMutation.mutateAsync();
      setView("chat");
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Oturum oluşturulamadı");
    }
  }

  async function handleSelectSession(sessionId: number) {
    if (!token) return;
    setSelectedSessionId(sessionId);
  }

  async function handleDeleteSession(sessionId: number) {
    if (!token) return;
    try {
      setActionError(null);
      await deleteSessionMutation.mutateAsync(sessionId);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Session could not be deleted");
    }
  }

  async function handleSend(content: string) {
    if (!token || !selectedSession) return;
    setSending(true);
    setPendingMessage(content);   // kullanıcı balonu anında görünür
    setStreamingContent("");      // AI balon hazır, içi dolacak
    setActiveTools([]);
    setIsThinking(false);
    setActionError(null);

    try {
      const stream = streamMessage(selectedSession.id, content, token);
      let buffer = "";

      for await (const event of stream) {
        if (event.t === "tk") {
          // İlk token gelince düşünme + tool göstergelerini kaldır
          if (buffer === "") {
            setIsThinking(false);
            setActiveTools([]);
          }
          buffer += event.v;
          setStreamingContent(buffer);
        } else if (event.t === "thinking") {
          setIsThinking(true);
        } else if (event.t === "tool") {
          if (event.status === "running") {
            setIsThinking(false);
            setActiveTools((prev) => prev.includes(event.name) ? prev : [...prev, event.name]);
          } else {
            setActiveTools((prev) => prev.filter((n) => n !== event.name));
          }
        } else if (event.t === "done") {
          // Stream bitti — session'ı yenile, streaming state'i temizle
          setPendingMessage(null);
          setStreamingContent(null);
          setActiveTools([]);
          setIsThinking(false);
          await Promise.all([
            queryClient.invalidateQueries({ queryKey: dashboardKeys.session(token, selectedSession.id) }),
            queryClient.invalidateQueries({ queryKey: dashboardKeys.sessions(token) }),
            queryClient.invalidateQueries({ queryKey: dashboardKeys.metrics(token) }),
            queryClient.invalidateQueries({ queryKey: dashboardKeys.appointments(token) }),
          ]);
          break;
        } else if (event.t === "err") {
          throw new Error(event.v);
        }
      }
    } catch (err) {
      setPendingMessage(null);
      setStreamingContent(null);
      setActiveTools([]);
      setIsThinking(false);
      setActionError(err instanceof Error ? err.message : "Mesaj gönderilemedi");
      if (selectedSession?.id) {
        await queryClient.invalidateQueries({ queryKey: dashboardKeys.session(token, selectedSession.id) });
      }
    } finally {
      setSending(false);
    }
  }

  const queryError = [
    sessionIndexQuery.error,
    selectedSessionQuery.error,
    appointmentsQuery.error,
    metricsQuery.error,
    logsQuery.error,
  ].find(Boolean);
  const error = actionError ?? (queryError instanceof Error ? queryError.message : queryError ? "Dashboard yüklenemedi" : null);

  // Surface dashboard-level errors via toast — fires once per distinct error message.
  useEffect(() => {
    if (error) showToast(error, "error");
  }, [error]);

  if (!user) return null;
  if ((sessionIndexQuery.isLoading || selectedSessionQuery.isLoading) && !selectedSession) {
    return <div className="loading-shell">Loading workspace...</div>;
  }

  const isClinicalView = view === "clinical" && (isOperator || isAdmin);

  return (
    <div
      className={`dashboard-shell ${isOperator ? "operator-view" : ""} ${isClinicalView ? "clinical-view" : ""}`}
      data-audience={audience ?? (isCustomer ? "customer" : "operator")}
    >
      <Sidebar
        user={user}
        sessions={sessions}
        appointments={appointments}
        selectedSessionId={selectedSession?.id}
        activeView={view}
        onSelectSession={(id) => { setView(isCustomer ? "chat" : "clinical"); if (isCustomer) handleSelectSession(id); }}
        onNewSession={() => { if (isCustomer) { setView("chat"); handleNewSession(); } else { setView("clinical"); } }}
        onDeleteSession={handleDeleteSession}
        onViewAppointments={() => setView("appointments")}
        onViewClinical={() => { setView("clinical"); navigate("/operator"); }}
        onViewClinicAdmin={() => { setView("clinic-admin"); navigate("/operator/admin"); }}
        onLogout={logout}
      />
      <main className="main-panel">
        {!isClinicalView ? (
          <ErrorBoundary scope="Metrics"><MetricsBar metrics={metrics} appointments={appointments} role={role} locale={user.locale} /></ErrorBoundary>
        ) : null}
        {error ? <div className="error-box" style={{ margin: "12px 24px 0" }}>{error}</div> : null}
        {view === "clinic-admin" && isAdmin ? (
          <ErrorBoundary scope="Clinic Admin">
            <ClinicAdminPanel token={token ?? ""} />
          </ErrorBoundary>
        ) : isClinicalView ? (
          <ErrorBoundary scope="Clinical">
            <ClinicalPanel token={token ?? ""} />
          </ErrorBoundary>
        ) : view === "appointments" && isCustomer ? (
          <ErrorBoundary scope="Randevular">
            <AppointmentsPage
              appointments={appointments}
              token={token ?? ""}
              locale={user.locale}
              onChanged={() => queryClient.invalidateQueries({ queryKey: dashboardKeys.appointments(token) })}
            />
          </ErrorBoundary>
        ) : (
          <ErrorBoundary scope="Sohbet">
            <ChatWindow session={selectedSession} user={user} sending={sending} pendingMessage={pendingMessage} streamingContent={streamingContent} activeTools={activeTools} isThinking={isThinking} token={token ?? ""} onSend={handleSend} />
          </ErrorBoundary>
        )}
      </main>
      {isCustomer && (
        <ErrorBoundary scope="Randevu paneli">
          <AppointmentPanel appointments={appointments} locale={user.locale} />
        </ErrorBoundary>
      )}
      {isAdmin && !isClinicalView && (
        <ErrorBoundary scope="Yönetim paneli">
          <aside className="audit-panel">
            <UsageCostCard token={token ?? ""} />
            <AdminPanel users={users} appointments={appointments} logs={logs} />
          </aside>
        </ErrorBoundary>
      )}
      {(isOperator || isAdmin) && isClinicalView && (
        <ErrorBoundary scope="Klinik araçlar">
          <aside className="audit-panel">
            <ClinicalPlayground token={token ?? ""} />
            <DecisionLogView />
          </aside>
        </ErrorBoundary>
      )}
    </div>
  );
}
