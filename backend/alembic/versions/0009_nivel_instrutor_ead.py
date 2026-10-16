"""Nível do instrutor (básico/técnico) e dias EAD da turma (turmas 80-20).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-16

- NÍVEL do instrutor: "basico" só pode dar aula em aprendizagem industrial básica (AIB) e qualificações;
  "tecnico" pode dar aula em todas as modalidades (AIB, AIT, HTC, ...). Padrão "tecnico" para não
  restringir quem já está cadastrado; ajuste os básicos no cadastro.
- DIAS EAD da turma: dias da semana reservados a atividades a distância (normalmente a sexta, nas turmas
  80-20). Nesses dias não há aula presencial; a grade mostra a etiqueta EAD.
Não destrutiva: só adiciona colunas com valor padrão.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("instrutores", sa.Column("nivel", sa.String(10), nullable=False, server_default="tecnico"))
    op.create_check_constraint("instrutores_nivel_check", "instrutores", "nivel in ('basico','tecnico')")
    op.add_column("turmas", sa.Column("dias_ead", postgresql.ARRAY(sa.Integer()), nullable=False, server_default="{}"))


def downgrade():
    op.drop_column("turmas", "dias_ead")
    op.drop_constraint("instrutores_nivel_check", "instrutores", type_="check")
    op.drop_column("instrutores", "nivel")
