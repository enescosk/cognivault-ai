"""Outbox dispatcher worker — komut satırı entry point.

Çalıştır:
  python -m app.workers.outbox_worker

Bu basit polling worker'dır. Production'da ARQ/Celery/cron + bu fonksiyon
ile değiştirilebilir; mantık `outbox_service.dispatch_pending_events` içinde.
"""

from __future__ import annotations

import logging
import signal
import sys
import time

from app.core.observability import configure_logging
from app.db.session import SessionLocal
from app.services.outbox_service import DEFAULT_HANDLERS, dispatch_pending_events

configure_logging()
logger = logging.getLogger(__name__)

# Polling aralığı — saniye. Trafik düşükse yükselt, mesaj kritikse düşür.
POLL_INTERVAL_SECONDS = 5


_shutdown = False


def _signal_handler(signum, frame):  # noqa: ARG001
    global _shutdown
    _shutdown = True
    logger.info("outbox.worker.shutdown_signal", extra={"signal": signum})


def main() -> int:
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    logger.info("outbox.worker.started", extra={"poll_interval_s": POLL_INTERVAL_SECONDS})

    while not _shutdown:
        db = SessionLocal()
        try:
            stats = dispatch_pending_events(db, DEFAULT_HANDLERS, batch_size=50)
            if any(stats.values()):
                logger.info("outbox.worker.tick", extra=stats)
        except Exception as exc:  # noqa: BLE001
            logger.exception("outbox.worker.error", extra={"error": str(exc)})
        finally:
            db.close()

        # Sleep'i parçala ki SIGTERM hızlı yanıtlansın
        for _ in range(POLL_INTERVAL_SECONDS):
            if _shutdown:
                break
            time.sleep(1)

    logger.info("outbox.worker.stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
