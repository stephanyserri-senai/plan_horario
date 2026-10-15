-- Atualização 0006 -> 0007: modalidade do instrutor (mensalista ou horista). Os turnos de planejamento (PL) e projeto (PJ) usam a tabela de bloqueios.
-- Não destrutiva (todos os instrutores começam como mensalista). Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0006 -> 0007

ALTER TABLE instrutores ADD COLUMN modalidade VARCHAR(12) DEFAULT 'mensalista' NOT NULL;

ALTER TABLE instrutores ADD CONSTRAINT instrutores_modalidade_check CHECK (modalidade in ('mensalista','horista'));

UPDATE alembic_version SET version_num='0007' WHERE alembic_version.version_num = '0006';

COMMIT;

