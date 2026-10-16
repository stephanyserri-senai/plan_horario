-- Atualização 0008 -> 0009: nível do instrutor (básico = AIB e qualificações; técnico = todas as modalidades) e dias EAD da turma (turmas 80-20).
-- Não destrutiva: todos os instrutores começam como técnico e nenhuma turma tem dia EAD. Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0008 -> 0009

ALTER TABLE instrutores ADD COLUMN nivel VARCHAR(10) DEFAULT 'tecnico' NOT NULL;

ALTER TABLE instrutores ADD CONSTRAINT instrutores_nivel_check CHECK (nivel in ('basico','tecnico'));

ALTER TABLE turmas ADD COLUMN dias_ead INTEGER[] DEFAULT '{}' NOT NULL;

UPDATE alembic_version SET version_num='0009' WHERE alembic_version.version_num = '0008';

COMMIT;

