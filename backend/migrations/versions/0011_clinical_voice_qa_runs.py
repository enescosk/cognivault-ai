"""Add real-device voice QA run records.

Revision ID: 0011_clinical_voice_qa_runs
Revises: 0010_clinical_appointment_doctor_slot
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_clinical_voice_qa_runs"
down_revision: Union[str, None] = "0010_clinical_appointment_doctor_slot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clinical_voice_qa_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clinic_id", sa.Integer(), nullable=False),
        sa.Column("tester", sa.String(length=120), nullable=False),
        sa.Column("device", sa.String(length=80), nullable=False),
        sa.Column("browser", sa.String(length=80), nullable=False),
        sa.Column("audio_condition", sa.String(length=120), nullable=False),
        sa.Column("voice_mode", sa.String(length=40), nullable=False),
        sa.Column("scenario", sa.String(length=80), nullable=False),
        sa.Column("mic_permission_seconds", sa.Float(), nullable=True),
        sa.Column("first_assistant_audio_seconds", sa.Float(), nullable=True),
        sa.Column("transcript_correct", sa.Boolean(), nullable=False),
        sa.Column("transcript_shown", sa.Boolean(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("completed_under_60s", sa.Boolean(), nullable=False),
        sa.Column("appointment_created", sa.Boolean(), nullable=False),
        sa.Column("operator_intervention", sa.Boolean(), nullable=False),
        sa.Column("emergency_guidance_shown", sa.Boolean(), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_clinical_voice_qa_runs_clinic_id"),
        "clinical_voice_qa_runs",
        ["clinic_id"],
        unique=False,
    )
    op.create_index(
        "ix_clinical_voice_qa_runs_clinic_created",
        "clinical_voice_qa_runs",
        ["clinic_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_clinical_voice_qa_runs_clinic_created", table_name="clinical_voice_qa_runs")
    op.drop_index(op.f("ix_clinical_voice_qa_runs_clinic_id"), table_name="clinical_voice_qa_runs")
    op.drop_table("clinical_voice_qa_runs")
