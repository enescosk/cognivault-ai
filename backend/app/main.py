import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routes import agents, appointments, audit, auth, billing, chat, clinical, enterprise, intelligence, users, voice
from app.core.config import get_settings
from app.core.observability import (
    MetricsTimer,
    configure_logging,
    http_requests_total,
    render_metrics,
)
from app.core.rate_limit import limiter
from app.db.schema import ensure_schema_up_to_date
from app.db.session import SessionLocal
from app.seed.data import seed_database
from app.services.agents import bootstrap_agent_registry

configure_logging()
logger = logging.getLogger(__name__)

settings = get_settings()

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
    # Şema kurulumu — sadece dev'de Alembic head'e taşır.
    # Production'da deploy pipeline `alembic upgrade head`'i kendisi koşar;
    # uygulama startup'ı DB şemasına dokunmaz.
    ensure_schema_up_to_date()
    # Production guard — demo kullanıcıları (ayse, admin@…) prod'da YARATILMAMALI.
    # SEED_DEMO_DATA=true bile olsa, ENVIRONMENT=production ise atla + uyarı logla.
    if settings.seed_demo_data and settings.is_production:
        logger.warning(
            "SECURITY: SEED_DEMO_DATA=true but ENVIRONMENT=%r — demo users + sample "
            "data will NOT be created. Disable SEED_DEMO_DATA in prod env.",
            settings.environment,
        )
    elif settings.seed_demo_data:
        db = SessionLocal()
        try:
            seed_database(db)
        finally:
            db.close()
    bootstrap_agent_registry()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
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


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(status_code=404, content={"error": "Not found", "detail": str(exc.detail)})


@app.exception_handler(403)
async def forbidden_handler(request: Request, exc):
    return JSONResponse(status_code=403, content={"error": "Forbidden", "detail": str(exc.detail)})


@app.exception_handler(401)
async def unauthorized_handler(request: Request, exc):
    return JSONResponse(status_code=401, content={"error": "Unauthorized", "detail": str(exc.detail)})

app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(users.router, prefix=settings.api_prefix)
app.include_router(chat.router, prefix=settings.api_prefix)
app.include_router(appointments.router, prefix=settings.api_prefix)
app.include_router(audit.router, prefix=settings.api_prefix)
app.include_router(voice.router, prefix=settings.api_prefix)
app.include_router(enterprise.router, prefix=settings.api_prefix)
app.include_router(intelligence.router, prefix=settings.api_prefix)
app.include_router(clinical.router, prefix=settings.api_prefix)
app.include_router(agents.router, prefix=settings.api_prefix)
app.include_router(billing.router, prefix=settings.api_prefix)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/healthz")
def liveness_probe() -> dict[str, str]:
    """Kubernetes-style liveness probe — only fails if the process is broken."""

    return {"status": "ok"}


@app.get("/readyz")
def readiness_probe() -> JSONResponse:
    """Readiness probe — verifies the database is reachable.

    Returns 200 with the dependency status JSON when everything is up; 503 if
    the DB check fails. Useful for load-balancer or k8s readiness gating.
    """

    checks: dict[str, str] = {}
    overall_ok = True
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        overall_ok = False
        checks["database"] = f"failed: {exc.__class__.__name__}"
        logger.error("readyz database check failed", extra={"error": str(exc)})
    finally:
        db.close()

    body = {"status": "ok" if overall_ok else "degraded", "checks": checks}
    return JSONResponse(content=body, status_code=200 if overall_ok else 503)


@app.get("/metrics")
def prometheus_metrics() -> Response:
    """Prometheus scrape endpoint. No auth (standard for /metrics) — scope it to
    the metrics network or behind an ingress allowlist in production."""

    body, content_type = render_metrics()
    return Response(content=body, media_type=content_type)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "status": "ok",
        "health": "/health",
        "api_prefix": settings.api_prefix,
        "frontend_hint": "Open http://localhost:5173 for the web app.",
    }
