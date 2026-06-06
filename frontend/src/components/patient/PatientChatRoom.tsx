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

type Lang = "tr" | "en";

/**
 * Doğal sesli yanıt — OpenAI TTS (nova) backend üzerinden. nova çok dilli olduğu
 * için TR/EN metni otomatik doğru telaffuz eder. Başarısız olursa tarayıcı Web
 * Speech'e düşer.
 */
function useVoice(slug: string, langRef: React.MutableRefObject<Lang>) {
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
    const bcp = langRef.current === "en" ? "en-US" : "tr-TR";
    u.lang = bcp;
    u.rate = 1.04;
    const v = window.speechSynthesis.getVoices().find((x) => x.lang?.startsWith(langRef.current));
    if (v) u.voice = v;
    u.onend = () => onEnd?.();
    u.onerror = () => onEnd?.();
    window.speechSynthesis.speak(u);
  }, [langRef]);

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

  const toggle = useCallback(() => { setEnabled((cur) => { if (cur) stop(); return !cur; }); }, [stop]);
  const enable = useCallback(() => setEnabled(true), []);
  useEffect(() => () => stop(), [stop]);
  return { enabled, toggle, enable, speak, stop };
}

/** Tarayıcı Web Speech Recognition (STT). Dil her turda dinamik verilir. */
const SpeechRecognitionImpl: any =
  typeof window !== "undefined"
    ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    : null;

function useSpeechRecognition() {
  const supported = Boolean(SpeechRecognitionImpl);
  const recRef = useRef<any>(null);

  const stop = useCallback(() => { try { recRef.current?.abort?.(); } catch { /* ignore */ } }, []);

  const start = useCallback(
    (onResult: (t: string) => void, onNoResult: () => void, bcp = "tr-TR") => {
      if (!SpeechRecognitionImpl) return;
      try { recRef.current?.abort?.(); } catch { /* ignore */ }
      const rec = new SpeechRecognitionImpl();
      rec.lang = bcp;
      rec.interimResults = false;
      rec.maxAlternatives = 1;
      rec.continuous = false;
      let got = false;
      rec.onresult = (e: any) => {
        const t = e?.results?.[0]?.[0]?.transcript ?? "";
        if (t && t.trim()) { got = true; onResult(t.trim()); }
      };
      // Sonuç gelmeden biterse (sessizlik/hata) → çağıran tarafı bilgilendir.
      rec.onend = () => { if (!got) onNoResult(); };
      rec.onerror = () => { /* onend zaten tetiklenecek */ };
      recRef.current = rec;
      try { rec.start(); } catch { /* ignore */ }
    },
    [],
  );

  useEffect(() => () => { try { recRef.current?.abort?.(); } catch { /* ignore */ } }, []);
  return { supported, start, stop };
}

