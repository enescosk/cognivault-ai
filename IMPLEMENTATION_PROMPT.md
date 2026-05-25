# CogniVault AI - Güvenlik & Performans Geliştirme Prompt'u

## 📋 Bağlam

CogniVault AI projesi bir kurumsal AI aracısı sistemi (FastAPI + React). Güvenlik ve performans analizinde 5 kritik, 8 yüksek seviye sorun tespit edildi. Bu prompt, sorunları öncelik sırasına göre düzeltmeyi rehberlik edecek.

---

## 🔴 PHASE 1: KRİTİK GÜVENLIK SORUNLARI (Gün 1-2)

### Task 1.1: Password Hashing'i SHA256'dan Bcrypt'e Geçir

**Dosya:** `backend/app/core/security.py`

**Gerekli Değişiklikler:**

1. `requirements.txt`'e ekle:
```
passlib[bcrypt]==1.7.4
```

2. `security.py`'yi tamamen yeniden yaz:

```python
from passlib.context import CryptContext
from datetime import datetime, timedelta, timezone
import jwt

from app.core.config import get_settings

# Bcrypt context (salt rounds: 12)
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)

def hash_password(password: str) -> str:
    """SHA256 yerine bcrypt kullan."""
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    return pwd_context.hash(password)

def verify_password(password: str, hashed_password: str) -> bool:
    """Bcrypt doğrulama."""
    return pwd_context.verify(password, hashed_password)

def create_access_token(subject: str, *, organization_id: int | None = None) -> str:
    settings = get_settings()
    if len(settings.jwt_secret) < 32:
        raise ValueError("JWT_SECRET must be at least 32 characters in production")
    
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload: dict[str, object] = {
        "sub": subject,
        "exp": expires_at,
        "iat": datetime.now(timezone.utc),
    }
    if organization_id is not None:
        payload["org_id"] = organization_id
    
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")
```

3. Test et:
```bash
cd backend
python -m pytest app/tests/test_security.py -v
```

**Test Kod Örneği:**
```python
# app/tests/test_security.py
import pytest
from app.core.security import hash_password, verify_password

def test_bcrypt_hashing():
    password = "MySecurePassword123!"
    hashed = hash_password(password)
    
    # Hash her zaman farklı (salt dahil)
    assert hashed != hash_password(password)
    
    # Ancak doğrulama çalışmalı
    assert verify_password(password, hashed)
    assert not verify_password("wrong", hashed)

def test_weak_password_rejected():
    with pytest.raises(ValueError):
        hash_password("short")
```

**Zaman:** 1 saat

---

### Task 1.2: JWT Secret Validation + Production Guard

**Dosya:** `backend/app/core/config.py`

**Gerekli Değişiklikler:**

```python
import os
from pydantic import field_validator
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # ... diğer ayarlar ...
    jwt_secret: str = "change-me-in-production"
    environment: str = "development"
    
    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, value: str, info) -> str:
        """Production'da JWT_SECRET zorunlu ve güçlü olmalı."""
        is_production = (
            os.getenv("ENVIRONMENT", "development").lower() in 
            {"production", "prod", "staging"}
        )
        
        if is_production:
            if value in {"change-me-in-production", "secret", "secret-key"}:
                raise ValueError(
                    "JWT_SECRET cannot be the default value in production. "
                    "Generate a strong random secret: "
                    "python -c \"import secrets; print(secrets.token_urlsafe(32))\""
                )
            if len(value) < 32:
                raise ValueError(
                    f"JWT_SECRET must be at least 32 characters in production. "
                    f"Current length: {len(value)}"
                )
        
        return value
    
    @property
    def has_weak_jwt_secret(self) -> bool:
        secret = self.jwt_secret.strip()
        return secret in {"change-me-in-production", "secret"} or len(secret) < 16
```

**main.py'de Check Ekle:**

```python
# backend/app/main.py
from app.core.config import get_settings

settings = get_settings()

# Startup kontrolü
if settings.is_production and settings.has_weak_jwt_secret:
    raise RuntimeError(
        f"SECURITY: JWT_SECRET is weak. Generate a new one:\n"
        f"python -c \"import secrets; print(secrets.token_urlsafe(32))\""
    )
```

**Zaman:** 30 dakika

---

### Task 1.3: CORS'u Whitelist'e Döndür

**Dosya:** `backend/app/main.py`

**Gerekli Değişiklikler:**

