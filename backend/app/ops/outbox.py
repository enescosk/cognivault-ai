"""Transactional outbox kanıt panosu.

Bu pano dış sağlayıcı çağırmaz; in-memory SQLite üzerinde outbox zincirinin
kritik değişmezlerini koşturur:

- enqueue caller transaction'ına bağlıdır,
- başarılı handler event'i DISPATCHED yapar,
- geçici hata retry planlar ve payload'u korur,
- handler eksikliği sonsuz pending döngüsü yerine DEAD_LETTER olur.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import OutboxEvent, OutboxEventStatus
from app.services.outbox_service import (
    dispatch_pending_events,
    enqueue_outbox_event,
    pending_events_query,
    summarize_outbox,
)

ARTIFACT_PATH = Path(__file__).resolve().parent / "data" / "outbox.json"


def _gate(id_: str, title: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"id": id_, "title": title, "pass": bool(passed), "detail": detail}


def build_report() -> dict:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    gates: list[dict[str, Any]] = []
    outbox_logger = logging.getLogger("app.services.outbox_service")
    previous_disabled = outbox_logger.disabled
    outbox_logger.disabled = True

    try:
        rolled_back = enqueue_outbox_event(db, event_type="whatsapp.send", payload={"body": "rollback"})
        rolled_back_id = rolled_back.id
        db.rollback()
        gates.append(
            _gate(
                "transactional_enqueue",
                "Caller rollback ederse outbox satırı kalmaz",
                db.get(OutboxEvent, rolled_back_id) is None,
                "enqueue_outbox_event commit etmez; atomiklik caller transaction'ında kalır.",
            )
        )

        sent = enqueue_outbox_event(db, event_type="whatsapp.send", payload={"body": "ok"})
        db.commit()
        called: list[int] = []
        success_stats = dispatch_pending_events(db, {"whatsapp.send": lambda event: called.append(event.id)})
        sent_saved = db.get(OutboxEvent, sent.id)
        gates.append(
            _gate(
                "successful_dispatch",
                "Başarılı handler DISPATCHED yazar",
                success_stats["dispatched"] == 1
                and called == [sent.id]
                and sent_saved is not None
                and sent_saved.status == OutboxEventStatus.DISPATCHED
                and sent_saved.dispatched_at is not None,
                f"stats={success_stats}",
            )
        )

        retry = enqueue_outbox_event(db, event_type="whatsapp.send", payload={"body": "retry"})
        db.commit()

        def fail(_: OutboxEvent) -> None:
            raise RuntimeError("geçici hata")

        retry_stats = dispatch_pending_events(db, {"whatsapp.send": fail})
        retry_saved = db.get(OutboxEvent, retry.id)
        gates.append(
            _gate(
                "retry_backoff",
                "Geçici hata payload'u koruyup retry planlar",
                retry_stats["failed"] == 1
                and retry_saved is not None
                and retry_saved.status == OutboxEventStatus.PENDING
                and retry_saved.attempts == 1
                and retry_saved.payload_json == {"body": "retry"}
                and bool(retry_saved.next_retry_at),
                f"stats={retry_stats}",
            )
        )

        unknown = enqueue_outbox_event(db, event_type="fax.send", payload={"body": "legacy"})
        db.commit()
        unknown_first = dispatch_pending_events(db, {})
        unknown_second = dispatch_pending_events(db, {})
        unknown_saved = db.scalars(select(OutboxEvent).where(OutboxEvent.id == unknown.id)).one()
        gates.append(
            _gate(
                "unknown_handler_dead_letter",
                "Handler eksikliği sonsuz pending döngüsü üretmez",
                unknown_first["no_handler"] == 1
                and unknown_second["no_handler"] == 0
                and unknown_saved.status == OutboxEventStatus.DEAD_LETTER,
                f"first={unknown_first}, second={unknown_second}",
            )
        )

        permanent = enqueue_outbox_event(
            db,
            event_type="email.send",
            payload={"subject": "x"},
            max_attempts=1,
        )
        db.commit()
        dead_stats = dispatch_pending_events(db, {"email.send": fail})
        permanent_saved = db.get(OutboxEvent, permanent.id)
        gates.append(
            _gate(
                "max_attempts_dead_letter",
                "Max attempt dolunca DEAD_LETTER olur",
                dead_stats["dead_letter"] == 1
                and permanent_saved is not None
                and permanent_saved.status == OutboxEventStatus.DEAD_LETTER,
                f"stats={dead_stats}",
            )
        )

        summary = summarize_outbox(db)
        gates.append(
            _gate(
                "operator_summary_contract",
                "Operator özeti pending/dead-letter sayar",
                summary["total"] == 4
                and summary["by_status"][OutboxEventStatus.DISPATCHED.value] == 1
                and summary["by_status"][OutboxEventStatus.PENDING.value] == 1
                and summary["by_status"][OutboxEventStatus.DEAD_LETTER.value] == 2,
                f"summary={summary}",
            )
        )

        compiled = str(
            pending_events_query(datetime.now(timezone.utc), 50).compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": False},
            )
        )
        gates.append(
            _gate(
                "postgres_skip_locked",
                "Çoklu worker aynı event'i kapmaz",
                "FOR UPDATE SKIP LOCKED" in compiled,
                "PostgreSQL sorgusu row-lock + skip-locked ile derlenir.",
            )
        )
    finally:
        outbox_logger.disabled = previous_disabled
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

    passed = sum(1 for gate in gates if gate["pass"])
    return {
        "name": "outbox_reliability_board",
        "summary": {"gates_passed": passed, "gates_total": len(gates)},
        "gates": gates,
        "overall_pass": passed == len(gates),
    }


def write_artifact(report: dict, path: Path = ARTIFACT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def render(report: dict) -> str:
    ok = lambda passed: "PASS" if passed else "FAIL"  # noqa: E731
    lines = ["CogniVault — Outbox Güvenilirlik Panosu", "=" * 58]
    for gate in report["gates"]:
        lines.append(f"{ok(gate['pass']):<4s} {gate['id']:<28s} {gate['title']}")
    summary = report["summary"]
    lines += [
        "-" * 58,
        f"Kapılar: {summary['gates_passed']}/{summary['gates_total']}",
        f"Genel: {ok(report['overall_pass'])}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="CogniVault outbox güvenilirlik panosu")
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
