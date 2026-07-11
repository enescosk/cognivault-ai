"""Dış ses rıza kapısı (KVKK sınır-ötesi) testleri.

Saf-import; `--noconftest` ile koşar. Ağ yok — yalnızca kapı mantığı ve
provider seçimi doğrulanır (bulut sınıfları instantiate edilir ama çağrılmaz).
"""

import json
from pathlib import Path
import subprocess
import sys

import pytest

from app.ai.voice_factory import external_voice_permitted
from app.ai.voice_routing import ARTIFACT_PATH, build_report


# ── Kapı doğruluk tablosu ────────────────────────────────────────────────────


def test_all_three_conditions_required():
    assert external_voice_permitted(
        external_enabled=True, consent_granted=True, has_credentials=True
    ) is True


@pytest.mark.parametrize(
    "ext,consent,creds",
    [
        (False, False, False),
        (True, False, False),
        (False, True, False),
        (False, False, True),
        (True, True, False),
        (True, False, True),
        (False, True, True),
    ],
)
def test_missing_any_condition_denies(ext, consent, creds):
    assert external_voice_permitted(
        external_enabled=ext, consent_granted=consent, has_credentials=creds
    ) is False


def test_default_is_denied():
    # Argümansız gerçek dünyada hepsi False varsayılır → yerel.
    assert external_voice_permitted(
        external_enabled=False, consent_granted=False, has_credentials=False
    ) is False


# ── Provider seçimi (monkeypatch'li ayarlar, ağ yok) ─────────────────────────


class _FakeSettings:
    voice_stt_provider = "elevenlabs"
    voice_tts_provider = "elevenlabs"
    voice_external_enabled = True
    openai_api_key = "sk-test"
    elevenlabs_api_key = "el-test"
    elevenlabs_voice_id = "voice-1"
    elevenlabs_tts_model = "eleven_flash_v2_5"
    elevenlabs_stt_model = "scribe_v2_realtime"
    piper_voice_path = "/nonexistent/piper.onnx"
    local_llm_timeout = 5.0


def test_stt_stays_local_without_consent(monkeypatch):
    from app.ai import voice_factory

    monkeypatch.setattr(voice_factory, "get_settings", lambda: _FakeSettings())
    provider = voice_factory.get_stt_provider(external_transfer_allowed=True, consent_granted=False)
    assert provider.__class__.__name__ == "LocalWhisperSTT"


def test_stt_routes_to_elevenlabs_with_full_gate(monkeypatch):
    from app.ai import voice_factory

    monkeypatch.setattr(voice_factory, "get_settings", lambda: _FakeSettings())
    provider = voice_factory.get_stt_provider(external_transfer_allowed=True, consent_granted=True)
    assert provider.__class__.__name__ == "ElevenLabsScribeSTT"


def test_tts_stays_local_without_consent(monkeypatch):
    from app.ai import voice_factory

    monkeypatch.setattr(voice_factory, "get_settings", lambda: _FakeSettings())
    provider = voice_factory.get_tts_provider(external_transfer_allowed=True, consent_granted=False)
    assert provider.__class__.__name__ in {"LocalPiperTTS", "MacSayTTS"}


def test_tts_routes_to_elevenlabs_with_full_gate(monkeypatch):
    from app.ai import voice_factory

    monkeypatch.setattr(voice_factory, "get_settings", lambda: _FakeSettings())
    provider = voice_factory.get_tts_provider(external_transfer_allowed=True, consent_granted=True)
    assert provider.__class__.__name__ == "ElevenLabsTTS"


def test_tts_without_voice_id_stays_local(monkeypatch):
    from app.ai import voice_factory

    class NoVoiceId(_FakeSettings):
        elevenlabs_voice_id = ""

    monkeypatch.setattr(voice_factory, "get_settings", lambda: NoVoiceId())
    provider = voice_factory.get_tts_provider(external_transfer_allowed=True, consent_granted=True)
    assert provider.__class__.__name__ in {"LocalPiperTTS", "MacSayTTS"}


# ── Rapor ────────────────────────────────────────────────────────────────────


def test_report_all_gates_pass():
    report = build_report()
    for key, gate in report["gates"].items():
        assert gate["pass"], f"kapı düştü: {key} → {gate}"
    assert report["overall_pass"] is True
    assert len(report["truth_table"]) == 8


def test_report_is_deterministic():
    a = json.dumps(build_report(), ensure_ascii=False, sort_keys=True)
    b = json.dumps(build_report(), ensure_ascii=False, sort_keys=True)
    assert a == b


def test_committed_artifact_is_fresh():
    committed = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    assert committed == build_report()


def test_cli_smoke_exits_zero():
    proc = subprocess.run(
        [sys.executable, "-m", "app.ai.voice_routing", "--no-save", "--json"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["overall_pass"] is True
