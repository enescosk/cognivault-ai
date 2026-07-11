import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routes import (
    agents,
    ai,
    appointments,
    audit,
    auth,
    billing,
    chat,
    clinic_admin,
    clinical,
    enterprise,
    intelligence,
    knowledge,
    public,
    quality,
    users,
    voice,
)
from app.api.dependencies import get_db
from app.core.config import get_settings
from app.core.errors import error_response
from app.core.exceptions import DomainError
from app.core.health import readiness_report
from app.core.observability import (
    MetricsTimer,
    RequestContextMiddleware,
    configure_logging,
    http_requests_total,
    render_metrics,
)
from app.core.rate_limit import limiter
from app.ai.voice_factory import warm_up_local_voice_stack
from app.db.bootstrap import initialize_database
from fastapi import Response
from sqlalchemy.orm import Session

configure_logging()
logger = logging.getLogger(__name__)

settings = get_settings()
settings.validate_runtime_safety()

# Production fail-fast: JWT_SECRET zayıfsa uygulamayı başlatma.
# Mesaj, operatöre nasıl güçlü secret üreteceğini anlatır.
_jwt_error = settings.jwt_secret_validation_error()
if _jwt_error is not None:
    raise RuntimeError(
        f"Refusing to start in {settings.environment!r}: {_jwt_error}"
    )
if settings.has_weak_jwt_secret:
    logger.warning(
        "SECURITY WARNING: JWT_SECRET is weak for production. "
        "Generate a strong one: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
    )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attaches an `X-Request-ID` header to every response and exposes it on `request.state`.

    The client may pass its own ID to correlate logs across services; otherwise a UUID4 is
    generated. Useful for audit trails and agent decision logging.
    """

    HEADER = "X-Request-ID"

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(self.HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[self.HEADER] = request_id
        return response


class MetricsMiddleware(BaseHTTPMiddleware):
    """Records HTTP latency + counts per (method, route, status).

    Uses `request.scope["route"].path` when FastAPI resolves a matching route, so
    `/api/users/42` is bucketed as `/api/users/{user_id}` instead of producing a
    new label per ID — keeps cardinality under control.

    Side-effect: her tamamlanmış request için JSON log satırı düşer (method,
    path, status, duration_ms, request_id). Bu satır admin-side log query'leri
    için temel kayıt.
    """

    async def dispatch(self, request: Request, call_next):
        import time as _time
        route_obj = request.scope.get("route")
        route_path = getattr(route_obj, "path", request.url.path)
        timer = MetricsTimer(request.method, route_path)
        started = _time.perf_counter()
        status_code = "500"
        try:
            with timer:
                response = await call_next(request)
                timer.status = str(response.status_code)
                status_code = str(response.status_code)
                return response
        except Exception:
            timer.status = "500"
            http_requests_total.labels(request.method, route_path, "500").inc()
            raise
        finally:
            duration_ms = round((_time.perf_counter() - started) * 1000.0, 2)
            logger.info(
                "http.request",
                extra={
                    "method": request.method,
                    "path": route_path,
                    "status": status_code,
                    "duration_ms": duration_ms,
                    "request_id": getattr(request.state, "request_id", None),
                },
            )


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database(settings)
    # Lokal STT/TTS modellerini arka planda ısıt — ilk sesli turda
    # model-yükleme takılması yaşanmasın (hata yükseltmez, thread'de koşar).
    warm_up_local_voice_stack()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    # Whitelist — wildcard "*" yerine sadece kullanılan HTTP verb'leri.
    # Yeni verb gerekirse buraya ekle; eklemeden frontend'den çağrılan
    # OPTIONS preflight'lar 403 alır.
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    # Frontend'in gerçekten gönderdiği header'lar — wildcard yerine açık liste.
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    # Response'da frontend'in okuyabilmesi gereken header'lar (request-id korelasyonu)
    expose_headers=["X-Request-ID"],
    # Preflight cache — 1 saat. Browser CORS preflight'larını az gönderir.
    max_age=3600,
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    message = str(exc.detail) if exc.detail else "Request failed"
    code = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        429: "rate_limited",
        503: "service_unavailable",
    }.get(exc.status_code, "http_error")
    return error_response(request, status_code=exc.status_code, code=code, message=message)


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError):
    code = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        502: "upstream_error",
    }.get(exc.http_status, "domain_error")
    return error_response(
        request,
        status_code=exc.http_status,
        code=code,
        message=exc.message,
        detail=exc.details or None,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return error_response(
        request,
        status_code=422,
        code="validation_error",
        message="Request validation failed",
        detail=exc.errors(),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled_exception", extra={"path": request.url.path})
    return error_response(
        request,
        status_code=500,
        code="internal_error",
        message="Unexpected backend error",
    )

app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(ai.router, prefix=settings.api_prefix)
app.include_router(users.router, prefix=settings.api_prefix)
app.include_router(chat.router, prefix=settings.api_prefix)
app.include_router(appointments.router, prefix=settings.api_prefix)
app.include_router(audit.router, prefix=settings.api_prefix)
app.include_router(voice.router, prefix=settings.api_prefix)
app.include_router(enterprise.router, prefix=settings.api_prefix)
app.include_router(knowledge.router, prefix=settings.api_prefix)
app.include_router(clinical.router, prefix=settings.api_prefix)
app.include_router(clinic_admin.router, prefix=settings.api_prefix)
app.include_router(public.router, prefix=settings.api_prefix)
app.include_router(intelligence.router, prefix=settings.api_prefix)
app.include_router(agents.router, prefix=settings.api_prefix)
app.include_router(billing.router, prefix=settings.api_prefix)
app.include_router(quality.router, prefix=settings.api_prefix)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def readiness(db: Session = Depends(get_db)) -> dict:
    return readiness_report(db)


@app.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
def readyz(db: Session = Depends(get_db)) -> dict:
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
        status = "ok"
    except Exception:  # noqa: BLE001
        database = "fail"
        status = "fail"
    return {"status": status, "checks": {"database": database}}


@app.get("/metrics")
def metrics() -> Response:
    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "status": "ok",
        "health": "/health",
        "readiness": "/health/ready",
        "api_prefix": settings.api_prefix,
        "frontend_hint": "Open http://127.0.0.1:5200 for the web app.",
    }
