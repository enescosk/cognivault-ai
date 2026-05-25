import type { PublicClinicView } from "../../api/patientClient";

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
        <h2>Hizmetlerimiz</h2>
        <ul>
          {clinic.services.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      </section>

      {clinic.branches.length > 0 ? (
        <section className="patient-branches">
          <h2>Şube ve çalışma saatleri</h2>
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
          AI ile randevu al →
        </button>
        {clinic.contact_phone ? (
          <a href={`tel:${clinic.contact_phone.replace(/\s/g, "")}`} className="patient-cta-secondary">
            ☎ Telefonla {clinic.contact_phone}
          </a>
        ) : null}
      </div>

      <p className="patient-hint">
        AI ile sohbet etmek için KVKK aydınlatma metnini okuyup onaylamanız gerekir.
        Aydınlatma metni v{clinic.disclosure.version} — saklama süresi, haklarınız ve
        veri işleme amacımız açıkça yazılıdır.
      </p>
    </div>
  );
}
