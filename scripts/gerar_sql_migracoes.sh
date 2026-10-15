#!/usr/bin/env bash
# Gera o SQL completo das migrações (Alembic offline) para revisão ou para
# aplicar manualmente no SQL Editor do Supabase. O Alembic continua sendo a
# fonte da verdade; regenere este arquivo sempre que criar uma migração.
set -euo pipefail
cd "$(dirname "$0")/../backend"
ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade head --sql > sql/schema_completo.sql
echo "Gerado backend/sql/schema_completo.sql"
# Atualização incremental para bancos que já estão na 0002 (ex.: homologação no Supabase)
{
  echo "-- Atualização 0002 -> 0003: unidades Beira Mar e Porto, áreas tecnológicas, turnos oficiais e área nos cadastros."
  echo "-- Não destrutiva: só cria a tabela de áreas, adiciona colunas anuláveis e insere o que ainda não existir."
  echo "-- Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run."
  ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade 0002:0003 --sql
} > sql/atualizacao_0003.sql
echo "Gerado backend/sql/atualizacao_0003.sql"
{
  echo "-- Atualização 0003 -> 0004: exceção justificada para regras acadêmicas (instrutor/laboratório de outra área, sem competência)."
  echo "-- Não destrutiva. Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run."
  ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade 0003:0004 --sql
} > sql/atualizacao_0004.sql
echo "Gerado backend/sql/atualizacao_0004.sql"
{
  echo "-- Atualização 0004 -> 0005: portal do instrutor (perfil instrutor, vínculo usuário × instrutor, observações e notificações) e substituição de instrutor nas aulas."
  echo "-- Não destrutiva. Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run."
  ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade 0004:0005 --sql
} > sql/atualizacao_0005.sql
echo "Gerado backend/sql/atualizacao_0005.sql"
{
  echo "-- Atualização 0005 -> 0006: turno da noite das 18:30 às 22:00 (aulas noturnas já programadas e disponibilidades são deslocadas 10 min)."
  echo "-- Não destrutiva e só age se a noite ainda estiver em 18:20–21:50. Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run."
  ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade 0005:0006 --sql
} > sql/atualizacao_0006.sql
echo "Gerado backend/sql/atualizacao_0006.sql"
{
  echo "-- Atualização 0006 -> 0007: modalidade do instrutor (mensalista ou horista). Os turnos de planejamento (PL) e projeto (PJ) usam a tabela de bloqueios."
  echo "-- Não destrutiva (todos os instrutores começam como mensalista). Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run."
  ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade 0006:0007 --sql
} > sql/atualizacao_0007.sql
echo "Gerado backend/sql/atualizacao_0007.sql"
