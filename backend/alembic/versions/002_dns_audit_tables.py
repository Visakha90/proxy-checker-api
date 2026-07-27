"""add dns audit and rollback tables

Revision ID: 002
Revises: 001
Create Date: 2024-01-02

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dns_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("record_type", sa.String(10), nullable=True),
        sa.Column("record_id", sa.Integer(), nullable=True),
        sa.Column("host", sa.String(255), nullable=True),
        sa.Column("before_state", sa.Text(), nullable=True),
        sa.Column("after_state", sa.Text(), nullable=True),
        sa.Column("operator", sa.String(100), nullable=False, server_default="system"),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_dns_audit_domain", "dns_audit_logs", ["domain"])
    op.create_index("idx_dns_audit_action", "dns_audit_logs", ["action"])
    op.create_index("idx_dns_audit_operator", "dns_audit_logs", ["operator"])
    op.create_index("idx_dns_audit_created", "dns_audit_logs", ["created_at"])

    op.create_table(
        "dns_rollback_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("batch_id", sa.String(64), nullable=False),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("record_id", sa.Integer(), nullable=True),
        sa.Column("previous_state", sa.Text(), nullable=True),
        sa.Column("new_state", sa.Text(), nullable=True),
        sa.Column("rolled_back", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_dns_rollback_domain", "dns_rollback_snapshots", ["domain"])
    op.create_index("idx_dns_rollback_batch", "dns_rollback_snapshots", ["batch_id"])


def downgrade() -> None:
    op.drop_table("dns_rollback_snapshots")
    op.drop_table("dns_audit_logs")
