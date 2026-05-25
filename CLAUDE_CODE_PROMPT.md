# CogniVault AI - Claude Code Agentic Prompt

## 🎯 MİSSİON

CogniVault AI projesinin güvenlik ve performans sorunlarını aşamalı olarak düzelt. Toplam 5 kritik + 8 yüksek seviye sorun var. Her aşamada test et, commit et, raporla.

---

## 📌 PROJE KONTEKSTİ

**Proje Yolu:** `/Users/ec/Desktop/cognivaultAi/`

**Teknoloji Stack:**
- Backend: Python 3.11+ / FastAPI / SQLAlchemy / PostgreSQL
- Frontend: React / TypeScript / Vite
- Database: SQLite (dev) / PostgreSQL (prod)
- Auth: JWT HS256 (SHA256 parolalar - SORUN!)

**Önceki Analiz:**
- `/Users/ec/Desktop/cognivaultAi/PERFORMANCE_SECURITY_ANALYSIS.md`
- `/Users/ec/Desktop/cognivaultAi/IMPLEMENTATION_PROMPT.md`

---

## 🔴 PHASE 1: KRİTİK GÜVENLIK (Priority: ASAP)

### TASK 1: SHA256 → Bcrypt'e Geçiş

**Hedef:** Password hashing'i bcrypt'e taşı, tüm testleri geç, eski parolaları migrate et.

**Dosyalar:**
- `backend/app/core/security.py` (yeniden yaz)
- `backend/requirements.txt` (passlib[bcrypt] ekle)
- `backend/app/tests/test_security.py` (yeni/güncelle)
- `backend/app/services/auth_service.py` (kontrol)

**Gereksinim:**
1. `passlib[bcrypt]` ekle requirements.txt'e
2. Hash function'ları bcrypt ile yeniden yaz
3. `iat` (issued at) claim'ini JWT'ye ekle
4. Secret validation strengthen et
5. Test yaz: hash consistency, timing attack resistance
6. Eski SHA256 parolaları kapsayan migration planlama (dokuma yeterli)

**Başarı Kriteri:**
```bash
✓ Security tests geçiyor
✓ Login çalışıyor
✓ Hash output'ları her zaman farklı (salt demosu)
✓ verify_password() doğru çalışıyor
✓ JWT'de iat ve exp var
```

**Aşamalar:**
1. `security.py` read → analiz
2. `test_security.py` oluştur (bcrypt testleri)
3. `security.py` rewrite (bcrypt impl)
4. `requirements.txt` update
5. Local test: `pytest app/tests/test_security.py -v`
6. Tüm auth endpoints'i test et
7. Commit: "security: replace SHA256 with bcrypt for password hashing"

---

### TASK 2: JWT Secret Validation (Production Guard)

**Hedef:** JWT_SECRET'i production'da zorunlu ve güçlü yap.

**Dosyalar:**
- `backend/app/core/config.py` (validator ekle)
- `backend/app/main.py` (startup check ekle)

**Gereksinim:**
1. `Settings.validate_jwt_secret()` yaz (Pydantic validator)
2. Production detection logic ekle
3. Zayıf secret'ı reddet (< 32 chars, bilinen values)
4. main.py'de startup check ekle
5. Error message'ı bilgilendirici yap

**Başarı Kriteri:**
```bash
✓ Development'ta: Zayıf secret çalışıyor (warning)
✓ Production simulation'da: Zayıf secret startup'ı blokluyor
✓ Error message'ı yardımcı (secret generate command'ı içeriyor)
```

**Aşamalar:**
1. `config.py`'i analiz et (environment detection)
2. Validator yaz
3. main.py'ye startup check ekle
4. Test: ENVIRONMENT=production başlat
5. Commit: "security: enforce strong JWT_SECRET in production"

---

### TASK 3: CORS Whitelist

**Hedef:** CORS'u güvenli whitelist'e döndür.

**Dosyalar:**
- `backend/app/main.py` (CORS middleware config)

**Gereksinim:**
1. `allow_methods=["*"]` → `["GET", "POST", "OPTIONS"]`
2. `allow_headers=["*"]` → `["Content-Type", "Authorization", "X-Request-ID"]`
3. `max_age=3600` ekle (preflight caching)
4. `expose_headers` belirle
5. Comment'ler ekle

