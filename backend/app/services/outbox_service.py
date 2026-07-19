"""Transactional Outbox dispatcher.

İki seam vardır:

1. `enqueue_outbox_event(db, ...)` — caller'ın **mevcut işlem bloğu** içinde
   tabloya satır yazar. Caller commit etmezse satır oluşmaz; commit ederse
   atomik garanti devreye girer.

2. `dispatch_pending_events(db, handlers)` — background worker tarafından
   periyodik çağrılır. PENDING + next_retry_at <= now satırları bulur,
   handler'lara aktarır, sonucu kaydeder. Hata durumunda exponential
   backoff ile retry, max_attempts aşılırsa DEAD_LETTER.

Worker tipi konfigürasyon meselesidir: ARQ + Redis, Celery, cron + script,
veya FastAPI startup task. Bu modül worker-agnostic.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import OutboxEvent, OutboxEventStatus

logger = logging.getLogger(__name__)

# Tip: bir handler outbox satırını alır, başarılı olursa None döner, hata
# durumunda Exception fırlatır → outbox tarafında retry mantığı devreye girer.
OutboxHandler = Callable[[OutboxEvent], None]


def enqueue_outbox_event(
    db: Session,
    *,
    event_type: str,
    payload: dict[str, Any],
    organization_id: int | None = None,
    clinic_id: int | None = None,
    max_attempts: int = 5,
) -> OutboxEvent:
    """Mevcut transaction içinde outbox satırı oluşturur.

    Caller, ana iş kaydı (örn. ClinicMessage.add) ile **aynı db.commit()**
    bloğunda bu fonksiyonu çağırmalı. Bu sayede ya her ikisi de yazılır ya da
    hiçbiri yazılmaz — dual-write problemi yok.
    """
    row = OutboxEvent(
        event_type=event_type,
        payload_json=payload,
        status=OutboxEventStatus.PENDING,
        organization_id=organization_id,
        clinic_id=clinic_id,
        attempts=0,
        max_attempts=max_attempts,
        next_retry_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()   # commit caller'a kalıyor — atomic transaction kuralı bu
    return row


def _backoff_seconds(attempts: int) -> int:
    """Exponential backoff + jitter: 2^attempts ± %20."""
    base = min(2 ** attempts, 3600)   # cap 1 saat
    jitter = random.uniform(0.8, 1.2)
    return int(base * jitter)


def pending_events_query(now: datetime, batch_size: int):
    """Dispatch edilebilir outbox satırları.

    PostgreSQL'de `FOR UPDATE SKIP LOCKED` birden fazla worker'ın aynı satırı
    almasını engeller. SQLite dialect'i bu kilidi desteklemediği için SQLAlchemy
    orada ifadeyi otomatik no-op derler; lokal/dev test davranışı korunur.
    """
    return (
        select(OutboxEvent)
        .where(OutboxEvent.status == OutboxEventStatus.PENDING)
        .where((OutboxEvent.next_retry_at == None) | (OutboxEvent.next_retry_at <= now))  # noqa: E711
        .order_by(OutboxEvent.created_at.asc())
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )


def dispatch_pending_events(
    db: Session,
    handlers: dict[str, OutboxHandler],
    *,
    batch_size: int = 50,
) -> dict[str, int]:
    """PENDING ve retry zamanı gelmiş eventleri sırayla dispatch eder.

    Args:
        db: kısa-ömürlü SessionLocal — worker her tetiklenmede yeni açmalı.
        handlers: event_type → handler fonksiyonu mapping.
        batch_size: tek seferde maksimum işlenecek event sayısı (DB yükü için).

    Returns:
        Sayım sözlüğü: {"dispatched": int, "failed": int, "dead_letter": int}
    """
    now = datetime.now(timezone.utc)
    stats = {"dispatched": 0, "failed": 0, "dead_letter": 0, "no_handler": 0}

    pending = db.scalars(pending_events_query(now, batch_size)).all()

    for event in pending:
        handler = handlers.get(event.event_type)
        if handler is None:
            stats["no_handler"] += 1
            event.status = OutboxEventStatus.DEAD_LETTER
            event.last_error = f"Handler bulunamadı: {event.event_type}"
            event.dispatched_at = None
            db.commit()
            logger.warning(
                "outbox.no_handler",
                extra={"event_type": event.event_type, "event_id": event.id},
            )
            continue

        try:
            handler(event)
        except Exception as exc:  # noqa: BLE001 — tüm handler hataları normalize
            event.attempts += 1
            event.last_error = str(exc)[:1000]
            if event.attempts >= event.max_attempts:
                event.status = OutboxEventStatus.DEAD_LETTER
                stats["dead_letter"] += 1
                logger.error(
                    "outbox.dead_letter",
                    extra={
                        "event_id": event.id,
                        "event_type": event.event_type,
                        "attempts": event.attempts,
                        "error": str(exc)[:300],
                    },
                )
            else:
                event.next_retry_at = now + timedelta(seconds=_backoff_seconds(event.attempts))
                stats["failed"] += 1
                logger.warning(
                    "outbox.retry_scheduled",
                    extra={
                        "event_id": event.id,
                        "attempts": event.attempts,
                        "next_retry_at": event.next_retry_at.isoformat(),
                    },
                )
            db.commit()
            continue

        event.status = OutboxEventStatus.DISPATCHED
        event.dispatched_at = now
        event.last_error = None
        db.commit()
        stats["dispatched"] += 1
        logger.info(
            "outbox.dispatched",
            extra={
                "event_id": event.id,
                "event_type": event.event_type,
                "attempts": event.attempts + 1,
            },
        )

    return stats


# ─── Demo handlers (production'da gerçek Twilio/Meta/SMTP wrap'ı ile değişir)
def handler_send_whatsapp(event: OutboxEvent) -> None:
    """Outbox'tan WhatsApp mesajı gönderir. Mevcut altyapı yoksa no-op log."""
    payload = event.payload_json or {}
    to = payload.get("to")
    body = payload.get("body")
    logger.info(
        "outbox.handler.whatsapp",
        extra={"to": to, "body_preview": (body or "")[:60]},
    )
    # Gerçek dünyada burada Twilio/Meta client çağrısı olur. Hata fırlatırsa
    # dispatch_pending_events retry mantığını uygular.


