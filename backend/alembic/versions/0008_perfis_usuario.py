"""Perfis de usuário: administrador, planejador, instrutor e observador.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-15

- ADMINISTRADOR: gestão do projeto (tudo).
- PLANEJADOR: usa as funções de planejamento (mesmas permissões de antes).
- INSTRUTOR: portal do instrutor.
- OBSERVADOR (novo): só acompanha — consulta cadastros, grade e indicadores e baixa relatórios; não altera nada.
Os perfis coordenador, gestor e consulta deixam de existir. Nenhum usuário é apagado: quem tinha
coordenador passa a planejador; gestor e consulta passam a observador.
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

OBSERVADOR = ["cadastros.ler", "alocacoes.ler", "indicadores.ler", "exportacao.executar"]


def upgrade():
    op.execute("ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS usuarios_perfil_check")
    op.execute("UPDATE usuarios SET perfil = 'planejador' WHERE perfil = 'coordenador'")
    op.execute("UPDATE usuarios SET perfil = 'observador' WHERE perfil IN ('gestor', 'consulta')")
    op.execute("ALTER TABLE usuarios ADD CONSTRAINT usuarios_perfil_check "
               "CHECK (perfil in ('administrador','planejador','instrutor','observador'))")
    op.execute("DELETE FROM permissoes_perfil WHERE perfil IN ('coordenador', 'gestor', 'consulta')")
    for a in OBSERVADOR:
        op.execute(f"INSERT INTO permissoes_perfil (perfil, acao) VALUES ('observador', '{a}') ON CONFLICT DO NOTHING")


def downgrade():
    op.execute("ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS usuarios_perfil_check")
    op.execute("UPDATE usuarios SET perfil = 'consulta' WHERE perfil = 'observador'")
    op.execute("ALTER TABLE usuarios ADD CONSTRAINT usuarios_perfil_check "
               "CHECK (perfil in ('administrador','planejador','coordenador','gestor','consulta','instrutor'))")
    op.execute("DELETE FROM permissoes_perfil WHERE perfil = 'observador'")
    for a in ["cadastros.ler", "alocacoes.ler", "indicadores.ler"]:
        op.execute(f"INSERT INTO permissoes_perfil (perfil, acao) VALUES ('consulta', '{a}') ON CONFLICT DO NOTHING")
