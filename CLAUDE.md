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
- EPIs: cadastrados no curso (`epis_curso`); cada turma recebe o controle (`epis_turma`: quantidade, prazo, comprado/separado,
  entregue) via `services/epis.sincronizar_turma`, chamado ao criar/alterar/duplicar/importar turma. Curso com
  `dispensa_epi` não precisa de EPI (lista vazia, não aparece como pendente).
- Interface e mensagens em português; nada de dados fictícios fora da demonstração (`backend/app/demo_semestre.py`).
- Migrações Alembic não destrutivas; para cada migração, gere o SQL do Supabase com `scripts/gerar_sql_migracoes.sh`
  (`backend/sql/atualizacao_NNNN.sql`) e cite-o no SUPABASE.md. O demo (`backend/sql/demo_semestre_completo.sql`)
  é gerado por `scripts/gerar_semestre_demo_sql.py`.
- Nunca expor chaves `service_role`, senhas ou segredos no frontend ou no repositório.
- Toda alocação passa pela validação central (`backend/app/services/validacao.py`).
- Turmas modulares: `turmas.modulos` (vazio = não modular) e `modulo_atual`; código `TIPO-SIGLA-MÓDULO-NÚMERO` (HTC-AIT-2-34).
  Ao criar um semestre, `services/modulos.avancar` passa as turmas ao próximo módulo (código sobe) até o último.
- UC fora do prazo: modular → reposição aos sábados (exceção `reposicao`, que libera dia/turno/disponibilidade só no turno de
  sábado); não modular → `passar_proximo_semestre` (prazo vai ao fim do próximo semestre). UC com um só habilitado: habilitar
  outro ou remanejar o habilitado (`resolucoes._remanejar`, ação `passar_uc`). Vários caminhos por caso vão em `opcoes`.
- Aderência do instrutor (`services/aderencia.py`): % da carga horária das UCs técnicas dos cursos da(s) área(s) que ele pode dar
  (sim = 1, em partes = 0,5, sem a certificação exigida = 0; transversais fora; versões da matriz juntas pelo código da UC),
  por curso, área e geral. O que falta vira proposta de PDI (`pdi_itens`); concluir com "habilitar" marca a UC como sim.
  Perfil do instrutor: `GET /api/instrutores/{id}/perfil` (abas: visão geral, competências e certificações — editáveis ali —,
  aderência e PDI). Lista em cartões com `GET /api/instrutores/resumo` (semestre, UCs, certificações, termo, PDI, alertas e ações).
  O mesmo perfil vai ao portal (`GET /api/portal/perfil`, `/api/portal/pdi`, só leitura); o instrutor registra formações em
  `POST /api/portal/formacoes`: habilita as UCs na hora (`aderencia.marcar_competencia`), conclui o item do PDI e cria observação
  tipo `formacao` para a coordenação. Índice por área da equipe em `aderencia.equipe()["por_area"]`.
- Modalidade: mensalista = jornada semanal fixa (teto de 90%); horista = termo de horas mensal (`termos_horas`, `services/termos.py`:
  horas de aula do mês e, opcional, dias da semana). O termo é ajustável numa urgência com a concordância do instrutor
  (`termos.ajustar`, ação `ajustar_termo`), então aula fora do termo é ALERTA (TERMO_HORAS_MES / TERMO_FORA_DOS_DIAS); o que impede
  é estar ocupado e a carga máxima do contrato. A geração do semestre procura manter o horista no termo; simulação e previsão de
  turmas ignoram o termo; a ocupação é medida sobre o contrato. Mensalista é ocupado primeiro (regra MENSALISTA_PRIMEIRO):
  todos são ocupados; critério `prioridade_mensalista` no solver (hora de horista custa; `equilibrio_carga` por grupo) e
  `planejamento.mensalistas_primeiro` / ordenação de `substituicao.candidatos` nas listas de instrutores. Termo só no perfil do instrutor (a antiga aba "Disponibilidade e termos de horas" saiu de Instrutores).
  Termo feito no fim do mês para o mês seguinte (regra TERMO_MES_SEGUINTE): `termos.painel` (meses + `proximo` com prazo e sugestão — dia fora do
  termo vai para o mês seguinte), aba "Termo de horas" no perfil (`PainelTermo` + `GradeTermo`: mês por semanas, dia × turno M/V/N/S com aula, pl, pj ou urgencia (tempo pago, cores e total) e horário do dia
  em `termos_horas.agenda` — célula {tipo, ini, fim}; horas contadas pelo horário, `HORARIOS_TURNO`; `termos.cobre`/`turno_da_aula` na validação; `dias_semana` derivado para o gerador; editável) e no portal (`GET /api/portal/termos`, só leitura).
- Versão da matriz: cada uma tem sua lista de UCs; em `rascunho` a lista é editável, depois de cadastrada (vigente/encerrada) fica fixa
  (código, nome, carga, modalidade, categoria; incluir/retirar) — `VERSAO_CADASTRADA` em `api/cadastros._regras_uc`; mudar = nova versão.
  UC `modalidade` presencial/ead; EAD só se `cursos.preve_ead`; UC EAD fica fora do gerador e da demanda (risco "ead" no acompanhamento).
- Um instrutor por UC (turma × UC × grupo): `validacao.titular_da_uc` + regra UM_INSTRUTOR_POR_UC (bloqueio; alerta com exceção
  regra_academica; não vale na substituição). O gerador restringe a atividade ao titular. `passar_uc` usa `substituir(..., transferir=True)`.
- Substituições: página `/substituicoes` (busca do instrutor → agenda semanal em cartões via `GET /api/substituicoes/aulas-do-instrutor` →
  clicar na aula abre o pop-up: só a aula, o dia, a UC no período ou tudo →
  `GET /api/substituicoes/candidatos?alocacao_ids=`). Horista fora do termo/disponibilidade = grupo `aprovacao`; `POST /api/substituicoes`
  com `aprovado_supervisao` e `concordancia` relaxa a disponibilidade (exceção "aprovada pela supervisão") e ajusta o termo do mês.
- Riscos: `services/resolucoes.sugerir` dá uma correção por caso (acao para `services/sugestoes.aplicar`); trocar sala e
  remarcar valem também com o horário publicado (ajuste operacional, como a substituição).

## Testes locais
`service postgresql start`; `cd backend && python -m pytest -q`; frontend: `cd frontend && npx tsc --noEmit -p . && npm run build`.
