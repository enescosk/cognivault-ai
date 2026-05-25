import { useState } from "react";
import { simulateWhatsAppMessage } from "../api/client";
import type { WebhookIngestionResponse } from "../types/api";

type Props = { token: string };

/**
 * Operator/admin için klinik AI test alanı.
 * Sahte WhatsApp mesajları gönderir, AI'ın çıkardığı niyet/güven/persona/
 * gerekirse insan-onayı bayrağını görsel olarak gösterir.
 *
 * Production gerçek webhook trafiği ile aynı pipeline'ı tetikler — bu sayede
 * operator gerçek hasta verisi olmadan AI davranışını canlı doğrulayabilir.
 */
export function ClinicalPlayground({ token }: Props) {
  const [phone, setPhone] = useState("+905551112233");
  const [body, setBody] = useState("Yarın için randevu almak istiyorum");
  const [patientName, setPatientName] = useState("Test Hasta");
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState<Array<{ sent: string; reply: WebhookIngestionResponse | null; error?: string }>>([]);

  const presets: Array<{ label: string; body: string }> = [
    { label: "Randevu", body: "Yarın için randevu almak istiyorum" },
    { label: "Fiyat", body: "Dolgu ne kadar ücret tutuyor?" },
    { label: "Sigorta", body: "SGK geçiyor mu acaba?" },
    { label: "Acil", body: "Diş ağrım çok şiddetli, bayılacak gibiyim" },
    { label: "Sinirli", body: "Saatlerdir bekliyorum hâlâ cevap yok, rezalet" },
  ];

  async function handleSend() {
    if (!body.trim()) return;
    setLoading(true);
    const sent = body;
    try {
      const result = await simulateWhatsAppMessage(token, {
        from_phone: phone,
        body: sent,
        patient_name: patientName || undefined,
      });
      setHistory((prev) => [{ sent, reply: result }, ...prev].slice(0, 10));
    } catch (err) {
      setHistory((prev) => [{ sent, reply: null, error: err instanceof Error ? err.message : "Hata" }, ...prev].slice(0, 10));
    } finally {
      setLoading(false);
    }
  }

  function riskClass(risk?: string | null): string {
    if (risk === "high") return "playground-pill playground-pill--high";
    if (risk === "medium") return "playground-pill playground-pill--medium";
    return "playground-pill playground-pill--low";
  }

  return (
    <div className="playground-card">
      <div className="playground-header">
        <div className="playground-title">Clinical AI Playground</div>
        <div className="playground-subtitle">Sahte hasta mesajı gönder, AI yanıtını gör</div>
      </div>

      <div className="playground-form">
        <div className="playground-row">
          <label>Telefon</label>
          <input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+90555..." />
        </div>
        <div className="playground-row">
          <label>İsim</label>
          <input value={patientName} onChange={(e) => setPatientName(e.target.value)} placeholder="Hasta adı (ops)" />
        </div>
        <div className="playground-row">
          <label>Mesaj</label>
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} />
        </div>
        <div className="playground-presets">
          {presets.map((p) => (
            <button key={p.label} type="button" className="playground-preset" onClick={() => setBody(p.body)}>
              {p.label}
            </button>
          ))}
        </div>
        <button type="button" className="playground-send" onClick={handleSend} disabled={loading || !body.trim()}>
          {loading ? "Gönderiliyor…" : "Mesajı Gönder"}
        </button>
      </div>

      <div className="playground-history">
        {history.length === 0 && (
          <div className="playground-empty">Henüz simülasyon yok. Yukarıdaki preset'lerden birini deneyebilirsin.</div>
        )}
        {history.map((entry, idx) => (
          <div key={idx} className="playground-entry">
            <div className="playground-msg-sent">
              <span className="playground-msg-label">Gönderildi:</span> {entry.sent}
            </div>
            {entry.error ? (
              <div className="playground-msg-error">Hata: {entry.error}</div>
            ) : entry.reply ? (
              <div className="playground-reply">
                <div className="playground-reply-meta">
                  <span className={riskClass(entry.reply.risk)}>{entry.reply.intent ?? "unknown"}</span>
                  <span className="playground-confidence">
                    güven: {((entry.reply.confidence ?? 0) * 100).toFixed(0)}%
                  </span>
                  {entry.reply.requires_human_review && (
                    <span className="playground-pill playground-pill--review">İnsan onayı gerekli</span>
                  )}
                  {entry.reply.persona_name && (
                    <span className="playground-persona">{entry.reply.persona_name}</span>
                  )}
                </div>
                {entry.reply.reply && <div className="playground-reply-text">{entry.reply.reply}</div>}
                {entry.reply.risk_reason && (
                  <div className="playground-risk-reason">Risk sebebi: {entry.reply.risk_reason}</div>
                )}
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
