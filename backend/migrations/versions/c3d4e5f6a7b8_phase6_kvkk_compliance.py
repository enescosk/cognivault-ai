"""Phase 6: KVKK compliance — consent records, retention timestamps, LLM usage telemetry.

Bu migration:
  - `consent_records` tablosunu ekler (KVKK Md. 5/6 açık rıza kaydı)
  - `clinic_patients.data_expires_at` ve `clinic_conversations.data_expires_at`
    kolonlarını ekler (KVKK Md. 7 retention politikası)
  - `llm_usage_records` tablosunu ekler (Faz 6 maliyet takibi)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── consent_records ────────────────────────────────────────────────────
    consent_type_enum = sa.Enum(
        "voice_recording",
        "data_processing",
        "cross_border_transfer",
        "insurance_lookup",
        name="consenttype",
    )
    clinic_channel_enum = sa.Enum(
        "whatsapp",
        "phone",
        "web",
        "form",
        name="clinicchannel",
        create_type=False,  # initial migration zaten yaratmış
    )

    op.create_table(
        "consent_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clinic_id", sa.Integer(), sa.ForeignKey("clinics.id"), nullable=False),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("clinic_patients.id"), nullable=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("clinic_conversations.id"), nullable=True),
        sa.Column("consent_type", consent_type_enum, nullable=False),
        sa.Column("granted", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("channel", clinic_channel_enum, nullable=True),
        sa.Column("ip_or_device_hint", sa.String(length=120), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consent_text_version", sa.String(length=32), nullable=False),
    )
    with op.batch_alter_table("consent_records", schema=None) as batch_op:
        batch_op.create_index("ix_consent_records_clinic_id", ["clinic_id"])
        batch_op.create_index("ix_consent_records_patient_id", ["patient_id"])
        batch_op.create_index("ix_consent_records_conversation_id", ["conversation_id"])
        batch_op.create_index("ix_consent_records_consent_type", ["consent_type"])

    # ── data_expires_at kolonları (KVKK Md. 7 retention) ──────────────────
    with op.batch_alter_table("clinic_patients", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("data_expires_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_index("ix_clinic_patients_data_expires_at", ["data_expires_at"])

    with op.batch_alter_table("clinic_conversations", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("data_expires_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_index("ix_clinic_conversations_data_expires_at", ["data_expires_at"])

    # ── llm_usage_records ──────────────────────────────────────────────────
    op.create_table(
        "llm_usage_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("agent_type", sa.String(length=60), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    with op.batch_alter_table("llm_usage_records", schema=None) as batch_op:
        batch_op.create_index("ix_llm_usage_records_provider", ["provider"])
        batch_op.create_index("ix_llm_usage_records_model", ["model"])
        batch_op.create_index("ix_llm_usage_records_agent_type", ["agent_type"])
        batch_op.create_index("ix_llm_usage_records_organization_id", ["organization_id"])
        batch_op.create_index("ix_llm_usage_records_user_id", ["user_id"])
        batch_op.create_index("ix_llm_usage_records_request_id", ["request_id"])
        batch_op.create_index("ix_llm_usage_records_created_at", ["created_at"])


def downgrade() -> None:
    op.drop_table("llm_usage_records")

    with op.batch_alter_table("clinic_conversations", schema=None) as batch_op:
        batch_op.drop_index("ix_clinic_conversations_data_expires_at")
        batch_op.drop_column("data_expires_at")

    with op.batch_alter_table("clinic_patients", schema=None) as batch_op:
        batch_op.drop_index("ix_clinic_patients_data_expires_at")
        batch_op.drop_column("data_expires_at")

    op.drop_table("consent_records")
    sa.Enum(name="consenttype").drop(op.get_bind(), checkfirst=False)
