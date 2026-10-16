"""Turmas PFP: turno integral 08:00–12:00 e 13:00–17:00.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-16

- Cria em cada unidade o turno "I" — Integral (PFP), 08:00–17:00 — com 8 aulas de 60 min de segunda a sexta
  (08–09, 09–10, 10–11, 11–12 e 13–14, 14–15, 15–16, 16–17; almoço 12:00–13:00).
- Instrutores que trabalham manhã e tarde (jornada MV) ganham a janela 08:00–17:00 nos dias em que já têm as duas,
  para poderem dar aula nas turmas PFP. Nenhum dado é apagado.
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

AULAS = [(8, 9), (9, 10), (10, 11), (11, 12), (13, 14), (14, 15), (15, 16), (16, 17)]


def upgrade():
    valores = ", ".join(f"({i}, '{a:02d}:00', '{b:02d}:00')" for i, (a, b) in enumerate(AULAS, 1))
    op.execute(f"""DO $$ DECLARE u record; t_id int; BEGIN
      FOR u IN SELECT id FROM unidades LOOP
        IF NOT EXISTS (SELECT 1 FROM turnos WHERE unidade_id = u.id AND codigo = 'I') THEN
          INSERT INTO turnos (unidade_id, codigo, nome, hora_inicio, hora_fim, ordem, ativo, criado_em, atualizado_em)
          VALUES (u.id, 'I', 'Integral (PFP)', '08:00', '17:00', 5, true, now(), now()) RETURNING id INTO t_id;
          INSERT INTO periodos_horarios (unidade_id, turno_id, ordem, hora_inicio, hora_fim, dias_semana, excepcional, ativo, criado_em, atualizado_em)
          SELECT u.id, t_id, v.ordem, v.ini::time, v.fim::time, '{{0,1,2,3,4}}', false, true, now(), now() FROM (VALUES {valores}) AS v(ordem, ini, fim);
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
    END $$""")


def downgrade():
    op.execute("DELETE FROM disponibilidade_instrutores WHERE hora_inicio = '08:00' AND hora_fim = '17:00'")
    op.execute("DELETE FROM periodos_horarios WHERE turno_id IN (SELECT t.id FROM turnos t WHERE t.codigo = 'I' "
               "AND NOT EXISTS (SELECT 1 FROM turmas x WHERE x.turno_id = t.id))")
    op.execute("DELETE FROM turnos t WHERE codigo = 'I' AND NOT EXISTS (SELECT 1 FROM periodos_horarios p WHERE p.turno_id = t.id) "
               "AND NOT EXISTS (SELECT 1 FROM turmas x WHERE x.turno_id = t.id)")
