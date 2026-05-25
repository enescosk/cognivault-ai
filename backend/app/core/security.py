"""Şifre hash'leme + JWT yardımcı modülü.

Geçiş notu (Faz 7): Tarihi `hash_password()` SHA-256 kullanıyordu. Bu modül
artık bcrypt'e geçti. Eski SHA-256 hash'leri `verify_password()` tarafından
hâlâ doğrulanır — bu sayede demo/sıkı kullanıcılar tek başına şifre değiştirmek
zorunda kalmaz, ilk başarılı login'de hash otomatik upgrade edilir
(bkz. `auth_service.authenticate_user`).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings


# Bcrypt cost factor: 12 = ~250ms/hash on modern CPUs. Düşürmek brute-force
# direncini azaltır; yükseltmek login latency'yi şişirir.
_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)


def hash_password(password: str) -> str:
    """Yeni hash üret — her zaman bcrypt (rastgele salt'lı)."""
    if not password:
        raise ValueError("password must not be empty")
    # Bcrypt'in 72 byte sınırı var — kullanıcıya bilgi ver
    if len(password.encode("utf-8")) > 72:
        raise ValueError("password too long (max 72 bytes for bcrypt)")
    return _pwd_context.hash(password)


def _is_legacy_sha256(hashed: str) -> bool:
    """Eski SHA-256 hex hash'ini bcrypt $2b$... formatından ayırır."""
    return len(hashed) == 64 and all(c in "0123456789abcdef" for c in hashed)


def verify_password(password: str, hashed_password: str) -> bool:
    """Hem yeni bcrypt hem eski SHA-256 hash'leri tolere eder.

    Eski hash başarılı doğrulanırsa caller (auth_service) hash'i upgrade etmeli.
    `needs_rehash()` ile bunu sorabilir.
    """
    if not hashed_password:
        return False
    if _is_legacy_sha256(hashed_password):
        # Sabit-zaman karşılaştırma — timing attack'a karşı
        legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return _constant_time_eq(legacy, hashed_password)
    try:
        return _pwd_context.verify(password, hashed_password)
    except Exception:  # noqa: BLE001 — passlib bazen UnknownHashError fırlatır
        return False


def needs_rehash(hashed_password: str) -> bool:
    """Hash bcrypt değilse veya cost factor eski ise True döner."""
    if _is_legacy_sha256(hashed_password):
        return True
    try:
        return _pwd_context.needs_update(hashed_password)
    except Exception:  # noqa: BLE001
        return True


def _constant_time_eq(a: str, b: str) -> bool:
    """Sabit zamanlı string karşılaştırma — timing leak engelleyici."""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0


# ─── JWT ────────────────────────────────────────────────────────────────────
def create_access_token(subject: str, *, organization_id: int | None = None) -> str:
    """Access token üretir.

    Eklenen claim'ler:
      - sub: kullanıcı id (string)
      - iat: issued-at (unix timestamp) — token reuse / replay denetimi
      - exp: expiration
      - org_id: opsiyonel tenant kimliği
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.jwt_expire_minutes)
    payload: dict[str, object] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": expires_at,
    }
    if organization_id is not None:
        payload["org_id"] = organization_id
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
