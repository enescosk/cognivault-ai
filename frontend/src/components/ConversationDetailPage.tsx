import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { getClinicalConversation, listAgentDecisions } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { useT } from "../i18n";
import type { ClinicalConversationDetail, ClinicalMessage } from "../types/api";
import { ErrorBoundary } from "./ErrorBoundary";
import { SkeletonBlock } from "./ui/Skeleton";

/**
 * Operator / admin için tek bir klinik sohbetin uçtan uca incelendiği sayfa.
 * Route: /operator/conversations/:id
 *
 * Sol kolon : mesaj zaman çizelgesi (hasta / asistan / operatör / sistem)
 * Sağ kolon : hasta bilgi kartı, sohbet meta verisi, bu sohbete ait ajan kararları
 *
 * Backend endpoint: GET /api/clinical/conversations/{id}
 * Decision endpoint: GET /api/agents/decisions?conversation_id=...
 *
 * --- Gemini Deep Research entegrasyonu (2026-05-25) ---
 * Bölüm A6 → medical_emergency için kırmızı acil banner + 112 yönlendirmesi
 * Bölüm H  → intent başına confidence eşikleri:
 *              book_appointment        ≥ 0.78
 *              reschedule_appointment  ≥ 0.82
 *              cancel_appointment      ≥ 0.82
 *              ask_price/insurance     ≥ 0.75
 *              medical_emergency       ≥ 0.80
 * Bölüm C  → KVKK consent ispatı patient panel'de görünür (kvkk_consent metadata)
 * Bölüm F#9 → sentiment trajectory (ilk hasta mesajı vs son hasta mesajı)
 * Bölüm B#1 → metadata.hallucination_risk=true ise mesaj kırmızı kenarlık
 * Bölüm B#6 → waiting_human statüsünde "sessiz transfer" uyarı barı
 */

/** Bölüm H: intent başına minimum güven eşikleri */
const INTENT_CONFIDENCE_THRESHOLDS: Record<string, number> = {
  book_appointment: 0.78,
  reschedule_appointment: 0.82,
  cancel_appointment: 0.82,
  ask_price: 0.75,
  ask_insurance: 0.75,
  ask_location: 0.7,
  ask_working_hours: 0.7,
  medical_emergency: 0.8,
  general_question: 0.7,
};

function isConfidenceBelowThreshold(intent: string | null | undefined, score: number | null | undefined): boolean {
  if (!intent || score === null || score === undefined) return false;
  const threshold = INTENT_CONFIDENCE_THRESHOLDS[intent];
  if (threshold === undefined) return false;
  return score < threshold;
}

