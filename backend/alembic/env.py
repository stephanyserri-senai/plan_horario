import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.core.db import Base
import app.models  # noqa: F401

config = context.config
from app.core.config import normalizar_url_banco

# Migrações devem usar conexão DIRETA ou o pooler em modo sessão (porta 5432),
# nunca o pooler em modo transação (6543). Ver SUPABASE.md.
url = normalizar_url_banco(os.environ.get("ALEMBIC_DATABASE_URL") or get_settings().database_url_migracoes
                           or get_settings().database_url)
config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
