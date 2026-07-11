# CogniVault Voice QA Runbook

Status: Pilot gate  
Date: 2026-07-08  
Scope: Public patient page voice call flow

## Purpose

This runbook proves whether a real patient can complete a voice-led appointment flow under realistic mobile conditions. A pilot cannot start until the required scenarios are run and blocking failures are triaged.

## Test URL

- Local web: `http://127.0.0.1:5185/c/demo-klinik`
- Phone/LAN: use `./scripts/run_mobile_phone.sh` or expose frontend/backend on the same Wi-Fi.

## Preconditions

- Backend health: `GET /health` returns `{"status":"ok"}`.
- Frontend build passes: `cd frontend && npm run build`.
- Backend suite passes or has a documented exception.
- Clinic has at least one available public slot.
- Consent flow is tested in both local voice mode and premium voice mode if premium credentials are configured.

## Required Devices

| Device | Browser | Required |
|---|---|---|
| iPhone | Safari | Yes |
| iPhone | Chrome | Yes |
| Android | Chrome | Yes |
| Desktop | Chrome | Optional baseline |

## Required Audio Conditions

| Condition | Required |
|---|---|
| Quiet room | Yes |
| Reception noise | Yes |
| Speaker mode | Yes |
| Wired or Bluetooth headset | Yes |
| Fast speech | Yes |
| Long pause before answer | Yes |
| Wrong phone number then correction | Yes |

## Core Scenario Script

Use the same scenario text across devices where possible.

1. Open patient page.
2. Accept KVKK disclosure.
3. If testing premium mode, accept cross-border and voice processing options.
4. Start voice call.
5. Pick Turkish.
6. Say: `Diş ağrım var, yarın randevu almak istiyorum.`
7. Say a full name.
8. Say a Turkish mobile number.
9. Pick the first available appointment.
10. Confirm that appointment result appears.

## Edge Scenario Script

1. Start voice call.
2. Pause silently for at least 3 seconds before speaking.
3. Say: `Dolgum düştü ama cuma öğleden sonra gelebilirim.`
4. When phone is requested, say an invalid number first.
5. Correct it with a valid `5XX XXX XX XX` number.
6. Pick a listed slot by ordinal: `İkinci saat olsun.`

## Emergency Safety Script

1. Start voice call.
2. Say: `Yüzüm şişti ve nefes almakta zorlanıyorum.`
3. Expected result: emergency banner, 112 guidance, no normal booking completion.

## Measurement Sheet

Copy one row per run.

| Run ID | Date | Tester | Device | Browser | Audio condition | Voice mode | Mic permission seconds | First assistant audio seconds | Transcript correct? | Transcript shown? | Retry count | Completed under 60s? | Appointment created? | Operator intervention? | Notes |
|---|---|---|---|---|---|---|---:|---:|---|---|---:|---|---|---|---|
| VQA-001 |  |  | iPhone | Safari | Quiet | Local |  |  |  |  |  |  |  |  |  |

## Pass/Fail Rules

Blocking:
- Emergency scenario does not show 112 guidance.
- Audio is sent to external provider without clinic permission and patient voice consent.
- Appointment is created with wrong phone/name after an obvious correction.
- Browser gets stuck listening or thinking for more than 20 seconds.
- Patient cannot end the call.

Major:
- Transcript is wrong in more than 2 of 10 normal runs.
- Retry rate is above 20%.
- Under-60-second completion is below 50%.
- Premium mode falls back to robotic/local voice without a visible diagnostic.

Minor:
- Transcript is correct but punctuation/casing is poor.
- Provider/debug chip is missing in operator view.
- Text wraps awkwardly on one viewport but remains usable.

## Pilot Gate

Pilot can start only when:
- All blocking issues are closed.
- At least 12 device/audio matrix runs are recorded.
- Emergency safety script passes on iPhone Safari and Android Chrome.
- Normal scenario booking success is at least 70%.
- Under-60-second booking success is at least 50%.
- Operator intervention rate is at most 25%.

## Issue Template

Use this format for every failed run.

```text
ID:
Severity: Blocking | Major | Minor
Device/browser:
Audio condition:
Voice mode:
Steps:
Expected:
Actual:
Transcript shown:
Provider:
Retry count:
Screenshots/logs:
Owner:
Status:
```

