from datetime import datetime, timedelta, timezone
import base64
import hmac
import hashlib
import os

import jwt

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


def hash_password(password: str) -> str:
    """
    Versioned, production-grade password hashing.

    Argon2id is preferred when the dependency is available. A memory-hard scrypt
    fallback keeps local/test installs safe even before optional wheels are present.
    """
    if _ARGON2_HASHER is not None:
        return _ARGON2_HASHER.hash(password)

    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "$".join(
        [
            SCRYPT_PREFIX,
            "n=16384,r=8,p=1",
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False

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

    if len(hashed_password) == LEGACY_SHA256_HEX_LENGTH:
        legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
        return hmac.compare_digest(legacy, hashed_password)

    return False


def password_needs_rehash(hashed_password: str) -> bool:
    if not hashed_password.startswith(ARGON2_PREFIX):
        return True
    if _ARGON2_HASHER is None:
        return False
    try:
        return _ARGON2_HASHER.check_needs_rehash(hashed_password)
    except InvalidHashError:
        return True


def create_access_token(subject: str) -> str:
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
