import { useEffect, useState } from "react";

import {
  createEnterpriseSession,
  getEnterpriseSession,
  getEnterpriseOverview,
  sendEnterpriseMessage,
  updateEnterpriseTicketStatus,
} from "../api/client";
import type {
  Appointment,
  ChatMessage,
  EnterpriseOverview,
  EnterpriseSessionDetail,
  EnterpriseSessionSummary,
  EnterpriseTicket,
} from "../types/api";

const trDateTime = new Intl.DateTimeFormat("tr-TR", { dateStyle: "short", timeStyle: "short" });

type EnterprisePanelProps = {
  token: string;
  appointments: Appointment[];
};

export function EnterprisePanel({ token, appointments }: EnterprisePanelProps) {
  const [overview, setOverview] = useState<EnterpriseOverview | null>(null);
  const [selectedSession, setSelectedSession] = useState<EnterpriseSessionDetail | null>(null);
  const [customerName, setCustomerName] = useState("Demo Caller");
  const [customerPhone, setCustomerPhone] = useState("+90 555 444 33 22");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [updatingTicketId, setUpdatingTicketId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadEnterprise();
  }, [token]);

  async function loadEnterprise(nextSession?: EnterpriseSessionDetail) {
    setError(null);
    try {
      const data = await getEnterpriseOverview(token);
      setOverview(data);
      if (nextSession) {
        setSelectedSession(nextSession);
      } else if (!selectedSession && data.sessions.length > 0) {
        setSelectedSession(await getEnterpriseSession(data.sessions[0].id, token));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Enterprise panel yüklenemedi");
    } finally {
      setLoading(false);
    }
  }

  async function handleCreateSession() {
    setLoading(true);
    try {
      const created = await createEnterpriseSession(token, {
        customer_name: customerName.trim() || "Demo Caller",
        customer_phone: customerPhone.trim() || undefined,
      });
      await loadEnterprise(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Enterprise oturum açılamadı");
    } finally {
      setLoading(false);
    }
  }

  async function handleSelectSession(session: EnterpriseSessionSummary) {
    setLoading(true);
    try {
      const detail = await getEnterpriseSession(session.id, token);
      setSelectedSession(detail);
      await loadEnterprise(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Oturum açılamadı");
    } finally {
      setLoading(false);
    }
  }

  async function handleOpenTicketSession(ticket: EnterpriseTicket) {
    if (!ticket.session_id) return;
    setLoading(true);
    setError(null);
    try {
      const detail = await getEnterpriseSession(ticket.session_id, token);
      setSelectedSession(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Müşteri görüşmesi açılamadı");
    } finally {
      setLoading(false);
    }
  }

  async function handleTicketStatus(ticket: EnterpriseTicket, status: "in_progress" | "escalated" | "closed") {
    setUpdatingTicketId(ticket.id);
    setError(null);
    const note = status === "closed"
      ? "Operator marked the customer issue as resolved."
      : status === "escalated"
        ? "Operator marked the issue as unresolved and escalated."
        : "Operator started working on the issue.";
    try {
      await updateEnterpriseTicketStatus(ticket.id, status, token, note);
      const data = await getEnterpriseOverview(token);
      setOverview(data);
      if (ticket.session_id && selectedSession?.id === ticket.session_id) {
        setSelectedSession(await getEnterpriseSession(ticket.session_id, token));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ticket durumu güncellenemedi");
    } finally {
      setUpdatingTicketId(null);
    }
  }

  async function handleSend() {
    if (!selectedSession || !message.trim()) return;
    const content = message.trim();
    setMessage("");
    setSending(true);
    setError(null);
    try {
      const response = await sendEnterpriseMessage(selectedSession.id, content, token);
      setSelectedSession(response.session);
      setOverview(await getEnterpriseOverview(token));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Enterprise mesaj gönderilemedi");
    } finally {
      setSending(false);
    }
  }

  if (loading && !overview) {
    return <div className="enterprise-panel enterprise-panel--loading">Enterprise workspace hazırlanıyor...</div>;
  }

  const metrics = overview?.metrics;
  const tickets = overview?.tickets ?? [];
  const departments = overview?.departments ?? [];
  const sessions = overview?.sessions ?? [];

  return (
    <div className="enterprise-panel">
      <div className="enterprise-header">
        <div>
          <div className="enterprise-kicker">Enterprise Mode</div>
          <h2>{metrics?.organization.name ?? "Cognivault Enterprise"}</h2>
          <p>Kuruma gelen müşteri mesajlarını tek ekranda işle; AI talebi sınıflandırır, departmana yönlendirir, ticket veya randevu sonucunu görünür kılar.</p>
        </div>
        <div className="enterprise-header-badge">RBAC · Audited · MVP</div>
      </div>

      {error ? <div className="error-box enterprise-error">{error}</div> : null}

      <div className="enterprise-metrics">
        <MetricCard label="Tickets" value={metrics?.total_tickets ?? 0} />
        <MetricCard label="Active Sessions" value={metrics?.active_sessions ?? 0} />
        <MetricCard label="Escalations" value={metrics?.escalations ?? 0} tone="warning" />
        <MetricCard label="Appointments" value={metrics?.appointments ?? 0} tone="success" />
      </div>

      <div className="enterprise-grid">
        <section className="enterprise-card enterprise-chat-card">
          <div className="enterprise-card-top">
            <div>
              <span className="enterprise-section-label">Gelen Müşteri Mesajları</span>
              <h3>{selectedSession?.customer.full_name ?? "New caller"}</h3>
            </div>
            <span className={`enterprise-status ${selectedSession?.status === "needs_human" ? "danger" : ""}`}>
              {sessionStatusLabel(selectedSession?.status ?? "ready")}
            </span>
          </div>

          <div className="enterprise-intake-form">
            <input value={customerName} onChange={(event) => setCustomerName(event.target.value)} placeholder="Customer name" />
            <input value={customerPhone} onChange={(event) => setCustomerPhone(event.target.value)} placeholder="Phone" />
            <button type="button" onClick={handleCreateSession}>New Intake</button>
          </div>

          <div className="enterprise-message-list">
            {selectedSession?.messages.length ? (
              selectedSession.messages.map((item) => {
                const kind = enterpriseMessageKind(item);
                return (
                  <div key={item.id} className={`enterprise-message ${kind}`}>
                    <div className="enterprise-message-meta">
                      <span>{kind === "customer" ? `Müşteri · ${selectedSession.customer.full_name}` : "Cognivault AI · Routing kararı"}</span>
                      <span>{trDateTime.format(new Date(item.created_at))}</span>
                    </div>
                    <p>{item.content}</p>
                  </div>
                );
              })
            ) : (
              <div className="enterprise-empty">Buraya kuruma gelen müşteri mesajını yazın; sistem intent, departman ve aksiyonu çıkaracak.</div>
            )}
          </div>

          <div className="enterprise-composer">
            <textarea
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void handleSend();
                }
              }}
              placeholder="Kuruma gelen müşteri mesajı: Örn. İnternet çalışmıyor, acil insan temsilci istiyorum..."
              disabled={sending || !selectedSession}
            />
            <button type="button" onClick={handleSend} disabled={sending || !selectedSession || !message.trim()}>
              İşle
            </button>
          </div>
        </section>

        <section className="enterprise-card">
          <div className="enterprise-card-top">
            <div>
              <span className="enterprise-section-label">Müşteri Talepleri</span>
              <h3>Kim ne sorunla yazdı?</h3>
            </div>
          </div>
          <div className="enterprise-ticket-list">
            {tickets.slice(0, 8).map((ticket) => (
              <article key={ticket.id} className="enterprise-ticket">
                <div className="enterprise-ticket-top">
                  <strong>{ticket.customer.full_name}</strong>
                  <span className={`enterprise-status ${ticket.status === "escalated" ? "danger" : ticket.status === "closed" ? "" : "pending"}`}>
                    {ticketStatusLabel(ticket.status)}
                  </span>
                </div>
                <div className="enterprise-ticket-intent">#{ticket.id} · {ticket.intent.replace(/_/g, " ")}</div>
                <p><b>Sorun:</b> {ticket.description}</p>
                <div className="enterprise-ticket-outcome">
                  <span>Sonuç</span>
                  <strong>{ticketOutcomeLabel(ticket)}</strong>
                </div>
                <div className="enterprise-ticket-foot">
                  <span>{ticket.department?.name ?? "General Support"}</span>
                  <span>{ticket.confidence}% confidence</span>
                </div>
                {ticket.handoff_package?.latest_resolution_note ? (
                  <div className="enterprise-ticket-note">{String(ticket.handoff_package.latest_resolution_note)}</div>
                ) : null}
                <div className="enterprise-ticket-actions">
                  <button type="button" onClick={() => void handleOpenTicketSession(ticket)} disabled={!ticket.session_id || updatingTicketId === ticket.id}>
                    Görüşmeyi aç
                  </button>
                  <button type="button" onClick={() => void handleTicketStatus(ticket, "in_progress")} disabled={updatingTicketId === ticket.id || ticket.status === "closed"}>
                    İşleme al
                  </button>
                  <button className="success" type="button" onClick={() => void handleTicketStatus(ticket, "closed")} disabled={updatingTicketId === ticket.id || ticket.status === "closed"}>
                    Çözüldü
                  </button>
                  <button className="danger" type="button" onClick={() => void handleTicketStatus(ticket, "escalated")} disabled={updatingTicketId === ticket.id}>
                    Çözülemedi
                  </button>
                </div>
              </article>
            ))}
            {tickets.length === 0 ? <div className="enterprise-empty">No tickets yet.</div> : null}
          </div>
        </section>

        <section className="enterprise-card">
          <div className="enterprise-card-top">
            <div>
              <span className="enterprise-section-label">Departments</span>
              <h3>Routing Map</h3>
            </div>
          </div>
          <div className="enterprise-department-list">
            {departments.map((department) => (
              <div key={department.id} className="enterprise-department">
                <strong>{department.name}</strong>
                <span>{department.description}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="enterprise-card">
          <div className="enterprise-card-top">
            <div>
              <span className="enterprise-section-label">Sessions</span>
              <h3>Recent Intake</h3>
            </div>
          </div>
          <div className="enterprise-session-list">
            {sessions.slice(0, 8).map((session) => (
              <button key={session.id} type="button" className="enterprise-session" onClick={() => void handleSelectSession(session)}>
                <strong>{session.customer.full_name}</strong>
                <span>{session.intent ?? "new"} · {session.department?.name ?? "unassigned"}</span>
                <small>{session.last_message_preview ?? "No activity"}</small>
              </button>
            ))}
          </div>
        </section>

        <section className="enterprise-card">
          <div className="enterprise-card-top">
            <div>
              <span className="enterprise-section-label">Randevu Sonuçları</span>
              <h3>Müşteri randevu alabildi mi?</h3>
            </div>
          </div>
          <div className="enterprise-appointment-list">
            {appointments.slice(0, 6).map((appointment) => (
              <article key={appointment.id} className="enterprise-appointment">
                <div className="enterprise-appointment-top">
                  <strong>{appointment.user_name ?? "Müşteri"}</strong>
                  <span className={`enterprise-status ${appointment.status === "confirmed" ? "" : "pending"}`}>
                    {appointmentStatusLabel(appointment.status)}
                  </span>
                </div>
                <p>{appointment.department}</p>
                <div className="enterprise-appointment-meta">
                  <span>{appointment.confirmation_code}</span>
                  <span>{trDateTime.format(new Date(appointment.scheduled_at))}</span>
                </div>
              </article>
            ))}
            {appointments.length === 0 ? <div className="enterprise-empty">Henüz başarılı randevu yok.</div> : null}
          </div>
        </section>
      </div>
    </div>
  );
}

function enterpriseMessageKind(message: ChatMessage) {
  return message.sender === "user" ? "customer" : "system";
}

function sessionStatusLabel(status: string) {
  const labels: Record<string, string> = {
    active: "Aktif",
    ready: "Hazır",
    needs_human: "Temsilci gerekiyor",
    closed: "Kapandı",
  };
  return labels[status] ?? status;
}

function ticketOutcomeLabel(ticket: EnterpriseTicket) {
  if (ticket.status === "closed") return "Problem çözüldü";
  if (ticket.status === "escalated") return "Çözülemedi, insana aktarıldı";
  if (ticket.status === "in_progress") return "Operatör inceliyor";
  return "Beklemede";
}

function appointmentStatusLabel(status: string) {
  const labels: Record<string, string> = {
    confirmed: "Randevu alındı",
    pending: "Bekliyor",
    cancelled: "İptal",
  };
  return labels[status] ?? status;
}

function ticketStatusLabel(status: string) {
  const labels: Record<string, string> = {
    open: "Açık",
    in_progress: "İşlemde",
    escalated: "Çözülemedi",
    closed: "Çözüldü",
  };
  return labels[status] ?? status;
}

function MetricCard({ label, value, tone }: { label: string; value: number; tone?: "success" | "warning" }) {
  return (
    <div className={`enterprise-metric ${tone ?? ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
