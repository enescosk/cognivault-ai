"""Add clinic doctor/slot references to clinical appointments.

ORM'de ClinicalAppointment.doctor_id (clinic_doctors) ve slot_id
(clinic_doctor_slots) vardı ama hiçbir migration bu kolonları eklemiyordu;
create_all ile doğan dev DB'lerde sessizce çalışıp `alembic upgrade head`
ile yönetilen kurulumlarda ilk sorguda patlıyordu.

Revision ID: 0010_clinical_appointment_doctor_slot
Revises: 0009_merge_heads
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_clinical_appointment_doctor_slot"
down_revision: Union[str, None] = "0009_merge_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("clinical_appointments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("doctor_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("slot_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_clinical_appointments_doctor_id_clinic_doctors",
            "clinic_doctors",
            ["doctor_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_clinical_appointments_slot_id_clinic_doctor_slots",
            "clinic_doctor_slots",
            ["slot_id"],
            ["id"],
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_appointments_doctor_id"),
            ["doctor_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_clinical_appointments_slot_id"),
            ["slot_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("clinical_appointments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_clinical_appointments_slot_id"))
        batch_op.drop_index(batch_op.f("ix_clinical_appointments_doctor_id"))
        batch_op.drop_constraint(
            "fk_clinical_appointments_slot_id_clinic_doctor_slots",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_clinical_appointments_doctor_id_clinic_doctors",
            type_="foreignkey",
        )
        batch_op.drop_column("slot_id")
        batch_op.drop_column("doctor_id")
