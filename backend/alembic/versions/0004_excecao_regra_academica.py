"""Áreas múltiplas e exceção justificada para regras acadêmicas.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-14

- Instrutores e ambientes podem atuar em mais de uma área (tabelas instrutor_areas
  e ambiente_areas, além da área principal) ou em todas (coluna todas_areas).
- Exceção justificada do tipo 'regra_academica' (instrutor/laboratório de outra
  área, instrutor sem competência cadastrada).
Não destrutiva: cria tabelas, adiciona colunas com valor padrão e amplia um CHECK.
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

SEGURANCA_SQL = """
ALTER TABLE public.instrutor_areas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ambiente_areas ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.instrutor_areas, public.ambiente_areas FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.instrutor_areas, public.ambiente_areas FROM authenticated';
  END IF;
END $$
"""


def upgrade():
    for t in ("instrutores", "ambientes"):
        op.add_column(t, sa.Column("todas_areas", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.create_table("instrutor_areas",
                    sa.Column("instrutor_id", sa.Integer(), sa.ForeignKey("instrutores.id", ondelete="CASCADE"), primary_key=True),
                    sa.Column("area_id", sa.Integer(), sa.ForeignKey("areas.id"), primary_key=True))
    op.create_table("ambiente_areas",
                    sa.Column("ambiente_id", sa.Integer(), sa.ForeignKey("ambientes.id", ondelete="CASCADE"), primary_key=True),
                    sa.Column("area_id", sa.Integer(), sa.ForeignKey("areas.id"), primary_key=True))
    op.execute(SEGURANCA_SQL)
    op.execute("ALTER TABLE excecoes_autorizadas DROP CONSTRAINT IF EXISTS excecoes_autorizadas_tipo_check")
    op.execute("ALTER TABLE excecoes_autorizadas ADD CONSTRAINT excecoes_autorizadas_tipo_check "
               "CHECK (tipo IN ('feriado_bloqueio', 'carga_horaria', 'regra_academica'))")


def downgrade():
    op.execute("ALTER TABLE excecoes_autorizadas DROP CONSTRAINT IF EXISTS excecoes_autorizadas_tipo_check")
    op.execute("ALTER TABLE excecoes_autorizadas ADD CONSTRAINT excecoes_autorizadas_tipo_check "
               "CHECK (tipo IN ('feriado_bloqueio', 'carga_horaria')) NOT VALID")
    op.drop_table("ambiente_areas")
    op.drop_table("instrutor_areas")
    for t in ("instrutores", "ambientes"):
        op.drop_column(t, "todas_areas")
