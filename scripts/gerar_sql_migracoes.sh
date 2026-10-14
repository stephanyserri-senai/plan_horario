#!/usr/bin/env bash
# Gera o SQL completo das migrações (Alembic offline) para revisão ou para
# aplicar manualmente no SQL Editor do Supabase. O Alembic continua sendo a
# fonte da verdade; regenere este arquivo sempre que criar uma migração.
set -euo pipefail
cd "$(dirname "$0")/../backend"
ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade head --sql > sql/schema_completo.sql
echo "Gerado backend/sql/schema_completo.sql"
