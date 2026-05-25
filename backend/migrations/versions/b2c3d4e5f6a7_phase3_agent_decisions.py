"""phase3: agent_decision_logs table

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-19 15:00:00

Unifies AI and human-in-the-loop decisions into a single queryable table.
All foreign keys are nullable so the row can be partially populated when a
field is not relevant (e.g. a clinical decision has no chat_session_id).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'agent_decision_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('agent_type', sa.String(length=60), nullable=False),
        sa.Column('intent', sa.String(length=120), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('risk', sa.String(length=20), nullable=False),
        sa.Column('requires_human', sa.Boolean(), nullable=False),
        sa.Column('action', sa.String(length=120), nullable=True),
        sa.Column('reason', sa.String(length=255), nullable=True),
        sa.Column('organization_id', sa.Integer(), nullable=True),
        sa.Column('clinic_id', sa.Integer(), nullable=True),
        sa.Column('conversation_id', sa.Integer(), nullable=True),
        sa.Column('chat_session_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('payload_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id']),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinics.id']),
        sa.ForeignKeyConstraint(['conversation_id'], ['clinic_conversations.id']),
        sa.ForeignKeyConstraint(['chat_session_id'], ['chat_sessions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('agent_decision_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_agent_decision_logs_agent_type'), ['agent_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_decision_logs_intent'), ['intent'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_decision_logs_risk'), ['risk'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_decision_logs_requires_human'), ['requires_human'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_decision_logs_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_decision_logs_clinic_id'), ['clinic_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_decision_logs_conversation_id'), ['conversation_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_decision_logs_chat_session_id'), ['chat_session_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_decision_logs_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_agent_decision_logs_request_id'), ['request_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('agent_decision_logs', schema=None) as batch_op:
        for col in (
            'request_id', 'user_id', 'chat_session_id', 'conversation_id',
            'clinic_id', 'organization_id', 'requires_human', 'risk', 'intent', 'agent_type',
        ):
            batch_op.drop_index(batch_op.f(f'ix_agent_decision_logs_{col}'))
    op.drop_table('agent_decision_logs')
