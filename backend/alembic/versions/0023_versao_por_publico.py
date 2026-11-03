"""Versões do mesmo curso por público (PAGANTE, SEDU, AIT...).

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-03

- matrizes_curriculares.tipo_oferta passa a aceitar até 30 caracteres (público/versão do curso: PAGANTE, SEDU, AIT, HTC...).
- A versão é única por curso + versão + público (antes: curso + versão), para o mesmo curso (mesma sigla) ter, por exemplo,
  a versão 2026 para PAGANTE e a 2026 para SEDU. Não apaga nada.
"""
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE matrizes_curriculares ALTER COLUMN tipo_oferta TYPE VARCHAR(30)")
    op.execute("ALTER TABLE matrizes_curriculares DROP CONSTRAINT IF EXISTS matrizes_curriculares_curso_id_versao_key")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_matriz_curso_versao_publico ON matrizes_curriculares "
               "(curso_id, versao, (coalesce(tipo_oferta, '')))")


def downgrade():
    op.execute("DROP INDEX IF EXISTS uq_matriz_curso_versao_publico")
    op.execute("ALTER TABLE matrizes_curriculares ADD CONSTRAINT matrizes_curriculares_curso_id_versao_key UNIQUE (curso_id, versao)")
