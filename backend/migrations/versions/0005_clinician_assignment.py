"""Link login users to doctors and assign shadow reviews.

Revision ID: 0005_clinician_assignment
Revises: 2077a27151c3
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_clinician_assignment"
down_revision: Union[str, None] = "2077a27151c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("doctors", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_doctors_user_id_users", "users", ["user_id"], ["id"])
        batch_op.create_index(batch_op.f("ix_doctors_user_id"), ["user_id"], unique=True)

    with op.batch_alter_table("shadow_reviews", schema=None) as batch_op:
        batch_op.add_column(sa.Column("assigned_doctor_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_shadow_reviews_assigned_doctor_id_doctors",
            "doctors",
            ["assigned_doctor_id"],
            ["id"],
        )
        batch_op.create_index(
            batch_op.f("ix_shadow_reviews_assigned_doctor_id"),
            ["assigned_doctor_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("shadow_reviews", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_shadow_reviews_assigned_doctor_id"))
        batch_op.drop_constraint("fk_shadow_reviews_assigned_doctor_id_doctors", type_="foreignkey")
        batch_op.drop_column("assigned_doctor_id")

    with op.batch_alter_table("doctors", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_doctors_user_id"))
        batch_op.drop_constraint("fk_doctors_user_id_users", type_="foreignkey")
        batch_op.drop_column("user_id")
