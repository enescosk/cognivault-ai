"""Phase 9: Transactional Outbox + Billing tables.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-05-25
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Outbox ────────────────────────────────────────────────────────────
    outbox_status_enum = sa.Enum(
        "pending", "dispatched", "failed", "dead_letter",
        name="outboxeventstatus",
    )

    # ── Billing enums (Faz 12) ────────────────────────────────────────────
    plan_tier_enum = sa.Enum(
        "starter", "growth", "enterprise", "internal",
        name="billingplantier",
    )
    sub_status_enum = sa.Enum(
        "active", "past_due", "cancelled", "trial",
        name="subscriptionstatus",
    )

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("status", outbox_status_enum, nullable=False, server_default="pending"),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("clinic_id", sa.Integer(), sa.ForeignKey("clinics.id"), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    with op.batch_alter_table("outbox_events", schema=None) as batch_op:
        batch_op.create_index("ix_outbox_events_event_type", ["event_type"])
        batch_op.create_index("ix_outbox_events_status", ["status"])
        batch_op.create_index("ix_outbox_events_organization_id", ["organization_id"])
        batch_op.create_index("ix_outbox_events_clinic_id", ["clinic_id"])
        batch_op.create_index("ix_outbox_events_next_retry_at", ["next_retry_at"])
        batch_op.create_index("ix_outbox_events_created_at", ["created_at"])


    # ── Billing tables (Faz 12) ───────────────────────────────────────────
    op.create_table(
        "billing_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tier", plan_tier_enum, nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("monthly_price_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("max_conversations_per_month", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_voice_minutes_per_month", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_agents", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_llm_cost_usd_per_month", sa.Float(), nullable=False, server_default="0"),
        sa.Column("features_json", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    with op.batch_alter_table("billing_plans", schema=None) as batch_op:
        batch_op.create_index("ix_billing_plans_tier", ["tier"], unique=True)

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("billing_plans.id"), nullable=False),
        sa.Column("status", sub_status_enum, nullable=False, server_default="trial"),
        sa.Column("current_period_start", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_subscription_id", sa.String(length=120), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    with op.batch_alter_table("subscriptions", schema=None) as batch_op:
        batch_op.create_index("ix_subscriptions_organization_id", ["organization_id"])
        batch_op.create_index("ix_subscriptions_status", ["status"])

    op.create_table(
        "usage_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("metric_key", sa.String(length=60), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    with op.batch_alter_table("usage_records", schema=None) as batch_op:
        batch_op.create_index("ix_usage_records_organization_id", ["organization_id"])
        batch_op.create_index("ix_usage_records_metric_key", ["metric_key"])
        batch_op.create_index("ix_usage_records_period_start", ["period_start"])


def downgrade() -> None:
    op.drop_table("usage_records")
    op.drop_table("subscriptions")
    op.drop_table("billing_plans")
    op.drop_table("outbox_events")
    sa.Enum(name="outboxeventstatus").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="subscriptionstatus").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="billingplantier").drop(op.get_bind(), checkfirst=False)
