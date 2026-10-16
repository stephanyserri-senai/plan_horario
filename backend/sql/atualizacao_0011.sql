-- Atualização 0010 -> 0011: turmas PFP — turno INTEGRAL (08:00–12:00 e 13:00–17:00, 8 aulas) em cada unidade;
-- instrutores com manhã e tarde (MV) passam a poder dar aula de dia inteiro. Não destrutiva. Cole no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0010 -> 0011

DO $$ DECLARE u record; t_id int; BEGIN
      FOR u IN SELECT id FROM unidades LOOP
        IF NOT EXISTS (SELECT 1 FROM turnos WHERE unidade_id = u.id AND codigo = 'I') THEN
          INSERT INTO turnos (unidade_id, codigo, nome, hora_inicio, hora_fim, ordem, ativo, criado_em, atualizado_em)
          VALUES (u.id, 'I', 'Integral (PFP)', '08:00', '17:00', 5, true, now(), now()) RETURNING id INTO t_id;
          INSERT INTO periodos_horarios (unidade_id, turno_id, ordem, hora_inicio, hora_fim, dias_semana, excepcional, ativo, criado_em, atualizado_em)
          SELECT u.id, t_id, v.ordem, v.ini::time, v.fim::time, '{0,1,2,3,4}', false, true, now(), now() FROM (VALUES (1, '08:00', '09:00'), (2, '09:00', '10:00'), (3, '10:00', '11:00'), (4, '11:00', '12:00'), (5, '13:00', '14:00'), (6, '14:00', '15:00'), (7, '15:00', '16:00'), (8, '16:00', '17:00')) AS v(ordem, ini, fim);
        END IF;
      END LOOP;
      -- quem tem manhã e tarde no mesmo dia pode dar aula de dia inteiro (08:00–17:00)
      INSERT INTO disponibilidade_instrutores (instrutor_id, dia_semana, hora_inicio, hora_fim, unidade_id)
      SELECT DISTINCT m.instrutor_id, m.dia_semana, time '08:00', time '17:00', m.unidade_id
        FROM disponibilidade_instrutores m
        JOIN instrutores i ON i.id = m.instrutor_id
        JOIN turnos tm ON tm.unidade_id = i.unidade_id AND tm.codigo = 'M'
        JOIN turnos tt ON tt.unidade_id = i.unidade_id AND tt.codigo = 'T'
        JOIN disponibilidade_instrutores t ON t.instrutor_id = m.instrutor_id AND t.dia_semana = m.dia_semana
       WHERE m.dia_semana < 5 AND m.hora_inicio <= tm.hora_inicio AND m.hora_fim >= tm.hora_fim
         AND t.hora_inicio <= tt.hora_inicio AND t.hora_fim >= tt.hora_fim
         AND NOT EXISTS (SELECT 1 FROM disponibilidade_instrutores x WHERE x.instrutor_id = m.instrutor_id AND x.dia_semana = m.dia_semana
                          AND x.hora_inicio <= time '08:00' AND x.hora_fim >= time '17:00');
    END $$;

UPDATE alembic_version SET version_num='0011' WHERE alembic_version.version_num = '0010';

COMMIT;

