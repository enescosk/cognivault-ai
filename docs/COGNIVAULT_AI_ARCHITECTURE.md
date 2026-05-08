# Cognivault Local-First AI Architecture

This is the target architecture for making Cognivault independent from third-party AI APIs while keeping the product reliable during the transition.

## North Star

Cognivault should treat every model as an internal capability, not as a hard-coded vendor dependency.

The backend owns the contract:

- Chat reasoning: OpenAI-compatible chat completions with tool calling
- Speech-to-text: local Whisper-compatible transcription
- Text-to-speech: local neural TTS
- Business execution: auditable backend tools, never model-side side effects
- Safety: deterministic fallback and human handoff when model confidence is low

## Runtime Layers

1. **API Layer**
   - FastAPI routes expose stable product endpoints.
   - Frontend never needs to know whether a local model, OpenAI, or a fallback engine answered.

2. **AI Runtime Layer**
   - `backend/app/ai/runtime.py` selects the active LLM runtime.
   - Local models are expected to expose an OpenAI-compatible endpoint through vLLM, llama.cpp server, TGI, Ollama-compatible gateways, or an internal gateway.
   - If no LLM runtime is configured, Cognivault still runs the guided local workflow engine.

3. **Voice Runtime Layer**
   - `backend/app/services/voice_ai_service.py` selects STT/TTS providers.
   - Local STT target: Whisper.cpp with a Turkish/English capable model.
   - Local TTS target: Piper voice model first; later a trained brand voice model can sit behind the same contract.

4. **Agent and Tool Layer**
   - The agent can call backend tools for slots, appointments, profile reads, and profile updates.
   - Models only propose actions; backend tools enforce permissions and write data.
   - This keeps the system safe even when models are replaced.

5. **Domain Intelligence Layer**
   - Rule-based parsing remains as a deterministic floor.
   - Local LLM/NLU models can improve language understanding without removing the fallback.
   - Clinical/enterprise flows should store confidence, extracted entities, and handoff packages for operator review.

## Model Factory Roadmap

### Phase 1: Local Serving

- Run a local OpenAI-compatible LLM server.
- Configure:

```env
PREFERRED_LLM_PROVIDER=local
LOCAL_LLM_BASE_URL=http://localhost:8080/v1
LOCAL_LLM_API_KEY=local
LOCAL_LLM_MODEL=your-local-model
```

- Validate with `GET /api/ai/capabilities`.

### Phase 2: Local Speech

- Build or install Whisper.cpp.
- Download a production-appropriate Whisper model.
- Install Piper and a Turkish/English voice model.
- Configure:

```env
SPEECH_STT_PROVIDER=local
WHISPER_CPP_BINARY=/absolute/path/to/whisper-cli
WHISPER_CPP_MODEL=/absolute/path/to/ggml-model.bin
SPEECH_TTS_PROVIDER=local
PIPER_BINARY=/absolute/path/to/piper
PIPER_VOICE_MODEL=/absolute/path/to/voice.onnx
```

### Phase 3: Cognivault NLU Dataset

Create an internal dataset from consented, redacted conversations:

- Intent labels: appointment booking, billing issue, technical issue, compliance, escalation, smalltalk, unknown
- Entities: department, date, time, phone, branch, urgency, customer sentiment
- Channel metadata: web chat, WhatsApp, phone, manual
- Outcome: completed, needs input, escalated, refused

Use this dataset for:

- Turkish noisy-text normalization
- Intent/entity classifier
- Reranker for tool selection
- Voice transcription correction
- Evaluation suites before each model release

### Phase 4: Private Fine-Tunes

Train internal adapters rather than replacing the whole platform at once:

- ASR correction model for customer calls
- Intent/entity extraction model
- Tool-calling policy model
- Clinic/enterprise persona adapters
- TTS brand voice model, only with licensed voice data and explicit consent

### Phase 5: Production Hardening

- Model registry with versioned artifacts
- Canary releases per tenant or clinic
- Golden conversation tests
- Audio WER tests for Turkish and English
- Tool-call accuracy tests
- Audit trails for model version, provider, confidence, and fallback reason
- Human handoff queue for low-confidence cases

## Backend Invariants

- No product route should import a vendor SDK directly unless it is inside a provider adapter.
- Every model response that can change state must go through a backend tool.
- Every customer-facing automated decision should have a fallback path.
- Every voice or LLM provider should be replaceable through environment config.
- Offline demo mode must keep working without API keys.

## Current Implementation

- `/api/ai/capabilities` reports active LLM and voice providers.
- `/api/voice/transcribe` supports Whisper.cpp first and OpenAI fallback.
- `/api/voice/synthesize` supports Piper first and OpenAI fallback.
- Chat agent can use a local OpenAI-compatible LLM runtime through `LOCAL_LLM_BASE_URL`.
- Existing guided workflow engine remains the zero-API reliability floor.
