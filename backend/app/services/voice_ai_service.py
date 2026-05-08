from __future__ import annotations

import io
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, status
from openai import OpenAI

from app.core.config import get_settings

ALLOWED_AUDIO_CONTENT_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/mp4",
    "audio/webm",
    "audio/ogg",
    "video/webm",
}
ALLOWED_AUDIO_SUFFIXES = {".wav", ".mp3", ".mp4", ".m4a", ".webm", ".ogg", ".oga"}


@dataclass(frozen=True)
class SpeechSynthesisResult:
    audio: bytes
    media_type: str
    filename: str
    provider: str


def _file_configured(*values: str) -> bool:
    return all(value and Path(value).exists() for value in values)


def whisper_cpp_configured() -> bool:
    settings = get_settings()
    return _file_configured(settings.whisper_cpp_binary, settings.whisper_cpp_model)


def piper_configured() -> bool:
    settings = get_settings()
    return _file_configured(settings.piper_binary, settings.piper_voice_model)


def _openai_voice_configured() -> bool:
    return bool(get_settings().openai_api_key.strip())


def voice_capabilities() -> dict:
    settings = get_settings()
    stt_provider = _select_stt_provider()
    tts_provider = _select_tts_provider()
    return {
        "stt": {
            "active_provider": stt_provider or "unconfigured",
            "preferred_provider": settings.speech_stt_provider,
            "local_whisper_cpp_configured": whisper_cpp_configured(),
            "openai_configured": _openai_voice_configured(),
            "offline_capable": whisper_cpp_configured(),
        },
        "tts": {
            "active_provider": tts_provider or "unconfigured",
            "preferred_provider": settings.speech_tts_provider,
            "local_piper_configured": piper_configured(),
            "openai_configured": _openai_voice_configured(),
            "offline_capable": piper_configured(),
        },
    }


def _select_stt_provider() -> str | None:
    settings = get_settings()
    preferred = settings.speech_stt_provider.strip().lower()
    if preferred in {"local", "whisper_cpp", "auto"} and whisper_cpp_configured():
        return "whisper_cpp"
    if preferred in {"openai", "auto"} and _openai_voice_configured():
        return "openai"
    return None


def _select_tts_provider() -> str | None:
    settings = get_settings()
    preferred = settings.speech_tts_provider.strip().lower()
    if preferred in {"local", "piper", "auto"} and piper_configured():
        return "piper"
    if preferred in {"openai", "auto"} and _openai_voice_configured():
        return "openai"
    return None


def transcribe_audio_bytes(
    *,
    audio_bytes: bytes,
    filename: str,
    content_type: str,
    language: str,
) -> tuple[str, str]:
    settings = get_settings()
    if not audio_bytes:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Ses dosyası boş.")
    if len(audio_bytes) > settings.max_voice_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Ses dosyası çok büyük.")

    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    suffix = Path(filename or "audio.webm").suffix.lower()
    if normalized_type and normalized_type not in ALLOWED_AUDIO_CONTENT_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Desteklenmeyen ses formatı.")
    if suffix and suffix not in ALLOWED_AUDIO_SUFFIXES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Desteklenmeyen ses dosya uzantısı.")

    provider = _select_stt_provider()
    if provider == "whisper_cpp":
        return _transcribe_with_whisper_cpp(audio_bytes=audio_bytes, filename=filename, language=language), provider
    if provider == "openai":
        return _transcribe_with_openai(
            audio_bytes=audio_bytes,
            filename=filename,
            content_type=content_type,
            language=language,
        ), provider

    raise HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "Ses tanıma sağlayıcısı hazır değil. Offline çalışmak için WHISPER_CPP_BINARY ve "
            "WHISPER_CPP_MODEL ayarlayın; bulut modu için OPENAI_API_KEY girin."
        ),
    )


def synthesize_speech_bytes(
    *, text: str, voice: str, speed: float, is_confirmation: bool = False
) -> SpeechSynthesisResult:
    text = text.strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Metin boş.")
    text = text[:4096]

    provider = _select_tts_provider()
    if provider == "piper":
        return _synthesize_with_piper(text=text)
    if provider == "openai":
        # Use higher-quality tts-1-hd for appointment confirmations where clarity matters
        return _synthesize_with_openai(text=text, voice=voice, speed=speed, hd=is_confirmation)

    raise HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "Ses sentezi sağlayıcısı hazır değil. Offline çalışmak için PIPER_BINARY ve "
            "PIPER_VOICE_MODEL ayarlayın; bulut modu için OPENAI_API_KEY girin."
        ),
    )


def _transcribe_with_openai(
    *,
    audio_bytes: bytes,
    filename: str,
    content_type: str,
    language: str,
) -> str:
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    try:
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=(filename, io.BytesIO(audio_bytes), content_type),
            language=language,
            response_format="text",
        )
        return result.strip() if isinstance(result, str) else str(result).strip()
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"Ses tanıma hatası: {exc}") from exc


def _transcribe_with_whisper_cpp(*, audio_bytes: bytes, filename: str, language: str) -> str:
    settings = get_settings()
    suffix = Path(filename or "audio.webm").suffix or ".webm"
    with tempfile.TemporaryDirectory(prefix="cognivault-stt-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        audio_path = tmp_path / f"input{suffix}"
        output_base = tmp_path / "transcript"
        audio_path.write_bytes(audio_bytes)

        command = [
            settings.whisper_cpp_binary,
            "-m",
            settings.whisper_cpp_model,
            "-f",
            str(audio_path),
            "-l",
            language,
            "-otxt",
            "-of",
            str(output_base),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
        if completed.returncode != 0:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                detail=f"Local Whisper.cpp hatası: {completed.stderr.strip() or completed.stdout.strip()}",
            )

        transcript_path = output_base.with_suffix(".txt")
        transcript = transcript_path.read_text(encoding="utf-8").strip() if transcript_path.exists() else completed.stdout.strip()
        if not transcript:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail="Local Whisper.cpp boş çıktı döndürdü.")
        return transcript


def _synthesize_with_openai(*, text: str, voice: str, speed: float, hd: bool = False) -> SpeechSynthesisResult:
    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)
    # tts-1-hd for confirmations (audibly better quality, ~2x latency)
    model = "tts-1-hd" if hd else "tts-1"
    try:
        response = client.audio.speech.create(
            model=model,
            voice=voice,  # type: ignore[arg-type]
            input=text,
            response_format="mp3",
            speed=max(0.25, min(4.0, speed)),
        )
        return SpeechSynthesisResult(
            audio=response.content,
            media_type="audio/mpeg",
            filename="speech.mp3",
            provider="openai",
        )
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"Ses sentezi hatası: {exc}") from exc


def _synthesize_with_piper(*, text: str) -> SpeechSynthesisResult:
    settings = get_settings()
    with tempfile.TemporaryDirectory(prefix="cognivault-tts-") as tmp_dir:
        output_path = Path(tmp_dir) / "speech.wav"
        command = [
            settings.piper_binary,
            "--model",
            settings.piper_voice_model,
            "--output_file",
            str(output_path),
        ]
        completed = subprocess.run(
            command,
            input=text,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if completed.returncode != 0 or not output_path.exists():
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                detail=f"Local Piper hatası: {completed.stderr.strip() or completed.stdout.strip()}",
            )
        return SpeechSynthesisResult(
            audio=output_path.read_bytes(),
            media_type="audio/wav",
            filename="speech.wav",
            provider="piper",
        )
