"""İP-5.2 — Gerçek HBYS/takvim adapteri (arayüz + dayanıklılık çekirdeği).

Bir kliniğin mevcut HBYS'i (Hastane Bilgi Yönetim Sistemi) ya da harici
takvimi (ör. dış randevu API'si) ile CogniVault randevu çekirdeğini
eşitleyen adapter soyutlaması. Gerçek satıcı entegrasyonu saha erişimi
gerektirir; bu modül satıcıdan bağımsız **dayanıklılık sözleşmesini** tanımlar
ve bellek-içi referans adapter ile kanıtlar:

- **Idempotency:** aynı `idempotency_key` ile tekrarlanan yazma tek kayıt
  üretir (ağ yeniden-denemesi çift randevu açmaz).
- **Conflict:** aynı hekim + çakışan zaman aralığı ikinci kez rezerve
  edilemez (`SlotConflictError`).
- **Retry:** geçici hata (`TransientHbysError`) sınırlı, deterministik
  yeniden-deneme ile toparlanır; kalıcı hata yükseltilir.
- **Rollback (saga):** çok adımlı işlemde (randevu + işlemler) sonraki adım
  başarısız olursa telafi (cancel) çalışır, yetim dış kayıt kalmaz.

Saf-Python, dış bağımlılık yok, tamamen deterministik (duvar-saati/rastgele
yok — geçici hatalar enjekte edilen sayaçla modellenir).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Callable, Protocol


ARTIFACT_PATH = Path(__file__).resolve().parent / "data" / "hbys_adapter.json"
DEFAULT_MAX_ATTEMPTS = 3


# ── Hatalar ──────────────────────────────────────────────────────────────────


class HbysError(Exception):
    """Adapter hatalarının kökü."""


class TransientHbysError(HbysError):
    """Yeniden denenebilir geçici hata (zaman aşımı, 5xx, kilit)."""


class PermanentHbysError(HbysError):
    """Yeniden denemenin düzeltemeyeceği kalıcı hata (geçersiz veri, 4xx)."""


class SlotConflictError(PermanentHbysError):
    """İstenen hekim/zaman aralığı zaten dolu."""


# ── Sözleşme ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BookingRequest:
    """CogniVault tarafından HBYS'e gönderilen randevu isteği.

    idempotency_key: Aynı mantıksal randevu için sabit anahtar (retry-güvenli).
    external_patient_ref / external_doctor_ref: HBYS tarafındaki kimlikler
    (ham PII değil, eşleştirme referansı).
    """

    idempotency_key: str
    external_patient_ref: str
    external_doctor_ref: str
    starts_at: datetime
    duration_minutes: int
    visit_reason: str = ""

    @property
    def ends_at(self) -> datetime:
        return self.starts_at + timedelta(minutes=self.duration_minutes)


@dataclass(frozen=True)
class BookingResult:
    external_ref: str
    idempotency_key: str
    status: str  # confirmed | cancelled
    deduplicated: bool = False  # True → mevcut kayıt döndürüldü, yeni açılmadı


class HbysAdapter(Protocol):
    """Somut HBYS/takvim entegrasyonlarının uygulaması gereken arayüz."""

    def create_booking(self, request: BookingRequest) -> BookingResult: ...

    def cancel_booking(self, external_ref: str) -> None: ...

    def find_booking(self, idempotency_key: str) -> BookingResult | None: ...


# ── Bellek-içi referans adapter ──────────────────────────────────────────────


@dataclass
class _StoredBooking:
    external_ref: str
    request: BookingRequest
    status: str


class InMemoryHbysAdapter:
    """Deterministik referans uygulama — testler ve saha-öncesi prova için.

    Gerçek satıcı adapteri bu davranışları HTTP/DB üzerinden sağlamalı; kapı
    testleri sözleşmeyi bu uygulama üzerinde doğrular.

    fail_script: create_booking çağrılarına enjekte edilen hata dizisi
    (idempotency_key -> yükselecek istisna listesi, sırayla tüketilir).
    Geçici hata sonrası retry'ı deterministik test etmek için.
    """

    def __init__(self, fail_script: dict[str, list[HbysError]] | None = None) -> None:
        self._by_ref: dict[str, _StoredBooking] = {}
        self._by_key: dict[str, str] = {}
        self._seq = 0
        self._fail_script = {k: list(v) for k, v in (fail_script or {}).items()}
        self.create_calls = 0
        self.cancel_calls = 0

    def _next_ref(self) -> str:
        self._seq += 1
        return f"HBYS-{self._seq:06d}"

    def _maybe_fail(self, request: BookingRequest) -> None:
        queued = self._fail_script.get(request.idempotency_key)
        if queued:
            raise queued.pop(0)

    def create_booking(self, request: BookingRequest) -> BookingResult:
        self.create_calls += 1
        # Idempotency: aynı anahtar varsa mevcut kaydı döndür (yan etki yok).
        existing_ref = self._by_key.get(request.idempotency_key)
        if existing_ref is not None:
            stored = self._by_ref[existing_ref]
            return BookingResult(
                external_ref=stored.external_ref,
                idempotency_key=request.idempotency_key,
                status=stored.status,
                deduplicated=True,
            )
        # Enjekte edilmiş hata (geçici/kalıcı) — anahtar kaydedilmeden önce.
        self._maybe_fail(request)
        # Conflict: aynı hekim, çakışan zaman aralığı.
        for stored in self._by_ref.values():
            if stored.status != "confirmed":
                continue
            other = stored.request
            if other.external_doctor_ref != request.external_doctor_ref:
                continue
            if request.starts_at < other.ends_at and other.starts_at < request.ends_at:
                raise SlotConflictError(
                    f"Hekim {request.external_doctor_ref} {request.starts_at.isoformat()} "
                    f"aralığında zaten dolu ({stored.external_ref})."
                )
        ref = self._next_ref()
        self._by_ref[ref] = _StoredBooking(external_ref=ref, request=request, status="confirmed")
        self._by_key[request.idempotency_key] = ref
        return BookingResult(external_ref=ref, idempotency_key=request.idempotency_key, status="confirmed")

    def cancel_booking(self, external_ref: str) -> None:
        self.cancel_calls += 1
        stored = self._by_ref.get(external_ref)
        if stored is None:
            raise PermanentHbysError(f"Bilinmeyen dış kayıt: {external_ref}")
        stored.status = "cancelled"

    def find_booking(self, idempotency_key: str) -> BookingResult | None:
        ref = self._by_key.get(idempotency_key)
        if ref is None:
            return None
        stored = self._by_ref[ref]
        return BookingResult(
            external_ref=stored.external_ref,
            idempotency_key=idempotency_key,
            status=stored.status,
            deduplicated=True,
        )

    # Test yardımcıları
    def active_bookings(self) -> list[_StoredBooking]:
        return [b for b in self._by_ref.values() if b.status == "confirmed"]


# ── Dayanıklılık sarmalayıcıları ─────────────────────────────────────────────


def sync_booking_with_retry(
    adapter: HbysAdapter,
    request: BookingRequest,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    on_attempt: Callable[[int, HbysError], None] | None = None,
) -> BookingResult:
    """Randevuyu HBYS'e yazar; geçici hatada yeniden dener.

    Idempotency anahtarı sayesinde yeniden-deneme çift kayıt açmaz. Kalıcı
    hata (conflict/geçersiz veri) hemen yükseltilir — yeniden denenmez.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts >= 1 olmalı")
    last_error: HbysError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return adapter.create_booking(request)
        except PermanentHbysError:
            raise  # Kalıcı hata — retry anlamsız.
        except TransientHbysError as exc:
            last_error = exc
            if on_attempt is not None:
                on_attempt(attempt, exc)
            continue
    assert last_error is not None
    raise last_error


