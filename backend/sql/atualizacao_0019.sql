-- Atualização 0018 -> 0019: UC presencial ou EAD (cursos.preve_ead e unidades_curriculares.modalidade; tudo o que
-- existe continua presencial). Só acrescenta colunas. Cole no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0018 -> 0019

ALTER TABLE cursos ADD COLUMN preve_ead BOOLEAN DEFAULT false NOT NULL;

ALTER TABLE unidades_curriculares ADD COLUMN modalidade VARCHAR(12) DEFAULT 'presencial' NOT NULL;

ALTER TABLE unidades_curriculares ADD CONSTRAINT ucs_modalidade_check CHECK (modalidade in ('presencial','ead'));

UPDATE alembic_version SET version_num='0019' WHERE alembic_version.version_num = '0018';

COMMIT;

