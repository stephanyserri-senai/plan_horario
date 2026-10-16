"""Coordenador e solicitações do instrutor; UCs transversais/técnicas; competência "sim / em partes"; turno de sábado.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-16

- COORDENADOR (perfil recriado): as mesmas permissões do planejador + aprovar as solicitações dos instrutores.
- SOLICITAÇÕES do instrutor (portal): folga ou substituição, com justificativa, aprovadas ou recusadas pelo coordenador.
- UC TRANSVERSAL (qualquer instrutor pode dar) ou TÉCNICA (só quem marcou a UC no perfil). Todas começam como técnica.
- COMPETÊNCIA: "sim" (pleno) ou "em partes" (parcial). "Sob supervisão" deixa de existir e passa a "em partes".
- SÁBADO: turno "S" (09:00–13:00, 4 aulas, só aos sábados) em cada unidade; o sábado passa a ser letivo nos
  calendários e entra no horário de funcionamento das unidades que já o têm cadastrado (09:00–13:00).
Não destrutiva: só acrescenta colunas, tabela e registros; nenhum dado é apagado.
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

PLANEJADOR = ["cadastros.ler", "cadastros.editar", "alocacoes.ler", "alocacoes.editar", "cenarios.criar", "cenarios.editar",
              "otimizacao.executar", "simulacao.executar", "indicadores.ler", "importacao.executar", "exportacao.executar",
              "dados_pessoais.ler", "observacoes.gerenciar"]
# sábado: 4 aulas de 55 min com intervalo de 20 min entre a 2ª e a 3ª (09:00–13:00)
SABADO = [("09:00", "09:55"), ("09:55", "10:50"), ("11:10", "12:05"), ("12:05", "13:00")]


def upgrade():
    # perfil coordenador
    op.execute("ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS usuarios_perfil_check")
    op.execute("ALTER TABLE usuarios ADD CONSTRAINT usuarios_perfil_check "
               "CHECK (perfil in ('administrador','planejador','coordenador','instrutor','observador'))")
    for a in PLANEJADOR + ["solicitacoes.aprovar"]:
        op.execute(f"INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', '{a}') ON CONFLICT DO NOTHING")
    op.execute("INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'solicitacoes.aprovar') ON CONFLICT DO NOTHING")

    # solicitações do instrutor
    op.create_table(
        "solicitacoes_instrutor",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("instrutor_id", sa.Integer, sa.ForeignKey("instrutores.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("data_inicio", sa.Date, nullable=False),
        sa.Column("data_fim", sa.Date, nullable=False),
        sa.Column("turnos", postgresql.ARRAY(sa.Integer), nullable=False, server_default="{}"),
        sa.Column("justificativa", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pendente"),
        sa.Column("resposta", sa.Text),
        sa.Column("decidido_por_id", sa.Integer, sa.ForeignKey("usuarios.id", ondelete="SET NULL")),
        sa.Column("decidido_em", sa.DateTime),
        sa.Column("efeitos", postgresql.JSONB),
        sa.Column("criado_em", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("tipo in ('folga','substituicao')", name="solicitacoes_tipo_check"),
        sa.CheckConstraint("status in ('pendente','aprovada','recusada','cancelada')", name="solicitacoes_status_check"),
        sa.CheckConstraint("data_fim >= data_inicio", name="solicitacoes_datas_check"),
    )

    # Supabase: a tabela nova fica fechada para a Data API (só o backend acessa)
    op.execute("""ALTER TABLE public.solicitacoes_instrutor ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.solicitacoes_instrutor FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.solicitacoes_instrutor FROM authenticated';
  END IF;
