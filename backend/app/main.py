import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routes import appointments, audit, auth, chat, enterprise, intelligence, users, voice
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.seed.data import seed_database

logger = logging.getLogger(__name__)

settings = get_settings()

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
    Base.metadata.create_all(bind=engine)
    if settings.seed_demo_data:
        db = SessionLocal()
        try:
            seed_database(db)
        finally:
            db.close()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "status": "ok",
        "health": "/health",
        "api_prefix": settings.api_prefix,
        "frontend_hint": "Open http://localhost:5173 for the web app.",
    }
