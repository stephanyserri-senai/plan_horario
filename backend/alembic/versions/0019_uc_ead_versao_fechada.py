"""UC presencial ou EAD e curso que prevê EAD.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-20

- cursos.preve_ead: o curso tem UCs a distância (padrão: não).
- unidades_curriculares.modalidade: presencial (padrão) ou ead. UC EAD não entra na grade presencial nem ocupa sala.
Só acrescenta colunas; tudo o que existe continua presencial.
"""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cursos", sa.Column("preve_ead", sa.Boolean, nullable=False, server_default=sa.text("false")))
    op.add_column("unidades_curriculares", sa.Column("modalidade", sa.String(12), nullable=False, server_default="presencial"))
    op.create_check_constraint("ucs_modalidade_check", "unidades_curriculares", "modalidade in ('presencial','ead')")


def downgrade():
    op.drop_constraint("ucs_modalidade_check", "unidades_curriculares", type_="check")
    op.drop_column("unidades_curriculares", "modalidade")
    op.drop_column("cursos", "preve_ead")
