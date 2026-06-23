# Backend Platform Standard

CogniVault backend is built around a small set of production invariants. Any new feature, LLM provider, voice provider, or clinical workflow should preserve these standards.

## Platform Invariants

- Every request has a correlation id through `X-Request-ID`.
- Every response includes request timing through `X-Process-Time-ms`.
- Every API error uses the same structured envelope.
- Readiness must expose database, security, LLM, and voice provider state.
- Model outputs never mutate state directly; they must call backend tools or services.
- Offline fallback must keep the core demo path alive even when no LLM API is configured.
- Real-world scenario tests are release gates, not optional demos.

## Error Contract

Errors return:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed",
    "request_id": "...",
    "path": "/api/..."
  }
}
```

Validation errors include a `detail` list. Internal errors do not leak implementation details to clients.

## Health Contract

- `/health` is the lightweight load balancer check.
- `/health/live` reports process liveness.
- `/health/ready` reports runtime readiness:
  - database connectivity
  - JWT/CORS security posture
  - active LLM provider and model
  - active STT/TTS providers

## LLM Contract

Local or cloud LLMs must sit behind the same OpenAI-compatible runtime contract:

- chat completions
- tool calling
- deterministic fallback when unavailable
- model/provider surfaced through `/api/ai/capabilities`

## Release Gate

Run this before shipping backend or model changes:

```bash
backend/venv/bin/python -m pytest backend/tests -q
cd frontend && npm run build
```

The backend test suite covers auth, RBAC, clinical flows, real-world scenarios, local voice providers, quality reporting, request observability, and readiness.
