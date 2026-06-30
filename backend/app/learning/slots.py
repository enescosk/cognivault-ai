"""İP-4.6 — Dinamik slot önerisi motoru (no-show riskine duyarlı).

İP-4.5 no-show riskini tüketir: bir hastaya hangi randevu slotlarının önerileceğini,
kliniğin doluluk dengesini ve hastanın gelmeme riskini birlikte gözeterek sıralar.

Sezgi (gate'lerle kilitlenir):
- **Riskli hasta** (risk ≥ eşik): yoğun/prime saatler cezalandırılır (gelmezse değerli
  kapasite boşa gitmesin); hatırlatma penceresi olan slotlar ödüllendirilir (hatırlatma
  riski düşürür — İP-4.7 ile bağlanır).
- **Güvenilir hasta**: prime saatler tercih edilebilir.
- **Dolu slot** (kapasite ≤ 0) asla önerilmez.
- Sıralama deterministiktir (skor ↓, sonra gün/saat/slot_id).

Saf Python. CLI: python -m app.learning.slots
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

RISK_THRESHOLD = 0.5
ARTIFACT_PATH = Path(__file__).resolve().parent / "data" / "slots.json"


@dataclass(frozen=True)
class Slot:
    slot_id: str
    day_offset: int       # 0 = bugün
    hour: int             # 8..18
    capacity_left: int
    is_peak: bool = False
    has_reminder_window: bool = False  # hatırlatma gönderecek kadar süre var mı


@dataclass(frozen=True)
class RecommendedSlot:
    slot_id: str
    day_offset: int
    hour: int
    score: float
    reasons: list[str]

    def as_dict(self) -> dict:
        return {
            "slot_id": self.slot_id,
            "day_offset": self.day_offset,
            "hour": self.hour,
            "score": self.score,
            "reasons": self.reasons,
        }


def slot_score(
    slot: Slot,
    no_show_risk: float,
    prefer_window: tuple[int, int] | None = None,
) -> tuple[float, list[str]]:
    """Tek slot için fayda skoru + gerekçeler. Dolu slot None döndürmez; çağıran filtreler."""
    show_prob = 1.0 - no_show_risk
    score = 0.0
    reasons: list[str] = []

    # Doluluk dengeleme: boş kapasiteyi doldurmaya hafif öncelik (tavan 5).
    score += 0.15 * min(slot.capacity_left, 5)

    if prefer_window and prefer_window[0] <= slot.hour <= prefer_window[1]:
        score += 0.6
        reasons.append("tercih_penceresi")

    if no_show_risk >= RISK_THRESHOLD:
        if slot.has_reminder_window:
            score += 0.5
            reasons.append("hatirlatma_penceresi")
        if slot.is_peak:
            score -= 0.7
            reasons.append("yogun_saat_cezasi")
    else:
        if slot.is_peak:
            score += 0.25
            reasons.append("guvenilir_hasta_prime")

    # Gelme olasılığıyla ölçekle (riskli hasta için tüm slotlar bir miktar değersizleşir).
    score *= 0.5 + show_prob
    return round(score, 4), reasons


def recommend_slots(
    slots: Sequence[Slot],
    no_show_risk: float,
    top_k: int = 3,
    prefer_window: tuple[int, int] | None = None,
) -> list[RecommendedSlot]:
    """Uygun slotları riske duyarlı skora göre sıralar; dolu slotları eler."""
    scored: list[RecommendedSlot] = []
    for s in slots:
        if s.capacity_left <= 0:
            continue
        score, reasons = slot_score(s, no_show_risk, prefer_window)
        scored.append(RecommendedSlot(s.slot_id, s.day_offset, s.hour, score, reasons))
    # Deterministik: skor ↓, sonra erken gün/saat, sonra slot_id.
    scored.sort(key=lambda r: (-r.score, r.day_offset, r.hour, r.slot_id))
    return scored[:top_k]


def recommend_for_patient(model, patient_features: dict, slots, **kwargs) -> list[RecommendedSlot]:
    """İP-4.5 NoShowModel'i ile riski hesaplayıp slot önerir (gerçek entegrasyon)."""
    risk = model.risk_score(patient_features)
    return recommend_slots(slots, risk, **kwargs)


