-- LIMPEZA DOS DADOS DE TESTE — para começar as validações com dados reais.
-- MANTÉM: unidades Beira Mar e Porto, áreas tecnológicas, turnos oficiais (manhã/tarde/noite/sábado), configurações
--         (pesos, regras de aula, limiares), perfis de acesso, usuários da equipe (administrador, planejador,
--         observador) e o histórico de auditoria.
-- APAGA:  logins do portal do instrutor (perfil instrutor), observações, notificações e solicitações dos instrutores,
--         cursos (e os EPIs exigidos), matrizes, UCs, turmas (e o controle de EPIs), instrutores, salas/laboratórios, tipos de sala, recursos, calendários,
--         feriados, bloqueios, semestres (cenários), aulas, gerações, simulações, importações e exceções.
--         UNIDADES E ÁREAS: todas mantidas (só sai unidade de demonstração, código DEMO-...).
-- IRREVERSÍVEL: faça um backup antes se houver algo que queira guardar. Cole o arquivo inteiro no SQL Editor e clique em Run.
DO $$
BEGIN
  IF to_regclass('public.configuracoes') IS NOT NULL AND EXISTS (SELECT 1 FROM configuracoes WHERE chave = 'producao_iniciada') THEN
    RAISE EXCEPTION 'Projeto já iniciado com dados reais (limpar_demo_iniciar_projeto.sql foi executado): este script de teste/demonstração apagaria ou misturaria dados. Não execute em produção.';
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
    || CASE WHEN to_regclass('public.solicitacoes_diarias') IS NOT NULL THEN ', solicitacoes_diarias' ELSE '' END
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
END $$;

-- Conferência: tudo zerado, exceto a estrutura fixa
SELECT (SELECT count(*) FROM unidades) AS unidades, (SELECT count(*) FROM areas) AS areas,
       (SELECT count(*) FROM turnos) AS turnos, (SELECT count(*) FROM cursos) AS cursos,
       (SELECT count(*) FROM turmas) AS turmas, (SELECT count(*) FROM instrutores) AS instrutores,
       (SELECT count(*) FROM ambientes) AS salas, (SELECT count(*) FROM cenarios_planejamento) AS semestres,
       (SELECT count(*) FROM usuarios) AS usuarios;
