-- Atualização 0013 -> 0014: cursos que não precisam de EPI (coluna cursos.dispensa_epi, padrão falso).
-- Só acrescenta a coluna. Cole no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0013 -> 0014

ALTER TABLE cursos ADD COLUMN dispensa_epi BOOLEAN DEFAULT false NOT NULL;

UPDATE alembic_version SET version_num='0014' WHERE alembic_version.version_num = '0013';

COMMIT;

