"""Add professional calendar fields and appointment procedures.

Revision ID: 0007_clinical_calendar_procedures
Revises: 0006_clinician_appointments
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_clinical_calendar_procedures"
down_revision: Union[str, None] = "0006_clinician_appointments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("clinical_appointments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="30"))
        batch_op.add_column(sa.Column("visit_reason", sa.String(length=500), nullable=True))
        batch_op.create_index(
            "ix_clinical_appointments_doctor_starts_at",
            ["assigned_doctor_id", "starts_at"],
            unique=False,
        )

    op.create_table(
        "clinical_appointment_procedures",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clinic_id", sa.Integer(), nullable=False),
        sa.Column("appointment_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=240), nullable=False),
        sa.Column("code", sa.String(length=80), nullable=True),
        sa.Column("tooth", sa.String(length=40), nullable=True),
        sa.Column("status", sa.Enum("PLANNED", "IN_PROGRESS", "COMPLETED", "CANCELLED", name="clinicalprocedurestatus"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("performed_by_doctor_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["appointment_id"], ["clinical_appointments.id"]),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"]),
        sa.ForeignKeyConstraint(["performed_by_doctor_id"], ["doctors.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_clinical_appointment_procedures_appointment_id"),
        "clinical_appointment_procedures",
        ["appointment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_clinical_appointment_procedures_clinic_id"),
        "clinical_appointment_procedures",
        ["clinic_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_clinical_appointment_procedures_clinic_id"),
        table_name="clinical_appointment_procedures",
    )
    op.drop_index(
        op.f("ix_clinical_appointment_procedures_appointment_id"),
        table_name="clinical_appointment_procedures",
    )
    op.drop_table("clinical_appointment_procedures")

    with op.batch_alter_table("clinical_appointments", schema=None) as batch_op:
        batch_op.drop_index("ix_clinical_appointments_doctor_starts_at")
        batch_op.drop_column("visit_reason")
        batch_op.drop_column("duration_minutes")
        batch_op.drop_column("ends_at")