```python
# Eski (UNSAFE)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],       # ❌ BURADA SORUN
    allow_headers=["*"],       # ❌ BURADA SORUN
)

# Yeni (SECURE)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],  # ✓ Whitelist
    allow_headers=[
        "Content-Type",
        "Authorization",
        "X-Request-ID",
    ],  # ✓ Whitelist
    max_age=3600,  # Preflight cache 1 saat
    expose_headers=["X-Request-ID"],  # Client'ın görebileceği headers
)
```

**Frontend'de Test Et:**

```javascript
// Frontend şöyle çalışmalı
fetch('/api/chat/sessions', {
    method: 'GET',
    headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
    }
})

// Bu başarısız olmalı (OPTIONS'da DELETE'ı soramaz)
fetch('/api/users/123', {
    method: 'DELETE',  // ❌ Not allowed
    headers: {'Authorization': `Bearer ${token}`}
}).catch(err => console.error('CORS blocked:', err))
```

**Zaman:** 20 dakika

---

### Task 1.4: Seed Data'yı Production Guard'ı ile Sarıl

**Dosya:** `backend/app/main.py`

**Gerekli Değişiklikler:**

```python
# Eski
@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.seed_demo_data:  # ❌ Production'da true olabilir
        db = SessionLocal()
        try:
            seed_database(db)
        finally:
            db.close()
    bootstrap_agent_registry()
    yield

# Yeni
@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    
    # Guard: Production'da demo data'yı engelle
    if settings.seed_demo_data:
        if settings.is_production:
            logger.warning(
                "SECURITY WARNING: seed_demo_data=true in production! "
                "This exposes demo credentials. Disabling seed."
            )
            settings.seed_demo_data = False
        else:
            db = SessionLocal()
            try:
                seed_database(db)
                logger.info("Demo database seeded for development")
            finally:
                db.close()
    
    bootstrap_agent_registry()
    yield
```

**Zaman:** 15 dakika

---

### Task 1.5: Webhook Signature Validation Zorunlu Yap

**Dosya:** `backend/app/core/config.py`

```python
class Settings(BaseSettings):
    # ...
    clinical_webhook_signature_required: bool = False  # ❌ Production'da True olmalı
    
    @field_validator("clinical_webhook_signature_required")
    @classmethod
    def validate_webhook_security(cls, value: bool, info) -> bool:
        """Production'da webhook signature validation zorunlu."""
        if info.context.get("is_production") and not value:
            raise ValueError(
                "clinical_webhook_signature_required must be True in production. "
                "Set it in .env: CLINICAL_WEBHOOK_SIGNATURE_REQUIRED=true"
            )
        return value
```

**Zaman:** 15 dakika

---

## 🟠 PHASE 2: YÜKSEK SEVİYE (Gün 2-3)

### Task 2.1: Database Connection Pool Optimize Et

**Dosya:** `backend/app/db/session.py`

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

from app.core.config import get_settings

settings = get_settings()

# Pool configuration
if settings.database_url.startswith("sqlite"):
    # SQLite uses single connection
    engine_kwargs = {
        "future": True,
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
else:
    # PostgreSQL/MySQL - proper pooling
    engine_kwargs = {
        "future": True,
        "poolclass": QueuePool,
        "pool_size": 20,           # Temel bağlantı sayısı
        "max_overflow": 40,        # Ek bağlantılar
        "pool_recycle": 3600,      # 1 saat sonra yenile (connection timeout)
        "pool_pre_ping": True,     # Bağlantı sağlığını kontrol et
        "echo_pool": settings.environment == "development",
    }

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
```

**Zaman:** 30 dakika

---

### Task 2.2: Rate Limiting'i Tüm API Endpoints'e Ekle

**Dosya:** `backend/app/api/routes/chat.py` (ve diğerleri)

```python
from fastapi import APIRouter, Depends, Request
from app.core.rate_limit import limiter

router = APIRouter(prefix="/chat", tags=["chat"])

@router.get("/sessions")
@limiter.limit("100/minute")  # ✓ Eklendi
def get_sessions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # ...

@router.post("/sessions")
@limiter.limit("30/minute")  # Yazma işlemleri daha sıkı
def create_chat_session(...):
    # ...

@router.get("/sessions/{session_id}")
@limiter.limit("100/minute")
def get_chat_session(...):
    # ...

@router.post("/sessions/{session_id}/messages")
@limiter.limit("30/minute")  # Zaten var
def send_message(...):
    # ...
```

**Diğer Routes'lara da ekle:**
- `appointments.py`: `GET /appointments` (100/min), `POST /appointments` (30/min)
- `users.py`: `GET /users` (100/min)
- `auth.py`: `POST /login` (10/minute - brute force prevent), `POST /register` (5/minute)

**Zaman:** 1 saat

---

### Task 2.3: Input Validation Pydantic Schemas Ekle

**Dosya:** `backend/app/schemas/` (yeni dosyalar)

```python
# backend/app/schemas/validation.py
from pydantic import BaseModel, Field, validator
import re

class CompanyOutreachRequest(BaseModel):
    """Harici şirket iletişim talebini validate et."""
    company_name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Şirket adı"
    )
    location: str = Field(
        ...,
        min_length=2,
        max_length=50,
        description="İçinde bulunduğu şehir"
    )
    purpose: str = Field(
        ...,
        min_length=5,
        max_length=200,
        description="İletişim amacı"
    )
    
    @validator("company_name")
    def validate_company_name(cls, v):
        # SQL injection / XSS karakterlerini kontrol et
        if re.search(r"[<>\"';()&\\|`]", v):
            raise ValueError("Company name contains invalid characters")
        return v.strip()
    
    @validator("location")
    def validate_location(cls, v):
        if re.search(r"[<>\"';()&\\|`]", v):
            raise ValueError("Location contains invalid characters")
        return v.strip()
    
    @validator("purpose")
    def validate_purpose(cls, v):
        if re.search(r"[<>\"';()&\\|]", v):
            raise ValueError("Purpose contains invalid characters")
        # ReDoS saldırısını önle - regex matching length limit
        if len(v) > 200:
            raise ValueError("Purpose too long")
        return v.strip()

