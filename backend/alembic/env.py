"""
Alembic environment.

CRITICAL: This module deliberately bypasses Alembic's ConfigParser for the
database URL. ConfigParser performs %-interpolation, which corrupts
URL-encoded passwords (e.g. "%40" for "@" raises
ValueError: invalid interpolation syntax).

Instead we build the engine directly from the single shared configuration
source: app.core.config.Settings (which reads DATABASE_URL from the
environment). This guarantees Alembic and FastAPI always use the identical
connection string.
"""

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_settings  # noqa: E402
from app.core.database import Base  # noqa: E402

# Import all models so Base.metadata is fully populated
from app.models.models import (  # noqa: E402,F401
    Proxy, ProxySource, CheckHistory, Statistics, DownloadLog, AppSettings
)
from app.models.dns_models import DNSAuditLog, DNSRollbackSnapshot  # noqa: E402,F401
from app.models.api_models import APIKey, APIRequestLog, APIUsageDaily  # noqa: E402,F401
from app.models.user_models import (  # noqa: E402,F401
    User, Webhook, ScheduledExport, ProxyUptime, ProxyChain
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# SINGLE SOURCE OF TRUTH for the database URL.
# Never written back into the Alembic ConfigParser (avoids % interpolation).
DATABASE_URL = get_settings().database_url


def run_migrations_offline() -> None:
    """Generate SQL without connecting."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create the engine directly from DATABASE_URL, bypassing ConfigParser."""
    connectable = create_async_engine(DATABASE_URL, poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
