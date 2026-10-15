"""Turno da noite das 18:30 às 22:00.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-15

As 4 aulas de 50 min da noite passam a 18:30–19:20, 19:20–20:10, (intervalo 20:10–20:20),
20:20–21:10 e 21:10–22:00 — todas 10 minutos depois do horário anterior (18:20–21:50).
Atualiza o turno e os períodos da noite das unidades, desloca as aulas noturnas já programadas
(+10 min) e ajusta as janelas de disponibilidade e o horário de funcionamento que terminavam às 21:50.
Só age se a noite ainda estiver no horário antigo (pode ser executada mais de uma vez).
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def _sql(antigo_ini: str, antigo_fim: str, novo_ini: str, novo_fim: str, sinal: str) -> str:
    # As aulas vão primeiro 100 anos à frente e depois voltam deslocadas: assim nenhuma colide, no meio do
    # UPDATE, com a aula seguinte que ainda não foi deslocada (restrições de não sobreposição).
    return f"""
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM turnos WHERE codigo = 'N' AND hora_inicio = '{antigo_ini}' AND hora_fim = '{antigo_fim}') THEN
    UPDATE alocacoes a SET inicio = a.inicio + interval '100 years', fim = a.fim + interval '100 years',
                           fim_ambiente = a.fim_ambiente + interval '100 years'
      FROM turmas t JOIN turnos tn ON tn.id = t.turno_id
     WHERE a.turma_id = t.id AND tn.codigo = 'N' AND tn.hora_inicio = '{antigo_ini}'
       AND a.inicio::time >= '{antigo_ini}' AND a.fim::time <= '{antigo_fim}';
    UPDATE alocacoes SET inicio = inicio - interval '100 years' {sinal} interval '10 minutes',
                         fim = fim - interval '100 years' {sinal} interval '10 minutes',
                         fim_ambiente = fim_ambiente - interval '100 years' {sinal} interval '10 minutes'
     WHERE inicio > timestamp '2100-01-01';
    UPDATE periodos_horarios p SET hora_inicio = p.hora_inicio {sinal} interval '10 minutes', hora_fim = p.hora_fim {sinal} interval '10 minutes'
      FROM turnos t WHERE p.turno_id = t.id AND t.codigo = 'N' AND t.hora_inicio = '{antigo_ini}';
    UPDATE turnos SET hora_inicio = '{novo_ini}', hora_fim = '{novo_fim}' WHERE codigo = 'N' AND hora_inicio = '{antigo_ini}' AND hora_fim = '{antigo_fim}';
    UPDATE disponibilidade_instrutores SET hora_inicio = '{novo_ini}' WHERE hora_inicio = '{antigo_ini}';
    UPDATE disponibilidade_instrutores SET hora_fim = '{novo_fim}' WHERE hora_fim = '{antigo_fim}';
    UPDATE disponibilidade_ambientes SET hora_inicio = '{novo_ini}' WHERE hora_inicio = '{antigo_ini}';
    UPDATE disponibilidade_ambientes SET hora_fim = '{novo_fim}' WHERE hora_fim = '{antigo_fim}';
    UPDATE horarios_funcionamento SET hora_fim = '{novo_fim}' WHERE hora_fim = '{antigo_fim}';
  END IF;
END $$
"""


def upgrade():
    op.execute(_sql("18:20", "21:50", "18:30", "22:00", "+"))


def downgrade():
    op.execute(_sql("18:30", "22:00", "18:20", "21:50", "-"))
