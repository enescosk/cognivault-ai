"""İP-3.7 — Enerji VAD testleri (saf-import, DB gerektirmez).

Koşum: pytest backend/tests/test_voice_vad.py --noconftest
"""

import json
import math

import pytest

from app.voice.turn_taking import TurnEvent, TurnTakingController
from app.voice.vad import (
    ARTIFACT_PATH,
    EnergyVad,
    EnergyVadConfig,
    build_report,
    render,
    rms_dbfs,
    write_artifact,
    zero_crossing_rate,
)

CFG = EnergyVadConfig()


def _tone(ms, amp=8000, freq=220.0, cfg=CFG):
    n = cfg.sample_rate * ms // 1000
    w = 2 * math.pi * freq / cfg.sample_rate
    return [int(amp * math.sin(w * i)) for i in range(n)]


def _sil(ms, cfg=CFG):
    return [0] * (cfg.sample_rate * ms // 1000)


def _hum(ms, amp=300, freq=60.0, cfg=CFG):
    n = cfg.sample_rate * ms // 1000
    w = 2 * math.pi * freq / cfg.sample_rate
    return [int(amp * math.sin(w * i)) for i in range(n)]


# ── DSP yardımcıları ────────────────────────────────────────────────────────
def test_rms_dbfs_silence_is_floor():
    assert rms_dbfs([0] * 320) == -100.0
    assert rms_dbfs([]) == -100.0


def test_rms_dbfs_known_amplitude():
    db = rms_dbfs(_tone(20, amp=8000))
    assert -16.5 < db < -14.0  # ~ -15.3 dBFS


def test_zero_crossing_rate():
    assert zero_crossing_rate([1, -1, 1, -1, 1]) == 1.0
    assert zero_crossing_rate([5] * 10) == 0.0
    assert zero_crossing_rate([7]) == 0.0


# ── VAD davranışı ───────────────────────────────────────────────────────────
def test_silence_never_speech():
    vad = EnergyVad()
    assert not any(vad.process(_sil(400)))


def test_loud_tone_is_speech_after_warmup():
    vad = EnergyVad()
    flags = vad.process(_hum(300) + _tone(400))  # uğultu warmup, sonra ton
    tone_flags = flags[300 // CFG.frame_ms :]
    assert sum(tone_flags) / len(tone_flags) >= 0.8


def test_constant_hum_is_tolerated():
    vad = EnergyVad()
    flags = vad.process(_hum(600))  # sabit arka-plan uğultusu
    assert sum(flags) / len(flags) <= 0.2


def test_config_validation():
    with pytest.raises(ValueError):
        EnergyVadConfig(sample_rate=0)


# ── VAD → turn-taking entegrasyonu ──────────────────────────────────────────
def test_vad_drives_turn_taking():
    vad = EnergyVad()
    ctrl = TurnTakingController()
    signal = _hum(300) + _tone(400) + _sil(700)  # warmup + konuşma + endpoint
    events = []
    for is_speech in vad.process(signal):
        events.extend(ctrl.process_frame(is_speech))
    assert TurnEvent.USER_TURN_START in events
    assert TurnEvent.USER_TURN_END in events


# ── Rapor + determinizm + artefakt ──────────────────────────────────────────
def test_report_gates_pass():
    report = build_report()
    assert report["overall_pass"] is True
    for g in report["gates"].values():
        assert g["pass"] is True
    assert "GEÇTİ" in render(report)


def test_report_is_deterministic():
    a = build_report()
    b = build_report()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_write_and_roundtrip(tmp_path):
    report = build_report()
    path = write_artifact(report, tmp_path / "vad.json")
    assert json.loads(path.read_text(encoding="utf-8")) == report


def test_committed_artifact_is_fresh():
    if not ARTIFACT_PATH.exists():
        pytest.skip("artefakt henüz üretilmemiş")
    committed = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    fresh = build_report()
    assert committed == fresh, "vad.json bayat — `python -m app.voice.vad` ile yenile"
