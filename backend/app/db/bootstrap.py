from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import inspect

from app.core.config import Settings
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.seed.data import seed_database

logger = logging.getLogger(__name__)

_BACKEND_DIR = Path(__file__).resolve().parents[2]

_RESET_HINT = (
    "Yerel demo DB'sini sıfırlamak için ./scripts/reset_demo_db.sh çalıştırın "
    "veya eksik kolonlar için yeni bir Alembic migration yazın."
)


def _is_ephemeral_sqlite(database_url: str) -> bool:
    """In-memory SQLite'ta Alembic ayrı bağlantı açar ve ayrı boş DB görür;
    migration koşmak anlamsızdır, düz create_all yeterli."""
    return database_url in ("sqlite://", "sqlite:///:memory:") or ":memory:" in database_url


def _alembic_config(database_url: str):
    from alembic.config import Config

    # Bilinçli olarak alembic.ini YÜKLENMEZ: env.py, ini dosyası verilirse
    # fileConfig ile logging'i yeniden kurar ve uvicorn log yapılandırmasını ezer.
    cfg = Config()
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "migrations"))
    # ConfigParser '%' karakterini interpolasyon sayar; URL'de kaçır.
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return cfg


def _schema_drift() -> dict[str, list[str]]:
    """ORM metadata'sının canlı DB'de karşılığı olmayan tablo/kolonları döndürür."""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    drift: dict[str, list[str]] = {}
    for table_name, table in Base.metadata.tables.items():
        if table_name not in existing_tables:
            drift[table_name] = ["<missing table>"]
            continue
        existing_columns = {c["name"] for c in inspector.get_columns(table_name)}
        missing = sorted({c.name for c in table.columns} - existing_columns)
        if missing:
            drift[table_name] = missing
    return drift


def _apply_schema(settings: Settings) -> None:
    """Yerel/dev şema kurulumu — migration-first.

    Üç durum:
    1. Boş DB           → `alembic upgrade head` (production ile aynı yol).
    2. Yönetilen DB     → (alembic_version var) `upgrade head` ile güncelle.
    3. Eski create_all DB → create_all ile eksik tabloları tamamla; şema ORM ile
       eşleşiyorsa head'e damgala (bundan sonra migration-yönetimli), eşleşmiyorsa
       create_all kolon EKLEYEMEYECEĞİ için net ve aksiyon verilebilir hatayla dur.

    Amaç: "git pull sonrası uygulama açılmıyor" sınıfı sorunları kullanıcıya
    kriptik OperationalError yerine ya sessizce çözmek ya tek cümlelik yol göstermek.
    """
    if _is_ephemeral_sqlite(settings.database_url):
        Base.metadata.create_all(bind=engine)
        return

    from alembic import command

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    cfg = _alembic_config(settings.database_url)

    if not existing_tables or "alembic_version" in existing_tables:
        state = "empty" if not existing_tables else "managed"
        logger.info("bootstrap_schema state=%s action=alembic_upgrade_head", state)
        command.upgrade(cfg, "head")
        # Güvenlik ağı: migration'lara henüz girmemiş ORM tablosu varsa tamamla
        # (kolon-parity testi bunu normalde imkânsız kılar; no-op beklenir).
        Base.metadata.create_all(bind=engine)
    else:
        logger.info("bootstrap_schema state=legacy_create_all action=create_all")
        Base.metadata.create_all(bind=engine)

    drift = _schema_drift()
    if drift:
        raise RuntimeError(
            f"Veritabanı şeması ORM ile uyumsuz (eksik kolon/tablo): {drift}. "
            f"{_RESET_HINT}"
        )

    if "alembic_version" not in set(inspect(engine).get_table_names()):
        # Eski DB şemayı tam karşılıyor — head'e damgala ki sonraki
        # açılışlarda upgrade yolu çalışsın.
        logger.info("bootstrap_schema action=stamp_head (legacy db adopted)")
        command.stamp(cfg, "head")


def initialize_database(settings: Settings) -> None:
    """
    Local/test bootstrap only.

    Production must run explicit migrations instead of mutating schema during
    app startup. The config guard enforces that contract.
    """
    if settings.auto_create_schema:
        logger.info("auto_create_schema_enabled")
        _apply_schema(settings)
    else:
        logger.info("auto_create_schema_disabled")

    if settings.seed_demo_data:
        db = SessionLocal()
        try:
            seed_database(db)
        finally:
            db.close()
