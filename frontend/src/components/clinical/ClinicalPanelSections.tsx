import { useState } from "react";

import type {
  ClinicalAppointmentRow,
  ClinicalConversationDetail,
  ClinicalConversationSummary,
  ClinicalSlotBoard,
  ClinicalSlotItem,
  ShadowReview,
} from "../../types/api";

const trDateTime = new Intl.DateTimeFormat("tr-TR", { dateStyle: "short", timeStyle: "short" });
const trDay = new Intl.DateTimeFormat("tr-TR", { weekday: "long", day: "2-digit", month: "long" });
const trTime = new Intl.DateTimeFormat("tr-TR", { hour: "2-digit", minute: "2-digit" });

export function SlotBoardCard({
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

export function SlotRow({ slot, onOpen }: { slot: ClinicalSlotItem; onOpen: (slot: ClinicalSlotItem) => void }) {
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

export function SlotAppointmentsModal({
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

export function AppointmentRow({
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
            ? `${trDateTime.format(new Date(row.starts_at))} · ${row.duration_minutes} dk`
            : `Talep: ${trDateTime.format(new Date(row.created_at))}`}
        </small>
        {row.visit_reason ? <small className="appointment-request-reason">{row.visit_reason}</small> : null}
        {row.procedures.length ? (
          <small className="appointment-request-procedures">
            {row.procedures.length} işlem · {row.procedures.filter((item) => item.status === "completed").length} tamamlandı
          </small>
        ) : null}
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

export function DoctorScheduleCalendar({
  appointments,
  onOpenDetail,
}: {
  appointments: ClinicalAppointmentRow[];
  onOpenDetail: (row: ClinicalAppointmentRow) => void;
}) {
  const scheduled = appointments
    .filter((row) => row.status !== "cancelled" && row.starts_at)
    .sort((a, b) => new Date(a.starts_at!).getTime() - new Date(b.starts_at!).getTime());
  const groups = scheduled.reduce<Array<{ key: string; date: Date; rows: ClinicalAppointmentRow[] }>>((result, row) => {
    const date = new Date(row.starts_at!);
    const key = `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
    const current = result[result.length - 1];
    if (!current || current.key !== key) result.push({ key, date, rows: [row] });
    else current.rows.push(row);
    return result;
  }, []);

  return (
    <section className="clinic-card doctor-calendar">
      <div className="clinical-card-top">
        <div>
          <span>Hekim bazlı saatli görünüm</span>
          <h3>Klinik ajandası</h3>
        </div>
        <b>{scheduled.length}</b>
      </div>
      {groups.length ? (
        <div className="doctor-calendar-days">
          {groups.map((group) => (
            <section key={group.key} className="doctor-calendar-day">
              <h4>{trDay.format(group.date)}</h4>
              <div className="doctor-calendar-slots">
                {group.rows.map((row) => (
                  <button key={row.id} type="button" className={`doctor-calendar-slot ${row.status}`} onClick={() => onOpenDetail(row)}>
                    <time>
                      <strong>{trTime.format(new Date(row.starts_at!))}</strong>
                      <small>{row.ends_at ? trTime.format(new Date(row.ends_at)) : `${row.duration_minutes} dk`}</small>
                    </time>
                    <span className="doctor-calendar-line" />
                    <div>
                      <strong>{row.patient_name ?? `Hasta #${row.patient_id}`}</strong>
                      <span>{row.physician_name ?? "Hekim ataması bekliyor"} · {row.department}</span>
                      <small>{row.visit_reason ?? "Ziyaret nedeni henüz girilmedi"}</small>
                    </div>
                    <span className={`appointment-request-badge ${row.status}`}>
                      {APPOINTMENT_STATUS_LABELS[row.status] ?? row.status}
                    </span>
                  </button>
                ))}
              </div>
            </section>
          ))}
        </div>
      ) : <div className="clinical-empty">Saat atanmış aktif randevu yok.</div>}
    </section>
  );
}

