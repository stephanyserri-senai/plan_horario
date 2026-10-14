-- LIMPEZA DOS DADOS DE TESTE — para começar as validações com dados reais.
-- MANTÉM: unidades Beira Mar e Porto, áreas tecnológicas, turnos oficiais (manhã/tarde/noite), configurações
--         (pesos, regras de aula, limiares), perfis de acesso, usuários e o histórico de auditoria.
-- APAGA:  observações dos instrutores (o usuário do instrutor continua, mas desvinculado), cursos, matrizes, UCs, turmas, instrutores, salas/laboratórios, tipos de sala, recursos, calendários,
--         feriados, bloqueios, semestres (cenários), aulas, gerações, simulações, importações e exceções;
--         e qualquer unidade que não seja BEIRA-MAR ou PORTO (com seus turnos).
-- IRREVERSÍVEL: faça um backup antes se houver algo que queira guardar. Cole o arquivo inteiro no SQL Editor e clique em Run.
DO $$
BEGIN
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
    || ' RESTART IDENTITY';
  -- instrutores: DELETE (a tabela de usuários, que é mantida, aponta para ela)
  DELETE FROM instrutores;
  PERFORM setval(pg_get_serial_sequence('instrutores', 'id'), 1, false);
  -- escopos de acesso que apontavam para cursos/turmas apagados ou unidades extras
  DELETE FROM permissoes WHERE escopo_tipo IN ('curso', 'turma')
     OR (escopo_tipo = 'unidade' AND escopo_id NOT IN (SELECT id FROM unidades WHERE codigo IN ('BEIRA-MAR', 'PORTO')));
  DELETE FROM periodos_horarios WHERE unidade_id NOT IN (SELECT id FROM unidades WHERE codigo IN ('BEIRA-MAR', 'PORTO'));
  DELETE FROM turnos WHERE unidade_id NOT IN (SELECT id FROM unidades WHERE codigo IN ('BEIRA-MAR', 'PORTO'));
  DELETE FROM areas WHERE unidade_id NOT IN (SELECT id FROM unidades WHERE codigo IN ('BEIRA-MAR', 'PORTO'));
  DELETE FROM unidades WHERE codigo NOT IN ('BEIRA-MAR', 'PORTO');
  DELETE FROM configuracoes WHERE chave = 'worker_status';
END $$;

-- Conferência: tudo zerado, exceto a estrutura fixa
SELECT (SELECT count(*) FROM unidades) AS unidades, (SELECT count(*) FROM areas) AS areas,
       (SELECT count(*) FROM turnos) AS turnos, (SELECT count(*) FROM cursos) AS cursos,
       (SELECT count(*) FROM turmas) AS turmas, (SELECT count(*) FROM instrutores) AS instrutores,
       (SELECT count(*) FROM ambientes) AS salas, (SELECT count(*) FROM cenarios_planejamento) AS semestres,
       (SELECT count(*) FROM usuarios) AS usuarios;