# backend/app/agent/orchestrator.py'de kullan
from app.schemas.validation import CompanyOutreachRequest

def extract_outreach_terms(text: str) -> dict | None:
    # ... extract logic ...
    
    # Validation ekle
    try:
        validated = CompanyOutreachRequest(
            company_name=company[:100],
            location=location[:50] if location else "Türkiye",
            purpose=purpose[:200] if purpose else "görüşme"
        )
        return {
            "company": validated.company_name,
            "location": validated.location,
            "purpose": validated.purpose,
            "search_query": f"{validated.company_name} {validated.location}".strip(),
        }
    except ValueError as e:
        logger.warning(f"Invalid outreach terms: {e}")
        return None
```

**Zaman:** 1 saat

---

### Task 2.4: Structured Logging'i Implement Et

**Dosya:** `backend/app/core/observability.py`

```python
import json
import logging
import time
from contextvars import ContextVar
from typing import Any

import structlog
from pythonjsonlogger import jsonlogger

# Context variable - her request'in unique ID'si
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
user_id_var: ContextVar[int | None] = ContextVar("user_id", default=None)

def setup_structlog():
    """Structured logging'i JSON formatında configure et."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

def get_logger(name: str = __name__):
    """Structured logger al."""
    logger = structlog.get_logger(name)
    return logger

# main.py'ye middleware ekle
from fastapi import Request
from app.core.observability import request_id_var, user_id_var, get_logger

logger = get_logger(__name__)

@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    """Her request'i structured log'la."""
    start_time = time.time()
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request_id_var.set(request_id)
    
    # User ID'yi auth'tan al (varsa)
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        user_id_var.set(user_id)
    
    try:
        response = await call_next(request)
    except Exception as exc:
        duration = time.time() - start_time
        logger.error(
            "request_failed",
            method=request.method,
            path=request.url.path,
            status_code=500,
            duration_ms=duration * 1000,
            exception=str(exc),
            exc_info=True,
        )
        raise
    
    duration = time.time() - start_time
    logger.info(
        "request_completed",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration * 1000,
    )
    
    response.headers["X-Request-ID"] = request_id
    return response
```

**Zaman:** 1 saat

---

## 🟡 PHASE 3: ORTA SEVİYE (Gün 4)

### Task 3.1: Secrets Management Hazırlığı

**.env.example şablonu oluştur:**

```bash
# .env.example
# ============================================
# SECURITY: Bu dosyayı .env olarak kopyala ve değerleri doldur
# UYARI: .env dosyasını repo'ya commit etme!
# ============================================

# Application
ENVIRONMENT=development
APP_NAME=Cognivault AI
API_PREFIX=/api

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/cognivault
# SQLite (dev için)
# DATABASE_URL=sqlite:///./cognivault.db

# JWT (Üretim için: python -c "import secrets; print(secrets.token_urlsafe(32))")
JWT_SECRET=change-me-in-production-min-32-chars-required
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=720

# External APIs
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4.1-mini
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-5

# Google Places (Intelligence)
GOOGLE_PLACES_API_KEY=AIzaSy...
INTELLIGENCE_EXTERNAL_ENABLED=false

# Meta/Whatsapp
META_ACCESS_TOKEN=EAA...
META_APP_SECRET=...
META_PHONE_NUMBER_ID=...
META_VERIFY_TOKEN=...

# Twilio
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_FROM=whatsapp:+...

# Email (Optional)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
SMTP_FROM=noreply@cognivault.local

# CORS
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173

# Security
SEED_DEMO_DATA=true  # Development'ta true, Production'ta false
CLINICAL_WEBHOOK_SIGNATURE_REQUIRED=false  # Production'ta true
```

**.gitignore'a ekle:**

```bash
echo ".env" >> .gitignore
echo ".env.local" >> .gitignore
echo ".env.production" >> .gitignore
echo "*.key" >> .gitignore
echo "*.pem" >> .gitignore
```

**Zaman:** 30 dakika

---

### Task 3.2: N+1 Query'leri Scan Et

**Dosya:** `backend/app/api/routes/chat.py`

```python
# Eski (N+1 problemi)
def get_sessions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sessions = list_sessions(db, current_user)  # ❌ N queries
    for session in sessions:
        _ = session.messages  # ❌ Her session için +1 query

# Yeni (Eager loading)
from sqlalchemy.orm import selectinload, joinedload

def get_sessions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sessions = db.scalars(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id)
        .options(selectinload(ChatSession.messages))  # ✓ 1 query!
    ).all()
    return sessions
```

**Zaman:** 2 saat (scanning + fixing)

---

## ✅ VERIFICATION CHECKLIST

Tüm değişiklikleri yaptıktan sonra kontrol et:

```bash
# 1. Dependencies yüklü mü?
pip install passlib[bcrypt]==1.7.4
pip install python-json-logger

# 2. Backend başlıyor mu?
cd backend
uvicorn app.main:app --reload

# 3. Security tests geçiyor mu?
python -m pytest app/tests/test_security.py -v

# 4. Login çalışıyor mu?
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "ayse@cognivault.com",
    "password": "demo123"
  }'

# 5. CORS kontrol
# Browser'da aç: localhost:5173
# DevTools → Network → yeni istek başlat
# Headers'ı kontrol et: Access-Control-Allow-Methods

# 6. Rate limit kontrol
for i in {1..35}; do
  curl -s http://localhost:8000/api/chat/sessions \
    -H "Authorization: Bearer $TOKEN" | grep -q "too many" && echo "Rate limited!"
done

# 7. Log output kontrol
# tail -f backend/logs/app.log | jq '.'  (JSON format olmalı)

# 8. Production simulation
ENVIRONMENT=production JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(32))") \
  python -c "from app.main import app; print('✓ Production startup successful')"
```

---

## 📅 TIMELINE

| Gün | Phase | Saat | Görevler |
|-----|-------|------|----------|
| 1 | 1.1-1.2 | 2 | Password hashing + JWT validation |
| 1 | 1.3-1.5 | 1.5 | CORS, Seed data, Webhooks |
| 2 | 2.1-2.2 | 2 | Database pool, Rate limiting |
| 2-3 | 2.3-2.4 | 2.5 | Input validation, Logging |
| 4 | 3.1-3.2 | 2.5 | Secrets management, N+1 queries |
| 5 | Testing & Deploy | 3 | QA, staging, production deploy |

**Toplam:** ~22 saat

---

## 🎯 DEPLOYMENT CHECKLIST

Production dağıtmadan önce:

- [ ] Bcrypt password hashing açık ve test edildi
- [ ] JWT_SECRET 32+ karakterdir ve production'da gizli
- [ ] CORS whitelist'e alındı
- [ ] Seed data disabled
- [ ] Webhook signature validation enabled
- [ ] Database pool configured
- [ ] Rate limiting aktif
- [ ] Input validation Pydantic'yle
- [ ] Structured logging JSON format'ında
- [ ] Secrets .env'ye alındı
- [ ] N+1 queries düzeltildi
- [ ] Tüm tests geçiyor
- [ ] HTTPS/TLS enabled
- [ ] Backups configured
- [ ] Monitoring alerts setup

---

## 📞 NOTLAR

- Her task'i ayrı branch'te yap: `git checkout -b feat/bcrypt-hashing`
- Commit mesajları: `git commit -m "SECURITY: Replace SHA256 with bcrypt for password hashing"`
- PR'ları review et review etmeden merge etme
- Production'a merge etmeden staging'de test et

---

**Prompt Hazırlayan:** Claude AI  
**Tarih:** 25 Mayıs 2026
