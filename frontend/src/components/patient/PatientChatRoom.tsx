import { useCallback, useEffect, useRef, useState } from "react";

import {
  confirmAppointment,
  holdSlotOffer,
  sendPatientMessage,
  synthesizePublicSpeech,
  updatePatientIdentity,
  type PublicClinicView,
  type PublicSlotOfferView,
} from "../../api/patientClient";

/**
 * Doğal sesli yanıt — OpenAI TTS (nova) backend üzerinden. MP3'ü çalar; başarısız
 * olursa (servis kapalı / ağ) tarayıcı Web Speech'e fallback yapar. `enabled`
 * manuel ses aç/kapat içindir.
 */
function useVoice(slug: string) {
  const [enabled, setEnabled] = useState(true);
  const enabledRef = useRef(true);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  useEffect(() => { enabledRef.current = enabled; }, [enabled]);

  const stop = useCallback(() => {
    if (audioRef.current) {
      try { audioRef.current.pause(); } catch { /* ignore */ }
      audioRef.current = null;
    }
    if (typeof window !== "undefined" && window.speechSynthesis) window.speechSynthesis.cancel();
  }, []);

  const speakBrowser = useCallback((text: string, onEnd?: () => void) => {
    if (typeof window === "undefined" || !window.speechSynthesis) { onEnd?.(); return; }
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "tr-TR";
    u.rate = 1.05;
    const v = window.speechSynthesis.getVoices().find((x) => x.lang?.startsWith("tr"));
    if (v) u.voice = v;
    u.onend = () => onEnd?.();
    u.onerror = () => onEnd?.();
    window.speechSynthesis.speak(u);
  }, []);

  const speak = useCallback(
    async (text: string, onEnd?: () => void) => {
      if (!enabledRef.current || !text || !text.trim()) { onEnd?.(); return; }
      stop();
      try {
        const buf = await synthesizePublicSpeech(slug, text);
        const url = URL.createObjectURL(new Blob([buf], { type: "audio/mpeg" }));
        const audio = new Audio(url);
        audioRef.current = audio;
        audio.onended = () => { URL.revokeObjectURL(url); onEnd?.(); };
        audio.onerror = () => { URL.revokeObjectURL(url); onEnd?.(); };
        await audio.play();
      } catch {
        speakBrowser(text, onEnd);
      }
    },
    [slug, stop, speakBrowser],
  );

  const toggle = useCallback(() => {
    setEnabled((cur) => { if (cur) stop(); return !cur; });
  }, [stop]);

  const enable = useCallback(() => setEnabled(true), []);

  useEffect(() => () => stop(), [stop]);
  return { enabled, toggle, enable, speak, stop };
}

/**
 * Tarayıcı Web Speech Recognition (STT) — sesli görüşmede hastanın konuşmasını
 * metne çevirir. Tek seferlik tanıma; her turda yeni instance. Sadece localhost/HTTPS.
 */
const SpeechRecognitionImpl: any =
  typeof window !== "undefined"
    ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    : null;

function useSpeechRecognition(lang = "tr-TR") {
  const supported = Boolean(SpeechRecognitionImpl);
  const recRef = useRef<any>(null);

  const stop = useCallback(() => {
    try { recRef.current?.abort?.(); } catch { /* ignore */ }
  }, []);

  const start = useCallback(
    (onResult: (transcript: string) => void) => {
      if (!SpeechRecognitionImpl) return;
      try { recRef.current?.abort?.(); } catch { /* ignore */ }
      const rec = new SpeechRecognitionImpl();
      rec.lang = lang;
      rec.interimResults = false;
      rec.maxAlternatives = 1;
      rec.continuous = false;
      rec.onresult = (e: any) => {
        const t = e?.results?.[0]?.[0]?.transcript ?? "";
        if (t && t.trim()) onResult(t.trim());
      };
      recRef.current = rec;
      try { rec.start(); } catch { /* ignore */ }
    },
    [lang],
  );

  useEffect(() => () => { try { recRef.current?.abort?.(); } catch { /* ignore */ } }, []);
  return { supported, start, stop };
}

interface Props {
  clinic: PublicClinicView;
  sessionToken: string;
  conversationId: number;
  initialWelcome?: string | null;
  onAppointmentConfirmed: () => void;
  onStartOver: () => void;
}

