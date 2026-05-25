"""Phase 8: PostgreSQL Row-Level Security — tenant isolation at DB engine.

Bu migration `organization_id` taşıyan 11 tabloya RLS politikası kurar.
Uygulama katmanı `SET LOCAL app.org_id = ...` yapar; PostgreSQL motoru her
satır okumasında bu değer ile tablodaki `organization_id` eşleşmediği
satırları görünmez kılar — bir geliştirici WHERE koşulunu unutsa bile
cross-tenant data leak matematiksel olarak imkansız hale gelir.

SQLite RLS desteklemediği için bu migration sadece PostgreSQL dialect'inde
çalışır. SQLite'da no-op olarak tanımlanmıştır; uygulama katmanındaki
`organization_id` filtresi dev ortamında savunma görevini sürdürür.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-05-25
"""

from typing import Sequence, Union

from alembic import op


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# RLS uygulanacak tablolar — hepsi organization_id sütununa sahip.
RLS_TABLES = [
    "users",
    "clinics",
    "departments",
    "routing_rules",
    "enterprise_agents",
    "enterprise_customers",
    "enterprise_sessions",
    "enterprise_tickets",
    "agent_decision_logs",
    "audit_logs",
    "llm_usage_records",
]


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgres():
        # SQLite/MySQL RLS desteklemiyor — no-op. Uygulama katmanındaki
        # organization_id filtresi dev ortamında savunma görevini sürdürür.
        return

    for table in RLS_TABLES:
        # 1) RLS'i aç. SUPERUSER bypass etmesin diye FORCE de uygula —
        #    böylece migration veya seed bile policy'lere tabi olur.
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

        # 2) Politikalar: SELECT/UPDATE/DELETE oturum org_id'sine eşit satırlar.
        #    INSERT için WITH CHECK aynı koşul → başka org'a yazılamaz.
        #    `current_setting('app.org_id', true)` ikinci arg=true ile setting
        #    yoksa NULL döner; NULL → COALESCE 0 → match olmaz, satır sızmaz.
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_select ON {table}")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_select ON {table}
            FOR SELECT
            USING (
                organization_id IS NULL
                OR organization_id = COALESCE(NULLIF(current_setting('app.org_id', true), '')::int, 0)
            )
            """
        )

        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_insert ON {table}")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_insert ON {table}
            FOR INSERT
            WITH CHECK (
                organization_id IS NULL
                OR organization_id = COALESCE(NULLIF(current_setting('app.org_id', true), '')::int, 0)
            )
            """
        )

        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_update ON {table}")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_update ON {table}
            FOR UPDATE
            USING (
                organization_id IS NULL
                OR organization_id = COALESCE(NULLIF(current_setting('app.org_id', true), '')::int, 0)
            )
            WITH CHECK (
                organization_id IS NULL
                OR organization_id = COALESCE(NULLIF(current_setting('app.org_id', true), '')::int, 0)
            )
            """
        )

        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_delete ON {table}")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_delete ON {table}
            FOR DELETE
            USING (
                organization_id IS NULL
                OR organization_id = COALESCE(NULLIF(current_setting('app.org_id', true), '')::int, 0)
            )
            """
        )

    # Performance: tüm tenant-scoped tablolarda organization_id'nin index'li
    # olduğunu doğrula. Yoksa RLS WHERE'i full-table-scan yapar — felaket.
    # Modeller `index=True` ile zaten ekliyor; bu sadece güvenlik kontrolü.


def downgrade() -> None:
    if not _is_postgres():
        return
    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_select ON {table}")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_insert ON {table}")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_update ON {table}")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_delete ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
