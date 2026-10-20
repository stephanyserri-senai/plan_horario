-- Atualização 0015 -> 0016: PDI dos instrutores (UCs a aprender/completar e certificações, com prioridade, prazo
-- e situação), a partir do índice de aderência. Só cria a tabela. Cole no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0015 -> 0016

CREATE TABLE pdi_itens (
    id SERIAL NOT NULL, 
    instrutor_id INTEGER NOT NULL, 
    curso_id INTEGER, 
    uc_codigo VARCHAR(30) NOT NULL, 
    uc_nome VARCHAR(200) NOT NULL, 
    tipo VARCHAR(20) DEFAULT 'uc' NOT NULL, 
    certificacao VARCHAR(200), 
    prioridade VARCHAR(10), 
    prazo DATE, 
    situacao VARCHAR(20) DEFAULT 'planejado' NOT NULL, 
    observacao TEXT, 
    concluido_em DATE, 
    criado_por_id INTEGER, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now(), 
    atualizado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now(), 
    PRIMARY KEY (id), 
    CONSTRAINT pdi_itens_tipo_check CHECK (tipo in ('uc','completar','certificacao')), 
    CONSTRAINT pdi_itens_situacao_check CHECK (situacao in ('planejado','em_andamento','concluido','cancelado')), 
    FOREIGN KEY(instrutor_id) REFERENCES instrutores (id) ON DELETE CASCADE, 
    FOREIGN KEY(curso_id) REFERENCES cursos (id) ON DELETE SET NULL, 
    FOREIGN KEY(criado_por_id) REFERENCES usuarios (id) ON DELETE SET NULL
);

CREATE INDEX ix_pdi_itens_instrutor_id ON pdi_itens (instrutor_id);

ALTER TABLE public.pdi_itens ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.pdi_itens FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.pdi_itens FROM authenticated';
  END IF;
END $$;

UPDATE alembic_version SET version_num='0016' WHERE alembic_version.version_num = '0015';

COMMIT;

