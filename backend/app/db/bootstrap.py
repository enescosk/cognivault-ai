from __future__ import annotations

import logging

from app.core.config import Settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.seed.data import seed_database

logger = logging.getLogger(__name__)


def initialize_database(settings: Settings) -> None:
    """
    Local/test bootstrap only.

    Production must run explicit migrations instead of mutating schema during
    app startup. The config guard enforces that contract.
    """
    if settings.auto_create_schema:
        logger.info("auto_create_schema_enabled")
        Base.metadata.create_all(bind=engine)
    else:
        logger.info("auto_create_schema_disabled")

    if settings.seed_demo_data:
        db = SessionLocal()
        try:
            seed_database(db)
        finally:
            db.close()
