"""Add org_id to all tables for multi-tenant isolation.

Revision ID: f4_org_id_multi_tenant
Revises: 1a9f8707528a
Create Date: 2025-01-24

Round 52 Fix 4: Multi-tenant isolation. Adds org_id column to all 9
tables that were missing it, with a default of 'default' for backward
compatibility. Every query is now scoped by org_id.
"""
from alembic import op
import sqlalchemy as sa

revision = "f4_org_id_multi_tenant"
down_revision = "1a9f8707528a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tables that need org_id added
    tables = [
        "import_jobs",
        "import_checkpoints",
        "oauth_credentials",
        "provider_connections",
    ]

    for table in tables:
        # Add org_id column with default 'default' for existing rows
        op.add_column(table, sa.Column("org_id", sa.String(),
                                       nullable=False, server_default="default"))
        # Create index for efficient org-scoped queries
        op.create_index(f"ix_{table}_org_id", table, ["org_id"])

    # For oauth_credentials and provider_connections, the primary key
    # was previously just (provider). Now it needs to be (provider, org_id).
    # SQLite doesn't support ALTER TABLE DROP PRIMARY KEY, so we recreate.
    # For PostgreSQL, use raw SQL:
    op.execute("ALTER TABLE oauth_credentials DROP CONSTRAINT IF EXISTS oauth_credentials_pkey")
    op.execute("ALTER TABLE oauth_credentials ADD PRIMARY KEY (provider, org_id)")
    op.execute("ALTER TABLE provider_connections DROP CONSTRAINT IF EXISTS provider_connections_pkey")
    op.execute("ALTER TABLE provider_connections ADD PRIMARY KEY (provider, org_id)")


def downgrade() -> None:
    tables = [
        "import_jobs",
        "import_checkpoints",
        "oauth_credentials",
        "provider_connections",
    ]
    for table in reversed(tables):
        op.drop_index(f"ix_{table}_org_id", table_name=table)
        op.drop_column(table, "org_id")
