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


def get_stt_provider() -> STTProvider:
    """Local-first: yalnızca açıkça openai + dış aktarım izni varsa buluta gider."""
    s = get_settings()
    if s.voice_stt_provider == "openai" and s.voice_external_enabled and s.openai_api_key:
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


def get_tts_provider() -> TTSProvider:
    """Local-first: openai yalnızca açıkça seçilip izin verilirse. Lokalde önce
    Piper, yüklenemezse macOS `say` — her durumda ses yurt içinde kalır."""
    s = get_settings()
    if s.voice_tts_provider == "openai" and s.voice_external_enabled and s.openai_api_key:
        return OpenAITTS()
    # Lokal: Piper varsa onu kullan (model lazy yüklenir, hata olursa say'e düşer),
    # hiç yoksa doğrudan macOS say. Her durumda ses yurt içinde kalır.
    if os.path.exists(s.piper_voice_path):
        return LocalPiperTTS()
    return MacSayTTS()
