FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# postgresql-client: yedekleme/geri-yükleme (pg_dump / pg_restore) aynı imajdan
# koşuyor — `app.ops.backup` bu ikilileri PATH'te arar ve bulamazsa yedek almayı
# reddeder. Prod'da "yedeğimiz var" cümlesi buna bağlı, opsiyonel değil.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
# Migration'lar imajda OLMAK ZORUNDA: production'da şema uygulama başlangıcında
# değil, açık `alembic upgrade head` ile değişir (bkz. app/db/bootstrap.py).
# Bunlar kopyalanmazsa migrate adımı konteynerde hiç koşamaz.
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

# Root olmayan kullanıcı. data/ uygulama tarafından yazılır (yedekler, ses
# önbelleği), o yüzden sahipliği devrediyoruz.
RUN useradd --create-home --uid 10001 cognivault \
    && mkdir -p /app/data \
    && chown -R cognivault:cognivault /app
USER cognivault

EXPOSE 8000

# curl kurmak yerine zaten var olan Python ile: /readyz DB'ye ulaşamazsa 503
# döner (bkz. app/main.py), urlopen da HTTPError fırlatır → konteyner unhealthy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=4).status == 200 else 1)"

# Worker sayısı ortamdan ayarlanabilir; klinik on-prem kutusu genelde 2-4 çekirdek.
ENV UVICORN_WORKERS=2
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS}"]