type Bubble = {
  id: string | number;
  sender: "patient" | "assistant" | "system";
  body: string;
  ts: string;
};

type Step = "name" | "complaint" | "phone" | "slot" | "done";

const WEEKDAYS = ["Pazar", "Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi"];
const ORDINALS: Array<[RegExp, number]> = [
  [/(ilk|birinci|ilki|en erken|en yak)/i, 0],
  [/(ikinci|2\.)/i, 1],
  [/(üçüncü|ucuncu|3\.)/i, 2],
  [/(dördüncü|dorduncu|4\.)/i, 3],
];

function normalizePhone(raw: string): string | null {
  const cleaned = raw.replace(/[^\d+]/g, "");
  const m = cleaned.match(/^(?:\+?90|0)?(5\d{9})$/);
  return m ? `+90${m[1]}` : null;
}

function cleanName(raw: string): string {
  let t = raw.trim().replace(/[.,!?]+$/g, "");
  t = t.replace(/^(benim\s+)?(ad[ıi]m|ismim|ben)\s+/i, "");
  t = t.replace(/\s+(ben(im)?|olur|oluyor)$/i, "");
  if (t.length < 2) t = raw.trim();
  return t.split(/\s+/).map((w) => w.charAt(0).toLocaleUpperCase("tr") + w.slice(1)).join(" ");
}

function isCloseIntent(text: string): boolean {
  return /(teşekkür|tesekkur|sağ ?ol|sag ?ol|kapat|hoşça|hosca|görüşürüz|gorusuruz|yeterli|bu kadar|iyi günler|iyi gunler|gerek yok|istemiyorum)/i.test(text);
}

