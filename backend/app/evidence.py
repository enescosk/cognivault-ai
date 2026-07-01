"""Üst-düzey Teknik Hazırlık Kanıt Panosu — tüm iş paketlerinin tek denetimi.

BiGG hakemi / klinik / iç denetim için **tek komut**la her iş paketinin başarı
ölçütünü kanıtlar. Her İP'nin kendi panosunu (ör. `clinical.report.build_dashboard`,
`governance.gate_report.build_gate_dashboard`, `learning.report.build_learning_dashboard`,
`voice.turn_taking`/`voice.vad`, `reception.greeting`) **orkestre eder** — metrik
yeniden hesaplamaz, mevcut public üreticileri çağırır ve `overall_pass`'lerini VE'ler.

Sağlamlık: bir alt-pano import/çalışma hatası verirse tüm pano çökmez; o paket
`status=error` ile başarısız işaretlenir (dürüst sinyal). Yalnızca deterministik
panolar dâhildir; gecikme (perf) panosu duvar-saati olduğundan burada değil, kendi
üreticisiyle (`app.perf.latency`) canlı koşulur.

CLI: `python -m app.evidence`  (çıkış kodu 0=GEÇTİ, 1=KALDI → CI'da kapı olarak kullanılır)
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

ARTIFACT_PATH = Path(__file__).resolve().parent / "data" / "readiness.json"

# (etiket, başlık, modül, üretici fonksiyon) — hepsi deterministik.
PANELS: list[tuple[str, str, str, str]] = [
    ("İP-1", "Türkçe triyaj NLU + kalibre çekimser yönlendirici", "app.clinical.report", "build_dashboard"),
    ("İP-2", "Deterministik yönetişim zarfı (kapı ihlali=0)", "app.governance.gate_report", "build_gate_dashboard"),
    ("İP-3.7a", "Gerçek-zamanlı ses — turn-taking / barge-in", "app.voice.turn_taking", "build_report"),
    ("İP-3.7b", "Gerçek-zamanlı ses — enerji VAD", "app.voice.vad", "build_report"),
    ("İP-4", "Hekim-döngülü iyileştirme + öngörücü süreklilik", "app.learning.report", "build_learning_dashboard"),
    ("Resepsiyon", "API öncesi karşılama + kötü-girdi koruması", "app.reception.greeting", "build_report"),
    ("İP-3.6", "Damıtma veri paketi (PII-temiz SFT + baseline protokolü)", "app.clinical.distillation", "build_report"),
    ("İP-6.2", "Tek komut klinik onboarding provizyonu", "app.onboarding.provision", "build_report"),
    ("İP-5.2", "HBYS/takvim adapteri dayanıklılık sözleşmesi", "app.integrations.hbys", "build_report"),
    ("Prod-Ops", "Dağıtım öncesi güvenlik preflight (guard doğrulama + migration head)", "app.ops.preflight", "build_report"),
]


def _count_gates(obj: object) -> tuple[int, int]:
    """Alt-panoda boolean `pass` taşıyan her kapıyı (geçen, toplam) sayar (genel/dayanıklı)."""
    passed = total = 0
    if isinstance(obj, dict):
        p = obj.get("pass")
        if isinstance(p, bool):
            total += 1
            passed += 1 if p else 0
        for v in obj.values():
            gp, gt = _count_gates(v)
            passed += gp
            total += gt
    elif isinstance(obj, list):
        for v in obj:
            gp, gt = _count_gates(v)
            passed += gp
            total += gt
    return passed, total


def build_readiness() -> dict:
    """Tüm iş-paketi panolarını çağırıp tek hazırlık panosu üretir."""
    packages: list[dict] = []
    for ip, title, mod, fn in PANELS:
        entry = {"ip": ip, "title": title, "source": f"{mod}.{fn}"}
        try:
            module = importlib.import_module(mod)
            report = getattr(module, fn)()
            gp, gt = _count_gates(report)
            entry.update(
                overall_pass=bool(report.get("overall_pass")),
                gates_passed=gp,
                gates_total=gt,
                status="ok",
            )
        except Exception as e:  # pragma: no cover - dayanıklılık dalı
            entry.update(overall_pass=False, gates_passed=0, gates_total=0, status=f"error: {type(e).__name__}: {e}")
        packages.append(entry)

    panels_passed = sum(1 for p in packages if p["overall_pass"])
    report = {
        "name": "technical_readiness_board",
        "packages": packages,
        "summary": {
            "panels": len(packages),
            "panels_passed": panels_passed,
            "gates_passed": sum(p["gates_passed"] for p in packages),
            "gates_total": sum(p["gates_total"] for p in packages),
        },
        "overall_pass": all(p["overall_pass"] for p in packages),
    }
    return report


def render(report: dict) -> str:
    ok = lambda b: "✅" if b else "❌"  # noqa: E731
    lines = [
        "CogniVault — Teknik Hazırlık Kanıt Panosu",
        "=" * 62,
    ]
    for p in report["packages"]:
        tag = "" if p["status"] == "ok" else f"  [{p['status']}]"
        lines.append(
            f"{ok(p['overall_pass'])} {p['ip']:<10s} {p['title'][:38]:<38s} "
            f"{p['gates_passed']}/{p['gates_total']} kapı{tag}"
        )
    s = report["summary"]
    lines += [
        "-" * 62,
        f"Paketler: {s['panels_passed']}/{s['panels']} geçti   ·   Kapılar: {s['gates_passed']}/{s['gates_total']} geçti",
        "=" * 62,
        f"{ok(report['overall_pass'])} GENEL TEKNİK HAZIRLIK: {'GEÇTİ' if report['overall_pass'] else 'KALDI'}",
    ]
    return "\n".join(lines)


def write_artifact(report: dict, path: Path = ARTIFACT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="CogniVault teknik hazırlık kanıt panosu")
    parser.add_argument("--no-save", action="store_true", help="artefakt yazma")
    parser.add_argument("--json", action="store_true", help="JSON çıktısı")
    args = parser.parse_args(argv)

    report = build_readiness()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render(report))
    if not args.no_save:
        path = write_artifact(report)
        if not args.json:
            print(f"\nArtefakt: {path}")
    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
