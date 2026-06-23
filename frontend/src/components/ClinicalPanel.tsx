import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import {
  getClinicalConversation,
  getClinicalComplianceProfile,
  getClinicalOverview,
  getClinicalPatentDossier,
  getClinicalSlotBoard,
  listClinicalAppointments,
  createManualClinicalAppointment,
  simulateVoiceCall,
  simulateWhatsAppMessage,
  updateClinicalAppointmentStatus,
  updateShadowReview,
  type ClinicalManualAppointmentInput,
} from "../api/client";
import { clinicalKeys } from "../api/queryKeys";
import type {
  ClinicalAppointmentRow,
  ClinicalConversationDetail,
  ClinicalConversationSummary,
  ClinicalSlotBoard,
  ClinicalSlotItem,
  ShadowReview,
} from "../types/api";
import { ShadowReviewCard } from "./clinical/ShadowReviewCard";
import {
  AppointmentDetailModal,
  AppointmentRequestsCard,
  ClinicalMetric,
  ConversationList,
  DoctorScheduleCalendar,
  DoctorScreen,
  SlotAppointmentsModal,
  SlotBoardCard,
  TestLab,
} from "./clinical/ClinicalPanelSections";

const trDateTime = new Intl.DateTimeFormat("tr-TR", { dateStyle: "short", timeStyle: "short" });

type ClinicalPanelProps = {
  token: string;
};

type PersonaId = "selin" | "arzu" | "can";
type ChannelMode = "phone" | "whatsapp";

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
    voice: "Sıcak ve hızlı",
    description: "Diş taşı, implant kontrolü, dermatoloji ve genel muayene randevularını toplar.",
  },
  {
    id: "arzu",
    name: "Arzu",
    title: "Sigorta ve klinik operasyon",
    voice: "Net ve güven veren",
    description: "Fiyat, SGK, özel sigorta, ödeme ve şube bilgilerini kontrollü cevaplar.",
  },
  {
    id: "can",
    name: "Can",
    title: "Medikal güvenlik",
    voice: "Sakin ve ciddi",
    description: "Acil veya riskli ifadeleri yakalar, doktora öncelikli not düşer.",
  },
];

const roleCards = [
  {
    title: "1. Karşılama",
    metric: "Telefon / WhatsApp",
    text: "Hasta uygulama indirmez. Kliniği arar veya WhatsApp yazar; AI kimlik, şikayet ve tercih bilgilerini toplar.",
  },
  {
    title: "2. Klinik routing",
    metric: "Niyet ve branş",
    text: "Halk ağzındaki şikayet Endodonti, Periodontoloji, Pedodonti veya genel muayene gibi aksiyona çevrilir.",
  },
  {
    title: "3. Randevu",
    metric: "Takvim",
    text: "Eksik gün, saat, şube ve hekim bilgisi tamamlanır; uygun slot oluşunca resepsiyon onayına düşer.",
  },
  {
    title: "4. Güvenlik",
    metric: "Doktor onayı",
    text: "Acil, belirsiz veya klinik risk taşıyan cevaplar otomatik gönderilmez; insan onayına alınır.",
  },
];

const routingCards = [
  { label: "Arka dişim zonkluyor", value: "Endodonti", text: "Kanal tedavisi ihtimali, ağrı önceliği ve yakın slot önerisi." },
  { label: "Diş etim kanıyor", value: "Periodontoloji", text: "Diş eti şikayeti, kanama şiddeti ve aciliyet kontrolü." },
  { label: "Çocuğumun dolgusu düştü", value: "Pedodonti", text: "Çocuk hasta akışı, veli bilgisi ve uygun hekim yönlendirmesi." },
  { label: "İmplant kontrolüm var", value: "İmplantoloji", text: "Kontrol randevusu, işlem geçmişi ve hekim tercihi toplama." },
];

const integrationCards = [
  { title: "HBYS / Klinik yazılımı", text: "Hasta kartı, hekim takvimi, slot ve randevu durumları tek pipeline'a bağlanır." },
  { title: "KVKK kayıt izi", text: "Açık rıza, mesaj geçmişi, insan onayı ve outbound bildirimler denetlenebilir tutulur." },
  { title: "Ses kalitesi", text: "Arka plan gürültüsü, aksan, yarım cümle ve yaşlı hasta konuşmaları için tekrar-sorma stratejisi." },
];

