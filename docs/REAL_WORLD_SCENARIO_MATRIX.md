# Real-World Scenario Matrix

These scenarios are covered by automated tests and represent the baseline that Cognivault must keep passing before any model, voice, or backend release.

## Covered Scenarios

| Scenario | User behavior | Expected result | Test |
| --- | --- | --- | --- |
| Noisy Turkish appointment booking | Customer writes `tekink destk`, `randevu alcam`, ASCII Turkish, and phone in one message | System detects Technical Support, collects purpose, offers slots, creates appointment | `test_noisy_turkish_appointment_flow_completes_offline` |
| ASCII Turkish language stability | Customer continues with `VPN baglantim... cozulmeli` after a Turkish opening | Assistant stays in Turkish instead of switching to English | `test_noisy_turkish_appointment_flow_completes_offline` |
| Typo-tolerant local NLU | Misspellings like `calismio`, `ftrmda`, `tekink destk` | Local parser maps to the correct department/date | `test_real_world_text_understanding_handles_typos_and_ascii_turkish` |
| Enterprise urgent escalation | Caller says internet/VPN is down and asks for a human | Ticket is escalated to Technical Support with high priority | `test_enterprise_escalates_noisy_connectivity_complaint` |
| Local STT | Backend is configured with a local Whisper.cpp-compatible binary | `/api/voice/transcribe` returns text and provider `whisper_cpp` | `test_local_voice_providers_are_exercised_through_api` |
| Local TTS | Backend is configured with a local Piper-compatible binary | `/api/voice/synthesize` streams WAV audio and provider `piper` | `test_local_voice_providers_are_exercised_through_api` |
| Local LLM serving | `LOCAL_LLM_BASE_URL` is configured | Runtime selects the local OpenAI-compatible model | `test_local_llm_runtime_is_selected_when_configured` |
| Offline streaming fallback | No OpenAI/local LLM is configured | SSE chat still responds through the guided workflow engine | `test_streaming_chat_uses_local_fallback_without_llm_runtime` |

## Release Rule

Before changing prompts, model providers, voice providers, routing rules, or appointment logic:

```bash
backend/venv/bin/python -m pytest backend/tests -q
cd frontend && npm run build
```

Both must pass. If a model improves one scenario but breaks another, the backend fallback and routing rules need to be adjusted before release.
