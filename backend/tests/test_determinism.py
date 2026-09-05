"""Kanıt artefaktlarının platformlar arası birebir kararlılığı.

Commit'lenen `data/*.json` panoları testlerde üreticinin çıktısıyla `==` ile
karşılaştırılıyor (bayatlama kapısı). Bu kapı ancak artefakt her makinede aynı
JSON'a serileşirse çalışır. `math` tabanlı metrikler libm farkları yüzünden son
bitte kayıyordu ve CI (Linux x86-64) macOS arm64'te üretilmiş artefaktı
reddediyordu:

    macOS arm64 : golden_ece = 0.24808362369337983
    Linux x86-64: golden_ece = 0.24808362369337997
"""
from __future__ import annotations

import json

from app.clinical.report import METRICS_ARTIFACT, build_dashboard
from app.core.determinism import ARTIFACT_FLOAT_DIGITS, stabilize_floats


def _floats(value, path="$"):
    """Yapıdaki tüm (yol, float) çiftlerini gezer."""
    if isinstance(value, bool):
        return
    if isinstance(value, float):
        yield path, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _floats(v, f"{path}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _floats(v, f"{path}[{i}]")


def test_stabilize_rounds_floats_at_every_depth():
    raw = {"a": 0.24808362369337983, "b": [{"c": 0.020854215391468915}], "d": (1.0 / 3,)}
    out = stabilize_floats(raw)
    assert out["a"] == 0.248083624
    assert out["b"][0]["c"] == 0.020854215
    assert out["d"] == [0.333333333]


def test_stabilize_leaves_non_floats_untouched():
    """bool Python'da int alt tipi — sayı gibi işlenip 1/0'a dönmemeli."""
    raw = {"ok": True, "off": False, "n": 42, "s": "0.5", "none": None}
    assert stabilize_floats(raw) == raw
    assert stabilize_floats(raw)["ok"] is True


def test_clinical_dashboard_has_no_platform_unstable_floats():
    """Panodaki hiçbir float 9 basamağın ötesinde hassasiyet taşımamalı."""
    offenders = [
        (path, value)
        for path, value in _floats(build_dashboard())
        if round(value, ARTIFACT_FLOAT_DIGITS) != value
    ]
    assert offenders == [], f"yuvarlanmamış float'lar artefaktı platforma bağımlı yapar: {offenders}"


def test_committed_metrics_artifact_is_platform_stable():
    """Commit'lenmiş artefakt da yuvarlanmış olmalı (bayat üretici yakalanır)."""
    committed = json.loads(METRICS_ARTIFACT.read_text(encoding="utf-8"))
    offenders = [
        (path, value)
        for path, value in _floats(committed)
        if round(value, ARTIFACT_FLOAT_DIGITS) != value
    ]
    assert offenders == [], f"artefakt yuvarlanmamış float içeriyor: {offenders}"


def test_rounding_does_not_move_any_quality_gate():
    """Yuvarlama kapı kararlarını değiştirmemeli — hassasiyet raporlananın çok üstünde."""
    dashboard = build_dashboard()
    cal = dashboard["metrics"]["calibration_ece"]
    emg = dashboard["metrics"]["emergency_recall"]

    assert dashboard["overall_pass"] is True
    assert cal["pass"] is True and cal["test_ece"] < cal["target"]
    assert emg["missed"] == 0
    # Raporlar 4 basamak gösteriyor; 9 basamağa yuvarlama görünen değeri korur.
    assert f"{cal['test_ece']:.4f}" == "0.0209"
