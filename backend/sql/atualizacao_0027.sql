-- Atualização 0026 -> 0027: instrutor com gestor imediato e uniforme (jaleco em 3 referências, blusa e botina).
-- Só acrescenta colunas. Cole no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0026 -> 0027

ALTER TABLE instrutores ADD COLUMN gestor_imediato VARCHAR(120);

ALTER TABLE instrutores ADD COLUMN jaleco_np VARCHAR(10);

ALTER TABLE instrutores ADD COLUMN jaleco_pmg VARCHAR(10);

ALTER TABLE instrutores ADD COLUMN jaleco_num VARCHAR(10);

ALTER TABLE instrutores ADD COLUMN tamanho_blusa VARCHAR(10);

ALTER TABLE instrutores ADD COLUMN numero_botina VARCHAR(10);

UPDATE alembic_version SET version_num='0027' WHERE alembic_version.version_num = '0026';

COMMIT;

