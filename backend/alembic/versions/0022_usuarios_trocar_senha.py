"""Troca de senha obrigatória no primeiro acesso.

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-03

- usuarios.trocar_senha: o usuário recebeu uma senha inicial e precisa definir a dele ao entrar. Só acrescenta a coluna
  (os usuários existentes ficam como estão).
"""
import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("usuarios", sa.Column("trocar_senha", sa.Boolean, nullable=False, server_default=sa.text("false")))


def downgrade():
    op.drop_column("usuarios", "trocar_senha")
