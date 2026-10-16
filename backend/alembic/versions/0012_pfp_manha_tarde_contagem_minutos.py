"""PFP em manhã e tarde; carga horária em minutos reais; versão da matriz por tipo de oferta.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-17

- PFP: o horário das turmas PFP passa a se chamar "Manhã e tarde (PFP)"; cada metade (08–12 e 13–17) é um turno
  inteiro e pode ter UC e instrutor diferentes. As janelas 08:00–17:00 que a 0011 criou para quem trabalha manhã e
  tarde são trocadas por 08:00–12:00 (quem é da manhã) e 13:00–17:00 (quem é da tarde).
- Carga horária: cada aula vale o tempo real (55 min de dia, 50 min à noite); a configuração "regras_aula" que estava
  em "hora_aula" passa a "relogio". Aulas já gravadas não são recalculadas (gere de novo os horários afetados).
- Matriz curricular: coluna tipo_oferta (ex.: HTC, AIT) para versões personalizadas por oferta. Nada é apagado
  além das janelas 08–17 geradas pela própria 0011.
"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("matrizes_curriculares", sa.Column("tipo_oferta", sa.String(10), nullable=True))
    op.execute("UPDATE turnos SET nome = 'Manhã e tarde (PFP)' WHERE codigo = 'I' AND nome = 'Integral (PFP)'")
    op.execute("""DO $$ BEGIN
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
    END $$""")
    op.execute("UPDATE configuracoes SET valor = jsonb_set(valor, '{contagem}', '\"relogio\"') "
               "WHERE chave = 'regras_aula' AND valor->>'contagem' = 'hora_aula'")


def downgrade():
    op.execute("UPDATE configuracoes SET valor = jsonb_set(valor, '{contagem}', '\"hora_aula\"') "
               "WHERE chave = 'regras_aula' AND valor->>'contagem' = 'relogio'")
    op.execute("DELETE FROM disponibilidade_instrutores WHERE (hora_inicio, hora_fim) IN ((time '08:00', time '12:00'), (time '13:00', time '17:00'))")
    op.execute("UPDATE turnos SET nome = 'Integral (PFP)' WHERE codigo = 'I' AND nome = 'Manhã e tarde (PFP)'")
    op.drop_column("matrizes_curriculares", "tipo_oferta")