// ── Yerelleştirme (TR/EN) ─────────────────────────────────────────────────────
const L = {
  tr: {
    complaintPrompt: "Size nasıl yardımcı olabilirim? Şikayetinizi kısaca anlatır mısınız? Örneğin diş ağrısı, dolgu ya da implant gibi.",
    namePrompt: "Randevu kaydını oluşturabilmem için adınızı ve soyadınızı alabilir miyim?",
    phonePrompt: "Onay SMS'ini gönderebilmem için cep telefonu numaranızı paylaşır mısınız?",
    phoneRetry: "Numarayı tam anlayamadım. Lütfen 5 ile başlayan 10 haneli cep numaranızı söyleyin. Örneğin 532 123 45 67.",
    slotPrompt: (dept: string, slots: string) => `${dept} için müsait saatlerimiz: ${slots}. Hangisinde randevu oluşturmamı istersiniz?`,
    slotNotFound: (slots: string) => `Bu saati bulamadım. Müsait saatler: ${slots}. Hangisini istersiniz? İsterseniz "ilk uygun saat" da diyebilirsiniz.`,
    noSlots: "Şu an sistemde net bir saat göremedim; klinik ekibimiz en kısa sürede sizinle iletişime geçecek. Dilerseniz başka bir gün ya da konu söyleyebilirsiniz.",
    booking: "Randevunuzu oluşturuyorum, bir saniye.",
    confirm: (name: string, slot: string, phone: string) => `Harika ${name}. ${slot} için randevunuz oluşturuldu. Onay mesajı ${phone} numarasına gönderilecek. Geçmiş olsun, iyi günler.`,
    confirmSys: (slot: string, name: string, phone: string) => `✓ Randevu oluşturuldu · ${slot} · ${name} · ${phone}`,
    bookErr: "Randevuyu oluştururken bir sorun oldu. Başka bir saat seçmek ister misiniz?",
    emergency: "Anlattıklarınız acil olabilir. Lütfen vakit kaybetmeden 112'yi arayın. Klinik ekibimize de yüksek öncelikli bildirim iletildi.",
    didntCatch: "Sizi tam duyamadım, bir daha söyleyebilir misiniz?",
    closeThanks: "Rica ederim, geçmiş olsun. İyi günler dilerim.",
    acks: ["Tabii", "Elbette", "Tamamdır", "Peki", "Memnuniyetle", "Anladım"],
    callStatus: { listening: "Dinliyorum… konuşabilirsiniz", thinking: "Düşünüyorum…", speaking: "Yanıtlıyor…", idle: "Bağlanıyor…" },
    callHint: "Sesli görüşme · mikrofon açık",
    inputPlaceholder: "Yazın ya da 📞 Sesli görüşme'ye basın…",
    lockedPlaceholder: "Görüşme tamamlandı",
    locale: "tr-TR",
    bcp: "tr-TR",
  },
  en: {
    complaintPrompt: "How can I help you today? Could you briefly describe your concern? For example a toothache, a filling, or an implant.",
    namePrompt: "To create your appointment, may I have your full name?",
    phonePrompt: "Could you share your mobile number so we can send the confirmation by SMS?",
    phoneRetry: "I couldn't quite get the number. Please tell me your 10-digit mobile number, for example 532 123 45 67.",
    slotPrompt: (dept: string, slots: string) => `Available times for ${dept}: ${slots}. Which one would you like me to book?`,
    slotNotFound: (slots: string) => `I couldn't match that time. Available times: ${slots}. Which would you like? You can also say "the first available time".`,
    noSlots: "I couldn't find an exact time right now; our clinic team will reach out to you shortly. You can also tell me another day or topic.",
    booking: "Creating your appointment, one moment.",
    confirm: (name: string, slot: string, phone: string) => `Wonderful ${name}. Your appointment for ${slot} is confirmed. A confirmation will be sent to ${phone}. Get well soon and have a great day.`,
    confirmSys: (slot: string, name: string, phone: string) => `✓ Appointment created · ${slot} · ${name} · ${phone}`,
    bookErr: "There was a problem creating the appointment. Would you like to pick another time?",
    emergency: "What you describe may be an emergency. Please call your local emergency number right away. I've also flagged our clinic team with high priority.",
    didntCatch: "Sorry, I didn't catch that — could you say it again?",
    closeThanks: "You're welcome, get well soon. Have a great day.",
    acks: ["Sure", "Of course", "Certainly", "Alright", "Gladly", "Got it"],
    callStatus: { listening: "Listening… please speak", thinking: "Thinking…", speaking: "Responding…", idle: "Connecting…" },
    callHint: "Voice call · microphone on",
    inputPlaceholder: "Type, or tap 📞 Voice call…",
    lockedPlaceholder: "Conversation completed",
    locale: "en-US",
    bcp: "en-US",
  },
} as const;

