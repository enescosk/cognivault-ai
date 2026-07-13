"""Telefon TwiML yanıtları için önceden sentezlenmiş ses cache'i.

Twilio `<Say voice="alice">` Türkçesi belirgin robotik; web hasta sayfası için
kurduğumuz doğal yerel TTS (Piper/fahrettin) telefonda kullanılmıyordu. Bu
modül yanıt metnini TwiML dönmeden ÖNCE lokal TTS ile sentezler (RTF ~0.04,
tipik yanıt <0,5 sn), baytları kısa ömürlü bellek-içi cache'e koyar ve TwiML
`<Play>/api/webhooks/voice/tts/{anahtar}.wav</Play>` ile çalar.

Tasarım notları:
- Anahtar = sha256(metin): ses YALNIZCA metni zaten bilen tarafça indirilebilir
  (Twilio az önce o metni bizden aldı) → URL üzerinden bilgi sızmaz.
- Sentez lokaldir (get_tts_provider(False) → Piper/say); hasta verisi bu yolda
  yurt dışına çıkmaz. Twilio çağrı taşıyıcısı olarak zaten arada (transport-only).
- Her hata sessizce None'a düşer → çağıran <Say> fallback'ini kullanır;
  telefon akışı TTS arızasıyla ASLA kesilmez.
- Tek-süreç (pilot) varsayımı: cache bellek-içidir. Çok-worker dağıtımda
  anahtar bulunamazsa endpoint 404 döner, Twilio o cümleyi atlar — bilinen
  sınırlama; çok-worker prod'da paylaşımlı cache gerekir.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_TTL_SECONDS = 15 * 60
_MAX_ENTRIES = 256

_cache: dict[str, tuple[float, bytes, str]] = {}
_lock = threading.Lock()


def _purge_locked(now: float) -> None:
    expired = [key for key, (ts, _, _) in _cache.items() if now - ts > _TTL_SECONDS]
    for key in expired:
        _cache.pop(key, None)
    if len(_cache) > _MAX_ENTRIES:
        # En eskiler atılır — kısa ömürlü telefon yanıtları için yeterli.
        for key, _ in sorted(_cache.items(), key=lambda item: item[1][0])[: len(_cache) - _MAX_ENTRIES]:
            _cache.pop(key, None)


def prompt_key(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def synthesize_prompt(text: str) -> str | None:
    """Metni lokal TTS ile sentezleyip cache'e koyar; anahtar döner.

    Aynı metin daha önce sentezlendiyse yeniden üretmez (karşılama ve tekrar
    eden yönlendirme cümleleri tek sefer sentezlenir). Her hata → None
    (çağıran <Say> fallback'i kullanır); exception asla dışarı çıkmaz.
    """
    settings = get_settings()
    if not getattr(settings, "voice_phone_native_tts_enabled", True):
        return None
    text = text.strip()
    if not text:
        return None
    key = prompt_key(text)
    now = time.time()
    with _lock:
        cached = _cache.get(key)
        if cached is not None:
            _cache[key] = (now, cached[1], cached[2])  # TTL tazele
            return key
    try:
        from app.ai.voice_factory import get_tts_provider

        audio, mime = get_tts_provider(False).synthesize(text)
    except Exception as exc:  # noqa: BLE001 — telefon akışı TTS'e kurban edilmez
        logger.warning("voice_prompt_synthesis_failed: %s", exc)
        return None
    if not audio:
        return None
    with _lock:
        _cache[key] = (now, audio, mime)
        _purge_locked(now)
    return key


def get_prompt_audio(key: str) -> tuple[bytes, str] | None:
    now = time.time()
    with _lock:
        cached = _cache.get(key)
        if cached is None or now - cached[0] > _TTL_SECONDS:
            _cache.pop(key, None)
            return None
        return cached[1], cached[2]


def clear_cache() -> None:
    """Test yardımcıları için."""
    with _lock:
        _cache.clear()
