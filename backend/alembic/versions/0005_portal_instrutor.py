"""Portal do instrutor.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-15

- Perfil de acesso "instrutor", vinculado a um cadastro de instrutor (usuarios.instrutor_id).
- Data da última atualização feita pelo próprio instrutor (instrutores.atualizado_pelo_instrutor_em).
- Observações/sugestões do instrutor sobre as turmas × UCs atribuídas (observacoes_instrutor).
- Notificações do instrutor no portal (notificacoes).
- Substituição de instrutor: titular original da aula (alocacoes.instrutor_titular_id).
- Permissões novas: portal.instrutor (perfil instrutor) e observacoes.gerenciar (administrador,
  planejador e coordenador).
Não destrutiva: adiciona colunas anuláveis, duas tabelas e amplia um CHECK.
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

SEGURANCA_SQL = """
ALTER TABLE public.observacoes_instrutor ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notificacoes ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.observacoes_instrutor, public.notificacoes FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.observacoes_instrutor, public.notificacoes FROM authenticated';
  END IF;
END $$
"""

PERMISSOES = [("instrutor", "portal.instrutor"), ("administrador", "observacoes.gerenciar"),
              ("planejador", "observacoes.gerenciar"), ("coordenador", "observacoes.gerenciar")]


def upgrade():
    op.execute("ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS usuarios_perfil_check")
    op.execute("ALTER TABLE usuarios ADD CONSTRAINT usuarios_perfil_check "
               "CHECK (perfil in ('administrador','planejador','coordenador','gestor','consulta','instrutor'))")
    op.add_column("usuarios", sa.Column("instrutor_id", sa.Integer(), sa.ForeignKey("instrutores.id", ondelete="SET NULL"), nullable=True))
    op.create_unique_constraint("usuarios_instrutor_id_key", "usuarios", ["instrutor_id"])
    op.add_column("instrutores", sa.Column("atualizado_pelo_instrutor_em", sa.DateTime(), nullable=True))
    op.create_table(
        "observacoes_instrutor",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instrutor_id", sa.Integer(), sa.ForeignKey("instrutores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("turma_uc_id", sa.Integer(), sa.ForeignKey("turma_uc.id", ondelete="CASCADE"), nullable=True),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="nova"),
        sa.Column("resposta", sa.Text(), nullable=True),
        sa.Column("respondido_por_id", sa.Integer(), sa.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("respondido_em", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status in ('nova','lida','resolvida')", name="observacoes_instrutor_status_check"),
    )
    op.create_index("ix_observacoes_instrutor_instrutor_id", "observacoes_instrutor", ["instrutor_id"])
    op.create_index("ix_observacoes_instrutor_turma_uc_id", "observacoes_instrutor", ["turma_uc_id"])
    op.create_table(
        "notificacoes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instrutor_id", sa.Integer(), sa.ForeignKey("instrutores.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo", sa.String(30), nullable=False),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("texto", sa.Text(), nullable=True),
        sa.Column("aba", sa.String(20), nullable=True),
        sa.Column("lida", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notificacoes_instrutor_id", "notificacoes", ["instrutor_id"])
    op.add_column("alocacoes", sa.Column("instrutor_titular_id", sa.Integer(), sa.ForeignKey("instrutores.id", ondelete="SET NULL"), nullable=True))
    op.execute(SEGURANCA_SQL)
    for perfil, acao in PERMISSOES:
        op.execute(f"INSERT INTO permissoes_perfil (perfil, acao) VALUES ('{perfil}', '{acao}') ON CONFLICT DO NOTHING")


def downgrade():
    for perfil, acao in PERMISSOES:
        op.execute(f"DELETE FROM permissoes_perfil WHERE perfil = '{perfil}' AND acao = '{acao}'")
    op.drop_column("alocacoes", "instrutor_titular_id")
    op.drop_table("notificacoes")
    op.drop_table("observacoes_instrutor")
    op.drop_column("instrutores", "atualizado_pelo_instrutor_em")
    op.drop_constraint("usuarios_instrutor_id_key", "usuarios", type_="unique")
    op.drop_column("usuarios", "instrutor_id")
    op.execute("UPDATE usuarios SET perfil = 'consulta' WHERE perfil = 'instrutor'")
    op.execute("ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS usuarios_perfil_check")
    op.execute("ALTER TABLE usuarios ADD CONSTRAINT usuarios_perfil_check "
               "CHECK (perfil in ('administrador','planejador','coordenador','gestor','consulta'))")
