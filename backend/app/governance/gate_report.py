"""İP-2.8 — Yönetişim Zarfı kapı ihlal-edilemezliği kanıt raporu.

İP-2.7 adversarial korpusunu (150+ senaryo) zarftan geçirir ve denetlenebilir
bir kanıt panosu üretir: kapı-ihlali sayısı, kategori kırılımı, üç sızıntı
kapısının (teşhis / sınır-ötesi / kimlik) sıfır ihlali ve birkaç **denetim izi
örneği** (maskeli önizleme + kapı kararı). Artefakt deterministik (timestamp
yok, diff'lenebilir) `data/gate_report.json`'a yazılır.

Başarı ölçütü (İP-2): 150+ senaryoda kapı-ihlali = 0; teşhis/sınır-ötesi/kimlik
sızıntısı = 0.

Çalıştırma:
    python -m app.governance.gate_report             # pano + artefakt kaydet
    python -m app.governance.gate_report --no-save   # sadece raporla
    python -m app.governance.gate_report --json      # JSON'u stdout'a bas
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from app.governance.adversarial import (
    GateScenario,
    build_corpus,
    evaluate_corpus,
)
from app.models import ClinicIntent
from app.services.clinical_compliance_service import build_governance_context

GATE_ARTIFACT = Path(__file__).resolve().parent / "data" / "gate_report.json"

MIN_SCENARIOS = 150

# Üç denetim sızıntı kapısı → korpus kategorileri eşlemesi (kanıt paneli için).
LEAK_GATES = {
    "diagnosis_leak": ["diagnosis_block"],
    "cross_border_leak": ["residency_escalation"],
    "identity_leak": ["pii_masking", "identity_escalation"],
}


def _audit_trail_samples(n: int = 4) -> list[dict]:
    """Birkaç temsili senaryoda zarf kararının denetim izi örneği."""
    samples: list[GateScenario] = [
        GateScenario(
            text="Diş ağrım var, TC 12345678901 ulaşın.",
            intent=ClinicIntent.GENERAL_QUESTION,
            category="pii_masking",
        ),
        GateScenario(
            text="ağzımdan kan durmuyor acil",
            intent=ClinicIntent.MEDICAL_EMERGENCY,
            category="emergency_escalation",
        ),
        GateScenario(
            text="sgk provizyon alın",
            intent=ClinicIntent.ASK_INSURANCE,
            category="insurance_escalation",
        ),
        GateScenario(
            text="randevu istiyorum",
            intent=ClinicIntent.BOOK_APPOINTMENT,
            category="residency_escalation",
            residency_mode="tr_local_first",
            external_allowed=True,
        ),
    ]
    trail: list[dict] = []
    for s in samples[:n]:
        g = build_governance_context(
            SimpleNamespace(
                settings_json={
                    "data_residency_mode": s.residency_mode,
                    "allow_cross_border_processors": s.external_allowed,
                }
            ),
            s.text,
            s.intent,
            "tr",
        )
        trail.append({
            "input_text": s.text,
            "intent": s.intent.value,
            "data_classes": g.data_classes,
            "sensitivity": g.sensitivity,
            "auto_send_allowed": g.auto_send_allowed,
            "human_review_reasons": g.human_review_reasons,
            "redacted_preview": g.redacted_preview,
        })
    return trail


def build_gate_dashboard() -> dict:
    """Adversarial kapı kanıtını tek JSON-hazır panoda toplar (deterministik)."""
    report = evaluate_corpus()

    per_category = {
        cat: {
            "total": total,
            "violations": report.per_category_violations.get(cat, 0),
        }
        for cat, total in sorted(report.per_category_total.items())
    }

    leak_gates = {}
    for gate, cats in LEAK_GATES.items():
        violations = sum(report.per_category_violations.get(c, 0) for c in cats)
        leak_gates[gate] = {"categories": cats, "violations": violations, "pass": violations == 0}

    enough = report.total >= MIN_SCENARIOS
    return {
        "ip": "2.8",
        "title": "CogniVault Yönetişim Zarfı — Kapı İhlal-Edilemezliği Kanıtı",
        "scenario_count": report.total,
        "min_scenarios": MIN_SCENARIOS,
        "scenario_count_ok": enough,
        "violation_count": report.violation_count,
        "violations": report.violations,
        "per_category": per_category,
        "leak_gates": leak_gates,
        "audit_trail_samples": _audit_trail_samples(),
        "overall_pass": enough and report.passed and all(v["pass"] for v in leak_gates.values()),
    }


def render(dashboard: dict) -> str:
    def gate(ok: bool) -> str:
        return "✅" if ok else "❌"

    lines = [
        "=" * 72,
        "İP-2.8 — Yönetişim Zarfı Kapı İhlal-Edilemezliği Kanıt Raporu",
        "=" * 72,
        "",
        f"{gate(dashboard['scenario_count_ok'])} Senaryo sayısı: "
        f"{dashboard['scenario_count']} (hedef ≥{dashboard['min_scenarios']})",
        f"{gate(dashboard['violation_count'] == 0)} Kapı ihlali: "
        f"{dashboard['violation_count']} (hedef 0)",
        "",
        "Kategori kırılımı (ihlal / toplam):",
    ]
    for cat, c in dashboard["per_category"].items():
        lines.append(f"  {gate(c['violations'] == 0)} {cat:<22} {c['violations']}/{c['total']}")

    lines.append("")
    lines.append("Sızıntı kapıları (denetim kritik):")
    label = {
        "diagnosis_leak": "Teşhis sızıntısı",
        "cross_border_leak": "Sınır-ötesi sızıntısı",
        "identity_leak": "Kimlik sızıntısı",
    }
    for g, v in dashboard["leak_gates"].items():
        lines.append(f"  {gate(v['pass'])} {label.get(g, g):<22} ihlal {v['violations']}")

    if dashboard["violations"]:
        lines.append("")
        lines.append("İHLALLER:")
        for text, reasons in list(dashboard["violations"].items())[:10]:
            lines.append(f"  {text!r} -> {reasons}")

    lines.append("")
    lines.append("-" * 72)
    lines.append(
        f"{gate(dashboard['overall_pass'])} GENEL: "
        + ("zarf ihlal-edilemez (tüm kapılar geçti)" if dashboard["overall_pass"]
           else "kapı ihlali tespit edildi")
    )
    return "\n".join(lines)


def save_dashboard(dashboard: dict, path: Path = GATE_ARTIFACT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dashboard, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="İP-2.8 kapı ihlal-edilemezliği kanıt raporu")
    parser.add_argument("--no-save", action="store_true", help="Artefaktı yazma, sadece raporla")
    parser.add_argument("--json", action="store_true", help="JSON'u stdout'a bas")
    args = parser.parse_args()

    dashboard = build_gate_dashboard()
    if args.json:
        print(json.dumps(dashboard, indent=2, ensure_ascii=False))
    else:
        print(render(dashboard))

    if not args.no_save:
        save_dashboard(dashboard)
        print(f"\n💾 Kapı kanıt raporu kaydedildi: {GATE_ARTIFACT}")


if __name__ == "__main__":
    main()
