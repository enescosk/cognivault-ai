import { useEffect, useRef, useState } from "react";
import type { ChatSessionDetail, User } from "../types/api";
import { transcribeAudio, synthesizeSpeech } from "../api/client";

type ChatWindowProps = {
  session: ChatSessionDetail | null;
  user: User;
  sending: boolean;
  pendingMessage: string | null;
  streamingContent: string | null;  // null=yok, ""=başladı ama token gelmedi, "abc"=akan içerik
  token: string;
  onSend: (content: string) => void;
};

const trDateTime = new Intl.DateTimeFormat("tr-TR", { dateStyle: "short", timeStyle: "short" });

async function requestMicrophoneStream(): Promise<MediaStream> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new DOMException("Microphone access is not supported in this browser.", "NotSupportedError");
  }

  if (typeof MediaRecorder === "undefined") {
    throw new DOMException("Audio recording is not supported in this browser.", "NotSupportedError");
  }

  try {
    const permission = await navigator.permissions?.query({ name: "microphone" as PermissionName });
    if (permission?.state === "denied") {
      throw new DOMException("Microphone permission is blocked for this site.", "NotAllowedError");
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "NotAllowedError") {
      throw error;
    }
    // Safari and some embedded browsers do not support microphone permission queries.
    // In that case, getUserMedia below is still the correct way to trigger the prompt.
  }

  return navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true
    }
  });
}

function getMicrophoneErrorMessage(error: unknown): string {
  const name = error instanceof DOMException ? error.name : "";

  if (name === "NotAllowedError" || name === "SecurityError") {
    return "Mikrofon izni tarayıcıda engellenmiş. Adres çubuğundaki site izinlerinden mikrofonu açıp sayfayı yenileyin.";
  }

  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return "Mikrofon bulunamadı. Lütfen bağlı bir mikrofon olduğundan emin olun.";
  }

  if (name === "NotReadableError" || name === "TrackStartError") {
    return "Mikrofona erişilemedi. Başka bir uygulama kullanıyor olabilir.";
  }

  if (name === "NotSupportedError") {
    return "Bu tarayıcı sesli yazmayı desteklemiyor. Chrome veya Safari ile tekrar deneyin.";
  }

  return "Mikrofon izni alınamadı. Tarayıcı izinlerini kontrol edip tekrar deneyin.";
}