@dataclass(frozen=True)
class ProcedureStep:
    """Randevuya bağlı bir işlem adımı (çok adımlı saga'nın parçası)."""

    name: str
    code: str = ""


def book_with_procedures(
    adapter: HbysAdapter,
    request: BookingRequest,
    procedures: list[ProcedureStep],
    *,
    procedure_writer: Callable[[BookingResult, ProcedureStep], None],
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> BookingResult:
    """Randevu + işlemleri tek mantıksal işlem gibi yazar (saga + rollback).

    Randevu yazıldıktan sonra işlemlerden biri başarısız olursa, telafi
    olarak randevu iptal edilir (HBYS'te yetim randevu bırakılmaz) ve hata
    yükseltilir.
    """
    result = sync_booking_with_retry(adapter, request, max_attempts=max_attempts)
    written = 0
    try:
        for step in procedures:
            procedure_writer(result, step)
            written += 1
    except Exception as exc:  # noqa: BLE001 — telafi için her hatayı yakala.
        adapter.cancel_booking(result.external_ref)
        raise HbysError(
            f"İşlem yazımı {written}/{len(procedures)} adımda başarısız; randevu geri alındı."
        ) from exc
    return result


# ── Rapor / kapılar ──────────────────────────────────────────────────────────


def _gate_idempotency() -> dict:
    adapter = InMemoryHbysAdapter()
    req = BookingRequest(
        idempotency_key="appt-1",
        external_patient_ref="P-1",
        external_doctor_ref="D-1",
        starts_at=datetime(2026, 8, 1, 10, 0),
        duration_minutes=30,
    )
    first = adapter.create_booking(req)
    second = adapter.create_booking(req)  # ağ retry gibi
    return {
        "target": "aynı idempotency_key tek kayıt üretir",
        "first_ref": first.external_ref,
        "second_ref": second.external_ref,
        "second_deduplicated": second.deduplicated,
        "active_bookings": len(adapter.active_bookings()),
        "pass": (
            first.external_ref == second.external_ref
            and second.deduplicated
            and len(adapter.active_bookings()) == 1
        ),
    }


def _gate_conflict() -> dict:
    adapter = InMemoryHbysAdapter()
    base = datetime(2026, 8, 1, 10, 0)
    adapter.create_booking(
        BookingRequest("a", "P-1", "D-1", base, 30)
    )
    blocked = False
    try:
        adapter.create_booking(
            BookingRequest("b", "P-2", "D-1", base + timedelta(minutes=15), 30)
        )
    except SlotConflictError:
        blocked = True
    # Farklı hekim aynı saatte serbest olmalı.
    other_doctor_ok = True
    try:
        adapter.create_booking(
            BookingRequest("c", "P-3", "D-2", base, 30)
        )
    except SlotConflictError:
        other_doctor_ok = False
    return {
        "target": "çakışan hekim/zaman ikinci kez rezerve edilemez; farklı hekim serbest",
        "overlap_blocked": blocked,
        "other_doctor_ok": other_doctor_ok,
        "active_bookings": len(adapter.active_bookings()),
        "pass": blocked and other_doctor_ok and len(adapter.active_bookings()) == 2,
    }


def _gate_retry() -> dict:
    # İlk iki deneme geçici hata, üçüncüde başarı.
    adapter = InMemoryHbysAdapter(
        fail_script={"retry-key": [TransientHbysError("timeout"), TransientHbysError("timeout")]}
    )
    req = BookingRequest("retry-key", "P-1", "D-1", datetime(2026, 8, 1, 11, 0), 30)
    attempts: list[int] = []
    result = sync_booking_with_retry(
        adapter, req, max_attempts=3, on_attempt=lambda n, e: attempts.append(n)
    )
    # Kalıcı hata retry edilmemeli.
    perm_adapter = InMemoryHbysAdapter(
        fail_script={"perm": [PermanentHbysError("geçersiz veri")]}
    )
    perm_retried = 0
    try:
        sync_booking_with_retry(
            perm_adapter,
            BookingRequest("perm", "P-1", "D-1", datetime(2026, 8, 1, 12, 0), 30),
            max_attempts=3,
            on_attempt=lambda n, e: None,
        )
    except PermanentHbysError:
        perm_retried = perm_adapter.create_calls
    return {
        "target": "geçici hata toparlanır (retry); kalıcı hata retry edilmez",
        "transient_attempts": len(attempts),
        "final_status": result.status,
        "permanent_create_calls": perm_retried,
        "pass": (
            result.status == "confirmed"
            and len(attempts) == 2  # iki başarısız denemede geri-çağrı
            and adapter.create_calls == 3
            and perm_retried == 1  # kalıcı hata yalnız bir kez denendi
        ),
    }


def _gate_rollback() -> dict:
    adapter = InMemoryHbysAdapter()
    req = BookingRequest("saga-1", "P-1", "D-1", datetime(2026, 8, 1, 13, 0), 30)
    procedures = [ProcedureStep("Muayene"), ProcedureStep("Röntgen"), ProcedureStep("Dolgu")]

    written: list[str] = []

    def failing_writer(result: BookingResult, step: ProcedureStep) -> None:
        if step.name == "Dolgu":
            raise RuntimeError("işlem yazımı başarısız")
        written.append(step.name)

    rolled_back = False
    try:
        book_with_procedures(
            adapter, req, procedures, procedure_writer=failing_writer
        )
    except HbysError:
        rolled_back = True

    return {
        "target": "çok adımlı işlemde kısmi hata randevuyu geri alır (yetim kayıt yok)",
        "procedures_written_before_failure": written,
        "rolled_back": rolled_back,
        "active_bookings": len(adapter.active_bookings()),
        "cancel_calls": adapter.cancel_calls,
        "pass": (
            rolled_back
            and len(adapter.active_bookings()) == 0
            and adapter.cancel_calls == 1
        ),
    }


def _gate_happy_path() -> dict:
    adapter = InMemoryHbysAdapter()
    req = BookingRequest("ok-1", "P-1", "D-1", datetime(2026, 8, 1, 9, 0), 30)
    steps = [ProcedureStep("Muayene"), ProcedureStep("Temizlik")]
    written: list[str] = []
    result = book_with_procedures(
        adapter, req, steps, procedure_writer=lambda r, s: written.append(s.name)
    )
    found = adapter.find_booking("ok-1")
    return {
        "target": "başarılı yol: randevu + tüm işlemler yazılır, bulunabilir",
        "external_ref": result.external_ref,
        "procedures_written": written,
        "found": found is not None and found.external_ref == result.external_ref,
        "pass": (
            result.status == "confirmed"
            and written == ["Muayene", "Temizlik"]
            and found is not None
            and len(adapter.active_bookings()) == 1
        ),
    }


def build_report() -> dict:
    gates = {
        "happy_path": _gate_happy_path(),
        "idempotency": _gate_idempotency(),
        "slot_conflict": _gate_conflict(),
        "retry_semantics": _gate_retry(),
        "saga_rollback": _gate_rollback(),
    }
    return {
        "name": "ip5_2_hbys_calendar_adapter",
        "purpose": "external_hbys_calendar_sync_resilience_contract",
        "gates": gates,
        "overall_pass": all(gate["pass"] for gate in gates.values()),
        "remaining": [
            "Gerçek satıcı adapteri (HBYS REST/DB) — saha erişimi ve kimlik bilgileri gerekir.",
            "Canlı idempotency anahtarının ClinicalAppointment.external_ref ile eşlenmesi.",
            "Satıcıya özgü hata haritalama (hangi HTTP kodu geçici/kalıcı).",
            "Gerçek çakışma kaynağı (HBYS takvimi) ile uçtan uca prova.",
        ],
    }


def render(report: dict) -> str:
    ok = lambda value: "PASS" if value else "FAIL"  # noqa: E731
    lines = [
        "İP-5.2 — HBYS/Takvim Adapteri Dayanıklılık Sözleşmesi",
        "=" * 60,
    ]
    for key, gate in report["gates"].items():
        lines.append(f"{ok(gate['pass']):<5} {key:<18} {gate['target']}")
    lines += ["-" * 60, f"GENEL: {ok(report['overall_pass'])}", "Kalan:"]
    lines.extend(f"- {item}" for item in report["remaining"])
    return "\n".join(lines)


def write_artifact(report: dict, path: Path = ARTIFACT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="İP-5.2 HBYS/takvim adapteri dayanıklılık panosu")
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
