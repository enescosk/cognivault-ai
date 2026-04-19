import { useEffect, useState } from "react";

import {
  createSession,
  getAppointments,
  getAuditLogs,
  getMetrics,
  getSession,
  listSessions,
  sendMessage
} from "../api/client";
import { useAuth } from "../context/AuthContext";
import type { Appointment, AuditLog, ChatSessionDetail, ChatSessionSummary, Metrics } from "../types/api";
import { AuditLogPanel } from "./AuditLogPanel";
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
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !user) {
      return;
    }
    void loadDashboard();
  }, [token, user]);

  async function loadDashboard(nextSessionId?: number) {
    if (!token) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [sessionList, auditEntries, appointmentList, metricSummary] = await Promise.all([
        listSessions(token),
        getAuditLogs(token),
        getAppointments(token),
        getMetrics(token)
      ]);
      setSessions(sessionList);
      setLogs(auditEntries);
      setAppointments(appointmentList);
      setMetrics(metricSummary);

      if (nextSessionId) {
        setSelectedSession(await getSession(nextSessionId, token));
      } else if (sessionList.length > 0) {
        const preferredId = selectedSession?.id ?? sessionList[0].id;
        setSelectedSession(await getSession(preferredId, token));
      } else {
        const created = await createSession(token);
        setSessions([
          {
            id: created.id,
            title: created.title,
            status: created.status,
            created_at: created.created_at,
            updated_at: created.updated_at,
            last_message_preview: null
          }
        ]);
        setSelectedSession(created);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dashboard failed to load");
    } finally {
      setLoading(false);
    }
  }

  async function handleNewSession() {
    if (!token) {
      return;
    }
    const created = await createSession(token);
    await loadDashboard(created.id);
  }

  async function handleSelectSession(sessionId: number) {
    if (!token) {
      return;
    }
    setSelectedSession(await getSession(sessionId, token));
  }

  async function handleSend(content: string) {
    if (!token || !selectedSession) {
      return;
    }
    setSending(true);
    setError(null);
    try {
      const response = await sendMessage(selectedSession.id, content, token);
      setSelectedSession(response.session);
      await loadDashboard(response.session.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Message could not be delivered");
      if (selectedSession?.id) {
        try {
          setSelectedSession(await getSession(selectedSession.id, token));
        } catch {
          // Keep the current UI state if refresh also fails.
        }
      }
    } finally {
      setSending(false);
    }
  }

  if (!user) {
    return null;
  }

  if (loading && !selectedSession) {
    return <div className="loading-shell">Loading workspace...</div>;
  }

  return (
    <div className="dashboard-shell">
      <Sidebar
        user={user}
        sessions={sessions}
        selectedSessionId={selectedSession?.id}
        onSelectSession={handleSelectSession}
        onNewSession={handleNewSession}
        onLogout={logout}
      />
      <main className="main-panel">
        <MetricsBar metrics={metrics} appointments={appointments} />
        {error ? <div className="error-box">{error}</div> : null}
        <ChatWindow session={selectedSession} user={user} sending={sending} onSend={handleSend} />
      </main>
      <AuditLogPanel logs={logs} appointments={appointments} />
    </div>
  );
}
