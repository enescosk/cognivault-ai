"""Fazli proje hazirlik panosu.

`app.evidence` teknik cekirdegin kapilarini kanitlar. Bu modul bir ust seviye
faz panosudur: teknik kaniti aynen kullanir, fakat pilot/production icin kod
disi kalan hukuk, saha, cihaz ve ticari kapilari da gorunur tutar.

Varsayilan CLI rapor amaclidir ve exit code 0 doner. `--strict` kullanilirsa
production-ready olmayan durum CI kapisi gibi 1 doner.
"""

from __future__ import annotations

from dataclasses import dataclass
import argparse
import json
from pathlib import Path
from typing import Literal

from app.clinical.distillation import build_report as build_distillation_report
from app.evidence import build_readiness
from app.integrations.hbys import build_report as build_hbys_report
from app.onboarding.provision import build_report as build_onboarding_report
from app.ops.preflight import build_report as build_preflight_report


ARTIFACT_PATH = Path(__file__).resolve().parent / "data" / "project_readiness.json"

GateStatus = Literal["passed", "partial", "pending", "blocked"]
GateKind = Literal["technical", "engineering", "legal", "field", "commercial", "ops"]


@dataclass(frozen=True)
class PhaseGate:
    id: str
    phase: str
    title: str
    kind: GateKind
    status: GateStatus
    evidence: str
    remaining: str
    priority: int

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "phase": self.phase,
            "title": self.title,
            "kind": self.kind,
            "status": self.status,
            "pass": self.status == "passed",
            "evidence": self.evidence,
            "remaining": self.remaining,
            "priority": self.priority,
        }


def _status_rank(status: GateStatus) -> int:
    return {"blocked": 0, "pending": 1, "partial": 2, "passed": 3}[status]


