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


def test_alembic_head_creates_all_orm_tables_and_columns():
    """`alembic upgrade head` temiz bir SQLite DB'de bütün ORM tablolarını
    VE her tablonun bütün kolonlarını yaratmalı.

    Eksik tablo veya eksik kolon → assertion fail → deploy bloklanır.

    İkinci incident (2026-07-08): clinical_appointments.doctor_id/slot_id
    ORM'e eklendi ama migration yazılmadı; bu test o sırada yalnız tablo
    ADLARINI karşılaştırdığı için yakalamadı ve mevcut kurulumlar açılışta
    OperationalError ile çöktü. Artık kolon düzeyinde karşılaştırıyoruz.
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

        orm_tables = set(Base.metadata.tables.keys())
        missing = orm_tables - migration_tables
        orphan = migration_tables - orm_tables

        assert not missing, (
            f"ORM has {len(missing)} table(s) that `alembic upgrade head` does NOT "
            f"create: {sorted(missing)}. Add them to a new migration before deploy."
        )

        column_drift: dict[str, list[str]] = {}
        for table_name, table in Base.metadata.tables.items():
            migration_columns = {c["name"] for c in inspector.get_columns(table_name)}
            missing_columns = {c.name for c in table.columns} - migration_columns
            if missing_columns:
                column_drift[table_name] = sorted(missing_columns)
        engine.dispose()

        assert not column_drift, (
            f"ORM has columns that `alembic upgrade head` does NOT create: "
            f"{column_drift}. Add them to a new migration before deploy — "
            f"existing installs will crash on first query otherwise."
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
