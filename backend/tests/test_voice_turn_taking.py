"""İP-3.7 — Turn-taking / barge-in durum makinesi testleri (saf-import, DB gerektirmez).

Koşum: pytest backend/tests/test_voice_turn_taking.py --noconftest
"""

import json

import pytest

from app.voice.turn_taking import (
    ARTIFACT_PATH,
    TurnEvent,
    TurnState,
    TurnTakingConfig,
    TurnTakingController,
    build_report,
    render,
    write_artifact,
)


def _spk(ms, frame_ms=20):
    return [True] * (ms // frame_ms)


def _sil(ms, frame_ms=20):
    return [False] * (ms // frame_ms)


# ── Onset debounce (gürültü toleransı) ──────────────────────────────────────
def test_short_blip_never_starts_turn():
    c = TurnTakingController()
    events = c.process_stream(_spk(100) + _sil(200))  # 100ms < 120ms onset
    assert events == []
    assert c.state == TurnState.LISTENING


def test_onset_threshold_starts_turn():
    c = TurnTakingController()
    events = c.process_stream(_spk(120))  # tam onset
    assert TurnEvent.USER_TURN_START in events
    assert c.state == TurnState.USER_SPEAKING


# ── Geçerli söylem: start + endpoint ────────────────────────────────────────
def test_real_utterance_start_and_end():
    c = TurnTakingController()
    events = c.process_stream(_spk(400) + _sil(700))
    assert events == [TurnEvent.USER_TURN_START, TurnEvent.USER_TURN_END]
    assert c.state == TurnState.LISTENING


def test_pause_shorter_than_endpoint_keeps_turn():
    c = TurnTakingController()
    # 400ms konuşma + 400ms duraklama (<600) + 400ms konuşma + endpoint
    events = c.process_stream(_spk(400) + _sil(400) + _spk(400) + _sil(700))
    assert events.count(TurnEvent.USER_TURN_START) == 1
    assert events.count(TurnEvent.USER_TURN_END) == 1


# ── Min-utterance: kısa söylem gürültü ──────────────────────────────────────
def test_too_short_utterance_is_noise():
    c = TurnTakingController()
    events = c.process_stream(_spk(160) + _sil(700))  # onset geçer ama voiced 160<200
    assert events == [TurnEvent.USER_TURN_START, TurnEvent.NOISE_IGNORED]


# ── Barge-in ────────────────────────────────────────────────────────────────
def test_barge_in_during_agent_speech():
    c = TurnTakingController()
    c.agent_speaking_started()
    events = c.process_stream(_sil(100) + _spk(300))  # 300ms > 200ms barge eşiği
    assert TurnEvent.BARGE_IN in events
    assert c.state == TurnState.USER_SPEAKING


def test_short_speech_during_agent_no_barge():
    c = TurnTakingController()
    c.agent_speaking_started()
    events = c.process_stream(_spk(100) + _sil(200))  # 100ms < 200ms barge
    assert TurnEvent.BARGE_IN not in events
    assert c.state == TurnState.AGENT_SPEAKING


def test_agent_natural_stop_emits_agent_turn_end():
    c = TurnTakingController()
    c.agent_speaking_started()
    c.process_stream(_sil(200))
    assert c.agent_speaking_stopped() == [TurnEvent.AGENT_TURN_END]
    assert c.state == TurnState.LISTENING


def test_agent_stop_after_barge_in_no_agent_turn_end():
    c = TurnTakingController()
    c.agent_speaking_started()
    c.process_stream(_sil(100) + _spk(300))  # barge-in → USER_SPEAKING
    assert c.agent_speaking_stopped() == []  # ajan turu zaten kesildi


# ── Max-utterance güvenlik tavanı ───────────────────────────────────────────
def test_max_utterance_force_ends():
    cfg = TurnTakingConfig(max_utterance_ms=400, endpoint_ms=10000)
    c = TurnTakingController(cfg)
    events = c.process_stream(_spk(2000))  # kesintisiz uzun konuşma
    assert TurnEvent.USER_TURN_END in events
    assert c.state == TurnState.LISTENING


# ── Config doğrulama ────────────────────────────────────────────────────────
def test_config_rejects_non_positive():
    with pytest.raises(ValueError):
        TurnTakingConfig(frame_ms=0)
    with pytest.raises(ValueError):
        TurnTakingConfig(onset_ms=-20)


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
    path = write_artifact(report, tmp_path / "turn_taking.json")
    assert json.loads(path.read_text(encoding="utf-8")) == report


def test_committed_artifact_is_fresh():
    if not ARTIFACT_PATH.exists():
        pytest.skip("artefakt henüz üretilmemiş")
    committed = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    fresh = build_report()
    assert committed == fresh, "turn_taking.json bayat — `python -m app.voice.turn_taking` ile yenile"
