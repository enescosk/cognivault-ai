import type { AICapabilities, QualityReport } from "../types/api";

type Props = {
  capabilities: AICapabilities | null;
  quality: QualityReport | null;
  view: "dashboard" | "chat" | "appointments" | "notes" | "clinical";
};

const viewLabels: Record<Props["view"], string> = {
  dashboard: "Genel bakis",
  chat: "Hasta sohbeti",
  appointments: "Randevu akışı",
  notes: "Randevu notlari",
  clinical: "Klinik komuta",
};

function providerLabel(value?: string) {
  if (!value) return "Bekleniyor";
  return value.split("_").join(" ");
}

function gradeLabel(value?: string) {
  if (value === "excellent") return "Mükemmel";
  if (value === "strong") return "Güçlü";
  return "İyileştiriliyor";
}

function boolSignal(value: unknown): boolean {
  return value === true;
}

function voiceDiagnosis(capabilities: AICapabilities | null, quality: QualityReport | null) {
  const voice = capabilities?.voice ?? quality?.voice;
  const stt = voice?.stt;
  const tts = voice?.tts;
  const sttProvider = stt?.active_provider ?? "Bekleniyor";
  const ttsProvider = tts?.active_provider ?? "Bekleniyor";
  const ready = sttProvider !== "unconfigured" && ttsProvider !== "unconfigured";
  const offlineReady = boolSignal(stt?.offline_capable) && boolSignal(tts?.offline_capable);
  const cloudReady = boolSignal(stt?.openai_configured) || boolSignal(tts?.openai_configured);
  let status = "Hazir";
  if (!ready) status = offlineReady ? "Yerel hazir" : cloudReady ? "Bulut anahtari var" : "Kurulum eksik";
  return {
    provider: `${sttProvider} / ${ttsProvider}`,
    ready,
    status,
  };
}

export function SystemHealthPanel({ capabilities, quality, view }: Props) {
  const recommendation = quality?.recommendations?.[0];
  const llmProvider = capabilities?.llm.active_provider ?? quality?.llm.active_provider;
  const voice = voiceDiagnosis(capabilities, quality);

  return (
    <section className="system-health-strip" aria-label="AI sistem durumu">
      <div className="system-health-primary">
        <div className="system-health-kicker">Canlı operasyon katmanı</div>
        <div className="system-health-title">
          <span>{viewLabels[view]}</span>
          <strong>{quality ? `${quality.score}/100 · ${gradeLabel(quality.grade)}` : "Kalite ölçümü hazırlanıyor"}</strong>
        </div>
      </div>

      <div className="system-health-metrics">
        <div className="system-health-pill">
          <span>LLM</span>
          <strong>{providerLabel(llmProvider)}</strong>
        </div>
        <div className={`system-health-pill ${voice.ready ? "system-health-pill--ok" : "system-health-pill--risk"}`}>
          <span>Ses</span>
          <strong>{providerLabel(voice.provider)}</strong>
          <small>{voice.status}</small>
        </div>
        <div className="system-health-pill">
          <span>Senaryo</span>
          <strong>{quality?.metrics.automated_scenarios ?? 0} otomatik</strong>
        </div>
        <div className={`system-health-pill ${quality?.metrics.recent_failures ? "system-health-pill--risk" : "system-health-pill--ok"}`}>
          <span>Backend</span>
          <strong>{quality?.metrics.recent_failures ? `${quality.metrics.recent_failures} hata` : "Temiz"}</strong>
        </div>
      </div>

      <div className="system-health-next">
        <span>Sıradaki iyileştirme</span>
        <strong>{recommendation?.title ?? "Sinyal bekleniyor"}</strong>
      </div>
    </section>
  );
}
