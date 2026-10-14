-- Atualização 0004 -> 0005: portal do instrutor (perfil instrutor, vínculo usuário × instrutor e observações sobre turmas/UCs).
-- Não destrutiva. Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0004 -> 0005

ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS usuarios_perfil_check;

ALTER TABLE usuarios ADD CONSTRAINT usuarios_perfil_check CHECK (perfil in ('administrador','planejador','coordenador','gestor','consulta','instrutor'));

ALTER TABLE usuarios ADD COLUMN instrutor_id INTEGER;

ALTER TABLE usuarios ADD FOREIGN KEY(instrutor_id) REFERENCES instrutores (id) ON DELETE SET NULL;

ALTER TABLE usuarios ADD CONSTRAINT usuarios_instrutor_id_key UNIQUE (instrutor_id);

ALTER TABLE instrutores ADD COLUMN atualizado_pelo_instrutor_em TIMESTAMP WITHOUT TIME ZONE;

CREATE TABLE observacoes_instrutor (
    id SERIAL NOT NULL, 
    instrutor_id INTEGER NOT NULL, 
    turma_uc_id INTEGER, 
    tipo VARCHAR(30) NOT NULL, 
    texto TEXT NOT NULL, 
    status VARCHAR(20) DEFAULT 'nova' NOT NULL, 
    resposta TEXT, 
    respondido_por_id INTEGER, 
    respondido_em TIMESTAMP WITHOUT TIME ZONE, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT observacoes_instrutor_status_check CHECK (status in ('nova','lida','resolvida')), 
    FOREIGN KEY(instrutor_id) REFERENCES instrutores (id) ON DELETE CASCADE, 
    FOREIGN KEY(turma_uc_id) REFERENCES turma_uc (id) ON DELETE CASCADE, 
    FOREIGN KEY(respondido_por_id) REFERENCES usuarios (id) ON DELETE SET NULL
);

CREATE INDEX ix_observacoes_instrutor_instrutor_id ON observacoes_instrutor (instrutor_id);

CREATE INDEX ix_observacoes_instrutor_turma_uc_id ON observacoes_instrutor (turma_uc_id);

ALTER TABLE public.observacoes_instrutor ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.observacoes_instrutor FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.observacoes_instrutor FROM authenticated';
  END IF;
END $$;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('instrutor', 'portal.instrutor') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('administrador', 'observacoes.gerenciar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('planejador', 'observacoes.gerenciar') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('coordenador', 'observacoes.gerenciar') ON CONFLICT DO NOTHING;

UPDATE alembic_version SET version_num='0005' WHERE alembic_version.version_num = '0004';

COMMIT;

