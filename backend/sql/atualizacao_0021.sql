-- Atualização 0020 -> 0021: pedidos de impressão dos instrutores (pelo portal, até a quinta-feira da semana anterior
-- ao uso), atendidos pela coordenação. Só cria a tabela. Cole no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0020 -> 0021

CREATE TABLE solicitacoes_impressao (
    id SERIAL NOT NULL, 
    instrutor_id INTEGER NOT NULL, 
    turma_id INTEGER, 
    titulo VARCHAR(200) NOT NULL, 
    descricao TEXT, 
    arquivo_url VARCHAR(500), 
    arquivo_nome VARCHAR(200), 
    arquivo_tamanho INTEGER, 
    arquivo_pdf BYTEA, 
    copias INTEGER NOT NULL, 
    paginas INTEGER, 
    frente_verso BOOLEAN DEFAULT false NOT NULL, 
    colorido BOOLEAN DEFAULT false NOT NULL, 
    data_uso DATE NOT NULL, 
    prazo DATE NOT NULL, 
    status VARCHAR(20) DEFAULT 'pendente' NOT NULL, 
    resposta TEXT, 
    atendido_por_id INTEGER, 
    atendido_em TIMESTAMP WITHOUT TIME ZONE, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now(), 
    PRIMARY KEY (id), 
    CONSTRAINT impressao_status_check CHECK (status in ('pendente','em_producao','pronta','entregue','recusada','cancelada')), 
    CONSTRAINT impressao_copias_check CHECK (copias > 0), 
    FOREIGN KEY(instrutor_id) REFERENCES instrutores (id) ON DELETE CASCADE, 
    FOREIGN KEY(turma_id) REFERENCES turmas (id) ON DELETE SET NULL, 
    FOREIGN KEY(atendido_por_id) REFERENCES usuarios (id) ON DELETE SET NULL
);

CREATE INDEX ix_solicitacoes_impressao_instrutor_id ON solicitacoes_impressao (instrutor_id);

ALTER TABLE public.solicitacoes_impressao ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.solicitacoes_impressao FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.solicitacoes_impressao FROM authenticated';
  END IF;
END $$;

UPDATE alembic_version SET version_num='0021' WHERE alembic_version.version_num = '0020';

COMMIT;

