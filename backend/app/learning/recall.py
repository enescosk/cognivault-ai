"""İP-4.7 — Kişiye özel proaktif geri-çağırma zamanlaması.

Yarım kalan tedavi / geciken kontrol için HANGİ hastayı, NE ZAMAN proaktif arayalım?
Klinik aciliyet + gecikme + no-show riskini (İP-4.5) birleştirip öncelik sırasına dizer.

Üç yumuşatılamaz kapı (KVKK + iletişim nezaketi — yönetişim zarfıyla hizalı):
1. **Rıza kapısı:** proaktif iletişime açık rıza vermeyen hasta ASLA aranmaz.
2. **Sessiz saat:** planlanan arama daima izinli iletişim penceresinde (09–18).
3. **Cooldown:** son temastan bu yana < cooldown gün geçen hasta tekrar aranmaz (spam yok).

Ham PII taşınmaz; hasta yalnızca anonim referansla temsil edilir.
Saf Python. CLI: python -m app.learning.recall
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

CONTACT_WINDOW = (9, 18)   # izinli arama saatleri (dahil)
COOLDOWN_DAYS = 14
URGENCY_WEIGHT = {"high": 1.0, "medium": 0.6, "low": 0.3}
ARTIFACT_PATH = Path(__file__).resolve().parent / "data" / "recall.json"


@dataclass(frozen=True)
class RecallCandidate:
    patient_ref: str            # anonim referans (ham PII yok)
    treatment_incomplete: bool
    days_overdue: int           # önerilen kontrolden bu yana gün
    no_show_risk: float         # İP-4.5 çıktısı
    consent_outreach: bool      # proaktif iletişime açık rıza
    days_since_last_contact: int
    urgency: str = "medium"     # high | medium | low
    preferred_channel: str = "sms"


@dataclass(frozen=True)
class ScheduledRecall:
    patient_ref: str
    priority: float
    scheduled_hour: int
    channel: str
    reasons: list[str]

    def as_dict(self) -> dict:
        return {
            "patient_ref": self.patient_ref,
            "priority": self.priority,
            "scheduled_hour": self.scheduled_hour,
            "channel": self.channel,
            "reasons": self.reasons,
        }


def recall_priority(c: RecallCandidate) -> tuple[float, list[str]]:
    """Geri-çağırma önceliği + gerekçeler. Yüksek = daha acil ulaşılmalı."""
    reasons: list[str] = []
    score = URGENCY_WEIGHT.get(c.urgency, 0.3)
    reasons.append(f"aciliyet_{c.urgency}")
    if c.treatment_incomplete:
        score += 0.3
        reasons.append("yarim_tedavi")
    if c.days_overdue > 0:
        score += 0.02 * min(c.days_overdue, 60)
        reasons.append("geciken_kontrol")
    # Yüksek no-show riski → nazik hatırlatma daha da değerli.
    score += 0.2 * c.no_show_risk
    if c.no_show_risk >= 0.5:
        reasons.append("yuksek_noshow_riski")
    return round(score, 4), reasons


def _eligible(c: RecallCandidate) -> bool:
    """Rıza + cooldown kapıları — ikisini de geçmeyen aranmaz."""
    return c.consent_outreach and c.days_since_last_contact >= COOLDOWN_DAYS


def schedule_recalls(
    candidates: Sequence[RecallCandidate],
    top_k: int | None = None,
    window: tuple[int, int] = CONTACT_WINDOW,
) -> list[ScheduledRecall]:
    """Uygun adayları önceliğe göre sıralar ve sessiz-saat içinde zamanlar."""
    eligible = [c for c in candidates if _eligible(c)]
    scored = []
    for c in eligible:
        pr, reasons = recall_priority(c)
        scored.append((pr, reasons, c))
    # Deterministik: öncelik ↓, sonra patient_ref.
    scored.sort(key=lambda t: (-t[0], t[2].patient_ref))

    span = window[1] - window[0]
    out: list[ScheduledRecall] = []
    for idx, (pr, reasons, c) in enumerate(scored):
        # Pencere içinde dağıt (daima izinli aralıkta kalır).
        hour = window[0] + (idx % (span + 1))
        out.append(ScheduledRecall(c.patient_ref, pr, hour, c.preferred_channel, reasons))
    return out[:top_k] if top_k is not None else out


# ── Deterministik sentetik senaryo ──────────────────────────────────────────
def synthetic_candidates() -> list[RecallCandidate]:
    return [
        RecallCandidate("P-001", True, 40, 0.72, True, 30, "high", "call"),
        RecallCandidate("P-002", False, 10, 0.30, True, 21, "low", "sms"),
        RecallCandidate("P-003", True, 95, 0.60, True, 60, "medium", "whatsapp"),
        # Rıza yok → asla aranmaz:
        RecallCandidate("P-004", True, 50, 0.80, False, 90, "high", "call"),
        # Cooldown içinde (son temas 5 gün önce) → aranmaz:
        RecallCandidate("P-005", True, 20, 0.55, True, 5, "high", "sms"),
        RecallCandidate("P-006", False, 30, 0.45, True, 45, "medium", "sms"),
    ]


def build_report(candidates: Sequence[RecallCandidate] | None = None) -> dict:
    candidates = list(candidates if candidates is not None else synthetic_candidates())
    scheduled = schedule_recalls(candidates)
    scheduled_refs = {s.patient_ref for s in scheduled}

    no_consent_refs = {c.patient_ref for c in candidates if not c.consent_outreach}
    cooldown_refs = {c.patient_ref for c in candidates if c.days_since_last_contact < COOLDOWN_DAYS}

    consent_pass = len(scheduled_refs & no_consent_refs) == 0
    cooldown_pass = len(scheduled_refs & cooldown_refs) == 0
    quiet_pass = all(CONTACT_WINDOW[0] <= s.scheduled_hour <= CONTACT_WINDOW[1] for s in scheduled)
    sorted_pass = all(scheduled[i].priority >= scheduled[i + 1].priority for i in range(len(scheduled) - 1))

    report = {
        "name": "proactive_recall_scheduler",
        "ip": "4.7",
        "input": {
            "n_candidates": len(candidates),
            "n_no_consent": len(no_consent_refs),
            "n_in_cooldown": len(cooldown_refs),
            "contact_window": list(CONTACT_WINDOW),
            "cooldown_days": COOLDOWN_DAYS,
        },
        "scheduled": [s.as_dict() for s in scheduled],
        "gates": {
            "consent_gate": {"target": "rızasız hasta aranmaz", "pass": consent_pass},
            "quiet_hours": {"target": "arama izinli saat penceresinde", "pass": quiet_pass},
            "cooldown_gate": {"target": "cooldown içinde tekrar aranmaz", "pass": cooldown_pass},
            "priority_sorted": {"target": "öncelik azalan sıralı", "pass": sorted_pass},
        },
    }
    report["overall_pass"] = bool(consent_pass and quiet_pass and cooldown_pass and sorted_pass)
    return report


def render(report: dict) -> str:
    ok = lambda b: "✅" if b else "❌"  # noqa: E731
    inp = report["input"]
    lines = [
        "İP-4.7 — Proaktif geri-çağırma zamanlayıcı",
        "=" * 46,
        f"Aday: {inp['n_candidates']}  (rızasız {inp['n_no_consent']} · cooldown {inp['n_in_cooldown']})",
        f"Pencere {inp['contact_window']} · cooldown {inp['cooldown_days']} gün",
        "Planlanan aramalar (öncelik sırası):",
    ]
    for i, s in enumerate(report["scheduled"], 1):
        lines.append(f"  {i}. {s['patient_ref']} @ {s['scheduled_hour']}:00 [{s['channel']}]  öncelik {s['priority']:.3f}  {s['reasons']}")
    lines.append("-" * 46)
    for g in report["gates"].values():
        lines.append(f"{ok(g['pass'])} {g['target']}")
    lines += ["=" * 46, f"{ok(report['overall_pass'])} GENEL: {'GEÇTİ' if report['overall_pass'] else 'KALDI'}"]
    return "\n".join(lines)


def write_artifact(report: dict, path: Path = ARTIFACT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="İP-4.7 proaktif geri-çağırma")
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
