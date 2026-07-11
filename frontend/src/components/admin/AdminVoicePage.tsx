import { useEffect, useState } from "react";
import {
  getVoiceSettings,
  testVoiceSettings,
  updateVoiceSettings,
  type VoiceDiagnostics,
  type VoiceSettings,
} from "../../api/client";
import { showToast } from "../ui/Toast";

interface Props {
  token: string;
}

const defaultSettings: VoiceSettings = {
  stt_provider: "local",
  tts_provider: "local",
  external_enabled: false,
  allow_cross_border_processors: false,
  tts_voice: "",
};

export function AdminVoicePage({ token }: Props) {
  const [settings, setSettings] = useState<VoiceSettings>(defaultSettings);
  const [diagnostics, setDiagnostics] = useState<VoiceDiagnostics | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const data = await getVoiceSettings(token);
        setDiagnostics(data);
        setSettings(data.settings);
      } catch (err) {
        showToast(err instanceof Error ? err.message : "Ses ayarları yüklenemedi.", "error");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [token]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const data = await updateVoiceSettings(token, settings);
      setDiagnostics(data);
      setSettings(data.settings);
      showToast("Ses provider ayarları güncellendi.", "success");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Ses ayarları kaydedilemedi.", "error");
    } finally {
      setSaving(false);
    }
  }

  async function handleTest() {
    setTesting(true);
    try {
      const data = await testVoiceSettings(token);
      setDiagnostics(data);
      showToast("Ses yapılandırma testi tamamlandı.", "success");
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Ses testi çalıştırılamadı.", "error");
    } finally {
      setTesting(false);
    }
  }

  if (loading) {
    return <div className="clinical-empty">Ses ayarları yükleniyor...</div>;
  }

  const simulated = diagnostics?.simulated_full_consent ?? {};
  const credentials = diagnostics?.credentials ?? {};
  const local = diagnostics?.local ?? {};

  return (
    <div className="clinic-card admin-voice-card">
      <div className="clinical-card-top clinical-card-top--spaced">
        <div>
          <span>Ses Provider</span>
          <h3>Doğal Ses ve STT Ayarları</h3>
        </div>
        <strong className={`clinical-status ${simulated.cloud_route_ready ? "" : "danger"}`}>
          {simulated.cloud_route_ready ? "bulut hazır" : "local/fallback"}
        </strong>
      </div>

      <form onSubmit={handleSave} className="clinical-form">
        <div className="admin-voice-grid">
          <label>
            STT Provider
            <select
              value={settings.stt_provider}
              onChange={(event) => setSettings((cur) => ({ ...cur, stt_provider: event.target.value }))}
            >
              <option value="local">Local Whisper</option>
              <option value="openai">OpenAI Whisper</option>
              <option value="elevenlabs">ElevenLabs Scribe</option>
            </select>
          </label>

          <label>
            TTS Provider
            <select
              value={settings.tts_provider}
              onChange={(event) => setSettings((cur) => ({ ...cur, tts_provider: event.target.value }))}
            >
              <option value="local">Local Piper</option>
              <option value="openai">OpenAI TTS</option>
              <option value="elevenlabs">ElevenLabs TTS</option>
            </select>
          </label>

          <label>
            TTS Voice
            <input
              value={settings.tts_voice ?? ""}
              onChange={(event) => setSettings((cur) => ({ ...cur, tts_voice: event.target.value }))}
              placeholder="nova veya ElevenLabs voice_id"
            />
          </label>
        </div>

        <div className="admin-voice-checks">
          <label>
            <input
              type="checkbox"
              checked={settings.external_enabled}
              onChange={(event) => setSettings((cur) => ({ ...cur, external_enabled: event.target.checked }))}
            />
            Klinik için harici ses provider yolu açık
          </label>
          <label>
            <input
              type="checkbox"
              checked={settings.allow_cross_border_processors}
              onChange={(event) => setSettings((cur) => ({ ...cur, allow_cross_border_processors: event.target.checked }))}
            />
            Klinik sınır-ötesi işleyici izni açık
          </label>
        </div>

        <div className="admin-voice-actions">
          <button type="submit" disabled={saving}>{saving ? "Kaydediliyor..." : "Ayarları Kaydet"}</button>
          <button type="button" onClick={handleTest} disabled={testing || saving}>
            {testing ? "Test ediliyor..." : "Canlı Konfigürasyon Testi"}
          </button>
        </div>
      </form>

      <div className="admin-voice-diagnostics">
        <DiagnosticPill label="STT route" value={String(simulated.stt_provider_class ?? "-")} />
        <DiagnosticPill label="TTS route" value={String(simulated.tts_provider_class ?? "-")} />
        <DiagnosticPill label="OpenAI key" value={credentials.openai_api_key ? "var" : "yok"} />
        <DiagnosticPill label="ElevenLabs key" value={credentials.elevenlabs_api_key ? "var" : "yok"} />
        <DiagnosticPill label="Piper" value={local.piper_voice_available ? "hazır" : "yok"} />
      </div>
    </div>
  );
}

function DiagnosticPill({ label, value }: { label: string; value: string }) {
  return (
    <span className="admin-voice-pill">
      <small>{label}</small>
      <strong>{value}</strong>
    </span>
  );
}
