"""Provider webhook signature verification helpers.

Both Twilio and Meta sign their webhooks with HMAC. Validating these signatures
is the only way to reject forged inbound messages that target the unauthenticated
webhook endpoints. Verification is gated by `clinical_webhook_signature_required`
so existing dev/test flows continue to work without secrets configured.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Mapping

from app.core.config import get_settings


def _twilio_canonical_string(url: str, params: Mapping[str, str]) -> str:
    """Twilio's request validator concatenates URL + sorted form fields."""

    sorted_pairs = sorted(params.items(), key=lambda item: item[0])
    return url + "".join(f"{k}{v}" for k, v in sorted_pairs)


def verify_twilio_signature(
    *,
    auth_token: str,
    request_url: str,
    form_params: Mapping[str, str],
    signature_header: str | None,
) -> bool:
    """Validates `X-Twilio-Signature` (HMAC-SHA1, base64) against the canonical request."""

    if not auth_token or not signature_header:
        return False
    canonical = _twilio_canonical_string(request_url, form_params)
    digest = hmac.new(
        auth_token.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature_header)


def verify_meta_signature(
    *,
    app_secret: str,
    raw_body: bytes,
    signature_header: str | None,
) -> bool:
    """Validates Meta's `X-Hub-Signature-256` (HMAC-SHA256, hex)."""

    if not app_secret or not signature_header:
        return False
    if not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    provided = signature_header.split("=", 1)[1].strip()
    return hmac.compare_digest(expected, provided)


def signature_required() -> bool:
    """Webhook imza doğrulamasının zorunlu olup olmadığını döner.

    Production'da her zaman True — `clinical_webhook_signature_required` flag'i
    false olsa bile prod'da imza zorunlu. Bu, config'i unutarak yanlış deploy
    edilen senaryolarda ikinci savunma katmanıdır.
    """
    settings = get_settings()
    if settings.is_production:
        return True
    return bool(settings.clinical_webhook_signature_required)
