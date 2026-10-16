-- Atualização 0009 -> 0010: perfil COORDENADOR (planejador + aprova solicitações), solicitações de folga/substituição dos instrutores,
-- UC transversal ou técnica, competência 'sim' / 'em partes' (sob supervisão vira em partes) e turno de SÁBADO (09:00–13:00) em cada unidade.
-- Não destrutiva. Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0009 -> 0010

ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS usuarios_perfil_check;

ALTER TABLE usuarios ADD CONSTRAINT usuarios_perfil_check CHECK (perfil in ('administrador','planejador','coordenador','instrutor','observador'));

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'cadastros.ler') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'cadastros.editar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'alocacoes.ler') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'alocacoes.editar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'cenarios.criar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'cenarios.editar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'otimizacao.executar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'simulacao.executar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'indicadores.ler') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'importacao.executar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'exportacao.executar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'dados_pessoais.ler') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'observacoes.gerenciar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'solicitacoes.aprovar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'solicitacoes.aprovar') ON CONFLICT DO NOTHING;

CREATE TABLE solicitacoes_instrutor (
    id SERIAL NOT NULL, 
    instrutor_id INTEGER NOT NULL, 
    tipo VARCHAR(20) NOT NULL, 
    data_inicio DATE NOT NULL, 
    data_fim DATE NOT NULL, 
    turnos INTEGER[] DEFAULT '{}' NOT NULL, 
    justificativa TEXT NOT NULL, 
    status VARCHAR(20) DEFAULT 'pendente' NOT NULL, 
    resposta TEXT, 
    decidido_por_id INTEGER, 
    decidido_em TIMESTAMP WITHOUT TIME ZONE, 
    efeitos JSONB, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT solicitacoes_tipo_check CHECK (tipo in ('folga','substituicao')), 
    CONSTRAINT solicitacoes_status_check CHECK (status in ('pendente','aprovada','recusada','cancelada')), 
    CONSTRAINT solicitacoes_datas_check CHECK (data_fim >= data_inicio), 
    FOREIGN KEY(instrutor_id) REFERENCES instrutores (id) ON DELETE CASCADE, 
    FOREIGN KEY(decidido_por_id) REFERENCES usuarios (id) ON DELETE SET NULL
);

CREATE INDEX ix_solicitacoes_instrutor_instrutor_id ON solicitacoes_instrutor (instrutor_id);

ALTER TABLE public.solicitacoes_instrutor ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.solicitacoes_instrutor FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.solicitacoes_instrutor FROM authenticated';
  END IF;
END $$;

ALTER TABLE unidades_curriculares ADD COLUMN categoria VARCHAR(12) DEFAULT 'tecnica' NOT NULL;

ALTER TABLE unidades_curriculares ADD CONSTRAINT ucs_categoria_check CHECK (categoria in ('tecnica','transversal'));

ALTER TABLE competencias_instrutores DROP CONSTRAINT IF EXISTS competencias_instrutores_nivel_check;

ALTER TABLE competencias_instrutores DROP CONSTRAINT IF EXISTS ck_competencias_instrutores_nivel;

DO $$ DECLARE r record; BEGIN
      FOR r IN SELECT conname FROM pg_constraint WHERE conrelid = 'competencias_instrutores'::regclass AND contype = 'c'
               AND strpos(pg_get_constraintdef(oid), 'supervisionado') > 0 LOOP
        EXECUTE 'ALTER TABLE competencias_instrutores DROP CONSTRAINT ' || quote_ident(r.conname);
      END LOOP; END $$;

UPDATE competencias_instrutores SET nivel = 'parcial' WHERE nivel = 'supervisionado';

ALTER TABLE competencias_instrutores ADD CONSTRAINT competencias_instrutores_nivel_check CHECK (nivel in ('pleno','parcial','em_formacao'));

DO $$ DECLARE u record; t_id int; BEGIN
      FOR u IN SELECT id FROM unidades LOOP
        IF NOT EXISTS (SELECT 1 FROM turnos WHERE unidade_id = u.id AND codigo = 'S') THEN
          INSERT INTO turnos (unidade_id, codigo, nome, hora_inicio, hora_fim, ordem, ativo, criado_em, atualizado_em)
          VALUES (u.id, 'S', 'Sábado', '09:00', '13:00', 4, true, now(), now()) RETURNING id INTO t_id;
          INSERT INTO periodos_horarios (unidade_id, turno_id, ordem, hora_inicio, hora_fim, dias_semana, excepcional, ativo, criado_em, atualizado_em)
          SELECT u.id, t_id, v.ordem, v.ini::time, v.fim::time, '{5}', false, true, now(), now() FROM (VALUES (1, '09:00', '09:55'), (2, '09:55', '10:50'), (3, '11:10', '12:05'), (4, '12:05', '13:00')) AS v(ordem, ini, fim);
        END IF;
        IF EXISTS (SELECT 1 FROM horarios_funcionamento WHERE unidade_id = u.id)
           AND NOT EXISTS (SELECT 1 FROM horarios_funcionamento WHERE unidade_id = u.id AND dia_semana = 5) THEN
          INSERT INTO horarios_funcionamento (unidade_id, dia_semana, hora_inicio, hora_fim, ativo) VALUES (u.id, 5, '09:00', '13:00', true);
        END IF;
      END LOOP;
      UPDATE calendarios SET dias_letivos = array_append(dias_letivos, 5) WHERE NOT (5 = ANY(dias_letivos));
    END $$;

UPDATE alembic_version SET version_num='0010' WHERE alembic_version.version_num = '0009';

COMMIT;

