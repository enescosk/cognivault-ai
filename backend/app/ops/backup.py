"""Yedekleme / geri-dönüş araç seti + otomatik prova (drill).

"Yedekleme provası yapılmamış bir sistemle hasta verisi tutulamaz" — bu modül
o provayı tek komuta indirir:

    python -m app.ops.backup drill

Drill zinciri: yedek al → bütünlüğünü doğrula → GEÇİCİ hedefe geri yükle →
tablo satır sayılarını yedekle karşılaştır → kanıt JSON'u yaz
(`data/backups/latest.json`). Zincirin herhangi bir halkası kırılırsa çıkış
kodu 1'dir; "yedeğimiz var" cümlesi ancak drill yeşilken kurulabilir.

Motor desteği:
- SQLite (demo/pilot varsayılanı): sqlite3 online backup API — sunucu ÇALIŞIRKEN
  bile tutarlı kopya alır (dosya kopyalamanın aksine yarım-yazım riski yok).
- PostgreSQL: `pg_dump -Fc` (varsa). Drill'de geri yükleme, yeni bir veritabanı
  yaratma yetkisi gerektirdiğinden `pg_restore --list` yapı doğrulamasıyla
  sınırlıdır ve kanıtta dürüstçe `structure_listing_only` diye işaretlenir.

Restore güvenliği: hedef dosya `--force` olmadan ASLA ezilmez; force ile bile
önce hedefin `.pre-restore-<ts>` kopyası alınır — geri dönüşün geri dönüşü olur.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BACKUPS_DIR = BACKEND_ROOT / "data" / "backups"


# ─── Yardımcılar ─────────────────────────────────────────────────────────────

def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sqlite_path_from_url(database_url: str) -> Path | None:
    """'sqlite:///relative' veya 'sqlite:////abs' URL'inden dosya yolunu çıkarır.

    Bellek-içi (':memory:') yedeklenemez → None. Göreli yol, uygulamanın
    çalışma dizini varsayımıyla (backend/) çözülür.
    """
    if not database_url.startswith("sqlite:"):
        return None
    raw = database_url.split("sqlite:///", 1)[-1] if "sqlite:///" in database_url else ""
    if not raw or ":memory:" in database_url:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = BACKEND_ROOT / path
    return path


def _default_database_url() -> str:
    from app.core.config import get_settings

    return get_settings().database_url


def _sqlite_table_counts(path: Path) -> dict[str, int]:
    """Kullanıcı tablolarının satır sayıları (salt-okunur bağlantıyla)."""
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        return {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tables}
    finally:
        conn.close()


# ─── Yedek alma ──────────────────────────────────────────────────────────────

def create_backup(database_url: str | None = None, backups_dir: Path | None = None) -> dict:
    """Yedek alır; kanıt sözlüğü döner. Başarısızlıkta exception yükseltir."""
    database_url = database_url or _default_database_url()
    backups_dir = Path(backups_dir or DEFAULT_BACKUPS_DIR)
    backups_dir.mkdir(parents=True, exist_ok=True)

    sqlite_path = sqlite_path_from_url(database_url)
    if sqlite_path is not None:
        if not sqlite_path.exists():
            raise FileNotFoundError(f"SQLite veritabanı bulunamadı: {sqlite_path}")
        target = backups_dir / f"{sqlite_path.stem}-{_now_stamp()}.db"
        # Online backup API: açık bağlantılar/yarım transaction'lar varken bile
        # SON COMMIT edilmiş tutarlı durumu kopyalar.
        src = sqlite3.connect(str(sqlite_path))
        dst = sqlite3.connect(str(target))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        return {
            "engine": "sqlite",
            "source": str(sqlite_path),
            "backup_path": str(target),
            "size_bytes": target.stat().st_size,
            "sha256": _sha256(target),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    if database_url.startswith(("postgresql:", "postgres:")):
        if shutil.which("pg_dump") is None:
            raise RuntimeError("pg_dump bulunamadı — PostgreSQL yedeği için gerekli.")
        target = backups_dir / f"cognivault-{_now_stamp()}.dump"
        subprocess.run(
            ["pg_dump", "--format=custom", f"--dbname={database_url}", f"--file={target}"],
            check=True,
            capture_output=True,
            timeout=600,
        )
        return {
            "engine": "postgresql",
            "source": database_url.split("@")[-1],  # kimlik bilgisi kanıta yazılmaz
            "backup_path": str(target),
            "size_bytes": target.stat().st_size,
            "sha256": _sha256(target),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    raise ValueError(f"Desteklenmeyen veritabanı URL şeması: {database_url.split(':', 1)[0]}")


# ─── Doğrulama ───────────────────────────────────────────────────────────────

def verify_backup(backup_path: str | Path) -> dict:
    """Yedeğin bütünlüğünü doğrular; ok=False döner, exception yükseltmez."""
    path = Path(backup_path)
    if not path.exists():
        return {"ok": False, "error": f"yedek dosyası yok: {path}"}

    if path.suffix == ".dump":
        if shutil.which("pg_restore") is None:
            return {"ok": False, "error": "pg_restore bulunamadı"}
        proc = subprocess.run(
            ["pg_restore", "--list", str(path)], capture_output=True, timeout=120
        )
        entries = len(proc.stdout.splitlines()) if proc.returncode == 0 else 0
        return {
            "ok": proc.returncode == 0 and entries > 0,
            "engine": "postgresql",
            "toc_entries": entries,
            "error": proc.stderr.decode()[:300] if proc.returncode != 0 else None,
        }

    try:
        uri = f"file:{path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            conn.close()
        if integrity != "ok":
            return {"ok": False, "engine": "sqlite", "error": f"integrity_check: {integrity}"}
        counts = _sqlite_table_counts(path)
        return {
            "ok": len(counts) > 0,
            "engine": "sqlite",
            "table_count": len(counts),
            "row_total": sum(counts.values()),
        }
    except sqlite3.Error as exc:
        return {"ok": False, "engine": "sqlite", "error": str(exc)}


# ─── Geri yükleme ────────────────────────────────────────────────────────────

def restore_backup(backup_path: str | Path, target_path: str | Path, *, force: bool = False) -> dict:
    """SQLite yedeğini hedefe geri yükler.

    Hedef mevcutsa `force=False` iken REDDEDER; force ile önce hedefin
    `.pre-restore-<ts>` güvenlik kopyası alınır. Yedek önce doğrulanır —
    bozuk yedekle sağlam hedefi ezmek imkânsızdır.
    """
    backup = Path(backup_path)
    target = Path(target_path)
    if backup.suffix == ".dump":
        raise NotImplementedError(
            "PostgreSQL geri yüklemesi otomatikleştirilmedi; şu komutu kullanın: "
            f"pg_restore --clean --if-exists --dbname=<URL> {backup}"
        )
    check = verify_backup(backup)
    if not check.get("ok"):
        raise RuntimeError(f"Yedek doğrulaması başarısız, geri yükleme iptal: {check.get('error')}")

    pre_restore_copy = None
    if target.exists():
        if not force:
            raise RuntimeError(
                f"Hedef mevcut: {target}. Üzerine yazmak için --force kullanın "
                "(önce .pre-restore kopyası alınır)."
            )
        pre_restore_copy = target.with_name(f"{target.name}.pre-restore-{_now_stamp()}")
        shutil.copy2(target, pre_restore_copy)

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(backup, target)
    return {
        "ok": True,
        "restored_to": str(target),
        "pre_restore_copy": str(pre_restore_copy) if pre_restore_copy else None,
        "verify": check,
    }


# ─── Prova (drill) ───────────────────────────────────────────────────────────

def run_drill(database_url: str | None = None, backups_dir: Path | None = None) -> dict:
    """Yedekle → doğrula → geçici hedefe geri yükle → satır sayılarını karşılaştır.

    Kanıt `backups/latest.json`'a yazılır. `overall_ok` ancak zincirin TAMAMI
    yeşilse True olur.
    """
    database_url = database_url or _default_database_url()
    backups_dir = Path(backups_dir or DEFAULT_BACKUPS_DIR)
    evidence: dict = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "overall_ok": False,
    }
    try:
        backup = create_backup(database_url, backups_dir)
        evidence["backup"] = backup
        verify = verify_backup(backup["backup_path"])
        evidence["verify"] = verify
        if not verify.get("ok"):
            return _write_evidence(evidence, backups_dir)

        if backup["engine"] == "sqlite":
            with tempfile.TemporaryDirectory() as tmp:
                restored = Path(tmp) / "restored.db"
                restore_backup(backup["backup_path"], restored)
                backup_counts = _sqlite_table_counts(Path(backup["backup_path"]))
                restored_counts = _sqlite_table_counts(restored)
                evidence["restore_drill"] = {
                    "restore_verified": restored_counts == backup_counts,
                    "table_count": len(restored_counts),
                    "row_total": sum(restored_counts.values()),
                    "mismatched_tables": sorted(
                        t for t in backup_counts if restored_counts.get(t) != backup_counts[t]
                    ),
                }
        else:
            evidence["restore_drill"] = {
                # Otomatik pg_restore yeni DB yaratma yetkisi ister; dürüst etiket.
                "restore_verified": "structure_listing_only",
                "toc_entries": verify.get("toc_entries"),
            }
        drill = evidence["restore_drill"]
        evidence["overall_ok"] = bool(verify.get("ok")) and drill.get("restore_verified") in (
            True,
            "structure_listing_only",
        )
    except Exception as exc:  # noqa: BLE001 — kanıtta hata da görünür olmalı
        evidence["error"] = str(exc)
    return _write_evidence(evidence, backups_dir)


def _write_evidence(evidence: dict, backups_dir: Path) -> dict:
    backups_dir.mkdir(parents=True, exist_ok=True)
    (backups_dir / "latest.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return evidence


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.ops.backup", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_backup = sub.add_parser("backup", help="Yedek al")
    p_verify = sub.add_parser("verify", help="Yedeği doğrula")
    p_verify.add_argument("path")
    p_restore = sub.add_parser("restore", help="Yedeği hedefe geri yükle (SQLite)")
    p_restore.add_argument("path")
    p_restore.add_argument("--target", required=True)
    p_restore.add_argument("--force", action="store_true")
    p_drill = sub.add_parser("drill", help="Tam prova: yedekle→doğrula→geri yükle→karşılaştır")
    for p in (p_backup, p_drill):
        p.add_argument("--database-url", default=None)
        p.add_argument("--backups-dir", default=None)

    args = parser.parse_args(argv)
    if args.command == "backup":
        result = create_backup(args.database_url, Path(args.backups_dir) if args.backups_dir else None)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    if args.command == "verify":
        result = verify_backup(args.path)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("ok") else 1
    if args.command == "restore":
        result = restore_backup(args.path, args.target, force=args.force)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    result = run_drill(args.database_url, Path(args.backups_dir) if args.backups_dir else None)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("overall_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
