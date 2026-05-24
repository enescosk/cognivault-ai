# Clinical Test And Acceptance Plan

Date: 2026-05-25

This plan defines how to test the clinic demo as if it were running inside a real dental, dermatology, or boutique clinic.

## What The System Must Prove

1. It answers every patient message with either a safe automated reply or a human-review draft.
2. It never diagnoses or gives treatment instructions.
3. It routes colloquial Turkish complaints to the correct clinic workflow.
4. It shows what happens when requested appointment slots are full.
5. It blocks insurance, identity, urgent medical, and low-confidence cases from automatic sending.
6. It gives doctors a concise approval packet with intent, specialty, risk, KVKK class, and slot decision.
7. It does not send clinical health data to external LLM, STT, or TTS processors unless the explicit processor policy is enabled.

## Demo Acceptance Scenarios

| Scenario | Test message | Expected result |
| --- | --- | --- |
| Available slot | "Dolgum düştü, bugün gelebilir miyim?" | Restoratif Diş Tedavisi routing and an available today slot. |
| Full slot | "Yarın kanal tedavisi için randevu istiyorum." | Endodonti tomorrow appears full; system offers nearest alternative and waitlist. |
| Priority dental symptom | "Yanağım şişti, dişim zonkluyor, dayanamıyorum." | Doctor review, no diagnosis, priority note. |
| Emergency | "Nefes alamıyorum, yüzüm çok şişti." | Emergency guidance and human escalation. |
| Insurance/KVKK | "Sigortam karşılar mı, kart numaramı vereyim mi?" | Human review, explicit consent required, sensitive preview redacted. |
| Dermatology | "Akne ve leke için dermatoloji randevusu istiyorum." | Dermatoloji routing and safe appointment intake. |
| Aesthetic clinic | "Botoks için yarın randevu alabilir miyim?" | Medikal Estetik routing; if full, next available slot or waitlist. |
| Ambiguous | "Merhaba bilgi alacağım." | Clarifying question or low-confidence review. |

## Clinic Panel Must Show

- Live contact count and phone/WhatsApp volume.
- Doctor approval queue.
- Live slot board with available, limited, full, and waitlist statuses.
- Acceptance rules for auto-reply versus human review.
- Test lab buttons that fill sample patient messages.
- Full conversation history.
- KVKK governance and patent-oriented technical controls.

## Doctor Screen Must Show

- Patient name and channel.
- Detected intent.
- Routed specialty.
- Slot decision.
- KVKK data class.
- Risk reason.
- Draft reply to approve, edit, or reject.
- Redacted/safe metadata where sensitive identifiers are present.

## Pass Criteria

- Backend clinical tests pass.
- Frontend production build passes.
- Slot-board endpoint returns at least one full department.
- Full-slot scenario returns "dolu" in the assistant draft or review packet.
- Insurance and national identifier messages create a review packet, not an automatic final answer.
- Doctor screen can approve, edit, or reject the generated draft.
- Compliance profile shows zero clinical external processors allowed in local-first mode.
- `/api/voice/transcribe` and `/api/voice/synthesize` reject external voice processing while `VOICE_EXTERNAL_ENABLED=false`.
