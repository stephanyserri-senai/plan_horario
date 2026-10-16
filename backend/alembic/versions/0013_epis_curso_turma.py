"""EPIs por curso e controle de compra/separação e entrega por turma.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-17

- epis_curso: EPIs que cada curso exige por aluno (quantidade por aluno e antecedência do prazo).
- epis_turma: o que cada turma precisa (quantidade = alunos × por aluno), com prazo e as marcações
  "comprado/separado" e "entregue". Só cria tabelas; nada existente é alterado.
"""
import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "epis_curso",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("curso_id", sa.Integer, sa.ForeignKey("cursos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nome", sa.String(150), nullable=False),
        sa.Column("quantidade_por_aluno", sa.Integer, nullable=False, server_default=sa.text("1")),
        sa.Column("antecedencia_dias", sa.Integer, nullable=False, server_default=sa.text("15")),
        sa.Column("observacao", sa.Text),
        sa.Column("ativo", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("criado_em", sa.DateTime, server_default=sa.func.now()),
        sa.Column("atualizado_em", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_epis_curso_curso_id", "epis_curso", ["curso_id"])
    op.create_table(
        "epis_turma",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("turma_id", sa.Integer, sa.ForeignKey("turmas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("epi_curso_id", sa.Integer, sa.ForeignKey("epis_curso.id", ondelete="SET NULL")),
        sa.Column("nome", sa.String(150), nullable=False),
        sa.Column("quantidade", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("prazo", sa.Date),
        sa.Column("providenciado", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("providenciado_em", sa.DateTime),
        sa.Column("entregue", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("entregue_em", sa.DateTime),
        sa.Column("atualizado_por_id", sa.Integer),
        sa.Column("observacao", sa.Text),
        sa.Column("criado_em", sa.DateTime, server_default=sa.func.now()),
        sa.Column("atualizado_em", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("turma_id", "epi_curso_id"),
    )
    op.create_index("ix_epis_turma_turma_id", "epis_turma", ["turma_id"])
    # Supabase: as tabelas novas ficam fechadas para a Data API (só o backend acessa)
    op.execute("""ALTER TABLE public.epis_curso ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.epis_turma ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.epis_curso, public.epis_turma FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.epis_curso, public.epis_turma FROM authenticated';
  END IF;
END $$""")


def downgrade():
    op.drop_table("epis_turma")
    op.drop_table("epis_curso")
