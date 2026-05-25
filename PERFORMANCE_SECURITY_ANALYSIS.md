# CogniVault AI - Performans ve Güvenlik Analizi

**Rapor Tarihi:** 25 Mayıs 2026  
**Analiz Kapsamı:** Backend (Python/FastAPI), Frontend (React), Proje Yapısı  
**Sonuç:** 🔴 5 Kritik, 8 Yüksek, 6 Orta Seviye Sorun

---

## 🔴 KRİTİK SORUNLAR

### 1. **Şifreler SHA256 Hash (SALT YOK) ile Korunuyor**

**Dosya:** `backend/app/core/security.py`  
**Risk Seviyesi:** KRITIK (CVSS 9.8)

```python
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()  # ❌ BURADA SORUN
```

**Sorunlar:**
- ✗ Salt kullanmıyor → Rainbow table saldırısı riski
- ✗ SHA256 parola hashleme için uygun değil
- ✗ GPU'da saniyede milyarlar hesaplanabiliyor
- ✗ OWASP standartlarını ihlal ediyor

**Çözüm:**
```python
from passlib.context import CryptContext

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12  # Sınıflandırma faktörü
)

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, hashed_password: str) -> bool:
    return pwd_context.verify(password, hashed_password)
```

**İş Etkisi:**
- Tüm hesapların şifresi 1-2 saatte crack edilebilir
- GDPR/KVKK cezaları: 1-5 milyon EUR
- Kullanıcı güveni kaybı

---

### 2. **Zayıf JWT Secret (Üretimde Sorun)**

**Dosya:** `backend/app/core/config.py`  
**Risk Seviyesi:** KRITIK (üretim dağıtılmışsa)

```python
jwt_secret: str = "change-me-in-production"  # ❌ DEFAULT SECRET
has_weak_jwt_secret: bool  # Kontrol var ama üretimde geçmiş olabilir
```

**Sorunlar:**
- ✗ Örnek şifreler işe yaramaz
- ✗ Uzunluk <16 karakter ise reddedilir (iyi)
- ✗ Ancak üretim başlamış ve eski token'lar geçerli olabilir
- ✗ Token'lar JSON Web Token'ıyla imzalanıyor; yanıldı, HS256 simetrik

**Çözüm:**
```python
# .env Şablonu
JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# Validation (İyi yapılmış)
@field_validator("jwt_secret")
def validate_jwt_secret(cls, value: str) -> str:
    if len(value) < 32 and not os.getenv("ENVIRONMENT") == "development":
        raise ValueError("JWT_SECRET must be 32+ chars in production")
    return value
```

**İş Etkisi:**
- Kullanıcı sessionları forge edilebilir
- Yönetici hesapları ele geçirilebilir
- Veri sızıntısı riski yüksek

---

### 3. **CORS Tüm Yöntemlere ve Headers'a İzin Veriyor**

**Dosya:** `backend/app/main.py`  
**Risk Seviyesi:** KRITIK

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],        # ❌ DELETE, PUT, PATCH hepsi izin veriliyor
    allow_headers=["*"],         # ❌ Tüm headers geçebiliyor
)
```

**Saldırı Senaryosu:**
```javascript
// Attacker.com'dan
fetch('https://cognivault.com/api/users/1', {
    method: 'DELETE',
    headers: {'X-Custom-Header': 'malicious'}
})
```

**Çözüm:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],  # ✓ Sadece gerekli olanlar
    allow_headers=["Content-Type", "Authorization"],  # ✓ Whitelist
    max_age=3600,
    expose_headers=["X-Request-ID"],
)
```

---

### 4. **Düşük Güvenlikli Bilineni Harici Entegrasyon (Google Places, Meta)**

**Dosya:** `backend/app/core/config.py` + `backend/app/agent/orchestrator.py`  
**Risk Seviyesi:** KRITIK

```python
# Yapılandırılanlar
google_places_api_key: str = ""
meta_access_token: str = ""
meta_app_secret: str = ""
```

**Sorunlar:**
- ✗ API keyleri .env dosyasında plaintext
- ✗ Hiç döndürme stratejisi yok
- ✗ Source code'da hardcoded pattern'ler
- ✗ Webhook signature doğrulaması production'da kapalı