function isEmergency(intent: string | null | undefined): boolean {
  return intent === "medical_emergency";
}
export function ConversationDetailPage() {
  const params = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { token, user, logout } = useAuth();
  const { t } = useT();

  const conversationId = Number(params.id);
  const idIsValid = Number.isFinite(conversationId) && conversationId > 0;

  const conversationQuery = useQuery({
    queryKey: ["clinical-conversation", conversationId],
    queryFn: () => getClinicalConversation(conversationId, token!),
    enabled: Boolean(token) && idIsValid,
    refetchInterval: 15_000,
  });

  const decisionsQuery = useQuery({
    queryKey: ["clinical-conversation-decisions", conversationId],
    queryFn: () =>
      listAgentDecisions(token!, { conversation_id: conversationId, limit: 30 }),
    enabled: Boolean(token) && idIsValid,
    refetchInterval: 30_000,
  });

  const data = conversationQuery.data;
  const messages = data?.messages ?? [];

  return (
    <div className="conv-detail-shell">
      <header className="conv-detail-header">
        <div className="conv-detail-header-left">
          <button
            type="button"
            className="conv-detail-back"
            onClick={() => navigate(-1)}
            aria-label={t("conv.back")}
          >
            ← {t("conv.back")}
          </button>
          <div className="conv-detail-title-block">
            <div className="conv-detail-title">
              {data ? <PatientLabel data={data} /> : t("common.loading")}
            </div>
            <div className="conv-detail-subtitle">
              {idIsValid ? `#${conversationId}` : t("conv.invalid_id")}
              {data ? ` · ${formatTimestamp(data.updated_at)}` : null}
            </div>
          </div>
        </div>
        <div className="conv-detail-header-right">
          {user ? (
            <span className="conv-detail-meta">
              {user.full_name} · {user.role.name}
            </span>
          ) : null}
          <button
            type="button"
            className="conv-detail-secondary"
            onClick={() => navigate("/operator/appointments")}
          >
            📅 Randevular
          </button>
          <button type="button" className="conv-detail-secondary" onClick={logout}>
            {t("auth.logout")}
          </button>
        </div>
      </header>

      {!idIsValid ? (
        <div className="error-box" style={{ margin: 24 }}>
          {t("conv.invalid_id")}
        </div>
      ) : null}

      {conversationQuery.error ? (
        <div className="error-box" style={{ margin: 24 }}>
          {conversationQuery.error instanceof Error
            ? conversationQuery.error.message
            : t("common.error_generic")}
        </div>
      ) : null}

      {idIsValid ? (
        <section className="conv-detail-body">
          <main className="conv-detail-main">
            {/* Bölüm A6: acil semptom tespit edilmişse en üstte kırmızı banner */}
            {data && isEmergency(data.intent) ? (
              <ErrorBoundary scope="Emergency banner">
                <EmergencyBanner data={data} />
              </ErrorBoundary>
            ) : null}

            {/* Bölüm B#6: waiting_human ise sessiz transfer uyarısı */}
            {data && data.status === "waiting_human" ? (
              <ErrorBoundary scope="Handoff banner">
                <HandoffBanner data={data} />
              </ErrorBoundary>
            ) : null}

            <ErrorBoundary scope="Conversation badges">
              {data ? <BadgeStrip data={data} /> : null}
            </ErrorBoundary>

            {/* Bölüm F#9: sentiment trajectory ufak şerit */}
            {data ? (
              <ErrorBoundary scope="Sentiment strip">
                <SentimentStrip messages={data.messages} />
              </ErrorBoundary>
            ) : null}

            <ErrorBoundary scope="Conversation messages">
              <div className="conv-detail-thread">
                {conversationQuery.isLoading ? <SkeletonBlock count={5} /> : null}
                {!conversationQuery.isLoading && messages.length === 0 ? (
                  <div className="decision-meta">{t("common.empty")}</div>
                ) : null}
                {messages.map((m) => (
                  <MessageBubble key={m.id} message={m} />
                ))}
              </div>
            </ErrorBoundary>
          </main>

          <aside className="conv-detail-side">
            <ErrorBoundary scope="Patient panel">
              {data ? <PatientPanel data={data} /> : <SkeletonBlock count={3} />}
            </ErrorBoundary>

            <ErrorBoundary scope="Voice event counters">
              {data ? <VoiceEventPanel data={data} /> : null}
            </ErrorBoundary>

            <ErrorBoundary scope="Conversation decisions">
              <div className="conv-detail-card">
                <div className="conv-detail-card-title">
                  {t("conv.related_decisions")}
                </div>
                {decisionsQuery.isLoading ? <SkeletonBlock count={2} /> : null}
                {decisionsQuery.data && decisionsQuery.data.length === 0 ? (
                  <div className="decision-meta">{t("common.empty")}</div>
                ) : null}
                {decisionsQuery.data?.map((row) => {
                  const pillCls = `decision-pill decision-pill-${row.risk}`;
                  return (
                    <div key={row.id} className="decision-row">
                      <div className="decision-row-head">
                        <div>
                          <strong style={{ fontSize: "0.86rem" }}>{row.intent}</strong>
                          <span className="decision-meta"> · {row.agent_type}</span>
                        </div>
                        <span className={pillCls}>
                          {row.risk === "low" || row.risk === "medium" || row.risk === "high"
                            ? t(`decisions.risk.${row.risk}` as const)
                            : row.risk}
                        </span>
                      </div>
                      <div className="decision-meta">
                        {row.action ?? "—"} ·{" "}
                        {Math.round((row.confidence ?? 0) * 100)}% ·{" "}
                        {formatTimestamp(row.created_at)}
                      </div>
                      {row.reason ? (
                        <div className="decision-meta">{row.reason}</div>
                      ) : null}
                    </div>
                  );
                })}
              </div>
              <Link to="/operator" className="conv-detail-secondary conv-detail-jump">
                {t("conv.back_to_panel")}
              </Link>
            </ErrorBoundary>
          </aside>
        </section>
      ) : null}
    </div>
  );
}

