"""Modalidade do instrutor: mensalista ou horista.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-15

- MENSALISTA: 40 h ou 20 h semanais garantidas; turnos sem aula são planejamento (PL) ou projeto (PJ).
- HORISTA: 40 h ou 20 h semanais não garantidas; turnos sem aula podem ficar vazios (dispensa).
Os turnos de PL e PJ são registrados como bloqueios do instrutor (tipos "planejamento" e "projeto").
Não destrutiva: adiciona uma coluna com valor padrão "mensalista".
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("instrutores", sa.Column("modalidade", sa.String(12), nullable=False, server_default="mensalista"))
    op.create_check_constraint("instrutores_modalidade_check", "instrutores", "modalidade in ('mensalista','horista')")


def downgrade():
    op.drop_constraint("instrutores_modalidade_check", "instrutores", type_="check")
    op.drop_column("instrutores", "modalidade")
