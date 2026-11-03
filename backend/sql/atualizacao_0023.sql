-- Atualização 0022 -> 0023: versões do mesmo curso por público (PAGANTE, SEDU, AIT...): o público aceita até 30
-- caracteres e a versão passa a ser única por curso + versão + público. Não apaga nada. Cole no SQL Editor e clique em Run.
BEGIN;

-- Running upgrade 0022 -> 0023

ALTER TABLE matrizes_curriculares ALTER COLUMN tipo_oferta TYPE VARCHAR(30);

ALTER TABLE matrizes_curriculares DROP CONSTRAINT IF EXISTS matrizes_curriculares_curso_id_versao_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_matriz_curso_versao_publico ON matrizes_curriculares (curso_id, versao, (coalesce(tipo_oferta, '')));

UPDATE alembic_version SET version_num='0023' WHERE alembic_version.version_num = '0022';

COMMIT;

