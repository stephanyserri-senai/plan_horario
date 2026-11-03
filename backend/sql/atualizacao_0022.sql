-- Atualização 0021 -> 0022: troca de senha obrigatória no primeiro acesso (usuarios.trocar_senha). Só acrescenta a
-- coluna. Cole no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0021 -> 0022

ALTER TABLE usuarios ADD COLUMN trocar_senha BOOLEAN DEFAULT false NOT NULL;

UPDATE alembic_version SET version_num='0022' WHERE alembic_version.version_num = '0021';

COMMIT;

