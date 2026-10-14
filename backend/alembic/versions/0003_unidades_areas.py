"""Estrutura fixa da instituição: unidades Beira Mar e Porto, áreas tecnológicas,
turnos oficiais e vínculo de área em cursos, turmas, instrutores e ambientes.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-14

Migração NÃO destrutiva: cria a tabela de áreas, adiciona colunas anuláveis e
INSERE as unidades/áreas/turnos que ainda não existirem (nada é alterado ou
removido). Os valores estão escritos aqui de forma literal (não dependem do
código da aplicação) e correspondem a app/core/estrutura.py.
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

DADOS_SQL = """
INSERT INTO unidades (codigo, nome, situacao, ativo) VALUES
  ('BEIRA-MAR', 'Unidade Beira Mar', 'ativa', true),
  ('PORTO', 'Unidade Porto', 'ativa', true)
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO areas (unidade_id, codigo, nome, ativo)
SELECT u.id, a.codigo, a.nome, true
FROM (VALUES
  ('AUTOMACAO', 'AUTOMAÇÃO', 'BEIRA-MAR'), ('ENERGIAS', 'ENERGIAS', 'BEIRA-MAR'), ('AUTOMOTIVA', 'AUTOMOTIVA', 'BEIRA-MAR'),
  ('MECATRONICA', 'MECATRÔNICA', 'BEIRA-MAR'), ('MECANICA', 'MECÂNICA', 'BEIRA-MAR'), ('INSTRUMENTACAO', 'INSTRUMENTAÇÃO', 'BEIRA-MAR'),
  ('LOGISTICA', 'LOGÍSTICA', 'PORTO'), ('PORTOS', 'PORTOS', 'PORTO'), ('DDS-TI', 'DDS/TI', 'PORTO'),
  ('ECONOMIA-CRIATIVA', 'ECONOMIA CRIATIVA', 'PORTO'), ('GESTAO', 'GESTÃO', 'PORTO')
) AS a(codigo, nome, unidade)
JOIN unidades u ON u.codigo = a.unidade
ON CONFLICT (codigo) DO NOTHING;

-- Turnos oficiais (4 aulas; manhã/tarde 55 min, noite 50 min) nas unidades que ainda não têm turnos
INSERT INTO turnos (unidade_id, codigo, nome, hora_inicio, hora_fim, ordem, ativo)
SELECT u.id, t.codigo, t.nome, t.ini::time, t.fim::time, t.ordem, true
FROM unidades u
CROSS JOIN (VALUES ('M', 'Manhã', '07:30', '11:30', 1), ('T', 'Tarde', '13:30', '17:30', 2), ('N', 'Noite', '18:20', '21:50', 3))
  AS t(codigo, nome, ini, fim, ordem)
WHERE u.codigo IN ('BEIRA-MAR', 'PORTO')
  AND NOT EXISTS (SELECT 1 FROM turnos x WHERE x.unidade_id = u.id);

INSERT INTO periodos_horarios (unidade_id, turno_id, ordem, hora_inicio, hora_fim, dias_semana, excepcional, ativo)
SELECT t.unidade_id, t.id, p.ordem, p.ini::time, p.fim::time, '{0,1,2,3,4}', false, true
FROM turnos t
JOIN unidades u ON u.id = t.unidade_id AND u.codigo IN ('BEIRA-MAR', 'PORTO')
JOIN (VALUES
  ('M', 1, '07:30', '08:25'), ('M', 2, '08:25', '09:20'), ('M', 3, '09:40', '10:35'), ('M', 4, '10:35', '11:30'),
  ('T', 1, '13:30', '14:25'), ('T', 2, '14:25', '15:20'), ('T', 3, '15:40', '16:35'), ('T', 4, '16:35', '17:30'),
  ('N', 1, '18:20', '19:10'), ('N', 2, '19:10', '20:00'), ('N', 3, '20:10', '21:00'), ('N', 4, '21:00', '21:50')
) AS p(turno, ordem, ini, fim) ON p.turno = t.codigo
WHERE NOT EXISTS (SELECT 1 FROM periodos_horarios x WHERE x.turno_id = t.id);

-- Regras de composição das aulas (padrão da instituição), se ainda não registradas
INSERT INTO configuracoes (chave, valor, descricao) VALUES ('regras_aula', '{"turno_inteiro": true, "contagem": "hora_aula"}'::jsonb,
  'Composição das aulas: com ''turno inteiro'', cada UC ocupa todas as aulas do turno no dia; aula parcial só no fechamento da carga horária (dividindo o turno com outra UC que também esteja fechando). ''hora_aula'': cada aula conta 1 h de carga horária.')
ON CONFLICT (chave) DO NOTHING;

-- Segurança: mesma política das demais tabelas (RLS e sem acesso pela Data API pública)
ALTER TABLE public.areas ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.areas FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.areas FROM authenticated';
  END IF;
END $$;
"""

TABELAS_COM_AREA = ("cursos", "turmas", "instrutores", "ambientes")


def upgrade():
    op.create_table(
        "areas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("unidade_id", sa.Integer(), sa.ForeignKey("unidades.id"), nullable=False),
        sa.Column("codigo", sa.String(length=40), nullable=False, unique=True),
        sa.Column("nome", sa.String(length=100), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_areas_unidade_id", "areas", ["unidade_id"])
    for t in TABELAS_COM_AREA:
        op.add_column(t, sa.Column("area_id", sa.Integer(), sa.ForeignKey("areas.id"), nullable=True))
        op.create_index(f"ix_{t}_area_id", t, ["area_id"])
    op.execute(DADOS_SQL.strip().rstrip(";"))


def downgrade():
    for t in TABELAS_COM_AREA:
        op.drop_index(f"ix_{t}_area_id", table_name=t)
        op.drop_column(t, "area_id")
    op.drop_index("ix_areas_unidade_id", table_name="areas")
    op.drop_table("areas")
    # unidades, turnos e configurações inseridos são mantidos (dados da instituição)
