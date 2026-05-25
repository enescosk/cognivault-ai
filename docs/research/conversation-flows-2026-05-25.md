# CogniVault Clinical Conversation Flow Research Synthesis

Date: 2026-05-25  
Scope: Turkey-focused private clinic intake, appointment automation, human handoff, and KVKK-aware dialogue management.  
Status: Working product synthesis. Legal statements must be verified by counsel before production rollout.

## Why This Exists

Gemini Deep Research and the Claude implementation pass converged on the same product direction: CogniVault Clinical must not behave like a generic chatbot. It needs a deterministic, audit-friendly clinical intake engine where the LLM understands the patient, but cannot invent availability, pricing, medical advice, or legal consent.

This document preserves the core findings so they do not remain only in chat history.

## Product Positioning

CogniVault Clinical is a premium multi-channel intake and dialogue-management platform for Turkey-based private clinics. Initial focus:

- Dental clinics
- Dermatology and aesthetic clinics
- Physiotherapy clinics
- Small private polyclinics and specialist practices

Primary channels:

- Voice calls over local VoIP or approved telephony providers
- WhatsApp, with explicit consent and channel-risk handling
- Web chat
- Clinic intake forms
- Operator and doctor panels

Core principle: patient experience should feel human, calm, and capable, while every risky operation remains tool-gated, logged, and reviewable.

## Canonical Intents And States

The research maps directly to the current backend enum surface.

Intents:

- `book_appointment`
- `reschedule_appointment`
- `cancel_appointment`
- `ask_price`
- `ask_insurance`
- `ask_location`
- `ask_working_hours`
- `medical_emergency`
- `general_question`
- `unknown`

Conversation statuses:

- `active`
- `waiting_human`
- `appointment_pending`
- `closed`

## Canonical Flows

### A1. New Patient Appointment By Phone

Goal: convert a first-time caller into a confirmed appointment without skipping KVKK disclosure.

Required flow:

1. Play short layered KVKK disclosure.
2. Capture explicit approval by voice or DTMF.
3. Detect appointment intent and treatment area.
4. Fetch real slots from calendar/HBYS.
5. Offer only returned slots.
6. Echo-confirm date, time, doctor, and phone number.
7. Create appointment in the source-of-truth system.
8. Send SMS/WhatsApp confirmation if allowed.

Hard guards:

- Never confirm a slot without `fetch_available_slots`.
- On unclear speech, use Turkish bridge phrases and echo confirmation.
- If the call drops, preserve state by phone number and resume within the recovery window.

### A2. Existing Patient Reschedule By WhatsApp

Goal: move an existing appointment while preserving the active appointment context.

Required flow:

1. Identify patient by phone.
2. Fetch active appointments.
3. If multiple appointments exist, ask which one.
4. Fetch alternative slots.
5. Confirm selected replacement.
6. Reschedule in HBYS.
7. Send updated details.

Hard guards:

- Do not cancel when the patient means reschedule.
- Handle multi-intent messages without losing the main reschedule task.
- If WhatsApp consent is not available, avoid health details and offer safer local channels.

### A3. Appointment Cancellation

Goal: respect cancellation while offering a low-friction reschedule path.

Required flow:

1. Detect cancellation intent.
2. Fetch active appointment.
3. Offer reschedule once, politely.
4. If the patient insists, cancel without friction.
5. Record cancellation reason.
6. Close with a clear confirmation.

Hard guards:

- Always ask for confirmation before destructive cancellation.
- Do not pressure patients during illness, distress, or emergency.

### A4. Price Question In Web Chat

Goal: answer within medical advertising and ethics boundaries, then convert to examination.

Required flow:

1. Detect price or comparison question.
2. Avoid exact treatment pricing where legal/ethical review says this is unsafe.
3. Explain that treatment plan and cost require examination.
4. Offer preliminary examination or consultation.
5. Fetch available slots only after interest is confirmed.

Hard guards:

- No discount, campaign, or comparative medical marketing claims without approved clinic policy and legal review.
- No invented prices.
- No direct diagnosis from symptoms.

### A5. Insurance, SGK, And Private Insurance

Goal: explain coverage boundaries without guaranteeing reimbursement.

Required flow:

1. Query approved insurance matrix.
2. Distinguish clinic agreement from policy-specific coverage.
3. If insurer is unknown, route to human review instead of saying no.
4. Offer appointment for proper diagnosis/provision flow.

Hard guards:

- No guaranteed reimbursement unless returned by an approved provision integration.
- No policy interpretation beyond approved knowledge base content.

### A6. Medical Emergency

Goal: bypass normal booking and trigger immediate safety guidance.

Triggers include examples such as severe bleeding, chest pain, breathing trouble, loss of consciousness, suicidal intent, major trauma, or rapidly worsening swelling.

Required flow:

1. Detect `medical_emergency` through keyword, model, and guardrail filters.
2. Immediately tell the patient to call 112 or go to the nearest emergency service.
3. Trigger clinic alarm for doctor/operator follow-up.
4. Set status to `waiting_human`.
5. Mute normal AI responses for the session.

Hard guards:

- No appointment-first flow in emergency mode.
- No diagnosis or medication instruction.
- No shadow-review delay before sending the emergency safety message.

### A7. Frustrated Or Angry Patient

