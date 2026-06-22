import { useEffect, useMemo, useState } from "react";

import {
  createClinicalAppointment,
  getClinicalConversation,
  getClinicalDoctors,
  getClinicalOverview,
  getDoctorSlots,
  getUpcomingClinicalAppointments,
  simulateVoiceCall,
  simulateWhatsAppMessage,
  updateClinicalAppointmentStatus,
  updateShadowReview,
} from "../api/client";
import type {
  ClinicalAppointment,
  ClinicDoctor,
  ClinicDoctorSlot,
  ClinicalConversationDetail,
  ClinicalConversationSummary,
  ClinicalMessage,
  ClinicalOverview,
  ShadowReview,
} from "../types/api";

const trDateTime = new Intl.DateTimeFormat("tr-TR", { dateStyle: "short", timeStyle: "short" });
const trTime = new Intl.DateTimeFormat("tr-TR", { hour: "2-digit", minute: "2-digit" });

type ClinicalPanelProps = {
  token: string;
};

type PersonaId = "selin" | "arzu" | "can";
type ChannelMode = "phone" | "whatsapp";
type WorkspaceView = "reception" | "doctor" | "owner";
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
type AppointmentDraft = {
  id?: number;
  department?: string;
  starts_at?: string | null;
  status?: string;
  missing_fields?: string[];
  source?: string;
};

const personaCards: Array<{
  id: PersonaId;
  name: string;
  title: string;
  voice: string;
  description: string;
  guardrail: string;
}> = [
  {
    id: "selin",
    name: "Selin",
    title: "Randevu resepsiyonisti",
    voice: "Sicak, hizli, net",
    description: "Telefon veya WhatsApp'tan gelen randevu talebini toparlar, eksik bilgiyi sorar.",
    guardrail: "Medikal tavsiye vermez; belirti gelirse Can'a devreder.",
  },
  {
    id: "arzu",
    name: "Arzu",
    title: "Sigorta ve klinik operasyon",
    voice: "Guven veren, prosedurel",
    description: "Fiyat, SGK, ozel sigorta, sube ve operasyon sorularini kontrollu cevaplar.",
    guardrail: "Kesin fiyat veya kapsam sozu vermez; politika verisi yoksa onaya dusurur.",
  },
  {
    id: "can",
    name: "Can",
    title: "Medikal guvenlik sorumlusu",
    voice: "Sakin, ciddi, hekim odakli",
    description: "Belirti, aciliyet, kirmizi bayrak ve doktor brifini olusturur.",
    guardrail: "Tani koymaz; olasi kategorileri doktor onayi icin ayirir.",
  },
];

const quickScenarios: Array<{
  label: string;
  channel: ChannelMode;
  persona: PersonaId;
  patient: string;
  phone: string;
  body: string;
}> = [
  {
    label: "Diş ağrısı + şişlik",
    channel: "phone",
    persona: "can",
    patient: "Melis Hasta",
    phone: "+90 555 707 80 90",
    body: "Dis agrim ve sislik var, implant bolgesi de agriyor. Bugun doktor gorebilir mi?",
  },
  {
    label: "Randevu toplama",
    channel: "whatsapp",
    persona: "selin",
    patient: "Ayse Hasta",
    phone: "+90 555 111 22 33",
    body: "Yarin dis tasi temizligi icin musait randevu var mi?",
  },
  {
    label: "Sigorta sorusu",
    channel: "whatsapp",
    persona: "arzu",
    patient: "Mehmet Hasta",
    phone: "+90 555 222 44 55",
    body: "Implant muayenesinde tamamlayici sigorta veya SGK geciyor mu?",
  },
  {
    label: "Acil red flag",
    channel: "phone",
    persona: "can",
    patient: "Acil Hasta",
    phone: "+90 555 404 50 60",
    body: "Gogsumde agri var ve nefes darligi yasiyorum, ne yapmaliyim?",
  },
];

const roleCards = [
  {
    id: "reception" as WorkspaceView,
    title: "Resepsiyon",
    metric: "Canli hasta masasi",
    text: "Arama ve WhatsApp tek kuyrukta toplanir; eksik bilgiler ve randevu aksiyonlari gorunur.",
  },
  {
    id: "doctor" as WorkspaceView,
    title: "Doktor",
    metric: "Medikal brif",
    text: "Sadece anlamli hasta ozetleri, aciliyet ve kirmizi bayrak bilgisi doktor ekranina duser.",
  },
  {
    id: "owner" as WorkspaceView,
    title: "Klinik sahibi",
    metric: "Doluluk & guven",
    text: "Kacan temas, doktor onayi, auto reply orani ve randevu uyarilari tek yerde izlenir.",
  },
];

