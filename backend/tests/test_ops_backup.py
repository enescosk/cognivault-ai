"""Yedekleme/geri-dönüş araç seti (app.ops.backup) — hermetik SQLite testleri.

Değişmezler:
- Yedek, kaynakla aynı satır sayılarını taşır ve sha256 kanıtı doğrudur.
- Bozuk yedek doğrulamadan geçemez ve sağlam hedefi ASLA ezemez.
- Restore hedefi force'suz ezmez; force'ta önce pre-restore kopyası alınır.
- Drill zinciri uçtan uca yeşilse overall_ok=True ve kanıt latest.json'a yazılır.
`--noconftest` ile de koşar (saf import; app fixture'ları gerekmez).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.ops.backup import (
    create_backup,
    restore_backup,
    run_drill,
    sqlite_path_from_url,
    verify_backup,
)


def _make_db(path: Path, *, patients: int = 5, appointments: int = 3) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE clinic_patients (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("CREATE TABLE clinical_appointments (id INTEGER PRIMARY KEY, starts TEXT)")
        conn.executemany(
            "INSERT INTO clinic_patients (name) VALUES (?)",
            [(f"Hasta {i}",) for i in range(patients)],
        )
        conn.executemany(
            "INSERT INTO clinical_appointments (starts) VALUES (?)",
            [(f"2026-07-2{i}",) for i in range(appointments)],
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture()
def source_db(tmp_path) -> Path:
    db = tmp_path / "kaynak.db"
    _make_db(db)
    return db


def _url(path: Path) -> str:
    return f"sqlite:///{path}"


# ─── Yedek alma + doğrulama ──────────────────────────────────────────────────

def test_create_backup_produces_verified_copy(source_db, tmp_path):
    backups = tmp_path / "yedekler"
    evidence = create_backup(_url(source_db), backups)

    assert evidence["engine"] == "sqlite"
    backup_path = Path(evidence["backup_path"])
    assert backup_path.exists() and backup_path.parent == backups
    # sha256 kanıtı dosyayla birebir tutmalı
    assert evidence["sha256"] == hashlib.sha256(backup_path.read_bytes()).hexdigest()

    check = verify_backup(backup_path)
    assert check["ok"] is True
    assert check["table_count"] == 2
    assert check["row_total"] == 8  # 5 hasta + 3 randevu


def test_backup_is_consistent_while_connection_open(source_db, tmp_path):
    """Sunucu çalışırken (açık bağlantı + commit edilmemiş yazım) yedek,
    SON COMMIT edilmiş tutarlı durumu içermeli."""
    live = sqlite3.connect(str(source_db))
    try:
        live.execute("INSERT INTO clinic_patients (name) VALUES ('commitlenmemis')")
        # commit YOK — yarım transaction yedeğe sızmamalı
        evidence = create_backup(_url(source_db), tmp_path / "y")
        check = verify_backup(evidence["backup_path"])
        assert check["ok"] is True
        assert check["row_total"] == 8  # commit edilmeyen satır yok
    finally:
        live.rollback()
        live.close()


def test_verify_rejects_truncated_backup(source_db, tmp_path):
    evidence = create_backup(_url(source_db), tmp_path / "y")
    backup_path = Path(evidence["backup_path"])
    data = backup_path.read_bytes()
    backup_path.write_bytes(data[: len(data) // 2])  # yedek bozuldu

    check = verify_backup(backup_path)
    assert check["ok"] is False
    assert check.get("error")


def test_verify_missing_file(tmp_path):
    check = verify_backup(tmp_path / "yok.db")
    assert check["ok"] is False


# ─── Geri yükleme güvenliği ──────────────────────────────────────────────────

def test_restore_refuses_existing_target_without_force(source_db, tmp_path):
    evidence = create_backup(_url(source_db), tmp_path / "y")
    target = tmp_path / "hedef.db"
    _make_db(target, patients=1, appointments=0)

    with pytest.raises(RuntimeError, match="force"):
        restore_backup(evidence["backup_path"], target)


def test_restore_with_force_keeps_pre_restore_copy(source_db, tmp_path):
    evidence = create_backup(_url(source_db), tmp_path / "y")
    target = tmp_path / "hedef.db"
    _make_db(target, patients=1, appointments=0)  # "eski" canlı DB

    result = restore_backup(evidence["backup_path"], target, force=True)
    assert result["ok"] is True
    # Hedef artık yedeğin içeriğini taşıyor
    conn = sqlite3.connect(str(target))
    try:
        assert conn.execute("SELECT COUNT(*) FROM clinic_patients").fetchone()[0] == 5
    finally:
        conn.close()
    # Eski hedefin güvenlik kopyası alınmış ve eski veriyi taşıyor
    pre = Path(result["pre_restore_copy"])
    assert pre.exists()
    conn = sqlite3.connect(str(pre))
    try:
        assert conn.execute("SELECT COUNT(*) FROM clinic_patients").fetchone()[0] == 1
    finally:
        conn.close()


def test_restore_never_overwrites_with_corrupt_backup(source_db, tmp_path):
    evidence = create_backup(_url(source_db), tmp_path / "y")
    backup_path = Path(evidence["backup_path"])
    backup_path.write_bytes(backup_path.read_bytes()[:100])  # bozuk yedek
    target = tmp_path / "hedef.db"
    _make_db(target, patients=1)

    with pytest.raises(RuntimeError, match="doğrulaması başarısız"):
        restore_backup(backup_path, target, force=True)
    # Sağlam hedefe dokunulmadı
    conn = sqlite3.connect(str(target))
    try:
        assert conn.execute("SELECT COUNT(*) FROM clinic_patients").fetchone()[0] == 1
    finally:
        conn.close()


# ─── Drill (prova) ───────────────────────────────────────────────────────────

def test_drill_end_to_end_produces_green_evidence(source_db, tmp_path):
    backups = tmp_path / "y"
    evidence = run_drill(_url(source_db), backups)

    assert evidence["overall_ok"] is True
    assert evidence["verify"]["ok"] is True
    assert evidence["restore_drill"]["restore_verified"] is True
    assert evidence["restore_drill"]["row_total"] == 8
    assert evidence["restore_drill"]["mismatched_tables"] == []

    latest = json.loads((backups / "latest.json").read_text())
    assert latest["overall_ok"] is True


def test_drill_missing_database_reports_failure_evidence(tmp_path):
    evidence = run_drill(f"sqlite:///{tmp_path}/olmayan.db", tmp_path / "y")
    assert evidence["overall_ok"] is False
    assert "error" in evidence
    # Başarısızlık da kanıta yazılır — sessiz kırmızı yok
    latest = json.loads((tmp_path / "y" / "latest.json").read_text())
    assert latest["overall_ok"] is False


# ─── URL çözümleme + CLI ─────────────────────────────────────────────────────

def test_sqlite_url_parsing():
    assert sqlite_path_from_url("sqlite:////abs/yol/db.db") == Path("/abs/yol/db.db")
    relative = sqlite_path_from_url("sqlite:///data/cognivault.db")
    assert relative is not None and relative.is_absolute()
    assert sqlite_path_from_url("sqlite://") is None
    assert sqlite_path_from_url("postgresql://x/y") is None


def test_cli_drill_exit_codes(source_db, tmp_path):
    ok = subprocess.run(
        [sys.executable, "-m", "app.ops.backup", "drill",
         "--database-url", _url(source_db), "--backups-dir", str(tmp_path / "y")],
        capture_output=True, cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert ok.returncode == 0, ok.stderr.decode()[:400]

    bad = subprocess.run(
        [sys.executable, "-m", "app.ops.backup", "drill",
         "--database-url", f"sqlite:///{tmp_path}/yok.db", "--backups-dir", str(tmp_path / "y2")],
        capture_output=True, cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert bad.returncode == 1
