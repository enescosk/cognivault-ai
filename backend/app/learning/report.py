"""İP-4 — Hekim-döngülü öğrenme katmanı konsolide kanıt panosu.

İP-4'ün altı bağımsız motorunu (RLHF etiket üretimi, otomatik-yanıt eşiği öğrenme,
karar süresi, no-show modeli, dinamik slot, proaktif geri-çağırma) tek denetlenebilir
JSON panoda toplar — her motorun kendi `overall_pass` kapısı + tüm katmanın `overall_pass`
VE'si. İP-1.8 (`clinical/report.py`), İP-2.8 (`governance/gate_report.py`) ve İP-3.9
(`perf/latency.py`) ile aynı desen: tekil üreticileri orkestre eder, yeniden hesaplamaz.

Tüm motorlar deterministik (sabit tohum / sentetik girdi, timestamp yok) → artefakt
diff'lenebilir ve `data/learning_report.json`'a donar.

Çalıştırma:
    python -m app.learning.report            # pano + artefakt
    python -m app.learning.report --no-save  # sadece raporla
    python -m app.learning.report --json     # JSON'u stdout'a bas
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.learning import decision_time, labels, noshow, recall, slots, thresholds

DASHBOARD_ARTIFACT = Path(__file__).resolve().parent / "data" / "learning_report.json"

# (İP no, motor anahtarı, etiket, rapor üretici) — pano bu sırayı korur.
ENGINES = [
    ("4.2", "rlhf_labels", "RLHF etiket üretimi", lambda: labels.build_report(labels.synthetic_feedback())),
    ("4.3", "auto_reply_threshold", "Otomatik-yanıt eşiği", lambda: thresholds.build_report(labels.synthetic_feedback())),
    ("4.4", "decision_time", "Karar süresi", decision_time.build_report),
    ("4.5", "no_show_model", "No-show risk modeli", noshow.build_report),
    ("4.6", "slot_recommender", "Dinamik slot önerisi", slots.build_report),
    ("4.7", "proactive_recall", "Proaktif geri-çağırma", recall.build_report),
]


def _headline_metrics(engines: dict) -> dict:
    """Panoda öne çıkan birkaç denetim-kritik metrik (motor raporlarından okunur)."""
    return {
        "rlhf_labels_count": engines["4.2"]["labels"]["count"],
        "rlhf_privacy_held": engines["4.2"]["gates"]["privacy_gate"]["privacy_held"],
        "auto_reply_threshold": engines["4.3"]["recommendation"]["recommended_threshold"],
        "auto_reply_coverage": engines["4.3"]["recommendation"]["coverage"],
        "decision_p95_seconds": engines["4.4"]["stats"]["p95"],
        "no_show_auc_test": engines["4.5"]["metrics"]["auc_test"],
        "slot_recommendations": len(engines["4.6"]["recommendations"]),
        "recall_scheduled": len(engines["4.7"]["scheduled"]),
    }


def build_learning_dashboard() -> dict:
    """Altı İP-4 motorunu tek JSON-hazır panoda toplar (deterministik)."""
    engines: dict[str, dict] = {}
    summary: dict[str, dict] = {}
    for ip, key, label, fn in ENGINES:
        rep = fn()
        engines[ip] = rep
        summary[ip] = {"key": key, "label": label, "pass": bool(rep["overall_pass"])}

    overall = all(s["pass"] for s in summary.values())
    return {
        "ip": "4",
        "title": "CogniVault Hekim-Döngülü Öğrenme — Konsolide Kanıt Panosu",
        "engine_count": len(engines),
        "summary": summary,
        "headline_metrics": _headline_metrics(engines),
        "engines": engines,
        "overall_pass": overall,
    }


def render(dashboard: dict) -> str:
    def gate(ok: bool) -> str:
        return "✅" if ok else "❌"

    lines = [
        "=" * 72,
        "İP-4 — Hekim-Döngülü Öğrenme Konsolide Kanıt Panosu",
        "=" * 72,
        f"Motor sayısı: {dashboard['engine_count']}",
        "",
        "Motorlar (kapı durumu):",
    ]
    for ip, s in dashboard["summary"].items():
        lines.append(f"  {gate(s['pass'])} İP-{ip:<4} {s['label']}")

    m = dashboard["headline_metrics"]
    lines += [
        "",
        "Öne çıkan metrikler:",
        f"  • No-show AUC (test)      : {m['no_show_auc_test']:.4f}",
        f"  • Karar süresi p95        : {m['decision_p95_seconds']:.1f} sn",
        f"  • Otomatik-yanıt eşiği    : {m['auto_reply_threshold']} (kapsam {m['auto_reply_coverage']:.2f})",
        f"  • RLHF etiket / mahremiyet: {m['rlhf_labels_count']} üretildi / {m['rlhf_privacy_held']} tutuldu",
        f"  • Slot önerisi / geri-çağırma: {m['slot_recommendations']} / {m['recall_scheduled']}",
        "-" * 72,
        f"{gate(dashboard['overall_pass'])} GENEL: "
        + ("tüm öğrenme kapıları geçti" if dashboard["overall_pass"] else "bir motor kapısı kaldı"),
    ]
    return "\n".join(lines)


def save_dashboard(dashboard: dict, path: Path = DASHBOARD_ARTIFACT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dashboard, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="İP-4 konsolide öğrenme kanıt panosu")
    parser.add_argument("--no-save", action="store_true", help="Artefaktı yazma, sadece raporla")
    parser.add_argument("--json", action="store_true", help="JSON'u stdout'a bas")
    args = parser.parse_args(argv)

    dashboard = build_learning_dashboard()
    if args.json:
        print(json.dumps(dashboard, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render(dashboard))

    if not args.no_save:
        save_dashboard(dashboard)
        if not args.json:
            print(f"\n💾 Öğrenme kanıt panosu kaydedildi: {DASHBOARD_ARTIFACT}")
    return 0 if dashboard["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