const architectureLanes = [
  { title: "Telefon", text: "Twilio Voice gelen aramayi webhook'a tasir; ses metne cevrilir." },
  { title: "WhatsApp", text: "Twilio Sandbox ile MVP, Meta Cloud API ile production kanalina gecis." },
  { title: "Clinical AI", text: "Intent, persona, structured triyaj, confidence ve safety karar katmani." },
  { title: "Doctor Inbox", text: "Riskli veya belirsiz cevap insana duser; doktor onayi kayit altina alinir." },
  { title: "DB & Audit", text: "Hasta, mesaj, randevu, shadow review ve reminder verisi iliskili saklanir." },
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

function getAppointmentDraft(value: Record<string, unknown> | null | undefined): AppointmentDraft | null {
  if (!value || typeof value !== "object") return null;
  return value as AppointmentDraft;
}

function formatUrgency(value?: string | null) {
  const labels: Record<string, string> = {
    emergency: "Acil",
    same_day: "Ayni gun",
    soon: "Yakin takip",
    routine: "Rutin",
    admin: "Operasyon",
  };
  return labels[value ?? ""] ?? (value ? value.replace(/_/g, " ") : "Rutin");
}

function urgencyTone(value?: string | null) {
  if (value === "emergency") return "critical";
  if (value === "same_day") return "warning";
  if (value === "soon") return "attention";
  return "stable";
}

function lastPatientMessage(conversation: ClinicalConversationDetail | null): ClinicalMessage | null {
  return [...(conversation?.messages ?? [])].reverse().find((message) => message.sender === "patient") ?? null;
}

function getConversationTriage(conversation: ClinicalConversationDetail | null): TriageInfo | null {
  const patientMessage = lastPatientMessage(conversation);
  return getTriage(patientMessage?.metadata_json) ?? null;
}

function percent(value?: number | null) {
  return `${Math.round((value ?? 0) * 100)}%`;
}

function toDatetimeLocal(date: Date) {
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function appointmentLabel(value?: string | null) {
  if (!value) return "Saat secilmedi";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Saat secilmedi";
  return trDateTime.format(date);
}

function datetimeLocalFromIso(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return toDatetimeLocal(date);
}

export function ClinicalPanel({ token }: ClinicalPanelProps) {
  const [overview, setOverview] = useState<ClinicalOverview | null>(null);
  const [upcomingAppointments, setUpcomingAppointments] = useState<ClinicalAppointment[]>([]);
  const [selectedConversation, setSelectedConversation] = useState<ClinicalConversationDetail | null>(null);
  const [workspaceView, setWorkspaceView] = useState<WorkspaceView>("doctor");
  const [phone, setPhone] = useState("+90 555 111 22 33");
  const [patientName, setPatientName] = useState("Ayse Hasta");
  const [body, setBody] = useState("Arka disim zonkluyor, yarin icin dis hekimi randevusu almak istiyorum.");
  const [channel, setChannel] = useState<ChannelMode>("phone");
  const [personaId, setPersonaId] = useState<PersonaId>("can");
  const [department, setDepartment] = useState("Dis hekimligi muayenesi");
  const [appointmentAt, setAppointmentAt] = useState(toDatetimeLocal(new Date(Date.now() + 90 * 60000)));
  const [editingReviewId, setEditingReviewId] = useState<number | null>(null);
  const [editedReply, setEditedReply] = useState("");
  const [doctors, setDoctors] = useState<ClinicDoctor[]>([]);
  const [selectedDoctorId, setSelectedDoctorId] = useState<number | null>(null);
  const [doctorSlots, setDoctorSlots] = useState<ClinicDoctorSlot[]>([]);
  const [selectedSlotId, setSelectedSlotId] = useState<number | null>(null);
  const [slotDate, setSlotDate] = useState(new Date().toISOString().slice(0, 10));
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"ops" | "appointments" | "pitch">("ops");
  const [activeSlot, setActiveSlot] = useState<ClinicalSlotItem | null>(null);
  const [detailAppointment, setDetailAppointment] = useState<ClinicalAppointmentRow | null>(null);
  const [detailConversation, setDetailConversation] = useState<ClinicalConversationDetail | null>(null);

  useEffect(() => {
    void loadClinical();
  }, [token]);

  useEffect(() => {
    const draft = getAppointmentDraft(selectedConversation?.appointment_draft);
    if (draft?.department) setDepartment(draft.department);
    if (draft?.starts_at) setAppointmentAt(datetimeLocalFromIso(draft.starts_at));
  }, [selectedConversation?.id]);

  async function loadClinical(nextConversationId?: number) {
    setError(null);
    try {
      const [data, appointments, doctorList] = await Promise.all([
        getClinicalOverview(token),
        getUpcomingClinicalAppointments(token, 1440).catch(() => []),
        getClinicalDoctors(token).catch(() => []),
      ]);
      setOverview(data);
      setUpcomingAppointments(appointments);
      setDoctors(doctorList);
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

  function applyScenario(scenario: (typeof quickScenarios)[number]) {
    setChannel(scenario.channel);
    setPersonaId(scenario.persona);
    setPatientName(scenario.patient);
    setPhone(scenario.phone);
    setBody(scenario.body);
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

  async function loadDoctorSlots(doctorId: number, date?: string) {
    try {
      const slots = await getDoctorSlots(doctorId, token, date);
      setDoctorSlots(slots);
    } catch {
      setDoctorSlots([]);
    }
  }

  async function handleDoctorSelect(doctorId: number) {
    setSelectedDoctorId(doctorId);
    setSelectedSlotId(null);
    const doc = doctors.find((d) => d.id === doctorId);
    if (doc) setDepartment(doc.specialty);
    await loadDoctorSlots(doctorId, slotDate);
  }

  async function handleSlotDateChange(date: string) {
    setSlotDate(date);
    if (selectedDoctorId) await loadDoctorSlots(selectedDoctorId, date);
  }

  async function createAppointmentFromSelection() {
    if (!selectedConversation) return;
    setBusy(true);
    setError(null);
    try {
      await createClinicalAppointment(token, {
        conversation_id: selectedConversation.id,
        department,
        doctor_id: selectedDoctorId ?? undefined,
        slot_id: selectedSlotId ?? undefined,
        starts_at: selectedSlotId ? undefined : (appointmentAt ? new Date(appointmentAt).toISOString() : null),
        notes: selectedConversation.doctor_summary ?? getConversationTriage(selectedConversation)?.doctor_summary,
      });
      setSelectedSlotId(null);
      await loadClinical(selectedConversation.id);
      if (selectedDoctorId) await loadDoctorSlots(selectedDoctorId, slotDate);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Randevu olusturulamadi");
    } finally {
      setBusy(false);
    }
  }

  const metrics = overview?.metrics;
  const pendingAppointmentCount = appointments.filter((row) => row.status === "pending").length;
  const conversations = overview?.conversations ?? [];
  const doctorInbox = overview?.doctor_inbox ?? [];
  const reviews = overview?.shadow_reviews ?? [];
  const selectedPersona = useMemo(
    () => personaCards.find((persona) => persona.id === personaId) ?? personaCards[0],
    [personaId],
  );
  const selectedTriage = getConversationTriage(selectedConversation);
  const selectedConditions = getConditions(selectedConversation?.possible_conditions, selectedTriage);
  const selectedDraft = getAppointmentDraft(selectedConversation?.appointment_draft);
  const selectedUrgency = selectedTriage?.urgency ?? selectedConversation?.last_urgency;
  const emergencyCount = metrics?.emergency_reviews ?? reviews.filter((review) => getTriage(review.metadata_json)?.urgency === "emergency").length;
  const sameDayCount = metrics?.same_day_reviews ?? reviews.filter((review) => getTriage(review.metadata_json)?.urgency === "same_day").length;
  const autoReplyPercent = percent(metrics?.auto_reply_rate);

  if (loading && !overview) {
    return <div className="clinical-panel clinical-panel--loading">Medikal komuta merkezi hazirlaniyor...</div>;
  }

  return (
    <div className="clinical-panel boutique-clinic-panel">
      <section className="clinic-command-hero">
        <div className="clinic-hero-main">
          <div className="clinical-kicker">CogniVault Medical OS</div>
          <h2>Ozel klinikler ve dis hekimleri icin AI hasta karşilama merkezi</h2>
          <p>
            Telefonu, WhatsApp'i, medikal triyaji, doktor onayini ve randevu uyarilarini tek guvenli is akişinda birleştiren butik klinik operasyon paneli.
          </p>
          <div className="hero-signal-row" aria-label="Sistem durumu">
            <span>Voice intake aktif</span>
            <span>Shadow Mode zorunlu</span>
            <span>Teşhis yok, doktor onayi var</span>
          </div>
        </div>
        <div className="clinic-hero-safety">
          <span>Bugunku guvenlik kuyrugu</span>
          <strong>{metrics?.pending_shadow_reviews ?? 0}</strong>
          <p>{emergencyCount} acil, {sameDayCount} ayni gun doktor degerlendirmesi bekliyor.</p>
          <div className="safety-meter">
            <i style={{ width: `${Math.min(100, Math.max(12, (metrics?.auto_reply_rate ?? 0) * 100))}%` }} />
          </div>
          <small>Auto reply orani: {autoReplyPercent}</small>
        </div>
      </section>

      {error ? <div className="error-box clinical-error">{error}</div> : null}

      {tab === "ops" ? (
        <>
      <section className="clinic-metric-strip">
        <ClinicalMetric label="Hasta temasi" value={metrics?.conversations_today ?? 0} hint="Bugun gelen telefon + WhatsApp" />
        <ClinicalMetric label="Telefon" value={metrics?.phone_calls_today ?? 0} hint={`WhatsApp: ${metrics?.whatsapp_threads_today ?? 0}`} />
        <ClinicalMetric label="Doctor Inbox" value={metrics?.doctor_inbox_count ?? 0} tone="warning" hint="Insan onayi bekleyen hasta" />
        <ClinicalMetric label="Randevu adayi" value={metrics?.appointments_pending ?? 0} tone="success" hint="Konusmadan cikan taslak" />
        <ClinicalMetric label="Medikal triyaj" value={metrics?.triage_reviews ?? 0} tone="danger" hint="Acil / ayni gun klinik kontrol" />
      </section>

      <section className="clinic-control-grid">
        <div className="clinic-card intake-console">
          <div className="clinical-card-top">
            <div>
              <span>AI Reception Desk</span>
              <h3>Hasta girisini yonet</h3>
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

          <div className="persona-active-brief">
            <span>{selectedPersona.voice}</span>
            <p>{selectedPersona.guardrail}</p>
          </div>

          <div className="clinical-form">
            <div className="form-pair">
              <input value={patientName} onChange={(event) => setPatientName(event.target.value)} placeholder="Hasta adi" />
              <input value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="+90..." />
            </div>
            <textarea value={body} onChange={(event) => setBody(event.target.value)} placeholder="Hastanin soyledigi medikal talep" />
            <button type="button" onClick={handleSimulate} disabled={busy || !body.trim()}>
              Talebi klinik akışa düşür
            </button>
          </div>

          <div className="scenario-row">
            {quickScenarios.map((scenario) => (
              <button key={scenario.label} type="button" onClick={() => applyScenario(scenario)}>
                {scenario.label}
              </button>
            ))}
          </div>
        </div>

        <div className="clinic-card doctor-cockpit">
          <div className="clinical-card-top">
            <div>
              <span>Doctor Cockpit</span>
              <h3>{selectedConversation?.patient.full_name ?? selectedConversation?.patient.phone ?? "Hasta sec"}</h3>
            </div>
            <strong className={`urgency-pill ${urgencyTone(selectedUrgency)}`}>{formatUrgency(selectedUrgency)}</strong>
          </div>

          <div className="patient-brief-grid">
            <article>
              <span>Kanal</span>
              <strong>{selectedConversation?.channel ?? "hazir"}</strong>
            </article>
            <article>
              <span>Intent</span>
              <strong>{selectedConversation?.intent?.replace(/_/g, " ") ?? "bekliyor"}</strong>
            </article>
            <article>
              <span>Confidence</span>
              <strong>{percent(selectedConversation?.confidence_score)}</strong>
            </article>
            <article>
              <span>Randevu</span>
              <strong>{selectedDraft ? appointmentLabel(selectedDraft.starts_at) : "aday yok"}</strong>
            </article>
          </div>

          <div className="doctor-summary-panel">
            <span>Doktora dusen brif</span>
            <p>
              {selectedTriage?.doctor_summary
                ?? selectedConversation?.doctor_summary
                ?? "Hasta secildiginde AI tarafindan uretilen medikal ozet, aciliyet ve takip sorulari burada gorunur."}
            </p>
            <div className="condition-chip-row">
              {selectedConditions.length ? selectedConditions.slice(0, 4).map((item, index) => (
                <b key={`${item.label ?? "condition"}-${index}`}>{item.label ?? "olasi kategori"}</b>
              )) : <b>Doktor degerlendirmesi bekleniyor</b>}
            </div>
          </div>

          <div className="clinical-message-list patient-timeline">
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
                        {message.intent} · {percent(message.confidence_score)} ·{" "}
                        {String(message.metadata_json?.persona_name ?? message.metadata_json?.channel ?? "")}
                      </small>
                    ) : null}
                    {triage ? (
                      <div className="triage-strip">
                        <b>{formatUrgency(triage.urgency)}</b>
                        <span>{conditions.slice(0, 2).map((item) => item.label).filter(Boolean).join(" · ") || "Doktor degerlendirmesi"}</span>
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

        <aside className="clinic-card action-rail">
          <div className="clinical-card-top">
            <div>
              <span>Clinic Actions</span>
              <h3>Onay, randevu, uyari</h3>
            </div>
          </div>

          <div className="appointment-composer">
            <span>{selectedDraft ? "Konusmadan cikan randevu adayi" : "Randevuya cevir"}</span>
            {selectedDraft ? (
              <div className="appointment-draft-card">
                <b>{selectedDraft.department ?? "Muayene"}</b>
                <strong>{appointmentLabel(selectedDraft.starts_at)}</strong>
                <small>
                  {(selectedDraft.missing_fields ?? []).length
                    ? `Eksik: ${(selectedDraft.missing_fields ?? []).join(", ")}`
                    : "AI konuşmadan randevu adayını çıkardı."}
                </small>
              </div>
            ) : null}
            <input value={department} onChange={(event) => setDepartment(event.target.value)} placeholder="Bolum / islem" />
            <input type="datetime-local" value={appointmentAt} onChange={(event) => setAppointmentAt(event.target.value)} />
            <button type="button" onClick={createAppointmentFromSelection} disabled={busy || !selectedConversation}>
              {selectedDraft ? "Randevuyu onayla" : "Randevu olustur"}
            </button>
          </div>

          <div className="reminder-stack">
            <div className="rail-title">
              <span>Yaklasan randevular</span>
              <b>{upcomingAppointments.length}</b>
            </div>
            {upcomingAppointments.length ? upcomingAppointments.slice(0, 4).map((appointment) => (
              <article key={appointment.id} className="reminder-card">
                <strong>{appointment.department}</strong>
                <span>{appointmentLabel(appointment.starts_at)}</span>
              </article>
            )) : <div className="clinical-empty compact">Yaklasan uyari yok.</div>}
          </div>

          <div className="shadow-mini-list">
            <div className="rail-title">
              <span>Doktor onayi</span>
              <b>{reviews.length}</b>
            </div>
            {reviews.length ? reviews.slice(0, 3).map((review) => {
              const triage = getTriage(review.metadata_json);
              return (
                <button key={review.id} type="button" className="shadow-mini-card" onClick={() => void loadClinical(review.conversation_id)}>
                  <strong>{formatUrgency(triage?.urgency)}</strong>
                  <span>{review.intent.replace(/_/g, " ")} · {review.persona_name ?? "AI"}</span>
                  <p>{review.draft_reply}</p>
                </button>
              );
            }) : <div className="clinical-empty compact">Onay bekleyen cevap yok.</div>}
          </div>
        </aside>
      </section>

      <section className="clinic-split-grid">
        <div className="clinic-card">
          <div className="clinical-card-top">
            <div>
              <span>Doctor Inbox</span>
              <h3>Oncelikli hasta kuyrugu</h3>
            </div>
          </div>
          <ConversationList
            conversations={doctorInbox}
            selectedId={selectedConversation?.id}
            empty="Doktor ekraninda bekleyen hasta yok."
            onSelect={handleSelect}
          />
        </div>

        <div className="clinic-card review-studio">
          <div className="clinical-card-top">
            <div>
              <span>Shadow Mode</span>
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
                    <span>{review.channel ?? "medical"} · {review.persona_name ?? "AI"} · {percent(review.confidence_score)}</span>
                  </div>
                  {triage ? (
                    <div className="doctor-brief">
                      <b>Aciliyet: {formatUrgency(triage.urgency)}</b>
                      <p>{triage.doctor_summary ?? String(review.metadata_json?.doctor_summary ?? "")}</p>
                      <span>{conditions.slice(0, 3).map((item) => item.label).filter(Boolean).join(" · ") || "Olasi kategori yok"}</span>
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

      <section className="clinic-product-grid">
        <div className="clinic-card role-workspace-card">
          <div className="clinical-card-top">
            <div>
              <span>Kullanici deneyimi</span>
              <h3>Her rol icin ayri ekran mantigi</h3>
            </div>
          </div>
          <div className="workspace-tabs">
            {roleCards.map((role) => (
              <button key={role.id} type="button" className={workspaceView === role.id ? "active" : ""} onClick={() => setWorkspaceView(role.id)}>
                {role.title}
              </button>
            ))}
          </div>
          {roleCards.filter((role) => role.id === workspaceView).map((role) => (
            <article key={role.id} className="role-focus-card">
              <span>{role.metric}</span>
              <strong>{role.title}</strong>
              <p>{role.text}</p>
            </article>
          ))}
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

        <div className="clinic-card doctors-card">
          <div className="clinical-card-top">
            <div>
              <span>Klinik kadrosu</span>
              <h3>Doktorlar ve musait slotlar</h3>
            </div>
          </div>
          {doctors.length === 0 ? (
            <div className="clinical-empty">Doktor bilgisi bulunamadi.</div>
          ) : (
            <div className="doctors-grid">
              {doctors.map((doc) => (
                <button
                  key={doc.id}
                  type="button"
                  className={`doctor-card-btn ${selectedDoctorId === doc.id ? "active" : ""}`}
                  onClick={() => handleDoctorSelect(doc.id)}
                >
                  <strong>{doc.title} {doc.full_name}</strong>
                  <span className="doctor-specialty">{doc.specialty}</span>
                  {doc.bio && <p className="doctor-bio">{doc.bio}</p>}
                </button>
              ))}
            </div>
          )}
          {selectedDoctorId && (
            <div className="slots-section">
              <div className="slots-date-picker">
                <label>Tarih: </label>
                <input type="date" value={slotDate} onChange={(e) => handleSlotDateChange(e.target.value)} />
              </div>
              {doctorSlots.length === 0 ? (
                <div className="clinical-empty">Bu tarihte musait slot yok.</div>
              ) : (
                <div className="slots-grid">
                  {doctorSlots.map((slot) => (
                    <button
                      key={slot.id}
                      type="button"
                      disabled={slot.is_booked}
                      className={`slot-btn ${slot.is_booked ? "booked" : ""} ${selectedSlotId === slot.id ? "selected" : ""}`}
                      onClick={() => {
                        setSelectedSlotId(slot.id);
                        setAppointmentAt(slot.start_time);
                      }}
                    >
                      {trTime.format(new Date(slot.start_time))}
                      {slot.is_booked && " ✕"}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="clinic-card architecture-card">
          <div className="clinical-card-top">
            <div>
              <span>Urun mimarisi</span>
              <h3>Kanal → AI → Doktor → Randevu</h3>
            </div>
          </div>
          <div className="architecture-lanes">
            {architectureLanes.map((lane, index) => (
              <article key={lane.title}>
                <b>{index + 1}</b>
                <div>
                  <strong>{lane.title}</strong>
                  <p>{lane.text}</p>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="clinic-bottom-grid">
        <div className="clinic-card">
          <div className="clinical-card-top">
            <div>
              <span>Tum hasta akisi</span>
              <h3>Klinik temaslari</h3>
            </div>
          </div>
          <ConversationList
            conversations={conversations}
            selectedId={selectedConversation?.id}
            empty="Henüz hasta teması yok."
            onSelect={handleSelect}
          />
        </div>

        <div className="clinic-card database-contract-card">
          <div className="clinical-card-top">
            <div>
              <span>Veri sozlesmesi</span>
              <h3>Backend ve DB omurgasi</h3>
            </div>
          </div>
          <div className="db-contract-grid">
            <article><span>patients</span><strong>Telefon, dil, kanal, kaynak</strong></article>
            <article><span>conversations</span><strong>Intent, status, confidence, urgency</strong></article>
            <article><span>messages</span><strong>Raw payload + persona + triage</strong></article>
            <article><span>shadow_reviews</span><strong>Doktor onayi ve karar izi</strong></article>
            <article><span>appointments</span><strong>Pending / confirmed randevu akisi</strong></article>
            <article><span>frustration_logs</span><strong>Risk, sikayet, kalite sinyali</strong></article>
          </div>
        </div>
      </section>
        </>
      ) : null}

      {tab === "pitch" ? (
        <>
      <section className="clinic-hero">
        <div className="clinic-hero-copy">
          <div className="clinical-kicker">CogniVault Clinical OS</div>
          <h2>Dental ve butik klinikler için AI çağrı merkezi kokpiti</h2>
          <p>
            Hasta konuşmasını anlayan, doğru branşa yönlendiren, randevu için eksik bilgileri tamamlayan
            ve riskli yanıtları doktor onayına alan medikal operasyon yüzeyi.
          </p>
          <div className="clinic-command-center">
            <article>
              <span>Canlı hedef</span>
              <strong>Kaçan çağrıyı randevuya çevir</strong>
            </article>
            <article>
              <span>Guardrail</span>
              <strong>Tanı koyma, riskli ifadeyi aktar</strong>
            </article>
            <article>
              <span>Persona</span>
              <strong>{selectedPersona.name} · {selectedPersona.title}</strong>
            </article>
          </div>
        </div>
        <div className="clinic-hero-panel">
          <span>Ürün odağı</span>
          <strong>Türkiye klinikleri için özgün, KVKK-first ve doktor onaylı premium intake motoru</strong>
          <p>Diş klinikleri, dermatoloji, estetik ve küçük özel kliniklerde telefon + WhatsApp randevu otomasyonu.</p>
        </div>
      </section>

      <section className="clinic-product-grid">
        <div className="clinic-card">
          <div className="clinical-card-top">
            <div>
              <span>Hasta yolculuğu</span>
              <h3>Çağrıdan randevuya akış</h3>
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
              <span>Routing zekası</span>
              <h3>Halk dilinden klinik aksiyona</h3>
            </div>
          </div>
          <div className="channel-decision-list routing-intelligence-list">
            {routingCards.map((card) => (
              <article key={card.label}>
                <span>{card.label}</span>
                <b>{card.value}</b>
                <p>{card.text}</p>
              </article>
            ))}
          </div>
        </div>

        <div className="clinic-card">
          <div className="clinical-card-top">
            <div>
              <span>Entegrasyon hazırlığı</span>
              <h3>Üretime giden backend omurgası</h3>
            </div>
          </div>
          <div className="persona-detail-list">
            {integrationCards.map((item) => (
              <article key={item.title}>
                <strong>{item.title}</strong>
                <span>READY PATH</span>
                <p>{item.text}</p>
              </article>
            ))}
          </div>
        </div>

        <div className="clinic-card">
          <div className="clinical-card-top">
            <div>
              <span>KVKK governance</span>
              <h3>Local-first güvenlik motoru</h3>
            </div>
          </div>
          <div className="persona-detail-list">
            <article className="active">
              <strong>{complianceProfile?.data_residency_default ?? "tr_local_first"}</strong>
              <span>DATA RESIDENCY</span>
              <p>Sağlık verisi için varsayılan mod Türkiye/yerel işleme; yurt dışı AI işlemcileri kapalı başlar.</p>
            </article>
            <article>
              <strong>{complianceProfile?.blocked_by_default.length ?? 7} blok kuralı</strong>
              <span>DEFAULT DENY</span>
              <p>Tanı, tedavi talimatı, izinsiz provizyon, kimlik/kart ve rızasız cross-border işlem otomatikleşmez.</p>
            </article>
            <article>
              <strong>
                {(complianceProfile?.processor_inventory ?? []).filter((item) => item.allowed_for_clinical === true).length} açık işlemci
              </strong>
              <span>PROCESSOR GATE</span>
              <p>Harici LLM, STT/TTS ve mesajlaşma işlemcileri klinik veride kapalı başlar; açık rıza ve sözleşme olmadan açılmaz.</p>
            </article>
          </div>
        </div>

        <div className="clinic-card">
          <div className="clinical-card-top">
            <div>
              <span>Patent hazırlığı</span>
              <h3>Teknik buluş omurgası</h3>
            </div>
          </div>
          <div className="channel-decision-list">
            {(patentDossier?.candidate_independent_claims.slice(0, 3) ?? [
              "Türkçe dental konuşmayı güvenli randevu akışına çeviren yöntem.",
              "Riskli sağlık, sigorta ve kimlik cevaplarını otomatik engelleyen sistem.",
              "Doktor onayı için redakte edilmiş teknik paket üreten orkestrasyon.",
            ]).map((claim, index) => (
              <article key={claim}>
                <span>Claim {index + 1}</span>
                <b>{claim.split(" ").slice(0, 9).join(" ")}</b>
                <p>{claim}</p>
              </article>
            ))}
          </div>
        </div>
      </section>
        </>
      ) : null}

      {tab === "appointments" ? (
        <>
          <section className="clinic-lab-grid clinic-lab-grid--single">
            <SlotBoardCard slotBoard={slotBoard} onOpenSlot={setActiveSlot} />
          </section>
          <AppointmentRequestsCard
            appointments={appointments}
            busy={busy}
            onConfirm={(row) => handleAppointmentStatus(row, "confirmed")}
            onCancel={(row) => handleAppointmentStatus(row, "cancelled")}
            onOpenDetail={openAppointmentDetail}
          />
        </>
      ) : null}

      {activeSlot ? (
        <SlotAppointmentsModal
          slot={activeSlot}
          busy={busy}
          onClose={() => setActiveSlot(null)}
          onBook={handleManualBooking}
        />
      ) : null}

      {detailAppointment ? (
        <AppointmentDetailModal
          appointment={detailAppointment}
          conversation={detailConversation}
          onClose={() => {
            setDetailAppointment(null);
            setDetailConversation(null);
          }}
        />
      ) : null}
    </div>
  );
}

function SlotBoardCard({
  slotBoard,
  onOpenSlot,
}: {
  slotBoard: ClinicalSlotBoard | null;
  onOpenSlot: (slot: ClinicalSlotItem) => void;
}) {
  const schedule = slotBoard?.schedule ?? [];
  return (
    <div className="clinic-card slot-board-card">
      <div className="clinical-card-top">
        <div>
          <span>Canlı slot panosu</span>
          <h3>Klinik doluluğu ve bekleme listesi</h3>
        </div>
        <b>{Math.round((slotBoard?.summary.occupancy_rate ?? 0) * 100)}%</b>
      </div>
      <div className="slot-summary-row">
        <article>
          <span>Sıradaki açık slot</span>
          <strong>{slotBoard?.summary.next_open_slot ?? "yükleniyor"}</strong>
        </article>
        <article>
          <span>Dolu bölüm</span>
          <strong>{slotBoard?.summary.full_departments ?? 0}</strong>
        </article>
        <article>
          <span>Bekleme listesi</span>
          <strong>{slotBoard?.summary.waitlist_total ?? 0}</strong>
        </article>
      </div>
      <p className="slot-board-hint">Randevuları görmek için bir bölüme tıklayın →</p>
      <div className="slot-board-list">
        {schedule.map((slot) => <SlotRow key={slot.id} slot={slot} onOpen={onOpenSlot} />)}
      </div>
    </div>
  );
}

function SlotRow({ slot, onOpen }: { slot: ClinicalSlotItem; onOpen: (slot: ClinicalSlotItem) => void }) {
  return (
    <button type="button" className={`slot-row slot-row--clickable ${slot.status}`} onClick={() => onOpen(slot)}>
      <div>
        <strong>{slot.department}</strong>
        <span>{slot.doctor} · {slot.date_label} · {slot.time_range}</span>
      </div>
      <div>
        <b>{slot.booked}/{slot.capacity}</b>
        <small>{slot.status === "full" ? "Dolu" : slot.status === "limited" ? "Son slot" : "Uygun"}</small>
      </div>
    </button>
  );
}

function SlotAppointmentsModal({
  slot,
  busy,
  onClose,
  onBook,
}: {
  slot: ClinicalSlotItem;
  busy: boolean;
  onClose: () => void;
  onBook: (input: { full_name: string; phone: string; notes?: string }) => Promise<boolean>;
}) {
  const appointments = slot.appointments ?? [];
  const [showForm, setShowForm] = useState(false);
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("+90 ");
  const [notes, setNotes] = useState("");

  async function submit() {
    if (!phone.trim() || phone.trim().length < 7) return;
    const ok = await onBook({ full_name: fullName, phone, notes });
    if (ok) {
      setShowForm(false);
      setFullName("");
      setPhone("+90 ");
      setNotes("");
    }
  }
  return (
    <div className="slot-modal-overlay" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="slot-modal" onClick={(event) => event.stopPropagation()}>
        <div className="slot-modal-head">
          <div>
            <span>Randevu takvimi</span>
            <h3>{slot.department}</h3>
            <p>{slot.doctor} · {slot.date_label} · {slot.time_range}</p>
          </div>
          <button type="button" className="slot-modal-close" onClick={onClose} aria-label="Kapat">×</button>
        </div>

        <div className="slot-modal-stats">
          <article>
            <span>Dolu / Kapasite</span>
            <strong>{slot.booked}/{slot.capacity}</strong>
          </article>
          <article>
            <span>Boş slot</span>
            <strong>{slot.open}</strong>
          </article>
          <article>
            <span>Bekleme listesi</span>
            <strong>{slot.waitlist_count}</strong>
          </article>
        </div>

        {appointments.length ? (
          <div className="slot-appointment-list">
            {appointments.map((appt) => (
              <article key={appt.id} className={`slot-appointment ${appt.status}`}>
                <div className="slot-appointment-time">{appt.time}</div>
                <div className="slot-appointment-main">
                  <strong>{appt.patient_name}</strong>
                  <span>{appt.branch} · {appt.doctor}</span>
                  <small>{appt.phone}</small>
                </div>
                <span className={`slot-appointment-badge ${appt.status}`}>{appt.status_label}</span>
              </article>
            ))}
          </div>
        ) : (
          <div className="clinical-empty">Bu slotta kayıtlı randevu yok — kapasite uygun.</div>
        )}

        <div className="slot-modal-book">
          {showForm ? (
            <div className="slot-book-form">
              <input
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                placeholder="Hasta adı"
              />
              <input
                value={phone}
                onChange={(event) => setPhone(event.target.value)}
                placeholder="+90..."
              />
              <input
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                placeholder="Not (opsiyonel)"
              />
              <div className="slot-book-actions">
                <button type="button" disabled={busy || phone.trim().length < 7} onClick={submit}>
                  Randevuyu oluştur
                </button>
                <button type="button" className="ghost" onClick={() => setShowForm(false)}>
                  Vazgeç
                </button>
              </div>
            </div>
          ) : (
            <button type="button" className="slot-book-cta" onClick={() => setShowForm(true)}>
              + Bu slota yeni randevu ekle
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

const APPOINTMENT_STATUS_LABELS: Record<string, string> = {
  pending: "Onay bekliyor",
  confirmed: "Onaylandı",
  cancelled: "İptal edildi",
};

function AppointmentRow({
  row,
  busy,
  onConfirm,
  onCancel,
  onOpenDetail,
}: {
  row: ClinicalAppointmentRow;
  busy: boolean;
  onConfirm: (row: ClinicalAppointmentRow) => void;
  onCancel: (row: ClinicalAppointmentRow) => void;
  onOpenDetail: (row: ClinicalAppointmentRow) => void;
}) {
  const phoneDigits = row.patient_phone ? row.patient_phone.replace(/[^\d+]/g, "") : null;
  const waNumber = phoneDigits ? phoneDigits.replace(/^\+/, "") : null;
  return (
    <article className={`appointment-request ${row.status}`}>
      <button
        type="button"
        className="appointment-request-main"
        onClick={() => onOpenDetail(row)}
        title="Detayı aç"
      >
        <strong>{row.patient_name ?? `Hasta #${row.patient_id}`}</strong>
        <span>
          {row.department}
          {row.physician_name ? ` · ${row.physician_name}` : ""}
          {row.branch_name ? ` · ${row.branch_name}` : ""}
        </span>
        <small>
          {row.starts_at
            ? trDateTime.format(new Date(row.starts_at))
            : `Talep: ${trDateTime.format(new Date(row.created_at))}`}
        </small>
        {row.patient_phone ? <small className="appointment-request-phone">{row.patient_phone}</small> : null}
      </button>
      <div className="appointment-request-side">
        <span className={`appointment-request-badge ${row.status}`}>
          {APPOINTMENT_STATUS_LABELS[row.status] ?? row.status}
        </span>
        {phoneDigits ? (
          <div className="appointment-request-contact">
            <a href={`tel:${phoneDigits}`} title="Ara">📞</a>
            {waNumber ? (
              <a href={`https://wa.me/${waNumber}`} target="_blank" rel="noreferrer" title="WhatsApp">💬</a>
            ) : null}
          </div>
        ) : null}
        {row.status === "pending" ? (
          <div className="appointment-request-actions">
            <button type="button" className="appointment-confirm" disabled={busy} onClick={() => onConfirm(row)}>
              Onayla
            </button>
            <button type="button" className="appointment-cancel" disabled={busy} onClick={() => onCancel(row)}>
              İptal
            </button>
          </div>
        ) : row.status === "confirmed" ? (
          <div className="appointment-request-actions">
            <button type="button" className="appointment-cancel" disabled={busy} onClick={() => onCancel(row)}>
              İptal et
            </button>
          </div>
        ) : null}
      </div>
    </article>
  );
}

function AppointmentBucket({
  title,
  subtitle,
  tone,
  rows,
  busy,
  emptyText,
  onConfirm,
  onCancel,
  onOpenDetail,
}: {
  title: string;
  subtitle: string;
  tone: "pending" | "confirmed" | "cancelled";
  rows: ClinicalAppointmentRow[];
  busy: boolean;
  emptyText: string;
  onConfirm: (row: ClinicalAppointmentRow) => void;
  onCancel: (row: ClinicalAppointmentRow) => void;
  onOpenDetail: (row: ClinicalAppointmentRow) => void;
}) {
  return (
    <div className={`clinic-card appointment-bucket appointment-bucket--${tone}`}>
      <div className="clinical-card-top">
        <div>
          <span>{subtitle}</span>
          <h3>{title}</h3>
        </div>
        <b>{rows.length}</b>
      </div>
      {rows.length ? (
        <div className="appointment-request-list">
          {rows.map((row) => (
            <AppointmentRow
              key={row.id}
              row={row}
              busy={busy}
              onConfirm={onConfirm}
              onCancel={onCancel}
              onOpenDetail={onOpenDetail}
            />
          ))}
        </div>
      ) : (
        <div className="clinical-empty">{emptyText}</div>
      )}
    </div>
  );
}

function AppointmentRequestsCard({
  appointments,
  busy,
  onConfirm,
  onCancel,
  onOpenDetail,
}: {
  appointments: ClinicalAppointmentRow[];
  busy: boolean;
  onConfirm: (row: ClinicalAppointmentRow) => void;
  onCancel: (row: ClinicalAppointmentRow) => void;
  onOpenDetail: (row: ClinicalAppointmentRow) => void;
}) {
  const pending = appointments.filter((row) => row.status === "pending");
  const confirmed = appointments.filter((row) => row.status === "confirmed");
  const cancelled = appointments.filter((row) => row.status === "cancelled");
  return (
    <section className="appointment-requests-grid">
      <AppointmentBucket
        title="Onay bekleyen hastalar"
        subtitle="Web chat üzerinden gelen talepler"
        tone="pending"
        rows={pending}
        busy={busy}
        emptyText="Onay bekleyen randevu yok."
        onConfirm={onConfirm}
        onCancel={onCancel}
        onOpenDetail={onOpenDetail}
      />
      <AppointmentBucket
        title="Onaylanan randevular"
        subtitle="Operatör onayından geçti"
        tone="confirmed"
        rows={confirmed}
        busy={busy}
        emptyText="Henüz onaylanmış randevu yok."
        onConfirm={onConfirm}
        onCancel={onCancel}
        onOpenDetail={onOpenDetail}
      />
      {cancelled.length ? (
        <AppointmentBucket
          title="İptal edilenler"
          subtitle="Arşiv"
          tone="cancelled"
          rows={cancelled}
          busy={busy}
          emptyText="İptal edilen randevu yok."
          onConfirm={onConfirm}
          onCancel={onCancel}
          onOpenDetail={onOpenDetail}
        />
      ) : null}
    </section>
  );
}

function TestLab({
  slotBoard,
  onPick,
}: {
  slotBoard: ClinicalSlotBoard | null;
  onPick: (message: string) => void;
}) {
  return (
    <div className="clinic-card test-lab-card">
      <div className="clinical-card-top">
        <div>
          <span>Test laboratuvarı</span>
          <h3>Kabul aldığımız senaryolar</h3>
        </div>
      </div>
      <div className="acceptance-rule-list">
        {(slotBoard?.acceptance_rules ?? []).map((item) => (
          <article key={item.rule}>
            <strong>{item.rule}</strong>
            <p>{item.result}</p>
          </article>
        ))}
      </div>
      <div className="scenario-pick-list">
        {(slotBoard?.test_scenarios ?? []).map((scenario) => (
          <button key={scenario.label} type="button" onClick={() => onPick(scenario.message)}>
            <strong>{scenario.label}</strong>
            <span>{scenario.expected_action}</span>
            <p>{scenario.expected_result}</p>
          </button>
        ))}
      </div>
    </div>
  );
}

function DoctorScreen({
  selectedConversation,
  reviews,
  slotBoard,
  busy,
  editingReviewId,
  editedReply,
  onEditReply,
  onStartEdit,
  onDecide,
}: {
  selectedConversation: ClinicalConversationDetail | null;
  reviews: ShadowReview[];
  slotBoard: ClinicalSlotBoard | null;
  busy: boolean;
  editingReviewId: number | null;
  editedReply: string;
  onEditReply: (value: string) => void;
  onStartEdit: (review: ShadowReview) => void;
  onDecide: (review: ShadowReview, status: "approved" | "edited" | "rejected") => void;
}) {
  const activeReview = reviews.find((review) => review.conversation_id === selectedConversation?.id) ?? reviews[0];
  const guardrail = activeReview?.metadata_json?.data && typeof activeReview.metadata_json.data === "object"
    ? (activeReview.metadata_json.data as { privacy_guardrail?: Record<string, unknown>; intake?: Record<string, unknown>; slot_decision?: Record<string, unknown> })
    : null;

  return (
    <section className="doctor-screen-grid">
      <div className="clinic-card doctor-command-card">
        <div className="clinical-card-top">
          <div>
            <span>Doktor ekranı</span>
            <h3>Klinik karar paketi</h3>
          </div>
          <strong className="clinical-status danger">{activeReview ? "onay bekliyor" : "temiz"}</strong>
        </div>
        {activeReview ? (
          <div className="doctor-approval-packet">
            <article>
              <span>Hasta</span>
              <strong>{selectedConversation?.patient.full_name ?? "Seçili hasta yok"}</strong>
            </article>
            <article>
              <span>Niyet</span>
              <strong>{activeReview.intent.replace(/_/g, " ")}</strong>
            </article>
            <article>
              <span>Branş</span>
              <strong>{String(guardrail?.intake?.specialty ?? "genel değerlendirme")}</strong>
            </article>
            <article>
              <span>Slot kararı</span>
              <strong>{String(guardrail?.slot_decision?.status_label ?? "slot kontrolü")}</strong>
            </article>
            <article>
              <span>KVKK sınıfı</span>
              <strong>{Array.isArray(guardrail?.privacy_guardrail?.data_classes) ? guardrail?.privacy_guardrail?.data_classes.join(", ") : "standart"}</strong>
            </article>
            <article>
              <span>Risk</span>
              <strong>{activeReview.risk_reason}</strong>
            </article>
          </div>
        ) : (
          <div className="clinical-empty">Doktor onayı bekleyen aktif kayıt yok.</div>
        )}
      </div>

      <div className="clinic-card doctor-command-card">
        <div className="clinical-card-top">
          <div>
            <span>Önerilen aksiyon</span>
            <h3>Hekim güvenli cevabı</h3>
          </div>
        </div>
        {activeReview ? (
          <article className="clinical-review doctor-review-focus">
            <p>{activeReview.draft_reply}</p>
            <small>{String((activeReview.metadata_json?.data as { slot_decision?: { patient_offer?: string } } | undefined)?.slot_decision?.patient_offer ?? slotBoard?.summary.next_open_slot ?? "")}</small>
            {editingReviewId === activeReview.id ? (
              <textarea value={editedReply} onChange={(event) => onEditReply(event.target.value)} />
            ) : null}
            <div className="clinical-review-actions">
              <button type="button" onClick={() => onDecide(activeReview, "approved")} disabled={busy}>Onayla</button>
              <button type="button" onClick={() => onStartEdit(activeReview)} disabled={busy}>Düzenle</button>
              {editingReviewId === activeReview.id ? (
                <button type="button" onClick={() => onDecide(activeReview, "edited")} disabled={busy || !editedReply.trim()}>
                  Düzenlemeyi gönder
                </button>
              ) : null}
              <button type="button" className="danger" onClick={() => onDecide(activeReview, "rejected")} disabled={busy}>Reddet</button>
            </div>
          </article>
        ) : (
          <div className="clinical-empty">Riskli cevap gelince doktorun onaylayacağı metin burada görünür.</div>
        )}
      </div>
    </section>
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
        <ConversationRow
          key={conversation.id}
          conversation={conversation}
          selected={selectedId === conversation.id}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}

function ConversationRow({
  conversation,
  selected,
  onSelect,
}: {
  conversation: ClinicalConversationSummary;
  selected: boolean;
  onSelect: (conversation: ClinicalConversationSummary) => void;
}) {
  const draft = getAppointmentDraft(conversation.appointment_draft);
  return (
    <button
      type="button"
      className={`clinical-conversation-row ${conversation.doctor_inbox ? "doctor" : ""} ${selected ? "selected" : ""}`}
      onClick={() => void onSelect(conversation)}
    >
      <strong>{conversation.patient.full_name ?? conversation.patient.phone}</strong>
      <span>
        {conversation.channel} · {conversation.persona_name ?? "AI"} · {conversation.intent?.replace(/_/g, " ") ?? "intent pending"}
      </span>
      {draft ? (
        <em>Randevu adayi · {draft.department ?? "Muayene"} · {appointmentLabel(draft.starts_at)}</em>
      ) : conversation.last_urgency ? (
        <em>
          {formatUrgency(conversation.last_urgency)} ·{" "}
          {(conversation.possible_conditions ?? []).slice(0, 2).map((item) => String(item.label ?? "")).filter(Boolean).join(" · ") || "doktor ozeti hazir"}
        </em>
      ) : null}
      <p>{conversation.doctor_summary ?? conversation.last_message_preview ?? "No messages yet"}</p>
    </button>
  );
}

function ClinicalMetric({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "success" | "warning" | "danger";
}) {
  return (
    <div className={`clinical-metric ${tone ?? ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {hint ? <small>{hint}</small> : null}
    </div>
  );
}
