"""İP-6.1 — Abonelik + başarı-bazlı faturalama MVP'si.

`docs/commercial/IP-6.1-pricing-billing-model.md`'deki ticari modeli makine-okur,
deterministik bir faturalama motoruna çevirir: bir klinik + bir ay için sabit
abonelik ücretini, başarılı randevu başına düşen başarı ücretini ve tavanı
hesaplar; olay kırılımını ve yumuşatılamaz faturalama kapılarını raporlar.

DİKKAT: `app/services/billing_service.py` AYRI bir modüldür (USD SaaS kota /
LLM maliyet guardrail'i). Bu modül onun yerine geçmez, ona dokunmaz.

Beş yumuşatılamaz faturalama kapısı (docs §6):
1. **KVKK kapısı:** KVKK/onay akışı tamamlanmamış randevu ücretlendirilemez.
2. **Audit kapısı:** audit-log'a yazılmamış randevu ücretlendirilemez.
3. **İnsan-inceleme kapısı:** human_review=True karar otomatik "başarılı
   randevu" sayılamaz → başarı ücreti üretmez.
4. **No-show/iptal kapısı:** no-show/iptal edilen randevu başarı ücreti üretmez.
5. **Tavan kapısı:** Growth ilk 3 ay, başarı ücreti sabit ücretin %100'ünü
   aşamaz (aşan kısım tavana kırpılır).

NOT: Buradaki TL rakamları pilot-öncesi tahmindir; docs "gerçek fiyat pilot
ödeme istekliliğiyle valide edilir" der. Sabit sayılar tek doğru kaynak olarak
aşağıdaki sabitlerde tutulur.

Ham PII taşınmaz; klinik/randevu yalnızca anonim referansla temsil edilir.
Saf Python, deterministik. CLI: python -m app.billing.success_billing
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

CURRENCY = "TL"

# ── Fiyatlandırma — tek doğru kaynak (docs §2, §3). Pilotla valide edilecek. ──
STARTER = "starter"
GROWTH = "growth"
ENTERPRISE = "enterprise"

MONTHLY_BASE_TL = {
    STARTER: 7500.0,
    GROWTH: 18500.0,
    ENTERPRISE: 0.0,   # özel fiyat — sözleşmeyle belirlenir, MVP'de 0 tutulur
}
SUCCESS_FEE_PER_APPOINTMENT_TL = {
    STARTER: 0.0,
    GROWTH: 75.0,
    ENTERPRISE: 0.0,   # özel — sözleşmeyle
}
SUCCESS_FEE_CAP_MONTHS = 3     # Growth: tavan yalnızca ilk 3 ay geçerli
SUCCESS_FEE_CAP_RATIO = 1.0    # tavan = sabit ücretin %100'ü

# ── Faturalama olay tipleri (docs §5) — referans/doğrulama için tek kaynak. ──
EVENT_TYPES = frozenset({
    "subscription_started",
    "subscription_renewed",
    "appointment_created_by_ai",
    "appointment_confirmed_by_clinic",
    "appointment_completed",
    "appointment_no_show",
    "plan_changed",
    "trial_converted",
})

# ── Randevu durumları ───────────────────────────────────────────────────────
SUCCESS_STATUS = "completed"   # MVP: başarı ücretini "tamamlanan" randevu tetikler (docs §3/§9)
BLOCKING_STATUSES = frozenset({"no_show", "cancelled"})  # başarı ücreti üretmez
APPOINTMENT_STATUSES = frozenset({"created", "confirmed", "completed", "no_show", "cancelled"})

ARTIFACT_PATH = Path(__file__).resolve().parent / "data" / "success_billing.json"


@dataclass(frozen=True)
class AppointmentRecord:
    """Bir aya ait tek randevunun anonim faturalama görünümü (ham PII yok)."""
    appointment_ref: str          # anonim referans
    status: str                   # created | confirmed | completed | no_show | cancelled
    kvkk_completed: bool          # KVKK/onay akışı tamam mı
    audit_logged: bool            # audit-log'a yazıldı mı
    human_review: bool = False    # hekim/insan incelemesi gerekiyor mu


@dataclass(frozen=True)
class ClinicMonth:
    """Bir klinik + bir ayın faturalama girdisi."""
    clinic_ref: str               # anonim referans
    plan: str                     # starter | growth | enterprise
    month_index: int              # abonelik başından itibaren ay no (1-based) — tavan penceresi
    appointments: tuple[AppointmentRecord, ...] = ()


def appointment_billing(appt: AppointmentRecord) -> tuple[bool, list[str]]:
    """Randevu başarı ücreti üretir mi? (billable, engelleyen_gerekçeler).

    Gerekçe listesi boşsa randevu ücretlendirilebilir. Her yumuşatılamaz kapı
    burada tek noktada uygulanır."""
    blockers: list[str] = []
    if appt.status in BLOCKING_STATUSES:
        blockers.append(f"durum_{appt.status}")          # no-show/iptal kapısı
    elif appt.status != SUCCESS_STATUS:
        blockers.append("tamamlanmadi")                  # henüz başarılı sayılmaz
    if not appt.kvkk_completed:
        blockers.append("kvkk_eksik")                    # KVKK kapısı
    if not appt.audit_logged:
        blockers.append("audit_eksik")                   # audit kapısı
    if appt.human_review:
        blockers.append("insan_incelemesi")              # insan-inceleme kapısı
    return (not blockers, blockers)


def summarize_month(cm: ClinicMonth) -> dict:
    """Bir klinik-ayı için sabit + başarı ücreti + tavan + toplam TL raporu."""
    if cm.plan not in MONTHLY_BASE_TL:
        raise ValueError(f"Bilinmeyen plan: {cm.plan!r}")

    base_fee = MONTHLY_BASE_TL[cm.plan]
    fee_per = SUCCESS_FEE_PER_APPOINTMENT_TL[cm.plan]

    counts: dict[str, int] = {}
    billable_refs: list[str] = []
    blocked: dict[str, list[str]] = {}
    for appt in cm.appointments:
        counts[appt.status] = counts.get(appt.status, 0) + 1
        ok, blockers = appointment_billing(appt)
        if ok:
            billable_refs.append(appt.appointment_ref)
        else:
            blocked[appt.appointment_ref] = blockers

    billable_refs.sort()
    n_billable = len(billable_refs)
    success_fee_raw = round(n_billable * fee_per, 2)

    cap_applies = cm.plan == GROWTH and cm.month_index <= SUCCESS_FEE_CAP_MONTHS
    cap_amount = round(base_fee * SUCCESS_FEE_CAP_RATIO, 2) if cap_applies else None
    if cap_applies:
        success_fee_capped = round(min(success_fee_raw, cap_amount), 2)
    else:
        success_fee_capped = success_fee_raw
    removed_by_cap = round(success_fee_raw - success_fee_capped, 2)
    total = round(base_fee + success_fee_capped, 2)

    return {
        "clinic_ref": cm.clinic_ref,
        "plan": cm.plan,
        "month_index": cm.month_index,
        "currency": CURRENCY,
        "base_fee_tl": base_fee,
        "success_fee_per_appointment_tl": fee_per,
        "counts": dict(sorted(counts.items())),
        "n_billable": n_billable,
        "billable_refs": billable_refs,
        "blocked": dict(sorted(blocked.items())),
        "success_fee_raw_tl": success_fee_raw,
        "cap_applies": cap_applies,
        "cap_amount_tl": cap_amount,
        "success_fee_capped_tl": success_fee_capped,
        "success_fee_removed_by_cap_tl": removed_by_cap,
        "total_tl": total,
    }


# ── Deterministik sentetik senaryo ──────────────────────────────────────────
def synthetic_clinic_months() -> list[ClinicMonth]:
    clean = lambda ref: AppointmentRecord(ref, "completed", True, True, False)  # noqa: E731
    return [
        # Growth 1. ay: tavanı tetikleyecek yoğun hacim + her kapıyı test eden engelli kayıtlar.
        # 300 temiz tamamlanan × 75 TL = 22.500 TL > 18.500 TL tavan → 4.000 TL kırpılır.
        ClinicMonth(
            clinic_ref="C-001",
            plan=GROWTH,
            month_index=1,
            appointments=tuple(
                [clean(f"A-{i:03d}") for i in range(300)]
                + [
                    AppointmentRecord("A-noshow", "no_show", True, True, False),
                    AppointmentRecord("A-cancel", "cancelled", True, True, False),
                    AppointmentRecord("A-kvkk", "completed", False, True, False),
                    AppointmentRecord("A-audit", "completed", True, False, False),
                    AppointmentRecord("A-human", "completed", True, True, True),
                    AppointmentRecord("A-open", "confirmed", True, True, False),
                ]
            ),
        ),
        # Growth 4. ay: tavan penceresi dışı → başarı ücreti kırpılmaz.
        ClinicMonth(
            clinic_ref="C-002",
            plan=GROWTH,
            month_index=4,
            appointments=tuple(clean(f"B-{i:03d}") for i in range(300)),
        ),
        # Starter: başarı ücreti yok, yalnızca sabit ücret.
        ClinicMonth("C-003", STARTER, 1, (clean("S-001"), clean("S-002"))),
        # Enterprise: özel fiyat (MVP'de 0), başarı ücreti yok.
        ClinicMonth("C-004", ENTERPRISE, 1, (clean("E-001"),)),
    ]


def build_report(clinic_months: Sequence[ClinicMonth] | None = None) -> dict:
    clinic_months = list(clinic_months if clinic_months is not None else synthetic_clinic_months())
    summaries = [summarize_month(cm) for cm in clinic_months]

    all_billable: set[str] = set()
    for s in summaries:
        all_billable.update(s["billable_refs"])

    # Her yumuşatılamaz kapı: engellenmesi gereken hiçbir randevu ücretlenmemeli.
    kvkk_pass = audit_pass = human_pass = noshow_pass = True
    for cm in clinic_months:
        for appt in cm.appointments:
            billed = appt.appointment_ref in all_billable
            if not appt.kvkk_completed and billed:
                kvkk_pass = False
            if not appt.audit_logged and billed:
                audit_pass = False
            if appt.human_review and billed:
                human_pass = False
            if appt.status in BLOCKING_STATUSES and billed:
                noshow_pass = False

    # Tavan kapısı: tavan uygulanan her ayda başarı ücreti sabit ücreti aşamaz.
    cap_pass = all(
        s["success_fee_capped_tl"] <= s["base_fee_tl"]
        for s in summaries
        if s["cap_applies"]
    )

    gates = {
        "kvkk_gate": {
            "target": "KVKK/onay tamamlanmamış randevu ücretlendirilmez",
            "pass": kvkk_pass,
        },
        "audit_gate": {
            "target": "audit-log'a yazılmamış randevu ücretlendirilmez",
            "pass": audit_pass,
        },
        "human_review_gate": {
            "target": "insan incelemesi gereken karar otomatik başarı sayılmaz",
            "pass": human_pass,
        },
        "no_show_gate": {
            "target": "no-show/iptal randevu başarı ücreti üretmez",
            "pass": noshow_pass,
        },
        "success_fee_cap": {
            "target": "Growth ilk 3 ay başarı ücreti sabit ücretin %100'ünü aşmaz",
            "cap_months": SUCCESS_FEE_CAP_MONTHS,
            "cap_ratio": SUCCESS_FEE_CAP_RATIO,
            "pass": cap_pass,
        },
    }

    report = {
        "name": "ip6_1_success_billing",
        "ip": "6.1",
        "currency": CURRENCY,
        "plans": {
            plan: {
                "base_fee_tl": MONTHLY_BASE_TL[plan],
                "success_fee_per_appointment_tl": SUCCESS_FEE_PER_APPOINTMENT_TL[plan],
            }
            for plan in sorted(MONTHLY_BASE_TL)
        },
        "cap": {
            "months": SUCCESS_FEE_CAP_MONTHS,
            "ratio": SUCCESS_FEE_CAP_RATIO,
            "note": "Growth ilk 3 ay: başarı ücreti sabit ücretin %100'ünü aşamaz.",
        },
        "event_types": sorted(EVENT_TYPES),
        "summaries": summaries,
        "gates": gates,
        "notes": [
            "TL rakamları pilot-öncesi tahmindir; gerçek fiyat pilot ödeme "
            "istekliliğiyle valide edilir (docs §1, §9).",
            "Başarı ücretini MVP'de 'tamamlanan' randevu tetikler; ücretli fazda "
            "'onaylanan' vs 'tamamlanan' modeli klinikle seçilir (docs §3).",
        ],
        "remaining": [
            "Gerçek ödeme/fatura entegrasyonu (docs §10 — pilot sonrası seçilir).",
            "Fiyatların pilot ödeme istekliliğiyle validasyonu (docs §9).",
            "Faturalama olaylarının canlı randevu/audit hattına bağlanması.",
        ],
    }
    report["overall_pass"] = all(gate["pass"] for gate in gates.values())
    return report


def render(report: dict) -> str:
    ok = lambda b: "✅" if b else "❌"  # noqa: E731
    lines = [
        "İP-6.1 — Abonelik + Başarı-Bazlı Faturalama",
        "=" * 60,
        "Planlar (TL/ay · başarı ücreti/randevu):",
    ]
    for plan, p in report["plans"].items():
        lines.append(f"  {plan:<11} {p['base_fee_tl']:>10.2f}  +{p['success_fee_per_appointment_tl']:>7.2f}")
    lines += [
        f"Tavan: Growth ilk {report['cap']['months']} ay, sabit ücretin %{int(report['cap']['ratio'] * 100)}'ü",
        "-" * 60,
        "Aylık özetler:",
    ]
    for s in report["summaries"]:
        cap_note = ""
        if s["cap_applies"] and s["success_fee_removed_by_cap_tl"] > 0:
            cap_note = f"  (tavan: -{s['success_fee_removed_by_cap_tl']:.2f})"
        lines.append(
            f"  {s['clinic_ref']} [{s['plan']}/ay {s['month_index']}] "
            f"sabit {s['base_fee_tl']:.2f} + başarı {s['success_fee_capped_tl']:.2f}"
            f" ({s['n_billable']} randevu) = {s['total_tl']:.2f} TL{cap_note}"
        )
    lines.append("-" * 60)
    for g in report["gates"].values():
        lines.append(f"{ok(g['pass'])} {g['target']}")
    lines += [
        "=" * 60,
        f"{ok(report['overall_pass'])} GENEL: {'GEÇTİ' if report['overall_pass'] else 'KALDI'}",
        "Not: " + report["notes"][0],
    ]
    return "\n".join(lines)


def write_artifact(report: dict, path: Path = ARTIFACT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="İP-6.1 abonelik + başarı-bazlı faturalama")
    parser.add_argument("--no-save", action="store_true", help="artefakt yazma")
    parser.add_argument("--json", action="store_true", help="JSON çıktısı")
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
