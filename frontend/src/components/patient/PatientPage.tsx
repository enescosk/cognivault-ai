import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import {
  clearPatientSession,
  getPublicClinic,
  loadPatientSession,
  savePatientSession,
  startConversation,
  type PatientSessionState,
} from "../../api/patientClient";
import { fill, useT } from "../../i18n";
import { ErrorBoundary } from "../ErrorBoundary";
import { SkeletonBlock } from "../ui/Skeleton";
import { PatientChatRoom } from "./PatientChatRoom";
import { PatientConfirmation } from "./PatientConfirmation";
import { PatientConsentModal } from "./PatientConsentModal";
import { PatientLanding } from "./PatientLanding";

/**
 * Patient page orchestrator.
 *
 * Route: /c/:slug
 *
 * 5 step state machine:
 *   landing   →  Hero card + "Randevu al" CTA
 *   consent   →  KVKK aydınlatma + onay (modal)
 *   onboarding →  Ad-soyad + telefon
 *   chat       →  Canlı AI sohbet
 *   confirm    →  Randevu özeti
 *
 * Patient kimliği `sessionStorage` üzerinden yönetilir — kullanıcı sayfayı
 * yenilerse hangi adımda kaldığı oradan resume edilir.
 */

/**
 * Yeni akış (2026-05-26): onboarding adımı kaldırıldı.
 *
 *   landing → consent → chat → confirm
 *
 * Kimlik (ad-soyad + telefon) artık form'da değil, AI sohbet sırasında
 * inline toplanıyor (PATCH /patient endpoint'iyle güncellenir). Bu, hasta
 * dropout'unu azaltır: form sürüyle alan görmek yerine doğrudan AI'la
 * konuşmaya başlıyor.
 */
type Step = "landing" | "consent" | "chat" | "confirm";

