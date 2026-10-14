-- Atualização 0003 -> 0004: exceção justificada para regras acadêmicas (instrutor/laboratório de outra área, sem competência).
-- Não destrutiva. Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0003 -> 0004

ALTER TABLE instrutores ADD COLUMN todas_areas BOOLEAN DEFAULT false NOT NULL;

ALTER TABLE ambientes ADD COLUMN todas_areas BOOLEAN DEFAULT false NOT NULL;

CREATE TABLE instrutor_areas (
    instrutor_id INTEGER NOT NULL, 
    area_id INTEGER NOT NULL, 
    PRIMARY KEY (instrutor_id, area_id), 
    FOREIGN KEY(instrutor_id) REFERENCES instrutores (id) ON DELETE CASCADE, 
    FOREIGN KEY(area_id) REFERENCES areas (id)
);

CREATE TABLE ambiente_areas (
    ambiente_id INTEGER NOT NULL, 
    area_id INTEGER NOT NULL, 
    PRIMARY KEY (ambiente_id, area_id), 
    FOREIGN KEY(ambiente_id) REFERENCES ambientes (id) ON DELETE CASCADE, 
    FOREIGN KEY(area_id) REFERENCES areas (id)
);

ALTER TABLE public.instrutor_areas ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ambiente_areas ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.instrutor_areas, public.ambiente_areas FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.instrutor_areas, public.ambiente_areas FROM authenticated';
  END IF;
END $$;

ALTER TABLE excecoes_autorizadas DROP CONSTRAINT IF EXISTS excecoes_autorizadas_tipo_check;

ALTER TABLE excecoes_autorizadas ADD CONSTRAINT excecoes_autorizadas_tipo_check CHECK (tipo IN ('feriado_bloqueio', 'carga_horaria', 'regra_academica'));

UPDATE alembic_version SET version_num='0004' WHERE alembic_version.version_num = '0003';

COMMIT;

