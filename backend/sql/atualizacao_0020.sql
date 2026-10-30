-- Atualização 0019 -> 0020: termo de horas por dia e turno (agenda do mês: em cada dia, os turnos com aula ou
-- planejamento). Só acrescenta a coluna; os termos existentes continuam valendo. Cole no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0019 -> 0020

ALTER TABLE termos_horas ADD COLUMN agenda JSONB;

UPDATE alembic_version SET version_num='0020' WHERE alembic_version.version_num = '0019';

COMMIT;

