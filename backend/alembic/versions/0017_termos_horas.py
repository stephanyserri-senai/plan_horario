"""Termo de horas mensal dos instrutores horistas.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-20

- termos_horas: por instrutor e mês, as horas de aula que o horista assume no mês (e outras ocupações).
  O termo muda de um mês para outro; o mensalista continua com a jornada semanal fixa. Só cria a tabela.
"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "termos_horas",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("instrutor_id", sa.Integer, sa.ForeignKey("instrutores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mes", sa.Date, nullable=False),
        sa.Column("horas_aula", sa.Numeric(6, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("horas_outras", sa.Numeric(6, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("observacao", sa.Text),
        sa.Column("atualizado_por_id", sa.Integer, sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
        sa.Column("criado_em", sa.DateTime, server_default=sa.func.now()),
        sa.Column("atualizado_em", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("instrutor_id", "mes"),
        sa.CheckConstraint("horas_aula >= 0"),
        sa.CheckConstraint("horas_outras >= 0"),
    )
    op.create_index("ix_termos_horas_instrutor_id", "termos_horas", ["instrutor_id"])
    # Supabase: a tabela nova fica fechada para a Data API (só o backend acessa)
    op.execute("""ALTER TABLE public.termos_horas ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.termos_horas FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.termos_horas FROM authenticated';
  END IF;
END $$""")


def downgrade():
    op.drop_table("termos_horas")
