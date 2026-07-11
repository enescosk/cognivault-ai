from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
import re
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Clinic,
    ClinicConversation,
    ClinicPatient,
    ClinicalSlotOffer,
    ClinicalSlotOfferStatus,
)


@dataclass(frozen=True)
class DemoSlot:
    id: str
    department: str
    doctor: str
    date_label: str
    time_range: str
    capacity: int
    booked: int
    next_available: str
    waitlist_count: int = 0

    @property
    def status(self) -> str:
        if self.booked >= self.capacity:
            return "full"
        if self.capacity - self.booked <= 1:
            return "limited"
        return "available"

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "department": self.department,
            "doctor": self.doctor,
            "date_label": self.date_label,
            "time_range": self.time_range,
            "capacity": self.capacity,
            "booked": self.booked,
            "open": max(self.capacity - self.booked, 0),
            "status": self.status,
            "next_available": self.next_available,
            "waitlist_count": self.waitlist_count,
        }


DEMO_SLOTS = [
    DemoSlot("endo-tomorrow", "Endodonti", "Dr. Ece Arslan", "yarın", "09:00-12:00", 6, 6, "bugün 16:40 acil değerlendirme", 3),
    DemoSlot("endo-next", "Endodonti", "Dr. Ece Arslan", "çarşamba", "10:20-14:40", 7, 4, "çarşamba 10:20"),
    DemoSlot("perio-tomorrow", "Periodontoloji", "Dr. Burak Tan", "yarın", "13:00-17:00", 5, 4, "yarın 16:30", 1),
    DemoSlot("pedo-tomorrow", "Pedodonti", "Dr. Mina Soyer", "yarın", "10:00-15:00", 4, 2, "yarın 10:45"),
    DemoSlot("implant-friday", "İmplantoloji", "Dr. Deniz Kural", "cuma", "11:00-16:00", 5, 5, "pazartesi 09:30", 2),
    DemoSlot("restorative-today", "Restoratif Diş Tedavisi", "Dr. Selin Okan", "bugün", "15:00-18:30", 8, 6, "bugün 15:40"),
    DemoSlot("derm-tomorrow", "Dermatoloji", "Dr. Nehir Aydın", "yarın", "09:30-13:30", 6, 3, "yarın 09:30"),
    DemoSlot("aesthetic-tomorrow", "Medikal Estetik", "Dr. Lara Demir", "yarın", "14:00-18:00", 5, 5, "perşembe 12:00", 4),
]

SLOT_STATUS_LABELS = {
    "available": "Uygun",
    "limited": "Son slotlar",
    "full": "Dolu",
    "waitlist": "Bekleme listesi",
    "doctor_review": "Doktor onayı",
}

# Operatör takvim detayı için demo hasta havuzu. Gerçek ClinicalAppointment
# kayıtları henüz oluşmadan, bir bölüme tıklandığında "kim / saat kaçta /
# nerede" sorusunu görselleştirmek için deterministik randevu üretiriz.
DEMO_PATIENT_NAMES = [
    "Ayşe Yılmaz", "Mehmet Demir", "Zeynep Kaya", "Mustafa Çelik",
    "Elif Şahin", "Can Aydın", "Fatma Arslan", "Ahmet Doğan",
    "Selin Koç", "Burak Yıldız", "Merve Aksoy", "Emre Polat",
    "Hülya Öztürk", "Kerem Acar", "Nur Eren", "Tolga Şen",
]
DEMO_BRANCHES = ["Merkez Şube", "Levent Şube"]
APPOINTMENT_STATUS_LABELS = {
    "confirmed": "Onaylandı",
    "pending": "Onay bekliyor",
}


def _parse_time_range(time_range: str) -> tuple[int, int]:
    """'09:00-12:00' -> (540, 720) dakika. Hatalı formatta güvenli varsayılan."""
    try:
        start_s, end_s = time_range.split("-")
        sh, sm = (int(part) for part in start_s.strip().split(":"))
        eh, em = (int(part) for part in end_s.strip().split(":"))
        return sh * 60 + sm, eh * 60 + em
    except Exception:
        return 9 * 60, 17 * 60


