-- Atualização 0016 -> 0017: termo de horas mensal dos instrutores horistas (horas de aula do mês e outras
-- ocupações; muda a cada mês). Só cria a tabela. Cole no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0016 -> 0017

CREATE TABLE termos_horas (
    id SERIAL NOT NULL, 
    instrutor_id INTEGER NOT NULL, 
    mes DATE NOT NULL, 
    horas_aula NUMERIC(6, 2) DEFAULT 0 NOT NULL, 
    horas_outras NUMERIC(6, 2) DEFAULT 0 NOT NULL, 
    observacao TEXT, 
    atualizado_por_id INTEGER, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now(), 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now(), 
    PRIMARY KEY (id), 
    UNIQUE (instrutor_id, mes), 
    CHECK (horas_aula >= 0), 
    CHECK (horas_outras >= 0), 
    FOREIGN KEY(instrutor_id) REFERENCES instrutores (id) ON DELETE CASCADE, 
    FOREIGN KEY(atualizado_por_id) REFERENCES usuarios (id) ON DELETE SET NULL
);

CREATE INDEX ix_termos_horas_instrutor_id ON termos_horas (instrutor_id);

ALTER TABLE public.termos_horas ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.termos_horas FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.termos_horas FROM authenticated';
  END IF;
END $$;

UPDATE alembic_version SET version_num='0017' WHERE alembic_version.version_num = '0016';

COMMIT;

