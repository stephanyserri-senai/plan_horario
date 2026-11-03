-- Atualização 0023 -> 0024: agendamento de ambientes (salas e laboratórios) pelos instrutores, confirmado pela
-- supervisão. Só cria a tabela. Cole no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0023 -> 0024

CREATE TABLE agendamentos_ambiente (
    id SERIAL NOT NULL, 
    ambiente_id INTEGER NOT NULL, 
    instrutor_id INTEGER, 
    solicitado_por_id INTEGER, 
    turma_id INTEGER, 
    turno_id INTEGER, 
    data DATE NOT NULL, 
    inicio TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    fim TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
    finalidade TEXT NOT NULL, 
    participantes INTEGER, 
    status VARCHAR(20) DEFAULT 'pendente' NOT NULL, 
    resposta TEXT, 
    decidido_por_id INTEGER, 
    decidido_em TIMESTAMP WITHOUT TIME ZONE, 
    bloqueio_id INTEGER, 
    criado_em TIMESTAMP WITHOUT TIME ZONE DEFAULT now(), 
    PRIMARY KEY (id), 
    CONSTRAINT agendamentos_status_check CHECK (status in ('pendente','confirmado','recusado','cancelado')), 
    CONSTRAINT agendamentos_periodo_check CHECK (fim > inicio), 
    FOREIGN KEY(ambiente_id) REFERENCES ambientes (id) ON DELETE CASCADE, 
    FOREIGN KEY(instrutor_id) REFERENCES instrutores (id) ON DELETE CASCADE, 
    FOREIGN KEY(solicitado_por_id) REFERENCES usuarios (id) ON DELETE SET NULL, 
    FOREIGN KEY(turma_id) REFERENCES turmas (id) ON DELETE SET NULL, 
    FOREIGN KEY(turno_id) REFERENCES turnos (id) ON DELETE SET NULL, 
    FOREIGN KEY(decidido_por_id) REFERENCES usuarios (id) ON DELETE SET NULL, 
    FOREIGN KEY(bloqueio_id) REFERENCES bloqueios (id) ON DELETE SET NULL
);

CREATE INDEX ix_agendamentos_ambiente_ambiente_id ON agendamentos_ambiente (ambiente_id);

CREATE INDEX ix_agendamentos_ambiente_instrutor_id ON agendamentos_ambiente (instrutor_id);

CREATE INDEX ix_agendamentos_ambiente_data ON agendamentos_ambiente (data);

ALTER TABLE public.agendamentos_ambiente ENABLE ROW LEVEL SECURITY;
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.agendamentos_ambiente FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.agendamentos_ambiente FROM authenticated';
  END IF;
END $$;

UPDATE alembic_version SET version_num='0024' WHERE alembic_version.version_num = '0023';

COMMIT;

