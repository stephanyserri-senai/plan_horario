-- Atualização 0002 -> 0003: unidades Beira Mar e Porto, áreas tecnológicas, turnos oficiais e área nos cadastros.
-- Não destrutiva: só cria a tabela de áreas, adiciona colunas anuláveis e insere o que ainda não existir.
-- Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0002 -> 0003

CREATE TABLE areas (
    id SERIAL NOT NULL, 
    unidade_id INTEGER NOT NULL, 
    codigo VARCHAR(40) NOT NULL, 
    nome VARCHAR(100) NOT NULL, 
    ativo BOOLEAN NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(unidade_id) REFERENCES unidades (id), 
    UNIQUE (codigo)
);

CREATE INDEX ix_areas_unidade_id ON areas (unidade_id);

ALTER TABLE cursos ADD COLUMN area_id INTEGER;

ALTER TABLE cursos ADD FOREIGN KEY(area_id) REFERENCES areas (id);

CREATE INDEX ix_cursos_area_id ON cursos (area_id);

ALTER TABLE turmas ADD COLUMN area_id INTEGER;

ALTER TABLE turmas ADD FOREIGN KEY(area_id) REFERENCES areas (id);

CREATE INDEX ix_turmas_area_id ON turmas (area_id);

ALTER TABLE instrutores ADD COLUMN area_id INTEGER;

ALTER TABLE instrutores ADD FOREIGN KEY(area_id) REFERENCES areas (id);

CREATE INDEX ix_instrutores_area_id ON instrutores (area_id);

ALTER TABLE ambientes ADD COLUMN area_id INTEGER;

ALTER TABLE ambientes ADD FOREIGN KEY(area_id) REFERENCES areas (id);

CREATE INDEX ix_ambientes_area_id ON ambientes (area_id);

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

UPDATE alembic_version SET version_num='0003' WHERE alembic_version.version_num = '0002';

COMMIT;