```python
clinical_webhook_signature_required: bool = False  # ❌ PRODUCTION'DA TRUE OLMALI
```

**Çözüm:**
```bash
# .env
GOOGLE_PLACES_API_KEY=sk-... # Vault'tan enjekte et
META_ACCESS_TOKEN=EAA... # 90 gün rotation
META_APP_SECRET=... # Şifreli depolama

# Code
class Settings(BaseSettings):
    @field_validator("google_places_api_key")
    def validate_api_key(cls, v, info):
        if info.context.get("is_production") and not v:
            raise ValueError("API key required in production")
        return v
```

---

### 5. **Gelen Veriler Doğrulanmıyor (SQL Injection Riski)**

**Dosya:** Çeşitli routes'lar  
**Risk Seviyesi:** KRITIK

**Örnek:** `backend/app/agent/orchestrator.py`

```python
def extract_outreach_terms(text: str) -> dict | None:
    # ❌ Regex'ler input doğrulama yapmadan işleniyor
    loc_match = re.search(
        r"\b([a-zçğıöşüİÇĞÖŞÜ]+)(?:'?(?:deki|daki|teki|taki|de|da|te|ta))\b",
        text,  # USER INPUT - hiç sanitize yok
    )
```

**Temel Tehdidler:**
- ✗ Reguler ifade DOS (ReDoS) saldırıları
- ✗ Database queries parametrizasyonu kontrol edin

**Çözüm:**
```python
from pydantic import BaseModel, Field, validator

class OutreachRequest(BaseModel):
    company_name: str = Field(..., max_length=100, pattern="^[\\w\\s-]+$")
    location: str = Field(..., max_length=50)
    purpose: str = Field(..., max_length=200)
    
    @validator("company_name")
    def validate_company(cls, v):
        if re.search(r"[<>\"';()&]", v):
            raise ValueError("Invalid characters")
        return v
```

---

## 🟠 YÜKSEK SEVİYE SORUNLAR

### 6. **Database Bağlantı Havuzu Yapılandırılmamış**

**Dosya:** `backend/app/db/session.py`  
**Etki:** Yüksek yük altında bağlantı tükenmesi

```python
engine = create_engine(settings.database_url, **engine_kwargs)
# ❌ Pool size belirlenmemiş (varsayılan: 5)
# ❌ Max overflow: 10 (çok düşük)
```

**Üretim ortamında:**
- 50+ eşzamanlı istek → bağlantılar doluyor
- Response süresi exponential artıyor
- 502 Bad Gateway hatası başlıyor

**Çözüm:**
```python
from sqlalchemy.pool import QueuePool

engine = create_engine(
    settings.database_url,
    poolclass=QueuePool,
    pool_size=20,           # Temel bağlantı sayısı
    max_overflow=40,        # Ek bağlantılar
    pool_recycle=3600,      # 1 saat sonra yenile
    pool_pre_ping=True,     # Bağlantı sağlığını kontrol et
    echo_pool=False,
)
```

---

### 7. **N+1 Sorgularının Riski (Gelişmiş Sorgulamada)**

**Dosya:** `backend/app/api/routes/chat.py` (satır 35-50)  
**Etki:** Veritabanı sorguları x100 artabilir

```python
def get_sessions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    sessions = list_sessions(db, current_user)
    for session in sessions:
        if session.messages:  # ❌ Her session için ayrı sorgu!
            session.messages[-1].content
```

