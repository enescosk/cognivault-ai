import socket

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.rate_limit import limiter
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import SessionLocal
from app.main import app
from app.api.dependencies import get_db
from app.models import Role, RoleName, User
from app.core.security import hash_password

# Testler "güvenli varsayılan" davranışı (lokal LLM/dış ses KAPALI) doğrular.
# Demo .env'i bu bayrakları açabilir (CLINICAL_AI_ENABLED, VOICE_EXTERNAL_ENABLED);
# bu ayarların test sonuçlarına sızmaması için cached settings objesini test
# koşumunda deterministik değerlere sabitle. get_settings() lru_cache'li tek bir
# instance döndürdüğü için (voice.py'nin import anında yakaladığı obje ile aynı),
# burada yapılan mutasyon tüm route'larda görünür.
_test_settings = get_settings()
_test_settings.clinical_ai_enabled = False
_test_settings.clinical_external_ai_allowed = False
_test_settings.voice_external_enabled = False
# Telefon TwiML testleri yanıt METNİNİ doğrular; gerçek TTS sentezi hem yavaş
# hem metni <Play> URL'ine gizler. Testte kapalı — TwiML <Say> fallback'i
# üretir. TTS'li verse davranışı test_phone_booking_flow'da mock ile açılır.
_test_settings.voice_phone_native_tts_enabled = False

# ── Ağ kill-switch'i (test koşumu ASLA gerçek servise gitmez) ───────────────
# Geliştirme makinesinde .env `LOCAL_LLM_BASE_URL`/`OPENAI_API_KEY` dolu ve
# Ollama ayakta olabiliyor. Bu ayarlar cached settings üzerinden testlere sızınca
# `select_llm_runtime()` gerçek bir runtime döndürüyor, `complete_json` de
# localhost:11434'e HTTP atıyordu: paket 65 dakikaya çıkıyor (CI'ın 15 dk
# limitini aşıyor) ve sonuçlar makinede Ollama açık mı diye değişiyordu.
# İki katmanlı savunma: (1) ayarları boşalt → runtime seçilemez,
# (2) socket.connect'i kapat → herhangi bir yol yine de dışarı çıkmayı denerse
# sessizce yavaşlamak yerine anlaşılır bir hata ile patlasın.
_test_settings.openai_api_key = ""
_test_settings.anthropic_api_key = ""
_test_settings.local_llm_base_url = ""
_test_settings.elevenlabs_api_key = ""
_test_settings.preferred_llm_provider = "local"


class BlockedNetworkCall(RuntimeError):
    """Test koşumunda gerçek ağ çağrısı denendi."""


_real_socket_connect = socket.socket.connect


def _blocked_socket_connect(self, address, *args, **kwargs):
    raise BlockedNetworkCall(
        f"Test koşumunda gerçek ağ bağlantısı engellendi: {address!r}. "
        "Dış servisi (LLM/STT/TTS/SMS) mock'layın; gerçek çağrı gerekiyorsa "
        "tests/conftest.py'deki allow_real_network fixture'ını kullanın."
    )


socket.socket.connect = _blocked_socket_connect


@pytest.fixture
def allow_real_network():
    """Bilerek gerçek ağ isteyen (entegrasyon) testler için kaçış kapısı."""
    socket.socket.connect = _real_socket_connect
    try:
        yield
    finally:
        socket.socket.connect = _blocked_socket_connect


# Test suite TestClient'ı tek IP üzerinden binlerce istek atar; login için
# `@limiter.limit("10/minute")` testleri brute-force kabul edip 429 döner ve
# `KeyError: 'access_token'` ile her fixture çöker. Üretim davranışı korunur,
# sadece test koşumunda kapatıyoruz. SlowAPI Limiter'ın resmi `enabled` flag'i
# bu amaç için var.
limiter.enabled = False

SQLITE_URL = "sqlite://"

engine = create_engine(
    SQLITE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
TEST_PASSWORD_HASH = hash_password("password123")


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    # Seed roles
    for role_name in RoleName:
        if not db.query(Role).filter_by(name=role_name).first():
            db.add(Role(name=role_name, description=role_name.value))
    db.commit()

    # Seed users
    customer_role = db.query(Role).filter_by(name=RoleName.CUSTOMER).first()
    admin_role = db.query(Role).filter_by(name=RoleName.ADMIN).first()
    operator_role = db.query(Role).filter_by(name=RoleName.OPERATOR).first()

    users = [
        User(full_name="Test Customer", email="customer@test.com",
             hashed_password=TEST_PASSWORD_HASH, locale="en",
             role_id=customer_role.id, is_active=True),
        User(full_name="Test Customer2", email="customer2@test.com",
             hashed_password=TEST_PASSWORD_HASH, locale="en",
             role_id=customer_role.id, is_active=True),
        User(full_name="Test Admin", email="admin@test.com",
             hashed_password=TEST_PASSWORD_HASH, locale="en",
             role_id=admin_role.id, is_active=True),
        User(full_name="Test Operator", email="operator@test.com",
             hashed_password=TEST_PASSWORD_HASH, locale="en",
             role_id=operator_role.id, is_active=True),
    ]
    for u in users:
        if not db.query(User).filter_by(email=u.email).first():
            db.add(u)
    db.commit()
    db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db_session():
    """Direct session against the test database (same engine as the FastAPI override)."""

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def customer_token(client):
    res = client.post("/api/auth/login", json={"email": "customer@test.com", "password": "password123"})
    return res.json()["access_token"]


@pytest.fixture
def admin_token(client):
    res = client.post("/api/auth/login", json={"email": "admin@test.com", "password": "password123"})
    return res.json()["access_token"]


@pytest.fixture
def operator_token(client):
    res = client.post("/api/auth/login", json={"email": "operator@test.com", "password": "password123"})
    return res.json()["access_token"]
