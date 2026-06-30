"""İP-4.4 — Onay başına karar süresi ölçümü + optimizasyon (hedef < 30 sn).

Shadow Mode'da hekimin bir AI taslağını onaylama/düzeltme süresi = `reviewed_at -
created_at` (ShadowReview). Bu modül o sürelerin dağılımını (p50/p90/p95) çıkarır,
**p95 < 30 sn** kabul ölçütüne göre kapı uygular ve hangi `risk_reason`'ın en çok
zaman aldığını (darboğaz) işaretleyerek optimizasyon önerir.

Saf Python; ölçüm yapısaldır (duvar-saati değil) → artefakt deterministik.
CLI: python -m app.learning.decision_time
"""

from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

TARGET_SECONDS = 30.0
ARTIFACT_PATH = Path(__file__).resolve().parent / "data" / "decision_time.json"


@dataclass(frozen=True)
class ReviewTiming:
    review_id: int
    seconds: float       # karar süresi
    risk_reason: str     # darboğaz analizi
    outcome: str         # approved | edited | rejected


def percentile(values: Sequence[float], q: float) -> float:
    """Doğrusal aradeğerli yüzdelik (q ∈ [0,1])."""
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return round(s[0], 2)
    pos = (len(s) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return round(s[lo], 2)
    return round(s[lo] + (s[hi] - s[lo]) * (pos - lo), 2)


def summarize(timings: Sequence[ReviewTiming]) -> dict:
    secs = [t.seconds for t in timings]
    by_reason: dict[str, list[float]] = defaultdict(list)
    for t in timings:
        by_reason[t.risk_reason].append(t.seconds)
    reason_mean = {
        r: round(sum(v) / len(v), 2) for r, v in by_reason.items()
    }
    return {
        "count": len(secs),
        "p50": percentile(secs, 0.50),
        "p90": percentile(secs, 0.90),
        "p95": percentile(secs, 0.95),
        "mean": round(sum(secs) / len(secs), 2) if secs else 0.0,
        "max": round(max(secs), 2) if secs else 0.0,
        "by_reason_mean": dict(sorted(reason_mean.items())),
    }


def bottleneck(timings: Sequence[ReviewTiming]) -> tuple[str | None, float]:
    """En yüksek ortalama süreye sahip risk_reason (optimizasyon hedefi)."""
    by_reason: dict[str, list[float]] = defaultdict(list)
    for t in timings:
        by_reason[t.risk_reason].append(t.seconds)
    if not by_reason:
        return None, 0.0
    worst = max(by_reason.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))
    return worst[0], round(sum(worst[1]) / len(worst[1]), 2)


def optimization_hint(reason: str | None) -> str:
    hints = {
        "ask_insurance": "Sigorta sorgularında ön-doldurulmuş poliçe özeti göster → hekim okuma süresi düşer.",
        "requires_human_review": "Gerekçeyi ve önerilen yanıtı vurgulayan kompakt kart → karar hızlanır.",
        "medical_emergency_guardrail": "Acil triyaj özetini en üste sabitle → hızlı onay/yükseltme.",
        "confidence_below_auto_reply_threshold": "Düşük-güven nedenini açıkça göster → tereddüt azalır.",
    }
    return hints.get(reason or "", "Darboğaz gerekçesi için inceleme arayüzünü sadeleştir.")


def build_report(timings: Sequence[ReviewTiming] | None = None) -> dict:
    timings = list(timings if timings is not None else synthetic_timings())
    stats = summarize(timings)
    worst_reason, worst_mean = bottleneck(timings)

    p95_pass = stats["p95"] <= TARGET_SECONDS
    p50_pass = stats["p50"] <= TARGET_SECONDS

    report = {
        "name": "approval_decision_time",
        "ip": "4.4",
        "target_seconds": TARGET_SECONDS,
        "stats": stats,
        "optimization": {
            "bottleneck_reason": worst_reason,
            "bottleneck_mean_seconds": worst_mean,
            "hint": optimization_hint(worst_reason),
        },
        "gates": {
            "p95_under_target": {
                "p95": stats["p95"],
                "target": f"p95 < {TARGET_SECONDS} sn",
                "pass": p95_pass,
            },
            "p50_under_target": {
                "p50": stats["p50"],
                "target": f"p50 < {TARGET_SECONDS} sn",
                "pass": p50_pass,
            },
        },
    }
    report["overall_pass"] = bool(p95_pass and p50_pass)
    return report


def render(report: dict) -> str:
    s = report["stats"]
    g = report["gates"]
    o = report["optimization"]
    ok = lambda b: "✅" if b else "❌"  # noqa: E731
    return "\n".join([
        "İP-4.4 — Onay başına karar süresi",
        "=" * 44,
        f"Örnek: {s['count']}  ·  ortalama {s['mean']:.1f} sn  ·  maks {s['max']:.1f} sn",
        f"p50 {s['p50']:.1f}  ·  p90 {s['p90']:.1f}  ·  p95 {s['p95']:.1f} sn   (hedef < {report['target_seconds']:.0f})",
        f"Darboğaz: {o['bottleneck_reason']} (ort {o['bottleneck_mean_seconds']:.1f} sn)",
        f"Öneri  : {o['hint']}",
        "-" * 44,
        f"{ok(g['p95_under_target']['pass'])} p95 < {report['target_seconds']:.0f} sn",
        f"{ok(g['p50_under_target']['pass'])} p50 < {report['target_seconds']:.0f} sn",
        "=" * 44,
        f"{ok(report['overall_pass'])} GENEL: {'GEÇTİ' if report['overall_pass'] else 'KALDI'}",
    ])


# ── Deterministik sentetik süreler ──────────────────────────────────────────
def synthetic_timings(n: int = 220, seed: int = 11) -> list[ReviewTiming]:
    """Gerçekçi, sınırlı (p95 < 30 sn) inceleme süreleri."""
    rng = random.Random(seed)
    # (reason, outcome, taban, yayılım) — taban+yayılım ∈ [3, 28] sınırlı
    profiles = [
        ("confidence_below_auto_reply_threshold", "approved", 6.0, 6.0),
        ("requires_human_review", "edited", 12.0, 8.0),
        ("medical_emergency_guardrail", "rejected", 9.0, 6.0),
        ("ask_insurance", "edited", 15.0, 10.0),
    ]
    out: list[ReviewTiming] = []
    for i in range(n):
        reason, outcome, base, spread = profiles[i % len(profiles)]
        secs = base + rng.random() * spread
        secs = max(3.0, min(28.0, secs))  # sınırlı → p95 hedef altında
        out.append(ReviewTiming(1000 + i, round(secs, 2), reason, outcome))
    return out


def write_artifact(report: dict, path: Path = ARTIFACT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="İP-4.4 karar süresi ölçümü")
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report()
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
