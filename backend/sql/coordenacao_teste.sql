-- COORDENAÇÃO DE TESTE — somente para homologação.
-- Login: coordenacao.teste   Senha: coord@123   (a senha fica guardada só como hash bcrypt)
-- Perfil coordenador: tudo o que o planejador faz + aprovar/recusar as solicitações de folga e substituição dos instrutores.
-- Requer a atualização 0010 (perfil coordenador). Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run. Pode rodar mais de uma vez.
-- (Modo Supabase Auth: crie também o usuário no painel do Supabase — Authentication → Users → Add user — com um e-mail
--  e esta senha, e troque abaixo 'coordenacao.teste' por esse e-mail.)
-- REMOVER depois dos testes:
--   DELETE FROM usuarios WHERE email = 'coordenacao.teste' AND nome LIKE 'Coordenação de TESTE%';
--   (se der erro por histórico vinculado: UPDATE usuarios SET ativo = false, senha_hash = '!removido' WHERE email = 'coordenacao.teste';)

INSERT INTO usuarios (nome, email, senha_hash, perfil, acesso_global, ativo)
VALUES ('Coordenação de TESTE (remover antes da produção)', 'coordenacao.teste', '$2b$12$9E0rP1w//L25Q8M592N83uSmz7CjvTd71hjZfIxffIWy9TuEQUFH6', 'coordenador', true, true)
ON CONFLICT (email) DO UPDATE SET perfil = 'coordenador', ativo = true, senha_hash = EXCLUDED.senha_hash
  WHERE usuarios.nome LIKE 'Coordenação de TESTE%';

-- Conferência
SELECT nome, email AS login, perfil, ativo FROM usuarios WHERE email = 'coordenacao.teste';