**Başarı Kriteri:**
```bash
✓ GET /api/chat/sessions çalışıyor
✓ POST /api/chat/sessions çalışıyor
✓ DELETE /api/users/123 başarısız (CORS block)
✓ Browser DevTools → CORS headers doğru
```

**Aşamalar:**
1. main.py'deki CORS middleware'i bul
2. Konfigürasyon güncelle
3. Commit: "security: enforce CORS method and header whitelist"

---

### TASK 4: Seed Data Production Guard

**Hedef:** Production'da demo data oluşturma engelle.

**Dosyalar:**
- `backend/app/main.py` (lifespan context)

**Gereksinim:**
1. `if settings.seed_demo_data and settings.is_production` check ekle
2. Production'da seed'i disable et (warning log)
3. Development'ta normal seed çalışsın

**Başarı Kriteri:**
```bash
✓ Development: Demo data seeded
✓ Production simulation: Demo data skip (warning logged)
✓ Demo users (admin@cognivault.com) prod'da oluşturulmuyor
```

**Aşamalar:**
1. main.py'deki lifespan bölümünü analiz et
2. Guard logic ekle
3. Test: ENVIRONMENT=production
4. Commit: "security: disable demo data seed in production"

---

### TASK 5: Webhook Signature Validation

**Hedef:** Meta/Twilio webhook'ları production'da imza doğrulama zorla.

**Dosyalar:**
- `backend/app/core/config.py` (validator)
- `backend/app/api/routes/clinical.py` (validation logic)

**Gereksinim:**
1. `clinical_webhook_signature_required` production'da true olmalı (validator)
2. Webhook route'larında signature check yapısı var mı kontrol et
3. Validation eksikse, başlık ekle (full impl gerekli değil, yapı yeterli)

**Başarı Kriteri:**
```bash
✓ Production: Signature validation required
✓ Development: Optional (testing kolaylaşsın)
✓ Error message: "Invalid webhook signature"
```

**Aşamalar:**
1. config.py'de validator ekle
2. clinical.py'de signature check kodu tarayıcı (var mı?)
3. Eksikse, yapıyı göster (full impl için başka task)
4. Commit: "security: require webhook signature validation in production"

---

## 🟠 PHASE 2: YÜKSEK SEVİYE (Gün 2-3)

### TASK 6: Database Connection Pool

**Hedef:** SQLite/PostgreSQL pool'u optimize et.

**Dosyalar:**
- `backend/app/db/session.py`

**Gereksinim:**
1. SQLite: `StaticPool` kullan
2. PostgreSQL: `QueuePool` + pool_size=20 + max_overflow=40 + pool_recycle=3600 + pool_pre_ping=True
3. Environment'a göre farklı konfigürasyon

**Başarı Kriteri:**
```bash
✓ SQLite başlıyor
✓ PostgreSQL connection pool yapılandırılmış
✓ High concurrency testinde hata yok
```

**Aşamalar:**
1. session.py read
2. Pool config yazma
3. Local test
4. Commit: "perf: configure database connection pooling"

---

### TASK 7: Rate Limiting Tüm Endpoints'e

**Hedef:** API endpoints'ini rate limit'le.

**Dosyalar:**
- `backend/app/api/routes/*.py` (tüm routers)

**Gereksinim:**
1. Her GET endpoint: `@limiter.limit("100/minute")`
2. Her POST endpoint: `@limiter.limit("30/minute")`
3. Auth endpoint: `POST /login` ve `/register` → `10/minute` ve `5/minute`
4. zaten `/messages` endpoint'te var, diğerlerine ekle

**Dosyalar:**
- `chat.py`: Sessions (GET/POST), Messages (POST var)
- `appointments.py`: GET, POST
- `users.py`: GET
- `auth.py`: login, register
- `audit.py`: GET (read-only safe)
- `enterprise.py`: GET/POST
- `clinical.py`: POST (webhooks)

**Başarı Kriteri:**
```bash
✓ 100 istek/dakika → GET başarılı
✓ 101. istek → 429 Too Many Requests
✓ Login 11. denemede blok
```

