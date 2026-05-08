import type { AICapabilities, QualityReport } from "../types/api";

type Props = {
  capabilities: AICapabilities | null;
  quality: QualityReport | null;
  view: "chat" | "appointments" | "clinical";
};

const viewLabels: Record<Props["view"], string> = {
  chat: "Hasta sohbeti",
  appointments: "Randevu akışı",
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

export function SystemHealthPanel({ capabilities, quality, view }: Props) {
  const recommendation = quality?.recommendations?.[0];
  const llmProvider = capabilities?.llm.active_provider ?? quality?.llm.active_provider;
  const voiceProvider = capabilities
    ? `${capabilities.voice.stt.active_provider} / ${capabilities.voice.tts.active_provider}`
    : quality
      ? `${quality.voice.stt.active_provider} / ${quality.voice.tts.active_provider}`
      : "Bekleniyor";

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
        <div className="system-health-pill">
          <span>Ses</span>
          <strong>{providerLabel(voiceProvider)}</strong>
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
