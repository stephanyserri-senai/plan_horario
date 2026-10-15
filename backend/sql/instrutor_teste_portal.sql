-- INSTRUTOR DE TESTE DO PORTAL — somente para homologação.
-- Login: instrutor.teste   Senha: instrutor@123   (a senha fica guardada só como hash bcrypt)
-- Requer a atualização 0005. Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run. Pode rodar mais de uma vez.
-- Cria um cadastro de instrutor de TESTE (Beira Mar, ENERGIAS, manhã e tarde de segunda a sexta), o usuário ligado a ele
-- e um aviso de boas-vindas. Para ver turmas no portal, atribua aulas a ele na grade (ou use "Substituir instrutor").
-- REMOVER depois dos testes (desfaça antes as aulas atribuídas a ele):
--   DELETE FROM usuarios WHERE email = 'instrutor.teste';
--   DELETE FROM instrutores WHERE matricula = 'TESTE-PORTAL';

INSERT INTO instrutores (matricula, nome, unidade_id, area_id, todas_areas, carga_horaria_contratual, limite_ch_letiva, max_horas_dia,
                         intervalo_minimo_h, situacao, ativo, areas_competencia)
SELECT 'TESTE-PORTAL', 'Instrutor de TESTE do portal (remover)', u.id, a.id, false, 40, 30, 8, 11, 'ativo', true, 'Cadastro de teste do portal do instrutor'
FROM unidades u JOIN areas a ON a.unidade_id = u.id AND a.codigo = 'ENERGIAS'
WHERE u.codigo = 'BEIRA-MAR'
ON CONFLICT (matricula) DO NOTHING;

INSERT INTO disponibilidade_instrutores (instrutor_id, dia_semana, hora_inicio, hora_fim)
SELECT i.id, d, t.hora_inicio, t.hora_fim
FROM instrutores i JOIN turnos t ON t.unidade_id = i.unidade_id AND t.codigo IN ('M', 'T') CROSS JOIN generate_series(0, 4) AS d
WHERE i.matricula = 'TESTE-PORTAL'
  AND NOT EXISTS (SELECT 1 FROM disponibilidade_instrutores x WHERE x.instrutor_id = i.id);

INSERT INTO usuarios (nome, email, senha_hash, perfil, acesso_global, ativo, instrutor_id)
SELECT 'Instrutor de TESTE do portal (remover)', 'instrutor.teste', '$2b$12$rO3dq0S425by5Tyt2o4CNucfcBkIzpWNliYo81opxj2gmm0KBVaZm', 'instrutor', false, true, i.id
FROM instrutores i WHERE i.matricula = 'TESTE-PORTAL'
ON CONFLICT (email) DO UPDATE SET instrutor_id = EXCLUDED.instrutor_id, ativo = true WHERE usuarios.perfil = 'instrutor';

INSERT INTO notificacoes (instrutor_id, tipo, titulo, texto, aba, lida)
SELECT i.id, 'cadastro', 'Bem-vindo(a) ao portal do instrutor',
       'Confira seus dados em “Meus dados e expertise”: marque as UCs que você ministra, os turnos e as certificações.', 'dados', false
FROM instrutores i WHERE i.matricula = 'TESTE-PORTAL'
  AND NOT EXISTS (SELECT 1 FROM notificacoes n WHERE n.instrutor_id = i.id AND n.titulo = 'Bem-vindo(a) ao portal do instrutor');

-- Conferência: deve mostrar 1 linha com o login e 10 janelas de disponibilidade (manhã e tarde, seg a sex)
SELECT u.email AS login, u.perfil, i.nome AS instrutor, (SELECT count(*) FROM disponibilidade_instrutores d WHERE d.instrutor_id = i.id) AS disponibilidade
FROM usuarios u JOIN instrutores i ON i.id = u.instrutor_id WHERE u.email = 'instrutor.teste';
