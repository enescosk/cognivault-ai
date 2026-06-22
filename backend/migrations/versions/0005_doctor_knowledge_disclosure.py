"""0005_doctor_knowledge_disclosure

ORM ile migration arasındaki şema farkını kapatır. Aşağıdaki tablolar
modellerde tanımlıydı ama hiçbir migration'da yaratılmıyordu:

  - clinic_doctors
  - clinic_doctor_slots  (clinic_doctors'a FK)
  - knowledge_articles
  - kvkk_disclosure_versions

Tablolar ORM metadata'sından birebir üretilir; böylece kolon/constraint
tanımları model ile %100 uyumlu kalır (schema-parity testi bunu doğrular).

Revision ID: 0005_doctor_knowledge_disclosure
Revises: 2077a27151c3
Create Date: 2026-06-22
"""
from typing import Sequence, Union

from alembic import op

from app.db.base import Base
import app.models  # noqa: F401 — tüm ORM modellerini metadata'ya kaydeder


# revision identifiers, used by Alembic.
revision: str = "0005_doctor_knowledge_disclosure"
down_revision: Union[str, None] = "2077a27151c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# FK bağımlılık sırası: clinic_doctors → clinic_doctor_slots
_TABLES = [
    "clinic_doctors",
    "clinic_doctor_slots",
    "knowledge_articles",
    "kvkk_disclosure_versions",
]


def upgrade() -> None:
    bind = op.get_bind()
    metadata = Base.metadata
    for name in _TABLES:
        metadata.tables[name].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    metadata = Base.metadata
    for name in reversed(_TABLES):
        metadata.tables[name].drop(bind=bind, checkfirst=True)