export function PatientChatRoom({
  clinic,
  sessionToken,
  conversationId,
  onAppointmentConfirmed,
  onStartOver,
}: Props) {
  const greeting =
    `Merhaba, ben ${clinic.name} asistanı. Size nasıl yardımcı olabilirim? ` +
    `Şikayetinizi kısaca anlatır mısınız? Örneğin diş ağrısı, dolgu ya da implant gibi.`;

  const [bubbles, setBubbles] = useState<Bubble[]>(() => [
    { id: "assistant-greeting", sender: "assistant", body: greeting, ts: new Date().toISOString() },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [emergency, setEmergency] = useState(false);
  const [step, setStep] = useState<Step>("complaint");
  const [slots, setSlots] = useState<PublicSlotOfferView[]>([]);

  // Çağrı modu
  const [callActive, setCallActive] = useState(false);
  const [callPhase, setCallPhase] = useState<"idle" | "listening" | "thinking" | "speaking">("idle");
  const callActiveRef = useRef(false);
  useEffect(() => { callActiveRef.current = callActive; }, [callActive]);

  // Async mantıkta güncel kalması gereken toplanan veriler
  const dataRef = useRef({ name: "", complaint: "", phone: "", department: "" });
  const slotsRef = useRef<PublicSlotOfferView[]>([]);
  const stepRef = useRef<Step>("complaint");
  useEffect(() => { stepRef.current = step; }, [step]);

  const voice = useVoice(clinic.slug);
  const rec = useSpeechRecognition("tr-TR");
  const scrollerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollerRef.current) scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
  }, [bubbles, busy]);

  const addBubble = useCallback((sender: Bubble["sender"], body: string) => {
    setBubbles((prev) => [...prev, { id: `${sender}-${Date.now()}-${Math.random()}`, sender, body, ts: new Date().toISOString() }]);
  }, []);

  // Asistan konuşur (balon + ses). Promise ses bitince çözülür.
  const say = useCallback(
    (text: string) =>
      new Promise<void>((resolve) => {
        addBubble("assistant", text);
        if (callActiveRef.current) setCallPhase("speaking");
        voice.speak(text, () => resolve());
      }),
    [addBubble, voice],
  );

  const listen = useCallback(() => {
    if (!callActiveRef.current) return;
    setCallPhase("listening");
    rec.start((transcript) => {
      if (!callActiveRef.current) return;
      setCallPhase("thinking");
      void handleAnswer(transcript);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rec]);

  function slotShort(offer: PublicSlotOfferView): string {
    const d = new Date(offer.starts_at);
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return `${WEEKDAYS[d.getDay()]} ${hh}:${mm}`;
  }
  function slotLong(offer: PublicSlotOfferView): string {
    const d = new Date(offer.starts_at);
    return new Intl.DateTimeFormat("tr-TR", {
      weekday: "long", day: "2-digit", month: "long", hour: "2-digit", minute: "2-digit",
    }).format(d);
  }
  function slotsSpoken(list: PublicSlotOfferView[]): string {
    return list.slice(0, 4).map(slotShort).join(", ");
  }

  function matchSlot(text: string, list: PublicSlotOfferView[]): PublicSlotOfferView | null {
    if (!list.length) return null;
    const t = text.toLocaleLowerCase("tr");
    for (const [re, idx] of ORDINALS) {
      if (re.test(t) && list[idx]) return list[idx];
    }
    // Gün adı eşleştir
    const dayIdx = WEEKDAYS.findIndex((w) => t.includes(w.toLocaleLowerCase("tr")));
    // Saat (0-23) yakala
    const hourMatch = t.match(/(\d{1,2})(?:[:.]\d{2})?/);
    const hour = hourMatch ? parseInt(hourMatch[1], 10) : null;
    let candidates = list;
    if (dayIdx >= 0) candidates = candidates.filter((o) => new Date(o.starts_at).getDay() === dayIdx);
    if (hour != null) {
      const byHour = candidates.find((o) => new Date(o.starts_at).getHours() === hour);
      if (byHour) return byHour;
    }
    if (dayIdx >= 0 && candidates.length) return candidates[0];
    return null;
  }

  function finish() {
    setStep("done");
    stepRef.current = "done";
    if (callActiveRef.current) endCall();
  }

  function handleEmergency() {
    setEmergency(true);
    setStep("done");
    stepRef.current = "done";
    void say("Anlattıklarınız acil olabilir. Lütfen vakit kaybetmeden 112'yi arayın. Klinik ekibimize de yüksek öncelikli bildirim iletildi.").then(() => {
      if (callActiveRef.current) endCall();
    });
  }

  // ── Adım soruları ─────────────────────────────────────────────────────────
  async function askName() {
    setStep("name"); stepRef.current = "name";
    await say("Anladım, geçmiş olsun. Randevu kaydını oluşturabilmem için adınızı ve soyadınızı alabilir miyim?");
    if (callActiveRef.current) listen();
  }
  async function askPhone() {
    setStep("phone"); stepRef.current = "phone";
    await say("Anladım. Randevu onayını SMS ile gönderebilmemiz için cep telefonu numaranızı alabilir miyim?");
    if (callActiveRef.current) listen();
  }
  async function askSlot() {
    setStep("slot"); stepRef.current = "slot";
    const list = slotsRef.current;
    if (!list.length) {
      await say("Şu anda uygun bir saat görünmüyor. Klinik ekibimiz en kısa sürede sizinle iletişime geçecek. İyi günler.");
      finish();
      return;
    }
    await say(`${dataRef.current.department} için müsait saatlerimiz: ${slotsSpoken(list)}. Hangi saatte randevu oluşturmamı istersiniz?`);
    if (callActiveRef.current) listen();
  }

  async function book(offer: PublicSlotOfferView) {
    setBusy(true);
    setError(null);
    try {
      await say("Randevunuzu oluşturuyorum, bir saniye.");
      const held =
        offer.status === "held"
          ? { slot_offer: offer }
          : await holdSlotOffer(clinic.slug, conversationId, sessionToken, offer.id);
      await confirmAppointment(clinic.slug, conversationId, sessionToken, {
        department: held.slot_offer.department,
        slot_offer_id: held.slot_offer.id,
        notes: "Hasta asistan üzerinden onayladı.",
      });
      addBubble("system", `✓ Randevu oluşturuldu · ${slotLong(offer)} · ${dataRef.current.name} · ${dataRef.current.phone}`);
      setStep("done"); stepRef.current = "done";
      await say(`Harika ${dataRef.current.name}. ${slotLong(offer)} için randevunuz oluşturuldu. Onay mesajı ${dataRef.current.phone} numarasına gönderilecek. Geçmiş olsun, iyi günler.`);
      if (callActiveRef.current) endCall();
      onAppointmentConfirmed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "randevu_oluşturulamadı");
      await say("Randevuyu oluştururken bir sorun oldu. Başka bir saat seçmek ister misiniz?");
      if (callActiveRef.current) listen();
    } finally {
      setBusy(false);
    }
  }

  // ── Hasta cevabı yönlendirici ───────────────────────────────────────────────
  async function handleAnswer(raw: string) {
    const text = raw.trim();
    if (!text || busy) return;
    addBubble("patient", text);

    const current = stepRef.current;
    // Slot adımında "vazgeçtim/yeterli" gibi ifadelerde nazikçe kapat (cevap
    // beklenen diğer adımlarda metni yutmamak için sadece burada kontrol).
    if (current === "slot" && isCloseIntent(text)) {
      await say("Rica ederim, geçmiş olsun. İyi günler dilerim.");
      finish();
      return;
    }

    setBusy(true);
    setError(null);
    try {
      if (current === "complaint") {
        dataRef.current.complaint = text;
        // Backend'e gönder → branş + gerçek müsait slotlar (+ acil tespiti)
        const res = await sendPatientMessage(
          clinic.slug, conversationId, sessionToken, `${text} için randevu almak istiyorum`,
        );
        if (res.assistant_message?.intent === "medical_emergency") {
          handleEmergency();
          return;
        }
        const data = (res.assistant_message?.metadata_json?.data as { intake?: { specialty?: string } } | undefined) ?? undefined;
        dataRef.current.department = data?.intake?.specialty ?? "Genel Diş Hekimliği";
        slotsRef.current = res.slot_offers ?? [];
        setSlots(res.slot_offers ?? []);
        await askName();
      } else if (current === "name") {
        dataRef.current.name = cleanName(text);
        await askPhone();
      } else if (current === "phone") {
        const phone = normalizePhone(text);
        if (!phone) {
          await say("Numarayı tam anlayamadım. Lütfen 5 ile başlayan 10 haneli cep numaranızı söyleyin. Örneğin 532 123 45 67.");
          if (callActiveRef.current) listen();
          return;
        }
        dataRef.current.phone = phone;
        await updatePatientIdentity(clinic.slug, conversationId, sessionToken, {
          full_name: dataRef.current.name, phone,
        });
        await askSlot();
      } else if (current === "slot") {
        const chosen = matchSlot(text, slotsRef.current);
        if (!chosen) {
          await say(`Bu saati bulamadım. Müsait saatler: ${slotsSpoken(slotsRef.current)}. Hangisini istersiniz? İsterseniz "ilk uygun saat" da diyebilirsiniz.`);
          if (callActiveRef.current) listen();
          return;
        }
        await book(chosen);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "bir_hata_oluştu");
      if (callActiveRef.current) {
        setCallPhase("listening");
        setTimeout(() => { if (callActiveRef.current) listen(); }, 600);
      }
    } finally {
      setBusy(false);
    }
  }

  function handleSubmit(e?: React.FormEvent) {
    e?.preventDefault();
    const body = input.trim();
    if (!body || busy) return;
    setInput("");
    void handleAnswer(body);
  }

  // ── Çağrı modu ──────────────────────────────────────────────────────────────
  function startCall() {
    if (!rec.supported) {
      setError("Tarayıcınız sesli görüşmeyi desteklemiyor — lütfen Chrome kullanın.");
      return;
    }
    if (emergency || step === "done") return;
    voice.enable();
    setCallActive(true);
    callActiveRef.current = true;
    setCallPhase("speaking");
    // İçinde bulunulan adıma uygun soruyu seslendirip dinlemeye geç.
    const prompt =
      stepRef.current === "complaint" ? greeting
        : stepRef.current === "name" ? "Adınızı ve soyadınızı alabilir miyim?"
        : stepRef.current === "phone" ? "Cep telefonu numaranızı alabilir miyim?"
        : stepRef.current === "slot" ? `Müsait saatler: ${slotsSpoken(slotsRef.current)}. Hangisini istersiniz?`
        : "Sizi dinliyorum.";
    void say(prompt).then(() => { if (callActiveRef.current) listen(); });
  }

  function endCall() {
    setCallActive(false);
    callActiveRef.current = false;
    setCallPhase("idle");
    rec.stop();
    voice.stop();
  }

  const locked = emergency || step === "done";

  return (
    <div className="patient-card patient-chat-card">
      {emergency ? (
        <div className="patient-emergency" role="alert">
          <div className="patient-emergency-dot" aria-hidden />
          <div>
            <strong>Acil durum tespit edildi.</strong>
            <p>
              Lütfen vakit kaybetmeden <a href="tel:112">112'yi arayın</a> veya en yakın acil servise
              başvurun. Klinik ekibimize yüksek öncelikli alarm iletildi.
            </p>
          </div>
        </div>
      ) : null}

      <header className="patient-chat-header">
        <div>
          <h2>{clinic.name}</h2>
          <span className="patient-chat-sub">AI asistanı · #{conversationId}</span>
        </div>
        <div className="patient-chat-actions">
          {rec.supported ? (
            <button
              type="button"
              className={`patient-call-btn ${callActive ? "is-active" : ""}`}
              onClick={callActive ? endCall : startCall}
              disabled={locked && !callActive}
              title={callActive ? "Görüşmeyi bitir" : "Sesli görüşme başlat (telefon gibi)"}
            >
              {callActive ? "■ Görüşmeyi bitir" : "📞 Sesli görüşme"}
            </button>
          ) : null}
          <button
            type="button"
            className={`patient-tts-toggle ${voice.enabled ? "is-on" : ""}`}
            onClick={voice.toggle}
            title={voice.enabled ? "Sesi kapat" : "Sesli yanıtı aç"}
            aria-pressed={voice.enabled}
          >
            {voice.enabled ? "🔊 Sesli" : "🔇 Sessiz"}
          </button>
          <button type="button" className="patient-cta-ghost" onClick={onStartOver}>
            Sohbeti kapat
          </button>
        </div>
      </header>

      {callActive ? (
        <div className={`patient-call-status phase-${callPhase}`} role="status" aria-live="polite">
          <span className="patient-call-pulse" aria-hidden />
          <span className="patient-call-status-text">
            {callPhase === "listening" ? "Dinliyorum… konuşabilirsiniz"
              : callPhase === "thinking" ? "Düşünüyorum…"
                : callPhase === "speaking" ? "Yanıtlıyor…" : "Bağlanıyor…"}
          </span>
          <span className="patient-call-hint">Sesli görüşme · mikrofon açık</span>
        </div>
      ) : null}

      <div className="patient-chat-scroller" ref={scrollerRef}>
        {bubbles.map((b) => (
          <div key={b.id} className={`patient-bubble patient-bubble-${b.sender}`}>
            <div className="patient-bubble-body">{b.body}</div>
          </div>
        ))}
        {busy ? (
          <div className="patient-bubble patient-bubble-assistant patient-bubble-typing">
            <span /><span /><span />
          </div>
        ) : null}
      </div>

      {/* Slot adımında tıklanabilir saat kartları (sesli seçime alternatif) */}
      {step === "slot" && slots.length > 0 && !locked ? (
        <div className="patient-slot-list" role="listbox" aria-label="Müsait randevu saatleri">
          {slots.slice(0, 6).map((offer) => (
            <button
              key={offer.id}
              type="button"
              className="patient-slot-card"
              onClick={() => { addBubble("patient", slotShort(offer)); void book(offer); }}
              disabled={busy}
            >
              <span className="patient-slot-time">{slotLong(offer)}</span>
              <span className="patient-slot-doctor">{offer.physician_name ?? "Klinik ekibi"}</span>
            </button>
          ))}
        </div>
      ) : null}

      {error ? <div className="patient-error-line">{error}</div> : null}

      <form className="patient-chat-input" onSubmit={handleSubmit}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={locked ? "Görüşme tamamlandı" : "Yazın ya da 📞 Sesli görüşme'ye basın…"}
          disabled={locked || busy}
        />
        <button type="submit" className="patient-cta" disabled={locked || busy || !input.trim()}>
          Gönder
        </button>
      </form>
    </div>
  );
}
