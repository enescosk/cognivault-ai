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
      // Body'de field'ları null göndermek yerine atlıyoruz (omit). Yeni
      // backend zaten Optional kabul ediyor; eski backend versiyonu hâlâ
      // çalışıyorsa `null` yerine field hiç gelmediği için 422 atmıyor.
      const res = await startConversation(slug, consentToken, {});
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

  if (!slug) {
    return <div className="patient-shell"><div className="patient-empty">Geçersiz klinik bağlantısı.</div></div>;
  }
  if (clinicQuery.isLoading) {
    return (
      <div className="patient-shell">
        <div className="patient-card"><SkeletonBlock count={4} /></div>
      </div>
    );
  }
  if (clinicQuery.error || !branding) {
    return (
      <div className="patient-shell">
        <div className="patient-card patient-error">
          <h2>Klinik bulunamadı</h2>
          <p>Bağlantınız yanlış olabilir veya klinik artık aktif değildir.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="patient-shell">
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
        <span>· KVKK aydınlatma v{branding.disclosure.version}</span>
      </footer>
    </div>
  );
}
