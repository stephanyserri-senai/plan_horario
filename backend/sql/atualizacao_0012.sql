-- Atualização 0011 -> 0012: turmas PFP em manhã (08–12) e tarde (13–17) com UC/instrutor diferentes; carga horária em minutos reais
-- (cada aula vale 55 min de dia, 50 à noite); versão da matriz por tipo de oferta. Não destrutiva. Cole no SQL Editor do Supabase e clique em Run.
BEGIN;

-- Running upgrade 0011 -> 0012

ALTER TABLE matrizes_curriculares ADD COLUMN tipo_oferta VARCHAR(10);

UPDATE turnos SET nome = 'Manhã e tarde (PFP)' WHERE codigo = 'I' AND nome = 'Integral (PFP)';

DO $$ BEGIN
      DELETE FROM disponibilidade_instrutores WHERE hora_inicio = time '08:00' AND hora_fim = time '17:00';
      INSERT INTO disponibilidade_instrutores (instrutor_id, dia_semana, hora_inicio, hora_fim, unidade_id)
      SELECT DISTINCT d.instrutor_id, d.dia_semana, x.ini, x.fim, d.unidade_id
        FROM disponibilidade_instrutores d
        JOIN instrutores i ON i.id = d.instrutor_id
        JOIN turnos t ON t.unidade_id = i.unidade_id AND t.codigo IN ('M', 'T')
        JOIN (VALUES ('M', time '08:00', time '12:00'), ('T', time '13:00', time '17:00')) AS x(cod, ini, fim) ON x.cod = t.codigo
       WHERE d.dia_semana < 5 AND d.hora_inicio <= t.hora_inicio AND d.hora_fim >= t.hora_fim
         AND NOT EXISTS (SELECT 1 FROM disponibilidade_instrutores y WHERE y.instrutor_id = d.instrutor_id AND y.dia_semana = d.dia_semana
                          AND y.hora_inicio <= x.ini AND y.hora_fim >= x.fim);
    END $$;

UPDATE configuracoes SET valor = jsonb_set(valor, '{contagem}', '"relogio"') WHERE chave = 'regras_aula' AND valor->>'contagem' = 'hora_aula';

UPDATE alembic_version SET version_num='0012' WHERE alembic_version.version_num = '0011';

COMMIT;

