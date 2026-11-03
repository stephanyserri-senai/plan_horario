"""Turnos sempre M, V e N (matutino, vespertino, noturno) e o turno V de sábado (14:00–18:00).

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-03

- turnos: o código "T" (tarde) passa a "V" (vespertino); nomes Matutino, Vespertino, Noturno e Matutino (sábado).
- Novo turno "SV" — Vespertino (sábado), 14:00–18:00, 4 aulas de 55 min (intervalo 15:50–16:10), em cada unidade que tem o
  turno de sábado. O horário de funcionamento do sábado vai até as 18:00. Nada é apagado.
"""
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

SABADO_V = [("14:00", "14:55"), ("14:55", "15:50"), ("16:10", "17:05"), ("17:05", "18:00")]


def upgrade():
    op.execute("UPDATE turnos t SET codigo = 'V' WHERE codigo = 'T' "
               "AND NOT EXISTS (SELECT 1 FROM turnos o WHERE o.unidade_id = t.unidade_id AND o.codigo = 'V')")
    op.execute("UPDATE turnos SET nome = 'Matutino' WHERE codigo = 'M'")
    op.execute("UPDATE turnos SET nome = 'Vespertino' WHERE codigo = 'V'")
    op.execute("UPDATE turnos SET nome = 'Noturno' WHERE codigo = 'N'")
    op.execute("UPDATE turnos SET nome = 'Matutino (sábado)' WHERE codigo = 'S'")
    valores = ", ".join(f"({i}, '{a}', '{b}')" for i, (a, b) in enumerate(SABADO_V, 1))
    op.execute(f"""DO $$ DECLARE u record; t_id int; BEGIN
      FOR u IN SELECT DISTINCT unidade_id AS id FROM turnos WHERE codigo = 'S' LOOP
        IF NOT EXISTS (SELECT 1 FROM turnos WHERE unidade_id = u.id AND codigo = 'SV') THEN
          INSERT INTO turnos (unidade_id, codigo, nome, hora_inicio, hora_fim, ordem, ativo, criado_em, atualizado_em)
          VALUES (u.id, 'SV', 'Vespertino (sábado)', '14:00', '18:00', 6, true, now(), now()) RETURNING id INTO t_id;
          INSERT INTO periodos_horarios (unidade_id, turno_id, ordem, hora_inicio, hora_fim, dias_semana, excepcional, ativo, criado_em, atualizado_em)
          SELECT u.id, t_id, v.ordem, v.ini::time, v.fim::time, '{{5}}', false, true, now(), now() FROM (VALUES {valores}) AS v(ordem, ini, fim);
        END IF;
      END LOOP;
      UPDATE horarios_funcionamento SET hora_fim = '18:00' WHERE dia_semana = 5 AND hora_fim < '18:00';
    END $$""")


def downgrade():
    op.execute("DELETE FROM periodos_horarios WHERE turno_id IN (SELECT t.id FROM turnos t WHERE t.codigo = 'SV' "
               "AND NOT EXISTS (SELECT 1 FROM turmas x WHERE x.turno_id = t.id))")
    op.execute("DELETE FROM turnos t WHERE codigo = 'SV' AND NOT EXISTS (SELECT 1 FROM periodos_horarios p WHERE p.turno_id = t.id) "
               "AND NOT EXISTS (SELECT 1 FROM turmas x WHERE x.turno_id = t.id)")
    op.execute("UPDATE turnos SET codigo = 'T', nome = 'Tarde' WHERE codigo = 'V'")
    op.execute("UPDATE turnos SET nome = 'Manhã' WHERE codigo = 'M'")
    op.execute("UPDATE turnos SET nome = 'Noite' WHERE codigo = 'N'")
    op.execute("UPDATE turnos SET nome = 'Sábado' WHERE codigo = 'S'")
