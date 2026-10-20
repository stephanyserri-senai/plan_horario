#!/usr/bin/env bash
# Gera o SQL completo das migrações (Alembic offline) para revisão ou para
# aplicar manualmente no SQL Editor do Supabase. O Alembic continua sendo a
# fonte da verdade; regenere este arquivo sempre que criar uma migração.
set -euo pipefail
cd "$(dirname "$0")/../backend"
ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade head --sql > sql/schema_completo.sql
echo "Gerado backend/sql/schema_completo.sql"
# Atualização incremental para bancos que já estão na 0002 (ex.: homologação no Supabase)
{
  echo "-- Atualização 0002 -> 0003: unidades Beira Mar e Porto, áreas tecnológicas, turnos oficiais e área nos cadastros."
  echo "-- Não destrutiva: só cria a tabela de áreas, adiciona colunas anuláveis e insere o que ainda não existir."
  echo "-- Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run."
  ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade 0002:0003 --sql
} > sql/atualizacao_0003.sql
echo "Gerado backend/sql/atualizacao_0003.sql"
{
  echo "-- Atualização 0003 -> 0004: exceção justificada para regras acadêmicas (instrutor/laboratório de outra área, sem competência)."
  echo "-- Não destrutiva. Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run."
  ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade 0003:0004 --sql
} > sql/atualizacao_0004.sql
echo "Gerado backend/sql/atualizacao_0004.sql"
{
  echo "-- Atualização 0004 -> 0005: portal do instrutor (perfil instrutor, vínculo usuário × instrutor, observações e notificações) e substituição de instrutor nas aulas."
  echo "-- Não destrutiva. Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run."
  ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade 0004:0005 --sql
} > sql/atualizacao_0005.sql
echo "Gerado backend/sql/atualizacao_0005.sql"
{
  echo "-- Atualização 0005 -> 0006: turno da noite das 18:30 às 22:00 (aulas noturnas já programadas e disponibilidades são deslocadas 10 min)."
  echo "-- Não destrutiva e só age se a noite ainda estiver em 18:20–21:50. Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run."
  ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade 0005:0006 --sql
} > sql/atualizacao_0006.sql
echo "Gerado backend/sql/atualizacao_0006.sql"
{
  echo "-- Atualização 0006 -> 0007: modalidade do instrutor (mensalista ou horista). Os turnos de planejamento (PL) e projeto (PJ) usam a tabela de bloqueios."
  echo "-- Não destrutiva (todos os instrutores começam como mensalista). Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run."
  ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade 0006:0007 --sql
} > sql/atualizacao_0007.sql
echo "Gerado backend/sql/atualizacao_0007.sql"
{
  echo "-- Atualização 0007 -> 0008: perfis de usuário = administrador, planejador, instrutor e observador (somente acompanhar)."
  echo "-- Nenhum usuário é apagado: coordenador passa a planejador; gestor e consulta passam a observador."
  echo "-- Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run."
  ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade 0007:0008 --sql
} > sql/atualizacao_0008.sql
echo "Gerado backend/sql/atualizacao_0008.sql"
{
  echo "-- Atualização 0008 -> 0009: nível do instrutor (básico = AIB e qualificações; técnico = todas as modalidades) e dias EAD da turma (turmas 80-20)."
  echo "-- Não destrutiva: todos os instrutores começam como técnico e nenhuma turma tem dia EAD. Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run."
  ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade 0008:0009 --sql
} > sql/atualizacao_0009.sql
echo "Gerado backend/sql/atualizacao_0009.sql"
{
  echo "-- Atualização 0009 -> 0010: perfil COORDENADOR (planejador + aprova solicitações), solicitações de folga/substituição dos instrutores,"
  echo "-- UC transversal ou técnica, competência 'sim' / 'em partes' (sob supervisão vira em partes) e turno de SÁBADO (09:00–13:00) em cada unidade."
  echo "-- Não destrutiva. Cole o arquivo inteiro no SQL Editor do Supabase e clique em Run."
  ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade 0009:0010 --sql
} > sql/atualizacao_0010.sql
echo "Gerado backend/sql/atualizacao_0010.sql"
{
  echo "-- Atualização 0010 -> 0011: turmas PFP — turno INTEGRAL (08:00–12:00 e 13:00–17:00, 8 aulas) em cada unidade;"
  echo "-- instrutores com manhã e tarde (MV) passam a poder dar aula de dia inteiro. Não destrutiva. Cole no SQL Editor do Supabase e clique em Run."
  ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade 0010:0011 --sql
} > sql/atualizacao_0011.sql
echo "Gerado backend/sql/atualizacao_0011.sql"
{
  echo "-- Atualização 0011 -> 0012: turmas PFP em manhã (08–12) e tarde (13–17) com UC/instrutor diferentes; carga horária em minutos reais"
  echo "-- (cada aula vale 55 min de dia, 50 à noite); versão da matriz por tipo de oferta. Não destrutiva. Cole no SQL Editor do Supabase e clique em Run."
  ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade 0011:0012 --sql
} > sql/atualizacao_0012.sql
echo "Gerado backend/sql/atualizacao_0012.sql"
{
  echo "-- Atualização 0012 -> 0013: EPIs por curso (quantidade por aluno e antecedência) e controle por turma"
  echo "-- (prazo, comprado/separado, entregue). Só cria tabelas. Cole no SQL Editor do Supabase e clique em Run."
  ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade 0012:0013 --sql
} > sql/atualizacao_0013.sql
echo "Gerado backend/sql/atualizacao_0013.sql"
{
  echo "-- Atualização 0013 -> 0014: cursos que não precisam de EPI (coluna cursos.dispensa_epi, padrão falso)."
  echo "-- Só acrescenta a coluna. Cole no SQL Editor do Supabase e clique em Run."
  ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade 0013:0014 --sql
} > sql/atualizacao_0014.sql
echo "Gerado backend/sql/atualizacao_0014.sql"
{
  echo "-- Atualização 0014 -> 0015: turmas modulares (módulos e módulo em curso; o código leva o módulo) e exceção de"
  echo "-- reposição aos sábados. Não destrutiva. Cole no SQL Editor do Supabase e clique em Run."
  ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade 0014:0015 --sql
} > sql/atualizacao_0015.sql
echo "Gerado backend/sql/atualizacao_0015.sql"
{
  echo "-- Atualização 0015 -> 0016: PDI dos instrutores (UCs a aprender/completar e certificações, com prioridade, prazo"
  echo "-- e situação), a partir do índice de aderência. Só cria a tabela. Cole no SQL Editor do Supabase e clique em Run."
  ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade 0015:0016 --sql
} > sql/atualizacao_0016.sql
echo "Gerado backend/sql/atualizacao_0016.sql"
{
  echo "-- Atualização 0016 -> 0017: termo de horas mensal dos instrutores horistas (horas de aula do mês e outras"
  echo "-- ocupações; muda a cada mês). Só cria a tabela. Cole no SQL Editor do Supabase e clique em Run."
  ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade 0016:0017 --sql
} > sql/atualizacao_0017.sql
echo "Gerado backend/sql/atualizacao_0017.sql"
{
  echo "-- Atualização 0017 -> 0018: dias da semana do termo de horas do horista (o termo é ajustável por urgência,"
  echo "-- com a concordância do instrutor). Só acrescenta a coluna. Cole no SQL Editor do Supabase e clique em Run."
  ALEMBIC_DATABASE_URL="postgresql+psycopg://usuario:senha@host/banco" python -m alembic upgrade 0017:0018 --sql
} > sql/atualizacao_0018.sql
echo "Gerado backend/sql/atualizacao_0018.sql"