def handler_send_email(event: OutboxEvent) -> None:
    payload = event.payload_json or {}
    logger.info(
        "outbox.handler.email",
        extra={"to": payload.get("to"), "subject": payload.get("subject")},
    )


DEFAULT_HANDLERS: dict[str, OutboxHandler] = {
    "whatsapp.send": handler_send_whatsapp,
    "email.send": handler_send_email,
}


def _scope_filters(organization_id: int | None) -> list:
    if organization_id is None:
        return []
    return [
        or_(
            OutboxEvent.organization_id == organization_id,
            OutboxEvent.organization_id.is_(None),
        )
    ]


def summarize_outbox(db: Session, *, organization_id: int | None = None) -> dict[str, Any]:
    """Operator/admin için outbox sağlık özeti.

    Legacy satırlar (`organization_id IS NULL`) görünür kalır; Phase 1 öncesi
    outbound denemeleri operatör ekranından kaybolmasın.
    """
    filters = _scope_filters(organization_id)
    now = datetime.now(timezone.utc)
    by_status = {status.value: 0 for status in OutboxEventStatus}
    for status, count in db.execute(
        select(OutboxEvent.status, func.count(OutboxEvent.id))
        .where(*filters)
        .group_by(OutboxEvent.status)
    ).all():
        key = status.value if isinstance(status, OutboxEventStatus) else str(status).lower()
        by_status[key] = int(count)

    pending_ready = db.scalar(
        select(func.count(OutboxEvent.id))
        .where(*filters)
        .where(OutboxEvent.status == OutboxEventStatus.PENDING)
        .where((OutboxEvent.next_retry_at == None) | (OutboxEvent.next_retry_at <= now))  # noqa: E711
    ) or 0
    oldest_pending = db.scalar(
        select(func.min(OutboxEvent.created_at))
        .where(*filters)
        .where(OutboxEvent.status == OutboxEventStatus.PENDING)
    )
    next_retry = db.scalar(
        select(func.min(OutboxEvent.next_retry_at))
        .where(*filters)
        .where(OutboxEvent.status == OutboxEventStatus.PENDING)
        .where(OutboxEvent.next_retry_at.is_not(None))
    )
    latest_dead = db.scalars(
        select(OutboxEvent)
        .where(*filters)
        .where(OutboxEvent.status == OutboxEventStatus.DEAD_LETTER)
        .order_by(OutboxEvent.created_at.desc())
        .limit(1)
    ).first()

    return {
        "total": sum(by_status.values()),
        "by_status": by_status,
        "pending_ready": int(pending_ready),
        "dead_letter": by_status[OutboxEventStatus.DEAD_LETTER.value],
        "oldest_pending_at": oldest_pending,
        "next_retry_at": next_retry,
        "latest_dead_letter_id": latest_dead.id if latest_dead else None,
        "latest_dead_letter_error": latest_dead.last_error if latest_dead else None,
    }


def list_outbox_events(
    db: Session,
    *,
    organization_id: int | None = None,
    status: OutboxEventStatus | None = None,
    event_type: str | None = None,
    limit: int = 100,
) -> list[OutboxEvent]:
    filters = _scope_filters(organization_id)
    if status is not None:
        filters.append(OutboxEvent.status == status)
    if event_type:
        filters.append(OutboxEvent.event_type == event_type)

    return list(
        db.scalars(
            select(OutboxEvent)
            .where(*filters)
            .order_by(OutboxEvent.created_at.desc(), OutboxEvent.id.desc())
            .limit(limit)
        )
    )
