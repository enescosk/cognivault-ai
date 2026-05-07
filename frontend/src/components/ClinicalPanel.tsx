import { useEffect, useMemo, useState } from "react";

import {
  getClinicalConversation,
  getClinicalOverview,
  simulateVoiceCall,
  simulateWhatsAppMessage,
  updateShadowReview,
} from "../api/client";
import type { ClinicalConversationDetail, ClinicalConversationSummary, ClinicalOverview, ShadowReview } from "../types/api";

const trDateTime = new Intl.DateTimeFormat("tr-TR", { dateStyle: "short", timeStyle: "short" });

type ClinicalPanelProps = {
  token: string;
};

type PersonaId = "selin" | "arzu" | "can";
type ChannelMode = "phone" | "whatsapp";
type PossibleCondition = {
  label?: string;
  rationale?: string;
  urgency?: string;
  confidence?: number;
};
type TriageInfo = {
  urgency?: string;
  red_flags?: string[];
  possible_conditions?: PossibleCondition[];
  recommended_action?: string;
  doctor_summary?: string;
  follow_up_questions?: string[];
  safety_disclaimer?: string;
  source?: string;
};

const personaCards: Array<{
  id: PersonaId;
  name: string;
  title: string;
  voice: string;
  description: string;
}> = [
  {
    id: "selin",
    name: "Selin",
    title: "Randevu resepsiyonisti",
    voice: "Sicak ve hizli",
    description: "Diş taşı, implant kontrolü, dermatoloji ve genel muayene randevularını toplar.",
  },
  {
    id: "arzu",
    name: "Arzu",
    title: "Sigorta ve klinik operasyon",
    voice: "Net ve guven veren",
    description: "Fiyat, SGK, özel sigorta, ödeme ve şube bilgilerini kontrollü cevaplar.",
  },
  {
    id: "can",
    name: "Can",
    title: "Medikal guvenlik",
    voice: "Sakin ve ciddi",
    description: "Acil veya riskli ifadeleri yakalar, doktora öncelikli not düşer.",
  },
];

const roleCards = [
  {
    title: "Hasta",
    metric: "Telefon / WhatsApp",
    text: "Yeni uygulama indirmez. Kliniği arar veya WhatsApp yazar; AI karşılar.",
  },
  {
    title: "Resepsiyon",
    metric: "Canli masa",
    text: "AI'ın topladığı bilgiyi görür, randevu ve geri dönüş akışını tamamlar.",
  },
  {
    title: "Doktor",
    metric: "Doctor Inbox",
    text: "Sadece tıbbi önem taşıyan özetleri ve yaklaşan randevu notlarını görür.",
  },
  {
    title: "Klinik sahibi",
    metric: "Doluluk & kacirilan arama",
    text: "Kaçan arama, dönüşen randevu ve memnuniyetsiz hasta riskini takip eder.",
  },
];

function getTriage(value: Record<string, unknown> | null | undefined): TriageInfo | null {
  const triage = value?.triage;
  if (!triage || typeof triage !== "object") return null;
  return triage as TriageInfo;
}

function getConditions(value: Array<Record<string, unknown>> | undefined, fallback?: TriageInfo | null): PossibleCondition[] {
  if (value?.length) return value as PossibleCondition[];
  return fallback?.possible_conditions ?? [];
}

function formatUrgency(value?: string | null) {
  if (!value) return "rutin";
  return value.replace(/_/g, " ");
}

