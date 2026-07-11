"""Ses sağlayıcı soyutlaması — STT (konuşma→metin) ve TTS (metin→konuşma).

KVKK local-first ilkesi: varsayılan olarak ses verisi yurt içinde, tamamen
cihaz/sunucu üzerinde işlenir. Bulut sağlayıcılar (OpenAI) yalnızca
`voice_external_enabled=True` VE provider açıkça "openai" seçildiği VE arayanın
ilettiği klinik-seviyesi sınır-ötesi rıza (`allow_cross_border_processors`) açık
olduğunda devreye girer. Aksi halde ses verisi hiçbir koşulda dışarı çıkmaz.

- STT: faster-whisper (CTranslate2, lokal). webm/opus dahil PyAV ile çözülür.
- TTS: Piper (nöral, tr_TR). Piper yüklenemezse macOS `say -v Yelda` (yine lokal).
       Her ikisi de WAV döndürür.
"""
from __future__ import annotations

import io
import logging
import math
import os
import subprocess
import tempfile
import threading
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.config import get_settings

logger = logging.getLogger("cognivault.voice")


@dataclass(frozen=True)
class TranscriptionResult:
    text: str
    confidence: float | None = None
    duration_seconds: float | None = None
    segments: int | None = None


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

    def transcribe_detailed(self, audio: bytes, language: str = "tr") -> TranscriptionResult:
        """Geriye uyumlu detaylı çıktı.

        Premium/provider SDK'ları farklı telemetry döndürür; temel sözleşme her
        sağlayıcı için metni korur, sağlayıcı destekliyorsa confidence/süre ekler.
        """
        return TranscriptionResult(text=self.transcribe(audio, language=language))


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
    """faster-whisper — ses sunucudan çıkmadan yurt içinde çözülür.

    Decode ayarları canlı sesli görüşme için seçildi:
    - `vad_filter`: baştaki/sondaki sessizliği atar → hem hız hem doğruluk.
    - `temperature=0` + `beam_size=5`: deterministik, en olası çözüm.
    - `condition_on_previous_text=False`: kısa tek-tur söylemlerde halüsinasyon
      sürüklenmesini engeller (önceki segment yanlışsa devamını zehirlemesin).
    - `initial_prompt`: diş kliniği alan sözlüğü — "ağrıyor→ağırıyor" gibi
      yakın-ses hatalarını azaltır.
    """

    def transcribe(self, audio: bytes, language: str = "tr") -> str:
        return self.transcribe_detailed(audio, language=language).text

    def transcribe_detailed(self, audio: bytes, language: str = "tr") -> TranscriptionResult:
        s = get_settings()
        model = _get_whisper()
        segments, _info = model.transcribe(
            io.BytesIO(audio),
            language=language or s.local_whisper_language or None,
            beam_size=5,
            temperature=0.0,
            vad_filter=True,
            condition_on_previous_text=False,
            initial_prompt=s.local_whisper_initial_prompt or None,
        )
        segment_list = list(segments)
        text = "".join(seg.text for seg in segment_list).strip()
        return TranscriptionResult(
            text=text,
            confidence=_estimate_whisper_confidence(segment_list) if text else 0.0,
            duration_seconds=_whisper_duration_seconds(segment_list, _info),
            segments=len(segment_list),
        )


def _estimate_whisper_confidence(segments: list[object]) -> float | None:
    if not segments:
        return None
    weighted = 0.0
    total_weight = 0.0
    for seg in segments:
        start = float(getattr(seg, "start", 0.0) or 0.0)
        end = float(getattr(seg, "end", start) or start)
        weight = max(0.05, end - start)
        avg_logprob = getattr(seg, "avg_logprob", None)
        no_speech_prob = getattr(seg, "no_speech_prob", None)
        if avg_logprob is None:
            continue
        acoustic = math.exp(min(0.0, float(avg_logprob)))
        speech = 1.0 - max(0.0, min(1.0, float(no_speech_prob or 0.0)))
        weighted += max(0.0, min(1.0, acoustic * speech)) * weight
        total_weight += weight
    if total_weight <= 0:
        return None
    return round(weighted / total_weight, 3)


def _whisper_duration_seconds(segments: list[object], info: object) -> float | None:
    duration = getattr(info, "duration", None)
    if isinstance(duration, (int, float)) and duration > 0:
        return round(float(duration), 3)
    ends = [float(getattr(seg, "end", 0.0) or 0.0) for seg in segments]
    if not ends:
        return None
    return round(max(ends), 3)


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


