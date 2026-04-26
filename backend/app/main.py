from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import appointments, audit, auth, chat, enterprise, intelligence, users, voice
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.seed.data import seed_database


settings = get_settings()


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
