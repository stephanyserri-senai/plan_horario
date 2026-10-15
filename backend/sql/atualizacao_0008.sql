-- Atualização 0007 -> 0008: perfis de usuário = administrador, planejador, instrutor e observador (somente acompanhar).
-- Nenhum usuário é apagado: coordenador passa a planejador; gestor e consulta passam a observador.
-- Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0007 -> 0008

ALTER TABLE usuarios DROP CONSTRAINT IF EXISTS usuarios_perfil_check;

UPDATE usuarios SET perfil = 'planejador' WHERE perfil = 'coordenador';

UPDATE usuarios SET perfil = 'observador' WHERE perfil IN ('gestor', 'consulta');

ALTER TABLE usuarios ADD CONSTRAINT usuarios_perfil_check CHECK (perfil in ('administrador','planejador','instrutor','observador'));

DELETE FROM permissoes_perfil WHERE perfil IN ('coordenador', 'gestor', 'consulta');

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('observador', 'cadastros.ler') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('observador', 'alocacoes.ler') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('observador', 'indicadores.ler') ON CONFLICT DO NOTHING;

INSERT INTO permissoes_perfil (perfil, acao) VALUES ('observador', 'exportacao.executar') ON CONFLICT DO NOTHING;

UPDATE alembic_version SET version_num='0008' WHERE alembic_version.version_num = '0007';

COMMIT;

