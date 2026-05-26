import { useEffect, useRef, useState } from "react";

import {
  confirmAppointment,
  holdSlotOffer,
  sendPatientMessage,
  updatePatientIdentity,
  type PublicClinicView,
  type PublicMessageView,
  type PublicSlotOfferView,
} from "../../api/patientClient";

interface Props {
  clinic: PublicClinicView;
  sessionToken: string;
  conversationId: number;
  /**
   * Backend `start_patient_conversation` döndüğünde proactive welcome
   * mesajını verir. Chat ilk açılışında bu, assistant balonu olarak
   * gösterilir. Sonraki yenileme döngülerinde session'dan kaybolur,
   * o yüzden default static welcome'a fallback yapıyoruz.
   */
  initialWelcome?: string | null;
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
  initialWelcome,
  onAppointmentConfirmed,
  onStartOver,
}: Props) {
  // Yeni akış: backend proactive welcome'ı assistant olarak basıyor.
  // Bunu chat'in ilk balonu olarak göster; ek olarak küçük bir system
  // mesajı KVKK / acil uyarısı ekliyor.
  const [bubbles, setBubbles] = useState<Bubble[]>(() => {
    const ts = new Date().toISOString();
    const initial: Bubble[] = [];
    if (initialWelcome) {
      initial.push({
        id: "assistant-welcome",
        sender: "assistant",
        body: initialWelcome,
        ts,
      });
    } else {
      initial.push({
        id: "assistant-welcome-fallback",
        sender: "assistant",
        body: `Merhaba, ben ${clinic.name} AI asistanı. Size nasıl yardımcı olabilirim?`,
        ts,
      });
    }
    initial.push({
      id: "system-emergency-hint",
      sender: "system",
      body:
        "ℹ Şikayetinizi ve tercih ettiğiniz gün/saati yazarsanız randevu oluşturabilirim. " +
        "Acil semptomlarınız varsa lütfen 112'yi arayın.",
      ts,
    });
    return initial;
  });
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversationStatus, setConversationStatus] = useState<string>("active");
  const [requiresReview, setRequiresReview] = useState(false);
  const [emergencyDetected, setEmergencyDetected] = useState(false);
  const [bookingDepartment, setBookingDepartment] = useState<string | null>(null);
  const [slotOffers, setSlotOffers] = useState<PublicSlotOfferView[]>([]);
  const [selectedSlot, setSelectedSlot] = useState<PublicSlotOfferView | null>(null);
  const [confirming, setConfirming] = useState(false);

  // Kimlik toplama gate'i: AI henüz LLM tool calling yapamadığı için
  // hasta randevu onayına basmadan ÖNCE kimliğini soruyoruz. Backend'de
  // şu an placeholder ("Misafir Hasta" + sahte telefon) var; gerçek
  // randevu için PATCH /patient ile günceller, sonra confirm akışına geçer.
  const [identityCollected, setIdentityCollected] = useState(false);
  const [identityFormOpen, setIdentityFormOpen] = useState(false);
  const [identityName, setIdentityName] = useState("");
  const [identityPhone, setIdentityPhone] = useState("");
  const [identityError, setIdentityError] = useState<string | null>(null);
  const [savingIdentity, setSavingIdentity] = useState(false);

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
      if (res.slot_offers.length > 0) {
        setSlotOffers(res.slot_offers);
        setSelectedSlot(null);
        setBookingDepartment(res.slot_offers[0].department);
      }
      setRequiresReview(res.requires_human_review);
      setConversationStatus(res.conversation_status);
    } catch (err) {
      setError(err instanceof Error ? err.message : "send_failed");
    } finally {
      setSending(false);
    }
  }

  function normalizePhone(raw: string): string | null {
    const cleaned = raw.replace(/[\s\-()]/g, "");
    const match = cleaned.match(/^(?:\+90|90|0)?(5\d{9})$/);
    return match ? `+90${match[1]}` : null;
  }

  /**
   * Kullanıcı "Randevu talebimi gönder" butonuna basınca burası çalışır.
   * Kimlik henüz toplanmamışsa form'u açar ve dönmez; toplanmışsa direkt
   * confirm endpoint'ine gider.
   */
  function handleConfirmAppointment() {
    if (!bookingDepartment || !selectedSlot) {
      setError("Lütfen önce klinik takviminden gelen uygun saatlerden birini seçin.");
      return;
    }
    if (!identityCollected) {
      setError(null);
      setIdentityFormOpen(true);
      return;
    }
    void proceedWithAppointmentConfirm();
  }

  async function proceedWithAppointmentConfirm() {
    if (!bookingDepartment || !selectedSlot) return;
    setConfirming(true);
    setError(null);
    try {
      const held = selectedSlot.status === "held"
        ? { slot_offer: selectedSlot }
        : await holdSlotOffer(clinic.slug, conversationId, sessionToken, selectedSlot.id);
      await confirmAppointment(clinic.slug, conversationId, sessionToken, {
        department: held.slot_offer.department,
        slot_offer_id: held.slot_offer.id,
        notes: "Hasta web chat üzerinden onayladı.",
      });
      onAppointmentConfirmed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "appointment_failed");
    } finally {
      setConfirming(false);
    }
  }

  /**
   * Kimlik form'undan submit edilince: PATCH /patient → identityCollected=true →
   * randevu onay akışını başlat. Hata olursa form açık kalır, kullanıcı tekrar
   * deneyebilir.
   */
  async function submitIdentityAndProceed(e?: React.FormEvent) {
    e?.preventDefault();
    setIdentityError(null);
    if (identityName.trim().length < 2) {
      setIdentityError("Lütfen adınızı ve soyadınızı girin.");
      return;
    }
    const normalized = normalizePhone(identityPhone);
    if (!normalized) {
      setIdentityError("Lütfen geçerli bir TR cep numarası girin (örn: 0532 123 45 67).");
      return;
    }
    setSavingIdentity(true);
    try {
      await updatePatientIdentity(clinic.slug, conversationId, sessionToken, {
        full_name: identityName.trim(),
        phone: normalized,
      });
      setIdentityCollected(true);
      setIdentityFormOpen(false);
      // Chat'e bilgilendirme balonu — şeffaflık için kayda alındığını söyle.
      setBubbles((prev) => [
        ...prev,
        {
          id: `sys-id-${Date.now()}`,
          sender: "system",
          body: `✓ Kayıt: ${identityName.trim()} · ${normalized}. Randevu oluşturuluyor…`,
          ts: new Date().toISOString(),
        },
      ]);
      await proceedWithAppointmentConfirm();
    } catch (err) {
      setIdentityError(err instanceof Error ? err.message : "identity_update_failed");
    } finally {
      setSavingIdentity(false);
    }
  }

  const chatLocked = emergencyDetected || conversationStatus === "closed";
  const canConfirmAppointment = Boolean(selectedSlot && bookingDepartment);

  function slotTimeLabel(offer: PublicSlotOfferView): string {
    const formatter = new Intl.DateTimeFormat("tr-TR", {
      weekday: "long",
      day: "2-digit",
      month: "long",
      hour: "2-digit",
      minute: "2-digit",
    });
    return formatter.format(new Date(offer.starts_at));
  }

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
            <strong>{bookingDepartment}</strong> için gerçek klinik takviminden
            üretilen uygun saatler:
          </div>
          {slotOffers.length > 0 ? (
            <div className="patient-slot-list" role="listbox" aria-label="Uygun randevu saatleri">
              {slotOffers.map((offer) => (
                <button
                  key={offer.id}
                  type="button"
                  className={`patient-slot-card ${selectedSlot?.id === offer.id ? "is-selected" : ""}`}
                  onClick={() => {
                    setSelectedSlot(offer);
                    setError(null);
                  }}
                >
                  <span className="patient-slot-time">{slotTimeLabel(offer)}</span>
                  <span className="patient-slot-doctor">
                    {offer.physician_name ?? "Klinik ekibi"}
                  </span>
                  <span className="patient-slot-status">
                    {offer.status === "held" ? "Tutuldu" : "15 dk geçerli teklif"}
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <div className="patient-banner-soft">
              Uygun saat için klinik ekibi takvimi kontrol ediyor. Net slot gelmeden
              randevu oluşturulmaz.
            </div>
          )}
          <button
            type="button"
            className="patient-cta"
            onClick={handleConfirmAppointment}
            disabled={confirming || savingIdentity || !canConfirmAppointment}
          >
            {confirming
              ? "Onaylanıyor…"
              : !identityCollected
                ? "Devam et — Bilgilerinizi alalım"
                : "Seçili saati randevuya çevir"}
          </button>

          {/* Kimlik gate: hasta randevu onayına bastıysa ama hâlâ
              placeholder ise inline mini form. Sadece bir kez doldurulur. */}
          {identityFormOpen && !identityCollected ? (
            <form className="patient-identity-form" onSubmit={submitIdentityAndProceed}>
              <div className="patient-identity-header">
                <strong>Son bir adım kaldı</strong>
                <p>
                  Randevu kaydınız ve SMS onayınız için sadece ad-soyad ve
                  cep telefonunuz gerekli. Bu bilgiler yerel sunucularımızda
                  KVKK uyumlu olarak saklanır.
                </p>
              </div>

              <label className="patient-field">
                <span>Ad-soyad</span>
                <input
                  type="text"
                  autoComplete="name"
                  required
                  value={identityName}
                  onChange={(e) => setIdentityName(e.target.value)}
                  placeholder="Ahmet Yılmaz"
                  disabled={savingIdentity}
                />
              </label>

              <label className="patient-field">
                <span>Cep telefonu</span>
                <input
                  type="tel"
                  autoComplete="tel"
                  inputMode="numeric"
                  required
                  value={identityPhone}
                  onChange={(e) => setIdentityPhone(e.target.value)}
                  placeholder="0532 123 45 67"
                  disabled={savingIdentity}
                />
              </label>

              {identityError ? (
                <div className="patient-error-line">{identityError}</div>
              ) : null}

              <div className="patient-consent-actions">
                <button
                  type="submit"
                  className="patient-cta"
                  disabled={savingIdentity}
                >
                  {savingIdentity ? "Kaydediliyor…" : "Randevuyu oluştur"}
                </button>
                <button
                  type="button"
                  className="patient-cta-ghost"
                  onClick={() => setIdentityFormOpen(false)}
                  disabled={savingIdentity}
                >
                  Vazgeç
                </button>
              </div>
            </form>
          ) : null}
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