export function ClinicalPanel({ token }: ClinicalPanelProps) {
  const queryClient = useQueryClient();
  const [selectedConversationId, setSelectedConversationId] = useState<number | null>(null);
  const [phone, setPhone] = useState("+90 555 111 22 33");
  const [patientName, setPatientName] = useState("Ayse Hasta");
  const [body, setBody] = useState("Arka disim zonkluyor, yarin icin dis hekimi randevusu almak istiyorum.");
  const [channel, setChannel] = useState<ChannelMode>("phone");
  const [personaId, setPersonaId] = useState<PersonaId>("selin");
  const [editingReviewId, setEditingReviewId] = useState<number | null>(null);
  const [editedReply, setEditedReply] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [tab, setTab] = useState<"ops" | "appointments" | "pitch">("ops");
  const [activeSlot, setActiveSlot] = useState<ClinicalSlotItem | null>(null);
  const [detailAppointment, setDetailAppointment] = useState<ClinicalAppointmentRow | null>(null);
  const overviewQuery = useQuery({
    queryKey: clinicalKeys.overview(token),
    queryFn: () => getClinicalOverview(token),
  });
  const complianceQuery = useQuery({
    queryKey: clinicalKeys.compliance(token),
    queryFn: () => getClinicalComplianceProfile(token),
  });
  const patentQuery = useQuery({
    queryKey: clinicalKeys.patent(token),
    queryFn: () => getClinicalPatentDossier(token),
    staleTime: 5 * 60_000,
  });
  const slotsQuery = useQuery({
    queryKey: clinicalKeys.slots(token),
    queryFn: () => getClinicalSlotBoard(token),
  });
  const appointmentsQuery = useQuery({
    queryKey: clinicalKeys.appointments(token),
    queryFn: () => listClinicalAppointments(token),
  });

  const overview = overviewQuery.data ?? null;
  const complianceProfile = complianceQuery.data ?? null;
  const patentDossier = patentQuery.data ?? null;
  const slotBoard = slotsQuery.data ?? null;
  const appointments = appointmentsQuery.data ?? [];
  const resolvedConversationId = selectedConversationId
    ?? overview?.doctor_inbox[0]?.id
    ?? overview?.conversations[0]?.id
    ?? null;
  const selectedConversationQuery = useQuery({
    queryKey: clinicalKeys.conversation(token, resolvedConversationId),
    queryFn: () => getClinicalConversation(resolvedConversationId!, token),
    enabled: resolvedConversationId !== null,
  });
  const selectedConversation = selectedConversationQuery.data ?? null;
  const detailConversationId = detailAppointment?.conversation_id ?? null;
  const detailConversationQuery = useQuery({
    queryKey: clinicalKeys.conversation(token, detailConversationId),
    queryFn: () => getClinicalConversation(detailConversationId!, token),
    enabled: detailConversationId !== null,
  });
  const detailConversation = detailConversationQuery.data ?? null;

  async function refreshClinical(options: { includeStatic?: boolean } = {}) {
    const invalidations = [
      queryClient.invalidateQueries({ queryKey: clinicalKeys.overview(token) }),
      queryClient.invalidateQueries({ queryKey: clinicalKeys.appointments(token) }),
      queryClient.invalidateQueries({ queryKey: clinicalKeys.slots(token) }),
    ];
    if (resolvedConversationId !== null) {
      invalidations.push(queryClient.invalidateQueries({ queryKey: clinicalKeys.conversation(token, resolvedConversationId) }));
    }
    if (options.includeStatic) {
      invalidations.push(queryClient.invalidateQueries({ queryKey: clinicalKeys.compliance(token) }));
    }
    await Promise.all(invalidations);
  }

  const simulateMutation = useMutation({
    mutationFn: () => channel === "phone"
      ? simulateVoiceCall(token, {
          from_phone: phone.trim(),
          patient_name: patientName.trim() || undefined,
          speech: body.trim(),
          persona_id: personaId,
        })
      : simulateWhatsAppMessage(token, {
          from_phone: phone.trim(),
          patient_name: patientName.trim() || undefined,
          body: body.trim(),
        }),
    onSuccess: async (result) => {
      setSelectedConversationId(result.conversation_id);
      await Promise.all([
        refreshClinical(),
        queryClient.invalidateQueries({ queryKey: clinicalKeys.conversation(token, result.conversation_id) }),
      ]);
    },
  });

  const reviewMutation = useMutation({
    mutationFn: ({ review, status }: { review: ShadowReview; status: "approved" | "edited" | "rejected" }) =>
      updateShadowReview(review.id, token, {
        status,
        final_reply: status === "edited" ? editedReply : review.draft_reply,
      }),
    onSuccess: async (updated) => {
      setEditingReviewId(null);
      setEditedReply("");
      setSelectedConversationId(updated.conversation_id);
      await refreshClinical();
    },
  });

  const manualBookingMutation = useMutation({
    mutationFn: (payload: ClinicalManualAppointmentInput) => createManualClinicalAppointment(token, payload),
    onSuccess: async (created) => {
      queryClient.setQueryData<ClinicalAppointmentRow[]>(clinicalKeys.appointments(token), (rows = []) => [created, ...rows]);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: clinicalKeys.overview(token) }),
        queryClient.invalidateQueries({ queryKey: clinicalKeys.slots(token) }),
      ]);
    },
  });

  const appointmentStatusMutation = useMutation({
    mutationFn: ({ appointmentId, status }: { appointmentId: number; status: "confirmed" | "cancelled" }) =>
      updateClinicalAppointmentStatus(token, appointmentId, status),
    onSuccess: (updated) => {
      queryClient.setQueryData<ClinicalAppointmentRow[]>(clinicalKeys.appointments(token), (rows = []) =>
        rows.map((row) => (row.id === updated.id ? updated : row)),
      );
      void queryClient.invalidateQueries({ queryKey: clinicalKeys.overview(token) });
    },
  });

  async function handleSimulate() {
    if (!body.trim()) return;
    setActionError(null);
    try {
      await simulateMutation.mutateAsync();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Hasta talebi islenemedi");
    }
  }

  async function handleSelect(conversation: ClinicalConversationSummary) {
    setActionError(null);
    setSelectedConversationId(conversation.id);
  }

  async function decideReview(review: ShadowReview, status: "approved" | "edited" | "rejected") {
    setActionError(null);
    try {
      await reviewMutation.mutateAsync({ review, status });
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Doktor onayi guncellenemedi");
    }
  }

  async function openAppointmentDetail(row: ClinicalAppointmentRow) {
    setDetailAppointment(row);
  }

  async function handleManualBooking(input: {
    full_name: string;
    phone: string;
    notes?: string;
  }): Promise<boolean> {
    if (!activeSlot) return false;
    setActionError(null);
    try {
      const slot = activeSlot;
      const [startTime] = slot.time_range.split("-").map((part) => part.trim());
      // date_label TR formatlı; gerçek datetime üretmek için bugünün tarihini
      // baz alıyoruz (demo amaçlı — production'da slot.starts_at gelecek).
      const now = new Date();
      const [hh, mm] = (startTime ?? "09:00").split(":").map(Number);
      const starts = new Date(now.getFullYear(), now.getMonth(), now.getDate(), hh || 9, mm || 0);
      await manualBookingMutation.mutateAsync({
        full_name: input.full_name.trim() || null,
        phone: input.phone.trim(),
        department: slot.department,
        starts_at: starts.toISOString(),
        physician_name: slot.doctor,
        notes: input.notes?.trim() || null,
      });
      return true;
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Randevu oluşturulamadı");
      return false;
    }
  }

  async function handleAppointmentStatus(
    appointment: ClinicalAppointmentRow,
    status: "confirmed" | "cancelled",
  ) {
    setActionError(null);
    try {
      await appointmentStatusMutation.mutateAsync({ appointmentId: appointment.id, status });
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Randevu durumu güncellenemedi");
    }
  }

  const busy = simulateMutation.isPending
    || reviewMutation.isPending
    || manualBookingMutation.isPending
    || appointmentStatusMutation.isPending;
  const queryError = [
    overviewQuery.error,
    complianceQuery.error,
    patentQuery.error,
    slotsQuery.error,
    appointmentsQuery.error,
    selectedConversationQuery.error,
    detailConversationQuery.error,
  ].find(Boolean);
  const error = actionError ?? (queryError instanceof Error ? queryError.message : queryError ? "Klinik paneli yüklenemedi" : null);

  const metrics = overview?.metrics;
  const pendingAppointmentCount = appointments.filter((row) => row.status === "pending").length;
  const conversations = overview?.conversations ?? [];
  const doctorInbox = overview?.doctor_inbox ?? [];
  const reviews = overview?.shadow_reviews ?? [];

  const selectedPersona = useMemo(
    () => personaCards.find((persona) => persona.id === personaId) ?? personaCards[0],
    [personaId],
  );

  if (overviewQuery.isLoading && !overview) {
    return <div className="clinical-panel clinical-panel--loading">Klinik operasyon kokpiti hazırlanıyor...</div>;
  }

  return (
    <div className="clinical-panel boutique-clinic-panel">
      <div className="clinic-tabbar" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "ops"}
          className={tab === "ops" ? "active" : ""}
          onClick={() => setTab("ops")}
        >
          Operasyon
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "appointments"}
          className={tab === "appointments" ? "active" : ""}
          onClick={() => setTab("appointments")}
        >
          Randevular
          {pendingAppointmentCount > 0 ? <span className="clinic-tab-badge">{pendingAppointmentCount}</span> : null}
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "pitch"}
          className={tab === "pitch" ? "active" : ""}
          onClick={() => setTab("pitch")}
        >
          Sunum
        </button>
      </div>

      {error ? <div className="error-box clinical-error">{error}</div> : null}

      {tab === "ops" ? (
        <>
      <section className="clinic-metric-strip">
        <ClinicalMetric label="Bugünkü hasta teması" value={metrics?.conversations_today ?? 0} />
        <ClinicalMetric label="Telefon araması" value={metrics?.phone_calls_today ?? 0} />
        <ClinicalMetric label="Doktor ekranında" value={metrics?.doctor_inbox_count ?? 0} tone="warning" />
        <ClinicalMetric label="Yaklaşan uyarı" value={metrics?.reminders_due ?? 0} tone="success" />
        <ClinicalMetric label="Doktor onayı" value={metrics?.pending_shadow_reviews ?? 0} tone="danger" />
      </section>

      <section className="clinic-lab-grid clinic-lab-grid--single">
        <TestLab
          slotBoard={slotBoard}
          onPick={(message) => {
            setBody(message);
            setPatientName("Test Hasta");
            setPhone("+90 555 777 88 99");
          }}
        />
      </section>

      <section className="clinic-workspace-grid">
        <div className="clinic-card clinic-call-card">
          <div className="clinical-card-top">
            <div>
              <span>Hasta girişi</span>
              <h3>Hasta konuşmasını simüle et</h3>
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
            <input value={patientName} onChange={(event) => setPatientName(event.target.value)} placeholder="Hasta adı" />
            <input value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="+90..." />
            <textarea value={body} onChange={(event) => setBody(event.target.value)} placeholder="Hastanın söylediği medikal talep" />
            <button type="button" onClick={handleSimulate} disabled={busy || !body.trim()}>
              Talebi klinik akışa düşür
            </button>
          </div>
        </div>

        <div className="clinic-card doctor-inbox-card">
          <div className="clinical-card-top">
            <div>
              <span>Doctor Inbox</span>
              <h3>İnsan onayı bekleyenler</h3>
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
              <span>Canlı hasta kaydı</span>
              <h3>{selectedConversation?.patient.full_name ?? "Hasta seç"}</h3>
            </div>
            <strong className={`clinical-status ${selectedConversation?.status === "waiting_human" ? "danger" : ""}`}>
              {selectedConversation?.status ?? "hazir"}
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
                  {message.intent ? (
                    <small>
                      {message.intent} · {Math.round((message.confidence_score ?? 0) * 100)}% ·{" "}
                      {String(message.metadata_json?.persona_name ?? message.metadata_json?.channel ?? "")}
                    </small>
                  ) : null}
                </article>
              ))
            ) : (
              <div className="clinical-empty">Hasta seçildiğinde arama ve mesaj geçmişi burada görünür.</div>
            )}
          </div>
        </div>
      </section>

      <DoctorScreen
        selectedConversation={selectedConversation}
        reviews={reviews}
        slotBoard={slotBoard}
        busy={busy}
        editingReviewId={editingReviewId}
        editedReply={editedReply}
        onEditReply={setEditedReply}
        onStartEdit={(review) => {
          setEditingReviewId(review.id);
          setEditedReply(review.draft_reply);
        }}
        onDecide={(review, status) => void decideReview(review, status)}
      />

      <section className="clinic-bottom-grid">
        <div className="clinic-card">
          <div className="clinical-card-top">
            <div>
              <span>Tüm akış</span>
              <h3>Hasta temasları</h3>
            </div>
          </div>
          <ConversationList
            conversations={conversations}
            selectedId={selectedConversation?.id}
            empty="Henüz hasta teması yok."
            onSelect={handleSelect}
          />
        </div>

        <div className="clinic-card">
          <div className="clinical-card-top">
            <div>
              <span>Doktor onayı</span>
              <h3>Riskli veya belirsiz cevaplar</h3>
            </div>
          </div>
          <div className="clinical-review-list">
            {reviews.length ? reviews.map((review) => (
              <ShadowReviewCard
                key={review.id}
                review={review}
                editing={editingReviewId === review.id}
                editedReply={editedReply}
                busy={busy}
                onEditedReplyChange={setEditedReply}
                onApprove={() => void decideReview(review, "approved")}
                onStartEdit={() => {
                  setEditingReviewId(review.id);
                  setEditedReply(review.draft_reply);
                }}
                onSubmitEdit={() => void decideReview(review, "edited")}
                onReject={() => void decideReview(review, "rejected")}
              />
            )) : <div className="clinical-empty">Doktor onayı bekleyen kayıt yok.</div>}
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
          <DoctorScheduleCalendar appointments={appointments} onOpenDetail={openAppointmentDetail} />
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
          }}
        />
      ) : null}
    </div>
  );
}
