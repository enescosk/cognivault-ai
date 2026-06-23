"""Add privacy-gated clinical model feedback records.

Revision ID: 0008_clinical_model_feedback
Revises: 0007_clinical_calendar_procedures
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_clinical_model_feedback"
down_revision: Union[str, None] = "0007_clinical_calendar_procedures"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clinical_model_feedback",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("clinic_id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("review_id", sa.Integer(), nullable=False),
        sa.Column("patient_message_id", sa.Integer(), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.String(length=24), nullable=False),
        sa.Column("original_reply", sa.Text(), nullable=False),
        sa.Column("corrected_reply", sa.Text(), nullable=True),
        sa.Column("mismatch_json", sa.JSON(), nullable=False),
        sa.Column("training_status", sa.String(length=32), server_default="pending_redaction", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["clinic_id"], ["clinics.id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["clinic_conversations.id"]),
        sa.ForeignKeyConstraint(["review_id"], ["shadow_reviews.id"]),
        sa.ForeignKeyConstraint(["patient_message_id"], ["clinic_messages.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_id", name="uq_clinical_model_feedback_review"),
    )
    for column in ("clinic_id", "conversation_id", "review_id", "patient_message_id", "reviewed_by_user_id", "outcome", "training_status"):
        op.create_index(op.f(f"ix_clinical_model_feedback_{column}"), "clinical_model_feedback", [column], unique=False)


def downgrade() -> None:
    op.drop_table("clinical_model_feedback")
