import { useEffect, useMemo, useState } from "react";

import {
  getClinicalConversation,
  getClinicalComplianceProfile,
  getClinicalOverview,
  getClinicalPatentDossier,
  getClinicalSlotBoard,
  simulateVoiceCall,
  simulateWhatsAppMessage,
  updateShadowReview,
} from "../api/client";
import type {
  ClinicalComplianceProfile,
  ClinicalConversationDetail,
  ClinicalConversationSummary,
  ClinicalOverview,
  ClinicalPatentDossier,
  ClinicalSlotBoard,
  ClinicalSlotItem,
  ShadowReview,
} from "../types/api";

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
  const [overview, setOverview] = useState<ClinicalOverview | null>(null);
  const [complianceProfile, setComplianceProfile] = useState<ClinicalComplianceProfile | null>(null);
  const [patentDossier, setPatentDossier] = useState<ClinicalPatentDossier | null>(null);
  const [slotBoard, setSlotBoard] = useState<ClinicalSlotBoard | null>(null);
  const [selectedConversation, setSelectedConversation] = useState<ClinicalConversationDetail | null>(null);
  const [phone, setPhone] = useState("+90 555 111 22 33");
  const [patientName, setPatientName] = useState("Ayse Hasta");
  const [body, setBody] = useState("Arka disim zonkluyor, yarin icin dis hekimi randevusu almak istiyorum.");
  const [channel, setChannel] = useState<ChannelMode>("phone");
  const [personaId, setPersonaId] = useState<PersonaId>("selin");
  const [editingReviewId, setEditingReviewId] = useState<number | null>(null);
  const [editedReply, setEditedReply] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"ops" | "pitch">("ops");

  useEffect(() => {
    void loadClinical();
  }, [token]);

  async function loadClinical(nextConversationId?: number) {
    setError(null);
    try {
      const [data, compliance, patent, slots] = await Promise.all([
        getClinicalOverview(token),
        getClinicalComplianceProfile(token),
        getClinicalPatentDossier(token),
        getClinicalSlotBoard(token),
      ]);
      setOverview(data);
      setComplianceProfile(compliance);
      setPatentDossier(patent);
      setSlotBoard(slots);
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

      <section className="clinic-lab-grid">
        <SlotBoardCard slotBoard={slotBoard} />
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
                  <button type="button" onClick={() => void decideReview(review, "approved")} disabled={busy}>Onayla</button>
                  <button type="button" onClick={() => { setEditingReviewId(review.id); setEditedReply(review.draft_reply); }} disabled={busy}>Düzenle</button>
                  {editingReviewId === review.id ? (
                    <button type="button" onClick={() => void decideReview(review, "edited")} disabled={busy || !editedReply.trim()}>Düzenlemeyi gönder</button>
                  ) : null}
                  <button type="button" className="danger" onClick={() => void decideReview(review, "rejected")} disabled={busy}>Reddet</button>
                </div>
              </article>
            )) : <div className="clinical-empty">Doktor onayı bekleyen kayıt yok.</div>}
          </div>
        </div>
      </section>
        </>
      ) : (
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
      )}
    </div>
  );
}

function SlotBoardCard({ slotBoard }: { slotBoard: ClinicalSlotBoard | null }) {
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
      <div className="slot-board-list">
        {schedule.map((slot) => <SlotRow key={slot.id} slot={slot} />)}
      </div>
    </div>
  );
}

function SlotRow({ slot }: { slot: ClinicalSlotItem }) {
  return (
    <article className={`slot-row ${slot.status}`}>
      <div>
        <strong>{slot.department}</strong>
        <span>{slot.doctor} · {slot.date_label} · {slot.time_range}</span>
      </div>
      <div>
        <b>{slot.booked}/{slot.capacity}</b>
        <small>{slot.status === "full" ? "Dolu" : slot.status === "limited" ? "Son slot" : "Uygun"}</small>
      </div>
    </article>
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
        <button
          key={conversation.id}
          type="button"
          className={`clinical-conversation-row ${conversation.doctor_inbox ? "doctor" : ""} ${selectedId === conversation.id ? "selected" : ""}`}
          onClick={() => void onSelect(conversation)}
        >
          <strong>{conversation.patient.full_name ?? conversation.patient.phone}</strong>
          <span>
            {conversation.channel} · {conversation.persona_name ?? "AI"} · {conversation.intent?.replace(/_/g, " ") ?? "niyet bekleniyor"}
          </span>
          <p>{conversation.last_message_preview ?? "Henüz mesaj yok"}</p>
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
