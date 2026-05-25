"""Domain-level exception hierarchy.

Servis katmanı `HTTPException` fırlatmamalı. HTTP, taşıma katmanı detayı —
servis bunu bilmemeli ki:
  - background worker'lardan (outbox, cron) çağrıldığında çökmesin
  - unit test'lerde request context olmadan domain test'i yazılabilsin
  - aynı servis bir CLI komutu veya gRPC handler arkasında yeniden kullanılabilsin

Yerine: servis katmanı `DomainError` türev hiyerarşisi fırlatır. API katmanı
(`app.main`) bunları HTTP status'lara çevirir tek noktadan.

Yeni hata tipi eklemek istersen:
  1. Burada uygun base'i extend et (NotFoundError, PermissionError, ValidationError)
  2. `STATUS_MAP` otomatik kapsar — extra eşleme gerekmez
  3. Servis katmanından doğrudan fırlat
"""

from __future__ import annotations

from fastapi import status


class DomainError(Exception):
    """Tüm domain hatalarının kökü. Doğrudan fırlatma — alt sınıfları kullan."""

    http_status: int = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        return self.message


class NotFoundError(DomainError):
    """Kaynak bulunamadı — 404'e dönüşür."""

    http_status = status.HTTP_404_NOT_FOUND


class PermissionError(DomainError):
    """Kullanıcının yetkisi yok — 403'e dönüşür.

    Not: Python built-in `PermissionError` ile aynı isim taşır ama farklı
    modülde. Import edenler `from app.core.exceptions import PermissionError`
    şeklinde aldığı için karışmaz.
    """

    http_status = status.HTTP_403_FORBIDDEN


class AuthenticationError(DomainError):
    """Kimlik doğrulanamadı — 401'e dönüşür."""

    http_status = status.HTTP_401_UNAUTHORIZED


class ValidationError(DomainError):
    """Domain kuralı ihlali — 400'e dönüşür. Pydantic validation'dan ayrı."""

    http_status = status.HTTP_400_BAD_REQUEST


class ConflictError(DomainError):
    """Kaynak zaten var veya çakışma — 409'a dönüşür."""

    http_status = status.HTTP_409_CONFLICT


class UpstreamError(DomainError):
    """Dış servis (OpenAI, Twilio, Stripe) hatası — 502'ye dönüşür."""

    http_status = status.HTTP_502_BAD_GATEWAY
