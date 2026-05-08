import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routes import ai, appointments, audit, auth, chat, clinical, enterprise, intelligence, quality, users, voice
from app.api.dependencies import get_db
from app.core.config import get_settings
from app.core.errors import error_response
from app.core.health import readiness_report
from app.core.observability import RequestContextMiddleware
from app.db.bootstrap import initialize_database
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

settings = get_settings()
settings.validate_runtime_safety()

if settings.jwt_secret in ("change-me-in-production", "replace-me", "secret"):
    logger.warning(
        "SECURITY WARNING: JWT_SECRET is set to a default/weak value. "
        "Set a strong random secret in production."
    )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database(settings)
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
app.include_router(intelligence.router, prefix=settings.api_prefix)
app.include_router(clinical.router, prefix=settings.api_prefix)
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
