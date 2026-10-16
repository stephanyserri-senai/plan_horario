-- Atualização 0012 -> 0013: EPIs por curso (quantidade por aluno e antecedência) e controle por turma
-- (prazo, comprado/separado, entregue). Só cria tabelas. Cole no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0012 -> 0013

CREATE TABLE epis_curso (
    id SERIAL NOT NULL, 
    curso_id INTEGER NOT NULL, 
    nome VARCHAR(150) NOT NULL, 
    quantidade_por_aluno INTEGER DEFAULT 1 NOT NULL, 
    antecedencia_dias INTEGER DEFAULT 15 NOT NULL, 
    observacao TEXT, 
    ativo BOOLEAN DEFAULT true NOT NULL, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now(), 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now(), 
    PRIMARY KEY (id), 
    FOREIGN KEY(curso_id) REFERENCES cursos (id) ON DELETE CASCADE
);

CREATE INDEX ix_epis_curso_curso_id ON epis_curso (curso_id);

CREATE TABLE epis_turma (
    id SERIAL NOT NULL, 
    turma_id INTEGER NOT NULL, 
    epi_curso_id INTEGER, 
    nome VARCHAR(150) NOT NULL, 
    quantidade INTEGER DEFAULT 0 NOT NULL, 
    prazo DATE, 
    providenciado BOOLEAN DEFAULT false NOT NULL, 
    providenciado_em TIMESTAMP WITHOUT TIME ZONE, 
    entregue BOOLEAN DEFAULT false NOT NULL, 
    entregue_em TIMESTAMP WITHOUT TIME ZONE, 
    atualizado_por_id INTEGER, 
    observacao TEXT, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now(), 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now(), 
    PRIMARY KEY (id), 
    UNIQUE (turma_id, epi_curso_id), 
    FOREIGN KEY(turma_id) REFERENCES turmas (id) ON DELETE CASCADE, 
    FOREIGN KEY(epi_curso_id) REFERENCES epis_curso (id) ON DELETE SET NULL
);

CREATE INDEX ix_epis_turma_turma_id ON epis_turma (turma_id);

ALTER TABLE public.epis_curso ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.epis_turma ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.epis_curso, public.epis_turma FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.epis_curso, public.epis_turma FROM authenticated';
  END IF;
END $$;

UPDATE alembic_version SET version_num='0013' WHERE alembic_version.version_num = '0012';

COMMIT;

