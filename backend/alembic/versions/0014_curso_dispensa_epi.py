"""Curso que não precisa de EPI.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-17

- cursos.dispensa_epi: marca os cursos que não exigem EPI (ex.: informática, gestão). Eles deixam de aparecer
  como "sem lista de EPIs". Só acrescenta a coluna (padrão: falso); nada existente muda.
"""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cursos", sa.Column("dispensa_epi", sa.Boolean, nullable=False, server_default=sa.text("false")))


def downgrade():
    op.drop_column("cursos", "dispensa_epi")
