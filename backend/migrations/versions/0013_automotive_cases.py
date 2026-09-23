"""Persistent owner-scoped automotive operations rehearsal."""
from alembic import op
import sqlalchemy as sa

revision = '0013_automotive_cases'
down_revision = '0012_clinic_channel_bindings'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('automotive_cases',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('organization_id', sa.Integer(), sa.ForeignKey('organizations.id'), nullable=True),
        sa.Column('request_key', sa.String(80), nullable=False),
        sa.Column('team_slot', sa.String(80), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('owner_id', 'request_key', name='uq_automotive_case_request'),
        sa.UniqueConstraint('owner_id', 'team_slot', name='uq_automotive_active_team'))
    op.create_index('ix_automotive_cases_owner_id', 'automotive_cases', ['owner_id'])
    op.create_index('ix_automotive_cases_organization_id', 'automotive_cases', ['organization_id'])


def downgrade():
    op.drop_index('ix_automotive_cases_organization_id', 'automotive_cases')
    op.drop_index('ix_automotive_cases_owner_id', 'automotive_cases')
    op.drop_table('automotive_cases')
