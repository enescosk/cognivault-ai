"""Production dağıtım paketi ↔ uygulama davranışı senkron mu?

`docker-compose.prod.yml`, `deploy/Caddyfile`, `Dockerfile` ve `.env.prod.example`
kodun dışında yaşıyor; hiçbir test onlara bakmazsa sessizce kodla çelişebilirler
ve bunu ancak canlıda fark ederiz. Bu dosya o çelişkileri **dağıtımdan önce**
yakalar.

Sözleşmeler:
  - Prod guard'ları (ENVIRONMENT/AUTO_CREATE_SCHEMA/SEED_DEMO_DATA) compose'da
    uygulamanın beklediği değerlerde.
  - Sırların compose'da varsayılanı YOK — "replace-me" ile canlıya çıkılamaz.
  - Backend imajı migration'ları ve yedekleme ikililerini içeriyor.
  - `/metrics` dışarıya kapalı, `/api/*` backend'e gidiyor.
  - deploy.sh'in aradığı zorunlu alanların hepsi .env.prod.example'da var.
"""
from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_PROD = REPO_ROOT / "docker-compose.prod.yml"
CADDYFILE = REPO_ROOT / "deploy" / "Caddyfile"
ENV_EXAMPLE = REPO_ROOT / ".env.prod.example"
DOCKERFILE = REPO_ROOT / "backend" / "Dockerfile"
DEPLOY_SH = REPO_ROOT / "scripts" / "prod" / "deploy.sh"
GITIGNORE = REPO_ROOT / ".gitignore"


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(COMPOSE_PROD.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def env_example_keys() -> set[str]:
    keys = set()
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            keys.add(line.split("=", 1)[0])
    return keys


# ── Prod guard'ları ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("service", ["backend", "outbox-worker", "migrate", "backup"])
def test_python_services_run_with_production_guards(compose, service):
    """Şema otomatik yaratılmaz, demo verisi tohumlanmaz, ortam production'dır.

    `app/db/bootstrap.py` production'da şemayı açık migration'a bırakıyor ve
    `app/core/config.py` guard'ı `SEED_DEMO_DATA`/`AUTO_CREATE_SCHEMA` açıkken
    production'ı reddediyor. Compose bu sözleşmeyi bozarsa konteyner ya hiç
    başlamaz ya da demo verisiyle canlıya çıkar.
    """
    env = compose["services"][service]["environment"]
    assert env["ENVIRONMENT"] == "production"
    assert env["AUTO_CREATE_SCHEMA"] == "false"
    assert env["SEED_DEMO_DATA"] == "false"


def test_database_is_postgres_not_sqlite(compose):
    """Preflight production'da sqlite'ı BLOCK sayıyor; compose da öyle olmalı."""
    url = compose["services"]["backend"]["environment"]["DATABASE_URL"]
    assert url.startswith("postgresql+psycopg://")
    assert "sqlite" not in url


def test_secrets_have_no_defaults(compose):
    """`${VAR:?...}` — eksik sır compose'u durdurur, sessizce varsayılana düşmez."""
    raw = COMPOSE_PROD.read_text(encoding="utf-8")
    for secret in ("JWT_SECRET", "POSTGRES_PASSWORD", "POSTGRES_USER", "POSTGRES_DB"):
        assert f"${{{secret}:?" in raw, f"{secret} için zorunluluk işareti (:?) yok"
    # Varsayılan atama sözdizimi (`:-`) sırlarda kullanılmamalı.
    for secret in ("JWT_SECRET", "POSTGRES_PASSWORD"):
        assert f"${{{secret}:-" not in raw, f"{secret} varsayılan değere düşüyor"


def test_database_port_is_not_published(compose):
    """Postgres yalnız iç ağdan erişilebilir olmalı."""
    assert "ports" not in compose["services"]["db"]


def test_only_caddy_publishes_host_ports(compose):
    """TLS sonlandırma tek giriş noktası; başka servis host'a port açmamalı."""
    publishing = {
        name for name, spec in compose["services"].items() if spec.get("ports")
    }
    assert publishing == {"caddy"}


# ── Başlatma sırası ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("service", ["backend", "outbox-worker"])
def test_app_waits_for_migration_to_complete(compose, service):
    """Yarım göçmüş şemayla trafik almaktansa hiç başlamamak."""
    depends = compose["services"][service]["depends_on"]
    assert depends["migrate"]["condition"] == "service_completed_successfully"
    assert depends["db"]["condition"] == "service_healthy"


def test_migrate_service_runs_alembic_upgrade_head(compose):
    assert compose["services"]["migrate"]["command"] == ["alembic", "upgrade", "head"]


def test_migrate_does_not_restart(compose):
    """Tek seferlik iş — yeniden başlatma döngüsüne girmemeli."""
    assert compose["services"]["migrate"]["restart"] == "no"


# ── Webhook / CORS tutarlılığı ───────────────────────────────────────────────

def test_webhook_base_url_matches_serving_domain(compose):
    """Twilio imzası CLINICAL_WEBHOOK_BASE_URL'e göre doğrulanır.

    Bu değer Caddy'nin servis ettiği domain'den farklı olursa imza doğrulaması
    her çağrıda düşer ve telefon akışı sessizce ölür.
    """
    env = compose["services"]["backend"]["environment"]
    assert env["CLINICAL_WEBHOOK_BASE_URL"] == "https://${COGNIVAULT_DOMAIN}"
    assert env["CORS_ORIGINS"].startswith("https://${COGNIVAULT_DOMAIN")


def test_frontend_api_url_is_same_origin(compose):
    """SPA API'yi kendi origin'inden çağırır — CORS yüzeyi açılmasın."""
    args = compose["services"]["frontend"]["build"]["args"]
    assert args["VITE_API_URL"] == "https://${COGNIVAULT_DOMAIN}/api"


# ── Caddy yönlendirmesi ──────────────────────────────────────────────────────

def test_caddy_blocks_metrics_from_public_internet():
    """/metrics istek hacmi ve klinik kimliği sızdırır; dışarıya kapalı olmalı."""
    caddy = CADDYFILE.read_text(encoding="utf-8")
    assert "handle /metrics*" in caddy
    assert "reverse_proxy" not in caddy.split("handle /metrics*")[1].split("}")[0]


@pytest.mark.parametrize("route", ["/api/*", "/healthz", "/readyz"])
def test_caddy_routes_backend_paths(route):
    caddy = CADDYFILE.read_text(encoding="utf-8")
    assert f"handle {route}" in caddy


def test_caddy_uses_acme_email_from_environment():
    """Sertifika yenileme hatası bir insana ulaşmalı."""
    assert "{$ACME_EMAIL}" in CADDYFILE.read_text(encoding="utf-8")


# ── Backend imajı ────────────────────────────────────────────────────────────

def test_image_contains_migrations():
    """Migration'lar imajda yoksa `alembic upgrade head` konteynerde koşamaz.

    Regresyon: bu dosyalar kopyalanmadığı için mevcut imajla production'a
    çıkmak fiilen imkânsızdı.
    """
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "COPY migrations ./migrations" in dockerfile
    assert "COPY alembic.ini" in dockerfile


def test_image_contains_postgres_client_for_backups():
    """`app.ops.backup` pg_dump/pg_restore yoksa yedek almayı REDDEDER."""
    assert "postgresql-client" in DOCKERFILE.read_text(encoding="utf-8")


def test_image_runs_as_non_root():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "USER cognivault" in dockerfile
    assert dockerfile.index("USER cognivault") > dockerfile.index("useradd")


def test_image_healthcheck_uses_readyz():
    """Healthcheck DB'yi de kontrol eden uca bakmalı (/readyz DB ölüyse 503)."""
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    assert "HEALTHCHECK" in dockerfile
    assert "/readyz" in dockerfile.split("HEALTHCHECK")[1]


# ── Operatör yüzeyi ──────────────────────────────────────────────────────────

def test_env_example_covers_every_key_deploy_script_requires(env_example_keys):
    """deploy.sh'in zorunlu tuttuğu her alan örnek dosyada bulunmalı.

    Aksi hâlde operatör örneği doldurur, script yine de "boş zorunlu alan" der.
    """
    deploy_sh = DEPLOY_SH.read_text(encoding="utf-8")
    required_line = next(
        line for line in deploy_sh.splitlines() if "for key in COGNIVAULT_DOMAIN" in line
    )
    required = required_line.split("for key in", 1)[1].split(";")[0].split()
    missing = [key for key in required if key not in env_example_keys]
    assert missing == [], f".env.prod.example'da eksik: {missing}"


def test_env_example_ships_kvkk_safe_defaults(env_example_keys):
    """Örnek dosya yerel-öncelik ve imza zorunluluğuyla gelmeli."""
    text = ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "CLINICAL_WEBHOOK_SIGNATURE_REQUIRED=true" in text
    assert "CLINICAL_CHANNEL_BINDING_STRICT=true" in text
    assert "CLINICAL_DATA_RESIDENCY_DEFAULT=tr_local_first" in text
    assert "CLINICAL_EXTERNAL_AI_ALLOWED=false" in text


def test_env_example_leaves_secrets_empty():
    """Örnekte hazır bir sır olmamalı — kopyalayıp öylece kullanmak imkânsız."""
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        if line.startswith(("JWT_SECRET=", "POSTGRES_PASSWORD=")):
            assert line.split("=", 1)[1] == "", f"örnekte dolu sır var: {line}"


def test_prod_secrets_file_is_gitignored():
    gitignore = GITIGNORE.read_text(encoding="utf-8")
    assert ".env.prod" in gitignore
    assert "!.env.prod.example" in gitignore, "örnek dosya yanlışlıkla yok sayılıyor"
