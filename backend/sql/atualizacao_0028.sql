-- Atualização 0027 -> 0028: UC com carga TOTAL, EaD e PRESENCIAL e modalidade presencial, EAD ou semipresencial.
-- Preserva os dados: UC EAD = tudo EaD; as demais = tudo presencial, marcadas com divisao_confirmada = false (a conferir).
-- Cole no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0027 -> 0028

ALTER TABLE unidades_curriculares ADD COLUMN carga_horaria_ead INTEGER;

ALTER TABLE unidades_curriculares ADD COLUMN carga_horaria_presencial INTEGER;

ALTER TABLE unidades_curriculares ADD COLUMN divisao_confirmada BOOLEAN DEFAULT false NOT NULL;

UPDATE unidades_curriculares SET carga_horaria_ead = carga_horaria_total, carga_horaria_presencial = 0, divisao_confirmada = true WHERE modalidade = 'ead' AND carga_horaria_ead IS NULL;

UPDATE unidades_curriculares SET carga_horaria_ead = 0, carga_horaria_presencial = carga_horaria_total WHERE carga_horaria_ead IS NULL;

ALTER TABLE unidades_curriculares ALTER COLUMN carga_horaria_ead SET NOT NULL;

ALTER TABLE unidades_curriculares ALTER COLUMN carga_horaria_ead SET DEFAULT '0';

ALTER TABLE unidades_curriculares ALTER COLUMN carga_horaria_presencial SET NOT NULL;

ALTER TABLE unidades_curriculares ALTER COLUMN modalidade TYPE VARCHAR(14);

ALTER TABLE unidades_curriculares DROP CONSTRAINT ucs_modalidade_check;

ALTER TABLE unidades_curriculares ADD CONSTRAINT ucs_modalidade_check CHECK (modalidade in ('presencial','ead','semipresencial'));

ALTER TABLE unidades_curriculares ADD CONSTRAINT ucs_cargas_nao_negativas CHECK (carga_horaria_ead >= 0 AND carga_horaria_presencial >= 0);

ALTER TABLE unidades_curriculares ADD CONSTRAINT ucs_cargas_somam_total CHECK (carga_horaria_ead + carga_horaria_presencial = carga_horaria_total);

UPDATE alembic_version SET version_num='0028' WHERE alembic_version.version_num = '0027';

COMMIT;