const WEEKDAYS_TR = ["pazar", "pazartesi", "salı", "çarşamba", "perşembe", "cuma", "cumartesi"];
const WEEKDAYS_EN = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];
const ORDINALS: Array<[RegExp, number]> = [
  [/(ilk|birinci|ilki|en erken|en yak|first|earliest|soonest)/i, 0],
  [/(ikinci|2\.|second)/i, 1],
  [/(üçüncü|ucuncu|3\.|third)/i, 2],
  [/(dördüncü|dorduncu|4\.|fourth)/i, 3],
];

function pick(arr: readonly string[]): string {
  return arr[Math.floor(Math.random() * arr.length)];
}

function normalizePhone(raw: string): string | null {
  let d = raw.replace(/\D/g, "");
  if (d.length > 10) d = d.slice(-10);
  if (d.length === 10 && d.startsWith("5")) return `+90${d}`;
  return null;
}

function cleanName(raw: string): string {
  let t = raw.trim().replace(/[.,!?]+$/g, "");
  t = t.replace(/^(benim\s+)?(ad[ıi]m|ismim|ben)\s+/i, "");
  t = t.replace(/^(my\s+name\s+is|i'?m|i am|it'?s)\s+/i, "");
  if (t.length < 2) t = raw.trim();
  return t.split(/\s+/).map((w) => w.charAt(0).toLocaleUpperCase("tr") + w.slice(1)).join(" ");
}

function detectLangChoice(text: string): Lang {
  const t = text.toLocaleLowerCase("tr");
  // İngilizce işaretleri (STT varyasyonları dahil: "english", "engl", "ingilizce")
  if (/(eng|ingiliz|inglizce|inglisce|ingilis|\ben\b)/.test(t)) return "en";
  if (/(türk|turk|turkish|türkçe|turkce|\btr\b)/.test(t)) return "tr";
  // İşaret yoksa: Türkçe'ye özgü karakter varsa TR, yoksa İngilizce metin say.
  if (/[çğışöü]/.test(t)) return "tr";
  if (/[a-z]/.test(t)) return "en";
  return "tr";
}

