"""Yol yardımı hattı: müşteri arama anahtarı + mesaj kayıtları.

1. `automotive_cases.contact_key` — arayan ya da WhatsApp'tan yazan müşterinin
   mesajı hangi işe ait? Numara iş kaydının JSON'unda duruyor, ama JSON içinde
   arama sahibin TÜM işlerini (kapanmışlar dahil) yüklemek demek. Anahtar,
   numaranın sha256 özetidir: sabit uzunlukta, indekslenebilir, ham numarayı
   indekse koymaz.

2. `automotive_messages` — müşteriye ve ekibe giden/gelen her mesaj. İş
   kaydının JSON'undan AYRI durur: teslim durumu (kabul/iletildi/okundu/
   başarısız) sağlayıcıdan sonradan gelir ve iş kaydını güncelleseydi
   operatörün eşzamanlı işlemiyle yarışırdı (sürüm çakışması ya da kayıp
   güncelleme). Mesaj satırları yalnız eklenir ve kendi durumlarını taşır.
"""
from alembic import op
import sqlalchemy as sa

revision = '0014_automotive_roadside'
down_revision = '0013_automotive_cases'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('automotive_cases', sa.Column('contact_key', sa.String(64), nullable=True))
    op.create_index('ix_automotive_cases_owner_contact', 'automotive_cases', ['owner_id', 'contact_key'])

    op.create_table('automotive_messages',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('case_id', sa.String(36), sa.ForeignKey('automotive_cases.id'), nullable=False),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('direction', sa.String(8), nullable=False),
        sa.Column('audience', sa.String(40), nullable=False),
        sa.Column('purpose', sa.String(40), nullable=False),
        sa.Column('form', sa.String(20), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('delivery_status', sa.String(24), nullable=False),
        sa.Column('provider_message_id', sa.String(128), nullable=True),
        sa.Column('outbox_event_id', sa.Integer(), nullable=True),
        sa.Column('error', sa.String(300), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('provider_message_id', name='uq_automotive_message_provider'))
    op.create_index('ix_automotive_messages_case_id', 'automotive_messages', ['case_id'])
    op.create_index('ix_automotive_messages_owner_id', 'automotive_messages', ['owner_id'])


def downgrade():
    op.drop_index('ix_automotive_messages_owner_id', 'automotive_messages')
    op.drop_index('ix_automotive_messages_case_id', 'automotive_messages')
    op.drop_table('automotive_messages')
    op.drop_index('ix_automotive_cases_owner_contact', 'automotive_cases')
    op.drop_column('automotive_cases', 'contact_key')
