"""Agendamento de ambientes (salas e laboratórios) pelos instrutores.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-03

- agendamentos_ambiente: pedido de uso de um ambiente num dia e turno (finalidade, turma, participantes), situação
  (pendente, confirmado, recusado, cancelado), retorno da supervisão e o bloqueio criado ao confirmar. Só cria a tabela.
"""
import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agendamentos_ambiente",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("ambiente_id", sa.Integer, sa.ForeignKey("ambientes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("instrutor_id", sa.Integer, sa.ForeignKey("instrutores.id", ondelete="CASCADE")),
        sa.Column("solicitado_por_id", sa.Integer, sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
        sa.Column("turma_id", sa.Integer, sa.ForeignKey("turmas.id", ondelete="SET NULL")),
        sa.Column("turno_id", sa.Integer, sa.ForeignKey("turnos.id", ondelete="SET NULL")),
        sa.Column("data", sa.Date, nullable=False),
        sa.Column("inicio", sa.DateTime, nullable=False),
        sa.Column("fim", sa.DateTime, nullable=False),
        sa.Column("finalidade", sa.Text, nullable=False),
        sa.Column("participantes", sa.Integer),
        sa.Column("status", sa.String(20), nullable=False, server_default="pendente"),
        sa.Column("resposta", sa.Text),
        sa.Column("decidido_por_id", sa.Integer, sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
        sa.Column("decidido_em", sa.DateTime),
        sa.Column("bloqueio_id", sa.Integer, sa.ForeignKey("bloqueios.id", ondelete="SET NULL")),
        sa.Column("criado_em", sa.DateTime, server_default=sa.func.now()),
        sa.CheckConstraint("status in ('pendente','confirmado','recusado','cancelado')", name="agendamentos_status_check"),
        sa.CheckConstraint("fim > inicio", name="agendamentos_periodo_check"),
    )
    op.create_index("ix_agendamentos_ambiente_ambiente_id", "agendamentos_ambiente", ["ambiente_id"])
    op.create_index("ix_agendamentos_ambiente_instrutor_id", "agendamentos_ambiente", ["instrutor_id"])
    op.create_index("ix_agendamentos_ambiente_data", "agendamentos_ambiente", ["data"])
    # Supabase: a tabela nova fica fechada para a Data API (só o backend acessa)
    op.execute("""ALTER TABLE public.agendamentos_ambiente ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.agendamentos_ambiente FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.agendamentos_ambiente FROM authenticated';
  END IF;
END $$""")


def downgrade():
    op.drop_table("agendamentos_ambiente")
