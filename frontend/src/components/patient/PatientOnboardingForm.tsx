import { useState } from "react";

import {
  startConversation,
  type PublicClinicView,
  type StartConversationResponse,
} from "../../api/patientClient";

interface Props {
  clinic: PublicClinicView;
  consentToken: string;
  onStarted: (data: StartConversationResponse) => void;
  onCancel: () => void;
}

/**
 * KVKK m.9 minimization: sadece ad-soyad + telefon.
 *
 * Burada hiçbir sağlık verisi sorulmaz. Şikayet metni chat'e geçildikten
 * sonra hastanın kendi ifadesiyle alınır.
 */
export function PatientOnboardingForm({ clinic, consentToken, onStarted, onCancel }: Props) {
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * TR cep numarasını normalize edip E.164 formatına çevirir.
   * Geçerli ise `+90` prefix'li 13 haneli string döner; değilse `null`.
   *
   * Kabul edilen girdiler:
   *   "0532 123 45 67"   "0537 033 47 21"   "0537-033-4721"
   *   "0537 0334721"     "5370334721"
   *   "+905370334721"    "905370334721"
   *   "+90 537 033 47 21"
   */
  function normalizePhone(raw: string): string | null {
    const cleaned = raw.replace(/[\s\-()]/g, "");
    const match = cleaned.match(/^(?:\+90|90|0)?(5\d{9})$/);
    return match ? `+90${match[1]}` : null;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (fullName.trim().length < 2) {
      setError("Lütfen adınızı ve soyadınızı girin.");
      return;
    }

    const normalizedPhone = normalizePhone(phone);
    if (!normalizedPhone) {
      setError("Lütfen geçerli bir TR cep numarası girin (örn: 0532 123 45 67).");
      return;
    }

    setSubmitting(true);
    try {
      const res = await startConversation(clinic.slug, consentToken, {
        full_name: fullName.trim(),
        phone: normalizedPhone,
        initial_message: null,
      });
      onStarted(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "onboarding_failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="patient-card patient-onboarding" onSubmit={handleSubmit}>
      <header>
        <h2>Sizi tanıyalım</h2>
        <p>
          Sadece ad-soyad ve telefon alıyoruz. Sağlık şikayetinizi bir sonraki adımda
          AI asistanımızla sohbet ederek aktaracaksınız.
        </p>
      </header>

      <label className="patient-field">
        <span>Ad-soyad</span>
        <input
          type="text"
          autoComplete="name"
          required
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          placeholder="Ahmet Yılmaz"
        />
      </label>

      <label className="patient-field">
        <span>Cep telefonu</span>
        <input
          type="tel"
          autoComplete="tel"
          inputMode="numeric"
          required
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          placeholder="0532 123 45 67"
        />
      </label>

      {error ? <div className="patient-error-line">{error}</div> : null}

      <div className="patient-consent-actions">
        <button type="submit" className="patient-cta" disabled={submitting}>
          {submitting ? "Sohbet başlatılıyor…" : "AI sohbetini başlat"}
        </button>
        <button type="button" className="patient-cta-ghost" onClick={onCancel}>
          Vazgeç
        </button>
      </div>

      <p className="patient-hint">
        Devam ederek <strong>v{clinic.disclosure.version}</strong> KVKK aydınlatma
        metnini kabul ettiğinizi onaylarsınız.
      </p>
    </form>
  );
}
