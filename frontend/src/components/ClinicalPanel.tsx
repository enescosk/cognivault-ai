import { useEffect, useState } from "react";

import {
  getClinicalConversation,
  getClinicalOverview,
  simulateVoiceCall,
  simulateWhatsAppMessage,
  updateShadowReview,
} from "../api/client";
import type { ClinicalConversationDetail, ClinicalOverview, ClinicalConversationSummary, ShadowReview } from "../types/api";

const trDateTime = new Intl.DateTimeFormat("tr-TR", { dateStyle: "short", timeStyle: "short" });

type ClinicalPanelProps = {
  token: string;
};

export function ClinicalPanel({ token }: ClinicalPanelProps) {
  const [overview, setOverview] = useState<ClinicalOverview | null>(null);
  const [selectedConversation, setSelectedConversation] = useState<ClinicalConversationDetail | null>(null);
  const [phone, setPhone] = useState("+90 555 111 22 33");
  const [patientName, setPatientName] = useState("Ayse Hasta");
  const [body, setBody] = useState("Yarin dermatoloji icin randevu var mi?");
  const [channel, setChannel] = useState<"whatsapp" | "phone">("phone");
  const [personaId, setPersonaId] = useState<"selin" | "arzu" | "can">("selin");
  const [editingReviewId, setEditingReviewId] = useState<number | null>(null);
  const [editedReply, setEditedReply] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadClinical();
  }, [token]);

  async function loadClinical(nextConversationId?: number) {
    setError(null);
    try {
      const data = await getClinicalOverview(token);
      setOverview(data);
      const id = nextConversationId ?? selectedConversation?.id ?? data.conversations[0]?.id;
      if (id) {
        setSelectedConversation(await getClinicalConversation(id, token));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Clinical panel yuklenemedi");
    } finally {
      setLoading(false);
    }
  }

  async function handleSimulate() {
    if (!body.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const result = channel === "phone"
        ? await simulateVoiceCall(token, {
            from_phone: phone.trim(),
            patient_name: patientName.trim() || undefined,
            speech: body.trim(),
            persona_id: personaId,
          })
        : await simulateWhatsAppMessage(token, {
            from_phone: phone.trim(),
            patient_name: patientName.trim() || undefined,
            body: body.trim(),
          });
      await loadClinical(result.conversation_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "WhatsApp mesaji islenemedi");
    } finally {
      setBusy(false);
    }
  }

  async function handleSelect(conversation: ClinicalConversationSummary) {
    setLoading(true);
    try {
      setSelectedConversation(await getClinicalConversation(conversation.id, token));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Konusma acilamadi");
    } finally {
      setLoading(false);
    }
  }

  async function decideReview(review: ShadowReview, status: "approved" | "edited" | "rejected") {
    setBusy(true);
    setError(null);
    try {
      await updateShadowReview(review.id, token, {
        status,
        final_reply: status === "edited" ? editedReply : review.draft_reply,
      });
      setEditingReviewId(null);
      setEditedReply("");
      await loadClinical(review.conversation_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Shadow review guncellenemedi");
    } finally {
      setBusy(false);
    }
  }

  if (loading && !overview) {
    return <div className="clinical-panel clinical-panel--loading">Clinical workspace hazirlaniyor...</div>;
  }

  const metrics = overview?.metrics;
  const conversations = overview?.conversations ?? [];
  const doctorInbox = overview?.doctor_inbox ?? [];
  const reviews = overview?.shadow_reviews ?? [];

  return (
    <div className="clinical-panel">
      <header className="clinical-header">
        <div>
          <div className="clinical-kicker">Clinical Receptionist</div>
          <h2>{metrics?.clinic_name ?? "Demo Klinik"}</h2>
          <p>Medikal arama ve hasta mesajlari; Selin, Arzu ve Can ses personalariyla karsilanir, doktor ekranina guvenli hasta notu olarak duser.</p>
        </div>
        <div className="clinical-header-badge">Phone · Medical AI Voices · Doctor Inbox</div>
      </header>

      {error ? <div className="error-box clinical-error">{error}</div> : null}

      <section className="clinical-metrics">
        <ClinicalMetric label="Bugunku hasta temasi" value={metrics?.conversations_today ?? 0} />
        <ClinicalMetric label="Telefon aramasi" value={metrics?.phone_calls_today ?? 0} />
        <ClinicalMetric label="Doktor ekrani" value={metrics?.doctor_inbox_count ?? 0} tone="warning" />
        <ClinicalMetric label="Yaklasan uyari" value={metrics?.reminders_due ?? 0} tone="success" />
        <ClinicalMetric label="Insan onayi" value={metrics?.pending_shadow_reviews ?? 0} tone="danger" />
      </section>

      <div className="clinical-grid">
        <section className="clinical-card clinical-simulator">
          <div className="clinical-card-top">
            <div>
              <span>Medical call simulator</span>
              <h3>Gelen hasta aramasi</h3>
            </div>
          </div>
          <div className="clinical-form">
            <div className="clinical-segmented">
              <button type="button" className={channel === "phone" ? "active" : ""} onClick={() => setChannel("phone")}>Telefon</button>
              <button type="button" className={channel === "whatsapp" ? "active" : ""} onClick={() => setChannel("whatsapp")}>WhatsApp</button>
            </div>
            <select value={personaId} onChange={(event) => setPersonaId(event.target.value as "selin" | "arzu" | "can")}>
              <option value="selin">Selin - randevu resepsiyonisti</option>
              <option value="arzu">Arzu - sigorta ve operasyon</option>
              <option value="can">Can - medikal guvenlik</option>
            </select>
            <input value={patientName} onChange={(event) => setPatientName(event.target.value)} placeholder="Hasta adi" />
            <input value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="+90..." />
            <textarea value={body} onChange={(event) => setBody(event.target.value)} placeholder="Hastanin telefonda soyledigi medikal talep" />
            <button type="button" onClick={handleSimulate} disabled={busy || !body.trim()}>
              Aramayi isle
            </button>
          </div>

          <div className="clinical-card-top clinical-card-top--spaced">
            <div>
              <span>Doctor inbox</span>
              <h3>Doktora dusenler</h3>
            </div>
          </div>
          <div className="clinical-conversation-list">
            {doctorInbox.map((conversation) => (
              <button
                key={conversation.id}
                type="button"
                className={`clinical-conversation-row doctor ${selectedConversation?.id === conversation.id ? "selected" : ""}`}
                onClick={() => void handleSelect(conversation)}
              >
                <strong>{conversation.patient.full_name ?? conversation.patient.phone}</strong>
                <span>{conversation.channel} · {conversation.persona_name ?? "AI"} · {conversation.status}</span>
                <p>{conversation.last_message_preview ?? "No messages yet"}</p>
              </button>
            ))}
            {doctorInbox.length === 0 ? <div className="clinical-empty">Doktor ekraninda bekleyen hasta yok.</div> : null}
          </div>

          <div className="clinical-card-top clinical-card-top--spaced">
            <div>
              <span>Conversations</span>
              <h3>Tum medikal akis</h3>
            </div>
          </div>
          <div className="clinical-conversation-list">
            {conversations.map((conversation) => (
              <button
                key={conversation.id}
                type="button"
                className={`clinical-conversation-row ${selectedConversation?.id === conversation.id ? "selected" : ""}`}
                onClick={() => void handleSelect(conversation)}
              >
                <strong>{conversation.patient.full_name ?? conversation.patient.phone}</strong>
                <span>{conversation.channel} · {conversation.persona_name ?? "AI"} · {conversation.intent?.replace(/_/g, " ") ?? "intent pending"}</span>
                <p>{conversation.last_message_preview ?? "No messages yet"}</p>
              </button>
            ))}
          </div>
        </section>

        <section className="clinical-card clinical-thread">
          <div className="clinical-card-top">
            <div>
              <span>Live thread</span>
              <h3>{selectedConversation?.patient.full_name ?? "Hasta sec"}</h3>
            </div>
            <strong className={`clinical-status ${selectedConversation?.status === "waiting_human" ? "danger" : ""}`}>
              {selectedConversation?.status ?? "ready"}
            </strong>
          </div>
          <div className="clinical-message-list">
            {selectedConversation?.messages.length ? (
              selectedConversation.messages.map((message) => (
                <article key={message.id} className={`clinical-message ${message.sender}`}>
                  <div>
                    <span>{message.sender}</span>
                    <span>{trDateTime.format(new Date(message.created_at))}</span>
                  </div>
                  <p>{message.content}</p>
                  {message.intent ? <small>{message.intent} · {Math.round((message.confidence_score ?? 0) * 100)}% · {String(message.metadata_json?.persona_name ?? message.metadata_json?.channel ?? "")}</small> : null}
                </article>
              ))
            ) : (
              <div className="clinical-empty">Konusma secildiginde mesajlar burada gorunur.</div>
            )}
          </div>
        </section>

        <section className="clinical-card clinical-shadow">
          <div className="clinical-card-top">
            <div>
              <span>Doctor approval</span>
              <h3>Doktor onayi</h3>
            </div>
          </div>
          <div className="clinical-review-list">
            {reviews.length ? reviews.map((review) => (
              <article key={review.id} className="clinical-review">
                <div className="clinical-review-top">
                  <strong>{review.intent.replace(/_/g, " ")}</strong>
                  <span>{review.channel ?? "medical"} · {review.persona_name ?? "AI"} · {Math.round(review.confidence_score * 100)}%</span>
                </div>
                <p>{review.draft_reply}</p>
                <small>{review.risk_reason}</small>
                {editingReviewId === review.id ? (
                  <textarea value={editedReply} onChange={(event) => setEditedReply(event.target.value)} />
                ) : null}
                <div className="clinical-review-actions">
                  <button type="button" onClick={() => void decideReview(review, "approved")} disabled={busy}>Approve</button>
                  <button type="button" onClick={() => { setEditingReviewId(review.id); setEditedReply(review.draft_reply); }} disabled={busy}>Edit</button>
                  {editingReviewId === review.id ? (
                    <button type="button" onClick={() => void decideReview(review, "edited")} disabled={busy || !editedReply.trim()}>Send edit</button>
                  ) : null}
                  <button type="button" className="danger" onClick={() => void decideReview(review, "rejected")} disabled={busy}>Reject</button>
                </div>
              </article>
            )) : <div className="clinical-empty">Bekleyen Shadow Mode kaydi yok.</div>}
          </div>
        </section>
      </div>
    </div>
  );
}

function ClinicalMetric({ label, value, tone }: { label: string; value: string | number; tone?: "success" | "warning" | "danger" }) {
  return (
    <div className={`clinical-metric ${tone ?? ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
