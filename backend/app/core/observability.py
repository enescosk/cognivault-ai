"""Observability primitives: JSON logging, Prometheus metrics, health probes.

Kept dependency-light: structured logging uses stdlib, metrics use prometheus-client.
OpenTelemetry tracing is intentionally out of scope for this iteration — the
request_id middleware already gives us correlation IDs that can later be exported
as trace IDs without changing the application code.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)


class JsonFormatter(logging.Formatter):
    """Minimal JSON log formatter. Includes request_id when set on the LogRecord."""

    BUILTIN_ATTRS = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message",
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Surface arbitrary extras (e.g. logger.info("...", extra={"request_id": rid}))
        for key, value in record.__dict__.items():
            if key in self.BUILTIN_ATTRS or key.startswith("_"):
                continue
            payload[key] = value
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Idempotent JSON logging setup. Safe to call from `main` at import time."""

    root = logging.getLogger()
    # Avoid duplicate handlers when uvicorn reload re-imports the module.
    if any(getattr(h, "_cognivault_json", False) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler._cognivault_json = True  # type: ignore[attr-defined]
    root.handlers = [handler]
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


# --- Prometheus metrics ----------------------------------------------------

# Dedicated registry so tests can introspect without polluting the global one.
REGISTRY = CollectorRegistry()

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests handled by the app, by method, route, and status code.",
    ("method", "route", "status"),
    registry=REGISTRY,
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds, by method and route.",
    ("method", "route"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)

agent_decisions_total = Counter(
    "agent_decisions_total",
    "Agent decisions recorded by type, risk, and whether human review was required.",
    ("agent_type", "risk", "requires_human"),
    registry=REGISTRY,
)

webhook_inbound_total = Counter(
    "webhook_inbound_total",
    "Inbound provider webhooks received, by provider and outcome (accepted/duplicate/rejected).",
    ("provider", "outcome"),
    registry=REGISTRY,
)


def render_metrics() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


class MetricsTimer:
    """Tiny context manager used by HTTP middleware to record one request."""

    __slots__ = ("method", "route", "status", "_start")

    def __init__(self, method: str, route: str):
        self.method = method
        self.route = route
        self.status = "200"
        self._start = 0.0

    def __enter__(self) -> "MetricsTimer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        duration = time.perf_counter() - self._start
        http_request_duration_seconds.labels(self.method, self.route).observe(duration)
        http_requests_total.labels(self.method, self.route, self.status).inc()
