from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SQLITE_DB = PROJECT_ROOT / "backend" / "data" / "cognivault.db"


WEAK_JWT_SECRETS = frozenset({
    "change-me-in-production",
    "replace-me",
    "secret",
    "secret-key",
    "jwt-secret",
    "dev-secret",
    "test-secret",
    "password",
    "12345678",
})

# Production'da JWT secret için minimum uzunluk. 32 byte = 256 bit entropy hedefi.
MIN_JWT_SECRET_LENGTH_PROD = 32
# Development'ta uyarı eşiği — daha esnek
MIN_JWT_SECRET_LENGTH_DEV = 16


class Settings(BaseSettings):
    app_name: str = "Cognivault AI API"
    app_env: str = "local"
    api_prefix: str = "/api"
    environment: str = "development"
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
    clinical_external_ai_allowed: bool = False
    voice_external_enabled: bool = False
    # Lokal LLM (KVKK local-first) — Ollama/vLLM OpenAI-uyumlu endpoint.
    # Ollama varsayılanı 11434; model demo için küçük tutuldu (M1/8GB).
    local_llm_base_url: str = "http://localhost:11434/v1"
    local_llm_model: str = "qwen2.5:3b-instruct"
    local_llm_timeout: float = 30.0
    # Klinik için varsayılan veri yerleşimi modu. tr_local_first => sağlık verisi
    # lokal LLM'de işlenir, dış sağlayıcıya (OpenAI/Anthropic) gitmez.
    clinical_data_residency_default: str = "tr_local_first"
    # ── Lokal ses (KVKK local-first): STT=faster-whisper, TTS=Piper TR ──────
    # "local" => ses verisi yurt dışına çıkmaz; "openai" sadece voice_external_enabled
    # true iken ve açıkça seçilirse kullanılır. Varsayılan tamamen lokaldir.
    voice_stt_provider: str = "local"   # local | openai | elevenlabs
    voice_tts_provider: str = "local"   # local | openai | elevenlabs
    # ── ElevenLabs (opt-in, rıza+DPA kapılı premium ses) ────────────────────
    # Varsayılan boş → devre dışı. Yalnızca voice_external_enabled=True VE
    # hasta VOICE_RECORDING rızası varken kullanılır (KVKK sınır-ötesi transfer).
    # TTS: Flash/Turbo (düşük gecikme). STT: Scribe v2 Realtime.
    elevenlabs_api_key: str = ""
    elevenlabs_tts_model: str = "eleven_flash_v2_5"
    elevenlabs_stt_model: str = "scribe_v2_realtime"
    elevenlabs_voice_id: str = ""  # klinik başına seçilen Selin sesi
    local_whisper_model: str = "small"  # tiny|base|small|medium — small TR için iyi denge
    local_whisper_compute: str = "int8"
    local_whisper_language: str = "tr"
    # Alan sözlüğü ipucu: whisper decode'unu diş kliniği bağlamına yaklaştırır
    # ("ağrıyor/dolgu/implant" gibi kelimeler ve TR telefon kalıpları daha az
    # yanlış çözülür). Boş string → ipucu gönderilmez.
    local_whisper_initial_prompt: str = (
        "Diş kliniği randevu görüşmesi. Hasta adı, telefon numarası, diş ağrısı, "
        "dolgu, kanal tedavisi, implant, ortodonti, diş eti, çekim, randevu saati."
    )
    # Piper prosodi ayarları — None → ses modelinin kendi varsayılanları.
    # length_scale >1 yavaşlatır (telefonda anlaşılırlık), noise_* doğallık katar.
    piper_length_scale: float | None = None
    piper_noise_scale: float | None = None
    piper_noise_w_scale: float | None = None
    # Açılışta lokal STT/TTS modellerini arka planda önceden yükle —
    # ilk sesli turdaki 3-10 sn'lik model-yükleme takılmasını yok eder.
    voice_warmup_enabled: bool = True
    piper_voice_path: str = str(BACKEND_ROOT / "data" / "piper" / "tr_TR-fahrettin-medium.onnx")
    # Tercih edilen ses dosyası yoksa sırayla denenecek yedekler (indirilmemiş
    # kurulumlar dfki ile çalışmaya devam eder; hiçbiri yoksa macOS say).
    piper_voice_fallbacks: list[str] = [
        str(BACKEND_ROOT / "data" / "piper" / "tr_TR-dfki-medium.onnx"),
    ]
    clinical_default_clinic_slug: str = "demo-klinik"
    # Kanal→klinik eşlemesi bulunamadığında davranış. False (demo): default
    # kliniğe düş — tek klinikli kurulum bugünkü gibi çalışır. True (çoklu
    # kiracı pilot): eşleşmeyen numara/WABA kimliği REDDEDİLİR; yanlış kliniğe
    # hasta verisi yazmak KVKK ihlalidir, sessiz düşüş kabul edilemez.
    clinical_channel_binding_strict: bool = False
    # ── SMS gönderimi ────────────────────────────────────────────────────────
    # "mock" (varsayılan): konsol simülasyonu. "netgsm": gerçek gönderim —
    # üç kimlik alanı da dolu olmalı, yoksa yüksek sesle loglanıp mock kullanılır.
    sms_provider: str = "mock"  # mock | netgsm
    # Gerçek takvim (ClinicDoctorSlot) boşken statik DEMO_SLOTS'a düşülsün mü?
    # True (demo): boş takvimde bile teklif üretilir. False (pilot): yalnız
    # gerçek takvim — boşsa hastaya "ekip sizinle iletişime geçecek" akışı.
    clinical_demo_slots_enabled: bool = True
    netgsm_usercode: str = ""
    netgsm_password: str = ""
    netgsm_msgheader: str = ""  # operatör onaylı gönderici başlığı
    sms_timeout: float = 10.0
    clinical_auto_reply_threshold: float = 0.90
    clinical_shadow_threshold: float = 0.75
    twilio_auth_token: str = ""
    twilio_account_sid: str = ""
    twilio_whatsapp_from: str = ""
    meta_verify_token: str = ""
    meta_access_token: str = ""
    meta_phone_number_id: str = ""
    meta_app_secret: str = ""
    clinical_webhook_signature_required: bool = False
    clinical_webhook_base_url: str = ""
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

    @field_validator("environment")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        return value.strip().lower() or "development"

    @property
    def is_production(self) -> bool:
        return self.environment in {"production", "prod", "staging"}

    @property
    def has_weak_jwt_secret(self) -> bool:
        """Dev için zayıflık kontrolü — production'da daha sıkı kural geçerli."""
        secret = self.jwt_secret.strip()
        return secret in WEAK_JWT_SECRETS or len(secret) < MIN_JWT_SECRET_LENGTH_DEV

    def jwt_secret_validation_error(self) -> str | None:
        """Production'da JWT_SECRET'in güçlü olduğunu doğrular.

        Dönen mesaj None değilse uygulama başlatılmamalı. Mesaj, operatöre nasıl
        çözüleceğini anlatır (`secrets.token_urlsafe(32)` komutu önerilir).
        """
        if not self.is_production:
            return None
        secret = self.jwt_secret.strip()
        if not secret:
            return "JWT_SECRET zorunlu — production'da boş geçilemez."
        if secret in WEAK_JWT_SECRETS:
            return (
                "JWT_SECRET bilinen-zayıf default değerlerden biri. "
                f"Yeni bir gizli üret: `python -c \"import secrets; print(secrets.token_urlsafe({MIN_JWT_SECRET_LENGTH_PROD}))\"`"
            )
        if len(secret) < MIN_JWT_SECRET_LENGTH_PROD:
            return (
                f"JWT_SECRET production için en az {MIN_JWT_SECRET_LENGTH_PROD} karakter olmalı "
                f"(mevcut: {len(secret)}). "
                f"Üret: `python -c \"import secrets; print(secrets.token_urlsafe({MIN_JWT_SECRET_LENGTH_PROD}))\"`"
            )
        # Entropi-hafif kontrol: tek-karakter veya çok tekrar eden pattern
        if len(set(secret)) < 8:
            return "JWT_SECRET düşük entropili (8'den az farklı karakter). Daha rastgele bir değer kullan."
        return None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def intelligence_allowed_source_list(self) -> list[str]:
        return [source.strip() for source in self.intelligence_allowed_sources.split(",") if source.strip()]

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
