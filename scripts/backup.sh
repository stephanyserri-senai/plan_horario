#!/usr/bin/env bash
# Backup lógico do banco (formato custom, compactado).
# Uso: DATABASE_URL=postgresql://plan:plan@localhost/plan_horario scripts/backup.sh [diretorio]
# Restauração: pg_restore --clean --if-exists -d "$DATABASE_URL" arquivo.dump
set -euo pipefail
DESTINO="${1:-backups}"
mkdir -p "$DESTINO"
ARQ="$DESTINO/plan_horario_$(date +%Y%m%d_%H%M%S).dump"
pg_dump --format=custom --no-owner "${DATABASE_URL:?defina DATABASE_URL}" -f "$ARQ"
echo "Backup gravado em $ARQ"
