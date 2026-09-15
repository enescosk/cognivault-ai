"""Klinik ses karakteri profilleri — Voice Studio ile canlı çağrı yolunun ortak dili.

İki taraf, iki ses:
- `receiver`: gelen aramayı/hasta sayfasını karşılayan asistan. Canlı yol budur.
- `caller`:   giden aramayı yapan asistan (stüdyodaki "Giden görüşme" provası).

Kayıt yeri `clinic.settings_json["voice"]["profiles"][<rol>]`. Tek kaynak olması
önemli: stüdyoda dinlenen ses ile hastanın duyduğu ses aynı olsun diye hem
`/voice-studio/speech` hem de hasta sayfası aynı sözlüğü
`get_tts_provider(voice_profile=...)`'e geçirir.

Doğrulama savunma amaçlı: kaydederken bir kez, okurken bir kez kırpılır. Tek
profilli eski kayıtlar (`voice.profile`, `voice.tts_voice`) receiver'a düşer.
"""
from __future__ import annotations

from typing import Any

# Türkçe için desteklenen modeller. multilingual_v2 en doğal, flash_v2_5 en hızlı
# (~75 ms), turbo ikisinin arası. Listede olmayan bir model kaydedilemez.
ALLOWED_MODELS = ("eleven_multilingual_v2", "eleven_flash_v2_5", "eleven_turbo_v2_5")

# Görüşmenin iki tarafı. Stüdyodaki yön seçimi ile birebir eşleşir:
# gelen görüşme → receiver, giden görüşme → caller.
ROLES = ("receiver", "caller")
DEFAULT_ROLE = "receiver"

_RANGES: dict[str, tuple[float, float]] = {
    "speed": (0.7, 1.2),
    "stability": (0.0, 1.0),
    "similarity_boost": (0.0, 1.0),
    "style": (0.0, 1.0),
}


def _clamped(key: str, value: Any) -> float | None:
    low, high = _RANGES[key]
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return None


def _sanitize(stored: dict | None, *, legacy_voice_id: str | None = None) -> dict:
    stored = stored or {}
    profile: dict[str, Any] = {}
    voice_id = stored.get("voice_id") or legacy_voice_id
    if voice_id:
        profile["voice_id"] = str(voice_id)
    if stored.get("model") in ALLOWED_MODELS:
        profile["model"] = stored["model"]
    for key in _RANGES:
        if key in stored:
            value = _clamped(key, stored[key])
            if value is not None:
                profile[key] = value
    if "speaker_boost" in stored:
        profile["speaker_boost"] = bool(stored["speaker_boost"])
    return profile


def clinic_voice_profile(voice_settings: dict | None, role: str = DEFAULT_ROLE) -> dict:
    """Kayıtlı ayarlardan `get_tts_provider` için override sözlüğü üretir.

    Yalnızca gerçekten kaydedilmiş alanlar döner; eksik olanlar Settings
    varsayılanlarına düşsün diye sözlüğe hiç konmaz.
    """
    voice = voice_settings or {}
    role = role if role in ROLES else DEFAULT_ROLE
    stored = (voice.get("profiles") or {}).get(role)
    if stored is None and role == DEFAULT_ROLE:
        # Rol ayrımından önce kaydedilmiş tek profil karşılayan taraftı.
        return _sanitize(voice.get("profile"), legacy_voice_id=voice.get("tts_voice"))
    return _sanitize(stored)


def normalize_profile(payload: dict) -> dict:
    """Kaydedilecek profili doğrular/kırpar. Bozuk alanlar sessizce düşer."""
    return _sanitize(payload)


def apply_profile(settings_json: dict | None, profile: dict, *, role: str = DEFAULT_ROLE,
                  tts_provider: str | None = None, external_enabled: bool | None = None,
                  allow_cross_border: bool | None = None) -> dict:
    """Bir rolün profilini klinik ayarlarına yazar; diğer rolü ve STT ayarlarını korur."""
    settings = dict(settings_json or {})
    role = role if role in ROLES else DEFAULT_ROLE
    if allow_cross_border is not None:
        # Klinik seviyesinde sınır-ötesi işleyici izni. Tek başına veri göndermez;
        # hasta ayrıca CROSS_BORDER_TRANSFER + VOICE_RECORDING rızası vermeli.
        settings["allow_cross_border_processors"] = bool(allow_cross_border)
    voice = dict(settings.get("voice") or {})
    profiles = dict(voice.get("profiles") or {})
    if not profiles and voice.get("profile"):
        profiles[DEFAULT_ROLE] = voice["profile"]  # eski tek profili taşı
    profiles[role] = profile
    voice["profiles"] = profiles
    voice.pop("profile", None)
    if role == DEFAULT_ROLE:
        # Eski okuyucular (clinic_admin ekranı) profilleri görmez; karşılayan
        # sesin kimliğini onların baktığı alanda da tut.
        voice["tts_voice"] = profile.get("voice_id") or voice.get("tts_voice")
    if tts_provider is not None:
        voice["tts_provider"] = tts_provider
    if external_enabled is not None:
        voice["external_enabled"] = bool(external_enabled)
    voice.setdefault("stt_provider", "local")
    voice.setdefault("tts_provider", "local")
    voice.setdefault("external_enabled", False)
    settings["voice"] = voice
    return settings


def call_readiness(settings_json: dict | None, *, server_key_configured: bool,
                   app_external_enabled: bool = True, role: str = DEFAULT_ROLE) -> list[str]:
    """Bu rolün sesinin canlı çağrıda çalmasına ne engel? (Boş liste → hazır.)

    Hasta rızası listede yok; o her görüşmede ayrıca sorulur ve yoksa yol zaten
    yerel sese düşer.
    """
    settings = settings_json or {}
    voice = settings.get("voice") or {}
    blockers = []
    if not app_external_enabled:
        # get_tts_provider bu bayrağı klinik ayarıyla AND'ler: kapalıyken klinik
        # ne kaydederse kaydetsin ses yerelde kalır. Sunucu .env'inden açılır.
        blockers.append("Sunucuda VOICE_EXTERNAL_ENABLED=false.")
    if (voice.get("tts_provider") or "local") != "elevenlabs":
        blockers.append("Klinik sesi hâlâ yerel Piper'a ayarlı.")
    if not clinic_voice_profile(voice, role).get("voice_id"):
        blockers.append("Bu taraf için kayıtlı bir ElevenLabs sesi yok.")
    if not voice.get("external_enabled"):
        blockers.append("Klinik için dış ses işleme kapalı.")
    if not settings.get("allow_cross_border_processors"):
        blockers.append("Sınır-ötesi işleyici izni kapalı.")
    if not server_key_configured:
        blockers.append("Sunucuda ELEVENLABS_API_KEY tanımlı değil.")
    return blockers
