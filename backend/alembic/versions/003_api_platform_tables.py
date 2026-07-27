"""add api platform tables

Revision ID: 003
Revises: 002
Create Date: 2024-01-03
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(64), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False, server_default="free"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("requests_today", sa.Integer(), server_default="0"),
        sa.Column("requests_total", sa.BigInteger(), server_default="0"),
        sa.Column("quota_daily", sa.Integer(), server_default="1000"),
        sa.Column("bandwidth_bytes", sa.BigInteger(), server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ip", sa.String(45), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_api_key_key", "api_keys", ["key"], unique=True)
    op.create_index("idx_api_key_user", "api_keys", ["user_id"])
    op.create_index("idx_api_key_tier", "api_keys", ["tier"])

    op.create_table(
        "api_request_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("api_key_id", sa.Integer(), nullable=True),
        sa.Column("api_key_str", sa.String(64), nullable=True),
        sa.Column("endpoint", sa.String(255), nullable=False),
        sa.Column("method", sa.String(10), nullable=False, server_default="GET"),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response_time_ms", sa.Float(), nullable=True),
        sa.Column("response_bytes", sa.Integer(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("query_params", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_api_log_key", "api_request_logs", ["api_key_id"])
    op.create_index("idx_api_log_endpoint", "api_request_logs", ["endpoint"])
    op.create_index("idx_api_log_created", "api_request_logs", ["created_at"])
    op.create_index("idx_api_log_status", "api_request_logs", ["status_code"])

    op.create_table(
        "api_usage_daily",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("api_key_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.String(10), nullable=False),
        sa.Column("requests", sa.Integer(), server_default="0"),
        sa.Column("bandwidth_bytes", sa.BigInteger(), server_default="0"),
        sa.Column("errors", sa.Integer(), server_default="0"),
        sa.Column("avg_response_ms", sa.Float(), server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_api_usage_key_date", "api_usage_daily", ["api_key_id", "date"], unique=True)


def downgrade() -> None:
    op.drop_table("api_usage_daily")
    op.drop_table("api_request_logs")
    op.drop_table("api_keys")
