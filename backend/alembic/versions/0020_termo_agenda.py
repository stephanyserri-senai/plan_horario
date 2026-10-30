"""Termo de horas por dia e turno: a agenda do mês (grade por semanas).

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-30

- termos_horas.agenda (JSONB): {"AAAA-MM-DD": {"M": "aula", "V": "pl", ...}} — em cada dia do mês, os turnos do termo
  (M = matutino, V = vespertino, N = noturno, S = sábado) com aula ou planejamento (PL; ex.: sábado pago para planejamento
  de quem não tem disponibilidade na semana). Vazio = vale o termo antigo (horas do mês e, se houver, os dias da semana).
  Só acrescenta a coluna.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("termos_horas", sa.Column("agenda", postgresql.JSONB))


def downgrade():
    op.drop_column("termos_horas", "agenda")