def slot_appointments(slot: DemoSlot) -> list[dict]:
    """Slot başına deterministik demo randevu listesi.

    booked sayısı kadar hasta üretir; randevu saatlerini slot'un time_range'i
    içine eşit dağıtır. Aynı slot her zaman aynı sonucu verir (slot.id seed).
    """
    count = max(slot.booked, 0)
    if count == 0:
        return []
    start_min, end_min = _parse_time_range(slot.time_range)
    span = max(end_min - start_min, count * 15)
    step = span / count
    seed = sum(ord(ch) for ch in slot.id)
    appointments: list[dict] = []
    for index in range(count):
        minute = int(start_min + index * step)
        minute -= minute % 5  # 5 dakikaya yuvarla
        hour, minute_of_hour = divmod(minute, 60)
        name = DEMO_PATIENT_NAMES[(seed + index * 3) % len(DEMO_PATIENT_NAMES)]
        branch = DEMO_BRANCHES[(seed + index) % len(DEMO_BRANCHES)]
        status = "pending" if index % 4 == 3 else "confirmed"
        masked = f"+90 5{(seed + index) % 9}{(seed * 2 + index) % 10} ••• •• {(seed * 7 + index * 13) % 100:02d}"
        appointments.append(
            {
                "id": f"{slot.id}-{index + 1}",
                "time": f"{hour:02d}:{minute_of_hour:02d}",
                "patient_name": name,
                "doctor": slot.doctor,
                "branch": branch,
                "department": slot.department,
                "date_label": slot.date_label,
                "phone": masked,
                "status": status,
                "status_label": APPOINTMENT_STATUS_LABELS[status],
            }
        )
    return appointments

OFFER_TTL_MINUTES = 15
HOLD_TTL_MINUTES = 5
ISTANBUL = ZoneInfo("Europe/Istanbul")
WEEKDAYS_TR = {
    "pazartesi": 0,
    "salı": 1,
    "sali": 1,
    "çarşamba": 2,
    "carsamba": 2,
    "perşembe": 3,
    "persembe": 3,
    "cuma": 4,
    "cumartesi": 5,
    "pazar": 6,
}


def _matching_slots(department: str, preferred_time: str | None = None) -> list[DemoSlot]:
    matches = [slot for slot in DEMO_SLOTS if slot.department == department]
    if preferred_time:
        preferred_matches = [slot for slot in matches if preferred_time in slot.date_label]
        if preferred_matches:
            return preferred_matches
    return matches


def build_slot_decision(intake: dict) -> dict:
    department = intake.get("specialty") or "Genel Diş Hekimliği"
    preferred_time = intake.get("preferred_time")
    urgency = intake.get("urgency") or "routine"
    matches = _matching_slots(department, preferred_time)

    if not matches:
        return {
            "department": department,
            "preferred_time": preferred_time,
            "status": "doctor_review" if urgency in {"priority", "emergency"} else "waitlist",
            "status_label": SLOT_STATUS_LABELS["doctor_review" if urgency in {"priority", "emergency"} else "waitlist"],
            "recommended_slot": "resepsiyon uygun slot kontrolü",
            "patient_offer": "Bu bölüm için takvim eşleşmesi net değil; resepsiyon ekranında uygun hekim ve şube kontrolü gerekiyor.",
            "waitlist_count": 0,
        }

    best = next((slot for slot in matches if slot.status != "full"), None)
    if best is None:
        fallback = matches[0]
        status = "doctor_review" if urgency == "priority" else "waitlist"
        return {
            "department": department,
            "preferred_time": preferred_time,
            "status": status,
            "status_label": SLOT_STATUS_LABELS[status],
            "recommended_slot": fallback.next_available,
            "patient_offer": (
                f"{department} için istediğiniz zaman dilimi dolu. En yakın seçenek {fallback.next_available}; "
                "isterseniz bekleme listesine de ekleyebilirim."
            ),
            "waitlist_count": fallback.waitlist_count,
            "matched_slot_id": fallback.id,
        }

    return {
        "department": department,
        "preferred_time": preferred_time,
        "status": best.status,
        "status_label": SLOT_STATUS_LABELS[best.status],
        "recommended_slot": best.next_available,
        "patient_offer": f"{department} için {best.next_available} uygun görünüyor.",
        "waitlist_count": best.waitlist_count,
        "matched_slot_id": best.id,
    }


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _is_before_now(value: datetime, now: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value < now


def _parse_next_available(value: str) -> datetime:
    """Convert demo labels into concrete datetimes.

    Demo labels stay human-friendly for operator panels, but public scheduling
    must be concrete and auditable. We intentionally support a tiny grammar and
    fail closed to tomorrow 10:00 if a demo label is malformed.
    """
    now_local = datetime.now(ISTANBUL)
    text = value.lower()
    match = re.search(r"(\d{1,2})[:.](\d{2})", text)
    hour, minute = (10, 0)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))

    target_date = now_local.date()
    if "yarın" in text or "yarin" in text:
        target_date = target_date + timedelta(days=1)
    else:
        weekday = next((idx for label, idx in WEEKDAYS_TR.items() if label in text), None)
        if weekday is not None:
            delta = (weekday - now_local.weekday()) % 7
            if delta == 0:
                delta = 7
            target_date = target_date + timedelta(days=delta)
        elif "bugün" in text or "bugun" in text:
            target_date = target_date
        else:
            target_date = target_date + timedelta(days=1)

    local_dt = datetime.combine(target_date, time(hour=hour, minute=minute), tzinfo=ISTANBUL)
    if local_dt <= now_local:
        local_dt = local_dt + timedelta(days=1)
    return local_dt.astimezone(timezone.utc)