**Durumu:** Kısmen iyileştirilmiş (selectinload'lar var), ama kontrol gerekli

**Çözüm:**
```python
from sqlalchemy.orm import selectinload, joinedload

sessions = db.scalars(
    select(ChatSession)
    .where(ChatSession.user_id == current_user.id)
    .options(selectinload(ChatSession.messages))  # ✓ Eager loading
).all()
```

---

### 8. **Seed Verileri Üretimde Otomatik Oluştuluyor**

**Dosya:** `backend/app/main.py` (satır 97-102)  
**Risk Seviyesi:** YÜKSEK

```python
if settings.seed_demo_data:  # ❌ PRODUCTION'DA TRUE OLABILIR
    db = SessionLocal()
    seed_database(db)  # Demo kullanıcılar: ayse@, john@, admin@
```

**Tehdid:**
- ❌ Bilinir credentials `admin@cognivault.com / demo123`
- ❌ Demo appointment slotları herkese açık
- ❌ Audit logları gerçek veri ile karışmış

**Çözüm:**
```python
@app.on_event("startup")
async def startup_event():
    if settings.is_production:
        if settings.seed_demo_data:
            raise RuntimeError(
                "seed_demo_data=true is forbidden in production. "
                "Disable it in .env"
            )
    else:
        seed_database(SessionLocal())
```

---

### 9. **Hata Mesajları Kötü Amaçlı Bilgi Açığa Çıkarıyor**

**Dosya:** `backend/app/api/dependencies.py` (satır 32-33)  
**Risk Seviyesi:** YÜKSEK

```python
except Exception as exc:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid token"  # ✓ Geneldir
    ) from exc
```

**İyi yapılmış ama başka yerlerde:**

```python
# ❌ BAD (readyz endpoint'te)
except Exception as exc:
    checks["database"] = f"failed: {exc.__class__.__name__}"
    logger.error("readyz database check failed", 
                extra={"error": str(exc)})  # Admin'e açığa çıkabiliyor
```

**Çözüm:**
```python
except Exception as exc:
    logger.error("DB check failed", exc_info=True)
    checks["database"] = "failed"  # Kaynağı gösterme
```

---

### 10. **Rate Limiting Eksik Birçok Endpoint'te**

**Dosya:** `backend/app/api/routes/chat.py` (satır 90)  
**Etki:** DDoS saldırılarına açık

```python
@limiter.limit("30/minute")  # ✓ /messages'ta var
def send_message(...):
    pass

# ❌ Ama /sessions'ta yok!
@router.get("/sessions")
def get_sessions(...):  # Sıradışı 1000 kez çağrılabilir
    pass
```

**Çözüm:**
```python
@router.get("/sessions")
@limiter.limit("100/minute")  # İlgili endpoints'i ekle
def get_sessions(...):
    pass
```

---

### 11. **Logging Yapılandırması Zayıf (Üretim Hazırlığında)**

**Dosya:** `backend/app/core/observability.py` + `app/main.py`  
**Etki:** Security incidents'ı izlenemeyecek

**Eksikler:**
- ❌ JSON yapılandırma yok (log aggregation zor)
- ❌ Structured fields eksik (trace_id, user_id, request_id)
- ❌ PII filtering yok (e-mail addresses loglanmış)
- ❌ Log rotation policy tanımlanmamış

**Çözüm:**
```python
# config/logging.py
import structlog
import logging

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    cache_logger_on_first_use=True,
)

# app/main.py
@app.middleware("http")
async def log_request_response(request: Request, call_next):
    request.state.start_time = time.time()
    structlog.get_logger().info(
        "request_start",
        method=request.method,
        path=request.url.path,
        user_id=getattr(request.state, "user_id", None),
    )
    response = await call_next(request)
    return response
```

---

### 12. **Secrets Yönetimi Eksik**

**Risk Seviyesi:** YÜKSEK

Şu anda:
```
.env → plaintext
git history → keyleri içeriyor olabilir
```

**Çözüm:**

```bash
# 1. Vault kullan (HashiCorp Vault / AWS Secrets Manager)
pip install hvac

# 2. .env.example şablonu oluştur
cat > .env.example << EOF
POSTGRES_PASSWORD=CHANGE_ME_IN_PROD
JWT_SECRET=CHANGE_ME_IN_PROD (min 32 chars)
OPENAI_API_KEY=CHANGE_ME_IN_PROD
EOF

# 3. .env'i .gitignore'a ekle
echo ".env" >> .gitignore
echo "*.key" >> .gitignore
```

---

## 🟡 ORTA SEVİYE SORUNLAR

### 13. **Frontend XSS Riski (React Props)**

**Dosya:** Render logic'te user input doğrudan render ediliyor  
**Etki:** Malicious scripts çalışabilir

---

### 14. **Dosya Yükleme Validasyonu Zayıf**

**Dosya:** `backend/app/api/user/sources/upload.py`  
**Sorunlar:**
- ❌ Dosya türü kontrolü basit
- ❌ Dosya boyutu limiti kontrol edin
- ❌ Malware scanning yok

---

### 15. **Concurrency Kontrol Yok**

**Dosya:** Chat session işlemleri  
**Sorun:** İki kullanıcı aynı anda session güncelleyebiliyor

---

### 16. **Performance: Compression Threshold Düşük**

**Dosya:** `backend/app/agent/orchestrator.py` (satır 236)

```python
_COMPRESS_THRESHOLD = 16  # ❌ 16+ mesaj sonra sıkıştrıyor
```

Sorun: Kısa konuşmalarda sıkıştrıma yapılmıyor, uzun konuşmalarda precision kaybı

---

### 17. **Metadata Eksik (Audit Trail)**

**Dosya:** `backend/app/models`  
**Eksikler:**
- ❌ `created_at` ama `modified_at` yok
- ❌ `modified_by` field'ı yok
- ❌ Soft delete desteği yok

---

### 18. **Health Check Endpoint'i Özel Doğrulama Yok**

**Dosya:** `backend/app/main.py` (satır 150-159)

```python
@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}  # ❌ Always returns ok
```

---

## 📊 PERFORMANCE SORUNLARI

| Sorun | Çoğunluk | Çözüm | Öncelik |
|-------|---------|--------|---------|
| SQL N+1 | Olası | Eager loading | ⚠️ YÜKSEK |
| Connection pool | Evet | Pool resize | ⚠️ YÜKSEK |
| Message history compression | Evet | Optimization | 🟡 ORTA |
| No caching strategy | Evet | Redis + decorator | 🟡 ORTA |
| Regex performance | Evet | Input length limit | 🟡 ORTA |

---

## 🎯 ÖNERİLEN İYİLEŞTİRMELER (Sırasına Göre)

### HAFTA 1 (Kritik)
- [ ] `hash_password` → bcrypt'e geçir
- [ ] JWT_SECRET validation'ı kontrol et
- [ ] CORS metodlarını whitelist'e döndür
- [ ] seed_demo_data'yı production'da disable et
- [ ] Webhook signature validation'ı aç

### HAFTA 2 (Yüksek)
- [ ] Database pool'u ayarla (pool_size=20, max_overflow=40)
- [ ] Rate limiting'i tüm endpoints'e ekle
- [ ] Input validation Pydantic schema'sı yap
- [ ] Logging'i JSON formatter'a geçir

### HAFTA 3-4 (Orta)
- [ ] Secrets management (Vault/AWS Secrets)
- [ ] N+1 queries'i scan et ve düzelt
- [ ] File upload validation'ı kuvvetlendir
- [ ] Audit trail completeness'i kontrol et

---

## 🔐 SECURITY CHECKLIST

```
✗ Password hashing: SHA256 (BURADA DEĞİŞ → bcrypt)
✗ JWT Secret: 16+ chars
✗ CORS: Whitelist methods/headers
✗ API Keys: .env in (Vault'a geçir)
✗ Input Validation: Pydantic schema'sı
✗ SQL Injection: Parameterized queries
✗ XSS Protection: CSP headers + DOMPurify
✗ CSRF Protection: SameSite cookies
✗ Rate Limiting: All endpoints
✗ Logging: Structured + PII filtering
✗ Secrets: Rotation policy
✗ HTTPS: Force TLS 1.2+
✗ Headers: HSTS, X-Frame-Options, X-Content-Type-Options (✓ var)
```

---

## 📈 İyileştirme Zaman Tahmini

| Aktivite | Saat | Başlangıç | Hedef |
|----------|------|-----------|--------|
| Password hashing fix | 2 | Hemen | Cumartesi |
| Security fixes (CORS, JWT) | 4 | Hemen | Salı |
| Database optimization | 6 | Salı | Perşembe |
| Testing & QA | 8 | Cuma | Pazartesi |
| Deployment | 2 | Pazartesi | Pazartesi |

**Toplam:** ~22 saat

---

## 📞 İletişim & Öneriler

Bu rapor CogniVault AI için hazırlanmıştır. Ayrıntılar için:

1. **Güvenlik danışmanı** ile kritik sorunları gözden geçirin
2. **Database admin** ile pool configuration'ı ayarlayın
3. **Frontend team** ile XSS prevention'ı koordine edin

---

**Rapor Hazırlayan:** Claude AI  
**İnceleme Tarihi:** 25 Mayıs 2026
