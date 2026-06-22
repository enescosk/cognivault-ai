from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any

from fastapi import Request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware


logger = logging.getLogger("cognivault.request")

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def current_request_id() -> str | None:
    return request_id_ctx.get()


# ─────────────────────────────────────────────────────────────────────────────
# Prometheus metric kayıtları (varsayılan global registry).
# Etiket sırası, çağıran kodun pozisyonel .labels(...) kullanımıyla eşleşmelidir.
# ─────────────────────────────────────────────────────────────────────────────

http_requests_total = Counter(
    "http_requests_total",
    "Toplam HTTP istek sayısı (method/route/status bazında).",
    ["method", "route", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP istek süresi (saniye), method/route bazında.",
    ["method", "route"],
)

agent_decisions_total = Counter(
    "agent_decisions_total",
    "Kaydedilen agent kararları (agent_type/risk/requires_human bazında).",
    ["agent_type", "risk", "requires_human"],
)

webhook_inbound_total = Counter(
    "webhook_inbound_total",
    "Gelen webhook olayları (provider/outcome bazında).",
    ["provider", "outcome"],
)


class MetricsTimer:
    """HTTP isteği için süre + sayım kaydeden bağlam yöneticisi.

    Kullanım:
        timer = MetricsTimer(method, route)
        with timer:
            response = await call_next(request)
            timer.status = str(response.status_code)

    Çıkışta süreyi histograma yazar ve http_requests_total sayacını artırır.
    `status` ayarlanmazsa hata kabul edilip "500" sayılır.
    """

    def __init__(self, method: str, route: str) -> None:
        self.method = method
        self.route = route
        self.status = "500"
        self._start = 0.0

    def __enter__(self) -> "MetricsTimer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        elapsed = time.perf_counter() - self._start
        http_request_duration_seconds.labels(self.method, self.route).observe(elapsed)
        http_requests_total.labels(self.method, self.route, self.status).inc()
        return False


def render_metrics() -> tuple[bytes, str]:
    """Prometheus exposition formatında (gövde, content-type) döner."""
    return generate_latest(), CONTENT_TYPE_LATEST


# ─────────────────────────────────────────────────────────────────────────────
# Yapılandırılmış JSON loglama.
# ─────────────────────────────────────────────────────────────────────────────

# LogRecord'un standart alanları — extra olarak eklenen alanları ayırt etmek için.
_RESERVED_LOG_KEYS: frozenset[str] = frozenset(
    vars(logging.makeLogRecord({})).keys()
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Log kayıtlarını tek satır JSON'a çevirir; extra alanları korur.

    Standart alanlar: level (küçük harf), logger, message. Kayda eklenen
    ek alanlar (request_id, organization_id, vb.) düz biçimde aktarılır.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }

        rid = current_request_id()
        if rid is not None:
            payload["request_id"] = rid

        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_KEYS or key.startswith("_"):
                continue
            payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    """Kök logger'ı stdout'a JSON formatıyla yayın yapacak şekilde ayarlar."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-ms"] = str(duration_ms)
        logger.info(
            "request_completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