def get_stt_provider(
    external_transfer_allowed: bool = False,
    *,
    consent_granted: bool = False,
    provider_name: str | None = None,
    external_enabled: bool | None = None,
) -> STTProvider:
    """Local-first: buluta yalnızca sağlayıcıya özel rıza kapısı geçilirse gidilir.

    Her bulut sağlayıcı için üç kapı gerekir: app-seviyesi dış işleme izni,
    hasta VOICE_RECORDING rızası ve sağlayıcı kimlik bilgisi. OpenAI yolunda
    ayrıca klinik-seviyesi sınır-ötesi rıza (`external_transfer_allowed`,
    `allow_cross_border_processors`) da gerekir.

    Her iki kapı de sağlanmazsa her zaman yerel Whisper.
    """
    s = get_settings()
    selected_provider = provider_name or s.voice_stt_provider
    effective_external_enabled = s.voice_external_enabled and (
        s.voice_external_enabled if external_enabled is None else external_enabled
    )
    if selected_provider == "elevenlabs" and external_voice_permitted(
        external_enabled=effective_external_enabled,
        consent_granted=consent_granted,
        has_credentials=bool(s.elevenlabs_api_key),
    ) and external_transfer_allowed:
        return ElevenLabsScribeSTT()
    if (
        selected_provider == "openai"
        and external_voice_permitted(
            external_enabled=effective_external_enabled,
            consent_granted=consent_granted,
            has_credentials=bool(s.openai_api_key),
        )
        and external_transfer_allowed
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


def resolve_piper_voice_path() -> str | None:
    """Kullanılacak Piper ses dosyasını belirler.

    Öncelik: yapılandırılan `piper_voice_path` → `piper_voice_fallbacks` sırası.
    Hiçbiri diskte yoksa None (çağıran MacSay'e düşer). Böylece daha doğal bir
    ses indirildiğinde otomatik kullanılır, indirilmemiş kurulum eski sesle
    çalışmaya devam eder.
    """
    s = get_settings()
    fallback_paths = getattr(s, "piper_voice_fallbacks", []) or []
    for candidate in [s.piper_voice_path, *fallback_paths]:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def _get_piper():
    global _piper_voice
    if _piper_voice is None:
        with _piper_lock:
            if _piper_voice is None:
                from piper import PiperVoice

                path = resolve_piper_voice_path()
                if path is None:
                    raise FileNotFoundError("Piper ses dosyası bulunamadı")
                logger.info("Loading local Piper voice: %s", path)
                _piper_voice = PiperVoice.load(path)
    return _piper_voice


def _piper_synthesis_config():
    """Settings'teki prosodi ayarlarından SynthesisConfig üretir (hepsi None → None)."""
    s = get_settings()
    if s.piper_length_scale is None and s.piper_noise_scale is None and s.piper_noise_w_scale is None:
        return None
    from piper.config import SynthesisConfig

    return SynthesisConfig(
        length_scale=s.piper_length_scale,
        noise_scale=s.piper_noise_scale,
        noise_w_scale=s.piper_noise_w_scale,
    )


class LocalPiperTTS(TTSProvider):
    """Piper nöral TTS (tr_TR) — ses yurt içinde üretilir. Piper yüklenemezse
    macOS `say`'e düşer (yine lokal); böylece local-first garantisi korunur."""

    def synthesize(self, text: str, voice: str | None = None) -> tuple[bytes, str]:
        try:
            v = _get_piper()
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                v.synthesize_wav(text, wf, syn_config=_piper_synthesis_config())
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


def get_tts_provider(
    external_transfer_allowed: bool = False,
    *,
    consent_granted: bool = False,
    provider_name: str | None = None,
    external_enabled: bool | None = None,
) -> TTSProvider:
    """Local-first: bulut TTS yalnızca sağlayıcıya özel rıza kapısı geçilirse.

    Her bulut sağlayıcı için app-seviyesi dış izin, hasta VOICE_RECORDING
    rızası ve kimlik bilgisi gerekir. OpenAI için klinik-seviyesi sınır-ötesi
    rıza da zorunludur.

    Aksi halde önce Piper, yoksa macOS `say` — ses yurt içinde kalır."""
    s = get_settings()
    selected_provider = provider_name or s.voice_tts_provider
    effective_external_enabled = s.voice_external_enabled and (
        s.voice_external_enabled if external_enabled is None else external_enabled
    )
    if selected_provider == "elevenlabs" and external_voice_permitted(
        external_enabled=effective_external_enabled,
        consent_granted=consent_granted,
        has_credentials=bool(s.elevenlabs_api_key and s.elevenlabs_voice_id),
    ) and external_transfer_allowed:
        return ElevenLabsTTS()
    if (
        selected_provider == "openai"
        and external_voice_permitted(
            external_enabled=effective_external_enabled,
            consent_granted=consent_granted,
            has_credentials=bool(s.openai_api_key),
        )
        and external_transfer_allowed
    ):
        return OpenAITTS()
    # Lokal: Piper varsa onu kullan (model lazy yüklenir, hata olursa say'e düşer),
    # hiç yoksa doğrudan macOS say. Her durumda ses yurt içinde kalır.
    if resolve_piper_voice_path() is not None:
        return LocalPiperTTS()
    return MacSayTTS()


# ─────────────────────────────────────────────────────────────────────────────
# Warm-up — ilk sesli turdaki model-yükleme takılmasını yok eder
# ─────────────────────────────────────────────────────────────────────────────
def warm_up_local_voice_stack() -> None:
    """Lokal STT/TTS modellerini arka plan thread'inde önceden yükler.

    Whisper-small yüklemesi ~2 sn, Piper ~1 sn; lazy bırakılırsa bu maliyet
    ilk hastanın ilk sesli turuna biner. Uygulama açılışında (lifespan) çağrılır;
    hata asla yükseltilmez — ses bağımlılıkları kurulu olmayan ortamlarda
    uygulama normal açılır, ilgili çağrı yolu zaten kendi fallback'ini uygular.
    """
    s = get_settings()
    if not s.voice_warmup_enabled:
        return

    def _load() -> None:
        if s.voice_stt_provider == "local":
            try:
                _get_whisper()
                logger.info("voice_warmup whisper=ready")
            except Exception as e:  # noqa: BLE001
                logger.warning("voice_warmup whisper failed: %s", e)
        if s.voice_tts_provider == "local" and resolve_piper_voice_path() is not None:
            try:
                _get_piper()
                logger.info("voice_warmup piper=ready")
            except Exception as e:  # noqa: BLE001
                logger.warning("voice_warmup piper failed: %s", e)

    threading.Thread(target=_load, name="voice-warmup", daemon=True).start()
