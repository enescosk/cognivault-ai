from datetime import datetime, timedelta, timezone
import hashlib

import jwt

from app.core.config import get_settings


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, hashed_password: str) -> bool:
    return hash_password(password) == hashed_password


def create_access_token(subject: str, *, organization_id: int | None = None) -> str:
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload: dict[str, object] = {"sub": subject, "exp": expires_at}
    if organization_id is not None:
        payload["org_id"] = organization_id
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
