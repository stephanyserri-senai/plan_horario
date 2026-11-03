-- RESTAURAR AS COMPETÊNCIAS DOS INSTRUTORES depois de reimportar os cursos (rode DEPOIS da planilha de cursos).
-- Usa a cópia mais recente de bkp_competencias_cursos (feita por limpar_cursos_recomecar.sql) e liga cada instrutor às UCs
-- de mesmo código do mesmo curso, em TODAS as versões/públicos reimportados. Não duplica; pode rodar mais de uma vez.
-- Cole no SQL Editor do Supabase e clique em Run.
INSERT INTO competencias_instrutores (instrutor_id, uc_id, nivel, valido_ate, ativo, criado_em, atualizado_em)
SELECT DISTINCT ON (i.id, u.id) i.id, u.id, b.nivel, b.valido_ate, coalesce(b.ativo, true), now(), now()
FROM bkp_competencias_cursos b
JOIN instrutores i ON i.matricula = b.instrutor_matricula
JOIN cursos c ON upper(c.codigo) = upper(b.curso_codigo)
JOIN matrizes_curriculares m ON m.curso_id = c.id
JOIN unidades_curriculares u ON u.matriz_id = m.id AND upper(u.codigo) = upper(b.uc_codigo)
WHERE b.copiado_em = (SELECT max(copiado_em) FROM bkp_competencias_cursos)
ORDER BY i.id, u.id, (b.nivel = 'pleno') DESC
ON CONFLICT (instrutor_id, uc_id) DO NOTHING;

-- Conferência: competências da cópia que NÃO acharam UC nos cursos reimportados (código de curso/UC mudou)
SELECT b.instrutor_matricula, b.curso_codigo, b.uc_codigo, b.nivel
FROM bkp_competencias_cursos b
WHERE b.copiado_em = (SELECT max(copiado_em) FROM bkp_competencias_cursos)
  AND NOT EXISTS (SELECT 1 FROM cursos c JOIN matrizes_curriculares m ON m.curso_id = c.id
                  JOIN unidades_curriculares u ON u.matriz_id = m.id
                  WHERE upper(c.codigo) = upper(b.curso_codigo) AND upper(u.codigo) = upper(b.uc_codigo))
ORDER BY 2, 3, 1;
