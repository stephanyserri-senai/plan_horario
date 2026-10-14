-- OPCIONAL: remove a unidade de teste (código TESTE) criada antes de as unidades serem fixas (Beira Mar e Porto).
-- Só apaga se não houver turmas, cursos, instrutores, salas, recursos ou cenários ligados a ela; caso contrário, nada é alterado.
DO $$
DECLARE u int;
BEGIN
  SELECT id INTO u FROM unidades WHERE codigo = 'TESTE';
  IF u IS NULL THEN
    RAISE NOTICE 'Unidade TESTE não encontrada: nada a fazer.';
    RETURN;
  END IF;
  IF EXISTS (SELECT 1 FROM turmas WHERE unidade_id = u) OR EXISTS (SELECT 1 FROM cursos WHERE unidade_id = u)
     OR EXISTS (SELECT 1 FROM instrutores WHERE unidade_id = u) OR EXISTS (SELECT 1 FROM ambientes WHERE unidade_id = u)
     OR EXISTS (SELECT 1 FROM cenarios_planejamento WHERE unidade_id = u) OR EXISTS (SELECT 1 FROM recursos WHERE unidade_id = u) THEN
    RAISE EXCEPTION 'A unidade TESTE tem turmas, cursos, instrutores, salas ou cenários ligados a ela. Nada foi apagado.';
  END IF;
  DELETE FROM periodos_horarios WHERE unidade_id = u;
  DELETE FROM turnos WHERE unidade_id = u;
  DELETE FROM calendario_excecoes WHERE calendario_id IN (SELECT id FROM calendarios WHERE unidade_id = u);
  DELETE FROM calendarios WHERE unidade_id = u;
  DELETE FROM horarios_funcionamento WHERE unidade_id = u;
  DELETE FROM setores WHERE unidade_id = u;
  DELETE FROM permissoes WHERE escopo_tipo = 'unidade' AND escopo_id = u;
  DELETE FROM deslocamentos_unidades WHERE origem_id = u OR destino_id = u;
  DELETE FROM instrutor_unidades WHERE unidade_id = u;
  UPDATE disponibilidade_instrutores SET unidade_id = NULL WHERE unidade_id = u;
  DELETE FROM unidades WHERE id = u;
  RAISE NOTICE 'Unidade TESTE removida.';
END $$;
