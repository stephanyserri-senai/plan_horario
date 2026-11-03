"""UC com carga TOTAL, EaD e PRESENCIAL e modalidade presencial, EAD ou semipresencial.

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-03

- unidades_curriculares: carga_horaria_ead, carga_horaria_presencial e divisao_confirmada; modalidade aceita
  'semipresencial'. Os registros existentes são preservados: UC EAD = tudo EaD (divisão confirmada, já era explícita);
  as demais = tudo presencial, como o sistema vinha tratando, com divisao_confirmada = falso (a conferir na
  reimportação ou no cadastro). Regras: cargas não negativas e EaD + presencial = total.
"""
import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("unidades_curriculares", sa.Column("carga_horaria_ead", sa.Integer, nullable=True))
    op.add_column("unidades_curriculares", sa.Column("carga_horaria_presencial", sa.Integer, nullable=True))
    op.add_column("unidades_curriculares", sa.Column("divisao_confirmada", sa.Boolean, nullable=False, server_default=sa.text("false")))
    op.execute("UPDATE unidades_curriculares SET carga_horaria_ead = carga_horaria_total, carga_horaria_presencial = 0, divisao_confirmada = true "
               "WHERE modalidade = 'ead' AND carga_horaria_ead IS NULL")
    op.execute("UPDATE unidades_curriculares SET carga_horaria_ead = 0, carga_horaria_presencial = carga_horaria_total "
               "WHERE carga_horaria_ead IS NULL")
    op.alter_column("unidades_curriculares", "carga_horaria_ead", nullable=False, server_default="0")
    op.alter_column("unidades_curriculares", "carga_horaria_presencial", nullable=False)
    op.alter_column("unidades_curriculares", "modalidade", type_=sa.String(14))
    op.drop_constraint("ucs_modalidade_check", "unidades_curriculares", type_="check")
    op.create_check_constraint("ucs_modalidade_check", "unidades_curriculares", "modalidade in ('presencial','ead','semipresencial')")
    op.create_check_constraint("ucs_cargas_nao_negativas", "unidades_curriculares", "carga_horaria_ead >= 0 AND carga_horaria_presencial >= 0")
    op.create_check_constraint("ucs_cargas_somam_total", "unidades_curriculares", "carga_horaria_ead + carga_horaria_presencial = carga_horaria_total")


def downgrade():
    op.drop_constraint("ucs_cargas_somam_total", "unidades_curriculares", type_="check")
    op.drop_constraint("ucs_cargas_nao_negativas", "unidades_curriculares", type_="check")
    op.drop_constraint("ucs_modalidade_check", "unidades_curriculares", type_="check")
    op.execute("UPDATE unidades_curriculares SET modalidade = 'presencial' WHERE modalidade = 'semipresencial'")
    op.create_check_constraint("ucs_modalidade_check", "unidades_curriculares", "modalidade in ('presencial','ead')")
    op.drop_column("unidades_curriculares", "divisao_confirmada")
    op.drop_column("unidades_curriculares", "carga_horaria_presencial")
    op.drop_column("unidades_curriculares", "carga_horaria_ead")
