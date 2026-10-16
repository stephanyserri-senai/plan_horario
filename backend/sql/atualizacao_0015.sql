-- Atualização 0014 -> 0015: turmas modulares (módulos e módulo em curso; o código leva o módulo) e exceção de
-- reposição aos sábados. Não destrutiva. Cole no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0014 -> 0015

ALTER TABLE turmas ADD COLUMN modulos INTEGER;

ALTER TABLE turmas ADD COLUMN modulo_atual INTEGER;

ALTER TABLE excecoes_autorizadas DROP CONSTRAINT excecoes_autorizadas_tipo_check;

ALTER TABLE excecoes_autorizadas ADD CONSTRAINT excecoes_autorizadas_tipo_check CHECK (tipo in ('feriado_bloqueio','carga_horaria','regra_academica','reposicao'));

UPDATE alembic_version SET version_num='0015' WHERE alembic_version.version_num = '0014';

COMMIT;

