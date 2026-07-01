"""Ses sağlayıcı soyutlaması — STT (konuşma→metin) ve TTS (metin→konuşma).

KVKK local-first ilkesi: varsayılan olarak ses verisi yurt içinde, tamamen
cihaz/sunucu üzerinde işlenir. Bulut sağlayıcılar (OpenAI) yalnızca
`voice_external_enabled=True` VE provider açıkça "openai" seçildiğinde devreye
girer. Aksi halde ses verisi hiçbir koşulda dışarı çıkmaz.

- STT: faster-whisper (CTranslate2, lokal). webm/opus dahil PyAV ile çözülür.
- TTS: Piper (nöral, tr_TR). Piper yüklenemezse macOS `say -v Yelda` (yine lokal).
       Her ikisi de WAV döndürür.
"""
from __future__ import annotations

import io
import logging
import os
import subprocess
import tempfile
import threading
import wave
from abc import ABC, abstractmethod

from app.core.config import get_settings

logger = logging.getLogger("cognivault.voice")


# ─────────────────────────────────────────────────────────────────────────────
# Dış ses (bulut STT/TTS) rıza kapısı — KVKK sınır-ötesi transfer
# ─────────────────────────────────────────────────────────────────────────────
def external_voice_permitted(
    *, external_enabled: bool, consent_granted: bool, has_credentials: bool
) -> bool:
    """Ses verisi buluta (OpenAI/ElevenLabs) gönderilebilir mi?

    Üç koşulun HEPSİ gerekir (yumuşatılamaz KVKK kapısı):
    - external_enabled: klinik dış işlemeyi/DPA'yı açıkça açtı (`voice_external_enabled`).
    - consent_granted:  hasta VOICE_RECORDING açık rızası verdi (governance katmanı).
    - has_credentials:  sağlayıcı API anahtarı yapılandırılmış.

    Biri bile eksikse ses yurt içinde (yerel yığın) işlenir. Bu saf fonksiyon
    çağrı-yolundan bağımsız test edilir; canlı yol per-hasta rızayı buraya taşır.
    """
    return bool(external_enabled and consent_granted and has_credentials)


# ─────────────────────────────────────────────────────────────────────────────
# STT — Speech to Text
# ─────────────────────────────────────────────────────────────────────────────
class STTProvider(ABC):
    @abstractmethod
    def transcribe(self, audio: bytes, language: str = "tr") -> str:
        """Ses baytlarını (webm/opus/wav/mp3) metne çevirir."""


_whisper_model = None
_whisper_lock = threading.Lock()


def _get_whisper():
    """faster-whisper modelini tek sefer yükler (singleton, thread-safe)."""
    global _whisper_model
    if _whisper_model is None:
        with _whisper_lock:
            if _whisper_model is None:
                from faster_whisper import WhisperModel

                s = get_settings()
                logger.info("Loading local Whisper model: %s (%s)", s.local_whisper_model, s.local_whisper_compute)
                _whisper_model = WhisperModel(
                    s.local_whisper_model, device="cpu", compute_type=s.local_whisper_compute
                )
    return _whisper_model


class LocalWhisperSTT(STTProvider):
    """faster-whisper — ses sunucudan çıkmadan yurt içinde çözülür."""

    def transcribe(self, audio: bytes, language: str = "tr") -> str:
        model = _get_whisper()
        segments, _info = model.transcribe(io.BytesIO(audio), language=language or None)
        return "".join(seg.text for seg in segments).strip()


class OpenAIWhisperSTT(STTProvider):
    """OpenAI Whisper — yalnızca dış aktarıma açıkça izin verildiğinde."""

    def transcribe(self, audio: bytes, language: str = "tr") -> str:
        from openai import OpenAI

        s = get_settings()
        client = OpenAI(api_key=s.openai_api_key)
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=("audio.webm", io.BytesIO(audio), "audio/webm"),
            language=language or "tr",
            response_format="text",
        )
        return result.strip() if isinstance(result, str) else str(result).strip()


