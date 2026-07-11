# CogniVault Top-Tier Roadmap

Status: Active engineering roadmap  
Date: 2026-07-08  
Owner: Product + Engineering  
Principle: Every pilot-facing feature must be measurable, consent-safe, and reversible.

## North Star

CogniVault must let a real patient book a clinic appointment in under 60 seconds with a voice or chat experience that feels trustworthy, not robotic, while keeping KVKK/local-first controls explicit and testable.

## Quality Bar

- No hidden data transfer: every external AI/STT/TTS route needs app flag, clinic permission, patient consent, and credentials.
- No silent schema drift: Alembic head must create every ORM table and column.
- No "it feels better" claims without telemetry: latency, transcript, retry count, and booking result must be recorded.
- No patient dead ends: every AI failure needs a clear operator or phone fallback.
- No pilot without acceptance criteria: device QA and KPI dashboard must exist before live clinic use.

## Phase 0 - Stabilize The Foundation

Done:
- Migration-first local bootstrap and schema drift detection.
- `0010_clinical_appointment_doctor_slot` migration for appointment doctor/slot columns.
- Alembic/ORM table+column parity test.
- Full backend suite passing after migration graph update.

Remaining:
- Keep migration graph/preflight artifact updated with every migration.
- Add a short release checklist before each pilot build.

Acceptance:
- `backend/.venv/bin/python -m pytest -q` passes.
- `frontend npm run build` passes.
- `/health/ready` is green except explicitly documented optional provider warnings.

## Phase 1 - Voice Trust Loop

Goal: The patient and operator can see what the AI heard, why it responded, and where voice failures happened.

Work:
- Done: Patient "Duydugum" surface after every STT result.
- Done: Backend returns transcript metadata: provider, confidence when available, language, byte size, audio duration, and processing latency.
- Done: Message payload stores voice metadata in conversation/message metadata.
- Done: Operator view shows transcript/debug metadata for voice-origin messages.
- Done: Count no-result retries and STT failures per conversation as first-class event counters.

Acceptance:
- A user can correct a misheard transcript without losing context.
- A QA tester can answer: provider used, transcript text, retry count, and whether booking completed.
- Tests cover consent-safe provider selection and metadata propagation.

## Phase 2 - Premium Natural Voice

Goal: Make the first 5 seconds sound like a premium clinic assistant, while consent remains explicit.

Provider order:
- Pilot wow mode: ElevenLabs TTS, optional ElevenLabs STT.
- Controlled fallback: OpenAI TTS/STT.
- KVKK local-first fallback: Piper + faster-whisper.

Work:
- Done: Add admin-visible voice capability panel.
- Done: Add env/provider validation diagnostics.
- Done: Add per-clinic voice settings and test button.
- Done: Add provider latency measurement for public STT.

Acceptance:
- Natural voice can be enabled per clinic only when clinic cross-border permission and patient voice consent are present.
- `/health/ready` explains missing provider setup clearly.
- Pilot clinic can switch back to local mode without code deploy.

## Phase 3 - Real Device QA

Goal: Validate voice under actual patient conditions.

Matrix:
- iPhone Safari, iPhone Chrome.
- Android Chrome.
- Wired/Bluetooth headset.
- Speaker mode.
- Quiet room.
- Reception noise.
- Fast speech, pauses, correction, wrong phone number.

Metrics:
- Time to microphone permission.
- Time to first assistant audio.
- STT correctness.
- Retry count.
- Completion under 60 seconds.
- Appointment created.
- Operator intervention required.

Acceptance:
- Done: Real-device QA run records can be entered from the clinical operations panel.
- Done: Pilot dashboard reads real-device QA count and blocking/major failure status.
- QA runbook filled for at least 12 scenarios.
- High-risk failures produce tickets with reproduction steps.
- No pilot starts if emergency handling or booking confirmation regresses.

## Phase 4 - Pilot KPI Dashboard

Goal: Clinic owner sees whether the AI is actually helping.

KPIs:
- Booking success rate.
- Under-60-second booking rate.
- STT retry rate.
- No-result rate.
- Operator intervention rate.
- Emergency safety incidents.
- Drop-off step.

Initial targets:
- Booking success >= 70%.
- Under-60-second booking >= 50%.
- STT retry rate <= 20%.
- Operator intervention <= 25%.
- Emergency safety incident = 0.
- Real-device QA runs >= 12 with no blocking/major failures.

Acceptance:
- Done: Dashboard/card is visible in operator or clinic admin panel.
- Done: Core voice metrics are computed from real event metadata; real-device QA gate is computed from QA run records.
- Done: Pilot weekly report can be exported or copied.

## Phase 5 - Clinic Pilot Readiness

Goal: One clinic can use the system with real staff and controlled patient traffic.

Work:
- Pilot launch checklist.
- Staff onboarding script.
- Consent/legal review packet.
- Rollback plan.
- Daily health check.
- Incident response path.

Acceptance:
- Clinic staff can complete a test booking without engineering help.
- Every pilot issue has severity, owner, reproduction, and resolution status.
- Product can decide go/no-go from data after one week.

## Current Engineering Queue

1. Run and record 12 real-device QA scenarios on iPhone/Android.
2. Stabilize VerifiedCallTR git/test state in the separate workspace.
