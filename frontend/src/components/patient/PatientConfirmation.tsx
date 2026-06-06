import type { PublicClinicView } from "../../api/patientClient";
import { fill, useT } from "../../i18n";

interface Props {
  clinic: PublicClinicView;
  onStartOver: () => void;
}

/**
 * Randevu kayıt sonrası onay ekranı.
 *
 * MVP: SMS gönderimi mock. Faz P3'te gerçek Netgsm/Twilio entegrasyonu.
 */
export function PatientConfirmation({ clinic, onStartOver }: Props) {
  const { t } = useT();
  return (
    <div className="patient-card patient-confirmation">
      <div className="patient-confirmation-check" aria-hidden>
        ✓
      </div>
      <h2>{t("patient.confirm.title")}</h2>
      <p>{fill(t("patient.confirm.body"), { name: clinic.name })}</p>

      <ul className="patient-confirmation-next">
        <li>{t("patient.confirm.next1")}</li>
        <li>{t("patient.confirm.next2")}</li>
        <li>{t("patient.confirm.next3")}</li>
      </ul>

      {clinic.public_address ? (
        <p className="patient-hint">
          <strong>{t("patient.confirm.address")}</strong> {clinic.public_address}
        </p>
      ) : null}
      {clinic.contact_phone ? (
        <p className="patient-hint">
          <strong>{t("patient.confirm.contact")}</strong> {clinic.contact_phone}
        </p>
      ) : null}

      <button type="button" className="patient-cta" onClick={onStartOver}>
        {t("patient.confirm.start_over")}
      </button>
    </div>
  );
}