export function AppointmentBucket({
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

export function AppointmentRequestsCard({
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

export function TestLab({
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

export function DoctorScreen({
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

export function ConversationList({
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

export function AppointmentDetailModal({
  appointment,
  conversation,
  onClose,
}: {
  appointment: ClinicalAppointmentRow;
  conversation: ClinicalConversationDetail | null;
  onClose: () => void;
}) {
  const phoneDigits = appointment.patient_phone ? appointment.patient_phone.replace(/[^\d+]/g, "") : null;
  const waNumber = phoneDigits ? phoneDigits.replace(/^\+/, "") : null;
  return (
    <div className="slot-modal-overlay" role="dialog" aria-modal="true" onClick={onClose}>
      <div className="slot-modal appointment-detail-modal" onClick={(event) => event.stopPropagation()}>
        <div className="slot-modal-head">
          <div>
            <span>Randevu detayı</span>
            <h3>{appointment.patient_name ?? `Hasta #${appointment.patient_id}`}</h3>
            <p>
              {appointment.department}
              {appointment.physician_name ? ` · ${appointment.physician_name}` : ""}
              {appointment.branch_name ? ` · ${appointment.branch_name}` : ""}
            </p>
          </div>
          <button type="button" className="slot-modal-close" onClick={onClose} aria-label="Kapat">×</button>
        </div>

        <div className="appointment-detail-meta appointment-detail-meta--calendar">
          <article>
            <span>Saat</span>
            <strong>
              {appointment.starts_at
                ? trDateTime.format(new Date(appointment.starts_at))
                : "—"}
            </strong>
          </article>
          <article>
            <span>Durum</span>
            <strong className={`appointment-request-badge ${appointment.status}`}>
              {APPOINTMENT_STATUS_LABELS[appointment.status] ?? appointment.status}
            </strong>
          </article>
          <article>
            <span>Telefon</span>
            <strong>{appointment.patient_phone ?? "—"}</strong>
          </article>
          <article>
            <span>Süre / bitiş</span>
            <strong>{appointment.ends_at ? `${appointment.duration_minutes} dk · ${trTime.format(new Date(appointment.ends_at))}` : `${appointment.duration_minutes} dk`}</strong>
          </article>
        </div>

        {phoneDigits ? (
          <div className="appointment-detail-contact">
            <a href={`tel:${phoneDigits}`}>📞 Ara</a>
            {waNumber ? (
              <a href={`https://wa.me/${waNumber}`} target="_blank" rel="noreferrer">💬 WhatsApp</a>
            ) : null}
          </div>
        ) : null}

        <div className="appointment-detail-clinical">
          <span>Ziyaret nedeni</span>
          <p>{appointment.visit_reason ?? "Henüz ziyaret nedeni girilmedi."}</p>
        </div>

        <div className="appointment-detail-procedure-plan">
          <div className="appointment-detail-section-head">
            <div>
              <span>Klinik işlem planı</span>
              <strong>Hastaya uygulanacak işlemler</strong>
            </div>
            <b>{appointment.procedures.length}</b>
          </div>
          {appointment.procedures.length ? (
            <ul>
              {appointment.procedures.map((procedure) => (
                <li key={procedure.id} className={`procedure-plan-row ${procedure.status}`}>
                  <span className="procedure-plan-dot" />
                  <div>
                    <strong>{procedure.name}</strong>
                    <small>{[procedure.tooth ? `Diş ${procedure.tooth}` : null, procedure.code, procedure.notes].filter(Boolean).join(" · ")}</small>
                  </div>
                  <em>{procedure.status === "completed" ? "Tamamlandı" : procedure.status === "in_progress" ? "İşlemde" : procedure.status === "cancelled" ? "İptal" : "Planlandı"}</em>
                </li>
              ))}
            </ul>
          ) : <div className="clinical-empty">İşlem planı henüz hekim tarafından oluşturulmadı.</div>}
        </div>

        {appointment.notes ? (
          <div className="appointment-detail-notes">
            <span>Not</span>
            <p>{appointment.notes}</p>
          </div>
        ) : null}

        <div className="appointment-detail-history">
          <h4>Sohbet geçmişi</h4>
          {appointment.conversation_id ? (
            conversation ? (
              conversation.messages.length ? (
                <ul>
                  {conversation.messages.map((message) => (
                    <li key={message.id} className={`appointment-detail-message ${message.sender}`}>
                      <small>
                        {message.sender === "patient"
                          ? "Hasta"
                          : message.sender === "assistant"
                          ? "AI"
                          : message.sender === "operator"
                          ? "Operatör"
                          : "Sistem"}
                        {" · "}
                        {trDateTime.format(new Date(message.created_at))}
                      </small>
                      <p>{message.content}</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="clinical-empty">Bu sohbette mesaj yok.</div>
              )
            ) : (
              <div className="clinical-empty">Sohbet yükleniyor…</div>
            )
          ) : (
            <div className="clinical-empty">Bu randevu operatör tarafından panelden açıldı.</div>
          )}
        </div>
      </div>
    </div>
  );
}

export function ClinicalMetric({ label, value, tone }: { label: string; value: string | number; tone?: "success" | "warning" | "danger" }) {
  return (
    <div className={`clinical-metric ${tone ?? ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
