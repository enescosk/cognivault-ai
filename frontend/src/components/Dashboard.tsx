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
import { useAuth } from "../context/AuthContext";
import type { Appointment, AuditLog, ChatSessionDetail, ChatSessionSummary, Metrics, User } from "../types/api";
import { AuditLogPanel } from "./AuditLogPanel";
import { AppointmentPanel } from "./AppointmentPanel";
import { AppointmentsPage } from "./AppointmentsPage";
import { AdminPanel } from "./AdminPanel";
import { OperatorPanel } from "./OperatorPanel";
import { ChatWindow } from "./ChatWindow";
import { MetricsBar } from "./MetricsBar";
import { Sidebar } from "./Sidebar";

export function Dashboard() {
  const { token, user, logout } = useAuth();
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [selectedSession, setSelectedSession] = useState<ChatSessionDetail | null>(null);
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [streamingContent, setStreamingContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"chat" | "appointments">("chat");

  const role = user?.role.name ?? "customer";
  const isCustomer = role === "customer";
  const isOperator = role === "operator";
  const isAdmin    = role === "admin";

  useEffect(() => {
    if (!token || !user) return;
    void loadDashboard();
  }, [token, user]);

  async function loadDashboard(nextSessionId?: number) {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const [sessionList, auditEntries, appointmentList, metricSummary] = await Promise.all([
        listSessions(token),
        getAuditLogs(token),
        getAppointments(token),
        getMetrics(token)
      ]);
      setLogs(auditEntries);
      setAppointments(appointmentList);
      setMetrics(metricSummary);
      if (role === "operator" || role === "admin") {
        listUsers(token).then(setUsers).catch(() => {});
      }

      // Boş oturumları (mesaj içermeyen) otomatik sil
      const emptyOnes = sessionList.filter(
        s => s.last_message_preview === null && s.id !== nextSessionId
      );
      const nonEmpty = sessionList.filter(s => s.last_message_preview !== null);
      // Tüm oturumlar boşsa en yenisini koru, geri kalanları sil
      const toDelete = nonEmpty.length > 0 ? emptyOnes : emptyOnes.slice(1);
      if (toDelete.length > 0) {
        await Promise.all(toDelete.map(s => deleteSession(s.id, token).catch(() => {})));
      }
      const cleanedList = sessionList.filter(s => !toDelete.some(d => d.id === s.id));
      setSessions(cleanedList);

      if (nextSessionId) {
        setSelectedSession(await getSession(nextSessionId, token));
      } else if (cleanedList.length > 0) {
        const preferredId = selectedSession?.id ?? cleanedList[0].id;
        const preferredExists = cleanedList.some(s => s.id === preferredId);
        setSelectedSession(await getSession(preferredExists ? preferredId : cleanedList[0].id, token));
      } else {
        const created = await createSession(token);
        setSessions([{ id: created.id, title: created.title, status: created.status, created_at: created.created_at, updated_at: created.updated_at, last_message_preview: null }]);
        setSelectedSession(created);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dashboard failed to load");
    } finally {
      setLoading(false);
    }
  }

  async function handleNewSession() {
    if (!token) return;
    // Seçili oturum zaten boşsa yeni oturum açma, onu öne getir
    if (selectedSession && selectedSession.messages.length === 0) {
      setView("chat");
      return;
    }
    const created = await createSession(token);
    await loadDashboard(created.id);
  }

  async function handleSelectSession(sessionId: number) {
    if (!token) return;
    setSelectedSession(await getSession(sessionId, token));
  }

  async function refreshMetrics() {
    if (!token) return;
    try {
      const [metricSummary, appointmentList] = await Promise.all([
        getMetrics(token),
        getAppointments(token),
      ]);
      setMetrics(metricSummary);
      setAppointments(appointmentList);
    } catch {}
  }

  async function handleDeleteSession(sessionId: number) {
    if (!token) return;
    try {
      await deleteSession(sessionId, token);
      const remaining = sessions.filter(s => s.id !== sessionId);
      setSessions(remaining);
      if (selectedSession?.id === sessionId) {
        if (remaining.length > 0) {
          setSelectedSession(await getSession(remaining[0].id, token));
        } else {
          const created = await createSession(token);
          setSessions([{ id: created.id, title: created.title, status: created.status, created_at: created.created_at, updated_at: created.updated_at, last_message_preview: null }]);
          setSelectedSession(created);
        }
      }
      // Metrics'i sil sonrası yenile
      void refreshMetrics();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Session could not be deleted");
    }
  }

  async function handleSend(content: string) {
    if (!token || !selectedSession) return;
    setSending(true);
    setPendingMessage(content);   // kullanıcı balonu anında görünür
    setStreamingContent("");      // AI balon hazır, içi dolacak
    setError(null);

    try {
      const stream = streamMessage(selectedSession.id, content, token);
      let buffer = "";

      for await (const event of stream) {
        if (event.t === "tk") {
          // Her token gelince buffer'a ekle → AI balon büyür
          buffer += event.v;
          setStreamingContent(buffer);
        } else if (event.t === "done") {
          // Stream bitti — session'ı yenile, streaming state'i temizle
          setPendingMessage(null);
          setStreamingContent(null);
          await loadDashboard(selectedSession.id);
          break;
        } else if (event.t === "err") {
          throw new Error(event.v);
        }
      }
    } catch (err) {
      setPendingMessage(null);
      setStreamingContent(null);
      setError(err instanceof Error ? err.message : "Mesaj gönderilemedi");
      if (selectedSession?.id) {
        try { setSelectedSession(await getSession(selectedSession.id, token)); } catch { /* ignore */ }
      }
    } finally {
      setSending(false);
    }
  }

  if (!user) return null;
  if (loading && !selectedSession) return <div className="loading-shell">Loading workspace...</div>;

  return (
    <div className="dashboard-shell">
      <Sidebar
        user={user}
        sessions={sessions}
        selectedSessionId={selectedSession?.id}
        activeView={view}
        onSelectSession={(id) => { setView("chat"); handleSelectSession(id); }}
        onNewSession={() => { setView("chat"); handleNewSession(); }}
        onDeleteSession={handleDeleteSession}
        onViewAppointments={() => setView("appointments")}
        onLogout={logout}
      />
      <main className="main-panel">
        <MetricsBar metrics={metrics} appointments={appointments} role={role} />
        {error ? <div className="error-box" style={{ margin: "12px 24px 0" }}>{error}</div> : null}
        {view === "appointments" && isCustomer
          ? <AppointmentsPage appointments={appointments} />
          : <ChatWindow session={selectedSession} user={user} sending={sending} pendingMessage={pendingMessage} streamingContent={streamingContent} token={token ?? ""} onSend={handleSend} />
        }
      </main>
      {isCustomer && <AppointmentPanel appointments={appointments} />}
      {isOperator && <OperatorPanel appointments={appointments} />}
      {isAdmin    && <AdminPanel users={users} appointments={appointments} logs={logs} />}
    </div>
  );
}
