"""
Anonim hasta için kısa-ömürlü token mekanizması.

Patient page'de auth login yerine iki tip kısa-ömürlü token kullanıyoruz:

  1. consent_token   — KVKK onayı sonrası 15 dakika geçerli.
                       Onboarding (ad-soyad + telefon) ekranı bu token'la
                       ConsentRecord'ı bağlar, ardından conversation aç.
  2. session_token   — Conversation açılınca üretilir. 60 dakika geçerli.
                       Tüm mesaj ve appointment endpoint'leri bunu kullanır.

İkisi de aynı JWT mekanizmasını kullanır (core/security.py). Token type
`typ` claim'i ile ayrılır (`patient_consent` / `patient_session`).

Bu modül **yalnızca public endpoint'lerinden** çağrılır.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, status

from app.core.config import get_settings

CONSENT_TOKEN_TTL_MIN = 15
SESSION_TOKEN_TTL_MIN = 60

CONSENT_TYP = "patient_consent"
SESSION_TYP = "patient_session"


@dataclass(frozen=True)
class ConsentPayload:
    """KVKK onay token'ının içerdiği bilgiler."""

    clinic_id: int
    clinic_slug: str
    disclosure_version: str
    consent_record_ids: tuple[int, ...]
    granted_at: int  # iat
    expires_at: int


@dataclass(frozen=True)
class SessionPayload:
    """Konuşma oturum token'ının içerdiği bilgiler."""

    clinic_id: int
    clinic_slug: str
    patient_id: int
    conversation_id: int
    disclosure_version: str
    expires_at: int


def _encode(payload: dict) -> str:
    settings = get_settings()
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="patient_token_expired",
        ) from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="patient_token_invalid",
        ) from exc


def issue_consent_token(
    *,
    clinic_id: int,
    clinic_slug: str,
    disclosure_version: str,
    consent_record_ids: list[int] | tuple[int, ...],
) -> str:
    """KVKK onayı verilen anda üretilir, onboarding adımının kapısıdır."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=CONSENT_TOKEN_TTL_MIN)
    payload = {
        "typ": CONSENT_TYP,
        "clinic_id": clinic_id,
        "clinic_slug": clinic_slug,
        "disclosure_version": disclosure_version,
        "consent_record_ids": list(consent_record_ids),
        "iat": int(now.timestamp()),
        "exp": expires_at,
    }
    return _encode(payload)


def issue_session_token(
    *,
    clinic_id: int,
    clinic_slug: str,
    patient_id: int,
    conversation_id: int,
    disclosure_version: str,
) -> str:
    """Sohbet açıldıktan sonra kullanılan uzun token."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=SESSION_TOKEN_TTL_MIN)
    payload = {
        "typ": SESSION_TYP,
        "clinic_id": clinic_id,
        "clinic_slug": clinic_slug,
        "patient_id": patient_id,
        "conversation_id": conversation_id,
        "disclosure_version": disclosure_version,
        "iat": int(now.timestamp()),
        "exp": expires_at,
    }
    return _encode(payload)


def decode_consent_token(token: str) -> ConsentPayload:
    """`Authorization: Bearer <token>` formatından geçen consent token'ı çözer."""
    data = _decode(token)
    if data.get("typ") != CONSENT_TYP:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="patient_token_wrong_type",
        )
    return ConsentPayload(
        clinic_id=int(data["clinic_id"]),
        clinic_slug=str(data["clinic_slug"]),
        disclosure_version=str(data["disclosure_version"]),
        consent_record_ids=tuple(int(item) for item in data.get("consent_record_ids", [])),
        granted_at=int(data.get("iat", 0)),
        expires_at=int(data.get("exp", 0)),
    )


def decode_session_token(token: str) -> SessionPayload:
    """Mesaj / appointment endpoint'lerine gelen session token'ı çözer."""
    data = _decode(token)
    if data.get("typ") != SESSION_TYP:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="patient_token_wrong_type",
        )
    return SessionPayload(
        clinic_id=int(data["clinic_id"]),
        clinic_slug=str(data["clinic_slug"]),
        patient_id=int(data["patient_id"]),
        conversation_id=int(data["conversation_id"]),
        disclosure_version=str(data["disclosure_version"]),
        expires_at=int(data.get("exp", 0)),
    )
