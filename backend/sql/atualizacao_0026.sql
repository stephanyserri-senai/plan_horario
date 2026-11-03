-- Atualização 0025 -> 0026: solicitação de diárias (recursos extras) para instrutores em eventos e projetos,
-- registrada e aprovada pela supervisão. Só cria a tabela. Cole no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0025 -> 0026

CREATE TABLE solicitacoes_diarias (
    id SERIAL NOT NULL, 
    instrutor_id INTEGER NOT NULL, 
    motivo VARCHAR(20) NOT NULL, 
    titulo VARCHAR(200) NOT NULL, 
    descricao TEXT, 
    destino VARCHAR(200), 
    data_inicio DATE NOT NULL, 
    data_fim DATE NOT NULL, 
    quantidade NUMERIC(5, 1) NOT NULL, 
    valor_unitario NUMERIC(10, 2), 
    outros_recursos TEXT, 
    centro_custo VARCHAR(60), 
    status VARCHAR(20) DEFAULT 'solicitada' NOT NULL, 
    resposta TEXT, 
    solicitado_por_id INTEGER, 
    decidido_por_id INTEGER, 
    decidido_em TIMESTAMP WITHOUT TIME ZONE, 
    pago_em DATE, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT diaria_status_check CHECK (status in ('solicitada','aprovada','paga','recusada','cancelada')), 
    CONSTRAINT diaria_motivo_check CHECK (motivo in ('evento','projeto','outro')), 
    CONSTRAINT diaria_quantidade_check CHECK (quantidade > 0), 
    CONSTRAINT diaria_periodo_check CHECK (data_fim >= data_inicio), 
    FOREIGN KEY(instrutor_id) REFERENCES instrutores (id) ON DELETE CASCADE, 
    FOREIGN KEY(solicitado_por_id) REFERENCES usuarios (id) ON DELETE SET NULL, 
    FOREIGN KEY(decidido_por_id) REFERENCES usuarios (id) ON DELETE SET NULL
);

CREATE INDEX ix_solicitacoes_diarias_instrutor_id ON solicitacoes_diarias (instrutor_id);

ALTER TABLE public.solicitacoes_diarias ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.solicitacoes_diarias FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.solicitacoes_diarias FROM authenticated';
  END IF;
END $$;

UPDATE alembic_version SET version_num='0026' WHERE alembic_version.version_num = '0025';

COMMIT;

