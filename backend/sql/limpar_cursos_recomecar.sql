-- LIMPAR OS CURSOS PARA RECOMEÇAR (cursos, versões da matriz e UCs) — dados reais, use com cuidado.
--
-- O que é apagado: cursos, versões da matriz, UCs (salas exigidas, pré-requisitos, recursos), EPIs dos cursos e, porque
-- dependem dos cursos, as TURMAS (com turma × UC, aulas programadas, EPIs das turmas, observações e bloqueios de turma)
-- e as competências dos instrutores (UCs marcadas no perfil).
-- O que fica: unidades, áreas, instrutores (dados, disponibilidade, certificações, termos, PDI), salas, tipos de sala,
-- usuários, semestres (vazios), configurações, calendários.
-- Antes de apagar, guarda cópias em bkp_competencias_cursos (instrutor × curso × UC, pelos códigos) e bkp_turmas_cursos
-- (as turmas com curso, versão e público), para restaurar depois de reimportar os cursos
-- (restaurar_competencias_apos_cursos.sql). As cópias ficam fechadas para a Data API (só o backend/SQL Editor).
-- SEGURANÇA: recusa rodar se houver aula REALIZADA (o histórico não é apagado) — nesse caso, nada muda.
-- Tudo roda num único bloco: ou apaga tudo, ou nada. Antes, rode cursos_conferir_antes_de_limpar.sql para ver as quantidades.
-- Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run.

DO $$
DECLARE
  n_realizadas int;
  lote timestamptz := now();
BEGIN
  SELECT count(*) INTO n_realizadas FROM alocacoes WHERE status = 'realizada';
  IF n_realizadas > 0 THEN
    RAISE EXCEPTION 'Há % aula(s) REALIZADA(S): limpar os cursos apagaria esse histórico. Nada foi alterado. Fale com o suporte para corrigir só as versões da matriz (reimportação) em vez de apagar.', n_realizadas;
  END IF;

  -- 1) cópias de segurança (por códigos, para sobreviver à reimportação)
  CREATE TABLE IF NOT EXISTS bkp_competencias_cursos (
    copiado_em timestamptz, instrutor_matricula text, curso_codigo text, uc_codigo text, nivel text, valido_ate date, ativo boolean);
  CREATE TABLE IF NOT EXISTS bkp_turmas_cursos (copiado_em timestamptz, curso_codigo text, versao text, publico text, turma jsonb);
  ALTER TABLE public.bkp_competencias_cursos ENABLE ROW LEVEL SECURITY;
  ALTER TABLE public.bkp_turmas_cursos ENABLE ROW LEVEL SECURITY;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON public.bkp_competencias_cursos, public.bkp_turmas_cursos FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON public.bkp_competencias_cursos, public.bkp_turmas_cursos FROM authenticated';
  END IF;

  INSERT INTO bkp_competencias_cursos
  SELECT DISTINCT lote, i.matricula, c.codigo, u.codigo, ci.nivel, ci.valido_ate, ci.ativo
  FROM competencias_instrutores ci
  JOIN instrutores i ON i.id = ci.instrutor_id
  JOIN unidades_curriculares u ON u.id = ci.uc_id
  JOIN matrizes_curriculares m ON m.id = u.matriz_id
  JOIN cursos c ON c.id = m.curso_id;

  INSERT INTO bkp_turmas_cursos
  SELECT lote, c.codigo, m.versao, m.tipo_oferta, to_jsonb(t) - 'id' - 'curso_id' - 'matriz_id'
  FROM turmas t JOIN cursos c ON c.id = t.curso_id JOIN matrizes_curriculares m ON m.id = t.matriz_id
  WHERE t.simulacao_id IS NULL;

  -- 2) turmas e o que depende delas (aulas programadas, validações, bloqueios de turma)
  DELETE FROM ocorrencias_validacao WHERE turma_id IS NOT NULL OR uc_id IS NOT NULL OR alocacao_id IS NOT NULL;
  DELETE FROM alocacoes;                       -- só há aulas programadas (as realizadas foram conferidas acima)
  DELETE FROM bloqueios WHERE alvo_tipo = 'turma';
  UPDATE agendamentos_ambiente SET turma_id = NULL WHERE turma_id IS NOT NULL;
  UPDATE solicitacoes_impressao SET turma_id = NULL WHERE turma_id IS NOT NULL;
  DELETE FROM turmas;                          -- em cascata: turma × UC, atividades, EPIs da turma, observações por UC

  -- 3) competências dos instrutores (copiadas acima) e a estrutura curricular
  DELETE FROM competencias_instrutores;
  UPDATE pdi_itens SET curso_id = NULL WHERE curso_id IS NOT NULL;   -- o PDI fica (UC pelo código)
  DELETE FROM uc_prerequisitos;
  DELETE FROM uc_recursos;
  DELETE FROM uc_tipos_ambiente;
  DELETE FROM unidades_curriculares;
  UPDATE matrizes_curriculares SET matriz_origem_id = NULL;
  DELETE FROM matrizes_curriculares;
  DELETE FROM cursos;                          -- em cascata: EPIs dos cursos

  RAISE NOTICE 'Cursos, versões, UCs e turmas apagados. Cópias: bkp_competencias_cursos e bkp_turmas_cursos (lote %).', lote;
END $$;

-- Conferência: deve mostrar 0 cursos, 0 UCs e 0 turmas, e quantas competências/turmas ficaram copiadas
SELECT (SELECT count(*) FROM cursos) AS cursos, (SELECT count(*) FROM unidades_curriculares) AS ucs, (SELECT count(*) FROM turmas) AS turmas,
       (SELECT count(*) FROM bkp_competencias_cursos WHERE copiado_em = (SELECT max(copiado_em) FROM bkp_competencias_cursos)) AS competencias_copiadas,
       (SELECT count(*) FROM bkp_turmas_cursos WHERE copiado_em = (SELECT max(copiado_em) FROM bkp_turmas_cursos)) AS turmas_copiadas,
       (SELECT count(*) FROM unidades) AS unidades_mantidas, (SELECT count(*) FROM areas) AS areas_mantidas,
       (SELECT count(*) FROM instrutores) AS instrutores_mantidos;