END $$""")

    # UC transversal ou técnica
    op.add_column("unidades_curriculares", sa.Column("categoria", sa.String(12), nullable=False, server_default="tecnica"))
    op.create_check_constraint("ucs_categoria_check", "unidades_curriculares", "categoria in ('tecnica','transversal')")

    # competência: sim (pleno) ou em partes (parcial)
    op.execute("ALTER TABLE competencias_instrutores DROP CONSTRAINT IF EXISTS competencias_instrutores_nivel_check")
    op.execute("ALTER TABLE competencias_instrutores DROP CONSTRAINT IF EXISTS ck_competencias_instrutores_nivel")
    op.execute("""DO $$ DECLARE r record; BEGIN
      FOR r IN SELECT conname FROM pg_constraint WHERE conrelid = 'competencias_instrutores'::regclass AND contype = 'c'
               AND strpos(pg_get_constraintdef(oid), 'supervisionado') > 0 LOOP
        EXECUTE 'ALTER TABLE competencias_instrutores DROP CONSTRAINT ' || quote_ident(r.conname);
      END LOOP; END $$""")
    op.execute("UPDATE competencias_instrutores SET nivel = 'parcial' WHERE nivel = 'supervisionado'")
    op.create_check_constraint("competencias_instrutores_nivel_check", "competencias_instrutores", "nivel in ('pleno','parcial','em_formacao')")

    # turno de sábado (09:00–13:00) em cada unidade que ainda não tem
    valores = ", ".join(f"({i}, '{a}', '{b}')" for i, (a, b) in enumerate(SABADO, 1))
    op.execute(f"""DO $$ DECLARE u record; t_id int; BEGIN
      FOR u IN SELECT id FROM unidades LOOP
        IF NOT EXISTS (SELECT 1 FROM turnos WHERE unidade_id = u.id AND codigo = 'S') THEN
          INSERT INTO turnos (unidade_id, codigo, nome, hora_inicio, hora_fim, ordem, ativo, criado_em, atualizado_em)
          VALUES (u.id, 'S', 'Sábado', '09:00', '13:00', 4, true, now(), now()) RETURNING id INTO t_id;
          INSERT INTO periodos_horarios (unidade_id, turno_id, ordem, hora_inicio, hora_fim, dias_semana, excepcional, ativo, criado_em, atualizado_em)
          SELECT u.id, t_id, v.ordem, v.ini::time, v.fim::time, '{{5}}', false, true, now(), now() FROM (VALUES {valores}) AS v(ordem, ini, fim);
        END IF;
        IF EXISTS (SELECT 1 FROM horarios_funcionamento WHERE unidade_id = u.id)
           AND NOT EXISTS (SELECT 1 FROM horarios_funcionamento WHERE unidade_id = u.id AND dia_semana = 5) THEN
          INSERT INTO horarios_funcionamento (unidade_id, dia_semana, hora_inicio, hora_fim, ativo) VALUES (u.id, 5, '09:00', '13:00', true);
        END IF;
      END LOOP;
      UPDATE calendarios SET dias_letivos = array_append(dias_letivos, 5) WHERE NOT (5 = ANY(dias_letivos));
    END $$""")


def downgrade():
    # o turno de sábado só sai se nenhuma turma o usa
    op.execute("DELETE FROM periodos_horarios WHERE turno_id IN (SELECT t.id FROM turnos t WHERE t.codigo = 'S' "
               "AND NOT EXISTS (SELECT 1 FROM turmas x WHERE x.turno_id = t.id))")
    op.execute("DELETE FROM turnos t WHERE codigo = 'S' AND NOT EXISTS (SELECT 1 FROM periodos_horarios p WHERE p.turno_id = t.id) "
               "AND NOT EXISTS (SELECT 1 FROM turmas x WHERE x.turno_id = t.id)")
    op.execute("ALTER TABLE competencias_instrutores DROP CONSTRAINT IF EXISTS competencias_instrutores_nivel_check")
    op.execute("UPDATE competencias_instrutores SET nivel = 'supervisionado' WHERE nivel = 'parcial'")
    op.create_check_constraint("competencias_instrutores_nivel_check", "competencias_instrutores", "nivel in ('pleno','supervisionado','em_formacao')")
    op.drop_constraint("ucs_categoria_check", "unidades_curriculares", type_="check")
    op.drop_column("unidades_curriculares", "categoria")
    op.drop_table("solicitacoes_instrutor")
    op.execute("DELETE FROM permissoes_perfil WHERE acao = 'solicitacoes.aprovar' OR perfil = 'coordenador'")
    op.execute("UPDATE usuarios SET perfil = 'planejador' WHERE perfil = 'coordenador'")
    op.execute("ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS usuarios_perfil_check")
    op.execute("ALTER TABLE usuarios ADD CONSTRAINT usuarios_perfil_check "
               "CHECK (perfil in ('administrador','planejador','instrutor','observador'))")
