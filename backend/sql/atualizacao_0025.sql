-- Atualização 0024 -> 0025: turnos M, V e N (matutino, vespertino, noturno): o código T passa a V e os nomes mudam;
-- cria o turno V de sábado (14:00–18:00). Nada é apagado. Cole no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0024 -> 0025

UPDATE turnos t SET codigo = 'V' WHERE codigo = 'T' AND NOT EXISTS (SELECT 1 FROM turnos o WHERE o.unidade_id = t.unidade_id AND o.codigo = 'V');

UPDATE turnos SET nome = 'Matutino' WHERE codigo = 'M';

UPDATE turnos SET nome = 'Vespertino' WHERE codigo = 'V';

UPDATE turnos SET nome = 'Noturno' WHERE codigo = 'N';

UPDATE turnos SET nome = 'Matutino (sábado)' WHERE codigo = 'S';

DO $$ DECLARE u record; t_id int; BEGIN
      FOR u IN SELECT DISTINCT unidade_id AS id FROM turnos WHERE codigo = 'S' LOOP
        IF NOT EXISTS (SELECT 1 FROM turnos WHERE unidade_id = u.id AND codigo = 'SV') THEN
          INSERT INTO turnos (unidade_id, codigo, nome, hora_inicio, hora_fim, ordem, ativo, criado_em, atualizado_em)
          VALUES (u.id, 'SV', 'Vespertino (sábado)', '14:00', '18:00', 6, true, now(), now()) RETURNING id INTO t_id;
          INSERT INTO periodos_horarios (unidade_id, turno_id, ordem, hora_inicio, hora_fim, dias_semana, excepcional, ativo, criado_em, atualizado_em)
          SELECT u.id, t_id, v.ordem, v.ini::time, v.fim::time, '{5}', false, true, now(), now() FROM (VALUES (1, '14:00', '14:55'), (2, '14:55', '15:50'), (3, '16:10', '17:05'), (4, '17:05', '18:00')) AS v(ordem, ini, fim);
        END IF;
      END LOOP;
      UPDATE horarios_funcionamento SET hora_fim = '18:00' WHERE dia_semana = 5 AND hora_fim < '18:00';
    END $$;

UPDATE alembic_version SET version_num='0025' WHERE alembic_version.version_num = '0024';

COMMIT;

