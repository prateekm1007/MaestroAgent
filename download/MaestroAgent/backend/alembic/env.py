"""Alembic environment configuration.

Reads DATABASE_URL from the environment (not from alembic.ini) and
uses the SQLAlchemy models from maestro_db.models as the migration target.

Supports both SQLite (dev) and PostgreSQL (production).
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool, create_engine
from sqlalchemy.engine.url import make_url

from alembic import context

import os
import sys

# Ensure the backend directory is on the path so we can import maestro_db
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import the models so Alembic can autogenerate migrations
from maestro_db.base import Base
from maestro_db import models  # noqa: F401 — registers all models with Base.metadata

target_metadata = Base.metadata

# Set the database URL from the environment (not from alembic.ini)
db_url = os.environ.get("DATABASE_URL", "sqlite:///maestro.db")
# Normalize file: prefix to sqlite:///
if db_url.startswith("file:"):
    db_url = f"sqlite:///{db_url.replace('file:', '')}"
config.set_main_option("sqlalchemy.url", db_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    url = config.get_main_option("sqlalchemy.url")
    parsed = make_url(url)
    is_sqlite = parsed.drivername.startswith("sqlite")

    if is_sqlite:
        connectable = create_engine(
            url,
            poolclass=pool.NullPool,
            connect_args={"check_same_thread": False},
        )
    else:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
