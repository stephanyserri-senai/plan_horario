"""Termo de horas: dias da semana do termo (ajustável por urgência, com a concordância do instrutor).

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-20

- termos_horas.dias_semana: dias da semana em que estão as horas do termo (vazio = qualquer dia da disponibilidade).
  Só acrescenta a coluna; os termos existentes continuam valendo para qualquer dia.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("termos_horas", sa.Column("dias_semana", postgresql.ARRAY(sa.Integer)))


def downgrade():
    op.drop_column("termos_horas", "dias_semana")