# ── Deterministik sentetik senaryo (sergileme + gate) ───────────────────────
def synthetic_scenario() -> tuple[float, list[Slot], tuple[int, int]]:
    risk = 0.7  # riskli hasta
    prefer_window = (9, 12)
    slots = [
        Slot("S1", 0, 9, capacity_left=2, is_peak=False, has_reminder_window=False),
        Slot("S2", 0, 10, capacity_left=3, is_peak=True, has_reminder_window=False),
        Slot("S3", 1, 9, capacity_left=2, is_peak=False, has_reminder_window=True),
        Slot("S4", 2, 17, capacity_left=1, is_peak=False, has_reminder_window=True),
        Slot("S5", 0, 13, capacity_left=0, is_peak=False, has_reminder_window=False),  # DOLU
    ]
    return risk, slots, prefer_window


def build_report(scenario=None) -> dict:
    risk, slots, prefer_window = scenario or synthetic_scenario()
    recs = recommend_slots(slots, risk, top_k=3, prefer_window=prefer_window)
    rec_ids = {r.slot_id for r in recs}

    full_ids = {s.slot_id for s in slots if s.capacity_left <= 0}
    reminder_available = any(s.has_reminder_window and s.capacity_left > 0 for s in slots)

    # Kapı 1: dolu slot önerilmemeli.
    no_full = len(rec_ids & full_ids) == 0
    # Kapı 2: riskli hastada (≥eşik) en üst öneri, hatırlatma penceresi varsa onu taşımalı.
    reminder_pref = (
        True
        if risk < RISK_THRESHOLD or not reminder_available
        else (bool(recs) and recs[0].day_offset >= 0 and "hatirlatma_penceresi" in recs[0].reasons)
    )
    # Kapı 3: riskli hastada prime/yoğun slot #1 olmamalı (yoğun-olmayan alternatif varken).
    nonpeak_avail = any((not s.is_peak) and s.capacity_left > 0 for s in slots)
    peak_not_top = True
    if risk >= RISK_THRESHOLD and nonpeak_avail and recs:
        top_slot = next(s for s in slots if s.slot_id == recs[0].slot_id)
        peak_not_top = not top_slot.is_peak
    # Kapı 4: skorlar azalan sıralı + sınırlı.
    sorted_desc = all(recs[i].score >= recs[i + 1].score for i in range(len(recs) - 1))

    report = {
        "name": "dynamic_slot_recommender",
        "ip": "4.6",
        "input": {
            "no_show_risk": risk,
            "prefer_window": list(prefer_window),
            "n_slots": len(slots),
            "n_full": len(full_ids),
        },
        "recommendations": [r.as_dict() for r in recs],
        "gates": {
            "no_full_recommended": {"target": "dolu slot önerilmez", "pass": no_full},
            "reminder_preference": {"target": "riskli hastada hatırlatma slotu öncelikli", "pass": reminder_pref},
            "peak_not_top_for_risky": {"target": "riskli hastada yoğun slot #1 değil", "pass": peak_not_top},
            "sorted_bounded": {"target": "skor azalan + ≤ top_k", "pass": sorted_desc and len(recs) <= 3},
        },
    }
    report["overall_pass"] = bool(no_full and reminder_pref and peak_not_top and sorted_desc)
    return report


def render(report: dict) -> str:
    ok = lambda b: "✅" if b else "❌"  # noqa: E731
    lines = [
        "İP-4.6 — Dinamik slot önerisi motoru",
        "=" * 44,
        f"No-show riski: {report['input']['no_show_risk']}   tercih {report['input']['prefer_window']}",
        f"Slot: {report['input']['n_slots']} (dolu {report['input']['n_full']})",
        "Öneriler (sıralı):",
    ]
    for i, r in enumerate(report["recommendations"], 1):
        lines.append(f"  {i}. {r['slot_id']} gün+{r['day_offset']} {r['hour']}:00  skor {r['score']:.3f}  {r['reasons']}")
    lines.append("-" * 44)
    for key, g in report["gates"].items():
        lines.append(f"{ok(g['pass'])} {g['target']}")
    lines += ["=" * 44, f"{ok(report['overall_pass'])} GENEL: {'GEÇTİ' if report['overall_pass'] else 'KALDI'}"]
    return "\n".join(lines)


def write_artifact(report: dict, path: Path = ARTIFACT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="İP-4.6 dinamik slot önerisi")
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
