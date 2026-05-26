import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import {
  getPublicDisclosure,
  submitConsent,
  type PublicClinicView,
} from "../../api/patientClient";
import { SkeletonBlock } from "../ui/Skeleton";

interface Props {
  clinic: PublicClinicView;
  onAccepted: (consentToken: string, disclosureVersion: string) => void;
  onCancel: () => void;
}

/**
 * KVKK aydınlatma + onay modal'ı.
 *
 * "Tam metni göster" expander açıldığında body indirilir; modal başlangıçta
 * sadece başlık + 4 madde özet + 2 buton (Kabul / Vazgeç).
 *
 * Kabul → POST /consent → consent_token döner → orchestrator'a iletir.
 * Vazgeç → landing'e dönülür, alternatif iletişim kanalları gösterilir.
 */
export function PatientConsentModal({ clinic, onAccepted, onCancel }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [includeCrossBorder, setIncludeCrossBorder] = useState(false);

  const disclosureQuery = useQuery({
    queryKey: ["public-disclosure", clinic.slug],
    queryFn: () => getPublicDisclosure(clinic.slug),
    enabled: expanded || true, // hash doğrulama için her zaman çek
    staleTime: 5 * 60_000,
  });

  async function handleAccept() {
    const disclosure = disclosureQuery.data;
    if (!disclosure) {
      setError("Aydınlatma metni yükleniyor — lütfen tekrar deneyin.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await submitConsent(clinic.slug, {
        disclosure_version: disclosure.version,
        disclosure_hash: disclosure.body_hash,
        accepted_cross_border: includeCrossBorder,
      });
      onAccepted(res.consent_token, disclosure.version);
    } catch (err) {
      setError(err instanceof Error ? err.message : "consent_failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="patient-card patient-consent">
      <header className="patient-consent-header">
        <h2>KVKK aydınlatma onayı</h2>
        <span className="patient-badge">v{clinic.disclosure.version}</span>
      </header>

      <ul className="patient-consent-bullets">
        <li>Ad-soyad, telefon ve sağlık şikayetiniz işlenir.</li>
        <li>Amaç: randevu yönetimi ve sizinle iletişim.</li>
        <li>Veriler yerel sunucularımızda işlenir.</li>
        <li>Saklama: 90 gün anonimleştirme, 1 yıl tam silme.</li>
        <li>KVKK m.11 kapsamındaki tüm haklarınız saklıdır.</li>
      </ul>

      <label className="patient-consent-checkbox">
        <input
          type="checkbox"
          checked={includeCrossBorder}
          onChange={(e) => setIncludeCrossBorder(e.target.checked)}
        />
        <span>
          WhatsApp, Twilio gibi yurt dışı transit aracılarının kullanımına da onay
          veriyorum. (Opsiyonel — verilmezse alternatif iletişim kanalı önerilir.)
        </span>
      </label>

      <button
        type="button"
        className="patient-link-button"
        onClick={() => setExpanded((v) => !v)}
      >
        {expanded ? "▴ Tam metni gizle" : "▾ Tam aydınlatma metnini oku"}
      </button>

      {expanded ? (
        <div className="patient-consent-fulltext">
          {disclosureQuery.isLoading ? (
            <SkeletonBlock count={4} />
          ) : disclosureQuery.error ? (
            <div className="patient-error-line">Aydınlatma metni yüklenemedi.</div>
          ) : (
            <pre>{disclosureQuery.data?.body}</pre>
          )}
        </div>
      ) : null}

      {error ? <div className="patient-error-line">{error}</div> : null}

      <div className="patient-consent-actions">
        <button
          type="button"
          className="patient-cta"
          onClick={handleAccept}
          disabled={submitting || !disclosureQuery.data}
        >
          {submitting ? "Onaylanıyor…" : "Kabul ediyorum, devam et"}
        </button>
        <button type="button" className="patient-cta-ghost" onClick={onCancel}>
          Vazgeç
        </button>
      </div>

      <p className="patient-hint">
        "Vazgeç" derseniz hizmetten men edilmezsiniz —
        {clinic.contact_phone ? ` ${clinic.contact_phone} numarasını arayabilir` : " klinikle telefonla iletişime geçebilir"}
        {" "}veya kliniğe direkt başvurabilirsiniz.
      </p>
    </div>
  );
}
