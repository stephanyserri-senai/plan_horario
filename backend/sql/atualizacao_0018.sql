-- Atualização 0017 -> 0018: dias da semana do termo de horas do horista (o termo é ajustável por urgência,
-- com a concordância do instrutor). Só acrescenta a coluna. Cole no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0017 -> 0018

ALTER TABLE termos_horas ADD COLUMN dias_semana INTEGER[];

UPDATE alembic_version SET version_num='0018' WHERE alembic_version.version_num = '0017';

COMMIT;

