"""Pedidos de impressão dos instrutores (pelo portal), atendidos pela coordenação.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-31

- solicitacoes_impressao: material, cópias, páginas, frente e verso, colorido, o PDF (até 4 MB) ou o link do arquivo, turma, dia de uso e prazo
  (quinta-feira da semana anterior ao uso), situação (pendente, em produção, pronta, entregue, recusada, cancelada) e o
  retorno da coordenação. Só cria a tabela.
"""
import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "solicitacoes_impressao",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("instrutor_id", sa.Integer, sa.ForeignKey("instrutores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("turma_id", sa.Integer, sa.ForeignKey("turmas.id", ondelete="SET NULL")),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("descricao", sa.Text),
        sa.Column("arquivo_url", sa.String(500)),
        sa.Column("arquivo_nome", sa.String(200)),
        sa.Column("arquivo_tamanho", sa.Integer),
        sa.Column("arquivo_pdf", sa.LargeBinary),
        sa.Column("copias", sa.Integer, nullable=False),
        sa.Column("paginas", sa.Integer),
        sa.Column("frente_verso", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("colorido", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("data_uso", sa.Date, nullable=False),
        sa.Column("prazo", sa.Date, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pendente"),
        sa.Column("resposta", sa.Text),
        sa.Column("atendido_por_id", sa.Integer, sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
        sa.Column("atendido_em", sa.DateTime),
        sa.Column("criado_em", sa.DateTime, server_default=sa.func.now()),
        sa.CheckConstraint("status in ('pendente','em_producao','pronta','entregue','recusada','cancelada')", name="impressao_status_check"),
        sa.CheckConstraint("copias > 0", name="impressao_copias_check"),
    )
    op.create_index("ix_solicitacoes_impressao_instrutor_id", "solicitacoes_impressao", ["instrutor_id"])
    # Supabase: a tabela nova fica fechada para a Data API (só o backend acessa)
    op.execute("""ALTER TABLE public.solicitacoes_impressao ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.solicitacoes_impressao FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.solicitacoes_impressao FROM authenticated';
  END IF;
END $$""")


def downgrade():
    op.drop_table("solicitacoes_impressao")