export function ChatWindow({ session, user, sending, pendingMessage, streamingContent, token, onSend }: ChatWindowProps) {
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  // ── STT: ses kaydı ───────────────────────────────────────────────────────
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef   = useRef<Blob[]>([]);

  // ── TTS: OpenAI ses sentezi ───────────────────────────────────────────────
  // Web Speech Synthesis yerine OpenAI TTS kullanıyoruz.
  // AudioContext ile mp3 çalınır — robotik değil, gerçek sinir ağı sesi.
  const [speakingId, setSpeakingId] = useState<number | null>(null);
  const [ttsLoading, setTtsLoading] = useState<number | null>(null);
  const audioSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const audioCtxRef    = useRef<AudioContext | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.messages, sending]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  function handleSubmit() {
    const trimmed = input.trim();
    if (!trimmed || sending) return;
    setInput("");
    onSend(trimmed);
  }

  // ── Mikrofon: kayıt başlat / durdur ──────────────────────────────────────
  async function toggleRecording() {
    setVoiceError(null);

    if (recording) {
      // Kaydı durdur → chunk'ları birleştir → Whisper'a gönder
      mediaRecorderRef.current?.stop();
      return;
    }

    // Mikrofon izni iste. İlk kullanımda tarayıcının izin penceresini tetikler.
    let stream: MediaStream;
    try {
      setVoiceError("Mikrofon izni isteniyor...");
      stream = await requestMicrophoneStream();
      setVoiceError(null);
    } catch (error) {
      setVoiceError(getMicrophoneErrorMessage(error));
      return;
    }

    // MediaRecorder'ı başlat — tarayıcının desteklediği en iyi formatı seç
    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "audio/webm";

    const recorder = new MediaRecorder(stream, { mimeType });
    audioChunksRef.current = [];

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunksRef.current.push(e.data);
    };

    recorder.onstop = async () => {
      // Tüm stream track'lerini kapat
      stream.getTracks().forEach(t => t.stop());
      setRecording(false);

      const blob = new Blob(audioChunksRef.current, { type: mimeType });
      if (blob.size < 1000) {
        setVoiceError("Ses çok kısa, tekrar deneyin.");
        return;
      }

      // Whisper API'ye gönder
      setTranscribing(true);
      try {
        const text = await transcribeAudio(blob, token, "tr");
        if (text) {
          setInput(prev => (prev ? prev + " " + text : text));
        } else {
          setVoiceError("Ses anlaşılamadı, tekrar deneyin.");
        }
      } catch {
        setVoiceError("Ses metne çevrilemedi.");
      } finally {
        setTranscribing(false);
      }
    };

    recorder.start(250); // her 250ms'de bir chunk
    mediaRecorderRef.current = recorder;
    setRecording(true);
  }

  // ── TTS: OpenAI ses sentezi ile oku / durdur ─────────────────────────────
  async function handleSpeak(msgId: number, text: string) {
    // Aynı mesaj çalıyorsa durdur
    if (speakingId === msgId) {
      audioSourceRef.current?.stop();
      audioSourceRef.current = null;
      setSpeakingId(null);
      return;
    }
    // Başka bir şey çalıyorsa önce onu durdur
    audioSourceRef.current?.stop();
    audioSourceRef.current = null;
    setSpeakingId(null);

    setTtsLoading(msgId);
    try {
      // Backend'den mp3 ArrayBuffer al
      const arrayBuffer = await synthesizeSpeech(text, token, "nova", 1.0);

      // AudioContext oluştur (veya devam et)
      if (!audioCtxRef.current || audioCtxRef.current.state === "closed") {
        audioCtxRef.current = new AudioContext();
      }
      const ctx = audioCtxRef.current;

      // mp3 → AudioBuffer → çal
      const audioBuffer = await ctx.decodeAudioData(arrayBuffer);
      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(ctx.destination);
      source.onended = () => {
        setSpeakingId(null);
        audioSourceRef.current = null;
      };
      source.start();
      audioSourceRef.current = source;
      setSpeakingId(msgId);
    } catch {
      setVoiceError("Ses oynatılamadı.");
    } finally {
      setTtsLoading(null);
    }
  }

  const roleName = user.role.name;
  const locale = user.locale.toUpperCase();
  const en = user.locale === "en";
  const messages = session?.messages ?? [];

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <div className="chat-header-left">
          <div className="chat-title">{session?.title ?? "Agent Workspace"}</div>
          <div className="chat-subtitle">{en ? "Guided enterprise workflow · RBAC enforced" : "Yönlendirmeli kurumsal akış · RBAC aktif"}</div>
        </div>
        <div className="chat-badges">
          <span className="chat-badge">
            <svg width="8" height="8" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="12"/></svg>
            {roleName} · {locale}
          </span>
          <span className="chat-badge">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
              <path d="M7 11V7a5 5 0 0110 0v4"/>
            </svg>
            {en ? "Audited" : "Denetleniyor"}
          </span>
        </div>
      </div>

      <div className="message-stream">
        <div className="message-stream-spacer" />

        {messages.length === 0 && !sending ? (
          <div className="empty-state">
            <div className="empty-icon">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
              </svg>
            </div>
            <h4>{en ? "Start the conversation" : "Konuşmayı başlat"}</h4>
            <p>{en ? "Type or use the microphone button for voice input. Turkish and English are supported." : "Yazarak veya mikrofon butonu ile sesli yazın. Türkçe ve İngilizce desteklenir."}</p>
          </div>
        ) : (
          messages.map((msg) => {
            const isUser = msg.sender === "user";
            if (msg.sender === "system" || msg.sender === "tool") return null;
            return (
              <div key={msg.id} className={`message-row ${isUser ? "outbound" : ""}`}>
                {/* AI avatarı — sadece AI mesajlarında sol tarafta */}
                {!isUser && (
                  <div className="msg-avatar">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 2a4 4 0 014 4v2a4 4 0 01-8 0V6a4 4 0 014-4z"/><path d="M3 20c0-4 4-7 9-7s9 3 9 7"/>
                    </svg>
                  </div>
                )}
                <div className="message-bubble">
                  <div className="message-meta">
                    <span className="message-sender">{isUser ? user.full_name : "Cognivault AI"}</span>
                    <span className="message-time">{trDateTime.format(new Date(msg.created_at))}</span>
                    {/* Sesli okuma butonu — sadece AI mesajlarında */}
                    {!isUser && (
                      <button
                        className={`tts-btn ${speakingId === msg.id ? "tts-btn--active" : ""}`}
                        onClick={() => void handleSpeak(msg.id, msg.content)}
                        disabled={ttsLoading !== null}
                        title={speakingId === msg.id ? (en ? "Stop" : "Durdur") : (en ? "Read aloud (OpenAI)" : "Sesli oku (OpenAI)")}
                        type="button"
                      >
                        {ttsLoading === msg.id ? (
                          // Yükleniyor
                          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="spin">
                            <path d="M21 12a9 9 0 11-6.219-8.56"/>
                          </svg>
                        ) : speakingId === msg.id ? (
                          // Çalıyor → durdur
                          <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">
                            <rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>
                          </svg>
                        ) : (
                          // Hoparlör
                          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
                            <path d="M15.54 8.46a5 5 0 010 7.07"/>
                            <path d="M19.07 4.93a10 10 0 010 14.14"/>
                          </svg>
                        )}
                      </button>
                    )}
                  </div>
                  <div className="message-content">{msg.content}</div>
                  {msg.appointment && (
                    <div className="confirmation-card">
                      <div className="confirmation-header">
                        <span className="confirmation-label">{en ? "Appointment Confirmed" : "Randevu Onaylandı"}</span>
                        <span className="status-badge success">{en ? "Confirmed" : "Onaylı"}</span>
                      </div>
                      <div className="confirmation-grid">
                        <div>
                          <span className="cf-label">{en ? "Department" : "Departman"}</span>
                          <span className="cf-value">{msg.appointment.department}</span>
                        </div>
                        <div>
                          <span className="cf-label">{en ? "Code" : "Kod"}</span>
                          <span className="cf-value" style={{ fontFamily: "var(--font-mono)", color: "var(--green)" }}>
                            {msg.appointment.confirmation_code}
                          </span>
                        </div>
                        <div>
                          <span className="cf-label">{en ? "Date" : "Tarih"}</span>
                          <span className="cf-value">{trDateTime.format(new Date(msg.appointment.scheduled_at))}</span>
                        </div>
                        <div>
                          <span className="cf-label">{en ? "Purpose" : "Amaç"}</span>
                          <span className="cf-value">{msg.appointment.purpose ?? "—"}</span>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}

        {/* Optimistic: kullanıcı mesajı API yanıtından önce */}
        {sending && pendingMessage && (
          <div className="message-row outbound">
            <div className="message-bubble">
              <div className="message-meta">
                <span className="message-sender">{user.full_name}</span>
                <span className="message-time">{en ? "now" : "şimdi"}</span>
              </div>
              <div className="message-content">{pendingMessage}</div>
            </div>
          </div>
        )}

        {/* AI yanıtı — token akışı veya typing indicator */}
        {sending && (
          <div className="message-row">
            <div className="msg-avatar">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 2a4 4 0 014 4v2a4 4 0 01-8 0V6a4 4 0 014-4z"/><path d="M3 20c0-4 4-7 9-7s9 3 9 7"/>
              </svg>
            </div>
            <div className="message-bubble">
              <div className="message-meta">
                <span className="message-sender">Cognivault AI</span>
              </div>
              {streamingContent !== null && streamingContent !== "" ? (
                /* Token'lar akıyor — metin büyüyor + yanıp sönen imleç */
                <div className="message-content streaming-content">
                  {streamingContent}<span className="stream-cursor" />
                </div>
              ) : (
                /* Henüz token gelmedi — tool loop çalışıyor */
                <div className="typing-indicator">
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                </div>
              )}
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="composer-area">
        <div className="composer-box">
          {/* ── Mikrofon butonu ──────────────────────────── */}
          <button
            className={`mic-btn ${recording ? "mic-btn--recording" : ""} ${transcribing ? "mic-btn--transcribing" : ""}`}
            onClick={toggleRecording}
            disabled={sending || transcribing}
            title={recording ? (en ? "Stop recording" : "Kaydı durdur") : (en ? "Voice input" : "Sesli yaz")}
            type="button"
            aria-label={recording ? (en ? "Stop recording" : "Kaydı durdur") : (en ? "Voice input" : "Sesli yaz")}
          >
            {transcribing ? (
              // Whisper işliyor — dönen nokta
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="spin">
                <path d="M21 12a9 9 0 11-6.219-8.56"/>
              </svg>
            ) : recording ? (
              // Kayıt var — stop ikonu
              <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
                <rect x="4" y="4" width="16" height="16" rx="2"/>
              </svg>
            ) : (
              // Normal — mikrofon ikonu
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/>
                <path d="M19 10v2a7 7 0 01-14 0v-2"/>
                <line x1="12" y1="19" x2="12" y2="23"/>
                <line x1="8" y1="23" x2="16" y2="23"/>
              </svg>
            )}
          </button>

          <textarea
            className="composer-textarea"
            placeholder={recording ? (en ? "Recording..." : "Dinliyorum...") : (en ? "Type or use voice input..." : "Yazın veya sesli konuşun...")}
            value={input}
            rows={1}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={sending || recording}
          />
          <button className="send-btn" onClick={handleSubmit} disabled={sending || recording || !input.trim()} type="button" aria-label={en ? "Send" : "Gönder"}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"/>
              <polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </div>

        {/* Hata mesajı */}
        {voiceError && (
          <div className="voice-error" onClick={() => setVoiceError(null)}>{voiceError} ✕</div>
        )}

        <div className="composer-hint">
          {recording
            ? (en ? "Recording in progress - press again to stop" : "Kayıt devam ediyor - durdurmak için tekrar bas")
            : (en ? "Enter to send · Shift+Enter for newline · voice input · listen to AI messages" : "Enter gönder · Shift+Enter yeni satır · sesli yaz · AI mesajını dinle")}
        </div>
      </div>
    </div>
  );
}
