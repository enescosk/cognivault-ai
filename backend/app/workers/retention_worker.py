"""KVKK data retention cleanup worker script.

Run:
  python -m app.workers.retention_worker
"""
from __future__ import annotations

import logging
import sys
import time

from app.core.observability import configure_logging
from app.db.session import SessionLocal
from app.services.clinical_compliance_service import run_retention_cleanup

configure_logging()
logger = logging.getLogger("cognivault.retention_worker")

# Clean interval in seconds (polls every 60 seconds)
CLEAN_INTERVAL_SECONDS = 60


def main() -> int:
    logger.info("retention.worker.started", extra={"clean_interval_s": CLEAN_INTERVAL_SECONDS})
    try:
        while True:
            db = SessionLocal()
            try:
                stats = run_retention_cleanup(db)
                if any(stats.values()):
                    logger.info("retention.worker.cleanup_executed", extra=stats)
            except Exception as exc:
                logger.exception("retention.worker.error", extra={"error": str(exc)})
            finally:
                db.close()
            time.sleep(CLEAN_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("retention.worker.stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
