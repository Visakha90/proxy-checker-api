"""initial migration

Revision ID: 001
Revises:
Create Date: 2024-01-01

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "proxy_sources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("url", sa.String(1024), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("proxy_type", sa.String(10), nullable=False, server_default="http"),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("last_scraped", sa.DateTime(timezone=True), nullable=True),
        sa.Column("proxy_count", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "proxies",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ip", sa.String(45), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("proxy_type", sa.String(10), nullable=False, server_default="http"),
        sa.Column("source_url", sa.String(1024), nullable=True),
        sa.Column("is_alive", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("latency", sa.Float(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("country_code", sa.String(5), nullable=True),
        sa.Column("isp", sa.String(255), nullable=True),
        sa.Column("anonymity_level", sa.String(20), nullable=True),
        sa.Column("ssl_support", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("fail_count", sa.Integer(), server_default="0"),
        sa.Column("check_count", sa.Integer(), server_default="0"),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_checked", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_proxy_ip_port", "proxies", ["ip", "port"], unique=True)
    op.create_index("idx_proxy_type", "proxies", ["proxy_type"])
    op.create_index("idx_proxy_alive", "proxies", ["is_alive"])
    op.create_index("idx_proxy_country", "proxies", ["country"])
    op.create_index("idx_proxy_anonymity", "proxies", ["anonymity_level"])

    op.create_table(
        "check_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("proxy_id", sa.Integer(), sa.ForeignKey("proxies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_alive", sa.Boolean(), nullable=False),
        sa.Column("latency", sa.Float(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "statistics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("total_proxies", sa.Integer(), server_default="0"),
        sa.Column("alive_proxies", sa.Integer(), server_default="0"),
        sa.Column("dead_proxies", sa.Integer(), server_default="0"),
        sa.Column("http_count", sa.Integer(), server_default="0"),
        sa.Column("https_count", sa.Integer(), server_default="0"),
        sa.Column("socks4_count", sa.Integer(), server_default="0"),
        sa.Column("socks5_count", sa.Integer(), server_default="0"),
        sa.Column("elite_count", sa.Integer(), server_default="0"),
        sa.Column("anonymous_count", sa.Integer(), server_default="0"),
        sa.Column("transparent_count", sa.Integer(), server_default="0"),
        sa.Column("avg_latency", sa.Float(), server_default="0.0"),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "download_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("file_type", sa.String(20), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("key", sa.String(100), unique=True, nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
    op.drop_table("download_logs")
    op.drop_table("statistics")
    op.drop_table("check_history")
    op.drop_table("proxies")
    op.drop_table("proxy_sources")
