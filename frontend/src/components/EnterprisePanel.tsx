import { useEffect, useState } from "react";

import {
  createEnterpriseSession,
  createKnowledgeArticle,
  getEnterpriseSession,
  getEnterpriseOverview,
  listKnowledgeArticles,
  sendEnterpriseMessage,
  searchKnowledgeArticles,
  updateEnterpriseTicket,
  updateEnterpriseTicketStatus,
} from "../api/client";
import type {
  Appointment,
  ChatMessage,
  EnterpriseOverview,
  EnterpriseSessionDetail,
  EnterpriseSessionSummary,
  EnterpriseTicket,
  KnowledgeArticle,
  KnowledgeSearchResult,
} from "../types/api";

const trDateTime = new Intl.DateTimeFormat("tr-TR", { dateStyle: "short", timeStyle: "short" });

type EnterprisePanelProps = {
  token: string;
  appointments: Appointment[];
  locale: string;
};

type CopilotInsights = {
  sentiment?: string;
  risk?: string;
  summary?: string;
  suggested_next_action?: string;
  signals?: string[];
};

type KnowledgeSuggestion = {
  id?: number;
  title?: string;
  content?: string;
  tags?: string[];
  score?: number;
};

export function EnterprisePanel({ token, appointments, locale }: EnterprisePanelProps) {
  const [overview, setOverview] = useState<EnterpriseOverview | null>(null);
  const [selectedSession, setSelectedSession] = useState<EnterpriseSessionDetail | null>(null);
  const [customerName, setCustomerName] = useState("Demo Caller");
  const [customerPhone, setCustomerPhone] = useState("+90 555 444 33 22");
  const [message, setMessage] = useState("");
  const [knowledgeArticles, setKnowledgeArticles] = useState<KnowledgeArticle[]>([]);
  const [knowledgeResults, setKnowledgeResults] = useState<KnowledgeSearchResult[]>([]);
  const [knowledgeQuery, setKnowledgeQuery] = useState("");
  const [articleTitle, setArticleTitle] = useState("");
  const [articleContent, setArticleContent] = useState("");
  const [articleTags, setArticleTags] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [creatingArticle, setCreatingArticle] = useState(false);
  const [updatingTicketId, setUpdatingTicketId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const en = locale === "en";

  useEffect(() => {
    void loadEnterprise();
  }, [token]);

  async function loadEnterprise(nextSession?: EnterpriseSessionDetail) {
    setError(null);
    try {
      const [data, articles] = await Promise.all([getEnterpriseOverview(token), listKnowledgeArticles(token)]);
      setOverview(data);
      setKnowledgeArticles(articles);
      if (nextSession) {
        setSelectedSession(nextSession);
      } else if (!selectedSession && data.sessions.length > 0) {
        setSelectedSession(await getEnterpriseSession(data.sessions[0].id, token));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : en ? "Enterprise panel could not be loaded" : "Enterprise panel yüklenemedi");
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
      setError(err instanceof Error ? err.message : en ? "Enterprise session could not be created" : "Enterprise oturum açılamadı");
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
      setError(err instanceof Error ? err.message : en ? "Session could not be opened" : "Oturum açılamadı");
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
      setError(err instanceof Error ? err.message : en ? "Customer conversation could not be opened" : "Müşteri görüşmesi açılamadı");
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
      setError(err instanceof Error ? err.message : en ? "Ticket status could not be updated" : "Ticket durumu güncellenemedi");
    } finally {
      setUpdatingTicketId(null);
    }
  }

  async function handleTicketUpdate(
    ticket: EnterpriseTicket,
    payload: { priority?: "low" | "normal" | "high" | "urgent"; assigned_agent_id?: number | null }
  ) {
    setUpdatingTicketId(ticket.id);
    setError(null);
    try {
      await updateEnterpriseTicket(ticket.id, payload, token);
      const data = await getEnterpriseOverview(token);
      setOverview(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : en ? "Ticket could not be updated" : "Ticket güncellenemedi");
    } finally {
      setUpdatingTicketId(null);
    }
  }

  async function handleCopyHandoff(ticket: EnterpriseTicket) {
    const copilot = getCopilotInsights(ticket);
    const suggestions = getKnowledgeSuggestions(ticket);
    const lines = [
      `Ticket #${ticket.id}`,
      `${en ? "Customer" : "Müşteri"}: ${ticket.customer.full_name}`,
      `${en ? "Status" : "Durum"}: ${ticketStatusLabel(ticket.status, en)}`,
      `${en ? "Priority" : "Öncelik"}: ${priorityLabel(ticket.priority, en)}`,
      `SLA: ${slaLabel(ticket, en).label}`,
      `${en ? "Department" : "Departman"}: ${ticket.department?.name ?? "General Support"}`,
      `${en ? "Assignee" : "Atanan"}: ${ticket.assigned_agent?.display_name ?? (en ? "Unassigned" : "Atanmamış")}`,
      `${en ? "Intent" : "Niyet"}: ${ticket.intent.replace(/_/g, " ")}`,
      `${en ? "Issue" : "Sorun"}: ${ticket.description}`,
      ...(copilot ? [
        `${en ? "Risk" : "Risk"}: ${riskLabel(copilot.risk, en)}`,
        `${en ? "Sentiment" : "Duygu"}: ${sentimentLabel(copilot.sentiment, en)}`,
        `${en ? "Next action" : "Sonraki aksiyon"}: ${copilot.suggested_next_action ?? copilot.summary ?? "-"}`,
      ] : []),
      ...(suggestions.length ? [
        `${en ? "Matched knowledge" : "Eşleşen bilgi"}: ${suggestions.map((item) => item.title).filter(Boolean).join(", ")}`,
      ] : []),
    ];
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
    } catch {
      setError(en ? "Handoff summary could not be copied" : "Handoff özeti panoya kopyalanamadı");
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
      setError(err instanceof Error ? err.message : en ? "Enterprise message could not be sent" : "Enterprise mesaj gönderilemedi");
    } finally {
      setSending(false);
    }
  }

  async function handleKnowledgeSearch() {
    const query = knowledgeQuery.trim();
    if (!query) {
      setKnowledgeResults([]);
      return;
    }
    setError(null);
    try {
      setKnowledgeResults(await searchKnowledgeArticles(token, query));
    } catch (err) {
      setError(err instanceof Error ? err.message : en ? "Knowledge search failed" : "Bilgi bankası aranamadı");
    }
  }

  async function handleCreateArticle() {
    if (!articleTitle.trim() || !articleContent.trim()) return;
    setCreatingArticle(true);
    setError(null);
    try {
      const created = await createKnowledgeArticle(token, {
        title: articleTitle.trim(),
        content: articleContent.trim(),
        tags: articleTags.split(",").map((tag) => tag.trim()).filter(Boolean),
      });
      setKnowledgeArticles([created, ...knowledgeArticles]);
      setArticleTitle("");
      setArticleContent("");
      setArticleTags("");
    } catch (err) {
      setError(err instanceof Error ? err.message : en ? "Knowledge article could not be saved" : "Bilgi makalesi kaydedilemedi");
    } finally {
      setCreatingArticle(false);
    }
  }

  if (loading && !overview) {
    return <div className="enterprise-panel enterprise-panel--loading">{en ? "Preparing enterprise workspace..." : "Enterprise workspace hazırlanıyor..."}</div>;
  }

  const metrics = overview?.metrics;
  const tickets = overview?.tickets ?? [];
  const departments = overview?.departments ?? [];
  const agents = overview?.agents ?? [];
  const sessions = overview?.sessions ?? [];
  const visibleKnowledge = knowledgeResults.length > 0 ? knowledgeResults : knowledgeArticles.slice(0, 5);

  return (
    <div className="enterprise-panel">
      <div className="enterprise-header">
        <div>
          <div className="enterprise-kicker">Enterprise Mode</div>
          <h2>{metrics?.organization.name ?? "Cognivault Enterprise"}</h2>
          <p>{en ? "Process incoming customer messages in one workspace; AI classifies, routes, and turns them into tickets or appointments." : "Kuruma gelen müşteri mesajlarını tek ekranda işle; AI talebi sınıflandırır, departmana yönlendirir, ticket veya randevu sonucunu görünür kılar."}</p>
        </div>
        <div className="enterprise-header-badge">RBAC · Audited · MVP</div>
      </div>

      {error ? <div className="error-box enterprise-error">{error}</div> : null}

      <div className="enterprise-metrics">
        <MetricCard label={en ? "Open Tickets" : "Açık Ticket"} value={metrics?.open_tickets ?? 0} />
        <MetricCard label={en ? "High Priority" : "Yüksek Öncelik"} value={metrics?.high_priority_tickets ?? 0} tone="warning" />
        <MetricCard label={en ? "SLA Breach" : "SLA Aşımı"} value={metrics?.sla_breached ?? 0} tone="warning" />
        <MetricCard label={en ? "Avg Confidence" : "Ort. Güven"} value={metrics?.avg_confidence ?? 0} suffix="%" tone="success" />
        <MetricCard label={en ? "Active Sessions" : "Aktif Oturum"} value={metrics?.active_sessions ?? 0} />
        <MetricCard label={en ? "Appointments" : "Randevu"} value={metrics?.appointments ?? 0} tone="success" />
      </div>

      <div className="enterprise-grid">
        <section className="enterprise-card enterprise-chat-card">
          <div className="enterprise-card-top">
            <div>
              <span className="enterprise-section-label">{en ? "Incoming Customer Messages" : "Gelen Müşteri Mesajları"}</span>
              <h3>{selectedSession?.customer.full_name ?? "New caller"}</h3>
            </div>
            <span className={`enterprise-status ${selectedSession?.status === "needs_human" ? "danger" : ""}`}>
              {sessionStatusLabel(selectedSession?.status ?? "ready", en)}
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
                      <span>{kind === "customer" ? `${en ? "Customer" : "Müşteri"} · ${selectedSession.customer.full_name}` : `Cognivault AI · ${en ? "Routing decision" : "Routing kararı"}`}</span>
                      <span>{trDateTime.format(new Date(item.created_at))}</span>
                    </div>
                    <p>{item.content}</p>
                  </div>
                );
              })
            ) : (
              <div className="enterprise-empty">{en ? "Write an incoming customer message here; the system will extract intent, department and action." : "Buraya kuruma gelen müşteri mesajını yazın; sistem intent, departman ve aksiyonu çıkaracak."}</div>
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
              placeholder={en ? "Incoming customer message: e.g. Internet is down, I urgently need a human agent..." : "Kuruma gelen müşteri mesajı: Örn. İnternet çalışmıyor, acil insan temsilci istiyorum..."}
              disabled={sending || !selectedSession}
            />
            <button type="button" onClick={handleSend} disabled={sending || !selectedSession || !message.trim()}>
              {en ? "Process" : "İşle"}
            </button>
          </div>
        </section>

        <section className="enterprise-card">
          <div className="enterprise-card-top">
            <div>
              <span className="enterprise-section-label">{en ? "Customer Requests" : "Müşteri Talepleri"}</span>
              <h3>{en ? "Who wrote with what issue?" : "Kim ne sorunla yazdı?"}</h3>
            </div>
          </div>
          <div className="enterprise-ticket-list">
            {tickets.slice(0, 8).map((ticket) => {
              const copilot = getCopilotInsights(ticket);
              const suggestions = getKnowledgeSuggestions(ticket);
              return (
              <article key={ticket.id} className="enterprise-ticket">
                <div className="enterprise-ticket-top">
                  <strong>{ticket.customer.full_name}</strong>
                  <span className={`enterprise-status ${ticket.status === "escalated" ? "danger" : ticket.status === "closed" ? "" : "pending"}`}>
                    {ticketStatusLabel(ticket.status, en)}
                  </span>
                </div>
                <div className="enterprise-ticket-intent">#{ticket.id} · {ticket.intent.replace(/_/g, " ")}</div>
                <div className="enterprise-ticket-badges">
                  <span className={`enterprise-priority ${ticket.priority}`}>{priorityLabel(ticket.priority, en)}</span>
                  <span className={`enterprise-sla ${slaLabel(ticket, en).tone}`}>{slaLabel(ticket, en).label}</span>
                  <span>{ticket.assigned_agent?.display_name ?? (en ? "Unassigned" : "Atanmamış")}</span>
                </div>
                <p><b>{en ? "Issue" : "Sorun"}:</b> {ticket.description}</p>
                <div className="enterprise-ticket-outcome">
                  <span>{en ? "Outcome" : "Sonuç"}</span>
                  <strong>{ticketOutcomeLabel(ticket, en)}</strong>
                </div>
                {copilot ? (
                  <div className="enterprise-copilot">
                    <div className="enterprise-copilot-top">
                      <span className={`enterprise-risk ${copilot.risk ?? "low"}`}>{riskLabel(copilot.risk, en)}</span>
                      <span>{sentimentLabel(copilot.sentiment, en)}</span>
                    </div>
                    <p>{copilot.suggested_next_action ?? copilot.summary}</p>
                    {copilot.signals?.length ? <small>{copilot.signals.slice(0, 4).join(" · ")}</small> : null}
                  </div>
                ) : null}
                {suggestions.length > 0 ? (
                  <div className="enterprise-knowledge-hints">
                    <span>{en ? "Matched knowledge" : "Eşleşen bilgi"}</span>
                    {suggestions.slice(0, 2).map((item) => (
                      <strong key={`${ticket.id}-${item.id ?? item.title}`}>{item.title}</strong>
                    ))}
                  </div>
                ) : null}
                <div className="enterprise-ticket-foot">
                  <span>{ticket.department?.name ?? "General Support"}</span>
                  <span>{ticket.confidence}% confidence</span>
                </div>
                <div className="enterprise-ticket-controls">
                  <label>
                    {en ? "Priority" : "Öncelik"}
                    <select
                      value={ticket.priority}
                      onChange={(event) => void handleTicketUpdate(ticket, { priority: event.target.value as "low" | "normal" | "high" | "urgent" })}
                      disabled={updatingTicketId === ticket.id || ticket.status === "closed"}
                    >
                      <option value="low">{en ? "Low" : "Düşük"}</option>
                      <option value="normal">Normal</option>
                      <option value="high">{en ? "High" : "Yüksek"}</option>
                      <option value="urgent">{en ? "Urgent" : "Acil"}</option>
                    </select>
                  </label>
                  <label>
                    {en ? "Assignee" : "Atanan"}
                    <select
                      value={ticket.assigned_agent?.id ?? ""}
                      onChange={(event) => {
                        const next = Number(event.target.value);
                        void handleTicketUpdate(ticket, { assigned_agent_id: next || null });
                      }}
                      disabled={updatingTicketId === ticket.id || ticket.status === "closed"}
                    >
                      <option value="">{en ? "Unassigned" : "Atanmamış"}</option>
                      {agents.map((agent) => (
                        <option key={agent.id} value={agent.id}>{agent.display_name}</option>
                      ))}
                    </select>
                  </label>
                </div>
                {ticket.handoff_package?.latest_resolution_note ? (
                  <div className="enterprise-ticket-note">{String(ticket.handoff_package.latest_resolution_note)}</div>
                ) : null}
                <div className="enterprise-ticket-actions">
                  <button type="button" onClick={() => void handleOpenTicketSession(ticket)} disabled={!ticket.session_id || updatingTicketId === ticket.id}>
                    {en ? "Open conversation" : "Görüşmeyi aç"}
                  </button>
                  <button type="button" onClick={() => void handleTicketStatus(ticket, "in_progress")} disabled={updatingTicketId === ticket.id || ticket.status === "closed"}>
                    {en ? "Start work" : "İşleme al"}
                  </button>
                  <button className="success" type="button" onClick={() => void handleTicketStatus(ticket, "closed")} disabled={updatingTicketId === ticket.id || ticket.status === "closed"}>
                    {en ? "Resolved" : "Çözüldü"}
                  </button>
                  <button className="danger" type="button" onClick={() => void handleTicketStatus(ticket, "escalated")} disabled={updatingTicketId === ticket.id}>
                    {en ? "Escalate" : "Çözülemedi"}
                  </button>
                  <button type="button" onClick={() => void handleCopyHandoff(ticket)} disabled={updatingTicketId === ticket.id}>
                    {en ? "Copy handoff" : "Handoff kopyala"}
                  </button>
                </div>
              </article>
              );
            })}
            {tickets.length === 0 ? <div className="enterprise-empty">{en ? "No tickets yet." : "Henüz ticket yok."}</div> : null}
          </div>
        </section>

        <section className="enterprise-card">
          <div className="enterprise-card-top">
            <div>
              <span className="enterprise-section-label">Departments</span>
              <h3>{en ? "Routing Map" : "Yönlendirme Haritası"}</h3>
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
              <h3>{en ? "Recent Intake" : "Son Intake"}</h3>
            </div>
          </div>
          <div className="enterprise-session-list">
            {sessions.slice(0, 8).map((session) => (
              <button key={session.id} type="button" className="enterprise-session" onClick={() => void handleSelectSession(session)}>
                <strong>{session.customer.full_name}</strong>
                <span>{session.intent ?? "new"} · {session.department?.name ?? "unassigned"}</span>
                <small>{session.last_message_preview ?? (en ? "No activity" : "Aktivite yok")}</small>
              </button>
            ))}
          </div>
        </section>

        <section className="enterprise-card enterprise-knowledge-card">
          <div className="enterprise-card-top">
            <div>
              <span className="enterprise-section-label">{en ? "Knowledge Base" : "Bilgi Bankası"}</span>
              <h3>{en ? "Reusable answers" : "Tekrar kullanılabilir yanıtlar"}</h3>
            </div>
            <span className="enterprise-status">{knowledgeArticles.length}</span>
          </div>

          <div className="enterprise-knowledge-search">
            <input
              value={knowledgeQuery}
              onChange={(event) => setKnowledgeQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void handleKnowledgeSearch();
              }}
              placeholder={en ? "Search VPN, invoice, appointment..." : "VPN, fatura, randevu ara..."}
            />
            <button type="button" onClick={() => void handleKnowledgeSearch()}>{en ? "Search" : "Ara"}</button>
          </div>

          <div className="enterprise-knowledge-list">
            {visibleKnowledge.map((article) => {
              const score = "score" in article ? (article as KnowledgeSearchResult).score : null;
              return (
                <article key={article.id} className="enterprise-knowledge-item">
                  <div>
                    <strong>{article.title}</strong>
                    {typeof score === "number" ? <span>{score}%</span> : null}
                  </div>
                  <p>{article.content}</p>
                  <small>{article.tags.join(" · ")}</small>
                </article>
              );
            })}
            {visibleKnowledge.length === 0 ? <div className="enterprise-empty">{en ? "No articles yet." : "Henüz makale yok."}</div> : null}
          </div>

          <div className="enterprise-knowledge-create">
            <input value={articleTitle} onChange={(event) => setArticleTitle(event.target.value)} placeholder={en ? "Article title" : "Makale başlığı"} />
            <textarea value={articleContent} onChange={(event) => setArticleContent(event.target.value)} placeholder={en ? "Short playbook or answer..." : "Kısa playbook veya yanıt..."} />
            <input value={articleTags} onChange={(event) => setArticleTags(event.target.value)} placeholder={en ? "tags, comma separated" : "etiketler, virgülle"} />
            <button type="button" onClick={() => void handleCreateArticle()} disabled={creatingArticle || !articleTitle.trim() || !articleContent.trim()}>
              {creatingArticle ? (en ? "Saving..." : "Kaydediliyor...") : (en ? "Add article" : "Makale ekle")}
            </button>
          </div>
        </section>

        <section className="enterprise-card">
          <div className="enterprise-card-top">
            <div>
              <span className="enterprise-section-label">{en ? "Appointment Results" : "Randevu Sonuçları"}</span>
              <h3>{en ? "Did the customer get an appointment?" : "Müşteri randevu alabildi mi?"}</h3>
            </div>
          </div>
          <div className="enterprise-appointment-list">
            {appointments.slice(0, 6).map((appointment) => (
              <article key={appointment.id} className="enterprise-appointment">
                <div className="enterprise-appointment-top">
                  <strong>{appointment.user_name ?? "Müşteri"}</strong>
                  <span className={`enterprise-status ${appointment.status === "confirmed" ? "" : "pending"}`}>
                    {appointmentStatusLabel(appointment.status, en)}
                  </span>
                </div>
                <p>{appointment.department}</p>
                <div className="enterprise-appointment-meta">
                  <span>{appointment.confirmation_code}</span>
                  <span>{trDateTime.format(new Date(appointment.scheduled_at))}</span>
                </div>
              </article>
            ))}
            {appointments.length === 0 ? <div className="enterprise-empty">{en ? "No successful appointments yet." : "Henüz başarılı randevu yok."}</div> : null}
          </div>
        </section>
      </div>
    </div>
  );
}

