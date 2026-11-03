-- LIMPAR TODO O DEMO E INICIAR O PROJETO (dados reais). Execute UMA vez, no SQL Editor do Supabase (cole o arquivo inteiro e clique em Run).
-- APAGA: toda a demonstração e os testes — cursos, matrizes, UCs, turmas, instrutores (com competências, termos de horas, PDI),
--        salas e laboratórios, recursos, calendários e feriados, bloqueios, semestres e aulas, gerações, simulações, importações,
--        observações, notificações, solicitações e pedidos de impressão dos instrutores, EPIs; os logins do portal (perfil instrutor),
--        os logins de demonstração/teste (coordenacao, coordenacao.teste, instrutor.teste, e-mails @demo.senai.br) e o histórico de
--        auditoria da fase de testes.
-- MANTÉM: TODAS as unidades e áreas (só sai unidade de demonstração, código DEMO-...), turnos e horários oficiais, configurações (pesos, regras de aula),
--         perfis de acesso e os usuários da equipe (administrador, supervisão, planejador, observador).
-- DEPOIS: o projeto fica marcado como iniciado; demo_semestre_completo.sql, demo_recarregar.sql, limpar_dados_teste.sql e os
--         logins de teste passam a se recusar a rodar (para não apagar nem misturar os dados reais). Este script também não roda de novo.
-- IRREVERSÍVEL: se quiser guardar algo, faça antes um backup (Supabase: Database → Backups).
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM configuracoes WHERE chave = 'producao_iniciada') THEN
    RAISE EXCEPTION 'O projeto já foi iniciado (este script já foi executado em %). Ele apagaria os dados reais: não execute de novo.',
      (SELECT valor->>'em' FROM configuracoes WHERE chave = 'producao_iniciada');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM unidades WHERE codigo = 'BEIRA-MAR') OR NOT EXISTS (SELECT 1 FROM unidades WHERE codigo = 'PORTO') THEN
    RAISE EXCEPTION 'Unidades oficiais não encontradas: aplique antes as atualizações 0003 e 0004.';
  END IF;
  -- portal do instrutor (atualização 0005): os usuários de instrutor continuam, só perdem o vínculo
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'usuarios' AND column_name = 'instrutor_id') THEN
    EXECUTE 'UPDATE usuarios SET instrutor_id = NULL WHERE instrutor_id IS NOT NULL';
  END IF;
  EXECUTE 'TRUNCATE TABLE
    alocacao_recursos,
    alocacoes,
    ambiente_areas,
    ambientes,
    atividades,
    bloqueios,
    calendario_excecoes,
    calendarios,
    cenarios_planejamento,
    competencias_instrutores,
    cursos,
    deslocamentos_unidades,
    disponibilidade_ambientes,
    disponibilidade_instrutores,
    excecoes_autorizadas,
    execucoes_otimizacao,
    habilitacoes_instrutores,
    horarios_funcionamento,
    importacoes,
    instrutor_areas,
    instrutor_unidades,
    matrizes_curriculares,
    ocorrencias_validacao,
    recursos,
    recursos_ambientes,
    registros_decisao,
    resultados_otimizacao,
    setores,
    simulacoes_capacidade,
    tipos_ambiente,
    turma_uc,
    turmas,
    uc_prerequisitos,
    uc_recursos,
    uc_tipos_ambiente,
    unidades_curriculares,
    validacoes,
    versoes_planejamento'
    || CASE WHEN to_regclass('public.observacoes_instrutor') IS NOT NULL THEN ', observacoes_instrutor' ELSE '' END
    || CASE WHEN to_regclass('public.notificacoes') IS NOT NULL THEN ', notificacoes' ELSE '' END
    || CASE WHEN to_regclass('public.solicitacoes_instrutor') IS NOT NULL THEN ', solicitacoes_instrutor' ELSE '' END
    || CASE WHEN to_regclass('public.epis_turma') IS NOT NULL THEN ', epis_turma, epis_curso' ELSE '' END
    || CASE WHEN to_regclass('public.pdi_itens') IS NOT NULL THEN ', pdi_itens' ELSE '' END
    || CASE WHEN to_regclass('public.termos_horas') IS NOT NULL THEN ', termos_horas' ELSE '' END
    || CASE WHEN to_regclass('public.solicitacoes_impressao') IS NOT NULL THEN ', solicitacoes_impressao' ELSE '' END
    || CASE WHEN to_regclass('public.agendamentos_ambiente') IS NOT NULL THEN ', agendamentos_ambiente' ELSE '' END
    || ' RESTART IDENTITY';
  -- instrutores: DELETE (a tabela de usuários, que é mantida, aponta para ela)
  DELETE FROM instrutores;
  PERFORM setval(pg_get_serial_sequence('instrutores', 'id'), 1, false);
  -- usuários do portal do instrutor (perfil instrutor): sem os instrutores, não servem mais. O histórico de
  -- auditoria é mantido (com o nome de quem fez), só deixa de apontar para o usuário apagado.
  UPDATE historico_auditoria SET usuario_id = NULL WHERE usuario_id IN (SELECT id FROM usuarios WHERE perfil = 'instrutor');
  DELETE FROM usuarios WHERE perfil = 'instrutor';
  -- escopos de acesso que apontavam para cursos/turmas apagados ou unidades extras
  -- UNIDADES E ÁREAS SÃO MANTIDAS (todas): só sai o que é de demonstração (código DEMO-...)
  DELETE FROM permissoes WHERE escopo_tipo IN ('curso', 'turma')
     OR (escopo_tipo = 'unidade' AND escopo_id IN (SELECT id FROM unidades WHERE codigo LIKE 'DEMO-%'));
  DELETE FROM periodos_horarios WHERE unidade_id IN (SELECT id FROM unidades WHERE codigo LIKE 'DEMO-%');
  DELETE FROM turnos WHERE unidade_id IN (SELECT id FROM unidades WHERE codigo LIKE 'DEMO-%');
  DELETE FROM areas WHERE unidade_id IN (SELECT id FROM unidades WHERE codigo LIKE 'DEMO-%');
  DELETE FROM unidades WHERE codigo LIKE 'DEMO-%';
  DELETE FROM configuracoes WHERE chave = 'worker_status';
  -- logins de demonstração e de teste (coordenação do demo, coordenação de teste, instrutor de teste, e-mails @demo)
  UPDATE historico_auditoria SET usuario_id = NULL WHERE usuario_id IN (
    SELECT id FROM usuarios WHERE email IN ('coordenacao', 'coordenacao.teste', 'instrutor.teste') OR email LIKE '%@demo.senai.br');
  DELETE FROM usuarios WHERE email IN ('coordenacao', 'coordenacao.teste', 'instrutor.teste') OR email LIKE '%@demo.senai.br';
  -- histórico de auditoria da fase de testes (tudo o que foi feito com os dados de demonstração)
  TRUNCATE TABLE historico_auditoria RESTART IDENTITY;
  -- marca: o projeto começou com dados reais; daqui em diante os scripts de demonstração/teste se recusam a rodar
  INSERT INTO configuracoes (chave, valor, descricao)
  VALUES ('producao_iniciada', jsonb_build_object('em', to_char(now() AT TIME ZONE 'America/Sao_Paulo', 'DD/MM/YYYY HH24:MI')),
          'Projeto iniciado com dados reais: os scripts de demonstração e de teste não rodam mais.')
  ON CONFLICT (chave) DO NOTHING;
END $$;

-- Conferência: estrutura fixa mantida, o resto zerado
SELECT (SELECT count(*) FROM unidades) AS unidades, (SELECT count(*) FROM areas) AS areas, (SELECT count(*) FROM turnos) AS turnos,
       (SELECT count(*) FROM cursos) AS cursos, (SELECT count(*) FROM turmas) AS turmas, (SELECT count(*) FROM instrutores) AS instrutores,
       (SELECT count(*) FROM ambientes) AS salas, (SELECT count(*) FROM cenarios_planejamento) AS semestres,
       (SELECT string_agg(email || ' (' || perfil || ')', ', ' ORDER BY email) FROM usuarios) AS usuarios_mantidos,
       (SELECT valor->>'em' FROM configuracoes WHERE chave = 'producao_iniciada') AS projeto_iniciado_em;