Goal: de-escalate and transfer without creating a silent handoff.

Required flow:

1. Detect strong negative sentiment.
2. Acknowledge the patient’s frustration.
3. Transfer to the right queue.
4. Show patient a clear wait-time expectation.
5. Show operator a summarized context card.

Hard guards:

- Do not argue tone or etiquette with the patient.
- Do not say “transferring” unless an operator queue and alert are actually created.

### A8. Multi-Intent Confusion

Goal: answer stacked questions in a stable order.

Example: “Randevuyu erteleyelim, fiyatı da sorayım, Allianz geçiyor mu?”

Required flow:

1. Parse all intents.
2. Choose the primary operational intent.
3. Answer secondary administrative questions safely.
4. Return to the main unfinished appointment action.

Hard guards:

- Do not drop secondary questions silently.
- Do not let a price or insurance question derail an active reschedule.

## UI Decisions Already Reflected In The Frontend

The current `ConversationDetailPage` uses research-driven signals:

- Emergency banner for `medical_emergency`
- Silent handoff banner when status is `waiting_human`
- Sentiment trajectory from patient message metadata
- KVKK consent signal in patient panel
- Confidence threshold warnings by intent
- Hallucination risk warnings on message bubbles
- Multi-intent footer in message bubbles
- Related AI decision log panel for shadow-review context

Frontend metadata keys already supported:

- `kvkk_consent`
- `consent_status`
- `consent`
- `sentiment_score`
- `hallucination_risk`
- `intents`
- `confidence_score`
- `emergency_routed`

## Backend Signals Required Next

The UI is ready for these signals, but backend production of several fields is still the next implementation phase.

Required backend additions:

1. Add `sentiment_score` to patient message metadata.
2. Add `intents[]` for multi-intent messages.
3. Add `hallucination_risk` when assistant text mentions unavailable or unverified slots.
4. Add `emergency_routed` when 112 guidance is sent.
5. Add consent state to conversation or patient metadata.
6. Add confidence threshold checks before unsafe assistant output.
7. Add `waiting_human` transition logs for handoff.
8. Add slot cross-checking between assistant response and `fetch_available_slots` result.

## KVKK Product Rules

Implementation must follow these working product rules until counsel provides final language:

- Use data minimization by default.
- Do not ask for detailed health history on WhatsApp unless the channel/legal basis is approved.
- If a patient refuses WhatsApp or overseas-transfer consent, do not deny service; offer local voice or secure local web form.
- Record consent version, timestamp, channel, and evidence.
- Keep health-data processing local by default.
- Treat third-party AI APIs as high-risk until explicit consent, contracts, and transfer analysis are complete.

## Local AI Stack Decision

Target local stack:

- LLM: Qwen2.5-7B-Instruct or equivalent local model
- STT: faster-whisper large-v3-turbo
- TTS: Coqui XTTS-v2 or F5-TTS after license review
- VAD: silero-vad
- Serving: Turkey-based data center or on-premise deployment

The LLM should reason and draft, but deterministic services must own:

- calendar availability
- appointment creation
- cancellation
- consent recording
- emergency escalation
- insurance matrix lookup
- audit logging

## Evaluation Dataset Requirements

Golden dataset should include at least 100 Turkish examples across:

- new appointment
- reschedule
- cancellation
- price insistence
- insurance questions
- emergency symptoms
- angry patient
- elderly patient phrasing
- typo-heavy WhatsApp messages
- voice transcript artifacts
- multi-intent messages
- prompt injection attempts
- full-calendar scenarios
- consent refusal
- child or guardian consent
- out-of-hours transfer

Each example should define:

- expected intent
- expected status
- expected tool calls
- forbidden behavior
- expected assistant message
- whether shadow review is required
- accepted metadata signals

## Patent-Oriented Technical Themes

Potential patent dossier themes to explore with counsel:

- Consent-aware clinical dialogue state machine across WhatsApp, voice, and web chat.
- Tool-gated appointment reasoning that prevents hallucinated availability.
- Local-first health dialogue architecture with audit-token consent evidence.
- Emergency bypass pipeline that locks normal AI output and triggers multi-channel clinic alarms.
- Shadow-review feedback loop for doctor/operator correction of AI drafts.
- Multi-intent clinical intake ordering for Turkish patient language patterns.

## Acceptance Criteria For The Next Engineering Phase

The next backend phase is successful when:

- A full slot scenario shows “no available slots” without hallucinating alternatives.
- Emergency examples always route to 112 guidance and `waiting_human`.
- Price questions never return a forbidden exact treatment price unless explicitly allowed by approved clinic policy.
- Consent refusal does not block service but changes the channel flow.
- Operator handoff always creates visible patient and staff-side state.
- Conversation detail UI displays real backend metadata, not only optional placeholders.
- Backend eval tests cover at least the canonical flows above.

## Related Repo Files

- `frontend/src/components/ConversationDetailPage.tsx`
- `frontend/src/styles/global.css`
- `frontend/src/i18n/dict.ts`
- `docs/ai-stack-decision.md`
- `docs/gemini-deep-research-addendum.md`
- `docs/kvkk/`
- `docs/dental-ai-golden-research-findings.md`
- `docs/dental-ai-patent-dossier.md`
