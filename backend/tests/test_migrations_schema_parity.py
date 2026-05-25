"""ORM ve Alembic head şemasının senkron kaldığını garanti eden invariant test.

Bu test geçmediği sürece üretime alınan herhangi bir deploy'da
`alembic upgrade head` ORM model'inin gerektirdiği bütün tabloları
üretmeyecek demektir — yani uygulama prod'da boş yere açılır ve ilk
sorguda patlar.

Daha önceki incident: 19 tablo (users, audit_logs, enterprise_*, intelligence_*)
ORM'de vardı ama hiçbir migration onları yaratmıyordu. Sebep: dev'de
`Base.metadata.create_all` her şeyi sessizce hallediyordu, kimse fark etmedi.

Bu test o sınıfı tüm hataları yakalar.
"""

from __future__ import annotations

import os
import tempfile

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.db.base import Base
import app.models  # noqa: F401 — bütün modelleri Base.metadata'ya kaydet


def _build_alembic_config(database_url: str) -> Config:
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(backend_dir, "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def test_alembic_head_creates_all_orm_tables():
    """`alembic upgrade head` temiz bir SQLite DB'de bütün ORM tablolarını yaratmalı.

    Eksik tablo → assertion fail → deploy bloklanır.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    try:
        url = f"sqlite:///{db_path}"
        cfg = _build_alembic_config(url)
        command.upgrade(cfg, "head")

        engine = create_engine(url)
        inspector = inspect(engine)
        migration_tables = set(inspector.get_table_names())
        # Alembic kendi versiyon tablosunu yazar; karşılaştırmadan çıkar.
        migration_tables.discard("alembic_version")
        engine.dispose()

        orm_tables = set(Base.metadata.tables.keys())
        missing = orm_tables - migration_tables
        orphan = migration_tables - orm_tables

        assert not missing, (
            f"ORM has {len(missing)} table(s) that `alembic upgrade head` does NOT "
            f"create: {sorted(missing)}. Add them to a new migration before deploy."
        )
        # Orphan tablolar daha az kritik (silinmiş model olabilir), warning seviyesinde
        # bırakıyoruz — strict fail yapmıyoruz çünkü tarihsel migration'lar bırakılır.
        if orphan:
            pytest.skip(
                f"Migrations create tables not present in ORM (legacy artefacts): {sorted(orphan)}"
            )
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)
