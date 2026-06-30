"""İP-3.8 / İP-3.9 — Yerel yığın gecikme ölçümü + gecikme/kalite raporu.

Bu modül iki şeyi yapar:

1. **İP-3.8 — Gecikme ölçümü.** Yerel yığının HER istekte sunucuda koşan
   saf-Python kritik yolunu (PII maskeleme → yönetişim zarfı → niyet sınıflama →
   triyaj) `time.perf_counter` ile gerçek olarak benchmark'lar; her aşama için
   p50/p95/p99 gecikme çıkarır ve modest-donanım **p95 bütçesine** göre kapı
   uygular. Bunlar gerçek ölçümlerdir (cihazda çalışır), ağ/model gerektirmez.

   Model aşamaları (yerel ASR / yerel LLM / yerel TTS) bu deterministik ortamda
   ölçülemez (gerçek model çalışma-zamanı gerekir); onlar için modest donanımda
   gözlemlenen **belgeli bütçe hedefleri** taşınır ve uçtan-uca ses-turu bütçesi
   (ASR + saf yol + LLM + TTS) çıkarılır.

2. **İP-3.9 — Gecikme + kalite raporu.** Ölçülen gecikmeyi İP-1.8 klinik kalite
   panosuyla (branş doğruluğu, ECE, acil recall, seçici risk) tek denetlenebilir
   panoda birleştirir.

Gecikme rakamları duvar-saati olduğundan artefakt **donmuş** (frozen) değildir;
testler bütçe-kapısı mantığını, yüzdelik hesabını ve rapor yapısını doğrular,
ham süreleri değil.

Çalıştırma:
    python -m app.perf.latency                 # gecikme + kalite panosu
    python -m app.perf.latency --latency-only   # sadece gecikme
    python -m app.perf.latency --json           # JSON'u stdout'a bas
    python -m app.perf.latency --trials 500     # benchmark deneme sayısı
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

from app.models import ClinicIntent
from app.services.clinical_compliance_service import (
    build_governance_context,
    mask_identifiers,
)

LATENCY_ARTIFACT = Path(__file__).resolve().parent / "data" / "latency_report.json"

DEFAULT_TRIALS = 300
DEFAULT_WARMUP = 20

# Temsili (sentetik, anonim) hasta mesajı — PII + acil + randevu sinyali içerir
# ki maskeleme/zarf/triyaj kritik yolu gerçekçi yük altında ölçülsün.
SAMPLE_TEXT = "dişim çok ağrıyor TC 12345678901 acil randevu lazım numaram 0532 111 22 33"

_CLINIC = SimpleNamespace(
    settings_json={
        "data_residency_mode": "tr_local_first",
        "allow_cross_border_processors": False,
    }
)


# ─────────────────────────────────────────────────────────────────────────────
# Saf yüzdelik / özet yardımcıları (deterministik — testlerle kilitlenir)
# ─────────────────────────────────────────────────────────────────────────────
def percentile(sorted_samples: list[float], q: float) -> float:
    """Sıralı örnekler üzerinde doğrusal-aradeğerli yüzdelik (numpy varsayılanı).

    `q` ∈ [0, 100]. Boş liste hata verir; tek eleman o elemanı döndürür.
    """
    if not sorted_samples:
        raise ValueError("percentile boş örnek listesi alamaz")
    if not 0.0 <= q <= 100.0:
        raise ValueError("q 0..100 aralığında olmalı")
    n = len(sorted_samples)
    if n == 1:
        return float(sorted_samples[0])
    rank = (q / 100.0) * (n - 1)
    lo = math.floor(rank)
    hi = math.ceil(rank)
    if lo == hi:
        return float(sorted_samples[lo])
    frac = rank - lo
    return float(sorted_samples[lo] + (sorted_samples[hi] - sorted_samples[lo]) * frac)


def summarize(samples_ms: list[float]) -> dict:
    """Örnek dizisini p50/p95/p99 + ortalama/min/maks/n özetine indirger (ms)."""
    s = sorted(samples_ms)
    return {
        "n": len(s),
        "p50_ms": round(percentile(s, 50), 4),
        "p95_ms": round(percentile(s, 95), 4),
        "p99_ms": round(percentile(s, 99), 4),
        "mean_ms": round(sum(s) / len(s), 4),
        "min_ms": round(s[0], 4),
        "max_ms": round(s[-1], 4),
    }


def benchmark(fn: Callable[[], object], trials: int, warmup: int = DEFAULT_WARMUP) -> list[float]:
    """`fn`'i `warmup`+`trials` kez çağırır; ısınma sonrası ms gecikmeleri döner."""
    for _ in range(max(0, warmup)):
        fn()
    samples: list[float] = []
    for _ in range(trials):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000.0)
    return samples


