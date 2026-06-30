"""İP-4.3 — Onaylardan zarf eşiği öğrenme (kapı kurallarını İHLAL ETMEDEN).

Shadow Mode hekim kararları (`ClinicalModelFeedback` → `FeedbackRecord`) bize, AI'nın
o güven seviyesinde otomatik yanıtlasaydı haklı mı çıkacağını söyler: hekim
**düzeltmesiz onayladıysa** otomatik yanıt doğru olurdu; **düzelttiyse/reddettiyse**
otomatik yanıt hata olurdu. Bu modül bu sinyalden, otomatik-yanıt güven eşiğini
veri-temelli kalibre eder.

Üç kapı kuralı korunur (yumuşatılamaz):
1. **Acil daima insana** — `FORCE_HUMAN_INTENTS` (acil/sigorta) otomatik-yanıt
   havuzuna HİÇ girmez; öğrenilen eşik bunları asla otomatikleştiremez.
2. **Güvenlik tabanı** — önerilen eşik `SAFETY_FLOOR`'un (mevcut shadow eşiği)
   ALTINA inemez; düşük güvende otomatik yanıt yasak kalır.
3. **Hata bütçesi** — otomatik-yanıtlanan kümede ampirik hata ≤ `error_budget` (%5).

Konformal benzeri eşik uydurma (bkz. İP-1.6 `selective.py`): bütçeyi karşılayan
EN KÜÇÜK eşik seçilir → otomasyon kapsamı en yükseğe çıkar, güvenlik korunur.

Saf Python. CLI: python -m app.learning.thresholds
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from app.learning.labels import (
    OUTCOME_APPROVED,
    FeedbackRecord,
    _partition,
)

# ── Kapı kuralları (sabit; öğrenme bunları gevşetemez) ──────────────────────
# Otomatik yanıta ASLA uygun olmayan niyetler — daima insana yükseltilir.
FORCE_HUMAN_INTENTS = frozenset({"medical_emergency", "ask_insurance"})
# Güvenlik tabanı — clinical_shadow_threshold (0.75) ile hizalı; altına inilmez.
SAFETY_FLOOR = 0.75
DEFAULT_ERROR_BUDGET = 0.05
# Eşik karşılaştırması yoksa (hiçbir aday bütçeyi tutmuyorsa) otomasyon kapalı.
NO_AUTO_REPLY = 1.01

ARTIFACT_PATH = Path(__file__).resolve().parent / "data" / "thresholds.json"


@dataclass(frozen=True)
class ThresholdRecommendation:
    recommended_threshold: float
    coverage: float          # otomatik-yanıt-uygun kayıt oranı (havuza göre)
    error_rate: float        # otomatik-yanıtlananlarda ampirik hata
    met_budget: bool
    pool_size: int           # değerlendirilebilir (acil-dışı) kayıt sayısı
    forced_human: int        # kapı gereği havuz dışı bırakılan kayıt

    def as_dict(self) -> dict:
        return {
            "recommended_threshold": self.recommended_threshold,
            "coverage": self.coverage,
            "error_rate": self.error_rate,
            "met_budget": self.met_budget,
            "pool_size": self.pool_size,
            "forced_human": self.forced_human,
        }


def _auto_reply_pool(records: Iterable[FeedbackRecord]) -> tuple[list[FeedbackRecord], int]:
    """Eğitilebilir + acil-dışı kayıtlar (otomatik-yanıt aday havuzu) ve hariç sayısı."""
    ready, _held, _invalid = _partition(records)
    pool: list[FeedbackRecord] = []
    forced = 0
    for r in ready.values():
        if r.intent in FORCE_HUMAN_INTENTS:
            forced += 1
            continue
        pool.append(r)
    return pool, forced


def _is_correct_auto(record: FeedbackRecord) -> bool:
    """Otomatik yanıt doğru olur muydu? Yalnızca düzeltmesiz onay = doğru."""
    return record.outcome == OUTCOME_APPROVED


def fit_auto_reply_threshold(
    records: Iterable[FeedbackRecord],
    error_budget: float = DEFAULT_ERROR_BUDGET,
    floor: float = SAFETY_FLOOR,
) -> ThresholdRecommendation:
    """Bütçeyi karşılayan EN KÜÇÜK (≥ taban) güven eşiğini öğrenir.

    Eşik adayları: taban + havuzdaki taban-üstü güven değerleri. Bir τ için
    {güven ≥ τ} kümesinde hata = düzeltilen/reddedilen oranı. Bütçeyi tutan en
    küçük τ kazanır (kapsamı azamileştirir). Hiçbiri tutmazsa otomasyon kapalı.
    """
    pool, forced = _auto_reply_pool(records)
    total = len(pool)
    if total == 0:
        return ThresholdRecommendation(NO_AUTO_REPLY, 0.0, 0.0, False, 0, forced)

    candidates = sorted({floor} | {r.confidence for r in pool if r.confidence >= floor})

    best: ThresholdRecommendation | None = None
    for tau in candidates:
        tail = [r for r in pool if r.confidence >= tau]
        if not tail:
            continue
        errors = sum(1 for r in tail if not _is_correct_auto(r))
        err_rate = errors / len(tail)
        if err_rate <= error_budget:
            best = ThresholdRecommendation(
                recommended_threshold=round(tau, 4),
                coverage=round(len(tail) / total, 4),
                error_rate=round(err_rate, 4),
                met_budget=True,
                pool_size=total,
                forced_human=forced,
            )
            break  # adaylar artan; ilk tutan = en küçük eşik

    if best is None:
        # Bütçe hiçbir eşikte tutmuyor → güvenli taraf: otomasyon kapalı.
        best = ThresholdRecommendation(NO_AUTO_REPLY, 0.0, 0.0, False, total, forced)
    return best


def build_report(
    records: Iterable[FeedbackRecord],
    error_budget: float = DEFAULT_ERROR_BUDGET,
    floor: float = SAFETY_FLOOR,
) -> dict:
    """Denetlenebilir eşik-öğrenme panosu; kapılar yumuşatılamazlığı kanıtlar."""
    records = list(records)
    rec = fit_auto_reply_threshold(records, error_budget, floor)
    pool, forced = _auto_reply_pool(records)
    intents_in_pool = Counter(r.intent for r in pool)

    # Kapı 1: acil/sigorta havuza hiç girmemeli.
    emergency_in_pool = sum(intents_in_pool.get(i, 0) for i in FORCE_HUMAN_INTENTS)
    emergency_pass = emergency_in_pool == 0
    # Kapı 2: önerilen eşik tabanın altına inmemeli (NO_AUTO_REPLY de güvenli).
    floor_pass = rec.recommended_threshold >= floor
    # Kapı 3: otomasyon önerildiyse hata bütçesi tutmalı.
    budget_pass = (not rec.met_budget) or (rec.error_rate <= error_budget)

    report = {
        "name": "auto_reply_threshold_learning",
        "ip": "4.3",
        "policy": {
            "current_floor": floor,
            "error_budget": error_budget,
            "force_human_intents": sorted(FORCE_HUMAN_INTENTS),
        },
        "recommendation": rec.as_dict(),
        "pool": {
            "size": rec.pool_size,
            "forced_human": forced,
            "by_intent": dict(sorted(intents_in_pool.items())),
        },
        "gates": {
            "emergency_never_auto": {
                "emergency_in_pool": emergency_in_pool,
                "target": "acil/sigorta otomatik havuzunda = 0",
                "pass": emergency_pass,
            },
            "floor_respected": {
                "recommended": rec.recommended_threshold,
                "floor": floor,
                "target": "önerilen ≥ güvenlik tabanı",
                "pass": floor_pass,
            },
            "error_budget_met": {
                "error_rate": rec.error_rate,
                "budget": error_budget,
                "target": "otomatik-yanıt hata ≤ bütçe",
                "pass": budget_pass,
            },
        },
    }
    report["overall_pass"] = bool(emergency_pass and floor_pass and budget_pass)
    return report


def render(report: dict) -> str:
    r = report["recommendation"]
    g = report["gates"]
    ok = lambda b: "✅" if b else "❌"  # noqa: E731
    auto = "KAPALI (aday yok)" if r["recommended_threshold"] >= NO_AUTO_REPLY else f"{r['recommended_threshold']:.4f}"
    return "\n".join([
        "İP-4.3 — Onaylardan otomatik-yanıt eşiği öğrenme",
        "=" * 50,
        f"Aday havuzu (acil-dışı): {r['pool_size']}   ·   kapı gereği insana: {r['forced_human']}",
        f"Önerilen eşik          : {auto}   (taban {report['policy']['current_floor']})",
        f"Kapsam / hata          : {r['coverage']:.4f}  /  {r['error_rate']:.4f}  (bütçe {report['policy']['error_budget']})",
        "-" * 50,
        f"{ok(g['emergency_never_auto']['pass'])} Acil daima insana (havuzda {g['emergency_never_auto']['emergency_in_pool']})",
        f"{ok(g['floor_respected']['pass'])} Güvenlik tabanı korundu",
        f"{ok(g['error_budget_met']['pass'])} Hata bütçesi",
        "=" * 50,
        f"{ok(report['overall_pass'])} GENEL: {'GEÇTİ' if report['overall_pass'] else 'KALDI'}",
    ])


def write_artifact(report: dict, path: Path = ARTIFACT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    import argparse

    from app.learning.labels import synthetic_feedback

    parser = argparse.ArgumentParser(description="İP-4.3 otomatik-yanıt eşiği öğrenme")
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(synthetic_feedback())
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
