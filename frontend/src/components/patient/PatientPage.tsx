import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import {
  clearPatientSession,
  getPublicClinic,
  loadPatientSession,
  savePatientSession,
  type PatientSessionState,
  type PublicClinicView,
} from "../../api/patientClient";
import { ErrorBoundary } from "../ErrorBoundary";
import { SkeletonBlock } from "../ui/Skeleton";
import { PatientChatRoom } from "./PatientChatRoom";
import { PatientConfirmation } from "./PatientConfirmation";
import { PatientConsentModal } from "./PatientConsentModal";
import { PatientLanding } from "./PatientLanding";
import { PatientOnboardingForm } from "./PatientOnboardingForm";

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

type Step = "landing" | "consent" | "onboarding" | "chat" | "confirm";

export function PatientPage() {
  const params = useParams<{ slug: string }>();
  const slug = (params.slug ?? "").trim();

  const [step, setStep] = useState<Step>("landing");
  const [session, setSession] = useState<PatientSessionState>(() => {
    if (!slug) return { slug: "" };
    return loadPatientSession(slug) ?? { slug };
  });

  // Returning sessions: hangi adımda devam etsin?
  useEffect(() => {
    if (!slug) return;
    if (session.session_token && session.conversation_id) {
      setStep("chat");
    } else if (session.consent_token) {
      setStep("onboarding");
    }
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

  const onConsentGranted = (consentToken: string, disclosureVersion: string) => {
    setSession((s) => ({
      ...s,
      consent_token: consentToken,
      disclosure_version: disclosureVersion,
      consent_expires_at: Date.now() + 15 * 60_000,
    }));
    setStep("onboarding");
  };

  const onConversationStarted = (data: {
    session_token: string;
    conversation_id: number;
    patient_id: number;
  }) => {
    setSession((s) => ({
      ...s,
      session_token: data.session_token,
      conversation_id: data.conversation_id,
      patient_id: data.patient_id,
      session_expires_at: Date.now() + 60 * 60_000,
    }));
    setStep("chat");
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
          />
        </ErrorBoundary>
      )}

      {step === "onboarding" && session.consent_token && (
        <ErrorBoundary scope="Patient onboarding">
          <PatientOnboardingForm
            clinic={branding}
            consentToken={session.consent_token}
            onStarted={onConversationStarted}
            onCancel={() => {
              clearPatientSession();
              setSession({ slug });
              setStep("landing");
            }}
          />
        </ErrorBoundary>
      )}

      {step === "chat" && session.session_token && session.conversation_id && (
        <ErrorBoundary scope="Patient chat">
          <PatientChatRoom
            clinic={branding}
            sessionToken={session.session_token}
            conversationId={session.conversation_id}
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