# ─────────────────────────────────────────────────────────────────────────────
# Ölçülen saf-Python aşamalar (her istekte koşan sunucu kritik yolu)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Stage:
    name: str
    label: str
    p95_budget_ms: float
    call: Callable[[], object]


def _call_intent() -> object:
    # Lazy import: klinik niyet sınıflayıcı (saf, ağ yok).
    from app.services.customer_understanding import understand_primary_intent

    return understand_primary_intent(SAMPLE_TEXT)


def _call_triage() -> object:
    from app.clinical.normalizer import triage

    return triage(SAMPLE_TEXT)


def measured_stages() -> list[Stage]:
    """Gerçekten benchmark'lanan saf-Python kritik-yol aşamaları (modest p95 bütçe)."""
    return [
        Stage(
            "pii_masking",
            "PII maskeleme",
            5.0,
            lambda: mask_identifiers(SAMPLE_TEXT),
        ),
        Stage(
            "governance_envelope",
            "Yönetişim zarfı",
            10.0,
            lambda: build_governance_context(_CLINIC, SAMPLE_TEXT, ClinicIntent.BOOK_APPOINTMENT, "tr"),
        ),
        Stage(
            "intent_classification",
            "Niyet sınıflama",
            15.0,
            _call_intent,
        ),
        Stage(
            "clinical_triage",
            "Klinik triyaj",
            15.0,
            _call_triage,
        ),
    ]


# Model aşamaları — bu ortamda ölçülemez; modest donanımda (CPU-öncelikli, kısa
# ifade) gözlemlenen belgeli p95 bütçe hedefleri. Uçtan-uca ses-turu bütçesini
# kurarken kullanılır.
MODEL_STAGE_BUDGETS = {
    "asr_local_whisper": {
        "label": "Yerel ASR (faster-whisper)",
        "p95_budget_ms": 1500.0,
        "note": "kısa ifade (~5sn), CPU int8; gerçek model çalışma-zamanı gerekir",
    },
    "llm_local_qwen": {
        "label": "Yerel LLM (Qwen2.5 / Ollama)",
        "p95_budget_ms": 2500.0,
        "note": "JSON-kısıtlı kısa yanıt; modest GPU/CPU; gerçek model gerekir",
    },
    "tts_local_piper": {
        "label": "Yerel TTS (Piper tr_TR)",
        "p95_budget_ms": 600.0,
        "note": "tek cümle sentez; gerçek ses çalışma-zamanı gerekir",
    },
}

# Uçtan-uca ses-turu (ASR→zarf/triyaj→LLM→TTS) modest-donanım hedefi.
END_TO_END_BUDGET_MS = 5000.0


def passes_budget(p95_ms: float, budget_ms: float) -> bool:
    """Saf kapı: ölçülen p95, bütçeyi aşmazsa geçer."""
    return p95_ms <= budget_ms


# ─────────────────────────────────────────────────────────────────────────────
# Rapor kurucu
# ─────────────────────────────────────────────────────────────────────────────
def build_latency_report(trials: int = DEFAULT_TRIALS, warmup: int = DEFAULT_WARMUP) -> dict:
    """İP-3.8 — saf-Python kritik yolu ölçer, bütçe kapısı uygular."""
    stages: dict[str, dict] = {}
    critical_path_p95 = 0.0
    for st in measured_stages():
        summary = summarize(benchmark(st.call, trials, warmup))
        ok = passes_budget(summary["p95_ms"], st.p95_budget_ms)
        critical_path_p95 += summary["p95_ms"]
        stages[st.name] = {
            "label": st.label,
            "summary": summary,
            "p95_budget_ms": st.p95_budget_ms,
            "pass": ok,
        }

    critical_path_p95 = round(critical_path_p95, 4)
    model_budget_sum = sum(m["p95_budget_ms"] for m in MODEL_STAGE_BUDGETS.values())
    e2e_p95_estimate = round(critical_path_p95 + model_budget_sum, 4)

    all_stages_pass = all(s["pass"] for s in stages.values())
    e2e_pass = e2e_p95_estimate <= END_TO_END_BUDGET_MS

    return {
        "ip": "3.8",
        "title": "CogniVault Yerel Yığın — Gecikme Ölçümü",
        "trials": trials,
        "warmup": warmup,
        "sample_text_masked": mask_identifiers(SAMPLE_TEXT),
        "measured_stages": stages,
        "critical_path_p95_ms": critical_path_p95,
        "model_stage_budgets": MODEL_STAGE_BUDGETS,
        "end_to_end": {
            "p95_estimate_ms": e2e_p95_estimate,
            "budget_ms": END_TO_END_BUDGET_MS,
            "pass": e2e_pass,
            "note": "uçtan-uca = ölçülen saf-yol p95 + model bütçe hedefleri toplamı",
        },
        "measured_stages_pass": all_stages_pass,
        "overall_pass": all_stages_pass and e2e_pass,
    }