export function ClinicalPanel({ token }: ClinicalPanelProps) {
  const [overview, setOverview] = useState<ClinicalOverview | null>(null);
  const [selectedConversation, setSelectedConversation] = useState<ClinicalConversationDetail | null>(null);
  const [phone, setPhone] = useState("+90 555 111 22 33");
  const [patientName, setPatientName] = useState("Ayse Hasta");
  const [body, setBody] = useState("Dis agrim var, yarin bir doktor gorebilir mi?");
  const [channel, setChannel] = useState<ChannelMode>("phone");
  const [personaId, setPersonaId] = useState<PersonaId>("selin");
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
      const id = nextConversationId ?? selectedConversation?.id ?? data.doctor_inbox[0]?.id ?? data.conversations[0]?.id;
      if (id) {
        setSelectedConversation(await getClinicalConversation(id, token));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Klinik paneli yuklenemedi");
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
      setError(err instanceof Error ? err.message : "Hasta talebi islenemedi");
    } finally {
      setBusy(false);
    }
  }

  async function handleSelect(conversation: ClinicalConversationSummary) {
    setLoading(true);
    try {
      setSelectedConversation(await getClinicalConversation(conversation.id, token));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Hasta kaydi acilamadi");
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
      setError(err instanceof Error ? err.message : "Doktor onayi guncellenemedi");
    } finally {
      setBusy(false);
    }
  }

  const metrics = overview?.metrics;
  const conversations = overview?.conversations ?? [];
  const doctorInbox = overview?.doctor_inbox ?? [];
  const reviews = overview?.shadow_reviews ?? [];

  const selectedPersona = useMemo(
    () => personaCards.find((persona) => persona.id === personaId) ?? personaCards[0],
    [personaId],
  );

  if (loading && !overview) {
    return <div className="clinical-panel clinical-panel--loading">Butik klinik paneli hazirlaniyor...</div>;
  }

  return (
    <div className="clinical-panel boutique-clinic-panel">
      <section className="clinic-hero">
        <div className="clinic-hero-copy">
          <div className="clinical-kicker">CogniVault Medical</div>
          <h2>Butik klinikler ve dis hekimleri icin AI resepsiyon</h2>
          <p>
            Telefonu ve WhatsApp'i kacirmayan; hastayi karsilayan, doktor ekranina ozet dusen
            ve randevu yaklasinca klinigi uyaran medikal operasyon masasi.
          </p>
        </div>
        <div className="clinic-hero-panel">
          <span>Ilk hedef pazar</span>
          <strong>Dis klinikleri · dermatoloji · estetik · kucuk ozel klinikler</strong>
          <p>Baslangic stratejisi: once butik kliniklerde cok iyi calisan dar ama premium urun.</p>
        </div>
      </section>

      {error ? <div className="error-box clinical-error">{error}</div> : null}

      <section className="clinic-metric-strip">
        <ClinicalMetric label="Bugunku hasta temasi" value={metrics?.conversations_today ?? 0} />
        <ClinicalMetric label="Telefon aramasi" value={metrics?.phone_calls_today ?? 0} />
        <ClinicalMetric label="Doktor ekraninda" value={metrics?.doctor_inbox_count ?? 0} tone="warning" />
        <ClinicalMetric label="Yaklasan uyari" value={metrics?.reminders_due ?? 0} tone="success" />
        <ClinicalMetric label="Doktor onayi" value={metrics?.pending_shadow_reviews ?? 0} tone="danger" />
      </section>

      <section className="clinic-workspace-grid">
        <div className="clinic-card clinic-call-card">
          <div className="clinical-card-top">
            <div>
              <span>Hasta girisi</span>
              <h3>Telefon veya WhatsApp simule et</h3>
            </div>
            <b>{selectedPersona.name}</b>
          </div>

          <div className="clinical-segmented">
            <button type="button" className={channel === "phone" ? "active" : ""} onClick={() => setChannel("phone")}>
              Telefon
            </button>
            <button type="button" className={channel === "whatsapp" ? "active" : ""} onClick={() => setChannel("whatsapp")}>
              WhatsApp
            </button>
          </div>

          <div className="persona-selector">
            {personaCards.map((persona) => (
              <button
                key={persona.id}
                type="button"
                className={persona.id === personaId ? "active" : ""}
                onClick={() => setPersonaId(persona.id)}
              >
                <strong>{persona.name}</strong>
                <span>{persona.title}</span>
              </button>
            ))}
          </div>

          <div className="clinical-form">
            <input value={patientName} onChange={(event) => setPatientName(event.target.value)} placeholder="Hasta adi" />
            <input value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="+90..." />
            <textarea value={body} onChange={(event) => setBody(event.target.value)} placeholder="Hastanin soyledigi medikal talep" />
            <button type="button" onClick={handleSimulate} disabled={busy || !body.trim()}>
              Talebi klinik akisa dusur
            </button>
          </div>
        </div>

        <div className="clinic-card doctor-inbox-card">
          <div className="clinical-card-top">
            <div>
              <span>Doctor Inbox</span>
              <h3>Doktora dusen hasta ozetleri</h3>
            </div>
          </div>
          <ConversationList
            conversations={doctorInbox}
            selectedId={selectedConversation?.id}
            empty="Doktor ekraninda bekleyen hasta yok."
            onSelect={handleSelect}
          />
        </div>

        <div className="clinic-card live-chart-card">
          <div className="clinical-card-top">
            <div>
              <span>Canli hasta kaydi</span>
              <h3>{selectedConversation?.patient.full_name ?? "Hasta sec"}</h3>
            </div>
            <strong className={`clinical-status ${selectedConversation?.status === "waiting_human" ? "danger" : ""}`}>
              {selectedConversation?.status ?? "hazir"}
            </strong>
          </div>
          <div className="clinical-message-list">
            {selectedConversation?.messages.length ? (
              selectedConversation.messages.map((message) => {
                const triage = getTriage(message.metadata_json);
                const conditions = getConditions(undefined, triage);
                return (
                  <article key={message.id} className={`clinical-message ${message.sender}`}>
                    <div>
                      <span>{message.sender}</span>
                      <span>{trDateTime.format(new Date(message.created_at))}</span>
                    </div>
                    <p>{message.content}</p>
                    {message.intent ? (
                      <small>
                        {message.intent} · {Math.round((message.confidence_score ?? 0) * 100)}% ·{" "}
                        {String(message.metadata_json?.persona_name ?? message.metadata_json?.channel ?? "")}
                      </small>
                    ) : null}
                    {triage ? (
                      <div className="triage-strip">
                        <b>{formatUrgency(triage.urgency)}</b>
                        <span>{conditions.slice(0, 2).map((item) => item.label).filter(Boolean).join(" · ") || "Doktor değerlendirmesi"}</span>
                      </div>
                    ) : null}
                  </article>
                );
              })
            ) : (
              <div className="clinical-empty">Hasta secildiginde arama ve mesaj gecmisi burada gorunur.</div>
            )}
          </div>
        </div>
      </section>

      <section className="clinic-product-grid">
        <div className="clinic-card">
          <div className="clinical-card-top">
            <div>
              <span>Kullanici ekranlari</span>
              <h3>Kim ne gorur?</h3>
            </div>
          </div>
          <div className="role-compare-grid">
            {roleCards.map((role) => (
              <article key={role.title} className="role-card">
                <span>{role.metric}</span>
                <strong>{role.title}</strong>
                <p>{role.text}</p>
              </article>
            ))}
          </div>
        </div>

        <div className="clinic-card">
          <div className="clinical-card-top">
            <div>
              <span>Kanallar</span>
              <h3>Telefon ve WhatsApp nasil baglanacak?</h3>
            </div>
          </div>
          <div className="channel-decision-list">
            <article>
              <b>Telefon: Twilio Voice</b>
              <p>Klinik numarasi Twilio'ya yonlenir. Gelen cagri `/api/webhooks/voice/incoming` endpoint'ine gelir.</p>
            </article>
            <article>
              <b>WhatsApp MVP: Twilio Sandbox</b>
              <p>Ilk klinik demolarinda hizli test. Gelen mesaj `/api/webhooks/whatsapp` endpoint'ine duser.</p>
            </article>
            <article>
              <b>WhatsApp Production: Meta Cloud API</b>
              <p>Onay ve isletme dogrulamasi tamamlaninca ayni clinical pipeline Meta webhook ile calisir.</p>
            </article>
          </div>
        </div>

        <div className="clinic-card">
          <div className="clinical-card-top">
            <div>
              <span>AI sesleri</span>
              <h3>Medikal persona seti</h3>
            </div>
          </div>
          <div className="persona-detail-list">
            {personaCards.map((persona) => (
              <article key={persona.id} className={persona.id === personaId ? "active" : ""}>
                <strong>{persona.name}</strong>
                <span>{persona.voice}</span>
                <p>{persona.description}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="clinic-bottom-grid">
        <div className="clinic-card">
          <div className="clinical-card-top">
            <div>
              <span>Tum akis</span>
              <h3>Hasta temaslari</h3>
            </div>
          </div>
          <ConversationList
            conversations={conversations}
            selectedId={selectedConversation?.id}
            empty="Henuz hasta temasi yok."
            onSelect={handleSelect}
          />
        </div>

        <div className="clinic-card">
          <div className="clinical-card-top">
            <div>
              <span>Doktor onayi</span>
              <h3>Riskli veya belirsiz cevaplar</h3>
            </div>
          </div>
          <div className="clinical-review-list">
            {reviews.length ? reviews.map((review) => {
              const triage = getTriage(review.metadata_json);
              const conditions = getConditions(review.metadata_json?.possible_conditions as Array<Record<string, unknown>> | undefined, triage);
              return (
                <article key={review.id} className="clinical-review">
                  <div className="clinical-review-top">
                    <strong>{review.intent.replace(/_/g, " ")}</strong>
                    <span>{review.channel ?? "medical"} · {review.persona_name ?? "AI"} · {Math.round(review.confidence_score * 100)}%</span>
                  </div>
                  {triage ? (
                    <div className="doctor-brief">
                      <b>Aciliyet: {formatUrgency(triage.urgency)}</b>
                      <p>{triage.doctor_summary ?? String(review.metadata_json?.doctor_summary ?? "")}</p>
                      <span>{conditions.slice(0, 3).map((item) => item.label).filter(Boolean).join(" · ") || "Olası kategori yok"}</span>
                    </div>
                  ) : null}
                  <p>{review.draft_reply}</p>
                  <small>{review.risk_reason}</small>
                  {editingReviewId === review.id ? (
                    <textarea value={editedReply} onChange={(event) => setEditedReply(event.target.value)} />
                  ) : null}
                  <div className="clinical-review-actions">
                    <button type="button" onClick={() => void decideReview(review, "approved")} disabled={busy}>Onayla</button>
                    <button type="button" onClick={() => { setEditingReviewId(review.id); setEditedReply(review.draft_reply); }} disabled={busy}>Duzenle</button>
                    {editingReviewId === review.id ? (
                      <button type="button" onClick={() => void decideReview(review, "edited")} disabled={busy || !editedReply.trim()}>Duzenlemeyi gonder</button>
                    ) : null}
                    <button type="button" className="danger" onClick={() => void decideReview(review, "rejected")} disabled={busy}>Reddet</button>
                  </div>
                </article>
              );
            }) : <div className="clinical-empty">Doktor onayi bekleyen kayit yok.</div>}
          </div>
        </div>
      </section>
    </div>
  );
}

function ConversationList({
  conversations,
  selectedId,
  empty,
  onSelect,
}: {
  conversations: ClinicalConversationSummary[];
  selectedId?: number;
  empty: string;
  onSelect: (conversation: ClinicalConversationSummary) => void;
}) {
  if (conversations.length === 0) {
    return <div className="clinical-empty">{empty}</div>;
  }

  return (
    <div className="clinical-conversation-list">
      {conversations.map((conversation) => (
        <button
          key={conversation.id}
          type="button"
          className={`clinical-conversation-row ${conversation.doctor_inbox ? "doctor" : ""} ${selectedId === conversation.id ? "selected" : ""}`}
          onClick={() => void onSelect(conversation)}
        >
          <strong>{conversation.patient.full_name ?? conversation.patient.phone}</strong>
          <span>
            {conversation.channel} · {conversation.persona_name ?? "AI"} · {conversation.intent?.replace(/_/g, " ") ?? "intent pending"}
          </span>
          {conversation.last_urgency ? (
            <em>
              {formatUrgency(conversation.last_urgency)} ·{" "}
              {(conversation.possible_conditions ?? []).slice(0, 2).map((item) => String(item.label ?? "")).filter(Boolean).join(" · ") || "doktor ozeti hazir"}
            </em>
          ) : null}
          <p>{conversation.last_message_preview ?? "No messages yet"}</p>
        </button>
      ))}
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
