# Planejamento Acadêmico (SENAI-ES) — memória do projeto

Plataforma de planejamento de horários, capacidade e ocupação: FastAPI + PostgreSQL (backend/), React + TS (frontend/),
deploy em Vercel + Supabase (SQL aplicado à mão pelo SQL Editor; ver SUPABASE.md).

## Regras de negócio
As regras da instituição (dias da turma, sábado, EAD 80-20, turno inteiro, teto de 90%, nível básico/técnico,
UC transversal/técnica, substituição, solicitações, quadro 5:4...) estão em **docs/REGRAS_DE_NEGOCIO.md**, gerado de
`backend/app/services/regras_institucionais.py`. Ao mudar uma regra: altere o código que a aplica, o catálogo e rode
`python scripts/gerar_regras_md.py` (um teste confere que o documento está em dia).

## Convenções
- Nomenclatura: TURNO é matutino, vespertino ou noturno (e o turno de sábado). Para contar aulas na semana use
  "dias de aula" (cada dia ocupa um turno inteiro), nunca "turnos por semana". Turmas PFP têm manhã (08–12) e tarde
  (13–17); cada metade é um turno, com UC e instrutor próprios (turno oculto "I"; na grade caem nas linhas da manhã e da tarde).
- Carga horária em minutos reais: cada aula vale 55 min (dia) ou 50 min (noite); o que falta vira outra aula
  (UC de 20 h no matutino = 22 aulas). "hora_aula" (60 min) é só opção nas configurações.
- Ausências do instrutor: PL (planejamento) e PJ (projeto) ficam na escola; TR (treinamento) libera das aulas
  (não é substituto possível e o gerador evita).
- Matriz curricular por curso com versões por tipo de oferta (`tipo_oferta`, ex.: AIT, HTC); sem pré-requisitos.
- Interface e mensagens em português; nada de dados fictícios fora da demonstração (`backend/app/demo_semestre.py`).
- Migrações Alembic não destrutivas; para cada migração, gere o SQL do Supabase com `scripts/gerar_sql_migracoes.sh`
  (`backend/sql/atualizacao_NNNN.sql`) e cite-o no SUPABASE.md. O demo (`backend/sql/demo_semestre_completo.sql`)
  é gerado por `scripts/gerar_semestre_demo_sql.py`.
- Nunca expor chaves `service_role`, senhas ou segredos no frontend ou no repositório.
- Toda alocação passa pela validação central (`backend/app/services/validacao.py`).

## Testes locais
`service postgresql start`; `cd backend && python -m pytest -q`; frontend: `cd frontend && npx tsc --noEmit -p . && npm run build`.
