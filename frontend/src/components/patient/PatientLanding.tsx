import type { PublicClinicView } from "../../api/patientClient";
import { fill, useT } from "../../i18n";

interface Props {
  clinic: PublicClinicView;
  onStart: () => void;
}

/**
 * Hasta sayfasının "vitrin" katmanı.
 *
 * 6 saniyede taranabilmesi gerekir (Bölüm C — landing dropoff).
 * Hero, hizmet etiketleri, şube bilgisi, tek bir net CTA.
 */
export function PatientLanding({ clinic, onStart }: Props) {
  const { t } = useT();
  return (
    <div className="patient-card patient-landing">
      <header className="patient-hero">
        {clinic.logo_url ? (
          <img className="patient-logo" src={clinic.logo_url} alt={clinic.name} />
        ) : (
          <div className="patient-logo-fallback" aria-hidden>
            {clinic.name.slice(0, 2).toUpperCase()}
          </div>
        )}
        <div className="patient-hero-text">
          <h1>{clinic.headline}</h1>
          <p>{clinic.sub_headline}</p>
        </div>
      </header>

      <section className="patient-services">
        <h2>{t("patient.landing.services")}</h2>
        <ul>
          {clinic.services.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      </section>

      {clinic.branches.length > 0 ? (
        <section className="patient-branches">
          <h2>{t("patient.landing.branches")}</h2>
          {clinic.branches.map((b) => (
            <div key={b.name} className="patient-branch-row">
              <strong>{b.name}</strong>
              {b.address ? <span>{b.address}</span> : null}
              {b.working_hours
                ? Object.entries(b.working_hours).map(([day, hours]) => (
                    <span key={day}>
                      <em>{day}:</em> {hours}
                    </span>
                  ))
                : null}
            </div>
          ))}
        </section>
      ) : null}

      <div className="patient-cta-row">
        <button type="button" className="patient-cta" onClick={onStart}>
          {t("patient.landing.cta")}
        </button>
        {clinic.contact_phone ? (
          <a href={`tel:${clinic.contact_phone.replace(/\s/g, "")}`} className="patient-cta-secondary">
            {fill(t("patient.landing.call"), { phone: clinic.contact_phone })}
          </a>
        ) : null}
      </div>

      <p className="patient-hint">
        {fill(t("patient.landing.hint"), { version: clinic.disclosure.version })}
      </p>
    </div>
  );
}