def build_perf_report(trials: int = DEFAULT_TRIALS, warmup: int = DEFAULT_WARMUP) -> dict:
    """İP-3.9 — gecikme (İP-3.8) + klinik kalite (İP-1.8) birleşik panosu."""
    from app.clinical.report import build_dashboard

    latency = build_latency_report(trials, warmup)
    quality = build_dashboard()
    return {
        "ip": "3.9",
        "title": "CogniVault Yerel Yığın — Gecikme + Kalite Raporu",
        "latency": latency,
        "quality": {
            "metrics": quality["metrics"],
            "overall_pass": quality["overall_pass"],
        },
        "overall_pass": latency["overall_pass"] and quality["overall_pass"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Render / kaydet / CLI
# ─────────────────────────────────────────────────────────────────────────────
def _gate(ok: bool) -> str:
    return "✅" if ok else "❌"


def render_latency(report: dict) -> str:
    lines = [
        "=" * 72,
        "İP-3.8 — Yerel Yığın Gecikme Ölçümü (saf-Python kritik yol)",
        "=" * 72,
        f"Deneme: {report['trials']} (ısınma {report['warmup']})",
        "",
        "Ölçülen aşamalar (p95 / bütçe):",
    ]
    for name, s in report["measured_stages"].items():
        lines.append(
            f"  {_gate(s['pass'])} {s['label']:<20} "
            f"p50={s['summary']['p50_ms']:.3f}ms  p95={s['summary']['p95_ms']:.3f}ms "
            f"(bütçe ≤{s['p95_budget_ms']:.0f}ms)"
        )
    lines.append("")
    lines.append(f"Saf kritik yol p95 toplam: {report['critical_path_p95_ms']:.3f}ms")
    lines.append("")
    lines.append("Model aşama bütçeleri (belgeli hedef — bu ortamda ölçülmez):")
    for name, m in report["model_stage_budgets"].items():
        lines.append(f"  • {m['label']:<28} ≤{m['p95_budget_ms']:.0f}ms")
    e2e = report["end_to_end"]
    lines.append("")
    lines.append(
        f"{_gate(e2e['pass'])} Uçtan-uca ses-turu p95 (tahmin): "
        f"{e2e['p95_estimate_ms']:.0f}ms (bütçe ≤{e2e['budget_ms']:.0f}ms)"
    )
    lines.append("-" * 72)
    lines.append(
        f"{_gate(report['overall_pass'])} GENEL: "
        + ("gecikme bütçeleri karşılandı" if report["overall_pass"] else "gecikme bütçesi aşıldı")
    )
    return "\n".join(lines)


def render_perf(report: dict) -> str:
    out = [render_latency(report["latency"]), "", "=" * 72, "Klinik kalite (İP-1.8):", "=" * 72]
    for name, block in report["quality"]["metrics"].items():
        out.append(f"  {_gate(block['pass'])} {name}")
    out.append("")
    out.append(
        f"{_gate(report['overall_pass'])} BİRLEŞİK GENEL: "
        + ("gecikme + kalite hedefleri karşılandı" if report["overall_pass"]
           else "gecikme veya kalite hedefi karşılanmadı")
    )
    return "\n".join(out)


def save_report(report: dict, path: Path = LATENCY_ARTIFACT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="İP-3.8/3.9 yerel yığın gecikme + kalite raporu")
    parser.add_argument("--latency-only", action="store_true", help="Sadece gecikme (kaliteyi atla)")
    parser.add_argument("--no-save", action="store_true", help="Artefaktı yazma")
    parser.add_argument("--json", action="store_true", help="JSON'u stdout'a bas")
    parser.add_argument("--trials", type=int, default=DEFAULT_TRIALS, help="Benchmark deneme sayısı")
    args = parser.parse_args()

    if args.latency_only:
        report = build_latency_report(args.trials)
        text = render_latency(report)
    else:
        report = build_perf_report(args.trials)
        text = render_perf(report)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(text)

    if not args.no_save:
        save_report(report)
        print(f"\n💾 Gecikme raporu kaydedildi: {LATENCY_ARTIFACT}")


if __name__ == "__main__":
    main()