class ElevenLabsScribeSTT(STTProvider):
    """ElevenLabs Scribe v2 Realtime — düşük gecikmeli TR konuşma tanıma.

    Yalnızca rıza kapısı (klinik DPA + hasta rızası + API anahtarı) geçilince
    devreye girer. Ses baytları ElevenLabs'e HTTP ile gider — sınır-ötesi
    transfer; bu yüzden çağrı yolu `external_voice_permitted()` kapısını
    geçmeden bu sınıf seçilmez.
    """

    def transcribe(self, audio: bytes, language: str = "tr") -> str:
        import httpx

        s = get_settings()
        resp = httpx.post(
            "https://api.elevenlabs.io/v1/speech-to-text",
            headers={"xi-api-key": s.elevenlabs_api_key},
            data={"model_id": s.elevenlabs_stt_model, "language_code": language or "tr"},
            files={"file": ("audio.webm", audio, "audio/webm")},
            timeout=s.local_llm_timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        return str(payload.get("text", "")).strip()


def get_stt_provider(*, consent_granted: bool = False) -> STTProvider:
    """Local-first: bulut STT yalnızca rıza kapısı (dış izin + hasta rızası +
    anahtar) geçilirse. Aksi halde her zaman yerel Whisper.
    """
    s = get_settings()
    if s.voice_stt_provider == "elevenlabs" and external_voice_permitted(
        external_enabled=s.voice_external_enabled,
        consent_granted=consent_granted,
        has_credentials=bool(s.elevenlabs_api_key),
    ):
        return ElevenLabsScribeSTT()
    if s.voice_stt_provider == "openai" and external_voice_permitted(
        external_enabled=s.voice_external_enabled,
        consent_granted=consent_granted,
        has_credentials=bool(s.openai_api_key),
    ):
        return OpenAIWhisperSTT()
    return LocalWhisperSTT()


# ─────────────────────────────────────────────────────────────────────────────
# TTS — Text to Speech  (her zaman (bytes, mime) döndürür)
# ─────────────────────────────────────────────────────────────────────────────
class TTSProvider(ABC):
    @abstractmethod
    def synthesize(self, text: str, voice: str | None = None) -> tuple[bytes, str]:
        """Metni sese çevirir; (ses_baytları, mime_type) döner."""


_piper_voice = None
_piper_lock = threading.Lock()


def _get_piper():
    global _piper_voice
    if _piper_voice is None:
        with _piper_lock:
            if _piper_voice is None:
                from piper import PiperVoice

                s = get_settings()
                logger.info("Loading local Piper voice: %s", s.piper_voice_path)
                _piper_voice = PiperVoice.load(s.piper_voice_path)
    return _piper_voice


class LocalPiperTTS(TTSProvider):
    """Piper nöral TTS (tr_TR) — ses yurt içinde üretilir. Piper yüklenemezse
    macOS `say`'e düşer (yine lokal); böylece local-first garantisi korunur."""

    def synthesize(self, text: str, voice: str | None = None) -> tuple[bytes, str]:
        try:
            v = _get_piper()
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                v.synthesize_wav(text, wf)
            return buf.getvalue(), "audio/wav"
        except Exception as e:  # noqa: BLE001
            logger.warning("Piper sentez hatası, macOS say fallback: %s", e)
            return MacSayTTS().synthesize(text, voice)


class MacSayTTS(TTSProvider):
    """macOS yerleşik `say -v Yelda` — Piper yoksa garantili lokal fallback."""

    def synthesize(self, text: str, voice: str | None = None) -> tuple[bytes, str]:
        # text argv elemanı olarak geçer (shell yok → enjeksiyon riski yok).
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            subprocess.run(
                ["say", "-v", "Yelda", "--data-format=LEI16@22050", "-o", path, text[:4000]],
                check=True, timeout=30, capture_output=True,
            )
            with open(path, "rb") as fh:
                return fh.read(), "audio/wav"
        finally:
            if os.path.exists(path):
                os.remove(path)


class OpenAITTS(TTSProvider):
    """OpenAI TTS (nova) — yalnızca dış aktarıma açıkça izin verildiğinde."""

    def synthesize(self, text: str, voice: str | None = None) -> tuple[bytes, str]:
        from openai import OpenAI

        s = get_settings()
        client = OpenAI(api_key=s.openai_api_key)
        resp = client.audio.speech.create(
            model="tts-1", voice=voice or "nova", input=text[:4096], response_format="mp3"
        )
        return resp.content, "audio/mpeg"


class ElevenLabsTTS(TTSProvider):
    """ElevenLabs Flash/Turbo TTS — düşük gecikmeli (~75ms) premium TR ses.

    Rıza kapısı (klinik DPA + hasta rızası + API anahtarı) geçilmeden seçilmez;
    metin ElevenLabs'e HTTP ile gider (sınır-ötesi transfer).
    """

    def synthesize(self, text: str, voice: str | None = None) -> tuple[bytes, str]:
        import httpx

        s = get_settings()
        voice_id = voice or s.elevenlabs_voice_id
        resp = httpx.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={"xi-api-key": s.elevenlabs_api_key, "accept": "audio/mpeg"},
            json={"text": text[:5000], "model_id": s.elevenlabs_tts_model},
            timeout=s.local_llm_timeout,
        )
        resp.raise_for_status()
        return resp.content, "audio/mpeg"


def get_tts_provider(*, consent_granted: bool = False) -> TTSProvider:
    """Local-first: bulut TTS yalnızca rıza kapısı (dış izin + hasta rızası +
    anahtar) geçilirse. Aksi halde önce Piper, yoksa macOS `say` — ses yurt
    içinde kalır."""
    s = get_settings()
    if s.voice_tts_provider == "elevenlabs" and external_voice_permitted(
        external_enabled=s.voice_external_enabled,
        consent_granted=consent_granted,
        has_credentials=bool(s.elevenlabs_api_key and s.elevenlabs_voice_id),
    ):
        return ElevenLabsTTS()
    if s.voice_tts_provider == "openai" and external_voice_permitted(
        external_enabled=s.voice_external_enabled,
        consent_granted=consent_granted,
        has_credentials=bool(s.openai_api_key),
    ):
        return OpenAITTS()
    # Lokal: Piper varsa onu kullan (model lazy yüklenir, hata olursa say'e düşer),
    # hiç yoksa doğrudan macOS say. Her durumda ses yurt içinde kalır.
    if os.path.exists(s.piper_voice_path):
        return LocalPiperTTS()
    return MacSayTTS()
