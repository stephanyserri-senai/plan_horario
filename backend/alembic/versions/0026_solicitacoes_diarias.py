"""Solicitação de diárias (recursos extras) para instrutores em eventos e projetos.

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-03

- solicitacoes_diarias: instrutor, motivo (evento, projeto, outro), título, local, período, quantidade de diárias,
  valor unitário, outros recursos, centro de custo, situação (solicitada, aprovada, paga, recusada, cancelada) e retorno
  da supervisão. Só cria a tabela.
"""
import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "solicitacoes_diarias",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("instrutor_id", sa.Integer, sa.ForeignKey("instrutores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("motivo", sa.String(20), nullable=False),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("descricao", sa.Text),
        sa.Column("destino", sa.String(200)),
        sa.Column("data_inicio", sa.Date, nullable=False),
        sa.Column("data_fim", sa.Date, nullable=False),
        sa.Column("quantidade", sa.Numeric(5, 1), nullable=False),
        sa.Column("valor_unitario", sa.Numeric(10, 2)),
        sa.Column("outros_recursos", sa.Text),
        sa.Column("centro_custo", sa.String(60)),
        sa.Column("status", sa.String(20), nullable=False, server_default="solicitada"),
        sa.Column("resposta", sa.Text),
        sa.Column("solicitado_por_id", sa.Integer, sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
        sa.Column("decidido_por_id", sa.Integer, sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
        sa.Column("decidido_em", sa.DateTime),
        sa.Column("pago_em", sa.Date),
        sa.Column("criado_em", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status in ('solicitada','aprovada','paga','recusada','cancelada')", name="diaria_status_check"),
        sa.CheckConstraint("motivo in ('evento','projeto','outro')", name="diaria_motivo_check"),
        sa.CheckConstraint("quantidade > 0", name="diaria_quantidade_check"),
        sa.CheckConstraint("data_fim >= data_inicio", name="diaria_periodo_check"),
    )
    op.create_index("ix_solicitacoes_diarias_instrutor_id", "solicitacoes_diarias", ["instrutor_id"])
    # Supabase: a tabela nova fica fechada para a Data API (só o backend acessa)
    op.execute("""ALTER TABLE public.solicitacoes_diarias ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.solicitacoes_diarias FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.solicitacoes_diarias FROM authenticated';
  END IF;
END $$""")


def downgrade():
    op.drop_index("ix_solicitacoes_diarias_instrutor_id", table_name="solicitacoes_diarias")
    op.drop_table("solicitacoes_diarias")
