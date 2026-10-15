-- Atualização 0005 -> 0006: turno da noite das 18:30 às 22:00 (aulas noturnas já programadas e disponibilidades são deslocadas 10 min).
-- Não destrutiva e só age se a noite ainda estiver em 18:20–21:50. Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0005 -> 0006

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM turnos WHERE codigo = 'N' AND hora_inicio = '18:20' AND hora_fim = '21:50') THEN
    UPDATE alocacoes a SET inicio = a.inicio + interval '100 years', fim = a.fim + interval '100 years',
                           fim_ambiente = a.fim_ambiente + interval '100 years'
      FROM turmas t JOIN turnos tn ON tn.id = t.turno_id
     WHERE a.turma_id = t.id AND tn.codigo = 'N' AND tn.hora_inicio = '18:20'
       AND a.inicio::time >= '18:20' AND a.fim::time <= '21:50';
    UPDATE alocacoes SET inicio = inicio - interval '100 years' + interval '10 minutes',
                         fim = fim - interval '100 years' + interval '10 minutes',
                         fim_ambiente = fim_ambiente - interval '100 years' + interval '10 minutes'
     WHERE inicio > timestamp '2100-01-01';
    UPDATE periodos_horarios p SET hora_inicio = p.hora_inicio + interval '10 minutes', hora_fim = p.hora_fim + interval '10 minutes'
      FROM turnos t WHERE p.turno_id = t.id AND t.codigo = 'N' AND t.hora_inicio = '18:20';
    UPDATE turnos SET hora_inicio = '18:30', hora_fim = '22:00' WHERE codigo = 'N' AND hora_inicio = '18:20' AND hora_fim = '21:50';
    UPDATE disponibilidade_instrutores SET hora_inicio = '18:30' WHERE hora_inicio = '18:20';
    UPDATE disponibilidade_instrutores SET hora_fim = '22:00' WHERE hora_fim = '21:50';
    UPDATE disponibilidade_ambientes SET hora_inicio = '18:30' WHERE hora_inicio = '18:20';
    UPDATE disponibilidade_ambientes SET hora_fim = '22:00' WHERE hora_fim = '21:50';
    UPDATE horarios_funcionamento SET hora_fim = '22:00' WHERE hora_fim = '21:50';
  END IF;
END $$;

UPDATE alembic_version SET version_num='0006' WHERE alembic_version.version_num = '0005';

COMMIT;

