"""phase1: tenant-scope columns + inbound idempotency

Revision ID: a1b2c3d4e5f6
Revises: ff0507ce5844
Create Date: 2026-05-19 14:00:00

Adds nullable `organization_id` to `users`, `clinics`, and `audit_logs`,
a nullable `clinic_id` and `request_id` to `audit_logs`, and a new
`inbound_events` table for webhook idempotency. All columns are nullable so
existing rows continue to work without backfill; the seed routine wires the
default clinic to the default organization on next startup.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'ff0507ce5844'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('organization_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_users_organization_id'), ['organization_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_users_organization_id_organizations',
            'organizations',
            ['organization_id'],
            ['id'],
        )

    with op.batch_alter_table('clinics', schema=None) as batch_op:
        batch_op.add_column(sa.Column('organization_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_clinics_organization_id'), ['organization_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_clinics_organization_id_organizations',
            'organizations',
            ['organization_id'],
            ['id'],
        )

    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('organization_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('clinic_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('request_id', sa.String(length=64), nullable=True))
        batch_op.create_index(batch_op.f('ix_audit_logs_organization_id'), ['organization_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_clinic_id'), ['clinic_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_audit_logs_request_id'), ['request_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_audit_logs_organization_id_organizations',
            'organizations',
            ['organization_id'],
            ['id'],
        )
        batch_op.create_foreign_key(
            'fk_audit_logs_clinic_id_clinics',
            'clinics',
            ['clinic_id'],
            ['id'],
        )

    op.create_table(
        'inbound_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('clinic_id', sa.Integer(), nullable=True),
        sa.Column('provider', sa.String(length=40), nullable=False),
        sa.Column('external_id', sa.String(length=160), nullable=False),
        sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('payload_json', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['clinic_id'], ['clinics.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider', 'external_id', name='uq_inbound_events_provider_external'),
    )
    with op.batch_alter_table('inbound_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_inbound_events_clinic_id'), ['clinic_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_inbound_events_external_id'), ['external_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_inbound_events_provider'), ['provider'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('inbound_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_inbound_events_provider'))
        batch_op.drop_index(batch_op.f('ix_inbound_events_external_id'))
        batch_op.drop_index(batch_op.f('ix_inbound_events_clinic_id'))
    op.drop_table('inbound_events')

    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_audit_logs_clinic_id_clinics', type_='foreignkey')
        batch_op.drop_constraint('fk_audit_logs_organization_id_organizations', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_audit_logs_request_id'))
        batch_op.drop_index(batch_op.f('ix_audit_logs_clinic_id'))
        batch_op.drop_index(batch_op.f('ix_audit_logs_organization_id'))
        batch_op.drop_column('request_id')
        batch_op.drop_column('clinic_id')
        batch_op.drop_column('organization_id')

    with op.batch_alter_table('clinics', schema=None) as batch_op:
        batch_op.drop_constraint('fk_clinics_organization_id_organizations', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_clinics_organization_id'))
        batch_op.drop_column('organization_id')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('fk_users_organization_id_organizations', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_users_organization_id'))
        batch_op.drop_column('organization_id')