export function PatientPage() {
  const { t, locale, setLocale } = useT();
  const params = useParams<{ slug: string }>();
  const slug = (params.slug ?? "").trim();

  const [step, setStep] = useState<Step>("landing");
  const [session, setSession] = useState<PatientSessionState>(() => {
    if (!slug) return { slug: "" };
    const saved = loadPatientSession(slug);
    const now = Date.now();
    if (
      saved &&
      ((saved.session_expires_at && saved.session_expires_at <= now) ||
        (saved.consent_expires_at && !saved.session_token && saved.consent_expires_at <= now))
    ) {
      clearPatientSession();
      return { slug };
    }
    return saved ?? { slug };
  });

  // Returning sessions: hangi adımda devam etsin?
  useEffect(() => {
    if (!slug) return;
    if (session.session_token && session.conversation_id) {
      setStep("chat");
    }
    // Onboarding step kaldırıldı; sadece consent kalmış session
    // yeniden landing'den başlasın (kullanıcı modal kapattı, devam etmek istemedi).
  }, []); // ilk yüklemede bir kez

  const clinicQuery = useQuery({
    queryKey: ["public-clinic", slug],
    queryFn: () => getPublicClinic(slug),
    enabled: Boolean(slug),
    retry: 1,
    staleTime: 5 * 60_000,
  });

  // Klinik teması — primary/accent renkleri CSS değişkeni olarak uygular
  useEffect(() => {
    if (!clinicQuery.data) return;
    document.documentElement.style.setProperty("--patient-primary", clinicQuery.data.primary_color);
    document.documentElement.style.setProperty("--patient-accent", clinicQuery.data.accent_color);
    document.title = clinicQuery.data.name;
    return () => {
      document.documentElement.style.removeProperty("--patient-primary");
      document.documentElement.style.removeProperty("--patient-accent");
    };
  }, [clinicQuery.data]);

  // session değişimini yan etkilerden bağımsız kaydet
  useEffect(() => {
    if (!slug || !session) return;
    savePatientSession({ ...session, slug });
  }, [session, slug]);

  const branding = clinicQuery.data;

  const [bootstrapError, setBootstrapError] = useState<string | null>(null);
  const [bootstrapping, setBootstrapping] = useState(false);
  const [initialWelcome, setInitialWelcome] = useState<string | null>(null);

  /**
   * Consent kabul edilince hemen anonim conversation aç.
   *
   * Yeni akışta hasta name/phone vermeden direkt chat'e geçiyor; backend
   * placeholder bir ClinicPatient (`anon-<uuid>`) yaratıyor, AI sohbet
   * sırasında set_patient_identity ile bu placeholder'ı güncelliyor.
   */
  const onConsentGranted = async (consentToken: string, disclosureVersion: string) => {
    setBootstrapping(true);
    setBootstrapError(null);
    try {
      // Backend compatibility shim: deployed backend'lerin bir kısmı hâlâ
      // PatientIdentityRequest.full_name ve phone'u required `str` olarak
      // istiyor (Optional refactor pick'lenmemiş olabilir). Bu yüzden
      // her zaman placeholder kimlik gönderiyoruz; ClinicPatient row'unda
      // `full_name="Misafir Hasta"` ve random TR cep placeholder'ı görünür.
      // AI sohbet sırasında PATCH /patient ile bu placeholder gerçek
      // değerlerle güncellenir (yeni anonimleştirme akışıyla aynı sonuç).
      const placeholderPhone =
        "+905" +
        Math.floor(10_000_000 + Math.random() * 89_999_999).toString();
      const res = await startConversation(slug, consentToken, {
        full_name: "Misafir Hasta",
        phone: placeholderPhone,
      });
      setSession((s) => ({
        ...s,
        consent_token: consentToken,
        disclosure_version: disclosureVersion,
        consent_expires_at: Date.now() + 15 * 60_000,
        session_token: res.session_token,
        conversation_id: res.conversation_id,
        patient_id: res.patient_id,
        session_expires_at: Date.now() + 60 * 60_000,
      }));
      setInitialWelcome(res.welcome_message ?? null);
      setStep("chat");
    } catch (err) {
      setBootstrapError(err instanceof Error ? err.message : "conversation_start_failed");
      // Modal'da kalalım; kullanıcı tekrar deneyebilsin.
      setSession((s) => ({
        ...s,
        consent_token: consentToken,
        disclosure_version: disclosureVersion,
        consent_expires_at: Date.now() + 15 * 60_000,
      }));
    } finally {
      setBootstrapping(false);
    }
  };

  const onAppointmentConfirmed = () => {
    setStep("confirm");
  };

  const onStartOver = () => {
    clearPatientSession();
    setSession({ slug });
    setStep("landing");
  };

  const langToggle = (
    <div className="patient-langbar">
      <button
        type="button"
        className="patient-lang-toggle"
        onClick={() => setLocale(locale === "tr" ? "en" : "tr")}
      >
        {t("patient.lang.switch")}
      </button>
    </div>
  );

  if (!slug) {
    return <div className="patient-shell"><div className="patient-empty">{t("patient.invalid_link")}</div></div>;
  }
  if (clinicQuery.isLoading) {
    return (
      <div className="patient-shell">
        {langToggle}
        <div className="patient-card"><SkeletonBlock count={4} /></div>
      </div>
    );
  }
  if (clinicQuery.error || !branding) {
    return (
      <div className="patient-shell">
        {langToggle}
        <div className="patient-card patient-error">
          <h2>{t("patient.clinic_not_found_title")}</h2>
          <p>{t("patient.clinic_not_found_body")}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="patient-shell">
      {langToggle}
      {step === "landing" && (
        <ErrorBoundary scope="Patient landing">
          <PatientLanding clinic={branding} onStart={() => setStep("consent")} />
        </ErrorBoundary>
      )}

      {step === "consent" && (
        <ErrorBoundary scope="Patient consent">
          <PatientConsentModal
            clinic={branding}
            onAccepted={onConsentGranted}
            onCancel={() => setStep("landing")}
            bootstrapping={bootstrapping}
            bootstrapError={bootstrapError}
          />
        </ErrorBoundary>
      )}

      {step === "chat" && session.session_token && session.conversation_id && (
        <ErrorBoundary scope="Patient chat">
          <PatientChatRoom
            clinic={branding}
            sessionToken={session.session_token}
            conversationId={session.conversation_id}
            initialWelcome={initialWelcome}
            onAppointmentConfirmed={onAppointmentConfirmed}
            onStartOver={onStartOver}
          />
        </ErrorBoundary>
      )}

      {step === "confirm" && (
        <ErrorBoundary scope="Patient confirmation">
          <PatientConfirmation clinic={branding} onStartOver={onStartOver} />
        </ErrorBoundary>
      )}

      <footer className="patient-footer">
        <span>{branding.name}</span>
        {branding.public_address ? <span>· {branding.public_address}</span> : null}
        {branding.contact_phone ? <span>· {branding.contact_phone}</span> : null}
        <span>· {fill(t("patient.footer.disclosure"), { version: branding.disclosure.version })}</span>
      </footer>
    </div>
  );
}
