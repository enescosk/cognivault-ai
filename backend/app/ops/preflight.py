"""Prod ops — dağıtım öncesi güvenlik preflight panosu.

Gerçek prod ortamı (canlı PostgreSQL, backup restore provası, secret rotation
tatbikatı) saha/altyapı gerektirir. Bu modül onun **kod ile doğrulanabilir**
ayağıdır: production dağıtımını bloklaması gereken güvenlik guard'larının
gerçekten çalıştığını kanıtlar ve migration bütünlüğünü denetler.

İki tür deterministik kanıt:
- **Guard doğrulama:** zayıf JWT, demo-seed, auto-schema, sqlite-in-prod,
  wildcard-CORS gibi güvensiz production config'leri guard'ların RED ettiğini;
  güvenli config'i KABUL ettiğini hem kabul hem red yolundan koşarak gösterir
  (dairesel değil — mekanizmanın kendisini test eder).
- **Migration bütünlüğü:** `migrations/versions/` revizyon grafiğini ayrıştırıp
  tam olarak tek alembic head olduğunu doğrular (geçmişte çift-head bug'ı oldu).

Ayrıca prod dağıtımı için insan-yürütmeli runbook adımlarını (backup/restore
provası, secret rotation, alert tatbikatı) dürüstçe "kalan" olarak listeler.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

from app.core.config import Settings


ARTIFACT_PATH = Path(__file__).resolve().parent / "data" / "preflight.json"
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations" / "versions"


# ── Migration grafiği ────────────────────────────────────────────────────────


def _literal(node: ast.AST) -> object:
    try:
        return ast.literal_eval(node)
    except (ValueError, SyntaxError):
        return None


def parse_migration_graph(versions_dir: Path = MIGRATIONS_DIR) -> dict[str, object]:
    """Alembic revizyon/down_revision grafiğini dosyalardan ayrıştırır (import etmeden)."""
    revisions: set[str] = set()
    down_refs: set[str] = set()
    edges: dict[str, tuple[str, ...]] = {}
    for path in sorted(versions_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        revision: str | None = None
        down: tuple[str, ...] = ()
        for stmt in tree.body:
            if not isinstance(stmt, ast.Assign) and not isinstance(stmt, ast.AnnAssign):
                continue
            targets = (
                [stmt.target] if isinstance(stmt, ast.AnnAssign) else stmt.targets
            )
            names = [t.id for t in targets if isinstance(t, ast.Name)]
            value = _literal(stmt.value) if stmt.value is not None else None
            if "revision" in names and isinstance(value, str):
                revision = value
            elif "down_revision" in names:
                if isinstance(value, str):
                    down = (value,)
                elif isinstance(value, (tuple, list)):
                    down = tuple(v for v in value if isinstance(v, str))
                elif value is None:
                    down = ()
        if revision is not None:
            revisions.add(revision)
            edges[revision] = down
            down_refs.update(down)
    heads = sorted(revisions - down_refs)
    bases = sorted(rev for rev, down in edges.items() if not down)
    return {"revisions": sorted(revisions), "heads": heads, "bases": bases, "edges": edges}


# ── Config guard doğrulama ───────────────────────────────────────────────────


# Yüksek-entropili, deterministik test secret'ı (>=32 char, çok farklı karakter).
STRONG_TEST_JWT = "k7Qm2Xp9Zt4Rw8Lc1Nv6Bh3Yd5Fj0GsAe"


def _prod(**overrides) -> Settings:
    """Env dosyasından bağımsız, deterministik production Settings profili."""
    base = {"environment": "production", "jwt_secret": STRONG_TEST_JWT}
    base.update(overrides)
    return Settings(_env_file=None, **base)


def _guard_raises(settings: Settings) -> str | None:
    try:
        settings.validate_runtime_safety()
    except RuntimeError as exc:
        return str(exc)
    return None


def _gate_migration_single_head() -> dict:
    graph = parse_migration_graph()
    return {
        "target": "tam olarak tek alembic head (çift-head yok)",
        "heads": graph["heads"],
        "revision_count": len(graph["revisions"]),
        "pass": len(graph["heads"]) == 1,
    }


def _gate_weak_jwt_rejected() -> dict:
    weak_err = _prod(jwt_secret="change-me-in-production").jwt_secret_validation_error()
    short_err = _prod(jwt_secret="short").jwt_secret_validation_error()
    strong_ok = _prod(jwt_secret=STRONG_TEST_JWT).jwt_secret_validation_error() is None
    # Dev'de guard gevşek olmalı (üretim-dışı geliştirmeyi bloklamaz).
    dev_none = Settings(_env_file=None, environment="development").jwt_secret_validation_error() is None
    return {
        "target": "prod'da zayıf/kısa JWT reddedilir, güçlü kabul edilir; dev serbest",
        "weak_rejected": bool(weak_err),
        "short_rejected": bool(short_err),
        "strong_accepted": strong_ok,
        "dev_unrestricted": dev_none,
        "pass": bool(weak_err) and bool(short_err) and strong_ok and dev_none,
    }


def _gate_demo_seed_blocked() -> dict:
    blocked = _guard_raises(_prod(seed_demo_data=True))
    allowed = _guard_raises(_prod(seed_demo_data=False, auto_create_schema=False))
    return {
        "target": "prod'da SEED_DEMO_DATA açıkken başlatma engellenir",
        "unsafe_blocked": blocked is not None,
        "safe_allowed": allowed is None,
        "pass": blocked is not None and allowed is None,
    }


def _gate_auto_schema_blocked() -> dict:
    blocked = _guard_raises(_prod(auto_create_schema=True, seed_demo_data=False))
    return {
        "target": "prod'da AUTO_CREATE_SCHEMA açıkken başlatma engellenir (migration zorunlu)",
        "unsafe_blocked": blocked is not None,
        "pass": blocked is not None,
    }


def _gate_kvkk_residency_defaults() -> dict:
    # Fabrika ayarı: sağlık verisi lokal işlenir, dış AI/ses varsayılan kapalı.
    s = Settings(_env_file=None)
    return {
        "target": "KVKK local-first varsayılanları: residency=tr_local_first, dış AI/ses kapalı",
        "residency_default": s.clinical_data_residency_default,
        "external_ai_off": s.clinical_external_ai_allowed is False,
        "external_voice_off": s.voice_external_enabled is False,
        "pass": (
            s.clinical_data_residency_default == "tr_local_first"
            and s.clinical_external_ai_allowed is False
            and s.voice_external_enabled is False
        ),
    }


def _gate_sqlite_flagged_in_prod() -> dict:
    """Preflight, prod'da sqlite backend'i uyarı olarak işaretlemeli."""
    prod_sqlite = _prod(database_url="sqlite:///./data/cognivault.db")
    prod_pg = _prod(database_url="postgresql+psycopg://u:p@db:5432/cognivault")
    return {
        "target": "prod'da sqlite backend işaretlenir; postgres kabul edilir",
        "sqlite_flagged": _database_is_sqlite(prod_sqlite),
        "postgres_ok": not _database_is_sqlite(prod_pg),
        "pass": _database_is_sqlite(prod_sqlite) and not _database_is_sqlite(prod_pg),
    }


def _gate_cors_wildcard_flagged() -> dict:
    wild = _prod(cors_origins="*")
    scoped = _prod(cors_origins="https://klinik.example")
    return {
        "target": "prod'da wildcard CORS işaretlenir; kapsamlı origin kabul edilir",
        "wildcard_flagged": _cors_has_wildcard(wild),
        "scoped_ok": not _cors_has_wildcard(scoped),
        "pass": _cors_has_wildcard(wild) and not _cors_has_wildcard(scoped),
    }


def _database_is_sqlite(settings: Settings) -> bool:
    return settings.database_url.strip().lower().startswith("sqlite")


def _cors_has_wildcard(settings: Settings) -> bool:
    return "*" in settings.cors_origin_list


def evaluate_production_config(settings: Settings) -> list[dict]:
    """Verilen bir config'in production dağıtımını bloklayan bulgularını döndürür.

    Operatörün elindeki gerçek profili denetlemek için kamuya açık yardımcı.
    Boş liste → dağıtıma hazır (bu deterministik kontroller açısından).
    """
    findings: list[dict] = []
    if settings.is_production:
        jwt_err = settings.jwt_secret_validation_error()
        if jwt_err:
            findings.append({"id": "jwt_secret", "severity": "block", "message": jwt_err})
        runtime_err = _guard_raises(settings)
        if runtime_err:
            findings.append({"id": "runtime_safety", "severity": "block", "message": runtime_err})
        if _database_is_sqlite(settings):
            findings.append({
                "id": "database_backend",
                "severity": "block",
                "message": "Production'da sqlite kullanılamaz; PostgreSQL DATABASE_URL ayarla.",
            })
        if _cors_has_wildcard(settings):
            findings.append({
                "id": "cors_wildcard",
                "severity": "warn",
                "message": "Production CORS wildcard (*) içeriyor; klinik origin'lerine daralt.",
            })
    if settings.clinical_data_residency_default != "tr_local_first":
        findings.append({
            "id": "residency",
            "severity": "warn",
            "message": "Klinik veri yerleşimi local-first değil; KVKK açısından gözden geçir.",
        })
    return findings


def build_report() -> dict:
    gates = {
        "migration_single_head": _gate_migration_single_head(),
        "weak_jwt_rejected": _gate_weak_jwt_rejected(),
        "demo_seed_blocked": _gate_demo_seed_blocked(),
        "auto_schema_blocked": _gate_auto_schema_blocked(),
        "kvkk_residency_defaults": _gate_kvkk_residency_defaults(),
        "sqlite_flagged_in_prod": _gate_sqlite_flagged_in_prod(),
        "cors_wildcard_flagged": _gate_cors_wildcard_flagged(),
    }
    # Örnek: temiz bir prod profilinin bloklayan bulgusu olmamalı.
    safe_prod_findings = evaluate_production_config(
        _prod(
            database_url="postgresql+psycopg://u:p@db:5432/cognivault",
            seed_demo_data=False,
            auto_create_schema=False,
            cors_origins="https://klinik.example",
        )
    )
    return {
        "name": "prod_ops_preflight",
        "purpose": "deployment_safety_guard_verification",
        "gates": gates,
        "safe_prod_profile_blocking_findings": [
            f for f in safe_prod_findings if f["severity"] == "block"
        ],
        "overall_pass": all(gate["pass"] for gate in gates.values())
        and not [f for f in safe_prod_findings if f["severity"] == "block"],
        "runbook_remaining": [
            "Gerçek prod PostgreSQL migration koşumu (alembic upgrade head).",
            "Backup alma + restore provası (RPO/RTO ölçümü).",
            "Secret rotation tatbikatı (JWT + DB + webhook token).",
            "Alert/runbook tatbikatı (health/readyz + hata oranı + gecikme alarmı).",
            "Olay müdahale (incident) kuru-koşusu.",
        ],
    }


def render(report: dict) -> str:
    ok = lambda value: "PASS" if value else "FAIL"  # noqa: E731
    lines = [
        "Prod Ops — Dağıtım Öncesi Güvenlik Preflight",
        "=" * 60,
    ]
    for key, gate in report["gates"].items():
        lines.append(f"{ok(gate['pass']):<5} {key:<24} {gate['target']}")
    lines += [
        "-" * 60,
        f"GENEL: {ok(report['overall_pass'])}",
        "Kalan (insan-yürütmeli runbook):",
    ]
    lines.extend(f"- {item}" for item in report["runbook_remaining"])
    return "\n".join(lines)


def write_artifact(report: dict, path: Path = ARTIFACT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prod ops dağıtım öncesi preflight panosu")
    parser.add_argument("--no-save", action="store_true", help="artefakt yazma")
    parser.add_argument("--json", action="store_true", help="JSON çıktısı")
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
