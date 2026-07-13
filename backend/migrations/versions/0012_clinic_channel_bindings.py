"""Channel address → clinic binding for multi-tenant webhook routing.

Telefon/WhatsApp webhook'ları bugüne kadar her mesajı default kliniğe
yazıyordu; ikinci klinik bağlandığı anda veriler karışırdı. Bu tablo aranan
numarayı / Meta phone_number_id'sini kliniğe bağlar.

Revision ID: 0012_clinic_channel_bindings
Revises: 0011_clinical_voice_qa_runs
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_clinic_channel_bindings"
down_revision: Union[str, None] = "0011_clinical_voice_qa_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clinic_channel_bindings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clinic_id", sa.Integer(), nullable=False),
        sa.Column(
            "channel",
            sa.Enum("WHATSAPP", "WEB_CHAT", "PHONE", "MANUAL", name="clinicchannel"),
            nullable=False,
        ),
        sa.Column("address", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"]),
        sa.UniqueConstraint("channel", "address", name="uq_channel_binding_address"),
    )
    op.create_index(
        op.f("ix_clinic_channel_bindings_clinic_id"),
        "clinic_channel_bindings",
        ["clinic_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_clinic_channel_bindings_address"),
        "clinic_channel_bindings",
        ["address"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_clinic_channel_bindings_address"), table_name="clinic_channel_bindings")
    op.drop_index(op.f("ix_clinic_channel_bindings_clinic_id"), table_name="clinic_channel_bindings")
    op.drop_table("clinic_channel_bindings")
