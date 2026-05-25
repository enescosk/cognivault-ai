import { useEffect, useRef, useState } from "react";

import {
  confirmAppointment,
  sendPatientMessage,
  type PublicClinicView,
  type PublicMessageView,
} from "../../api/patientClient";

interface Props {
  clinic: PublicClinicView;
  sessionToken: string;
  conversationId: number;
  onAppointmentConfirmed: () => void;
  onStartOver: () => void;
}

type Bubble = {
  id: string | number;
  sender: "patient" | "assistant" | "system";
  body: string;
  intent?: string | null;
  meta?: Record<string, unknown> | null;
  ts: string;
};

/**
 * Canlı AI sohbet ekranı.
 *
 * MVP: streaming yok — POST /messages bir round-trip; AI cevabı geldiğinde
 * iki balon birden eklenir. Faz P3'te SSE streaming.
 *
 * Acil semptom (medical_emergency intent) algılanırsa sayfanın tepesinde
 * kırmızı banner ve 112 yönlendirmesi; chat kilitlenir, onStartOver ile
 * kapatılır.
 */
export function PatientChatRoom({
  clinic,
  sessionToken,
  conversationId,
  onAppointmentConfirmed,
  onStartOver,
}: Props) {
  const [bubbles, setBubbles] = useState<Bubble[]>([
    {
      id: "system-welcome",
      sender: "system",
      body:
        "AI asistanı hazır. Şikayetinizi veya randevu talebinizi yazabilirsiniz. " +
        "Acil semptomlarınız varsa lütfen 112'yi arayın.",
      ts: new Date().toISOString(),
    },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversationStatus, setConversationStatus] = useState<string>("active");
  const [requiresReview, setRequiresReview] = useState(false);
  const [emergencyDetected, setEmergencyDetected] = useState(false);
  const [bookingDepartment, setBookingDepartment] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  const scrollerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollerRef.current) {
      scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
    }
  }, [bubbles.length]);

  function appendFromView(view: PublicMessageView): void {
    setBubbles((prev) => [
      ...prev,
      {
        id: view.id,
        sender: view.sender === "operator" || view.sender === "system" ? "system" : view.sender,
        body: view.body,
        intent: view.intent,
        meta: view.metadata_json,
        ts: view.created_at,
      },
    ]);
  }

  async function handleSend(e?: React.FormEvent) {
    e?.preventDefault();
    if (!input.trim() || sending) return;
    const body = input.trim();
    setInput("");
    setSending(true);
    setError(null);
    try {
      const res = await sendPatientMessage(clinic.slug, conversationId, sessionToken, body);
      appendFromView(res.patient_message);
      if (res.assistant_message) {
        appendFromView(res.assistant_message);
        if (res.assistant_message.intent === "medical_emergency") {
          setEmergencyDetected(true);
        }
        // Backend AI book_appointment intent + makul güven → booking section'ı aç
        if (
          res.assistant_message.intent === "book_appointment" &&
          (res.assistant_message.confidence_score ?? 0) >= 0.78
        ) {
          // metadata.data.intake.specialty → muhtemel branş
          const data = (res.assistant_message.metadata_json?.data as { intake?: { specialty?: string } } | undefined) ?? undefined;
          setBookingDepartment(data?.intake?.specialty ?? "Genel Diş Hekimliği");
        }
      } else if (res.requires_human_review) {
        // Asistan mesajı yazılmadıysa shadow review akışındayız → bilgi balonu ekle
        setBubbles((prev) => [
          ...prev,
          {
            id: `sys-${Date.now()}`,
            sender: "system",
            body:
              "Mesajınızı aldık. Klinik personeli kısa sürede size yazılı olarak dönüş yapacak.",
            ts: new Date().toISOString(),
          },
        ]);
      }
      setRequiresReview(res.requires_human_review);
      setConversationStatus(res.conversation_status);
    } catch (err) {
      setError(err instanceof Error ? err.message : "send_failed");
    } finally {
      setSending(false);
    }
  }

  async function handleConfirmAppointment() {
    if (!bookingDepartment) return;
    setConfirming(true);
    try {
      await confirmAppointment(clinic.slug, conversationId, sessionToken, {
        department: bookingDepartment,
        starts_at: null,
        notes: "Hasta web chat üzerinden onayladı.",
      });
      onAppointmentConfirmed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "appointment_failed");
    } finally {
      setConfirming(false);
    }
  }

  const chatLocked = emergencyDetected || conversationStatus === "closed";

  return (
    <div className="patient-card patient-chat-card">
      {emergencyDetected ? (
        <div className="patient-emergency" role="alert">
          <div className="patient-emergency-dot" aria-hidden />
          <div>
            <strong>Acil durum tespit edildi.</strong>
            <p>
              Lütfen vakit kaybetmeden <a href="tel:112">112'yi arayın</a> veya en yakın
              acil servise başvurun. Klinik ekibimize de yüksek öncelikli alarm
              iletildi.
            </p>
          </div>
        </div>
      ) : null}

      <header className="patient-chat-header">
        <div>
          <h2>{clinic.name}</h2>
          <span className="patient-chat-sub">AI asistanı · #{conversationId}</span>
        </div>
        <button type="button" className="patient-cta-ghost" onClick={onStartOver}>
          Sohbeti kapat
        </button>
      </header>

      <div className="patient-chat-scroller" ref={scrollerRef}>
        {bubbles.map((b) => (
          <div key={b.id} className={`patient-bubble patient-bubble-${b.sender}`}>
            <div className="patient-bubble-body">{b.body}</div>
            {b.intent ? <div className="patient-bubble-meta">{b.intent}</div> : null}
          </div>
        ))}
        {sending ? (
          <div className="patient-bubble patient-bubble-assistant patient-bubble-typing">
            <span />
            <span />
            <span />
          </div>
        ) : null}
      </div>

      {bookingDepartment && !chatLocked ? (
        <div className="patient-booking-card">
          <div>
            <strong>{bookingDepartment}</strong> için randevu talebinizi
            onaylayalım mı?
          </div>
          <button
            type="button"
            className="patient-cta"
            onClick={handleConfirmAppointment}
            disabled={confirming}
          >
            {confirming ? "Onaylanıyor…" : "Randevu talebimi gönder"}
          </button>
        </div>
      ) : null}

      {error ? <div className="patient-error-line">{error}</div> : null}

      <form className="patient-chat-input" onSubmit={handleSend}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={
            chatLocked ? "Sohbet kilitlendi" : "Mesajınızı yazın…"
          }
          disabled={chatLocked || sending}
        />
        <button type="submit" className="patient-cta" disabled={chatLocked || sending || !input.trim()}>
          Gönder
        </button>
      </form>

      {requiresReview && !emergencyDetected ? (
        <div className="patient-banner-soft">
          Mesajınız klinik personelinin onayını bekliyor — kısa süre içinde dönüş yapılacak.
        </div>
      ) : null}
    </div>
  );
}