function isCloseIntent(text: string): boolean {
  return /(teşekkür|tesekkur|sağ ?ol|sag ?ol|kapat|hoşça|hosca|görüşürüz|gorusuruz|yeterli|bu kadar|iyi günler|iyi gunler|gerek yok|istemiyorum|thanks|thank you|that'?s all|no thanks|bye|goodbye|nothing else)/i.test(text);
}

/** Şikayet tipine göre çeşitlenen empatik/uygun ön cevap. */
function complaintAck(text: string, lang: Lang): string {
  const t = text.toLocaleLowerCase("tr");
  const has = (...ws: string[]) => ws.some((w) => t.includes(w));
  const pain = has("ağrı", "agri", "zonk", "sızı", "sizi", "kanama", "şiş", "sis", "acı", "aci", "pain", "ache", "hurt", "sore", "swollen", "bleed");
  const cosmetic = has("implant", "beyazlat", "estetik", "gülüş", "gulus", "botoks", "lamina", "veneer", "whiten", "aesthet", "cosmetic", "smile");
  const checkup = has("temizlik", "kontrol", "muayene", "tartar", "clean", "check", "scaling", "exam");
  const pediatric = has("çocuk", "cocuk", "oğlum", "oglum", "kızım", "kizim", "child", "kid", "son", "daughter");
  if (lang === "en") {
    if (pain) return "I'm sorry to hear that — let's take care of it.";
    if (cosmetic) return "Great choice.";
    if (checkup) return "Sure.";
    if (pediatric) return "Of course.";
    return "Got it.";
  }
  if (pain) return "Geçmiş olsun, hemen ilgilenelim.";
  if (cosmetic) return "Harika bir tercih.";
  if (checkup) return "Tabii, hemen bakalım.";
  if (pediatric) return "Elbette, çocuğunuz için en uygun şekilde planlayalım.";
  return "Anladım.";
}

interface Props {
  clinic: PublicClinicView;
  sessionToken: string;
  conversationId: number;
  initialWelcome?: string | null;
  onAppointmentConfirmed: () => void;
  onStartOver: () => void;
}

type Bubble = { id: string | number; sender: "patient" | "assistant" | "system"; body: string; ts: string };
type Step = "language" | "complaint" | "name" | "phone" | "slot" | "done";

export function PatientChatRoom({
  clinic,
  sessionToken,
  conversationId,
  onAppointmentConfirmed,
  onStartOver,
}: Props) {
  const greeting =
    `Merhaba! Hello! 🙂 Görüşmeye Türkçe mi yoksa İngilizce mi devam etmek istersiniz? ` +
    `— Would you like to continue in Turkish or English?`;

  const [bubbles, setBubbles] = useState<Bubble[]>(() => [
    { id: "assistant-greeting", sender: "assistant", body: greeting, ts: new Date().toISOString() },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [emergency, setEmergency] = useState(false);
  const [step, setStep] = useState<Step>("language");
  const [slots, setSlots] = useState<PublicSlotOfferView[]>([]);
  const [, setLangState] = useState<Lang>("tr");

  const [callActive, setCallActive] = useState(false);
  const [callPhase, setCallPhase] = useState<"idle" | "listening" | "thinking" | "speaking">("idle");
  const callActiveRef = useRef(false);
  useEffect(() => { callActiveRef.current = callActive; }, [callActive]);

  const langRef = useRef<Lang>("tr");
  const dataRef = useRef({ name: "", complaint: "", phone: "", department: "" });
  const slotsRef = useRef<PublicSlotOfferView[]>([]);
  const stepRef = useRef<Step>("language");
  useEffect(() => { stepRef.current = step; }, [step]);

  const voice = useVoice(clinic.slug, langRef);
  const rec = useSpeechRecognition();
  const scrollerRef = useRef<HTMLDivElement>(null);
  const noResultRef = useRef(0);

  const t = () => L[langRef.current];

  useEffect(() => {
    if (scrollerRef.current) scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
  }, [bubbles, busy]);

  const addBubble = useCallback((sender: Bubble["sender"], body: string) => {
    setBubbles((prev) => [...prev, { id: `${sender}-${Date.now()}-${Math.random()}`, sender, body, ts: new Date().toISOString() }]);
  }, []);

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
    rec.start(
      (transcript) => {
        if (!callActiveRef.current) return;
        noResultRef.current = 0;
        setCallPhase("thinking");
        void handleAnswer(transcript);
      },
      () => {
        // Duyamadı: birkaç kez nazikçe tekrar iste; çok denerse sustur (call açık kalır).
        if (!callActiveRef.current) return;
        noResultRef.current += 1;
        if (noResultRef.current >= 3) { noResultRef.current = 0; setCallPhase("idle"); return; }
        void say(t().didntCatch).then(() => { if (callActiveRef.current) listen(); });
      },
      t().bcp,
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rec, say]);

  function slotShort(offer: PublicSlotOfferView): string {
    const d = new Date(offer.starts_at);
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    const wd = new Intl.DateTimeFormat(t().locale, { weekday: "long" }).format(d);
    return `${wd} ${hh}:${mm}`;
  }
  function slotLong(offer: PublicSlotOfferView): string {
    return new Intl.DateTimeFormat(t().locale, {
      weekday: "long", day: "2-digit", month: "long", hour: "2-digit", minute: "2-digit",
    }).format(new Date(offer.starts_at));
  }
  function slotsSpoken(list: PublicSlotOfferView[]): string {
    return list.slice(0, 4).map(slotShort).join(", ");
  }

  function matchSlot(text: string, list: PublicSlotOfferView[]): PublicSlotOfferView | null {
    if (!list.length) return null;
    const s = text.toLocaleLowerCase("tr");
    for (const [re, idx] of ORDINALS) if (re.test(s) && list[idx]) return list[idx];
    let dayIdx = WEEKDAYS_TR.findIndex((w) => s.includes(w));
    if (dayIdx < 0) dayIdx = WEEKDAYS_EN.findIndex((w) => s.includes(w));
    const hourMatch = s.match(/(\d{1,2})(?:[:.]\d{2})?/);
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
    setStep("done"); stepRef.current = "done";
    if (callActiveRef.current) endCall();
  }

  function handleEmergency() {
    setEmergency(true);
    setStep("done"); stepRef.current = "done";
    void say(t().emergency).then(() => { if (callActiveRef.current) endCall(); });
  }

  // ── Adım soruları ─────────────────────────────────────────────────────────
  async function askComplaint() {
    setStep("complaint"); stepRef.current = "complaint";
    await say(t().complaintPrompt);
    if (callActiveRef.current) listen();
  }
  async function askName() {
    setStep("name"); stepRef.current = "name";
    await say(`${complaintAck(dataRef.current.complaint, langRef.current)} ${t().namePrompt}`);
    if (callActiveRef.current) listen();
  }
  async function askPhone() {
    setStep("phone"); stepRef.current = "phone";
    const first = dataRef.current.name.split(" ")[0] || "";
    await say(`${pick(t().acks)}${first ? " " + first : ""}. ${t().phonePrompt}`);
    if (callActiveRef.current) listen();
  }
  async function askSlot() {
    setStep("slot"); stepRef.current = "slot";
    const list = slotsRef.current;
    if (!list.length) {
      await say(t().noSlots);
      if (callActiveRef.current) listen();
      return;
    }
    await say(`${pick(t().acks)}. ${t().slotPrompt(dataRef.current.department, slotsSpoken(list))}`);
    if (callActiveRef.current) listen();
  }

  async function book(offer: PublicSlotOfferView) {
    setBusy(true); setError(null);
    try {
      await say(t().booking);
      const held =
        offer.status === "held"
          ? { slot_offer: offer }
          : await holdSlotOffer(clinic.slug, conversationId, sessionToken, offer.id);
      await confirmAppointment(clinic.slug, conversationId, sessionToken, {
        department: held.slot_offer.department,
        slot_offer_id: held.slot_offer.id,
        notes: "Hasta asistan üzerinden onayladı.",
      });
      addBubble("system", t().confirmSys(slotLong(offer), dataRef.current.name, dataRef.current.phone));
      setStep("done"); stepRef.current = "done";
      await say(t().confirm(dataRef.current.name, slotLong(offer), dataRef.current.phone));
      if (callActiveRef.current) endCall();
      onAppointmentConfirmed();
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
      await say(t().bookErr);
      if (callActiveRef.current) listen();
    } finally {
      setBusy(false);
    }
  }

  // ── Yönlendirici ────────────────────────────────────────────────────────────
  async function handleAnswer(raw: string) {
    const text = raw.trim();
    if (!text || busy) return;
    addBubble("patient", text);
    const current = stepRef.current;

    if (current === "slot" && isCloseIntent(text)) {
      await say(t().closeThanks);
      finish();
      return;
    }

    setBusy(true); setError(null);
    try {
      if (current === "language") {
        const chosen = detectLangChoice(text);
        langRef.current = chosen;
        setLangState(chosen);
        await askComplaint();
      } else if (current === "complaint") {
        dataRef.current.complaint = text;
        const res = await sendPatientMessage(
          clinic.slug, conversationId, sessionToken, `${text} için randevu almak istiyorum`,
        );
        if (res.emergency || res.detected_intent === "medical_emergency") { handleEmergency(); return; }
        dataRef.current.department = res.specialty ?? (langRef.current === "en" ? "General Dentistry" : "Genel Diş Hekimliği");
        const offers = res.slot_offers ?? [];
        slotsRef.current = offers; setSlots(offers);
        await askName();
      } else if (current === "name") {
        dataRef.current.name = cleanName(text);
        await askPhone();
      } else if (current === "phone") {
        const phone = normalizePhone(text);
        if (!phone) {
          await say(t().phoneRetry);
          if (callActiveRef.current) listen();
          return;
        }
        dataRef.current.phone = phone;
        await updatePatientIdentity(clinic.slug, conversationId, sessionToken, { full_name: dataRef.current.name, phone });
        await askSlot();
      } else if (current === "slot") {
        const chosen = matchSlot(text, slotsRef.current);
        if (!chosen) {
          await say(t().slotNotFound(slotsSpoken(slotsRef.current)));
          if (callActiveRef.current) listen();
          return;
        }
        await book(chosen);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "error");
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

  // Dil seçim butonu — STT/yazıya güvenmeden garantili seçim.
  function chooseLanguage(l: Lang) {
    if (busy) return;
    langRef.current = l;
    setLangState(l);
    addBubble("patient", l === "en" ? "English" : "Türkçe");
    void askComplaint();
  }

  function startCall() {
    if (!rec.supported) {
      setError(langRef.current === "en" ? "Your browser doesn't support voice calls — please use Chrome." : "Tarayıcınız sesli görüşmeyi desteklemiyor — lütfen Chrome kullanın.");
      return;
    }
    if (emergency || step === "done") return;
    voice.enable();
    setCallActive(true);
    callActiveRef.current = true;
    setCallPhase("speaking");
    const lastAssistant = [...bubbles].reverse().find((b) => b.sender === "assistant");
    voice.speak(lastAssistant?.body ?? greeting, () => { if (callActiveRef.current) listen(); });
  }

  function endCall() {
    setCallActive(false);
    callActiveRef.current = false;
    setCallPhase("idle");
    rec.stop();
    voice.stop();
  }

  const locked = emergency || step === "done";
  const tr = t();

  return (
    <div className="patient-card patient-chat-card">
      {emergency ? (
        <div className="patient-emergency" role="alert">
          <div className="patient-emergency-dot" aria-hidden />
          <div>
            <strong>{langRef.current === "en" ? "Possible emergency detected." : "Acil durum tespit edildi."}</strong>
            <p>
              {langRef.current === "en" ? "Please call your local emergency number" : "Lütfen vakit kaybetmeden"}{" "}
              <a href="tel:112">{langRef.current === "en" ? "(112)" : "112'yi arayın"}</a>{" "}
              {langRef.current === "en" ? "right away. Our clinic team has been alerted." : "veya en yakın acil servise başvurun. Klinik ekibimize yüksek öncelikli alarm iletildi."}
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
              title={callActive ? "Görüşmeyi bitir" : "Sesli görüşme başlat"}
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
          <span className="patient-call-status-text">{tr.callStatus[callPhase]}</span>
          <span className="patient-call-hint">{tr.callHint}</span>
        </div>
      ) : null}

      <div className="patient-chat-scroller" ref={scrollerRef}>
        {bubbles.map((b) => (
          <div key={b.id} className={`patient-bubble patient-bubble-${b.sender}`}>
            <div className="patient-bubble-body">{b.body}</div>
          </div>
        ))}
        {busy ? (
          <div className="patient-bubble patient-bubble-assistant patient-bubble-typing"><span /><span /><span /></div>
        ) : null}
      </div>

      {step === "language" && !locked ? (
        <div className="patient-lang-pick">
          <button type="button" className="patient-lang-btn" onClick={() => chooseLanguage("tr")} disabled={busy}>
            🇹🇷 Türkçe devam et
          </button>
          <button type="button" className="patient-lang-btn" onClick={() => chooseLanguage("en")} disabled={busy}>
            🇬🇧 Continue in English
          </button>
        </div>
      ) : null}

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
              <span className="patient-slot-doctor">{offer.physician_name ?? (langRef.current === "en" ? "Clinic team" : "Klinik ekibi")}</span>
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
          placeholder={locked ? tr.lockedPlaceholder : tr.inputPlaceholder}
          disabled={locked || busy}
        />
        <button type="submit" className="patient-cta" disabled={locked || busy || !input.trim()}>
          Gönder
        </button>
      </form>
    </div>
  );
}
