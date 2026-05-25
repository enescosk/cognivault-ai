"""SQLAlchemy engine + session yapılandırması.

Dialect'e göre farklı pool stratejisi:

- SQLite (dev): `StaticPool` ile tek bağlantı paylaşımlı tutulur. Test ve
  geliştirme için yeterli; `check_same_thread=False` async sürdürüleme uyumlu.
- PostgreSQL (prod): `QueuePool` ile bağlantılar önceden açılır + yeniden
  kullanılır. Saatlik geri dönüşüm (recycle) idle bağlantıların DB tarafında
  kapatılmasına karşı koruma sağlar. `pool_pre_ping=True` başlamadan önce
  bağlantıyı doğrular (yarı kapalı socket'ler temizlenir).
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

from app.core.config import get_settings


settings = get_settings()

engine_kwargs: dict = {"future": True}

if settings.database_url.startswith("sqlite"):
    # In-memory SQLite (`sqlite:///:memory:`) tek bağlantıyı paylaşmak ZORUNDA —
    # her thread yeni bağlantı açarsa şema kaybolur.
    engine_kwargs["connect_args"] = {"check_same_thread": False}
    if ":memory:" in settings.database_url:
        engine_kwargs["poolclass"] = StaticPool
else:
    # PostgreSQL / MySQL — production pool. Trafik için tunable:
    # pool_size: idle-zamanda hazır bağlantı sayısı
    # max_overflow: pool dolduğunda açılabilecek ek bağlantı
    # pool_recycle: saniye cinsinden bağlantı ömrü (3600 = 1 saat)
    # pool_pre_ping: SELECT 1 ile sağlık kontrolü (yarı-kapalı socket koruması)
    engine_kwargs.update(
        poolclass=QueuePool,
        pool_size=20,
        max_overflow=40,
        pool_recycle=3600,
        pool_pre_ping=True,
        pool_timeout=30,
    )

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