def _base_gates(
    technical_passed: bool,
    distillation_passed: bool,
    onboarding_passed: bool,
    hbys_passed: bool,
    preflight_passed: bool,
) -> list[PhaseGate]:
    technical_status: GateStatus = "passed" if technical_passed else "blocked"
    technical_remaining = (
        "Teknik kanit panosunda kalan paket yok."
        if technical_passed
        else "app.evidence alt panolarinda kalan paketi duzelt ve kapilari yeniden kostur."
    )
    distillation_status: GateStatus = "partial" if distillation_passed else "pending"
    distillation_evidence = (
        "Deterministik, PII-temiz distillation veri paketi hazir; gercek egitim kosumu yok."
        if distillation_passed
        else "Korpus var; distillation veri paketi kapilari henuz gecmedi."
    )
    return [
        PhaseGate(
            id="technical_readiness_board",
            phase="İP-1/2/3.7/4/R",
            title="Teknik cekirdek kanit panosu",
            kind="technical",
            status=technical_status,
            evidence="app.evidence: teknik panolarin tek komut orkestrasyonu",
            remaining=technical_remaining,
            priority=1,
        ),
        PhaseGate(
            id="ip3_6_model_distillation",
            phase="İP-3.6",
            title="Kucuk on-prem model TR dis korpusunda damitma/ince-ayar",
            kind="engineering",
            status=distillation_status,
            evidence=distillation_evidence,
            remaining="Baseline model secimi, distillation/fine-tune kosumu, kalite/latency karsilastirma raporu.",
            priority=2,
        ),
        PhaseGate(
            id="ip3_7_real_voice_field",
            phase="İP-3.7",
            title="Gercek ses altyapisi ve saha gecikme olcumu",
            kind="field",
            status="partial",
            evidence="Turn-taking ve enerji VAD kontrol mantigi testli; gercek mikrofon/Twilio kosumu yok.",
            remaining="Mikrofon yakalama, gercek kayitlarda gurultu/aksan testi, uc-tan-uca p95 ses gecikmesi.",
            priority=3,
        ),
        PhaseGate(
            id="mobile_ios_qa_build",
            phase="Mobil",
            title="iPhone dokunmatik QA + ad hoc/TestFlight build",
            kind="field",
            status="blocked",
            evidence="Expo web ve TypeScript hazir; EAS profilleri dokumante.",
            remaining="Expo login, Apple Developer/UDID, gerekiyorsa Xcode, gercek iPhone uzerinde QA.",
            priority=4,
        ),
        PhaseGate(
            id="kvkk_legal_approval",
            phase="İP-5/6",
            title="KVKK aydinlatma, acik riza, DPA ve yurt disi aktarim hukuk onayi",
            kind="legal",
            status="blocked",
            evidence="Teknik local-first ve consent kapilari var; yazili hukukcu onayi repo disi.",
            remaining="Uzman hukukcu yazili onayi, pilot sozlesmesi/DPA, VERBIS ve saklama-silme yorumu.",
            priority=5,
        ),
        PhaseGate(
            id="pilot_clinic_contracts",
            phase="İP-5.2",
            title="3-5 pilot klinik gorusmesi ve imzali pilot baslangici",
            kind="field",
            status="blocked",
            evidence="Pilot launch pack hazir.",
            remaining="Klinik aday listesi, gorusme notlari, imzali pilot kapsam/sorumluluk metni.",
            priority=6,
        ),
        PhaseGate(
            id="field_call_trial_30",
            phase="İP-5.3",
            title="Gercek numarayla en az 30 Turkce cagri deneyi",
            kind="field",
            status="blocked",
            evidence="Webhook imza, CallSid conversation, status callback ve doctor feedback akisi testli.",
            remaining="Gercek Twilio/alternatif numara, imza dogrulama acik, gurultu/aksan/kopma/gecikme raporu.",
            priority=7,
        ),
        PhaseGate(
            id="clinic_task_completion",
            phase="İP-5.3",
            title="Resepsiyonist/hekim gorev tamamlama testi",
            kind="field",
            status="blocked",
            evidence="Web operator paneli, hekim inbox ve mobil hekim deneyimi hazir.",
            remaining="En az bir klinikte onceden sabitlenmis kritik gorev hedefleriyle saha testi.",
            priority=8,
        ),
        PhaseGate(
            id="one_day_onboarding",
            phase="İP-6.2/6.3",
            title="Tek komut tenant provizyonu + <1 gun onboarding",
            kind="engineering",
            status="partial" if onboarding_passed else "pending",
            evidence=(
                "Tek komut idempotent provizyon (klinik+sube+hekim+hizmet+personel+KVKK) kapilari testli."
                if onboarding_passed
                else "Onboarding playbook hazir; provizyon otomasyonu kapilari henuz gecmedi."
            ),
            remaining="Pilot klinikte kronometreli gercek kurulum (<6 saat) ve kanal baglama izinleri.",
            priority=9,
        ),
        PhaseGate(
            id="hbys_calendar_adapter",
            phase="İP-5.2",
            title="Gercek HBYS/takvim adapteri",
            kind="engineering",
            status="partial" if hbys_passed else "pending",
            evidence=(
                "Adapter arayuzu + dayaniklilik sozlesmesi (idempotency/conflict/retry/saga-rollback) testli."
                if hbys_passed
                else "Ic randevu modeli, cakisma kontrolu ve procedure planlama mevcut."
            ),
            remaining="Gercek satici adapteri (HBYS REST/DB), erisim/kimlik bilgileri ve canli takvimle uctan uca prova.",
            priority=10,
        ),
        PhaseGate(
            id="production_ops",
            phase="Prod",
            title="Production PostgreSQL, backup/restore, secret, alarm ve olay tatbikati",
            kind="ops",
            status="partial" if preflight_passed else "pending",
            evidence=(
                "Dagitim oncesi preflight: prod guvenlik guard'lari (zayif JWT/demo-seed/auto-schema/sqlite/CORS) + tek migration head test-kanitli."
                if preflight_passed
                else "Health/readyz, metrics, request-id ve prod runtime fail-fast kontrolleri mevcut."
            ),
            remaining="Gercek prod ortaminda migration kosumu, backup restore provasi, secret rotation, alert/runbook tatbikati.",
            priority=11,
        ),
        PhaseGate(
            id="pricing_wtp_validation",
            phase="İP-6.1",
            title="Fiyat ve odeme istekliligi validasyonu",
            kind="commercial",
            status="blocked",
            evidence="Pricing/billing model paketi hazir.",
            remaining="Pilot gorusmelerinden odeme istekliligi, plan sinirlari ve manuel fatura karari.",
            priority=12,
        ),
        PhaseGate(
            id="patent_attorney_review",
            phase="İP-6.4-6.6",
            title="Patent vekili novelty/istem incelemesi",
            kind="legal",
            status="blocked",
            evidence="Novelty cercevesi, istem taslaklari ve vekil paketi hazir.",
            remaining="Vekilin resmi arama/istem kapsami gorusu ve basvuru stratejisi.",
            priority=13,
        ),
        PhaseGate(
            id="paid_clinic_conversion",
            phase="İP-6.8",
            title="En az 5 ucretli klinik donusumu",
            kind="commercial",
            status="blocked",
            evidence="Ticari paket hazir; canli ucretli klinik kaniti yok.",
            remaining="Pilot basarisi, teklif, sozlesme ve odeme/donusum kaydi.",
            priority=14,
        ),
    ]


