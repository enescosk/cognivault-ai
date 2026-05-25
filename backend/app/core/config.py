from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_DB = PROJECT_ROOT / "backend" / "data" / "cognivault.db"


WEAK_JWT_SECRETS = frozenset({"change-me-in-production", "replace-me", "secret", "secret-key", "jwt-secret"})


class Settings(BaseSettings):
    app_name: str = "Cognivault AI API"
    api_prefix: str = "/api"
    environment: str = "development"
    database_url: str = f"sqlite:///{DEFAULT_SQLITE_DB.as_posix()}"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    anthropic_intent_model: str = "claude-3-5-haiku-latest"
    clinical_ai_enabled: bool = False
    clinical_external_ai_allowed: bool = False
    voice_external_enabled: bool = False
    clinical_default_clinic_slug: str = "demo-klinik"
    clinical_auto_reply_threshold: float = 0.90
    clinical_shadow_threshold: float = 0.75
    twilio_auth_token: str = ""
    twilio_account_sid: str = ""
    twilio_whatsapp_from: str = ""
    meta_verify_token: str = ""
    meta_access_token: str = ""
    meta_phone_number_id: str = ""
    meta_app_secret: str = ""
    intelligence_external_enabled: bool = False
    intelligence_allowed_sources: str = "manual,website,google_places,x_api,reddit_api"
    intelligence_max_results_per_job: int = 25
    intelligence_default_rate_limit_per_minute: int = 30
    google_places_api_key: str = ""
    # E-posta bildirimi (isteğe bağlı — boş bırakılırsa simülasyon modu)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = "noreply@cognivault.local"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    seed_demo_data: bool = True
    # When true, inbound provider webhooks (Twilio, Meta) must carry a valid
    # signature header — required for production.
    clinical_webhook_signature_required: bool = False
    # Public URL used as the canonical base when verifying Twilio request signatures.
    # If empty, the request URL as received by FastAPI is used.
    clinical_webhook_base_url: str = ""

    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_ROOT / ".env"), str(BACKEND_ROOT / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("cors_origins")
    @classmethod
    def clean_origins(cls, value: str) -> str:
        return ",".join(origin.strip() for origin in value.split(",") if origin.strip())

    @field_validator("environment")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        return value.strip().lower() or "development"

    @property
    def is_production(self) -> bool:
        return self.environment in {"production", "prod", "staging"}

    @property
    def has_weak_jwt_secret(self) -> bool:
        secret = self.jwt_secret.strip()
        return secret in WEAK_JWT_SECRETS or len(secret) < 16

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def intelligence_allowed_source_list(self) -> list[str]:
        return [source.strip() for source in self.intelligence_allowed_sources.split(",") if source.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
