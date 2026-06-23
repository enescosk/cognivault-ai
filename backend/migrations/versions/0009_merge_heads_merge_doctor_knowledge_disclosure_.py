"""merge doctor_knowledge_disclosure + clinical_model_feedback heads

Revision ID: 0009_merge_heads
Revises: 0005_doctor_knowledge_disclosure, 0008_clinical_model_feedback
Create Date: 2026-06-23 22:16:34.011311

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009_merge_heads'
down_revision: Union[str, None] = ('0005_doctor_knowledge_disclosure', '0008_clinical_model_feedback')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