def build_project_readiness() -> dict:
    technical = build_readiness()
    distillation = build_distillation_report()
    onboarding = build_onboarding_report()
    hbys = build_hbys_report()
    preflight = build_preflight_report()
    gates = [
        gate.to_dict()
        for gate in _base_gates(
            bool(technical["overall_pass"]),
            bool(distillation["overall_pass"]),
            bool(onboarding["overall_pass"]),
            bool(hbys["overall_pass"]),
            bool(preflight["overall_pass"]),
        )
    ]
    counts = {
        "total": len(gates),
        "passed": sum(1 for gate in gates if gate["status"] == "passed"),
        "partial": sum(1 for gate in gates if gate["status"] == "partial"),
        "pending": sum(1 for gate in gates if gate["status"] == "pending"),
        "blocked": sum(1 for gate in gates if gate["status"] == "blocked"),
    }
    remaining = sorted(
        [gate for gate in gates if gate["status"] != "passed"],
        key=lambda gate: (gate["priority"], _status_rank(gate["status"])),
    )
    report = {
        "name": "project_readiness_board",
        "technical_overall_pass": bool(technical["overall_pass"]),
        "production_ready": all(gate["status"] == "passed" for gate in gates),
        "recommended_label": (
            "production-ready"
            if all(gate["status"] == "passed" for gate in gates)
            else "production-oriented pilot"
        ),
        "current_phase": "İP-5.2 pilot hazirlik + İP-3.6/3.7 saha teknik tamamlama",
        "technical_summary": technical["summary"],
        "distillation_summary": {
            "baseline": {
                "validation_exact_label_accuracy": distillation["baseline"]["validation"]["exact_label_accuracy"],
                "test_exact_label_accuracy": distillation["baseline"]["test"]["exact_label_accuracy"],
            },
            "dataset_artifact": distillation["dataset_artifact"],
            "eval_input_artifact": distillation["eval_input_artifact"],
            "overall_pass": bool(distillation["overall_pass"]),
            "splits": distillation["splits"],
            "total_examples": distillation["total_examples"],
        },
        "counts": counts,
        "gates": gates,
        "next_actions": [
            {
                "id": gate["id"],
                "phase": gate["phase"],
                "title": gate["title"],
                "status": gate["status"],
                "remaining": gate["remaining"],
            }
            for gate in remaining[:6]
        ],
        "overall_pass": all(gate["status"] == "passed" for gate in gates),
    }
    return report


def render(report: dict) -> str:
    status_label = {
        "passed": "PASS",
        "partial": "PARTIAL",
        "pending": "PENDING",
        "blocked": "BLOCKED",
    }
    lines = [
        "CogniVault — Fazli Proje Hazirlik Panosu",
        "=" * 72,
        f"Etiket: {report['recommended_label']}",
        f"Faz   : {report['current_phase']}",
        f"Teknik: {'PASS' if report['technical_overall_pass'] else 'BLOCKED'} "
        f"({report['technical_summary']['panels_passed']}/{report['technical_summary']['panels']} pano, "
        f"{report['technical_summary']['gates_passed']}/{report['technical_summary']['gates_total']} kapi)",
        "-" * 72,
    ]
    for gate in report["gates"]:
        label = status_label[gate["status"]]
        lines.append(f"{label:<8} {gate['phase']:<10} {gate['title'][:48]:<48}")
    lines += [
        "-" * 72,
        "Siradaki aksiyonlar:",
    ]
    for idx, action in enumerate(report["next_actions"], start=1):
        lines.append(f"{idx}. {action['phase']} / {action['title']} — {action['remaining']}")
    lines += [
        "=" * 72,
        f"GENEL: {'PASS' if report['production_ready'] else 'NOT PRODUCTION-READY'}",
    ]
    return "\n".join(lines)


def write_artifact(report: dict, path: Path = ARTIFACT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CogniVault fazli proje hazirlik panosu")
    parser.add_argument("--no-save", action="store_true", help="artefakt yazma")
    parser.add_argument("--json", action="store_true", help="JSON çıktısı")
    parser.add_argument("--strict", action="store_true", help="production-ready degilse 1 don")
    args = parser.parse_args(argv)

    report = build_project_readiness()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render(report))
    if not args.no_save:
        path = write_artifact(report)
        if not args.json:
            print(f"\nArtefakt: {path}")
    return 1 if args.strict and not report["production_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
