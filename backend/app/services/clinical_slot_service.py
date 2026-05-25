from __future__ import annotations

from dataclasses import dataclass


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
        "schedule": [slot.as_dict() for slot in DEMO_SLOTS],
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
