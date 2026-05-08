from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_DB = PROJECT_ROOT / "backend" / "data" / "cognivault.db"


class Settings(BaseSettings):
    app_name: str = "Cognivault AI API"
    app_env: str = "local"
    api_prefix: str = "/api"
    database_url: str = f"sqlite:///{DEFAULT_SQLITE_DB.as_posix()}"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    anthropic_intent_model: str = "claude-haiku-4-5-20251001"
    preferred_agent_provider: str = "auto"  # auto | openai | anthropic | local
    local_llm_base_url: str = ""
    local_llm_api_key: str = "local"
    local_llm_model: str = "cognivault-local"
    preferred_llm_provider: str = "auto"
    speech_stt_provider: str = "auto"
    speech_tts_provider: str = "auto"
    whisper_cpp_binary: str = ""
    whisper_cpp_model: str = ""
    piper_binary: str = ""
    piper_voice_model: str = ""
    max_voice_upload_bytes: int = 15_000_000
    clinical_ai_enabled: bool = False
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
    quality_artifact_path: str = str(PROJECT_ROOT / "backend" / "data" / "quality" / "latest_report.json")
    google_places_api_key: str = ""
    # E-posta bildirimi (isteğe bağlı — boş bırakılırsa simülasyon modu)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = "noreply@cognivault.local"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5200,http://127.0.0.1:5200,http://localhost:5273,http://127.0.0.1:5273"
    seed_demo_data: bool = True
    auto_create_schema: bool = True

    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_ROOT / ".env"), str(BACKEND_ROOT / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("cors_origins")
    @classmethod
    def clean_origins(cls, value: str) -> str:
        return ",".join(origin.strip() for origin in value.split(",") if origin.strip())

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def intelligence_allowed_source_list(self) -> list[str]:
        return [source.strip() for source in self.intelligence_allowed_sources.split(",") if source.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in {"prod", "production"}

    def validate_runtime_safety(self) -> None:
        weak_secrets = {"change-me-in-production", "replace-me", "secret", ""}
        if self.is_production and self.jwt_secret in weak_secrets:
            raise RuntimeError("JWT_SECRET must be set to a strong value when APP_ENV=production")
        if self.is_production and self.seed_demo_data:
            raise RuntimeError("SEED_DEMO_DATA must be false when APP_ENV=production")
        if self.is_production and self.auto_create_schema:
            raise RuntimeError("AUTO_CREATE_SCHEMA must be false in production; run migrations explicitly")


@lru_cache
def get_settings() -> Settings:
    return Settings()
