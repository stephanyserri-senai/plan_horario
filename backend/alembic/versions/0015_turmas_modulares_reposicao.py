"""Turmas modulares e reposição de aulas aos sábados.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-17

- turmas.modulos / turmas.modulo_atual: turma modular (um módulo por semestre). O código leva o módulo
  (HTC-ELT-2-12 = 2º módulo da turma 12) e sobe a cada semestre até o último módulo. Vazio = não modular.
- excecoes_autorizadas: novo tipo 'reposicao' (aula de reposição aos sábados de turma que não termina no prazo).
Só acrescenta colunas e amplia a lista de tipos; nada existente muda.
"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("turmas", sa.Column("modulos", sa.Integer, nullable=True))
    op.add_column("turmas", sa.Column("modulo_atual", sa.Integer, nullable=True))
    op.drop_constraint("excecoes_autorizadas_tipo_check", "excecoes_autorizadas", type_="check")
    op.create_check_constraint("excecoes_autorizadas_tipo_check", "excecoes_autorizadas",
                               "tipo in ('feriado_bloqueio','carga_horaria','regra_academica','reposicao')")


def downgrade():
    op.drop_constraint("excecoes_autorizadas_tipo_check", "excecoes_autorizadas", type_="check")
    op.create_check_constraint("excecoes_autorizadas_tipo_check", "excecoes_autorizadas",
                               "tipo in ('feriado_bloqueio','carga_horaria','regra_academica')")
    op.drop_column("turmas", "modulo_atual")
    op.drop_column("turmas", "modulos")
