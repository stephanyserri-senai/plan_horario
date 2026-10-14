"""Preparação para Supabase/Vercel: vínculo com Supabase Auth, fila de jobs,
conteúdo da importação persistido, RLS e bloqueio da Data API.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-14

Migração NÃO destrutiva: apenas adiciona colunas anuláveis/índices, habilita
RLS e revoga privilégios dos papéis públicos do Supabase (anon/authenticated).
O backend acessa o banco com o papel dono das tabelas (que não é afetado por
RLS); o navegador nunca acessa as tabelas diretamente.
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

RLS_SQL = """
DO $$
DECLARE t record;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE 'ALTER TABLE public.' || quote_ident(t.tablename) || ' ENABLE ROW LEVEL SECURITY';
  END LOOP;
  -- Papéis da Data API do Supabase (inexistentes em PostgreSQL comum).
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon';
    EXECUTE 'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon';
    EXECUTE 'REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM anon';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM authenticated';
    EXECUTE 'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM authenticated';
    EXECUTE 'REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM authenticated';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM authenticated';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM authenticated';
  END IF;
END $$;
"""


def upgrade():
    op.add_column("usuarios", sa.Column("auth_user_id", sa.String(length=36), nullable=True))
    op.create_unique_constraint("uq_usuarios_auth_user_id", "usuarios", ["auth_user_id"])
    op.add_column("importacoes", sa.Column("conteudo", sa.LargeBinary(), nullable=True))
    for tabela in ("execucoes_otimizacao", "simulacoes_capacidade"):
        op.add_column(tabela, sa.Column("worker", sa.String(length=120), nullable=True))
        op.add_column(tabela, sa.Column("heartbeat_em", sa.DateTime(), nullable=True))
    op.add_column("simulacoes_capacidade", sa.Column("iniciado_em", sa.DateTime(), nullable=True))
    op.add_column("simulacoes_capacidade", sa.Column("finalizado_em", sa.DateTime(), nullable=True))
    # Índices parciais para a fila (busca rápida de jobs pendentes).
    op.create_index("ix_execucoes_fila", "execucoes_otimizacao", ["id"], postgresql_where=sa.text("status IN ('pendente','executando')"))
    op.create_index("ix_simulacoes_fila", "simulacoes_capacidade", ["id"], postgresql_where=sa.text("status IN ('pendente','executando')"))
    op.execute(RLS_SQL)


def downgrade():
    op.drop_index("ix_simulacoes_fila", table_name="simulacoes_capacidade")
    op.drop_index("ix_execucoes_fila", table_name="execucoes_otimizacao")
    op.drop_column("simulacoes_capacidade", "finalizado_em")
    op.drop_column("simulacoes_capacidade", "iniciado_em")
    for tabela in ("execucoes_otimizacao", "simulacoes_capacidade"):
        op.drop_column(tabela, "heartbeat_em")
        op.drop_column(tabela, "worker")
    op.drop_column("importacoes", "conteudo")
    op.drop_constraint("uq_usuarios_auth_user_id", "usuarios", type_="unique")
    op.drop_column("usuarios", "auth_user_id")
    # RLS permanece habilitado (medida de segurança; não é revertida automaticamente).
