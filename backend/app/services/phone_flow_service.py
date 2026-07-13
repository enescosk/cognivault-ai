"""Telefon randevu akışı — Yol A (Gather turlu, durum makineli).

Web hasta sayfasındaki teklif → seç → onayla zincirini telefon kanalına taşır.
Bugüne kadar telefon tek yönlü intake'ti: arayan şikayetini söylüyor, sistem
"doktor ekranına düştü" deyip kapatıyordu — randevu telefonda KAPANMIYORDU.

Durum, `ClinicConversation.metadata_json["phone_flow"]` içinde yaşar:
    {"stage": "offering", "offer_ids": [1, 2, 3]}
Telefonda ayrıca "hold" adımı yoktur (web'deki slot-picker'ın karşılığı sözlü
seçimdir): eşleşen teklif tek adımda gerçek takvim slotunu kilitler
(`book_underlying_calendar_slot`), randevuyu yaratır ve SMS'leri gönderir.

Güvenlik değişmezleri:
- Acil/insan-yükseltme yolları DOKUNULMAZDIR: `shadow_review` üretilen veya
  acil intent'li turlarda bu servis devreye girmez (None döner, mevcut
  eskalasyon yanıtı kullanılır).
- Somut randevu saatleri yalnızca ClinicalSlotOffer tablosundan geçer — bu
  modül de saat İCAT ETMEZ, web ile aynı teklif motorunu kullanır.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Clinic,
    ClinicConversation,
    ClinicConversationStatus,
    ClinicIntent,
    ClinicPatient,
    ClinicalAppointment,
    ClinicalAppointmentStatus,
    ClinicalSlotOffer,
    ClinicalSlotOfferStatus,
)
from app.services.clinical_appointment_service import resolve_appointment_doctor
from app.services.clinical_service import IngestionResult
from app.services.clinical_slot_service import (
    ISTANBUL,
    book_underlying_calendar_slot,
    build_public_slot_offers,
)
from app.services.notification_service import (
    _format_dt_tr,
    send_appointment_sms_to_doctor,
    send_appointment_sms_to_patient,
)

logger = logging.getLogger(__name__)

# Sözlü seçimde konuşulan turda kaç teklif okunur (TTS uzunluğu ↔ seçenek dengesi)
MAX_SPOKEN_OFFERS = 3


@dataclass(frozen=True)
class PhoneTurnOutcome:
    reply: str
    stage: str  # "offering" | "booked"


# ─── Sözlü slot eşleme ───────────────────────────────────────────────────────

_ORDINAL_PATTERNS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"\b(birincisi|birinciyi|birinci|ilkini|ilki|ilk|bir numara)\b"), 0),
    (re.compile(r"\b(ikincisi|ikinciyi|ikinci|iki numara)\b"), 1),
    (re.compile(r"\b(üçüncüsü|üçüncüyü|üçüncü|ucuncu|üç numara)\b"), 2),
]
_ANY_SLOT = re.compile(r"ilk uygun|fark ?etmez|hangisi olursa|uygun olan|siz seçin|en erken")
_WEEKDAYS_TR = {
    "pazartesi": 0, "salı": 1, "sali": 1, "çarşamba": 2, "carsamba": 2,
    "perşembe": 3, "persembe": 3, "cuma": 4, "cumartesi": 5, "pazar": 6,
}
# Konuşma dilinde saat: "dokuz", "dokuz buçuk", "on dört" … STT çoğu zaman
# rakam yazar ("9.30", "14:00"); kelime hâli de yaygın olduğundan ikisi de
# desteklenir. Uzun ifadeler önce eşleşsin diye uzunluğa göre sıralanır.
_HOUR_WORDS = {
    "sekiz": 8, "dokuz": 9, "on bir": 11, "on iki": 12, "on üç": 13,
    "on dört": 14, "on beş": 15, "on altı": 16, "on yedi": 17, "on": 10,
}


def _spoken_hour(text: str) -> tuple[int, int] | None:
    """Konuşulan metinden (saat, dakika) çıkarır; bulunamazsa None."""
    digit = re.search(r"\b(\d{1,2})(?:[:.](\d{2}))?\b", text)
    if digit:
        hour = int(digit.group(1))
        minute = int(digit.group(2)) if digit.group(2) else (30 if "buçuk" in text else 0)
        if 0 <= hour <= 23:
            return hour, minute
    for word in sorted(_HOUR_WORDS, key=len, reverse=True):
        if re.search(rf"\b{word}\b", text):
            return _HOUR_WORDS[word], 30 if "buçuk" in text else 0
    return None


def _local(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ISTANBUL)


def match_spoken_slot(text: str, offers: list[ClinicalSlotOffer]) -> ClinicalSlotOffer | None:
    """Arayanın söylediğini tekliflerden biriyle eşler.

    Sıra: "fark etmez/ilk uygun" → ilk teklif; sıra sözü (birinci/ikinci/üçüncü);
    gün adı + saat filtreleri (frontend matchSlot ile aynı yaklaşım).
    """
    if not offers:
        return None
    s = text.strip().lower().replace("i̇", "i")

    if _ANY_SLOT.search(s):
        return offers[0]
    for pattern, index in _ORDINAL_PATTERNS:
        if pattern.search(s) and index < len(offers):
            return offers[index]

    candidates = offers
    weekday = next((idx for name, idx in _WEEKDAYS_TR.items() if name in s), None)
    if weekday is not None:
        candidates = [o for o in candidates if _local(o.starts_at).weekday() == weekday]
    if "yarın" in s or "yarin" in s:
        tomorrow = (datetime.now(ISTANBUL) + timedelta(days=1)).date()
        candidates = [o for o in candidates if _local(o.starts_at).date() == tomorrow]
    hour_minute = _spoken_hour(s)
    if hour_minute is not None:
        hour, minute = hour_minute
        exact = [
            o for o in candidates
            if _local(o.starts_at).hour == hour and _local(o.starts_at).minute == minute
        ]
        if exact:
            return exact[0]
        by_hour = [o for o in candidates if _local(o.starts_at).hour == hour]
        if by_hour:
            return by_hour[0]
        return None  # saat söyledi ama tutmadı — yanlış slot bağlamak yerine tekrar sor
    if weekday is not None and candidates:
        return candidates[0]
    return None


# ─── Konuşma yanıtları ───────────────────────────────────────────────────────

_ORDINAL_LABELS = ["birinci", "ikinci", "üçüncü"]


def _speak_offers(offers: list[ClinicalSlotOffer]) -> str:
    parts = []
    for i, offer in enumerate(offers[:MAX_SPOKEN_OFFERS]):
        doctor = f", {offer.physician_name}" if offer.physician_name else ""
        parts.append(f"{_ORDINAL_LABELS[i]}: {_format_dt_tr(offer.starts_at)}{doctor}")
    listing = "; ".join(parts)
    return (
        f"Sizin için müsait randevu saatleri şunlar: {listing}. "
        "Hangisini istersiniz? Örneğin birincisi diyebilirsiniz."
    )


def _load_active_offers(db: Session, conversation: ClinicConversation, offer_ids: list[int]) -> list[ClinicalSlotOffer]:
    if not offer_ids:
        return []
    now = datetime.now(timezone.utc)
    offers = list(
        db.scalars(
            select(ClinicalSlotOffer)
            .where(
                ClinicalSlotOffer.id.in_(offer_ids),
                ClinicalSlotOffer.conversation_id == conversation.id,
                ClinicalSlotOffer.status.in_(
                    (ClinicalSlotOfferStatus.OFFERED, ClinicalSlotOfferStatus.HELD)
                ),
            )
            .order_by(ClinicalSlotOffer.starts_at.asc())
        )
    )
    return [
        o for o in offers
        if (o.expires_at.replace(tzinfo=timezone.utc) if o.expires_at.tzinfo is None else o.expires_at) >= now
    ]


def _set_stage(db: Session, conversation: ClinicConversation, stage: dict | None) -> None:
    meta = dict(conversation.metadata_json or {})
    if stage is None:
        meta.pop("phone_flow", None)
    else:
        meta["phone_flow"] = stage
    conversation.metadata_json = meta
    db.add(conversation)


def _confirm_offer(
    db: Session,
    *,
    clinic: Clinic,
    patient: ClinicPatient,
    conversation: ClinicConversation,
    offer: ClinicalSlotOffer,
) -> str:
    """Sözlü seçimi randevuya çevirir (web confirm akışının telefon karşılığı)."""
    booked_slot = book_underlying_calendar_slot(db, offer)  # dolmuşsa ValueError
    offer.status = ClinicalSlotOfferStatus.CONSUMED
    db.add(offer)

    assigned_doctor = resolve_appointment_doctor(
        db, clinic, physician_name=offer.physician_name, department=offer.department
    )
    # Ingest hattı randevu-niyetli turda doktor ekranı için PENDING bir TASLAK
    # yaratmış olabilir (created_from=ai_conversation_draft). Yeni kayıt açıp
    # çift randevu üretmek yerine o taslağı somut seçimle GÜNCELLE.
    draft = db.scalars(
        select(ClinicalAppointment)
        .where(
            ClinicalAppointment.conversation_id == conversation.id,
            ClinicalAppointment.clinic_id == clinic.id,
            ClinicalAppointment.status == ClinicalAppointmentStatus.PENDING,
        )
        .order_by(ClinicalAppointment.id.desc())
    ).first()
    appointment = draft or ClinicalAppointment(
        clinic_id=clinic.id,
        patient_id=patient.id,
        conversation_id=conversation.id,
        status=ClinicalAppointmentStatus.PENDING,
        metadata_json={},
    )
    appointment.branch_id = offer.branch_id
    appointment.doctor_id = booked_slot.doctor_id if booked_slot else None
    appointment.slot_id = booked_slot.id if booked_slot else None
    appointment.assigned_doctor_id = assigned_doctor.id if assigned_doctor else None
    appointment.department = offer.department
    appointment.starts_at = offer.starts_at
    appointment.ends_at = offer.ends_at or (offer.starts_at + timedelta(minutes=30))
    appointment.duration_minutes = (
        max(15, int((offer.ends_at - offer.starts_at).total_seconds() // 60))
        if offer.ends_at
        else 30
    )
    appointment.visit_reason = appointment.visit_reason or offer.department
    appointment.metadata_json = {
        **(appointment.metadata_json or {}),
        "source": "phone_call",
        "slot_offer_id": offer.id,
        "slot_offer_source": offer.source,
        "physician_name": offer.physician_name,
        "confirmed_via": "voice_webhook",
    }
    db.add(appointment)
    conversation.status = ClinicConversationStatus.APPOINTMENT_PENDING
    _set_stage(db, conversation, {"stage": "booked", "appointment_pending": True})
    db.commit()
    db.refresh(appointment)

    branding = (clinic.settings_json or {}).get("branding") or {}
    clinic_phone = branding.get("contact_phone")
    if patient.phone and not patient.phone.startswith("anon-"):
        send_appointment_sms_to_patient(
            patient_phone=patient.phone,
            patient_name=patient.full_name,
            clinic_name=clinic.name,
            clinic_phone=clinic_phone,
            department=offer.department,
            physician_name=offer.physician_name,
            starts_at=offer.starts_at,
            confirmation_code=f"CV{appointment.id:06d}",
        )
    send_appointment_sms_to_doctor(
        doctor_phone=branding.get("doctor_notification_phone") or clinic_phone,
        doctor_name=offer.physician_name,
        clinic_name=clinic.name,
        patient_name=patient.full_name,
        patient_phone=patient.phone or "telefon",
        department=offer.department,
        starts_at=offer.starts_at,
    )

    doctor = f" {offer.physician_name}" if offer.physician_name else ""
    return (
        f"Harika. {_format_dt_tr(offer.starts_at)} için{doctor} randevunuzu oluşturdum. "
        "Onay mesajı telefonunuza gönderilecek. Geçmiş olsun, iyi günler."
    )


def _fresh_offers(
    db: Session,
    *,
    clinic: Clinic,
    patient: ClinicPatient,
    conversation: ClinicConversation,
    slot_decision: dict | None,
) -> PhoneTurnOutcome | None:
    offers = build_public_slot_offers(
        db,
        clinic=clinic,
        patient=patient,
        conversation=conversation,
        slot_decision=slot_decision,
        limit=MAX_SPOKEN_OFFERS,
    )
    if not offers:
        return None
    _set_stage(db, conversation, {"stage": "offering", "offer_ids": [o.id for o in offers]})
    db.commit()
    return PhoneTurnOutcome(reply=_speak_offers(offers), stage="offering")


def handle_phone_turn(db: Session, result: IngestionResult, speech: str) -> PhoneTurnOutcome | None:
    """Bir telefon turunu randevu akışına bağlar.

    None dönerse mevcut davranış (ingest yanıtı / eskalasyon metni) kullanılır.
    """
    conversation = result.conversation
    intent = conversation.intent
    meta = (conversation.metadata_json or {}).get("phone_flow") or {}
    stage = meta.get("stage")

    # Güvenlik önceliği: ACİL her aşamada akışı keser ve bekleyen seçim durumu
    # temizlenir — bir sonraki tur "birincisi" dese bile bayat tekliflere bağlanamaz.
    if intent == ClinicIntent.MEDICAL_EMERGENCY:
        if stage:
            _set_stage(db, conversation, None)
            db.commit()
        return None
    if stage == "booked":
        return None  # randevu bu aramada zaten kapandı; kalan turlar normal akışa

    # Teklif aşamasındaki tur BİZİM sorumuza cevaptır ("birincisi", "9 buçuk"):
    # sınıflandırıcının bu kısa söylemlere düşük güven verip shadow-review
    # üretmesi beklenir ve akışı DURDURMAMALIDIR — eşleşme önce denenir,
    # eşleşme yoksa eskalasyon yanıtına düşülür (aşağıda).
    #
    # NOT: result.appointment ingest'in doktor ekranı TASLAĞI olabilir
    # (created_from=ai_conversation_draft) — bu bir onay değildir; onayda o
    # taslak somut seçimle güncellenir (_confirm_offer).

    if stage == "offering":
        offers = _load_active_offers(db, conversation, list(meta.get("offer_ids") or []))
        if offers:
            selected = match_spoken_slot(speech, offers)
            if selected is not None:
                try:
                    reply = _confirm_offer(
                        db,
                        clinic=result.clinic,
                        patient=result.patient,
                        conversation=conversation,
                        offer=selected,
                    )
                    return PhoneTurnOutcome(reply=reply, stage="booked")
                except ValueError:
                    # Slot bu arada başka kanaldan doldu — dürüstçe söyle, yenile.
                    db.rollback()
                    _set_stage(db, conversation, None)
                    db.commit()
                    refreshed = _fresh_offers(
                        db,
                        clinic=result.clinic,
                        patient=result.patient,
                        conversation=conversation,
                        slot_decision=None,
                    )
                    prefix = "Üzgünüm, o saat az önce doldu. "
                    if refreshed is not None:
                        return PhoneTurnOutcome(reply=prefix + refreshed.reply, stage="offering")
                    return PhoneTurnOutcome(
                        reply=prefix + "Şu an başka uygun saat göremiyorum; klinik ekibimiz sizi arayacak.",
                        stage="offering",
                    )
            # Eşleşmedi. Güvenlik-öncelikli kural: bu tur bir shadow review
            # ürettiyse ("yüzüm şişti", "nefes almakta zorlanıyorum",
            # sigorta/fiyat sorusu, düşük güvenli her şey) mevcut eskalasyon
            # yanıtı KONUŞULUR — "nefes alamıyorum" diyen arayana slot listesi
            # okumak kabul edilemez. Stage silinmez; arayan bir sonraki turda
            # yine seçim yapabilir. Yalnız shadow'suz (yüksek güvenli,
            # tıbbi/riskli sinyalsiz) söylemde teklifler tekrar okunur.
            if result.shadow_review is not None:
                return None
            return PhoneTurnOutcome(
                reply="Tam anlayamadım. " + _speak_offers(offers), stage="offering"
            )
        # Teklifler süresi dolmuş — tazele.
        _set_stage(db, conversation, None)
        db.commit()
        refreshed = _fresh_offers(
            db,
            clinic=result.clinic,
            patient=result.patient,
            conversation=conversation,
            slot_decision=None,
        )
        if refreshed is not None:
            return PhoneTurnOutcome(
                reply="Önceki saatlerin süresi doldu. " + refreshed.reply, stage="offering"
            )
        return None

    # Yeni teklif aşaması: yalnız randevu niyetinde (web'deki kapıyla hizalı):
    # otomatik yanıt turunda serbest; shadow-review'lu turda ancak güven ≥0.78
    # ise teklif okunur (public.py'deki eşikle birebir aynı).
    booking_intents = {ClinicIntent.BOOK_APPOINTMENT, ClinicIntent.RESCHEDULE_APPOINTMENT}
    if intent not in booking_intents:
        return None
    if result.shadow_review is not None and (result.shadow_review.confidence_score or 0) < 0.78:
        return None
    message_meta = (result.message.metadata_json or {}) if result.message is not None else {}
    slot_decision = (message_meta.get("data") or {}).get("slot_decision")
    return _fresh_offers(
        db,
        clinic=result.clinic,
        patient=result.patient,
        conversation=conversation,
        slot_decision=slot_decision,
    )
