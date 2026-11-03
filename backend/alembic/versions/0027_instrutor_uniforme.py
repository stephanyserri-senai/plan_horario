"""Instrutor: gestor imediato e uniforme (jaleco em 3 referências, blusa e botina).

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-03

- instrutores: gestor_imediato, jaleco_np (numeração profissional), jaleco_pmg (P/M/G), jaleco_num (1, 2, 3),
  tamanho_blusa e numero_botina. Só acrescenta colunas (vazias).
"""
import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

COLUNAS = [("gestor_imediato", 120), ("jaleco_np", 10), ("jaleco_pmg", 10), ("jaleco_num", 10), ("tamanho_blusa", 10), ("numero_botina", 10)]


def upgrade():
    for nome, tam in COLUNAS:
        op.add_column("instrutores", sa.Column(nome, sa.String(tam)))


def downgrade():
    for nome, _ in reversed(COLUNAS):
        op.drop_column("instrutores", nome)
