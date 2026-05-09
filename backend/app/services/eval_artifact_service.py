from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from app.core.config import PROJECT_ROOT, get_settings


@dataclass(frozen=True)
class EvalArtifact:
    generated_at: str
    suite: str
    total: int
    passed: int
    failed: int
    pass_rate: float
    p95_latency_ms: float | None
    source: str


def _coerce_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def load_latest_eval_artifact() -> EvalArtifact | None:
    path = Path(get_settings().quality_artifact_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    total = int(payload.get("total") or payload.get("total_scenarios") or 0)
    passed = int(payload.get("passed") or 0)
    failed = int(payload.get("failed") or max(0, total - passed))
    pass_rate = _coerce_float(payload.get("pass_rate"))
    if pass_rate is None:
        pass_rate = round((passed / total) * 100, 2) if total else 0.0
    if pass_rate <= 1 and total:
        pass_rate *= 100

    return EvalArtifact(
        generated_at=str(payload.get("generated_at") or datetime.now(timezone.utc).isoformat()),
        suite=str(payload.get("suite") or "local_quality_suite"),
        total=total,
        passed=passed,
        failed=failed,
        pass_rate=round(pass_rate, 2),
        p95_latency_ms=_coerce_float(payload.get("p95_latency_ms")),
        source=path.as_posix(),
    )
