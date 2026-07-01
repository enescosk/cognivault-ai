"""Üst-düzey teknik hazırlık kanıt panosu testleri (saf-import, DB gerektirmez).

Koşum: pytest backend/tests/test_evidence.py --noconftest
"""

import json

from app import evidence
from app.evidence import _count_gates, build_readiness, main, render


# ── Genel kapı sayacı ───────────────────────────────────────────────────────
def test_count_gates_generic():
    obj = {
        "gates": {"a": {"pass": True}, "b": {"pass": False}},
        "overall_pass": True,  # 'pass' değil → sayılmaz
        "nested": [{"pass": True}, {"x": {"pass": True}}],
    }
    passed, total = _count_gates(obj)
    assert total == 4
    assert passed == 3


def test_count_gates_empty():
    assert _count_gates({}) == (0, 0)
    assert _count_gates([]) == (0, 0)


# ── Konsolide pano ──────────────────────────────────────────────────────────
def test_all_packages_present_and_pass():
    report = build_readiness()
    assert len(report["packages"]) == len(evidence.PANELS)
    for p in report["packages"]:
        assert p["status"] == "ok", f"{p['ip']} → {p['status']}"
        assert p["overall_pass"] is True, f"{p['ip']} panosu kaldı"
        assert p["gates_total"] > 0


def test_overall_pass_true():
    report = build_readiness()
    assert report["overall_pass"] is True
    s = report["summary"]
    assert s["panels_passed"] == s["panels"]
    assert s["gates_passed"] == s["gates_total"]
    # özet, paket toplamlarıyla tutarlı
    assert s["gates_total"] == sum(p["gates_total"] for p in report["packages"])


def test_render_contains_verdict():
    assert "GENEL TEKNİK HAZIRLIK: GEÇTİ" in render(build_readiness())


def test_deterministic():
    a = build_readiness()
    b = build_readiness()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_cli_exit_zero_when_all_pass():
    assert main(["--no-save"]) == 0


# ── Dayanıklılık: bir alt-pano bozulursa pano çökmez, o paket kalır ──────────
def test_broken_panel_fails_gracefully(monkeypatch):
    bad = evidence.PANELS + [("İP-X", "kasıtlı bozuk", "app.does_not_exist", "build_report")]
    monkeypatch.setattr(evidence, "PANELS", bad)
    report = build_readiness()
    broken = report["packages"][-1]
    assert broken["status"].startswith("error")
    assert broken["overall_pass"] is False
    assert report["overall_pass"] is False  # bir paket bile kalırsa genel kalır