function enterpriseMessageKind(message: ChatMessage) {
  return message.sender === "user" ? "customer" : "system";
}

function sessionStatusLabel(status: string, en = false) {
  const labels: Record<string, string> = en
    ? { active: "Active", ready: "Ready", needs_human: "Human needed", closed: "Closed" }
    : { active: "Aktif", ready: "Hazır", needs_human: "Temsilci gerekiyor", closed: "Kapandı" };
  return labels[status] ?? status;
}

function ticketOutcomeLabel(ticket: EnterpriseTicket, en = false) {
  if (ticket.status === "closed") return en ? "Problem resolved" : "Problem çözüldü";
  if (ticket.status === "escalated") return en ? "Escalated to a human" : "Çözülemedi, insana aktarıldı";
  if (ticket.status === "in_progress") return en ? "Operator is reviewing" : "Operatör inceliyor";
  return en ? "Waiting" : "Beklemede";
}

function appointmentStatusLabel(status: string, en = false) {
  const labels: Record<string, string> = en
    ? { confirmed: "Booked", pending: "Pending", cancelled: "Cancelled" }
    : { confirmed: "Randevu alındı", pending: "Bekliyor", cancelled: "İptal" };
  return labels[status] ?? status;
}

function ticketStatusLabel(status: string, en = false) {
  const labels: Record<string, string> = en
    ? { open: "Open", in_progress: "In progress", escalated: "Escalated", closed: "Closed" }
    : { open: "Açık", in_progress: "İşlemde", escalated: "Çözülemedi", closed: "Çözüldü" };
  return labels[status] ?? status;
}

