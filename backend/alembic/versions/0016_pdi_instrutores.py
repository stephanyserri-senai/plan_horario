"""PDI dos instrutores (plano de desenvolvimento individual) a partir do índice de aderência.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-20

- pdi_itens: UCs que o instrutor vai aprender ou completar e certificações a obter, com prioridade,
  prazo e situação (planejado, em andamento, concluído, cancelado). Só cria a tabela.
"""
import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "pdi_itens",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("instrutor_id", sa.Integer, sa.ForeignKey("instrutores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("curso_id", sa.Integer, sa.ForeignKey("cursos.id", ondelete="SET NULL")),
        sa.Column("uc_codigo", sa.String(30), nullable=False),
        sa.Column("uc_nome", sa.String(200), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False, server_default="uc"),
        sa.Column("certificacao", sa.String(200)),
        sa.Column("prioridade", sa.String(10)),
        sa.Column("prazo", sa.Date),
        sa.Column("situacao", sa.String(20), nullable=False, server_default="planejado"),
        sa.Column("observacao", sa.Text),
        sa.Column("concluido_em", sa.Date),
        sa.Column("criado_por_id", sa.Integer, sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
        sa.Column("criado_em", sa.DateTime, server_default=sa.func.now()),
        sa.Column("atualizado_em", sa.DateTime, server_default=sa.func.now()),
        sa.CheckConstraint("tipo in ('uc','completar','certificacao')", name="pdi_itens_tipo_check"),
        sa.CheckConstraint("situacao in ('planejado','em_andamento','concluido','cancelado')", name="pdi_itens_situacao_check"),
    )
    op.create_index("ix_pdi_itens_instrutor_id", "pdi_itens", ["instrutor_id"])
    # Supabase: a tabela nova fica fechada para a Data API (só o backend acessa)
    op.execute("""ALTER TABLE public.pdi_itens ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.pdi_itens FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.pdi_itens FROM authenticated';
  END IF;
END $$""")


def downgrade():
    op.drop_table("pdi_itens")