def _active_offer_statuses() -> tuple[ClinicalSlotOfferStatus, ...]:
    return (ClinicalSlotOfferStatus.OFFERED, ClinicalSlotOfferStatus.HELD)


def expire_stale_slot_offers(db: Session) -> int:
    now = _now_utc()
    stale = list(
        db.scalars(
            select(ClinicalSlotOffer).where(
                ClinicalSlotOffer.status.in_(_active_offer_statuses()),
                ClinicalSlotOffer.expires_at < now,
            )
        )
    )
    for offer in stale:
        offer.status = ClinicalSlotOfferStatus.EXPIRED
        db.add(offer)
    if stale:
        db.commit()
    return len(stale)


def build_public_slot_offers(
    db: Session,
    *,
    clinic: Clinic,
    patient: ClinicPatient,
    conversation: ClinicConversation,
    slot_decision: dict | None,
    limit: int = 3,
) -> list[ClinicalSlotOffer]:
    """Persist concrete offers for the public patient page.

    The model may identify department and urgency, but this function is the only
    place that turns that into a concrete appointment time. Existing unexpired
    offers are reused to keep refreshes and repeated sends stable.
    """
    expire_stale_slot_offers(db)
    now = _now_utc()
    existing = list(
        db.scalars(
            select(ClinicalSlotOffer)
            .where(
                ClinicalSlotOffer.clinic_id == clinic.id,
                ClinicalSlotOffer.patient_id == patient.id,
                ClinicalSlotOffer.conversation_id == conversation.id,
                ClinicalSlotOffer.status.in_(_active_offer_statuses()),
                ClinicalSlotOffer.expires_at >= now,
            )
            .order_by(ClinicalSlotOffer.starts_at.asc())
            .limit(limit)
        )
    )
    if existing:
        return existing

    decision = slot_decision or {}
    department = decision.get("department") or "Genel Diş Hekimliği"
    matched_slot_id = decision.get("matched_slot_id")
    primary = next((slot for slot in DEMO_SLOTS if slot.id == matched_slot_id), None)
    candidates = [primary] if primary else []
    candidates.extend(slot for slot in _matching_slots(department) if slot not in candidates)
    if not candidates:
        candidates = [slot for slot in DEMO_SLOTS if slot.status != "full"]

    # Adaylar anlatı sırasında gelir (eşleşen slot önce); hastaya sunum ise
    # kronolojik olmalı — "en kısa zamanda" diyen hastaya önce en erken saat.
    dated = [(slot, _parse_next_available(slot.next_available)) for slot in candidates if slot is not None]
    dated.sort(key=lambda pair: pair[1])

    concrete: list[ClinicalSlotOffer] = []
    for slot, starts_at in dated[: max(limit * 2, 1)]:
        if any(offer.starts_at == starts_at and offer.department == slot.department for offer in concrete):
            continue
        concrete.append(
            ClinicalSlotOffer(
                clinic_id=clinic.id,
                patient_id=patient.id,
                conversation_id=conversation.id,
                branch_id=None,
                department=slot.department,
                physician_name=slot.doctor,
                starts_at=starts_at,
                ends_at=starts_at + timedelta(minutes=40),
                status=ClinicalSlotOfferStatus.OFFERED,
                source="demo_slot_engine",
                expires_at=now + timedelta(minutes=OFFER_TTL_MINUTES),
                metadata_json={
                    "demo_slot_id": slot.id,
                    "status_label": SLOT_STATUS_LABELS.get(slot.status, slot.status),
                    "capacity": slot.capacity,
                    "booked": slot.booked,
                    "open": max(slot.capacity - slot.booked, 0),
                    "next_available_label": slot.next_available,
                    "waitlist_count": slot.waitlist_count,
                },
            )
        )
        if len(concrete) >= limit:
            break

    for offer in concrete:
        db.add(offer)
    if concrete:
        db.commit()
        for offer in concrete:
            db.refresh(offer)
    return concrete