function priorityLabel(priority: string, en = false) {
  const labels: Record<string, string> = en
    ? { low: "Low", normal: "Normal", high: "High", urgent: "Urgent" }
    : { low: "Düşük", normal: "Normal", high: "Yüksek", urgent: "Acil" };
  return labels[priority] ?? priority;
}

function slaLabel(ticket: EnterpriseTicket, en = false) {
  if (ticket.status === "closed") return { label: en ? "SLA done" : "SLA tamam", tone: "ok" };
  const created = new Date(ticket.created_at).getTime();
  const elapsedHours = Number.isFinite(created) ? (Date.now() - created) / 36e5 : 0;
  const limits: Record<string, number> = { urgent: 2, high: 4, normal: 24, low: 72 };
  const limit = limits[ticket.priority] ?? limits.normal;
  if (elapsedHours >= limit) return { label: en ? "SLA breached" : "SLA aşıldı", tone: "danger" };
  if (elapsedHours >= limit * 0.75) return { label: en ? "SLA nearing" : "SLA yaklaşıyor", tone: "warning" };
  return { label: en ? `${Math.max(1, Math.ceil(limit - elapsedHours))}h left` : `${Math.max(1, Math.ceil(limit - elapsedHours))}s kaldı`, tone: "ok" };
}

function getCopilotInsights(ticket: EnterpriseTicket): CopilotInsights | null {
  const insights = ticket.handoff_package?.copilot_insights;
  return insights && typeof insights === "object" ? insights as CopilotInsights : null;
}