function VoiceEventPanel({ data }: { data: ClinicalConversationDetail }) {
  const counters = readVoiceEventCounters(data.metadata_json ?? undefined);
  const lastEvent = readLastVoiceEvent(data.metadata_json ?? undefined);
  if (!counters && !lastEvent) return null;

  return (
    <div className="conv-detail-card">
      <div className="conv-detail-card-title">Voice events</div>
      <div className="conv-voice-event-grid">
        <VoiceEventCell label="No-result" value={counters?.noResult ?? 0} />
        <VoiceEventCell label="Retry prompt" value={counters?.retryPrompt ?? 0} />
        <VoiceEventCell label="STT failure" value={counters?.sttFailure ?? 0} tone={counters?.sttFailure ? "risk" : undefined} />
        <VoiceEventCell label="Max retry" value={counters?.maxRetry ?? 0} />
      </div>
      {lastEvent ? (
        <div className="conv-voice-last-event">
          Son event: <strong>{lastEvent.eventType}</strong>
          {lastEvent.reason ? ` · ${lastEvent.reason}` : ""}
          {lastEvent.createdAt ? ` · ${formatTimestamp(lastEvent.createdAt)}` : ""}
        </div>
      ) : null}
    </div>
  );
}

function VoiceEventCell({ label, value, tone }: { label: string; value: number; tone?: "risk" }) {
  return (
    <div className={`conv-voice-event-cell ${tone === "risk" ? "is-risk" : ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function PatientLabel({ data }: { data: ClinicalConversationDetail }) {
  return (
    <>
      {data.patient.full_name ?? data.patient.phone}{" "}
      <span className="conv-detail-subtitle" style={{ marginLeft: 8 }}>
        · {data.patient.phone}
      </span>
    </>
  );
}

function BadgeStrip({ data }: { data: ClinicalConversationDetail }) {
  const { t } = useT();
  const conf = Math.round((data.confidence_score ?? 0) * 100);
  return (
    <div className="conv-detail-badges">
      <span className={`conv-badge conv-badge-status-${data.status}`}>
        {t(`conv.status.${data.status}` as const, data.status.replace(/_/g, " "))}
      </span>
      <span className={`conv-badge conv-badge-channel-${data.channel}`}>
        {t(`conv.channel.${data.channel}` as const, data.channel)}
      </span>
      {data.intent ? (
        <span className="conv-badge conv-badge-intent">
          {t(`conv.intent.${data.intent}` as const, data.intent)}
        </span>
      ) : null}
      {data.confidence_score !== null && data.confidence_score !== undefined ? (
        <span className="conv-badge conv-badge-conf">{conf}% conf</span>
      ) : null}
      {data.doctor_inbox ? (
        <span className="conv-badge conv-badge-flag">{t("conv.doctor_inbox_flag")}</span>
      ) : null}
      {data.persona_name ? (
        <span className="conv-badge conv-badge-persona">{data.persona_name}</span>
      ) : null}
    </div>
  );
}

function PatientPanel({ data }: { data: ClinicalConversationDetail }) {
  const { t } = useT();

  /**
   * Bölüm C → KVKK ispatlanabilirlik. Konuşma metadata'sında veya
   * mesaj metadata'sında consent izi var mı, bunu tek bakışta göster.
   * Kabul edilen anahtarlar: kvkk_consent, consent_status, consent
   */
  const consent = useMemo(() => extractConsentSignal(data), [data]);

  const rows: Array<[string, string]> = [
    [t("conv.patient.phone"), data.patient.phone],
    [t("conv.patient.language"), data.patient.language?.toUpperCase() ?? "—"],
    [t("conv.patient.source"), data.patient.source ?? "—"],
    [t("conv.patient.first_seen"), formatTimestamp(data.patient.created_at)],
    [t("conv.patient.last_seen"), formatTimestamp(data.patient.updated_at)],
  ];

  return (
    <div className="conv-detail-card">
      <div className="conv-detail-card-title">{t("conv.patient.title")}</div>
      {data.patient.full_name ? (
        <div className="conv-detail-card-headline">{data.patient.full_name}</div>
      ) : (
        <div className="conv-detail-card-headline conv-detail-anon">
          {t("conv.patient.anon")}
        </div>
      )}

      {/* Bölüm C: KVKK consent banner */}
      <div className={`conv-consent conv-consent-${consent.status}`}>
        <span className="conv-consent-dot" aria-hidden />
        <div className="conv-consent-text">
          <strong>{t(`conv.consent.${consent.status}` as const, consent.status)}</strong>
          {consent.detail ? (
            <span className="conv-consent-meta"> · {consent.detail}</span>
          ) : null}
        </div>
      </div>

      <dl className="conv-detail-kv">
        {rows.map(([k, v]) => (
          <div key={k} className="conv-detail-kv-row">
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

type ConsentStatus = "accepted" | "rejected" | "pending" | "unknown";

function extractConsentSignal(data: ClinicalConversationDetail): {
  status: ConsentStatus;
  detail: string | null;
} {
  // Konuşma seviyesinde
  const convMeta = (data as unknown as { metadata_json?: Record<string, unknown> }).metadata_json;
  const fromConv = readConsent(convMeta);
  if (fromConv.status !== "unknown") return fromConv;

  // Mesajlardan en eski/en güçlü iz
  for (const m of data.messages) {
    const fromMsg = readConsent(m.metadata_json ?? undefined);
    if (fromMsg.status !== "unknown") return fromMsg;
  }
  return { status: "unknown", detail: null };
}

function readConsent(meta: Record<string, unknown> | undefined): {
  status: ConsentStatus;
  detail: string | null;
} {
  if (!meta) return { status: "unknown", detail: null };
  const raw =
    (meta.kvkk_consent as unknown) ??
    (meta.consent_status as unknown) ??
    (meta.consent as unknown);

  if (raw === undefined || raw === null) return { status: "unknown", detail: null };

  if (typeof raw === "boolean") {
    return { status: raw ? "accepted" : "rejected", detail: null };
  }
  if (typeof raw === "string") {
    const v = raw.toLowerCase();
    if (["accepted", "granted", "true", "yes", "onaylandi", "onaylandı"].includes(v)) {
      return { status: "accepted", detail: null };
    }
    if (["rejected", "denied", "no", "false", "reddedildi"].includes(v)) {
      return { status: "rejected", detail: null };
    }
    if (["pending", "awaiting"].includes(v)) return { status: "pending", detail: null };
  }
  if (typeof raw === "object") {
    const obj = raw as Record<string, unknown>;
    const status = (obj.status as string | undefined) ?? "unknown";
    const detail =
      (obj.granted_via as string | undefined) ?? (obj.version as string | undefined) ?? null;
    if (status === "accepted" || status === "rejected" || status === "pending") {
      return { status, detail };
    }
  }
  return { status: "unknown", detail: null };
}

/**
 * Bölüm A6 — medical_emergency intent algılandığında en üstte gözüken
 * yüksek görünürlüklü banner. Doktor/operatör 112 yönlendirmesinin
 * yapılıp yapılmadığını metadata'dan okur ve net feedback verir.
 */
function EmergencyBanner({ data }: { data: ClinicalConversationDetail }) {
  const { t } = useT();
  const routedTo112 = useMemo(() => {
    for (const m of data.messages) {
      const meta = m.metadata_json ?? {};
      if (meta.emergency_routed === true) return true;
      const content = m.content ?? "";
      if (/112|acil servis/i.test(content) && m.sender !== "patient") return true;
    }
    return false;
  }, [data.messages]);

  return (
    <div className="conv-emergency-banner" role="alert">
      <div className="conv-emergency-pulse" aria-hidden />
      <div className="conv-emergency-body">
        <strong>{t("conv.emergency.title")}</strong>
        <span> {t("conv.emergency.subtitle")}</span>
      </div>
      <div className={`conv-emergency-status conv-emergency-${routedTo112 ? "ok" : "missing"}`}>
        {routedTo112 ? t("conv.emergency.routed") : t("conv.emergency.missing")}
      </div>
    </div>
  );
}

/**
 * Bölüm B#6 — "sessiz transfer" sorununu açığa çıkarmak için
 * waiting_human statüsünde gözüken uyarı barı. Kaç dakikadır beklediğini ve
 * son operatör mesajının ne zaman olduğunu hesaplar.
 */
function HandoffBanner({ data }: { data: ClinicalConversationDetail }) {
  const { t } = useT();
  const lastOperator = useMemo(() => {
    for (let i = data.messages.length - 1; i >= 0; i--) {
      if (data.messages[i].sender === "operator") return data.messages[i];
    }
    return null;
  }, [data.messages]);

  const waitingMinutes = useMemo(() => {
    const ref = data.messages[data.messages.length - 1]?.created_at ?? data.updated_at;
    try {
      const diff = Date.now() - new Date(ref).getTime();
      return Math.max(0, Math.round(diff / 60_000));
    } catch {
      return null;
    }
  }, [data]);

  return (
    <div className="conv-handoff-banner" role="status">
      <strong>{t("conv.handoff.title")}</strong>
      <span>
        {lastOperator
          ? t("conv.handoff.last_operator") + ": " + formatTimestamp(lastOperator.created_at)
          : t("conv.handoff.no_operator_yet")}
      </span>
      {waitingMinutes !== null ? (
        <span className="conv-handoff-wait">
          ⏱ {waitingMinutes}m {t("conv.handoff.waiting")}
        </span>
      ) : null}
    </div>
  );
}

/**
 * Bölüm F#9 — sentiment trajectory. Hasta mesajları arasından ilk vs son
 * sentiment skorunu çıkarır, trend yönünü gösterir. Metadata'da
 * `sentiment_score` (number -1..1) olduğunu varsayar. Yoksa gizler.
 */
function SentimentStrip({ messages }: { messages: ClinicalMessage[] }) {
  const { t } = useT();
  const patientMessages = useMemo(() => messages.filter((m) => m.sender === "patient"), [messages]);

  const scores = patientMessages
    .map((m) => {
      const v = m.metadata_json?.sentiment_score;
      return typeof v === "number" ? v : null;
    })
    .filter((v): v is number => v !== null);

  if (scores.length < 2) return null;

  const first = scores[0];
  const last = scores[scores.length - 1];
  const delta = last - first;
  const direction = delta > 0.1 ? "up" : delta < -0.1 ? "down" : "flat";

  return (
    <div className={`conv-sentiment conv-sentiment-${direction}`}>
      <span className="conv-sentiment-label">{t("conv.sentiment.title")}</span>
      <span>
        {first.toFixed(2)} → {last.toFixed(2)}
      </span>
      <span className="conv-sentiment-delta">
        {direction === "up" ? "↑" : direction === "down" ? "↓" : "→"}{" "}
        {t(`conv.sentiment.${direction}` as const, direction)}
      </span>
    </div>
  );
}

function MessageBubble({ message }: { message: ClinicalMessage }) {
  const { t } = useT();

  const sideClass = useMemo(() => {
    switch (message.sender) {
      case "patient":
        return "conv-bubble-patient";
      case "assistant":
        return "conv-bubble-assistant";
      case "operator":
        return "conv-bubble-operator";
      default:
        return "conv-bubble-system";
    }
  }, [message.sender]);

  const conf =
    message.confidence_score !== null && message.confidence_score !== undefined
      ? Math.round(message.confidence_score * 100)
      : null;

  // Bölüm A8: tek mesajda birden fazla intent — metadata'da `intents` array'i destekle
  const extraIntents = useMemo<string[]>(() => {
    const meta = message.metadata_json ?? {};
    const list = meta.intents;
    if (Array.isArray(list)) return list.filter((x): x is string => typeof x === "string");
    return [];
  }, [message.metadata_json]);

  // Bölüm H: confidence eşik altı uyarısı
  const belowThreshold = isConfidenceBelowThreshold(message.intent, message.confidence_score);

  // Bölüm B#1: hallucination_risk
  const hallucination = Boolean(message.metadata_json?.hallucination_risk);

  // Bölüm A6: acil — mesaj seviyesinde de işaretle
  const emergency = isEmergency(message.intent);
  const voiceTranscript = readVoiceTranscript(message.metadata_json ?? undefined);

  const bubbleFlags = [
    belowThreshold ? "conv-bubble-low-conf" : "",
    hallucination ? "conv-bubble-hallucination" : "",
    emergency ? "conv-bubble-emergency" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <article className={`conv-bubble ${sideClass} ${bubbleFlags}`}>
      <header className="conv-bubble-head">
        <span className="conv-bubble-sender">{message.sender}</span>
        <span className="conv-bubble-time">{formatTimestamp(message.created_at)}</span>
      </header>
      <div className="conv-bubble-body">{message.content}</div>
      {voiceTranscript ? (
        <div className="conv-voice-transcript">
          <span className="conv-voice-label">AI duydu:</span>
          <span className="conv-voice-text">"{voiceTranscript.transcript}"</span>
          {voiceTranscript.provider ? (
            <span className="conv-voice-provider">{voiceTranscript.provider}</span>
          ) : null}
          {voiceTranscript.audioBytes ? (
            <span className="conv-voice-provider">{formatBytes(voiceTranscript.audioBytes)}</span>
          ) : null}
          {voiceTranscript.confidence !== null ? (
            <span className={`conv-voice-provider ${voiceTranscript.confidence < 0.7 ? "is-low" : ""}`}>
              STT %{Math.round(voiceTranscript.confidence * 100)}
            </span>
          ) : null}
          {voiceTranscript.durationSeconds !== null ? (
            <span className="conv-voice-provider">{voiceTranscript.durationSeconds.toFixed(1)} sn</span>
          ) : null}
          {voiceTranscript.processingMs !== null ? (
            <span className="conv-voice-provider">{voiceTranscript.processingMs} ms</span>
          ) : null}
        </div>
      ) : null}
      {(message.intent || conf !== null || extraIntents.length > 0) && (
        <footer className="conv-bubble-foot">
          {message.intent ? <span>{message.intent}</span> : null}
          {extraIntents.map((i) => (
            <span key={i} className="conv-bubble-secondary-intent">+ {i}</span>
          ))}
          {conf !== null ? (
            <span className={belowThreshold ? "conv-bubble-warn" : undefined}>
              {conf}%
              {belowThreshold ? ` · ${t("conv.warn.low_confidence")}` : ""}
            </span>
          ) : null}
          {hallucination ? (
            <span className="conv-bubble-warn">⚠ {t("conv.warn.hallucination")}</span>
          ) : null}
          {message.language ? <span>{message.language.toUpperCase()}</span> : null}
        </footer>
      )}
    </article>
  );
}

function readVoiceTranscript(meta: Record<string, unknown> | undefined): {
  transcript: string;
  provider: string | null;
  audioBytes: number | null;
  confidence: number | null;
  durationSeconds: number | null;
  processingMs: number | null;
} | null {
  const raw = meta?.voice_transcript;
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  const transcript = typeof obj.transcript === "string" ? obj.transcript.trim() : "";
  if (!transcript) return null;
  return {
    transcript,
    provider: typeof obj.provider === "string" ? obj.provider : null,
    audioBytes: typeof obj.audio_bytes === "number" ? obj.audio_bytes : null,
    confidence: typeof obj.confidence === "number" ? obj.confidence : null,
    durationSeconds: typeof obj.duration_seconds === "number" ? obj.duration_seconds : null,
    processingMs: typeof obj.processing_ms === "number" ? obj.processing_ms : null,
  };
}

function readVoiceEventCounters(meta: Record<string, unknown> | undefined): {
  noResult: number;
  retryPrompt: number;
  sttFailure: number;
  maxRetry: number;
} | null {
  const raw = meta?.voice_event_counters;
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  return {
    noResult: numberFromUnknown(obj.no_result),
    retryPrompt: numberFromUnknown(obj.retry_prompt),
    sttFailure: numberFromUnknown(obj.stt_failure),
    maxRetry: numberFromUnknown(obj.max_retry_count),
  };
}

function readLastVoiceEvent(meta: Record<string, unknown> | undefined): {
  eventType: string;
  reason: string | null;
  createdAt: string | null;
} | null {
  const raw = meta?.last_voice_event;
  if (!raw || typeof raw !== "object") return null;
  const obj = raw as Record<string, unknown>;
  const eventType = typeof obj.event_type === "string" ? obj.event_type : "";
  if (!eventType) return null;
  return {
    eventType,
    reason: typeof obj.reason === "string" ? obj.reason : null,
    createdAt: typeof obj.created_at === "string" ? obj.created_at : null,
  };
}

function numberFromUnknown(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}
