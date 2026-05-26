"""clinical slot offers

Revision ID: 0003_clinical_slot_offers
Revises: 0002_postgres_rls
Create Date: 2026-05-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_clinical_slot_offers"
down_revision: Union[str, None] = "0002_postgres_rls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clinical_slot_offers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clinic_id", sa.Integer(), nullable=False),
        sa.Column("patient_id", sa.Integer(), nullable=True),
        sa.Column("conversation_id", sa.Integer(), nullable=True),
        sa.Column("branch_id", sa.Integer(), nullable=True),
        sa.Column("department", sa.String(length=140), nullable=False),
        sa.Column("physician_name", sa.String(length=160), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Enum("OFFERED", "HELD", "CONSUMED", "EXPIRED", "CANCELLED", name="clinicalslotofferstatus"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["branch_id"], ["clinic_branches.id"]),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["clinic_conversations.id"]),
        sa.ForeignKeyConstraint(["patient_id"], ["clinic_patients.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("clinical_slot_offers", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_clinical_slot_offers_clinic_id"), ["clinic_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_clinical_slot_offers_conversation_id"), ["conversation_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_clinical_slot_offers_expires_at"), ["expires_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_clinical_slot_offers_patient_id"), ["patient_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_clinical_slot_offers_starts_at"), ["starts_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_clinical_slot_offers_status"), ["status"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("clinical_slot_offers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_clinical_slot_offers_status"))
        batch_op.drop_index(batch_op.f("ix_clinical_slot_offers_starts_at"))
        batch_op.drop_index(batch_op.f("ix_clinical_slot_offers_patient_id"))
        batch_op.drop_index(batch_op.f("ix_clinical_slot_offers_expires_at"))
        batch_op.drop_index(batch_op.f("ix_clinical_slot_offers_conversation_id"))
        batch_op.drop_index(batch_op.f("ix_clinical_slot_offers_clinic_id"))
    op.drop_table("clinical_slot_offers")
