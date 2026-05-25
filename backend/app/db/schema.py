"""DB şema bootstrap'ı — uygulama açılışında çağrılır.

Tek doğru yol: Alembic migrations. `Base.metadata.create_all` zaten geçmişte
bir migration'ın oluşturmadığı tabloları sessizce yaratıp prod'da olmayan
ama dev'de olan bir hayalet şema yaratmıştı (19 tablo eksikti). Bu modül
o döngüyü kırar.

Çağrı modu:
  - dev (`environment != production`): otomatik `alembic upgrade head`.
    Geliştirici elle migration çalıştırmak zorunda kalmaz.
  - prod: startup'ta NO-OP. Migration deploy pipeline'ında manuel
    `alembic upgrade head` ile uygulanmış olmalı (her release önce migration).
"""

from __future__ import annotations

import logging
import os

from alembic import command
from alembic.config import Config

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _alembic_config() -> Config:
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(backend_dir, "migrations"))
    cfg.set_main_option("sqlalchemy.url", get_settings().database_url)
    return cfg


def ensure_schema_up_to_date() -> None:
    """Dev'de Alembic head'e taşır, prod'da müdahale etmez.

    Pre-production CI'da `pytest` `test_alembic_head_creates_all_orm_tables`
    test'ini koştuğu için head'in ORM ile parity'sini garanti eder; dolayısıyla
    bu fonksiyon `Base.metadata.create_all` ile aynı eski sonucu üretir.
    """
    settings = get_settings()
    if settings.is_production:
        logger.info(
            "db.schema.skip_upgrade",
            extra={"reason": "production_env_uses_explicit_migration_step"},
        )
        return

    logger.info("db.schema.upgrade_start")
    command.upgrade(_alembic_config(), "head")
    logger.info("db.schema.upgrade_done")