def hold_slot_offer(
    db: Session,
    *,
    clinic_id: int,
    patient_id: int,
    conversation_id: int,
    offer_id: int,
) -> ClinicalSlotOffer:
    expire_stale_slot_offers(db)
    offer = db.get(ClinicalSlotOffer, offer_id)
    now = _now_utc()
    if (
        offer is None
        or offer.clinic_id != clinic_id
        or offer.patient_id != patient_id
        or offer.conversation_id != conversation_id
    ):
        raise ValueError("slot_offer_not_found")
    if offer.status not in {ClinicalSlotOfferStatus.OFFERED, ClinicalSlotOfferStatus.HELD}:
        raise ValueError("slot_offer_not_available")
    if _is_before_now(offer.expires_at, now):
        offer.status = ClinicalSlotOfferStatus.EXPIRED
        db.add(offer)
        db.commit()
        raise ValueError("slot_offer_expired")
    offer.status = ClinicalSlotOfferStatus.HELD
    offer.expires_at = now + timedelta(minutes=HOLD_TTL_MINUTES)
    db.add(offer)
    db.commit()
    db.refresh(offer)
    return offer


def consume_held_slot_offer(
    db: Session,
    *,
    clinic_id: int,
    patient_id: int,
    conversation_id: int,
    offer_id: int,
) -> ClinicalSlotOffer:
    expire_stale_slot_offers(db)
    offer = db.get(ClinicalSlotOffer, offer_id)
    now = _now_utc()
    if (
        offer is None
        or offer.clinic_id != clinic_id
        or offer.patient_id != patient_id
        or offer.conversation_id != conversation_id
    ):
        raise ValueError("slot_offer_not_found")
    if offer.status != ClinicalSlotOfferStatus.HELD:
        raise ValueError("slot_offer_must_be_held")
    if _is_before_now(offer.expires_at, now):
        offer.status = ClinicalSlotOfferStatus.EXPIRED
        db.add(offer)
        db.commit()
        raise ValueError("slot_offer_expired")
    offer.status = ClinicalSlotOfferStatus.CONSUMED
    db.add(offer)
    db.commit()
    db.refresh(offer)
    return offer


def build_slot_board() -> dict:
    full_count = sum(1 for slot in DEMO_SLOTS if slot.status == "full")
    total_capacity = sum(slot.capacity for slot in DEMO_SLOTS)
    total_booked = sum(slot.booked for slot in DEMO_SLOTS)
    return {
        "summary": {
            "clinic_mode": "live_demo",
            "occupancy_rate": round(total_booked / total_capacity, 2),
            "full_departments": full_count,
            "next_open_slot": "bugün 15:40 Restoratif Diş Tedavisi",
            "waitlist_total": sum(slot.waitlist_count for slot in DEMO_SLOTS),
        },
        "schedule": [{**slot.as_dict(), "appointments": slot_appointments(slot)} for slot in DEMO_SLOTS],
        "acceptance_rules": [
            {
                "rule": "Net randevu talebi ve uygun slot",
                "result": "AI slot önerir, eksik ad-soyad/saat bilgisini tamamlar, düşük riskte otomatik cevap verebilir.",
            },
            {
                "rule": "İstenen slot dolu",
                "result": "AI en yakın alternatifi ve bekleme listesini önerir; ağrı varsa doktor onayına alır.",
            },
            {
                "rule": "Acil belirti, kimlik, sigorta veya klinik karar",
                "result": "Otomatik gönderim yapılmaz; doktor/operatör onay paketi oluşur.",
            },
            {
                "rule": "Belirsiz veya konu dışı mesaj",
                "result": "Tanı vermeden tek netleştirme sorusu sorulur veya düşük güvenle insan onayına düşer.",
            },
        ],
        "test_scenarios": [
            {
                "label": "Uygun dental slot",
                "message": "Dolgum düştü, bugün gelebilir miyim?",
                "expected_action": "slot öner",
                "expected_result": "Restoratif Diş Tedavisi için bugün 15:40 önerisi",
            },
            {
                "label": "Dolu slot",
                "message": "Yarın kanal tedavisi için randevu istiyorum.",
                "expected_action": "alternatif ve bekleme listesi",
                "expected_result": "Endodonti yarın dolu, en yakın alternatif önerilir",
            },
            {
                "label": "Doktor onayı",
                "message": "Yanağım şişti, dişim zonkluyor, dayanamıyorum.",
                "expected_action": "shadow_review",
                "expected_result": "Priority dental symptom doktor ekranına düşer",
            },
            {
                "label": "KVKK/sigorta",
                "message": "Sigortam kanal tedavisini karşılar mı, kart numaramı vereyim mi?",
                "expected_action": "human_review",
                "expected_result": "Açık rıza ve operatör onayı gerekir",
            },
            {
                "label": "Dermatoloji",
                "message": "Cildimde leke ve akne var, dermatoloji randevusu alabilir miyim?",
                "expected_action": "slot öner",
                "expected_result": "Dermatoloji için uygun slot aranır",
            },
        ],
    }
