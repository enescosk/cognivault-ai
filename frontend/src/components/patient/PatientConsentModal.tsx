import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import {
  getPublicDisclosure,
  submitConsent,
  type PublicClinicView,
} from "../../api/patientClient";
import { fill, useT } from "../../i18n";
import { SkeletonBlock } from "../ui/Skeleton";

interface Props {
  clinic: PublicClinicView;
  /** Async — kabul edilince orchestrator hemen startConversation çağırır. */
  onAccepted: (consentToken: string, disclosureVersion: string) => void | Promise<void>;
  onCancel: () => void;
  /** True ise "Sohbet açılıyor…" durumu gösterir (orchestrator startConversation çalışıyor). */
  bootstrapping?: boolean;
  /** Orchestrator startConversation hata verdiyse buraya düşer. */
  bootstrapError?: string | null;
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
export function PatientConsentModal({
  clinic,
  onAccepted,
  onCancel,
  bootstrapping = false,
  bootstrapError = null,
}: Props) {
  const { t } = useT();
  const [expanded, setExpanded] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [includeCrossBorder, setIncludeCrossBorder] = useState(false);
  const [includeVoiceProcessing, setIncludeVoiceProcessing] = useState(false);

  const disclosureQuery = useQuery({
    queryKey: ["public-disclosure", clinic.slug],
    queryFn: () => getPublicDisclosure(clinic.slug),
    enabled: expanded || true, // hash doğrulama için her zaman çek
    staleTime: 5 * 60_000,
  });

  async function handleAccept() {
    const disclosure = disclosureQuery.data;
    if (!disclosure) {
      setError(t("patient.consent.loading_retry"));
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const res = await submitConsent(clinic.slug, {
        disclosure_version: disclosure.version,
        disclosure_hash: disclosure.body_hash,
        accepted_cross_border: includeCrossBorder,
        accepted_voice_processing: includeVoiceProcessing,
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
        <h2>{t("patient.consent.title")}</h2>
        <span className="patient-badge">{clinic.disclosure.version}</span>
      </header>

      <ul className="patient-consent-bullets">
        <li>{t("patient.consent.bullet1")}</li>
        <li>{t("patient.consent.bullet2")}</li>
        <li>{t("patient.consent.bullet3")}</li>
        <li>{t("patient.consent.bullet4")}</li>
        <li>{t("patient.consent.bullet5")}</li>
      </ul>

      <label className="patient-consent-checkbox">
        <input
          type="checkbox"
          checked={includeCrossBorder}
          onChange={(e) => {
            setIncludeCrossBorder(e.target.checked);
            if (!e.target.checked) setIncludeVoiceProcessing(false);
          }}
        />
        <span>{t("patient.consent.cross_border")}</span>
      </label>

      <label className="patient-consent-checkbox">
        <input
          type="checkbox"
          checked={includeVoiceProcessing}
          onChange={(e) => {
            setIncludeVoiceProcessing(e.target.checked);
            if (e.target.checked) setIncludeCrossBorder(true);
          }}
        />
        <span>{t("patient.consent.voice_processing")}</span>
      </label>

      <button
        type="button"
        className="patient-link-button"
        onClick={() => setExpanded((v) => !v)}
      >
        {expanded ? t("patient.consent.hide_full") : t("patient.consent.show_full")}
      </button>

      {expanded ? (
        <div className="patient-consent-fulltext">
          {disclosureQuery.isLoading ? (
            <SkeletonBlock count={4} />
          ) : disclosureQuery.error ? (
            <div className="patient-error-line">{t("patient.consent.load_failed")}</div>
          ) : (
            <pre>{disclosureQuery.data?.body}</pre>
          )}
        </div>
      ) : null}

      {(error || bootstrapError) ? (
        <div className="patient-error-line">{error || bootstrapError}</div>
      ) : null}

      <div className="patient-consent-actions">
        <button
          type="button"
          className="patient-cta"
          onClick={handleAccept}
          disabled={submitting || bootstrapping || !disclosureQuery.data}
        >
          {bootstrapping
            ? t("patient.consent.bootstrapping")
            : submitting
              ? t("patient.consent.submitting")
              : t("patient.consent.accept")}
        </button>
        <button
          type="button"
          className="patient-cta-ghost"
          onClick={onCancel}
          disabled={bootstrapping}
        >
          {t("common.cancel")}
        </button>
      </div>

      <p className="patient-hint">
        {clinic.contact_phone
          ? fill(t("patient.consent.cancel_hint_phone"), { phone: clinic.contact_phone })
          : t("patient.consent.cancel_hint_nophone")}
      </p>
    </div>
  );
}
