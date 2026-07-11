"""Lokal ses yığını (Piper/Whisper) yardımcıları — model dosyası çözünürlüğü ve warm-up.

Gerçek model yüklemez; dosya-sistemi çözünürlüğünü ve "hata asla yükseltmez"
sözleşmesini doğrular. `--noconftest` ile de koşar (saf import).
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from app.ai import voice_factory
from app.core.config import get_settings


@pytest.fixture()
def settings():
    s = get_settings()
    original = (
        s.piper_voice_path,
        list(s.piper_voice_fallbacks),
        s.voice_warmup_enabled,
        s.voice_stt_provider,
        s.voice_tts_provider,
    )
    yield s
    (
        s.piper_voice_path,
        s.piper_voice_fallbacks,
        s.voice_warmup_enabled,
        s.voice_stt_provider,
        s.voice_tts_provider,
    ) = original


def test_resolve_prefers_configured_path(settings, tmp_path):
    preferred = tmp_path / "tr_TR-fahrettin-medium.onnx"
    fallback = tmp_path / "tr_TR-dfki-medium.onnx"
    preferred.write_bytes(b"onnx")
    fallback.write_bytes(b"onnx")
    settings.piper_voice_path = str(preferred)
    settings.piper_voice_fallbacks = [str(fallback)]
    assert voice_factory.resolve_piper_voice_path() == str(preferred)


def test_resolve_falls_back_when_preferred_missing(settings, tmp_path):
    fallback = tmp_path / "tr_TR-dfki-medium.onnx"
    fallback.write_bytes(b"onnx")
    settings.piper_voice_path = str(tmp_path / "yok.onnx")
    settings.piper_voice_fallbacks = [str(fallback)]
    assert voice_factory.resolve_piper_voice_path() == str(fallback)


def test_resolve_returns_none_when_no_voice_on_disk(settings, tmp_path):
    settings.piper_voice_path = str(tmp_path / "yok.onnx")
    settings.piper_voice_fallbacks = [str(tmp_path / "yok2.onnx")]
    assert voice_factory.resolve_piper_voice_path() is None


def test_tts_provider_uses_fallback_voice_file(settings, tmp_path):
    """Tercih edilen ses inmemişse (eski kurulum) Piper yine seçilmeli."""
    fallback = tmp_path / "tr_TR-dfki-medium.onnx"
    fallback.write_bytes(b"onnx")
    settings.piper_voice_path = str(tmp_path / "yok.onnx")
    settings.piper_voice_fallbacks = [str(fallback)]
    settings.voice_tts_provider = "local"
    provider = voice_factory.get_tts_provider()
    assert isinstance(provider, voice_factory.LocalPiperTTS)


def test_tts_provider_macsay_when_no_voice_files(settings, tmp_path):
    settings.piper_voice_path = str(tmp_path / "yok.onnx")
    settings.piper_voice_fallbacks = []
    settings.voice_tts_provider = "local"
    provider = voice_factory.get_tts_provider()
    assert isinstance(provider, voice_factory.MacSayTTS)


def test_warmup_disabled_is_noop(settings, monkeypatch):
    settings.voice_warmup_enabled = False
    called = []
    monkeypatch.setattr(voice_factory, "_get_whisper", lambda: called.append("w"))
    monkeypatch.setattr(voice_factory, "_get_piper", lambda: called.append("p"))
    voice_factory.warm_up_local_voice_stack()
    time.sleep(0.05)
    assert called == []


def test_warmup_never_raises_when_models_fail(settings, monkeypatch, tmp_path):
    """Ses bağımlılığı kurulmamış ortamda açılış asla çökmemeli."""
    settings.voice_warmup_enabled = True
    settings.voice_stt_provider = "local"
    settings.voice_tts_provider = "local"
    voice_file = tmp_path / "v.onnx"
    voice_file.write_bytes(b"onnx")
    settings.piper_voice_path = str(voice_file)

    def boom():
        raise ModuleNotFoundError("faster_whisper yok")

    monkeypatch.setattr(voice_factory, "_get_whisper", boom)
    monkeypatch.setattr(voice_factory, "_get_piper", boom)
    voice_factory.warm_up_local_voice_stack()  # exception thread'de yutulur
    deadline = time.time() + 2
    while time.time() < deadline:
        time.sleep(0.02)  # thread'in koşması için küçük pencere
        break


def test_warmup_loads_local_models(settings, monkeypatch, tmp_path):
    settings.voice_warmup_enabled = True
    settings.voice_stt_provider = "local"
    settings.voice_tts_provider = "local"
    voice_file = tmp_path / "v.onnx"
    voice_file.write_bytes(b"onnx")
    settings.piper_voice_path = str(voice_file)

    loaded: list[str] = []
    monkeypatch.setattr(voice_factory, "_get_whisper", lambda: loaded.append("whisper"))
    monkeypatch.setattr(voice_factory, "_get_piper", lambda: loaded.append("piper"))
    voice_factory.warm_up_local_voice_stack()
    deadline = time.time() + 2
    while time.time() < deadline and len(loaded) < 2:
        time.sleep(0.02)
    assert sorted(loaded) == ["piper", "whisper"]


def test_whisper_confidence_estimate_uses_segment_quality():
    strong = [
        SimpleNamespace(start=0.0, end=1.0, avg_logprob=-0.05, no_speech_prob=0.02),
        SimpleNamespace(start=1.0, end=2.0, avg_logprob=-0.10, no_speech_prob=0.03),
    ]
    weak = [
        SimpleNamespace(start=0.0, end=1.0, avg_logprob=-1.2, no_speech_prob=0.35),
    ]

    strong_conf = voice_factory._estimate_whisper_confidence(strong)
    weak_conf = voice_factory._estimate_whisper_confidence(weak)

    assert strong_conf is not None and strong_conf > 0.85
    assert weak_conf is not None and weak_conf < strong_conf


def test_whisper_duration_prefers_decoder_info():
    info = SimpleNamespace(duration=4.25)
    segments = [SimpleNamespace(end=2.0)]
    assert voice_factory._whisper_duration_seconds(segments, info) == 4.25