function getKnowledgeSuggestions(ticket: EnterpriseTicket): KnowledgeSuggestion[] {
  const suggestions = ticket.handoff_package?.knowledge_suggestions;
  return Array.isArray(suggestions) ? suggestions as KnowledgeSuggestion[] : [];
}

function riskLabel(risk: string | undefined, en = false) {
  const labels: Record<string, string> = en
    ? { low: "Low risk", medium: "Medium risk", high: "High risk" }
    : { low: "Düşük risk", medium: "Orta risk", high: "Yüksek risk" };
  return labels[risk ?? "low"] ?? (risk ?? "low");
}

function sentimentLabel(sentiment: string | undefined, en = false) {
  const labels: Record<string, string> = en
    ? { positive: "Positive", neutral: "Neutral", negative: "Negative" }
    : { positive: "Pozitif", neutral: "Nötr", negative: "Negatif" };
  return labels[sentiment ?? "neutral"] ?? (sentiment ?? "neutral");
}

function MetricCard({ label, value, suffix, tone }: { label: string; value: number; suffix?: string; tone?: "success" | "warning" }) {
  return (
    <div className={`enterprise-metric ${tone ?? ""}`}>
      <span>{label}</span>
      <strong>{value}{suffix ?? ""}</strong>
    </div>
  );
}