**Aşamalar:**
1. Her route dosyasını tarayıcı
2. @limiter.limit decorators ekle
3. Auth endpoints'i daha sıkı limitle
4. Test: curl loop → 429 alın
5. Commit: "security: implement rate limiting on all endpoints"

---

### TASK 8: Input Validation (Pydantic Schemas)

**Hedef:** Harici çağrıları (Google Places, outreach) validate et.

**Dosyalar:**
- `backend/app/schemas/validation.py` (yeni dosya)
- `backend/app/agent/orchestrator.py` (integration)

**Gereksinim:**
1. `CompanyOutreachRequest` schema yaz:
   - company_name: max 100, no special chars
   - location: max 50, no special chars
   - purpose: max 200, no special chars
2. Regex validation ekle (< > " ' ; ( ) & \ | ` forbidden)
3. ReDoS saldırı prevent'i (length limit + regex compile timeout)
4. orchestrator.py'deki `extract_outreach_terms()` fonksiyonunu güncelle
5. Validation exception handling ekle

**Başarı Kriteri:**
```bash
✓ Valid input geçiyor
✓ SQL injection karakterleri reject
✓ XSS karakterleri reject
✓ Çok uzun input reject
```

**Aşamalar:**
1. validation.py oluştur
2. Schema'ları yaz
3. orchestrator.py'deki extract_outreach_terms() güncelle
4. Test: malicious input'lar
5. Commit: "security: add input validation for external requests"

---

### TASK 9: Structured Logging

**Hedef:** JSON structured logging'i implement et.

**Dosyalar:**
- `backend/app/core/observability.py` (güncelle)
- `backend/app/main.py` (middleware ekle)
- `backend/requirements.txt` (python-json-logger ekle)

**Gereksinim:**
1. `python-json-logger` ekle
2. Structlog configure et (JSON output)
3. RequestID middleware ekle (her request'i log'la)
4. Context variables (request_id, user_id)
5. PII filtering (email'leri maskelendir - optional)

**Başarı Kriteri:**
```bash
✓ Logs JSON format'ında
✓ Her log'ta: timestamp, level, message, request_id
✓ Error logs: exception traceback
✓ Performance: duration_ms field'ı
```

**Aşamalar:**
1. requirements.txt'e python-json-logger ekle
2. observability.py'yi güncelle
3. main.py'ye logging middleware ekle
4. Local test: tail -f logs | jq '.'
5. Commit: "ops: implement structured JSON logging"

---

## 🟡 PHASE 3: ORTA SEVİYE (Gün 4)

### TASK 10: Secrets Management (.env Template)

**Hedef:** Production-ready .env şablonu oluştur.

**Dosyalar:**
- `.env.example` (şablon)
- `.gitignore` (update)

**Gereksinim:**
1. `.env.example` oluştur (tüm variables'ın template version'ı)
2. .gitignore'a `.env`, `.env.local`, `*.key` ekle
3. Açıklayıcı comments ekle
4. Security warnings ekle

**Başarı Kriteri:**
```bash
✓ .env.example var
✓ .env .gitignore'da
✓ README'de: "cp .env.example .env" instruction
```

**Aşamalar:**
1. .env.example oluştur
2. .gitignore güncelle
3. Commit: "docs: add .env template and security guidelines"

---

### TASK 11: N+1 Queries Taraması

**Hedef:** Eager loading'i verify et ve optimize et.

**Dosyalar:**
- `backend/app/services/chat_service.py`
- `backend/app/api/routes/chat.py`
- Diğer services

**Gereksinim:**
1. list_sessions() tarayıcı → selectinload var mı?
2. get_session() → message loading eager mi?
3. Enterprise routes'ları tarayıcı
4. SQL query'leri debug mode'da gözlemle
5. N+1 problem varsa, selectinload() ekle

**Başarı Kriteri:**
```bash
✓ 10 session yüklemesi = 1-2 query (not 11)
✓ Messages = eager loaded
✓ SQLAlchemy logger: sql echo test
```

**Aşamalar:**
1. chat_service.py'de list_sessions() bak
2. selectinload yoksa, ekle
3. get_session() messages'ı eager load'lu mu kontrol
4. SQL debug: `echo=True` ile test
5. Commit: "perf: optimize N+1 queries with eager loading"

---

## ✅ VERIFICATION & TESTING

Tüm task'lardan sonra:

```bash
# 1. Dependencies
pip install -r backend/requirements.txt

# 2. Backend startup
cd backend
uvicorn app.main:app --reload

# 3. Security tests
python -m pytest app/tests/test_security.py -v

# 4. Full test suite
python -m pytest app/tests/ -v --cov

# 5. Production simulation
ENVIRONMENT=production \
JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(32))") \
  python -c "from app.main import app; from app.core.config import get_settings; print(f'✓ Startup OK, JWT length: {len(get_settings().jwt_secret)}')"

# 6. Manual API test
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "ayse@cognivault.com", "password": "demo123"}' \
  | jq '.'

# 7. Rate limit test
for i in {1..35}; do
  curl -s http://localhost:8000/api/chat/sessions \
    -H "Authorization: Bearer $TOKEN" 
done | tail -5

# 8. CORS test
# Browser: localhost:5173 → Network → OPTIONS isteğini kontrol et

# 9. Log format test
tail -20 backend/logs/*.log | jq '.'

# 10. Git history
git log --oneline -10
```

---

## 📋 COMMIT TEMPLATE

```
git commit -m "TYPE: Brief description

- What was changed
- Why it was changed
- Security/performance impact

Files: path/to/file.py"
```

**Types:**
- `security`: Güvenlik sorunu fix
- `perf`: Performance improvement
- `refactor`: Code cleanup
- `test`: Test ekle/güncelle
- `docs`: Documentation
- `ops`: DevOps/infrastructure

---

## 🎯 CLAUDE CODE EXECUTION

Claude Code ile şu şekilde çalış:

```bash
# Start
claude code /Users/ec/Desktop/cognivaultAi

# Her task'ı ayrı branch'te yap
git checkout -b feat/task-name

# Task tamamlama:
# 1. Files oku/yaz
# 2. Tests oluştur
# 3. Local test et
# 4. Commit et
# 5. Raporla (ne yaptın, ne test ettim, git hash)

# Task bitince:
git log -1 --stat
```

---

## 🚨 KRITIK NOTLAR

1. **Backup al:** Başlamadan önce `git commit` veya zip
2. **Main'i commit etme:** Feature branches kullan
3. **Incremental test:** Her task'tan sonra test et
4. **Frontend'i restart:** Backend değişirse, yarn dev'i restart et
5. **Database migration:** Eski parolaları bcrypt'e convert etme (dokuma yeterli)

---

## 📊 PROGRESS TRACKING

```
PHASE 1 - CRITICAL SECURITY
- [ ] TASK 1: SHA256 → Bcrypt
- [ ] TASK 2: JWT Secret Validation
- [ ] TASK 3: CORS Whitelist
- [ ] TASK 4: Seed Data Guard
- [ ] TASK 5: Webhook Validation

PHASE 2 - HIGH PRIORITY
- [ ] TASK 6: DB Connection Pool
- [ ] TASK 7: Rate Limiting
- [ ] TASK 8: Input Validation
- [ ] TASK 9: Structured Logging

PHASE 3 - MEDIUM PRIORITY
- [ ] TASK 10: .env Template
- [ ] TASK 11: N+1 Queries

TESTING & DEPLOYMENT
- [ ] All tests passing
- [ ] Production simulation OK
- [ ] Security checklist ✓
- [ ] Ready to deploy
```

---

## 📞 Q&A

**"Hangi version Python kullanmalı?"**  
→ Python 3.11+ (project kullanıyor)

**"Database'i reset etmeliyim?"**  
→ Hayır, SQLite fixture'ları local dev'de otomatik oluşuluyor

**"Frontend'i değişmeli mi?"**  
→ Hayır, backend-only changes. Frontend testleri sadece CORS kontrol

**"Production'a deploy ederim?"**  
→ PHASE 1 tamamlandıktan sonra, test ortamına önce

---

**Prompt Hazırlayan:** Claude AI  
**Last Updated:** 25 Mayıs 2026  
**Project:** CogniVault AI Security & Performance Hardening
