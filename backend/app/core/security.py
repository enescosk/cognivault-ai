"""Şifre hash'leme + JWT yardımcı modülü.

Geçiş notu (Faz 7): Tarihi `hash_password()` SHA-256 kullanıyordu. Bu modül
artık bcrypt'e geçti. Eski SHA-256 hash'leri `verify_password()` tarafından
hâlâ doğrulanır — bu sayede demo/sıkı kullanıcılar tek başına şifre değiştirmek
zorunda kalmaz, ilk başarılı login'de hash otomatik upgrade edilir
(bkz. `auth_service.authenticate_user`).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import base64
import hmac
import hashlib
import os

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import InvalidHashError, VerifyMismatchError
except ImportError:  # pragma: no cover - dependency fallback for tiny local envs
    PasswordHasher = None  # type: ignore[assignment]
    InvalidHashError = Exception  # type: ignore[assignment]
    VerifyMismatchError = Exception  # type: ignore[assignment]


ARGON2_PREFIX = "$argon2"
SCRYPT_PREFIX = "scrypt"
LEGACY_SHA256_HEX_LENGTH = 64
_ARGON2_HASHER = (
    PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2, hash_len=32, salt_len=16)
    if PasswordHasher
    else None
)


# Bcrypt cost factor: 12 = ~250ms/hash on modern CPUs. Düşürmek brute-force
# direncini azaltır; yükseltmek login latency'yi şişirir.
_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)


BCRYPT_MAX_BYTES = 72


def _is_legacy_sha256(hashed_password: str) -> bool:
    """Hash 64 karakterlik hex ise eski SHA-256 kabul edilir."""
    if len(hashed_password) != LEGACY_SHA256_HEX_LENGTH:
        return False
    try:
        int(hashed_password, 16)
    except ValueError:
        return False
    return True


def hash_password(password: str) -> str:
    """Bcrypt ile şifre hash'ler.

    Boş şifre ve bcrypt'in 72 byte sınırını aşan şifreler net `ValueError` ile
    reddedilir — sessiz truncation'a izin verilmez.
    """
    if not password:
        raise ValueError("Şifre boş olamaz.")
    if len(password.encode("utf-8")) > BCRYPT_MAX_BYTES:
        raise ValueError(
            f"Şifre çok uzun: bcrypt en fazla {BCRYPT_MAX_BYTES} byte destekler."
        )
    return _pwd_context.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False

    if _is_legacy_sha256(hashed_password):
        legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(legacy, hashed_password)

    if hashed_password.startswith(ARGON2_PREFIX):
        if _ARGON2_HASHER is None:
            return False
        try:
            return _ARGON2_HASHER.verify(hashed_password, password)
        except (InvalidHashError, VerifyMismatchError):
            return False

    if hashed_password.startswith(f"{SCRYPT_PREFIX}$"):
        try:
            _, params, salt_b64, digest_b64 = hashed_password.split("$", 3)
            param_values = dict(item.split("=", 1) for item in params.split(","))
            salt = base64.b64decode(salt_b64.encode("ascii"))
            expected = base64.b64decode(digest_b64.encode("ascii"))
            actual = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt,
                n=int(param_values["n"]),
                r=int(param_values["r"]),
                p=int(param_values["p"]),
                dklen=len(expected),
            )
            return hmac.compare_digest(actual, expected)
        except (KeyError, ValueError, TypeError):
            return False

    try:
        return _pwd_context.verify(password, hashed_password)
    except Exception:  # noqa: BLE001
        return False


def needs_rehash(hashed_password: str) -> bool:
    """Hash bcrypt değilse veya cost factor eski ise True döner."""
    if _is_legacy_sha256(hashed_password):
        return True
    try:
        return _pwd_context.needs_update(hashed_password)
    except Exception:  # noqa: BLE001
        return True


# Geriye dönük uyumluluk için alias.
password_needs_rehash = needs_rehash


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
