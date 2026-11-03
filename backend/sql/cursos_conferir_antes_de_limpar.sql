-- CONFERIR ANTES DE LIMPAR OS CURSOS (só leitura: não altera nada).
-- Mostra o que limpar_cursos_recomecar.sql apagaria e o que fica. Cole no SQL Editor do Supabase e clique em Run.
SELECT 'cursos' AS item, count(*) AS quantidade, 'apaga' AS acao FROM cursos
UNION ALL SELECT 'versões da matriz', count(*), 'apaga' FROM matrizes_curriculares
UNION ALL SELECT 'UCs', count(*), 'apaga' FROM unidades_curriculares
UNION ALL SELECT 'turmas', count(*), 'apaga (cópia em bkp_turmas_cursos)' FROM turmas WHERE simulacao_id IS NULL
UNION ALL SELECT 'aulas programadas', count(*), 'apaga' FROM alocacoes WHERE status <> 'realizada'
UNION ALL SELECT 'aulas REALIZADAS', count(*), 'se > 0 a limpeza NÃO roda' FROM alocacoes WHERE status = 'realizada'
UNION ALL SELECT 'competências de instrutores (UCs marcadas)', count(*), 'apaga (cópia em bkp_competencias_cursos)' FROM competencias_instrutores
UNION ALL SELECT 'EPIs dos cursos', count(*), 'apaga' FROM epis_curso
UNION ALL SELECT 'unidades', count(*), 'mantém' FROM unidades
UNION ALL SELECT 'áreas', count(*), 'mantém' FROM areas
UNION ALL SELECT 'instrutores', count(*), 'mantém' FROM instrutores
UNION ALL SELECT 'salas e laboratórios', count(*), 'mantém' FROM ambientes
UNION ALL SELECT 'usuários', count(*), 'mantém' FROM usuarios;
