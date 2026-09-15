"""Ses demosu aracının ağsız parçaları.

Sentez ve giriş HTTP ister; burada seçim mantığı, metin üretimi ve CLI
sözleşmesi doğrulanır — müşteriye giden metnin bozulmadan üretildiği garanti
altına alınsın diye.
"""
from __future__ import annotations

import pytest

from app.ops import voice_demo as vd


VOICES = [
    {"id": "axtmxCPnqPghs9C5SjJ8", "name": "Meloxia Turkish Pro", "labels": {"language": "tr"}},
    {"id": "EXAVITQu4vr4xnSDxMaL", "name": "Sarah - Mature, Reassuring", "labels": {}},
    {"id": "cgSgspJ2msm6clMCkdW9", "name": "Jessica - Playful, Bright", "labels": {}},
]


def test_voice_lookup_by_name_id_and_ambiguity():
    assert vd.pick_voice(VOICES, "meloxia")["id"] == "axtmxCPnqPghs9C5SjJ8"
    assert vd.pick_voice(VOICES, "axtmxCPnqPghs9C5SjJ8")["name"] == "Meloxia Turkish Pro"
    with pytest.raises(vd.ApiError, match="eşleşen ses yok"):
        vd.pick_voice(VOICES, "yokboyle")


def test_ambiguous_query_refuses_to_guess():
    twins = VOICES + [{"id": "x1", "name": "Meloxia Turkish Casual", "labels": {}}]
    with pytest.raises(vd.ApiError, match="birden fazla"):
        vd.pick_voice(twins, "meloxia")


def test_only_assistant_lines_are_synthesized_by_default():
    scenario = vd.SCENARIOS["randevu"]
    lines = vd.assistant_lines(scenario, iki_taraf=False)
    assert [i for i, _s, _t in lines] == [1, 3, 5, 7]
    assert {s for _i, s, _t in lines} == {"asistan"}
    assert len(vd.assistant_lines(scenario, iki_taraf=True)) == len(scenario["replikler"])


def test_transcript_carries_every_line_and_the_demo_disclaimer():
    scenario = vd.SCENARIOS["randevu"]
    settings = {"klinik": "demo-klinik", "ses_adi": "Meloxia Turkish Pro",
                "model": "eleven_multilingual_v2", "hiz": 1.0, "stability": 0.45,
                "style": 0.0, "tarih": "15.09.2026 15:29"}
    results = {1: {"dosya": "01-asistan.mp3", "ms": 1646, "bayt": 96174}}
    text = vd.build_transcript("randevu", scenario, settings, results)
    for _speaker, line in scenario["replikler"]:
        assert line in text
    assert "Meloxia Turkish Pro" in text and "Karşılayan asistan" in text
    # Müşteriye giden metin demo olduğunu kendi başına söylemeli.
    assert "gerçek bir arama yapılmamış" in text
    # Sesi üretilmemiş replikte dosya referansı olmamalı.
    assert text.count("🔊") == 1


def test_outgoing_scenario_is_labelled_as_the_caller_side():
    text = vd.build_transcript("giden-tanisma", vd.SCENARIOS["giden-tanisma"], {}, {})
    assert "Arayan asistan" in text


def test_cli_defaults_and_role_mapping():
    assert vd.SIDES == {"karsilayan": "receiver", "arayan": "caller"}
    assert set(vd.MODELS) == {"multilingual", "flash", "turbo"}
    assert all(m.startswith("eleven_") for m in vd.MODELS.values())
    # Her senaryonun tarafı geçerli olmalı, yoksa --kaydet yanlış role yazar.
    for key, scenario in vd.SCENARIOS.items():
        assert scenario["taraf"] in vd.SIDES, key
        assert scenario["replikler"][0][0] == "asistan", key


def test_listing_scenarios_needs_no_backend(capsys):
    assert vd.main(["--senaryolar"]) == 0
    out = capsys.readouterr().out
    assert "randevu" in out and "giden-tanisma" in out


def test_unreachable_backend_reports_clearly(monkeypatch, capsys):
    monkeypatch.setattr(vd, "login", lambda *_a, **_k: "token")
    def refuse(*_a, **_k):
        raise vd.ApiError("http://localhost:8000 adresine ulaşılamadı (Connection refused). Backend ayakta mı?")
    monkeypatch.setattr(vd, "request", refuse)
    assert vd.main(["--senaryo", "randevu", "--token", "t"]) == 1
    assert "Backend ayakta mı?" in capsys.readouterr().out
