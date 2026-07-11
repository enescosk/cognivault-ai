"""Sesli STT/TTS'in klinik-seviyesi sınır-ötesi rıza kapısını atlamadığını kilitler.

`build_compliance_profile` (clinical_compliance_service.py) "external_voice_stt_tts"
işlemcisini `voice_external_enabled AND allow_cross_border_processors` ikisi de açık
olmadan "clinical_default": "blocked" olarak tanımlar. İki ayrı ses hattı var:

  - `app/ai/voice_factory.py` (get_stt_provider/get_tts_provider) — hasta sayfası
    (public.py) tarafından kullanılır.
  - `app/services/voice_ai_service.py` (_select_stt_provider/_select_tts_provider)
    — personel paneli (voice.py) tarafından kullanılır.

Her ikisi de global `voice_external_enabled` bayrağının yanında, arayanın ilettiği
klinik-seviyesi rızayı (`external_transfer_allowed`) zorunlu kılmalı; global bayrak
tek başına ya da klinik rızası tek başına yeterli olmamalı.
"""

from app.ai import voice_factory
from app.core.config import get_settings
from app.services import voice_ai_service


# ─────────────────────────────────────────────────────────────────────────────
# app/ai/voice_factory.py — hasta sayfası (public.py) hattı
# ─────────────────────────────────────────────────────────────────────────────
def test_stt_defaults_to_local_without_clinic_consent(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "voice_stt_provider", "openai")
    monkeypatch.setattr(settings, "voice_external_enabled", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    provider = voice_factory.get_stt_provider()  # external_transfer_allowed varsayılan False
    assert isinstance(provider, voice_factory.LocalWhisperSTT)


def test_stt_stays_local_when_only_app_switch_on(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "voice_stt_provider", "openai")
    monkeypatch.setattr(settings, "voice_external_enabled", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    provider = voice_factory.get_stt_provider(external_transfer_allowed=False)
    assert isinstance(provider, voice_factory.LocalWhisperSTT)


def test_stt_stays_local_when_only_clinic_consent_on(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "voice_stt_provider", "openai")
    monkeypatch.setattr(settings, "voice_external_enabled", False)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    provider = voice_factory.get_stt_provider(external_transfer_allowed=True)
    assert isinstance(provider, voice_factory.LocalWhisperSTT)


def test_stt_uses_openai_only_with_full_consent(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "voice_stt_provider", "openai")
    monkeypatch.setattr(settings, "voice_external_enabled", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    provider = voice_factory.get_stt_provider(external_transfer_allowed=True, consent_granted=True)
    assert isinstance(provider, voice_factory.OpenAIWhisperSTT)


def test_stt_stays_local_when_voice_consent_missing(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "voice_stt_provider", "openai")
    monkeypatch.setattr(settings, "voice_external_enabled", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    provider = voice_factory.get_stt_provider(external_transfer_allowed=True, consent_granted=False)
    assert isinstance(provider, voice_factory.LocalWhisperSTT)


def test_tts_defaults_to_local_without_clinic_consent(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "voice_tts_provider", "openai")
    monkeypatch.setattr(settings, "voice_external_enabled", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    provider = voice_factory.get_tts_provider()
    assert not isinstance(provider, voice_factory.OpenAITTS)


def test_tts_uses_openai_only_with_full_consent(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "voice_tts_provider", "openai")
    monkeypatch.setattr(settings, "voice_external_enabled", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    provider = voice_factory.get_tts_provider(external_transfer_allowed=True, consent_granted=True)
    assert isinstance(provider, voice_factory.OpenAITTS)


def test_tts_stays_local_when_voice_consent_missing(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "voice_tts_provider", "openai")
    monkeypatch.setattr(settings, "voice_external_enabled", True)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    provider = voice_factory.get_tts_provider(external_transfer_allowed=True, consent_granted=False)
    assert not isinstance(provider, voice_factory.OpenAITTS)


# ─────────────────────────────────────────────────────────────────────────────
# app/services/voice_ai_service.py — personel paneli (voice.py) hattı
# ─────────────────────────────────────────────────────────────────────────────
def test_select_stt_provider_never_picks_openai_without_full_consent(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "speech_stt_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "whisper_cpp_binary", "")
    monkeypatch.setattr(settings, "whisper_cpp_model", "")

    monkeypatch.setattr(settings, "voice_external_enabled", False)
    assert voice_ai_service._select_stt_provider(external_transfer_allowed=True) is None

    monkeypatch.setattr(settings, "voice_external_enabled", True)
    assert voice_ai_service._select_stt_provider(external_transfer_allowed=False) is None

    assert voice_ai_service._select_stt_provider(external_transfer_allowed=True) == "openai"


def test_select_tts_provider_never_picks_openai_without_full_consent(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "speech_tts_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "piper_binary", "")
    monkeypatch.setattr(settings, "piper_voice_model", "")

    monkeypatch.setattr(settings, "voice_external_enabled", False)
    assert voice_ai_service._select_tts_provider(external_transfer_allowed=True) is None

    monkeypatch.setattr(settings, "voice_external_enabled", True)
    assert voice_ai_service._select_tts_provider(external_transfer_allowed=False) is None

    assert voice_ai_service._select_tts_provider(external_transfer_allowed=True) == "openai"


def test_transcribe_audio_bytes_returns_503_without_consent_even_if_openai_configured(monkeypatch):
    """Yerel motor yoksa VE rıza yoksa: hasta sesi hiçbir zaman sessizce OpenAI'a
    kaçmaz — açık 503 hatası verir (fail-closed)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "speech_stt_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "whisper_cpp_binary", "")
    monkeypatch.setattr(settings, "whisper_cpp_model", "")
    monkeypatch.setattr(settings, "voice_external_enabled", True)

    from fastapi import HTTPException
    import pytest

    with pytest.raises(HTTPException) as exc_info:
        voice_ai_service.transcribe_audio_bytes(
            audio_bytes=b"fake-audio-bytes",
            filename="sample.webm",
            content_type="audio/webm",
            language="tr",
            external_transfer_allowed=False,
        )
    assert exc_info.value.status_code == 503


def test_synthesize_speech_bytes_returns_503_without_consent_even_if_openai_configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "speech_tts_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "piper_binary", "")
    monkeypatch.setattr(settings, "piper_voice_model", "")
    monkeypatch.setattr(settings, "voice_external_enabled", True)

    from fastapi import HTTPException
    import pytest

    with pytest.raises(HTTPException) as exc_info:
        voice_ai_service.synthesize_speech_bytes(
            text="Merhaba", voice="nova", speed=1.0, external_transfer_allowed=False,
        )
    assert exc_info.value.status_code == 503
