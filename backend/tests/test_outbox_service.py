"""Transactional outbox davranışı — hermetik SQLite testleri."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import OutboxEvent, OutboxEventStatus
from app.services.outbox_service import dispatch_pending_events, enqueue_outbox_event, pending_events_query


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def _reload(db, event_id: int) -> OutboxEvent:
    return db.scalars(select(OutboxEvent).where(OutboxEvent.id == event_id)).one()


def test_enqueue_participates_in_caller_transaction(db):
    event = enqueue_outbox_event(
        db,
        event_type="whatsapp.send",
        payload={"to": "+905551112233", "body": "Merhaba"},
        organization_id=7,
        clinic_id=3,
    )
    event_id = event.id
    db.rollback()

    assert db.get(OutboxEvent, event_id) is None


def test_dispatch_success_marks_event_dispatched(db):
    event = enqueue_outbox_event(db, event_type="whatsapp.send", payload={"body": "ok"})
    db.commit()
    called: list[int] = []

    stats = dispatch_pending_events(
        db,
        {"whatsapp.send": lambda item: called.append(item.id)},
    )

    assert stats == {"dispatched": 1, "failed": 0, "dead_letter": 0, "no_handler": 0}
    assert called == [event.id]
    saved = _reload(db, event.id)
    assert saved.status == OutboxEventStatus.DISPATCHED
    assert saved.dispatched_at is not None
    assert saved.last_error is None


def test_failed_dispatch_schedules_retry_without_losing_payload(db, monkeypatch):
    monkeypatch.setattr("app.services.outbox_service._backoff_seconds", lambda attempts: 30)
    event = enqueue_outbox_event(db, event_type="whatsapp.send", payload={"body": "retry"})
    db.commit()

    def fail(_: OutboxEvent) -> None:
        raise RuntimeError("geçici sağlayıcı hatası")

    before = datetime.now(timezone.utc)
    stats = dispatch_pending_events(db, {"whatsapp.send": fail})

    assert stats == {"dispatched": 0, "failed": 1, "dead_letter": 0, "no_handler": 0}
    saved = _reload(db, event.id)
    assert saved.status == OutboxEventStatus.PENDING
    assert saved.attempts == 1
    assert saved.payload_json == {"body": "retry"}
    assert saved.last_error == "geçici sağlayıcı hatası"
    assert saved.next_retry_at is not None
    retry_at = saved.next_retry_at
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    assert retry_at >= before + timedelta(seconds=25)


def test_failed_dispatch_dead_letters_after_max_attempts(db):
    event = enqueue_outbox_event(
        db,
        event_type="whatsapp.send",
        payload={},
        max_attempts=1,
    )
    db.commit()

    def fail(_: OutboxEvent) -> None:
        raise RuntimeError("kalıcı hata")

    stats = dispatch_pending_events(db, {"whatsapp.send": fail})

    assert stats == {"dispatched": 0, "failed": 0, "dead_letter": 1, "no_handler": 0}
    saved = _reload(db, event.id)
    assert saved.status == OutboxEventStatus.DEAD_LETTER
    assert saved.attempts == 1
    assert saved.last_error == "kalıcı hata"


def test_unknown_event_type_is_dead_lettered_not_replayed_forever(db):
    event = enqueue_outbox_event(db, event_type="fax.send", payload={"body": "eski kanal"})
    db.commit()

    first = dispatch_pending_events(db, {})
    second = dispatch_pending_events(db, {})

    assert first == {"dispatched": 0, "failed": 0, "dead_letter": 0, "no_handler": 1}
    assert second == {"dispatched": 0, "failed": 0, "dead_letter": 0, "no_handler": 0}
    saved = _reload(db, event.id)
    assert saved.status == OutboxEventStatus.DEAD_LETTER
    assert saved.last_error == "Handler bulunamadı: fax.send"


def test_future_retry_is_not_dispatched_before_due(db):
    event = enqueue_outbox_event(db, event_type="whatsapp.send", payload={})
    event.next_retry_at = datetime.now(timezone.utc) + timedelta(hours=1)
    db.commit()

    stats = dispatch_pending_events(db, {"whatsapp.send": lambda _: None})

    assert stats == {"dispatched": 0, "failed": 0, "dead_letter": 0, "no_handler": 0}
    assert _reload(db, event.id).status == OutboxEventStatus.PENDING


def test_pending_query_uses_skip_locked_for_postgresql():
    compiled = str(
        pending_events_query(datetime.now(timezone.utc), 25).compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": False},
        )
    )

    assert "FOR UPDATE SKIP LOCKED" in compiled
